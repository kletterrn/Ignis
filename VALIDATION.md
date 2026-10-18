# Ignis pilot validation · 18 October 2026

This is an implemented field-pilot platform, with significant detection and field-validation limits. It is not an operational wildfire warning system.

## 3D, stereo and thermal increment

- 25 Python checks and two JavaScript map checks pass locally. New checks run real
  OpenCV stereo matching on a deterministic synthetic 4 m plane, reject invalid
  calibration and unsynchronized pairs, verify scaled Kelvin temperatures,
  nodata coverage and projected threshold area, and enforce local-only results
  without automatic publication. CI now installs OpenCV; PyTorch-specific checks
  still require the local locked environment.
- Stereo reference result: median 4.000 m, valid-pixel fraction approximately
  43.52%, depth range 3.979–4.021 m. This is synthetic geometry, not real sensor
  accuracy. PLY/NPZ exports and a rotatable local point cloud are implemented.
- Synthetic thermal input: 20 / 80 °C, 256 hot pixels at 4 m² each, candidate
  footprint 0.1024 ha. Temperature metadata, scale/offset, masks, unit conversion
  and input/calibration provenance are retained. Thermal thresholds never create
  confirmed incidents or approved perimeters automatically.
- Public/shared map has real Terrarium DEM terrain at vertical scale 1:1,
  2D/3D switching, compass and fullscreen. MapLibre was updated from 5.6.0 to
  5.24.0 after browser testing found terrain-switching renderer failures; styles
  rebuild their DEM sources together. Terrain tiles were verified reachable with
  CORS. DEM resolution/date vary and are not survey accuracy claims.
- Code is Apache-2.0 with third-party data notices. SENSOR_GUIDE.md documents the
  sensor contract and fixtures; RESPONDER_READINESS.md records agency acceptance
  gates. No real stereo/thermal hardware calibration or field test was available.
- Browser operator checks completed both sensor upload forms using the synthetic
  fixtures, produced the expected values and download links, and retained result
  history across reload. Shared 3D imagery terrain rendered successfully after
  the renderer update. A forced terrain-provider outage was not browser-tested.
