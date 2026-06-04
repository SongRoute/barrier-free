"""Segment-level aggregation and before/after comparison helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping


METERS_PER_DEGREE_LAT = 111_320.0
RISK_PREDICTIONS = {"danger", "caution", "candidate"}
DEFAULT_RISK_SCORES = {
    "danger": 0.90,
    "caution": 0.55,
    "candidate": 0.45,
    "normal": 0.0,
}


def segment_id_for(lat, lon, segment_meters: int = 10) -> str:
    """Return a stable approximate grid id for a GPS coordinate."""

    if segment_meters <= 0:
        raise ValueError("segment_meters must be positive")

    latitude = float(lat)
    longitude = float(lon)
    lat_bucket = math.floor(latitude * METERS_PER_DEGREE_LAT / segment_meters)
    lon_scale = METERS_PER_DEGREE_LAT * math.cos(math.radians(latitude))
    lon_bucket = math.floor(longitude * lon_scale / segment_meters)
    return f"{segment_meters:g}m:{lat_bucket}:{lon_bucket}"


def aggregate_events(events: Iterable[Mapping], segment_meters: int = 10) -> dict:
    """Aggregate event rows by approximate road segment."""

    grouped = {}
    for event in events:
        if not _gps_valid(event):
            continue

        segment_id = _event_segment_id(event, segment_meters)
        if not segment_id:
            continue

        score = _event_risk_score(event)
        is_risk_candidate = _prediction(event) in RISK_PREDICTIONS
        row = grouped.setdefault(
            segment_id,
            {
                "segment_id": segment_id,
                "segment_meters": segment_meters,
                "event_count": 0,
                "risk_candidate_count": 0,
                "max_risk_score": 0.0,
                "avg_risk_score": 0.0,
                "repeated_detection_ratio": 0.0,
                "risk_level": "normal",
                "center_lat": None,
                "center_lon": None,
                "_risk_score_total": 0.0,
                "_lat_total": 0.0,
                "_lon_total": 0.0,
            },
        )
        row["event_count"] += 1
        row["risk_candidate_count"] += int(is_risk_candidate)
        row["max_risk_score"] = max(row["max_risk_score"], score)
        row["_risk_score_total"] += score
        row["_lat_total"] += float(event["lat"])
        row["_lon_total"] += float(event["lon"])

    for row in grouped.values():
        event_count = row["event_count"]
        row["avg_risk_score"] = row["_risk_score_total"] / event_count
        row["repeated_detection_ratio"] = row["risk_candidate_count"] / event_count
        row["center_lat"] = row["_lat_total"] / event_count
        row["center_lon"] = row["_lon_total"] / event_count
        row["risk_level"] = _risk_level(
            row["max_risk_score"],
            row["risk_candidate_count"],
        )
        del row["_risk_score_total"]
        del row["_lat_total"]
        del row["_lon_total"]

    return grouped


def compare_segments(before, after) -> list[dict]:
    """Compare before and after segment summaries."""

    before_by_segment = _summary_by_segment(before)
    after_by_segment = _summary_by_segment(after)
    comparison = []

    for segment_id in sorted(set(before_by_segment) | set(after_by_segment)):
        before_row = before_by_segment.get(segment_id)
        after_row = after_by_segment.get(segment_id)
        before_score = _summary_score(before_row)
        after_score = _summary_score(after_row)

        comparison.append(
            {
                "segment_id": segment_id,
                "status": _comparison_status(before_score, after_score),
                "before_score": before_score,
                "after_score": after_score,
                "improvement_rate": _improvement_rate(before_score, after_score),
                "before_event_count": _event_count(before_row),
                "after_event_count": _event_count(after_row),
                "before_risk_level": _risk_level_for_summary(before_row),
                "after_risk_level": _risk_level_for_summary(after_row),
            }
        )

    return comparison


def _event_segment_id(event: Mapping, segment_meters: int) -> str:
    try:
        return segment_id_for(event["lat"], event["lon"], segment_meters=segment_meters)
    except (KeyError, TypeError, ValueError):
        return str(event.get("segment_id", ""))


def _event_risk_score(event: Mapping) -> float:
    prediction = _prediction(event)
    if prediction == "normal":
        return 0.0

    default = DEFAULT_RISK_SCORES.get(prediction, 0.0)
    try:
        raw_score = float(event.get("risk_score", default))
    except (TypeError, ValueError):
        raw_score = default
    return min(1.0, max(0.0, raw_score))


def _prediction(event: Mapping) -> str:
    return str(event.get("prediction", "normal")).lower()


def _gps_valid(event: Mapping) -> bool:
    value = event.get("gps_valid", 1)
    return value not in {0, "0", False, "false", "False"}


def _risk_level(max_risk_score: float, risk_candidate_count: int = 0) -> str:
    if max_risk_score >= 0.70:
        return "danger"
    if risk_candidate_count > 0 or max_risk_score > 0:
        return "caution"
    return "normal"


def _summary_by_segment(summary) -> dict:
    if isinstance(summary, Mapping):
        return dict(summary)
    return {row["segment_id"]: row for row in summary}


def _summary_score(row) -> float | None:
    if row is None:
        return None
    try:
        return float(row.get("max_risk_score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _event_count(row) -> int:
    if row is None:
        return 0
    try:
        return int(row.get("event_count", 0))
    except (TypeError, ValueError):
        return 0


def _risk_level_for_summary(row) -> str | None:
    if row is None:
        return None
    return row.get("risk_level", _risk_level(_summary_score(row) or 0.0))


def _comparison_status(before_score: float | None, after_score: float | None) -> str:
    if before_score is None:
        if after_score is not None and after_score > 0:
            return "new_risk"
        return "not_comparable"
    if after_score is None:
        return "not_comparable"
    if before_score == 0 and after_score == 0:
        return "unchanged_clean"
    if before_score == 0 and after_score > 0:
        return "new_risk"
    if after_score < before_score:
        return "improved"
    if after_score > before_score:
        return "worsened"
    return "not_comparable"


def _improvement_rate(before_score: float | None, after_score: float | None) -> float | None:
    if before_score is None or after_score is None or before_score == 0:
        return None
    return (before_score - after_score) / before_score
