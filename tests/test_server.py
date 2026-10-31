"""آزمون انتها‌به‌انتها API (با checkpoint آموزش‌دیده)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CHECKPOINT = os.path.join(ROOT, "checkpoints", "rayan-1-small.npz")

try:
    from fastapi.testclient import TestClient
    HAVE_CLIENT = True
except Exception:  # pragma: no cover
    HAVE_CLIENT = False


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        cls.db_path = tmp.name
        os.environ["RAYAN_DB"] = cls.db_path

        from web import server, store as store_module
        store_module._store = None  # پایگاه‌دادهٔ تمیز برای آزمون
        os.chdir(ROOT)
        server.engine = server.load_engine(CHECKPOINT)
        cls.server = server
        cls.client = TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        try:
            os.unlink(cls.db_path)
        except OSError:
            pass
        os.environ.pop("RAYAN_DB", None)
        from web import store as store_module
        store_module._store = None

    # ---------------------------------------------------------------- پایه
    def test_health(self):
        data = self.client.get("/api/health").json()
        self.assertTrue(data["ok"])
        self.assertGreater(data["model"]["params"], 1_000_000)

    def test_model(self):
        data = self.client.get("/api/model").json()
        self.assertEqual(data["config"]["vocab_size"], 10000)
        self.assertGreaterEqual(len(data["limitations"]), 3)

    def test_pages(self):
        for path in ("/", "/chat", "/login", "/signup", "/pricing", "/models", "/about", "/docs"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            self.assertIn("رایان", res.text)
        self.assertIn("urlset", self.client.get("/sitemap.xml").text)
        self.assertIn("User-agent", self.client.get("/robots.txt").text)

    def test_models_catalog(self):
        data = self.client.get("/api/models").json()
        self.assertGreaterEqual(len(data["models"]), 2)
        self.assertEqual(data["default"], "rayan-1-small")
        self.assertTrue(any(m["status"] == "ready" for m in data["models"]))

    def test_samples(self):
        data = self.client.get("/api/samples").json()
        self.assertGreaterEqual(len(data["samples"]), 3)

    # ----------------------------------------------------------------- چت
    def test_chat_short(self):
        res = self.client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16,
                                                  "session_id": "short"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data["answer"], str)
        self.assertIn("stats", data)
        self.assertLessEqual(data["stats"]["tokens"], 16)
        self.assertTrue(data["conversation_id"])
        self.assertIn("usage", data)

    def test_chat_persists_conversation(self):
        res = self.client.post("/api/chat", json={"message": "دربارهٔ ایران", "max_new_tokens": 16})
        conv_id = res.json()["conversation_id"]
        listing = self.client.get("/api/conversations").json()["conversations"]
        self.assertTrue(any(c["id"] == conv_id for c in listing))
        detail = self.client.get(f"/api/conversations/{conv_id}").json()["conversation"]
        self.assertEqual(len(detail["messages"]), 2)
        self.assertEqual(detail["messages"][0]["role"], "user")

    def test_multi_turn_history(self):
        first = self.client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16,
                                                    "session_id": "mt-1"}).json()
        second = self.client.post("/api/chat", json={
            "message": "خوبی؟", "conversation_id": first["conversation_id"], "max_new_tokens": 16,
        }).json()
        self.assertGreater(second["stats"]["prompt_tokens"], first["stats"]["prompt_tokens"])

    def test_stream(self):
        with self.client.stream("POST", "/api/chat/stream",
                                json={"message": "سلام", "max_new_tokens": 16, "session_id": "stream"}) as res:
            self.assertEqual(res.status_code, 200)
            payload = "".join(res.iter_text())
        self.assertIn('"type": "start"', payload)
        self.assertIn('"type": "done"', payload)
        self.assertIn("conversation_id", payload)

    def test_empty_rejected(self):
        res = self.client.post("/api/chat", json={"message": "   "})
        self.assertEqual(res.status_code, 400)

    def test_deep_rejected_on_stream(self):
        res = self.client.post("/api/chat/stream", json={"message": "سلام", "deep": True})
        self.assertEqual(res.status_code, 400)

    # ---------------------------------------------------------------- حساب
    def test_auth_flow(self):
        client = TestClient(self.server.app)
        me = client.get("/api/auth/me").json()
        self.assertIsNone(me["user"])
        self.assertEqual(me["plan"], "guest")

        res = client.post("/api/auth/register", json={
            "name": "آزمون", "email": "tester@example.com", "password": "test-password",
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["user"]["email"], "tester@example.com")

        me = client.get("/api/auth/me").json()
        self.assertEqual(me["user"]["email"], "tester@example.com")
        self.assertEqual(me["plan"], "free")
        self.assertEqual(me["usage"]["chat"]["limit"], 200)

        dup = client.post("/api/auth/register", json={
            "name": "دوباره", "email": "tester@example.com", "password": "test-password",
        })
        self.assertEqual(dup.status_code, 409)

        client.post("/api/auth/logout")
        self.assertIsNone(client.get("/api/auth/me").json()["user"])

        bad = client.post("/api/auth/login", json={"email": "tester@example.com", "password": "wrong-pass"})
        self.assertEqual(bad.status_code, 401)
        ok = client.post("/api/auth/login", json={"email": "tester@example.com", "password": "test-password"})
        self.assertEqual(ok.status_code, 200)

    def test_share_flow(self):
        client = TestClient(self.server.app)
        conv = client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16}).json()["conversation_id"]
        share = client.post(f"/api/conversations/{conv}/share").json()
        self.assertIn("token", share)
        public = client.get(f"/api/share/{share['token']}")
        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.json()["conversation"]["id"], conv)
        self.assertEqual(client.get("/s/" + share["token"]).status_code, 200)
        self.assertEqual(client.get("/api/share/does-not-exist").status_code, 404)

    def test_guest_cannot_read_others_conversation(self):
        owner = TestClient(self.server.app)
        conv = owner.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16}).json()["conversation_id"]
        stranger = TestClient(self.server.app)
        self.assertEqual(stranger.get(f"/api/conversations/{conv}").status_code, 404)
        self.assertEqual(stranger.delete(f"/api/conversations/{conv}").status_code, 404)

    def test_quota_enforced(self):
        from web import server
        original = dict(server.LIMITS["free"])
        server.LIMITS["free"] = {"chat": 1, "deep": 1}
        try:
            client = TestClient(self.server.app)
            res = client.post("/api/auth/register", json={
                "name": "سهمیه", "email": "quota@example.com", "password": "test-password",
            })
            self.assertEqual(res.status_code, 200)
            first = client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16})
            self.assertEqual(first.status_code, 200)
            second = client.post("/api/chat", json={"message": "دوباره", "max_new_tokens": 16})
            self.assertEqual(second.status_code, 429)
            usage = client.get("/api/usage").json()
            self.assertEqual(usage["chat"]["used"], 1)
            self.assertEqual(usage["chat"]["limit"], 1)
        finally:
            server.LIMITS["free"] = original


if __name__ == "__main__":
    unittest.main()
