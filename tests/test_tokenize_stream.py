"""آزمون برابری رمزگذاری جریانی با رمزگذاری یک‌جا.

اگر مرز تکه‌ها روی شکستن خط بیفتد، خروجی ``encode_stream`` باید بیت‌به‌بیت با
``tokenizer.encode`` روی کل متن یکی باشد؛ در غیر این صورت آموزش روی توکن‌هایی
تمرین می‌کند که با استنتاج (که متن را یک‌جا رمز می‌کند) هم‌خوان نیستند.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rayan.tokenizer import BPETokenizer

TOKENIZER = os.path.join(ROOT, "tokenizer", "rayan_bpe_16k.json")


def load_stream_module():
    path = os.path.join(ROOT, "scripts", "tokenize_corpus.py")
    spec = importlib.util.spec_from_file_location("rayan_tokenize_corpus", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(os.path.exists(TOKENIZER), "tokenizer missing")
class StreamTokenizeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tok = BPETokenizer.load(TOKENIZER)
        cls.module = load_stream_module()
        cls.text = (
            "خط اول این متن است.\n"
            "خط دوم کمی طولانی‌تر است و نیم‌فاصله دارد.\n"
            "\n"
            "پاراگراف تازه با شعر: ای دل اگر به عشق، برسی به کام خویش.\n"
            "پایان متن.\n"
        ) * 40

    def _run(self, chunk_chars: int) -> list[int]:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(self.text)
            src = fh.name
        out = src + ".u16"
        try:
            info = self.module.encode_stream(src, out, self.tok, chunk_chars=chunk_chars)
            ids = np.fromfile(out, dtype=np.uint16).tolist()
        finally:
            for path in (src, out):
                try:
                    os.unlink(path)
                except OSError:
                    pass
        self.assertEqual(info["chars"], len(self.text))
        self.assertEqual(info["tokens"], len(ids))
        return ids

    def test_small_chunks_match_whole_text(self):
        expected = self.tok.encode(self.text)
        for chunk in (64, 300, 1024):
            with self.subTest(chunk=chunk):
                self.assertEqual(self._run(chunk), expected)

    def test_no_newline_block_grows(self):
        """متنی بدون شکستن خط باید کامل خوانده شود، نه نصفه."""
        text = "یک متن بدون شکستن خط " * 200
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(text)
            src = fh.name
        out = src + ".u16"
        try:
            info = self.module.encode_stream(src, out, self.tok, chunk_chars=100)
            ids = np.fromfile(out, dtype=np.uint16).tolist()
        finally:
            for path in (src, out):
                try:
                    os.unlink(path)
                except OSError:
                    pass
        self.assertEqual(info["chars"], len(text))
        # بدون شکستن خط، برش روی آخرین فاصله انجام می‌شود؛ پس توکن‌ها هم باید یکی باشند
        self.assertEqual(ids, self.tok.encode(text))

    def test_long_text_without_any_separator_keeps_every_char(self):
        """متن پیوستهٔ بی‌فاصله هم نباید نویسه از دست بدهد."""
        text = "الف" * 5000
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(text)
            src = fh.name
        out = src + ".u16"
        try:
            info = self.module.encode_stream(src, out, self.tok, chunk_chars=256)
        finally:
            for path in (src, out):
                try:
                    os.unlink(path)
                except OSError:
                    pass
        self.assertEqual(info["chars"], len(text))

    def test_newlines_survive_roundtrip(self):
        ids = self.tok.encode(self.text)
        self.assertEqual(self.tok.decode(ids), self.text.rstrip("\n"))


if __name__ == "__main__":
    unittest.main()
