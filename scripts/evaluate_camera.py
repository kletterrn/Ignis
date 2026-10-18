"""Frozen-protocol real camera/video comparison; no production publication."""
import argparse
import hashlib
import json
import math
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote,unquote

import cv2
import httpx
from PIL import Image
from services.camera import Classifier,SmokeDetector,DETECTION_THRESHOLD,DETECTOR_SHA256,overlap

class TemporalGate:
    """Five spatially consistent samples; one review alert until 30 clear seconds."""
    def __init__(self):
        self.box=None;self.hits=0;self.first=None;self.previous=None
        self.latched=False;self.last_positive=None

    def update(self,second,regions):
        if self.previous is not None and (second<=self.previous or second-self.previous>6):
            self.hits=0;self.box=None;self.first=None
        self.previous=second
        candidates=[p for p in regions if p['score']>=DETECTION_THRESHOLD]
        if not candidates:
            self.hits=0;self.box=None;self.first=None
            if self.last_positive is not None and second-self.last_positive>=30:self.latched=False
            return None
        matched=[p for p in candidates if self.box is not None and overlap(self.box,p['box'])>=.1]
        item=max(matched or candidates,key=lambda p:p['score'])
        if not matched:self.hits=0;self.first=second
        self.hits+=1;self.box=item['box'];self.last_positive=second
        if self.hits>=5 and second-self.first>=4 and not self.latched:
            self.latched=True
            return item
        return None


ROOT=Path(__file__).resolve().parents[1]


