# Barrier-Free Campus Road Risk Design

## Purpose

This project builds a practical MVP for a campus road manager map that highlights road segments likely to be difficult for small wheels, such as wheelchair front casters. The first version does not claim to prove wheelchair danger directly. It produces a "small-wheel mobility risk candidate map" that helps managers inspect, repair, and compare road conditions before and after maintenance.

The embedded practice goal is to use Raspberry Pi 3B, IMU, GPS, and a webcam in a simple but realistic pipeline:

1. Collect bicycle-mounted IMU/GPS data on old campus roads.
2. Detect high-impact candidate points.
3. Label candidates using field measurements, not image classification.
4. Train a lightweight feature-based classifier.
5. Run inference on the Raspberry Pi during survey rides.
6. Show risk candidates and maintenance improvement on a web map.

## Key Decisions

- The main ML input is IMU-derived features. Webcam images are for visual confirmation only.
- Image classification is out of scope for the MVP.
- A test cart is not required. Because there is not enough time to use one, the MVP uses bicycle rides plus manual field measurements.
- Labels are based on measured road defects such as step height, crack width, and pothole depth.
- The product wording is "risk candidate" rather than "confirmed wheelchair danger" until expert or wheelchair-user validation is available.
- Data transfer is manual. After a ride, session files are copied from the Pi to a laptop and uploaded into the web map.
- Maintenance comparison is done by 10 m road segment, not exact point matching, to reduce GPS error sensitivity.
- Physical data is not available during development, so mock sessions drive tests and early UI work.
- Implementation should use TDD and active sub-agent review once the implementation plan is approved.

## Existing Context

There is a related unfinished project at `/Users/song/Projects/pi`.

Useful parts to carry forward:

- Leaflet static map prototype.
- CSV session loading.
- Danger-only and confidence filters.
- GPS-valid filtering.
- Sample CSV generator.
- Campus-centered map coordinates near Chungbuk National University.

Parts that need expansion:

- The old CSV schema stores only final prediction and confidence.
- The new MVP needs raw IMU sessions, GPS sessions, event sessions, photo references, label policy metadata, and before/after comparison metadata.
- The manager map needs segment aggregation and maintenance comparison, not only point markers.

## System Architecture

The system has four bounded areas.

### 1. Raspberry Pi Collector

The collector runs on Raspberry Pi 3B during bicycle rides.

Responsibilities:

- Read IMU data at a target rate of 100 Hz.
- Read GPS position, GPS validity, and speed at the module's available rate.
- Keep a short rolling webcam buffer.
- Write raw IMU and GPS data continuously.
- During early data collection, use a loose impact threshold to identify candidate locations.
- During survey rides after model training, calculate IMU features and run the classifier in near real time.
- Save event records when the classifier emits `caution` or `danger`.
- Save confirmation photos around each event.

The collector is not responsible for training the model or doing maintenance comparison.

### 2. Labeling And Training Tools

These tools run on a laptop.

Responsibilities:

- Load raw session data and mock session data.
- Convert IMU streams into fixed windows, initially 1 second.
- Extract features from each window.
- Attach labels from field measurements.
- Train and evaluate a lightweight classifier, preferably Random Forest first.
- Export a model artifact that can run on the Raspberry Pi.

The first training goal is not perfect accuracy. It should prioritize recall for `caution` and `danger`, because missing a risk candidate is worse than asking a manager to inspect an extra candidate.

### 3. Session Upload And Manager Map

The manager map runs locally in a browser for the MVP.

Responsibilities:

- Accept manually copied session folders or uploaded CSV/JSON files.
- Render ride paths and risk candidates on a Leaflet map.
- Group events into 10 m road segments.
- Show event photos and measurement metadata in popups or a side panel.
- Compare before and after sessions by segment.
- Display improvement metrics for each segment.

No real-time server upload is required in the first version.

### 4. Mock Data And Tests

Because real sensor data requires physical riding, development starts with mock data.

Responsibilities:

- Generate plausible raw IMU, GPS, and event sessions.
- Include normal riding, rough-road vibration, isolated non-road shocks, GPS invalid periods, and repeated risk candidates.
- Generate paired before/after sessions with known improvement values.
- Provide deterministic test fixtures with fixed seeds.

Mock data must be structured like real session data so implementation can switch to physical data without rewriting the map or training pipeline.

## Data Flow

### Calibration And Labeling Flow

