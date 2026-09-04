import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from herdr_flight_radar import sbs

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_sbs_session.txt")


class ParseSbsLineTest(unittest.TestCase):
    def test_ignores_blank_line(self):
        self.assertIsNone(sbs.parse_sbs_line(""))
        self.assertIsNone(sbs.parse_sbs_line("   \n"))

    def test_ignores_non_msg_line(self):
        self.assertIsNone(sbs.parse_sbs_line("SEL,1,1,1,A1,1,,,,,,,,,,,,,,,,"))

    def test_ignores_short_line(self):
        self.assertIsNone(sbs.parse_sbs_line("MSG,1,1,1,A1"))

    def test_ignores_line_with_no_hex(self):
        line = "MSG,1,1,1,,f,,,,,,,,,,,,,,,,"
        self.assertIsNone(sbs.parse_sbs_line(line))

    def test_parses_identification_message(self):
        line = "MSG,1,111,11111,A12345,111111,2026/09/04,12:00:00.000,2026/09/04,12:00:00.000,UAL123,,,,,,,,,,,"
        fields = sbs.parse_sbs_line(line)
        self.assertEqual(fields["hex"], "A12345")
        self.assertEqual(fields["callsign"], "UAL123")
        self.assertIsNone(fields["altitude_ft"])

    def test_parses_position_message(self):
        line = "MSG,3,111,11111,A12345,111111,2026/09/04,12:00:01.000,2026/09/04,12:00:01.000,,5000,,,47.6100,-122.3300,,,,,,0"
        fields = sbs.parse_sbs_line(line)
        self.assertEqual(fields["altitude_ft"], 5000.0)
        self.assertAlmostEqual(fields["lat"], 47.6100)
        self.assertAlmostEqual(fields["lon"], -122.3300)


class AircraftTableTest(unittest.TestCase):
    def test_merges_incremental_fields_by_hex(self):
        table = sbs.AircraftTable()
        with open(FIXTURE_PATH) as f:
            for line in f:
                table.update_from_line(line)

        self.assertEqual(len(table), 2)
        snapshot = {ac.hex: ac for ac in table.snapshot()}

        ual = snapshot["A12345"]
        self.assertEqual(ual.callsign, "UAL123")
        self.assertEqual(ual.altitude_ft, 5000.0)
        self.assertEqual(ual.speed_kt, 250.0)
        self.assertEqual(ual.track_deg, 90.0)
        self.assertAlmostEqual(ual.lat, 47.6100)
        self.assertAlmostEqual(ual.lon, -122.3300)

        dal = snapshot["B67890"]
        self.assertEqual(dal.callsign, "DAL456")
        self.assertEqual(dal.altitude_ft, 32000.0)

    def test_snapshot_excludes_aircraft_without_position(self):
        table = sbs.AircraftTable()
        table.update_from_line(
            "MSG,1,1,1,C99999,1,,,,,SWA1,,,,,,,,,,,")
        self.assertEqual(len(table), 1)
        self.assertEqual(table.snapshot(), [])

    def test_expire_stale_removes_old_aircraft(self):
        clock = {"t": 0.0}
        table = sbs.AircraftTable(stale_seconds=10.0, clock=lambda: clock["t"])
        table.update_from_line(
            "MSG,3,1,1,D11111,1,,,,,,1000,,,10.0,20.0,,,,,,0")
        clock["t"] = 11.0
        expired = table.expire_stale()
        self.assertEqual(expired, ["D11111"])
        self.assertEqual(len(table), 0)

    def test_expire_stale_keeps_fresh_aircraft(self):
        clock = {"t": 0.0}
        table = sbs.AircraftTable(stale_seconds=10.0, clock=lambda: clock["t"])
        table.update_from_line(
            "MSG,3,1,1,D11111,1,,,,,,1000,,,10.0,20.0,,,,,,0")
        clock["t"] = 5.0
        expired = table.expire_stale()
        self.assertEqual(expired, [])
        self.assertEqual(len(table), 1)


if __name__ == "__main__":
    unittest.main()
