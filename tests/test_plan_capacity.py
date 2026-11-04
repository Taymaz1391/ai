import json
import subprocess
import sys
import unittest

from scripts.plan_100b import ROOT
from scripts.plan_capacity import resources


class TrillionPlanTests(unittest.TestCase):
    def setUp(self):
        cfg = json.loads((ROOT / 'configs/rayan-1t.json').read_text())
        self.model = cfg['model']

    def test_trillion_is_plan_not_claim(self):
        r = resources(self.model)
        self.assertEqual(r['parameters'], 1_008_418_867_200)
        self.assertEqual(r['status'], 'plan_only_not_trained')
        self.assertEqual(r['target_training_tokens_heuristic'], 20 * r['parameters'])
        self.assertNotIn('hypothetical_compute_scenario', r)

    def test_memory_lower_bounds(self):
        r = resources(self.model)
        scenario = r['hypothetical_memory_scenario']
        self.assertEqual(scenario['bf16_weight_shards_minimum'], 32)
        self.assertEqual(scenario['adam_state_shards_minimum'], 253)

    def test_explicit_compute_assumption(self):
        r = resources(self.model, aggregate_flops_per_second=1e18)
        self.assertAlmostEqual(r['hypothetical_compute_scenario']['idealized_days'],
                               r['training_flops_approx_6ND'] / 1e18 / 86400)

    def test_invalid_resource_inputs(self):
        for key in ('device_memory_gb', 'usable_fraction', 'aggregate_flops_per_second'):
            for value in (0, -1, float('inf'), float('nan'), True):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    resources(self.model, **{key: value})
        with self.assertRaises(ValueError):
            resources(self.model, usable_fraction=1.01)

    def test_cli(self):
        proc = subprocess.run([sys.executable, '-m', 'scripts.plan_capacity'],
                              cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(proc.stdout)['parameters'], 1_008_418_867_200)
        invalid = subprocess.run([sys.executable, '-m', 'scripts.plan_capacity',
                                  '--device-memory-gb', '0'], cwd=ROOT,
                                 capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
