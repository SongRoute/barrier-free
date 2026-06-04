import unittest

from barrier_free import mock_data, schema


class MockDataTest(unittest.TestCase):
    def test_mock_before_after_sessions_are_deterministic(self):
        first = mock_data.build_demo_dataset(seed=42)
        second = mock_data.build_demo_dataset(seed=42)

        self.assertEqual(first["before"]["session"]["session_id"], "demo_before_run01")
        self.assertEqual(first, second)
        self.assertGreater(len(first["before"]["raw_imu"]), 50)
        self.assertGreater(len(first["before"]["events"]), len(first["after"]["events"]))

    def test_generated_sessions_match_schema(self):
        dataset = mock_data.build_demo_dataset(seed=11)

        for bundle in dataset.values():
            schema.validate_session_bundle(bundle)

    def test_generated_sessions_include_labels(self):
        dataset = mock_data.build_demo_dataset(seed=12)

        before = dataset["before"]

        self.assertIn("labels", before)
        self.assertGreater(len(before["labels"]), 0)
        self.assertLessEqual(
            {label["label"] for label in before["labels"]},
            {"normal", "caution", "danger", "exclude"},
        )

    def test_schema_accepts_raw_candidate_events(self):
        dataset = mock_data.build_demo_dataset(seed=13)
        bundle = dataset["before"]
        candidate = dict(bundle["events"][0])
        candidate["prediction"] = "candidate"
        candidate["model_version"] = "none"
        bundle["events"] = [candidate]

        schema.validate_session_bundle(bundle)


if __name__ == "__main__":
    unittest.main()
