"""آزمون بستنِ اجرا: کارت واقعی، انتشار checkpoint و هم‌خوانی توکنایزر.

هیچ عددی از خود اسکریپت انتظار نمی‌رود؛ فقط بررسی می‌شود که مقادیر از checkpoint
و فایل‌های واقعی خوانده شوند و کارت سایت با مدل منتشرشده هم‌خوان باشد.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rayan.model import GPTConfig, init_params, load_checkpoint, save_checkpoint  # noqa: E402
from rayan.tokenizer import BPETokenizer  # noqa: E402

TOKENIZER = os.path.join(ROOT, "tokenizer", "rayan_bpe_16k.json")


@unittest.skipUnless(os.path.exists(TOKENIZER), "tokenizer missing")
class FinalizeRunTest(unittest.TestCase):
    def test_finalize_writes_truthful_card(self):
        tmp = tempfile.mkdtemp(prefix="rayan-finalize-")
        cfg = GPTConfig(vocab_size=16000, block_size=16, n_layer=1, n_head=1, n_embd=8)
        params = init_params(cfg, seed=5)
        source = os.path.join(tmp, "tiny.npz")
        save_checkpoint(source, cfg, params, {"step": 7, "tokens_seen": 1234, "steps_planned": 10})
        metrics = os.path.join(tmp, "metrics.jsonl")
        with open(metrics, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"step": 5, "loss": 8.0, "tok_s": 900.0, "tokens": 1000,
                                 "elapsed_s": 10.0, "kind": "train"}) + "\n")
            fh.write(json.dumps({"step": 7, "val_loss": 7.5, "ppl": 1808.0, "bits_per_char": 2.5,
                                 "kind": "eval"}) + "\n")

        run_config = os.path.join(tmp, "run.json")
        report = os.path.join(tmp, "report.json")
        published = os.path.join(tmp, "last.npz")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "finalize_run.py"),
             "--checkpoint", source, "--tokenizer", TOKENIZER, "--metrics", metrics,
             "--publish", published, "--run-config", run_config, "--report", report,
             "--skip-eval", "--name", "آزمون"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])

        with open(run_config, encoding="utf-8") as fh:
            card = json.load(fh)
        self.assertEqual(card["vocab"], 16000)
        self.assertEqual(card["params"], int(sum(p.size for p in params.values())))
        self.assertEqual(card["steps"], 7)
        self.assertEqual(card["tokens_seen"], 1234)
        self.assertEqual(card["val_loss"], 7.5)
        self.assertEqual(card["best_val_loss"], 7.5)
        self.assertEqual(card["tokens_per_second"], 900.0)
        self.assertTrue(card["name"])

        # مدل منتشرشده باید با توکنایزر ۱۶هزارتایی هم‌واژگان باشد
        published_cfg, _, published_meta = load_checkpoint(published)
        tokenizer = BPETokenizer.load(TOKENIZER)
        self.assertEqual(published_cfg.vocab_size, tokenizer.vocab_size)
        self.assertEqual(published_meta.get("model_id"), "rayan-2-base")
        self.assertEqual(published_meta.get("params"), card["params"])

        with open(report, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["params"], card["params"])
        self.assertIsNone(data["independent_evaluation"])
        self.assertEqual(data["training_metrics"]["tokens_seen"], 1234)

    def test_mismatched_tokenizer_is_rejected(self):
        tmp = tempfile.mkdtemp(prefix="rayan-finalize-bad-")
        cfg = GPTConfig(vocab_size=10000, block_size=16, n_layer=1, n_head=1, n_embd=8)
        source = os.path.join(tmp, "old.npz")
        save_checkpoint(source, cfg, init_params(cfg, seed=3), {"step": 1})
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "finalize_run.py"),
             "--checkpoint", source, "--tokenizer", TOKENIZER,
             "--publish", os.path.join(tmp, "last.npz"),
             "--run-config", os.path.join(tmp, "run.json"),
             "--report", os.path.join(tmp, "report.json"), "--skip-eval"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("vocab mismatch", (proc.stdout + proc.stderr))


if __name__ == "__main__":
    unittest.main()
