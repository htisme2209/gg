"""Offline coverage for candidate discovery, pricing, reports and batch completion."""
from contextlib import redirect_stdout
import io
import itertools
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import query_sku as sku


def offer(**updates):
    result = {"product": "g1.2tb.ai.subs_variant", "id": "trial", "title": "AI plan",
              "token": "private-offer-token", "phases": [
                  {"micros": "0", "period": "P1W", "cycles": 13, "currency": "VND", "formatted_price": "0 ₫"},
                  {"micros": "199000000000", "period": "P1M", "cycles": 0, "currency": "VND", "formatted_price": "199.000 ₫"}]}
    result.update(updates)
    return result


class CandidatesAndPricesTests(unittest.TestCase):
    def test_discovery_includes_full_matrix_and_prioritizes_known_products(self):
        actual = sku.generate_candidates()
        known = list(dict.fromkeys(sku.KNOWN_PRODUCTS))
        self.assertEqual(actual[:len(known)], known)
        self.assertEqual(len(actual), len(set(actual)))
        expected = {".".join(part for part in (prefix, capacity, suffix.strip(".")) if part)
                    for prefix, capacity, suffix in
                    itertools.product(sku.PREFIXES, sku.CAPACITIES, sku.SUFFIXES)}
        self.assertTrue(expected.issubset(actual))
        self.assertTrue({"g1.2tb.ai.subs_variant", "g1.2tb.subs_variant", "g1.play.2tb.ai",
                         "g1.30gb.lite", "g1.play.2tb.ai.subs_variant",
                         "g1.youtube_premium_individual_add_on"}.issubset(actual))
        self.assertTrue({f"{prefix}.{name}" for prefix, name in itertools.product(
            sku.PREFIXES, ("ai.pro", "ai.ultra", "ai.plus", "ai.lite", "2tb.ai", "5tb.ai")
        )}.issubset(sku.LOOSE_PRODUCTS))
        self.assertEqual(actual, sku.generate_candidates())

    def test_offer_tiers_cover_expected_patterns_without_full_cross_product(self):
        core = sku.build_offer_candidates()
        expanded = sku.build_offer_candidates(tier=2)
        self.assertEqual(core[:len(sku.KNOWN_OFFERS)], list(sku.KNOWN_OFFERS))
        self.assertEqual(expanded[:len(core)], core)
        self.assertEqual(len(core), len(set(core)))
        self.assertEqual(len(expanded), len(set(expanded)))
        self.assertLess(len(core), 20_000)
        self.assertLess(len(expanded), 100_000)
        self.assertTrue({
            "eft-3mo", "3mo-eft", "eft-1yr", "eft-14d", "trial-1mo", "intro-3mo",
            "3months-eft-2024", "eft-3m-2027", "intro-price-3mo", "75off-3mo",
            "half-off-6mo", "1mo-free", "3mo-50off", "6months-eft-ss-2026",
            "eft-3mo-fold8", "eft-6mo-motorola", "eft-12mo-chromebook-plus",
            "eft-3mo-vzw", "eft-1mo-playpass", "eft-3mo-churn", "student-eft-12mo",
        }.issubset(core))
        extra = {
            "eft-3mo-q1-2026", "6months-eft-ss-h2-2026", "eft-3mo-2026-2tb",
            "eft-6mo-ss-2027", "ss-6months-eft-2026", "6months-trial-samsung-2026",
            "trial-30d-oppo", "pixel-4months-promo", "honor-intro-2mo",
        }
        self.assertTrue(extra.issubset(expanded))
        self.assertTrue(extra.isdisjoint(core))

    def test_underscore_offer_ids_are_optional_and_keep_the_original_variants(self):
        expanded = sku.build_offer_candidates(tier=2)
        with_underscores = sku.build_offer_candidates(include_underscores=True, tier=2)
        expected = {"eft_3mo", "free_trial_1m", "eft_3mo_q1_2026", "6months_eft_ss_h2_2026"}
        self.assertTrue(expected.isdisjoint(expanded))
        self.assertTrue(expected.issubset(with_underscores))
        self.assertEqual(with_underscores[:len(expanded)], expanded)
        self.assertEqual(len(with_underscores), len(set(with_underscores)))

    def test_empty_capacity_produces_prefix_and_suffix_without_empty_segments(self):
        self.assertIn("", sku.CAPACITIES)
        self.assertIn("", sku.SUFFIXES)
        self.assertIn(".ai", sku.SUFFIXES)
        candidates = sku.generate_candidates()
        actual = set(candidates)
        for prefix in sku.PREFIXES:
            with self.subTest(prefix=prefix):
                self.assertIn(prefix, actual)
                self.assertIn(prefix + ".ai", actual)
                self.assertNotIn(prefix + ".", actual)
                self.assertNotIn(prefix + "..ai", actual)
        self.assertTrue(all(".." not in product and not product.endswith(".") for product in candidates))

    def test_discovery_preserves_manual_and_file_priority_before_known_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "skus.txt"
            source.write_text("g1.file_only\n" + sku.KNOWN_PRODUCTS[0] + "\ng1.manual_only # duplicate\n", encoding="utf-8")
            candidates = sku.build_candidates(["g1.manual_only", sku.KNOWN_PRODUCTS[0]], discover=True, sku_file=source)
        prefix = ["g1.manual_only", sku.KNOWN_PRODUCTS[0], "g1.file_only"]
        self.assertEqual(candidates[:len(prefix)], prefix)
        self.assertEqual(len(candidates), len(set(candidates)))
        remaining_known = [product for product in dict.fromkeys(sku.KNOWN_PRODUCTS) if product not in prefix]
        self.assertEqual(candidates[len(prefix):len(prefix) + len(remaining_known)], remaining_known)

    def test_manual_and_file_candidates_preserve_order_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "skus.txt"
            source.write_text("\ufeff# comment\ng1.manual # note\ng1.second\n\n", encoding="utf-8")
            self.assertEqual(sku.build_candidates([" g1.manual ", "g1.first"], sku_file=source),
                             ["g1.manual", "g1.first", "g1.second"])

    def test_invalid_candidate_ids_fail_before_scanning(self):
        for invalid in ["UPPERCASE", "g1.bad-name", "g1 space", "../bad", "g1;command", "g1..ai", "g1.", "x" * 201]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                sku.build_candidates([invalid])

    def test_calendar_periods_and_repeated_week_cycles(self):
        for period, cycles, expected in [("P1Y", 1, "1 năm"), ("P6M", 1, "6 tháng"),
                                         ("P13W", 1, "13 tuần"), ("P1W", 13, "13 tuần")]:
            with self.subTest(period=period, cycles=cycles):
                self.assertEqual(sku.format_period(period, cycles), expected)

    def test_all_pricing_phases_and_their_real_currency_are_reported(self):
        data = offer()
        data["phases"].insert(1, {"micros": "99000000000", "period": "P1M", "cycles": 3,
                                   "currency": "VND", "formatted_price": "99.000 ₫"})
        row = sku.offer_row(data)
        self.assertTrue(row["free"])
        self.assertIn("13 tuần", row["trial"])
        self.assertIn("99.000 ₫", row["after"])
        self.assertIn("199.000 ₫", row["after"])
        self.assertNotIn("$", row["after"])

    def test_paid_offer_is_not_misclassified_as_trial(self):
        row = sku.offer_row(offer(phases=[{"micros": "4500000", "period": "P1M", "currency": "EUR"}]))
        self.assertFalse(row["free"])
        self.assertEqual(row["trial"], "Không có")
        self.assertIn("4.5 EUR", row["after"])

    def test_finite_paid_intro_shows_duration_but_recurring_price_does_not(self):
        data = offer(phases=[
            {"micros": "1000000", "period": "P1M", "cycles": 3, "recurrence_mode": 2,
             "currency": "EUR", "formatted_price": "1 €"},
            {"micros": "5000000", "period": "P1M", "cycles": 0, "recurrence_mode": 1,
             "currency": "EUR", "formatted_price": "5 €"}])
        row = sku.offer_row(data)
        intro, recurring = row["after"].split(" → ")
        self.assertIn("trong 3 tháng", intro)
        self.assertNotIn("trong", recurring)
        self.assertIn("5 €", recurring)

    def test_decimal_fallback_does_not_invent_dollar_currency(self):
        row = sku.offer_row(offer(phases=[{"micros": "1234567", "period": "P1M", "currency": "JPY"}]))
        self.assertIn("1.234567 JPY", row["after"])
        self.assertNotIn("$", row["after"])

    def test_reports_strip_tokens_recursively_without_mutating_source(self):
        report = {"offers": [offer(base_plan="monthly")], "errors": [], "candidates": [], "products": [],
                  "batches": [{"offerToken": "nested-secret", "purchaseToken": "purchase-secret"}], "status": "complete"}
        with tempfile.TemporaryDirectory() as directory:
            json_path, md_path = sku.write_reports(report, Path(directory) / "report.json")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertNotIn("token", data["offers"][0])
            self.assertEqual(data["batches"], [{}])
            self.assertEqual(data["offers"][0]["base_plan"], "monthly")
            markdown = md_path.read_text(encoding="utf-8")
            self.assertIn("| Sản phẩm | Base Plan ID | Offer ID |", markdown)
            self.assertIn("| g1.2tb.ai.subs_variant | monthly | trial |", markdown)
            self.assertNotIn("private-offer-token", markdown)
        self.assertEqual(report["offers"][0]["token"], "private-offer-token")

    def test_tokens_can_be_explicitly_included_in_json(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path, _ = sku.write_reports({"offers": [offer()]}, Path(directory) / "report", include_tokens=True)
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8"))["offers"][0]["token"], "private-offer-token")


class FakeScript:
    def __init__(self):
        self.callback = None
        self.on_load = lambda: self.emit({"ev": "ready"})
        self.query_action = lambda batch, products: None
        self.exports_sync = Mock()
        self.exports_sync.query.side_effect = lambda *args: self.query_action(*args)
        self.load = Mock(side_effect=lambda: self.on_load())
        self.unload = Mock()

    def on(self, event, callback):
        if event != "message":
            raise AssertionError(event)
        self.callback = callback

    def emit(self, payload):
        self.callback({"type": "send", "payload": payload}, None)


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.script = FakeScript()
        self.session = Mock()
        self.session.create_script.return_value = self.script
        self.scanner = sku.OfferScanner(self.session, timeout=0.02)
        self.scanner.start()

    def complete(self, batch, products=(), code=0, **kwargs):
        self.script.emit({"ev": "query_complete", "batch": batch, "products": list(products), "code": code, **kwargs})

    def test_pd_and_first_offer_do_not_finish_before_remaining_offers(self):
        emitted = threading.Event()
        results = []
        errors = []
        self.scanner.timeout = 2

        def begin(batch, products):
            self.script.emit({"ev": "pd", "batch": batch, "code": 0, "n": 1})
            self.script.emit({"ev": "offer", "batch": batch, **offer(id="first")})
            emitted.set()

        def query():
            try:
                results.append(self.scanner.query(["g1.test"], "batch"))
            except BaseException as error:
                errors.append(error)

        self.script.query_action = begin
        worker = threading.Thread(target=query)
        worker.start()
        self.addCleanup(worker.join, 3)
        self.assertTrue(emitted.wait(1))
        self.assertTrue(worker.is_alive())
        self.assertFalse(self.scanner.pending["batch"]["done"].is_set())
        self.script.emit({"ev": "offer", "batch": "batch", **offer(id="second")})
        self.complete("batch", ["g1.test"])
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual([o["id"] for o in results[0]["offers"]], ["first", "second"])
        self.assertEqual(results[0]["status"], "ok")

    def test_zero_products_is_a_completed_empty_batch(self):
        self.script.query_action = lambda batch, products: self.complete(batch)
        result = self.scanner.query(["g1.missing"], 1)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["offers"], [])
        self.assertEqual(result["not_returned"], ["g1.missing"])

    def test_billing_errors_are_retained_and_not_described_as_missing_skus(self):
        def respond(batch, products):
            self.script.emit({"ev": "query_error", "batch": batch, "m": "service unavailable"})
            self.complete(batch, code=2, msg="network failed")
        self.script.query_action = respond
        result = self.scanner.query(["g1.test"], 1)
        self.assertEqual(result["status"], "error")
        self.assertIn("service unavailable", result["errors"])
        self.assertTrue(any("network failed" in message for message in result["errors"]))
        self.assertEqual(result["not_returned"], [])

    def test_frida_error_during_query_is_retained(self):
        self.script.query_action = lambda *args: self.script.callback({"type": "error", "description": "runtime broke"}, None)
        result = self.scanner.query(["g1.test"], 1)
        self.assertEqual(result["status"], "error")
        self.assertIn("runtime broke", result["errors"])
        self.assertEqual(self.scanner.pending, {})

    def test_timeout_keeps_partial_offers_without_claiming_success(self):
        self.script.query_action = lambda batch, products: self.script.emit({"ev": "offer", "batch": batch, **offer()})
        result = self.scanner.query(["g1.test"], 1)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(len(result["offers"]), 1)
        self.assertTrue(result["errors"])
        self.assertEqual(result["not_returned"], [])
        self.assertEqual(self.scanner.pending, {})

    def test_late_or_foreign_batch_events_cannot_pollute_results(self):
        def respond(batch, products):
            self.script.emit({"ev": "offer", "batch": "foreign", **offer(id="foreign")})
            self.complete(batch)
            self.script.emit({"ev": "offer", "batch": batch, **offer(id="late")})
        self.script.query_action = respond
        result = self.scanner.query(["g1.test"], 1)
        self.assertEqual(result["offers"], [])

    def test_rpc_exception_becomes_error_result(self):
        self.script.query_action = Mock(side_effect=RuntimeError("RPC failed"))
        result = self.scanner.query(["g1.test"], 1)
        self.assertEqual(result["status"], "error")
        self.assertIn("RPC failed", result["errors"])
        self.assertEqual(self.scanner.pending, {})

    def test_start_errors_and_timeout_raise_instead_of_succeeding_empty(self):
        for message in [None, {"type": "error", "description": "Java unavailable"}]:
            with self.subTest(message=message):
                script = FakeScript()
                script.on_load = lambda: script.callback(message, None) if message else None
                session = Mock()
                session.create_script.return_value = script
                scanner = sku.OfferScanner(session, timeout=0.001)
                with self.assertRaises(RuntimeError):
                    scanner.start()

    def test_close_unloads_even_if_dispose_fails_and_leaves_detach_to_owner(self):
        self.script.exports_sync.dispose.side_effect = RuntimeError("already disconnected")
        self.scanner.close()
        self.script.exports_sync.dispose.assert_called_once()
        self.script.unload.assert_called_once()
        self.session.detach.assert_not_called()


