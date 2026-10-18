"""Pinned full-video comparison; new footage is never used to tune this run."""
import argparse
import hashlib
import json
import math
import time
import zipfile
from pathlib import Path

import cv2
import httpx
from PIL import Image

from scripts.evaluate_camera import fetch,confusion,TemporalGate as StageOneGate
from services.camera import CameraDetector,TemporalGate,DETECTOR_SHA256,FLAME_SHA256,DETECTION_THRESHOLD

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fetch',action='store_true');args=parser.parse_args()
    protocol_path=ROOT/'validation/camera_refinement_protocol.json';protocol=json.loads(protocol_path.read_text())
    assert protocol['smoke_model_sha256']==DETECTOR_SHA256 and protocol['flame_model_sha256']==FLAME_SHA256 and protocol['threshold']==DETECTION_THRESHOLD
    root=ROOT/'data/camera-refinement';root.mkdir(parents=True,exist_ok=True)
    if args.fetch:
        manifest=fetch(protocol,root)
        for dataset in protocol['firesense']:
            archive_path=ROOT/'data/camera-evaluation'/('firesense-'+dataset['kind']+'.zip')
            url='https://zenodo.org/records/836749/files/'+dataset['file']+'?download=1'
            if not archive_path.exists():
                with httpx.stream('GET',url,follow_redirects=True,timeout=120) as response:
                    response.raise_for_status();size=0
                    with archive_path.open('wb') as stream:
                        for chunk in response.iter_bytes():
                            size+=len(chunk)
                            if size>900_000_000:raise ValueError('Archive exceeds limit')
                            stream.write(chunk)
            assert hashlib.sha256(archive_path.read_bytes()).hexdigest()==dataset['sha256']
            with zipfile.ZipFile(archive_path) as archive:
                for member in archive.infolist():
                    if not member.filename.endswith('.avi'):continue
                    parts=Path(member.filename).parts
                    if len(parts)!=2 or parts[0] not in ('pos','neg') or member.file_size>400_000_000:raise ValueError('Unexpected archive member')
                    path=root/'firesense'/dataset['kind']/parts[0]/parts[1];path.parent.mkdir(parents=True,exist_ok=True)
                    data=archive.read(member);path.write_bytes(data)
                    manifest['videos'].append({'name':'firesense_'+dataset['kind']+'_'+path.stem,'path':str(path),'fire':parts[0]=='pos','source':url,'archive_member':member.filename,'sha256':hashlib.sha256(data).hexdigest(),'dataset':'FIRESENSE '+dataset['kind']})
        manifest['protocol_sha256']=hashlib.sha256(protocol_path.read_bytes()).hexdigest()
        (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    else:manifest=json.loads((root/'manifest.json').read_text())
    assert manifest['protocol_sha256']==hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    checkpoint=root/'progress.json';code_sha=hashlib.sha256((ROOT/'services/camera.py').read_bytes()).hexdigest()
    try:previous=json.loads(checkpoint.read_text())
    except (OSError,ValueError):previous={}
    if previous.get('protocol_sha256')!=manifest['protocol_sha256'] or previous.get('model_code_sha256')!=code_sha:previous={}
    detector=CameraDetector();archive_rows=previous.get('archive_rows',[]);clips=previous.get('clips',[]);elapsed=previous.get('elapsed',0.);inferred=previous.get('inferred',0)
    def save_progress():
        temporary=checkpoint.with_suffix('.part')
        temporary.write_text(json.dumps({'protocol_sha256':manifest['protocol_sha256'],'model_code_sha256':code_sha,'completed':len(clips),'total':len(manifest['videos']),'archive_rows':archive_rows,'elapsed':elapsed,'inferred':inferred,'clips':clips}),encoding='utf-8')
        temporary.replace(checkpoint)
    for sample in manifest['samples']:
        assert hashlib.sha256(Path(sample['path']).read_bytes()).hexdigest()==sample['sha256']
        if any(r['source']==sample['source'] and r['sha256']==sample['sha256'] for r in archive_rows):continue
        with Image.open(sample['path']) as image:
            start=time.perf_counter();smoke=detector.smoke.detect(image);flame=detector.flame.detect(image);elapsed+=time.perf_counter()-start;inferred+=1
        archive_rows.append({k:v for k,v in {**sample,'before':any(p['score']>=.5 for p in smoke),'after':any(p['score']>=.5 for p in smoke+flame),'regions':smoke+flame}.items() if k!='path'})
        save_progress()
        if len(archive_rows)%10==0:print('Archive progress',len(archive_rows),'/',len(manifest['samples']),flush=True)
    print('Archive',confusion(archive_rows,'before'),confusion(archive_rows,'after'),flush=True)
    for item in manifest['videos']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
        if any(c['name']==item['name'] and c['sha256']==item['sha256'] for c in clips):continue
        cap=cv2.VideoCapture(item['path']);fps=cap.get(cv2.CAP_PROP_FPS);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not cap.isOpened() or not math.isfinite(fps) or fps<=0:raise ValueError('Invalid video')
        before_gate=StageOneGate();after_gate=TemporalGate();before=[];after=[];samples=[];index=0;last=-1
        while True:
            ok,frame=cap.read()
            if not ok:break
            second=int(index/fps);index+=1
            if second==last:continue
            last=second;image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            start=time.perf_counter();smoke=detector.smoke.detect(image);flame=detector.flame.detect(image);elapsed+=time.perf_counter()-start;inferred+=1
            if before_gate.update(second,smoke):before.append(second)
            alert=after_gate.update(second,smoke+flame)
            if alert:after.append({'second':second,'label':alert['label']})
            samples.append({'second':second,'smoke_score':max((p['score'] for p in smoke),default=0.),'flame_score':max((p['score'] for p in flame),default=0.)})
        cap.release()
        if not index:raise ValueError('No decodable frames '+item['name'])
        clip={k:v for k,v in {**item,'duration_seconds':index/fps,'reported_frames':total,'decoded_frames':index,'decode_status':'complete' if index==total else 'header_count_mismatch','before_alert_seconds':before,'after_alerts':after,'samples':samples}.items() if k!='path'}
        clips.append(clip);print(item['name'],round(index/fps,2),'s before/after',len(before),len(after),flush=True)
        # Incremental evidence survives interruption; it is not an acceptance result until complete.
        save_progress()
    def metrics(group):
        positives=[c for c in group if c['fire']];negatives=[c for c in group if not c['fire']];hours=sum(c['duration_seconds'] for c in negatives)/3600
        result={'clips':len(group),'positive_clips':len(positives),'negative_hours':hours}
        for key,alerts in [('before','before_alert_seconds'),('after','after_alerts')]:
            count=sum(len(c[alerts]) for c in negatives)
            result[key]={'positive_clips_alerted':sum(bool(c[alerts]) for c in positives),'false_alerts':count,'false_alerts_per_hour':count/hours if hours else None,'zero_alert_one_sided_95pct_upper_per_hour':-math.log(.05)/hours if hours and count==0 else None}
        return result
    original={'non_fire_patrolbot_onboard','cleaner','coolerbot','rover','icra','hand_held_camera_wildfire','hand_held_batteries_night'}
    report={'status':'completed','protocol_sha256':manifest['protocol_sha256'],'models':{'smoke_sha256':DETECTOR_SHA256,'flame_sha256':FLAME_SHA256},'archive':{'frames':len(archive_rows),'before':confusion(archive_rows,'before'),'after':confusion(archive_rows,'after')},'all_video':metrics(clips),'new_video':metrics([c for c in clips if c['name'] not in original]),'development_regressions':metrics([c for c in clips if c['name'] in original]),'throughput_fps':inferred/elapsed,'device':detector.device,'limitations':protocol['limitations'],'archive_samples':archive_rows,'video_clips':clips}
    (ROOT/'validation/camera_refinement_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('archive_samples','video_clips')},indent=2),flush=True)


if __name__=='__main__':main()
