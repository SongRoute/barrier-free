"""현장/mock 라벨을 IMU 창에 연결한다."""

from __future__ import annotations

from . import features


def training_rows_from_bundle(bundle: dict) -> list[dict]:
    """세션 bundle에서 exclude를 제외한 학습 행을 만든다."""

    windows = features.window_imu_rows(bundle["raw_imu"], window_seconds=1.0)
    rows = []
    for label in bundle.get("labels", []):
        if label["label"] == "exclude":
            continue
        window = _window_for_label(windows, label)
        if not window:
            continue
        speed = features.nearest_speed_for_window(window, bundle["gps"])
        rows.append(
            {
                "label_id": label["label_id"],
                "event_id": label.get("event_id", ""),
                "label": label["label"],
                "timestamp_start": label["timestamp_start"],
                "timestamp_end": label["timestamp_end"],
                "features": features.extract_window_features(window, speed_mps=speed),
            }
        )
    return rows


def _window_for_label(windows: list[list[dict]], label: dict) -> list[dict]:
    target = (label["timestamp_start"] + label["timestamp_end"]) / 2
    if not windows:
        return []
    nearest = min(
        windows,
        key=lambda window: abs(((window[0]["timestamp"] + window[-1]["timestamp"]) / 2) - target),
    )
    nearest_middle = (nearest[0]["timestamp"] + nearest[-1]["timestamp"]) / 2
    if abs(nearest_middle - target) > 0.75:
        return []
    return nearest
