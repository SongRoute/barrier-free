import json
import tempfile
import unittest
from pathlib import Path

from barrier_free import collector, mock_data, model, schema


class CollectorCliTest(unittest.TestCase):
    def test_collector_raw_mode_writes_candidate_session_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            path = collector.run_mock_collection(out, seed=3)

            self.assertTrue((path / "session.json").exists())
            self.assertTrue((path / "raw_imu.csv").exists())
            self.assertTrue((path / "gps.csv").exists())
            self.assertTrue((path / "events.csv").exists())
            self.assertTrue((path / "labels.csv").exists())
            events = list(_read_csv(path / "events.csv"))
            self.assertGreater(len(events), 0)
            self.assertEqual({row["prediction"] for row in events}, {"candidate"})

    def test_collector_inference_mode_uses_model_predictions(self):
        dataset = mock_data.build_demo_dataset(seed=4)
        training_rows = model.training_rows_from_bundle(dataset["before"])
        clf = model.TinyForestClassifier(tree_count=9, seed=4).fit(training_rows)

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            model_path = out / "model.json"
            model_path.write_text(clf.to_json(), encoding="utf-8")

            path = collector.run_mock_collection(out, seed=4, model_path=model_path)

            session = json.loads((path / "session.json").read_text(encoding="utf-8"))
            events = list(_read_csv(path / "events.csv"))
            self.assertEqual(session["model_version"], "tiny-forest-mock")
            self.assertTrue({row["prediction"] for row in events} <= {"caution", "danger"})
            self.assertGreater(len(events), 0)


def _read_csv(path: Path):
    import csv

    with path.open("r", newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


if __name__ == "__main__":
    unittest.main()
