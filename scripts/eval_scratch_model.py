#!/usr/bin/env python3
"""سنجشِ مدلِ صفرآموختهٔ رایان روی دادهٔ کنارگذاشته.

سه عدد می‌دهد تا «بهتر شد» یا «بدتر شد» قابلِ داوری باشد:

    loss / ppl / bits-per-char  روی پنجره‌های کنارگذاشته
    توکن-F1 پاسخِ تولیدشده با پاسخِ مرجع (دستورپذیری، نه حفظ)
    نمونه‌های واقعی برای خواندنِ انسانی

    python scripts/eval_scratch_model.py --checkpoint checkpoints/rayan-3-base.npz \
        --tokenizer tokenizer/rayan_bpe_16k.json \
        --val data/rayan3/val.txt --val-raw data/rayan3/val_raw.txt
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rayan.generate import Engine  # noqa: E402
from rayan.model import forward, load_checkpoint  # noqa: E402
from rayan.tokenizer import BPETokenizer  # noqa: E402


def encode(path: str, tokenizer: BPETokenizer) -> tuple[np.ndarray, float]:
    text = open(path, encoding="utf-8").read()
    ids = np.array(tokenizer.encode(text), dtype=np.int64)
    return ids, len(text) / max(1, len(ids))


def window_loss(params, cfg, data: np.ndarray, block: int, batches: int, batch: int,
                seed: int = 7) -> float:
    rng = np.random.default_rng(seed)
    losses = []
    for _ in range(batches):
        starts = rng.integers(0, max(1, len(data) - block - 2), size=batch)
        x = np.stack([data[i:i + block] for i in starts])
        y = np.stack([data[i + 1:i + 1 + block] for i in starts])
        _logits, loss = forward(params, cfg, x, y)
        losses.append(float(loss))
    return float(np.mean(losses))


def tokens_of(text: str) -> list[str]:
    return re.findall(r"[\w\u200c]+", (text or "").lower())


def f1(pred: str, ref: str) -> float:
    p, r = tokens_of(pred), tokens_of(ref)
    if not p or not r:
        return 0.0
    common = 0
    pool = list(r)
    for word in p:
        if word in pool:
            pool.remove(word)
            common += 1
    if not common:
        return 0.0
    precision, recall = common / len(p), common / len(r)
    return 2 * precision * recall / (precision + recall)


def main() -> None:
    parser = argparse.ArgumentParser(description="سنجشِ مدلِ صفرآموخته")
    parser.add_argument("--checkpoint", default="checkpoints/rayan-2-base.npz")
    parser.add_argument("--tokenizer", default="tokenizer/rayan_bpe_16k.json")
    parser.add_argument("--val", default="data/rayan3/val.txt")
    parser.add_argument("--val-raw", default="data/rayan3/val_raw.txt")
    parser.add_argument("--block", type=int, default=192)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--batches", type=int, default=6)
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--max-new", type=int, default=64)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    tok = BPETokenizer.load(os.path.join(ROOT, args.tokenizer)
                            if not os.path.isabs(args.tokenizer) else args.tokenizer)
    cfg, params, meta = load_checkpoint(os.path.join(ROOT, args.checkpoint)
                                        if not os.path.isabs(args.checkpoint) else args.checkpoint)
    result: dict = {"checkpoint": args.checkpoint, "config": cfg.to_dict(),
                    "params": int(sum(v.size for v in params.values())),
                    "meta_val_loss": meta.get("val_loss")}

    for label, path in (("chat", args.val), ("raw", args.val_raw)):
        if not path or not os.path.exists(os.path.join(ROOT, path)):
            continue
        data, chars_per_token = encode(os.path.join(ROOT, path), tok)
        if len(data) <= args.block + 2:
            continue
        loss = window_loss(params, cfg, data, args.block, args.batches, args.batch)
        result[label] = {
            "tokens": int(len(data)),
            "chars_per_token": round(chars_per_token, 3),
            "loss": round(loss, 4),
            "ppl": round(math.exp(loss), 2),
            "bits_per_char": round(loss / math.log(2) / chars_per_token, 4),
        }

    # دستورپذیری: پاسخ را از خودِ مدل می‌گیریم و با پاسخِ مرجع مقایسه می‌کنیم
    engine = Engine(checkpoint=os.path.join(ROOT, args.checkpoint),
                    tokenizer_path=os.path.join(ROOT, args.tokenizer))
    prompts, refs, answers = [], [], []
    for line in open(os.path.join(ROOT, args.val), encoding="utf-8"):
        line = line.strip()
        if not line.startswith("<|doc|> <|user|>"):
            continue
        try:
            question = line.split("<|user|>", 1)[1].split("<|bot|>", 1)[0].strip()
            reference = line.split("<|bot|>", 1)[1].split("<|nl|>", 1)[0].strip()
        except IndexError:
            continue
        prompts.append(question)
        refs.append(reference)
        if len(prompts) >= args.samples:
            break

    scores = []
    for question, reference in zip(prompts, refs):
        try:
            text, _generation, _prompt = engine.reply(
                question, mode="chat", max_new_tokens=args.max_new,
                temperature=0.7, top_k=40, top_p=0.9)
        except Exception as exc:  # noqa: BLE001 - سنجش نباید بشکند
            text = f"[خطا: {exc}]"
        scores.append(round(f1(text, reference), 3))
        answers.append({"question": question, "reference": reference[:400],
                        "answer": text[:400], "f1": scores[-1]})
    result["instruction"] = {
        "samples": len(scores),
        "mean_f1": round(float(np.mean(scores)), 3) if scores else 0.0,
        "answers": answers,
    }

    text = json.dumps(result, ensure_ascii=False, indent=1)
    print(text)
    if args.out:
        out_path = os.path.join(ROOT, args.out) if not os.path.isabs(args.out) else args.out
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")


if __name__ == "__main__":
    main()
