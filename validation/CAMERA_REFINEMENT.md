# Camera refinement · 19 October 2026

The new flame branch recovers additional real fire clips without adding false alerts on this replay. Smoke detection is still inadequate for operational reliance. Scores are uncalibrated; every automatic item remains a local review candidate.

## Implementation

- Retain the pinned Pyronear YOLO11s smoke detector and its 0.5 decision threshold.
- Add the pinned CCTV-AI YOLOv8n **fire class only**, RGB 320 × 320 letterboxing. Its weaker smoke class is unused.
- A flame candidate (score ≥0.5) must also pass PyroVision ReXNet (score ≥0.8) on a crop with 1.5× context, aspect-preserving padding to 384 × 256 and the existing ImageNet normalization. Whole-ROI inference is used; the historical maximum over unrelated crops is not used for verification.
- Confirm five of the last eight spatially overlapping samples of the same class, spanning ≥4 seconds; reset history after a gap >6 seconds. One review item until 30 seconds without a positive sample. Slow but valid RTSP sampling is distinguished from reconnect gaps.
- Keep distinct episodes within the same minute as separate stable evidence IDs. Annotated previews use the actual class; evidence stores the triggering score. Worker throughput no longer counts an extra frame.
- Show declared/decoded frame disagreement in worker health rather than interpreting missing footage as clear conditions.

Weights, preprocessors and thresholds are recorded in `services/camera.py` and the [frozen protocol](camera_refinement_protocol.json). The complete [machine report](camera_refinement_results.json) retains file hashes, source URLs, per-sample boxes/scores, decoding counts and review-alert offsets. No raw footage is published.

## Dataset and split

72 real video files: all 23 MP4 files from the pinned FURG revision and all 49 AVI files in both FIRESENSE archives. These contain controlled fires/smoke, building/vehicle fires, wildfire footage and non-fire scenes. A dark battery-fire clip is **not** a nighttime wildfire field validation. There are 41 source-labeled positive and 31 negative clips. Distinct filenames do not establish distinct incidents; cross-dataset or upstream-training overlap is unknown.

35 clips were assigned to development (34 completed plus the next interrupted clip from the rejected trial). The remaining **37 clips—21 positive, 16 negative—were reserved before the final flame-confirmation rule ran**. They were not used to select its thresholds. Later posthoc smoke-verification extensions were rejected and did not change this rule.

FIRESENSE is credited to Nikos Grammalidis, Kosmas Dimitropoulos and Enis Cetin, CC BY 4.0, DOI [10.5281/zenodo.836749](https://zenodo.org/records/836749). FURG: Steffens et al., [source repository](https://github.com/steffensbola/furg-fire-dataset), repository license CC0; source credits/watermarks are retained. HPWREN images: © HPWREN / UCSD, [FIgLib](https://www.hpwren.ucsd.edu/FIgLib/). Older videos may overlap upstream training; the reserved split tests this implementation, not guaranteed model-training independence.

## Results on the same inputs

Before = previous production smoke-only detector with five consecutive confirmations. After = smoke plus the independently checked flame branch and five-of-eight confirmation.

| Clip-level metric | Before | After |
| --- | ---: | ---: |
| Positive clips alerted, all 72 files | 11 / 41 | 26 / 41 |
| Recall, all positive clips | 26.83% | 63.41% |
| Precision, positive/negative clip decisions | 68.75% | 83.87% |
| False review alerts | 5 | 5 |
| Negative decoded exposure | 21.13 min | 21.13 min |
| Replay-normalized false alerts/hour | 14.20 | 14.20 |
| Reserved positive clips alerted | 5 / 21 | 11 / 21 |
| Reserved-set recall | 23.81% | 52.38% |
| Reserved-set precision | 62.50% | 78.57% |
| Reserved negative clips with alerts | 3 / 16 | 3 / 16 |

The 15 additional alerted positive clips are visible-flame recoveries. All five remaining false alerts are smoke alerts, also present in the baseline; their timing can differ. The larger test exposes smoke false alarms absent from the previous six-minute sample. **14.20/hour is an observed replay rate over a short selected dataset, not an operational estimate; it is still unacceptable evidence for autonomous responder warning.**

By source: FURG positive detection 5/17 →14/17, zero negative alerts over 6.64 minutes; FIRESENSE fire 2/11 →8/11, three negative alerts unchanged; FIRESENSE smoke 4/13 →4/13, two negative alerts unchanged. Both original missed positive FURG clips now alert.

The four additional HPWREN events contain 65 frames (33 plume-positive /32 negative): **11 TP,22 FN,0 FP,32 TN**, 33.33% recall. The smoke model is unchanged and no raw flame proposals existed in these frames; its already-computed, hash-matched detections were reused exactly. The new branch therefore cannot recover their missed faint plumes. These minute-cadence images are not continuous false-alert exposure.

## Decode coverage and throughput

44.47 minutes of footage were actually decoded. Five AVI headers disagreed with decoding: four by one frame, and `smoke/neg/testneg03.809.avi` yielded 182 frames (6.07 s) against 748 declared (24.93 s). Only decoded seconds enter exposure. The full-file hash still matches the published dataset archive. No unseen tail is counted as negative footage or clearance.

Measured uncached video inference: **3.36 frames/s on this CPU**, including the flame ROI verifier. Ten development clips reused hash-matched smoke outputs; they are excluded from that throughput figure. This is not end-to-end network latency, cold model-download time, sustained native-resolution RTSP capacity, or a GPU result. Large ten-view camera frames remain below 1 frame/s on this PC; the console warns and reports dropped RTSP samples.

## Checks and rejected alternatives

- 38 Python regressions and five JavaScript checks pass, including class-separated confirmation, slow sampling/reconnects, distinct episodes, decode warnings, model decoding, coordinate/schema validation, industrial context and sensor-scale overlays.
- Real battery-fire worker replay: one automatic item, manual review, two explicitly **synthetic** mapped boundaries, comparison, isolated publication and withdrawal passed. [Replay evidence](camera_replay.json); the geometry is unrelated to the video location and is not a measured fire footprint.
- The actual worker also processes the 113.6-second cardboard-box negative without automatic evidence; [negative replay](camera_negative_replay.json).
- The first unverified flame setting produced a cardboard false alert. Its incomplete results are retained in [candidate A](camera_refinement_candidate_a.json) with its [protocol](camera_refinement_protocol_candidate_a.json); source snapshot a8bdb98. It was rejected, not silently omitted.
- A cutoff-only trial was replaced by ROI confirmation. Newer smoke checkpoints, finer image tiles and a temporal-model diagnostic did not establish a better supported detector. A later posthoc attempt to apply ROI verification to smoke removed three real smoke detections and was rejected; [diagnostic](rejected_smoke_screening.json). No final thresholds were retuned using the reserved outcomes.

## Acceptance

**Operational camera acceptance remains FAILED.** Fifteen positive clips still have no alert, faint-smoke sensitivity remains poor, and the larger negative test exposes false warnings. No physical RTSP, drone, German seasonal/night/fog/industrial-camera field campaign, sustained long-duration false-alert rate or agency acceptance was verified. Human review, manual evidence capture and existing emergency observation procedures remain necessary. This report supports supervised pilot evaluation only.
