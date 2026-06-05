# 실제 주행 전/후 비교 MVP 완료 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**목표:** Pi에서 수집한 실제 before/after 세션 폴더를 입력으로 받아, 관리자 Leaflet 지도에서 전/후 위험 후보 구간 비교까지 보여주는 텀프로젝트 MVP를 완성한다.

**Architecture:** 기존 세션 계약(`session.json`, `raw_imu.csv`, `gps.csv`, `events.csv`, `labels.csv`)은 유지한다. 새 기능은 실제 세션 폴더를 읽어 10 m 구간 집계와 before/after 비교 JSON을 만들고, 웹에서는 현재 세션 이벤트와 별도로 비교 오버레이를 표시한다.

**Tech Stack:** Python 3 표준 라이브러리, `unittest`, Vanilla JS, Leaflet, 정적 HTTP 서버.

---

## 현재 확인된 상태

- GitHub `origin/main` 최신 커밋 `a05e929` 반영 완료.
- Pi에서 발견한 GPS 병목 수정 반영 완료:
  - `collector.py`: GPS 1 Hz polling, IMU 20 Hz 유지, 직전 fix 재사용.
  - `gps_neo_m8n.py`: serial timeout 0.2 s, `timeout_lines=25`, `reset_input_buffer()` 적용.
- 전체 테스트 통과: `python3 -m unittest discover -s tests -v` → 25개 OK.
- 이미 가능한 것:
  - mock E2E 학습/추론/전후비교/지도 export.
  - 실제 Pi 센서 health check.
  - 실제 센서 수집 세션 생성.
- 아직 부족한 것:
  - 실제 수집 세션 2개를 `before/after`로 묶어 `web/demo_data.json`으로 내보내는 명령.
  - 웹 지도에서 전/후 비교 상태(`improved`, `worsened`, `new_risk`)를 명확히 표시하는 오버레이.
  - 실외 주행 직후 데이터 품질을 빠르게 판단하는 audit 명령.

## 파일 구조

- `barrier_free/field_export.py`: 실제 세션 폴더를 읽어 web payload를 생성한다.
- `barrier_free/session_audit.py`: 수집 세션의 GPS valid 비율, IMU 행 수, 이벤트 수, 사진 수를 요약한다.
- `barrier_free/segments.py`: before/after 주행 coverage를 반영해 미주행 구간을 개선으로 오판하지 않게 한다.
- `barrier_free/cli.py`: `compare-sessions`, `audit-session` 명령을 추가한다.
- `web/index.html`: 비교 오버레이 토글과 안내 문구를 추가한다.
- `web/app.js`: 비교 오버레이 렌더링, 상태별 색상, 비교 popup을 추가한다.
- `web/style.css`: 비교 범례와 상태 배지를 정리한다.
- `tests/test_field_export.py`: 실제 세션 폴더 기반 before/after export 테스트.
- `tests/test_session_audit.py`: 수집 세션 품질 점검 테스트.
- `tests/test_web_export.py`: 웹 정적 파일에 비교 오버레이 기능이 포함되는지 확인한다.
- `README.md`: Pi 수집 후 실제 세션 비교 실행법을 추가한다.

## Task 1: Coverage-aware before/after 비교

**담당:** Worker A 또는 메인 에이전트

**중요 판단:** 단기 MVP에서도 `after` 주행이 해당 before 위험 구간을 지나가지 않았으면 `improved`라고 표시하지 않는다. 이 경우는 `not_comparable`로 둔다. 그래야 발표에서 “안 지나간 곳을 개선으로 착각했다”는 약점이 생기지 않는다.

**Files:**

- Modify: `barrier_free/segments.py`
- Modify: `tests/test_segments.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_segments.py`에 추가한다.

```python
def test_compare_before_after_uses_route_coverage_to_avoid_false_improvement(self):
    covered = "covered"
    not_covered = "not_covered"
    before = {
        covered: _summary(covered, 0.80),
        not_covered: _summary(not_covered, 0.70),
    }
    after = {}

    comparison = {
        row["segment_id"]: row
        for row in segments.compare_segments(
            before,
            after,
            before_coverage={covered, not_covered},
            after_coverage={covered},
        )
    }

    self.assertEqual(comparison[covered]["status"], "improved")
    self.assertAlmostEqual(comparison[covered]["improvement_rate"], 1.0)
    self.assertEqual(comparison[not_covered]["status"], "not_comparable")
    self.assertIsNone(comparison[not_covered]["improvement_rate"])
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
python3 -m unittest tests.test_segments -v
```

