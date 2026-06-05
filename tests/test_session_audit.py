import tempfile
import unittest
from pathlib import Path

from barrier_free import mock_data, schema, session_audit


class SessionAuditTest(unittest.TestCase):
    def test_audit_session_reports_collection_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = mock_data.build_demo_dataset(seed=42)["before"]
            path = schema.write_session_bundle(bundle, Path(tmp) / "session")
            _write_event_photos(path, bundle["events"])

            report = session_audit.audit_session(path)

            self.assertEqual(report["session_id"], "demo_before_run01")
            self.assertEqual(report["phase"], "before")
            self.assertGreater(report["raw_imu_rows"], 0)
            self.assertGreater(report["gps_rows"], 0)
            self.assertGreaterEqual(report["gps_valid_ratio"], 0.8)
            self.assertGreater(report["event_count"], 0)
            self.assertEqual(report["photo_count"], report["expected_photo_count"])
            self.assertEqual(report["missing_photo_count"], 0)
            self.assertTrue(report["ok"])
            self.assertEqual(report["issues"], [])

    def test_audit_session_flags_missing_imu_poor_gps_and_missing_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = mock_data.build_demo_dataset(seed=7)["before"]
            bundle["raw_imu"] = []
            for row in bundle["gps"]:
                row["gps_valid"] = 0
            path = schema.write_session_bundle(bundle, Path(tmp) / "session")

            report = session_audit.audit_session(path)

            self.assertEqual(report["raw_imu_rows"], 0)
            self.assertEqual(report["gps_valid_ratio"], 0.0)
            self.assertGreater(report["event_count"], 0)
            self.assertEqual(report["photo_count"], 0)
            self.assertFalse(report["ok"])
            self.assertIn("raw_imu.csv가 비어 있음", report["issues"])
            self.assertIn("GPS valid 비율이 80% 미만", report["issues"])
            self.assertIn("이벤트가 있지만 사진이 없음", report["issues"])

    def test_audit_session_flags_missing_referenced_photos_even_with_stale_photo(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = mock_data.build_demo_dataset(seed=11)["before"]
            path = schema.write_session_bundle(bundle, Path(tmp) / "session")
            (path / "photos" / "stale.jpg").write_bytes(b"not referenced")

            report = session_audit.audit_session(path)

            self.assertEqual(report["photo_count"], 1)
            self.assertGreater(report["expected_photo_count"], 0)
            self.assertEqual(report["missing_photo_count"], report["expected_photo_count"])
            self.assertFalse(report["ok"])
            self.assertIn("이벤트 사진 파일 누락", report["issues"])


def _write_event_photos(path: Path, events: list[dict]) -> None:
    for event in events:
        for key in ("photo_before", "photo_after"):
            photo = event.get(key)
            if not photo:
                continue
            photo_path = path / photo
            photo_path.parent.mkdir(parents=True, exist_ok=True)
            photo_path.write_bytes(b"fake image")


if __name__ == "__main__":
    unittest.main()
