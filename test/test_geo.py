import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from herdr_flight_radar import geo


class HaversineTest(unittest.TestCase):
    def test_same_point_is_zero(self):
        self.assertAlmostEqual(geo.haversine_miles(47.6062, -122.3321, 47.6062, -122.3321), 0.0, places=6)

    def test_known_distance_sea_to_pdx(self):
        # Seattle (SEA) to Portland (PDX) airports, ~129 statute miles great-circle.
        sea = (47.4502, -122.3088)
        pdx = (45.5898, -122.5951)
        dist = geo.haversine_miles(sea[0], sea[1], pdx[0], pdx[1])
        self.assertAlmostEqual(dist, 129.0, delta=2.0)

    def test_quarter_equator_is_quarter_circumference(self):
        # Two points 90 degrees apart on the equator are 1/4 of Earth's
        # circumference apart.
        dist = geo.haversine_miles(0.0, 0.0, 0.0, 90.0)
        expected = 2 * 3.14159265358979 * geo.EARTH_RADIUS_MILES / 4
        self.assertAlmostEqual(dist, expected, delta=1.0)

    def test_symmetric(self):
        a = (10.0, 20.0)
        b = (-5.0, 30.0)
        self.assertAlmostEqual(
            geo.haversine_miles(a[0], a[1], b[0], b[1]),
            geo.haversine_miles(b[0], b[1], a[0], a[1]),
            places=9,
        )


class BearingTest(unittest.TestCase):
    def test_due_north(self):
        self.assertAlmostEqual(geo.bearing_deg(0.0, 0.0, 1.0, 0.0), 0.0, delta=0.5)

    def test_due_east(self):
        self.assertAlmostEqual(geo.bearing_deg(0.0, 0.0, 0.0, 1.0), 90.0, delta=0.5)

    def test_due_south(self):
        self.assertAlmostEqual(geo.bearing_deg(0.0, 0.0, -1.0, 0.0), 180.0, delta=0.5)

    def test_due_west(self):
        self.assertAlmostEqual(geo.bearing_deg(0.0, 0.0, 0.0, -1.0), 270.0, delta=0.5)

    def test_range_is_0_to_360(self):
        bearing = geo.bearing_deg(10.0, 10.0, 5.0, -5.0)
        self.assertGreaterEqual(bearing, 0.0)
        self.assertLess(bearing, 360.0)


if __name__ == "__main__":
    unittest.main()
