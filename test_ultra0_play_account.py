"""Offline tests for identifying the signed-in Google Play account safely."""
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import call, patch

import ultra0


def screen(*items):
    root = ET.Element("hierarchy")
    window = ET.SubElement(root, "node", {"package": ultra0.VENDING, "bounds": "[0,0][1080,1920]"})
    for attributes in items:
        defaults = {"package": ultra0.VENDING, "text": "", "content-desc": "",
                    "class": "android.widget.TextView", "bounds": "[100,100][900,200]"}
        defaults.update(attributes)
        ET.SubElement(window, "node", defaults)
    return ET.tostring(root, encoding="unicode")


AVATAR = screen({"content-desc": "Signed in as Test Person target@example.com\nGoogle One account.\nAccount and settings.",
                 "class": "android.widget.FrameLayout", "clickable": "true"})
WELCOME = screen({"text": "Welcome to Google Play"},
                 {"text": "Not now", "content-desc": "Not now", "clickable": "true"})
LEGACY_AVATAR = screen({"content-desc": "Account and settings", "clickable": "true"})
MENU = screen({"text": "Manage your Google Account"}, {"text": "target@example.com"})
SUBSCRIPTION_DETAIL = screen(
    {"text": "Subscriptions"}, {"text": "Active"}, {"text": "Canceled"},
    {"text": "Google AI Pro (5 TB)"}, {"text": "Your subscription will end Nov 19, 2028"},
    {"content-desc": "Navigate up", "bounds": "[0,0][100,100]", "clickable": "true"},
    {"text": "Resubscribe", "bounds": "[100,1500][900,1600]", "clickable": "true"})
SUBSCRIPTION_LIST = screen(
    {"text": "Subscriptions"},
    {"content-desc": "Navigate up", "bounds": "[20,100][100,180]", "clickable": "true"})
PAYMENTS_MENU = screen(
    {"text": "Payments & subscriptions"},
    {"content-desc": "Navigate up", "bounds": "[40,120][120,200]", "clickable": "true"})


class PlayAccountXmlTests(unittest.TestCase):
    def parse(self, xml):
        return ultra0._play_account_from_xml(xml)

    def test_personalized_avatar_identifies_current_account(self):
        self.assertEqual(self.parse(AVATAR), "target@example.com")

    def test_account_case_is_normalized(self):
        xml = screen({"content-desc": "Signed in as Person TARGET@EXAMPLE.COM. Account and settings."})
        self.assertEqual(self.parse(xml), "target@example.com")

    def test_two_accounts_in_expanded_menu_are_ambiguous(self):
        xml = screen({"text": "Manage your Google Account"},
                     {"text": "other@example.com"}, {"text": "target@example.com"})
        self.assertEqual(self.parse(xml), "")

    def test_selected_account_in_expanded_menu_is_used(self):
        xml = screen({"text": "Manage your Google Account"},
                     {"text": "other@example.com", "selected": "false"},
                     {"text": "target@example.com", "selected": "true"})
        self.assertEqual(self.parse(xml), "target@example.com")

    def test_checked_account_in_expanded_menu_is_used(self):
        xml = screen({"text": "Manage your Google Account"},
                     {"text": "other@example.com", "checked": "false"},
                     {"text": "target@example.com", "checked": "true"})
        self.assertEqual(self.parse(xml), "target@example.com")

    def test_foreign_package_cannot_supply_signed_in_account(self):
        xml = screen({"package": "com.example.other", "content-desc": "Signed in as other@example.com. Account and settings."})
        self.assertEqual(self.parse(xml), "")

    def test_generic_play_email_is_not_account_evidence(self):
        self.assertEqual(self.parse(screen({"text": "Contact support@example.com"})), "")

    def test_foreign_package_email_cannot_pollute_play_menu(self):
        xml = screen({"text": "Manage your Google Account"},
                     {"text": "other@example.com", "package": "com.example.other"})
        self.assertEqual(self.parse(xml), "")

    def test_malformed_xml_fails_closed(self):
        self.assertEqual(self.parse("<hierarchy><node"), "")


class CurrentPlayAccountTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.shell_calls = []
        patches = [patch.object(ultra0, "ui_xml", return_value="<hierarchy/>"),
                   patch.object(ultra0, "sh", side_effect=self.shell),
                   patch.object(ultra0, "tap", side_effect=lambda *a: self.events.append(("tap", a))),
                   patch.object(ultra0, "tap_text", side_effect=self.tap_text),
                   patch.object(ultra0.time, "sleep"), patch.object(ultra0, "warn")]
        self.xml = patches[0].start()
        self.addCleanup(patches[0].stop)
        for p in patches[1:]:
            p.start()
            self.addCleanup(p.stop)

    def tap_text(self, *labels, **kwargs):
        self.events.append(("tap_text", labels))
        return True

    def shell(self, *args, **kwargs):
        self.shell_calls.append(args)
        if args[0] != "shell":
            raise AssertionError("Unexpected operation: " + repr(args))
        if args[1] == "input keyevent 4":
            self.events.append(("back", ()))
        elif not args[1].startswith("monkey -p " + ultra0.VENDING):
            raise AssertionError("Unexpected operation: " + repr(args))
        return ""

    def test_initial_avatar_is_read_without_tapping_or_back(self):
        self.xml.return_value = AVATAR
        self.assertEqual(ultra0.current_play_account(), "target@example.com")
        self.assertEqual(self.events, [])

    def test_welcome_not_now_is_dismissed_before_reading_avatar(self):
        self.xml.side_effect = [WELCOME, AVATAR]
        self.assertEqual(ultra0.current_play_account(), "target@example.com")
        self.assertEqual(len(self.events), 1)
        self.assertIn(self.events[0][0], ("tap", "tap_text"))

    def test_legacy_avatar_opens_menu_then_closes_own_menu(self):
        self.xml.side_effect = [LEGACY_AVATAR, MENU]
        self.assertEqual(ultra0.current_play_account(), "target@example.com")
        self.assertEqual([event[0] for event in self.events], ["tap", "back"])

    def test_already_open_menu_is_preserved(self):
        self.xml.return_value = MENU
        self.assertEqual(ultra0.current_play_account(), "target@example.com")
        self.assertEqual(self.events, [])

    def test_unreadable_screen_returns_empty_without_back(self):
        self.xml.return_value = screen({"text": "Unknown screen"})
        self.assertEqual(ultra0.current_play_account(), "")
        self.assertFalse(any(event[0] == "back" for event in self.events))

    def test_xml_dump_failure_returns_empty_without_back(self):
        self.xml.side_effect = RuntimeError("offline mock dump failure")
        self.assertEqual(ultra0.current_play_account(), "")
        self.assertFalse(any(event[0] == "back" for event in self.events))

    def test_ambiguous_google_account_entries_are_never_tapped(self):
        self.xml.return_value = screen(
            {"content-desc": "Google Account: other@example.com", "clickable": "true"},
            {"content-desc": "Google Account: target@example.com", "clickable": "true"})
        self.assertEqual(ultra0.current_play_account(), "")
        self.assertEqual(self.events, [])

    def test_foreign_package_welcome_and_dismiss_button_are_never_tapped(self):
        self.xml.return_value = screen(
            {"package": "com.example.other", "text": "Welcome to Google Play"},
            {"package": "com.example.other", "text": "Not now", "clickable": "true"})
        self.assertEqual(ultra0.current_play_account(), "")
        self.assertEqual(self.events, [])

    def test_foreign_dismiss_button_is_not_used_for_play_welcome(self):
        self.xml.return_value = screen(
            {"text": "Welcome to Google Play"},
            {"package": "com.example.other", "text": "Not now", "clickable": "true"})
        self.assertEqual(ultra0.current_play_account(), "")
        self.assertEqual(self.events, [])

    def test_open_store_foregrounds_play_before_reading(self):
        self.xml.return_value = AVATAR
        self.assertEqual(ultra0.current_play_account(open_store=True), "target@example.com")
        self.assertTrue(any("monkey -p " + ultra0.VENDING in call[1] for call in self.shell_calls))
        self.assertEqual(self.events, [])

    def test_deep_subscription_task_returns_via_known_pages_without_resubscribing(self):
        self.xml.side_effect = [SUBSCRIPTION_DETAIL, SUBSCRIPTION_LIST, PAYMENTS_MENU, AVATAR]
        self.assertEqual(ultra0.current_play_account(open_store=True), "target@example.com")
        self.assertEqual(self.events, [("tap", (50, 50)), ("tap", (60, 140)), ("tap", (80, 160))])
        self.assertNotIn(("tap", (500, 1550)), self.events)
        self.assertEqual(self.xml.call_count, 4)

    def test_deep_page_is_preserved_without_explicit_open_store(self):
        self.xml.return_value = SUBSCRIPTION_DETAIL
        self.assertEqual(ultra0.current_play_account(), "")
        self.assertEqual(self.events, [])

    def test_foreign_package_navigation_is_never_used(self):
        self.xml.return_value = screen(
            {"text": "Subscriptions"},
            {"package": "com.example.other", "content-desc": "Navigate up", "clickable": "true"})
        self.assertEqual(ultra0.current_play_account(open_store=True), "")
        self.assertEqual(self.events, [])

    def test_other_pages_do_not_use_up_navigation(self):
        self.xml.return_value = screen({"text": "Settings"}, {"content-desc": "Navigate up", "clickable": "true"})
        self.assertEqual(ultra0.current_play_account(open_store=True), "")
        self.assertEqual(self.events, [])

    def test_ambiguous_account_menu_is_not_navigated_away_from(self):
        self.xml.return_value = screen(
            {"text": "Subscriptions"}, {"content-desc": "Navigate up", "clickable": "true"},
            {"content-desc": "Google Account: other@example.com", "clickable": "true"},
            {"content-desc": "Google Account: target@example.com", "clickable": "true"})
        self.assertEqual(ultra0.current_play_account(open_store=True), "")
        self.assertEqual(self.events, [])

    def test_up_navigation_remains_bounded_if_page_does_not_change(self):
        self.xml.return_value = SUBSCRIPTION_DETAIL
        self.assertEqual(ultra0.current_play_account(open_store=True), "")
        self.assertEqual(self.xml.call_count, 4)
        self.assertEqual(self.events, [("tap", (50, 50))] * 4)

    def test_known_page_without_up_control_never_falls_back_to_back_key(self):
        self.xml.return_value = screen({"text": "Subscriptions"}, {"text": "Resubscribe", "clickable": "true"})
        self.assertEqual(ultra0.current_play_account(open_store=True), "")
        self.assertEqual(self.events, [])


