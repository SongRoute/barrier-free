"""실제 주행 수집 세션의 품질을 빠르게 점검한다."""

from __future__ import annotations

from pathlib import Path

from . import field_export


def audit_session(path: Path) -> dict:
    """수집 세션 폴더의 핵심 품질 지표와 이슈를 반환한다."""

    path = Path(path)
    bundle = field_export.read_session_folder(path)
    gps_rows = bundle["gps"]
    raw_imu_rows = len(bundle["raw_imu"])
    event_count = len(bundle["events"])
    photo_count = _photo_count(path)
    expected_photos = _expected_event_photos(bundle["events"])
    missing_photos = [photo for photo in expected_photos if not (path / photo).exists()]
    valid_count = sum(1 for row in gps_rows if _is_valid_gps(row))
    gps_valid_ratio = valid_count / len(gps_rows) if gps_rows else 0.0
    issues = []

    if raw_imu_rows == 0:
        issues.append("raw_imu.csv가 비어 있음")
    if gps_valid_ratio < 0.8:
        issues.append("GPS valid 비율이 80% 미만")
    if event_count > 0 and photo_count == 0:
        issues.append("이벤트가 있지만 사진이 없음")
    if missing_photos:
        issues.append("이벤트 사진 파일 누락")

    return {
        "session_id": bundle["session"]["session_id"],
        "phase": bundle["session"]["phase"],
        "raw_imu_rows": raw_imu_rows,
        "gps_rows": len(gps_rows),
        "gps_valid_ratio": gps_valid_ratio,
        "event_count": event_count,
        "photo_count": photo_count,
        "expected_photo_count": len(expected_photos),
        "missing_photo_count": len(missing_photos),
        "ok": not issues,
        "issues": issues,
    }


def _photo_count(path: Path) -> int:
    photos_path = path / "photos"
    if not photos_path.exists():
        return 0
    return len(list(photos_path.glob("*.jpg")))


def _expected_event_photos(events: list[dict]) -> list[Path]:
    photos = []
    for event in events:
        for key in ("photo_before", "photo_after"):
            value = event.get(key, "")
            if value:
                photos.append(Path(value))
    return photos


def _is_valid_gps(row: dict) -> bool:
    try:
        return int(row.get("gps_valid", 0)) == 1
    except (TypeError, ValueError):
        return False
