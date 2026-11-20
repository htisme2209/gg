"""The Play-account check must never reach a subscription transaction."""
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import ultra0


class CheckPlayAccountCliTests(unittest.TestCase):
    def run_check(self, current, *extra):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            guards = {}
            for name in ("ensure_root", "ensure_network", "ensure_frida_server", "ensure_module_apk",
                         "ensure_vending", "read_purchase_token", "launch_app", "run_trial",
                         "confirm_zero", "process", "add_account", "switch_play"):
                guards[name] = stack.enter_context(patch.object(
                    ultra0, name, side_effect=AssertionError("Unexpected action: " + name)))
            stack.enter_context(patch.object(ultra0, "REPORT_DIR", Path(directory)))
            stack.enter_context(patch.object(ultra0, "ADB", None))
            stack.enter_context(patch.object(ultra0, "SERIAL", None))
            stack.enter_context(patch.object(ultra0, "SKIP_ACCOUNT_CHECK", False, create=True))
            stack.enter_context(patch.object(ultra0, "find_adb", return_value="mock-adb"))
            shell = stack.enter_context(patch.object(ultra0, "sh", return_value="device"))
            account = stack.enter_context(patch.object(ultra0, "current_play_account", return_value=current))
            stack.enter_context(patch("sys.argv", ["ultra0.py", "--serial", "mock-device",
                                                   "--account", "target@example.com",
                                                   "--check-play-account", *extra]))
            output = io.StringIO()
            with redirect_stdout(output):
                code = ultra0.main()
            reports = list(Path(directory).glob("play-account-check-*.json"))
            self.assertEqual(len(reports), 1)
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            account.assert_called_once_with(open_store=True)
            self.assertEqual(shell.call_args_list, [
                call("connect", "mock-device", timeout=10),
                call("get-state", check=True),
            ])
            for guard in guards.values():
                guard.assert_not_called()
            return code, report, output.getvalue()

    def test_check_only_ignores_purchase_flags_and_verifies_ui_account(self):
        code, report, output = self.run_check("target@example.com", "--stack", "--plan", "pro6c", "--force")
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "verified")
        self.assertTrue(report["account_matches"])
        self.assertEqual(report["serial"], "mock-device")

    def test_unknown_or_wrong_account_does_not_pass_as_expected_email(self):
        for current, expected in (("", "play_account_unverified"),
                                  ("other@example.com", "wrong_account")):
            with self.subTest(expected=expected):
                code, report, output = self.run_check(current)
                self.assertEqual(code, 1)
                self.assertEqual(report["status"], expected)
                self.assertFalse(report["account_matches"])
                self.assertNotIn("other@example.com", json.dumps(report) + output)


if __name__ == "__main__":
    unittest.main()
