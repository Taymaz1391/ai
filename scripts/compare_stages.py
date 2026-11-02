#!/usr/bin/env python3
"""سنجش مستقل مرحله‌های هم‌ترازسازی و انتخاب مدلِ منتشرشده.

سه عکسِ `checkpoints/stages/{base,sft,dpo}.npz` (که `scripts/train_align.py`
می‌سازد) روی یک مجموعهٔ پرسش دانشی که در هیچ‌کدام از مراحل دیده نشده ارزیابی
می‌شوند. معیارها:

* **برخورد کلیدی** — آیا پاسخ واژهٔ انتظاری پرسش را دارد؟ (تنها معیار مستقل از داور)
* **داور خودکار** — همان امتیازدهی `rayan/rubric.py`
* **آنتروپی گفتگو** — سرگشتگی روی پرسش‌های آزمون

قاعدهٔ انتخاب، از پیش تعیین‌شده و بدون دست‌کاری:

1. برخورد کلیدی بیشتر برنده است.
2. اگر برابر بود، اختلاف داور با بوت‌استرپ زوجی سنجیده می‌شود؛ فقط اگر احتمال
   برتری ≥ ۰٫۹ باشد آن مرحله برنده است.
3. در غیر این صورت دو مرحله از نظر کیفیت تولید قابل‌تفکیک نیستند و مرحلهٔ با
   سرگشتگی کمتر (مدل زبانی‌تر) انتخاب می‌شود.

خروجی: `checkpoints/last.npz` (مدل منتشرشده) و `reports/stages.json`.

    python scripts/compare_stages.py
    python scripts/compare_stages.py --stages checkpoints/stages --out checkpoints/last.npz
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from rayan.model import load_checkpoint  # noqa: E402
from rayan.tokenizer import BPETokenizer  # noqa: E402
from train_align import chat_perplexity, generation_scores, split_prompts  # noqa: E402

STAGES = ("base", "sft", "dpo")
STAGE_LABELS = {"base": "پیش‌آموزش", "sft": "تنظیم دستورمحور (SFT)",
                "dpo": "بهینه‌سازی ترجیح (DPO)"}
TOKENIZER_BY_VOCAB = {16000: "tokenizer/rayan_bpe_16k.json",
                      10000: "tokenizer/rayan_bpe.json"}


def knowledge_prompts() -> list[dict]:
    """پرسش‌های دانشی سنجش، بدون هیچ شاهدی از پیکره (تولید خالص مدل)."""
    from eval_qa import CASES

    return [{"user": question, "reference": "", "expected": expected}
            for question, expected in CASES]


def hit_flags(answers: list[str], prompts: list[dict]) -> list[int]:
    flags = []
    for answer, prompt in zip(answers, prompts):
        folded = (answer or "").replace("ي", "ی").replace("ك", "ک")
        flags.append(int(any(word in folded for word in prompt["expected"])))
    return flags


def hit_rate(answers: list[str], prompts: list[dict]) -> float:
    flags = hit_flags(answers, prompts)
    return sum(flags) / max(1, len(flags))


def bootstrap_probability(better: list[float], worse: list[float],
                          rounds: int = 2000, seed: int = 3) -> float:
    """احتمال این‌که میانگین اختلاف زوجی مثبت باشد (بوت‌استرپ)."""
    diffs = np.asarray(better, dtype=np.float64) - np.asarray(worse, dtype=np.float64)
    if diffs.size == 0:
        return 0.0
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, diffs.size, size=(rounds, diffs.size))
    return float(np.mean(diffs[picks].mean(axis=1) > 0))


def evaluate_stage(path: str, prompts: list[dict], seeds: list[dict]) -> dict:
    cfg, params, meta = load_checkpoint(path)
    tokenizer_path = os.path.join(ROOT, TOKENIZER_BY_VOCAB[cfg.vocab_size])
    tokenizer = BPETokenizer.load(tokenizer_path)
    started = time.time()
    result = generation_scores(params, cfg, tokenizer, prompts, max_new_tokens=80,
                               samples_n=3, keep_all=True)
    answers = result.pop("answers")
    return {
        "checkpoint": os.path.relpath(path, ROOT),
        "params": int(sum(v.size for v in params.values())),
        "chat_ppl": round(chat_perplexity(params, cfg, tokenizer, seeds), 2),
        "rubric_mean": round(result["rubric_mean"], 4),
        "rubric_totals": [round(v, 4) for v in result["totals"]],
        "hit_rate": round(hit_rate(answers, prompts), 3),
        "hit_flags": hit_flags(answers, prompts),
        "empty_rate": round(result["empty_rate"], 3),
        "repetition_mean": round(result["repetition_mean"], 3),
        "length_mean": round(result["length_mean"], 1),
        "samples": [{"user": p["user"], "answer": a} for p, a in zip(prompts, answers)][:6],
        "seconds": round(time.time() - started, 1),
        "meta": {k: meta.get(k) for k in ("stage", "step", "tokenizer", "chat_ppl")},
    }


def choose(results: dict[str, dict], threshold: float = 0.9) -> tuple[str, dict]:
    """اعمال قاعدهٔ انتخاب؛ خروجی: نام مرحلهٔ برنده و توضیح تصمیم.

    هر مقایسه‌ای که با بوت‌استرپ زوجی به آستانهٔ اطمینان نرسد، «تساوی» شمرده
    می‌شود؛ در آن حالت مرحله‌ای که احتمال بالاتری به پاسخ‌های واقعی گفتگو
    می‌دهد (سرگشتگی کمتر روی دادهٔ کنارگذاشته) منتشر می‌شود.
    """
    order = sorted(results, key=lambda name: (-results[name]["hit_rate"],
                                              -results[name]["rubric_mean"],
                                              results[name]["chat_ppl"]))
    best, second = order[0], order[1]
    hit_probability = bootstrap_probability([float(v) for v in results[best]["hit_flags"]],
                                            [float(v) for v in results[second]["hit_flags"]])
    rubric_probability = bootstrap_probability(results[best]["rubric_totals"],
                                               results[second]["rubric_totals"])
    stats = {"hit_probability": round(hit_probability, 3),
             "rubric_probability": round(rubric_probability, 3),
             "gap_hits": results[best]["hit_rate"] - results[second]["hit_rate"],
             "gap_rubric": round(results[best]["rubric_mean"] - results[second]["rubric_mean"], 4)}

    if hit_probability >= threshold:
        return best, {"rule": "برخورد کلیدی با تفکیک آماری", "winner": best, **stats,
                      "detail": (f"{best}: برخورد {results[best]['hit_rate']:.2f} در برابر "
                                 f"{results[second]['hit_rate']:.2f} (p={hit_probability:.2f})")}
    if rubric_probability >= threshold:
        return best, {"rule": "داور با تفکیک آماری", "winner": best, **stats,
                      "detail": (f"{best}: داور {results[best]['rubric_mean']:.3f} در برابر "
                                 f"{results[second]['rubric_mean']:.3f} (p={rubric_probability:.2f})")}

    winner = min(results, key=lambda name: results[name]["chat_ppl"])
    return winner, {"rule": "تساوی در کیفیت تولید؛ سرگشتگی کمتر", "winner": winner, **stats,
                    "detail": (f"هیچ مرحله‌ای در برخورد/داور تفکیک‌پذیر نبود "
                               f"(p={hit_probability:.2f}/{rubric_probability:.2f})؛ "
                               f"کمترین سرگشتگی گفتگو: {results[winner]['chat_ppl']:.2f}")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stages", default="checkpoints/stages")
    parser.add_argument("--out", default="checkpoints/last.npz")
    parser.add_argument("--report", default="reports/stages.json")
    parser.add_argument("--seeds", default="data/chat_seed.jsonl")
    parser.add_argument("--seed-limit", type=int, default=0,
                        help="۰ یعنی همهٔ پرسش‌های کنارگذاشته")
    args = parser.parse_args()

    dirname = os.path.join(ROOT, args.stages)
    missing = [name for name in STAGES
               if not os.path.exists(os.path.join(dirname, f"{name}.npz"))]
    if missing:
        print(f"عکس مرحله‌ها موجود نیست: {', '.join(missing)} → اول train_align.py")
        return 2

    prompts = knowledge_prompts()
    seeds: list[dict] = []
    with open(os.path.join(ROOT, args.seeds), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                row = json.loads(line)
                seeds.append({"user": row["user"], "assistant": row["assistant"]})
    # فقط همان بخش کنارگذاشته‌ای که در SFT دیده نشده (هم‌برش با train_align)
    seeds = split_prompts(seeds, ratio=0.2)[1]
    if args.seed_limit:
        seeds = seeds[:args.seed_limit]

    results = {}
    for name in STAGES:
        print(f"[stages] {STAGE_LABELS[name]} …", flush=True)
        results[name] = evaluate_stage(os.path.join(dirname, f"{name}.npz"), prompts, seeds)
        print(f"          برخورد {results[name]['hit_rate']:.2f} · داور "
              f"{results[name]['rubric_mean']:.3f} · پرش ‌{results[name]['chat_ppl']:.2f} · "
              f"{results[name]['seconds']:.0f}s", flush=True)

    winner, decision = choose(results)
    source = os.path.join(dirname, f"{winner}.npz")
    target = os.path.join(ROOT, args.out)
    if os.path.abspath(source) != os.path.abspath(target):
        tmp = target + ".tmp"
        shutil.copyfile(source, tmp)
        os.replace(tmp, target)

    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "prompts": len(prompts), "stages": results,
              "decision": decision, "shipped": os.path.relpath(target, ROOT)}
    path = os.path.join(ROOT, args.report)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"[stages] برنده: {winner} — {decision['detail']}")
    print(f"[stages] منتشر شد: {report['shipped']} · گزارش: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
