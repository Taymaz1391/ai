"""مدلِ سرویس‌شده باید بهترین چک‌پوینتِ موجود باشد، نه فایلِ موقتِ حلقهٔ آموزش."""
from __future__ import annotations

import os
import unittest

from web import server


class CheckpointRegistryTest(unittest.TestCase):
    def test_last_npz_is_not_preferred(self):
        names = [os.path.basename(path) for path, _tok in server.CHECKPOINT_CANDIDATES]
        self.assertIn("last.npz", names)
        self.assertNotEqual(names[0], "last.npz",
                            "last.npz خروجیِ موقتِ آموزش است؛ نباید اولویتِ سرویس باشد")

    def test_first_existing_is_the_sft_model(self):
        existing = [path for path, _tok in server.CHECKPOINT_CANDIDATES if os.path.exists(path)]
        self.assertTrue(existing, "هیچ چک‌پوینتی روی دیسک نیست")
        if os.path.exists(os.path.join("checkpoints", "rayan-3-sft.npz")):
            self.assertEqual(os.path.basename(existing[0]), "rayan-3-sft.npz")

    def test_every_candidate_has_a_tokenizer(self):
        for path, tokenizer in server.CHECKPOINT_CANDIDATES:
            self.assertTrue(tokenizer.endswith(".json"))


if __name__ == "__main__":
    unittest.main()