- The first cloud CI run exposed an unbounded test dependency install selecting
  OpenCV 5 despite the application requiring OpenCV <5. CI now uses the tested
  direct versions from uv.lock via requirements-ci.txt, without PyTorch weights.
  The corrected [GitHub run 39166712248](https://github.com/kletterrn/Ignis/actions/runs/39166712248) passed both core and Site jobs.

## Passed locally

- 25 Python regression tests (including preservation of local detail in large camera frames): CSV/schema validation, UTC parsing, provider timeouts without credential disclosure, coordinate and polygon validity, independent area calculation, holes, symmetric growth, missing coverage, contraction, record deduplication, durable publication retry, access/origin/CSRF protection, review/publish/withdraw, upload rejection, interrupted camera recovery and temporal confirmation.
- TypeScript type checking and production Site build.
- Local D1-backed HTTP checks: missing credentials rejected; collector/operator role separation; browser-origin rejection; invalid coordinates rejected; repeated ingestion deduplicated; approved perimeter visible only with a published incident; withdrawal hides it; private evidence unavailable. Windows Miniflare sometimes restarts after an early rejected POST; the check retries that specific adapter response. Product publication retries transient failures independently.
- Real model weights downloaded from the official PyroVision v0.2.0 release, verified against SHA256 `e536564ef97d2aed90a7572f08ca752087fc10f7c3544911edca70f473d55fc7`; all model state keys matched the current Holocron implementation.
- End-to-end isolated MP4 replay: 28 real Getty Fire camera archive frames encoded as a clearly accelerated video and processed; one automatic candidate and one image manually selected as evidence; two explicitly synthetic georeferenced boundaries approved; 15.948 ha added area calculated; publication visibility and withdrawal checked. No fixture incidents were sent to the public site.
- Geometry arithmetic: 298.9868847 ha versus 298.9868881 ha from independent WGS84 geodesic calculation, a relative difference of approximately 0.00000115%. This validates the area calculation for that test geometry, not the accuracy of fire delineation.
- dNBR processing tested on georeferenced four-band synthetic before/after rasters. All-cloud coverage correctly prevents an outline. Drone raster previews retain georeferencing and exclude nodata from their observed footprint.

## Camera detection results: sensitivity improved, false alarms remain unacceptable

The model was evaluated on 28 sampled images from the October 15, 2026 HPWREN FIgLib Henderson Fire / Buffalo Bump South sequence, after the July 2022 weight release. Labels follow the archive's offset from first visible plume: 14 negative and 14 positive frames. Credit: [HPWREN / UCSD](https://www.hpwren.ucsd.edu/FIgLib/).

The initial whole-frame baseline, at score threshold 0.7:

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

The initial failure was traced to lost plume detail during whole-frame resizing. The final implementation evaluates the full frame plus nine overlapping half-frame crops, each with the same pretrained normalization and input size, and uses the maximum score. The threshold remains 0.7; no model training was performed. The Henderson sequence was used to diagnose that change and is not a held-out test of the revised algorithm.

A second, previously unused sequence — September 9, 2026 Getty Fire / Mount Wilson West — provides the final chronological holdout of 14 negative and 14 positive samples:

| Final crop-based metric | Result |
| --- | --- |
| True positives / false negatives | 13 / 1 |
| False positives / true negatives | 14 / 0 |
| Recall | 92.86% |
| Precision | 48.15% |
| CPU classifier throughput | Approximately 3.17 complete frames/second |
| MP4 worker replay throughput | Approximately 3.64 frames/second |
| False alerts per hour | Not established on continuous footage |

These results do **not** establish operational reliability. Cropping improves sensitivity but introduces severe false positives on this sequence. Baseline and holdout summaries are committed in `validation/results.json`; full local scores are under `outputs/`.

Three consecutive positive samples are needed for an automatic review item; human capture is available regardless of the model score. The small sample does not represent German conditions, night scenes, fog, weather extremes, other cameras or continuous alert behavior. GPU acceleration was unavailable in the installed PyTorch runtime; GPU throughput was not measured. Raw JSON results are reproducible under ignored `outputs/` using the scripts documented in README.

## Hosted verification

- Public Site deployment succeeded at [Ignis](https://ignis-fire-monitoring.davidkhaliqi05.chatgpt.site).
- Live collection/publication of five DWD ICON / Open-Meteo model points succeeded. All four FIRMS sources report `configuration_missing`, as requested. No synthetic fire events are published.
- Anonymous public reads work. Unauthenticated cloud writes return 401; `/operator` is absent from the hosted Site.
- Public browser review showed the map, unconfigured satellite state, live weather values and source-health details without JavaScript errors.
- [GitHub CI](https://github.com/kletterrn/Ignis/actions/runs/39164781109) passed for the implementation. [Cloud collector run 39164873501](https://github.com/kletterrn/Ignis/actions/runs/39164873501) completed successfully on GitHub and updated the public weather data at 20:47 UTC; the schedule targets minutes 7, 22, 37 and 52. This verifies the cloud execution path independently of local processing; the PC was not physically powered off during the test. Scheduled timing remains best effort. OpenCV sensor and camera-worker checks run in CI; the PyTorch-specific classifier-detail check runs locally and is skipped by the lightweight CI runtime.

## Intentionally unconfigured or still unverified

- NASA FIRMS access and Copernicus download credentials remain empty at the user's request. STAC discovery and imported-raster processing are implemented. Successful authenticated Copernicus download and live satellite ingestion remain unverified.
- The old public NASA/CARTO values were removed from the local configuration and the tracked `.env` was deleted. Provider-side revocation was not performed; historical Git commits still contain the former file.
- No physical camera, RTSP endpoint, thermal sensor or drone was available. Real hardware reconnection, device timestamps, calibration, field georeferencing and thermal interpretation remain unverified.
- Real Sentinel segmentation has not been compared against dated Copernicus ground references. The comparison tool reports overlap, area error and Hausdorff distance when matching candidate/reference polygons are supplied. No real-world perimeter accuracy figure is claimed.
- No real-world direction/velocity accuracy, uptime guarantee, emergency-response acceptance or predictive spread capability is claimed. Weather is modeled context; area change is derived only from compatible approved observations.
- Browser resizing, touch interaction and prolonged multi-day soak behavior have not been comprehensively validated.
- Current Shapely/PyTorch versions emit upstream deprecation warnings; execution and checks pass. The warnings are not hidden.
