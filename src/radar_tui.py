#!/usr/bin/env python3
"""Pane entrypoint: real-time ADS-B flight radar TUI backed by dump1090."""
import os
import sys

_ROOT = os.environ.get("HERDR_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from herdr_flight_radar.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
