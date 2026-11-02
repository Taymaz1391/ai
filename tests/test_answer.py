"""آزمون لایهٔ پاسخ اختصاصی (web/answer.py)."""
from __future__ import annotations

import datetime as dt
import unittest

from web import answer, skills


class SubjectTest(unittest.TestCase):
    def test_subject_drops_fillers(self):
        self.assertEqual(answer._subject("ابوعلی سینا که بود؟"), "ابوعلی سینا")
        self.assertEqual(answer._subject("چرا آسمان آبی است؟"), "آسمان آبی")
        self.assertEqual(answer._subject("سلام! خودت را معرفی کن"), "")


class QualityTest(unittest.TestCase):
    def test_degenerate_detects_loop(self):
        self.assertTrue(answer.degenerate("خب " * 40))
        self.assertFalse(answer.degenerate("پاریس پایتخت فرانسه است و در شمال این کشور قرار دارد."))

    def test_relevant_scores(self):
        self.assertEqual(answer.relevant("پایتخت فرانسه", "پاریس پایتخت فرانسه است."), 1.0)
        self.assertEqual(answer.relevant("پایتخت فرانسه", "هوا امروز خوب است."), 0.0)


class EnhanceTest(unittest.TestCase):
    def test_offtopic_gets_grounded_answer(self):
        """پاسخِ جایگزین باید موضوع را نام ببرد و جملهٔ کامل باشد، نه حلقهٔ تکراری."""
        out = answer.enhance("ابوعلی سینا که بود؟", "خب خب خب خب خب خب خب خب خب خب خب خب")
        self.assertIn("ابوعلی سینا", out)
        self.assertFalse(answer.degenerate(out))
        self.assertGreater(len(out), 40)

    def test_good_answer_is_kept(self):
        text = "پاریس پایتخت فرانسه است و در شمال این کشور قرار دارد."
        self.assertTrue(answer.enhance("پایتخت فرانسه کجاست؟", text).startswith("پاریس"))

    def test_empty_answer_asks_back(self):
        out = answer.enhance("چیزی", "…")
        self.assertGreater(len(out), 20)

    def test_echo_is_trimmed(self):
        out = answer.enhance("پایتخت فرانسه کجاست", "پایتخت فرانسه کجاست پاریس است")
        self.assertIn("پاریس", out)

    def test_followup_keeps_context(self):
        out = answer.enhance("بیشتر توضیح بده", "این شهر پرجمعیت‌ترین شهر کشور است.",
                             history=[("پاریس کجاست؟", "در شمال فرانسه.")])
        self.assertIn("پاریس", out)


class PersonalizeTest(unittest.TestCase):
    def test_greeting_uses_name(self):
        hit = answer.personalize(skills.match("سلام"), {"user": {"name": "سارا"}})
        self.assertIn("سارا", hit["answer"])

    def test_night_greeting(self):
        hit = answer.personalize(skills.match("سلام"), {}, dt.datetime(2026, 1, 1, 23, 30))
        self.assertRegex(hit["answer"], "شب|آرام")


class SkillsTest(unittest.TestCase):
    def test_self_intro(self):
        hit = skills.match("خودت را معرفی کن")
        self.assertEqual(hit["skill"], "self_intro")
        self.assertIn("رایان", hit["answer"])


if __name__ == "__main__":
    unittest.main()
