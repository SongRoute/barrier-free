"""MVP CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import collector


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="베리어프리 도로 위험 후보 지도 MVP")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="mock Pi 수집 세션을 생성한다")
    demo.add_argument("--out", type=Path, default=Path("demo_sessions"))
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--model", type=Path, default=None)

    args = parser.parse_args(argv)
    if args.command == "demo":
        path = collector.run_mock_collection(args.out, seed=args.seed, model_path=args.model)
        print(path)
        return 0
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
