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
    """before/after 세션 폴더 2개를 web/demo_data.json 구조로 저장한다."""

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
