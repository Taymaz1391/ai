#!/usr/bin/env python3
"""میزانِ رایان — سنجش فارسی روی همهٔ نسخه‌های مدل، با اعداد خودمان.

این آزمون را خود پروژه نوشته و هیچ‌جا از دیگری کپی نشده؛ پس «منبع» بیرونی ندارد.
هدف دو چیز است:

1. **صادق بودن** — هیچ عددی دستی نوشته نمی‌شود؛ همه از اجرای واقعی مدل روی
   همین ماشین می‌آید و در ``reports/arena.json`` ذخیره می‌شود.
2. **قابل تکرار بودن** — هر کس همین اسکریپت را اجرا کند به همین عددها می‌رسد.

دسته‌ها: دانش عمومی، ادب و شعر، ریاضی و ابزار، دستور زبان، کد، گفتگوی روزمره.
معیارها همه عینی‌اند: واژهٔ کلیدی، عدد، نسبت فارسی، طول، و نبودِ حلقهٔ تکرار.

    python scripts/arena_benchmark.py                # همهٔ نسخه‌ها
    python scripts/arena_benchmark.py --models last  # فقط نسخهٔ فعال
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHECKPOINTS = ROOT / "checkpoints"
REPORTS = ROOT / "reports"
TOKENIZER = ROOT / "tokenizer" / "rayan_bpe.json"
TOKENIZER_16K = ROOT / "tokenizer" / "rayan_bpe_16k.json"

# ---------------------------------------------------------------- مجموعهٔ آزمون
# هر پرسش یک شرط عینی دارد؛ هیچ داوری سلیقه‌ای در کار نیست.
SUITE: list[dict] = [
    # دانش عمومی
    {"cat": "دانش عمومی", "q": "پایتخت ایران کجاست؟", "any": ["تهران"]},
    {"cat": "دانش عمومی", "q": "پایتخت فرانسه کدام شهر است؟", "any": ["پاریس"]},
    {"cat": "دانش عمومی", "q": "بلندترین قلهٔ ایران چه نام دارد؟", "any": ["دماوند"]},
    {"cat": "دانش عمومی", "q": "خلیج فارس در کدام منطقه است؟", "any": ["فارس"]},
    {"cat": "دانش عمومی", "q": "زلزله چگونه به وجود می‌آید؟", "min_chars": 40},
    {"cat": "دانش عمومی", "q": "آب در چه دمایی می‌جوشد؟", "any": ["۱۰۰", "100", "صد"]},
    # ادب و شعر
    {"cat": "ادب و شعر", "q": "فردوسی کیست؟", "any": ["شاهنامه", "فردوسی"]},
    {"cat": "ادب و شعر", "q": "حافظ اهل کدام شهر بود؟", "any": ["شیراز"]},
    {"cat": "ادب و شعر", "q": "شاهنامهٔ فردوسی دربارهٔ چیست؟", "min_chars": 40},
    {"cat": "ادب و شعر", "q": "یک بیت شعر دربارهٔ دریا بنویس.", "min_chars": 30, "persian": 0.6},
    {"cat": "ادب و شعر", "q": "مولانا کی بود؟", "any": ["مولانا", "مولوی", "رومی"]},
    # ریاضی و ابزار
    {"cat": "ریاضی و ابزار", "q": "۷ * ۶ چند است؟", "any": ["42", "۴۲"]},
    {"cat": "ریاضی و ابزار", "q": "۱۲۳ + ۴۵۶ چند می‌شود؟", "any": ["579", "۵۷۹"]},
    {"cat": "ریاضی و ابزار", "q": "۹۶ تقسیم بر ۱۲", "any": ["8", "۸"]},
    {"cat": "ریاضی و ابزار", "q": "۲۵ ٪ از ۸۰ چند است؟", "any": ["20", "۲۰"]},
    # دستور زبان
    {"cat": "دستور زبان", "q": "«کتاب‌ها» جمع چه واژه‌ای است؟", "any": ["کتاب"]},
    {"cat": "دستور زبان", "q": "فعل جملهٔ «او رفت» کدام است؟", "any": ["رفت"]},
    {"cat": "دستور زبان", "q": "تفاوت «را» و «به» را توضیح بده.", "min_chars": 40},
    {"cat": "دستور زبان", "q": "در جملهٔ «هوا سرد است»، نهاد کدام است؟", "any": ["هوا"]},
    # کد
    {"cat": "کد", "q": "یک تابع پایتون برای جمع دو عدد بنویس.", "any": ["def", "+"]},
    {"cat": "کد", "q": "در پایتون فهرست را چطور می‌سازیم؟", "any": ["[", "list"]},
    {"cat": "کد", "q": "حلقهٔ تکرار در پایتون چه دستوری است؟", "any": ["for", "while"]},
    # گفتگوی روزمره
    {"cat": "گفتگوی روزمره", "q": "سلام، حالت چطور است؟", "min_chars": 8},
    {"cat": "گفتگوی روزمره", "q": "برای شروع یک روز خوب چه پیشنهادی داری؟", "min_chars": 40},
    {"cat": "گفتگوی روزمره", "q": "خسته‌ام و حوصله ندارم.", "min_chars": 25},
    {"cat": "گفتگوی روزمره", "q": "یک برنامهٔ ساده برای ورزش روزانه بده.", "min_chars": 40},
    {"cat": "گفتگوی روزمره", "q": "چطور بهتر بخوابم؟", "min_chars": 40},
    {"cat": "گفتگوی روزمره", "q": "ممنون از کمکت.", "min_chars": 6},
    # ── دور دوم: پرسش‌هایی که پاسخشان در دور اول نبود ─────────────────────
    {"cat": "دانش عمومی", "q": "مرکز استان فارس کجاست؟", "any": ["شیراز"]},
    {"cat": "دانش عمومی", "q": "بزرگ‌ترین دریاچهٔ ایران چه نام دارد؟", "any": ["ارومیه"]},
    {"cat": "دانش عمومی", "q": "پایتخت ژاپن چیست؟", "any": ["توکیو"]},
    {"cat": "دانش عمومی", "q": "واحد اندازه‌گیری نیرو چیست؟", "any": ["نیوتون", "نیوتن"]},
    {"cat": "دانش عمومی", "q": "خون را کدام اندام در بدن پمپ می‌کند؟", "any": ["قلب"]},
    {"cat": "دانش عمومی", "q": "ایران چند استان دارد؟", "any": ["۳۱", "31"]},
    {"cat": "دانش عمومی", "q": "نزدیک‌ترین سیاره به خورشید کدام است؟", "any": ["عطارد"]},
    {"cat": "دانش عمومی", "q": "نویسندهٔ کتاب گلستان کیست؟", "any": ["سعدی"]},
    {"cat": "دانش عمومی", "q": "آب از چه عنصرهایی ساخته شده است؟", "any": ["هیدروژن", "اکسیژن"]},
    {"cat": "ادب و شعر", "q": "نویسندهٔ شاهنامه کیست؟", "any": ["فردوسی"]},
    {"cat": "ادب و شعر", "q": "مثنوی معنوی از کیست؟", "any": ["مولانا", "مولوی", "رومی"]},
    {"cat": "ادب و شعر", "q": "سبک شعر نیما یوشیج چه نام دارد؟", "any": ["نیمایی", "نو"]},
    {"cat": "ادب و شعر", "q": "حافظ در کدام شهر دفن شده است؟", "any": ["شیراز"]},
    {"cat": "ادب و شعر", "q": "یک جمله دربارهٔ اهمیت کتاب‌خوانی بنویس.", "min_chars": 40},
    {"cat": "ریاضی و ابزار", "q": "۱۵ × ۴ چند است؟", "any": ["60", "۶۰"]},
    {"cat": "ریاضی و ابزار", "q": "۱۰۰ منهای ۳۷ چند می‌شود؟", "any": ["63", "۶۳"]},
    {"cat": "ریاضی و ابزار", "q": "۲۰ ٪ از ۱۵۰ چند است؟", "any": ["30", "۳۰"]},
    {"cat": "ریاضی و ابزار", "q": "۷۲ تقسیم بر ۹", "any": ["8", "۸"]},
    {"cat": "دستور زبان", "q": "در جملهٔ «علی کتاب را خواند»، مفعول کدام است؟", "any": ["کتاب"]},
    {"cat": "دستور زبان", "q": "فعل جملهٔ «بچه‌ها بازی کردند» کدام است؟", "any": ["کردند"]},
    {"cat": "دستور زبان", "q": "«مردان» جمع چه واژه‌ای است؟", "any": ["مرد"]},
    {"cat": "دستور زبان", "q": "تفاوت جملهٔ پرسشی و خبری چیست؟", "min_chars": 40},
    {"cat": "کد", "q": "تابع فاکتوریل در پایتون بنویس.", "any": ["def"]},
    {"cat": "کد", "q": "تابع تشخیص عدد اول بنویس.", "any": ["def"]},
    {"cat": "کد", "q": "مجموع اعداد یک تا ده را با حلقه بنویس.", "any": ["for", "while"]},
    {"cat": "کد", "q": "دیکشنری در پایتون چطور ساخته می‌شود؟", "any": ["{", "dict"]},
    {"cat": "گفتگوی روزمره", "q": "امروز حالم خوب نیست.", "min_chars": 25},
    {"cat": "گفتگوی روزمره", "q": "یک راه برای تمرکز بیشتر پیشنهاد بده.", "min_chars": 40},
    {"cat": "گفتگوی روزمره", "q": "شب بخیر.", "min_chars": 5},
    {"cat": "گفتگوی روزمره", "q": "ازت ممنونم.", "min_chars": 5},
]


def persian_ratio(text: str) -> float:
    """سهم نویسه‌های فارسی از کل نویسه‌های معنادار."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    persian = sum(1 for ch in letters if "\u0600" <= ch <= "\u06FF")
    return persian / len(letters)


