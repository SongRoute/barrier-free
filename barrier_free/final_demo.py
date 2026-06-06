"""최종 시연용 누적 세션 분석과 리포트 생성."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from . import field_export, risk_scoring, segments


THRESHOLD_VERSION = "threshold-v1"


def export_final_demo(
    *,
    sessions_root: Path,
    output_dir: Path,
    report_dir: Path,
    route_name: str | None,
    thresholds: risk_scoring.RiskThresholds,
    segment_meters: int = 10,
    include_synthetic: bool = False,
) -> Path:
    """누적 세션을 before/after 그룹으로 분석해 web payload와 Markdown 리포트를 저장한다."""

    if segment_meters <= 0:
        raise ValueError("segment_meters must be positive")

    all_paths = field_export.discover_session_paths(sessions_root)
    selected_records = []
    skipped_records = []
    for path in all_paths:
        bundle = field_export.read_session_folder(path)
        session = bundle["session"]
        if route_name is not None and session["route_name"] != route_name:
            skipped_records.append({"path": str(path), "reason": "route_name mismatch", "session": session})
            continue
        if session["phase"] not in {"before", "after"}:
            skipped_records.append({"path": str(path), "reason": "phase is not before/after", "session": session})
            continue
        if _is_synthetic_session(session) and not include_synthetic:
            skipped_records.append({"path": str(path), "reason": "synthetic after excluded", "session": session})
            continue

        scored_windows = _scored_windows_with_context(bundle, thresholds, segment_meters=segment_meters)
        events = risk_scoring.event_rows_from_scored_windows(
            scored_windows,
            session_id=session["session_id"],
            model_version=THRESHOLD_VERSION,
        )
        coverage = segments.route_coverage_segments(bundle["gps"], segment_meters=segment_meters)
        selected_records.append(
            {
                "path": path,
                "bundle": bundle,
                "scored_windows": scored_windows,
                "events": events,
                "coverage": coverage,
            }
        )

    before_records = [record for record in selected_records if record["bundle"]["session"]["phase"] == "before"]
    after_records = [record for record in selected_records if record["bundle"]["session"]["phase"] == "after"]
    if not before_records or not after_records:
        raise ValueError("final-demo requires at least one before and after session for the selected route")
    before_events = _all_events(before_records)
    after_events = _all_events(after_records)
    before_summary = segments.aggregate_events(before_events, segment_meters=segment_meters)
    after_summary = segments.aggregate_events(after_events, segment_meters=segment_meters)
    before_coverage = _coverage_union(before_records)
    after_coverage = _coverage_union(after_records)
    comparison = segments.compare_segments(
        before_summary,
        after_summary,
        before_coverage=before_coverage,
        after_coverage=after_coverage,
    )
    comparison = _enrich_comparison(comparison, before_records, after_records, segment_meters=segment_meters)
    synthetic_session_count = sum(1 for record in selected_records if _is_synthetic_session(record["bundle"]["session"]))
    final_summary = _final_summary(
        selected_records,
        before_records,
        after_records,
        comparison,
        route_name,
        synthetic_session_count=synthetic_session_count,
    )

    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "final_summary.md"
    report_path.write_text(
        _markdown_report(final_summary, thresholds, selected_records, skipped_records),
        encoding="utf-8",
    )

    payload = {
        "source": {
            "type": "field-final-demo",
            "sessions_root": str(sessions_root),
            "route_name": route_name,
            "session_count": len(selected_records),
            "skipped_session_count": len(skipped_records),
            "segment_meters": segment_meters,
            "window_seconds": 1.0,
            "report_path": str(report_path),
            "synthetic_session_count": synthetic_session_count,
            "include_synthetic": include_synthetic,
        },
        "thresholds": {
            "version": THRESHOLD_VERSION,
            **thresholds.to_dict(),
            "segment_meters": segment_meters,
        },
        "model": {
            "type": "imu-threshold",
            "version": THRESHOLD_VERSION,
            "training_rows": 0,
            "recall": None,
            "confusion_matrix": {},
        },
        "final_summary": final_summary,
        "presentation": {
            "default_view": "comparison" if comparison else "session",
            "headline": _headline(final_summary),
            "summary_metrics": final_summary,
        },
        "sessions": [_session_payload(record, segment_meters=segment_meters) for record in selected_records],
        "comparison": comparison,
        "group_comparison": _group_comparison(final_summary, comparison),
        "skipped_sessions": [
            {
                "session_id": record["session"]["session_id"],
                "phase": record["session"]["phase"],
                "route_name": record["session"]["route_name"],
                "reason": record["reason"],
            }
            for record in skipped_records
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "demo_data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _scored_windows_with_context(bundle: dict, thresholds: risk_scoring.RiskThresholds, *, segment_meters: int) -> list[dict]:
    session = bundle["session"]
    rows = []
    for row in risk_scoring.score_session_windows(bundle, thresholds):
        segment_id = ""
        if row["gps_valid"]:
            try:
                segment_id = segments.segment_id_for(row["lat"], row["lon"], segment_meters=segment_meters)
            except (TypeError, ValueError):
                segment_id = ""
        rows.append(
            {
                **row,
                "segment_id": segment_id,
                "source_session_id": session["session_id"],
                "phase": session["phase"],
                "route_name": session["route_name"],
                "threshold_version": THRESHOLD_VERSION,
            }
        )
    return rows


def _session_payload(record: dict, *, segment_meters: int) -> dict:
    bundle = record["bundle"]
    session = bundle["session"]
    summary = segments.aggregate_events(record["events"], segment_meters=segment_meters)
    return {
        "name": f"{session['route_name']}:{session['phase']}:{session['session_id']}",
        "kind": "field-session",
        "session": session,
        "gps": bundle["gps"],
        "events": record["events"],
        "segments": list(summary.values()),
        "imu_windows": record["scored_windows"],
        "metrics": _session_metrics(bundle, record),
    }


def _session_metrics(bundle: dict, record: dict) -> dict:
    gps_rows = bundle["gps"]
    valid_gps = sum(1 for row in gps_rows if int(row.get("gps_valid", 0)) == 1)
    windows = record["scored_windows"]
    counts = Counter(row["prediction"] for row in windows)
    return {
        "gps_valid_ratio": valid_gps / len(gps_rows) if gps_rows else 0.0,
        "imu_window_count": len(windows),
        "normal_window_count": counts.get("normal", 0),
        "caution_window_count": counts.get("caution", 0),
        "danger_window_count": counts.get("danger", 0),
        "risk_window_count": counts.get("caution", 0) + counts.get("danger", 0),
        "event_count": len(record["events"]),
        "coverage_count": len(record["coverage"]),
        "peak_accel_delta": max((float(row["accel_delta_max"]) for row in windows), default=0.0),
        "peak_jerk": max((float(row["jerk_max"]) for row in windows), default=0.0),
    }


def _final_summary(
    selected_records: list[dict],
    before_records: list[dict],
    after_records: list[dict],
    comparison: list[dict],
    route_name: str | None,
    *,
    synthetic_session_count: int,
) -> dict:
    counts = Counter(row["status"] for row in comparison)
    before_danger = _window_count(before_records, "danger")
    after_danger = _window_count(after_records, "danger")
    before_risk = _risk_window_count(before_records)
    after_risk = _risk_window_count(after_records)
    return {
        "route_name": route_name or _route_name_from_records(selected_records),
        "session_count": len(selected_records),
        "synthetic_session_count": synthetic_session_count,
        "before_session_count": len(before_records),
        "after_session_count": len(after_records),
        "before_danger_windows": before_danger,
        "after_danger_windows": after_danger,
        "before_risk_windows": before_risk,
        "after_risk_windows": after_risk,
        "danger_reduction_rate": _reduction_rate(before_danger, after_danger),
        "risk_reduction_rate": _reduction_rate(before_risk, after_risk),
        "improved_segment_count": counts.get("improved", 0),
        "worsened_segment_count": counts.get("worsened", 0),
        "new_risk_segment_count": counts.get("new_risk", 0),
        "not_comparable_segment_count": counts.get("not_comparable", 0),
    }


def _enrich_comparison(
    comparison: list[dict],
    before_records: list[dict],
    after_records: list[dict],
    *,
    segment_meters: int,
) -> list[dict]:
    before_detected = _detected_session_counts(before_records, segment_meters=segment_meters)
    after_detected = _detected_session_counts(after_records, segment_meters=segment_meters)
    before_covered = _covered_session_counts(before_records)
    after_covered = _covered_session_counts(after_records)
    enriched = []
    for row in comparison:
        segment_id = row["segment_id"]
        before_coverage_count = before_covered.get(segment_id, 0)
        after_coverage_count = after_covered.get(segment_id, 0)
        before_detected_count = before_detected.get(segment_id, 0)
        after_detected_count = after_detected.get(segment_id, 0)
        enriched.append(
            {
                **row,
                "before_detected_session_count": before_detected_count,
                "after_detected_session_count": after_detected_count,
                "before_coverage_session_count": before_coverage_count,
                "after_coverage_session_count": after_coverage_count,
                "before_detection_rate": before_detected_count / before_coverage_count if before_coverage_count else 0.0,
                "after_detection_rate": after_detected_count / after_coverage_count if after_coverage_count else 0.0,
            }
        )
    return enriched


def _detected_session_counts(records: list[dict], *, segment_meters: int) -> dict:
    counts = defaultdict(set)
    for record in records:
        session_id = record["bundle"]["session"]["session_id"]
        for event in record["events"]:
            try:
                segment_id = segments.segment_id_for(event["lat"], event["lon"], segment_meters=segment_meters)
            except (TypeError, ValueError):
                continue
            counts[segment_id].add(session_id)
    return {segment_id: len(session_ids) for segment_id, session_ids in counts.items()}


def _covered_session_counts(records: list[dict]) -> dict:
    counts = defaultdict(set)
    for record in records:
        session_id = record["bundle"]["session"]["session_id"]
        for segment_id in record["coverage"]:
            counts[segment_id].add(session_id)
    return {segment_id: len(session_ids) for segment_id, session_ids in counts.items()}


def _markdown_report(
    final_summary: dict,
    thresholds: risk_scoring.RiskThresholds,
    selected_records: list[dict],
    skipped_records: list[dict],
) -> str:
    danger_reduction = _percent(final_summary["danger_reduction_rate"])
    risk_reduction = _percent(final_summary["risk_reduction_rate"])
    lines = [
        "# 소형 바퀴 이동 위험 후보 지도 최종 요약",
        "",
    ]
    if final_summary["synthetic_session_count"] > 0:
        lines.extend(
            [
                "## synthetic after 경고",
                "",
                "- 이 리포트에는 실제 after 수집 전 파이프라인 검증용 synthetic after 세션이 포함되어 있습니다.",
                "- 실제 실험 결과로 주장하지 말고, 소프트웨어 동작 확인 및 발표 화면 점검용으로만 사용하세요.",
                "",
            ]
        )
    lines.extend(
        [
        "## 한 줄 결론",
        "",
        f"장애물 설치 주행 대비 장애물 제거 후 주행에서 danger window 감소율은 {danger_reduction}, 전체 위험 window 감소율은 {risk_reduction}입니다.",
        "",
        "## 실험 해석",
        "",
        "- 이 결과는 휠체어 안전을 확정 판정하는 것이 아니라, 관리자가 점검할 위험 후보 구간을 빠르게 찾기 위한 MVP 결과입니다.",
        "- 같은 짧은 경로를 장애물 설치 주행(before)과 장애물 제거 후 주행(after)으로 반복해 IMU 충격 강도 변화를 비교합니다.",
        "- GPS 오차는 10 m 내외 구간 집계와 before/after coverage 비교로 완화합니다.",
        "",
        "## 핵심 지표",
        "",
        f"- 사용 세션 수: {final_summary['session_count']}",
        f"- synthetic 세션 수: {final_summary['synthetic_session_count']}",
        f"- before 세션 수: {final_summary['before_session_count']}",
        f"- after 세션 수: {final_summary['after_session_count']}",
        f"- before danger window: {final_summary['before_danger_windows']}",
        f"- after danger window: {final_summary['after_danger_windows']}",
        f"- 개선 구간 수: {final_summary['improved_segment_count']}",
        f"- 악화 구간 수: {final_summary['worsened_segment_count']}",
        f"- 비교 불가 구간 수: {final_summary['not_comparable_segment_count']}",
        "",
        "## 적용 임계값",
        "",
        f"- caution delta: {thresholds.caution_delta}",
        f"- danger delta: {thresholds.danger_delta}",
        f"- danger jerk: {thresholds.danger_jerk}",
        "",
        "## 사용한 세션",
        "",
        ]
    )
    for record in selected_records:
        session = record["bundle"]["session"]
        lines.append(f"- {session['session_id']} ({session['phase']}, route={session['route_name']})")
    if skipped_records:
        lines.extend(["", "## 제외된 세션", ""])
        for record in skipped_records:
            session = record["session"]
            lines.append(f"- {session['session_id']} ({record['reason']})")
    lines.extend(
        [
            "",
            "## 한계와 다음 단계",
            "",
            "- 임계값은 현장 데이터 분포를 보며 조정해야 합니다.",
            "- 더 많은 라벨 데이터가 쌓이면 threshold 방식에서 LightGBM 등 지도학습 모델로 확장할 수 있습니다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _group_comparison(final_summary: dict, comparison: list[dict]) -> list[dict]:
    return [
        {
            "route_name": final_summary["route_name"],
            "before_session_count": final_summary["before_session_count"],
            "after_session_count": final_summary["after_session_count"],
            "improved_segment_count": final_summary["improved_segment_count"],
            "worsened_segment_count": final_summary["worsened_segment_count"],
            "new_risk_segment_count": final_summary["new_risk_segment_count"],
            "not_comparable_segment_count": final_summary["not_comparable_segment_count"],
            "comparison_count": len(comparison),
        }
    ]


def _all_events(records: list[dict]) -> list[dict]:
    events = []
    for record in records:
        events.extend(record["events"])
    return events


def _coverage_union(records: list[dict]) -> set[str]:
    coverage = set()
    for record in records:
        coverage.update(record["coverage"])
    return coverage


def _window_count(records: list[dict], prediction: str) -> int:
    return sum(1 for record in records for row in record["scored_windows"] if row["prediction"] == prediction)


def _risk_window_count(records: list[dict]) -> int:
    return sum(1 for record in records for row in record["scored_windows"] if row["prediction"] in {"caution", "danger"})


def _reduction_rate(before_count: int, after_count: int) -> float:
    if before_count <= 0:
        return 0.0
    return max(0.0, (before_count - after_count) / before_count)


def _route_name_from_records(records: list[dict]) -> str:
    route_names = sorted({record["bundle"]["session"]["route_name"] for record in records})
    return route_names[0] if len(route_names) == 1 else "mixed"


def _headline(final_summary: dict) -> str:
    return (
        "장애물 제거 후 danger window "
        f"{final_summary['before_danger_windows']}개 → {final_summary['after_danger_windows']}개"
    )


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _is_synthetic_session(session: dict) -> bool:
    return (
        bool(session.get("synthetic_after"))
        or str(session.get("model_version", "")) == "synthetic-after"
        or str(session.get("session_id", "")).startswith("after_mock_")
    )
