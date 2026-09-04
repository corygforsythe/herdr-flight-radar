"""Orchestrates the Flight Radar pane: config, dump1090 lifecycle, the SBS
feed thread, and either the interactive curses TUI or a plain-text
fallback when stdout is not a TTY.
"""
import curses
import sys
import time

from . import config as config_mod
from . import dump1090_manager
from . import feed as feed_mod
from . import geo
from . import render
from . import sbs

REFRESH_SECONDS = 1.0
STATUS_ROWS = 2
CLICK_BSTATE_MASK = (
    curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED | curses.BUTTON1_RELEASED
    | curses.BUTTON1_DOUBLE_CLICKED | curses.BUTTON1_TRIPLE_CLICKED
)

CHART_COLOR_PAIR = 1
AIRCRAFT_COLOR_PAIR = 2


def _init_colors():
    """Set up chart-vs-aircraft color pairs if the terminal supports color.

    Returns True if colors were set up (callers should use the color-pair
    attrs above), False if this terminal can't do color and callers must
    fall back to the plain, uncolored rendering.
    """
    try:
        if not curses.has_colors() or curses.COLORS < 8:
            return False
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
            chart_fg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
            chart_fg = curses.COLOR_WHITE
        # Aircraft (the important moving thing) get a bright, high-contrast
        # color; chart chrome (range rings, cardinal markers) stays
        # dim/default so aircraft stand out against it on both light and
        # dark terminals.
        curses.init_pair(CHART_COLOR_PAIR, chart_fg, bg)
        curses.init_pair(AIRCRAFT_COLOR_PAIR, curses.COLOR_CYAN, bg)
        return True
    except curses.error:
        # No initialized screen (e.g. outside a real curses.wrapper session)
        # or an environment that otherwise can't do color negotiation at
        # all; fall back to the plain, uncolored rendering rather than
        # crashing or corrupting output.
        return False


def format_detail(ac, center_lat, center_lon):
    distance = geo.haversine_miles(center_lat, center_lon, ac.lat, ac.lon)
    bearing = geo.bearing_deg(center_lat, center_lon, ac.lat, ac.lon)
    callsign = ac.callsign or "(unknown)"
    alt = "{:.0f} ft".format(ac.altitude_ft) if ac.altitude_ft is not None else "unknown"
    speed = "{:.0f} kt".format(ac.speed_kt) if ac.speed_kt is not None else "unknown"
    heading = "{:.0f}°".format(ac.track_deg) if ac.track_deg is not None else "unknown"
    return (
        "{cs}  hex={hex}  alt={alt}  spd={speed}  hdg={heading}  "
        "{dist:.1f}mi @ {brg:.0f}°".format(
            cs=callsign, hex=ac.hex, alt=alt, speed=speed, heading=heading,
            dist=distance, brg=bearing,
        )
    )


def visible_sorted(cfg, table):
    aircraft = table.snapshot()
    with_distance = [
        (geo.haversine_miles(cfg.lat, cfg.lon, ac.lat, ac.lon), ac)
        for ac in aircraft
    ]
    in_range = [(dist, ac) for dist, ac in with_distance if dist <= cfg.radius_miles]
    in_range.sort(key=lambda pair: pair[0])
    return [ac for _dist, ac in in_range]


def run_plain_text(cfg, table):
    """Non-interactive fallback for non-TTY stdout: print one snapshot."""
    print("Flight Radar - center {:.4f},{:.4f}  radius {:.0f}mi".format(
        cfg.lat, cfg.lon, cfg.radius_miles))
    visible = visible_sorted(cfg, table)
    if not visible:
        print("(no aircraft in range)")
        return
    for ac in visible:
        print(format_detail(ac, cfg.lat, cfg.lon))


def _wait_for_dismiss():
    try:
        input("\nPress Enter to close this pane...")
    except (EOFError, KeyboardInterrupt):
        pass