class UiSnapshotTests(unittest.TestCase):
    def shell_fixture(self, outcomes):
        calls, paths, attempts = [], [], {}

        def value_or_raise(value):
            if isinstance(value, Exception):
                raise value
            return value

        def shell(*args, **kwargs):
            self.assertEqual(args[0], "shell")
            self.assertIs(kwargs.get("check"), True)
            self.assertGreater(kwargs.get("timeout", 0), 0)
            command = args[1]
            calls.append(command)
            if command.startswith("uiautomator dump "):
                path = command.removeprefix("uiautomator dump ")
                self.assertRegex(path, r"^/sdcard/ultra0-ui-[0-9a-f]{32}\.xml$")
                self.assertNotIn(path, attempts)
                self.assertLess(len(paths), len(outcomes), "snapshot exceeded expected bounded attempts")
                attempts[path] = outcomes[len(paths)]
                paths.append(path)
                return value_or_raise(attempts[path].get("dump", "UI hierarchy dumped to: " + path))
            if command.startswith("cat "):
                path = command.removeprefix("cat ")
                self.assertIn(path, attempts, "read must use this attempt's own snapshot")
                return value_or_raise(attempts[path].get("xml", "<hierarchy/>"))
            if command.startswith("rm -f "):
                path = command.removeprefix("rm -f ")
                self.assertIn(path, attempts)
                return value_or_raise(attempts[path].get("cleanup", ""))
            raise AssertionError("Unexpected operation: " + command)

        return shell, calls, paths

    def assert_cleaned(self, calls, paths):
        self.assertEqual([command.removeprefix("rm -f ") for command in calls if command.startswith("rm -f ")], paths)
        self.assertNotIn("cat /sdcard/ui.xml", calls)

    def test_valid_snapshot_uses_unique_path_and_checked_cleanup(self):
        xml = '<hierarchy><node text="fresh"/></hierarchy>'
        fake, calls, paths = self.shell_fixture([{"xml": xml}])
        with patch.object(ultra0, "sh", side_effect=fake):
            self.assertEqual(ultra0.ui_xml(), xml)
        self.assertEqual(calls, ["uiautomator dump " + paths[0], "cat " + paths[0], "rm -f " + paths[0]])
        self.assert_cleaned(calls, paths)

    def test_zero_exit_dump_error_is_not_read_and_retries_with_fresh_path(self):
        fake, calls, paths = self.shell_fixture([{"dump": "ERROR: null root node returned"}, {}])
        with patch.object(ultra0, "sh", side_effect=fake):
            self.assertEqual(ultra0.ui_xml(), "<hierarchy/>")
        self.assertEqual(len(paths), 2)
        self.assertNotIn("cat " + paths[0], calls)
        self.assert_cleaned(calls, paths)

    def test_dump_exit_failure_is_cleaned_and_never_reads_stale_file(self):
        fake, calls, paths = self.shell_fixture([{"dump": RuntimeError("dump failed")} for _ in range(3)])
        with patch.object(ultra0, "sh", side_effect=fake), self.assertRaisesRegex(RuntimeError, "3.*dump.*dump failed"):
            ultra0.ui_xml()
        self.assertEqual(len(paths), 3)
        self.assertFalse(any(command.startswith("cat ") for command in calls))
        self.assert_cleaned(calls, paths)

    def test_zero_exit_missing_snapshot_is_retried_instead_of_returning_old_xml(self):
        fake, calls, paths = self.shell_fixture([{"xml": RuntimeError("No such file or directory")}, {}])
        with patch.object(ultra0, "sh", side_effect=fake):
            self.assertEqual(ultra0.ui_xml(), "<hierarchy/>")
        self.assertEqual(len(paths), 2)
        self.assert_cleaned(calls, paths)

    def test_empty_malformed_and_wrong_root_snapshots_are_rejected(self):
        for invalid in ["", "   ", "<hierarchy><node", "<not-hierarchy/>"]:
            with self.subTest(xml=invalid):
                fake, calls, paths = self.shell_fixture([{"xml": invalid}, {}])
                with patch.object(ultra0, "sh", side_effect=fake):
                    self.assertEqual(ultra0.ui_xml(), "<hierarchy/>")
                self.assertEqual(len(paths), 2)
                self.assert_cleaned(calls, paths)

    def test_invalid_xml_exhaustion_reports_validation_stage_and_cleans_every_attempt(self):
        fake, calls, paths = self.shell_fixture([{"xml": ""} for _ in range(3)])
        with patch.object(ultra0, "sh", side_effect=fake), self.assertRaisesRegex(RuntimeError, "3.*validate"):
            ultra0.ui_xml()
        self.assertEqual(len(paths), 3)
        self.assert_cleaned(calls, paths)

    def test_cleanup_failure_is_checked_and_warned_without_discarding_valid_snapshot(self):
        fake, calls, paths = self.shell_fixture([{"cleanup": RuntimeError("cleanup failed")}])
        with patch.object(ultra0, "sh", side_effect=fake), patch.object(ultra0, "warn") as warn:
            self.assertEqual(ultra0.ui_xml(), "<hierarchy/>")
        warn.assert_called_once()
        self.assert_cleaned(calls, paths)

    def test_overlapping_calls_never_share_or_remove_each_others_snapshot(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        dumped, read, cleaned = [], [], []

        def shell(*args, **kwargs):
            self.assertEqual(args[0], "shell")
            self.assertIs(kwargs.get("check"), True)
            command = args[1]
            if command.startswith("uiautomator dump "):
                path = command.removeprefix("uiautomator dump ")
                with lock:
                    dumped.append(path)
                barrier.wait(timeout=2)
                return "dumped"
            if command.startswith("cat "):
                path = command.removeprefix("cat ")
                with lock:
                    read.append(path)
                return '<hierarchy snapshot="' + path + '"/>'
            if command.startswith("rm -f "):
                path = command.removeprefix("rm -f ")
                with lock:
                    cleaned.append(path)
                return ""
            raise AssertionError(command)

        with patch.object(ultra0, "sh", side_effect=shell), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ultra0.ui_xml) for _ in range(2)]
            results = [future.result(timeout=3) for future in futures]
        self.assertEqual(len(set(dumped)), 2)
        self.assertCountEqual(read, dumped)
        self.assertCountEqual(cleaned, dumped)
        self.assertCountEqual([ET.fromstring(xml).get("snapshot") for xml in results], dumped)


if __name__ == "__main__":
    unittest.main()
