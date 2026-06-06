"""before 세션에서 개발/시연 검증용 synthetic after 세션을 생성한다."""

from __future__ import annotations

import shutil
from pathlib import Path
from statistics import median

from . import field_export, schema


def generate_mock_after_sessions(
    *,
    sessions_root: Path,
    route_name: str,
    output_dir: Path | None = None,
    improvement_factor: float = 0.35,
    session_prefix: str = "after_mock",
    overwrite: bool = False,
) -> list[Path]:
    """같은 route의 before 세션들을 진동 완화된 synthetic after 세션으로 복제한다.

    `improvement_factor`는 0에 가까울수록 IMU 편차를 강하게 줄이고, 1이면 원본과 거의 같다.
    이 함수는 실제 after 실험을 대체하기보다 최종 파이프라인 검증용 데이터를 만들기 위한 도구다.
    """

    if not 0 <= improvement_factor <= 1:
        raise ValueError("improvement_factor must be between 0 and 1")
    if not route_name:
        raise ValueError("route_name is required")

    output_root = output_dir or sessions_root
    before_records = []
    for path in field_export.discover_session_paths(sessions_root):
        bundle = field_export.read_session_folder(path)
        session = bundle["session"]
        if session["phase"] == "before" and session["route_name"] == route_name:
            before_records.append((path, bundle))

    if not before_records:
        raise ValueError(f"no before sessions found for route_name: {route_name}")

    generated_paths = []
    for _source_path, bundle in before_records:
        source_session = bundle["session"]
        target_session_id = f"{session_prefix}_{source_session['session_id']}"
        target_path = output_root / target_session_id
        if target_path.exists():
            if not overwrite:
                raise ValueError(f"target session already exists: {target_path}")
            shutil.rmtree(target_path)

        after_session = dict(source_session)
        after_session["session_id"] = target_session_id
        after_session["phase"] = "after"
        after_session["source_session_id"] = source_session["session_id"]
        after_session["synthetic_after"] = True
        after_session["model_version"] = "synthetic-after"
        after_session["notes"] = (
            f"synthetic after generated from {source_session['session_id']}; "
            f"improvement_factor={improvement_factor}"
        )

        after_bundle = {
            "session": after_session,
            "raw_imu": _smooth_imu_rows(bundle["raw_imu"], improvement_factor),
            "gps": [dict(row) for row in bundle["gps"]],
            "events": [],
            "labels": [],
        }
        generated_paths.append(schema.write_session_bundle(after_bundle, target_path))

    return generated_paths


def _smooth_imu_rows(rows: list[dict], improvement_factor: float) -> list[dict]:
    if not rows:
        return []

    baseline = {
        field: median(float(row[field]) for row in rows)
        for field in ("ax", "ay", "az", "gx", "gy", "gz")
    }
    smoothed = []
    for row in rows:
        smoothed_row = {"timestamp": row["timestamp"]}
        for field in ("ax", "ay", "az", "gx", "gy", "gz"):
            value = float(row[field])
            smoothed_row[field] = round(baseline[field] + (value - baseline[field]) * improvement_factor, 6)
        smoothed.append(smoothed_row)
    return smoothed
