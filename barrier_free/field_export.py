"""실제 수집 세션 before/after를 관리자 지도 payload로 변환한다."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from . import features, schema, segments


def export_session_comparison(
    *,
    before_path: Path,
    after_path: Path,
    output_dir: Path,
    segment_meters: int = 10,
) -> Path:
    """before/after 세션 폴더 2개를 web/demo_data.json 구조로 저장한다."""

    before_bundle = read_session_folder(before_path)
    after_bundle = read_session_folder(after_path)
    _validate_comparison_metadata(before_bundle, after_bundle)
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


def export_session_preview(
    *,
    session_path: Path,
    output_dir: Path,
    segment_meters: int = 10,
) -> Path:
    """단일 수집 세션을 web/demo_data.json 구조로 저장한다."""

    bundle = read_session_folder(session_path)
    summary = segments.aggregate_events(bundle["events"], segment_meters=segment_meters)
    coverage = segments.route_coverage_segments(bundle["gps"], segment_meters=segment_meters)
    payload = {
        "source": {
            "type": "field-session-preview",
            "session_path": str(session_path),
            "segment_meters": segment_meters,
            "coverage_count": len(coverage),
        },
        "model": {
            "type": "field-or-threshold",
            "version": bundle["session"].get("model_version", "none"),
            "training_rows": 0,
            "recall": None,
            "confusion_matrix": {},
        },
        "sessions": [
            session_payload("preview", bundle, summary),
        ],
        "comparison": [],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "demo_data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _validate_comparison_metadata(before_bundle: dict, after_bundle: dict) -> None:
    before_session = before_bundle["session"]
    after_session = after_bundle["session"]
    if before_session["phase"] != "before":
        raise ValueError(f"before session phase must be before: {before_session['phase']}")
    if after_session["phase"] != "after":
        raise ValueError(f"after session phase must be after: {after_session['phase']}")
    if before_session["route_name"] != after_session["route_name"]:
        raise ValueError(
            "route_name must match: "
            f"{before_session['route_name']} != {after_session['route_name']}"
        )


def session_payload(name: str, bundle: dict, summary: dict) -> dict:
    return {
        "name": name,
        "session": bundle["session"],
        "gps": bundle["gps"],
        "events": bundle["events"],
        "segments": list(summary.values()),
        "imu_windows": imu_window_payloads(bundle),
    }


def imu_window_payloads(bundle: dict) -> list[dict]:
    """1초 IMU window를 지도 표시용 강도 payload로 변환한다."""

    windows = features.window_imu_rows(bundle["raw_imu"], window_seconds=1.0)
    gps_rows = bundle["gps"]
    nearest_gps_rows = _nearest_gps_rows_for_windows(windows, gps_rows)
    payloads = []
    for index, (window, gps_row) in enumerate(zip(windows, nearest_gps_rows), start=1):
        speed = float(gps_row.get("speed_mps", 0.0))
        feature_row = features.extract_window_features(window, speed_mps=speed)
        payloads.append(
            {
                "window_id": f"imu_window_{index:04d}",
                "timestamp_start": window[0]["timestamp"],
                "timestamp_end": window[-1]["timestamp"],
                "sample_count": len(window),
                "lat": gps_row["lat"],
                "lon": gps_row["lon"],
                "gps_valid": gps_row["gps_valid"],
                "speed_mps": gps_row["speed_mps"],
                "accel_mag_max": round(float(feature_row["accel_mag_max"]), 4),
                "accel_mag_mean": round(float(feature_row["accel_mag_mean"]), 4),
                "accel_delta_max": round(_accel_delta_max(window), 4),
                "jerk_max": round(float(feature_row["jerk_max"]), 4),
            }
        )
    return payloads


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


def _nearest_gps_rows_for_windows(windows: list[list[dict]], gps_rows: list[dict]) -> list[dict]:
    if not windows:
        return []
    if not gps_rows:
        return [_invalid_gps_row(window[0]["timestamp"]) for window in windows]

    sorted_gps = sorted(gps_rows, key=lambda row: row["timestamp"])
    nearest_rows = []
    cursor = 0
    for window in windows:
        middle = (window[0]["timestamp"] + window[-1]["timestamp"]) / 2
        while cursor + 1 < len(sorted_gps):
            current_distance = abs(sorted_gps[cursor]["timestamp"] - middle)
            next_distance = abs(sorted_gps[cursor + 1]["timestamp"] - middle)
            if next_distance > current_distance:
                break
            cursor += 1
        nearest_rows.append(sorted_gps[cursor])
    return nearest_rows


def _invalid_gps_row(timestamp: float) -> dict:
    return {"timestamp": timestamp, "lat": 0.0, "lon": 0.0, "gps_valid": 0, "speed_mps": 0.0}


def _accel_delta_max(window: list[dict]) -> float:
    deltas = []
    for row in window:
        accel_mag = math.sqrt(row["ax"] * row["ax"] + row["ay"] * row["ay"] + row["az"] * row["az"])
        deltas.append(abs(accel_mag - 1.0))
    return max(deltas) if deltas else 0.0


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
