from datetime import datetime, timedelta, timezone

from models.fire_observation import Observation

#Filter for timezone
def filter_by_hours(
    observations: list[Observation], hours: int, now: datetime | None = None
) -> list[Observation]:
    if hours not in (1, 6, 12, 24):
        raise ValueError("Time range must be one of 1, 6, 12, 24 hours")
    reference = now if now is not None else datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("Reference time must include a timezone")
    cutoff = reference - timedelta(hours=hours)
    return [
        observation
        for observation in observations
        if cutoff <= observation.detected_at <= reference
    ]


def serialize_observation(observation: Observation) -> dict:
    return {
        "latitude": observation.latitude,
        "longitude": observation.longitude,
        "detected_at": observation.detected_at.strftime("%Y-%m-%d %H:%M UTC"),
        "source": observation.source,
        "satellite": observation.satellite,
        "sensor": observation.sensor,
        "confidence": observation.confidence,
        "frp": observation.frp,
        "daynight": observation.daynight,
    }
