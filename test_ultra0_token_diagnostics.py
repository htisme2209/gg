"""Offline checks for the cache-only purchase-token diagnostic command."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import ultra0


class TokenDiagnosticCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="ultra0-diagnose-cli-")
        self.addCleanup(directory.cleanup)
        self.report_dir = Path(directory.name)
        self.normal_report = self.report_dir / "current.json"
        self.normal_report.write_text('{"status":"prior-normal-report"}', encoding="utf-8")
        self.normal_bytes = self.normal_report.read_bytes()
        self.current_user = "0"
        self.activity_dump = "mResumedActivity: ActivityRecord{test u0 com.android.vending/.MainActivity t1}"
        self.forbidden = {}
        names = ["ensure_root", "ensure_network", "ensure_frida_server", "ensure_module_apk",
                 "ensure_vending", "current_play_account", "switch_play", "launch_app", "process",
                 "run_trial", "confirm_zero", "verify", "add_account", "add_card"]
        for name in names:
            mock = Mock(side_effect=AssertionError("Diagnostic must not call " + name))
            self.forbidden[name] = mock
            self.start(patch.object(ultra0, name, mock))
        self.start(patch.object(ultra0, "REPORT_DIR", self.report_dir))
        self.start(patch.object(ultra0, "SERIAL", "previous-device"))
        self.start(patch.object(ultra0, "ADB", None))
        self.start(patch.object(ultra0, "SKIP_ACCOUNT_CHECK", False, create=True))
        self.adb = self.start(patch.object(ultra0, "find_adb", return_value="offline-adb"))
        self.shell = self.start(patch.object(ultra0, "sh", side_effect=self.fake_shell))
        self.pick = self.start(patch.object(ultra0, "pick_device", side_effect=self.select_device))
        self.read = self.start(patch.object(ultra0, "read_purchase_token", side_effect=self.token_found))

    def start(self, context):
        result = context.start()
        self.addCleanup(context.stop)
        return result

    def fake_shell(self, *args, **kwargs):
        if args == ("get-state",) and kwargs == {"check": True}:
            return "device"
        if kwargs == {"timeout": 15, "check": True}:
            if args == ("shell", "am get-current-user"):
                return self.current_user
            if args == ("shell", "dumpsys activity activities"):
                return self.activity_dump
        raise AssertionError("Unexpected device command: " + repr((args, kwargs)))

    def select_device(self):
        ultra0.SERIAL = "selected-offline-device"

    def token_found(self, sku_short, account_email, expected_token="", diagnostics=None):
        self.assertEqual(sku_short, "subs_variant")
        self.assertEqual(account_email, "target@example.com")
        diagnostics.update(reason="selected", account_rows=2, product_rows=1, usable_rows=1,
                           rejected={}, token_fields={"purchaseToken": 1, "token": 0})
        return "private-returned-test-token"

    def run_cli(self, *arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["ultra0.py", *arguments]), redirect_stdout(stdout), redirect_stderr(stderr):
            result = ultra0.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def report(self):
        reports = list(self.report_dir.glob("token-check-*.json"))
        self.assertEqual(len(reports), 1)
        text = reports[0].read_text(encoding="utf-8")
        return reports[0], json.loads(text), text

    def assert_no_application_or_purchase_actions(self):
        for name, mock in self.forbidden.items():
            with self.subTest(forbidden=name):
                mock.assert_not_called()

    def test_explicit_serial_and_legacy_flags_use_only_cache_diagnostic_path(self):
        result, output, _ = self.run_cli("--diagnose-token", "--account", "TARGET@example.com", "--serial", "offline-device",
                                       "--stack", "--list", "--force", "--mode", "5", "--old-token", "private-expected-test-token")
        self.assertEqual(result, 0)
        self.assertEqual(ultra0.SERIAL, "offline-device")
        self.assertEqual(self.shell.call_args_list, [
            call("connect", "offline-device", timeout=10),
            call("get-state", check=True),
            call("shell", "am get-current-user", timeout=15, check=True),
            call("shell", "dumpsys activity activities", timeout=15, check=True),
        ])
        self.pick.assert_not_called()
        self.assertEqual(self.read.call_args.kwargs["expected_token"], "private-expected-test-token")
        self.assert_no_application_or_purchase_actions()
        path, report, text = self.report()
        self.assertEqual(report["status"], "token_found")
        self.assertEqual(report["email"], "target@example.com")
        self.assertEqual(report["token_diagnostics"]["usable_rows"], 1)
        self.assertNotIn("private-returned-test-token", text + output)
        self.assertNotIn("private-expected-test-token", text + output)
        self.assertNotEqual(path, self.normal_report)
        self.assertEqual(self.normal_report.read_bytes(), self.normal_bytes)

    def test_placeholder_account_is_rejected_before_any_adb_access(self):
        with self.assertRaises(SystemExit) as error:
            self.run_cli("--diagnose-token", "--account", "current@device")
        self.assertEqual(error.exception.code, 2)
        self.adb.assert_not_called()
        self.shell.assert_not_called()
        self.pick.assert_not_called()
        self.read.assert_not_called()
        self.assert_no_application_or_purchase_actions()
        self.assertEqual(list(self.report_dir.glob("token-check-*.json")), [])

    def test_no_explicit_serial_uses_selected_device_without_starting_apps(self):
        result, _, _ = self.run_cli("--diagnose-token", "--account", "target@example.com")
        self.assertEqual(result, 0)
        self.assertEqual(ultra0.SERIAL, "selected-offline-device")
        self.pick.assert_called_once()
        self.assertEqual(self.shell.call_args_list, [
            call("shell", "am get-current-user", timeout=15, check=True),
            call("shell", "dumpsys activity activities", timeout=15, check=True),
        ])
        self.assert_no_application_or_purchase_actions()

    def test_missing_cached_token_returns_nonzero_and_retains_reason_counts(self):
        def missing(sku_short, account_email, expected_token="", diagnostics=None):
            diagnostics.update(reason="no_account_rows", account_rows=0, product_rows=0, usable_rows=0,
                               rejected={}, token_fields={"purchaseToken": 0, "token": 0})
            return ""
        self.read.side_effect = missing
        result, _, _ = self.run_cli("--diagnose-token", "--account", "target@example.com", "--serial", "offline-device")
        self.assertEqual(result, 1)
        _, report, _ = self.report()
        self.assertEqual(report["status"], "purchase_token_not_found")
        self.assertEqual(report["token_diagnostics"]["reason"], "no_account_rows")
        self.assertEqual(report["token_diagnostics"]["account_rows"], 0)
        self.assert_no_application_or_purchase_actions()
        self.assertEqual(self.normal_report.read_bytes(), self.normal_bytes)

    def test_snapshot_read_failure_returns_nonzero_and_saves_error_report(self):
        def failed(sku_short, account_email, expected_token="", diagnostics=None):
            diagnostics.update(reason="read_failed")
            raise ultra0.PurchaseTokenReadError("offline snapshot hash mismatch")
        self.read.side_effect = failed
        result, _, _ = self.run_cli("--diagnose-token", "--account", "target@example.com", "--serial", "offline-device")
        self.assertEqual(result, 1)
        _, report, _ = self.report()
        self.assertEqual(report["status"], "purchase_token_read_failed")
        self.assertIn("offline snapshot hash mismatch", report["error"])
        self.assertEqual(report["token_diagnostics"]["reason"], "read_failed")
        self.assert_no_application_or_purchase_actions()

    def test_profile_mismatch_records_only_numeric_ids_without_raw_activity_data(self):
        self.current_user = "10"
        self.activity_dump = (
            "Private unrelated metadata: foreign-person@example.com private-dump-marker\n"
            "topResumedActivity=ActivityRecord{abcdef u10 com.android.vending/.MainActivity t22}\n"
            "mResumedActivity: ActivityRecord{abcdef u10 com.android.vending/.MainActivity t22}\n")

        def missing(sku_short, account_email, expected_token="", diagnostics=None):
            diagnostics.update(reason="no_account_rows", account_rows=0, product_rows=0, usable_rows=0)
            return ""

        self.read.side_effect = missing
        result, output, _ = self.run_cli("--diagnose-token", "--account", "target@example.com", "--serial", "offline-device")
        self.assertEqual(result, 1)
        _, report, text = self.report()
        self.assertEqual(report["device_diagnostics"], {
            "serial": "offline-device", "cache_android_user": 0,
            "current_android_user": 10, "resumed_play_user": 10})
        self.assertNotIn("foreign-person@example.com", text + output)
        self.assertNotIn("private-dump-marker", text + output)
        self.assertNotIn("ActivityRecord", text + output)
        self.assert_no_application_or_purchase_actions()

    def test_explicit_supported_source_is_passed_to_lookup_without_exposing_its_token(self):
        product = "g1.play.2tb.ai"

        def selected_source(sku_short, account_email, expected_token="", diagnostics=None):
            self.assertEqual(sku_short, product)
            self.assertEqual(account_email, "target@example.com")
            diagnostics.update(reason="selected", selected_product=product, matched_products=[product],
                               account_rows=1, product_rows=1, usable_rows=1)
            return "private-source-token"

        self.read.side_effect = selected_source
        code, output, _ = self.run_cli("--diagnose-token", "--account", "target@example.com",
                                       "--serial", "offline-device", "--token-product", product)
        self.assertEqual(code, 0)
        self.assertEqual(self.read.call_args.args[0], product)
        _, report, text = self.report()
        self.assertEqual(report["token_diagnostics"]["selected_product"], product)
        self.assertNotIn("private-source-token", text + output)
        self.assert_no_application_or_purchase_actions()

    def test_unsupported_source_is_rejected_before_adb_or_lookup(self):
        with self.assertRaises(SystemExit) as error:
            self.run_cli("--diagnose-token", "--account", "target@example.com",
                         "--serial", "offline-device", "--token-product", "g1.play.20tb")
        self.assertEqual(error.exception.code, 2)
        self.adb.assert_not_called()
        self.shell.assert_not_called()
        self.read.assert_not_called()
        self.assert_no_application_or_purchase_actions()


if __name__ == "__main__":
    unittest.main()
