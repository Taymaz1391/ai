"""آزمون‌های ریاضی مدل: گرادیان، حافظهٔ KV و نمونه‌گیری."""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rayan.model import (
    GPTConfig, InferenceModel, backward, forward, init_params, sample_from_logits,
)


class ModelMathTest(unittest.TestCase):
    def setUp(self):
        self.cfg = GPTConfig(vocab_size=48, block_size=8, n_layer=2, n_head=2, n_embd=16)
        self.params = init_params(self.cfg, seed=3, dtype=np.float64)
        rng = np.random.default_rng(7)
        self.x = rng.integers(0, self.cfg.vocab_size, (2, 8))
        self.y = rng.integers(0, self.cfg.vocab_size, (2, 8))

    def test_gradient_matches_numeric(self):
        _, _, cache = forward(self.params, self.cfg, self.x, self.y, keep_cache=True)
        grads = backward(self.params, self.cfg, cache)
        idx = (3, 5)
        eps = 1e-5
        key = "h1.mlp1_w"
        original = self.params[key][idx]
        self.params[key][idx] = original + eps
        _, plus = forward(self.params, self.cfg, self.x, self.y)
        self.params[key][idx] = original - eps
        _, minus = forward(self.params, self.cfg, self.x, self.y)
        self.params[key][idx] = original
        numeric = (plus - minus) / (2 * eps)
        analytic = float(grads[key][idx])
        self.assertLess(abs(numeric - analytic), 1e-5)

    def test_kv_cache_matches_full_forward(self):
        cfg = GPTConfig(vocab_size=64, block_size=16, n_layer=2, n_head=2, n_embd=16)
        params = init_params(cfg, seed=5)
        model = InferenceModel(cfg, params)
        ids = [3, 9, 11, 2, 7]
        full, _ = forward(params, cfg, np.array([ids]))
        cached, kv = model.logits_for_prompt(ids)
        self.assertLess(np.abs(full[0, -1] - cached).max(), 2e-4)
        nxt = 13
        full2, _ = forward(params, cfg, np.array([ids + [nxt]]))
        cached2, _ = model.next_logits(nxt, len(ids), kv)
        self.assertLess(np.abs(full2[0, -1] - cached2).max(), 2e-4)

    def test_sampler_is_valid_and_deterministic(self):
        logits = np.linspace(-2, 2, 100)
        a = sample_from_logits(logits, np.random.default_rng(1), temperature=0.8, top_k=20, top_p=0.9)
        b = sample_from_logits(logits, np.random.default_rng(1), temperature=0.8, top_k=20, top_p=0.9)
        self.assertEqual(a, b)
        token, logprob, entropy = a
        self.assertGreaterEqual(token, 0)
        self.assertLess(token, 100)
        self.assertLessEqual(logprob, 0.0)
        self.assertGreaterEqual(entropy, 0.0)

    def test_param_count(self):
        params = init_params(self.cfg, seed=1)
        self.assertEqual(sum(p.size for p in params.values()),
                         self.cfg.vocab_size * self.cfg.n_embd
                         + self.cfg.block_size * self.cfg.n_embd
                         + 2 * self.cfg.n_embd
                         + self.cfg.n_layer * (12 * self.cfg.n_embd ** 2 + 13 * self.cfg.n_embd))


if __name__ == "__main__":
    unittest.main()