Expected:

```text
TypeError: compare_segments() got an unexpected keyword argument 'before_coverage'
```

- [ ] **Step 3: 최소 구현**

`compare_segments()` 시그니처를 확장한다. 기존 테스트가 깨지지 않도록 coverage 인자는 선택값으로 둔다.

```python
def compare_segments(before, after, before_coverage=None, after_coverage=None) -> list[dict]:
    """Compare before and after segment summaries."""

    before_by_segment = _summary_by_segment(before)
    after_by_segment = _summary_by_segment(after)
    before_coverage = set(before_coverage or before_by_segment)
    after_coverage = set(after_coverage or after_by_segment)
    comparison = []

    for segment_id in sorted(set(before_by_segment) | set(after_by_segment)):
        before_row = before_by_segment.get(segment_id)
        after_row = after_by_segment.get(segment_id)
        before_score = _summary_score(before_row)
        after_score = _summary_score(after_row)
        comparable = segment_id in before_coverage and segment_id in after_coverage
        if before_row is not None and after_row is None and comparable:
            after_score = 0.0

        comparison.append(
            {
                "segment_id": segment_id,
                "status": _comparison_status(before_score, after_score, comparable=comparable),
                "before_score": before_score,
                "after_score": after_score,
                "improvement_rate": _improvement_rate(before_score, after_score, comparable=comparable),
                "before_event_count": _event_count(before_row),
                "after_event_count": _event_count(after_row),
                "before_risk_level": _risk_level_for_summary(before_row),
                "after_risk_level": _risk_level_for_summary(after_row),
            }
        )

    return comparison
```

`_comparison_status()`와 `_improvement_rate()`를 확장한다.

```python
def _comparison_status(before_score: float | None, after_score: float | None, comparable: bool = True) -> str:
    if not comparable:
        return "not_comparable"
    if before_score is None:
        if after_score is not None and after_score > 0:
            return "new_risk"
        return "not_comparable"
    if after_score is None:
        return "not_comparable"
    if before_score == 0 and after_score == 0:
        return "unchanged_clean"
    if before_score == 0 and after_score > 0:
        return "new_risk"
    if after_score < before_score:
        return "improved"
    if after_score > before_score:
        return "worsened"
    return "not_comparable"


def _improvement_rate(before_score: float | None, after_score: float | None, comparable: bool = True) -> float | None:
    if not comparable or before_score is None or after_score is None or before_score == 0:
        return None
    return (before_score - after_score) / before_score
```

- [ ] **Step 4: GPS route coverage helper 추가**

`segments.py`에 추가한다.

```python
def route_coverage_segments(gps_rows: Iterable[Mapping], segment_meters: int = 10) -> set[str]:
    """GPS valid 주행 경로가 지나간 segment id 집합을 반환한다."""

    coverage = set()
    for row in gps_rows:
        if not _gps_valid(row):
            continue
        try:
            coverage.add(segment_id_for(row["lat"], row["lon"], segment_meters=segment_meters))
        except (KeyError, TypeError, ValueError):
            continue
    return coverage
```

- [ ] **Step 5: 통과 확인**

Run:

```bash
python3 -m unittest tests.test_segments -v
```

Expected:

```text
OK
```

- [ ] **Step 6: 커밋**

```bash
git add barrier_free/segments.py tests/test_segments.py
git commit -m "fix: avoid false improvement for uncovered after segments"
```

## Task 2: 실제 세션 before/after export

**담당:** Worker A 또는 메인 에이전트

**Files:**

- Create: `barrier_free/field_export.py`
- Create: `tests/test_field_export.py`
- Modify: `barrier_free/cli.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_field_export.py`를 만든다.

