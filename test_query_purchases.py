"""Offline tests for isolated, metadata-only subscription diagnostics."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import query_purchases as purchases


def purchased(**updates):
    row = {"products": ["g1.2tb.ai.subs_variant"], "purchase_state": 1,
           "auto_renewing": False, "acknowledged": True, "token_present": True}
    row.update(updates)
    return row


class FakeScript:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.callback = None
        self.exports_sync = Mock()
        self.unload = Mock()
        self.load = Mock(side_effect=self.deliver)

    def on(self, event, callback):
        if event != "message":
            raise AssertionError(event)
        self.callback = callback

    def deliver(self):
        for message in self.messages:
            self.callback(message, None)


def completion(rows, code=0, **extra):
    return {"type": "send", "payload": {"ev": "purchases_complete", "code": code,
                                           "purchases": rows, **extra}}


class PurchaseQueryTests(unittest.TestCase):
    def run_messages(self, messages):
        script = FakeScript(messages)
        session = Mock()
        session.create_script.return_value = script
        result = purchases.query_current_subscriptions(session, timeout=0.001)
        script.exports_sync.dispose.assert_called_once()
        script.unload.assert_called_once()
        session.detach.assert_not_called()
        return result

    def test_purchased_nonrenewing_metadata_preserves_flags_and_drops_receipts(self):
        unsafe = purchased(products=["g1.2tb.ai.subs_variant", "g1.2tb.ai.subs_variant"],
                           purchaseToken="private-token", token="second-private-token", originalJson="private-receipt",
                           email="foreign@example.com", unknown={"secret": "private-value"})
        result = self.run_messages([completion([unsafe], debugMessage="private-debug-message")])
        self.assertEqual(result, {"status": "complete", "purchases": [purchased()], "code": 0, "error_stage": None})
        serialized = json.dumps(result)
        for secret in ["private-token", "private-receipt", "foreign@example.com", "private-value", "private-debug-message"]:
            self.assertNotIn(secret, serialized)
        self.assertIs(result["purchases"][0]["auto_renewing"], False)
        self.assertIs(result["purchases"][0]["acknowledged"], True)
        self.assertIs(result["purchases"][0]["token_present"], True)

    def test_empty_success_is_distinct_from_query_failure(self):
        success = self.run_messages([completion([])])
        failure = self.run_messages([completion([], code=3, msg="private-error-detail")])
        self.assertEqual(success["status"], "complete")
        self.assertEqual(success["purchases"], [])
        self.assertEqual(success["code"], 0)
        self.assertEqual(failure["status"], "error")
        self.assertEqual(failure["code"], 3)
        self.assertEqual(failure["error_stage"], "query")
        self.assertNotIn("private-error-detail", json.dumps(failure))

    def test_timeout_is_not_an_empty_success(self):
        result = self.run_messages([])
        self.assertEqual(result, {"status": "timeout", "purchases": [], "code": None, "error_stage": "timeout"})

    def test_invalid_metadata_fails_the_allowlist_instead_of_coercing_values(self):
        invalid = [None, {}, ["not-an-object"], [purchased(products="g1.bad")],
                   [purchased(products=["foreign.product"])], [purchased(products=["g1." + "x" * 201])],
                   [purchased(purchase_state=True)], [purchased(purchase_state=9)],
                   [purchased(auto_renewing=0)], [purchased(acknowledged="true")],
                   [purchased(token_present=None)]]
        for rows in invalid:
            with self.subTest(rows=rows):
                result = self.run_messages([completion(rows)])
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error_stage"], "metadata")
                self.assertEqual(result["purchases"], [])

    def test_frida_error_and_untrusted_stage_never_forward_raw_strings(self):
        messages = [
            {"type": "error", "description": "private-token in Frida description", "stack": "private-receipt"},
            {"type": "send", "payload": {"ev": "purchases_error", "stage": "private-stage-value", "m": "private-token", "code": True}},
            {"type": "send", "payload": {"ev": "purchases_error", "stage": "serialize", "m": "private-receipt", "code": 6}},
        ]
        for message in messages:
            with self.subTest(message_type=message["type"]):
                result = self.run_messages([message])
                self.assertEqual(result["status"], "error")
                self.assertNotIn("private-", json.dumps(result))
                self.assertIn(result["error_stage"], ("runtime", "serialize"))
                self.assertIsNot(result["code"], True)

    def test_script_failure_still_disposes_and_unloads_without_exception_leak(self):
        script = FakeScript()
        script.load.side_effect = RuntimeError("private-load-receipt")
        script.exports_sync.dispose.side_effect = RuntimeError("private-dispose-token")
        script.unload.side_effect = RuntimeError("private-unload-token")
        session = Mock()
        session.create_script.return_value = script
        result = purchases.query_current_subscriptions(session, timeout=0.001)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_stage"], "runtime")
        self.assertNotIn("private-", json.dumps(result))
        script.exports_sync.dispose.assert_called_once()
        script.unload.assert_called_once()

    def test_first_terminal_result_cannot_be_overwritten_by_late_callbacks(self):
        result = self.run_messages([completion([purchased()]),
                                    {"type": "error", "description": "private-late-error"}, completion([])])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["purchases"], [purchased()])


class PurchaseDiagnosticCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="purchase-query-cli-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "purchases.json"
        self.session = Mock()
        self.script = FakeScript([completion([purchased(purchaseToken="private-token", receipt="private-receipt")])])
        self.session.create_script.return_value = self.script
        self.prepare = self.start(patch.object(purchases.query_sku, "prepare_device", return_value=(self.session, "target@example.com")))
        self.forbidden = {}
        for name in ["process", "run_trial", "confirm_zero", "add_card", "switch_play", "read_purchase_token"]:
            self.forbidden[name] = self.start(patch.object(purchases.ultra0, name, side_effect=AssertionError("Forbidden " + name)))

    def start(self, context):
        result = context.start()
        self.addCleanup(context.stop)
        return result

    def run_cli(self, *extra_arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = purchases.main(["--serial", "offline-device", "--account", "TARGET@example.com",
                                     "--timeout", "0.001", "--output", str(self.path), *extra_arguments])
        return result, json.loads(self.path.read_text(encoding="utf-8")), stdout.getvalue() + stderr.getvalue()

    def assert_no_purchase_functions(self):
        for name, mock in self.forbidden.items():
            with self.subTest(forbidden=name):
                mock.assert_not_called()

    def test_verified_play_ui_does_not_claim_payer_verification_and_secrets_are_omitted(self):
        code, report, output = self.run_cli()
        self.assertEqual(code, 0)
        self.prepare.assert_called_once()
        self.assertEqual(self.prepare.call_args.args, ("offline-device", "target@example.com"))
        self.assertTrue(callable(self.prepare.call_args.kwargs["on_stage"]))
        self.assertEqual(report["play_account"], "target@example.com")
        self.assertIs(report["play_ui_account_verified"], True)
        self.assertIs(report["payer_account_verified"], False)
        self.assertEqual(report["purchases"], [purchased()])
        self.assertNotIn("private-", json.dumps(report) + output)
        self.script.exports_sync.dispose.assert_called_once()
        self.script.unload.assert_called_once()
        self.session.detach.assert_called_once()
        self.assert_no_purchase_functions()

    def test_query_failure_cleans_up_and_saves_redacted_failure_report(self):
        self.script.messages = [{"type": "error", "description": "private-receipt in runtime error"}]
        self.session.detach.side_effect = RuntimeError("private-detach-token")
        code, report, output = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["error_stage"], "runtime")
        self.assertNotIn("private-", json.dumps(report) + output)
        self.script.exports_sync.dispose.assert_called_once()
        self.script.unload.assert_called_once()
        self.session.detach.assert_called_once()
        self.assert_no_purchase_functions()

    def test_device_setup_failure_does_not_leak_exception_description(self):
        self.prepare.side_effect = RuntimeError("private-receipt foreign@example.com")
        code, report, output = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(report["error_stage"], "device_setup")
        self.assertNotIn("private-receipt", json.dumps(report) + output)
        self.assertNotIn("foreign@example.com", json.dumps(report) + output)
        self.session.detach.assert_not_called()
        self.assert_no_purchase_functions()

    def test_setup_failure_keeps_safe_stage_without_raw_exception(self):
        def failed_prepare(serial, account, on_stage=None):
            self.assertEqual(account, "target@example.com")
            on_stage("play_account_unverified")
            raise RuntimeError("private-receipt foreign@example.com")
        self.prepare.side_effect = failed_prepare
        code, report, output = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(report["error_stage"], "play_account_unverified")
        self.assertNotIn("private-receipt", json.dumps(report) + output)
        self.assertNotIn("foreign@example.com", json.dumps(report) + output)
        self.session.create_script.assert_not_called()
        self.session.detach.assert_not_called()
        self.assert_no_purchase_functions()

    def test_allow_unverified_ui_queries_only_metadata_and_preserves_verification_limits(self):
        self.prepare.return_value = (self.session, "")
        code, report, output = self.run_cli("--allow-unverified-ui")
        self.assertEqual(code, 0)
        self.assertEqual(self.prepare.call_args.args, ("offline-device", None))
        self.assertTrue(callable(self.prepare.call_args.kwargs["on_stage"]))
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["purchases"], [purchased()])
        self.assertEqual(report["play_account"], "")
        self.assertIs(report["play_ui_account_verified"], False)
        self.assertIs(report["payer_account_verified"], False)
        self.assertNotIn("private-", json.dumps(report) + output)
        self.session.detach.assert_called_once()
        self.assert_no_purchase_functions()

    def test_allow_unverified_ui_still_blocks_known_account_mismatch_and_detaches(self):
        self.prepare.return_value = (self.session, "other@example.com")
        code, report, output = self.run_cli("--allow-unverified-ui")
        self.assertEqual(code, 1)
        self.assertEqual(self.prepare.call_args.args, ("offline-device", None))
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["error_stage"], "play_account_mismatch")
        self.assertIs(report["play_ui_account_verified"], False)
        self.assertIs(report["payer_account_verified"], False)
        self.assertEqual(report["purchases"], [])
        self.session.create_script.assert_not_called()
        self.session.detach.assert_called_once()
        self.assert_no_purchase_functions()


if __name__ == "__main__":
    unittest.main()
