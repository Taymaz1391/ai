"""آزمون لایهٔ دانشنامه (ویکی‌پدیای فارسی) در مسیر «فکر کردن».

یک پایگاه کوچک FTS5 در پوشهٔ موقت ساخته می‌شود و همان ساختاری را دارد که
``scripts/build_wiki.py`` تولید می‌کند.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web import retrieval  # noqa: E402

ARTICLES = [
    ("فتوسنتز",
     "فتوسنتز (به انگلیسی: Photosynthesis) فرایندی است که در آن گیاهان با استفاده از "
     "نور خورشید و آب، غذا می‌سازند. این فرایند در کلروپلاست انجام می‌شود."),
    ("جنگ جهانی دوم",
     "متفقین غربی (کشورهای مستقل اصلی)\nجنگ جهانی دوم، جنگی فراگیر بین سال‌های ۱۹۳۹ تا "
     "۱۹۴۵ بود. آلمان در ۱۹۳۹ به لهستان حمله کرد."),
    ("برج میلاد",
     "تصویری از قسمت پایینی برج میلاد برج میلاد نام برج مخابراتی چندمنظوره‌ای است که در "
     "شمال غربی تهران قرار دارد."),
    ("دماوند",
     "دماوند کوهی در شمال ایران است. این کوه بلندترین قلهٔ ایران به شمار می‌رود."),
]

ALIASES = [("فتوسنتز چیست", "فتوسنتز"), ("برج میلاد تهران", "برج میلاد")]


class WikiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="rayan-wiki-")
        cls.db = os.path.join(cls.tmp, "wiki.sqlite3")
        with sqlite3.connect(cls.db) as db:
            db.executescript(
                """
                CREATE VIRTUAL TABLE articles USING fts5(
                    title, lead, norm UNINDEXED, tokenize='unicode61'
                );
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE alias (norm TEXT PRIMARY KEY, target TEXT);
                """
            )
            for title, lead in ARTICLES:
                db.execute("INSERT INTO articles(title, lead, norm) VALUES (?,?,?)",
                           (title, lead, retrieval.normalize(title)))
                for source in ALIASES:
                    if source[1] == title:
                        db.execute("INSERT OR IGNORE INTO alias(norm, target) VALUES (?,?)",
                                   (retrieval.normalize(source[0]), retrieval.normalize(title)))
            db.execute("INSERT INTO meta(key, value) VALUES ('articles', ?)", (str(len(ARTICLES)),))
            db.commit()
        cls.env = mock.patch.dict(os.environ, {"RAYAN_WIKI": cls.db})
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def test_exists(self):
        self.assertTrue(retrieval.wiki_exists(self.db))

    def test_exact_title(self):
        entry = retrieval.wiki_lookup("فتوسنتز چیست؟", path=self.db)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["title"], "فتوسنتز")
        self.assertEqual(entry["match"], "عنوان دقیق")

    def test_alias(self):
        entry = retrieval.wiki_lookup("برج میلاد تهران کجاست؟", path=self.db)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["title"], "برج میلاد")
        self.assertEqual(entry["match"], "تغییرمسیر")

    def test_subject_stops_at_question_word(self):
        self.assertEqual(retrieval.question_subject("پایتخت ایران کجاست؟"), ["پایتخت", "ایران"])
        self.assertEqual(retrieval.question_subject("فتوسنتز چگونه انجام می‌شود؟"), ["فتوسنتز"])

    def test_lead_answer_strips_caption(self):
        entry = retrieval.wiki_lookup("برج میلاد کجاست؟", path=self.db)
        answer = retrieval._wiki_lead_answer(entry["lead"], entry["phrase"], "برج میلاد کجاست؟")
        self.assertTrue(answer.startswith("برج میلاد نام برج"))
        self.assertNotIn("تصویری از قسمت", answer)

    def test_lead_answer_strips_infobox_prefix(self):
        entry = retrieval.wiki_lookup("جنگ جهانی دوم چه بود؟", path=self.db)
        answer = retrieval._wiki_lead_answer(entry["lead"], entry["phrase"], "جنگ جهانی دوم چه بود؟")
        self.assertTrue(answer.startswith("جنگ جهانی دوم"))
        self.assertIn("۱۹۳۹", answer)

    def test_think_uses_wiki_first(self):
        result = retrieval.think("فتوسنتز چیست؟", path=self.db)
        self.assertEqual(result["engine"], "wiki")
        self.assertIn("گیاهان", result["answer"])
        self.assertEqual(result["sources"][0]["source"], "ویکی‌پدیای فارسی")

    def test_place_question_prefers_location_sentence(self):
        result = retrieval.think("دماوند کجاست؟", path=self.db)
        self.assertIn("شمال ایران", result["answer"])


if __name__ == "__main__":
    unittest.main()
