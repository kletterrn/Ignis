import logging
import os

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from providers.nasa_firms import FIRMSDataError, fetch_observations
from services.observations import filter_by_hours, serialize_observation


#app.py location
BASE_DIR = Path(__file__).resolve().parent

#Loading API + Flask
#Load variables from .env
load_dotenv(BASE_DIR / ".env")

#Create Flask app
app = Flask(__name__)

#Configuration for Project Ignis
app.config.update(
    FIRMS_MAP_KEY=os.getenv("FIRMS_MAP_KEY", "").strip(),
    FIRMS_SOURCE=os.getenv("FIRMS_SOURCE", "VIIRS_NOAA21_NRT").strip(),
    FIRMS_AREA=os.getenv("FIRMS_AREA", "5.8,47.2,15.1,55.1").strip(),
    CARTO_BASEMAP_API_KEY=os.getenv("CARTO_BASEMAP_API_KEY", "").strip(),
)

# All avaliable Satellites 

SATELLITE_SOURCES = {
    "VIIRS_NOAA21_NRT": "NOAA-21 · VIIRS",
    "VIIRS_NOAA20_NRT": "NOAA-20 · VIIRS",
    "VIIRS_SNPP_NRT": "Suomi-NPP · VIIRS",
    "MODIS_NRT": "Terra / Aqua · MODIS",
}


#MAP

def region_view(area):

    try:
        west, south, east, north = map(float, area.split(","))

        valid_longitude = -180 <= west < east <= 180
        valid_latitude = -90 <= south < north <= 90

        if valid_longitude and valid_latitude:
            return {
                "bounds": [
                    [west, south],
                    [east, north]
                ]
            }

    except ValueError:
        pass

    return {"center": [0, 20], "zoom": 2}



@app.get("/")
def index():

    #Config send to Frontend
    config_data = {
        "source": app.config["FIRMS_SOURCE"],
        "area": app.config["FIRMS_AREA"],
        "view": region_view(app.config["FIRMS_AREA"]),
        "cartoKey": app.config["CARTO_BASEMAP_API_KEY"],
        "sources": SATELLITE_SOURCES,
    }

    #Load index
    return render_template("index.html", config_data=config_data)



@app.get("/api/observations")
def observations_api():

    #Get the selected time window from the URL
    #Example: /api/observations?hours=6
    hours = request.args.get("hours", "24")

    #Time
    if hours not in ("1", "6", "12", "24"):
        return jsonify(
            error="Wähle ein Zeitfenster von 1, 6, 12 oder 24 Stunden."
        ), 400

    hours = int(hours)

    #Get the selected satellite data from the URL
    #If no sources are selected, use default satellite
    selected = request.args.get(
        "sources",
        app.config["FIRMS_SOURCE"]
    )

    sources = selected.split(",")

    #Remove duplicates
    sources = list(dict.fromkeys(source.strip() for source in sources))

    #Check if selected satellites are supported
    for source in sources:

        if source not in SATELLITE_SOURCES:
            return jsonify(
                error="Select one or more supported satellite sources."
            ), 400

    #UT
    now = datetime.now(timezone.utc)

    #Get NASA FIRMS API
    key = app.config["FIRMS_MAP_KEY"]

    payload = {
        "observations": [],
        "checked_at": now.isoformat(),
        "hours": hours,
        "source": ",".join(sources),
        "area": app.config["FIRMS_AREA"],
        "sources": [],
    }

    #If user didnt import API Key
    if not key or key == "REPLACE_WITH_YOUR_OWN_KEY":

        return jsonify(
            **payload,
            status="configuration_missing",
            message="Add your NASA FIRMS map key to .env, then restart the app."
        )

    #AI generated. Connecting several satellites
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:

        futures = {}

        #Start downloading the data
        for source in sources:

            futures[source] = executor.submit(
                fetch_observations,
                key,
                source,
                app.config["FIRMS_AREA"],
                2
            )

        #for duplicates
        seen = set()

        #results
        for source, future in futures.items():
            try:
                #Wait for satellite response
                records = future.result()

                #Keep observations within the selected time window
                records = filter_by_hours(records, hours, now)

            except FIRMSDataError as exc:

                #Error logging
                app.logger.warning(
                    "FIRMS %s unavailable: %s",
                    source,
                    exc.safe_reason
                )

                payload["sources"].append({
                    "id": source,
                    "label": SATELLITE_SOURCES[source],
                    "status": "unavailable",
                    "count": 0
                })

                continue

            #Count
            count = 0

            for record in records:

                #For dupes
                identity = (
                    record.satellite,
                    record.sensor,
                    record.latitude,
                    record.longitude,
                    record.detected_at
                )

                #skipping dupes
                if identity in seen:
                    continue

                #saving seen data
                seen.add(identity)
                item = serialize_observation(record)

                #From where came the data
                item["dataset"] = source
                payload["observations"].append(item)

                count += 1

            #Remember that this satellite responded successfully
            payload["sources"].append({
                "id": source,
                "label": SATELLITE_SOURCES[source],
                "status": "connected",
                "count": count
            })


    payload["observations"].sort(
        key=lambda item: item["detected_at"],
        reverse=True
    )

    #Count how many satellites responded
    successful = 0

    for source in payload["sources"]:

        if source["status"] == "connected":
            successful += 1

    #determine the connection status
    if successful == len(sources):

        status = "connected"
        message = "Selected satellite feeds received."

    elif successful > 0:

        status = "partial"
        message = "Some satellite feeds are unavailable."

    else:

        status = "unavailable"
        message = "NASA FIRMS is unavailable. Check your configuration."

    http_status = 200 if successful > 0 else 502

    return jsonify(
        **payload,
        status=status,
        message=message
    ), http_status



@app.get("/health")
def health():

    return jsonify(
        status="ok",
        name="Project Ignis"
    )



if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "8000")),
        debug=False
    )