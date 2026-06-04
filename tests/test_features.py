import unittest

from barrier_free import features, mock_data


class FeatureExtractionTest(unittest.TestCase):
    def test_extract_features_from_one_second_window(self):
        rows = [
            {
                "timestamp": 0.00,
                "ax": 0.0,
                "ay": 0.0,
                "az": 1.0,
                "gx": 0.0,
                "gy": 0.0,
                "gz": 0.0,
            },
            {
                "timestamp": 0.50,
                "ax": 3.0,
                "ay": 4.0,
                "az": 0.0,
                "gx": 0.0,
                "gy": 0.0,
                "gz": 2.0,
            },
            {
                "timestamp": 0.99,
                "ax": 0.0,
                "ay": 0.0,
                "az": 2.0,
                "gx": 0.0,
                "gy": 0.0,
                "gz": 0.0,
            },
        ]

        result = features.extract_window_features(rows, speed_mps=2.5)

        self.assertAlmostEqual(result["accel_mag_max"], 5.0)
        self.assertAlmostEqual(result["speed_mps"], 2.5)
        self.assertEqual(result["z_peak_count"], 1)

    def test_window_imu_rows_uses_non_overlapping_seconds(self):
        dataset = mock_data.build_demo_dataset(seed=42)
        windows = features.window_imu_rows(dataset["before"]["raw_imu"], window_seconds=1.0)

        self.assertEqual(len(windows), 24)
        self.assertEqual(len(windows[0]), 20)
        self.assertGreater(windows[4][-1]["timestamp"], windows[4][0]["timestamp"])


if __name__ == "__main__":
    unittest.main()
