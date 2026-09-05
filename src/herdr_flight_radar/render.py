"""Polar radar rendering onto a Unicode braille sub-cell grid.

Each terminal cell holds a 2 (wide) x 4 (tall) braille dot grid. Given
typical terminal font metrics (~1:2 character cell width:height), that 2x4
dot grid works out to roughly *square* dot spacing in real screen space:
dot pitch horizontal = cell_width / 2, dot pitch vertical = cell_height / 4
= (2 * cell_width) / 4 = cell_width / 2. That is why callers should size
the canvas with width_cells == 2 * height_cells: it keeps range rings
visually circular instead of elliptical.
"""
import math

from . import geo

BRAILLE_BASE = 0x2800
DOT_BITS = {
    (0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (0, 3): 0x40,
    (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (1, 3): 0x80,
}

# Index by an 8-way bucket of true track, 0 = north, going clockwise.
HEADING_GLYPHS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]
UNKNOWN_HEADING_GLYPH = "●"

RING_FRACTIONS = (0.25, 0.5, 0.75, 1.0)

MAX_LABEL_LEN = 8


def aircraft_label(ac):
    """Callsign if the feed has reported one, else the ICAO hex."""
    callsign = (ac.callsign or "").strip()
    return (callsign or ac.hex)[:MAX_LABEL_LEN]


class BrailleCanvas:
    def __init__(self, width_cells, height_cells):
        self.width_cells = width_cells
        self.height_cells = height_cells
        self.px_width = width_cells * 2
        self.px_height = height_cells * 4
        self._cells = [[0] * width_cells for _ in range(height_cells)]

    def set_px(self, x, y):
        x, y = int(round(x)), int(round(y))
        if x < 0 or y < 0 or x >= self.px_width or y >= self.px_height:
            return
        col, row = x // 2, y // 4
        bit = DOT_BITS[(x % 2, y % 4)]
        self._cells[row][col] |= bit

    def char_at(self, col, row):
        bits = self._cells[row][col]
        return chr(BRAILLE_BASE + bits) if bits else " "

    def rows(self):
        return [
            "".join(self.char_at(c, r) for c in range(self.width_cells))
            for r in range(self.height_cells)
        ]


def heading_glyph(track_deg):
    if track_deg is None:
        return UNKNOWN_HEADING_GLYPH
    bucket = int(((track_deg % 360.0) + 22.5) // 45.0) % 8
    return HEADING_GLYPHS[bucket]


def project_to_px(lat, lon, center_lat, center_lon, radius_miles, canvas):
    """Return (x, y) pixel coords on canvas, or None if outside the radius."""
    distance = geo.haversine_miles(center_lat, center_lon, lat, lon)
    if distance > radius_miles:
        return None
    bearing = geo.bearing_deg(center_lat, center_lon, lat, lon)
    theta = math.radians(bearing)
    nx = math.sin(theta) * (distance / radius_miles)
    ny = -math.cos(theta) * (distance / radius_miles)

    px_r = min(canvas.px_width, canvas.px_height) / 2.0 - 1
    cx, cy = canvas.px_width / 2.0, canvas.px_height / 2.0
    return cx + nx * px_r, cy + ny * px_r


def _draw_ring(canvas, fraction):
    px_r = (min(canvas.px_width, canvas.px_height) / 2.0 - 1) * fraction
    cx, cy = canvas.px_width / 2.0, canvas.px_height / 2.0
    steps = max(72, int(px_r * 8))
    for i in range(steps):
        theta = 2 * math.pi * i / steps
        canvas.set_px(cx + px_r * math.sin(theta), cy - px_r * math.cos(theta))


def _cell_for_bearing(canvas, bearing_deg_, fraction=1.0):
    px_r = (min(canvas.px_width, canvas.px_height) / 2.0 - 1) * fraction
    cx, cy = canvas.px_width / 2.0, canvas.px_height / 2.0
    theta = math.radians(bearing_deg_)
    x = cx + px_r * math.sin(theta)
    y = cy - px_r * math.cos(theta)
    col = min(canvas.width_cells - 1, max(0, int(x) // 2))
    row = min(canvas.height_cells - 1, max(0, int(y) // 4))
    return row, col


def _blank_run(grid, row, col, step):
    """Count contiguous blank cells in `row` starting after `col`, stepping by `step`."""
    width_cells = len(grid[0]) if grid else 0
    count = 0
    c = col + step
    while 0 <= c < width_cells and grid[row][c] == " ":
        count += 1
        c += step
    return count


def _fits(grid, row, col_start, length):
    """True if [col_start, col_start + length) is in-bounds and all blank
    in `row`. `grid[row]` must already reflect every obstacle placed so
    far this frame (chart content, other glyphs, other labels)."""
    width = len(grid[0]) if grid else 0
    if col_start < 0 or col_start + length > width:
        return False
    return all(grid[row][col_start + i] == " " for i in range(length))


def _place_label(grid, row, col, label):
    """Write label into blank cells beside (row, col), never letting a
    label that would otherwise fit run off the grid edge, into static
    chart content (a ring), or into another aircraft's already-placed
    glyph or label.

    Tries a fixed set of candidates in priority order: immediately right
    of the glyph (matching prior behavior), then immediately left, then
    right and left one row above, then right and left one row below.
    The first candidate that fits entirely in blank cells wins. Callers
    must place every aircraft's glyph before placing any aircraft's
    label (so a later glyph can never clobber an earlier label) and
    must place labels in a fixed deterministic order (e.g. by hex) so
    the same frame always resolves collisions the same way.

    If nothing fits fully, falls back to the prior behavior of
    truncating on the right of the glyph's own row, keeping a crowded
    radar legible when there's genuinely no room to show the whole
    label anywhere -- this is the disclosed density limit: in an
    extremely tight cluster there can be more aircraft than
    non-overlapping candidate positions.

    Returns (row, col_start, length) of the placed label span -- the
    row may differ from the glyph's row when an above/below candidate
    was used -- so callers can compute the full glyph+label span(s) for
    rendering purposes.
    """
    label_len = len(label)
    height = len(grid)

    candidates = [(row, col + 1), (row, col - label_len)]
    if row - 1 >= 0:
        candidates.append((row - 1, col + 1))
        candidates.append((row - 1, col - label_len))
    if row + 1 < height:
        candidates.append((row + 1, col + 1))
        candidates.append((row + 1, col - label_len))

    if label_len:
        for r, start in candidates:
            if _fits(grid, r, start, label_len):
                for i, ch in enumerate(label):
                    grid[r][start + i] = ch
                return r, start, label_len

    right_space = _blank_run(grid, row, col, +1)
    n = min(label_len, right_space)
    start = col + 1
    for i, ch in enumerate(label[:n]):
        grid[row][start + i] = ch
    return row, start, n


class Frame:
    def __init__(self, lines, aircraft_cells, center_cell, aircraft_spans=(),
                 hit_cells=None):
        self.lines = lines
        self.aircraft_cells = aircraft_cells  # {(row, col): hex} -- glyph cells only
        self.center_cell = center_cell
        # (row, col_start, length) covering each aircraft's glyph + label,
        # for color rendering.
        self.aircraft_spans = aircraft_spans
        # {(row, col): hex} for every cell of the glyph *and* its label,
        # wherever _place_label actually drew it this frame. Used for
        # click-to-select so clicking the label text selects the aircraft
        # too, not just its glyph.
        self.hit_cells = hit_cells if hit_cells is not None else dict(aircraft_cells)

    def hex_at(self, row, col):
        return self.hit_cells.get((row, col))


def render_frame(center_lat, center_lon, radius_miles, aircraft, width_cells,
                  height_cells):
    """Render one radar frame.

    aircraft: iterable of objects with .hex, .callsign, .lat, .lon,
    .track_deg
    Returns a Frame with plain text lines (range rings, cardinal markers,
    a heading glyph plus an adjacent identifying label per visible
    aircraft) plus a cell -> hex map for mouse-click hit testing. The hit
    map covers both the glyph's own cell and wherever its label actually
    landed this frame (right, left, above, or below), so clicking either
    selects the aircraft.
    """
    canvas = BrailleCanvas(width_cells, height_cells)
    for frac in RING_FRACTIONS:
        _draw_ring(canvas, frac)

    grid = [list(row) for row in canvas.rows()]

    for bearing_, label in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
        row, col = _cell_for_bearing(canvas, bearing_, fraction=1.0)
        grid[row][col] = label

    center_row, center_col = height_cells // 2, width_cells // 2
    grid[center_row][center_col] = "+"

    # Two passes: place every aircraft's glyph first, so a later
    # aircraft's glyph can never clobber an earlier aircraft's label
    # (see _place_label's docstring). Labels are then placed in a fixed
    # order (by hex) so collisions resolve the same way every frame.
    positions = []
    for ac in aircraft:
        px = project_to_px(ac.lat, ac.lon, center_lat, center_lon, radius_miles, canvas)
        if px is None:
            continue
        x, y = px
        col = min(width_cells - 1, max(0, int(x) // 2))
        row = min(height_cells - 1, max(0, int(y) // 4))
        positions.append((row, col, ac))

    aircraft_cells = {}
    for row, col, ac in positions:
        grid[row][col] = heading_glyph(ac.track_deg)
        aircraft_cells[(row, col)] = ac.hex

    aircraft_spans = []
    hit_cells = dict(aircraft_cells)
    for row, col, ac in sorted(positions, key=lambda p: p[2].hex):
        label_row, label_start, label_len = _place_label(grid, row, col, aircraft_label(ac))
        for i in range(label_len):
            hit_cells[(label_row, label_start + i)] = ac.hex
        if label_len and label_row != row:
            aircraft_spans.append((row, col, 1))
            aircraft_spans.append((label_row, label_start, label_len))
        else:
            span_start = min(col, label_start) if label_len else col
            span_end = max(col, label_start + label_len - 1) if label_len else col
            aircraft_spans.append((row, span_start, span_end - span_start + 1))

    lines = ["".join(row) for row in grid]
    return Frame(lines=lines, aircraft_cells=aircraft_cells,
                 center_cell=(center_row, center_col),
                 aircraft_spans=aircraft_spans, hit_cells=hit_cells)
