import os
import httpx
import pandas as pd

from io import StringIO
from dotenv import load_dotenv

load_dotenv()

#API Key laden
map_key = os.getenv("FIRMS_MAP_KEY")

#NASA FIRMS API
source = "VIIRS_NOAA21_NRT"
area = "5.8,47.2,15.1,55.1"
days = 2

url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{source}/{area}/{days}"

#Satellitendaten abrufen
response = httpx.get(url, timeout=40)
response.raise_for_status()

#CSV in DataFrame umwandeln
df = pd.read_csv(StringIO(response.text))

#Daten anzeigen
print("Anzahl Beobachtungen:", len(df))
print("Spalten:", df.columns.tolist())
print(df.head(3))