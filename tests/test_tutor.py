"""آزمون دستیار موضوعی: کدِ تولیدشده باید اجرا شود، دستور زبان باید از خودِ جمله بیاید."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web import tutor  # noqa: E402


def _blocks(answer: str) -> list[str]:
    """قطعه‌های کدِ داخل پاسخ را جدا می‌کند."""
    return re.findall(r"```python\n(.*?)```", answer, re.S)


class CodeTest(unittest.TestCase):
    CASES = (
        "یک تابع پایتون برای جمع دو عدد بنویس.",
        "یک تابع برای تفریق دو عدد بنویس",
        "یک تابع ضرب دو عدد بنویس",
        "یک تابع تقسیم دو عدد بنویس",
        "یک تابع فاکتوریل بنویس",
        "تابع فیبوناچی بنویس",
        "تابع تشخیص عدد اول بنویس",
        "در پایتون فهرست را چطور می‌سازیم؟",
        "حلقهٔ تکرار در پایتون چه دستوری است؟",
        "دیکشنری در پایتون چطور بسازیم؟",
        "مرتب‌سازی فهرست در پایتون",
        "کد معکوس رشته در پایتون",
        "یک تابع پایتون بنویس",
        "مجموع اعداد یک تا ده را با حلقه بنویس.",
    )

    def test_every_answer_has_runnable_code(self):
        for question in self.CASES:
            with self.subTest(question=question):
                hit = tutor.answer(question)
                self.assertIsNotNone(hit, question)
                self.assertEqual(hit["engine"], "code")
                blocks = _blocks(hit["answer"])
                self.assertTrue(blocks, question)
                code = blocks[0]
                compile(code, "<tutor>", "exec")          # نحو درست
                namespace: dict = {}
                exec(code, namespace)                      # اجرا هم می‌شود
                self.assertIn("__builtins__", namespace)

    def test_add_function_is_correct(self):
        hit = tutor.answer("یک تابع پایتون برای جمع دو عدد بنویس.")
        namespace: dict = {}
        exec(_blocks(hit["answer"])[0], namespace)
        self.assertEqual(namespace["add"](2, 3), 5)
        self.assertEqual(namespace["add"](-4, 1), -3)

    def test_factorial_is_correct(self):
        hit = tutor.answer("یک تابع فاکتوریل بنویس")
        namespace: dict = {}
        exec(_blocks(hit["answer"])[0], namespace)
        self.assertEqual(namespace["factorial"](5), 120)
        self.assertEqual(namespace["factorial"](0), 1)

    def test_prime_is_correct(self):
        hit = tutor.answer("تابع تشخیص عدد اول بنویس")
        namespace: dict = {}
        exec(_blocks(hit["answer"])[0], namespace)
        prime = namespace["is_prime"]
        self.assertTrue(prime(97))
        self.assertFalse(prime(1))
        self.assertFalse(prime(100))

    def test_divide_guard(self):
        hit = tutor.answer("یک تابع تقسیم دو عدد بنویس")
        namespace: dict = {}
        exec(_blocks(hit["answer"])[0], namespace)
        self.assertEqual(namespace["divide"](10, 4), 2.5)
        with self.assertRaises(ValueError):
            namespace["divide"](1, 0)

    def test_no_false_positive_on_math_or_literature(self):
        for question in ("تابع در ریاضی چیست؟", "تابع خطی را توضیح بده",
                         "فهرست خریدم را چطور بنویسم؟", "دیکشنری انگلیسی به فارسی می‌خواهم"):
            self.assertIsNone(tutor.answer(question), question)


class GrammarTest(unittest.TestCase):
    def test_verb(self):
        answer = tutor.answer("فعل جملهٔ «او رفت» کدام است؟")["answer"]
        self.assertIn("«رفت»", answer)

    def test_subject(self):
        answer = tutor.answer("در جملهٔ «هوا سرد است»، نهاد کدام است؟")["answer"]
        self.assertIn("«هوا»", answer)

    def test_object(self):
        answer = tutor.answer("مفعول جملهٔ «کتاب را خواندم» کدام است؟")["answer"]
        self.assertIn("«کتاب»", answer)

    def test_tense(self):
        answer = tutor.answer("زمان فعل جملهٔ «او می‌رود» چیست؟")["answer"]
        self.assertIn("حال", answer)

    def test_predicate(self):
        answer = tutor.answer("مسند جملهٔ «هوا سرد است» کدام است؟")["answer"]
        self.assertIn("«سرد»", answer)

    def test_plural(self):
        answer = tutor.answer("«کتاب‌ها» جمع چه واژه‌ای است؟")["answer"]
        self.assertIn("«کتاب»", answer)
        self.assertNotIn("\u200c»", answer)     # نیم‌فاصلهٔ آویزان نماند

    def test_singular(self):
        answer = tutor.answer("مفرد «درختان» چیست؟")["answer"]
        self.assertIn("«درخت»", answer)

    def test_ra_vs_be(self):
        answer = tutor.answer("تفاوت «را» و «به» را توضیح بده.")["answer"]
        self.assertIn("مفعول", answer)
        self.assertGreater(len(answer), 80)

    def test_concept_question(self):
        answer = tutor.answer("نهاد چیست؟")["answer"]
        self.assertIn("خبر", answer)

    def test_substring_is_not_a_keyword(self):
        """«پیشنهادی» نباید «نهاد» شمرده شود و پاسخ دستوری بگیرد."""
        for question in ("برای شروع یک روز خوب چه پیشنهادی داری؟",
                         "یک برنامهٔ ساده برای ورزش روزانه بده."):
            self.assertIsNone(tutor.answer(question), question)

    def test_unknown_sentence_is_not_guessed(self):
        # بدون فعل شناخته‌شده، پاسخ ساخته نمی‌شود
        self.assertIsNone(tutor.grammar_answer("رنگ جملهٔ «xyz» کدام است؟"))


class FactTest(unittest.TestCase):
    def test_boiling_water(self):
        answer = tutor.answer("آب در چه دمایی می‌جوشد؟")["answer"]
        self.assertIn("۱۰۰", answer)
        self.assertIn("سلسیوس", answer)

    def test_seasons_and_numbers(self):
        self.assertIn("هشت", tutor.answer("منظومهٔ شمسی چند سیاره دارد؟")["answer"])
        self.assertIn("Au", tutor.answer("نماد شیمیایی طلا چیست؟")["answer"])
        self.assertIn("۲۰۶", tutor.answer("بدن انسان چند استخوان دارد؟")["answer"])

    def test_province_center(self):
        self.assertIn("شیراز", tutor.answer("مرکز استان فارس کجاست؟")["answer"])
        self.assertIn("کرج", tutor.answer("مرکز استان البرز کدام شهر است؟")["answer"])

    def test_book_author(self):
        self.assertIn("سعدی", tutor.answer("نویسندهٔ کتاب گلستان کیست؟")["answer"])
        self.assertIn("هدایت", tutor.answer("مولف «بوف کور» چه کسی است؟")["answer"])

    def test_units_and_water(self):
        self.assertIn("نیوتون", tutor.answer("واحد اندازه‌گیری نیرو چیست؟")["answer"])
        self.assertIn("هیدروژن", tutor.answer("آب از چه عنصری ساخته شده است؟")["answer"])

    def test_no_fact_for_unrelated(self):
        self.assertIsNone(tutor.fact_answer("یک برنامهٔ ساده برای ورزش روزانه بده."))


if __name__ == "__main__":
    unittest.main()
