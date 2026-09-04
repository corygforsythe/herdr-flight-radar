"""Background thread that streams dump1090's SBS feed into an AircraftTable.

dump1090 pushes one line per decoded message rather than being polled, but
we still treat "how fresh is the data" the same way a ~1s poll loop would:
the render loop wakes on its own timer and reads whatever has accumulated
in the table since the last frame (see app.py).
"""
import socket
import threading
import time

from . import sbs


class SbsFeed:
    def __init__(self, host, port, table, reconnect_delay=2.0):
        self._host = host
        self._port = port
        self._table = table
        self._reconnect_delay = reconnect_delay
        self._lock = threading.Lock()
        self._connected = False
        self._last_error = None
        self._stop = threading.Event()
        self._thread = None

    @property
    def connected(self):
        with self._lock:
            return self._connected

    @property
    def last_error(self):
        with self._lock:
            return self._last_error

    def _set_status(self, connected, error=None):
        with self._lock:
            self._connected = connected
            self._last_error = error

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self):
        while not self._stop.is_set():
            try:
                with socket.create_connection((self._host, self._port), timeout=5) as sock:
                    sock.settimeout(1.0)
                    self._set_status(True)
                    buf = b""
                    while not self._stop.is_set():
                        try:
                            chunk = sock.recv(4096)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            self._table.update_from_line(line.decode("ascii", "ignore"))
            except OSError as exc:
                self._set_status(False, str(exc))

            if self._stop.is_set():
                break
            time.sleep(self._reconnect_delay)
