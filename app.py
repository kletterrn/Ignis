import json
import base64
import io
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from providers.nasa_firms import AREA, SATELLITE_SOURCES
from services.collector import collect, flush_outbox
from services.geometry import compare, measure, polygon, timestamp
from services.store import Store, utcnow

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=256*1024*1024, DATA_DIR=str(BASE_DIR/"data"))
store = Store(Path(app.config["DATA_DIR"])/"ignis.sqlite")
CSRF = secrets.token_urlsafe(32)
worker = None
collection_lock = threading.Lock()

def local_request():
    return request.remote_addr in ("127.0.0.1", "::1") and request.host.split(":")[0] in ("127.0.0.1", "localhost", "[", "testserver")

@app.before_request
def protect_operator():
    if request.path.startswith(("/operator", "/api/operator")):
        if not local_request():
            return jsonify(error="Local operator access only"),403
        if request.method != "GET":
            origin=request.headers.get("Origin")
            if (origin and urlparse(origin).netloc != request.host) or request.headers.get("Sec-Fetch-Site") == "cross-site" or not secrets.compare_digest(request.headers.get("X-Ignis-CSRF",""),CSRF):
                return jsonify(error="Invalid request origin or CSRF token"),403

@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="same-origin"
    response.headers["X-Frame-Options"]="DENY"
    if request.path.startswith(("/operator","/api/operator")):
        response.headers["Cache-Control"]="no-store"
    return response

@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description),exc.code
    if isinstance(exc,(ValueError,KeyError,TypeError)):
        return jsonify(error=str(exc)[:300]),400
    app.logger.error("Local operation failed: %s",type(exc).__name__)
    return jsonify(error="Operation failed. Check local configuration and input files."),500

@app.get("/")
@app.get("/operator")
def index():
    operator=request.path=="/operator"
    return render_template("index.html",config_data={"source":"VIIRS_NOAA21_NRT","sources":SATELLITE_SOURCES,"area":AREA,"view":{"bounds":[[5.8,47.2],[15.1,55.1]]},"cartoKey":"","operator":operator,"csrf":CSRF if operator else None})

@app.get("/api/observations")
def observations_api():
    hours=request.args.get("hours","24")
    if hours not in ("1","6","12","24"):
        raise ValueError("Choose 1, 6, 12 or 24 hours")
    sources=list(dict.fromkeys(request.args.get("sources","VIIRS_NOAA21_NRT").split(",")))
    if any(x not in SATELLITE_SOURCES for x in sources):
        raise ValueError("Unsupported satellite source")
    now=datetime.now(timezone.utc)
    records=[x for x in store.all("observations") if x["dataset"] in sources and now-timedelta(hours=int(hours)) <= timestamp(x["acquired_at"]) <= now]
    states=[store.get("sources",x) or {"id":x,"label":SATELLITE_SOURCES[x],"status":"configuration_missing","count":0} for x in sources]
    for state in states:
        if state.get("last_success_at") and now-timestamp(state["last_success_at"]) > timedelta(minutes=45): state["status"]="stale"
    good=sum(x["status"]=="connected" for x in states)
    return jsonify(observations=sorted(records,key=lambda x:x["acquired_at"],reverse=True),sources=states,status="connected" if good==len(states) else "partial" if good else "configuration_missing" if all(x["status"]=="configuration_missing" for x in states) else "unavailable",checked_at=max((x.get("checked_at","") for x in states),default="") or None,hours=int(hours),source=",".join(sources),area=AREA,message="Persistierte Beobachtungen · Feedstatus beachten")

@app.get("/api/v1/<resource>")
def public_api(resource):
    if resource=="health":
        return jsonify(sources=store.all("sources"),checked_at=utcnow())
    if resource=="weather": return jsonify(weather=store.all("weather"))
    if resource=="incidents": return jsonify(incidents=[{k:v for k,v in x.items() if k!='evidence_ids'} for x in store.all("incidents") if x.get("review_state")=="published"])
    if resource=="evidence":
        return jsonify(evidence=[{"id":key,"incident_id":item['id']} for item in store.all('incidents') if item.get('review_state')=='published' for key in item.get('evidence_ids',[])[:5]])
    if resource=="perimeters":
        ids={x["id"] for x in store.all("incidents") if x.get("review_state")=="published"}
        return jsonify(perimeters=[x for x in store.all("perimeters") if x["incident_id"] in ids and x["review_state"]=="approved"])
    return jsonify(error="Not found"),404

@app.get("/health")
def health(): return jsonify(status="ok",name="Project Ignis")

@app.get('/api/v1/evidence/<key>')
def public_evidence(key):
    if not any(item.get('review_state')=='published' and key in item.get('evidence_ids',[])[:5] for item in store.all('incidents')):return jsonify(error='Not found'),404
    record=store.get('evidence',key)
    if not record:return jsonify(error='Not found'),404
    from PIL import Image
    with Image.open(record['path']) as image:
        image=image.convert('RGB');image.thumbnail((512,512));buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=80)
    buffer.seek(0)
    return send_file(buffer,mimetype='image/jpeg')

