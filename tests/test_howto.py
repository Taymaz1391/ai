"""آزمونِ راهنمای کاربردی و ابزارهای تازه (بدونِ شبکه)."""

from __future__ import annotations

import unittest

from web import howto, tools


class HowtoCardTest(unittest.TestCase):
    def test_cards_answer_with_steps(self):
        cases = {
            "چطور قبض گاز را کم کنم؟": "bills",
            "چطور عادت کتاب‌خواندن بسازم؟": "reading",
            "چطور رزومه بنویسم؟": "interview",
            "برای یادگیری زبان، هر روز چقدر وقت بگذارم؟": "language",
            "چطور بوی بد یخچال را از بین ببرم؟": "cleaning",
        }
        for question, guide in cases.items():
            with self.subTest(question=question):
                found = howto.answer(question)
                self.assertIsNotNone(found)
                self.assertEqual(found["guide"], guide)
                self.assertIn("۱.", found["answer"])
                self.assertGreater(len(found["answer"]), 120)

    def test_generic_guide_is_topic_neutral(self):
        found = howto.answer("چطور برای نگهداری از گیاه آپارتمانی برنامه بچینم؟")
        self.assertIsNotNone(found)
        self.assertEqual(found["guide"], "generic")
        # قالبِ عمومی نباید دربارهٔ «نوشتن» یا «عدد» حرف بزند
        self.assertNotIn("عددی و یک‌خطی", found["answer"])
        self.assertIn("علتِ اصلی", found["answer"])


class HowtoGateTest(unittest.TestCase):
    def test_social_is_not_a_guide(self):
        for question in ("حالت چطوره؟", "سلام، خوبی؟", "مرسی از راهنماییت",
                         "سلام وقت بخیر", "چه کارهایی می‌توانی انجام بدهی؟"):
            with self.subTest(question=question):
                self.assertIsNone(howto.answer(question))

    def test_tech_goes_to_code_engine(self):
        for question in ("در پایتون چطور یک فایل را بخوانم؟",
                         "در جاوااسکریپت چطور به کلیک گوش بدهم؟"):
            with self.subTest(question=question):
                self.assertIsNone(howto.answer(question))

    def test_knowledge_question_is_not_hijacked(self):
        for question in ("چه کسی لامپ را اختراع کرد؟",
                         "بلندترین کوه جهان چه نام دارد؟",
                         "غزل چیست؟"):
            with self.subTest(question=question):
                self.assertIsNone(howto.answer(question))

    def test_short_or_empty_subject_rejected(self):
        for question in ("چطور؟", "چیکار کنم", "چطور انجامش بدهم"):
            with self.subTest(question=question):
                self.assertIsNone(howto.answer(question))

    def test_topics_are_unique(self):
        ids = list(howto.topics())
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("reading", ids)
        self.assertIn("cleaning", ids)


class WeekdayShiftTest(unittest.TestCase):
    def test_forward_shift(self):
        out = tools.weekday_shift("اگر امروز سه‌شنبه باشد، پنج روز بعد چه روزی است؟")
        self.assertIsNotNone(out)
        self.assertIn("یکشنبه", out["answer"])

    def test_backward_shift(self):
        out = tools.weekday_shift("اگر امروز جمعه باشد دو روز قبل چه روزی بود؟")
        self.assertIsNotNone(out)
        self.assertIn("چهارشنبه", out["answer"])

    def test_unrelated_question(self):
        self.assertIsNone(tools.weekday_shift("قبض گاز من چقدر است؟"))
        self.assertIsNone(tools.weekday_shift("سه‌شنبه چه ساعتی جلسه داریم؟"))

    def test_date_tool_not_stolen_by_code_question(self):
        self.assertIsNone(tools.detect("در پایتون چطور تاریخ امروز را بگیرم؟"))
        self.assertTrue(tools.detect("تاریخ امروز چندمه؟"))

    def test_math_with_zwnj_operator(self):
        out = tools.detect("۱۲ تقسیم بر ۴ به‌علاوهٔ ۷ چند است؟")
        self.assertIsNotNone(out)
        self.assertEqual(out["value"], 10)


if __name__ == "__main__":
    unittest.main()
