#!/usr/bin/env python3
"""بنچمارک شفاف رایان — همان چیزی که واقعاً می‌شود سنجید، بدون ادعای اضافه.

سه دسته سنجیده می‌شود:

* ``tool`` / ``tool_now`` — دقت ابزارهای محلی (ماشین‌حساب و تقویم شمسی).
* ``normalize`` — یکدست‌سازی خط فارسی (ی/ک عربی، فاصله‌های اضافه).
* ``generation`` — کیفیت خروجی مدل با معیارهای عینی: وجود واژهٔ کلیدی، طول،
  نسبت فارسی و (اختیاری) وجود الگوی کد.

خروجی در ``reports/benchmark.json`` و ``docs/BENCHMARKS.md`` نوشته می‌شود.
اعداد مرجع Claude Opus 5.5 از اعلامیهٔ سازنده/گزارش‌های عمومی گرفته شده‌اند و
مقایسهٔ مستقیم با مدل ۶٫۵ میلیون پارامتری **معتبر نیست**؛ در سند توضیح داده شده.

    python scripts/benchmark.py                 # اجرای کامل
    python scripts/benchmark.py --limit-gen 4   # سریع‌تر (فقط ۴ تولید)
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHECKPOINT = ROOT / "checkpoints" / "rayan-1-small.npz"
TOKENIZER = ROOT / "tokenizer" / "rayan_bpe.json"
DATA = ROOT / "data" / "benchmark.jsonl"
REPORTS = ROOT / "reports"
DOCS = ROOT / "docs"

# اعداد منتشرشدهٔ Opus 5.5 (سپتامبر ۲۰۲۶) — فقط برای زمینه، نه مقایسهٔ هم‌سنگ
OPUS = {
    "model": "Claude Opus 5.5",
    "released": "2026-09-22",
    "context_tokens": 1_000_000,
    "price_in_per_mtok_usd": 4.0,
    "price_out_per_mtok_usd": 20.0,
    "published": {
        "SWE-bench Pro": 89.9,
        "SWE-bench Multilingual": 93.9,
        "Terminal-Bench 4.0": 66.4,
        "Humanity's Last Exam (no tools)": 64.4,
        "Humanity's Last Exam (with tools)": 67.7,
        "Global-MMLU": 94.3,
        "GDPval-AA v2.1 (Elo)": 1846,
    },
    "sources": [
        "https://codersera.com/blog/claude-opus-5-5-complete-guide-2026/",
        "https://llm-stats.com/blog/research/claude-opus-5-5-launch",
        "https://hokai.io/hub/models/claude-opus-5.5",
    ],
}


def load_items(limit_gen: int | None = None) -> list[dict]:
    items, seen_gen = [], 0
    for line in DATA.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row["kind"] == "generation":
            if limit_gen is not None and seen_gen >= limit_gen:
                continue
            seen_gen += 1
        items.append(row)
    return items


def run_tool(item: dict) -> dict:
    from web import tools

    found = tools.detect(item["prompt"])
    ok = bool(found)
    if ok and item["kind"] == "tool":
        ok = found.get("tool") == "calc" and abs(float(found.get("value", 1e9)) - item["expect_value"]) < 1e-6
    elif ok and item["kind"] == "tool_now":
        ok = found.get("tool") == "now" and bool(found.get("jalali"))
    return {"id": item["id"], "kind": item["kind"], "ok": ok,
            "got": (found or {}).get("value") if found else None}


def run_normalize(item: dict) -> dict:
    from rayan.text import normalize

    got = normalize(item["prompt"])
    return {"id": item["id"], "kind": "normalize", "ok": got == item["expect"], "got": got}


def run_generation(engine, item: dict) -> dict:
    from rayan.text import persian_ratio
    from web import knowledge, skills

    started = time.time()
    hit = skills.match(item["prompt"])
    kb = knowledge.answer(item["prompt"]) if not hit else None
    if hit or kb:
        answer = (hit or {}).get("answer") or kb["answer"]
        elapsed, tokens, speed = 0.0, 0, 0.0
        via = "skill" if hit else "knowledge"
    else:
        answer, generation, _prompt = engine.reply(item["prompt"], mode="chat", max_new_tokens=96)
        elapsed = time.time() - started
        tokens, speed = len(generation.tokens), generation.tokens_per_second
        via = "model"
    text = answer.strip()
    checks = {"chars": len(text) >= item.get("min_chars", 0)}
    if item.get("accept_any"):
        checks["keyword"] = any(word in text for word in item["accept_any"])
    if item.get("min_persian"):
        checks["persian"] = persian_ratio(text) >= item["min_persian"]
    return {
        "id": item["id"], "kind": "generation", "ok": all(checks.values()),
        "checks": checks, "answer": text[:280], "seconds": round(elapsed, 2),
        "tokens": tokens, "tok_per_s": speed, "via": via,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-gen", type=int, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if not CHECKPOINT.exists():
        print("checkpoint پیدا نشد؛ ابتدا مدل را آموزش بده.")
        return 1

    items = load_items(args.limit_gen)
    results: list[dict] = []
    engine = None
    started = time.time()

    for item in items:
        if item["kind"] in ("tool", "tool_now"):
            results.append(run_tool(item))
        elif item["kind"] == "normalize":
            results.append(run_normalize(item))
        else:
            if engine is None:
                from rayan.generate import Engine

                engine = Engine(str(CHECKPOINT), str(TOKENIZER))
                engine.warmup() if hasattr(engine, "warmup") else None
            results.append(run_generation(engine, item))

    def accuracy(kind: str) -> float:
        rows = [r for r in results if r["kind"] == kind]
        if not rows:
            return 0.0
        return round(100.0 * sum(1 for r in rows if r["ok"]) / len(rows), 1)

    gen_rows = [r for r in results if r["kind"] == "generation"]
    latencies = [r["seconds"] for r in gen_rows] or [0.0]
    speeds = [r["tok_per_s"] for r in gen_rows] or [0.0]

    summary = {
        "model": "rayan-1-small",
        "params": 6_574_848,
        "checkpoint": CHECKPOINT.name,
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_seconds": round(time.time() - started, 1),
        "tasks": len(results),
        "accuracy": {
            "tools_percent": accuracy("tool"),
            "clock_percent": accuracy("tool_now"),
            "normalize_percent": accuracy("normalize"),
            "generation_percent": accuracy("generation"),
        },
        "latency": {
            "generation_p50_s": round(statistics.median(latencies), 2),
            "generation_max_s": round(max(latencies), 2),
            "tokens_per_second_p50": round(statistics.median(speeds), 1),
        },
        "engine_mix": {
            "skill": sum(1 for r in gen_rows if r.get("via") == "skill"),
            "knowledge": sum(1 for r in gen_rows if r.get("via") == "knowledge"),
            "model": sum(1 for r in gen_rows if r.get("via") == "model"),
        },
        "cost_usd_per_million_tokens": 0.0,
        "context_tokens": 256,
        "opus_reference": OPUS,
        "results": results,
    }

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "benchmark.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    write_docs(summary)
    if not args.quiet:
        print(json.dumps({k: summary[k] for k in ("accuracy", "latency", "tasks")},
                         ensure_ascii=False, indent=2))
    return 0


def fa(text) -> str:
    """ارقام لاتین را برای سند فارسی به رقم فارسی تبدیل می‌کند."""
    table = str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")
    return str(text).translate(table)


def write_docs(summary: dict) -> None:
    acc = {k: fa(v) for k, v in summary["accuracy"].items()}
    lat = {k: fa(v) for k, v in summary["latency"].items()}
    opus = summary["opus_reference"]
    rows = "\n".join(
        f"| {name} | {value} |" for name, value in opus["published"].items())
    md = f"""# بنچمارک شفاف رایان

