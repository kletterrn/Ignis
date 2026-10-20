import hashlib
import queue
import threading
import time
from collections import deque
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import httpx
from PIL import Image, ImageOps
from services.store import utcnow

WEIGHTS_URL = "https://github.com/pyronear/pyro-vision/releases/download/v0.2.0/rexnet1_0x_256-ff0c2ca1.pth"
# Official v0.2.0 asset, pinned by actual SHA256 (the filename suffix is not its SHA256).
WEIGHTS_SHA256 = "e536564ef97d2aed90a7572f08ca752087fc10f7c3544911edca70f473d55fc7"

class Classifier:
    """Historical crop baseline and whole-ROI flame verifier; outputs are uncalibrated."""
    def __init__(self, root="data/models"):
        import torch
        from holocron.models import rexnet1_0x
        from torchvision.transforms import ToTensor, Normalize
        torch.set_num_threads(min(4, torch.get_num_threads()))
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = rexnet1_0x(num_classes=1).eval()
        state = torch.hub.load_state_dict_from_url(WEIGHTS_URL, model_dir=root, map_location="cpu", weights_only=True)
        weights = Path(root) / WEIGHTS_URL.rsplit("/",1)[-1]
        if hashlib.sha256(weights.read_bytes()).hexdigest() != WEIGHTS_SHA256:
            raise ValueError("Model checksum mismatch")
        self.model.load_state_dict(state, strict=True)
        self.model.to(self.device)
        self.to_tensor = ToTensor()
        self.normalize = Normalize([.485,.456,.406],[.229,.224,.225])

    def score(self, image, *, multi_crop=True):
        image=image.convert('RGB')
        crops=[image]
        # Overlapping crops preserve small plumes otherwise lost when a large frame is resized.
        if multi_crop and image.width>=768 and image.height>=512:
            w,h=image.size
            crops.extend(image.crop((int(x*w),int(y*h),int((x+.5)*w),int((y+.5)*h))) for y in (0,.25,.5) for x in (0,.25,.5))
        # Every crop uses the pretrained PyroVision 256x384 input and normalization.
        tensor = self.torch.stack([self.normalize(self.to_tensor(ImageOps.pad(crop,(384,256),method=Image.Resampling.BILINEAR,color=0))) for crop in crops]).to(self.device)
        with self.torch.inference_mode():
            return float(self.model(tensor).sigmoid().max().item())


DETECTOR_URL='https://huggingface.co/pyronear/yolov11s/resolve/fe7d3a0c3710c1c4d61163058182ff7c44e34f31/yolov11s.onnx'
DETECTOR_SHA256='dcf513579615d7b701fbab2d1633d383684fd5885210fb0a46fae8aae29459aa'
DETECTION_THRESHOLD=.5


