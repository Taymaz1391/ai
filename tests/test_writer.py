"""آزمون نویسندهٔ رایان: متن نوشتاری باید واقعاً متن باشد، نه تعریف دانشنامه‌ای."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web import retrieval, writer  # noqa: E402


class TopicTest(unittest.TestCase):
    def test_topic_extraction(self):
        self.assertEqual(writer.topic_of("یادداشتی دربارهٔ پاییز بنویس."), "پاییز")
        self.assertEqual(writer.topic_of("داستان کوتاهی دربارهٔ باران بنویس."), "باران")
        self.assertEqual(writer.topic_of("متنی دربارهٔ کتاب‌خوانی بنویس."), "کتاب‌خوانی")

    def test_no_leftover_letters(self):
        for question in ("یادداشتی دربارهٔ پاییز بنویس.", "نامه‌ای برای دوستم بنویس."):
            topic = writer.topic_of(question)
            self.assertFalse(topic.startswith("ی "), topic)
            self.assertNotIn("ای ", topic)


class WritingTest(unittest.TestCase):
    def test_note_is_a_note(self):
        hit = writer.answer("یادداشتی دربارهٔ پاییز بنویس.")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["engine"], "write")
        text = hit["answer"]
        self.assertGreater(len(text), 200)
        self.assertIn("پاییز", text)
        # نباید با تعریف فرهنگ‌نامه‌ای شروع شود
        self.assertFalse(text.startswith("پاییز یا خزان یکی از چهار فصل"))

    def test_story_has_narrative(self):
        hit = writer.answer("داستان کوتاهی دربارهٔ باران بنویس.")
        self.assertEqual(hit["engine"], "write")
        text = hit["answer"]
        self.assertIn("باران", text)
        self.assertGreaterEqual(text.count("\n\n"), 2)

    def test_letter_has_frame(self):
        text = writer.answer("نامه‌ای برای دوستم بنویس.")["answer"]
        self.assertIn("سلام", text)
        self.assertIn("با احترام", text)

    def test_poem_is_not_written_by_writer(self):
        # شعر از پیکره می‌آید، نه از این لایه
        self.assertIsNone(writer.answer("یک بیت شعر دربارهٔ دریا بنویس."))

    def test_think_does_not_answer_writing(self):
        self.assertIsNone(retrieval.think("یادداشتی دربارهٔ پاییز بنویس.")["answer"])

    def test_no_junk_captions(self):
        facts = writer._facts_about("باران")
        for fact in facts:
            self.assertNotIn("نگاره", fact)
            self.assertNotIn("px", fact)
            self.assertLess(fact.count("باران"), 4)


class GuideTest(unittest.TestCase):
    def test_sleep(self):
        hit = writer.answer("چطور بهتر بخوابم؟")
        self.assertEqual(hit["engine"], "guide")
        self.assertIn("خواب", hit["answer"])
        self.assertIn("پزشک", hit["answer"])

    def test_exercise(self):
        hit = writer.answer("یک برنامهٔ ورزشی ساده بده.")
        self.assertEqual(hit["engine"], "guide")
        self.assertIn("پیاده‌روی", hit["answer"])

    def test_factual_question_is_not_a_guide(self):
        self.assertIsNone(writer.answer("پایتخت فرانسه کدام شهر است؟"))


if __name__ == "__main__":
    unittest.main()
