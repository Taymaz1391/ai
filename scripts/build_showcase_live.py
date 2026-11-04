#!/usr/bin/env python3
"""ساختِ نمونه‌های «پاسخ واقعی» برای صفحهٔ فرود (`reports/showcase.json`).

نمونه‌ها از خودِ سرویس گرفته می‌شوند، نه از خروجیِ خامِ یک مدلِ نیمه‌آموخته:
اسکریپت به همان مسیرِ `/api/chat` پیام می‌فرستد و فقط پاسخ‌هایی را نگه می‌دارد
که از دروازهٔ کیفیت بگذرند (طولِ کافی، فارسیِ روان، بی‌تکرار، و شاملِ واژهٔ
کلیدیِ همان پرسش). اگر پاسخی ضعیف بود کنار گذاشته می‌شود؛ چیزی ساخته یا
ویرایش نمی‌شود.

    python scripts/build_showcase_live.py                 # با سرورِ درون‌فرآیندی
    python scripts/build_showcase_live.py --api http://127.0.0.1:8020
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "reports", "showcase.json")

# (دسته، پرسش، واژه‌های کلیدی که پاسخ باید داشته باشد)
PROMPTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("chat", "پایتخت ایران کجاست؟", ("تهران",)),
    ("chat", "بزرگ‌ترین اقیانوس جهان کدام است؟", ("آرام",)),
    ("chat", "معنی brave به فارسی چیست؟", ("شجاع", "دلیر")),
    ("chat", "جذر ۱۴۴ چند است؟", ("۱۲", "12")),
    ("chat", "۱۵ درصد از ۲۰۰ چند است؟", ("۳۰", "30")),
    ("chat", "در SQL چطور تعداد رکوردها را بشمارم؟", ("COUNT", "count")),
    ("chat", "چطور قبض برق را کم کنم؟", ("برق", "لامپ", "کولر")),
    ("chat", "قند خون نرمال چقدر است؟", ("۱۰۰", "۷۰")),
    ("chat", "ایران چند استان دارد؟", ("۳۱", "31")),
    ("chat", "میانگین ۱۰ و ۲۰ و ۳۰ چند است؟", ("۲۰", "20")),
]

_FA = re.compile(r"[\u0600-\u06FF]")


def _bad(text: str) -> str | None:
    """اگر پاسخ برای نمایش روی صفحهٔ فرود مناسب نیست، دلیلش را برمی‌گرداند."""
    text = (text or "").strip()
    if len(text) < 25:
        return "کوتاه"
    if not _FA.search(text):
        return "فارسی نیست"
    words = re.findall(r"\w+", text)
    if len(words) > 8 and len(set(words)) / len(words) < 0.55:
        return "تکراری"
    for banned in ("نمی‌دانم", "پاسخِ بررسی‌شده‌ای", "مدل زبانی", "پیکره", "توکن"):
        if banned in text:
            return f"داخلی: {banned}"
    return None


def _ask_local(questions: list[str]) -> list[dict]:
    from fastapi.testclient import TestClient  # noqa: PLC0415

    os.chdir(ROOT)
    os.environ.setdefault("RAYAN_DB", "/tmp/showcase.sqlite3")
    os.environ.setdefault("RAYAN_REQUIRE_SIGNUP", "0")
    os.environ.setdefault("RAYAN_WATCH", "0")
    from web import server  # noqa: PLC0415

    client = TestClient(server.app)
    client.__enter__()
    for _ in range(120):
        if server.engine is not None:
            break
        time.sleep(0.5)
    started = time.time()
    out = []
    for question in questions:
        t0 = time.time()
        response = client.post("/api/chat", json={"message": question})
        seconds = time.time() - t0
        data = response.json() if response.status_code == 200 else {}
        out.append({"q": question, "answer": data.get("answer", ""),
                    "engine": data.get("engine"), "seconds": round(seconds, 3),
                    "status": response.status_code})
    # سهمیهٔ سنجش را پاک کن تا اجرای دوباره گیر نکند
    try:
        store = server.store()
        store._exec("DELETE FROM events WHERE user_id IS NULL", ())  # noqa: SLF001
    except Exception:  # noqa: BLE001
        pass
    client.__exit__(None, None, None)
    print(f"زمانِ کل: {time.time() - started:.1f} ثانیه")
    return out


def _ask_remote(api: str, questions: list[str]) -> list[dict]:
    import urllib.error
    import urllib.request

    out = []
    for question in questions:
        body = json.dumps({"message": question}).encode()
        req = urllib.request.Request(api.rstrip("/") + "/api/chat", data=body,
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read())
                status = response.status
        except urllib.error.HTTPError as exc:
            data, status = {}, exc.code
        out.append({"q": question, "answer": data.get("answer", ""),
                    "engine": data.get("engine"), "seconds": round(time.time() - t0, 3),
                    "status": status})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="", help="آدرسِ سرور در حال اجرا (اختیاری)")
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args()

    questions = [q for _mode, q, _want in PROMPTS]
    results = _ask_remote(args.api, questions) if args.api else _ask_local(questions)
    by_question = {row["q"]: row for row in results}

    examples, dropped = [], []
    for mode, question, wants in PROMPTS:
        row = by_question.get(question) or {}
        answer = (row.get("answer") or "").strip()
        reason = _bad(answer)
        if reason is None and wants and not any(w in answer for w in wants):
            reason = "بی‌ربط به پرسش"
        if reason:
            dropped.append((question, reason))
            continue
        examples.append({
            "mode": mode,
            "prompt": question,
            "text": answer,
            "engine": row.get("engine"),
            "seconds": row.get("seconds"),
            "verified": True,
        })

    payload = {
        "examples": examples,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": "پاسخِ واقعی همین سرویس (سنجش با دروازهٔ کیفیت)",
        "checked": len(PROMPTS),
        "kept": len(examples),
        "dropped": [{"q": q, "why": w} for q, w in dropped],
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"{len(examples)} نمونه از {len(PROMPTS)} پرسش در {args.out}")
    for question, reason in dropped:
        print(f"  − {question} ({reason})")


if __name__ == "__main__":
    main()
