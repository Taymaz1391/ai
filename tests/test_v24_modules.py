"""آزمون‌های لایهٔ تازهٔ پاسخ‌گویی: ترجمه، مسئلهٔ کلامی، بستهٔ دانش و نگهبان‌ها."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web import answer, knowledge, mathword, translate, tutor  # noqa: E402


class TranslateTest(unittest.TestCase):
    """ترجمه باید جمله را با ترتیبِ درست بدهد، نه واژه‌های پراکنده."""

    def test_fa_to_en_simple(self):
        out = translate.answer("ترجمه کن به انگلیسی: من امروز خسته‌ام")["answer"]
        self.assertIn("I am", out)
        self.assertIn("tired", out)

    def test_fa_to_en_future_place(self):
        out = translate.answer("ترجمه کن به انگلیسی: ما فردا به شیراز می‌رویم")["answer"]
        self.assertIn("Shiraz", out)
        self.assertIn("will", out)

    def test_en_to_fa_copula(self):
        out = translate.answer("ترجمه کن به فارسی: She is a doctor.")["answer"]
        self.assertIn("پزشک", out)

    def test_en_to_fa_have(self):
        out = translate.answer("ترجمه کن به فارسی: I have a book.")["answer"]
        self.assertIn("کتاب", out)
        self.assertIn("دارم", out)

    def test_en_to_fa_go(self):
        out = translate.answer("ترجمه کن به فارسی: We go to school.")["answer"]
        self.assertIn("مدرسه", out)

    def test_fixed_phrase(self):
        out = translate.answer("به انگلیسی «شب بخیر» چه می‌شود؟")["answer"]
        self.assertIn("ood night", out)

    def test_gloss(self):
        hit = translate.lookup("happy")
        self.assertIsNotNone(hit)
        self.assertIn("خوشحال", hit["meaning"])


class MathWordTest(unittest.TestCase):
    """مسئله‌های کلامی باید عددِ درست و روشِ بازبینی بدهند."""

    def _answer(self, question: str) -> str:
        hit = mathword.answer(question)
        self.assertIsNotNone(hit, question)
        return hit["answer"]

    def test_percent(self):
        self.assertIn("۷۵", self._answer("۳۰ درصد از ۲۵۰ چند است؟"))

    def test_average(self):
        self.assertIn("۱۵", self._answer("میانگین ۱۲ و ۱۸ چند است؟"))

    def test_root(self):
        self.assertIn("۱۴", self._answer("جذر ۱۹۶ چند است؟"))

    def test_ratio(self):
        self.assertIn("۴", self._answer("اگر سن پدر ۴۰ و پسر ۱۰ باشد، پدر چند برابر پسر است؟"))

    def test_speed_distance(self):
        self.assertIn("۳۶۰", self._answer("سرعت ۱۲۰ کیلومتر بر ساعت در ۳ ساعت چند کیلومتر است؟"))

    def test_speed_from_distance(self):
        self.assertIn("۹۰", self._answer("ماشینی ۱۸۰ کیلومتر را در ۲ ساعت می‌رود؛ سرعتش چقدر است؟"))

    def test_workers_inverse(self):
        self.assertIn("۲", self._answer("اگر ۴ نفر در ۳ روز کاری را تمام کنند، ۶ نفر در چند روز؟"))

    def test_geometry(self):
        self.assertIn("۱۲", self._answer("مساحت مثلثی با قاعده ۶ و ارتفاع ۴ چند است؟"))
        self.assertIn("۲۸", self._answer("محیط مربعی با ضلع ۷ سانتی‌متر چند است؟"))

    def test_worded_fraction(self):
        self.assertIn("۶۰", self._answer("دو سوم ۹۰ چند است؟"))

    def test_plain_question_is_not_hijacked(self):
        self.assertIsNone(mathword.answer("پایتخت ایران کجاست؟"))


class KnowledgePackTest(unittest.TestCase):
    """بستهٔ دانش باید معتبر، بی‌تکرار و پاسخ‌گو باشد."""

    PACK = ROOT / "data" / "knowledge-pack.jsonl"

    def test_pack_is_valid_jsonl(self):
        rows = [json.loads(line) for line in
                self.PACK.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertGreater(len(rows), 200)
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)), "شناسهٔ تکراری در بستهٔ دانش")
        for row in rows:
            self.assertTrue(row["q"].strip())
            self.assertTrue(row["a"].strip())
            self.assertTrue(row["keys"])

    def test_no_internal_naming_in_answers(self):
        """هیچ پاسخ دانشی نباید نامِ فایل، مخزن یا پیکره را لو بدهد."""
        banned = ("knowledge.jsonl", "github", "repo", "پیکره", "checkpoint", ".npz")
        for line in self.PACK.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            body = json.loads(line)["a"]
            for word in banned:
                self.assertNotIn(word, body)

    def test_lookup_hits(self):
        samples = {
            "بلندترین ساختمان جهان کدام است؟": "خلیفه",
            "ویتامین D از کجا می‌آید؟": "خورشید",
            "چرا ماه شکلش عوض می‌شود؟": "اهله",
            "بزرگ‌ترین جزیرهٔ جهان کدام است؟": "گرینلند",
            "مرکز استان گیلان کجاست؟": "رشت",
        }
        for question, expected in samples.items():
            hit = knowledge.answer(question)
            self.assertIsNotNone(hit, question)
            self.assertIn(expected, hit["answer"])

    def test_small_talk_is_not_a_fact(self):
        for phrase in ("خوبی؟", "ممنون", "خداحافظ"):
            self.assertIsNone(knowledge.answer(phrase), phrase)

    def test_year_question_prefers_a_year(self):
        hit = knowledge.answer("تهران در چه سالی پایتخت ایران شد؟")
        self.assertIsNotNone(hit)
        self.assertRegex(hit["answer"], r"۱۷۹۶|۱۱۷۵")

    def test_start_and_end_are_distinguished(self):
        start = knowledge.answer("جنگ جهانی دوم در چه سالی شروع شد؟")
        end = knowledge.answer("جنگ جهانی دوم در چه سالی پایان یافت؟")
        self.assertIn("۱۹۳۹", start["answer"])
        self.assertIn("۱۹۴۵", end["answer"])

    def test_location_question_still_works(self):
        hit = knowledge.answer("پایتخت ایران کجاست؟")
        self.assertIn("تهران", hit["answer"])


class TutorTest(unittest.TestCase):
    """کد باید کد باشد: SQL، جاوااسکریپت و پایتون هر سه پاسخ دارند."""

    def test_sql_insert(self):
        out = tutor.answer("در SQL چطور یک رکورد تازه اضافه کنم؟")["answer"]
        self.assertIn("INSERT", out)

    def test_js_event(self):
        out = tutor.answer("در جاوااسکریپت چطور یک دکمه را به تابع وصل کنم؟")["answer"]
        self.assertIn("addEventListener", out)

    def test_python_loop(self):
        out = tutor.answer("در پایتون با حلقه اعداد ۱ تا ۵ را چاپ کن")["answer"]
        self.assertIn("range", out)
        self.assertIn("for", out)

    def test_python_random(self):
        out = tutor.answer("در پایتون چطور یک عدد تصادفی بگیرم؟")["answer"]
        self.assertIn("random", out)

    def test_python_cast(self):
        out = tutor.answer("در پایتون چطور یک رشته را به عدد تبدیل کنم؟")["answer"]
        self.assertIn("int(", out)


class GroundedTest(unittest.TestCase):
    """وقتی شاهدی نیست، پاسخ باید کارِ بعدی را نشان بدهد، نه بهانه بیاورد."""

    def test_no_excuse_phrases(self):
        out = answer.grounded("چطور یک قایق بادبانی ارزان بخرم؟")
        for phrase in ("نمی‌دانم", "قابل‌اتکایی ندارم", "بیرون از توان"):
            self.assertNotIn(phrase, out)

    def test_answer_mentions_subject(self):
        out = answer.grounded("چطور یک قایق بادبانی بخرم؟")
        self.assertIn("قایق", out)
        self.assertGreater(len(out), 40)

    def test_evidence_takes_priority(self):
        out = answer.grounded("پایتخت فرانسه کجاست؟")
        self.assertTrue(out.strip())


if __name__ == "__main__":
    unittest.main()
