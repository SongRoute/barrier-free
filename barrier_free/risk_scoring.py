"""IMU feature 기반 수치 위험도 산출."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from . import features


@dataclass(frozen=True)
class RiskThresholds:
    """현장 데이터에 맞춰 조정 가능한 위험도 임계값."""

    caution_delta: float = 0.35
    danger_delta: float = 0.75
    danger_jerk: float = 12.0

    def __post_init__(self) -> None:
        if self.caution_delta <= 0:
            raise ValueError("caution_delta must be positive")
        if self.danger_delta <= self.caution_delta:
            raise ValueError("danger_delta must be greater than caution_delta")
        if self.danger_jerk <= 0:
            raise ValueError("danger_jerk must be positive")

    def to_dict(self) -> dict:
        return asdict(self)


def classify_window(feature_row: dict, thresholds: RiskThresholds) -> dict:
    """IMU window feature를 normal/caution/danger로 분류한다."""

    accel_delta = float(feature_row.get("accel_delta_max", 0.0))
    jerk = float(feature_row.get("jerk_max", 0.0))
    reasons = []
    if accel_delta >= thresholds.danger_delta or jerk >= thresholds.danger_jerk:
        prediction = "danger"
        risk_score = max(_ratio(accel_delta, thresholds.danger_delta), _ratio(jerk, thresholds.danger_jerk))
        if accel_delta >= thresholds.danger_delta:
            reasons.append("accel_delta")
        if jerk >= thresholds.danger_jerk:
            reasons.append("jerk")
    elif accel_delta >= thresholds.caution_delta:
        prediction = "caution"
        risk_score = _ratio(accel_delta, thresholds.danger_delta)
        reasons.append("accel_delta")
    else:
        prediction = "normal"
        risk_score = _ratio(accel_delta, thresholds.danger_delta)

    return {
        "prediction": prediction,
        "risk_score": round(min(1.0, max(0.0, risk_score)), 4),
        "confidence": round(min(1.0, max(0.0, _confidence(prediction, accel_delta, jerk, thresholds))), 4),
        "risk_reasons": reasons,
    }


def score_session_windows(bundle: dict, thresholds: RiskThresholds) -> list[dict]:
    """세션 bundle의 IMU row를 1초 window별 위험도 payload로 변환한다."""

    windows = features.window_imu_rows(bundle["raw_imu"], window_seconds=1.0)
    gps_rows = features.nearest_gps_rows_for_windows(windows, bundle["gps"])
    scored = []
    for index, (window, gps_row) in enumerate(zip(windows, gps_rows), start=1):
        speed = float(gps_row.get("speed_mps", 0.0))
        feature_row = features.extract_window_features(window, speed_mps=speed)
        feature_row["accel_delta_max"] = _accel_delta_max(window)
        classification = classify_window(feature_row, thresholds)
        scored.append(
            {
                "window_id": f"imu_window_{index:04d}",
                "timestamp_start": window[0]["timestamp"],
                "timestamp_end": window[-1]["timestamp"],
                "sample_count": len(window),
                "lat": gps_row["lat"],
                "lon": gps_row["lon"],
                "gps_valid": gps_row["gps_valid"],
                "speed_mps": speed,
                "accel_mag_max": round(float(feature_row["accel_mag_max"]), 4),
                "accel_mag_mean": round(float(feature_row["accel_mag_mean"]), 4),
                "accel_delta_max": round(float(feature_row["accel_delta_max"]), 4),
                "jerk_max": round(float(feature_row["jerk_max"]), 4),
                **classification,
            }
        )
    return scored


def event_rows_from_scored_windows(scored_windows: list[dict], *, session_id: str, model_version: str = "threshold-v1") -> list[dict]:
    """segment 집계를 위해 normal이 아닌 window를 event row 형태로 변환한다."""

    events = []
    for row in scored_windows:
        if row["prediction"] == "normal":
            continue
        events.append(
            {
                "event_id": f"{session_id}_{row['window_id']}",
                "timestamp_start": row["timestamp_start"],
                "timestamp_end": row["timestamp_end"],
                "lat": row["lat"],
                "lon": row["lon"],
                "gps_valid": row["gps_valid"],
                "speed_mps": row["speed_mps"],
                "prediction": row["prediction"],
                "confidence": row["confidence"],
                "risk_score": row["risk_score"],
                "segment_id": "",
                "photo_before": "",
                "photo_after": "",
                "model_version": model_version,
                "source": "imu-threshold",
                "source_window_id": row["window_id"],
                "source_session_id": row.get("source_session_id", session_id),
                "threshold_version": row.get("threshold_version", model_version),
                "risk_reasons": row.get("risk_reasons", []),
                "route_name": row.get("route_name", ""),
                "phase": row.get("phase", ""),
            }
        )
    return events


def _ratio(value: float, threshold: float) -> float:
    if threshold <= 0:
        return 0.0
    return value / threshold


def _confidence(prediction: str, accel_delta: float, jerk: float, thresholds: RiskThresholds) -> float:
    if prediction == "danger":
        return max(_ratio(accel_delta, thresholds.danger_delta), _ratio(jerk, thresholds.danger_jerk))
    if prediction == "caution":
        margin = accel_delta - thresholds.caution_delta
        width = max(thresholds.danger_delta - thresholds.caution_delta, 0.001)
        return 0.55 + min(0.4, max(0.0, margin / width) * 0.4)
    return max(0.1, 1.0 - _ratio(accel_delta, thresholds.caution_delta))


def _accel_delta_max(window: list[dict]) -> float:
    deltas = []
    for row in window:
        accel_mag = (row["ax"] * row["ax"] + row["ay"] * row["ay"] + row["az"] * row["az"]) ** 0.5
        deltas.append(abs(accel_mag - 1.0))
    return max(deltas) if deltas else 0.0
