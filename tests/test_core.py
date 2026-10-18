import io
import json
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock

import httpx
import numpy as np
import pytest
import rasterio
from pyproj import Geod
from shapely.geometry import box,mapping,Polygon

from providers.nasa_firms import parse_firms_csv,FIRMSDataError,fetch_observations
from services.geometry import measure,compare
from services.store import Store
from services.imagery import burned_outline

CSV='latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp,daynight\n50,10,2026-10-18,0030,N21,VIIRS,n,3.1,D\n'
def boundary(geom,date='2026-10-18T00:00:00+00:00'):
    return {**measure(mapping(geom)),"acquired_at":date,"review_state":"approved","footprint_kind":"burned","coverage":mapping(box(9,49,12,52))}

def test_csv_and_utc():
    records=parse_firms_csv(CSV)
    assert records[0].detected_at.hour==0 and records[0].detected_at.minute==30
    assert records[0].detected_at.tzinfo==timezone.utc
    assert parse_firms_csv(CSV.split('\n')[0]+'\n')==[]

@pytest.mark.parametrize('text',['<html>Error</html>',CSV.replace('50,10,','nan,10,'),CSV.replace(',0030,',',2460,'),CSV.replace('50,10,','91,10,')])
def test_invalid_csv(text):
    with pytest.raises(FIRMSDataError):parse_firms_csv(text)

def test_provider_failure_redacts_key(monkeypatch):
    def fail(*args,**kwargs):raise httpx.ReadTimeout('secret URL')
    monkeypatch.setattr('providers.nasa_firms.httpx.get',fail)
    monkeypatch.setattr('providers.nasa_firms.time.sleep',lambda _:None)
    with pytest.raises(FIRMSDataError) as exc:fetch_observations('sensitive-key')
    assert 'sensitive' not in str(exc.value) and 'secret' not in str(exc.value)

def test_area_holes_independent_reference():
    geom=Polygon(box(10,50,10.02,50.02).exterior.coords,[box(10.005,50.005,10.01,50.01).exterior.coords])
    result=measure(mapping(geom))
    geod=Geod(ellps='WGS84')
    outer=abs(geod.geometry_area_perimeter(Polygon(geom.exterior))[0])
    inner=sum(abs(geod.geometry_area_perimeter(Polygon(r))[0]) for r in geom.interiors)
    reference=(outer-inner)/10000
    assert abs(result['burned_area_ha']/reference-1)<.01
    assert result['enclosed_area_ha']>result['burned_area_ha']

def test_invalid_geometry():
    with pytest.raises(ValueError):measure({'type':'Polygon','coordinates':[[[10,50],[11,51],[10,51],[11,50],[10,50]]]})
    with pytest.raises(ValueError):measure(mapping(box(0,0,1,1)))

def test_change_missing_coverage_and_symmetric_growth():
    old=boundary(box(10,50,10.01,50.01))
    new=boundary(box(9.999,49.999,10.011,50.011),'2026-10-18T01:00:00+00:00')
    result=compare(old,new)
    assert result['status']=='measured' and result['added_area_ha']>0
    assert result['dominant_sector'] is None
    new['coverage']=None
    assert compare(old,new)['status']=='insufficient_evidence'

def test_change_dates_and_contraction():
    old=boundary(box(10,50,10.01,50.01))
    new=boundary(box(10,50,10.005,50.005),'2026-10-18T01:00:00+00:00')
    assert compare(old,new)['status']=='insufficient_evidence'
    new['acquired_at']=old['acquired_at']
    assert compare(old,new)['status']=='insufficient_evidence'

def test_store_idempotence_and_outbox(tmp_path):
    store=Store(tmp_path/'state.sqlite')
    store.put('x',{'id':'a','value':1});store.put('x',{'id':'a','value':2})
    assert store.all('x')==[{'id':'a','value':2}]
    store.queue({'x':1});store.failed(1)
    assert Store(tmp_path/'state.sqlite').pending()[0]['error']
    store.delivered(1);assert not store.pending()

def raster(path,burn=False,cloud=False):
    data=np.zeros((4,20,20),dtype='float32');data[0]=.6;data[1]=.2;data[2]=4;data[3]=1
    if burn:data[0,5:15,5:15]=.2;data[1,5:15,5:15]=.6;data[2,5:15,5:15]=5
    if cloud:data[2]=9
    with rasterio.open(path,'w',driver='GTiff',width=20,height=20,count=4,dtype='float32',crs='EPSG:4326',transform=rasterio.transform.from_origin(10,50.02,.001,.001)) as dst:dst.write(data)

def test_dnBR_cloud_mask_and_outline(tmp_path):
    pre,post=tmp_path/'pre.tif',tmp_path/'post.tif';raster(pre);raster(post,True)
    result=burned_outline(pre,post)
    assert result['review_state']=='draft' and result['burned_area_ha']>0 and result['clear_coverage_fraction']==1
    raster(post,True,True)
    with pytest.raises(ValueError,match='No common clear'):burned_outline(pre,post)

@pytest.fixture
def client(tmp_path,monkeypatch):
    import app
    monkeypatch.setattr(app,'store',Store(tmp_path/'app.sqlite'))
    app.app.config.update(TESTING=True,DATA_DIR=str(tmp_path))
    return app.app.test_client()

