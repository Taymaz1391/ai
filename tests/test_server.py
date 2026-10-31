"""آزمون انتها‌به‌انتها API (با checkpoint آموزش‌دیده)."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

CHECKPOINT = os.path.join(ROOT, "checkpoints", "parsia-1-small.npz")

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
        from web import server
        os.chdir(ROOT)
        server.engine = server.load_engine(CHECKPOINT)
        cls.client = TestClient(server.app)

    def test_health(self):
        data = self.client.get("/api/health").json()
        self.assertTrue(data["ok"])
        self.assertGreater(data["model"]["params"], 1_000_000)

    def test_model(self):
        data = self.client.get("/api/model").json()
        self.assertEqual(data["config"]["vocab_size"], 10000)
        self.assertGreaterEqual(len(data["limitations"]), 3)

    def test_samples(self):
        data = self.client.get("/api/samples").json()
        self.assertGreaterEqual(len(data["samples"]), 3)

    def test_chat_short(self):
        res = self.client.post("/api/chat", json={"message": "سلام", "max_new_tokens": 16, "session_id": "test"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data["answer"], str)
        self.assertIn("stats", data)
        self.assertLessEqual(data["stats"]["tokens"], 16)

    def test_stream(self):
        with self.client.stream("POST", "/api/chat/stream",
                                json={"message": "سلام", "max_new_tokens": 16, "session_id": "test2"}) as res:
            self.assertEqual(res.status_code, 200)
            payload = "".join(res.iter_text())
        self.assertIn('"type": "start"', payload)
        self.assertIn('"type": "done"', payload)

    def test_empty_rejected(self):
        res = self.client.post("/api/chat", json={"message": "   "})
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
