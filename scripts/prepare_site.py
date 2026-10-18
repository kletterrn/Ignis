"""Copy shared dashboard assets; never copy local environment or operator credentials."""
import json
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from providers.nasa_firms import AREA,SATELLITE_SOURCES
ROOT=Path(__file__).resolve().parents[1]
config={"source":"VIIRS_NOAA21_NRT","sources":SATELLITE_SOURCES,"area":AREA,"view":{"bounds":[[5.8,47.2],[15.1,55.1]]},"cartoKey":"","operator":False,"csrf":None}
env=Environment(loader=FileSystemLoader(ROOT/"templates"),autoescape=True)
html=env.get_template("index.html").render(config_data=config,url_for=lambda _,filename:"/static/"+filename)
target=ROOT/"site"/"public"
target.mkdir(exist_ok=True)
(target/"dashboard.html").write_text(html,encoding="utf-8")
shutil.copytree(ROOT/"static",target/"static",dirs_exist_ok=True)
print("Shared public dashboard prepared (operator disabled)")
