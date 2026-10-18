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

- 31 Python regression tests (including preservation of local detail in large camera frames): CSV/schema validation, UTC parsing, provider timeouts without credential disclosure, coordinate and polygon validity, independent area calculation, holes, symmetric growth, missing coverage, contraction, record deduplication, durable publication retry, access/origin/CSRF protection, review/publish/withdraw, upload rejection, interrupted camera recovery and temporal confirmation.
- TypeScript type checking and production Site build.
- Local D1-backed HTTP checks: missing credentials rejected; collector/operator role separation; browser-origin rejection; invalid coordinates rejected; repeated ingestion deduplicated; approved perimeter visible only with a published incident; withdrawal hides it; private evidence unavailable. Windows Miniflare sometimes restarts after an early rejected POST; the check retries that specific adapter response. Product publication retries transient failures independently.
- Real model weights downloaded from the official PyroVision v0.2.0 release, verified against SHA256 `e536564ef97d2aed90a7572f08ca752087fc10f7c3544911edca70f473d55fc7`; all model state keys matched the current Holocron implementation.
- End-to-end isolated MP4 replay: 28 real Getty Fire camera archive frames encoded as a clearly accelerated video and processed; zero automatic candidates and one image manually selected as evidence (3.89 frames/s with the current detector); two explicitly synthetic georeferenced boundaries approved; 15.948 ha added area calculated; publication visibility and withdrawal checked. No fixture incidents were sent to the public site.
- Geometry arithmetic: 298.9868847 ha versus 298.9868881 ha from independent WGS84 geodesic calculation, a relative difference of approximately 0.00000115%. This validates the area calculation for that test geometry, not the accuracy of fire delineation.
- dNBR processing tested on georeferenced four-band synthetic before/after rasters. All-cloud coverage correctly prevents an outline. Drone raster previews retain georeferencing and exclude nodata from their observed footprint.

## Camera revision: fewer false alarms, operational acceptance FAILED

ReXNet crop-maximum scores previously promoted many non-fire scenes. The worker now uses a pinned Pyronear YOLO11s ONNX smoke detector with RGB letterboxing, crop-to-frame box transforms and NMS. Five overlapping detections spanning at least four seconds are required for a review item; one item per episode, rearmed after 30 seconds without a positive sample. Scores are uncalibrated. Manual evidence capture remains available. Interrupted recovery, bounded queues and monotonic RTSP time are retained; dropped samples and insufficient throughput are visible.

The frozen [protocol](validation/camera_protocol.json) and [complete results](validation/camera_results.json) include source URLs, SHA256 values, individual scores/boxes, clip durations and alert timestamps. Run `uv run python -m scripts.evaluate_camera --fetch`. Both actual pretrained models were executed on the same inputs; no simulated model outputs were used. The four 2026 HPWREN events postdate the fixed 2025 detector. Getty/Henderson were development only. Stage-one evaluation is preserved in commit b1a02b6; no threshold was adjusted after seeing these holdout scores.

| 66 archive frames: 34 positive / 32 negative | Previous ReXNet | Current smoke detector |
| --- | ---: | ---: |
| True positives / missed positives | 25 / 9 | 15 / 19 |
| False positives / true negatives | 18 / 14 | 1 / 31 |
| Precision | 58.14% | 93.75% |
| Recall | 73.53% | 44.12% |

False-positive frames fell by 94.4%, but recall deteriorated materially. Crosley and Sorrento each had **zero detected positive frames**. These sparse minute-cadence images do not establish continuous alarm rates or event latency. Labels follow the archive's visible-plume onset rather than an independently adjudicated German dataset. Credit: [HPWREN / UCSD](https://www.hpwren.ucsd.edu/FIgLib/).

