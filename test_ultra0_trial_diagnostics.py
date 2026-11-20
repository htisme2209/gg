"""Exercise message diagnostics with a fake Frida session, entirely offline."""
import sys
import types
import unittest
from unittest.mock import Mock, patch

import ultra0


class FakeScript:
    def __init__(self, messages):
        self.messages = messages
        self.callback = None

    def on(self, event, callback):
        if event != "message":
            raise AssertionError(event)
        self.callback = callback

    def load(self):
        for message in self.messages:
            self.callback(message, None)


class TrialDiagnosticsTests(unittest.TestCase):
    def run_messages(self, messages):
        script = FakeScript(messages)
        session = Mock()
        session.create_script.return_value = script
        device = Mock()
        device.attach.return_value = session
        frida = types.SimpleNamespace(get_device=Mock(return_value=device))
        with patch.dict(sys.modules, {"frida": frida}), \
                patch.object(ultra0, "SERIAL", "offline-device"), \
                patch.object(ultra0.time, "sleep") as sleep, \
                patch.object(ultra0, "step"), \
                patch.object(ultra0, "note") as note, \
                patch.object(ultra0, "warn") as warn, \
                patch.object(ultra0, "ok") as ok:
            result = ultra0.run_trial(123, wait=0, plan="pro12")
        frida.get_device.assert_called_once_with("offline-device", timeout=10)
        device.attach.assert_called_once_with(123)
        sleep.assert_called_once_with(0)
        return result, warn, note, ok

    def test_frida_javascript_error_is_captured_and_warned(self):
        result, warn, _, _ = self.run_messages([
            {"type": "error", "description": "ReferenceError: Java is not defined"}])
        self.assertEqual(result["errors"], [{
            "ev": "frida_script_err", "m": "ReferenceError: Java is not defined"}])
        self.assertIsNone(result["launched"])
        self.assertEqual(result["events"], result["errors"])
        self.assertIn("Java is not defined", warn.call_args.args[0])

    def test_boot_fail_is_captured_and_warned(self):
        payload = {"ev": "boot_fail", "m": "bridge unavailable"}
        result, warn, _, _ = self.run_messages([{"type": "send", "payload": payload}])
        self.assertEqual(result["errors"], [payload])
        self.assertIn("bridge unavailable", warn.call_args.args[0])

    def test_no_activity_is_captured_as_structured_error(self):
        payload = {"ev": "no_activity"}
        result, warn, _, _ = self.run_messages([{"type": "send", "payload": payload}])
        self.assertEqual(result["errors"], [payload])
        self.assertIn("no_activity", warn.call_args.args[0])

    def test_non_dictionary_payloads_are_ignored(self):
        result, warn, note, ok = self.run_messages([
            {"type": "send", "payload": payload}
            for payload in [None, "unexpected", ["not", "an", "object"], 123, True]])
        self.assertEqual(result, {"offers": [], "launched": None, "purchase": None, "errors": [], "events": []})
        warn.assert_not_called()
        note.assert_not_called()
        ok.assert_not_called()

    def test_valid_offer_launch_and_purchase_messages_still_collected(self):
        offer = {"ev": "offer", "id": "test-offer", "micros": "0", "period": "P1Y", "token": "test-token"}
        launched = {"ev": "launched", "code": 0, "msg": ""}
        purchase = {"ev": "purchase_cb", "code": 0}
        result, warn, note, ok = self.run_messages([
            {"type": "send", "payload": payload} for payload in [offer, launched, purchase]])
        self.assertEqual(result["offers"], [offer])
        self.assertEqual(result["launched"], launched)
        self.assertEqual(result["purchase"], purchase)
        self.assertEqual(result["errors"], [])
        warn.assert_not_called()
        self.assertTrue(any("P1Y" in call.args[0] for call in note.call_args_list))
        ok.assert_called_once()

    def test_chosen_upgrade_mode_and_activity_are_retained_in_event_order(self):
        events = [
            {"ev": "setup", "code": 0, "msg": "connected"},
            {"ev": "pd", "code": 0, "n": 1, "msg": "products available"},
            {"ev": "chosen", "product": "g1.2tb.ai.subs_variant", "id": "6months-eft-ss-2026", "period": "P6M"},
            {"ev": "mode_applied", "mode": 5, "ok": True},
            {"ev": "stack_mode", "mode": 5},
            {"ev": "activity", "a": "example.GoogleOneActivity"},
        ]
        result, warn, _, _ = self.run_messages([{"type": "send", "payload": event} for event in events])
        self.assertEqual(result["events"], events)
        self.assertEqual(result["errors"], [])
        warn.assert_not_called()

    def test_billing_setup_and_product_errors_preserve_exact_debug_message(self):
        for event in [{"ev": "setup", "code": 3, "msg": "Billing unavailable for this account"},
                      {"ev": "pd", "code": 6, "n": 0, "msg": "Internal product query failed"}]:
            with self.subTest(event=event["ev"]):
                result, warn, _, _ = self.run_messages([{"type": "send", "payload": event}])
                self.assertIn(event, result["events"])
                self.assertTrue(result["errors"])
                self.assertTrue(any(event["msg"] in call.args[0] for call in warn.call_args_list))

    def test_failed_mode_application_is_not_reported_as_success(self):
        event = {"ev": "mode_applied", "mode": 5, "ok": False, "m": "Replacement mode setter unavailable"}
        result, warn, _, _ = self.run_messages([{"type": "send", "payload": event}])
        self.assertIn(event, result["events"])
        self.assertTrue(result["errors"])
        warn.assert_called()

    def test_empty_product_response_is_an_explicit_diagnostic_failure(self):
        event = {"ev": "pd", "code": 0, "n": 0, "msg": ""}
        result, warn, _, _ = self.run_messages([{"type": "send", "payload": event}])
        self.assertIn(event, result["events"])
        self.assertTrue(result["errors"])
        warn.assert_called()

    def test_diagnostic_events_do_not_retain_purchase_token_values(self):
        event = {"ev": "stack_mode", "mode": 5, "token": "token-secret", "purchaseToken": "purchase-secret",
                 "old": "old-secret", "head": "head-secret"}
        result, _, _, _ = self.run_messages([{"type": "send", "payload": event}])
        self.assertEqual(result["events"], [{"ev": "stack_mode", "mode": 5}])

    def test_failed_billing_launch_warns_instead_of_claiming_sheet_opened(self):
        launched = {"ev": "launched", "code": 5, "msg": "Replacement request rejected"}
        result, warn, _, ok = self.run_messages([{"type": "send", "payload": launched}])
        self.assertEqual(result["launched"], launched)
        self.assertIn(launched, result["events"])
        self.assertTrue(result["errors"])
        self.assertTrue(any(launched["msg"] in call.args[0] for call in warn.call_args_list))
        ok.assert_not_called()

    def test_item_unavailable_sheet_is_recorded_without_confirming_purchase(self):
        message = "The item you requested is not available for purchase."
        xml = '<hierarchy><node text="' + message + '" bounds="[0,0][100,100]"/></hierarchy>'
        with patch.object(ultra0, "ui_xml", return_value=xml), \
                patch.object(ultra0, "tap_text") as tap_text, \
                patch.object(ultra0.time, "sleep"), \
                patch.object(ultra0, "step"), patch.object(ultra0, "warn"):
            result = ultra0.confirm_zero(wait=2)
        self.assertTrue(result["unavailable"])
        self.assertFalse(result["confirmed"])
        self.assertIn(message, result["text"])
        tap_text.assert_not_called()

    def test_generic_play_billing_error_returns_before_price_or_confirmation_checks(self):
        message = "Something went wrong on our end. Please try again."
        xml = ('<hierarchy><node package="com.android.vending" text="Error" bounds="[0,0][100,100]"/>'
               '<node package="com.android.vending" text="' + message + '" bounds="[0,100][100,200]"/>'
               '<node package="com.android.vending" text="Google AI Subscribe US$0" bounds="[0,200][100,300]"/>'
               '<node package="com.android.vending" text="Got it" bounds="[0,300][100,400]"/></hierarchy>')
        with patch.object(ultra0, "ui_xml", return_value=xml), \
                patch.object(ultra0, "tap_text") as tap_text, \
                patch.object(ultra0.time, "sleep"), \
                patch.object(ultra0, "step"), patch.object(ultra0, "warn"):
            result = ultra0.confirm_zero(wait=2)
        self.assertTrue(result["billing_error"])
        self.assertFalse(result["confirmed"])
        self.assertFalse(result["ineligible"])
        self.assertIsNone(result["price"])
        self.assertIn(message, result["text"])
        tap_text.assert_not_called()

    def test_generic_error_from_other_package_is_not_classified_as_play_billing_error(self):
        xml = ('<hierarchy><node package="com.example.other" text="Something went wrong on our end. Please try again." '
               'bounds="[0,0][100,100]"/></hierarchy>')
        with patch.object(ultra0, "ui_xml", return_value=xml), \
                patch.object(ultra0, "tap_text") as tap_text, \
                patch.object(ultra0.time, "sleep"), \
                patch.object(ultra0, "step"), patch.object(ultra0, "warn"):
            result = ultra0.confirm_zero(wait=2)
        self.assertFalse(result["billing_error"])
        self.assertFalse(result["confirmed"])
        tap_text.assert_not_called()


