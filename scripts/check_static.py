#!/usr/bin/env python3
"""بررسی سلامت نسخهٔ استاتیک: هیچ ارجاع مطلقی به مسیرهای داخلی نمانده باشد."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED = ["index.html", "chat.html", "login.html", "signup.html",
            "pricing.html", "models.html", "about.html", "docs.html",
            "manifest.webmanifest", "sw.js", "static/ui.js", "static/styles.css"]
# ارجاع‌های /api/ در نسخهٔ استاتیک مجازند (به سرور اشاره می‌کنند)
INTERNAL = re.compile(r'(?:href|src)="(/(?!api/)[^"]*)"')


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    problems: list[str] = []
    for name in REQUIRED:
        if not (root / name).exists():
            problems.append(f"missing: {name}")
    for page in sorted(root.glob("*.html")):
        for ref in INTERNAL.findall(page.read_text(encoding="utf-8")):
            problems.append(f"{page.name} → {ref}")
    if "signup" not in (root / "signup.html").read_text(encoding="utf-8") \
            if (root / "signup.html").exists() else True:
        problems.append("signup.html is missing data-mode=signup") if (root / "signup.html").exists() else None
    if problems:
        print("static check failed:")
        for item in problems:
            print("  -", item)
        return 1
    print(f"static check ok: {len(list(root.glob('*.html')))} pages in {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
