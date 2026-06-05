# Final Demo Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pi에 누적된 모든 실측 세션을 수치 기반 임계값으로 분석하고, 장애물 설치 전/후 반복 주행 비교 지도와 최종 발표용 리포트를 한 번에 생성한다.

**Architecture:** 새 `risk_scoring` 모듈은 IMU window를 `normal/caution/danger`로 분류하고, 새 `final_demo` 모듈은 세션 탐색, before/after 그룹 집계, 지도 payload, Markdown 리포트 생성을 담당한다. 기존 `field_export`, `segments`, `web` 구조는 유지하되 final-demo payload 필드를 추가해 하위 호환을 보장한다.

**Tech Stack:** Python stdlib, 기존 CSV/JSON schema, Leaflet web UI, `unittest`, Node `--check`.

---

## File Structure

- Create `barrier_free/risk_scoring.py`: threshold 설정, IMU window 위험도 계산, window event 변환.
- Create `barrier_free/final_demo.py`: 모든 세션을 읽어 route/phase별 그룹 비교 payload와 Markdown 리포트 생성.
- Modify `barrier_free/cli.py`: `final-demo` CLI 추가.
- Modify `web/index.html`, `web/app.js`, `web/style.css`: final summary, threshold, group comparison 표시.
- Modify `README.md`: Pi 실험 및 최종 데모 명령 추가.
- Add tests:
  - `tests/test_risk_scoring.py`
  - `tests/test_final_demo.py`
  - update `tests/test_pi_cli.py`
  - update `tests/test_web_export.py`

---

### Task 1: 수치 기반 Risk Scoring 모듈

**Files:**
- Create: `barrier_free/risk_scoring.py`
- Test: `tests/test_risk_scoring.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_risk_scoring.py`:

```python
import unittest

from barrier_free import risk_scoring


class RiskScoringTest(unittest.TestCase):
    def test_classifies_window_by_tunable_thresholds(self):
        thresholds = risk_scoring.RiskThresholds(caution_delta=0.35, danger_delta=0.75, danger_jerk=12.0)

        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.2, "jerk_max": 2.0}, thresholds)["prediction"],
            "normal",
        )
        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.5, "jerk_max": 3.0}, thresholds)["prediction"],
            "caution",
        )
        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.8, "jerk_max": 3.0}, thresholds)["prediction"],
            "danger",
        )
        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.2, "jerk_max": 15.0}, thresholds)["prediction"],
            "danger",
        )

    def test_scores_session_windows_from_raw_imu_and_gps(self):
        bundle = {
            "raw_imu": [
                {"timestamp": 1.0, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
                {"timestamp": 1.5, "ax": 0.0, "ay": 0.0, "az": 1.2, "gx": 0.0, "gy": 0.0, "gz": 0.0},
                {"timestamp": 2.0, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
                {"timestamp": 2.5, "ax": 0.0, "ay": 0.0, "az": 2.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
            ],
            "gps": [
                {"timestamp": 1.0, "lat": 36.0, "lon": 127.0, "gps_valid": 1, "speed_mps": 2.0},
                {"timestamp": 2.0, "lat": 36.0001, "lon": 127.0, "gps_valid": 1, "speed_mps": 2.0},
            ],
        }
        thresholds = risk_scoring.RiskThresholds(caution_delta=0.3, danger_delta=0.7, danger_jerk=99.0)

        windows = risk_scoring.score_session_windows(bundle, thresholds)

        self.assertEqual([row["prediction"] for row in windows], ["normal", "danger"])
        self.assertIn("risk_score", windows[1])
        self.assertEqual(windows[1]["gps_valid"], 1)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_risk_scoring -v
```

Expected: import or attribute failure because `risk_scoring` does not exist.

- [ ] **Step 3: Implement minimal module**

Implement:

```python
from dataclasses import asdict, dataclass
from . import features

@dataclass(frozen=True)
class RiskThresholds:
    caution_delta: float = 0.35
    danger_delta: float = 0.75
    danger_jerk: float = 12.0

    def to_dict(self) -> dict:
        return asdict(self)
```

Add `classify_window(feature_row, thresholds)` and `score_session_windows(bundle, thresholds)`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
python3 -m unittest tests.test_risk_scoring -v
```

Expected: OK.

---

### Task 2: Final Demo 분석/리포트 모듈

**Files:**
- Create: `barrier_free/final_demo.py`
- Test: `tests/test_final_demo.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_final_demo.py` with mock before/after sessions. The test must assert:

- `export_final_demo(...)` creates `web/demo_data.json`
- payload source type is `final-demo`
- payload includes all sessions
- payload includes `final_summary`
- payload includes `thresholds`
- payload includes `group_comparison`
- `report/final_summary.md` exists and contains Korean presentation text

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 -m unittest tests.test_final_demo -v
```

Expected: import or attribute failure because `final_demo` does not exist.

- [ ] **Step 3: Implement module**

Implement functions:

```python
def export_final_demo(
    *,
    sessions_root: Path,
    output_dir: Path,
    report_dir: Path,
    route_name: str | None,
    thresholds: risk_scoring.RiskThresholds,
    segment_meters: int = 10,
) -> Path:
    ...
```

Behavior:

- discover all session folders using `field_export.discover_session_paths`
- filter by `route_name` when provided
- read bundles with `field_export.read_session_folder`
- generate scored windows for each session using `risk_scoring.score_session_windows`
- aggregate windows into synthetic event-like rows for segment comparison
- group sessions by `phase == before` and `phase == after`
- produce `final_summary`, `group_comparison`, `sessions`, `comparison`
- write `output_dir/demo_data.json`
- write `report_dir/final_summary.md`

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
python3 -m unittest tests.test_final_demo -v
```

Expected: OK.

---

### Task 3: CLI 연결

**Files:**
- Modify: `barrier_free/cli.py`
- Test: `tests/test_pi_cli.py`

- [ ] **Step 1: Write failing tests**

Add test:

```python
def test_cli_help_lists_final_demo_command(self):
    output = io.StringIO()
    with self.assertRaises(SystemExit):
        with redirect_stdout(output):
            cli.main(["--help"])
    self.assertIn("final-demo", output.getvalue())
```

Add test for command invocation using temp sessions:

```python
def test_final_demo_cli_writes_web_payload_and_report(self):
    ...
    exit_code = cli.main(["final-demo", str(sessions_root), "--out", str(web), "--report-out", str(report)])
    self.assertEqual(exit_code, 0)
    self.assertTrue((web / "demo_data.json").exists())
    self.assertTrue((report / "final_summary.md").exists())
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest tests.test_pi_cli -v
```

Expected: FAIL because `final-demo` command is missing.

- [ ] **Step 3: Implement CLI**

Add parser:

```python
final_demo_cmd = sub.add_parser("final-demo", help="누적 세션으로 최종 before/after 데모 payload와 리포트를 생성한다")
final_demo_cmd.add_argument("path", type=Path)
final_demo_cmd.add_argument("--out", type=Path, default=Path("web"))
final_demo_cmd.add_argument("--report-out", type=Path, default=Path("report"))
final_demo_cmd.add_argument("--route-name", default=None)
final_demo_cmd.add_argument("--segment-meters", type=int, default=10)
final_demo_cmd.add_argument("--caution-threshold", type=float, default=0.35)
final_demo_cmd.add_argument("--danger-threshold", type=float, default=0.75)
final_demo_cmd.add_argument("--danger-jerk", type=float, default=12.0)
```

Call `final_demo.export_final_demo(...)`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
python3 -m unittest tests.test_pi_cli -v
```

Expected: OK.

---

### Task 4: Web final-demo presentation UI

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`
- Test: `tests/test_web_export.py`

- [ ] **Step 1: Write failing static tests**

Update `tests/test_web_export.py` to assert:

```python
self.assertIn('id="final-summary"', index)
self.assertIn('id="threshold-summary"', index)
self.assertIn("renderFinalSummary", app)
self.assertIn("renderThresholdSummary", app)
self.assertIn("group_comparison", app)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest tests.test_web_export -v
```

Expected: FAIL because DOM ids/functions are missing.

- [ ] **Step 3: Implement UI**

Add panels:

```html
<h2>최종 요약</h2>
<div id="final-summary"></div>
<h2>임계값</h2>
<div id="threshold-summary"></div>
```

Add JS functions:

```javascript
function renderFinalSummary(data) { ... }
function renderThresholdSummary(data) { ... }
```

Call them from `render()`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
python3 -m unittest tests.test_web_export -v
node --check web/app.js
```

Expected: OK.

---

### Task 5: README와 최종 시연 Runbook

**Files:**
- Modify: `README.md`
- Create: `docs/final_demo_runbook.md`

- [ ] **Step 1: Add concise Korean runbook**

Create a runbook containing:

- obstacle before collection commands
- obstacle after collection commands
- `final-demo` command
- web serving command
- demo video storyboard
- threshold adjustment guide

- [ ] **Step 2: Verify docs contain executable commands**

Run:

```bash
rg "final-demo|--caution-threshold|장애물|시연 영상" README.md docs/final_demo_runbook.md
```

Expected: matching lines exist.

---

### Task 6: Full verification and integration

**Files:**
- All touched files.

- [ ] **Step 1: Run full test suite**

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests OK.

- [ ] **Step 2: Run web syntax check**

```bash
node --check web/app.js
```

Expected: exit 0.

- [ ] **Step 3: Run final-demo smoke**

```bash
python3 -m barrier_free.cli final-demo demo_sessions --out /tmp/barrier-free-final-web --report-out /tmp/barrier-free-final-report
```

Expected:

- `/tmp/barrier-free-final-web/demo_data.json` exists
- `/tmp/barrier-free-final-report/final_summary.md` exists

- [ ] **Step 4: Review diff**

```bash
git diff --stat
git diff --check
```

Expected: no whitespace errors; diff is limited to planned files.