```python
import json
import tempfile
import unittest
from pathlib import Path

from barrier_free import field_export, mock_data, schema


class FieldExportTest(unittest.TestCase):
    def test_export_session_comparison_reads_before_after_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = mock_data.build_demo_dataset(seed=42)
            before_path = schema.write_session_bundle(dataset["before"], root / "before")
            after_path = schema.write_session_bundle(dataset["after"], root / "after")

            payload_path = field_export.export_session_comparison(
                before_path=before_path,
                after_path=after_path,
                output_dir=root / "web",
                segment_meters=10,
            )

            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            self.assertEqual(payload_path.name, "demo_data.json")
            self.assertEqual([session["name"] for session in payload["sessions"]], ["before", "after"])
            self.assertIn("comparison", payload)
            self.assertTrue(any(row["status"] == "improved" for row in payload["comparison"]))
            self.assertEqual(payload["source"]["type"], "field-session-comparison")
            self.assertEqual(payload["source"]["segment_meters"], 10)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
python3 -m unittest tests.test_field_export -v
```

Expected:

```text
ImportError: cannot import name 'field_export'
```

- [ ] **Step 3: 최소 구현**

`barrier_free/field_export.py`를 만든다. 기존 `cli._read_session_folder`, `cli._session_payload`와 동일한 구조를 재사용하되, 새 파일 안에 독립 함수로 둔다.

```python
"""실제 수집 세션 before/after를 관리자 지도 payload로 변환한다."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from . import schema, segments


def export_session_comparison(
    *,
    before_path: Path,
    after_path: Path,
    output_dir: Path,
    segment_meters: int = 10,
) -> Path:
    before_bundle = read_session_folder(before_path)
    after_bundle = read_session_folder(after_path)
    before_summary = segments.aggregate_events(before_bundle["events"], segment_meters=segment_meters)
    after_summary = segments.aggregate_events(after_bundle["events"], segment_meters=segment_meters)
    before_coverage = segments.route_coverage_segments(before_bundle["gps"], segment_meters=segment_meters)
    after_coverage = segments.route_coverage_segments(after_bundle["gps"], segment_meters=segment_meters)
    comparison = segments.compare_segments(
        before_summary,
        after_summary,
        before_coverage=before_coverage,
        after_coverage=after_coverage,
    )

    payload = {
        "source": {
            "type": "field-session-comparison",
            "before_path": str(before_path),
            "after_path": str(after_path),
            "segment_meters": segment_meters,
            "before_coverage_count": len(before_coverage),
            "after_coverage_count": len(after_coverage),
        },
        "model": {
            "type": "field-or-threshold",
            "version": before_bundle["session"].get("model_version", "none"),
            "training_rows": 0,
            "recall": None,
            "confusion_matrix": {},
        },
        "sessions": [
            session_payload("before", before_bundle, before_summary),
            session_payload("after", after_bundle, after_summary),
        ],
        "comparison": comparison,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "demo_data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def session_payload(name: str, bundle: dict, summary: dict) -> dict:
    return {
        "name": name,
        "session": bundle["session"],
        "gps": bundle["gps"],
        "events": bundle["events"],
        "segments": list(summary.values()),
    }


def read_session_folder(path: Path) -> dict:
    bundle = {
        "session": json.loads((path / "session.json").read_text(encoding="utf-8")),
        "raw_imu": read_csv(path / "raw_imu.csv"),
        "gps": read_csv(path / "gps.csv"),
        "events": read_csv(path / "events.csv"),
        "labels": read_csv(path / "labels.csv"),
    }
    schema.validate_session_bundle(bundle)
    return bundle


def read_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return [coerce_row(row) for row in csv.DictReader(f)]


def coerce_row(row: dict) -> dict:
    result = {}
    float_fields = {
        "timestamp",
        "timestamp_start",
        "timestamp_end",
        "lat",
        "lon",
        "speed_mps",
        "confidence",
        "risk_score",
        "ax",
        "ay",
        "az",
        "gx",
        "gy",
        "gz",
        "step_height_mm",
        "crack_width_mm",
        "pothole_depth_mm",
    }
    int_fields = {"gps_valid", "non_road_shock", "run_index"}
    for key, value in row.items():
        if value == "":
            result[key] = value
        elif key in float_fields:
            result[key] = float(value)
        elif key in int_fields:
            result[key] = int(float(value))
        else:
            result[key] = value
    return result
```

