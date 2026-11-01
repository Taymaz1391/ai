#!/usr/bin/env python3
"""مقایسهٔ منصفانهٔ دو مدل با «بیت بر نویسه» روی یک متن اعتبارسنجی مشترک.

توکنایزر دو مدل متفاوت است، پس مقایسهٔ مستقیم ppl گمراه‌کننده است. معیار درست،
هزینهٔ پیش‌بینی هر نویسه است:

    bits/char = (loss_nats / ln2) / (chars / tokens)

    python scripts/compare_models.py \\
        --old checkpoints/rayan-1-small.npz tokenizer/rayan_bpe.json \\
        --new checkpoints/rayan-2-base.npz tokenizer/rayan_bpe_16k.json \\
        --val data/val.txt --chars 300000

خروجی JSON در ``reports/compare-*.json`` ذخیره می‌شود؛ هیچ عددی دستی وارد نمی‌شود.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rayan.model import forward, load_checkpoint  # noqa: E402
from rayan.tokenizer import BPETokenizer  # noqa: E402


def evaluate(checkpoint: str, tokenizer_path: str, text: str, max_windows: int = 64) -> dict:
    cfg, params, meta = load_checkpoint(checkpoint)
    tok = BPETokenizer.load(tokenizer_path)
    if cfg.vocab_size != tok.vocab_size:
        raise ValueError(f"{checkpoint}: vocab {cfg.vocab_size} != tokenizer {tok.vocab_size}")
    ids = np.asarray(tok.encode(text), dtype=np.int64)
    block = cfg.block_size
    windows = max(1, min(max_windows, len(ids) // (block + 1)))
    losses = []
    started = time.time()
    for i in range(windows):
        start = i * block
        x = ids[start:start + block][None, :]
        y = ids[start + 1:start + 1 + block][None, :]
        if x.shape[1] < block:
            break
        _, loss = forward(params, cfg, x, y)
        losses.append(float(loss))
    mean_nats = float(np.mean(losses)) if losses else float("nan")
    bits_per_token = mean_nats / math.log(2)
    chars_per_token = len(text) / max(1, len(ids))
    return {
        "checkpoint": os.path.abspath(checkpoint),
        "tokenizer": os.path.abspath(tokenizer_path),
        "params": int(sum(v.size for v in params.values())),
        "cfg": cfg.to_dict() if hasattr(cfg, "to_dict") else str(cfg),
        "checkpoint_step": (meta or {}).get("step"),
        "windows": len(losses),
        "chars": len(text),
        "tokens": int(len(ids)),
        "chars_per_token": round(chars_per_token, 3),
        "val_loss_nats": round(mean_nats, 4),
        "bits_per_token": round(bits_per_token, 4),
        "bits_per_char": round(bits_per_token / chars_per_token, 4),
        "ppl": round(math.exp(mean_nats), 2),
        "seconds": round(time.time() - started, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", nargs=2, metavar=("CHECKPOINT", "TOKENIZER"), required=True)
    parser.add_argument("--new", nargs=2, metavar=("CHECKPOINT", "TOKENIZER"), required=True)
    parser.add_argument("--val", default=os.path.join(ROOT, "data", "val.txt"))
    parser.add_argument("--chars", type=int, default=300_000)
    parser.add_argument("--windows", type=int, default=64)
    parser.add_argument("--out-dir", default=os.path.join(ROOT, "reports"))
    args = parser.parse_args()

    text = open(args.val, encoding="utf-8").read(args.chars)
    result = {"val_chars": len(text), "val_file": os.path.abspath(args.val)}
    result["old"] = evaluate(args.old[0], args.old[1], text, args.windows)
    result["new"] = evaluate(args.new[0], args.new[1], text, args.windows)
    delta = result["old"]["bits_per_char"] - result["new"]["bits_per_char"]
    result["delta_bits_per_char"] = round(delta, 4)
    result["better"] = "new" if delta > 0 else "old"

    os.makedirs(args.out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(args.out_dir, f"compare-{stamp}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    print(f"\n[=] saved {path}", flush=True)
    print(f"[=] بهتر: {result['better']} | اختلاف {delta:+.4f} بیت بر نویسه", flush=True)


if __name__ == "__main__":
    main()
