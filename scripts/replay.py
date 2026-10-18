"""Offline acceptance replay in an isolated store; never publishes fixture incidents."""
import json,time,shutil,tempfile
from pathlib import Path
from PIL import Image
from shapely.geometry import mapping,box
import app
from services.camera import CameraWorker
from services.store import Store

def main():
    images=sorted(Path('data/validation').glob('*/*.jpg'))
    if not images:raise ValueError('Run python -m scripts.fetch_validation first')
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);sequence=root/'sequence';sequence.mkdir()
        for index,path in enumerate(images):
            with Image.open(path) as im:im.convert('RGB').save(sequence/f'{index:04d}.jpg')
        app.store=Store(root/'state.sqlite');app.app.config['DATA_DIR']=str(root)
        app.worker=CameraWorker(app.store,root/'evidence')
        client=app.app.test_client()
        def post(path,body):
            r=client.post('/api/operator/'+path,json=body,headers={'X-Ignis-CSRF':app.CSRF})
            assert r.status_code<300,r.json
            return r.json
        job_id=app.worker.start(str(sequence),'sequence')
        app.worker.thread.join(timeout=90)
        job=app.store.get('jobs',job_id)
        assert job['status']=='completed',job
        assert job['frames']==len(images)
        evidence=post('camera/snapshot',{'id':job_id})
        incident=post('incidents',{'title':'SYNTHETISCHER REPLAY – kein realer Brand','evidence_ids':[evidence['id']]})
        boundaries=[]
        for i,geom in enumerate([box(10,50,10.01,50.01),box(10,50,10.012,50.01)]):
            body={'incident_id':incident['id'],'geometry':mapping(geom),'coverage':mapping(box(9.99,49.99,10.03,50.03)),'acquired_at':f'2026-10-18T0{i}:00:00+00:00','method':'synthetic replay','resolution_m':20,'provenance':'Synthetic geometry; unrelated to camera location'}
            p=post('perimeters',body);post(f"perimeters/{p['id']}/approve",{});boundaries.append(p)
        change=post('compare',{'before':boundaries[0]['id'],'after':boundaries[1]['id']})
        assert change['status']=='measured' and change['added_area_ha']>0
        # Disable cloud transport for this isolated replay, while exercising publication visibility.
        app.flush_outbox=lambda store:{'status':'isolated_replay','pending':len(store.pending())}
        post(f"incidents/{incident['id']}/publish",{})
        assert len(client.get('/api/v1/incidents').json['incidents'])==1
        assert client.get('/api/v1/evidence/'+evidence['id']).status_code==200
        post(f"incidents/{incident['id']}/withdraw",{})
        assert client.get('/api/v1/evidence/'+evidence['id']).status_code==404
        report={'status':'passed','frames':job['frames'],'device':job['device'],'worker_throughput_fps':job['throughput_fps'],'automatic_evidence_count':len(app.store.all('evidence'))-1,'manual_evidence_count':1,'reviewed_boundaries':2,'added_area_ha':change['added_area_ha'],'publication':'isolated only; no fixture sent to cloud'}
        Path('outputs').mkdir(exist_ok=True);Path('outputs/replay.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
