"""MVP CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import collector, mock_data, model, segments


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

    args = parser.parse_args(argv)
    if args.command == "demo":
        path = collector.run_mock_collection(args.out, seed=args.seed, model_path=args.model)
        print(path)
        return 0
    if args.command == "web-demo":
        path = export_demo(args.out, seed=args.seed)
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


def _session_payload(name: str, bundle: dict, summary: dict) -> dict:
    return {
        "name": name,
        "session": bundle["session"],
        "gps": bundle["gps"],
        "events": bundle["events"],
        "segments": list(summary.values()),
    }


if __name__ == "__main__":
    raise SystemExit(main())