- [ ] **Step 4: CLI 추가**

`barrier_free/cli.py` 상단 import에 `field_export`를 추가한다.

```python
from . import collector, field_export, mock_data, model, schema, segments
```

`main()`의 parser 설정에 추가한다.

```python
compare = sub.add_parser("compare-sessions", help="실제 before/after 세션을 web demo_data.json으로 변환한다")
compare.add_argument("--before", type=Path, required=True)
compare.add_argument("--after", type=Path, required=True)
compare.add_argument("--out", type=Path, default=Path("web"))
compare.add_argument("--segment-meters", type=int, default=10)
```

명령 분기에 추가한다.

```python
if args.command == "compare-sessions":
    path = field_export.export_session_comparison(
        before_path=args.before,
        after_path=args.after,
        output_dir=args.out,
        segment_meters=args.segment_meters,
    )
    print(path)
    return 0
```

- [ ] **Step 5: 통과 확인**

Run:

```bash
python3 -m unittest tests.test_field_export -v
python3 -m barrier_free.cli compare-sessions --help
```

Expected:

```text
OK
```

- [ ] **Step 6: 커밋**

```bash
git add barrier_free/field_export.py barrier_free/cli.py tests/test_field_export.py
git commit -m "feat: export field before-after session comparison"
```

## Task 3: 수집 세션 phase와 이름 지정

**담당:** Worker C 또는 메인 에이전트

**Files:**

- Modify: `barrier_free/collector.py`
- Modify: `barrier_free/cli.py`
- Modify: `tests/test_collector_cli.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_collector_cli.py`의 실제 센서 수집 테스트에 phase/session_id/route_name 검증을 추가하거나 새 테스트를 만든다.

```python
def test_sensor_collection_accepts_field_metadata(self):
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp)

        path = collector.run_sensor_collection(
            output,
            imu_reader=FakeIMU(),
            gps_reader=FakeGPS(),
            duration_seconds=1.0,
            sample_rate_hz=2.0,
            session_id="before_short_test",
            phase="before",
            route_name="campus_test_route",
            sleeper=None,
            clock=FakeClock(),
        )

        session = json.loads((path / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(session["session_id"], "before_short_test")
        self.assertEqual(session["phase"], "before")
        self.assertEqual(session["route_name"], "campus_test_route")
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
python3 -m unittest tests.test_collector_cli -v
```

Expected:

```text
TypeError: run_sensor_collection() got an unexpected keyword argument 'phase'
```

- [ ] **Step 3: collector 인자 추가**

`run_sensor_collection()`에 추가한다.

```python
phase: str = "demo",
route_name: str = "pi_field_collection",
run_index: int = 1,
```

session 생성부를 바꾼다.

```python
"phase": phase,
"run_index": run_index,
"route_name": route_name,
```

- [ ] **Step 4: CLI 인자 추가**

`collect` parser에 추가한다.

```python
collect.add_argument("--phase", choices=["calibration", "before", "after", "demo"], default="demo")
collect.add_argument("--session-id", default=None)
collect.add_argument("--route-name", default="pi_field_collection")
collect.add_argument("--run-index", type=int, default=1)
```

`_collect_from_hardware()` 호출에 전달한다.

```python
session_id=args.session_id,
phase=args.phase,
route_name=args.route_name,
run_index=args.run_index,
```

- [ ] **Step 5: 통과 확인**

Run:

```bash
python3 -m unittest tests.test_collector_cli -v
python3 -m barrier_free.cli collect --help
```

Expected:

```text
OK
```

- [ ] **Step 6: 커밋**

```bash
git add barrier_free/collector.py barrier_free/cli.py tests/test_collector_cli.py
git commit -m "feat: allow field collection metadata"
```

## Task 4: 웹 전/후 비교 보기 모드

**담당:** Worker B

**Files:**

- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`
- Modify: `tests/test_web_export.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_web_export.py`의 `test_web_static_files_include_leaflet_map_and_filters`에 아래 assertion을 추가한다.

```python
self.assertIn('id="view-mode"', index)
self.assertIn("renderComparisonMode", app)
self.assertIn("statusColor", app)
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
python3 -m unittest tests.test_web_export -v
```

Expected:

```text
FAIL: 'id="view-mode"' not found
```

- [ ] **Step 3: HTML 보기 모드 추가**

`web/index.html`의 controls 안에 추가한다.

```html
<label>
  보기
  <select id="view-mode">
    <option value="session">선택 세션</option>
    <option value="comparison">전/후 비교</option>
  </select>