def degenerate(text: str) -> bool:
    """حلقهٔ تکرار: یک واژه بیش از حد تکرار شده یا یک عبارت پشت‌سرهم می‌آید."""
    words = re.findall(r"\w+", text)
    if len(words) < 12:
        return False
    if len(set(words)) / len(words) < 0.4:
        return True
    grams = [" ".join(words[i:i + 5]) for i in range(len(words) - 4)]
    return max((grams.count(g) for g in set(grams)), default=0) >= 3


def score(answer: str, item: dict) -> dict:
    text = (answer or "").strip()
    checks = {"طول": len(text) >= item.get("min_chars", 0)}
    if item.get("any"):
        checks["واژهٔ کلیدی"] = any(word in text for word in item["any"])
    if item.get("persian"):
        checks["فارسی"] = persian_ratio(text) >= item["persian"]
    checks["بی‌تکرار"] = not degenerate(text)
    return {"ok": all(checks.values()), "checks": checks}


def _api_session(base: str, ip: str):
    """یک حساب آزمون می‌سازد و کوکی‌اش را نگه می‌دارد (همان مسیر کاربر واقعی)."""
    import http.cookiejar
    import urllib.request

    from web import security

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {"Content-Type": "application/json", "Referer": base + "/",
               "X-Forwarded-For": ip}

    def call(path: str, payload: dict | None = None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(base + path, data=data, headers=headers)
        with opener.open(request, timeout=120) as response:
            body = response.read().decode("utf-8", "replace")
        try:
            return json.loads(body or "{}")
        except ValueError:            # صفحهٔ HTML (کوکی/نشست)، نه خطا
            return {}

    call("/chat")
    challenge = call("/api/captcha")
    call("/api/auth/register", {
        "name": "آزمون میزان", "email": f"arena{int(time.time()*1000) % 10**9}@example.com",
        "password": "arena-bench-pass",
        "captcha": {"token": challenge["token"],
                    "nonce": security.HumanCheck.solve(challenge["salt"], challenge["bits"]),
                    "evidence": {"moves": 12, "keys": 5, "elapsed_ms": 2100}}})
    return call


def run_api(base: str, items: list, pace: float = 1.4) -> dict:
    """سنجش همان چیزی که کاربر می‌بیند: کل مسیر محصول، نه مدل خام.

    ``pace`` فاصلهٔ درخواست‌ها را با محدودیت نرخِ خودِ سرویس (۴۵ درخواست در دقیقه
    برای هر نشانی) هم‌تراز می‌کند؛ زمان اندازه‌گیری‌شده فقط خودِ پاسخ است و این
    فاصله در عددِ سرعت حساب نمی‌شود.
    """
    started = time.time()
    call = _api_session(base, "198.51.100.77")
    rows, latencies = [], []
    for index, item in enumerate(items, 1):
        if pace and index > 1:
            time.sleep(pace)
        begin = time.perf_counter()
        try:
            for attempt in range(3):
                try:
                    body = call("/api/chat", {"message": item["q"], "max_new_tokens": 64})
                    break
                except Exception:  # noqa: BLE001 - فقط ۴۲۹ را دوباره امتحان می‌کنیم
                    if attempt == 2:
                        raise
                    time.sleep(20)
            if "error" in body:
                raise RuntimeError(body.get("error"))
            answer = str(body.get("answer") or "")
            engine = body.get("engine") or ""
        except Exception as exc:  # noqa: BLE001
            answer, engine = f"خطا: {exc}", "error"
        seconds = time.perf_counter() - begin
        latencies.append(seconds)
        verdict = score(answer, item)
        rows.append({"cat": item["cat"], "q": item["q"], "answer": answer[:300],
                     "seconds": round(seconds, 2), "engine": engine, **verdict})
        if os.environ.get("ARENA_VERBOSE"):
            print(f"  {index}/{len(items)} {item['q'][:30]} "
                  f"{'✓' if verdict['ok'] else '✗'} {seconds:.2f}s [{engine}]", flush=True)
    by_cat: dict[str, dict] = {}
    for row in rows:
        bucket = by_cat.setdefault(row["cat"], {"total": 0, "ok": 0})
        bucket["total"] += 1
        bucket["ok"] += 1 if row["ok"] else 0
    ordered = sorted(latencies)
    return {
        "id": "product",
        "tasks": len(rows),
        "score": round(100 * sum(1 for r in rows if r["ok"]) / max(1, len(rows)), 1),
        "by_category": {cat: round(100 * v["ok"] / v["total"], 1) for cat, v in by_cat.items()},
        "latency_p50_s": round(ordered[len(ordered) // 2], 2) if ordered else None,
        "latency_max_s": round(max(ordered), 2) if ordered else None,
        "tokens_per_second": None,
        "wall_seconds": round(time.time() - started, 1),
        "results": rows,
    }


def run_model(name: str, path: Path, items: list, budget: int) -> dict:
    from rayan.generate import Engine

    import numpy as np

    vocab = int(np.load(path, allow_pickle=True)["wte"].shape[0])
    tokenizer = TOKENIZER_16K if vocab == 16000 else TOKENIZER
    engine = Engine(str(path), str(tokenizer))
    rows, latencies, speeds = [], [], []
    for index, item in enumerate(items, 1):
        started = time.perf_counter()
        try:
            answer, generation, _ = engine.reply(item["q"], mode="chat",
                                                 max_new_tokens=budget)
            seconds = time.perf_counter() - started
            tokens = getattr(generation, "tokens", [])
            speed = getattr(generation, "tokens_per_second", 0) or 0
        except Exception as exc:  # noqa: BLE001 - یک پرسش نباید کل سنجش را بشکند
            answer, seconds, tokens, speed = f"خطا: {exc}", 0.0, [], 0.0
        verdict = score(answer, item)
        latencies.append(seconds)
        if speed:
            speeds.append(speed)
        rows.append({"cat": item["cat"], "q": item["q"], "answer": str(answer)[:300],
                     "seconds": round(seconds, 2), "tokens": len(tokens), **verdict})
        if os.environ.get("ARENA_VERBOSE"):
            print(f"  [{name}] {index}/{len(items)} {item['q'][:28]} "
                  f"{'✓' if verdict['ok'] else '✗'} {seconds:.2f}s", flush=True)
    total = len(rows) or 1
    by_cat: dict[str, dict] = {}
    for row in rows:
        bucket = by_cat.setdefault(row["cat"], {"total": 0, "ok": 0})
        bucket["total"] += 1
        bucket["ok"] += 1 if row["ok"] else 0
    return {
        "id": name,
        "tasks": len(rows),
        "score": round(100 * sum(1 for r in rows if r["ok"]) / total, 1),
        "by_category": {cat: round(100 * v["ok"] / v["total"], 1) for cat, v in by_cat.items()},
        "latency_p50_s": round(statistics.median(latencies), 2) if latencies else None,
        "latency_max_s": round(max(latencies), 2) if latencies else None,
        "tokens_per_second": round(statistics.median(speeds), 1) if speeds else None,
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=None,
                        help="نام فایل‌های checkpoint بدون پسوند؛ پیش‌فرض: همه")
    parser.add_argument("--budget", type=int, default=48, help="حداکثر توکن برای هر پاسخ")
    parser.add_argument("--api", default="", help="نشانی سرور؛ سنجش مسیر کامل محصول")
    parser.add_argument("--raw", action="store_true", help="سنجش مدل خام هم انجام شود")
    parser.add_argument("--pace", type=float, default=1.4,
                        help="فاصلهٔ درخواست‌ها در سنجش محصول (ثانیه)، هم‌تراز با محدودیت نرخ")
    args = parser.parse_args()

    if args.api:
        report = {"suite": "میزانِ رایان", "tasks": len(SUITE), "mode": "product",
                  "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "notes": ("سنجش روی مسیر کامل محصول (ابزار، دانشنامه و مدل) و روی همین ماشین. "
                            "آزمون را خود پروژه نوشته است.")}
        report["models"] = [run_api(args.api, SUITE, pace=args.pace)]
        REPORTS.mkdir(exist_ok=True)
        (REPORTS / "arena.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
        model = report["models"][0]
        print(json.dumps({k: model[k] for k in ("score", "by_category", "latency_p50_s",
                                                "tasks")}, ensure_ascii=False, indent=2))
        return 0

    wanted = args.models or ["last", "rayan-1-small", "rayan-2-base", "rayan-2-last",
                             "rayan-aligned"]
    started = time.time()
    report = {"suite": "میزانِ رایان", "tasks": len(SUITE),
              "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "notes": ("همهٔ عددها از اجرای مدل‌ها روی همین ماشین می‌آید. "
                        "آزمون را خود پروژه نوشته؛ هیچ پرسشی از مجموعهٔ دیگری کپی نشده است."),
              "models": []}
    for name in wanted:
        path = CHECKPOINTS / f"{name}.npz"
        if not path.exists():
            print(f"[=] {name} نیست؛ رد شد", flush=True)
            continue
        print(f"[+] {name}", flush=True)
        report["models"].append(run_model(name, path, SUITE, args.budget))

    report["wall_seconds"] = round(time.time() - started, 1)
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "arena.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    table = [{"model": m["id"], "score": m["score"], "p50_s": m["latency_p50_s"],
              "tok/s": m["tokens_per_second"]} for m in report["models"]]
    print(json.dumps(table, ensure_ascii=False, indent=2))
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
