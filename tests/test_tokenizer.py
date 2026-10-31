"""آزمون‌های توکنایزر فارسی پارسیا."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from parsia.tokenizer import SPECIAL_TOKENS, BPETokenizer

TOKENIZER = os.path.join(ROOT, "tokenizer", "parsia_bpe.json")


@unittest.skipUnless(os.path.exists(TOKENIZER), "tokenizer not trained yet")
class TokenizerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tok = BPETokenizer.load(TOKENIZER)

    def test_vocab_and_specials(self):
        self.assertEqual(self.tok.vocab_size, 10000)
        for token in SPECIAL_TOKENS:
            self.assertIn(token, self.tok.token_to_id)
        ids = self.tok.encode("<|doc|> <|user|> سلام <|bot|> ")
        self.assertIn(self.tok.special_ids["<|doc|>"], ids)
        self.assertIn(self.tok.special_ids["<|user|>"], ids)

    def test_persian_roundtrip(self):
        text = "زبان فارسی، خانه اندیشه است و می‌شود با آن نوشت."
        decoded = self.tok.decode(self.tok.encode(text))
        for word in ("فارسی", "خانه", "اندیشه", "می‌شود"):
            self.assertIn(word, decoded)

    def test_zwnj_preserved(self):
        text = "نمی‌دانم کتاب‌ها را می‌شود خواند"
        ids = self.tok.encode(text)
        decoded = self.tok.decode(ids)
        self.assertIn("نمی‌دانم", decoded)
        self.assertIn("کتاب‌ها", decoded)

    def test_punctuation_and_digits(self):
        text = "سال ۱۴۰۵ بود، واقعاً؟"
        decoded = self.tok.decode(self.tok.encode(text))
        self.assertIn("؟", decoded)
        self.assertIn("1405", decoded)

    def test_skip_specials(self):
        ids = self.tok.encode("<|doc|> سلام <|verse|> دنیا <|bot|> ")
        decoded = self.tok.decode(ids, skip_specials=True)
        self.assertNotIn("<|", decoded)
        self.assertIn("سلام", decoded)

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "val.txt")), "validation corpus missing")
    def test_compression(self):
        with open(os.path.join(ROOT, "data", "val.txt"), encoding="utf-8") as fh:
            text = fh.read()[:120_000]
        ratio = len(text) / len(self.tok.encode(text))
        self.assertGreater(ratio, 3.0)  # نویسه بر توکن
        self.assertLess(ratio, 6.0)


if __name__ == "__main__":
    unittest.main()
