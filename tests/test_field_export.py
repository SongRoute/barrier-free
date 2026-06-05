import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from barrier_free import field_export, mock_data, schema


class FieldExportTest(unittest.TestCase):
    def test_export_session_preview_reads_single_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = mock_data.build_demo_dataset(seed=42)
            session_path = schema.write_session_bundle(dataset["before"], root / "before")

            payload_path = field_export.export_session_preview(
                session_path=session_path,
                output_dir=root / "web",
                segment_meters=10,
            )

            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            self.assertEqual(payload_path.name, "demo_data.json")
            self.assertEqual(payload["source"]["type"], "field-session-preview")
            self.assertEqual(payload["source"]["segment_meters"], 10)
            self.assertGreater(payload["source"]["coverage_count"], 0)
            self.assertEqual([session["name"] for session in payload["sessions"]], ["preview"])
            self.assertGreater(len(payload["sessions"][0]["segments"]), 0)
            self.assertGreater(len(payload["sessions"][0]["imu_windows"]), 0)
            imu_window = payload["sessions"][0]["imu_windows"][0]
            self.assertIn("accel_delta_max", imu_window)
            self.assertIn("accel_mag_max", imu_window)
            self.assertIn("lat", imu_window)
            self.assertIn("lon", imu_window)
            self.assertEqual(payload["comparison"], [])

    def test_export_session_index_reads_multiple_session_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = mock_data.build_demo_dataset(seed=42)
            before_path = schema.write_session_bundle(dataset["before"], root / "sessions" / "before")
            after_path = schema.write_session_bundle(dataset["after"], root / "sessions" / "after")
            (root / "sessions" / "notes.txt").write_text("ignore me", encoding="utf-8")

            payload_path = field_export.export_session_index(
                sessions_root=root / "sessions",
                output_dir=root / "web",
                segment_meters=10,
            )

            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source"]["type"], "field-session-index")
            self.assertEqual(payload["source"]["session_count"], 2)
            self.assertEqual(payload["source"]["session_paths"], [str(after_path), str(before_path)])
            self.assertEqual(
                [session["session"]["session_id"] for session in payload["sessions"]],
                ["demo_after_run01", "demo_before_run01"],
            )
            self.assertEqual(payload["comparison"], [])
            self.assertGreater(len(payload["sessions"][0]["imu_windows"]), 0)

    def test_imu_window_payloads_do_not_rescan_all_gps_rows_per_window(self):
        gps_rows = CountingRows(
            [
                {
                    "timestamp": float(index) * 0.1,
                    "lat": 36.0 + index * 0.00001,
                    "lon": 127.0,
                    "gps_valid": 1,
                    "speed_mps": 2.0,
                }
                for index in range(1000)
            ]
        )
        raw_imu = [
            {
                "timestamp": float(index) * 0.5,
                "ax": 0.0,
                "ay": 0.0,
                "az": 1.0 + (0.1 if index % 4 == 0 else 0.0),
                "gx": 0.0,
                "gy": 0.0,
                "gz": 0.0,
            }
            for index in range(20)
        ]

        windows = field_export.imu_window_payloads({"raw_imu": raw_imu, "gps": gps_rows})

        self.assertEqual(len(windows), 10)
        self.assertLess(gps_rows.iteration_count, 3000)

    def test_export_session_comparison_reads_before_after_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = mock_data.build_demo_dataset(seed=42)
            before_path = schema.write_session_bundle(dataset["before"], root / "before")
            after_path = schema.write_session_bundle(dataset["after"], root / "after")

            payload_path = field_export.export_session_comparison(
                before_path=before_path,
                after_path=after_path,
                output_dir=root / "web",
                segment_meters=10,
            )

            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            self.assertEqual(payload_path.name, "demo_data.json")
            self.assertEqual([session["name"] for session in payload["sessions"]], ["before", "after"])
            self.assertIn("comparison", payload)
            self.assertTrue(any(row["status"] == "improved" for row in payload["comparison"]))
            self.assertEqual(payload["source"]["type"], "field-session-comparison")
            self.assertEqual(payload["source"]["segment_meters"], 10)
            self.assertGreater(payload["source"]["before_coverage_count"], 0)
            self.assertGreater(payload["source"]["after_coverage_count"], 0)

    def test_export_session_comparison_rejects_swapped_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = mock_data.build_demo_dataset(seed=42)
            before_path = schema.write_session_bundle(dataset["after"], root / "wrong_before")
            after_path = schema.write_session_bundle(dataset["before"], root / "wrong_after")

            with self.assertRaisesRegex(ValueError, "before session phase must be before"):
                field_export.export_session_comparison(
                    before_path=before_path,
                    after_path=after_path,
                    output_dir=root / "web",
                )

    def test_export_session_comparison_rejects_route_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = mock_data.build_demo_dataset(seed=42)
            after = deepcopy(dataset["after"])
            after["session"]["route_name"] = "different_route"
            before_path = schema.write_session_bundle(dataset["before"], root / "before")
            after_path = schema.write_session_bundle(after, root / "after")

            with self.assertRaisesRegex(ValueError, "route_name must match"):
                field_export.export_session_comparison(
                    before_path=before_path,
                    after_path=after_path,
                    output_dir=root / "web",
                )

class CountingRows(list):
    def __init__(self, rows):
        super().__init__(rows)
        self.iteration_count = 0

    def __iter__(self):
        for row in super().__iter__():
            self.iteration_count += 1
            yield row


if __name__ == "__main__":
    unittest.main()
