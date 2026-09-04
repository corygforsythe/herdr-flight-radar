import io
import os
import socket
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from herdr_flight_radar import dump1090_manager as dm


class IsReachableTest(unittest.TestCase):
    def test_true_when_something_is_listening(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        try:
            self.assertTrue(dm.is_reachable("127.0.0.1", port, timeout=1.0))
        finally:
            srv.close()

    def test_false_when_nothing_is_listening(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
        srv.close()  # bound and released; almost certainly refused now
        self.assertFalse(dm.is_reachable("127.0.0.1", port, timeout=1.0))


class EnsureDump1090Test(unittest.TestCase):
    def test_uses_existing_instance_without_starting_one(self):
        with mock.patch.object(dm, "is_reachable", return_value=True), \
             mock.patch.object(dm.Dump1090Process, "start") as mock_start:
            proc, owned = dm.ensure_dump1090(47.6, -122.3)
        self.assertIsNone(proc)
        self.assertFalse(owned)
        mock_start.assert_not_called()

    def test_starts_own_instance_when_none_reachable(self):
        with mock.patch.object(dm, "is_reachable", return_value=False), \
             mock.patch.object(dm.Dump1090Process, "start", autospec=True) as mock_start:
            mock_start.side_effect = lambda self, *a, **k: setattr(self, "_proc", mock.Mock())
            proc, owned = dm.ensure_dump1090(47.6, -122.3)
        self.assertIsNotNone(proc)
        self.assertTrue(owned)
        mock_start.assert_called_once()


class Dump1090ProcessStartTest(unittest.TestCase):
    def test_raises_when_binary_missing(self):
        with mock.patch.object(dm, "find_binary", return_value=None):
            proc = dm.Dump1090Process()
            with self.assertRaises(dm.Dump1090Error) as ctx:
                proc.start(47.6, -122.3)
            self.assertIn("could not be found", str(ctx.exception))

    def test_raises_readable_error_when_process_exits_immediately(self):
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = 1
        fake_proc.stdout = io.StringIO("usbcheck: no supported devices found\n")

        with mock.patch.object(dm, "find_binary", return_value="/usr/bin/dump1090"), \
             mock.patch("subprocess.Popen", return_value=fake_proc):
            proc = dm.Dump1090Process()
            with self.assertRaises(dm.Dump1090Error) as ctx:
                proc.start(47.6, -122.3, startup_timeout=1.0)
            self.assertIn("no SDR device", str(ctx.exception))
            self.assertIn("no supported devices found", str(ctx.exception))

    def test_succeeds_once_port_becomes_reachable(self):
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None  # still running

        reachable_calls = {"n": 0}

        def fake_is_reachable(host, port, timeout=1.0):
            reachable_calls["n"] += 1
            return reachable_calls["n"] >= 2

        with mock.patch.object(dm, "find_binary", return_value="/usr/bin/dump1090"), \
             mock.patch("subprocess.Popen", return_value=fake_proc), \
             mock.patch.object(dm, "is_reachable", side_effect=fake_is_reachable):
            proc = dm.Dump1090Process()
            result = proc.start(47.6, -122.3, startup_timeout=5.0)

        self.assertIs(result, proc)
        self.assertTrue(proc.owned)

    def test_stop_only_terminates_process_we_started(self):
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None
        proc = dm.Dump1090Process()
        proc._proc = fake_proc  # simulate an owned, running process

        proc.stop()

        fake_proc.terminate.assert_called_once()
        self.assertFalse(proc.owned)

    def test_stop_is_a_noop_when_we_never_started_anything(self):
        proc = dm.Dump1090Process()
        proc.stop()  # must not raise
        self.assertFalse(proc.owned)


if __name__ == "__main__":
    unittest.main()
