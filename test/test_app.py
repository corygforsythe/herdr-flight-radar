import curses
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from herdr_flight_radar import app, render, sbs
from herdr_flight_radar.config import Config

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_sbs_session.txt")


class _FakeStdscr:
    """Minimal stdscr stand-in so _curses_main can run outside a real TTY."""

    def __init__(self, height, width, chars):
        self.height = height
        self.width = width
        self._chars = list(chars)
        self.addstr_calls = []

    def getmaxyx(self):
        return self.height, self.width

    def nodelay(self, flag):
        pass

    def timeout(self, ms):
        pass

    def erase(self):
        pass

    def addstr(self, row, col, text):
        self.addstr_calls.append((row, col, text))

    def chgat(self, row, col, num, attr):
        pass

    def refresh(self):
        pass

    def getch(self):
        return self._chars.pop(0)


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


class CursesMainMouseFilterTest(unittest.TestCase):
    def test_motion_event_does_not_select_but_click_does(self):
        cfg = Config(lat=10.0, lon=20.0, radius_miles=100.0, path="unused")
        table = sbs.AircraftTable()
        table.update_from_fields({
            "hex": "ABC123", "callsign": "TEST01", "altitude_ft": 5000.0,
            "speed_kt": 200.0, "track_deg": 90.0, "lat": 10.1, "lon": 20.0,
        })

        # _curses_main sizes its canvas to 40x20 for a 44x22 stdscr (see
        # _canvas_size); pre-compute the same frame to find which cell the
        # aircraft lands in, so the fake mouse events can target it.
        frame = render.render_frame(cfg.lat, cfg.lon, cfg.radius_miles,
                                     table.snapshot(), 40, 20)
        (row, col), hx = next(iter(frame.aircraft_cells.items()))
        self.assertEqual(hx, "ABC123")

        stdscr = _FakeStdscr(height=22, width=44,
                              chars=[curses.KEY_MOUSE, curses.KEY_MOUSE, ord("q")])
        feed = SimpleNamespace(connected=True)

        # First getmouse() call reports pure pointer motion (no click bits
        # set) and must be ignored; second is a real click at the same
        # cell and must select the aircraft.
        mouse_events = [
            (0, col, row, 0, curses.REPORT_MOUSE_POSITION),
            (0, col, row, 0, curses.BUTTON1_CLICKED),
        ]

        with mock.patch.object(curses, "curs_set"), \
                mock.patch.object(curses, "mousemask"), \
                mock.patch.object(curses, "getmouse", side_effect=mouse_events):
            app._curses_main(stdscr, cfg, table, feed)

        detail_row = stdscr.height - 1
        detail_texts = [text for r, _c, text in stdscr.addstr_calls if r == detail_row]

        self.assertEqual(detail_texts[0], "")
        self.assertEqual(detail_texts[1], "", "a motion-only event must not select an aircraft")
        self.assertIn("ABC123", detail_texts[2])


if __name__ == "__main__":
    unittest.main()
