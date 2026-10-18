"""Evaluate labeled image sequences: CSV path,label,event,offset_seconds. Labels 0/1."""
import argparse,csv,json,time
from pathlib import Path
from PIL import Image
from services.camera import Classifier,CameraDetector,DETECTION_THRESHOLD

def main():
    parser=argparse.ArgumentParser();parser.add_argument('manifest');parser.add_argument('--output',default='outputs/camera-benchmark.json');parser.add_argument('--legacy',action='store_true');args=parser.parse_args()
    rows=list(csv.DictReader(Path(args.manifest).open(encoding='utf-8')))
    if not rows or any(r['label'] not in ('0','1') for r in rows):raise ValueError('Labeled images required')
    model=Classifier() if args.legacy else CameraDetector();threshold=.7 if args.legacy else DETECTION_THRESHOLD;results=[];start=time.perf_counter()
    for row in rows:
        with Image.open(row['path']) as image:score=model.score(image)
        results.append({**row,'score':score,'prediction':int(score>=threshold)})
    elapsed=time.perf_counter()-start
    tp=sum(int(r['label'])==1 and r['prediction']==1 for r in results);fp=sum(int(r['label'])==0 and r['prediction']==1 for r in results);fn=sum(int(r['label'])==1 and r['prediction']==0 for r in results)
    negatives={}
    for r in results:
        if r['label']=='0':negatives.setdefault(r['event'],[]).append(float(r['offset_seconds']))
    negative_hours=sum(max(v)-min(v) for v in negatives.values() if len(v)>1)/3600
    # Sparse archive frames cannot establish continuous operational alert rates.
    report={'device':model.device,'frames':len(rows),'elapsed_seconds':elapsed,'throughput_fps':len(rows)/elapsed,'threshold':threshold,'true_positive':tp,'false_positive':fp,'false_negative':fn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,'negative_observation_span_hours':negative_hours,'false_alerts_per_hour':None,'false_alerts_note':'Not measured: sparse frame evaluation is not continuous video alert evaluation','results':results}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))

if __name__=='__main__':main()
