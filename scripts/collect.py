"""Run locally or in Actions; credentials never appear in output."""
import os
import httpx
from pathlib import Path
from dotenv import load_dotenv
from services.collector import collect, flush_outbox
from services.store import Store

def main():
    load_dotenv()
    store = Store(Path("data/collector.sqlite"))
    points={}
    url=os.getenv('IGNIS_SITE_URL','').rstrip('/')
    if url.startswith('https://'):
        try:
            previous=httpx.get(url+'/api/v1/health',timeout=25).raise_for_status().json()
            for source in previous['sources']:store.put('sources',source)
            data=httpx.get(url+'/api/v1/perimeters',timeout=25).raise_for_status().json()
            for p in sorted(data['perimeters'],key=lambda x:x['acquired_at']):
                coordinates=p['geometry']['coordinates'][0] if p['geometry']['type']=='Polygon' else p['geometry']['coordinates'][0][0]
                points['incident_'+p['incident_id']]=((min(c[1] for c in coordinates)+max(c[1] for c in coordinates))/2,(min(c[0] for c in coordinates)+max(c[0] for c in coordinates))/2)
                if len(points)>=20:break
        except (httpx.HTTPError,ValueError,KeyError):pass
    payload = collect(store, os.getenv("FIRMS_MAP_KEY", ""), os.getenv("FIRMS_AREA", "5.8,47.2,15.1,55.1"),points)
    observations = payload.pop("observations")
    for start in range(0, max(1, len(observations)), 250):
        store.queue({**payload, "observations": observations[start:start + 250]})
    result = flush_outbox(store, os.getenv("IGNIS_COLLECTOR_TOKEN", ""))
    print(f"Collection: {len(observations)} observations; publication: {result['status']}")
    if result["status"] != "synced":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
