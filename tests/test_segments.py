import unittest

from barrier_free import mock_data, segments


class SegmentTest(unittest.TestCase):
    def test_segment_id_is_stable_and_changes_across_about_ten_meter_cells(self):
        segment_id = segments.segment_id_for(36.628, 127.456, segment_meters=10)

        self.assertIsInstance(segment_id, str)
        self.assertEqual(
            segment_id,
            segments.segment_id_for(36.628, 127.456, segment_meters=10),
        )
        self.assertNotEqual(
            segment_id,
            segments.segment_id_for(36.629, 127.456, segment_meters=10),
        )

    def test_aggregate_events_scores_risk_candidates_and_normal_events(self):
        lat = 36.628
        lon = 127.456
        segment_id = segments.segment_id_for(lat, lon, segment_meters=10)
        summary = segments.aggregate_events(
            [
                _event(lat, lon, "danger", 0.80),
                _event(lat, lon, "candidate", 0.50),
                _event(lat, lon, "normal", 0.95),
            ],
            segment_meters=10,
        )

        row = summary[segment_id]
        self.assertEqual(row["event_count"], 3)
        self.assertAlmostEqual(row["max_risk_score"], 0.80)
        self.assertAlmostEqual(row["avg_risk_score"], (0.80 + 0.50 + 0.0) / 3)
        self.assertAlmostEqual(row["repeated_detection_ratio"], 2 / 3)
        self.assertEqual(row["risk_level"], "danger")
        self.assertEqual(len(row["events"]), 3)

    def test_compare_before_after_statuses_and_improvement_rate(self):
        clean = "clean"
        improved = "improved"
        worsened = "worsened"
        new_risk = "new"
        missing_after = "missing_after"

        before = {
            clean: _summary(clean, 0.0),
            improved: _summary(improved, 0.80),
            worsened: _summary(worsened, 0.30),
            new_risk: _summary(new_risk, 0.0),
            missing_after: _summary(missing_after, 0.60),
        }
        after = {
            clean: _summary(clean, 0.0),
            improved: _summary(improved, 0.40),
            worsened: _summary(worsened, 0.60),
            new_risk: _summary(new_risk, 0.50),
        }

        comparison = {row["segment_id"]: row for row in segments.compare_segments(before, after)}

        self.assertEqual(comparison[clean]["status"], "unchanged_clean")
        self.assertIsNone(comparison[clean]["improvement_rate"])
        self.assertEqual(comparison[improved]["status"], "improved")
        self.assertAlmostEqual(comparison[improved]["improvement_rate"], 0.50)
        self.assertEqual(comparison[worsened]["status"], "worsened")
        self.assertAlmostEqual(comparison[worsened]["improvement_rate"], -1.0)
        self.assertEqual(comparison[new_risk]["status"], "new_risk")
        self.assertIsNone(comparison[new_risk]["improvement_rate"])
        self.assertEqual(comparison[missing_after]["status"], "improved")
        self.assertAlmostEqual(comparison[missing_after]["improvement_rate"], 1.0)

    def test_compare_before_after_uses_route_coverage_to_avoid_false_improvement(self):
        covered = "covered"
        not_covered = "not_covered"
        before = {
            covered: _summary(covered, 0.80),
            not_covered: _summary(not_covered, 0.70),
        }
        after = {}

        comparison = {
            row["segment_id"]: row
            for row in segments.compare_segments(
                before,
                after,
                before_coverage={covered, not_covered},
                after_coverage={covered},
            )
        }

        self.assertEqual(comparison[covered]["status"], "improved")
        self.assertAlmostEqual(comparison[covered]["improvement_rate"], 1.0)
        self.assertEqual(comparison[not_covered]["status"], "not_comparable")
        self.assertIsNone(comparison[not_covered]["improvement_rate"])

    def test_mock_before_after_reports_improvement(self):
        dataset = mock_data.build_demo_dataset(seed=42)
        before = segments.aggregate_events(dataset["before"]["events"], segment_meters=10)
        after = segments.aggregate_events(dataset["after"]["events"], segment_meters=10)

        comparison = segments.compare_segments(before, after)

        improved = [row for row in comparison if row["status"] == "improved"]
        self.assertTrue(improved)
        self.assertGreaterEqual(improved[0]["improvement_rate"], 0.0)


def _event(lat, lon, prediction, risk_score):
    return {
        "event_id": f"{prediction}_{risk_score}",
        "timestamp_start": 0.0,
        "timestamp_end": 1.0,
        "lat": lat,
        "lon": lon,
        "gps_valid": 1,
        "speed_mps": 2.5,
        "prediction": prediction,
        "confidence": 0.9,
        "risk_score": risk_score,
        "segment_id": "",
        "photo_before": "",
        "photo_after": "",
        "model_version": "test",
    }


def _summary(segment_id, max_risk_score):
    risk_level = "normal"
    if max_risk_score >= 0.70:
        risk_level = "danger"
    elif max_risk_score > 0:
        risk_level = "caution"
    return {
        "segment_id": segment_id,
        "event_count": 1,
        "max_risk_score": max_risk_score,
        "avg_risk_score": max_risk_score,
        "repeated_detection_ratio": 1.0 if max_risk_score > 0 else 0.0,
        "risk_level": risk_level,
    }


if __name__ == "__main__":
    unittest.main()
