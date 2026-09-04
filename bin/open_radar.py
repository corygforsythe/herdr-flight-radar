#!/usr/bin/env python3
"""Plugin action: open the Flight Radar pane as a split, bound to a keybinding."""
import os
import subprocess
import sys


def main():
    herdr = os.environ.get("HERDR_BIN_PATH", "herdr")
    plugin_id = os.environ.get("HERDR_PLUGIN_ID")
    pane_id = os.environ.get("HERDR_PANE_ID")

    if not plugin_id:
        sys.stderr.write("open_radar: HERDR_PLUGIN_ID not set in environment\n")
        return 1

    cmd = [
        herdr, "plugin", "pane", "open",
        "--plugin", plugin_id,
        "--entrypoint", "radar",
        "--placement", "split",
        "--focus",
    ]
    # --target-pane and --workspace together fail with invalid_params on this
    # herdr version; send only one. Anchor the split off the calling pane
    # when we know it, otherwise let herdr pick the focused workspace.
    if pane_id:
        cmd += ["--target-pane", pane_id]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout or "failed to open radar pane\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