class SmokeDetector:
    """Official fixed-shape ONNX smoke detector; scores are not probabilities."""
    name='Pyronear YOLO11s 2025-07-22'
    device='ONNX Runtime CPU'
    size=1024
    labels=('smoke',)
    minimum_score=.25

    def __init__(self,root='data/models'):
        import onnxruntime as ort
        path=Path(root)/'yolov11s-20250722.onnx';path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            response=httpx.get(DETECTOR_URL,follow_redirects=True,timeout=120)
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest()!=DETECTOR_SHA256:raise ValueError('Detector checksum mismatch')
            temporary=path.with_suffix('.part');temporary.write_bytes(response.content);temporary.replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=DETECTOR_SHA256:raise ValueError('Detector checksum mismatch')
        options=ort.SessionOptions();options.intra_op_num_threads=4
        self.net=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
        self.input=self.net.get_inputs()[0].name

    def detect(self,image):
        image=image.convert('RGB');w,h=image.size
        views=[(0,0,w,h)]
        if w>=1280 and h>=768:
            views.extend((int(x*w),int(y*h),int((x+.5)*w),int((y+.5)*h)) for y in (0,.25,.5) for x in (0,.25,.5))
        candidates=[]
        for x1,y1,x2,y2 in views:
            for item in self._detect(image.crop((x1,y1,x2,y2))):
                a,b,c,d=item['box']
                candidates.append({**item,'box':[(x1+a*(x2-x1))/w,(y1+b*(y2-y1))/h,(x1+c*(x2-x1))/w,(y1+d*(y2-y1))/h]})
        boxes=[[p['box'][0],p['box'][1],p['box'][2]-p['box'][0],p['box'][3]-p['box'][1]] for p in candidates]
        keep=cv2.dnn.NMSBoxes(boxes,[p['score'] for p in candidates],.25,.45)
        return [candidates[i] for i in np.asarray(keep).reshape(-1)[:20]]

    def _detect(self,image):
        image=image.convert('RGB');w,h=image.size
        ratio=min(self.size/w,self.size/h);rw,rh=round(w*ratio),round(h*ratio)
        xpad,ypad=(self.size-rw)//2,(self.size-rh)//2
        canvas=np.full((self.size,self.size,3),114,dtype='uint8')
        canvas[ypad:ypad+rh,xpad:xpad+rw]=np.asarray(image.resize((rw,rh),Image.Resampling.BILINEAR))
        tensor=canvas.transpose(2,0,1)[None].astype('float32')/255
        output=self.net.run(None,{self.input:tensor})[0]
        anchors=sum((self.size//s)**2 for s in (8,16,32))
        if output.shape!=(1,4+len(self.labels),anchors) or not np.isfinite(output).all():raise ValueError('Unexpected detector output')
        boxes=[];scores=[];classes=[]
        for row in output[0].T:
            cx,cy,bw,bh=row[:4];category=int(np.argmax(row[4:]));score=float(row[4+category])
            if score<self.minimum_score:continue
            x1,y1=max(0,(cx-bw/2-xpad)/ratio),max(0,(cy-bh/2-ypad)/ratio)
            x2,y2=min(w,(cx+bw/2-xpad)/ratio),min(h,(cy+bh/2-ypad)/ratio)
            if x2<=x1 or y2<=y1:continue
            boxes.append([float(x1),float(y1),float(x2-x1),float(y2-y1)]);scores.append(float(score));classes.append(category)
        keep=cv2.dnn.NMSBoxesBatched(boxes,scores,classes,self.minimum_score,.45)
        return [{'box':[boxes[i][0]/w,boxes[i][1]/h,(boxes[i][0]+boxes[i][2])/w,(boxes[i][1]+boxes[i][3])/h],
                 'score':scores[i],'label':self.labels[classes[i]]} for i in np.asarray(keep).reshape(-1)[:20]]

    def score(self,image):
        return max((x['score'] for x in self.detect(image)),default=0.)


FLAME_URL='https://huggingface.co/fiacecson20/cctv-ai-fire-smoke/resolve/343990e42d99a5d27e9f35fc7c80880dc5f43f45/best.onnx'
FLAME_SHA256='f2699b753e78be8d392bfa63e64bf102ea3ceb8b6086a59dfd8192b61a0c6fad'
FLAME_THRESHOLD=.5
VERIFIER_THRESHOLD=.8


class FlameDetector(SmokeDetector):
    """Independent flame branch; this model's weaker smoke class is not used."""
    size=320
    labels=('fire','smoke')
    minimum_score=FLAME_THRESHOLD
    name='CCTV-AI YOLOv8n flame 2026-05-05'

    def __init__(self,root='data/models'):
        import onnxruntime as ort
        path=Path(root)/'fire-smoke-yolov8n.onnx';path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            response=httpx.get(FLAME_URL,follow_redirects=True,timeout=120);response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest()!=FLAME_SHA256:raise ValueError('Flame detector checksum mismatch')
            temporary=path.with_suffix('.part');temporary.write_bytes(response.content);temporary.replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=FLAME_SHA256:raise ValueError('Flame detector checksum mismatch')
        options=ort.SessionOptions();options.intra_op_num_threads=4
        self.net=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider']);self.input=self.net.get_inputs()[0].name
        self.verifier=Classifier(root)
        self.device='ONNX Runtime CPU + ReXNet '+self.verifier.device

    def detect(self,image):
        confirmed=[];w,h=image.size
        for p in self._detect(image):
            if p['label']!='fire':continue
            x,y,a,b=p['box'];dx=(a-x)*.25;dy=(b-y)*.25
            crop=image.convert('RGB').crop((max(0,round((x-dx)*w)),max(0,round((y-dy)*h)),min(w,round((a+dx)*w)),min(h,round((b+dy)*h))))
            score=self.verifier.score(crop,multi_crop=False)
            if not np.isfinite(score):raise ValueError('Unexpected flame verification output')
            if score>=VERIFIER_THRESHOLD:confirmed.append({**p,'verification_score':score,'verification_model':'PyroVision ReXNet whole ROI'})
        return confirmed


class CameraDetector:
    name='Pyronear smoke + CCTV-AI flame + ReXNet ROI confirmation'
    device='ONNX Runtime CPU'

    def __init__(self,root='data/models'):
        self.smoke=SmokeDetector(root);self.flame=FlameDetector(root)
        self.device=self.flame.device

    def detect(self,image):return self.smoke.detect(image)+self.flame.detect(image)

    def score(self,image):return max((p['score'] for p in self.detect(image)),default=0.)


def overlap(a,b):
    x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]))
    intersection=x*y
    return intersection/max((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection,1e-12)


class TemporalGate:
    """Five of eight spatially consistent samples; one alert until 30 clear seconds."""
    def __init__(self):
        self.history=deque(maxlen=8);self.hits=0;self.previous=None
        self.latched=False;self.last_positive=None

    def update(self,second,regions):
        if self.previous is not None and (second<=self.previous or second-self.previous>6):
            self.history.clear()
        self.previous=second
        candidates=[p for p in regions if p['score']>=DETECTION_THRESHOLD]
        self.history.append((second,candidates));self.hits=0
        if not candidates:
            if self.last_positive is not None and second-self.last_positive>=30:self.latched=False
            return None
        self.last_positive=second
        for item in sorted(candidates,key=lambda p:p['score'],reverse=True):
            matches=[t for t,items in self.history if any(p.get('label','smoke')==item.get('label','smoke') and overlap(p['box'],item['box'])>=.1 for p in items)]
            self.hits=max(self.hits,len(matches))
            if len(matches)>=5 and second-min(matches)>=4 and not self.latched:
                self.latched=True
                return item
        return None

class CameraWorker:
    def __init__(self, store, root):
        self.store, self.root = store, Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.classifier = None
        # Interrupted work is explicit and resumable through its persisted job.
        for job in store.all("jobs"):
            if job["status"] in ("running", "starting", "reconnecting"):
                job["status"] = "interrupted"
                store.put("jobs", job)

    def start(self, source, kind="video", job_id=None, acquired_at=None):
        if kind not in ("video", "rtsp", "sequence"):
            raise ValueError("Unsupported source kind")
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("One stream is already running")
            self.stop_event.clear()
            job = self.store.get("jobs", job_id) if job_id else None
            job = job or {"id":uuid4().hex,"source":source,"kind":kind,"frames":0,"seconds":0,"created_at":utcnow(),"acquired_at":acquired_at,"status":"starting"}
            self.store.put("jobs",job)
            self.thread = threading.Thread(target=self.run,args=(job,),daemon=True)
            self.thread.start()
        return job["id"]

    def stop(self):
        self.stop_event.set()

    def run(self, job):
        frames = queue.Queue(maxsize=2)
        capture_done = threading.Event()
        producer_error = []
        job.setdefault('dropped_frames',0)
        def capture():
            cap = None
            stream_started=time.monotonic();stream_offset=job.get('seconds',0)
            try:
                if job["kind"] == "sequence":
                    paths = sorted(Path(job["source"]).glob("*"))
                    for i,path in enumerate(paths):
                        if self.stop_event.is_set(): break
                        if i < job["frames"]: continue
                        with Image.open(path) as im: image=im.convert("RGB")
                        while not self.stop_event.is_set():
                            try: frames.put((float(i),image),timeout=.5); break
                            except queue.Full: pass
                    return
                backoff = 1
                while not self.stop_event.is_set():
                    cap = cv2.VideoCapture()
                    cap.open(job["source"], cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,10000,cv2.CAP_PROP_READ_TIMEOUT_MSEC,10000])
                    if not cap.isOpened():
                        if job["kind"] != "rtsp": raise ValueError("Video could not be opened")
                        job["status"]="reconnecting"; self.store.put("jobs",job)
                        if self.stop_event.wait(backoff): break
                        backoff=min(30,backoff*2); continue
                    job["status"]="running"; self.store.put("jobs",job)
                    fps = cap.get(cv2.CAP_PROP_FPS) or 25
                    declared_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if job['kind']!='rtsp' else 0
                    index = int(job.get("seconds",0)*fps) if job["kind"] != "rtsp" else 0
                    if index: cap.set(cv2.CAP_PROP_POS_FRAMES,index)
                    last = -1
                    while not self.stop_event.is_set():
                        ok,frame = cap.read()
                        if not ok: break
                        second = int(stream_offset+time.monotonic()-stream_started) if job["kind"] == "rtsp" else int(index/fps)
                        index+=1
                        if second == last: continue
                        last=second
                        image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                        if job["kind"] == "rtsp":
                            try: frames.put_nowait((float(second),image))
                            except queue.Full: job['dropped_frames']+=1
                        else:
                            while not self.stop_event.is_set():
                                try: frames.put((float(second),image),timeout=.5); break
                                except queue.Full: pass
                    cap.release()
                    if job['kind']!='rtsp' and not self.stop_event.is_set():
                        job.update(decoded_frames=index,declared_frames=declared_frames)
                        if declared_frames>0 and declared_frames!=index:
                            job['decode_warning']=f'Dateikopf: {declared_frames} Frames; dekodiert: {index}. Abdeckung des Dateiendes unsicher.'
                    if job["kind"] != "rtsp": break
                    if self.stop_event.wait(backoff): break
            except Exception:
                producer_error.append("Media read failed; check source and format")
            finally:
                if cap is not None: cap.release()
                capture_done.set()
        try:
            self.classifier = self.classifier or CameraDetector()
            producer=threading.Thread(target=capture,daemon=True);producer.start()
            gate=TemporalGate()
            started=time.perf_counter();initial_frames=job['frames']
            while not (capture_done.is_set() and frames.empty()) and not self.stop_event.is_set():
                try: second,image=frames.get(timeout=.5)
                except queue.Empty: continue
                regions=self.classifier.detect(image)
                score=max((p['score'] for p in regions),default=0.)
                alert=gate.update(second,regions)
                preview=self.root/(job['id']+'_current.jpg')
                annotated=image.copy()
                from PIL import ImageDraw
                draw=ImageDraw.Draw(annotated)
                for region in regions:
                    if region['score']<DETECTION_THRESHOLD:continue
                    a,b,c,d=region['box'];box=(a*image.width,b*image.height,c*image.width,d*image.height)
                    draw.rectangle(box,outline='#ff8833',width=3);draw.text((box[0],box[1]),f"{region.get('label','smoke')} {region['score']:.2f}",fill='#ff8833')
                annotated.save(preview,quality=85)
                job['preview_path']=str(preview)
                job.update(frames=job["frames"]+1,seconds=second+1,score=score,regions=regions,model=self.classifier.name,confirmation_samples=gate.hits,
                           alert_latched=gate.latched,device=self.classifier.device,status="running",updated_at=utcnow(),throughput_fps=(job["frames"]-initial_frames)/max(time.perf_counter()-started,.001))
                self.store.put("jobs",job)
                if alert:
                    key=hashlib.sha256(f"{job['id']}:{second:.6f}:{alert.get('label','smoke')}".encode()).hexdigest()[:32]
                    path=self.root/(key+".jpg");annotated.save(path,quality=90)
                    self.store.put("evidence",{"id":key,"job_id":job["id"],"observed_at":utcnow(),"acquired_at":job.get("acquired_at"),"offset_seconds":second,"model_score":alert['score'],"model":self.classifier.name,"regions":regions,"path":str(path),"review_state":"pending","georeferenced":False,"trigger":"spatial_temporal_"+alert.get('label','smoke')})
            was_stopped=self.stop_event.is_set()
            self.stop_event.set();producer.join(timeout=12)
            job["status"]="failed" if producer_error else "stopped" if was_stopped else "completed"
            if producer_error: job["error"]=producer_error[0]
        except Exception:
            self.stop_event.set()
            job.update(status="failed",error="Inference unavailable; inspect local model installation and source")
        job["updated_at"]=utcnow();self.store.put("jobs",job)