Seven actual [FURG videos](https://github.com/steffensbola/furg-fire-dataset), at the pinned source revision and their original frame rate, were decoded and sampled once per video second. Five negative clips total **367.73 seconds (6.13 minutes / 0.10215 camera-hours)**. Source XML confirms no annotated fire in the negative clips. Previous pipeline: three false review alerts, 29.37/hour over this short exposure. Current pipeline: zero observed false alerts; **the one-sided 95% Poisson upper bound is still 29.33/hour**, so no low operational false-alert rate is established. The assumptions behind that interval may not describe correlated real camera scenes.

Both positive clips (`hand_held_camera_wildfire`, 25.79 s; `hand_held_batteries_night`, 20.52 s) produced **no current automatic alert**, compared with one each previously. A smoke-only model and a fixed-view spatial policy do not support a general handheld or nighttime flame detector. FURG videos predate upstream training; training overlap is unknown and they are not claimed as an upstream-independent model holdout. No German/night/seasonal field precision or recall is established.

Measured mixed-input CPU inference: previous 8.44 frames/s, current 2.19 frames/s; native large camera frames with ten views achieved only approximately 0.49 frames/s in development. These are local CPU timings, exclude network/decode/operator latency, and do not establish real-time capacity on another PC. No GPU or live RTSP throughput was measured.

Mighty Mongoose v5.1.0 and Tenacious Tiger v8.3.0 were also explored on a small subset after stage-one results were known. They still missed smoke scenes and were not adopted. Those diagnostics are development comparisons, not fresh holdouts. No claims of improved responder readiness are made from them.

**Decision:** retain explicit experimental status and operator review. The camera acceptance gate is failed. The reduction in false alarms does not compensate for missed fires and does not make this an emergency warning system.

## Hosted and provider verification

- Public dashboard deployed on [GitHub Pages](https://kletterrn.github.io/Ignis/), deployment [39167980302](https://github.com/kletterrn/Ignis/actions/runs/39167980302). Relative assets and read-only API configuration are generated by `scripts.prepare_site --github-pages` and published by `pages.yml`. Previous Sites frontend redirects to this address. Dynamic D1/R2/API hosting remains on Sites; GitHub Pages cannot execute that backend.
- Exact-origin CORS permits public GET requests from `https://kletterrn.github.io`; an unrelated origin receives no allow-origin header. Unauthenticated cloud ingestion returns 401; operator routes remain unavailable publicly. Source archives contain no local credentials or raw footage.
- Updated NASA credentials stored locally and in the existing GitHub Actions secret. [Collector run 39168233135](https://github.com/kletterrn/Ignis/actions/runs/39168233135) succeeded: all four FIRMS sources and five weather points connected. Browser showed 93 filtered 24-hour thermal observations, live weather and 4/4 healthy feeds at the verification time. These are unconfirmed thermal observations, including possible non-wildfire heat sources.
- Corrected Copernicus OAuth returned 200. Public STAC search found real Sentinel-2 scenes; authenticated Process returned a 36 × 56 pixel, four-band, georeferenced raster over [13.95,50.85,13.96,50.86], with 100% observed coverage and SCL classes 3/4/5. Product `S2A_MSIL2A_20261016T101041_N0513_R022_T33UVS_20261016T170806`; STAC product start 10:10:41.024 UTC, Process catalog tile time 10:16:48.138 UTC. The former one-second time filter returned an empty TIFF with HTTP 200. Selection now spans ±15 minutes around product start, preserves scene/time-basis provenance, and rejects missing coverage before replacing evidence. Authentication failures are actionable and redacted. Cloud/shadow masking still applies during change mapping.
- The cloud collection path ran on GitHub independently of local processing. The PC was not physically shut down during the check. Scheduled timing remains best effort.

## Still unverified

- The old public NASA/CARTO values were removed from the local configuration and the tracked `.env` was deleted. Provider-side revocation was not performed; historical Git commits still contain the former file.
- No physical camera, RTSP endpoint, thermal sensor or drone was available. Real hardware reconnection, device timestamps, calibration, field georeferencing and thermal interpretation remain unverified.
- Real Sentinel segmentation has not been compared against dated Copernicus ground references. The comparison tool reports overlap, area error and Hausdorff distance when matching candidate/reference polygons are supplied. No real-world perimeter accuracy figure is claimed.
- No real-world direction/velocity accuracy, uptime guarantee, emergency-response acceptance or predictive spread capability is claimed. Weather is modeled context; area change is derived only from compatible approved observations.
- Browser resizing, touch interaction and prolonged multi-day soak behavior have not been comprehensively validated.
- Current Shapely/PyTorch versions emit upstream deprecation warnings; execution and checks pass. The warnings are not hidden.
