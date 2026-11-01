#!/usr/bin/env python3
"""بررسی سلامت نسخهٔ وب که همین حالا سرو می‌شود.

سه چیز را تضمین می‌کند:

1. هیچ صفحه‌ای دارایی (فونت، تصویر، اسکریپت، استایل) را از دامنهٔ بیرونی نمی‌گیرد؛
   پس در قطعیِ اینترنت بین‌المللی هم سایت همان شکل می‌ماند.
2. هر ارجاع محلی به یک فایل واقعی اشاره می‌کند (لینک مرده نماند).
3. سرویس‌ورکر و مانیفست سرِ جایشان هستند تا سایت آفلاین هم باز شود.

    python scripts/check_static.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"

REQUIRED = ["index.html", "app.html", "auth.html", "admin.html", "offline.html",
            "pricing.html", "models.html", "about.html", "compare.html",
            "manifest.webmanifest", "sw.js", "styles.css", "pages.css", "chat.css",
            "assets/video/intro.mp4", "assets/video/intro-poster.jpg"]

REF = re.compile(r'(?:href|src)="([^"#?]+)')
EXTERNAL = re.compile(r'^(?:https?:)?//(?!localhost|127\.0\.0\.1)')
# آدرس‌های مجازِ بیرونی: فقط لینک بیرون‌رو (repo) که فقط با کلیک باز می‌شود.
ALLOWED_EXTERNAL = ("github.com/taymaz1391/ai",)


def main() -> int:
    problems: list[str] = []
    for name in REQUIRED:
        if not (STATIC / name).exists():
            problems.append(f"missing: {name}")

    checked = 0
    for page in sorted(STATIC.rglob("*")):
        if page.suffix not in (".html", ".js", ".css") or not page.is_file():
            continue
        text = page.read_text(encoding="utf-8", errors="replace")
        rel = page.relative_to(STATIC)
        for ref in REF.findall(text):
            checked += 1
            if EXTERNAL.match(ref):
                if not any(host in ref.lower() for host in ALLOWED_EXTERNAL):
                    problems.append(f"{rel}: external asset {ref}")
                continue
            if any(ch in ref for ch in "${}+`"):  # مقدارِ ساخته‌شده در زمان اجرا
                continue
            if ref.startswith("/static/"):
                target = STATIC / ref[len("/static/"):]
            elif ref.startswith("/"):
                continue  # مسیر صفحه، نه فایل
            else:
                target = (page.parent / ref).resolve()
            if not target.exists():
                problems.append(f"{rel}: dead link {ref}")

    if problems:
        print("static check failed:")
        for item in problems[:60]:
            print("  -", item)
        print(f"({len(problems)} problems)")
        return 1
    pages = len(list(STATIC.glob("*.html")))
    print(f"static check ok: {pages} pages, {checked} references, همه محلی")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
