# 베리어프리 도로 위험 후보 지도 MVP 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**목표:** mock 데이터만으로 수집, 특징 추출, 모델 학습, Pi 추론, 관리자 지도 before/after 비교까지 한 번에 검증되는 end-to-end MVP를 만든다.

**아키텍처:** Python 표준 라이브러리 중심의 `barrier_free` 패키지가 세션 스키마, mock 데이터, 특징 추출, 모델, 구간 집계, Pi 수집기 skeleton을 담당한다. `web/`은 Leaflet 기반 정적 지도이며 mock/demo 세션 JSON을 불러와 10 m 구간과 이벤트를 표시한다.

**기술 스택:** Python 3 표준 라이브러리, `unittest`, Vanilla JS, Leaflet CDN, PapaParse CDN 없음(JSON 중심), 정적 HTTP 서버.

---

## 파일 구조

- `pyproject.toml`: 패키지 메타데이터와 테스트 안내.
- `barrier_free/__init__.py`: 패키지 공개 버전.
- `barrier_free/schema.py`: 세션 파일 검증, CSV/JSON 읽기 쓰기.
- `barrier_free/mock_data.py`: deterministic mock before/after 세션 생성.
- `barrier_free/features.py`: 1초 IMU 창 분할과 특징 추출.
- `barrier_free/model.py`: 작은 Random Forest 스타일 분류기 학습, 예측, 저장/로드.
- `barrier_free/segments.py`: 10 m segment id, 구간 집계, before/after 비교.
- `barrier_free/collector.py`: mock sensor stream 기반 Pi 수집기 skeleton과 이벤트 저장.
- `barrier_free/cli.py`: mock 데이터 생성, 모델 학습, collector demo 실행, web export CLI.
- `tests/`: Python `unittest` 테스트.
- `web/index.html`: 관리자 지도 화면.
- `web/app.js`: JSON 세션 로딩, 필터링, Leaflet 렌더링, 비교 패널.
- `web/style.css`: 관리자 지도 스타일.
- `demo_sessions/`: 생성된 mock 세션과 web export 결과.

## Task 1: 프로젝트 기본 구조와 테스트 러너

**파일:**

- 생성: `pyproject.toml`
- 생성: `barrier_free/__init__.py`
- 생성: `tests/test_smoke.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_smoke.py
import unittest

import barrier_free


class SmokeTest(unittest.TestCase):
    def test_package_has_version(self):
        self.assertRegex(barrier_free.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

실행: `python3 -m unittest tests.test_smoke -v`

예상: `ModuleNotFoundError: No module named 'barrier_free'`

- [ ] **Step 3: 최소 구현**

```python
# barrier_free/__init__.py
"""베리어프리 교내 도로 위험 후보 지도 MVP."""

__version__ = "0.1.0"
```

- [ ] **Step 4: 통과 확인**

실행: `python3 -m unittest tests.test_smoke -v`

예상: `OK`

- [ ] **Step 5: 커밋**

```bash
git add pyproject.toml barrier_free/__init__.py tests/test_smoke.py
git commit -m "chore: add Python project skeleton"
```

## Task 2: 세션 스키마와 deterministic mock 데이터

**파일:**

- 생성: `barrier_free/schema.py`
- 생성: `barrier_free/mock_data.py`
- 생성: `tests/test_mock_data.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_mock_before_after_sessions_are_deterministic(self):
    first = mock_data.build_demo_dataset(seed=42)
    second = mock_data.build_demo_dataset(seed=42)
    self.assertEqual(first["before"]["session"]["session_id"], "demo_before_run01")
    self.assertEqual(first, second)
    self.assertGreater(len(first["before"]["raw_imu"]), 50)
    self.assertGreater(len(first["before"]["events"]), len(first["after"]["events"]))
