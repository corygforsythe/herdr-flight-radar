import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from herdr_flight_radar import render


def ac(hex_, lat, lon, track_deg=None):
    return SimpleNamespace(hex=hex_, lat=lat, lon=lon, track_deg=track_deg)


class HeadingGlyphTest(unittest.TestCase):
    def test_north(self):
        self.assertEqual(render.heading_glyph(0), "↑")

    def test_east(self):
        self.assertEqual(render.heading_glyph(90), "→")

    def test_south(self):
        self.assertEqual(render.heading_glyph(180), "↓")

    def test_wraps_near_360(self):
        self.assertEqual(render.heading_glyph(359), "↑")

    def test_unknown_is_dot(self):
        self.assertEqual(render.heading_glyph(None), render.UNKNOWN_HEADING_GLYPH)


class ProjectToPxTest(unittest.TestCase):
    def test_center_point_projects_to_canvas_center(self):
        canvas = render.BrailleCanvas(width_cells=40, height_cells=20)
        px = render.project_to_px(10.0, 20.0, 10.0, 20.0, 100.0, canvas)
        self.assertIsNotNone(px)
        x, y = px
        self.assertAlmostEqual(x, canvas.px_width / 2.0, delta=1.0)
        self.assertAlmostEqual(y, canvas.px_height / 2.0, delta=1.0)

    def test_point_beyond_radius_is_none(self):
        canvas = render.BrailleCanvas(width_cells=40, height_cells=20)
        # ~0.9 degrees latitude north is about 62 miles; use a point far
        # further away than the configured radius.
        px = render.project_to_px(20.0, 20.0, 10.0, 20.0, 50.0, canvas)
        self.assertIsNone(px)

    def test_due_north_point_moves_up(self):
        canvas = render.BrailleCanvas(width_cells=40, height_cells=20)
        x, y = render.project_to_px(10.5, 20.0, 10.0, 20.0, 100.0, canvas)
        self.assertLess(y, canvas.px_height / 2.0)
        self.assertAlmostEqual(x, canvas.px_width / 2.0, delta=1.0)

    def test_due_east_point_moves_right(self):
        canvas = render.BrailleCanvas(width_cells=40, height_cells=20)
        x, y = render.project_to_px(10.0, 21.0, 10.0, 20.0, 200.0, canvas)
        self.assertGreater(x, canvas.px_width / 2.0)
        self.assertAlmostEqual(y, canvas.px_height / 2.0, delta=1.0)


class RenderFrameTest(unittest.TestCase):
    def test_includes_only_in_range_aircraft(self):
        aircraft = [
            ac("NEAR01", 10.1, 20.0, track_deg=0),
            ac("FAR01", 40.0, 90.0, track_deg=0),
        ]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 40, 20)
        hexes = set(frame.aircraft_cells.values())
        self.assertIn("NEAR01", hexes)
        self.assertNotIn("FAR01", hexes)

    def test_cardinal_markers_present(self):
        frame = render.render_frame(10.0, 20.0, 100.0, [], 40, 20)
        joined = "\n".join(frame.lines)
        for marker in "NESW":
            self.assertIn(marker, joined)

    def test_hex_at_matches_aircraft_cells(self):
        aircraft = [ac("ABC123", 10.1, 20.0, track_deg=90)]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 40, 20)
        (row, col), hx = next(iter(frame.aircraft_cells.items()))
        self.assertEqual(hx, "ABC123")
        self.assertEqual(frame.hex_at(row, col), "ABC123")

    def test_hex_at_returns_none_for_empty_cell(self):
        frame = render.render_frame(10.0, 20.0, 100.0, [], 40, 20)
        self.assertIsNone(frame.hex_at(0, 0))


class BrailleCanvasTest(unittest.TestCase):
    def test_set_px_out_of_bounds_is_ignored(self):
        canvas = render.BrailleCanvas(width_cells=4, height_cells=4)
        canvas.set_px(-1, -1)
        canvas.set_px(999, 999)
        for row in canvas.rows():
            self.assertEqual(row, " " * 4)

    def test_set_px_sets_a_dot(self):
        canvas = render.BrailleCanvas(width_cells=4, height_cells=4)
        canvas.set_px(0, 0)
        rows = canvas.rows()
        self.assertNotEqual(rows[0][0], " ")


if __name__ == "__main__":
    unittest.main()
