"""Copy shared dashboard assets; never copy local environment or operator credentials."""
import json
import argparse
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from providers.nasa_firms import AREA,SATELLITE_SOURCES
from services.assets import asset_url
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--github-pages',action='store_true');args=parser.parse_args()
config={"source":"VIIRS_NOAA21_NRT","sources":SATELLITE_SOURCES,"area":AREA,"view":{"bounds":[[5.8,47.2],[15.1,55.1]]},"cartoKey":"","operator":False,"csrf":None,
        "apiBase":"https://ignis-fire-monitoring.davidkhaliqi05.chatgpt.site" if args.github_pages else '',"homeUrl":"./" if args.github_pages else '/'}
env=Environment(loader=FileSystemLoader(ROOT/"templates"),autoescape=True)
env.globals['asset_url']=lambda filename:asset_url(filename,'./static/' if args.github_pages else '/static/')
html=env.get_template("index.html").render(config_data=config,url_for=lambda _,filename:("./static/" if args.github_pages else "/static/")+filename)
if not args.github_pages:
    html='<!doctype html><html lang="de"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=https://kletterrn.github.io/Ignis/"><link rel="canonical" href="https://kletterrn.github.io/Ignis/"><title>Ignis ist auf GitHub umgezogen</title><p><a href="https://kletterrn.github.io/Ignis/">Ignis auf GitHub Pages öffnen</a></p></html>'
target=ROOT/"outputs"/"github-pages" if args.github_pages else ROOT/"site"/"public"
target.mkdir(parents=True,exist_ok=True)
(target/("index.html" if args.github_pages else "dashboard.html")).write_text(html,encoding="utf-8")
shutil.copytree(ROOT/"static",target/"static",dirs_exist_ok=True)
print("Shared public dashboard prepared (operator disabled)")