1. Bicycle ride collects raw IMU, GPS, and candidate photos.
2. Candidate points are inspected in the field.
3. The team measures step height, crack width, and pothole depth.
4. Each candidate receives one label: `normal`, `caution`, `danger`, or `exclude`.
5. Label rules are written as `label_policy_v1`.
6. Laptop tools match field labels to nearby IMU windows.
7. Feature extraction creates model training rows.
8. A Random Forest model is trained and evaluated.
9. The chosen model is exported with a model version.

### Survey Flow

1. Raspberry Pi collects IMU and GPS while the bicycle follows a planned campus route.
2. Each 1 second IMU window is converted into features.
3. The model predicts `normal`, `caution`, or `danger`.
4. For `caution` and `danger`, the Pi writes an event record and saves confirmation photos.
5. After the ride, files are copied to the laptop.
6. The manager map loads the session and renders events by segment.

### Maintenance Comparison Flow

1. A road segment is surveyed before maintenance.
2. The same route is surveyed after maintenance.
3. Events are grouped into 10 m segments.
4. Each segment receives summary metrics:
   - event count
   - maximum risk score
   - average risk score
   - repeated-detection ratio
   - before/after improvement rate
5. The map colors segments by current risk and improvement.

## Session Data Contract

Each ride session should be stored as one folder:

```text
sessions/2026-06-12_before_run01/
  raw_imu.csv
  gps.csv
  events.csv
  photos/
  session.json
```

### `session.json`

Required fields:

- `session_id`: stable session identifier.
- `phase`: `calibration`, `before`, `after`, or `demo`.
- `run_index`: integer run number for repeated rides.
- `started_at`: ISO 8601 timestamp.
- `route_name`: human-readable route name.
- `device`: Raspberry Pi and sensor notes.
- `model_version`: model artifact version, or `none` for raw collection.
- `label_policy_version`: label policy version, or `none` for unlabeled collection.
- `notes`: short free-text notes.

### `raw_imu.csv`

Columns:

- `timestamp`
- `ax`
- `ay`
- `az`
- `gx`
- `gy`
- `gz`

Acceleration and gyroscope units must be documented in `session.json` once the actual IMU module is chosen.

### `gps.csv`

Columns:

- `timestamp`
- `lat`
- `lon`
- `gps_valid`
- `speed_mps`

When GPS is invalid, rows should still be written. The last known coordinate may be retained, but `gps_valid=0` must allow the map and training tools to filter or down-rank those records.

### `events.csv`

Columns:

- `event_id`
- `timestamp_start`
- `timestamp_end`
- `lat`
- `lon`
- `gps_valid`
- `speed_mps`
- `prediction`
- `confidence`
- `risk_score`
- `segment_id`
- `photo_before`
- `photo_after`
- `model_version`

`prediction` uses `normal`, `caution`, or `danger`. Event files normally include only `caution` and `danger`, but the schema allows `normal` for tests and debugging.

## Label Policy

The exact threshold values are decided after a short field trial. The first policy file is `label_policy_v1`.

Labels:

- `normal`: no meaningful small-wheel mobility concern based on measurement and visual inspection.
- `caution`: a road defect that may inconvenience small wheels and should be reviewed.
- `danger`: a road defect likely to block, destabilize, or strongly shock small wheels.
- `exclude`: a shock source unrelated to road defects, such as braking, sharp turning, curb impact outside the target route, speed bump, sensor mount failure, or obvious GPS mismatch.

The label file must store the measured values used to justify the label. Photos support review but do not define the label by themselves.

For mock data and tests before field measurements exist, use a deterministic mock policy:

- `normal`: generated risk score below `0.35`.
- `caution`: generated risk score from `0.35` up to but not including `0.70`.
- `danger`: generated risk score equal to or above `0.70`.
- `exclude`: generated non-road shock flag is true.

The mock policy is only a development fixture. Physical field labels replace it when real measurements exist.

## Feature-Based ML Design

The first model uses engineered features rather than raw time-series deep learning.

Windowing:

- Use 1 second windows for the first MVP.
- Use non-overlapping windows for the first MVP to keep Pi runtime and event deduplication simple.
- Attach GPS speed by nearest timestamp or average speed during the window.

Candidate features:

- maximum absolute acceleration per axis
- acceleration magnitude maximum
- acceleration magnitude mean
- acceleration magnitude standard deviation
- jerk maximum
- jerk mean
- z-axis peak count
- gyroscope magnitude maximum
- gyroscope magnitude standard deviation
- GPS speed

Model:

