import unittest

from barrier_free import mock_data, model


class ModelTest(unittest.TestCase):
    def test_training_rows_match_labels_and_exclude_non_road_shocks(self):
        dataset = mock_data.build_demo_dataset(seed=7)

        training_rows = model.training_rows_from_bundle(dataset["before"])

        self.assertGreater(len(training_rows), 0)
        self.assertNotIn("exclude", {row["label"] for row in training_rows})
        self.assertLessEqual(
            {"normal", "caution", "danger"},
            {row["label"] for row in training_rows},
        )
        self.assertIn("accel_mag_max", training_rows[0]["features"])

    def test_out_of_range_labels_do_not_match_nearest_window(self):
        dataset = mock_data.build_demo_dataset(seed=7)
        bundle = dataset["before"]
        out_of_range = dict(bundle["labels"][0])
        out_of_range["label_id"] = "outside"
        out_of_range["timestamp_start"] = 1.0
        out_of_range["timestamp_end"] = 2.0
        bundle["labels"] = [out_of_range]

        training_rows = model.training_rows_from_bundle(bundle)

        self.assertEqual(training_rows, [])

    def test_model_predicts_known_mock_classes(self):
        dataset = mock_data.build_demo_dataset(seed=7)
        training_rows = model.training_rows_from_bundle(dataset["before"])
        clf = model.TinyForestClassifier(tree_count=9, seed=7)
        clf.fit(training_rows)

        predictions = {clf.predict(row["features"])["prediction"] for row in training_rows}

        self.assertLessEqual({"caution", "danger"}, predictions)
        self.assertIn(
            clf.predict(training_rows[0]["features"])["prediction"],
            {"normal", "caution", "danger"},
        )

    def test_model_roundtrip_keeps_predictions_and_metrics(self):
        dataset = mock_data.build_demo_dataset(seed=8)
        training_rows = model.training_rows_from_bundle(dataset["before"])
        clf = model.TinyForestClassifier(tree_count=11, seed=8)
        clf.fit(training_rows)

        restored = model.TinyForestClassifier.from_json(clf.to_json())
        original_prediction = clf.predict(training_rows[0]["features"])
        restored_prediction = restored.predict(training_rows[0]["features"])
        metrics = model.evaluate(clf, training_rows)

        self.assertEqual(original_prediction, restored_prediction)
        self.assertIn("confusion_matrix", metrics)
        self.assertIn("recall", metrics)
        self.assertIn("danger", metrics["recall"])


if __name__ == "__main__":
    unittest.main()
