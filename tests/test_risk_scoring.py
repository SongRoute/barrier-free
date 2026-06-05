import unittest

from barrier_free import risk_scoring


class RiskScoringTest(unittest.TestCase):
    def test_thresholds_reject_invalid_values(self):
        with self.assertRaisesRegex(ValueError, "caution_delta"):
            risk_scoring.RiskThresholds(caution_delta=0.0)
        with self.assertRaisesRegex(ValueError, "danger_delta"):
            risk_scoring.RiskThresholds(caution_delta=0.5, danger_delta=0.4)
        with self.assertRaisesRegex(ValueError, "danger_jerk"):
            risk_scoring.RiskThresholds(danger_jerk=0.0)

    def test_classifies_window_by_tunable_thresholds(self):
        thresholds = risk_scoring.RiskThresholds(
            caution_delta=0.35,
            danger_delta=0.75,
            danger_jerk=12.0,
        )

        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.2, "jerk_max": 2.0}, thresholds)["prediction"],
            "normal",
        )
        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.5, "jerk_max": 3.0}, thresholds)["prediction"],
            "caution",
        )
        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.8, "jerk_max": 3.0}, thresholds)["prediction"],
            "danger",
        )
        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.8, "jerk_max": 3.0}, thresholds)["risk_reasons"],
            ["accel_delta"],
        )
        self.assertEqual(
            risk_scoring.classify_window({"accel_delta_max": 0.2, "jerk_max": 15.0}, thresholds)["prediction"],
            "danger",
        )

    def test_scores_session_windows_from_raw_imu_and_gps(self):
        bundle = {
            "raw_imu": [
                {"timestamp": 1.0, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
                {"timestamp": 1.5, "ax": 0.0, "ay": 0.0, "az": 1.2, "gx": 0.0, "gy": 0.0, "gz": 0.0},
                {"timestamp": 2.0, "ax": 0.0, "ay": 0.0, "az": 1.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
                {"timestamp": 2.5, "ax": 0.0, "ay": 0.0, "az": 2.0, "gx": 0.0, "gy": 0.0, "gz": 0.0},
            ],
            "gps": [
                {"timestamp": 1.0, "lat": 36.0, "lon": 127.0, "gps_valid": 1, "speed_mps": 2.0},
                {"timestamp": 2.0, "lat": 36.0001, "lon": 127.0, "gps_valid": 1, "speed_mps": 2.0},
            ],
        }
        thresholds = risk_scoring.RiskThresholds(caution_delta=0.3, danger_delta=0.7, danger_jerk=99.0)

        windows = risk_scoring.score_session_windows(bundle, thresholds)

        self.assertEqual([row["prediction"] for row in windows], ["normal", "danger"])
        self.assertIn("risk_score", windows[1])
        self.assertIn("risk_reasons", windows[1])
        self.assertEqual(windows[1]["gps_valid"], 1)
        self.assertEqual(windows[1]["sample_count"], 2)

    def test_event_rows_keep_window_evidence_fields(self):
        scored_windows = [
            {
                "window_id": "imu_window_0001",
                "timestamp_start": 1.0,
                "timestamp_end": 1.5,
                "lat": 36.0,
                "lon": 127.0,
                "gps_valid": 1,
                "speed_mps": 2.0,
                "prediction": "danger",
                "confidence": 0.9,
                "risk_score": 0.95,
                "risk_reasons": ["accel_delta"],
                "threshold_version": "threshold-v1",
                "route_name": "obstacle_demo_route",
                "phase": "before",
            }
        ]

        events = risk_scoring.event_rows_from_scored_windows(scored_windows, session_id="before_001")

        self.assertEqual(events[0]["source"], "imu-threshold")
        self.assertEqual(events[0]["source_window_id"], "imu_window_0001")
        self.assertEqual(events[0]["risk_reasons"], ["accel_delta"])
        self.assertEqual(events[0]["route_name"], "obstacle_demo_route")
        self.assertEqual(events[0]["phase"], "before")


if __name__ == "__main__":
    unittest.main()
