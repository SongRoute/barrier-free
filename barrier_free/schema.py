"""세션 파일 스키마 검증과 CSV/JSON 입출력."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable


SESSION_FIELDS = {
    "session_id",
    "phase",
    "run_index",
    "started_at",
    "route_name",
    "device",
    "model_version",
    "label_policy_version",
    "notes",
}

RAW_IMU_FIELDS = ("timestamp", "ax", "ay", "az", "gx", "gy", "gz")
GPS_FIELDS = ("timestamp", "lat", "lon", "gps_valid", "speed_mps")
EVENT_FIELDS = (
    "event_id",
    "timestamp_start",
    "timestamp_end",
    "lat",
    "lon",
    "gps_valid",
    "speed_mps",
    "prediction",
    "confidence",
    "risk_score",
    "segment_id",
    "photo_before",
    "photo_after",
    "model_version",
)
LABEL_FIELDS = (
    "label_id",
    "event_id",
    "timestamp_start",
    "timestamp_end",
    "lat",
    "lon",
    "label",
    "step_height_mm",
    "crack_width_mm",
    "pothole_depth_mm",
    "non_road_shock",
    "notes",
)

PREDICTIONS = {"normal", "caution", "danger", "candidate"}
LABELS = {"normal", "caution", "danger", "exclude"}
PHASES = {"calibration", "before", "after", "demo"}


class SchemaError(ValueError):
    """세션 구조가 데이터 계약을 만족하지 않을 때 발생한다."""


def validate_session_bundle(bundle: dict) -> None:
    """메모리상의 세션 bundle이 필수 구조를 만족하는지 검증한다."""

    for key in ("session", "raw_imu", "gps", "events", "labels"):
        if key not in bundle:
            raise SchemaError(f"missing bundle key: {key}")

    session = bundle["session"]
    missing_session = SESSION_FIELDS - set(session)
    if missing_session:
        raise SchemaError(f"missing session fields: {sorted(missing_session)}")
    if session["phase"] not in PHASES:
        raise SchemaError(f"invalid phase: {session['phase']}")

    _validate_rows("raw_imu", bundle["raw_imu"], RAW_IMU_FIELDS)
    _validate_rows("gps", bundle["gps"], GPS_FIELDS)
    _validate_rows("events", bundle["events"], EVENT_FIELDS)
    _validate_rows("labels", bundle["labels"], LABEL_FIELDS)

    for event in bundle["events"]:
        if event["prediction"] not in PREDICTIONS:
            raise SchemaError(f"invalid prediction: {event['prediction']}")
    for label in bundle["labels"]:
        if label["label"] not in LABELS:
            raise SchemaError(f"invalid label: {label['label']}")


def write_session_bundle(bundle: dict, output_dir: Path) -> Path:
    """세션 bundle을 session.json, raw_imu.csv, gps.csv, events.csv로 저장한다."""

    validate_session_bundle(bundle)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "session.json").write_text(
        json.dumps(bundle["session"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_csv(output_dir / "raw_imu.csv", RAW_IMU_FIELDS, bundle["raw_imu"])
    write_csv(output_dir / "gps.csv", GPS_FIELDS, bundle["gps"])
    write_csv(output_dir / "events.csv", EVENT_FIELDS, bundle["events"])
    write_csv(output_dir / "labels.csv", LABEL_FIELDS, bundle["labels"])
    (output_dir / "photos").mkdir(exist_ok=True)
    return output_dir


def write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict]) -> None:
    """dict row 목록을 CSV로 저장한다."""

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=tuple(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in writer.fieldnames})


def _validate_rows(name: str, rows: list[dict], required_fields: tuple[str, ...]) -> None:
    if not isinstance(rows, list):
        raise SchemaError(f"{name} must be a list")
    for index, row in enumerate(rows):
        missing = [field for field in required_fields if field not in row]
        if missing:
            raise SchemaError(f"{name}[{index}] missing fields: {missing}")
