"""آموزش توکنایزر BPE پارسیا روی پیکرهٔ فارسی و ارزیابی آن."""
from __future__ import annotations

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsia.tokenizer import BPETokenizer  # noqa: E402


def sample_text(path: str, chars: int, seed: int = 11) -> str:
    text = open(path, encoding="utf-8").read()
    rng = random.Random(seed)
    window = 1600
    windows = max(1, chars // window)
    pieces = []
    for _ in range(windows):
        start = rng.randrange(0, max(1, len(text) - window))
        pieces.append(text[start:start + window])
    return "\n".join(pieces)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default="data/train.txt")
    parser.add_argument("--val", default="data/val.txt")
    parser.add_argument("--out", default="tokenizer/parsia_bpe.json")
    parser.add_argument("--vocab-size", type=int, default=10_000)
    parser.add_argument("--sample-chars", type=int, default=9_000_000)
    args = parser.parse_args()

    sample = sample_text(args.train, args.sample_chars)
    print(f"BPE training sample: {len(sample)/1e6:.1f} MB")
    t0 = time.time()
    tok = BPETokenizer.train(sample, vocab_size=args.vocab_size)
    print(f"trained in {time.time() - t0:.1f}s -> {tok.stats()}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tok.save(args.out)
    print("saved", args.out)

    # آزمون رفت‌وبرگشت و سرعت
    val = open(args.val, encoding="utf-8").read()[:400_000]
    t0 = time.time()
    ids = tok.encode(val)
    elapsed = time.time() - t0
    back = tok.decode(ids)
    print(f"encoded {len(val):,} chars -> {len(ids):,} tokens in {elapsed:.1f}s "
          f"({len(val)/elapsed/1000:.0f} kchar/s, {len(val)/max(1,len(ids)):.2f} chars/token)")
    print("round-trip OK:", back[:120] == val[:120])
    print("sample decode:", back[:160].replace("\n", " ⏎ "))
    print("token sample:", [tok.vocab[i] for i in ids[:30]])


if __name__ == "__main__":
    main()