> این سند خودکار ساخته می‌شود: `python scripts/benchmark.py`
> آخرین اجرا: {fa(summary['run_at'])} — مدل `{summary['model']}` با {fa(f"{summary['params']:,}")} پارامتر.

## نتیجهٔ رایان در همین ماشین

| سنجه | نتیجه |
|---|---|
| دقت ابزار ماشین‌حساب | **{acc['tools_percent']}٪** |
| دقت ساعت/تقویم شمسی | **{acc['clock_percent']}٪** |
| یکدست‌سازی خط فارسی | **{acc['normalize_percent']}٪** |
| کیفیت تولید متن (معیار عینی) | **{acc['generation_percent']}٪** |
| تأخیر میانهٔ تولید | **{lat['generation_p50_s']} ثانیه** |
| سرعت تولید | **{lat['tokens_per_second_p50']} توکن/ثانیه** |
| هزینهٔ هر یک میلیون توکن | **۰ دلار** (سرور خودت) |
| طول زمینه | {fa(summary['context_tokens'])} توکن |

این اعداد روی {fa(summary['tasks'])} کار در همین مخزن و بدون هیچ سرویس بیرونی اندازه
گرفته شده‌اند؛ فایل خام: `reports/benchmark.json`. آزمون تولید، «درست‌بودن واژهٔ
کلیدی/طول/فارسی‌بودن» را می‌سنجد، نه هوشمندی کلی را — و همین‌جا صادق باشیم:
مدل ۶٫۵ میلیون پارامتری در پاسخ‌های استدلالی ضعیف است.

