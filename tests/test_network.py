"""آزمون حالت شبکه: سایت در قطعیِ اینترنت بین‌المللی هم کامل کار می‌کند."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from web import network


class NetworkModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = dict(network._state)
        self._tmp = tempfile.TemporaryDirectory()
        self._file = network.STATE_FILE
        network.STATE_FILE = os.path.join(self._tmp.name, "network.json")

    def tearDown(self) -> None:
        network._state.clear()
        network._state.update(self._saved)
        network.STATE_FILE = self._file
        self._tmp.cleanup()

    def test_national_mode_blocks_everything(self):
        network.set_mode("national")
        self.assertFalse(network.allow_outbound())
        self.assertTrue(network.stats()["assets_local"])

    def test_global_mode_opens(self):
        network.set_mode("global")
        self.assertTrue(network.allow_outbound())

    def test_auto_backs_off_after_failure(self):
        network.set_mode("auto")
        self.assertTrue(network.allow_outbound())
        network.report_failure("timeout")
        self.assertFalse(network.allow_outbound())
        self.assertIn("timeout", network.stats()["last_error"])
        network.report_success()
        self.assertTrue(network.allow_outbound())

    def test_bad_mode_rejected(self):
        with self.assertRaises(ValueError):
            network.set_mode("moon")

    def test_choice_survives_restart(self):
        network.set_mode("national")
        network._state["mode"] = "auto"          # انگار سرور تازه بالا آمده
        network._load()
        self.assertEqual(network.mode(), "national")

    def test_search_skips_network_in_national_mode(self):
        from web import search

        network.set_mode("national")
        with mock.patch("urllib.request.urlopen") as opener:
            self.assertEqual(search._get("https://example.com"), "")
            opener.assert_not_called()

    def test_learn_fetch_skips_network_in_national_mode(self):
        from web import learn

        network.set_mode("national")
        with mock.patch("urllib.request.urlopen") as opener:
            self.assertIsNone(learn.fetch("https://example.com"))
            opener.assert_not_called()

    def test_failed_search_does_not_break_page(self):
        from web import search

        network.set_mode("auto")
        with mock.patch("urllib.request.urlopen", side_effect=OSError("cut")):
            self.assertEqual(search._get("https://example.com"), "")
        self.assertFalse(network.allow_outbound())


class CapacityReportTest(unittest.TestCase):
    def test_report_comes_from_the_server_not_a_brochure(self):
        from web import server

        report = server.capacity_report()
        for key in ("workers", "concurrency_limit", "cache_size", "hardware",
                    "database", "network", "honest_note"):
            self.assertIn(key, report)
        self.assertIn("database", report)
        self.assertIn("wiki_bytes", report["database"])
        self.assertTrue(report["honest_note"])


if __name__ == "__main__":
    unittest.main()
