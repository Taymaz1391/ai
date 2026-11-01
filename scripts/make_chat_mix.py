#!/usr/bin/env python3
"""ساخت فایل ترکیبی آموزش: متن عمومی + سهم مشخصی دادهٔ گفتگویی.

مدل پایه قالب گفتگو را از پیکرهٔ عمومی یاد نمی‌گیرد؛ این اسکریپت بدون تکرار
بی‌رویه و با نسبتِ قابل‌تنظیم، گفتگوهای آغازین را کنار متن عمومی می‌گذارد.

    python scripts/make_chat_mix.py --train-ids data/train.u16 --out data/mix.u16 \
        --seed-jsonl data/chat_seed.jsonl --tokenizer tokenizer/rayan_bpe_16k.json \
        --general-tokens 1290000 --chat-tokens 140000
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rayan.tokenizer import BPETokenizer  # noqa: E402


def chat_text(path: str) -> str:
    """گفتگوها در قالب <|doc|> <|user|> … <|bot|> … با شکستن خط."""
    parts: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            user = (row.get("user") or "").strip()
            assistant = (row.get("assistant") or "").strip()
            if user and assistant:
                parts.append(f"<|doc|>\n<|user|> {user} <|bot|> {assistant}\n")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-ids", default="data/train.u16")
    parser.add_argument("--out", default="data/mix.u16")
    parser.add_argument("--seed-jsonl", default="data/chat_seed.jsonl")
    parser.add_argument("--tokenizer", default="tokenizer/rayan_bpe_16k.json")
    parser.add_argument("--general-tokens", type=int, default=1_290_000)
    parser.add_argument("--chat-tokens", type=int, default=140_000)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()

    tok = BPETokenizer.load(args.tokenizer)
    text = chat_text(args.seed_jsonl)
    if not text:
        raise SystemExit("no chat seeds found")
    chat_ids = np.asarray(tok.encode(text), dtype=np.uint16)
    reps = max(1, args.chat_tokens // max(1, len(chat_ids)))
    chat_block = np.tile(chat_ids, reps)

    base = np.memmap(args.train_ids, dtype=np.uint16, mode="r")
    general_tokens = min(args.general_tokens, max(1, len(base) - 10))
    rng = np.random.default_rng(args.seed)
    start = int(rng.integers(0, max(1, len(base) - general_tokens)))
    general = np.asarray(base[start:start + general_tokens], dtype=np.uint16)

    mix = np.concatenate([general, chat_block])
    with open(args.out, "wb") as fh:
        fh.write(mix.tobytes())
    share = len(chat_block) / max(1, len(mix)) * 100
    print(json.dumps({
        "out": os.path.abspath(args.out),
        "general_tokens": int(len(general)),
        "chat_tokens": int(len(chat_block)),
        "chat_repeats": reps,
        "chat_share_percent": round(share, 2),
        "total_tokens": int(len(mix)),
        "bytes": os.path.getsize(args.out),
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
