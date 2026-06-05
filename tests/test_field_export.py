import json
import tempfile
import unittest
from pathlib import Path

from barrier_free import field_export, mock_data, schema


class FieldExportTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
