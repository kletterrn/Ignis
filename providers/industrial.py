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
                rows=db.execute('SELECT name,ETRS89_x,ETRS89_y,inspire_id FROM betriebe WHERE jahr=2024').fetchall()
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


def annotate_industry(records,cache_path='data/industrial-cache.json'):
    path=Path(cache_path);now=time.time();failed=False
    try:cache=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):cache={}
    if records and now-cache.get('time',0)>7*86400:
        try:
            cache={'time':now,'reporting_year':2024,'source':SOURCE,'facilities':fetch_facilities()}
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.part');temporary.write_text(json.dumps(cache),encoding='utf-8');temporary.replace(path)
        except (httpx.HTTPError,ValueError,KeyError,zipfile.BadZipFile,sqlite3.Error,OSError):failed=True
    checked=datetime.fromtimestamp(cache['time'],timezone.utc).isoformat() if cache.get('time') else None
    facilities=cache.get('facilities',[])
    for o in records:
        for key in ('context_name','context_source','context_distance_m'):o.pop(key,None)
        o.update(context_kind='unknown',context_checked_at=checked)
        if o.get('thermal_type') in (1,2,3):
            o.update(context_kind='static_source',context_name='NASA: volcano / static land / offshore source',context_source='NASA FIRMS thermal type')
            continue
        nearby=[f for f in facilities if abs(f['latitude']-o['latitude'])<.01 and abs(f['longitude']-o['longitude'])<.02]
        nearest=min(nearby,key=lambda f:distance_m(o,f),default=None)
        if nearest is not None and (distance:=distance_m(o,nearest))<=1000:
            o.update(context_kind='industrial',context_name=nearest['name'],context_source=SOURCE+' (UBA PRTR 2024)',context_distance_m=round(distance))
    return {'status':'unavailable' if failed or not facilities else 'connected','count':sum(o['context_kind']!='unknown' for o in records)}