def _canvas_size(height, width):
    avail_h = max(1, height - STATUS_ROWS)
    avail_w = max(2, width)
    height_cells = avail_h
    width_cells = height_cells * 2
    if width_cells > avail_w:
        width_cells = avail_w - (avail_w % 2) or 2
        height_cells = max(1, width_cells // 2)
    return height_cells, width_cells


def _curses_main(stdscr, cfg, table, feed):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(int(REFRESH_SECONDS * 1000))
    curses.mousemask(curses.ALL_MOUSE_EVENTS)
    color = _init_colors()

    selected_hex = None

    while True:
        height, width = stdscr.getmaxyx()
        height_cells, width_cells = _canvas_size(height, width)

        table.expire_stale()
        aircraft = table.snapshot()
        frame = render.render_frame(
            cfg.lat, cfg.lon, cfg.radius_miles, aircraft,
            width_cells, height_cells,
        )

        stdscr.erase()
        chart_attr = curses.color_pair(CHART_COLOR_PAIR) if color else curses.A_NORMAL
        for i, line in enumerate(frame.lines):
            if i >= height - STATUS_ROWS:
                break
            try:
                stdscr.addstr(i, 0, line[:width], chart_attr)
            except curses.error:
                pass

        if color:
            aircraft_attr = curses.color_pair(AIRCRAFT_COLOR_PAIR) | curses.A_BOLD
            for row, col, length in frame.aircraft_spans:
                if row >= height - STATUS_ROWS or col >= width:
                    continue
                span_len = min(length, width - col)
                try:
                    stdscr.chgat(row, col, span_len, aircraft_attr)
                except curses.error:
                    pass

        if selected_hex is not None:
            selected_cell = next(
                (cell for cell, hx in frame.aircraft_cells.items() if hx == selected_hex),
                None,
            )
            if selected_cell is not None:
                row, col = selected_cell
                highlight_attr = curses.A_REVERSE | curses.A_BOLD
                if color:
                    highlight_attr |= curses.color_pair(AIRCRAFT_COLOR_PAIR)
                try:
                    stdscr.chgat(row, col, 1, highlight_attr)
                except curses.error:
                    pass

        status_row = height - 2
        conn = "connected" if feed.connected else "reconnecting..."
        status = "aircraft in range: {n}  feed: {conn}  [click] select  [q] quit".format(
            n=len(frame.aircraft_cells), conn=conn,
        )
        try:
            stdscr.addstr(status_row, 0, status[: max(0, width - 1)])
        except curses.error:
            pass

        detail_row = height - 1
        detail = ""
        if selected_hex is not None:
            match = next((a for a in aircraft if a.hex == selected_hex), None)
            detail = (
                format_detail(match, cfg.lat, cfg.lon)
                if match is not None
                else "{} not currently in range".format(selected_hex)
            )
        try:
            stdscr.addstr(detail_row, 0, detail[: max(0, width - 1)])
        except curses.error:
            pass

        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord("q"), ord("Q")):
            return
        if ch == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
            except curses.error:
                continue
            if not (bstate & CLICK_BSTATE_MASK):
                continue
            hit = frame.hex_at(my, mx)
            if hit is not None:
                selected_hex = hit


def main():
    try:
        cfg = config_mod.load_config()
    except config_mod.ConfigError as exc:
        sys.stderr.write(str(exc) + "\n")
        if sys.stdout.isatty():
            print(str(exc))
            _wait_for_dismiss()
        return 1

    try:
        dump_proc, _owned = dump1090_manager.ensure_dump1090(cfg.lat, cfg.lon)
    except dump1090_manager.Dump1090Error as exc:
        sys.stderr.write(str(exc) + "\n")
        if sys.stdout.isatty():
            print(str(exc))
            _wait_for_dismiss()
        return 1

    table = sbs.AircraftTable()
    feed = feed_mod.SbsFeed(
        dump1090_manager.DEFAULT_HOST, dump1090_manager.DEFAULT_SBS_PORT, table,
    ).start()

    try:
        if not sys.stdout.isatty():
            time.sleep(1.5)  # let a little data accumulate before the one snapshot
            run_plain_text(cfg, table)
        else:
            curses.wrapper(_curses_main, cfg, table, feed)
    finally:
        feed.stop()
        if dump_proc is not None:
            dump_proc.stop()

    return 0
