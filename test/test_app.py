import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from herdr_flight_radar import app, sbs
from herdr_flight_radar.config import Config

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_sbs_session.txt")


class VisibleSortedTest(unittest.TestCase):
    def test_filters_and_sorts_by_distance(self):
        table = sbs.AircraftTable()
        with open(FIXTURE_PATH) as f:
            for line in f:
                table.update_from_line(line)

        # Center near Seattle; UAL123 (~47.61,-122.33) is close, DAL456
        # (Portland-area, ~45.59,-122.60) is roughly 130mi away.
        cfg = Config(lat=47.6062, lon=-122.3321, radius_miles=50.0, path="unused")
        visible = app.visible_sorted(cfg, table)

        self.assertEqual([ac.hex for ac in visible], ["A12345"])

    def test_wide_radius_includes_and_orders_both(self):
        table = sbs.AircraftTable()
        with open(FIXTURE_PATH) as f:
            for line in f:
                table.update_from_line(line)

        cfg = Config(lat=47.6062, lon=-122.3321, radius_miles=500.0, path="unused")
        visible = app.visible_sorted(cfg, table)

        self.assertEqual([ac.hex for ac in visible], ["A12345", "B67890"])


class FormatDetailTest(unittest.TestCase):
    def test_includes_core_fields(self):
        table = sbs.AircraftTable()
        with open(FIXTURE_PATH) as f:
            for line in f:
                table.update_from_line(line)
        ac = next(a for a in table.snapshot() if a.hex == "A12345")

        line = app.format_detail(ac, 47.6062, -122.3321)

        self.assertIn("UAL123", line)
        self.assertIn("A12345", line)
        self.assertIn("5000", line)
        self.assertIn("250", line)
        self.assertIn("90", line)

    def test_handles_missing_optional_fields(self):
        table = sbs.AircraftTable()
        table.update_from_line("MSG,3,1,1,E22222,1,,,,,,,,,10.0,20.0,,,,,,0")
        ac = next(iter(table.snapshot()))

        line = app.format_detail(ac, 10.0, 20.0)

        self.assertIn("(unknown)", line)
        self.assertIn("unknown", line)


if __name__ == "__main__":
    unittest.main()