def download(client,url,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        response=client.get(url);response.raise_for_status();path.write_bytes(response.content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(protocol,root):
    samples=[];videos=[]
    with httpx.Client(timeout=120,follow_redirects=True) as client:
        for event in protocol['archive_holdout']:
            base='https://cdn.hpwren.ucsd.edu/HPWREN-FIgLib-Data/'+event+'/'
            html=client.get(base+'index.html').raise_for_status().text
            names=list(dict.fromkeys(re.findall(r'href=([0-9]+_[+-][0-9]+\.jpg)',unquote(html))))
            selected=[]
            for sign in ('_-','_+'):
                group=[n for n in names if sign in n][::protocol['archive_stride']]
                if not group:raise ValueError('Missing label group for '+event)
                selected+=group
            for name in selected:
                path=root/event/name;sha=download(client,base+quote(name),path)
                samples.append({'event':event,'path':str(path),'source':base+quote(name),'label':int('_+' in name),'offset_seconds':int(name.split('_')[1].split('.')[0]),'sha256':sha})
            print('Fetched holdout:',event,len(selected),'frames',flush=True)
        for item in protocol['continuous_video']:
            name=item['name'];base=f"https://raw.githubusercontent.com/steffensbola/furg-fire-dataset/{protocol['video_revision']}/"
            path=root/'furg'/(name+'.mp4');sha=download(client,base+name+'.mp4',path)
            xml=path.with_suffix('.xml');download(client,base+item.get('annotation_name',name+'.xml'),xml)
            annotations=ET.parse(xml).findall('./frames/_')
            fire_frames=sum(bool(frame.find('annotations').findall('_')) for frame in annotations)
            if bool(fire_frames)!=item['fire']:raise ValueError('Video label disagrees with source annotation')
            videos.append({**item,'path':str(path),'source':base+name+'.mp4','sha256':sha,'source_annotated_fire_frames':fire_frames})
            print('Fetched video:',name,flush=True)
    manifest={'samples':samples,'videos':videos}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def confusion(rows,key):
    tp=sum(r['label']==1 and r[key] for r in rows);fp=sum(r['label']==0 and r[key] for r in rows)
    fn=sum(r['label']==1 and not r[key] for r in rows);tn=sum(r['label']==0 and not r[key] for r in rows)
    return {'tp':tp,'fp':fp,'fn':fn,'tn':tn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fetch',action='store_true');parser.add_argument('--output',default='validation/camera_results.json');args=parser.parse_args()
    protocol_path=ROOT/'validation/camera_protocol.json';protocol=json.loads(protocol_path.read_text())
    assert protocol['threshold']==DETECTION_THRESHOLD and protocol['model_sha256']==DETECTOR_SHA256
    root=ROOT/'data/camera-evaluation';root.mkdir(parents=True,exist_ok=True)
    manifest=fetch(protocol,root) if args.fetch else json.loads((root/'manifest.json').read_text())
    detector=SmokeDetector();legacy=Classifier();rows=[];timing={'before':0.,'after':0.};counts={'before':0,'after':0}
    for event in protocol['archive_holdout']:
        group=[]
        for sample in [s for s in manifest['samples'] if s['event']==event]:
            path=Path(sample['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==sample['sha256']
            with Image.open(path) as image:
                start=time.perf_counter();before=legacy.score(image);timing['before']+=time.perf_counter()-start;counts['before']+=1
                start=time.perf_counter();regions=detector.detect(image);timing['after']+=time.perf_counter()-start;counts['after']+=1
            score=max((p['score'] for p in regions),default=0.)
            group.append({k:v for k,v in {**sample,'before_score':before,'after_score':score,'before':before>=.7,'after':score>=DETECTION_THRESHOLD,'regions':regions}.items() if k!='path'})
        rows+=group
        print('Holdout',event,'before',confusion(group,'before'),'after',confusion(group,'after'),flush=True)
    clips=[]
    for item in manifest['videos']:
        path=Path(item['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        cap=cv2.VideoCapture(str(path));fps=cap.get(cv2.CAP_PROP_FPS);total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not cap.isOpened() or not math.isfinite(fps) or fps<=0:raise ValueError('Invalid video')
        duration=total/fps;gate=TemporalGate();index=0;last=-1;hits=0;last_legacy=-60;before_alerts=[];after_alerts=[];samples=0;regions_seen=0
        while True:
            ok,frame=cap.read()
            if not ok:break
            second=int(index/fps);index+=1
            if second==last:continue
            last=second;samples+=1;image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            start=time.perf_counter();before=legacy.score(image);timing['before']+=time.perf_counter()-start;counts['before']+=1
            hits=hits+1 if before>=.7 else 0
            if hits>=3 and second-last_legacy>=60:before_alerts.append(second);last_legacy=second
            start=time.perf_counter();regions=detector.detect(image);timing['after']+=time.perf_counter()-start;counts['after']+=1
            regions_seen+=int(any(p['score']>=DETECTION_THRESHOLD for p in regions))
            if gate.update(second,regions):after_alerts.append(second)
        cap.release()
        if index!=total:raise ValueError('Truncated video: '+item['name'])
        clips.append({k:v for k,v in {**item,'duration_seconds':duration,'sampled_frames':samples,'detected_frames':regions_seen,'before_alert_seconds':before_alerts,'after_alert_seconds':after_alerts}.items() if k!='path'})
        print('Video',item['name'],'seconds',round(duration,2),'alerts before/after',len(before_alerts),len(after_alerts),flush=True)
    negative=[c for c in clips if not c['fire']];hours=sum(c['duration_seconds'] for c in negative)/3600
    before_false=sum(len(c['before_alert_seconds']) for c in negative);after_false=sum(len(c['after_alert_seconds']) for c in negative)
    report={'protocol_sha256':hashlib.sha256(protocol_path.read_bytes()).hexdigest(),'model_sha256':DETECTOR_SHA256,'threshold':DETECTION_THRESHOLD,
            'archive':{'frames':len(rows),'before':confusion(rows,'before'),'after':confusion(rows,'after'),
                       'events':[{'event':event,'before':confusion([r for r in rows if r['event']==event],'before'),'after':confusion([r for r in rows if r['event']==event],'after')} for event in protocol['archive_holdout']]},
            'continuous_video':{'negative_hours':hours,'before_false_alerts':before_false,'after_false_alerts':after_false,
                                'before_false_alerts_per_hour':before_false/hours,'after_false_alerts_per_hour':after_false/hours,
                                'after_zero_alert_one_sided_95pct_poisson_upper_per_hour':-math.log(.05)/hours if after_false==0 else None,
                                'positive_clips':sum(c['fire'] for c in clips),'positive_clips_alerted':sum(c['fire'] and bool(c['after_alert_seconds']) for c in clips)},
            'throughput_fps':{key:counts[key]/timing[key] for key in timing},'device':detector.device,
            'limitations':protocol['limitations'],'archive_samples':rows,'video_clips':clips,
            'credits':['HPWREN / UCSD https://www.hpwren.ucsd.edu/FIgLib/','Steffens et al. FURG Fire Dataset https://github.com/steffensbola/furg-fire-dataset']}
    output=ROOT/args.output;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('archive_samples','video_clips')},indent=2),flush=True)


if __name__=='__main__':main()
