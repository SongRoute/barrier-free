import json
import tempfile
import unittest
from pathlib import Path

from barrier_free import cli


class EndToEndTest(unittest.TestCase):
    def test_end_to_end_demo_pipeline_uses_model_and_collector(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            demo_json = cli.run_end_to_end_demo(out, seed=42)
            payload = json.loads(demo_json.read_text(encoding="utf-8"))

            self.assertEqual(len(payload["sessions"]), 2)
            self.assertEqual(payload["collector"]["session_id"], "mock_collection_run01")
            self.assertGreater(payload["model"]["training_rows"], 0)
            before_events = payload["sessions"][0]["events"]
            self.assertGreater(len(before_events), 0)
            self.assertTrue({event["prediction"] for event in before_events} <= {"caution", "danger"})
            self.assertTrue(
                any(
                    row["status"] in {"improved", "worsened", "new_risk", "not_comparable"}
                    for row in payload["comparison"]
                )
            )
            self.assertTrue((out / "model.json").exists())
            self.assertTrue((out / "mock_collection_run01" / "events.csv").exists())


if __name__ == "__main__":
    unittest.main()
