"""Exercise cloud API on local Wrangler only; test data is never sent to production."""
import os,json
from datetime import datetime,timezone,timedelta
import httpx
from dotenv import load_dotenv

def main():
    load_dotenv()
    url='http://127.0.0.1:5173'
    now=datetime.now(timezone.utc).isoformat()
    collector={'Authorization':'Bearer '+os.environ['IGNIS_COLLECTOR_TOKEN']}
    operator={'Authorization':'Bearer '+os.environ['IGNIS_OPERATOR_TOKEN']}
    # Windows Miniflare can restart a reused POST connection after an early rejection.
    with httpx.Client(base_url=url,timeout=30,limits=httpx.Limits(max_keepalive_connections=0)) as c:
        send=c.post
        def post(*args,**kwargs):
            response=send(*args,**kwargs)
            if response.status_code==503 and 'worker restarted mid-request' in response.text:
                response=send(*args,**kwargs)
            return response
        c.post=post
        assert c.post('/api/v1/ingest',json={}).status_code==401
        denied=c.post('/api/v1/ingest',json={'incidents':[],'perimeters':[]},headers=collector)
        assert denied.status_code==400,(denied.status_code,denied.text)
        assert c.post('/api/v1/ingest',json={'observations':[],'sources':[],'weather':[]},headers={**collector,'Origin':'https://evil.test'}).status_code==403
        item={'id':'fixture_thermal','latitude':50,'longitude':10,'acquired_at':now,'retrieved_at':now,'detected_at':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),'source':'NASA_FIRMS','dataset':'VIIRS_NOAA21_NRT','satellite':'N21','sensor':'VIIRS','confidence':'n','frp':2.,'daynight':'D'}
        batch={'observations':[item],'sources':[{'id':'VIIRS_NOAA21_NRT','status':'connected','checked_at':now,'last_success_at':now,'count':1}],'weather':[]}
        for _ in range(2):
            accepted=c.post('/api/v1/ingest',json=batch,headers=collector)
            assert accepted.status_code==200,(accepted.status_code,accepted.text)
        response=c.get('/api/observations').raise_for_status().json()
        assert len([x for x in response['observations'] if x['id']==item['id']])==1
        bad={**item,'latitude':float(100)}
        assert c.post('/api/v1/ingest',json={**batch,'observations':[bad]},headers=collector).status_code==400
        incident={'id':'fixture_incident','title':'Local acceptance fixture','description':'Never deployed','review_state':'published','created_at':now,'updated_at':now}
        geometry={'type':'Polygon','coordinates':[[[10,50],[10.01,50],[10.01,50.01],[10,50.01],[10,50]]]}
        p={'id':'fixture_perimeter','incident_id':incident['id'],'geometry':geometry,'coverage':geometry,'burned_area_ha':79.7,'enclosed_area_ha':79.7,'area_crs':'EPSG:3035','acquired_at':now,'created_at':now,'reviewed_at':now,'review_state':'approved','method':'synthetic','resolution_m':20,'footprint_kind':'burned','provenance':'Synthetic test only'}
        assert c.post('/api/v1/ingest',json={'incidents':[incident],'perimeters':[p]},headers=operator).status_code==200
        assert any(x['id']==p['id'] for x in c.get('/api/v1/perimeters').json()['perimeters'])
        incident['review_state']='withdrawn'
        assert c.post('/api/v1/ingest',json={'incidents':[incident],'perimeters':[]},headers=operator).status_code==200
        assert not any(x['id']==p['id'] for x in c.get('/api/v1/perimeters').json()['perimeters'])
        assert c.get('/api/v1/evidence/private').status_code==404
    print('Cloud API: authorization, role separation, origin, validation, idempotence, publication and withdrawal passed locally.')

if __name__=='__main__':main()
