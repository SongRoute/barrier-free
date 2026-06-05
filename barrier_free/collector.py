"""Raspberry Pi 수집기 skeleton.

현재는 실제 센서 대신 mock stream을 사용한다. 하드웨어 IMU/GPS가 준비되면
이 파일의 stream 입력 부분만 교체하고 세션 계약은 유지한다.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import features, mock_data, model, schema


def run_mock_collection(output_dir: Path, seed: int = 42, model_path: Path | None = None) -> Path:
    """mock sensor stream으로 Pi 수집 세션 폴더를 생성한다.

    model_path가 없으면 raw 후보 수집 모드로 `candidate` 이벤트를 쓴다.
    model_path가 있으면 실제 특징 추출과 모델 예측을 사용한다.
    """

    source = mock_data.build_demo_dataset(seed=seed)["before"]
    classifier = _load_model(model_path)
    bundle = {
        "session": dict(source["session"]),
        "raw_imu": list(source["raw_imu"]),
        "gps": list(source["gps"]),
        "events": [],
        "labels": [],
    }
    bundle["session"]["session_id"] = "mock_collection_run01"
    bundle["session"]["phase"] = "demo"
    bundle["session"]["model_version"] = "tiny-forest-mock" if classifier else "none"

    windows = features.window_imu_rows(bundle["raw_imu"], window_seconds=1.0)
    events = []
    for index, window in enumerate(windows, start=1):
        speed = features.nearest_speed_for_window(window, bundle["gps"])
        feature_row = features.extract_window_features(window, speed_mps=speed)
        gps_row = _nearest_gps(window, bundle["gps"])

        if classifier is None:
            if feature_row["accel_mag_max"] < 1.8:
                continue
            prediction = {
                "prediction": "candidate",
                "confidence": min(0.99, feature_row["accel_mag_max"] / 4.0),
                "risk_score": min(1.0, feature_row["accel_mag_max"] / 4.0),
            }
            model_version = "none"
        else:
            prediction = classifier.predict(feature_row)
            if prediction["prediction"] == "normal":
                continue
            model_version = "tiny-forest-mock"

        events.append(
            {
                "event_id": f"mock_collection_event_{index:02d}",
                "timestamp_start": window[0]["timestamp"],
                "timestamp_end": window[-1]["timestamp"],
                "lat": gps_row["lat"],
                "lon": gps_row["lon"],
                "gps_valid": gps_row["gps_valid"],
                "speed_mps": gps_row["speed_mps"],
                "prediction": prediction["prediction"],
                "confidence": round(float(prediction["confidence"]), 3),
                "risk_score": round(float(prediction["risk_score"]), 3),
                "segment_id": "",
                "photo_before": f"photos/mock_collection_event_{index:02d}_before.jpg",
                "photo_after": f"photos/mock_collection_event_{index:02d}_after.jpg",
                "model_version": model_version,
            }
        )

    bundle["events"] = events
    output_path = output_dir / bundle["session"]["session_id"]
    return schema.write_session_bundle(bundle, output_path)


def run_sensor_collection(
    output_dir: Path,
    *,
    imu_reader,
    gps_reader,
    camera=None,
    duration_seconds: float = 60.0,
    sample_rate_hz: float = 20.0,
    model_path: Path | None = None,
    session_id: str | None = None,
    impact_threshold: float = 1.8,
    sleeper=time.sleep,
    clock=time.time,
) -> Path:
    """실제 센서 reader에서 세션을 수집한다.

    imu_reader는 `read_sample(timestamp=None)`, gps_reader는 `read_sample()`을 제공해야 한다.
    camera는 선택 사항이며 `capture(path)`를 제공하면 이벤트 사진을 저장한다.
    """

    classifier = _load_model(model_path)
    started_at = clock()
    session_id = session_id or time.strftime("pi_session_%Y%m%d_%H%M%S", time.localtime(started_at))
    raw_imu = []
    gps_rows = []
    sample_count = max(1, int(duration_seconds * sample_rate_hz))

    interval = 1.0 / sample_rate_hz
    last_gps = {"timestamp": started_at, "lat": 0.0, "lon": 0.0,
                "gps_valid": 0, "speed_mps": 0.0}
    gps_every = max(1, int(round(sample_rate_hz)))  # 1초에 한 번만 GPS 읽기

    for i in range(sample_count):
        ts = clock()
        raw_imu.append(imu_reader.read_sample(timestamp=ts))
        if i % gps_every == 0:
            last_gps = gps_reader.read_sample()
        gps_rows.append(dict(last_gps, timestamp=ts))
        if sleeper is not None:
            sleeper(0 if sample_count <= 10 else interval)


    bundle = {
        "session": {
            "session_id": session_id,
            "phase": "demo",
            "run_index": 1,
            "started_at": _iso8601(started_at),
            "route_name": "pi_field_collection",
            "device": "Raspberry Pi 3B + MPU6050 + NEO-M8N + USB webcam",
            "model_version": "tiny-forest-mock" if classifier else "none",
            "label_policy_version": "none",
            "notes": "hardware sensor collection",
        },
        "raw_imu": raw_imu,
        "gps": gps_rows,
        "events": [],
        "labels": [],
    }

    windows = features.window_imu_rows(raw_imu, window_seconds=1.0)
    events = _events_from_windows(
        windows,
        gps_rows,
        classifier=classifier,
        camera=camera,
        output_dir=output_dir / session_id,
        impact_threshold=impact_threshold,
    )
    bundle["events"] = events
    return schema.write_session_bundle(bundle, output_dir / session_id)


def _load_model(model_path: Path | None) -> model.TinyForestClassifier | None:
    if model_path is None:
        return None
    return model.TinyForestClassifier.from_json(model_path.read_text(encoding="utf-8"))


def _nearest_gps(window: list[dict], gps_rows: list[dict]) -> dict:
    middle = (window[0]["timestamp"] + window[-1]["timestamp"]) / 2
    return min(gps_rows, key=lambda row: abs(row["timestamp"] - middle))


def _events_from_windows(
    windows: list[list[dict]],
    gps_rows: list[dict],
    *,
    classifier: model.TinyForestClassifier | None,
    camera,
    output_dir: Path,
    impact_threshold: float,
) -> list[dict]:
    events = []
    for index, window in enumerate(windows, start=1):
        speed = features.nearest_speed_for_window(window, gps_rows)
        feature_row = features.extract_window_features(window, speed_mps=speed)
        gps_row = _nearest_gps(window, gps_rows)
        if classifier is None:
            if feature_row["accel_mag_max"] < impact_threshold:
                continue
            prediction = {
                "prediction": "candidate",
                "confidence": min(0.99, feature_row["accel_mag_max"] / max(impact_threshold * 2, 0.1)),
                "risk_score": min(1.0, feature_row["accel_mag_max"] / max(impact_threshold * 2, 0.1)),
            }
            model_version = "none"
        else:
            prediction = classifier.predict(feature_row)
            if prediction["prediction"] == "normal":
                continue
            model_version = "tiny-forest-mock"

        event_id = f"event_{index:04d}"
        photo_before = ""
        photo_after = ""
        if camera is not None:
            photo_before = f"photos/{event_id}_before.jpg"
            photo_after = f"photos/{event_id}_after.jpg"
            camera.capture(output_dir / photo_before)
            camera.capture(output_dir / photo_after)

        events.append(
            {
                "event_id": event_id,
                "timestamp_start": window[0]["timestamp"],
                "timestamp_end": window[-1]["timestamp"],
                "lat": gps_row["lat"],
                "lon": gps_row["lon"],
                "gps_valid": gps_row["gps_valid"],
                "speed_mps": gps_row["speed_mps"],
                "prediction": prediction["prediction"],
                "confidence": round(float(prediction["confidence"]), 3),
                "risk_score": round(float(prediction["risk_score"]), 3),
                "segment_id": "",
                "photo_before": photo_before,
                "photo_after": photo_after,
                "model_version": model_version,
            }
        )
    return events


def _iso8601(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))
