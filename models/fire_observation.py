from dataclasses import dataclass
from datetime import datetime

#float (number) str (name)
@dataclass(frozen=True)
class Observation:
    latitude: float
    longitude: float
    detected_at: datetime
    source: str
    satellite: str
    sensor: str
    confidence: str
    frp: float
    daynight: str