</label>
```

aside의 summary 아래에 범례를 추가한다.

```html
<div id="legend">
  <span class="badge improved">개선</span>
  <span class="badge worsened">악화</span>
  <span class="badge new-risk">새 위험</span>
</div>
```

- [ ] **Step 4: JS 비교 모드 추가**

`web/app.js` 상단에 추가한다.

```javascript
const comparisonLayer = L.layerGroup().addTo(map);
```

`render()` 시작부에 보기 모드를 분기한다.

```javascript
const viewMode = document.getElementById("view-mode").value;
if (viewMode === "comparison") {
  renderComparisonMode(payload.comparison, payload.sessions);
  renderSummary(payload.comparison);
  return;
}
```

`clearLayers()`에 추가한다.

```javascript
comparisonLayer.clearLayers();
```

새 함수를 추가한다.

```javascript
function renderComparisonMode(comparison, sessions) {
  const segmentById = new Map();
  for (const session of sessions) {
    for (const segment of session.segments || []) {
      if (!segmentById.has(segment.segment_id)) {
        segmentById.set(segment.segment_id, segment);
      }
    }
  }

  for (const row of comparison) {
    if (!["improved", "worsened", "new_risk"].includes(row.status)) continue;
    const segment = segmentById.get(row.segment_id);
    if (!segment) continue;
    const lat = Number(segment.center_lat);
    const lon = Number(segment.center_lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

    const marker = L.circleMarker([lat, lon], {
      radius: 16,
      color: statusColor(row.status),
      fillColor: statusColor(row.status),
      fillOpacity: 0.14,
      weight: 4,
    });
    marker.bindPopup(comparisonPopup(row));
    marker.on("click", () => showDetails(comparisonPopup(row)));
    marker.addTo(comparisonLayer);
  }
}

function statusColor(status) {
  if (status === "improved") return "#16a34a";
  if (status === "worsened") return "#dc2626";
  if (status === "new_risk") return "#7c3aed";
  return "#64748b";
}

function comparisonPopup(row) {
  return `
    <strong>전/후 비교</strong><br>
    상태: ${comparisonStatusLabel(row.status)}<br>
    before: ${Number(row.before_score || 0).toFixed(2)}<br>
    after: ${Number(row.after_score || 0).toFixed(2)}<br>
    개선율: ${row.improvement_rate === null ? "N/A" : `${(Number(row.improvement_rate) * 100).toFixed(1)}%`}
  `;
}

function comparisonStatusLabel(status) {
  if (status === "improved") return "개선";
  if (status === "worsened") return "악화";
  if (status === "new_risk") return "새 위험";
  if (status === "unchanged_clean") return "양호 유지";
  return "비교 불가";
}
```

이벤트 리스너 목록에 `comparison-overlay`를 추가한다.

```javascript
for (const id of ["danger-only", "gps-valid-only", "confidence-filter", "view-mode"]) {
  document.getElementById(id).addEventListener("input", render);
}
```

- [ ] **Step 5: CSS 범례 추가**

`web/style.css`에 추가한다.

```css
#legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.75rem 0 1rem;
}

.badge {
  border-radius: 999px;
  color: white;
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.25rem 0.55rem;
}

.badge.improved {
  background: #16a34a;
}

.badge.worsened {
  background: #dc2626;
}

.badge.new-risk {
  background: #7c3aed;
}
```

- [ ] **Step 6: 통과 확인**

Run:

```bash
python3 -m unittest tests.test_web_export -v
```

Expected:

```text
OK
```

- [ ] **Step 7: 커밋**

```bash
git add web/index.html web/app.js web/style.css tests/test_web_export.py
git commit -m "feat: show before-after comparison mode on map"
```

## Task 5: 주행 세션 품질 점검 CLI

**담당:** Worker C 또는 메인 에이전트

**Files:**

- Create: `barrier_free/session_audit.py`
- Create: `tests/test_session_audit.py`
- Modify: `barrier_free/cli.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_session_audit.py`를 만든다.

```python
import tempfile
import unittest
from pathlib import Path

