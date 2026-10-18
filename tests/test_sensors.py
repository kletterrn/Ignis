import io
import json
import numpy as np
import pytest
import rasterio
from services.sensors import stereo_measure,thermal_measure
from scripts.sensor_fixtures import create

AT='2026-10-18T00:00:00Z'


def test_stereo_actual_matching_reference_plane(tmp_path):
    pytest.importorskip('cv2')
    calibration=create(tmp_path)
    result=stereo_measure(tmp_path/'left.png',tmp_path/'right.png',calibration,AT,AT,tmp_path/'result')
    assert abs(result['depth_m']['median']-4)<.04
    assert result['valid_fraction']>.1
    assert result['georeferenced'] is False and result['review_state']=='unvalidated'
    assert len(result['points_preview'])<=2500
    arrays=np.load(tmp_path/'result'/'depth.npz')
    assert np.isnan(arrays['depth_m'][~arrays['valid']]).all()
    assert (tmp_path/'result'/'points.ply').exists()


def test_stereo_rejects_unsynchronised_or_uncalibrated_input(tmp_path):
    pytest.importorskip('cv2')
    c=create(tmp_path)
    def run():return stereo_measure(tmp_path/'left.png',tmp_path/'right.png',c,AT,'2026-10-18T00:00:01Z',tmp_path/'result')
    with pytest.raises(ValueError,match='50 ms'):run()
    for key,value in [('translation_unit','mm'),('image_size',[640,384]),('T',[0,0,0]),('R',[[0,0,0]]*3),('rms_px',float('nan'))]:
        bad={**c,key:value}
        with pytest.raises(ValueError):stereo_measure(tmp_path/'left.png',tmp_path/'right.png',bad,AT,AT,tmp_path/'result')


def test_thermal_kelvin_scaling_nodata_area_and_no_fire_claim(tmp_path):
    create(tmp_path)
    result=thermal_measure(tmp_path/'thermal.tif',60,tmp_path/'result')
    assert result['temperature_c']['min']==pytest.approx(20)
    assert result['temperature_c']['max']==pytest.approx(80)
    assert result['hot_pixel_count']==256
    assert result['candidate_area_ha']==pytest.approx(256*4/10000,rel=.001)
    assert result['valid_fraction']==pytest.approx(31/32)
    assert result['review_state']=='unvalidated' and 'geometry' not in result
    assert result['temperature_kind']=='apparent'
    cold=thermal_measure(tmp_path/'thermal.tif',100,tmp_path/'cold')
    assert cold['candidate_geometry'] is None and cold['candidate_area_ha']==0
    with rasterio.open(tmp_path/'thermal.tif','r+') as dst:dst.update_tags(TEMPERATURE_UNIT='palette')
    with pytest.raises(ValueError,match='palette'):thermal_measure(tmp_path/'thermal.tif',60,tmp_path/'bad')


def test_sensor_api_private_and_no_automatic_publication(tmp_path,monkeypatch):
    import app
    from services.store import Store
    create(tmp_path)
    monkeypatch.setattr(app,'store',Store(tmp_path/'store.sqlite'))
    monkeypatch.setitem(app.app.config,'DATA_DIR',str(tmp_path/'data'))
    client=app.app.test_client()
    def payload():return {'raster':(io.BytesIO((tmp_path/'thermal.tif').read_bytes()),'thermal.tif'),'threshold_c':'60'}
    assert client.post('/api/operator/sensors/thermal',data=payload()).status_code==403
    result=client.post('/api/operator/sensors/thermal',data=payload(),headers={'X-Ignis-CSRF':app.CSRF})
    assert result.status_code==201
    key=result.json['id']
    assert client.get('/api/operator/measurements/'+key).status_code==200
    assert client.get('/api/operator/measurements/'+key+'/candidate').status_code==200
    assert client.get('/api/operator/measurements/'+key+'/points').status_code==404
    assert client.get('/api/operator/measurements/'+key,environ_overrides={'REMOTE_ADDR':'192.0.2.1'}).status_code==403
    assert client.get('/api/v1/measurements').status_code==404
    assert client.get('/api/v1/incidents').json['incidents']==[]
    assert app.store.pending()==[]
