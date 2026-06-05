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
            self.assertEqual(payload["comparison"], [])

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


if __name__ == "__main__":
    unittest.main()
