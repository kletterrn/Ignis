# Ignis pilot validation · 18 October 2026

This is an implemented field-pilot platform, with significant detection and field-validation limits. It is not an operational wildfire warning system.

## Passed locally

- 20 Python regression tests: CSV/schema validation, UTC parsing, provider timeouts without credential disclosure, coordinate and polygon validity, independent area calculation, holes, symmetric growth, missing coverage, contraction, record deduplication, durable publication retry, access/origin/CSRF protection, review/publish/withdraw, upload rejection, interrupted camera recovery and temporal confirmation.
- TypeScript type checking and production Site build.
- Local D1-backed HTTP checks: missing credentials rejected; collector/operator role separation; browser-origin rejection; invalid coordinates rejected; repeated ingestion deduplicated; approved perimeter visible only with a published incident; withdrawal hides it; private evidence unavailable. Windows Miniflare sometimes restarts after an early rejected POST; the check retries that specific adapter response. Product publication retries transient failures independently.
- Real model weights downloaded from the official PyroVision v0.2.0 release, verified against SHA256 `e536564ef97d2aed90a7572f08ca752087fc10f7c3544911edca70f473d55fc7`; all model state keys matched the current Holocron implementation.
- End-to-end isolated replay: 28 real camera archive frames processed; one image manually selected as evidence; two explicitly synthetic georeferenced boundaries approved; 15.948 ha added area calculated; publication visibility and withdrawal checked. No fixture incidents were sent to the public site.
- Geometry arithmetic: 298.9868847 ha versus 298.9868881 ha from independent WGS84 geodesic calculation, a relative difference of approximately 0.00000115%. This validates the area calculation for that test geometry, not the accuracy of fire delineation.
- dNBR processing tested on georeferenced four-band synthetic before/after rasters. All-cloud coverage correctly prevents an outline. Drone raster previews retain georeferencing and exclude nodata from their observed footprint.

## Camera detection result: insufficient for field reliance

The model was evaluated on 28 sampled images from the October 15, 2026 HPWREN FIgLib Henderson Fire / Buffalo Bump South sequence, after the July 2022 weight release. Labels follow the archive's offset from first visible plume: 14 negative and 14 positive frames. Credit: [HPWREN / UCSD](https://www.hpwren.ucsd.edu/FIgLib/).

At the implemented 0.7 score threshold:

| Metric | Result |
| --- | --- |
| True positives | 0 |
| False negatives | 14 |
| False positives | 0 |
| Recall | 0% |
| Precision | Undefined: no positive predictions |
| CPU classifier throughput | Approximately 21.3 frames/second on this PC |
| Full local worker replay | Approximately 18 frames/second |
| False alerts per hour | Not established; sparse minute-spaced images are not continuous video |

There was no threshold tuning or model training against this sample. Three consecutive positive samples are needed for an automatic review item; human capture is available regardless of the model score. The small sample does not represent German conditions, night scenes, fog, weather extremes, other cameras or continuous alert behavior. GPU acceleration was unavailable in the installed PyTorch runtime; GPU throughput was not measured. Raw JSON results are reproducible under ignored `outputs/` using the scripts documented in README.

## Hosted verification

- Public Site deployment succeeded at [Ignis](https://ignis-fire-monitoring.davidkhaliqi05.chatgpt.site).
- Live collection/publication of five DWD ICON / Open-Meteo model points succeeded. All four FIRMS sources report `configuration_missing`, as requested. No synthetic fire events are published.
- Anonymous public reads work. Unauthenticated cloud writes return 401; `/operator` is absent from the hosted Site.
- Public browser review showed the map, unconfigured satellite state, live weather values and source-health details without JavaScript errors.
- Cloud collector scheduling and CI results are recorded in GitHub Actions; the schedule targets minutes 7, 22, 37 and 52. A successful runner execution verifies cloud collection independently of this PC; scheduled timing is still best effort.

## Intentionally unconfigured or still unverified

- NASA FIRMS access and Copernicus download credentials remain empty at the user's request. STAC discovery and imported-raster processing are implemented. Successful authenticated Copernicus download and live satellite ingestion remain unverified.
- The old public NASA/CARTO values were removed from the local configuration and the tracked `.env` was deleted. Provider-side revocation was not performed; historical Git commits still contain the former file.
- No physical camera, RTSP endpoint, thermal sensor or drone was available. Real hardware reconnection, device timestamps, calibration, field georeferencing and thermal interpretation remain unverified.
- Real Sentinel segmentation has not been compared against dated Copernicus ground references. The comparison tool reports overlap, area error and Hausdorff distance when matching candidate/reference polygons are supplied. No real-world perimeter accuracy figure is claimed.
- No real-world direction/velocity accuracy, uptime guarantee, emergency-response acceptance or predictive spread capability is claimed. Weather is modeled context; area change is derived only from compatible approved observations.
- Browser resizing, touch interaction and prolonged multi-day soak behavior have not been comprehensively validated.
- Current Shapely/PyTorch versions emit upstream deprecation warnings; execution and checks pass. The warnings are not hidden.
