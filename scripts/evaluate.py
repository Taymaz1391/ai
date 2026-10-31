"""ارزیابی صادقانهٔ پارسیا روی دادهٔ نگه‌داشته‌شده + نمونه‌سازی.

    python scripts/evaluate.py --checkpoint checkpoints/parsia-1-small.npz

خروجی: reports/evaluation.json و reports/samples.md
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
sys.path.insert(0, ROOT)

from parsia.generate import Engine, polish  # noqa: E402
from parsia.model import forward, load_checkpoint  # noqa: E402
from parsia.tokenizer import BPETokenizer  # noqa: E402

PROMPTS = [
    ("chat", "سلام! خودت را معرفی کن"),
    ("chat", "یک شعر بگو"),
    ("chat", "مدل زبانی چیست؟"),
    ("chat", "دربارهٔ ایران برایم بگو"),
    ("continue", "در دل کویر، شب‌ها آسمان پر از ستاره است و"),
    ("poetry", ""),
]


def evaluate_loss(cfg, params, data: np.ndarray, block: int, batch_size: int = 8):
    """میانگین وزنی خطا، perplexity، بیت بر نویسه و دقت top-1/top-5 روی کل اعتبارسنجی."""
    n_windows = max(1, (len(data) - 1) // block)
    total_loss, total_tokens = 0.0, 0
    top1, top5 = 0, 0
    started = time.time()
    for start in range(0, n_windows, batch_size):
        windows = []
        for wi in range(start, min(start + batch_size, n_windows)):
            chunk = data[wi * block:(wi + 1) * block + 1]
            if len(chunk) < 2:
                continue
            windows.append(chunk)
        if not windows:
            continue
        block_len = min(len(w) for w in windows)
        x = np.stack([w[:block_len - 1] for w in windows]).astype(np.int64)
        y = np.stack([w[1:block_len] for w in windows]).astype(np.int64)
        logits, loss = forward(params, cfg, x, y)
        n = y.size
        total_loss += float(loss) * n
        total_tokens += n
        preds5 = np.argpartition(-logits, 5, axis=-1)[..., :5]
        top1 += int((logits.argmax(-1) == y).sum())
        top5 += int((preds5 == y[..., None]).any(-1).sum())
    seconds = time.time() - started
    mean_loss = total_loss / max(1, total_tokens)
    return {
        "val_loss": round(mean_loss, 4),
        "ppl": round(math.exp(mean_loss), 2),
        "tokens_evaluated": total_tokens,
        "top1_accuracy": round(top1 / max(1, total_tokens), 4),
        "top5_accuracy": round(top5 / max(1, total_tokens), 4),
        "eval_seconds": round(seconds, 2),
        "tokens_per_second": round(total_tokens / max(1e-6, seconds), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="checkpoints/parsia-1-small.npz")
    parser.add_argument("--tokenizer", default="tokenizer/parsia_bpe.json")
    parser.add_argument("--val", default="data/val.txt")
    parser.add_argument("--out", default="reports")
    parser.add_argument("--seeds", default="11,23,37")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    tokenizer = BPETokenizer.load(args.tokenizer)
    cfg, params, meta = load_checkpoint(args.checkpoint)
    report = {
        "checkpoint": args.checkpoint,
        "meta": meta,
        "config": cfg.to_dict(),
        "params": int(sum(p.size for p in params.values())),
        "tokenizer": tokenizer.stats(),
    }
    print(f"checkpoint step={meta.get('step')} params={report['params']:,}")

    if os.path.exists(args.val):
        text = open(args.val, encoding="utf-8").read()
        t0 = time.time()
        ids = np.asarray(tokenizer.encode(text), dtype=np.uint16)
        print(f"encoded validation in {time.time()-t0:.1f}s: {len(ids):,} tokens")
        metrics = evaluate_loss(cfg, params, ids, cfg.block_size)
        chars_per_token = len(text) / max(1, len(ids))
        metrics["bits_per_char"] = round(metrics["val_loss"] / math.log(2) / chars_per_token, 4)
        metrics["chars_per_token"] = round(chars_per_token, 2)
        report["evaluation"] = metrics
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(f"[!] {args.val} پیدا نشد؛ ارزیابی خطا رد شد.")

    engine = Engine(args.checkpoint, args.tokenizer)
    samples = []
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    for mode, prompt in PROMPTS:
        for seed in seeds:
            prompt_ids, _ = engine.build_prompt(prompt or "یک شعر بگو", mode)
            generation = engine.generate(prompt_ids, mode=mode, seed=seed)
            text = polish(tokenizer.decode(generation.tokens), mode)
            samples.append({
                "mode": mode,
                "prompt": prompt or "یک شعر بگو",
                "seed": seed,
                "text": text,
                "tokens": len(generation.tokens),
                "seconds": round(generation.seconds, 2),
                "tok_s": round(generation.tokens_per_second, 1),
                "confidence": round(generation.confidence, 3),
            })
            print(f"[{mode}] {prompt or 'شعر'} (seed {seed}) -> {text[:80]!r}")
    report["samples"] = samples
    report["generation"] = {
        "mean_tok_s": round(float(np.mean([s["tok_s"] for s in samples])), 1),
        "mean_confidence": round(float(np.mean([s["confidence"] for s in samples])), 3),
    }

    with open(os.path.join(args.out, "evaluation.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    lines = ["# نمونه‌های تولید پارسیا", "", f"checkpoint: `{args.checkpoint}` · step {meta.get('step')}", ""]
    if "evaluation" in report:
        ev = report["evaluation"]
        lines += [
            "| سنجه | مقدار |", "|---|---|",
            f"| خطای اعتبارسنجی | {ev['val_loss']} |",
            f"| Perplexity | {ev['ppl']} |",
            f"| بیت بر نویسه | {ev['bits_per_char']} |",
            f"| دقت top-1 | {ev['top1_accuracy']*100:.1f}٪ |",
            f"| دقت top-5 | {ev['top5_accuracy']*100:.1f}٪ |",
            "", "---", "",
        ]
    for sample in samples:
        lines += [
            f"### {sample['mode']} · بذر {sample['seed']}",
            f"**ورودی:** {sample['prompt']}",
            "",
            "```text",
            sample["text"],
            "```",
            f"_{sample['tokens']} توکن · {sample['tok_s']} توکن/ث · اطمینان {sample['confidence']}_",
            "",
        ]
    with open(os.path.join(args.out, "samples.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {args.out}/evaluation.json and {args.out}/samples.md")


if __name__ == "__main__":
    main()
