"""MVP CLI."""

from __future__ import annotations

import argparse
import csv
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import collector, field_export, mock_data, model, schema, segments, session_audit


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

    check_imu = sub.add_parser("check-imu", help="MPU6050 연결과 샘플 값을 확인한다")
    check_imu.add_argument("--bus", type=int, default=1)

    check_gps = sub.add_parser("check-gps", help="NEO-M8N GPS 연결과 RMC 값을 확인한다")
    check_gps.add_argument("--port", default="/dev/serial0")
    check_gps.add_argument("--baudrate", type=int, default=9600)

    check_camera = sub.add_parser("check-camera", help="USB 웹캠 캡처를 확인한다")
    check_camera.add_argument("--device", default="/dev/video0")
    check_camera.add_argument("--out", type=Path, default=Path("camera_check"))

    collect = sub.add_parser("collect", help="실제 센서로 주행 세션을 수집한다")
    collect.add_argument("--out", type=Path, default=Path("sessions"))
    collect.add_argument("--duration", type=float, default=60.0)
    collect.add_argument("--rate", type=float, default=20.0)
    collect.add_argument("--model", type=Path, default=None)
    collect.add_argument("--phase", choices=["calibration", "before", "after", "demo"], default="demo")
    collect.add_argument("--session-id", default=None)
    collect.add_argument("--route-name", default="pi_field_collection")
    collect.add_argument("--run-index", type=int, default=1)
    collect.add_argument("--gps-port", default="/dev/serial0")
    collect.add_argument("--gps-baudrate", type=int, default=9600)
    collect.add_argument("--camera-device", default="/dev/video0")

    compare = sub.add_parser("compare-sessions", help="실제 before/after 세션을 web demo_data.json으로 변환한다")
    compare.add_argument("--before", type=Path, required=True)
    compare.add_argument("--after", type=Path, required=True)
    compare.add_argument("--out", type=Path, default=Path("web"))
    compare.add_argument("--segment-meters", type=int, default=10)

    audit = sub.add_parser("audit-session", help="수집 세션의 IMU/GPS/이벤트/사진 품질을 요약한다")
    audit.add_argument("path", type=Path)

    preview = sub.add_parser("preview-session", help="단일 수집 세션을 지도 확인용 demo_data.json으로 변환한다")
    preview.add_argument("path", type=Path)
    preview.add_argument("--out", type=Path, default=Path("web"))
    preview.add_argument("--segment-meters", type=int, default=10)

    serve = sub.add_parser("serve-session", help="단일 수집 세션을 지도 확인용으로 변환하고 웹 서버를 실행한다")
    serve.add_argument("path", type=Path)
    serve.add_argument("--out", type=Path, default=Path("web"))
    serve.add_argument("--segment-meters", type=int, default=10)
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)

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
    if args.command == "check-imu":
        print(json.dumps(_check_imu(args.bus), ensure_ascii=False, indent=2))
        return 0
    if args.command == "check-gps":
        print(json.dumps(_check_gps(args.port, args.baudrate), ensure_ascii=False, indent=2))
        return 0
    if args.command == "check-camera":
        print(json.dumps(_check_camera(args.device, args.out), ensure_ascii=False, indent=2))
        return 0
    if args.command == "collect":
        path = _collect_from_hardware(args)
        print(path)
        return 0
    if args.command == "compare-sessions":
        path = field_export.export_session_comparison(
            before_path=args.before,
            after_path=args.after,
            output_dir=args.out,
            segment_meters=args.segment_meters,
        )
        print(path)
        return 0
    if args.command == "audit-session":
        print(json.dumps(session_audit.audit_session(args.path), ensure_ascii=False, indent=2))
        return 0
    if args.command == "preview-session":
        path = field_export.export_session_preview(
            session_path=args.path,
            output_dir=args.out,
            segment_meters=args.segment_meters,
        )
        print(path)
        print(json.dumps(session_audit.audit_session(args.path), ensure_ascii=False, indent=2))
        return 0
    if args.command == "serve-session":
        return _serve_session_preview(args)
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


def _check_imu(bus_number: int) -> dict:
    from .hardware.imu_mpu6050 import MPU6050Reader

    return MPU6050Reader(bus_number=bus_number).health_check()


def _check_gps(port: str, baudrate: int) -> dict:
    from .hardware.gps_neo_m8n import NEOM8NReader

    return NEOM8NReader(port=port, baudrate=baudrate).health_check()


def _check_camera(device: str, output_dir: Path) -> dict:
    from .hardware.camera_usb import USBCamera

    return USBCamera(device=device).health_check(output_dir)


def _collect_from_hardware(args) -> Path:
    from .hardware.camera_usb import USBCamera
    from .hardware.gps_neo_m8n import NEOM8NReader
    from .hardware.imu_mpu6050 import MPU6050Reader

    return collector.run_sensor_collection(
        args.out,
        imu_reader=MPU6050Reader(),
        gps_reader=NEOM8NReader(port=args.gps_port, baudrate=args.gps_baudrate),
        camera=USBCamera(device=args.camera_device),
        duration_seconds=args.duration,
        sample_rate_hz=args.rate,
        model_path=args.model,
        session_id=args.session_id,
        phase=args.phase,
        route_name=args.route_name,
        run_index=args.run_index,
    )


def _serve_session_preview(args) -> int:
    path = field_export.export_session_preview(
        session_path=args.path,
        output_dir=args.out,
        segment_meters=args.segment_meters,
    )
    audit = session_audit.audit_session(args.path)
    display_host = "localhost" if args.host in {"0.0.0.0", "::"} else args.host
    print(
        json.dumps(
            {
                "payload": str(path),
                "url": f"http://{display_host}:{args.port}/web/",
                "pi_url_hint": f"http://<raspberry-pi-ip>:{args.port}/web/",
                "audit": audit,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(_project_root()))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
