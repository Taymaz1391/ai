"""آزمون مهارت‌های قطعی و دانشنامهٔ محلی + مسیرهای API."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web import knowledge, skills  # noqa: E402

# سایت هر checkpointی را که موجود باشد بار می‌کند؛ آزمون هم همان را می‌سنجد.
CHECKPOINTS = [os.path.join(ROOT, "checkpoints", name) for name in
               ("last.npz", "rayan-2-base.npz", "rayan-1-small.npz")]
CHECKPOINT = next((p for p in CHECKPOINTS if os.path.exists(p)), CHECKPOINTS[-1])

try:
    from fastapi.testclient import TestClient
    HAVE_CLIENT = True
except Exception:  # pragma: no cover
    HAVE_CLIENT = False


class SkillTest(unittest.TestCase):
    def test_greeting(self):
        hit = skills.match("سلام!")
        self.assertEqual(hit["skill"], "greeting")
        self.assertIn("رایان", hit["answer"])

    def test_identity_and_install(self):
        self.assertEqual(skills.match("تو کی هستی؟")["skill"], "identity")
        # نصب از مرورگر است؛ صفحهٔ دانلود حذف شده و لینک مرده نمی‌دهیم
        self.assertIn("مرورگر", skills.match("چطور نصب کنم؟")["answer"])

    def test_code_request_is_honest(self):
        hit = skills.match("یک تابع پایتون بنویس")
        self.assertEqual(hit["skill"], "code_request")
        self.assertIn("قوی نیستم", hit["answer"])

    def test_answers_leak_no_internals(self):
        """هیچ پاسخ مهارتی نباید پارامتر، پیکره، مسیر فایل یا لینک مخزن را لو بدهد."""
        banned = ("پارامتر", "میلیونی", "NumPy", "github", "/docs", "/course", "/download",
                  "checkpoint", "پیکره")
        for probe in ("سلام", "تو کی هستی؟", "خودت را معرفی کن", "چه کارهایی می‌کنی؟",
                      "قیمت چقدر است؟", "چطور نصب کنم؟", "مستندات کجاست؟",
                      "یک تابع پایتون بنویس"):
            hit = skills.match(probe)
            self.assertIsNotNone(hit, probe)
            for word in banned:
                self.assertNotIn(word, hit["answer"], f"{probe} → {word}")

    def test_no_false_positive(self):
        self.assertIsNone(skills.match("باران امروز چه حالی دارد؟"))
        self.assertIsNone(skills.match("یک متن طولانی " * 20))

    def test_no_secrets_in_skills(self):
        """هیچ پاسخ آماده‌ای نباید گذرواژهٔ مالک یا جزئیات داخلی را لو بدهد."""
        forbidden = ("13911391", "owner.json", "pw_hash", "RAYAN_OWNER")
        for name, pattern, answer in skills._RULES:  # noqa: SLF001
            for secret in forbidden:
                self.assertNotIn(secret, answer, name)


class KnowledgeTest(unittest.TestCase):
    def test_capital(self):
        hit = knowledge.answer("پایتخت ایران کجاست؟")
        self.assertIsNotNone(hit)
        self.assertIn("تهران", hit["answer"])

    def test_poet(self):
        self.assertIn("شاهنامه", knowledge.answer("فردوسی که بود؟")["answer"])

    def test_unknown_question_returns_none(self):
        self.assertIsNone(knowledge.answer("قیمت دلار امروز چقدر است؟"))
        self.assertIsNone(knowledge.answer("یک شعر دربارهٔ پاییز بگو"))

    def test_entries_are_valid_json(self):
        path = os.path.join(ROOT, "data", "knowledge.jsonl")
        count = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    self.assertTrue(row["q"])
                    self.assertTrue(row["a"])
                    count += 1
        self.assertGreaterEqual(count, 30)


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class SkillApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="rayan-skills-")
        os.environ["RAYAN_DB"] = os.path.join(cls.tmp, "test.sqlite3")
        os.environ["RAYAN_OWNER_FILE"] = os.path.join(cls.tmp, "owner.json")
        os.environ["RAYAN_ADMIN_FILE"] = os.path.join(cls.tmp, "admin.json")
        from web import store as store_module
        store_module._store = None
        from web import server
        if server.engine is None:
            server.engine = server.load_engine(CHECKPOINT)
        server.engine_error = None
        os.chdir(ROOT)
        cls.server = server
        cls.client = TestClient(server.app)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from auth_support import signup
        signup(cls.client)  # هوش فقط با حساب ثبت‌نام‌شده

    @classmethod
    def tearDownClass(cls):
        import shutil
        for key in ("RAYAN_DB", "RAYAN_OWNER_FILE", "RAYAN_ADMIN_FILE"):
            os.environ.pop(key, None)
        from web import store as store_module
        store_module._store = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_chat_greeting_uses_skill(self):
        res = self.client.post("/api/chat", json={"message": "سلام", "mode": "chat"})
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["engine"], "skill")
        self.assertEqual(data["stats"]["finish_reason"], "skill")

    def test_chat_fact_is_grounded(self):
        """سؤال دانشی باید از شاهد (پیکره/دانشنامه) جواب بگیرد، نه از متن آماده."""
        from web import retrieval
        if not retrieval.index_exists() and not retrieval.wiki_exists():
            self.skipTest("ایندکس محلی ساخته نشده است")
        res = self.client.post("/api/chat", json={"message": "پایتخت ایران کجاست؟", "mode": "chat"})
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertIn(data["engine"], {"think", "knowledge", "chat"})
        if data["engine"] == "think":
            self.assertTrue(data["sources"])
        self.assertIn("تهران", data["answer"])

    def test_stream_greeting_uses_skill(self):
        with self.client.stream("POST", "/api/chat/stream",
                                json={"message": "سلام", "mode": "chat"}) as res:
            self.assertEqual(res.status_code, 200)
            events = [json.loads(line) for line in res.iter_lines() if line]
        done = [e for e in events if e["type"] == "done"][0]
        self.assertEqual(done["engine"], "skill")

    def test_benchmark_endpoint(self):
        res = self.client.get("/api/benchmark")
        if res.status_code == 404:
            self.skipTest("benchmark not generated yet")
        data = res.json()
        self.assertEqual(data["params"], 6_574_848)
        self.assertIn("generation_percent", data["accuracy"])
        self.assertIn("opus_reference", data)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
