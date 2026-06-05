import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from barrier_free import cli, schema


class PiCliTest(unittest.TestCase):
    def test_cli_help_lists_pi_commands(self):
        output = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stdout(output):
                cli.main(["--help"])

        text = output.getvalue()
        self.assertIn("check-imu", text)
        self.assertIn("check-gps", text)
        self.assertIn("check-camera", text)
        self.assertIn("collect", text)
        self.assertIn("compare-sessions", text)
        self.assertIn("audit-session", text)
        self.assertIn("preview-session", text)
        self.assertIn("preview-sessions", text)
        self.assertIn("serve-session", text)
        self.assertIn("serve-sessions", text)
        self.assertIn("final-demo", text)

    def test_collect_help_lists_no_camera_option(self):
        output = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stdout(output):
                cli.main(["collect", "--help"])

        self.assertIn("--no-camera", output.getvalue())

    def test_final_demo_cli_writes_web_payload_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_root = root / "sessions"
            _write_cli_session(sessions_root / "before_001", "before_001", "before", shock_az=2.0)
            _write_cli_session(sessions_root / "after_001", "after_001", "after", shock_az=1.1)

            exit_code = cli.main(
                [
                    "final-demo",
                    str(sessions_root),
                    "--out",
                    str(root / "web"),
                    "--report-out",
                    str(root / "report"),
                    "--route-name",
                    "obstacle_demo_route",
                    "--caution-threshold",
                    "0.35",
                    "--danger-threshold",
                    "0.75",
                    "--danger-jerk",
                    "99",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "web" / "demo_data.json").exists())
            self.assertTrue((root / "report" / "final_summary.md").exists())


def _write_cli_session(path: Path, session_id: str, phase: str, shock_az: float) -> Path:
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
            "notes": "cli final demo test",
        },
        "raw_imu": [
            {"timestamp": 1000.0, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
            {"timestamp": 1000.5, "ax": 0.0, "ay": 0.0, "az": shock_az, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        ],
        "gps": [
            {"timestamp": 1000.0, "lat": 36.6256, "lon": 127.4540, "gps_valid": 1, "speed_mps": 2.0},
        ],
        "events": [],
        "labels": [],
    }
    return schema.write_session_bundle(bundle, path)


if __name__ == "__main__":
    unittest.main()
