"""آزمون‌های نسخهٔ ۲۳: پنل تنظیمات، کد تأیید ایمیل، ورود مالک به مدیریت و راهنما.

هیچ‌کدام از آزمون‌ها به پایگاه‌دادهٔ واقعی دست نمی‌زنند؛ همه در فایل موقت.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from fastapi.testclient import TestClient
    HAVE_CLIENT = True
except Exception:  # pragma: no cover
    HAVE_CLIENT = False

CHECKPOINTS = [os.path.join(ROOT, "checkpoints", name) for name in
               ("last.npz", "rayan-2-base.npz", "rayan-1-small.npz")]
CHECKPOINT = next((p for p in CHECKPOINTS if os.path.exists(p)), CHECKPOINTS[-1])

from auth_support import human_proof, signup  # noqa: E402


class GuideTest(unittest.TestCase):
    """راهنمای موضوعی باید جواب بدهد، نه پیشنهاد."""

    def setUp(self):
        from web import guide
        self.guide = guide

    def test_known_topics_answer(self):
        for question, topic in (
            ("چطور برنامه‌نویسی یاد بگیرم؟", "programming"),
            ("چطور بهتر بخوابم؟", "sleep"),
            ("چطور در مصاحبهٔ کاری موفق شوم؟", "interview"),
            ("برای شروع ورزش چه کنم؟", "fitness"),
        ):
            result = self.guide.answer(question)
            self.assertIsNotNone(result, question)
            self.assertEqual(result["source"], f"guide:{topic}")
            self.assertGreater(len(result["answer"]), 200)

    def test_answer_has_numbered_steps(self):
        result = self.guide.answer("چطور برنامه‌نویسی یاد بگیرم؟")
        self.assertIn("۱.", result["answer"])
        self.assertIn("۲.", result["answer"])

    def test_unknown_topic_gets_method_answer(self):
        result = self.guide.answer("چطور یخچال را تمیز کنم؟")
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "guide:method")
        self.assertIn("یخچال", result["answer"])

    def test_no_suggestion_copy(self):
        """هیچ پاسخی نباید کاربر را به «روشن‌کردن وب» یا پرسش دیگر حواله بدهد."""
        for topic in self.guide.topics():
            text = self.guide.answer("چطور " + topic + " یاد بگیرم؟")
            if not text:
                continue
            self.assertNotIn("دکمهٔ «وب»", text["answer"])
            self.assertNotIn("پیشنهاد می‌کنم", text["answer"])

    def test_factual_question_not_guided(self):
        self.assertIsNone(self.guide.answer("قیمت دلار چند است؟"))


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class PanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        cls.db_path = tmp.name
        os.environ["RAYAN_DB"] = cls.db_path
        os.environ["RAYAN_EMAIL_DEV"] = "1"
        from web import server, store as store_module
        store_module._store = None
        os.chdir(ROOT)
        server.engine = server.load_engine(CHECKPOINT)
        cls.server = server
        cls.client = TestClient(server.app)
        cls.signup = signup(cls.client, email="panel-user@example.com")

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.db_path)
        except OSError:
            pass
        os.environ.pop("RAYAN_DB", None)
        os.environ.pop("RAYAN_EMAIL_DEV", None)
        from web import store as store_module
        store_module._store = None

    def test_settings_page(self):
        res = self.client.get("/settings")
        self.assertEqual(res.status_code, 200)
        self.assertIn("تنظیمات", res.text)
        self.assertIn("no-store", res.headers.get("cache-control", ""))

    def test_auth_state_is_never_cached(self):
        res = self.client.get("/api/auth/me")
        self.assertIn("no-store", res.headers.get("cache-control", ""))

    def test_register_returns_verification_for_new_user(self):
        fresh = TestClient(self.server.app)
        fresh.get("/chat")
        res = fresh.post("/api/auth/register", json={
            "name": "تازه", "email": "fresh-v23@example.com", "password": "fresh-pass-9",
            "captcha": human_proof(fresh)})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertFalse(body["admin"])  # ثبت‌نام عادی، مدیر نیست
        self.assertTrue(body["verification"]["required"])
        self.assertTrue(body["verification"]["dev_code"])

    def test_email_code_roundtrip(self):
        reg = self.signup.get("verification") or {}
        code = reg.get("dev_code")
        self.assertTrue(code)
        status = self.client.get("/api/auth/verification").json()
        self.assertEqual(status["email"], "panel-user@example.com")
        self.assertFalse(status["verified"])
        wrong = self.client.post("/api/auth/verification/confirm",
                                 json={"code": "000000" if code != "000000" else "111111"})
        self.assertEqual(wrong.status_code, 400)
        good = self.client.post("/api/auth/verification/confirm", json={"code": code})
        self.assertEqual(good.status_code, 200, good.text)
        self.assertTrue(good.json()["verified"])
        self.assertTrue(self.client.get("/api/auth/verification").json()["verified"])

    def test_password_change(self):
        bad = self.client.post("/api/auth/password",
                               json={"current": "wrong-pass", "new": "another-pass-1"})
        self.assertEqual(bad.status_code, 403)
        ok = self.client.post("/api/auth/password",
                              json={"current": "test-password", "new": "another-pass-1"})
        self.assertEqual(ok.status_code, 200, ok.text)
        # برگرداندن گذرواژه برای آزمون‌های بعدی همین کلاس
        self.client.post("/api/auth/password",
                         json={"current": "another-pass-1", "new": "test-password"})

    def test_owner_elevation(self):
        """مالکِ واردشده بی‌گذرواژهٔ دوم وارد پنل مدیریت می‌شود."""
        from web import admin as admin_module
        login = self.client.post("/api/auth/login", json={
            "identifier": "panel-user@example.com", "password": "test-password",
            "captcha": human_proof(self.client)})
        self.assertEqual(login.status_code, 200, login.text)
        user_id = login.json()["user"]["id"]
        # این حساب را مالک می‌کنیم؛ در نصب واقعی مالک از مسیر ورودِ مالک می‌آید
        from web import store as store_module
        store_module.store().set_owner(int(user_id))
        denied = TestClient(self.server.app).post("/api/admin/elevate", json={})
        self.assertIn(denied.status_code, (401, 403))
        lifted = self.client.post("/api/admin/elevate", json={})
        self.assertEqual(lifted.status_code, 200, lifted.text)
        csrf = lifted.json()["csrf"]
        self.assertTrue(csrf)
        session = self.client.get("/api/admin/session").json()
        self.assertTrue(session.get("authenticated"))
        self.client.post("/api/admin/logout", headers={"x-rayan-csrf": csrf})
        _ = admin_module  # نگه‌داشتنِ import برای خوانایی


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class MailPanelTest(unittest.TestCase):
    """پیکربندی ایمیل از پنل مدیریت: بی‌فایل، بی‌متغیر محیطی، با آزمونِ ارسال."""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = tmp.name
        os.environ["RAYAN_DB"] = self.db_path
        os.environ.pop("RAYAN_SMTP_HOST", None)
        os.environ.pop("RAYAN_SMTP_FROM", None)
        from web import server, security, store as store_module
        store_module._store = None
        store_module.store().set_setting("mail.host", "")
        store_module.store().set_setting("mail.from", "")
        # محدودسازهای نرخ در کل فرایند مشترک‌اند؛ آزمون‌های پیشین نباید این کلاس را ببندند
        server.limiter.hits.clear()
        with security.captcha_limiter.lock:
            security.captcha_limiter.hits.clear()
        os.chdir(ROOT)
        server.engine = server.load_engine(CHECKPOINT)
        self.server = server
        self.client = TestClient(server.app)
        signup(self.client, email=f"mail-admin-{os.path.basename(self.db_path)}@example.com")
        me = self.client.get("/api/auth/me").json()
        store_module.store().set_owner(int(me["user"]["id"]))
        lifted = self.client.post("/api/admin/elevate", json={})
        assert lifted.status_code == 200, lifted.text
        self.csrf = {"x-rayan-csrf": lifted.json()["csrf"]}

    def tearDown(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass
        os.environ.pop("RAYAN_DB", None)
        from web import store as store_module
        store_module._store = None

    def test_status_hides_password(self):
        data = self.client.get("/api/admin/mail").json()
        self.assertIn("configured", data)
        self.assertNotIn("password", data)
        self.assertFalse(data["configured"])

    def test_save_requires_csrf(self):
        res = self.client.post("/api/admin/mail", json={"host": "smtp.example.com",
                                                        "sender": "رایان <a@example.com>"})
        self.assertEqual(res.status_code, 403)

    def test_save_and_configures(self):
        res = self.client.post("/api/admin/mail", headers=self.csrf, json={
            "host": "smtp.example.com", "port": 587, "user": "bot@example.com",
            "password": "secret-app-pass", "sender": "رایان <bot@example.com>",
            "mode": "starttls"})
        self.assertEqual(res.status_code, 200, res.text)
        status = self.client.get("/api/admin/mail").json()
        self.assertTrue(status["configured"])
        self.assertTrue(status["has_password"])
        self.assertEqual(status["host"], "smtp.example.com")
        # گذرواژه در پاسخ هیچ مسیری نمی‌آید
        self.assertNotIn("secret-app-pass", res.text)

    def test_bad_sender_rejected(self):
        res = self.client.post("/api/admin/mail", headers=self.csrf,
                               json={"host": "smtp.example.com", "sender": "بی‌نشانی"})
        self.assertEqual(res.status_code, 400)

    def test_unconfigured_test_send_is_honest_503(self):
        res = self.client.post("/api/admin/mail/test", headers=self.csrf,
                               json={"to": "someone@example.com"})
        self.assertEqual(res.status_code, 503)

    def test_failed_delivery_is_not_a_fake_success(self):
        """اگر SMTP جواب ندهد، پاسخ باید خطا باشد نه «ارسال شد»."""
        self.client.post("/api/admin/mail", headers=self.csrf, json={
            "host": "127.0.0.1", "port": 9, "user": "", "password": "",
            "sender": "رایان <bot@example.com>", "mode": "none"})
        res = self.client.post("/api/admin/mail/test", headers=self.csrf,
                               json={"to": "someone@example.com"})
        self.assertIn(res.status_code, (502, 503))


if __name__ == "__main__":
    unittest.main()