class Pro3SelectionTests(unittest.TestCase):
    def selected_target(self, source):
        import json
        import re
        products = re.search(r'\bvar PRODUCTS=(\[[^\]]*\]);', source)
        prefer = re.search(r'\bvar PREFER=("(?:\\.|[^"\\])*");', source)
        self.assertIsNotNone(products)
        self.assertIsNotNone(prefer)
        return json.loads(products[1]), json.loads(prefer[1])

    def test_pro3_selects_exact_requested_product_and_offer_without_changing_pro6(self):
        self.assertEqual(self.selected_target(ultra0.build_js(plan="pro3")),
                         (["g1.play.2tb.ai"], "eft-3mo"))
        self.assertEqual(self.selected_target(ultra0.build_js(plan="pro6")),
                         (["g1.2tb.ai.subs_variant"], "6months-eft"))

    def test_pro3_target_is_preserved_with_list_or_verified_upgrade_options(self):
        for list_only in [False, True]:
            with self.subTest(list_only=list_only):
                script = ultra0.build_js(plan="pro3", list_only=list_only, stack=True,
                                         old_token="verified-offline-test-token", stack_mode=5)
                self.assertEqual(self.selected_target(script), (["g1.play.2tb.ai"], "eft-3mo"))
                if list_only:
                    self.assertIn("var LIST_ONLY=true;", script)
                    self.assertNotIn("verified-offline-test-token", script)
                else:
                    self.assertIn("var STACK_MODE=5;", script)
                    self.assertIn('"verified-offline-test-token"', script)

    def test_help_advertises_pro3_without_device_or_transaction_access(self):
        from contextlib import redirect_stdout
        import io
        output = io.StringIO()
        with patch.object(sys, "argv", ["ultra0.py", "--help"]), redirect_stdout(output), \
                patch.object(ultra0, "find_adb", side_effect=AssertionError("no device access")) as adb, \
                patch.object(ultra0, "sh", side_effect=AssertionError("no device commands")) as shell, \
                patch.object(ultra0, "process", side_effect=AssertionError("no transactions")) as process:
            with self.assertRaises(SystemExit) as exit_status:
                ultra0.main()
        self.assertEqual(exit_status.exception.code, 0)
        self.assertIn("pro3", output.getvalue())
        adb.assert_not_called()
        shell.assert_not_called()
        process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
