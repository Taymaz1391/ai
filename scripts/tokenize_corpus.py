#!/usr/bin/env python3
"""تبدیل پیکرهٔ متنی به فایل شناسه‌های باینری (uint16) برای آموزش کم‌حافظه.

    python scripts/tokenize_corpus.py --tokenizer tokenizer/rayan_bpe_16k.json \\
        --input data/train.txt --out data/train.u16 [--val data/val.txt --val-out data/val.u16]

متن تکه‌تکه (روی مرز خط) خوانده و رمزگذاری می‌شود، پس حافظه مستقل از اندازهٔ
پیکره ثابت می‌ماند. آموزش هم با ``np.memmap`` همین فایل را می‌خواند و کل پیکره
را در RAM نگه نمی‌دارد.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rayan.tokenizer import BPETokenizer  # noqa: E402


def split_point(block: str) -> int:
    """نزدیک‌ترین مرز قطعهٔ توکن‌سازی در انتهای بلوک (شکستن خط، وگرنه فاصله)."""
    for sep in ("\n", " "):
        pos = block.rfind(sep)
        if pos != -1:
            return pos + 1
    return -1


def encode_stream(path: str, out_path: str, tokenizer: BPETokenizer,
                  chunk_chars: int = 1_000_000, dtype=np.uint16) -> dict:
    """رمزگذاری جریانی با مرزهایی که با مرز قطعهٔ BPE هم‌ترازند.

    هر بار فقط تا آخرین شکستن خط (یا در نبودش، آخرین فاصله) مصرف می‌شود و باقی
    برای دور بعد می‌ماند. چون این دو نویسه مرز قطعه در پیش‌توکن‌سازی‌اند، خروجی
    بیت‌به‌بیت با رمزگذاری یک‌جای کل متن یکی است (در ``tests/test_tokenize_stream.py``
    آزموده می‌شود). حافظه مستقل از اندازهٔ پیکره ثابت می‌ماند.
    """
    started = time.time()
    chars = 0
    tokens = 0
    pending = ""
    with open(path, encoding="utf-8") as src, open(out_path, "wb") as dst:
        while True:
            block = pending + src.read(chunk_chars)
            if not block:
                break
            cut = split_point(block)
            if cut == -1 or cut >= len(block):
                ready, pending = block, ""
            else:
                ready, pending = block[:cut], block[cut:]
            ids = tokenizer.encode(ready)
            if ids:
                dst.write(np.asarray(ids, dtype=dtype).tobytes())
                tokens += len(ids)
            chars += len(ready)
        if pending:  # pragma: no cover - با منطق بالا هرگز رخ نمی‌دهد
            ids = tokenizer.encode(pending)
            if ids:
                dst.write(np.asarray(ids, dtype=dtype).tobytes())
                tokens += len(ids)
            chars += len(pending)
    elapsed = max(0.001, time.time() - started)
    return {
        "input": os.path.abspath(path), "output": os.path.abspath(out_path),
        "chars": chars, "tokens": tokens, "bytes": os.path.getsize(out_path),
        "chars_per_token": round(chars / max(1, tokens), 3),
        "kchar_per_s": round(chars / elapsed / 1000),
        "seconds": round(elapsed, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer", default="tokenizer/rayan_bpe_16k.json")
    parser.add_argument("--input", default="data/train.txt")
    parser.add_argument("--out", default="data/train.u16")
    parser.add_argument("--val", default="")
    parser.add_argument("--val-out", default="data/val.u16")
    args = parser.parse_args()

    tok = BPETokenizer.load(args.tokenizer)
    print(f"tokenizer: {tok.stats()}", flush=True)
    info = {"tokenizer": args.tokenizer, "tokenizer_stats": tok.stats()}
    info["train"] = encode_stream(args.input, args.out, tok)
    print(json.dumps(info["train"], ensure_ascii=False, indent=2), flush=True)
    if args.val:
        info["val"] = encode_stream(args.val, args.val_out, tok)
        print(json.dumps(info["val"], ensure_ascii=False, indent=2), flush=True)
    with open(os.path.join(ROOT, "data", "tokenized_stats.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
