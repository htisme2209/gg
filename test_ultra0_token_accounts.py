"""Offline regression tests for account-scoped subscription token selection."""
import inspect
import hashlib
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

import ultra0


class PurchaseTokenAccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="ultra0-token-tests-")
        self.addCleanup(self.directory.cleanup)
        self.directory_path = Path(self.directory.name)
        self.fixture = self.directory_path / "fixture.db"
        self.pulled_dir = self.directory_path / "pulled"
        self.pulled_dir.mkdir()
        with closing(sqlite3.connect(self.fixture)) as db:
            db.execute("CREATE TABLE ownership (account TEXT, doc_id TEXT, subs_valid_until_time, inapp_purchase_data TEXT)")
            db.commit()
        self.sh = Mock(side_effect=self.fake_shell)
        for p in [patch.object(ultra0, "sh", self.sh),
                  patch.object(ultra0, "note"), patch.object(ultra0, "warn"),
                  patch.object(ultra0.time, "time", return_value=1000),
                  patch.object(ultra0.tempfile, "gettempdir", return_value=str(self.pulled_dir))]:
            p.start()
            self.addCleanup(p.stop)

    def fake_shell(self, *args, **kwargs):
        if args[0] == "exec-out":
            name = args[1].rsplit("/", 1)[1].strip("'")
            return Path(str(self.fixture) + ("-wal" if name.endswith("-wal") else "")).read_bytes()
        if args[0] == "shell":
            if args[1] == "id":
                return "uid=0(root)"
            if "fingerprint()" in args[1]:
                manifest = []
                for suffix in ("", "-wal"):
                    path = Path(str(self.fixture) + suffix)
                    if path.exists():
                        manifest.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  library.db{suffix}")
                return "\n".join(manifest)
            return ""
        raise AssertionError("Unexpected operation: " + repr(args))

    def row(self, account, token="target-token", expiry=2000000, data=None, product="g1.2tb.ai.subs_variant"):
        if data is None:
            data = json.dumps({"purchaseToken": token})
        with closing(sqlite3.connect(self.fixture)) as db:
            db.execute("INSERT INTO ownership VALUES (?, ?, ?, ?)", (account, product, expiry, data))
            db.commit()

    def test_other_account_with_later_expiry_cannot_win(self):
        self.row("htisme222@gmail.com", "other-token", 9000000)
        self.row("htisme223@gmail.com", "target-token", 2000000)
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "htisme223@gmail.com"), "target-token")

    def test_account_normalization_does_not_match_similar_addresses(self):
        self.row(" HTISME223@GMAIL.COM ", "target-token", 2000000)
        self.row("xhtisme223@gmail.com", "other-token", 9000000)
        self.assertEqual(ultra0.read_purchase_token("subs_variant", " htisme223@gmail.com "), "target-token")

    def test_missing_or_placeholder_account_rejected_before_adb(self):
        for account in ["", "  ", "current@device"]:
            with self.subTest(account=account), self.assertRaises(ValueError):
                ultra0.read_purchase_token("subs_variant", account)
        self.sh.assert_not_called()

    def test_malformed_rows_do_not_hide_a_valid_same_account_token(self):
        for data in ["not json", "[]", '"a string"', "null", "123", "{}"]:
            self.row("target@example.com", expiry=9000000, data=data)
        self.row("target@example.com", token="invalid-expiry", expiry="not a timestamp")
        self.row("target@example.com", token="valid-token", expiry=2000000)
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com"), "valid-token")

    def test_best_token_is_ranked_only_within_account_and_product(self):
        self.row("target@example.com", "expired", 900000)
        self.row("target@example.com", "active", 2000000)
        self.row("target@example.com", "later", 3000000)
        self.row("target@example.com", "wrong-product", 9000000, product="unrelated-product")
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com"), "later")

    def test_expected_token_requires_ownership_by_target_account(self):
        self.row("other@example.com", "other-token", 9000000)
        self.row("target@example.com", "target-token", 2000000)
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", expected_token="other-token"), "")
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", expected_token="target-token"), "target-token")

    def test_no_matching_account_returns_no_token(self):
        self.row("other@example.com", "other-token")
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com"), "")

    def test_database_transfer_failure_is_a_read_error_not_absent_token(self):
        def fail_transfer(*args, **kwargs):
            if args[0] == "exec-out":
                raise RuntimeError("offline mock transfer failure")
            return self.fake_shell(*args, **kwargs)
        self.sh.side_effect = fail_transfer
        with self.assertRaisesRegex(ultra0.PurchaseTokenReadError, "offline mock transfer failure"):
            ultra0.read_purchase_token("subs_variant", "target@example.com")

    def test_committed_token_in_wal_is_included_without_checkpointing_source(self):
        writer = sqlite3.connect(self.fixture)
        self.addCleanup(writer.close)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO ownership VALUES (?, ?, ?, ?)",
                       ("target@example.com", "g1.2tb.ai.subs_variant", 2000000,
                        json.dumps({"purchaseToken": "wal-token"})))
        writer.commit()
        wal = Path(str(self.fixture) + "-wal")
        wal_before = wal.read_bytes()
        main_only = self.directory_path / "main-only.db"
        shutil.copyfile(self.fixture, main_only)
        with closing(sqlite3.connect(main_only)) as db:
            self.assertEqual(db.execute("select count(*) from ownership").fetchone()[0], 0)
        diagnostics = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com",
                                                  diagnostics=diagnostics), "wal-token")
        self.assertTrue(diagnostics["snapshot"]["wal_present"])
        self.assertEqual(diagnostics["reason"], "selected")
        self.assertEqual(wal.read_bytes(), wal_before)

    def test_diagnostics_distinguish_account_cache_absent_and_other_product(self):
        self.row("other@example.com", "foreign-secret")
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "")
        self.assertEqual(diag["reason"], "no_account_rows")
        self.assertEqual(diag["account_rows"], 0)
        self.assertEqual(diag["database_summary"]["ownership_rows"], 1)
        self.assertEqual(diag["database_summary"]["distinct_account_count"], 1)
        self.assertEqual(diag["database_summary"]["sku_rows_all_accounts"], 1)
        self.row("target@example.com", "target-secret", product="unrelated-product")
        ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag)
        self.assertEqual(diag["reason"], "no_product_rows")
        self.assertEqual(diag["account_rows"], 1)
        self.assertEqual(diag["product_rows"], 0)
        rendered = json.dumps(diag)
        for secret in ("foreign-secret", "target-secret", "other@example.com"):
            self.assertNotIn(secret, rendered)

    def test_empty_database_is_distinct_from_target_account_absent(self):
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "")
        self.assertEqual(diag["database_summary"]["ownership_rows"], 0)
        self.assertEqual(diag["database_summary"]["distinct_account_count"], 0)
        self.assertEqual(diag["database_summary"]["account_storage_types"], {})
        self.assertIn("ownership", ultra0.token_diagnostic_summary(diag))

    def test_app_ownership_entry_is_distinct_from_subscription_receipt(self):
        self.row("target@example.com", data="", product=ultra0.PKG)
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "")
        self.assertEqual(diag["reason"], "no_product_rows")
        self.assertEqual(diag["target_inventory"], {
            "google_one_app_rows": 1, "g1_products": [], "other_document_rows": 0, "g1_product_count": 0})
        self.assertIn("bản ghi ứng dụng", ultra0.token_diagnostic_summary(diag))

    def test_other_g1_products_are_diagnosed_without_broadening_token_selection(self):
        self.row("target@example.com", "not-selected-secret", product="g1.play.20tb")
        self.row("target@example.com", data="", product="unrecognized-document-secret")
        self.row("other@example.com", "foreign-token-secret", product="g1.foreign.product")
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "")
        self.assertEqual(diag["target_inventory"]["g1_products"], [
            {"product": "g1.play.20tb", "rows": 1, "receipt_rows": 1, "expiry_rows": 1}])
        self.assertEqual(diag["target_inventory"]["other_document_rows"], 1)
        for value in ("secret", "other@example.com", "g1.foreign.product"):
            self.assertNotIn(value, json.dumps(diag))

    def test_owner_storage_metadata_contains_counts_without_foreign_identifiers(self):
        self.row("other@example.com", "other-token")
        self.row(None, "blank-account-token")
        self.row("", "empty-account-token")
        self.row(b"opaque-owner-id", "opaque-token")
        diag = {}
        ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag)
        summary = diag["database_summary"]
        self.assertEqual(summary["ownership_rows"], 4)
        self.assertEqual(summary["blank_account_rows"], 2)
        self.assertEqual(summary["account_storage_types"], {"blob": 1, "null": 1, "text": 2})
        self.assertNotIn("opaque-owner-id", json.dumps(diag))
        self.assertNotIn("other@example.com", json.dumps(diag))

    def test_diagnostics_explain_rejected_receipts_without_exposing_values(self):
        self.row("target@example.com", data="not json")
        self.row("target@example.com", data="[]")
        self.row("target@example.com", data="{}")
        self.row("target@example.com", data=json.dumps({"token": "alias-secret"}))
        self.row("target@example.com", "expiry-secret", expiry=None)
        diag = {}
        ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag)
        self.assertEqual(diag["reason"], "no_usable_token")
        self.assertEqual(diag["rejected"], {"invalid_json": 1, "receipt_not_object": 1,
                                          "missing_purchase_token": 2, "invalid_expiry": 1})
        self.assertEqual(diag["token_fields"], {"purchaseToken": 1, "token": 1})
        self.assertNotIn("secret", json.dumps(diag))

    def test_sku_underscore_is_literal_rather_than_sql_wildcard(self):
        self.row("target@example.com", "wrong-token", product="g1.2tb.ai.subsXvariant")
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com"), "")

    def test_changed_snapshot_retries_then_reads_stable_copy(self):
        self.row("target@example.com")
        attempts = 0

        def changing_shell(*args, **kwargs):
            nonlocal attempts
            if args[0] == "shell" and "fingerprint()" in args[1]:
                attempts += 1
                if attempts < 3:
                    return "SNAPSHOT_CHANGED"
            return self.fake_shell(*args, **kwargs)

        self.sh.side_effect = changing_shell
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "target-token")
        self.assertEqual(diag["snapshot"]["attempts"], 3)

    def test_continuously_changing_snapshot_is_a_read_error(self):
        def unstable_shell(*args, **kwargs):
            if args[0] == "shell" and "fingerprint()" in args[1]:
                return "SNAPSHOT_CHANGED"
            return self.fake_shell(*args, **kwargs)
        self.sh.side_effect = unstable_shell
        diag = {}
        with self.assertRaises(ultra0.PurchaseTokenReadError):
            ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag)
        self.assertEqual(diag["reason"], "read_failed")
        self.assertEqual(diag["snapshot"]["attempts"], 3)

    def test_corrupt_transfer_is_a_read_error_not_missing_token(self):
        def corrupt_transfer(*args, **kwargs):
            return b"corrupt bytes" if args[0] == "exec-out" else self.fake_shell(*args, **kwargs)
        self.sh.side_effect = corrupt_transfer
        with self.assertRaises(ultra0.PurchaseTokenReadError):
            ultra0.read_purchase_token("subs_variant", "target@example.com")


    def test_new_ai_pro_source_is_selected_only_for_its_own_account(self):
        self.row("target@example.com", "new-source-token", product="g1.play.2tb.ai")
        self.row("other@example.com", "foreign-token-secret", 9000000, product="g1.2tb.ai.subs_variant")
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "new-source-token")
        self.assertEqual(diag["selected_product"], "g1.play.2tb.ai")
        self.assertCountEqual(diag["matched_products"], ["g1.2tb.ai.subs_variant", "g1.play.2tb.ai"])
        self.assertNotIn("foreign-token-secret", json.dumps(diag))
        self.assertNotIn("other@example.com", json.dumps(diag))

    def test_decorated_supported_document_is_canonicalized_for_inventory_and_selection(self):
        product = "g1.play.2tb.ai"
        self.row("target@example.com", "decorated-token", product=f"inapp:{ultra0.PKG}:subs:{product}")
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "decorated-token")
        self.assertEqual(diag["selected_product"], product)
        self.assertEqual(diag["target_inventory"]["g1_products"], [
            {"product": product, "rows": 1, "receipt_rows": 1, "expiry_rows": 1}])

    def test_supported_product_lookalikes_and_multi_product_documents_are_rejected(self):
        product = "g1.play.2tb.ai"
        for doc_id in ["x" + product, product + "x", product + ".annual", product + "_other", product + "-other",
                       "g1.2tb.ai.subs_variant.extra", "inapp:g1.2tb.ai.subs_variant:g1.play.2tb.ai"]:
            self.row("target@example.com", "must-not-select", product=doc_id)
        diag = {}
        for selector in ("subs_variant", "g1.play.2tb.ai", "g1.2tb.ai.subs_variant"):
            with self.subTest(selector=selector):
                self.assertEqual(ultra0.read_purchase_token(selector, "target@example.com", diagnostics=diag), "")
                self.assertEqual(diag["product_rows"], 0)

    def test_receipt_product_id_cannot_contradict_supported_document_product(self):
        product = "g1.play.2tb.ai"
        self.row("target@example.com", expiry=9000000, product=product,
                 data=json.dumps({"purchaseToken": "contradicting-token", "productId": "g1.2tb.ai.subs_variant"}))
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com"), "")
        self.row("target@example.com", product=product,
                 data=json.dumps({"purchaseToken": "matching-token", "productId": product}))
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com"), "matching-token")

    def test_distinct_active_products_are_ambiguous_until_explicit_source_is_selected(self):
        old, new = "g1.2tb.ai.subs_variant", "g1.play.2tb.ai"
        self.row("target@example.com", "old-source-token", 9000000, product=old)
        self.row("target@example.com", "new-source-token", 2000000, product=new)
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "")
        self.assertEqual(diag["reason"], "ambiguous_products")
        self.assertCountEqual(diag["matched_products"], [old, new])
        self.assertEqual(ultra0.read_purchase_token(new, "target@example.com"), "new-source-token")
        self.assertEqual(ultra0.read_purchase_token(old, "target@example.com"), "old-source-token")
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", expected_token="new-source-token"), "new-source-token")

    def test_active_supported_product_is_preferred_over_other_expired_product(self):
        self.row("target@example.com", "expired-old", 900000, product="g1.2tb.ai.subs_variant")
        self.row("target@example.com", "active-new", 2000000, product="g1.play.2tb.ai")
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "active-new")
        self.assertTrue(diag["selected_active"])
        self.assertEqual(diag["selected_product"], "g1.play.2tb.ai")

    def test_distinct_expired_products_remain_ambiguous_instead_of_guessing_latest(self):
        self.row("target@example.com", "expired-old", 800000, product="g1.2tb.ai.subs_variant")
        self.row("target@example.com", "expired-new", 900000, product="g1.play.2tb.ai")
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "")
        self.assertEqual(diag["reason"], "ambiguous_products")

    def test_identical_token_across_supported_products_is_not_false_ambiguity(self):
        self.row("target@example.com", "same-token", 2000000, product="g1.2tb.ai.subs_variant")
        self.row("target@example.com", "same-token", 3000000, product="g1.play.2tb.ai")
        diag = {}
        self.assertEqual(ultra0.read_purchase_token("subs_variant", "target@example.com", diagnostics=diag), "same-token")
        self.assertEqual(diag["reason"], "selected")