class CliTests(unittest.TestCase):
    def test_candidate_id_modes_do_not_touch_device_or_write_reports(self):
        cases = [
            (["--candidate-offers"], "Offer ID", "eft-3mo"),
            (["--candidate-offers", "--offer-tier", "2", "--include-underscores"],
             "tầng 2", "free_trial_1mo_q1_2026"),
            (["--candidate-base-plans"], "Base Plan ID", "annual-plan"),
        ]
        with patch.object(sku, "prepare_device", side_effect=AssertionError("device access")) as prepare, \
                patch.object(sku, "write_reports", side_effect=AssertionError("write")) as write:
            for args, heading, candidate in cases:
                with self.subTest(args=args), redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(sku.main(args), 0)
                    summary, *candidates = output.getvalue().splitlines()
                    self.assertIn(heading, summary)
                    self.assertIn(candidate, candidates)
        prepare.assert_not_called()
        write.assert_not_called()

    def test_discovery_dry_run_does_not_touch_device_or_write_reports(self):
        output = io.StringIO()
        with patch.object(sku, "prepare_device", side_effect=AssertionError("device access")) as prepare, \
                patch.object(sku, "write_reports", side_effect=AssertionError("write")) as write, redirect_stdout(output):
            result = sku.main(["--discover", "--dry-run"])
        self.assertEqual(result, 0)
        self.assertIn("g1.2tb.ai.subs_variant", output.getvalue())
        prepare.assert_not_called()
        write.assert_not_called()

    def test_manual_sku_cli_uses_batches_and_cleans_up(self):
        session = Mock()
        scanner = Mock()
        scanner.query.return_value = {"batch": 1, "requested": ["g1.manual"], "status": "ok", "code": 0,
                                      "products": [], "offers": [], "errors": [], "not_returned": ["g1.manual"]}
        with patch.object(sku, "prepare_device", return_value=(session, "target@example.com")) as prepare, \
                patch.object(sku, "OfferScanner", return_value=scanner), \
                patch.object(sku, "write_reports", return_value=(Path("x.json"), Path("x.md"))) as write, \
                redirect_stdout(io.StringIO()):
            result = sku.main(["g1.manual", "--serial", "offline-device"])
        self.assertEqual(result, 0)
        prepare.assert_called_once_with("offline-device", None)
        scanner.query.assert_called_once_with(["g1.manual"], 1)
        scanner.close.assert_called_once()
        session.detach.assert_called_once()
        self.assertEqual(write.call_args.args[0]["status"], "complete")

    def test_startup_failure_is_reported_and_resources_cleaned_up(self):
        session = Mock()
        scanner = Mock()
        scanner.start.side_effect = RuntimeError("Billing unavailable")
        with patch.object(sku, "prepare_device", return_value=(session, "target@example.com")), \
                patch.object(sku, "OfferScanner", return_value=scanner), \
                patch.object(sku, "write_reports", return_value=(Path("x.json"), Path("x.md"))) as write, \
                redirect_stdout(io.StringIO()):
            result = sku.main(["g1.manual"])
        self.assertEqual(result, 1)
        scanner.close.assert_called_once()
        session.detach.assert_called_once()
        report = write.call_args.args[0]
        self.assertEqual(report["status"], "error")
        self.assertIn("Billing unavailable", report["errors"])

    def test_detach_failure_preserves_results_in_partial_report(self):
        session = Mock()
        session.detach.side_effect = RuntimeError("device disconnected")
        scanner = Mock()
        returned_offer = offer()
        scanner.query.return_value = {"batch": 1, "requested": ["g1.manual"], "status": "ok", "code": 0,
                                      "products": ["g1.manual"], "offers": [returned_offer], "errors": [], "not_returned": []}
        with patch.object(sku, "prepare_device", return_value=(session, "target@example.com")), \
                patch.object(sku, "OfferScanner", return_value=scanner), \
                patch.object(sku, "write_reports", return_value=(Path("x.json"), Path("x.md"))) as write, \
                redirect_stdout(io.StringIO()):
            result = sku.main(["g1.manual"])
        self.assertEqual(result, 1)
        write.assert_called_once()
        report = write.call_args.args[0]
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["offers"], [returned_offer])
        self.assertEqual(report["products"], ["g1.manual"])
        self.assertTrue(any("device disconnected" in error for error in report["errors"]))
        scanner.close.assert_called_once()
        session.detach.assert_called_once()


if __name__ == "__main__":
    unittest.main()
