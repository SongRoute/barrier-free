"""MVP CLI."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from . import collector, mock_data, model, schema, segments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="베리어프리 도로 위험 후보 지도 MVP")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="mock Pi 수집 세션을 생성한다")
    demo.add_argument("--out", type=Path, default=Path("demo_sessions"))
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--model", type=Path, default=None)

    web_demo = sub.add_parser("web-demo", help="관리자 지도용 demo_data.json을 생성한다")
    web_demo.add_argument("--out", type=Path, default=Path("web"))
    web_demo.add_argument("--seed", type=int, default=42)

    e2e = sub.add_parser("e2e-demo", help="학습, collector 추론, web export를 모두 실행한다")
    e2e.add_argument("--out", type=Path, default=Path("demo_sessions"))
    e2e.add_argument("--seed", type=int, default=42)

    args = parser.parse_args(argv)
    if args.command == "demo":
        path = collector.run_mock_collection(args.out, seed=args.seed, model_path=args.model)
        print(path)
        return 0
    if args.command == "web-demo":
        path = export_demo(args.out, seed=args.seed)
        print(path)
        return 0
    if args.command == "e2e-demo":
        path = run_end_to_end_demo(args.out, seed=args.seed)
        web_path = _project_root() / "web" / "demo_data.json"
        web_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(path)
        return 0
    raise AssertionError(f"unknown command: {args.command}")


def export_demo(output_dir: Path, seed: int = 42) -> Path:
    """관리자 지도에서 바로 읽을 수 있는 demo_data.json을 생성한다."""

    dataset = mock_data.build_demo_dataset(seed=seed)
    training_rows = model.training_rows_from_bundle(dataset["before"])
    classifier = model.TinyForestClassifier(tree_count=11, seed=seed).fit(training_rows)
    metrics = model.evaluate(classifier, training_rows)

    before_summary = segments.aggregate_events(dataset["before"]["events"], segment_meters=10)
    after_summary = segments.aggregate_events(dataset["after"]["events"], segment_meters=10)
    comparison = segments.compare_segments(before_summary, after_summary)

    payload = {
        "model": {
            "type": "TinyForestClassifier",
            "version": "tiny-forest-mock",
            "training_rows": metrics["training_rows"],
            "recall": metrics["recall"],
            "confusion_matrix": metrics["confusion_matrix"],
        },
        "sessions": [
            _session_payload("before", dataset["before"], before_summary),
            _session_payload("after", dataset["after"], after_summary),
        ],
        "comparison": comparison,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "demo_data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_end_to_end_demo(output_dir: Path, seed: int = 42) -> Path:
    """mock 학습부터 collector inference와 web payload까지 전체 흐름을 실행한다."""

    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = mock_data.build_demo_dataset(seed=seed)
    training_rows = model.training_rows_from_bundle(dataset["before"])
    classifier = model.TinyForestClassifier(tree_count=11, seed=seed).fit(training_rows)
    metrics = model.evaluate(classifier, training_rows)

    model_path = output_dir / "model.json"
    model_path.write_text(classifier.to_json(), encoding="utf-8")

    collector_seed = seed + 1
    collector_path = collector.run_mock_collection(output_dir, seed=collector_seed, model_path=model_path)
    before_bundle = _read_session_folder(collector_path)
    after_bundle = dataset["after"]

    before_summary = segments.aggregate_events(before_bundle["events"], segment_meters=10)
    after_summary = segments.aggregate_events(after_bundle["events"], segment_meters=10)
    comparison = segments.compare_segments(before_summary, after_summary)

    payload = {
        "model": {
            "type": "TinyForestClassifier",
            "version": "tiny-forest-mock",
            "training_rows": metrics["training_rows"],
            "recall": metrics["recall"],
            "confusion_matrix": metrics["confusion_matrix"],
        },
        "collector": {
            "session_id": before_bundle["session"]["session_id"],
            "seed": collector_seed,
            "path": str(collector_path),
        },
        "sessions": [
            _session_payload("before", before_bundle, before_summary),
            _session_payload("after", after_bundle, after_summary),
        ],
        "comparison": comparison,
    }

    path = output_dir / "demo_data.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _session_payload(name: str, bundle: dict, summary: dict) -> dict:
    return {
        "name": name,
        "session": bundle["session"],
        "gps": bundle["gps"],
        "events": bundle["events"],
        "segments": list(summary.values()),
    }


def _read_session_folder(path: Path) -> dict:
    bundle = {
        "session": json.loads((path / "session.json").read_text(encoding="utf-8")),
        "raw_imu": _read_csv(path / "raw_imu.csv"),
        "gps": _read_csv(path / "gps.csv"),
        "events": _read_csv(path / "events.csv"),
        "labels": _read_csv(path / "labels.csv"),
    }
    schema.validate_session_bundle(bundle)
    return bundle


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return [_coerce_row(row) for row in csv.DictReader(f)]


def _coerce_row(row: dict) -> dict:
    result = {}
    for key, value in row.items():
        if value == "":
            result[key] = value
        elif key in {
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
        }:
            result[key] = float(value)
        elif key in {"gps_valid", "non_road_shock", "run_index"}:
            result[key] = int(float(value))
        else:
            result[key] = value
    return result


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    raise SystemExit(main())
