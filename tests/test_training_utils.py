"""آزمون ابزارهای آموزش: نسبت نویسه بر توکن و برنامهٔ نرخ یادگیری."""
from __future__ import annotations

import argparse
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rayan.train import lr_at, measure_chars_per_token  # noqa: E402


class CharsPerTokenTest(unittest.TestCase):
    def setUp(self):
        self.old_cwd = os.getcwd()
        os.chdir(ROOT)

    def tearDown(self):
        os.chdir(self.old_cwd)

    def test_explicit_value_wins(self):
        args = argparse.Namespace(chars_per_token=3.25, val="data/val.txt")
        self.assertEqual(measure_chars_per_token(args, [1, 2, 3]), 3.25)

    def test_measured_from_tokenized_stats(self):
        """عدد باید از آمار واقعی بیاید، نه از مقدار ثابت قدیمی ۴٫۲۵."""
        path = os.path.join(ROOT, "data", "tokenized_stats.json")
        if not os.path.exists(path):
            self.skipTest("tokenized stats missing")
        args = argparse.Namespace(chars_per_token=0.0, val="data/val.txt")
        ratio = measure_chars_per_token(args, [1, 2, 3])
        self.assertGreater(ratio, 3.0)
        self.assertLess(ratio, 4.5)


class ScheduleTest(unittest.TestCase):
    def test_warmup_rises(self):
        self.assertLess(lr_at(0, 100, 1e-3, 1e-4, 10), lr_at(9, 100, 1e-3, 1e-4, 10))

    def test_decays_to_min(self):
        # کسینوس در گام آخر «تقریباً» به کف می‌رسد (progress کامل فقط بعد از پایان است)
        self.assertLess(lr_at(99, 100, 1e-3, 1e-4, 10), 1.05e-4)

    def test_resume_window_is_relative(self):
        """در ادامهٔ آموزش، گام صفرِ نسبی باید نرخ پایه را بدهد (بعد از warmup)."""
        base = lr_at(0, 40, 3e-4, 6e-5, 1)
        self.assertAlmostEqual(base, 3e-4, places=9)


if __name__ == "__main__":
    unittest.main()
