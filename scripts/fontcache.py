"""آماده‌سازی فونت‌های TTF برای ساخت تصویر و ویدیو.

دارایی‌های سایت با فرمت woff2 ذخیره می‌شوند تا صفحه سریع بار شود، اما PIL
فقط TTF/OTF می‌خواند. این ماژول همان فایل‌های مخزن را یک‌بار به TTF تبدیل
می‌کند و در پوشهٔ موقت می‌گذارد؛ هیچ دانلود بیرونی لازم نیست.
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "web", "static", "assets", "fonts")
OUT = "/tmp"

WEIGHTS = ("Regular", "Medium", "Bold", "ExtraBold", "Black")


def ensure_fonts(verbose: bool = False) -> str:
    os.makedirs(OUT, exist_ok=True)
    missing = [w for w in WEIGHTS if not os.path.exists(os.path.join(OUT, f"Vazirmatn-{w}.ttf"))]
    if missing:
        from fontTools.ttLib import TTFont  # نصب: pip install fonttools brotli

        for w in missing:
            src = os.path.join(SRC, f"Vazirmatn-{w}.woff2")
            if not os.path.exists(src):
                raise SystemExit(f"فونت پیدا نشد: {src}")
            font = TTFont(src)
            font.flavor = None
            font.save(os.path.join(OUT, f"Vazirmatn-{w}.ttf"))
            if verbose:
                print(f"[fonts] {w} → /tmp/Vazirmatn-{w}.ttf", flush=True)
    return OUT


if __name__ == "__main__":
    print(ensure_fonts(verbose=True))
