#!/usr/bin/env python3
"""بررسی سلامتِ نصب روی هاست — یک فرمان، گزارشِ روشن.

    python deploy/host_check.py

هر ردیف یا ✓ است یا ✗ با یک راهِ حلِ کوتاه. اگر همه ✓ شد، برنامه آماده است.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OK, BAD, WARN = "✓", "✗", "!"


def line(mark: str, title: str, detail: str = "", fix: str = "") -> None:
    print(f" {mark} {title}" + (f" — {detail}" if detail else ""))
    if fix:
        print(f"     راهِ حل: {fix}")


def main() -> int:
    problems = 0

    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 10):
        line(OK, "پایتون", f"{major}.{minor}")
    else:
        problems += 1
        line(BAD, "پایتون", f"{major}.{minor}", "در پنل هاست نسخهٔ ۳.۱۰ یا بالاتر را انتخاب کن.")

    os.environ.setdefault("RAYAN_HOST", "1")
    try:
        from web.hosting import prepare_host_env
        data_dir = prepare_host_env(ROOT)
        line(OK, "پوشهٔ داده", data_dir)
    except Exception as exc:  # noqa: BLE001
        problems += 1
        line(BAD, "پوشهٔ داده", str(exc), "RAYAN_DATA_DIR را به پوشه‌ای نوشتنی بده.")
        return problems

    packages = {}
    for name in ("fastapi", "uvicorn", "numpy", "pydantic", "email_validator"):
        try:
            module = __import__(name)
            packages[name] = getattr(module, "__version__", "?")
        except Exception:  # noqa: BLE001
            packages[name] = ""
    missing = [name for name, version in packages.items() if not version]
    if missing:
        problems += 1
        line(BAD, "بسته‌های پایتون", "نیست: " + "، ".join(missing),
             "در پنل هاست «Run Pip Install» را با requirements.txt بزن.")
    else:
        line(OK, "بسته‌های پایتون", "، ".join(f"{k}={v}" for k, v in packages.items()))

    checkpoint = os.path.join(ROOT, "checkpoints", "rayan-1-small.npz")
    tokenizer = os.path.join(ROOT, "tokenizer", "rayan_bpe.json")
    if os.path.exists(checkpoint) and os.path.getsize(checkpoint) > 1_000_000:
        line(OK, "مدل", f"{os.path.getsize(checkpoint) / 1e6:.1f} مگابایت")
    else:
        problems += 1
        line(BAD, "مدل", "فایل وزن‌ها پیدا نشد", "checkpoints/rayan-1-small.npz را دوباره آپلود کن.")
    if not os.path.exists(tokenizer):
        problems += 1
        line(BAD, "توکن‌ساز", "فایل واژه‌نامه نیست", "پوشهٔ tokenizer/ را کامل آپلود کن.")
    else:
        line(OK, "توکن‌ساز", "هست")

    try:
        from web import knowledge

        rows = len(knowledge.load())
        if rows:
            line(OK, "دانشنامه", f"{rows} ورودی")
        else:
            line(WARN, "دانشنامه", "خالی", "data/knowledge*.jsonl را آپلود کن.")
        hit = knowledge.answer("پایتخت فرانسه چیست؟")
        line(OK if hit else WARN, "پرسشِ آزمایشی", (hit or {}).get("answer", "پاسخی نیامد")[:60])
    except Exception as exc:  # noqa: BLE001
        problems += 1
        line(BAD, "دانشنامه", str(exc))

    try:
        from web import server
        from web.hosting import to_wsgi

        wsgi = to_wsgi(server.app)
        captured: dict = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = headers

        environ = {
            "REQUEST_METHOD": "GET", "PATH_INFO": "/api/health", "QUERY_STRING": "",
            "SERVER_NAME": "localhost", "SERVER_PORT": "8000",
            "SERVER_PROTOCOL": "HTTP/1.1", "wsgi.url_scheme": "http",
            "wsgi.input": __import__("io").BytesIO(b""), "CONTENT_LENGTH": "0",
        }
        body = b"".join(wsgi(environ, start_response))
        payload = json.loads(body.decode("utf-8") or "{}")
        if captured.get("status", "").startswith("200") and "ok" in payload:
            line(OK, "پلِ WSGI", "/api/health پاسخ داد")
        else:
            problems += 1
            line(BAD, "پلِ WSGI", captured.get("status", "?"),
                 "لاگ خطای هاست را ببین؛ معمولاً بستهٔ ناقص است.")
    except Exception as exc:  # noqa: BLE001
        problems += 1
        line(BAD, "پلِ WSGI", str(exc))

    base = os.environ.get("RAYAN_BASE_PATH", "")
    if base:
        line(OK, "زیرشاخه", base)
    else:
        line(OK, "زیرشاخه", "روی ریشهٔ دامنه")

    if not os.environ.get("RAYAN_OWNER_PASSWORD") and not os.path.exists(
            os.environ.get("RAYAN_OWNER_FILE", "")):
        line(WARN, "گذرواژهٔ مدیر", "تعریف نشده",
             "RAYAN_OWNER_PASSWORD را در متغیرهای محیطی پنل بگذار.")
    else:
        line(OK, "گذرواژهٔ مدیر", "تعریف شده")

    print()
    if problems:
        print(f"{problems} مورد نیاز به رفع دارد.")
        return 1
    print("همه‌چیز آماده است. نشانی سایت را باز کن و /admin را با گذرواژهٔ خودت وارد شو.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
