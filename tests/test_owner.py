"""آزمون ورود مالک با نام کاربری فارسی و گذرواژهٔ محلی.

هیچ‌کدام از آزمون‌ها به فایل‌های واقعی `data/` دست نمی‌زنند؛ همه در پوشهٔ موقت.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CHECKPOINT = os.path.join(ROOT, "checkpoints", "rayan-1-small.npz")

try:
    from fastapi.testclient import TestClient
    HAVE_CLIENT = True
except Exception:  # pragma: no cover
    HAVE_CLIENT = False

from web import owner as owner_module  # noqa: E402


class UsernameTest(unittest.TestCase):
    """نام کاربری فارسی باید با نیم‌فاصله، فاصلهٔ اضافه و ی/ک عربی هم بخواند."""

    def test_variants(self):
        for variant in (
            "تایماز جلیلی",
            "تایماز  جلیلی",
            "  تایماز جلیلی ",
            "تایماز\u200cجلیلی",   # نیم‌فاصله
            "تایماز جلیلی\u200f",  # علامت راست‌به‌چپ
            "تایماز جليلي",         # ی عربی در «جليلي»
        ):
            self.assertTrue(owner_module.matches_username(variant), variant)

    def test_rejects_other_names(self):
        self.assertFalse(owner_module.matches_username(""))
        self.assertFalse(owner_module.matches_username("تایماز"))
        self.assertFalse(owner_module.matches_username("مدیر"))
        self.assertFalse(owner_module.matches_username("تایماز جلیلی ۲"))


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class OwnerLoginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="rayan-owner-")
        os.environ["RAYAN_DB"] = os.path.join(cls.tmp, "test.sqlite3")
        os.environ["RAYAN_OWNER_FILE"] = os.path.join(cls.tmp, "owner.json")
        os.environ["RAYAN_ADMIN_FILE"] = os.path.join(cls.tmp, "admin.json")
        os.environ["RAYAN_ADMIN_PASSWORD"] = "owner-route-admin-pass"
        os.environ.pop("RAYAN_OWNER_PASSWORD", None)
        os.environ.pop("RAYAN_ENV", None)

        from web import admin as admin_mod
        from web import store as store_module
        importlib.reload(owner_module)
        importlib.reload(admin_mod)
        store_module._store = None

        from web import server
        server.owner_module = owner_module
        server.engine_error = None
        if server.engine is None:
            server.engine = server.load_engine(CHECKPOINT)
        os.chdir(ROOT)
        cls.server = server
        cls.client = TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        import shutil
        for key in ("RAYAN_DB", "RAYAN_OWNER_FILE", "RAYAN_ADMIN_FILE", "RAYAN_ADMIN_PASSWORD"):
            os.environ.pop(key, None)
        from web import store as store_module
        store_module._store = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def login(self, identifier: str, password: str):
        return TestClient(self.server.app).post(
            "/api/auth/login", json={"identifier": identifier, "password": password}
        )

    # ------------------------------------------------------------ ورود مالک
    def test_owner_login_grants_admin_panel(self):
        resp = self.login("تایماز جلیلی", owner_module.DEV_DEFAULT_PASSWORD)
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertTrue(data["admin"])
        self.assertEqual(data["redirect"], "/admin")
        self.assertTrue(data["csrf"])
        self.assertEqual(data["owner"]["name"], owner_module.DEFAULT_NAME)
        self.assertIn("rayan_session", resp.cookies)
        self.assertIn("rayan_admin", resp.cookies)

        client = TestClient(self.server.app)
        client.cookies.update(resp.cookies)
        session = client.get("/api/admin/session").json()
        self.assertTrue(session["authenticated"])
        self.assertEqual(session["user"]["name"], owner_module.DEFAULT_NAME)
        self.assertTrue(session["owner"]["default_password"])
        # مدیر واقعی: سلف‌تست و تنظیمات در دسترس است
        self.assertEqual(client.get("/api/selftest").status_code, 200)

    def test_owner_login_with_zwnj_and_spacing(self):
        resp = self.login(" تایماز\u200cجلیلی ", owner_module.DEV_DEFAULT_PASSWORD)
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_owner_wrong_password(self):
        resp = self.login("تایماز جلیلی", "00000000")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("نادرست", resp.json()["detail"])

    def test_non_owner_name_is_rejected(self):
        resp = self.login("کاربر ناشناس", owner_module.DEV_DEFAULT_PASSWORD)
        self.assertEqual(resp.status_code, 401)

    def test_email_login_still_works(self):
        client = TestClient(self.server.app)
        created = client.post("/api/auth/register", json={
            "name": "آزمون", "email": "owner-test@example.com", "password": "long-enough-pass",
        })
        self.assertEqual(created.status_code, 200, created.text)
        body = created.json()
        self.assertFalse(body.get("admin"))
        self.assertNotIn("rayan_admin", created.cookies)

    # ------------------------------------------------------- چرخش گذرواژه
    def test_owner_password_rotation(self):
        login = self.login("تایماز جلیلی", owner_module.DEV_DEFAULT_PASSWORD)
        admin_client = TestClient(self.server.app)
        admin_client.cookies.update(login.cookies)
        csrf = login.json()["csrf"]

        denied = admin_client.post("/api/admin/owner-password",
                                   json={"password": "a-new-owner-pass"})
        self.assertEqual(denied.status_code, 403)  # بدون توکن CSRF

        too_short = admin_client.post("/api/admin/owner-password",
                                      json={"password": "short"},
                                      headers={"x-rayan-csrf": csrf})
        self.assertEqual(too_short.status_code, 400)

        same = admin_client.post("/api/admin/owner-password",
                                 json={"password": owner_module.DEV_DEFAULT_PASSWORD},
                                 headers={"x-rayan-csrf": csrf})
        self.assertEqual(same.status_code, 400)

        changed = admin_client.post("/api/admin/owner-password",
                                    json={"password": "a-new-owner-pass"},
                                    headers={"x-rayan-csrf": csrf})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertFalse(changed.json()["owner"]["default_password"])

        self.assertEqual(admin_client.get("/api/admin/session").json()["owner"]["default_password"], False)
        self.assertEqual(self.login("تایماز جلیلی", owner_module.DEV_DEFAULT_PASSWORD).status_code, 401)
        self.assertEqual(self.login("تایماز جلیلی", "a-new-owner-pass").status_code, 200)

        # بازگرداندن حالت پیش‌فرض تا ترتیب اجرای آزمون‌ها اهمیت نداشته باشد
        owner_module.set_password(owner_module.DEV_DEFAULT_PASSWORD, generated=True)

    def test_owner_file_is_private_and_not_tracked(self):
        path = Path(os.environ["RAYAN_OWNER_FILE"])
        owner_module.credentials()  # در نبود فایل، نسخهٔ توسعه آن را می‌سازد
        self.assertTrue(path.exists())
        mode = path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn(owner_module.DEV_DEFAULT_PASSWORD, raw)
        self.assertIn("pw_hash", raw)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
