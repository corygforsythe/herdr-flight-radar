"""Detect, launch, and clean up a dump1090 process.

We standardize on dump1090's SBS/BaseStation TCP output (default port
30003), which is enabled by any invocation that turns on networking
(--net or --net-only) across dump1090 and dump1090-fa builds, regardless
of which JSON/HTTP options that particular build or install happens to
support. That lets "is one already running" and "read data from it" share
one code path (see sbs.py) whether we started the process or found an
existing one already serving on that port.
"""
import os
import shutil
import socket
import subprocess
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_SBS_PORT = 30003

_EXTRA_BINARY_LOCATIONS = [
    "/opt/homebrew/bin/dump1090",
    "/usr/local/bin/dump1090",
    "/usr/bin/dump1090",
]


class Dump1090Error(Exception):
    """Raised when dump1090 cannot be located or fails to start. User-facing."""


def is_reachable(host=DEFAULT_HOST, port=DEFAULT_SBS_PORT, timeout=1.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_binary():
    found = shutil.which("dump1090")
    if found:
        return found
    for candidate in _EXTRA_BINARY_LOCATIONS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class Dump1090Process:
    """Tracks a dump1090 process we launched, so we only ever stop our own."""

    def __init__(self):
        self._proc = None

    @property
    def owned(self):
        return self._proc is not None

    def start(self, lat, lon, host=DEFAULT_HOST, port=DEFAULT_SBS_PORT,
              startup_timeout=8.0):
        binary = find_binary()
        if binary is None:
            raise Dump1090Error(
                "dump1090 is not running and the dump1090 binary could not be "
                "found on PATH or in common install locations. Install it "
                "(see https://github.com/antirez/dump1090 or your platform's "
                "dump1090-fa package) or start it yourself with networking "
                "enabled on port {port}.".format(port=port)
            )

        # Deliberately real reception (no --net-only): this must actually try
        # to open the SDR so real traffic gets decoded when hardware is
        # present, and fail loudly (caught below) when it is not.
        args = [
            binary,
            "--net",
            "--net-bind-address", host,
            "--net-sbs-port", str(port),
            "--lat", str(lat),
            "--lon", str(lon),
            "--quiet",
        ]
        try:
            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            raise Dump1090Error("Failed to launch dump1090 ({binary}): {err}".format(
                binary=binary, err=exc,
            ))

        deadline = time.time() + startup_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ""
                raise Dump1090Error(
                    "dump1090 exited immediately (exit code {code}). This "
                    "usually means no SDR device is attached or it is busy. "
                    "Output:\n{output}".format(code=proc.returncode, output=output.strip())
                )
            if is_reachable(host, port, timeout=0.5):
                self._proc = proc
                return self
            time.sleep(0.2)

        proc.terminate()
        raise Dump1090Error(
            "dump1090 started but never opened port {port} within "
            "{timeout:.0f}s; giving up.".format(port=port, timeout=startup_timeout)
        )

    def stop(self):
        if self._proc is None:
            return
        proc, self._proc = self._proc, None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def ensure_dump1090(lat, lon, host=DEFAULT_HOST, port=DEFAULT_SBS_PORT):
    """Return (Dump1090Process|None, owned_by_us: bool).

    If a usable instance is already listening on the SBS port, we use it
    as-is and never touch its lifecycle. Otherwise we launch our own and
    hand back the handle so the caller can stop it (and only it) on exit.
    """
    if is_reachable(host, port):
        return None, False

    proc = Dump1090Process()
    proc.start(lat, lon, host=host, port=port)
    return proc, True
