"""ساختن دادهٔ ترجیح: چند پاسخ از مدل نمونه می‌گیریم و داور خودکار رتبه می‌دهد.

    python scripts/make_preferences.py --checkpoint checkpoints/rayan-1-small.npz \\
        --out data/preferences.jsonl --samples 3 --limit 160

خروجی هر خط:
    {"user": …, "chosen": …, "rejected": …, "reason": …, "gap": …,
     "scores": {"chosen": {…}, "rejected": {…}}}

هیچ برچسب انسانی در کار نیست؛ داور همان معیارهای عینیِ `rayan/rubric.py` است.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rayan import rubric  # noqa: E402
from rayan.generate import Engine  # noqa: E402

SEED_FILES = ("data/chat_seed.jsonl", "data/knowledge.jsonl")


def load_prompts(limit: int = 0) -> list[dict]:
    """پرسش‌ها با پاسخ مرجع (اگر باشد) و واژه‌های انتظاری."""
    rows: list[dict] = []
    seen: set[str] = set()
    for path in SEED_FILES:
        full = os.path.join(ROOT, path)
        if not os.path.exists(full):
            continue
        with open(full, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                user = (row.get("user") or row.get("q") or "").strip()
                if not user or user in seen:
                    continue
                seen.add(user)
                rows.append({
                    "user": user,
                    "reference": (row.get("assistant") or row.get("a") or "").strip(),
                    "expected": [*(row.get("expected") or []), *(row.get("keys") or [])],
                })
    return rows[:limit] if limit else rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="checkpoints/rayan-1-small.npz")
    parser.add_argument("--tokenizer", default="")
    parser.add_argument("--out", default="data/preferences.jsonl")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-gap", type=float, default=0.25)
    parser.add_argument("--max-new-tokens", type=int, default=70)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()

    tokenizer = args.tokenizer or ("tokenizer/rayan_bpe_16k.json"
                                   if "16k" in args.checkpoint else "tokenizer/rayan_bpe.json")
    engine = Engine(os.path.join(ROOT, args.checkpoint), os.path.join(ROOT, tokenizer))
    prompts = load_prompts(args.limit)
    print(f"[prefs] {len(prompts)} پرسش · {args.samples} نمونه برای هرکدام", flush=True)

    temperatures = [0.65, 0.8, 0.95, 1.1, 1.25]
    out_path = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    accepted = rejected_pairs = 0
    started = time.time()
    with open(out_path, "w", encoding="utf-8") as fh:
        for index, prompt in enumerate(prompts):
            prompt_ids, _text = engine.build_prompt(prompt["user"], "chat")
            candidates: list[dict] = []
            for k in range(max(2, args.samples)):
                temperature = temperatures[k % len(temperatures)]
                generation = engine.generate(
                    prompt_ids, mode="chat", temperature=temperature,
                    max_new_tokens=args.max_new_tokens,
                    seed=args.seed + index * 17 + k * 101,
                )
                text = engine.tokenizer.decode(generation.tokens, skip_specials=True).strip()
                scored = rubric.score(text, reference=prompt["reference"],
                                      expected=prompt["expected"],
                                      finish=generation.finish_reason)
                candidates.append({"text": text, "score": scored})
            candidates.sort(key=lambda item: item["score"]["total"], reverse=True)
            best, worst = candidates[0], candidates[-1]
            if not rubric.prefer(best["score"], worst["score"], args.min_gap) or not best["text"]:
                rejected_pairs += 1
                continue
            row = {
                "user": prompt["user"],
                "chosen": best["text"],
                "rejected": worst["text"],
                "reason": rubric.reason(best["score"], worst["score"]),
                "gap": round(best["score"]["total"] - worst["score"]["total"], 3),
                "scores": {"chosen": best["score"], "rejected": worst["score"]},
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            accepted += 1
            if (index + 1) % 20 == 0:
                print(f"  {index + 1}/{len(prompts)} · زوج پذیرفته‌شده {accepted} · "
                      f"{time.time() - started:.0f}s", flush=True)

    summary = {"prompts": len(prompts), "pairs": accepted, "skipped": rejected_pairs,
               "seconds": round(time.time() - started, 1), "out": args.out,
               "checkpoint": args.checkpoint}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
