# Agency and responder deployment

Ignis currently supports supervised analysis and technical evaluation. It has not
passed operational acceptance as a warning or dispatch system. Public access and
an open-source license do not establish field reliability.

## What the implemented platform does

- Public German dashboard and API, 2D / 3D terrain, weather and source freshness.
- Four NASA FIRMS adapters, local video / image / RTSP inference and human review.
- Georeferenced drone raster / GeoJSON imports, Sentinel-2 search and authenticated
  download adapter, masked dNBR candidates, editable approved perimeter history.
- EPSG:3035 area, compatible dated boundary comparisons and growth sectors.
- Local calibrated stereo-pair depth/point clouds and radiometric GeoTIFF apparent
  temperature/threshold-footprint measurements; see SENSOR_GUIDE.md.
- Local-only raw footage and credentials; explicit selected-evidence publication,
  withdrawal and retriable outbox; independent collector / operator write tokens.
- Reproducible tests and replay fixtures. See VALIDATION.md for actual results.

The 3D map drapes the same reviewed boundaries and weather on a bare-earth DEM.
The vertical scale is 1:1. Hectares remain projected footprint areas. It does not
measure flame height or volume, reconstruct drone meshes, perform physical camera
calibration, or predict spread. The separate stereo adapter accepts supplied
calibration and synchronized pairs; its coordinates remain local to the camera.
Terrain, satellite basemap and incident imagery can
have different dates and resolutions. DEM relief is not survey-grade evidence.

## Current release acceptance

| Gate | Evidence now | Required before operational reliance |
| --- | --- | --- |
| Live detection feeds | All four NASA feeds + weather collected on GitHub; corrected Copernicus OAuth and real raster download verified | Outage/recovery exercise and documented coverage/revisit gaps |
| Camera reliability | Four-event holdout: 15 TP, 19 FN, 1 FP, 31 TN; 0/2 positive videos alerted. Acceptance FAILED. See VALIDATION.md | Independent German day/night/season/negative footage, calibrated operating threshold, recall/precision and continuous false alerts per camera-hour agreed with the agency |
| Physical hardware | Recorded replay and restart tests work | Real RTSP loss/reconnect, timestamp drift, device calibration, power/network interruption, sustained throughput and evidence provenance |
| Perimeter quality | Geometry arithmetic and synthetic dNBR checks pass | Dated real Sentinel/drone comparisons against independent reference products; report IoU and delineation error separately from area arithmetic |
| Movement interpretation | Compatible boundary differencing, missing-coverage and symmetric-growth guards | Field verification of observed growth and sampling limits; preserve uncertainty and avoid inferring the fire front from wind |
| Security / access | Loopback operator, CSRF/origin guards, write-role isolation and private evidence checks | Agency security review, token rotation/recovery exercise, audited operator access, approved camera placement and evidence retention policy |
| Service resilience | GitHub collection and durable local publication retry demonstrated | Agreed availability/latency target, external monitoring and alert escalation, restore-tested backups, multi-day soak/load tests and a responsible on-call operator |
| Incident use | Human review and public withdrawal supported | Named agency sponsor, documented operating procedure, operator training and signed acceptance criteria |

The current architecture assumes one local operator. Shared agency operator
accounts, dispatch integrations, guaranteed scheduling, and an operational alert
escalation service are not implemented. The free-hosted pilot is best effort.

## Supervised evaluation procedure

1. Clone the public repository, retain licenses, run the locked installation and
   regression checks. Keep credentials and raw evidence outside version control.
2. Use a separate test deployment and test tokens. Run the isolated replay;
   verify review, mapped perimeter, dated comparison, publication and withdrawal.
3. Configure live providers and a permitted camera with a documented field of
   view. Establish independent reference labels before selecting a threshold.
4. Measure continuous false alerts, missed events, latency and outages. Validate
   mappings against independently dated/georeferenced evidence.
5. Exercise offline/restart/publication failures and restore backups. Publish
   only reviewed findings and preserve their acquisition times and limitations.
6. Record agency-specific acceptance results and unresolved risks. Until accepted,
   maintain established emergency observation/reporting procedures independently.

No software check in this repository substitutes for those field acceptance steps.
