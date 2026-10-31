"""ساخت دارایی‌های برند رایان — نشان، قفل کامل لوگو، فاوآیکون و تصویر اشتراک.

    python scripts/make_brand.py

منبع قفل لوگو: ``web/static/assets/brand/logo-source.jpg`` (همان فایل اصلی برند).
خروجی‌ها قطعی و بازتولیدپذیرند و هیچ سرویس بیرونی لازم ندارند.
"""
from __future__ import annotations

import math
import os
import sys

import arabic_reshaper
import numpy as np
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from fontcache import ensure_fonts  # noqa: E402

ensure_fonts()

BRAND_DIR = os.path.join(ROOT, "web", "static", "assets", "brand")
ICON_DIR = os.path.join(ROOT, "web", "static", "assets", "icons")
FONT_DIR = "/tmp"

NAVY = (5, 11, 26)
NAVY_2 = (8, 18, 40)
INK = (11, 23, 43)          # متن تیره برای تم روشن
PAPER = (247, 250, 255)     # پس‌زمینهٔ تم روشن

SOURCE = os.path.join(BRAND_DIR, "logo-source.jpg")


def _fa(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


# ---------------------------------------------------------------- نشان کره‌ای
def orb(size: int, glow: float = 0.0) -> Image.Image:
    """کرهٔ برند با گرادیان شعاعی و دو چشم سفید، در ابعاد دلخواه."""
    ss = 2
    n = size * ss
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
    cx, cy = 0.34 * n, 0.26 * n
    cx2, cy2 = 0.50 * n, 0.50 * n
    r_full = 0.36 * n
    dist = np.sqrt(((xs - cx2) / r_full) ** 2 + ((ys - cy2) / r_full) ** 2)
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
    eye_r = 0.0527 * n
    alpha = np.clip((1.0 - dist) * n * 0.5, 0, 1)
    img = np.zeros((n, n, 4), dtype=np.uint8)
    img[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    img[..., 3] = (alpha * 255).astype(np.uint8)
    out = Image.fromarray(img, "RGBA").resize((size, size), Image.LANCZOS)
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


# ------------------------------------------------------- قفل کامل لوگو (artwork)
def _ramp(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """رمپ نرم بین دو آستانه؛ ترتیب آستانه‌ها اهمیتی ندارد."""
    if abs(hi - lo) < 1e-6:
        return (x >= hi).astype(np.float32)
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return (t * t * (3 - 2 * t)).astype(np.float32)


def _extract(source_path: str = SOURCE) -> tuple[Image.Image, Image.Image]:
    """پس‌زمینهٔ تیرهٔ لوگو را به آلفا تبدیل می‌کند.

    بازمی‌گرداند (نسخهٔ متن سفید, نسخهٔ متن جوهری) — هر دو با پس‌زمینهٔ شفاف.
    """
    src = Image.open(source_path).convert("RGB")
    px = np.asarray(src).astype(np.float32) / 255.0
    mx = px.max(axis=2)
    mn = px.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1e-4)

    # متن سفید: روشنایی بالا و اشباع کم؛ هالهٔ آبی پس‌زمینه زیر آستانه می‌ماند
    text_a = _ramp(mx, 0.34, 0.62) * _ramp(sat, 0.42, 0.16)
    # کرهٔ رنگی: اشباع بالا حتی با روشنایی متوسط
    orb_a = _ramp(mx * (0.35 + 0.65 * sat), 0.30, 0.52)
    alpha = np.clip(np.maximum(text_a, orb_a), 0, 1)

    bg = np.array(NAVY, dtype=np.float32) / 255.0
    safe = np.maximum(alpha, 1e-3)[..., None]
    color = np.clip((px - bg * (1 - safe)) / safe, 0, 1)

    # حذف هاله‌های پراکندهٔ پس‌زمینه: فقط پیکسل‌هایی می‌مانند که نزدیک محتوای اصلی‌اند
    strong = alpha > 0.55
    near = strong.copy()
    for dy in range(-5, 6):
        for dx in range(-5, 6):
            if dx * dx + dy * dy > 25:
                continue
            shifted = np.roll(np.roll(strong, dy, axis=0), dx, axis=1)
            near |= shifted
    alpha = np.where(near, alpha, 0.0)

    # لبهٔ کره را به دایرهٔ دقیق تبدیل می‌کنیم (حذف پیکسل‌های نویزی هالهٔ بالا)
    core = (sat > 0.55) & (mx > 0.45)
    core[int(src.height * 0.40):] = False          # فقط ناحیهٔ بالای قفل لوگو
    if core.any():
        ys_o, xs_o = np.nonzero(core)
        cy_o = (ys_o.min() + ys_o.max()) / 2.0
        cx_o = (xs_o.min() + xs_o.max()) / 2.0
        radius = min(xs_o.max() - xs_o.min(), ys_o.max() - ys_o.min()) / 2.0 + 1.0
        yy, xx = np.mgrid[0:src.height, 0:src.width]
        r = np.sqrt((yy - cy_o) ** 2 + (xx - cx_o) ** 2)
        disc = _ramp(r, radius + 0.8, radius - 1.2)   # ۱ داخل، ۰ خارج
        orb_zone = yy < cy_o + radius + 4
        alpha = np.where(orb_zone, np.minimum(alpha, disc) if False else disc, alpha)
        # داخل کره رنگ اصلی حفظ می‌شود، حتی اگر آلفا کمی کم بوده باشد
        alpha = np.where(orb_zone & (r < radius - 1), np.maximum(alpha, 0.985), alpha)

    a8 = (alpha * 255).astype(np.uint8)
    white_img = Image.fromarray(np.dstack([(color * 255).astype(np.uint8), a8]), "RGBA")

    # نسخهٔ متن تیره: متن سفید به جوهری تبدیل می‌شود، اما کره و چشم‌هایش دست‌نخورده می‌مانند
    rows = strong.any(axis=1)
    orb_end = int(np.argmax(rows)) + int(np.argmin(rows[int(np.argmax(rows)):]))  # پایان کره
    ink_weight = _ramp(sat, 0.34, 0.12) * _ramp(mx, 0.30, 0.55)
    band = np.ones((px.shape[0], 1), dtype=np.float32)
    band[max(orb_end - 6, 0):] = 1.0
    band[:max(orb_end - 6, 0)] = 0.0
    ink_weight = ink_weight * band
    ink_weight = ink_weight[..., None]
    ink = np.array(INK, dtype=np.float32) / 255.0
    tinted = color * (1 - ink_weight) + ink * ink_weight
    ink_img = Image.fromarray(np.dstack([(np.clip(tinted, 0, 1) * 255).astype(np.uint8), a8]), "RGBA")

    bbox = alpha > 0.20
    rows = np.where(bbox.any(axis=1))[0]
    cols = np.where(bbox.any(axis=0))[0]
    pad = 12
    box = (max(int(cols[0]) - pad, 0), max(int(rows[0]) - pad, 0),
           min(int(cols[-1]) + pad, src.width), min(int(rows[-1]) + pad, src.height))
    return white_img.crop(box), ink_img.crop(box)


def _fit(img: Image.Image, width: int) -> Image.Image:
    if img.width == width:
        return img
    height = round(img.height * width / img.width)
    return img.resize((width, height), Image.LANCZOS)


def _on_canvas(art: Image.Image, bg: tuple[int, int, int], pad_ratio: float = 0.10,
               glow: bool = True) -> Image.Image:
    """قفل لوگو را روی یک بوم مربع/مستطیل با هالهٔ نرم می‌نشاند."""
    w = max(art.width, 1)
    pad = int(w * pad_ratio)
    size = (art.width + pad * 2, art.height + pad * 2)
    canvas = Image.new("RGBA", size, bg + (255,))
    if glow:
        halo = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(halo)
        d.ellipse([size[0] * 0.18, size[1] * 0.02, size[0] * 0.82, size[1] * 0.55],
                  fill=(20, 96, 220, 90))
        halo = halo.filter(ImageFilter.GaussianBlur(int(size[0] * 0.09)))
        canvas = Image.alpha_composite(canvas, halo)
    canvas.alpha_composite(art, (pad, pad))
    return canvas


def avatar(path: str, size: int, bg_color: tuple[int, int, int] | None) -> None:
    """آیکون برنامه: فقط کرهٔ برند (بدون هیچ نام تایپ‌شده)."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0) if bg_color is None else bg_color + (255,))
    if bg_color is not None:
        d = ImageDraw.Draw(canvas)
        d.ellipse([0, 0, size - 1, size - 1], fill=bg_color + (255,))
    pad = int(size * 0.06)
    ball = orb(size - 2 * pad)
    canvas.alpha_composite(ball, (pad, pad))
    canvas.save(path, optimize=True)


def og_image(path: str) -> None:
    """تصویر اشتراک‌گذاری با لوگوتایپ تازه (کره بالای «رایان») — بدون نام تایپ‌شده."""
    W, H = 1200, 630
    stack_path = os.path.join(BRAND_DIR, "logotype-stack-white.png")
    bg = Image.new("RGBA", (W, H), NAVY + (255,))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse([W * 0.30, -H * 0.55, W * 0.70, H * 0.42], fill=(16, 78, 186, 165))
    d.ellipse([-W * 0.12, H * 0.55, W * 0.45, H * 1.2], fill=(10, 48, 120, 120))
    d.ellipse([W * 0.62, H * 0.62, W * 1.05, H * 1.15], fill=(12, 92, 168, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    bg = Image.alpha_composite(bg, glow)
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, W, 40):
        for y in range(0, H, 40):
            gd.point((x, y), fill=(120, 190, 255, 22))
    bg = Image.alpha_composite(bg, grid)

    if os.path.exists(stack_path):
        art = Image.open(stack_path).convert("RGBA")
        target_h = 340
        art = art.resize((int(art.width * target_h / art.height), target_h), Image.LANCZOS)
        bg.alpha_composite(art, ((W - art.width) // 2, 24))

    d = ImageDraw.Draw(bg)
    _center_text(d, (0, H - 240, W, H - 186), _fa("هوش مصنوعی، به زبان فارسی"),
                 _font("Vazirmatn-Black.ttf", 44), (255, 255, 255))
    _center_text(d, (0, H - 168, W, H - 126),
                 "from scratch · numpy · 6.57M params · persian ai",
                 _font("Vazirmatn-Medium.ttf", 23), (128, 176, 226))
    _center_text(d, (0, H - 104, W, H - 54), "taymaz1391.github.io/ai",
                 _font("Vazirmatn-Bold.ttf", 25), (86, 156, 255))
    bg.convert("RGB").save(path, quality=92, optimize=True)


def main() -> None:
    os.makedirs(BRAND_DIR, exist_ok=True)
    os.makedirs(ICON_DIR, exist_ok=True)
    orb(1024, glow=0.55).save(os.path.join(BRAND_DIR, "orb-1024.png"), optimize=True)
    orb(512).save(os.path.join(BRAND_DIR, "orb-512.png"), optimize=True)
    orb(256).save(os.path.join(BRAND_DIR, "orb-256.png"), optimize=True)
    orb(128).save(os.path.join(BRAND_DIR, "orb-128.png"), optimize=True)
    avatar(os.path.join(ICON_DIR, "favicon-32.png"), 32, None)
    avatar(os.path.join(ICON_DIR, "favicon-192.png"), 192, NAVY)
    avatar(os.path.join(ICON_DIR, "apple-touch-icon.png"), 180, NAVY)
    avatar(os.path.join(ICON_DIR, "maskable-512.png"), 512, NAVY)
    og_image(os.path.join(BRAND_DIR, "og-image.png"))
    print("brand assets written to", BRAND_DIR, "and", ICON_DIR)


if __name__ == "__main__":
    main()
