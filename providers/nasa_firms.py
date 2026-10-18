import csv
import math
import time
from datetime import datetime, timezone
from io import StringIO
import httpx
from models.fire_observation import Observation

BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
SATELLITE_SOURCES = {"VIIRS_NOAA21_NRT": "NOAA-21 · VIIRS", "VIIRS_NOAA20_NRT": "NOAA-20 · VIIRS", "VIIRS_SNPP_NRT": "Suomi-NPP · VIIRS", "MODIS_NRT": "Terra / Aqua · MODIS"}
AREA = "5.8,47.2,15.1,55.1"


class FIRMSDataError(Exception):
    def __init__(self, reason):
        self.safe_reason = reason
        super().__init__(reason)


def parse_firms_csv(csv_text):
    reader = csv.DictReader(StringIO(csv_text.strip()))
    required = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument", "confidence", "frp", "daynight"}
    if not required.issubset(reader.fieldnames or []):
        raise FIRMSDataError("Invalid CSV header")
    observations, invalid = [], 0
    for row in reader:
        try:
            lat, lon, frp = (float(row[k]) for k in ("latitude", "longitude", "frp"))
            if not all(math.isfinite(x) for x in (lat, lon, frp)) or not (-90 <= lat <= 90 and -180 <= lon <= 180) or frp < 0:
                raise ValueError()
            detected = datetime.strptime(f"{row['acq_date']} {row['acq_time'].zfill(4)}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
            dimensions=[]
            for name in ('scan','track'):
                value=float(row[name]) if row.get(name) else None
                if value is not None and (not math.isfinite(value) or not 0<value<=10):raise ValueError()
                dimensions.append(value)
            thermal_type=int(row['type']) if row.get('type') else None
            if thermal_type is not None and thermal_type not in (0,1,2,3):raise ValueError()
            observations.append(Observation(lat, lon, detected, "NASA_FIRMS", row["satellite"], row["instrument"], row["confidence"], frp, row["daynight"],*dimensions,thermal_type))
        except (ValueError, TypeError, KeyError, AttributeError):
            invalid += 1
    # Partial malformed responses must not masquerade as complete coverage.
    if invalid:
        raise FIRMSDataError(f"CSV contains {invalid} invalid records")
    return observations


def fetch_observations(map_key, source="VIIRS_NOAA21_NRT", area=AREA, day_range=2):
    if source not in SATELLITE_SOURCES or day_range not in range(1, 6):
        raise FIRMSDataError("Invalid source or day range")
    if not map_key or "REPLACE" in map_key:
        raise FIRMSDataError("configuration_missing")
    if area != "world":
        try:
            w, s, e, n = map(float, area.split(","))
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise ValueError()
        except ValueError as exc:
            raise FIRMSDataError("Invalid region") from exc
    for attempt in range(3):
        try:
            response = httpx.get(f"{BASE_URL}/{map_key}/{source}/{area}/{day_range}", timeout=35)
            response.raise_for_status()
            return parse_firms_csv(response.text)
        except httpx.HTTPError:
            if attempt == 2:
                raise FIRMSDataError("Provider network or HTTP failure") from None
            time.sleep(2 ** attempt)