def post(client,path,body,**kwargs):
    import app
    return client.post('/api/operator/'+path,json=body,headers={'X-Ignis-CSRF':app.CSRF,**kwargs})

def test_csrf_and_origin(client):
    assert client.post('/api/operator/incidents',json={'title':'x'}).status_code==403
    assert post(client,'incidents',{'title':'x'},Origin='https://evil.test').status_code==403
    assert client.get('/api/operator/state',headers={'Host':'evil.test'}).status_code==403

def test_review_to_public_replay(client):
    incident=post(client,'incidents',{'title':'Replay fixture','description':'Synthetic boundary'}).json
    assert client.get('/api/v1/incidents').json['incidents']==[]
    p=boundary(box(10,50,10.01,50.01))
    p.update(incident_id=incident['id'])
    saved=post(client,'perimeters',p)
    assert saved.status_code==201
    assert post(client,f"incidents/{incident['id']}/publish",{}).status_code==400
    assert post(client,f"perimeters/{saved.json['id']}/approve",{}).status_code==200
    assert post(client,f"incidents/{incident['id']}/publish",{}).status_code==200
    assert len(client.get('/api/v1/incidents').json['incidents'])==1
    assert len(client.get('/api/v1/perimeters').json['perimeters'])==1
    assert post(client,f"incidents/{incident['id']}/withdraw",{}).status_code==200
    assert client.get('/api/v1/perimeters').json['perimeters']==[]

def test_local_asset_not_public(client):
    assert client.get('/api/v1/evidence/private').status_code==404
    assert client.get('/api/operator/assets/evidence/unknown').status_code==404

def test_observation_windows(client):
    assert client.get('/api/observations?hours=5').status_code==400
    assert client.get('/api/observations?sources=nope').status_code==400
    assert client.get('/api/observations').json['observations']==[]

def test_outbox_network_recovery(tmp_path,monkeypatch):
    from services.collector import flush_outbox
    store=Store(tmp_path/'outbox.sqlite');store.queue({'incidents':[],'perimeters':[]})
    monkeypatch.setenv('IGNIS_SITE_URL','https://example.test');monkeypatch.setenv('IGNIS_OPERATOR_TOKEN','test-token')
    calls=[]
    def fail(*args,**kwargs):calls.append(1);raise httpx.ReadTimeout('private URL')
    monkeypatch.setattr('services.collector.httpx.post',fail);monkeypatch.setattr('services.collector.time.sleep',lambda _:None)
    assert flush_outbox(store)['pending']==1 and len(calls)==3
    response=Mock();response.raise_for_status.return_value=None
    monkeypatch.setattr('services.collector.httpx.post',lambda *a,**k:response)
    assert flush_outbox(store)['status']=='synced' and not store.pending()

def test_invalid_upload_and_private_remote_access(client):
    import app
    response=client.post('/api/operator/upload',data={'file':(io.BytesIO(b'evil'),'data.exe')},headers={'X-Ignis-CSRF':app.CSRF},content_type='multipart/form-data')
    assert response.status_code==400
    assert client.get('/api/operator/state',environ_overrides={'REMOTE_ADDR':'192.0.2.3'}).status_code==403

def test_interrupted_camera_job_is_resumable(tmp_path):
    pytest.importorskip('cv2')
    from services.camera import CameraWorker
    store=Store(tmp_path/'camera.sqlite')
    store.put('jobs',{'id':'interrupted','status':'running','source':'local.mp4','frames':10,'seconds':10,'kind':'video'})
    CameraWorker(store,tmp_path/'evidence')
    assert store.get('jobs','interrupted')['status']=='interrupted'

def test_camera_temporal_confirmation(tmp_path):
    pytest.importorskip('cv2')
    from PIL import Image
    from services.camera import CameraWorker
    root=tmp_path/'frames';root.mkdir()
    for i in range(3):Image.new('RGB',(48,32)).save(root/f'{i}.jpg')
    store=Store(tmp_path/'camera.sqlite');worker=CameraWorker(store,tmp_path/'evidence')
    class DeterministicClassifier:
        device='test'
        def score(self,image):return .9
    worker.classifier=DeterministicClassifier()
    key=worker.start(str(root),'sequence');worker.thread.join(timeout=10)
    assert store.get('jobs',key)['status']=='completed'
    assert store.get('jobs',key)['frames']==3
    assert len(store.all('evidence'))==1

def test_high_resolution_local_signal_survives_downsampling():
    torch=pytest.importorskip('torch')
    pytest.importorskip('cv2')
    from torchvision.transforms import ToTensor
    from PIL import Image
    from services.camera import Classifier
    model=Classifier.__new__(Classifier)
    model.torch=torch;model.device='cpu';model.to_tensor=ToTensor();model.normalize=lambda x:x
    model.model=lambda batch:4*(batch.mean(dim=(1,2,3))-.5)
    image=Image.new('RGB',(768,512),'black');image.paste('white',(0,0,384,256))
    assert model.score(image)>.8
    assert model.score(Image.new('RGB',(384,256),'black'))<.2
