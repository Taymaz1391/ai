#!/usr/bin/env python3
"""ساخت لوگوتایپ‌های استاندارد رایان از قفل کامل برند.

    python scripts/make_logotype.py

خروجی‌ها در ``web/static/assets/brand``:

* ``logotype-stack-{ink,white}.png`` — نشان (کره) بالا، لوگوتایپ «رایان» زیرش.
  همان چیدمانی که در برند اصلی است و در فوتر، هدر گفتگو و تیترها استفاده می‌شود.
* ``mark-{ink,white}.png`` — فقط لوگوتایپ «رایان» برای استفادهٔ درون‌خطی
  به‌جای متن تایپ‌شده.

هیچ دانلود بیرونی لازم نیست؛ منبع همان ``lockup-*.png`` است که از
``logo-source.jpg`` ساخته شده.
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "web", "static", "assets", "brand")


def bands(img: Image.Image, threshold: int = 24) -> list[tuple[int, int]]:
    """باندهای افقی محتوا (ردیف‌های پشت‌سرهم غیرخالی)."""
    alpha = np.array(img.convert("RGBA"))[..., 3]
    rows = (alpha > threshold).sum(axis=1)
    out: list[tuple[int, int]] = []
    start = None
    for y, value in enumerate(rows):
        if value > 0 and start is None:
            start = y
        elif value == 0 and start is not None:
            out.append((start, y - 1))
            start = None
    if start is not None:
        out.append((start, len(rows) - 1))
    return out


def trim(img: Image.Image, pad: int = 8, threshold: int = 24) -> Image.Image:
    alpha = np.array(img.convert("RGBA"))[..., 3]
    ys, xs = np.where(alpha > threshold)
    if not len(xs):
        return img
    box = (max(xs.min() - pad, 0), max(ys.min() - pad, 0),
           min(xs.max() + pad + 1, img.width), min(ys.max() + pad + 1, img.height))
    return img.crop(box)


def orb_art(src: Image.Image, size: int) -> Image.Image:
    """کرهٔ لوگو را از لوگوتایپ جدا می‌کند (کادر نامرئی هر دو نسخه یکی است)."""
    return src.crop((145, 0, 225, 94)).resize((size, size), Image.LANCZOS)


def build(ink: bool) -> None:
    suffix = "ink" if ink else "white"
    src = Image.open(os.path.join(BRAND, f"wordmark-{suffix}.png")).convert("RGBA")
    orb = orb_art(src, 512)

    # لوگوتایپ فارسی: «رایان» بدون خط LATIN زیرش
    fa = src.crop((0, 0, 132, 66))
    fa = trim(fa, pad=2)
    fa.save(os.path.join(BRAND, f"mark-{suffix}.png"), optimize=True)

    # چیدمان عمودی: کره بالا، لوگوتایپ زیرش
    width = 900
    orb_w = int(width * 0.52)
    orb_h = orb_w
    mark_w = int(width * 0.94)
    mark_h = int(fa.height * mark_w / fa.width)
    gap = int(orb_w * 0.26)
    canvas = Image.new("RGBA", (width, orb_h + gap + mark_h), (0, 0, 0, 0))
    canvas.alpha_composite(orb.resize((orb_w, orb_h), Image.LANCZOS), ((width - orb_w) // 2, 0))
    canvas.alpha_composite(fa.resize((mark_w, mark_h), Image.LANCZOS), ((width - mark_w) // 2, orb_h + gap))
    canvas = trim(canvas, pad=10)
    canvas.save(os.path.join(BRAND, f"logotype-stack-{suffix}.png"), optimize=True)
    print(f"[logotype] {suffix}: mark {fa.size} · stack {canvas.size}", flush=True)


def main() -> None:
    build(ink=True)
    build(ink=False)


if __name__ == "__main__":
    main()
