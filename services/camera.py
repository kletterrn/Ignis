import hashlib
import queue
import threading
import time
from pathlib import Path
from uuid import uuid4

import cv2
from PIL import Image, ImageOps
from services.store import utcnow

WEIGHTS_URL = "https://github.com/pyronear/pyro-vision/releases/download/v0.2.0/rexnet1_0x_256-ff0c2ca1.pth"
# Official v0.2.0 asset, pinned by actual SHA256 (the filename suffix is not its SHA256).
WEIGHTS_SHA256 = "e536564ef97d2aed90a7572f08ca752087fc10f7c3544911edca70f473d55fc7"

class Classifier:
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

    def score(self, image):
        image=image.convert('RGB')
        crops=[image]
        # Overlapping crops preserve small plumes otherwise lost when a large frame is resized.
        if image.width>=768 and image.height>=512:
            w,h=image.size
            crops.extend(image.crop((int(x*w),int(y*h),int((x+.5)*w),int((y+.5)*h))) for y in (0,.25,.5) for x in (0,.25,.5))
        # Every crop uses the pretrained PyroVision 256x384 input and normalization.
        tensor = self.torch.stack([self.normalize(self.to_tensor(ImageOps.pad(crop,(384,256),method=Image.Resampling.BILINEAR,color=0))) for crop in crops]).to(self.device)
        with self.torch.inference_mode():
            return float(self.model(tensor).sigmoid().max().item())

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
        def capture():
            cap = None
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
                    index = int(job.get("seconds",0)*fps) if job["kind"] != "rtsp" else 0
                    if index: cap.set(cv2.CAP_PROP_POS_FRAMES,index)
                    last = -1
                    started = time.monotonic()
                    while not self.stop_event.is_set():
                        ok,frame = cap.read()
                        if not ok: break
                        second = int(time.monotonic()-started) if job["kind"] == "rtsp" else int(index/fps)
                        index+=1
                        if second == last: continue
                        last=second
                        image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                        if job["kind"] == "rtsp":
                            try: frames.put_nowait((float(second),image))
                            except queue.Full: pass
                        else:
                            while not self.stop_event.is_set():
                                try: frames.put((float(second),image),timeout=.5); break
                                except queue.Full: pass
                    cap.release()
                    if job["kind"] != "rtsp": break
                    if self.stop_event.wait(backoff): break
            except Exception:
                producer_error.append("Media read failed; check source and format")
            finally:
                if cap is not None: cap.release()
                capture_done.set()
        try:
            self.classifier = self.classifier or Classifier()
            producer=threading.Thread(target=capture,daemon=True);producer.start()
            hits, last_alert, previous_second = 0, -60., None
            started=time.perf_counter();initial_frames=job['frames']
            while not (capture_done.is_set() and frames.empty()) and not self.stop_event.is_set():
                try: second,image=frames.get(timeout=.5)
                except queue.Empty: continue
                score=self.classifier.score(image)
                preview=self.root/(job['id']+'_current.jpg')
                image.save(preview,quality=85)
                job['preview_path']=str(preview)
                if previous_second is None or second-previous_second > 2: hits=0
                previous_second=second
                hits=hits+1 if score >= .7 else 0
                job.update(frames=job["frames"]+1,seconds=second+1,score=score,device=self.classifier.device,status="running",updated_at=utcnow(),throughput_fps=(job["frames"]-initial_frames+1)/max(time.perf_counter()-started,.001))
                self.store.put("jobs",job)
                if hits >= 3 and second-last_alert >= 60:
                    key=hashlib.sha256(f"{job['id']}:{int(second)//60}".encode()).hexdigest()[:32]
                    path=self.root/(key+".jpg");image.save(path,quality=90)
                    self.store.put("evidence",{"id":key,"job_id":job["id"],"observed_at":utcnow(),"acquired_at":job.get("acquired_at"),"offset_seconds":second,"model_score":score,"model":"PyroVision ReXNet v0.2.0","path":str(path),"review_state":"pending","georeferenced":False})
                    last_alert=second
            was_stopped=self.stop_event.is_set()
            self.stop_event.set();producer.join(timeout=12)
            job["status"]="failed" if producer_error else "stopped" if was_stopped else "completed"
            if producer_error: job["error"]=producer_error[0]
        except Exception:
            self.stop_event.set()
            job.update(status="failed",error="Inference unavailable; inspect local model installation and source")
        job["updated_at"]=utcnow();self.store.put("jobs",job)