- Start with Random Forest.
- Use Decision Tree only if Pi runtime or explainability becomes more important than accuracy.
- Prefer recall for `caution` and `danger`.
- Store confusion matrix and per-class precision/recall after training.

## Manager Map Design

The first map can extend the old Leaflet prototype.

Core views:

- Session selector or upload control.
- Before/after selector.
- Risk-only filter.
- Minimum confidence filter.
- GPS-valid filter.
- 10 m segment layer.
- Event marker layer.
- Segment details panel.

Segment details:

- current risk level
- event count
- average and maximum risk score
- repeated-detection ratio
- before/after improvement rate
- linked event photos
- field measurement label, when available

Improvement formula:

```text
improvement_rate = (before_score - after_score) / before_score
```

If `before_score` is zero, the UI should not report a percentage. It should display `new risk`, `unchanged clean`, or `not comparable` depending on the after score and available sessions.

## Error Handling

Raspberry Pi collector:

- Continue writing IMU data if GPS is invalid.
- Mark `gps_valid=0` instead of dropping records.
- If the webcam frame is unavailable during an event, write the event with empty photo fields and an error note.
- If the model artifact is missing, run in raw collection mode and do not emit model predictions.
- If sensor reads fail repeatedly, write a clear error record and keep the process alive when possible.

Training tools:

- Reject sessions missing required columns.
- Reject labels that do not match the label policy vocabulary.
- Warn when labeled candidates cannot be matched to IMU windows.
- Keep excluded events out of model training.

Manager map:

- Validate uploaded session files before rendering.
- Show a human-readable error when a file is missing or malformed.
- Allow GPS-invalid events to be hidden by default.
- Avoid exact point matching for before/after comparison; use segment IDs.

## Testing Strategy

Development must use TDD once implementation begins.

Required TDD behavior:

- Write a failing test before production code.
- Run the targeted test and confirm the expected failure.
- Implement the smallest change to pass.
- Re-run the targeted test and then the relevant broader suite.
- Refactor only after tests pass.

Mock data is the primary development fixture until physical data exists.

Important tests:

- Mock session generator creates deterministic sessions from a seed.
- Feature extraction returns expected values for small synthetic IMU windows.
- Label matching connects field labels to the correct GPS/IMU windows.
- Excluded labels do not enter the training dataset.
- Model training produces predictions with the expected class vocabulary.
- Segment aggregation groups events into stable 10 m buckets.
- Before/after comparison handles improvement, worsening, new risk, clean segments, and missing before scores.
- Map CSV/JSON parsing rejects malformed data and accepts valid mock sessions.

## Sub-Agent Implementation Strategy

After the implementation plan is approved, work should be split into independent tasks and executed with sub-agents when practical.

Recommended task boundaries:

- Mock data generator and fixtures.
- Session schema validation.
- Feature extraction and label matching.
- ML training and model export.
- Pi collector skeleton and event writing.
- Manager map upload and parsing.
- 10 m segment aggregation and before/after metrics.
- UI rendering and filter behavior.

Each implementation task should have:

- an implementer sub-agent,
- a spec-compliance review,
- a code-quality review,
- tests written before production code,
- a small commit after the task passes.

Parallel sub-agent work is appropriate only for independent research or review. Implementation tasks that touch the same files should be sequenced to avoid conflicts.

## MVP Acceptance Criteria

The MVP is successful when:

- A deterministic mock dataset can simulate before and after road sessions.
- The training pipeline can run on mock or labeled session data.
- The Pi-side code can run in raw collection mode and model inference mode, even if the first verification uses mock sensor streams.
- The manager map can load at least two sessions and display caution/danger candidates.
- The manager map groups events into 10 m segments.
- The manager map reports before/after improvement for comparable segments.
- Event details include confirmation photo paths when available.
- The project documentation clearly states that this is a risk candidate map, not a confirmed clinical accessibility assessment.

## Out Of Scope For MVP

- Image classification.
- Automatic Pi-to-server upload.
- Real-time web dashboard.
- Deep learning time-series classifier.
- Direct safety claims for wheelchair users without external validation.
- Full production deployment.

## Hardware And Field Constraints

- The collector must isolate IMU sensor access behind a small interface with mock and hardware implementations, so the concrete IMU module can be selected without changing downstream code.
- The exact physical label thresholds are finalized after a short field trial, then recorded in `label_policy_v1`.
- The old `/Users/song/Projects/pi` web prototype can be copied or re-created in this workspace during implementation, but its CSV contract should not be treated as sufficient for the new MVP.
