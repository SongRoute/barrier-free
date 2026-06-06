import json
import tempfile
import unittest
from pathlib import Path

from barrier_free import cli


class WebExportTest(unittest.TestCase):
    def test_export_web_demo_contains_comparison_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)

            payload_path = cli.export_demo(out, seed=42)
            payload = json.loads(payload_path.read_text(encoding="utf-8"))

            self.assertIn("sessions", payload)
            self.assertEqual(len(payload["sessions"]), 2)
            self.assertIn("comparison", payload)
            self.assertGreater(len(payload["comparison"]), 0)
            self.assertIn("model", payload)
            self.assertGreater(payload["model"]["training_rows"], 0)

    def test_web_static_files_include_leaflet_map_and_filters(self):
        index = Path("web/index.html").read_text(encoding="utf-8")
        app = Path("web/app.js").read_text(encoding="utf-8")

        self.assertIn('id="map"', index)
        self.assertIn('id="session-list"', index)
        self.assertIn('id="view-mode"', index)
        self.assertIn('id="imu-heat-toggle"', index)
        self.assertIn('id="marker-size"', index)
        self.assertIn('id="marker-size-value"', index)
        self.assertIn('id="final-summary"', index)
        self.assertIn('id="threshold-summary"', index)
        self.assertIn("leaflet", index.lower())
        self.assertIn("L.map", app)
        self.assertIn("renderSegments", app)
        self.assertIn("renderEvents", app)
        self.assertIn("renderImuHeatRoute", app)
        self.assertIn("imuColor", app)
        self.assertIn("markerScale", app)
        self.assertIn("scaledMarkerRadius", app)
        self.assertIn("renderComparisonMode", app)
        self.assertIn("statusColor", app)
        self.assertIn("applyDefaultView", app)
        self.assertIn("renderFinalSummary", app)
        self.assertIn("renderThresholdSummary", app)
        self.assertIn("group_comparison", app)


if __name__ == "__main__":
    unittest.main()