## اعداد منتشرشدهٔ Claude Opus 5.5 (فقط برای زمینه)

منبع: اعلامیه و کارت سیستم سازنده و گزارش‌های عمومی ({fa(opus['released'])})، زمینهٔ
{fa(f"{opus['context_tokens']:,}")} توکن، قیمت {fa(opus['price_in_per_mtok_usd'])} دلار ورودی و
{fa(opus['price_out_per_mtok_usd'])} دلار خروجی به‌ازای هر میلیون توکن.

| بنچمارک | Opus 5.5 |
|---|---|
{rows}

منابع: {", ".join(opus['sources'])}

## چرا این مقایسه هم‌سنگ نیست

- این بنچمارک‌ها (SWE-bench Pro، HLE، Terminal-Bench) تکالیف عامل‌محور و چندمرحله‌ای
  هستند؛ سنجه‌های ما (ابزار محلی، خط فارسی، تولید کوتاه) چیز دیگری را می‌سنجند.
- برای رسیدن به سطح آن مدل‌ها به داده و توان محاسباتی در حد هزاران GPU-ساعت نیاز است؛
  روی دو vCPU و بدون GPU نه آموزش چنین مدلی ممکن است نه صادقانه.
- ادعای «جلو زدن از Opus 5.5» با این سخت‌افزار **درست نیست** و در این پروژه ثبت نمی‌شود.

## جاهایی که رایان واقعاً جلوتر است

| محور | رایان | Opus 5.5 |
|---|---|---|
| هزینه | ۰ دلار، سرور خودت | ۴/۲۰ دلار به ازای هر میلیون توکن |
| حریم خصوصی | هیچ داده‌ای از سرور بیرون نمی‌رود | پردازش ابری |
| اجرا | آفلاین‌پذیر، بدون کلید API | نیازمند شبکه و حساب |
| مالکیت | کد و وزن‌ها باز، قابل آموزش دوباره | اختصاصی |
| تأخیر شبکه | صفر (همان ماشین) | رفت‌وبرگشت به مرکز داده |
| نصب | APK/EXE/PWA به یک سرور خودت | فقط وب/اپ رسمی |

## چطور بازتولید کنی

```bash
python scripts/benchmark.py
python -m pytest -q            # صحت مسیرها
```
"""
    DOCS.mkdir(exist_ok=True)
    (DOCS / "BENCHMARKS.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
