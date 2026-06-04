"""Raspberry Pi 수집기 skeleton.

현재는 실제 센서 대신 mock stream을 사용한다. 하드웨어 IMU/GPS가 준비되면
이 파일의 stream 입력 부분만 교체하고 세션 계약은 유지한다.
"""

from __future__ import annotations

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


def _load_model(model_path: Path | None) -> model.TinyForestClassifier | None:
    if model_path is None:
        return None
    return model.TinyForestClassifier.from_json(model_path.read_text(encoding="utf-8"))


def _nearest_gps(window: list[dict], gps_rows: list[dict]) -> dict:
    middle = (window[0]["timestamp"] + window[-1]["timestamp"]) / 2
    return min(gps_rows, key=lambda row: abs(row["timestamp"] - middle))
