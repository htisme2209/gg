"""Offline checks for Frida server compatibility; never contact a device."""
import io
import lzma
import sys
import types
import unittest
from unittest.mock import Mock, patch

import ultra0


class FridaEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.running = True
        self.version = "17.27.1"
        self.staged_version = "16.5.9"
        self.abi = "x86_64"
        self.root = True
        self.calls = []
        self.fail_push = False
        self.device = Mock()
        self.device.enumerate_processes.return_value = []
        self.frida = types.SimpleNamespace(
            __version__="16.5.9", get_device=Mock(return_value=self.device))
        self.network = Mock(side_effect=lambda *a, **k: io.BytesIO(lzma.compress(b"offline-test-server")))
        self.patches = [
            patch.dict(sys.modules, {"frida": self.frida}),
            patch.object(ultra0, "SERIAL", "127.0.0.1:16384"),
            patch.object(ultra0, "sh", side_effect=self.shell),
            patch.object(ultra0, "note"), patch.object(ultra0, "ok"),
            patch.object(ultra0, "warn"), patch.object(ultra0.time, "sleep"),
            patch("urllib.request.urlopen", self.network),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def shell(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if args[0] == "push":
            self.assertEqual(args[-1], ultra0.FRIDA_REMOTE + ".new")
            if self.fail_push:
                raise RuntimeError("mock push failed")
            return "1 file pushed"
        self.assertEqual(args[0], "shell")
        command = args[1]
        if command.startswith("su -c '") and command.endswith("'"):
            command = command[7:-1]
        if command == "id":
            return "uid=0(root)" if self.root else "uid=2000(shell)"
        if command.startswith("pidof frida-server"):
            return "4242" if self.running else ""
        if "--version" in command:
            return self.staged_version if ultra0.FRIDA_REMOTE + ".new" in command else self.version
        if command == "getprop ro.product.cpu.abi":
            return self.abi
        if command.startswith("kill "):
            self.running = False
            return ""
        if command.startswith("mv "):
            self.version = self.staged_version
            return ""
        if "nohup " in command or command.startswith(ultra0.FRIDA_REMOTE + " -D"):
            self.running = True
            return ""
        if command.startswith(("chmod ", "rm ")):
            return ""
        raise AssertionError("Unexpected device operation: " + repr(args))

    def commands(self):
        return [" ".join(args) for args, _ in self.calls]

    def assert_not_stopped(self):
        self.assertFalse(any("kill " in command for command in self.commands()))
        self.assertTrue(self.running)

    def test_matching_running_server_is_probed_without_replacement(self):
        self.version = self.frida.__version__
        ultra0.ensure_frida_server()
        self.network.assert_not_called()
        self.assert_not_stopped()
        self.frida.get_device.assert_called_with(ultra0.SERIAL, timeout=10)
        self.device.enumerate_processes.assert_called()

    def test_mismatch_stages_and_verifies_before_stopping_old_server(self):
        ultra0.ensure_frida_server()
        url = self.network.call_args.args[0]
        self.assertTrue(url.endswith("/16.5.9/frida-server-16.5.9-android-x86_64.xz"), url)
        commands = self.commands()
        staged_check = next(i for i, c in enumerate(commands) if ".new --version" in c)
        stop = next(i for i, c in enumerate(commands) if "kill 4242" in c)
        move = next(i for i, c in enumerate(commands) if "mv " in c)
        self.assertLess(staged_check, stop)
        self.assertLess(stop, move)
        self.assertEqual(self.version, "16.5.9")
        self.device.enumerate_processes.assert_called()

    def test_corrupt_download_leaves_old_daemon_running(self):
        self.network.side_effect = lambda *a, **k: io.BytesIO(b"not an xz archive")
        with self.assertRaises((RuntimeError, lzma.LZMAError, SystemExit)):
            ultra0.ensure_frida_server()
        self.assert_not_stopped()

    def test_failed_push_leaves_old_daemon_running(self):
        self.fail_push = True
        with self.assertRaises((RuntimeError, SystemExit)):
            ultra0.ensure_frida_server()
        self.assert_not_stopped()

    def test_wrong_staged_version_leaves_old_daemon_running(self):
        self.staged_version = "17.27.1"
        with self.assertRaises((RuntimeError, SystemExit)):
            ultra0.ensure_frida_server()
        self.assert_not_stopped()

    def test_unknown_abi_fails_before_download_or_stop(self):
        self.abi = "unknown-cpu"
        with self.assertRaises(RuntimeError):
            ultra0.ensure_frida_server()
        self.network.assert_not_called()
        self.assert_not_stopped()

    def test_unsupported_client_fails_before_device_or_network_access(self):
        self.frida.__version__ = "17.27.1"
        with self.assertRaises(SystemExit):
            ultra0.ensure_frida_server()
        self.assertEqual(self.calls, [])
        self.network.assert_not_called()

    def test_non_root_shell_stops_and_starts_using_su(self):
        self.root = False
        ultra0.ensure_frida_server()
        commands = self.commands()
        self.assertTrue(any("su -c 'kill 4242" in c for c in commands))
        self.assertTrue(any("su -c '" in c and "nohup " in c for c in commands))
        self.device.enumerate_processes.assert_called()

    def test_matching_file_with_stale_daemon_is_restarted_and_reprobed(self):
        self.version = self.frida.__version__
        self.device.enumerate_processes.side_effect = [RuntimeError("protocol mismatch"), []]
        ultra0.ensure_frida_server()
        self.network.assert_not_called()
        self.assertTrue(any("kill 4242" in c for c in self.commands()))
        self.assertEqual(self.device.enumerate_processes.call_count, 2)

    def test_running_process_without_working_protocol_is_not_success(self):
        self.device.enumerate_processes.side_effect = RuntimeError("protocol mismatch")
        with self.assertRaisesRegex(RuntimeError, "protocol mismatch"):
            ultra0.ensure_frida_server()
        self.assertTrue(self.running)
        ultra0.ok.assert_not_called()


if __name__ == "__main__":
    unittest.main()