@app.get("/api/operator/state")
def state():
    jobs=[{k:v for k,v in x.items() if k not in ("source","preview_path")} for x in store.all("jobs")]
    evidence=[{k:v for k,v in x.items() if k!="path"} for x in store.all("evidence")]
    return jsonify(incidents=store.all("incidents"),perimeters=store.all("perimeters"),jobs=jobs,evidence=evidence,outbox=[{"id":x["id"],"error":x["error"]} for x in store.pending()])

@app.post("/api/operator/collect")
def collect_api():
    if not collection_lock.acquire(blocking=False): return jsonify(status="running"),202
    def run():
        try: collect(store,os.getenv("FIRMS_MAP_KEY",""),os.getenv("FIRMS_AREA",AREA))
        finally: collection_lock.release()
    threading.Thread(target=run,daemon=True).start()
    return jsonify(status="started"),202

@app.post("/api/operator/incidents")
def incident_api():
    data=request.get_json()
    title=str(data["title"]).strip()
    if not title or len(title)>120: raise ValueError("Title required; maximum 120 characters")
    item={"id":uuid4().hex,"title":title,"created_at":utcnow(),"updated_at":utcnow(),"review_state":"draft","evidence_ids":data.get("evidence_ids",[]),"description":str(data.get("description",""))[:2000]}
    if not isinstance(item["evidence_ids"],list) or any(not store.get("evidence",x) for x in item["evidence_ids"]): raise ValueError("Unknown evidence")
    store.put("incidents",item)
    return jsonify(item),201

@app.post("/api/operator/incidents/<key>/<action>")
def review_incident(key,action):
    item=store.get("incidents",key)
    if not item: return jsonify(error="Not found"),404
    if action not in ("publish","withdraw"): raise ValueError("Unsupported review action")
    item.update(review_state="published" if action=="publish" else "withdrawn",updated_at=utcnow())
    perimeters=[x for x in store.all("perimeters") if x["incident_id"]==key and x["review_state"]=="approved"]
    if action=="publish" and not perimeters: raise ValueError("Approve a georeferenced boundary before public publication")
    store.put("incidents",item)
    public_item={k:v for k,v in item.items() if k!="evidence_ids"}
    evidence=[]
    if action=="publish":
        from PIL import Image
        for evidence_id in item.get("evidence_ids",[])[:5]:
            record=store.get("evidence",evidence_id)
            if not record: continue
            with Image.open(record["path"]) as image:
                image=image.convert("RGB");image.thumbnail((512,512))
                buffer=io.BytesIO();image.save(buffer,format="JPEG",quality=80)
            evidence.append({"id":evidence_id,"incident_id":key,"jpeg":base64.b64encode(buffer.getvalue()).decode()})
    store.queue({"incidents":[public_item],"perimeters":perimeters if action=="publish" else [],"evidence":evidence})
    return jsonify(flush_outbox(store))

@app.post("/api/operator/perimeters")
def perimeter_api():
    data=request.get_json()
    if not store.get("incidents",data["incident_id"]): raise ValueError("Unknown incident")
    timestamp(data["acquired_at"])
    data["acquired_at"]=timestamp(data['acquired_at']).astimezone(timezone.utc).isoformat()
    geometry=measure(data["geometry"])
    coverage=polygon(data["coverage"])
    if not coverage.covers(polygon(geometry["geometry"])): raise ValueError("Boundary must be inside observed coverage")
    item={**geometry,"id":uuid4().hex,"incident_id":data["incident_id"],"acquired_at":data["acquired_at"],"created_at":utcnow(),"coverage":data["coverage"],"method":str(data.get("method","manual"))[:80],"resolution_m":data.get("resolution_m"),"footprint_kind":data.get("footprint_kind","burned"),"review_state":"draft","provenance":str(data.get("provenance","Operator tracing"))[:500]}
    if item["footprint_kind"] not in ("burned","active"): raise ValueError("Choose burned or active footprint")
    if item["resolution_m"] is not None and not 0 < float(item["resolution_m"]) <= 1000: raise ValueError("Invalid resolution")
    if item["resolution_m"] is not None: item["resolution_m"]=float(item["resolution_m"])
    store.put("perimeters",item)
    return jsonify(item),201

@app.post("/api/operator/perimeters/<key>/approve")
def approve_perimeter(key):
    item=store.get("perimeters",key)
    if not item: return jsonify(error="Not found"),404
    item.update(review_state="approved",reviewed_at=utcnow())
    return jsonify(store.put("perimeters",item))

@app.post("/api/operator/compare")
def compare_api():
    data=request.get_json()
    a,b=store.get("perimeters",data["before"]),store.get("perimeters",data["after"])
    if not a or not b or a["incident_id"]!=b["incident_id"]: raise ValueError("Choose two boundaries of the same incident")
    result=compare(a,b)
    b["change"]=result;store.put("perimeters",b)
    return jsonify(result)

@app.post("/api/operator/sync")
def sync_api(): return jsonify(flush_outbox(store))

