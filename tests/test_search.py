"""آزمون جست‌وجوی وب: تحلیل HTML، ویکی‌پدیا، کش، ترکیب پاسخ و مسیر API."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web import search  # noqa: E402

# سایت هر checkpointی را که موجود باشد بار می‌کند؛ آزمون هم همان را می‌سنجد.
CHECKPOINTS = [os.path.join(ROOT, "checkpoints", name) for name in
               ("last.npz", "rayan-2-base.npz", "rayan-1-small.npz")]
CHECKPOINT = next((p for p in CHECKPOINTS if os.path.exists(p)), CHECKPOINTS[-1])

try:
    from fastapi.testclient import TestClient
    HAVE_CLIENT = True
except Exception:  # pragma: no cover
    HAVE_CLIENT = False

DDG_HTML = """
<div class="result results_links">
  <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">عنوان نخست</a>
  <a class="result__snippet" href="https://example.com/a">توضیح <b>نخست</b> دربارهٔ موضوع.</a>
</div>
<div class="result results_links">
  <a rel="nofollow" class="result__a" href="https://example.org/b">عنوان دوم</a>
  <div class="result__snippet">توضیح دوم.</div>
</div>
"""

WIKI_JSON = json.dumps({
    "query": {"search": [
        {"title": "تهران", "snippet": "تهران <span class=\"searchmatch\">پایتخت</span> ایران است."},
        {"title": "ایران", "snippet": "ایران کشوری در غرب آسیاست."},
    ]}
}, ensure_ascii=False)


class ParseTest(unittest.TestCase):
    def test_plain_duckduckgo(self):
        with mock.patch.object(search, "_get", return_value=DDG_HTML):
            items = search._ddg("تهران", 5)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["url"], "https://example.com/a")
        self.assertEqual(items[0]["snippet"], "توضیح نخست دربارهٔ موضوع.")
        self.assertEqual(items[1]["domain"], "example.org")

    def test_wikipedia(self):
        with mock.patch.object(search, "_get", return_value=WIKI_JSON):
            items = search._wiki("تهران", 2, "fa")
        self.assertEqual(items[1]["title"], "ایران")
        self.assertEqual(items[0]["snippet"], "تهران پایتخت ایران است.")
        self.assertIn("fa.wikipedia.org", items[0]["url"])

    def test_provider_fallback_and_cache(self):
        calls = []

        def fake(url, accept="text/html"):
            calls.append(url)
            if "duckduckgo" in url:
                raise OSError("blocked")
            return WIKI_JSON

        search._CACHE.clear()
        with mock.patch.object(search, "_get", fake), \
                mock.patch.dict(os.environ, {"RAYAN_SEARCH_PROVIDERS": "ddg,wiki"}):
            first = search.search("تهران", limit=2)
            second = search.search("تهران", limit=2)
        self.assertEqual(len(first["results"]), 2)
        self.assertEqual(first["provider"], "wikipedia-fa")
        self.assertTrue(second["cached"])
        self.assertEqual(len(calls), 2)  # ddg خطا داد، ویکی یک‌بار؛ بار دوم از کش

    def test_all_providers_down(self):
        search._CACHE.clear()
        with mock.patch.object(search, "_get", side_effect=OSError("offline")):
            data = search.search("چیزی", limit=3)
        self.assertEqual(data["results"], [])
        self.assertEqual(data["provider"], "")

    def test_compose(self):
        results = [
            {"title": "الف", "url": "https://a.example/1", "snippet": "یک", "source": "x", "domain": "a.example"},
            {"title": "ب", "url": "https://b.example/2", "snippet": "دو", "source": "x", "domain": "b.example"},
        ]
        fa = search.compose("موضوع", results)
        self.assertIn("۲ منبع وب", fa)
        self.assertIn("https://b.example/2", fa)
        self.assertIn("خلاصهٔ عین منابع", fa)
        en = search.compose("topic", results, lang="en")
        self.assertIn("Based on 2 web sources", en)
        self.assertIn("دسترسی پیدا نکردم", search.compose("x", []))

    def test_wants_search(self):
        self.assertTrue(search.wants_search("آخرین خبرهای فناوری را جستجو کن"))
        self.assertTrue(search.wants_search("Search the web for this"))
        self.assertFalse(search.wants_search("یک شعر بگو"))


@unittest.skipUnless(HAVE_CLIENT, "httpx/fastapi TestClient unavailable")
@unittest.skipUnless(os.path.exists(CHECKPOINT), "checkpoint not trained yet")
class SearchApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="rayan-search-")
        os.environ["RAYAN_DB"] = os.path.join(cls.tmp, "test.sqlite3")
        os.environ["RAYAN_OWNER_FILE"] = os.path.join(cls.tmp, "owner.json")
        os.environ["RAYAN_ADMIN_FILE"] = os.path.join(cls.tmp, "admin.json")
        os.environ["RAYAN_ADMIN_PASSWORD"] = "search-route-admin-pass"
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
        for key in ("RAYAN_DB", "RAYAN_OWNER_FILE", "RAYAN_ADMIN_FILE", "RAYAN_ADMIN_PASSWORD"):
            os.environ.pop(key, None)
        from web import store as store_module
        store_module._store = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fake_results(self, query, limit=5, lang="fa"):
        return {"query": query, "provider": "test", "cached": False, "results": [
            {"title": "منبع آزمون", "url": "https://example.com/x", "snippet": "خلاصهٔ آزمون",
             "source": "test", "domain": "example.com"},
        ][:limit]}

    def test_search_endpoint(self):
        with mock.patch.object(search, "search", side_effect=self.fake_results):
            res = self.client.get("/api/search", params={"q": "تهران"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["results"][0]["domain"], "example.com")

    def test_search_endpoint_rejects_short_query(self):
        self.assertEqual(self.client.get("/api/search", params={"q": "x"}).status_code, 422)

    def test_chat_with_web_returns_sources(self):
        with mock.patch.object(search, "search", side_effect=self.fake_results):
            res = self.client.post("/api/chat", json={
                "message": "دربارهٔ تهران جستجو کن", "mode": "chat", "web": True,
            })
        self.assertEqual(res.status_code, 200, res.text)
        data = res.json()
        self.assertEqual(data["engine"], "web")
        self.assertEqual(len(data["sources"]), 1)
        self.assertIn("خلاصهٔ آزمون", data["answer"])
        self.assertIn("https://example.com/x", data["answer"])

    def test_chat_without_web_stays_mocked_offline(self):
        """بدون وب، مدل محلی پاسخ می‌دهد و هیچ فراخوانی شبکه‌ای لازم نیست.

        جست‌وجوی خودکار را صریح خاموش می‌کنیم؛ وگرنه روی ماشینی که اینترنت دارد
        پاسخِ ضعیف «زمینه‌دار» می‌شود و آزمون به شبکه وابسته می‌ماند.
        """
        empty = {"query": "x", "provider": "test", "cached": False, "results": []}
        with mock.patch.object(search, "search", return_value=empty):
            res = self.client.post("/api/chat", json={
                "message": "باران پاییزی", "mode": "chat", "web": False, "max_new_tokens": 16,
            })
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["engine"], "chat")
        self.assertEqual(res.json()["sources"], [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
