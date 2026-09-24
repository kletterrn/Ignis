import time
from io import StringIO
from datetime import datetime, timezone

import httpx
import pandas as pd

from models.fire_observation import Observation


BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

CACHE_SECONDS = 600
cache = {}


class FIRMSDataError(Exception):
    def __init__(self, reason):
        self.safe_reason = reason
        super().__init__(reason)


def parse_firms_csv(csv_text):

    df = pd.read_csv(StringIO(csv_text))

    observations = []

    for row in df.to_dict("records"):

        try:
            date = str(row["acq_date"])
            acquisition_time = str(row["acq_time"]).zfill(4)

            detected_at = datetime.strptime(
                f"{date} {acquisition_time}",
                #Jahr, Monat, Tag, Stunde, Minute
                "%Y-%m-%d %H%M"
            ).replace(tzinfo=timezone.utc)

            observation = Observation(
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                detected_at=detected_at,
                source="NASA_FIRMS",
                satellite=str(row["satellite"]),
                sensor=str(row["instrument"]),
                confidence=str(row["confidence"]),
                frp=float(row["frp"]),
                daynight=str(row["daynight"])
            )

            observations.append(observation)

        except (ValueError, TypeError, KeyError):
            continue

    return observations


def fetch_observations(
    map_key,
    source="VIIRS_NOAA21_NRT",
    area="5.8,47.2,15.1,55.1",
    day_range=2
):

    url = f"{BASE_URL}/{map_key}/{source}/{area}/{day_range}"

    response = httpx.get(url, timeout=40)

    response.raise_for_status()

    observations = parse_firms_csv(response.text)

    return observations