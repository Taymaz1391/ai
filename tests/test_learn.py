"""آزمون‌های لایهٔ دانشِ آنلاین: خواندن صفحه، استخراج متن، ذخیره و پاسخ با منبع."""
from __future__ import annotations

import http.server
import os
import socketserver
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web import learn  # noqa: E402

PAGE = """<html><head><title>دانشنامهٔ آزاد — بلاک‌چین</title>
<script>console.log("x")</script></head><body>
<nav>خانه | درباره</nav>
<h1>فناوری بلاک‌چین</h1>
<p>بلاک‌چین یک دفتر کل توزیع‌شده است که هر تراکنش در بلوکی رمزنگاری‌شده در آن ثبت می‌شود.</p>
<p>این فناوری با بیت‌کوین شناخته شد و امروز در ثبت اسناد هم به کار می‌رود.</p>
<footer>تماس با ما</footer></body></html>"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - امضای http.server
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D401 - ساکت
        return


class LearnTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.tmp = tempfile.mkdtemp(prefix="rayan-learn-")
        cls.env = mock.patch.dict(os.environ, {
            "RAYAN_LEARN_ALLOW_LOCAL": "1",
            "RAYAN_LEARNED": os.path.join(cls.tmp, "learned.sqlite3"),
            "RAYAN_ONLINE": "1",
        })
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        # هر آزمون با پایگاه تازه شروع می‌شود
        path = os.environ["RAYAN_LEARNED"]
        if os.path.exists(path):
            os.remove(path)

    def url(self, path=None):
        return f"http://127.0.0.1:{self.port}/{path or self._testMethodName}"

    def test_extractor_keeps_paragraphs_and_drops_chrome(self):
        page = learn.fetch(self.url())
        self.assertIsNotNone(page)
        self.assertIn("بلاک‌چین", page["body"])
        self.assertNotIn("console.log", page["body"])
        self.assertNotIn("تماس با ما", page["body"])
        self.assertIn("دانشنامه", page["title"])

    def test_ssrf_blocks_private_networks(self):
        with mock.patch.dict(os.environ, {"RAYAN_LEARN_ALLOW_LOCAL": "0"}):
            self.assertIsNone(learn._check_url("http://127.0.0.1:8000/"))
            self.assertIsNone(learn._check_url("http://169.254.169.254/latest/meta-data"))
            self.assertIsNone(learn._check_url("file:///etc/passwd"))
            self.assertIsNone(learn._check_url("http://10.0.0.5/admin"))

    def test_learn_store_lookup_and_answer(self):
        page = learn.learn_url(self.url())
        self.assertTrue(page["stored"])
        self.assertEqual(learn.lookup("بلاک‌چین چیست؟")["url"], self.url())
        result = learn.answer("بلاک‌چین چیست؟", learn=False)
        self.assertIsNotNone(result)
        self.assertIn("دفتر کل", result["answer"])
        self.assertEqual(result["sources"][0]["domain"], f"127.0.0.1:{self.port}")

    def test_duplicate_url_not_stored_twice(self):
        learn.learn_url(self.url())
        again = learn.learn_url(self.url())
        self.assertFalse(again["stored"])
        self.assertEqual(learn.stats()["pages"], 1)

    def test_curiosity_queue_and_grow(self):
        learn.remember("نظریهٔ ریسمان چیست؟")
        self.assertIn("نظریهٔ ریسمان چیست؟", learn.pending())
        with mock.patch.object(learn, "learn_query", return_value=[{"title": "x"}]) as patched:
            result = learn.grow(limit=1)
        self.assertEqual(result["learned"], 1)
        patched.assert_called_once()
        self.assertNotIn("نظریهٔ ریسمان چیست؟", learn.pending())

    def test_best_answer_ignores_unrelated_text(self):
        text = ("هوا امروز آفتابی است. این متن هیچ ربطی به پرسش ندارد ولی بلند است و "
                "باید رد شود چون موضوع را ندارد.")
        self.assertIsNone(learn.best_answer(text, "فتوسنتز چیست؟"))

    def test_stats_shape(self):
        stats = learn.stats()
        self.assertTrue(stats["ready"])
        self.assertIn("pages", stats)
        self.assertIn("waiting", stats)


if __name__ == "__main__":
    unittest.main()
