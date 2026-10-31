#!/usr/bin/env python3
"""ساخت لوگوتایپ‌های رسمی رایان از تصویر اصلی برند.

    python scripts/make_logotype.py

منبع، ``logo-source.jpg`` است (همان برگهٔ رسمی برند: کره بالای «رایان»).
لوگوتایپ با همان ترسیم اصلی برند بریده و پس‌زمینه‌اش شفاف می‌شود — هیچ
حرفی دوباره تایپ نمی‌شود.

خروجی‌ها در ``web/static/assets/brand``:

* ``mark-{ink,white}.png`` — فقط لوگوتایپ «رایان» برای استفادهٔ درون‌خطی.
* ``logotype-stack-{ink,white}.png`` — کره بالا، لوگوتایپ زیرش (قفل کامل).
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "web", "static", "assets", "brand")

# کادر لوگوتایپ فارسی در برگهٔ ۱۲۵۴×۱۲۵۴ (اندازه‌گیری‌شده)، با کمی حاشیه
WORDMARK_BOX = (366, 474, 888, 802)
NAVY = np.array([10, 23, 48], dtype=np.float32)
BLUE = np.array([26, 99, 240], dtype=np.float32)


def _alpha(lum_max: np.ndarray) -> np.ndarray:
    """پس‌زمینهٔ سرمه‌ای تیره شفاف می‌شود؛ حروف روشن کامل می‌مانند."""
    return np.clip((lum_max - 88.0) / 70.0, 0.0, 1.0)


def extract_mark(ink: bool) -> Image.Image:
    src = Image.open(os.path.join(BRAND, "logo-source.jpg")).convert("RGB")
    crop = np.asarray(src.crop(WORDMARK_BOX)).astype(np.float32)
    mx = crop.max(axis=2)
    mn = crop.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    alpha = _alpha(mx)
    if ink:
        # حروف سرمه‌ای، لهجه‌های آبی برند سر جای خودشان
        rgb = np.where((sat < 0.35)[..., None], NAVY, BLUE)
    else:
        # روی زمینهٔ تیره: حروف سفید، لهجه‌ها همان آبی برند
        white = np.array([247, 250, 255], dtype=np.float32)
        rgb = np.where((sat < 0.35)[..., None], white, BLUE)
    img = Image.fromarray(np.dstack([rgb, alpha * 255.0]).astype(np.uint8), "RGBA")
    return trim(img, pad=2)


def trim(img: Image.Image, pad: int = 8, threshold: int = 12) -> Image.Image:
    alpha = np.array(img.convert("RGBA"))[..., 3]
    ys, xs = np.where(alpha > threshold)
    if not len(xs):
        return img
    box = (max(int(xs.min()) - pad, 0), max(int(ys.min()) - pad, 0),
           min(int(xs.max()) + pad + 1, img.width), min(int(ys.max()) + pad + 1, img.height))
    return img.crop(box)


def build(ink: bool) -> None:
    suffix = "ink" if ink else "white"
    mark = extract_mark(ink)
    mark.save(os.path.join(BRAND, f"mark-{suffix}.png"), optimize=True)

    orb_src = Image.open(os.path.join(BRAND, "orb-512.png")).convert("RGBA")
    width = 900
    orb_w = int(width * 0.46)
    mark_w = int(width * 0.92)
    mark_h = int(mark.height * mark_w / mark.width)
    gap = int(orb_w * 0.22)
    canvas = Image.new("RGBA", (width, orb_w + gap + mark_h), (0, 0, 0, 0))
    canvas.alpha_composite(orb_src.resize((orb_w, orb_w), Image.LANCZOS), ((width - orb_w) // 2, 0))
    canvas.alpha_composite(mark.resize((mark_w, mark_h), Image.LANCZOS), ((width - mark_w) // 2, orb_w + gap))
    canvas = trim(canvas, pad=6)
    canvas.save(os.path.join(BRAND, f"logotype-stack-{suffix}.png"), optimize=True)
    print(f"[logotype] {suffix}: mark {mark.size} · stack {canvas.size}", flush=True)


def main() -> None:
    build(ink=True)
    build(ink=False)


if __name__ == "__main__":
    main()