@app.post("/api/operator/upload")
def upload_api():
    files=request.files.getlist("file")
    if not files or len(files)>300: raise ValueError("Choose 1–300 files")
    key=uuid4().hex;root=Path(app.config["DATA_DIR"])/"uploads"/key;root.mkdir(parents=True)
    paths=[]
    allowed={".mp4",".avi",".mov",".mkv",".jpg",".jpeg",".png",".tif",".tiff",".geojson",".json"}
    for i,f in enumerate(files):
        suffix=Path(f.filename).suffix.lower()
        if suffix not in allowed: raise ValueError("Unsupported file type")
        path=root/(f"{i:05d}"+suffix);f.save(path);paths.append(str(path))
    record={"id":key,"paths":paths,"created_at":utcnow()}
    store.put("uploads",record)
    result={"id":key,"count":len(paths)}
    if len(paths)==1 and Path(paths[0]).suffix in (".tif",".tiff"):
        from services.imagery import inspect_orthomosaic
        record["raster"]=inspect_orthomosaic(paths[0]);store.put("uploads",record)
        result["raster"]={k:v for k,v in record["raster"].items() if k!="preview"}
    if len(paths)==1 and Path(paths[0]).suffix in (".json",".geojson"):
        if Path(paths[0]).stat().st_size>1_000_000: raise ValueError("GeoJSON limit 1 MB")
        result.update(measure(json.loads(Path(paths[0]).read_text(encoding="utf-8"))))
    return jsonify(result),201

@app.get("/api/operator/assets/<kind>/<key>")
def asset(kind,key):
    if kind=="evidence":
        record=store.get("evidence",key);path=record["path"] if record else None
    elif kind=="raster":
        record=store.get("uploads",key);path=record.get("raster",{}).get("preview") if record else None
    elif kind=="job":
        record=store.get("jobs",key);path=record.get("preview_path") if record else None
    else: path=None
    if not path: return jsonify(error="Not found"),404
    return send_file(path)

@app.post("/api/operator/camera/<action>")
def camera_api(action):
    global worker
    from services.camera import CameraWorker
    worker=worker or CameraWorker(store,Path(app.config["DATA_DIR"])/"evidence")
    if action=="stop": worker.stop();return jsonify(status="stopping")
    data=request.get_json()
    if action=="snapshot":
        job=store.get("jobs",data["id"])
        if not job or not job.get("preview_path"):raise ValueError("No preview available")
        import shutil
        key=uuid4().hex;path=Path(app.config["DATA_DIR"])/"evidence"/(key+'.jpg')
        path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(job['preview_path'],path)
        item={"id":key,"job_id":job['id'],"observed_at":utcnow(),"acquired_at":job.get('acquired_at'),"offset_seconds":job.get('seconds',0),"model_score":job.get('score',0),"model":"PyroVision ReXNet v0.2.0","path":str(path),"review_state":"pending","georeferenced":False,"trigger":"operator"}
        return jsonify(store.put('evidence',item)),201
    if action=="resume":
        job=store.get("jobs",data["id"])
        if not job: raise ValueError("Unknown job")
        return jsonify(id=worker.start(job["source"],job["kind"],job_id=job["id"]))
    if action!="start": raise ValueError("Unsupported action")
    if data.get("rtsp"):
        source=data["rtsp"]
        if urlparse(source).scheme not in ("rtsp","rtsps"): raise ValueError("RTSP source required")
        kind="rtsp"
    else:
        upload=store.get("uploads",data["upload_id"])
        if not upload: raise ValueError("Unknown upload")
        kind="sequence" if len(upload["paths"])>1 else "video"
        source=str(Path(upload["paths"][0]).parent) if kind=="sequence" else upload["paths"][0]
    acquired=data.get("acquired_at")
    if acquired: timestamp(acquired)
    return jsonify(id=worker.start(source,kind,acquired_at=acquired)),202

@app.post("/api/operator/imagery/<action>")
def imagery_api(action):
    from services.imagery import search_scenes, download_scene, burned_outline
    data=request.get_json()
    if action=="search": return jsonify(scenes=search_scenes(data["bbox"],data["start"],data["end"]))
    if action=="download":
        key=uuid4().hex;root=Path(app.config["DATA_DIR"])/"uploads"/key;root.mkdir(parents=True)
        path=download_scene(data["bbox"],data["acquired_at"],root/"scene.tif")
        store.put("uploads",{"id":key,"paths":[path],"acquired_at":data["acquired_at"],"created_at":utcnow()})
        return jsonify(id=key)
    if action=="outline":
        pre,post=store.get("uploads",data["before"]),store.get("uploads",data["after"])
        if not pre or not post: raise ValueError("Choose before and after raster uploads")
        result=burned_outline(pre["paths"][0],post["paths"][0],float(data.get("threshold",.2)))
        result["acquired_at"]=post.get("acquired_at")
        result["provenance"]=f"Before upload {pre['id']}; after upload {post['id']}"
        return jsonify(result)
    raise ValueError("Unsupported action")

if __name__=="__main__":
    from services.camera import CameraWorker
    worker=CameraWorker(store,Path(app.config["DATA_DIR"])/"evidence")
    app.run(host="127.0.0.1",port=int(os.getenv("PORT","8000")),debug=False)