from barrier_free import mock_data, schema, session_audit


class SessionAuditTest(unittest.TestCase):
    def test_audit_session_reports_collection_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = mock_data.build_demo_dataset(seed=42)["before"]
            path = schema.write_session_bundle(bundle, Path(tmp) / "session")

            report = session_audit.audit_session(path)

            self.assertEqual(report["session_id"], "demo_before_run01")
            self.assertGreater(report["raw_imu_rows"], 0)
            self.assertGreater(report["gps_rows"], 0)
            self.assertGreaterEqual(report["gps_valid_ratio"], 0.95)
            self.assertGreater(report["event_count"], 0)
            self.assertIn("ok", report)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run:

```bash
python3 -m unittest tests.test_session_audit -v
```

Expected:

```text
ImportError: cannot import name 'session_audit'
```

- [ ] **Step 3: 최소 구현**

`barrier_free/session_audit.py`를 만든다.

```python
"""실제 주행 수집 세션의 품질을 빠르게 점검한다."""

from __future__ import annotations

from pathlib import Path

from . import field_export


def audit_session(path: Path) -> dict:
    bundle = field_export.read_session_folder(path)
    gps_rows = bundle["gps"]
    valid_count = sum(1 for row in gps_rows if int(row.get("gps_valid", 0)) == 1)
    gps_valid_ratio = valid_count / len(gps_rows) if gps_rows else 0.0
    photo_count = len(list((path / "photos").glob("*.jpg"))) if (path / "photos").exists() else 0
    event_count = len(bundle["events"])
    raw_imu_rows = len(bundle["raw_imu"])
    issues = []

    if raw_imu_rows == 0:
        issues.append("raw_imu.csv가 비어 있음")
    if gps_valid_ratio < 0.8:
        issues.append("GPS valid 비율이 80% 미만")
    if event_count > 0 and photo_count == 0:
        issues.append("이벤트가 있지만 사진이 없음")

    return {
        "session_id": bundle["session"]["session_id"],
        "phase": bundle["session"]["phase"],
        "raw_imu_rows": raw_imu_rows,
        "gps_rows": len(gps_rows),
        "gps_valid_ratio": gps_valid_ratio,
        "event_count": event_count,
        "photo_count": photo_count,
        "ok": not issues,
        "issues": issues,
    }
```

- [ ] **Step 4: CLI 추가**

`barrier_free/cli.py` import에 `session_audit`를 추가한다.

```python
from . import collector, field_export, mock_data, model, schema, segments, session_audit
```

parser에 추가한다.

```python
audit = sub.add_parser("audit-session", help="수집 세션의 IMU/GPS/이벤트/사진 품질을 요약한다")
audit.add_argument("path", type=Path)
```

명령 분기에 추가한다.

```python
if args.command == "audit-session":
    print(json.dumps(session_audit.audit_session(args.path), ensure_ascii=False, indent=2))
    return 0
```

- [ ] **Step 5: 통과 확인**

Run:

```bash
python3 -m unittest tests.test_session_audit -v
python3 -m barrier_free.cli audit-session --help
```

Expected:

```text
OK
```

- [ ] **Step 6: 커밋**

```bash
git add barrier_free/session_audit.py barrier_free/cli.py tests/test_session_audit.py
git commit -m "feat: audit field collection sessions"
```

## Task 6: 실제 전/후 비교 실행 문서화

**담당:** Worker D 또는 메인 에이전트

**Files:**

- Modify: `README.md`

- [ ] **Step 1: README에 Pi 주행 후 절차 추가**

`README.md`에 다음 섹션을 추가한다.

```markdown
## 실제 주행 데이터로 전/후 비교 지도 만들기

1. 정비 전 또는 기준 주행을 수집합니다.

```bash
python3 -m barrier_free.cli collect \
  --out sessions \
  --duration 180 \
  --rate 20 \
  --phase before \
  --session-id before_001 \
  --route-name campus_test_route \
  --gps-port /dev/serial0 \
  --camera-device /dev/video0
