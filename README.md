# herdr-flight-radar

A [Herdr](https://herdr.dev) plugin: a real-time ADS-B flight radar rendered
as a TUI split pane, backed by [dump1090](https://github.com/antirez/dump1090)
(tested against the dump1090-fa fork), centered on a user-configured
location.

The radar draws range rings and cardinal (N/E/S/W) markers on a Unicode
braille sub-cell grid, plots each in-range aircraft as a heading arrow
labeled with its callsign (or ICAO hex if no callsign has been received
yet), and updates live as dump1090 reports new positions. Click an
aircraft's arrow or its label text to see its callsign, altitude, speed,
and heading in the status line. On terminals with color support, aircraft
are drawn in a bright, high-contrast color distinct from the dimmer chart
chrome; terminals without color support fall back to the existing
uncolored rendering.

## Install / link

Requires herdr >= 0.8.0 and a `dump1090` binary on the machine (any build
that supports `--net`, e.g. dump1090-fa). No other dependencies — the
plugin is pure-stdlib Python 3, run through `bin/run-python.sh`, a small
wrapper that extends `PATH` so `python3` and `dump1090` resolve even under
the minimal `PATH` Herdr's plugin runtime spawns commands with.

```sh
herdr plugin link /path/to/herdr-flight-radar
herdr plugin list   # confirm it shows up enabled
```

Open the radar with the `prefix+r` keybinding (bound to the "Open Flight
Radar" plugin action), or manually:

```sh
herdr plugin action invoke open --plugin dev.coryforsythe.herdr-flight-radar
```

## Configuration

The plugin reads `$HERDR_PLUGIN_CONFIG_DIR/config.json` (find that path
with `herdr plugin config-dir dev.coryforsythe.herdr-flight-radar`). See
`config.example.json` in this repo for a template:

```json
{
  "location": { "lat": 47.6062, "lon": -122.3321 },
  "radius_miles": 100
}
```

- `location` (required): the radar's center point, in decimal degrees.
- `radius_miles` (optional, default `100`): display radius. **Statute
  miles are the canonical unit everywhere in this codebase** — the config
  key, internal geometry (`geo.py`), and the on-screen distance readout all
  use miles, not km or nautical miles.

If the file is missing, or has no `location`, the pane prints a clear
message explaining what to add and exactly where, instead of a blank
screen or a crash. There is no OS location-services integration by
design — location is always explicit user configuration.

## How dump1090 is located, started, and stopped

On open, the pane:

1. Tries to connect to `127.0.0.1:30003` — dump1090's SBS/BaseStation TCP
   output, which any `--net`-enabled dump1090 build serves on that port by
   default. If something is already listening there, the plugin treats it
   as an existing usable instance and **never touches its lifecycle** —
   it only reads from it.
2. Otherwise, it looks for a `dump1090` binary (via `PATH`, then
   `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`) and launches it
   itself with real reception enabled (`--net --net-bind-address 127.0.0.1
   --net-sbs-port 30003 --lat <lat> --lon <lon>`) — no `--net-only`, so it
   actually attempts to open SDR hardware and decode real traffic when a
   receiver is present.
3. If dump1090 exits immediately (no SDR attached, or the device is
   already claimed by another process), the pane shows dump1090's own
   diagnostic output under a plain-language explanation and waits for
   Enter, instead of looping or crashing.
4. Only a dump1090 process **this plugin itself launched** is stopped when
   the pane closes; an instance that was already running when the pane
   opened is left exactly as it was found.

Aircraft state (callsign, altitude, ground speed, track, position) is
accumulated per ICAO hex address from the streamed SBS feed — that
protocol reports each field incrementally across several message types
rather than all at once, which is the standard way dump1090 clients build
up a full picture per aircraft (see `src/herdr_flight_radar/sbs.py`). The
on-screen frame refreshes once per second, matching dump1090's own update
cadence.

## Non-interactive fallback

If stdout is not a TTY, the pane program prints one plain-text snapshot
(aircraft in range, sorted by distance) instead of drawing the curses UI.
All of the parsing, filtering, and positioning logic lives in plain
functions (`geo.py`, `sbs.py`, `render.py`) that are unit-tested directly
and don't require a terminal at all — see `test/`.

## Verification

- `python3 -m unittest discover -s test -p 'test_*.py'` — 79 unit tests
  covering haversine/bearing math, SBS parsing and aircraft-state merging,
  config validation, dump1090 process management (mocked), radar
  projection/rendering, and mouse click-vs-motion filtering.
- Linked against a real local herdr 0.8.2 install (`herdr plugin link`,
  `herdr plugin list`) and opened via the plugin action end-to-end in a
  live pane.
- Verified against a synthetic SBS server (two synthetic aircraft) that
  the feed parser, haversine filtering, distance/bearing math, and
  plain-text detail output are all correct.
- Verified against the machine's real, already-installed `dump1090-fa`
  and an attached RTL-SDR dongle: no SDR hardware was available for a
  clean receive during this pass (the device was already claimed by
  another running `dump1090 --interactive` process), so the pane's error
  path was exercised for real — it printed dump1090's own
  `usb_claim_interface` diagnostic under a clear explanation and waited
  for Enter, rather than crashing or leaving a blank pane. It did not
  start a duplicate dump1090 and left the pre-existing process untouched.
- Mouse click-to-detail was verified against a real PTY (Python's `pty`
  module driving the actual `radar_tui.py` process under `curses`, not a
  mock): with a synthetic aircraft rendered on-screen, an injected mouse
  click at that exact cell selected it, applied the reverse/bold
  highlight, and printed its full detail line (callsign, hex, altitude,
  speed, heading). One implementation note from that run: this machine's
  ncurses only negotiated legacy X10 mouse mode (`\x1b[?1000h`) rather
  than SGR (`\x1b[?1006h`) for the `TERM` in use — `curses.mousemask()`
  handles whichever protocol the terminal actually negotiates
  transparently, so this doesn't affect the plugin itself, but it means a
  raw SGR-encoded click (as opposed to one generated by an actual mouse
  in a real terminal emulator) won't register. This was not tested inside
  a specific GUI terminal emulator's own window (iTerm2/Terminal.app) —
  only via a direct PTY — so treat "clicking with a physical mouse in
  your terminal app of choice" as verified at the protocol/logic level,
  not confirmed pixel-for-pixel in every terminal emulator.
