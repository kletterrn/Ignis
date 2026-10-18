import httpx
import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from services.imagery import download_scene
from services.geometry import timestamp


def test_scene_window_and_empty_coverage_do_not_replace_evidence(monkeypatch,tmp_path):
    monkeypatch.setenv('CDSE_CLIENT_ID','local-client')
    monkeypatch.setenv('CDSE_CLIENT_SECRET','local-secret')
    destination=tmp_path/'scene.tif'
    instant=timestamp('2026-10-16T10:10:41.024Z')
    observed=True
    def post(url,**kwargs):
        if url.endswith('/token'):
            return httpx.Response(200,json={'access_token':'private-token'},request=httpx.Request('POST',url))
        window=kwargs['json']['input']['data'][0]['dataFilter']['timeRange']
        assert (instant-timestamp(window['from'])).total_seconds()==900
        assert (timestamp(window['to'])-instant).total_seconds()==900
        with MemoryFile() as memory:
            with memory.open(driver='GTiff',width=2,height=2,count=4,dtype='float32',crs='EPSG:4326',transform=from_origin(10,50,.001,.001)) as raster:
                bands=np.ones((4,2,2),dtype='float32');bands[3]=int(observed);raster.write(bands)
            return httpx.Response(200,content=memory.read(),request=httpx.Request('POST',url))
    monkeypatch.setattr('services.imagery.httpx.post',post)
    download_scene([10,49.99,10.01,50],instant.isoformat(),destination)
    original=destination.read_bytes()
    observed=False
    with pytest.raises(ValueError,match='no observed coverage'):
        download_scene([10,49.99,10.01,50],instant.isoformat(),destination)
    assert destination.read_bytes()==original


def test_authentication_failure_is_actionable_and_redacted(monkeypatch,tmp_path):
    monkeypatch.setenv('CDSE_CLIENT_ID','local-client')
    monkeypatch.setenv('CDSE_CLIENT_SECRET','local-secret')
    monkeypatch.setattr('services.imagery.httpx.post',lambda *a,**kw:httpx.Response(401,text='local-secret'))
    with pytest.raises(ValueError,match='authentication rejected') as error:
        download_scene([10,49.99,10.01,50],'2026-10-16T10:10:41Z',tmp_path/'scene.tif')
    assert 'local-secret' not in str(error.value)
