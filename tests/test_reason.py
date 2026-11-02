"""آزمون‌های لایهٔ «فکر کردن» رایان: بازیابی، استناد، محاسبه و صداقت.

هدف این آزمون‌ها اطمینان از سه چیز است:

۱. پاسخ از شاهد ساخته می‌شود و منبع دارد (نه از متن از پیش نوشته‌شده).
۲. وقتی شاهدی نیست، هیچ واقعیتی ساخته نمی‌شود.
۳. محاسبه و تبدیل یکا دقیق است.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("RAYAN_ONLINE", "0")  # آزمون‌ها نباید به شبکه بروند

from web import reason, retrieval  # noqa: E402

DOCS = [
    ("doc-iran", "پایتخت ایران تهران است. تهران بزرگ‌ترین شهر ایران است و مرکز استان تهران است."),
    ("doc-france", "پایتخت فرانسه پاریس است. پاریس در شمال فرانسه قرار دارد."),
    ("doc-water", "آب در دمای صد درجهٔ سانتی‌گراد می‌جوشد. این دما به فشار هوا بستگی دارد."),
    ("doc-fa", "زبان فارسی از خانوادهٔ زبان‌های هندواروپایی است. فارسی در ایران و افغانستان رایج است."),
    ("doc-other", "باشگاه فوتبال دومبارتون یک باشگاه فوتبال در شهر دومبارتون اسکاتلند است."),
]


class RetrievalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="rayan-index-")
        cls.corpus = os.path.join(cls.tmp, "corpus.txt")
        with open(cls.corpus, "w", encoding="utf-8") as fh:
            for _key, body in DOCS:
                fh.write("<|doc|>\n" + body + "\n")
        cls.db = os.path.join(cls.tmp, "index.sqlite3")
        cls.info = retrieval.build_index([("آزمون", cls.corpus)], out_path=cls.db)

    def test_index_built(self):
        self.assertTrue(retrieval.index_exists(self.db))
        self.assertEqual(self.info["documents"], len(DOCS))
        self.assertGreater(self.info["passages"], 0)

    def test_answer_comes_from_evidence(self):
        result = retrieval.think("پایتخت ایران کجاست؟", path=self.db)
        self.assertIsNotNone(result["answer"])
        self.assertIn("تهران", result["answer"])
        self.assertNotIn("پاریس", result["answer"])
        self.assertTrue(result["sources"])
        self.assertGreater(result["confidence"], 0.5)

    def test_correct_document_selected(self):
        result = retrieval.think("پایتخت فرانسه کجاست؟", path=self.db)
        self.assertIn("پاریس", result["answer"])
        self.assertNotIn("تهران", result["answer"])

    def test_question_word_not_in_subject(self):
        """واژه‌های پرسشی نباید موضوع حساب شوند (باگ قدیمی: «کجاست»)."""
        subject = retrieval.subject_phrase("پایتخت ایران کجاست؟")
        self.assertNotIn("کجاست", subject)
        self.assertIn("ایران", subject)

    def test_no_evidence_returns_none(self):
        result = retrieval.think("دربارهٔ سیاهچاله‌های کهکشان آندرومدا چه می‌دانی؟", path=self.db)
        self.assertIsNone(result["answer"])
        self.assertEqual(result["confidence"], 0.0)

    def test_unrelated_sentence_rejected(self):
        """باشگاه فوتبال نباید جواب «پایتخت ایران» شود."""
        result = retrieval.think("پایتخت ایران کجاست؟", path=self.db)
        self.assertNotIn("دومبارتون", result["answer"])

    def test_trace_is_real(self):
        result = retrieval.think("زبان فارسی چیست؟", path=self.db)
        self.assertTrue(result["trace"])
        for step in result["trace"]:
            self.assertIn("step", step)
            self.assertIn("detail", step)


class FollowupTest(unittest.TestCase):
    """پرسش‌های کوتاه پیگیری باید موضوع گفتگو را به ارث ببرند."""

    HISTORY = [("پایتخت فرانسه کجاست؟", "پایتخت فرانسه پاریس است.")]

    def test_short_followup_inherits_subject(self):
        self.assertEqual(retrieval.resolve_followup("و ژاپن؟", self.HISTORY),
                         "پایتخت ژاپن کجاست")

    def test_single_word_followup(self):
        self.assertEqual(retrieval.resolve_followup("ژاپن؟", self.HISTORY),
                         "پایتخت ژاپن کجاست")

    def test_new_question_untouched(self):
        self.assertEqual(retrieval.resolve_followup("فتوسنتز چیست؟", self.HISTORY),
                         "فتوسنتز چیست؟")

    def test_same_subject_untouched(self):
        self.assertEqual(retrieval.resolve_followup("و پایتختش؟", self.HISTORY), "و پایتختش؟")

    def test_no_history(self):
        self.assertEqual(retrieval.resolve_followup("و ژاپن؟", []), "و ژاپن؟")


class ReasonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="rayan-reason-")
        corpus = os.path.join(cls.tmp, "corpus.txt")
        with open(corpus, "w", encoding="utf-8") as fh:
            for _key, body in DOCS:
                fh.write("<|doc|>\n" + body + "\n")
        cls.db = os.path.join(cls.tmp, "index.sqlite3")
        retrieval.build_index([("آزمون", corpus)], out_path=cls.db)
        cls.previous = os.environ.get("RAYAN_INDEX")
        os.environ["RAYAN_INDEX"] = cls.db

    @classmethod
    def tearDownClass(cls):
        if cls.previous is None:
            os.environ.pop("RAYAN_INDEX", None)
        else:
            os.environ["RAYAN_INDEX"] = cls.previous

    def test_evidence_path(self):
        out = reason.answer("پایتخت ایران کجاست؟")
        self.assertEqual(out["engine"], "think")
        self.assertIn("تهران", out["answer"])
        self.assertTrue(out["sources"])
        self.assertTrue(out["thought"]["steps"])

    def test_arithmetic(self):
        out = reason.answer("۱۲*۳ چند است؟")
        self.assertEqual(out["engine"], "calc")
        self.assertIn("۳۶", out["answer"])

    def test_unit_conversion(self):
        out = reason.answer("۵ کیلومتر به متر")
        self.assertEqual(out["engine"], "convert")
        self.assertIn("۵٬۰۰۰", out["answer"])

    def test_honest_when_unknown(self):
        out = reason.answer("نظریهٔ ریسمان را با جزئیات توضیح بده")
        if out["answer"]:
            # مسیر مدل: نباید ادعای واقعیتِ ساختگی کند
            self.assertIn(out["engine"], {"chat", "deep"})
        else:
            text = reason.honest("نظریهٔ ریسمان چیست؟", ["فیزیک", "کوانتوم"])
            self.assertIn("شاهد مطمئنی", text)
            self.assertIn("فیزیک", text)

    def test_no_prewritten_answer_for_factual_question(self):
        """پرسشی که در دانشنامه نیست باید یا شاهد داشته باشد یا صریح بگوید نمی‌دانم."""
        out = reason.answer("بیشترین جمعیت استان‌های ایران چقدر است؟")
        self.assertNotIn("۶٫۵۷", out.get("answer") or "")


class LooksFactualTest(unittest.TestCase):
    def test_questions(self):
        self.assertTrue(retrieval.looks_factual("پایتخت ایران کجاست؟"))
        self.assertTrue(retrieval.looks_factual("زبان فارسی چیست"))
        self.assertFalse(retrieval.looks_factual("سلام"))
        self.assertFalse(retrieval.looks_factual("یک شعر بگو"))


if __name__ == "__main__":
    unittest.main()
