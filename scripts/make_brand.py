"""ساخت دارایی‌های برند رایان: نشان کره‌ای، فاوآیکون و تصویر اشتراک‌گذاری.

    python scripts/make_brand.py

همهٔ خروجی‌ها قطعی و بازتولیدپذیرند (بدون وابستگی به سرویس بیرونی).
"""
from __future__ import annotations

import math
import os

import arabic_reshaper
import numpy as np
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND_DIR = os.path.join(ROOT, "web", "static", "assets", "brand")
ICON_DIR = os.path.join(ROOT, "web", "static", "assets", "icons")
FONT_DIR = "/tmp"

NAVY = (5, 11, 26)
NAVY_2 = (8, 18, 40)


def _fa(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


def orb(size: int, glow: float = 0.0) -> Image.Image:
    """کرهٔ برند با گرادیان شعاعی و دو چشم سفید، در ابعاد دلخواه."""
    ss = 2
    n = size * ss
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    cx, cy = 0.34 * n, 0.26 * n
    cx2, cy2 = 0.50 * n, 0.50 * n
    # شعاع درون کره
    r_full = 0.36 * n
    dist = np.sqrt(((xs - cx2) / r_full) ** 2 + ((ys - cy2) / r_full) ** 2)
    # جهت گرادیان از نور بالا-راست
    t = np.sqrt(((xs - cx) / (1.55 * n)) ** 2 + ((ys - cy) / (1.55 * n)) ** 2)
    t = np.clip(t / max(t.max(), 1e-6) * 1.18, 0, 1)[..., None]
    stops = np.array([
        [0.0, 125, 240, 255],
        [0.26, 56, 210, 255],
        [0.58, 18, 139, 255],
        [0.82, 11, 71, 232],
        [1.0, 8, 38, 168],
    ], dtype=np.float32)
    rgb = np.zeros((n, n, 3), dtype=np.float32)
    for (p0, *c0), (p1, *c1) in zip(stops[:-1], stops[1:]):
        mask = (t >= p0) & (t <= p1)
        f = (t - p0) / max(p1 - p0, 1e-6)
        for ch in range(3):
            rgb[..., ch] = np.where(mask[..., 0], c0[ch] + (c1[ch] - c0[ch]) * f[..., 0], rgb[..., ch])
    eye_y = 0.50 * n
    eye_r = 0.0527 * n * (size / 256 * 256 / size)  # نسبت ثابت به اندازهٔ کره
    eye_r = 0.0527 * n
    alpha = np.clip((1.0 - dist) * n * 0.5, 0, 1)  # لبهٔ نرم
    img = np.zeros((n, n, 4), dtype=np.uint8)
    img[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    img[..., 3] = (alpha * 255).astype(np.uint8)
    out = Image.fromarray(img, "RGBA").resize((size, size), Image.LANCZOS)
    # بازتاب نور روی لایهٔ جدا تا شفافیت کره حفظ شود
    shine = Image.new("RGBA", out.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    sd.ellipse([0.25 * size, 0.16 * size, 0.60 * size, 0.42 * size], fill=(255, 255, 255, 34))
    sd.ellipse([0.28 * size, 0.18 * size, 0.51 * size, 0.34 * size], fill=(255, 255, 255, 26))
    shine = shine.filter(ImageFilter.GaussianBlur(size * 0.012))
    out = Image.alpha_composite(out, shine)
    draw = ImageDraw.Draw(out, "RGBA")
    for ex in (0.406, 0.594):
        draw.ellipse(
            [(ex - 0.0527) * size, (0.5 - 0.0527) * size,
             (ex + 0.0527) * size, (0.5 + 0.0527) * size],
            fill=(255, 255, 255, 255),
        )
    if glow > 0:
        halo = Image.new("RGBA", out.size, (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse(
            [size * 0.12, size * 0.12, size * 0.88, size * 0.88],
            fill=(30, 123, 255, int(120 * glow)),
        )
        halo = halo.filter(ImageFilter.GaussianBlur(size * 0.06))
        halo.alpha_composite(out)
        out = halo
    return out


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def _center_text(draw, box, text, font, fill):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    w, h = right - left, bottom - top
    x = box[0] + (box[2] - box[0] - w) / 2 - left
    y = box[1] + (box[3] - box[1] - h) / 2 - top
    draw.text((x, y), text, font=font, fill=fill)


def og_image(path: str) -> None:
    W, H = 1200, 630
    bg = Image.new("RGB", (W, H), NAVY)
    # هاله‌های نرم
    glow = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(glow)
    d.ellipse([W * 0.22, -H * 0.55, W * 0.78, H * 0.55], fill=(10, 34, 88))
    d.ellipse([W * 0.34, -H * 0.30, W * 0.66, H * 0.35], fill=(10, 52, 128))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    bg = Image.blend(bg, glow, 0.9)
    # شبکهٔ نقطه‌ای محو
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, W, 40):
        for y in range(0, H, 40):
            gd.point((x, y), fill=(120, 190, 255, 26))
    bg = Image.alpha_composite(bg.convert("RGBA"), grid)
    # کره
    ball = orb(230, glow=0.9)
    bg.alpha_composite(ball, (int(W / 2 - 115), 46))
    d = ImageDraw.Draw(bg)
    _center_text(d, (0, 292, W, 404), _fa("رایان"), _font("Vazirmatn-Black.ttf", 104), (255, 255, 255))
    _center_text(d, (0, 408, W, 448), "R A Y A N", _font("Vazirmatn-Bold.ttf", 30), (110, 170, 255))
    _center_text(d, (0, 466, W, 512), _fa("هوش مصنوعی، به زبان فارسی"), _font("Vazirmatn-Medium.ttf", 30), (170, 200, 235))
    _center_text(d, (0, 552, W, 590), "from scratch · numpy · 6.57M params", _font("Vazirmatn-Regular.ttf", 21), (108, 132, 168))
    bg.convert("RGB").save(path, quality=92, optimize=True)


def avatar(path: str, size: int, bg_color: tuple[int, int, int] | None) -> None:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0) if bg_color is None else bg_color + (255,))
    if bg_color is not None:
        d = ImageDraw.Draw(canvas)
        d.ellipse([0, 0, size - 1, size - 1], fill=bg_color + (255,))
    pad = int(size * 0.06)
    ball = orb(size - 2 * pad)
    canvas.alpha_composite(ball, (pad, pad))
    canvas.save(path, optimize=True)


def main() -> None:
    os.makedirs(BRAND_DIR, exist_ok=True)
    os.makedirs(ICON_DIR, exist_ok=True)
    orb(1024, glow=0.55).save(os.path.join(BRAND_DIR, "orb-1024.png"), optimize=True)
    orb(512).save(os.path.join(BRAND_DIR, "orb-512.png"), optimize=True)
    orb(256).save(os.path.join(BRAND_DIR, "orb-256.png"), optimize=True)
    orb(128).save(os.path.join(BRAND_DIR, "orb-128.png"), optimize=True)
    avatar(os.path.join(ICON_DIR, "favicon-32.png"), 32, None)
    avatar(os.path.join(ICON_DIR, "favicon-192.png"), 192, (5, 11, 26))
    avatar(os.path.join(ICON_DIR, "apple-touch-icon.png"), 180, (5, 11, 26))
    avatar(os.path.join(ICON_DIR, "maskable-512.png"), 512, (5, 11, 26))
    og_image(os.path.join(BRAND_DIR, "og-image.png"))
    print("brand assets written to", BRAND_DIR, "and", ICON_DIR)


if __name__ == "__main__":
    main()
