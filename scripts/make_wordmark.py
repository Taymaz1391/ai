#!/usr/bin/env python3
"""ساخت لوگوتایپ افقی رایان (نشان + نام) برای نوار بالا و فوتر.

    python scripts/make_wordmark.py

خروجی‌ها در ``web/static/assets/brand/``:
  wordmark-ink.png    متن جوهری، برای تم روشن
  wordmark-white.png  متن سفید، برای تم تیره
  wordmark-blue.png   متن آبی‌گرادیانی برای پس‌زمینهٔ روشن
همه شفاف و ۲× هستند تا روی نمایشگرهای پیکسل‌سخت تیز بمانند.
"""
from __future__ import annotations

import os
import sys

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from make_brand import BRAND_DIR, _font, orb  # noqa: E402

NAME = "رایان"
TAGLINE = "RAYAN"


def _fa(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


def _spaced(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, spacing: int) -> int:
    """متن با فاصلهٔ حروف (برای RAYAN کوچک)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return int(x)


def build(fill: tuple[int, int, int], gradient: bool = False) -> Image.Image:
    scale = 2
    orb_size = 88 * scale
    name_font = _font("Vazirmatn-Black.ttf", 62 * scale)
    tag_font = _font("Vazirmatn-Bold.ttf", 17 * scale)

    probe = Image.new("RGBA", (10, 10))
    pd = ImageDraw.Draw(probe)
    name = _fa(NAME)
    nb = pd.textbbox((0, 0), name, font=name_font)
    name_w, name_h = nb[2] - nb[0], nb[3] - nb[1]
    tag_w = int(pd.textlength(TAGLINE, font=tag_font) + 6 * scale * (len(TAGLINE) - 1))
    gap = 16 * scale
    pad = 3 * scale
    text_w = max(name_w, tag_w)
    width = orb_size + gap + text_w + pad * 2
    height = max(orb_size, name_h + 10 * scale + tag_font.size) + pad * 2

    art = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(art)

    # متن در چپ، نشان در راست (چیدمان راست‌به‌چپ)
    text_right = width - pad - orb_size - gap
    text_left = text_right - text_w
    top = (height - (name_h + 8 * scale + tag_font.size)) // 2
    draw.text((text_right - name_w - nb[0], top - nb[1]), name, font=name_font, fill=fill + (255,))
    tag_y = top + name_h + 8 * scale
    if gradient:
        mask = Image.new("L", (width, height), 0)
        md = ImageDraw.Draw(mask)
        _spaced(md, (text_right - tag_w, 0), TAGLINE, tag_font, 255, 6 * scale)
        md.text((text_right - name_w - nb[0], top - nb[1]), name, font=name_font, fill=255)
        grad = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grad)
        w = width
        for x in range(w):
            t = x / max(w - 1, 1)
            r = int(53 + (77 - 53) * t)
            g = int(200 + (93 - 200) * t)
            b = int(245 + (251 - 245) * t)
            gd.line([(x, 0), (x, height)], fill=(r, g, b, 255))
        art = Image.composite(grad, art, mask)
        draw = ImageDraw.Draw(art)
    else:
        _spaced(draw, (text_right - tag_w, tag_y), TAGLINE, tag_font, fill + (255,), 6 * scale)

    icon = orb(orb_size)
    art.alpha_composite(icon, (width - pad - orb_size, (height - orb_size) // 2))
    return art.resize((width // scale, height // scale), Image.LANCZOS)


def main() -> None:
    os.makedirs(BRAND_DIR, exist_ok=True)
    targets = {
        "wordmark-ink.png": ((12, 26, 43), False),
        "wordmark-white.png": ((255, 255, 255), False),
        "wordmark-blue.png": ((26, 99, 240), True),
    }
    for name, (fill, gradient) in targets.items():
        img = build(fill, gradient)
        img.save(os.path.join(BRAND_DIR, name), optimize=True)
        print(f"[brand] {name} {img.size[0]}×{img.size[1]}")


if __name__ == "__main__":
    main()
