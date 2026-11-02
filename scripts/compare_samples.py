#!/usr/bin/env python3
"""نمونه‌های هم‌شرط دو مدل، برای مقایسهٔ کیفی و عددی خروجی.

    python scripts/compare_samples.py \\
        --old checkpoints/rayan-1-small.npz tokenizer/rayan_bpe.json \\
        --new checkpoints/last.npz tokenizer/rayan_bpe_16k.json \\
        --out reports/compare-samples.md

برای هر پرسش، هر دو مدل با همان بذر و همان تنظیمات نمونه‌گیری تولید می‌کنند.
هیچ متنی ویرایش دستی نمی‌شود و هیچ عددی جز آنچه اندازه‌گیری شده گزارش نمی‌شود.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rayan.generate import Engine, polish  # noqa: E402

PROMPTS = [
    ("chat", "سلام! خودت را معرفی کن"),
    ("chat", "مدل زبانی چیست؟"),
    ("chat", "دربارهٔ ایران برایم بگو"),
    ("chat", "یک شعر بگو"),
    ("continue", "در دل کویر، شب‌ها آسمان پر از ستاره است و"),
]

PERSIAN = re.compile(r"[\u0600-\u06FF]")


def stats(text: str) -> dict:
    words = text.split()
    uniq = len(set(words))
    trigrams = {}
    for i in range(len(words) - 2):
        gram = " ".join(words[i:i + 3])
        trigrams[gram] = trigrams.get(gram, 0) + 1
    # تکرار سه‌واژه‌ای: هرچه کمتر، خروجی متنوع‌تر
    repeat = 1.0 - (len(trigrams) / max(1, sum(trigrams.values()))) if trigrams else 0.0
    persian = len(PERSIAN.findall(text)) / max(1, len(text))
    return {
        "chars": len(text),
        "words": len(words),
        "unique_ratio": round(uniq / max(1, len(words)), 3),
        "repeat_ratio": round(max(0.0, repeat), 3),
        "persian_ratio": round(persian, 3),
    }


def run_model(checkpoint: str, tokenizer_path: str, seeds: list[int]) -> dict:
    engine = Engine(checkpoint, tokenizer_path)
    rows = []
    for mode, prompt in PROMPTS:
        for seed in seeds:
            prompt_ids, _ = engine.build_prompt(prompt, mode)
            generation = engine.generate(prompt_ids, mode=mode, seed=seed)
            text = polish(engine.tokenizer.decode(generation.tokens), mode).strip()
            rows.append({
                "mode": mode,
                "prompt": prompt,
                "seed": seed,
                "text": text,
                "tokens": len(generation.tokens),
                "seconds": round(generation.seconds, 2),
                "confidence": round(generation.confidence, 3),
                **stats(text),
            })
    return {
        "checkpoint": os.path.abspath(checkpoint),
        "tokenizer": os.path.abspath(tokenizer_path),
        "params": int(sum(p.size for p in engine.params.values())),
        "rows": rows,
    }


def markdown(old: dict, new: dict) -> str:
    def mean(rows, key):
        return sum(r[key] for r in rows) / max(1, len(rows))

    lines = [
        "# مقایسهٔ نمونه‌های رایان ۱ و رایان ۲",
        "",
        f"- نسخهٔ قبلی: `{os.path.basename(old['checkpoint'])}` ({old['params']:,} پارامتر)",
        f"- نسخهٔ جدید: `{os.path.basename(new['checkpoint'])}` ({new['params']:,} پارامتر)",
        "- هر دو با همان پرسش، همان بذر و همان تنظیمات نمونه‌گیری اجرا شده‌اند.",
        "",
        "| سنجهٔ خودکار | رایان ۱ | رایان ۲ |",
        "|---|---|---|",
        f"| نسبت واژه‌های یکتا | {mean(old['rows'], 'unique_ratio'):.3f} | {mean(new['rows'], 'unique_ratio'):.3f} |",
        f"| نسبت تکرار | {mean(old['rows'], 'repeat_ratio'):.3f} | {mean(new['rows'], 'repeat_ratio'):.3f} |",
        f"| نسبت حروف فارسی | {mean(old['rows'], 'persian_ratio'):.3f} | {mean(new['rows'], 'persian_ratio'):.3f} |",
        f"| طول پاسخ (نویسه) | {mean(old['rows'], 'chars'):.0f} | {mean(new['rows'], 'chars'):.0f} |",
        f"| اطمینان میانگین | {mean(old['rows'], 'confidence'):.3f} | {mean(new['rows'], 'confidence'):.3f} |",
        "",
        "> اطمینان، میانگین احتمال توکن‌های تولیدشده است؛ بالاتر بودن آن به‌تنهایی «بهتر» نیست.",
        "",
    ]
    for index, prompt_row in enumerate(old["rows"]):
        new_row = new["rows"][index]
        lines += [
            f"## {prompt_row['prompt']} (بذر {prompt_row['seed']})",
            "",
            f"**رایان ۱:** {prompt_row['text'] or '—'}",
            "",
            f"**رایان ۲:** {new_row['text'] or '—'}",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", nargs=2, metavar=("CHECKPOINT", "TOKENIZER"), required=True)
    parser.add_argument("--new", nargs=2, metavar=("CHECKPOINT", "TOKENIZER"), required=True)
    parser.add_argument("--seeds", default="11,29")
    parser.add_argument("--out", default=os.path.join(ROOT, "reports", "compare-samples.md"))
    parser.add_argument("--json-out", default=os.path.join(ROOT, "reports", "compare-samples.json"))
    args = parser.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    started = time.time()
    print("generating with the previous model ...", flush=True)
    old = run_model(args.old[0], args.old[1], seeds)
    print("generating with the new model ...", flush=True)
    new = run_model(args.new[0], args.new[1], seeds)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(markdown(old, new))
    with open(args.json_out, "w", encoding="utf-8") as fh:
        json.dump({"old": old, "new": new, "seconds": round(time.time() - started, 1)}, fh,
                  ensure_ascii=False, indent=2)
    print(f"[=] wrote {args.out} and {args.json_out} in {time.time() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
