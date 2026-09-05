import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from herdr_flight_radar import render


def ac(hex_, lat, lon, track_deg=None, callsign=None):
    return SimpleNamespace(hex=hex_, lat=lat, lon=lon, track_deg=track_deg,
                            callsign=callsign)


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


class AircraftLabelTest(unittest.TestCase):
    def test_uses_callsign_when_present(self):
        aircraft = ac("ABC123", 10.0, 20.0, callsign="UAL123")
        self.assertEqual(render.aircraft_label(aircraft), "UAL123")

    def test_falls_back_to_hex_when_no_callsign(self):
        aircraft = ac("ABC123", 10.0, 20.0, callsign=None)
        self.assertEqual(render.aircraft_label(aircraft), "ABC123")

    def test_falls_back_to_hex_for_blank_callsign(self):
        aircraft = ac("ABC123", 10.0, 20.0, callsign="   ")
        self.assertEqual(render.aircraft_label(aircraft), "ABC123")

    def test_label_is_truncated(self):
        aircraft = ac("ABC123", 10.0, 20.0, callsign="LONGCALLSIGN99")
        self.assertLessEqual(len(render.aircraft_label(aircraft)), render.MAX_LABEL_LEN)


class RenderFrameLabelTest(unittest.TestCase):
    def test_label_with_callsign_appears_next_to_arrow(self):
        aircraft = [ac("ABC123", 10.1, 20.0, track_deg=90, callsign="UAL123")]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 40, 20)
        (row, col), _hx = next(iter(frame.aircraft_cells.items()))
        self.assertTrue(frame.lines[row][col + 1:col + 4].startswith("UAL"))

    def test_label_falls_back_to_hex_without_callsign(self):
        aircraft = [ac("ABC123", 10.1, 20.0, track_deg=90, callsign=None)]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 40, 20)
        (row, col), _hx = next(iter(frame.aircraft_cells.items()))
        self.assertTrue(frame.lines[row][col + 1:col + 4].startswith("ABC"))

    def test_crowded_area_truncates_label_instead_of_overwriting_ring(self):
        # This point lands close enough to a range ring that only a
        # couple of blank cells are open before ring glyphs start; the
        # label must stop there instead of overwriting the ring.
        aircraft = [ac("ABC123", 10.1, 20.0, track_deg=90, callsign="UAL123")]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 40, 20)
        (row, col), _hx = next(iter(frame.aircraft_cells.items()))
        self.assertNotIn("UAL123", frame.lines[row])

    def test_label_flips_left_when_clipped_on_the_right(self):
        # This point sits near the top of the radar where the outer ring's
        # curve leaves only 5 blank cells to the right of the glyph before
        # the ring resumes -- not enough for the 6-char "UAL123" callsign --
        # but 7 blank cells open up to the left. Before the fix, the label
        # always drew rightward and silently truncated to "UAL12"; the fix
        # must notice the label doesn't fit to the right, and place the
        # full label to the left instead so it's never partially visible.
        aircraft = [ac("ABC123", 11.22719636721447, 20.109022060115862,
                        track_deg=0, callsign="UAL123")]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 40, 20)
        (row, col), _hx = next(iter(frame.aircraft_cells.items()))
        self.assertIn("UAL123", frame.lines[row])
        self.assertLess(frame.lines[row].index("UAL123"), col)

    def test_label_does_not_change_hit_testing(self):
        aircraft = [ac("ABC123", 10.1, 20.0, track_deg=90, callsign="UAL123")]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 40, 20)
        (row, col), hx = next(iter(frame.aircraft_cells.items()))
        self.assertEqual(hx, "ABC123")
        self.assertEqual(frame.hex_at(row, col), "ABC123")
        # The label cell itself (adjacent to the glyph) must not be a hit target.
        self.assertNotIn((row, col + 1), frame.aircraft_cells)


class RenderFrameLabelCollisionTest(unittest.TestCase):
    def test_close_aircraft_labels_do_not_clip_each_other(self):
        # Two aircraft close enough together that AAA111's default
        # (immediately-right) label placement would run straight through
        # BBB222's glyph cell. Before the fix, aircraft were drawn and
        # labeled one at a time in input order: AAA111's label was placed
        # while BBB222's glyph cell still looked blank (its glyph hadn't
        # been drawn yet), so BBB222's glyph then overwrote the middle of
        # AAA111's already-placed label, and BBB222's own label found no
        # room left and vanished. The fix must place every aircraft's
        # glyph before placing any label, and pick a non-colliding
        # candidate placement for each, so both full labels survive.
        aircraft = [
            ac("AAA111", 10.02, 20.0, track_deg=90, callsign="UAL111"),
            ac("BBB222", 10.02, 20.12, track_deg=90, callsign="DAL222"),
        ]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 80, 40)
        joined = "\n".join(frame.lines)
        self.assertIn("UAL111", joined)
        self.assertIn("DAL222", joined)

    def test_dense_cluster_documents_partial_overlap_without_crashing(self):
        # More aircraft crammed into a tiny canvas than there are
        # non-colliding candidate positions. This is the disclosed density
        # limit (see render._place_label's docstring): the fix guarantees
        # a best-effort, non-crashing placement search, not full
        # non-overlap under every possible density.
        aircraft = [
            ac("A{:05d}".format(i), 10.0 + i * 0.001, 20.0 + i * 0.001,
               track_deg=90, callsign="C{:04d}".format(i))
            for i in range(10)
        ]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 20, 10)
        # No crash, and every rendered line stays within the canvas width
        # even when labels can't all find a non-colliding home.
        for line in frame.lines:
            self.assertEqual(len(line), 20)


class RenderFrameAircraftSpansTest(unittest.TestCase):
    def test_span_covers_glyph_and_label(self):
        aircraft = [ac("ABC123", 10.1, 20.0, track_deg=90, callsign="UAL123")]
        frame = render.render_frame(10.0, 20.0, 100.0, aircraft, 40, 20)
        (row, col), _hx = next(iter(frame.aircraft_cells.items()))
        self.assertEqual(len(frame.aircraft_spans), 1)
        span_row, span_col, span_len = frame.aircraft_spans[0]
        self.assertEqual((span_row, span_col), (row, col))
        # 1 glyph cell + however many label chars actually fit.
        placed_label = frame.lines[row][col + 1:col + span_len]
        self.assertEqual(span_len, 1 + len(placed_label))
        self.assertTrue(placed_label == "" or "UAL123".startswith(placed_label))

    def test_no_aircraft_means_no_spans(self):
        frame = render.render_frame(10.0, 20.0, 100.0, [], 40, 20)
        self.assertEqual(frame.aircraft_spans, [])


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
