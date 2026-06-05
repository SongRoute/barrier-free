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

    def test_sensor_collection_writes_real_session_contract_with_camera_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            imu = FakeIMU()
            gps = FakeGPS()
            camera = FakeCamera()

            path = collector.run_sensor_collection(
                out,
                imu_reader=imu,
                gps_reader=gps,
                camera=camera,
                duration_seconds=1.0,
                sample_rate_hz=5,
            )

            self.assertTrue((path / "session.json").exists())
            self.assertTrue((path / "raw_imu.csv").exists())
            self.assertTrue((path / "gps.csv").exists())
            events = list(_read_csv(path / "events.csv"))
            self.assertGreater(len(events), 0)
            self.assertEqual({row["prediction"] for row in events}, {"candidate"})
            self.assertTrue((path / events[0]["photo_before"]).exists())

    def test_sensor_collection_accepts_field_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            path = collector.run_sensor_collection(
                out,
                imu_reader=FakeIMU(),
                gps_reader=FakeGPS(),
                duration_seconds=1.0,
                sample_rate_hz=2.0,
                session_id="before_short_test",
                phase="before",
                route_name="campus_test_route",
                run_index=2,
                sleeper=None,
                clock=FakeClock(),
            )

            session = json.loads((path / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(session["session_id"], "before_short_test")
            self.assertEqual(session["phase"], "before")
            self.assertEqual(session["route_name"], "campus_test_route")
            self.assertEqual(session["run_index"], 2)

    def test_sensor_collection_without_camera_leaves_photo_references_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = collector.run_sensor_collection(
                Path(tmp),
                imu_reader=FakeIMU(),
                gps_reader=FakeGPS(),
                camera=None,
                duration_seconds=1.0,
                sample_rate_hz=5,
                sleeper=None,
            )

            events = list(_read_csv(path / "events.csv"))
            self.assertGreater(len(events), 0)
            self.assertEqual({row["photo_before"] for row in events}, {""})
            self.assertEqual({row["photo_after"] for row in events}, {""})

    def test_sensor_collection_flushes_raw_files_during_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            session_id = "streaming_checkpoint_test"
            expected_path = out / session_id
            imu = InspectingIMU(expected_path)

            collector.run_sensor_collection(
                out,
                imu_reader=imu,
                gps_reader=FakeGPS(),
                camera=None,
                duration_seconds=2.0,
                sample_rate_hz=5,
                session_id=session_id,
                sleeper=None,
            )

            self.assertTrue(imu.saw_incremental_files)

    def test_sensor_collection_returns_partial_session_on_keyboard_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = collector.run_sensor_collection(
                Path(tmp),
                imu_reader=FakeIMU(),
                gps_reader=FakeGPS(),
                camera=None,
                duration_seconds=5.0,
                sample_rate_hz=5,
                session_id="partial_interrupt_test",
                sleeper=InterruptingSleeper(raise_on_call=4),
            )

            self.assertTrue((path / "session.json").exists())
            self.assertGreaterEqual(len(list(_read_csv(path / "raw_imu.csv"))), 4)
            self.assertGreaterEqual(len(list(_read_csv(path / "gps.csv"))), 4)
            self.assertTrue((path / "events.csv").exists())


def _read_csv(path: Path):
    import csv

    with path.open("r", newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


class FakeIMU:
    def __init__(self):
        self.index = 0

    def read_sample(self, timestamp=None):
        self.index += 1
        shock = 2.4 if self.index in {2, 3} else 0.0
        return {
            "timestamp": 1000.0 + self.index * 0.2 if timestamp is None else timestamp,
            "ax": shock,
            "ay": 0.0,
            "az": 1.0 + shock,
            "gx": 0.0,
            "gy": 0.0,
            "gz": 0.0,
        }


class InspectingIMU(FakeIMU):
    def __init__(self, session_path: Path):
        super().__init__()
        self.session_path = session_path
        self.saw_incremental_files = False

    def read_sample(self, timestamp=None):
        if self.index >= 1:
            raw_path = self.session_path / "raw_imu.csv"
            gps_path = self.session_path / "gps.csv"
            if raw_path.exists() and gps_path.exists():
                raw_lines = raw_path.read_text(encoding="utf-8").strip().splitlines()
                gps_lines = gps_path.read_text(encoding="utf-8").strip().splitlines()
                self.saw_incremental_files = len(raw_lines) >= 2 and len(gps_lines) >= 2
        return super().read_sample(timestamp=timestamp)


class FakeGPS:
    def __init__(self):
        self.index = 0

    def read_sample(self):
        self.index += 1
        return {
            "timestamp": 1000.0 + self.index * 0.2,
            "lat": 36.628 + self.index * 0.00001,
            "lon": 127.456,
            "gps_valid": 1,
            "speed_mps": 2.7,
        }


class FakeCamera:
    def capture(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake image")
        return path


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        self.now += 0.2
        return self.now


class InterruptingSleeper:
    def __init__(self, raise_on_call: int):
        self.raise_on_call = raise_on_call
        self.calls = 0

    def __call__(self, seconds):
        self.calls += 1
        if self.calls >= self.raise_on_call:
            raise KeyboardInterrupt


if __name__ == "__main__":
    unittest.main()
