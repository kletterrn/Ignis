import json
import time

import httpx
import pytest

from providers.industrial import annotate_industry
from providers.nasa_firms import parse_firms_csv,FIRMSDataError
from services.observations import serialize_observation


def test_firms_preserves_pixel_dimensions_and_optional_static_type():
    text='latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp,daynight,scan,track,type\n50,10,2026-10-18,1200,N21,VIIRS,n,4,D,0.4,0.6,2\n'
    record=serialize_observation(parse_firms_csv(text)[0])
    assert (record['scan_km'],record['track_km'],record['thermal_type'])==(.4,.6,2)
    with pytest.raises(FIRMSDataError):parse_firms_csv(text.replace('0.4,0.6','nan,0.6'))


def test_industry_context_preserves_raw_observations_and_reports_outages(monkeypatch,tmp_path):
    cache=tmp_path/'context.json';cache.write_text(json.dumps({'time':time.time(),'facilities':[{'name':'Reference steel works','latitude':50,'longitude':10}]}))
    records=[{'latitude':50,'longitude':10.001},{'latitude':50,'longitude':10.03},{'latitude':50,'longitude':10.03,'thermal_type':2}]
    result=annotate_industry(records,cache)
    assert result=={'status':'connected','count':2}
    assert len(records)==3 and records[0]['context_kind']=='industrial' and 60<records[0]['context_distance_m']<80
    assert records[1]['context_kind']=='unknown' and records[2]['context_kind']=='static_source'
    def fail():raise httpx.ReadTimeout('unavailable')
    monkeypatch.setattr('providers.industrial.fetch_facilities',fail)
    fresh=[{'latitude':50,'longitude':10}]
    assert annotate_industry(fresh,tmp_path/'missing.json')['status']=='unavailable'
    assert fresh[0]['context_kind']=='unknown' and fresh[0]['context_checked_at'] is None
    cache.write_text(json.dumps({'time':1,'facilities':[{'name':'Old reference','latitude':50,'longitude':10}]}))
    stale=cache.read_bytes();assert annotate_industry(fresh,cache)['status']=='unavailable'
    assert fresh[0]['context_kind']=='industrial' and cache.read_bytes()==stale
