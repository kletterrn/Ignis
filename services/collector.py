import hashlib
import os
import time
from datetime import datetime, timedelta, timezone
import httpx
from providers.nasa_firms import AREA, SATELLITE_SOURCES, FIRMSDataError, fetch_observations
from providers.weather import fetch_weather
from providers.industrial import annotate_industry
from services.observations import serialize_observation
from services.store import utcnow

WEATHER_POINTS = {"north": (53.55, 10.0), "east": (52.52, 13.40), "west": (50.94, 6.96), "south": (48.14, 11.58), "central": (51.31, 9.49)}

def collect(store, map_key, area=AREA, extra_points=None):
    statuses, records, weather = [], [], []
    now = utcnow()
    for source, label in SATELLITE_SOURCES.items():
        try:
            items = fetch_observations(map_key, source, area, 2)
            for record in items:
                item = serialize_observation(record)
                item.update(acquired_at=record.detected_at.isoformat(), retrieved_at=now, dataset=source)
                identity = [record.satellite, record.sensor, record.latitude, record.longitude, item["acquired_at"]]
                item["id"] = hashlib.sha256(repr(identity).encode()).hexdigest()[:32]
                records.append(item)
            status = {"id": source, "label": label, "status": "connected", "count": len(items), "checked_at": now, "last_success_at": now}
        except FIRMSDataError as exc:
            previous = store.get("sources", source) or {}
            status = {"id": source, "label": label, "status": "configuration_missing" if exc.safe_reason == "configuration_missing" else "unavailable", "count": 0, "checked_at": now, "last_success_at": previous.get("last_success_at")}
        store.put("sources", status)
        statuses.append(status)
    context=annotate_industry(records)
    previous=store.get('sources','industrial_context') or {}
    context.update(id='industrial_context',label='Industriekontext · UBA/EEA 2024',checked_at=now,last_success_at=now if context['status']=='connected' else previous.get('last_success_at'))
    statuses.append(context);store.put('sources',context)
    for item in records:store.put('observations',item)
    for key, (lat, lon) in {**WEATHER_POINTS,**(extra_points or {})}.items():
        try:
            item = fetch_weather(lat, lon, key)
            store.put("weather", item)
            weather.append(item)
            status = {"id": "weather_" + key, "status": "connected", "checked_at": now, "last_success_at": now}
        except (httpx.HTTPError, ValueError, KeyError):
            previous = store.get("sources", "weather_" + key) or {}
            status = {"id": "weather_" + key, "status": "unavailable", "checked_at": now, "last_success_at": previous.get("last_success_at")}
        store.put("sources", status)
        statuses.append(status)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    with store.db() as db:
        db.execute("DELETE FROM records WHERE kind='observations' AND json_extract(body,'$.acquired_at') < ?", (cutoff,))
    return {"observations": list({x["id"]: x for x in records}.values()), "sources": statuses, "weather": weather}

def flush_outbox(store, token=None):
    url = os.getenv("IGNIS_SITE_URL", "").rstrip("/")
    token = token or os.getenv("IGNIS_OPERATOR_TOKEN", "")
    if not url or not token:
        return {"status": "configuration_missing", "pending": len(store.pending())}
    if not url.startswith("https://"):
        raise ValueError("Cloud destination must use HTTPS")
    for item in store.pending():
        try:
            for attempt in range(3):
                try:
                    response = httpx.post(url + "/api/v1/ingest", json=item["body"], headers={"Authorization": f"Bearer {token}"}, timeout=40)
                    response.raise_for_status()
                    break
                except httpx.HTTPError as exc:
                    if attempt==2 or isinstance(exc,httpx.HTTPStatusError) and exc.response.status_code<500 and exc.response.status_code!=429:raise
                    time.sleep(2**attempt)
            store.delivered(item["id"])
        except httpx.HTTPError:
            store.failed(item["id"])
            break
    return {"status": "pending" if store.pending() else "synced", "pending": len(store.pending())}
