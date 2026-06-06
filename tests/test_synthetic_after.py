import tempfile
import unittest
from pathlib import Path

from barrier_free import field_export, schema, synthetic_after


class SyntheticAfterTest(unittest.TestCase):
    def test_generate_mock_after_sessions_from_matching_before_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions_root = root / "sessions"
            before_path = _write_before_session(sessions_root / "before_001", "before_001", route_name="campus_test_route")
            _write_before_session(sessions_root / "other_route_before", "other_route_before", route_name="other_route")

            generated = synthetic_after.generate_mock_after_sessions(
                sessions_root=sessions_root,
                route_name="campus_test_route",
                improvement_factor=0.25,
            )

            self.assertEqual([path.name for path in generated], ["after_mock_before_001"])
            before = field_export.read_session_folder(before_path)
            after = field_export.read_session_folder(generated[0])
            self.assertEqual(after["session"]["phase"], "after")
            self.assertEqual(after["session"]["route_name"], "campus_test_route")
            self.assertEqual(after["session"]["source_session_id"], "before_001")
            self.assertTrue(after["session"]["synthetic_after"])
            self.assertEqual(after["session"]["model_version"], "synthetic-after")
            self.assertIn("synthetic after", after["session"]["notes"])
            self.assertLess(_max_z_delta(after["raw_imu"]), _max_z_delta(before["raw_imu"]))

    def test_generate_mock_after_rejects_invalid_improvement_factor(self):
        with self.assertRaisesRegex(ValueError, "improvement_factor"):
            synthetic_after.generate_mock_after_sessions(
                sessions_root=Path("sessions"),
                route_name="campus_test_route",
                improvement_factor=1.5,
            )


def _write_before_session(path: Path, session_id: str, route_name: str) -> Path:
    bundle = {
        "session": {
            "session_id": session_id,
            "phase": "before",
            "run_index": 1,
            "started_at": "2026-06-06T00:00:00Z",
            "route_name": route_name,
            "device": "test",
            "model_version": "none",
            "label_policy_version": "none",
            "notes": "synthetic after source",
        },
        "raw_imu": [
            {"timestamp": 1000.0, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
            {"timestamp": 1000.5, "ax": 0.0, "ay": 0.0, "az": 2.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
        ],
        "gps": [{"timestamp": 1000.0, "lat": 36.6256, "lon": 127.454, "gps_valid": 1, "speed_mps": 2.0}],
        "events": [],
        "labels": [],
    }
    return schema.write_session_bundle(bundle, path)


def _max_z_delta(rows: list[dict]) -> float:
    return max(abs(float(row["az"]) - 1.0) for row in rows)


if __name__ == "__main__":
    unittest.main()