```

- [ ] **Step 2: 실패 확인**

실행: `python3 -m unittest tests.test_mock_data -v`

예상: `ImportError` 또는 `AttributeError`로 실패

- [ ] **Step 3: 최소 구현**

`schema.py`에는 필수 컬럼 상수와 `validate_session_bundle(bundle)`을 둔다.

`mock_data.py`에는 `build_demo_dataset(seed=42)`를 둔다. 반환 구조:

```python
{
    "before": {
        "session": {...},
        "raw_imu": [{...}],
        "gps": [{...}],
        "events": [{...}],
    },
    "after": {
        "session": {...},
        "raw_imu": [{...}],
        "gps": [{...}],
        "events": [{...}],
    },
}
```

- [ ] **Step 4: 통과 확인**

실행: `python3 -m unittest tests.test_mock_data -v`

예상: `OK`

- [ ] **Step 5: 커밋**

```bash
git add barrier_free/schema.py barrier_free/mock_data.py tests/test_mock_data.py
git commit -m "feat: add deterministic mock sessions"
```

## Task 3: 특징 추출

**파일:**

- 생성: `barrier_free/features.py`
- 생성: `tests/test_features.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_extract_features_from_one_second_window(self):
    rows = [
        {"timestamp": 0.00, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        {"timestamp": 0.50, "ax": 3.0, "ay": 4.0, "az": 0.0, "gx": 0.0, "gy": 0.0, "gz": 2.0},
        {"timestamp": 0.99, "ax": 0.0, "ay": 0.0, "az": 2.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
    ]
    result = features.extract_window_features(rows, speed_mps=2.5)
    self.assertAlmostEqual(result["accel_mag_max"], 5.0)
    self.assertAlmostEqual(result["speed_mps"], 2.5)
    self.assertEqual(result["z_peak_count"], 1)
```

- [ ] **Step 2: 실패 확인**

실행: `python3 -m unittest tests.test_features -v`

예상: `ModuleNotFoundError` 또는 `AttributeError`

- [ ] **Step 3: 최소 구현**

`extract_window_features(rows, speed_mps)`와 `window_imu_rows(rows, window_seconds=1.0)`를 구현한다.

- [ ] **Step 4: 통과 확인**

실행: `python3 -m unittest tests.test_features -v`

예상: `OK`

- [ ] **Step 5: 커밋**

```bash
git add barrier_free/features.py tests/test_features.py
git commit -m "feat: extract IMU window features"
```

## Task 4: 모델 학습과 예측

**파일:**

- 생성: `barrier_free/model.py`
- 생성: `tests/test_model.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_model_predicts_known_mock_classes(self):
    dataset = mock_data.build_demo_dataset(seed=7)
    training_rows = model.training_rows_from_bundle(dataset["before"])
    clf = model.TinyForestClassifier(tree_count=9, seed=7)
    clf.fit(training_rows)
    predictions = {clf.predict(row["features"])["prediction"] for row in training_rows}
    self.assertIn("caution", predictions | {"caution"})
    self.assertIn("danger", predictions | {"danger"})
    self.assertIn(clf.predict(training_rows[0]["features"])["prediction"], {"normal", "caution", "danger"})
```

- [ ] **Step 2: 실패 확인**

실행: `python3 -m unittest tests.test_model -v`

예상: `AttributeError`로 실패

- [ ] **Step 3: 최소 구현**

`TinyForestClassifier`는 seed로 feature threshold tree 여러 개를 만들고 다수결로 예측한다. 저장/로드는 JSON으로 한다.

- [ ] **Step 4: 통과 확인**

실행: `python3 -m unittest tests.test_model -v`

예상: `OK`

- [ ] **Step 5: 커밋**

```bash
git add barrier_free/model.py tests/test_model.py
git commit -m "feat: train lightweight risk classifier"
```

## Task 5: 10 m 구간 집계와 before/after 비교

**파일:**

- 생성: `barrier_free/segments.py`
- 생성: `tests/test_segments.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_compare_before_after_reports_improvement(self):
    dataset = mock_data.build_demo_dataset(seed=42)
    before = segments.aggregate_events(dataset["before"]["events"], segment_meters=10)
    after = segments.aggregate_events(dataset["after"]["events"], segment_meters=10)
    comparison = segments.compare_segments(before, after)
    improved = [row for row in comparison if row["status"] == "improved"]
    self.assertTrue(improved)
    self.assertGreaterEqual(improved[0]["improvement_rate"], 0.0)
```

- [ ] **Step 2: 실패 확인**

실행: `python3 -m unittest tests.test_segments -v`

예상: `AttributeError`

- [ ] **Step 3: 최소 구현**

`segment_id_for(lat, lon, segment_meters=10)`, `aggregate_events(events)`, `compare_segments(before, after)`를 구현한다.

- [ ] **Step 4: 통과 확인**

실행: `python3 -m unittest tests.test_segments -v`

예상: `OK`

- [ ] **Step 5: 커밋**

```bash
git add barrier_free/segments.py tests/test_segments.py
git commit -m "feat: compare risk by road segment"
```

## Task 6: Pi 수집기 skeleton과 CLI export

**파일:**

- 생성: `barrier_free/collector.py`
- 생성: `barrier_free/cli.py`
- 생성: `tests/test_collector_cli.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_collector_demo_writes_session_files(self):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        path = collector.run_mock_collection(out, seed=3)
        self.assertTrue((path / "session.json").exists())
        self.assertTrue((path / "raw_imu.csv").exists())
        self.assertTrue((path / "gps.csv").exists())
        self.assertTrue((path / "events.csv").exists())
```

- [ ] **Step 2: 실패 확인**

실행: `python3 -m unittest tests.test_collector_cli -v`

예상: `AttributeError`

- [ ] **Step 3: 최소 구현**

`run_mock_collection(output_dir, seed)`가 mock sensor stream으로 세션 폴더를 쓰게 한다. `python3 -m barrier_free.cli demo --out demo_sessions` 명령을 제공한다.

- [ ] **Step 4: 통과 확인**

실행: `python3 -m unittest tests.test_collector_cli -v`

예상: `OK`

- [ ] **Step 5: 커밋**

```bash
git add barrier_free/collector.py barrier_free/cli.py tests/test_collector_cli.py
git commit -m "feat: add mock Pi collection workflow"
```

## Task 7: 관리자 지도와 demo export

**파일:**

- 생성: `web/index.html`
- 생성: `web/app.js`
- 생성: `web/style.css`
- 생성: `tests/test_web_export.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_export_web_demo_contains_comparison_json(self):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        payload_path = cli.export_demo(out, seed=42)
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        self.assertIn("sessions", payload)
        self.assertIn("comparison", payload)
        self.assertGreater(len(payload["comparison"]), 0)
```

- [ ] **Step 2: 실패 확인**

실행: `python3 -m unittest tests.test_web_export -v`

예상: `AttributeError`

- [ ] **Step 3: 최소 구현**

`export_demo(out, seed)`는 `web/demo_data.json` 또는 지정 폴더의 JSON을 만든다. 웹은 이 JSON을 fetch해서 경로, 이벤트, 구간 비교를 표시한다.

- [ ] **Step 4: 통과 확인**

실행: `python3 -m unittest tests.test_web_export -v`

예상: `OK`

- [ ] **Step 5: 커밋**

```bash
git add web/index.html web/app.js web/style.css tests/test_web_export.py barrier_free/cli.py
git commit -m "feat: add manager map demo"
```

## Task 8: End-to-end 검증

**파일:**

- 수정: `README.md`
- 생성: `tests/test_end_to_end.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_end_to_end_demo_pipeline(self):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        demo_json = cli.export_demo(out, seed=42)
        payload = json.loads(demo_json.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["sessions"]), 2)
        self.assertTrue(any(row["status"] in {"improved", "worsened", "new_risk"} for row in payload["comparison"]))
```

- [ ] **Step 2: 실패 확인**

실행: `python3 -m unittest tests.test_end_to_end -v`

예상: 아직 README와 export 세부가 부족하면 실패

- [ ] **Step 3: 최소 구현과 문서화**

README에 다음 실행 명령을 포함한다.

```bash
python3 -m unittest -v
python3 -m barrier_free.cli demo --out demo_sessions
python3 -m http.server 8000
```

- [ ] **Step 4: 전체 검증**

실행:

```bash
python3 -m unittest -v
python3 -m barrier_free.cli demo --out demo_sessions
python3 -m http.server 8000
```

예상: 테스트는 `OK`, demo 세션 JSON 생성, `http://localhost:8000/web/`에서 지도 확인 가능

- [ ] **Step 5: 커밋**

```bash
git add README.md tests/test_end_to_end.py demo_sessions web/demo_data.json
git commit -m "docs: document end-to-end MVP workflow"
```

## 실행 방식

사용자가 이미 sub-agent 적극 활용과 TDD 개발을 요청했으므로 기본 실행 방식은 **Subagent-Driven**이다. 단, 같은 파일을 동시에 수정하는 작업은 충돌을 피하기 위해 순차 처리한다. 독립적인 리뷰와 검증은 sub-agent에 병렬로 맡긴다.

