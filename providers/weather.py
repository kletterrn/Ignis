import httpx
from services.store import utcnow

VARIABLES = "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m"

def fetch_weather(latitude, longitude, key):
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("Invalid weather coordinates")
    response = httpx.get("https://api.open-meteo.com/v1/dwd-icon", params={"latitude": latitude, "longitude": longitude, "current": VARIABLES, "hourly": VARIABLES, "forecast_days": 2, "timezone": "UTC", "wind_speed_unit": "kmh"}, timeout=25)
    response.raise_for_status()
    data = response.json()
    if not data.get("current") or not data.get("hourly"):
        raise ValueError("Missing weather fields")
    return {"id": key, "latitude": latitude, "longitude": longitude, "retrieved_at": utcnow(), "current": data["current"], "hourly": data["hourly"], "units": data["current_units"], "model": "DWD ICON (Open-Meteo seamless)", "attribution": "DWD / Open-Meteo · CC BY 4.0", "modeled": True}
