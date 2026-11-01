"""آزمون‌های ورودِ بدون‌کوکی و پنل مدیریتِ تازه.

سایت در iframe یا مرورگرِ سخت‌گیر ممکن است کوکی را ذخیره نکند؛ در آن حالت کاربر
با توکنِ نشست شناخته می‌شود. این آزمون‌ها همان مسیر را می‌سنجند تا باگِ
«وارد می‌شوم اما مهمانم» برنگردد.
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

from auth_support import human_proof  # noqa: E402


class BearerUnitTest(unittest.TestCase):
    """تابعِ استخراج توکن باید فقط توکنِ معتبر را بپذیرد."""

    def test_bearer_regex(self):
        from web.server import _TOKEN_RE
        self.assertTrue(_TOKEN_RE.fullmatch("A" * 32))
        self.assertFalse(_TOKEN_RE.fullmatch("short"))
        self.assertFalse(_TOKEN_RE.fullmatch("space inside token value!!"))


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class HeaderAuthTest(unittest.TestCase):
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

    def _register(self):
        client = TestClient(self.server.app)
        client.get("/chat")
        res = client.post("/api/auth/register", json={
            "name": "کاربر توکن", "email": f"token-{os.urandom(4).hex()}@example.com",
            "password": "token-pass-9", "captcha": human_proof(client)})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def test_login_returns_token(self):
        client = TestClient(self.server.app)
        client.get("/chat")
        body = self._register()
        res = client.post("/api/auth/login", json={
            "identifier": body["user"]["email"], "password": "token-pass-9",
            "captcha": human_proof(client)})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json().get("token"))

    def test_me_without_cookie(self):
        base = self._register()
        bare = TestClient(self.server.app)  # هیچ کوکی‌ای ندارد
        res = bare.get("/api/auth/me", headers={"Authorization": f"Bearer {base['token']}"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["signed_in"])
        self.assertEqual(res.json()["user"]["email"], base["user"]["email"])

    def test_me_without_anything_is_guest(self):
        bare = TestClient(self.server.app)
        res = bare.get("/api/auth/me")
        self.assertFalse(res.json()["signed_in"])

    def test_garbage_bearer_is_guest(self):
        bare = TestClient(self.server.app)
        res = bare.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token-000000"})
        self.assertFalse(res.json()["signed_in"])

    def test_owner_login_returns_admin_token(self):
        client = TestClient(self.server.app)
        client.get("/admin")
        res = client.post("/api/admin/login", json={"password": "13911391"})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body.get("admin_token"))
        bare = TestClient(self.server.app)
        res = bare.get("/api/admin/overview", headers={"X-Rayyan-Admin": body["admin_token"]})
        self.assertEqual(res.status_code, 200, res.text)

    def test_admin_endpoints_reject_anonymous(self):
        bare = TestClient(self.server.app)
        for path in ("/api/admin/overview", "/api/admin/knowledge/entries", "/api/admin/quality"):
            self.assertEqual(bare.get(path).status_code, 401, path)


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class KnowledgeEditorTest(unittest.TestCase):
    """ویرایشِ دانشنامه از پنل باید بی‌درنگ در پاسخ‌ها دیده شود."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        cls.db_path = tmp.name
        cls.kb_file = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        cls.kb_file.close()
        os.environ["RAYAN_DB"] = cls.db_path
        os.environ["RAYAN_KNOWLEDGE_FILE"] = cls.kb_file.name
        from web import admin, knowledge, server, store as store_module
        store_module._store = None
        os.chdir(ROOT)
        server.engine = server.load_engine(CHECKPOINT)
        cls.server, cls.knowledge = server, knowledge
        knowledge._ENTRIES = None
        cls.admin_token = admin._ensure_admin_user("owner@rayan.local")  # noqa: SLF001
        from web import store as sm
        cls.session = sm.store().create_admin_session(int(cls.admin_token), "csrf-test", ip="127.0.0.1")
        cls.client = TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        for path in (cls.db_path, cls.kb_file.name):
            try:
                os.unlink(path)
            except OSError:
                pass
        os.environ.pop("RAYAN_DB", None)
        os.environ.pop("RAYAN_KNOWLEDGE_FILE", None)
        from web import store as store_module, knowledge
        store_module._store = None
        knowledge._ENTRIES = None

    def _headers(self):
        return {"X-Rayyan-Admin": self.session}

    def test_upsert_then_answer(self):
        res = self.client.post("/api/admin/knowledge/entries", headers=self._headers(), json={
            "id": "kb-test-row", "q": "قانون اول نیوتن چیست؟",
            "keys": ["قانون اول نیوتن", "اینرسی"],
            "a": "قانون اول نیوتن: جسمِ بی‌نیرو ساکن یا با سرعتِ ثابت می‌ماند (اینرسی)."})
        self.assertEqual(res.status_code, 200, res.text)
        hit = self.knowledge.answer("قانون اول نیوتن چیست؟")
        self.assertIsNotNone(hit)
        self.assertIn("اینرسی", hit["answer"])

    def test_delete_removes_row(self):
        self.client.post("/api/admin/knowledge/entries", headers=self._headers(), json={
            "id": "kb-temp-row", "q": "پرسش آزمایشی", "keys": ["آزمایشی"], "a": "پاسخ آزمایشی"})
        res = self.client.delete("/api/admin/knowledge/entries/kb-temp-row", headers=self._headers())
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIsNone(self.knowledge.answer("پرسش آزمایشی"))

    def test_quality_report_list(self):
        res = self.client.get("/api/admin/quality", headers=self._headers())
        self.assertEqual(res.status_code, 200)
        self.assertIn("sets", res.json())


if __name__ == "__main__":
    unittest.main()
