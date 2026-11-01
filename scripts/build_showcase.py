"""ساخت فایل نمایش نمونه‌ها برای صفحهٔ مدل از گزارش ارزیابی.

    python scripts/build_showcase.py --evaluation reports/evaluation.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re

FA_DIGITS = str.maketrans("0123456789.,", "۰۱۲۳۴۵۶۷۸۹٫٬")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PREFERRED = [
    ("chat", "خودت را معرفی"),
    ("poetry", "شعر"),
    ("continue", "کویر"),
]


def _fa(value: float, digits: int = 2) -> str:
    text = f"{value:,.{digits}f}".replace(",", "\u0000").replace(".", "\u0001")
    text = text.translate(FA_DIGITS).replace("\u0000", "٬").replace("\u0001", "٫")
    return text


def _final_train_loss(path: str) -> float | None:
    if not os.path.exists(path):
        return None
    last = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "loss" in row:
                last = row
    return float(last["loss"]) if last else None


def default_metrics_path() -> str:
    """جدیدترین گزارش آموزش موجود؛ نسخهٔ ۲ اولویت دارد."""
    for candidate in ("logs/metrics-v2.jsonl", "logs/metrics.jsonl"):
        if os.path.exists(os.path.join(ROOT, candidate)):
            return candidate
    return "logs/metrics.jsonl"


def update_model_card(evaluation: dict, path: str, metrics_path: str | None = None) -> bool:
    """جدول ارزیابی را میان نشانه‌های eval در کارت مدل جای‌گذاری می‌کند."""
    ev = evaluation.get("evaluation")
    if not ev or not os.path.exists(path):
        return False
    metrics = evaluation.get("metrics") or {}
    meta = evaluation.get("meta") or {}
    steps = metrics.get("steps") or meta.get("step")
    tokens = meta.get("tokens_seen")
    cfg = evaluation.get("config") or {}
    if not tokens and steps and cfg.get("batch_size") and cfg.get("block_size"):
        tokens = int(steps) * int(cfg["batch_size"]) * int(cfg["block_size"])
    final_loss = _final_train_loss(os.path.join(ROOT, metrics_path or default_metrics_path()))
    rows = [
        "> ارزیابی روی کل مجموعهٔ اعتبارسنجی، بدون dropout و بدون نمونه‌گیری داغ.",
        "",
        "| سنجه | مقدار |",
        "|---|---|",
        f"| خطای اعتبارسنجی (nats/token) | {_fa(ev['val_loss'], 4)} |",
        f"| Perplexity | {_fa(ev['ppl'], 2)} |",
        f"| بیت بر نویسه | {_fa(ev['bits_per_char'], 4)} |",
        f"| دقت توکن بعدی (top-1 / top-5) | {_fa(ev['top1_accuracy'] * 100, 1)}٪ / {_fa(ev['top5_accuracy'] * 100, 1)}٪ |",
        f"| خطای آموزش (پایان) | {_fa(final_loss, 4) if final_loss is not None else '—'} |",
        f"| توکن دیده‌شده | {_fa(tokens, 0) if tokens else '—'} |",
    ]
    block = "<!-- eval:start -->\n" + "\n".join(rows) + "\n<!-- eval:end -->"
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if "<!-- eval:start -->" not in text:
        return False
    text = re.sub(r"<!-- eval:start -->.*?<!-- eval:end -->", block, text, flags=re.S)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return True


def score_sample(sample: dict) -> float:
    """امتیاز سادهٔ کیفیت برای انتخاب بهترین نمونهٔ هر حالت (بدون ویرایش دستی)."""
    text = (sample.get("text") or "").strip()
    tokens = int(sample.get("tokens") or 0)
    if not text:
        return -9.0
    score = 0.0
    if tokens < 8:
        score -= 2.0
    if 30 <= tokens <= 140:
        score += 1.0
    if text[-1:] in ".!؟…»:؛":
        score += 0.8
    words = text.split()
    if len(words) >= 3:
        trigrams = [tuple(words[i:i + 3]) for i in range(len(words) - 2)]
        score += 0.8 * len(set(trigrams)) / len(trigrams)
    if "\n" in text:
        score += 0.6 if sample.get("mode") == "poetry" else 0.2
    score += float(sample.get("confidence") or 0) * 2.0
    persian = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    score += 0.8 * persian / len(text)
    score -= 1.6 * latin / len(text)
    if text[:1] and "\u0600" <= text[0] <= "\u06ff":
        score += 0.3
    return score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", default="reports/evaluation.json")
    parser.add_argument("--out", default="reports/showcase.json")
    parser.add_argument("--model-card", default="docs/MODEL_CARD.md")
    args = parser.parse_args()
    with open(args.evaluation, encoding="utf-8") as fh:
        data = json.load(fh)
    samples = data.get("samples", [])
    chosen = []
    for mode, hint in PREFERRED:
        pool = [
            sample for sample in samples
            if sample["mode"] == mode and (hint in sample.get("prompt", "") or mode == "poetry")
        ]
        if pool:
            chosen.append(max(pool, key=lambda sample: score_sample(sample) + (0.08 if sample.get("deep") else 0.0)))
    if len(chosen) < 3:
        for sample in samples:
            if sample not in chosen:
                chosen.append(sample)
            if len(chosen) >= 3:
                break
    examples = [
        {
            "mode": s["mode"],
            "prompt": s.get("prompt", ""),
            "text": s.get("text", ""),
            "tokens": s.get("tokens", 0),
            "tok_s": s.get("tok_s", 0),
            "confidence": s.get("confidence", 0),
            "deep": bool(s.get("deep")),
        }
        for s in chosen[:3]
    ]
    payload = {
        "examples": examples,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "checkpoint_step": data.get("meta", {}).get("step"),
        "note": "نمونه‌های تصادفی بدون ویرایش دستی از همین مدل.",
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"wrote {args.out} with {len(examples)} examples")
    if os.path.exists(args.model_card) and update_model_card(data, args.model_card):
        print(f"updated evaluation table in {args.model_card}")


if __name__ == "__main__":
    main()
