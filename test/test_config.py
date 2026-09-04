import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from herdr_flight_radar import config as config_mod


class LoadConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.path = os.path.join(self.tmpdir.name, "config.json")

    def write(self, data):
        with open(self.path, "w") as f:
            json.dump(data, f)

    def test_missing_file_raises_readable_error(self):
        with self.assertRaises(config_mod.ConfigError) as ctx:
            config_mod.load_config(self.path)
        self.assertIn("No Flight Radar location is configured", str(ctx.exception))
        self.assertIn(self.path, str(ctx.exception))

    def test_missing_location_raises_readable_error(self):
        self.write({"radius_miles": 50})
        with self.assertRaises(config_mod.ConfigError) as ctx:
            config_mod.load_config(self.path)
        self.assertIn("missing a location", str(ctx.exception))

    def test_valid_config_with_explicit_radius(self):
        self.write({"location": {"lat": 47.6, "lon": -122.3}, "radius_miles": 50})
        cfg = config_mod.load_config(self.path)
        self.assertEqual(cfg.lat, 47.6)
        self.assertEqual(cfg.lon, -122.3)
        self.assertEqual(cfg.radius_miles, 50.0)

    def test_default_radius_is_100_miles(self):
        self.write({"location": {"lat": 47.6, "lon": -122.3}})
        cfg = config_mod.load_config(self.path)
        self.assertEqual(cfg.radius_miles, config_mod.DEFAULT_RADIUS_MILES)
        self.assertEqual(cfg.radius_miles, 100.0)

    def test_out_of_range_lat_raises(self):
        self.write({"location": {"lat": 200.0, "lon": -122.3}})
        with self.assertRaises(config_mod.ConfigError):
            config_mod.load_config(self.path)

    def test_non_positive_radius_raises(self):
        self.write({"location": {"lat": 47.6, "lon": -122.3}, "radius_miles": 0})
        with self.assertRaises(config_mod.ConfigError):
            config_mod.load_config(self.path)

    def test_malformed_json_raises_readable_error(self):
        with open(self.path, "w") as f:
            f.write("{not valid json")
        with self.assertRaises(config_mod.ConfigError) as ctx:
            config_mod.load_config(self.path)
        self.assertIn("Could not read", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
