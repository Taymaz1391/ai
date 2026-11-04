"""Capacity planning must not allocate the proposed model."""
import json
import unittest
from pathlib import Path

from scripts.plan_100b import estimate


class CapacityPlanTests(unittest.TestCase):
    def test_matches_current_model_count(self):
        self.assertEqual(estimate(dict(vocab_size=16000, block_size=256,
                                      n_layer=6, n_head=6, n_embd=384))['parameters'],
                         16889856)

    def test_target(self):
        cfg = json.loads((Path(__file__).resolve().parents[1] /
                          'configs/rayan-100b.json').read_text())
        result = estimate(cfg['model'])
        self.assertGreaterEqual(result['parameters'], 100_000_000_000)
        self.assertLess(result['parameters'], 102_000_000_000)
        self.assertEqual(result['status'], 'plan_only_not_trained')
        self.assertEqual(result['bf16_weights_bytes'], result['parameters'] * 2)

    def test_invalid(self):
        for width in (-1, True, 11):
            with self.assertRaises(ValueError):
                estimate(dict(vocab_size=100, block_size=10,
                              n_layer=1, n_head=2, n_embd=width))