```

2. 세션 품질을 확인합니다.

```bash
python3 -m barrier_free.cli audit-session sessions/pi_session_YYYYMMDD_HHMMSS
```

3. 같은 경로를 정비 후 또는 비교 주행으로 다시 수집합니다.

4. before/after 비교 JSON을 생성합니다.

```bash
python3 -m barrier_free.cli compare-sessions \
  --before sessions/before_001 \
  --after sessions/after_001 \
  --out web
```

5. 지도를 엽니다.

```bash
python3 -m http.server 8000
```

브라우저:

```text
http://localhost:8000/web/
```
```

- [ ] **Step 2: 문서 검증**

Run:

```bash
rg "compare-sessions|audit-session|실제 주행 데이터로 전/후 비교" README.md
```

Expected:

```text
compare-sessions
audit-session
실제 주행 데이터로 전/후 비교
```

- [ ] **Step 3: 커밋**

```bash
git add README.md
git commit -m "docs: add field before-after comparison runbook"
```

## Task 7: 전체 검증과 브라우저 확인

**담당:** 메인 에이전트

**Files:**

- No direct edit unless verification finds a bug.

- [ ] **Step 1: 전체 테스트**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected:

```text
OK
```

- [ ] **Step 2: mock E2E 재생성**

Run:

```bash
python3 -m barrier_free.cli e2e-demo --out demo_sessions
```

Expected:

```text
demo_sessions/demo_data.json
```

- [ ] **Step 3: 실제 세션 비교 CLI smoke**

mock 세션을 실제 폴더처럼 사용해 smoke test를 실행한다.

```bash
python3 -m barrier_free.cli compare-sessions \
  --before demo_sessions/mock_collection_run01 \
  --after demo_sessions/mock_collection_run01 \
  --out /tmp/barrier-free-web-smoke
```

Expected:

```text
/tmp/barrier-free-web-smoke/demo_data.json
```

- [ ] **Step 4: 로컬 웹 서버**

Run:

```bash
python3 -m http.server 8000
```

Expected:

```text
Serving HTTP on :: port 8000
```

- [ ] **Step 5: Browser 검증**

브라우저에서 `http://localhost:8000/web/` 확인:

- 지도 타일 로딩.
- 세션 선택 가능.
- 이벤트 점 표시.
- 전/후 비교 오버레이 토글 가능.
- 요약 패널에 개선/악화/새 위험 카운트 표시.
- 비교 marker 클릭 시 before/after score와 개선율 표시.

- [ ] **Step 6: 최종 커밋 및 푸시**

Run:

```bash
git status --short --branch
git push
```

Expected:

```text
working tree clean
Everything up-to-date
```

## 서브에이전트 운영 계획

- Explorer 1: CLI/데이터 파이프라인 빈틈 조사.
- Explorer 2: 웹/지도 전후비교 UX 빈틈 조사.
- Explorer 3: 검증/완료 리스크 조사.
- Worker A: `field_export.py`와 `tests/test_field_export.py` 구현.
- Worker B: `web/*` 비교 오버레이와 `tests/test_web_export.py` 구현.
- Worker C: `session_audit.py`와 `tests/test_session_audit.py` 구현.
- 메인 에이전트: `cli.py` 충돌 조정, README, 전체 테스트, 브라우저 검증, 최종 푸시.

병렬 기준:

- Worker A와 Worker B는 병렬 가능하다. A는 Python export, B는 웹 표시라 write set이 거의 분리된다.
- Worker C는 `cli.py`를 건드리므로 A의 CLI 변경 후 진행하거나, 메인 에이전트가 CLI 통합을 맡는다.
- README와 최종 검증은 모든 구현 후 진행한다.

## 완료 기준

- 실제 또는 mock 세션 폴더 2개로 `compare-sessions`가 `web/demo_data.json`을 생성한다.
- 웹 지도에서 before/after 개별 세션과 비교 오버레이를 모두 볼 수 있다.
- `audit-session`으로 실외 주행 직후 GPS valid 비율, IMU 행 수, 이벤트/사진 수를 확인할 수 있다.
- 전체 테스트가 통과한다.
- 브라우저에서 `http://localhost:8000/web/` 수동 검증을 통과한다.
- GitHub `origin/main`에 최종 커밋이 푸시되어 있다.
