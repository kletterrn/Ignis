# Stereo and thermal measurements

These local operator tools process supplied calibrated data. They do not validate
the calibration's truth or provide operational accuracy guarantees. Raw inputs,
measurement records and exports remain under ignored `data/measurements/`. Nothing
is added to public incidents or the cloud publication queue automatically.

## Reproducible demonstration

```powershell
uv run python -m scripts.sensor_fixtures
uv run pytest tests/test_sensors.py -q
.\Launch-Ignis.ps1
```

Open `/operator`, sections 5 and 6. The fixture files are under
`data/sensor-fixtures/`. They are explicitly synthetic: stereo has a known 4 m
plane; the thermal image has 20 °C background and an 80 °C square. Use
`2026-10-18T00:00:00.000` for both stereo UTC acquisition fields. They demonstrate
software arithmetic and matching, not field accuracy.

## Stereo input contract

Provide a synchronized left/right PNG or JPEG pair and an OpenCV pinhole stereo
calibration JSON. Required fields:

```json
{
  "calibration_id": "YOUR-RIG-CALIBRATION-REFERENCE",
  "calibrated_at": "2026-01-01T00:00:00Z",
  "translation_unit": "m",
  "rms_px": 0.3,
  "image_size": [320, 192],
  "K1": [[240,0,160],[0,240,96],[0,0,1]],
  "K2": [[240,0,160],[0,240,96],[0,0,1]],
  "D1": [0,0,0,0,0], "D2": [0,0,0,0,0],
  "R": [[1,0,0],[0,1,0],[0,0,1]], "T": [-0.2,0,0]
}
```

The numerical matrices above are an example, **not your camera calibration**.
`K1/K2` contain pixel intrinsics; `D1/D2` distortion; `R/T` transform left to right
camera coordinates, with translation in metres. The adapter supports horizontal
rigs with negative T.x. It rejects a zero baseline, invalid rotation/intrinsics,
nonfinite parameters, RMS above 2 pixels, a timestamp difference above 50 ms,
future calibration dates, changed image size, or oversized images. Maximum image
size is 2 million pixels and width 2048. The RMS and acquisition timestamps are
supplied metadata, not independently verified acceptance evidence.

OpenCV rectifies the pair, runs StereoSGBM in both directions and excludes
inconsistent matches, invalid rectification margins and depths outside
0.05–2000 m. Fewer than 100 valid pixels suppress the measurement. The disparity
search is bounded to at most 128 pixels; unsupported geometry/ranges may produce
no usable depth. Check coverage and source imagery, not just the median depth.

Outputs: local rotatable RGB point-cloud preview, PLY cloud (up to 100,000 points),
NPZ depth in metres with a valid-pixel mask and Q matrix, preview and JSON report
with calibration/input hashes. Coordinates are in the rectified left-camera
frame (x right, y down, z forward). They are **not georeferenced**. The scene-depth
summary is not an object-specific fire measurement. Smoke, flames, vegetation
motion, low texture and reflections can break stereo correspondence even when
the numerical calibration is valid. Accurate fire location or dimensions require
independent reference targets, rig pose, synchronization verification and an
appropriate object/surface interpretation; those are not supplied by this tool.

Method: [OpenCV camera calibration and 3D reconstruction](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html).

## Thermal input contract

Export an **orthorectified, georeferenced, single-band radiometric GeoTIFF** from
your sensor/vendor processing software, with valid-data/nodata information. A
palette JPEG or a normal thermal-looking RTSP video is not radiometric input.
GeoTIFF metadata tags must contain:

```text
TEMPERATURE_UNIT=Celsius             # or Kelvin
TEMPERATURE_KIND=apparent
SENSOR_ID=your-sensor-reference
CALIBRATION_ID=your-calibration-reference
CALIBRATED_AT=2026-01-01T00:00:00Z
ACQUIRED_AT=2026-10-18T00:00:00Z
```

Pixel conversion is `raw * band_scale + band_offset`, then Kelvin minus 273.15
when applicable. Rasterio's GeoTIFF band scale and offset default to 1 and 0;
the sensor export must supply correct values. Inputs are bounded to 4 million
pixels and the Germany pilot region; missing metadata, nonfinite scale/offset,
unsupported units, calibration after acquisition, no valid pixels and temperatures
outside -273.15–3000 °C are rejected. The current adapter accepts apparent
radiometric temperature only; it does not apply unknown vendor calibration or
atmospheric/emissivity corrections.

Outputs: valid-pixel min/median/max apparent temperature, user-selected threshold,
candidate heat footprint preserving holes/nodata, EPSG:3035 footprint hectares,
coverage, input SHA256, red threshold preview and GeoJSON/JSON exports. Thermal
candidate outlines appear dashed red on the local map and remain explicitly
unvalidated. Threshold area is not a confirmed wildfire or currently flaming
area. Ordinary sensor perspective frames must first be orthorectified using valid
pose/terrain information before claiming a ground footprint.

Method: [Rasterio dataset metadata, scales and offsets](https://rasterio.readthedocs.io/en/stable/api/rasterio.io.html).

## Hardware acceptance still needed

Use traceable distance targets for stereo, and calibrated blackbody/reference
temperature targets for thermal. Test operating ranges, sensor saturation,
emissivity, atmosphere, camera drift, synchronization and georeferencing. Record
independent errors and rejection rates. No actual stereo rig, radiometric sensor
or field accuracy test was available for this implementation.
