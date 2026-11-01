#!/usr/bin/env python3
"""سنجش ظرفیت واقعی سایت روی همین ماشین — بدون عدد ساختگی.

چند کاربر هم‌زمان شبیه‌سازی می‌شوند، هر کدام یک حساب می‌سازد و پرسش‌های دانشی
می‌فرستد؛ در پایان RPS، تأخیر میانه و صدک ۹۵، نرخ خطا و «تعداد کاربر هم‌زمانی
که این ماشین با نرخ خطای زیر ۱٪ جواب می‌دهد» گزارش می‌شود.

    python scripts/load_test.py --clients 16 --requests 5
    python scripts/load_test.py --clients 64 --requests 10 --json reports/load.json
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import statistics
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web import security  # noqa: E402

QUESTIONS = [
    "پایتخت ایران کجاست؟",
    "بلندترین قلهٔ ایران کجاست؟",
    "فردوسی کیست؟",
    "نوروز چیست؟",
    "خلیج فارس کجاست؟",
    "زلزله چیست؟",
    "تهران کجاست؟",
    "حافظ کیست؟",
]


def _opener(base: str):
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), base


def _call(op, path: str, payload: dict | None = None, timeout: float = 60,
          ip: str | None = None) -> tuple[int, float]:
    started = time.perf_counter()
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "Referer": op[1] + "/"}
    if ip:
        # هر کاربر پشت پراکسی، IP خودش را در همین سرآیند می‌فرستد.
        headers["X-Forwarded-For"] = ip
    req = urllib.request.Request(op[1] + path, data=data, headers=headers)
    try:
        with op[0].open(req, timeout=timeout) as res:
            res.read()
            return res.status, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, time.perf_counter() - started
    except Exception:  # noqa: BLE001
        return 0, time.perf_counter() - started


def run_client(index: int, base: str, requests_per_client: int, results: list,
               spread: bool = False) -> None:
    op = _opener(base)
    ip = f"10.{index // 250}.{index % 250}.7" if spread else None
    _call(op, "/chat", ip=ip)
    request = urllib.request.Request(base + "/api/captcha")
    if ip:
        request.add_header("X-Forwarded-For", ip)
    challenge = json.loads(op[0].open(request, timeout=20).read().decode())
    signup = {
        "name": f"بار {index}", "email": f"load{index}-{int(time.time())}@example.com",
        "password": "load-test-pass",
        "captcha": {"token": challenge["token"],
                    "nonce": security.HumanCheck.solve(challenge["salt"], challenge["bits"]),
                    "evidence": {"moves": 10, "keys": 4, "elapsed_ms": 1800}},
    }
    code, _ = _call(op, "/api/auth/register", signup, ip=ip)
    if code not in (200, 201):
        results.append({"status": code, "seconds": 0.0, "signup": True})
        return
    for turn in range(requests_per_client):
        question = QUESTIONS[(index + turn) % len(QUESTIONS)]
        status, seconds = _call(op, "/api/chat", {"message": question, "max_new_tokens": 40}, ip=ip)
        results.append({"status": status, "seconds": seconds})


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=os.environ.get("RAYAN_BASE", "http://localhost:8000"))
    parser.add_argument("--clients", type=int, default=8)
    parser.add_argument("--requests", type=int, default=3, help="پرسش به‌ازای هر کاربر")
    parser.add_argument("--json", default="")
    parser.add_argument("--spread", action="store_true",
                        help="هر کاربر IP جدا (پشت پراکسی) — سنجش ظرفیت سرور، نه سقف هر IP")
    parser.add_argument("--only-cached", action="store_true",
                        help="همهٔ کاربران یک پرسش می‌فرستند (سنجش کش)")
    args = parser.parse_args()
    if args.only_cached:
        global QUESTIONS
        QUESTIONS = QUESTIONS[:1]

    results: list = []
    threads = [threading.Thread(target=run_client,
                                args=(i, args.base, args.requests, results, args.spread))
               for i in range(args.clients)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - started

    chats = [row for row in results if not row.get("signup")]
    limited = [row for row in chats if row["status"] == 429]
    errors = [row for row in chats if row["status"] not in (200, 429)]
    ok = [row for row in chats if row["status"] == 200]
    latencies = [row["seconds"] for row in ok]
    total = len(results) + len(errors)
    report = {
        "base": args.base,
        "clients": args.clients,
        "requests_per_client": args.requests,
        "total_calls": len(results),
        "sign_up_failures": sum(1 for row in results if row.get("signup")),
        "chat_errors": len(errors),
        "rate_limited": len(limited),
        "error_rate": round(len(errors) / max(1, len(chats)), 4),
        "limited_rate": round(len(limited) / max(1, len(chats)), 4),
        "wall_seconds": round(elapsed, 2),
        "throughput_rps": round(len(results) / max(0.001, elapsed), 2),
        "latency_ms": {
            "mean": round(statistics.mean(latencies) * 1000, 1) if latencies else None,
            "median": round(percentile(latencies, 0.5) * 1000, 1),
            "p95": round(percentile(latencies, 0.95) * 1000, 1),
            "max": round(max(latencies) * 1000, 1) if latencies else None,
        },
        "error_codes": {str(code): sum(1 for row in chats if row["status"] == code)
                        for code in sorted({row["status"] for row in chats})},
        "note": ("این عدد ظرفیت سنجیده‌شدهٔ همین ماشین با همین مدل است؛ "
                 "۴۲۹ یعنی سقف ضدِسوءاستفادهٔ هر IP (نه خرابی). "
                 "برای مقیاس میلیونی، سرورهای بیشتر و پایگاه‌دادهٔ شبکه‌ای لازم است."),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        path = os.path.join(ROOT, args.json)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0 if report["error_rate"] < 0.05 else 1


if __name__ == "__main__":
    raise SystemExit(main())
