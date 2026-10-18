# Third-party software and data

The root Apache-2.0 license covers Ignis code, including the local processor and
web application. It does not relicense dependencies, pretrained weights, tiles,
imagery, or third-party observations. Retain their notices when redistributing.
Dependency versions are recorded in `uv.lock` and `site/package-lock.json`;
installed packages contain their own license notices.

| Component / source | License or terms / attribution |
| --- | --- |
| MapLibre GL JS | BSD-3-Clause; https://github.com/maplibre/maplibre-gl-js |
| Pyronear YOLO11s checkpoint | Downloaded separately, pinned revision/SHA256 in `services/camera.py`. The Hugging Face card labels Apache-2.0 but the actual ONNX metadata states AGPL-3.0; retain both notices and resolve licensing with the upstream publisher before redistributing weights or offering a derivative model service. https://huggingface.co/pyronear/yolov11s and https://ultralytics.com/license |
| ONNX Runtime | MIT; https://github.com/microsoft/onnxruntime |
| FURG Fire Dataset | CC0; Steffens et al., https://github.com/steffensbola/furg-fire-dataset. Videos/XML downloaded locally for validation only. |
| PyroVision and Holocron | Apache-2.0; official weight URL and SHA256 in `services/camera.py`; https://github.com/pyronear/pyro-vision |
| OpenStreetMap | © OpenStreetMap contributors, ODbL data; tile service has separate usage policy: https://www.openstreetmap.org/copyright and https://operations.osmfoundation.org/policies/tiles/ |
| Esri World Imagery | Esri and contributing imagery providers; visible source attribution is retained. Service terms apply: https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9 |
| Terrain Tiles on AWS | Mapzen / Tilezen aggregated DEM; attribution varies by source. Europe terrain data produced using Copernicus data and information funded by the European Union — EU-DEM layers; Austria © offene Daten Österreichs — Digitales Geländemodell (DGM) Österreich; global SRTM / GMTED2010 courtesy of USGS; global ETOPO1 courtesy of NOAA. Complete credits: https://github.com/tilezen/joerd/blob/master/docs/attribution.md; dataset: https://registry.opendata.aws/terrain-tiles/ |
| DWD ICON / Open-Meteo weather | Modeled weather, CC BY 4.0 attribution; public free API used for the noncommercial pilot. https://open-meteo.com/en/docs/dwd-api and https://open-meteo.com/en/terms |
| NASA FIRMS | NASA FIRMS and the named MODIS / VIIRS source retained per observation; https://www.earthdata.nasa.gov/data/tools/firms |
| Copernicus Sentinel | Copernicus Sentinel data terms, acquisition dates and product identifiers retained; https://dataspace.copernicus.eu/ |
| HPWREN FIgLib validation imagery | © HPWREN / UCSD, https://www.hpwren.ucsd.edu/FIgLib/. Downloaded locally only; not included in GitHub or the public Site. |

Terrain tiles are visualization context. Their resolution and acquisition dates
vary; a 1:1 vertical display is not a claim of surveyed height accuracy. Tile
services and the noncommercial weather endpoint provide no Ignis uptime guarantee.
Agency or commercial deployments must verify their intended provider usage and
provision suitable services; the software does not activate paid accounts.
