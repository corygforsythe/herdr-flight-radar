# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.
- Run tests with `python3 -m unittest discover -s test -p 'test_*.py'`. Pure
  stdlib, no pip deps, no pytest — keep it that way so the plugin runs under
  whatever `python3` is already on the minimal PATH Herdr spawns commands
  with (see `bin/run-python.sh`).
- Canonical distance unit everywhere in this codebase is **statute miles**
  (`geo.py`, config's `radius_miles`, on-screen readouts). Don't introduce km
  or nautical miles without converting at the boundary.
- Data ingestion talks to dump1090's SBS/BaseStation port (127.0.0.1:30003)
  over raw TCP, not `--write-json`/HTTP. That's deliberate: SBS on 30003 is
  what any `--net`-enabled dump1090 build serves by default regardless of
  fork/config, so "is one already running" and "read from it" share one
  code path (`dump1090_manager.is_reachable` / `feed.SbsFeed`) whether we
  started the process or found an existing one. See `sbs.py`'s module
  docstring for the wire format.
- `dump1090_manager.Dump1090Process.start()` intentionally omits
  `--net-only` so it actually attempts real SDR reception; don't add it
  back without re-reading why (it would silently succeed forever with zero
  aircraft, including when no receiver is attached — defeats the
  device-busy/no-SDR error path the plugin is supposed to surface).
- Confirmed herdr 0.8.2 quirks when working with this plugin's manifest
  (re-verify if the herdr version has moved):
  - `herdr plugin pane open --target-pane X --workspace Y` together fails
    `invalid_params`; send only one.
  - `herdr plugin action invoke` runs against the **currently UI-focused**
    pane/workspace, not the CLI caller's own `$HERDR_PANE_ID` — don't
    invoke it casually from an unrelated shell; it can open/focus a split
    pane in someone else's live session. Verified by opening one in the
    user's actual firstmate workspace during initial development; cleaned
    up with `herdr plugin pane close <id>`, which restored prior focus.
  - The plugin runtime's `PATH` can be as minimal as
    `/usr/bin:/bin:/usr/sbin:/sbin`. `/usr/bin/python3` (Apple's system
    Python) is already on that PATH, but `dump1090` (typically
    `/opt/homebrew/bin/dump1090`) is not — `bin/run-python.sh` extends PATH
    before exec'ing python3 so `shutil.which("dump1090")` still finds it.
- `render._place_label` (see its docstring) draws each aircraft's label to
  the right of its glyph by default, trying left, then above/below,
  when the label wouldn't otherwise fully fit (grid edge, ring, or
  another aircraft's glyph/label) — don't assume a label cell is always
  at `col + 1`, or on the glyph's own row; use `Frame.aircraft_spans` for
  the actual drawn range(s) (`render_frame` emits two spans for one
  aircraft when its label landed on a different row than its glyph).
  Hit-testing still only ever uses the glyph's own cell (`aircraft_cells`),
  independent of label placement. `render_frame` draws every aircraft's
  glyph before placing any label (so a later glyph can't clobber an
  earlier label) and places labels in a fixed order (sorted by hex) so
  collisions resolve the same way every frame. Disclosed limit: in an
  extremely dense cluster there can be more aircraft than non-colliding
  candidate positions, so some overlap can still occur there — the
  search is best-effort, not a guarantee of full non-overlap at every
  density.
- Mouse click-to-detail uses `curses.mousemask`, not manual SGR escape
  parsing — verified end-to-end via a real PTY harness (inject raw mouse
  bytes, confirm the hit aircraft's detail line renders). That harness
  found this machine's ncurses negotiates legacy X10 mouse mode
  (`\x1b[?1000h`) for the `TERM` in use, not SGR (`\x1b[?1006h`); `curses`
  handles whichever the terminal actually negotiates, so this is a note
  for anyone re-running that kind of raw-byte test, not a plugin bug.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
