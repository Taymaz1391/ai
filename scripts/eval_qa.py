"""سنجش صادقانهٔ لایهٔ پاسخ‌گویی روی پرسش‌های دانشی.

هر پرسش یک یا چند واژهٔ کلیدی انتظاری دارد؛ اگر پاسخِ ساخته‌شده هیچ‌کدام را
نداشته باشد، «نادرست» شمرده می‌شود و اگر هیچ شاهدی پیدا نشود «بدون پاسخ».
هیچ عددی دستی وارد نمی‌شود؛ خروجی JSON در ``reports/`` ذخیره می‌شود.

    python scripts/eval_qa.py
    python scripts/eval_qa.py --json reports/qa.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web import retrieval  # noqa: E402

CASES: list[tuple[str, list[str]]] = [
    ("پایتخت ایران کجاست؟", ["تهران"]),
    ("پایتخت فرانسه کجاست؟", ["پاریس"]),
    ("پایتخت ژاپن کجاست؟", ["توکیو"]),
    ("بلندترین قلهٔ ایران کجاست؟", ["دماوند"]),
    ("بلندترین قلهٔ جهان کجاست؟", ["اورست"]),
    ("زبان فارسی چیست؟", ["هندواروپایی", "ایرانی", "فارسی"]),
    ("فتوسنتز چیست؟", ["گیاه", "نور", "سبزینه"]),
    ("اینترنت چیست؟", ["شبکه", "رایانه", "اینترنت"]),
    ("جنگ جهانی دوم چه بود؟", ["1939", "۱۹۳۹", "آلمان", "جهانی"]),
    ("جنگ جهانی اول چه بود؟", ["1914", "۱۹۱۴", "آلمان"]),
    ("خوارزمی کیست؟", ["ریاضی", "جبر", "خوارزمی"]),
    ("حافظ کیست؟", ["شاعر", "غزل", "شیراز"]),
    ("مولانا کیست؟", ["شاعر", "مولوی", "مثنوی"]),
    ("فردوسی کیست؟", ["شاهنامه", "شاعر"]),
    ("سعدی کیست؟", ["شاعر", "گلستان", "بوستان"]),
    ("نوروز چیست؟", ["سال نو", "فروردین", "جشن"]),
    ("زلزله چیست؟", ["زمین", "لرزه", "لرزش"]),
    ("تهران کجاست؟", ["پایتخت", "ایران"]),
    ("خلیج فارس کجاست؟", ["ایران", "خلیج"]),
    ("دریاچهٔ ارومیه کجاست؟", ["آذربایجان", "ایران", "دریاچه"]),
    ("سازمان ملل چیست؟", ["ملل", "کشور", "سازمان"]),
    ("آب چیست؟", ["مایع", "آب", "هیدروژن"]),
    ("سیب چیست؟", ["میوه", "درخت", "سیب"]),
    ("خون چیست؟", ["مایع", "خون", "سلول"]),
    ("مغز چیست؟", ["مغز", "عصبی", "اندام"]),
    ("دماوند کجاست؟", ["البرز", "دماوند", "کوه"]),
    ("انقلاب مشروطه چه بود؟", ["مشروطه", "قاجار", "مجلس"]),
    ("سازمان ملل متحد چه کاری می‌کند؟", ["صلح", "کشور", "ملل"]),
    ("نفت چیست؟", ["نفت", "هیدروکربن", "سوخت"]),
    ("برج میلاد کجاست؟", ["تهران", "برج"]),
]


def evaluate(limit: int = 16) -> dict:
    rows = []
    answered = correct = 0
    for question, expected in CASES:
        started = time.time()
        try:
            result = retrieval.think(question, limit=limit)
        except Exception as exc:  # noqa: BLE001
            result = {"answer": None, "error": str(exc)}
        answer = result.get("answer") or ""
        hit = bool(answer) and any(word in answer for word in expected)
        answered += bool(answer)
        correct += hit
        rows.append({
            "question": question,
            "answer": answer[:220],
            "expected": expected,
            "engine": result.get("engine"),
            "confidence": result.get("confidence"),
            "verdict": "درست" if hit else ("نادرست" if answer else "بدون پاسخ"),
            "seconds": round(time.time() - started, 3),
        })
    total = len(CASES)
    return {
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total": total,
        "answered": answered,
        "correct": correct,
        "answered_rate": round(answered / total, 3),
        "accuracy_on_all": round(correct / total, 3),
        "accuracy_on_answered": round(correct / max(1, answered), 3),
        "seconds": round(sum(row["seconds"] for row in rows), 2),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=os.path.join(ROOT, "reports", "qa.json"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    report = evaluate()
    os.makedirs(os.path.dirname(args.json), exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    if not args.quiet:
        for row in report["rows"]:
            print(f"[{row['verdict']}] {row['question']}")
            print(f"    {(row['answer'] or '—')[:150]}")
    print(json.dumps({key: report[key] for key in
                      ("total", "answered", "correct", "answered_rate",
                       "accuracy_on_all", "accuracy_on_answered", "seconds")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