class ProcessTokenAccountTests(unittest.TestCase):
    def setUp(self):
        self.read_signature = inspect.signature(ultra0.read_purchase_token)
        self.mocks = {}
        defaults = {
            "current_play_account": "target@example.com", "read_purchase_token": "target-token",
            "launch_app": 123, "run_trial": {"offers": [], "launched": None, "purchase": None, "errors": []},
            "switch_play": True, "add_account": True, "confirm_zero": {}, "verify": "",
        }
        for name, result in defaults.items():
            p = patch.object(ultra0, name, return_value=result)
            self.mocks[name] = p.start()
            self.addCleanup(p.stop)
        for p in [patch.object(ultra0, "SKIP_ACCOUNT_CHECK", True, create=True),
                  patch.object(ultra0, "note"), patch.object(ultra0, "warn"),
                  patch.object(ultra0, "ok"), patch("builtins.print")]:
            p.start()
            self.addCleanup(p.stop)

    def token_arguments(self):
        call = self.mocks["read_purchase_token"].call_args
        return self.read_signature.bind(*call.args, **call.kwargs).arguments

    def assert_no_launch(self):
        self.mocks["launch_app"].assert_not_called()
        self.mocks["run_trial"].assert_not_called()

    def test_force_explicit_email_scopes_upgrade_token_to_requested_account(self):
        ultra0.process("target@example.com", add=False, stack=True)
        self.assertEqual(self.token_arguments()["account_email"], "target@example.com")
        self.mocks["switch_play"].assert_not_called()
        self.mocks["current_play_account"].assert_not_called()
        kwargs = self.mocks["run_trial"].call_args.kwargs
        self.assertTrue(kwargs["stack"])
        self.assertEqual(kwargs["old_token"], "target-token")
        self.assertEqual(kwargs["stack_mode"], 5)

    def test_force_placeholder_resolves_current_account_before_reading_token(self):
        events = []
        self.mocks["current_play_account"].side_effect = lambda **k: events.append("resolve") or "target@example.com"
        self.mocks["read_purchase_token"].side_effect = lambda *a, **k: events.append("token") or "target-token"
        ultra0.process("current@device", add=False, stack=True)
        self.assertEqual(events, ["resolve", "token"])
        self.mocks["current_play_account"].assert_called_once_with(open_store=True)
        self.assertEqual(self.token_arguments()["account_email"], "target@example.com")
        self.mocks["switch_play"].assert_not_called()

    def test_unreadable_placeholder_stops_upgrade_before_token_or_launch(self):
        self.mocks["current_play_account"].return_value = ""
        result = ultra0.process("current@device", add=False, stack=True)
        self.assertEqual(result["status"], "play_account_unverified")
        self.mocks["read_purchase_token"].assert_not_called()
        self.assert_no_launch()

    def test_missing_upgrade_token_stops_without_cross_account_fallback(self):
        self.mocks["read_purchase_token"].return_value = ""
        result = ultra0.process("target@example.com", add=False, stack=True)
        self.assertEqual(result["status"], "purchase_token_not_found")
        self.assert_no_launch()

    def test_ambiguous_product_tokens_stop_upgrade_without_opening_billing(self):
        def ambiguous(*args, diagnostics=None, **kwargs):
            diagnostics.update(reason="ambiguous_products", matched_products=["g1.2tb.ai.subs_variant", "g1.play.2tb.ai"])
            return ""
        self.mocks["read_purchase_token"].side_effect = ambiguous
        result = ultra0.process("target@example.com", add=False, stack=True)
        self.assertEqual(result["status"], "purchase_token_ambiguous")
        self.assert_no_launch()

    def test_explicit_token_source_restricts_lookup_but_does_not_change_requested_offer(self):
        ultra0.process("target@example.com", add=False, plan="pro6c", stack=True, token_product="g1.play.2tb.ai")
        self.assertEqual(self.token_arguments()["sku_short"], "g1.play.2tb.ai")
        self.assertEqual(self.token_arguments()["account_email"], "target@example.com")
        kwargs = self.mocks["run_trial"].call_args.kwargs
        self.assertEqual(kwargs["plan"], "pro6c")
        self.assertEqual(kwargs["old_token"], "target-token")

    def test_subscription_database_read_error_stops_as_read_failed(self):
        self.mocks["read_purchase_token"].side_effect = ultra0.PurchaseTokenReadError("offline mock database unavailable")
        result = ultra0.process("target@example.com", add=False, stack=True)
        self.assertEqual(result["status"], "purchase_token_read_failed")
        self.assertIn("offline mock database unavailable", result["error"])
        self.assert_no_launch()

    def test_explicit_old_token_is_validated_even_without_stack(self):
        self.mocks["read_purchase_token"].return_value = ""
        result = ultra0.process("target@example.com", add=False, old_token="foreign-token")
        self.assertEqual(self.token_arguments()["expected_token"], "foreign-token")
        self.assertEqual(result["status"], "purchase_token_account_unverified")
        self.assert_no_launch()

    def test_verified_explicit_token_is_used_with_requested_upgrade_mode(self):
        self.mocks["read_purchase_token"].return_value = "verified-token"
        ultra0.process("target@example.com", add=False, old_token="verified-token", stack_mode=3)
        self.assertEqual(self.token_arguments()["expected_token"], "verified-token")
        kwargs = self.mocks["run_trial"].call_args.kwargs
        self.assertTrue(kwargs["stack"])
        self.assertEqual(kwargs["old_token"], "verified-token")
        self.assertEqual(kwargs["stack_mode"], 3)

    def test_plain_registration_needs_no_existing_purchase_token(self):
        self.mocks["read_purchase_token"].side_effect = AssertionError("plain registration must not read subscription tokens")
        self.mocks["current_play_account"].side_effect = AssertionError("force must skip account UI for plain registration")
        ultra0.process("current@device", add=False)
        self.mocks["read_purchase_token"].assert_not_called()
        kwargs = self.mocks["run_trial"].call_args.kwargs
        self.assertFalse(kwargs["stack"])
        self.assertEqual(kwargs["old_token"], "")
        self.assertIsNone(kwargs["stack_mode"])

    def test_list_only_never_reads_or_passes_purchase_tokens(self):
        result = ultra0.process("current@device", add=False, list_only=True, stack=True, old_token="unverified-token", stack_mode=5)
        self.assertEqual(result["status"], "listed")
        self.mocks["read_purchase_token"].assert_not_called()
        kwargs = self.mocks["run_trial"].call_args.kwargs
        self.assertFalse(kwargs["stack"])
        self.assertEqual(kwargs["old_token"], "")
        self.assertIsNone(kwargs["stack_mode"])
        self.assertTrue(kwargs["list_only"])
        self.mocks["confirm_zero"].assert_not_called()
        self.mocks["verify"].assert_not_called()

    def test_no_switch_rejects_wrong_account_before_token_read(self):
        with patch.object(ultra0, "SKIP_ACCOUNT_CHECK", False):
            self.mocks["current_play_account"].return_value = "other@example.com"
            result = ultra0.process("target@example.com", add=False, no_switch=True, stack=True)
        self.assertEqual(result["status"], "wrong_account")
        self.mocks["read_purchase_token"].assert_not_called()
        self.assert_no_launch()

    def test_upgrade_token_is_json_encoded_without_raw_javascript_injection(self):
        token = 'test-token"; throw new Error("must stay a string"); //\nline2\\end'
        script = ultra0.build_js(plan="pro6", stack=True, old_token=token)
        self.assertIn(json.dumps(token), script)
        self.assertNotIn(token, script)
        self.assertNotIn("queryPurchasesAsync", script)
        self.assertIn("setOldPurchaseToken", script)

    def test_upgrade_modes_are_validated_only_when_used(self):
        for invalid in [0, 6, -1]:
            with self.subTest(mode=invalid), self.assertRaises(ValueError):
                ultra0.build_js(plan="pro6", stack=True, old_token="verified-token", stack_mode=invalid)
        ultra0.build_js(plan="pro6", stack_mode=99)
        listing = ultra0.build_js(plan="pro6", list_only=True, stack=True,
                                  old_token="secret-ignored-in-list-mode", stack_mode=99)
        self.assertNotIn("secret-ignored-in-list-mode", listing)

    def test_prior_active_subscription_does_not_prove_new_purchase_succeeded(self):
        self.mocks["run_trial"].return_value = {"offers": [], "launched": {"code": 0}, "purchase": None, "errors": []}
        self.mocks["confirm_zero"].return_value = {"confirmed": False, "ineligible": True}
        self.mocks["verify"].return_value = "Google AI Ultra existing subscription"
        result = ultra0.process("target@example.com", add=False)
        self.assertNotEqual(result["status"], "subscribed")

    def test_confirmed_sheet_without_success_callback_is_only_submitted(self):
        self.mocks["run_trial"].return_value = {"offers": [], "launched": {"code": 0}, "purchase": None, "errors": []}
        self.mocks["confirm_zero"].return_value = {"confirmed": True}
        self.mocks["verify"].return_value = "Google AI Ultra existing subscription"
        result = ultra0.process("target@example.com", add=False)
        self.assertEqual(result["status"], "submitted")

    def test_confirmed_sheet_and_success_callback_are_required_for_subscribed(self):
        self.mocks["run_trial"].return_value = {"offers": [], "launched": {"code": 0}, "purchase": {"code": 0}, "errors": []}
        self.mocks["confirm_zero"].return_value = {"confirmed": True}
        result = ultra0.process("target@example.com", add=False)
        self.assertEqual(result["status"], "subscribed")

    def test_failed_or_cancelled_purchase_callback_prevents_sheet_confirmation(self):
        for code, expected in [(1, "purchase_cancelled"), (5, "purchase_failed")]:
            with self.subTest(code=code):
                self.mocks["run_trial"].return_value = {"offers": [], "launched": {"code": 0}, "purchase": {"code": code}, "errors": []}
                result = ultra0.process("target@example.com", add=False)
                self.assertEqual(result["status"], expected)
                self.mocks["confirm_zero"].assert_not_called()

    def test_purchase_error_arriving_during_confirmation_is_recorded_and_prioritized(self):
        trial = {"offers": [], "launched": {"code": 0}, "purchase": None, "errors": [], "events": []}
        callback = {"ev": "purchase_cb", "code": 5, "msg": "Offer became unavailable"}
        self.mocks["run_trial"].return_value = trial

        def confirm(**kwargs):
            trial["purchase"] = callback
            trial["events"].append(callback)
            return {"confirmed": True}

        self.mocks["confirm_zero"].side_effect = confirm
        self.mocks["verify"].return_value = "Google AI Ultra existing subscription"
        result = ultra0.process("target@example.com", add=False)
        self.assertEqual(result["purchase"], callback)
        self.assertEqual(result["status"], "purchase_failed")

    def test_generic_billing_error_is_recorded_without_navigating_to_old_subscription(self):
        trial = {"offers": [], "launched": {"code": 0}, "purchase": None, "errors": [], "events": []}
        self.mocks["run_trial"].return_value = trial
        message = "Something went wrong on our end. Please try again."

        def confirm(**kwargs):
            trial["events"].append({"ev": "activity", "a": "example.BillingActivity"})
            return {"confirmed": False, "billing_error": True, "text": message}

        self.mocks["confirm_zero"].side_effect = confirm
        self.mocks["verify"].return_value = "Prior active Google AI Ultra subscription"
        result = ultra0.process("target@example.com", add=False)
        self.assertEqual(result["status"], "billing_error")
        self.assertEqual(result["sheet"]["text"], message)
        self.assertEqual(result["events"], trial["events"])
        self.mocks["verify"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
