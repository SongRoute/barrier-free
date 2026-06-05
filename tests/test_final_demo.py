import json
import tempfile
import unittest
from pathlib import Path

from barrier_free import final_demo, risk_scoring, schema


class FinalDemoTest(unittest.TestCase):
    def test_export_final_demo_groups_all_before_after_sessions_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_root = root / "sessions"
            _write_session(sessions_root / "before_001", "before_001", "before", shock_az=2.0)
            _write_session(sessions_root / "before_002", "before_002", "before", shock_az=1.9)
            _write_session(sessions_root / "after_001", "after_001", "after", shock_az=1.1)
            _write_session(sessions_root / "after_002", "after_002", "after", shock_az=1.2)
            _write_session(sessions_root / "calibration_001", "calibration_001", "calibration", shock_az=2.2)

            payload_path = final_demo.export_final_demo(
                sessions_root=sessions_root,
                output_dir=root / "web",
                report_dir=root / "report",
                route_name="obstacle_demo_route",
                thresholds=risk_scoring.RiskThresholds(caution_delta=0.35, danger_delta=0.75, danger_jerk=99.0),
                segment_meters=10,
            )

            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            report = (root / "report" / "final_summary.md").read_text(encoding="utf-8")

            self.assertEqual(payload["source"]["type"], "field-final-demo")
            self.assertEqual(payload["source"]["session_count"], 4)
            self.assertEqual(payload["source"]["skipped_session_count"], 1)
            self.assertEqual(payload["thresholds"]["danger_delta"], 0.75)
            self.assertEqual(len(payload["sessions"]), 4)
            self.assertIn("final_summary", payload)
            self.assertIn("group_comparison", payload)
            self.assertGreater(payload["final_summary"]["before_danger_windows"], payload["final_summary"]["after_danger_windows"])
            self.assertGreater(payload["final_summary"]["danger_reduction_rate"], 0)
            self.assertTrue(any(row["status"] == "improved" for row in payload["comparison"]))
            self.assertIn("소형 바퀴 이동 위험 후보 지도", report)
            self.assertIn("장애물 설치 주행", report)
            self.assertIn("장애물 제거 후 주행", report)

    def test_export_final_demo_thresholds_change_predictions_from_raw_imu(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_root = root / "sessions"
            _write_session(sessions_root / "before_001", "before_001", "before", shock_az=1.6)
            _write_session(sessions_root / "after_001", "after_001", "after", shock_az=1.1)

            strict_path = final_demo.export_final_demo(
                sessions_root=sessions_root,
                output_dir=root / "strict_web",
                report_dir=root / "strict_report",
                route_name="obstacle_demo_route",
                thresholds=risk_scoring.RiskThresholds(caution_delta=0.7, danger_delta=1.1, danger_jerk=99.0),
            )
            sensitive_path = final_demo.export_final_demo(
                sessions_root=sessions_root,
                output_dir=root / "sensitive_web",
                report_dir=root / "sensitive_report",
                route_name="obstacle_demo_route",
                thresholds=risk_scoring.RiskThresholds(caution_delta=0.2, danger_delta=0.5, danger_jerk=99.0),
            )

            strict = json.loads(strict_path.read_text(encoding="utf-8"))
            sensitive = json.loads(sensitive_path.read_text(encoding="utf-8"))

            self.assertLess(
                strict["final_summary"]["before_danger_windows"],
                sensitive["final_summary"]["before_danger_windows"],
            )

    def test_export_final_demo_requires_before_and_after_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_root = root / "sessions"
            _write_session(sessions_root / "before_001", "before_001", "before", shock_az=2.0)

            with self.assertRaisesRegex(ValueError, "before and after"):
                final_demo.export_final_demo(
                    sessions_root=sessions_root,
                    output_dir=root / "web",
                    report_dir=root / "report",
                    route_name="obstacle_demo_route",
                    thresholds=risk_scoring.RiskThresholds(),
                )

    def test_export_final_demo_rejects_invalid_segment_meters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_root = root / "sessions"
            _write_session(sessions_root / "before_001", "before_001", "before", shock_az=2.0)
            _write_session(sessions_root / "after_001", "after_001", "after", shock_az=1.1)

            with self.assertRaisesRegex(ValueError, "segment_meters"):
                final_demo.export_final_demo(
                    sessions_root=sessions_root,
                    output_dir=root / "web",
                    report_dir=root / "report",
                    route_name="obstacle_demo_route",
                    thresholds=risk_scoring.RiskThresholds(),
                    segment_meters=0,
                )


def _write_session(path: Path, session_id: str, phase: str, shock_az: float) -> Path:
    raw_imu = [
        {"timestamp": 1000.0, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        {"timestamp": 1000.5, "ax": 0.0, "ay": 0.0, "az": shock_az, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        {"timestamp": 1001.0, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        {"timestamp": 1001.5, "ax": 0.0, "ay": 0.0, "az": 1.05, "gx": 0.0, "gy": 0.0, "gz": 0.0},
    ]
    gps = [
        {"timestamp": 1000.0, "lat": 36.6256, "lon": 127.4540, "gps_valid": 1, "speed_mps": 2.0},
        {"timestamp": 1001.0, "lat": 36.62561, "lon": 127.45401, "gps_valid": 1, "speed_mps": 2.0},
    ]
    bundle = {
        "session": {
            "session_id": session_id,
            "phase": phase,
            "run_index": 1,
            "started_at": "2026-06-06T00:00:00Z",
            "route_name": "obstacle_demo_route",
            "device": "test",
            "model_version": "none",
            "label_policy_version": "none",
            "notes": "synthetic final demo test",
        },
        "raw_imu": raw_imu,
        "gps": gps,
        "events": [],
        "labels": [],
    }
    return schema.write_session_bundle(bundle, path)


if __name__ == "__main__":
    unittest.main()
