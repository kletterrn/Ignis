"""Registered-facility proximity is context, never proof that a hotspot is harmless."""
import io
import json
import math
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path
from datetime import datetime,timezone

import httpx

URL='https://thru.de/wp-content/uploads/2026/03/prtr_2024.zip'
SOURCE='https://thru.de/downloads/'
EEA='https://air.discomap.eea.europa.eu/arcgis/rest/services/Air/IED_SiteMap/MapServer/0/query'
EEA_SOURCE='https://industry.eea.europa.eu/industrial-emissions/explore-data-on-the-map'


def fetch_facilities():
    chunks=[];size=0
    with httpx.stream('GET',URL,follow_redirects=True,timeout=45) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            size+=len(chunk)
            if size>20_000_000:raise ValueError('PRTR archive exceeds download limit')
            chunks.append(chunk)
    with zipfile.ZipFile(io.BytesIO(b''.join(chunks))) as archive:
        member=archive.getinfo('prtr_2024.db')
        if member.file_size>200_000_000:raise ValueError('PRTR database exceeds size limit')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'registry.db';path.write_bytes(archive.read(member))
            with closing(sqlite3.connect(path)) as db:
                db.execute('PRAGMA query_only=ON')
                rows=db.execute("SELECT name,ETRS89_x,ETRS89_y,inspire_id FROM betriebe WHERE jahr=2024 AND nace_code NOT LIKE '01.%' AND nace_code NOT LIKE '02.%' AND nace_code NOT LIKE '03.%'").fetchall()
    facilities=[]
    for name,lon,lat,identifier in rows:
        if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)) or not (46<=lat<=56 and 5<=lon<=16):continue
        facilities.append({'name':str(name)[:100],'latitude':lat,'longitude':lon,'identifier':str(identifier)[:100]})
    if not facilities:raise ValueError('No valid PRTR facility coordinates')
    return facilities


def distance_m(a,b):
    lat1,lat2=math.radians(a['latitude']),math.radians(b['latitude'])
    dlat=lat2-lat1;dlon=math.radians(b['longitude']-a['longitude'])
    value=math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 12742000*math.asin(math.sqrt(min(1,value)))


def fetch_border_facilities():
    parameters={'f':'json','where':"Site_reporting_year=2024 AND countryCode <> 'DE' AND eprtr_sectors <> 'INTENSIVE LIVESTOCK'",'geometry':'5.8,47.2,15.1,55.1','geometryType':'esriGeometryEnvelope','inSR':'4326','spatialRel':'esriSpatialRelIntersects','outFields':'siteName,x_4258,y_4258,InspireSiteId','returnGeometry':'false','resultRecordCount':1000,'orderByFields':'OBJECTID'}
    facilities=[]
    with httpx.Client(timeout=45) as client:
        for offset in range(0,10000,1000):
            payload=client.get(EEA,params={**parameters,'resultOffset':offset}).raise_for_status().json()
            if payload.get('error') or not isinstance(payload.get('features'),list):raise ValueError('EEA registry response invalid')
            for feature in payload['features']:
                a=feature['attributes'];lon,lat=a['x_4258'],a['y_4258']
                if isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and 47.2<=lat<=55.1 and 5.8<=lon<=15.1:
                    facilities.append({'name':str(a['siteName'])[:100],'latitude':lat,'longitude':lon,'identifier':str(a['InspireSiteId'])[:100]})
            if not payload.get('exceededTransferLimit'):break
        else:raise ValueError('EEA registry pagination incomplete')
    if not facilities:raise ValueError('EEA registry contains no valid facility coordinates')
    return facilities


def annotate_industry(records,cache_path='data/industrial-cache.json'):
    path=Path(cache_path);now=time.time();failed=False
    try:cache=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):cache={}
    if 'facilities' in cache:cache={'de':cache}
    changed=False;facilities=[];checked=None
    for key,fetcher,source in [('de',fetch_facilities,SOURCE+' (UBA PRTR 2024)'),('eea',fetch_border_facilities,EEA_SOURCE+' (EEA 2024)')]:
        entry=cache.get(key,{})
        if records and (entry.get('schema')!=2 or now-entry.get('time',0)>7*86400):
            try:
                entry={'schema':2,'time':now,'facilities':fetcher()};cache[key]=entry;changed=True
            except (httpx.HTTPError,ValueError,KeyError,zipfile.BadZipFile,sqlite3.Error,OSError):failed=True
        retrieved=datetime.fromtimestamp(entry['time'],timezone.utc).isoformat() if entry.get('time') else None
        checked=max(checked or '',retrieved or '') or None
        facilities.extend({**f,'source':source,'checked_at':retrieved} for f in entry.get('facilities',[]))
    if changed:
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.part');temporary.write_text(json.dumps(cache),encoding='utf-8');temporary.replace(path)
    for o in records:
        for key in ('context_name','context_source','context_distance_m'):o.pop(key,None)
        o.update(context_kind='unknown',context_checked_at=checked)
        if o.get('thermal_type') in (1,2,3):
            o.update(context_kind='static_source',context_name='NASA: volcano / static land / offshore source',context_source='NASA FIRMS thermal type')
            continue
        nearby=[f for f in facilities if abs(f['latitude']-o['latitude'])<.01 and abs(f['longitude']-o['longitude'])<.02]
        nearest=min(nearby,key=lambda f:distance_m(o,f),default=None)
        if nearest is not None and (distance:=distance_m(o,nearest))<=1000:
            o.update(context_kind='industrial',context_name=nearest['name'],context_source=(nearest['source']+'; ID '+nearest['identifier'])[:200],context_distance_m=round(distance),context_checked_at=nearest['checked_at'])
    return {'status':'unavailable' if failed or not facilities else 'connected','count':sum(o['context_kind']!='unknown' for o in records)}
