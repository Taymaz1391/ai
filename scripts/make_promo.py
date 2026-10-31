#!/usr/bin/env python3
"""ساخت ویدیوی تبلیغاتی رایان — تصویر، حرکت، گذار و موسیقی، همه محلی.

    python scripts/make_promo.py --lang fa --ratio 16x9
    python scripts/make_promo.py --lang fa --preview 1.6,4.6,8.4

خروجی: ``web/static/assets/video/promo-{fa,en}-{16x9,9x16,1x1}.mp4`` به‌همراه
پوستر هر نسخه. هیچ استوک، هیچ API و هیچ فایل بیرونی لازم نیست؛ فونت‌ها از
مخزن خوانده می‌شوند، تصویرها با PIL و صدا با numpy ساخته و با ffmpeg
(بستهٔ imageio-ffmpeg) چسبانده می‌شوند.

قاعدهٔ مهم: بوم همیشه RGB است و با ``ImageDraw.Draw(img, "RGBA")`` رنگ‌های
نیمه‌شفاف به‌درستی ترکیب می‌شوند؛ تصویرهای RGBA فقط با paste_alpha روی بوم
می‌نشینند.

صحنه‌ها: ۱) شعله‌ور شدن نشان و لوگوتایپ  ۲) تیتر جنبشی  ۳) گفتگوی زنده
۴) سه عدد راستین  ۵) فراخوان پایانی — با گذار موج نور بین صحنه‌ها.
"""
from __future__ import annotations

import argparse
import bisect
import math
import os
import random
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from fontcache import ensure_fonts  # noqa: E402

ensure_fonts()

from make_brand import _fa, orb  # noqa: E402

FPS = 30
DURATION = 16.4
BOUNDS = [0.0, 3.4, 6.8, 10.4, 13.4, DURATION]
TRANS = 0.5

NAVY = (6, 14, 34)
DEEP = (2, 6, 18)
CYAN = (56, 210, 255)
BLUE = (26, 99, 240)
ICE = (214, 234, 255)
WHITE = (255, 255, 255)

FONT_DIR = "/tmp"
BRAND = os.path.join(ROOT, "web", "static", "assets", "brand")

TEXT = {
    "fa": {
        "kicker": "ساخته‌شده از صفر",
        "tagline": "هوش مصنوعی، به زبان فارسی",
        "headline": ["فارسی را", "می‌فهمد، از صفر"],
        "chips": ["گفتگو و استریم", "ابزارهای محلی", "بدون API بیرونی"],
        "chat_title": "گفتگوی تازه",
        "chat_user": "یک بیت دربارهٔ شب و باران بگو",
        "chat_bot": "شب است و پنجره باز؛ باران برایت شعر می‌گوید.",
        "chat_hint": "پیامت را بنویس",
        "stats_title": "اندازه‌گیری روی همین سرور",
        "stats": [("۶٬۵۷۴٬۸۴۸", "پارامتر"), ("۸۴", "توکن بر ثانیه"), ("۰٫۰۴", "ثانیه، میانهٔ پاسخ")],
        "stats_note": "بدون GPU، بدون سرویس بیرونی، هزینهٔ صفر",
        "cta": "همین حالا امتحان کن",
        "url": "github.com/Taymaz1391/ai",
        "final_note": "متن‌باز، بدون API بیرونی، ساخته‌شده در ایران",
    },
}


# ------------------------------------------------------------------ کمکی‌ها
def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def fade(x: float, a: float, b: float) -> float:
    return clamp01((x - a) / max(b - a, 1e-6))


def ease_out(x: float) -> float:
    return 1 - (1 - clamp01(x)) ** 3


def ease_in_out(x: float) -> float:
    x = clamp01(x)
    return 3 * x * x - 2 * x * x * x


def spring(x: float) -> float:
    x = clamp01(x)
    return 1 - math.exp(-6.2 * x) * math.cos(9.0 * x)


def num(text: str, lang: str) -> str:
    if lang != "fa":
        return text
    return text.translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))


def font(weight: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, f"Vazirmatn-{weight}.ttf"), max(int(size), 6))


def put(draw: ImageDraw.ImageDraw, xy, txt: str, f, fill, anchor: str = "mm") -> None:
    draw.text(xy, txt, font=f, fill=fill, anchor=anchor)


def lh(f: ImageFont.FreeTypeFont) -> int:
    return int(f.size * 1.52)


def wrap(draw: ImageDraw.ImageDraw, text: str, f, max_w: float, lang: str) -> list[str]:
    lines: list[str] = []
    cur: list[str] = []
    for word in text.split():
        trial = " ".join(cur + [word])
        probe = _fa(trial) if lang == "fa" else trial
        if not cur or draw.textlength(probe, font=f) <= max_w:
            cur.append(word)
        else:
            lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines


def fa_slice(full: str, part: str) -> str:
    """تکه‌ای از متن فارسی را با شکل‌های درست حروف نشان می‌دهد.

    شکل هر حرف به همسایه‌هایش بستگی دارد؛ اگر «شب است و پنجره» را جدا
    reshaper کنیم، «ه» پایانی به «هٔ» وسط تبدیل می‌شود. راه‌حل: کل جمله را
    یک‌بار reshape و معکوس می‌کنیم و برش‌های پیشوندی را از انتهای همان رشته
    برمی‌داریم.
    """
    import arabic_reshaper

    visible = arabic_reshaper.reshape(full)[::-1]
    reshaped_part = arabic_reshaper.reshape(part)
    n = len(reshaped_part)
    if n >= len(visible):
        return visible
    return visible[len(visible) - n:]


def paste_alpha(img: Image.Image, sprite: Image.Image, pos) -> Image.Image:
    """چسباندن یک تصویر RGBA روی بوم RGB، فقط در کادر خودش (سریع)."""
    x, y = int(pos[0]), int(pos[1])
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img.width, x + sprite.width), min(img.height, y + sprite.height)
    if x1 <= x0 or y1 <= y0:
        return img
    crop = sprite.crop((x0 - x, y0 - y, x0 - x + (x1 - x0), y0 - y + (y1 - y0)))
    region = img.crop((x0, y0, x1, y1)).convert("RGBA")
    region.alpha_composite(crop)
    img.paste(region.convert("RGB"), (x0, y0))
    return img


def over(img: Image.Image, layer: Image.Image) -> Image.Image:
    """ترکیب یک لایهٔ تمام‌قاب RGBA روی بوم RGB."""
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


# ------------------------------------------------------------------ رندرر
class Renderer:
    SCENES = ("ignite", "statement", "chat", "stats", "cta")

    def __init__(self) -> None:
        self.orb512 = orb(512)
        self.orb256 = orb(256)
        self.mark = Image.open(os.path.join(BRAND, "mark-white.png")).convert("RGBA")
        self._bg: dict[tuple[int, int], Image.Image] = {}
        self._vig: dict[tuple[int, int], Image.Image] = {}
        self._noise: dict[tuple[int, int], list[Image.Image]] = {}
        self._bokeh = self._make_bokeh(96)
        rnd = random.Random(1402)
        self.stars = [(rnd.random(), rnd.random(), rnd.uniform(0.4, 1.9), rnd.uniform(0, 6.28)) for _ in range(96)]

    # ------------------------------------------------------------ بافت‌ها
    @staticmethod
    def _make_bokeh(size: int) -> Image.Image:
        n = size
        ys, xs = np.mgrid[0:n, 0:n].astype(np.float32)
        r = np.sqrt((xs - n / 2) ** 2 + (ys - n / 2) ** 2) / (n / 2)
        a = np.clip(1 - r, 0, 1) ** 2.2
        rgba = np.zeros((n, n, 4), np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = 176, 228, 255
        rgba[..., 3] = (a * 255).astype(np.uint8)
        return Image.fromarray(rgba, "RGBA")

    def bg(self, w: int, h: int) -> Image.Image:
        key = (w, h)
        if key not in self._bg:
            ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
            top = np.array((7, 17, 40), np.float32)
            mid = np.array((4, 10, 26), np.float32)
            bot = np.array(DEEP, np.float32)
            r1 = np.clip(ys / 0.55, 0, 1)
            r2 = np.clip((ys - 0.55) / 0.45, 0, 1)
            arr = top * (1 - r1) + mid * r1
            arr = arr * (1 - r2) + bot * r2
            arr = arr[:, None, :].repeat(w, axis=1)
            self._bg[key] = Image.fromarray(arr.astype(np.uint8), "RGB")
        return self._bg[key].copy()

    def vignette(self, w: int, h: int) -> Image.Image:
        key = (w, h)
        if key not in self._vig:
            mask = Image.new("L", (w, h), 0)
            d = ImageDraw.Draw(mask)
            d.ellipse([-w * 0.28, -h * 0.28, w * 1.28, h * 1.28], fill=255)
            mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * 0.09))
            dark = Image.new("RGBA", (w, h), (1, 4, 12, 255))
            dark.putalpha(Image.eval(mask, lambda v: int((255 - v) * 0.72)))
            self._vig[key] = dark
        return self._vig[key]

    def noise(self, w: int, h: int) -> list[Image.Image]:
        key = (w, h)
        if key not in self._noise:
            rng = np.random.default_rng(7)
            layers = []
            for _ in range(3):
                arr = rng.integers(0, 255, (h, w, 1), dtype=np.uint8).repeat(4, axis=2)
                arr[..., 0], arr[..., 1], arr[..., 2] = 150, 190, 255
                arr[..., 3] = 7
                layers.append(Image.fromarray(arr, "RGBA"))
            self._noise[key] = layers
        return self._noise[key]

    def aurora(self, w: int, h: int, t: float) -> Image.Image:
        q = 6
        small = Image.new("RGBA", (max(2, w // q), max(2, h // q)), (0, 0, 0, 0))
        d = ImageDraw.Draw(small, "RGBA")
        sw, sh = small.size
        blobs = [
            (0.26 + 0.05 * math.sin(t * 0.45), 0.24 + 0.03 * math.cos(t * 0.37), 0.60, (44, 126, 255, 112)),
            (0.80 + 0.04 * math.cos(t * 0.33), 0.28 + 0.04 * math.sin(t * 0.51), 0.50, (24, 190, 255, 88)),
            (0.50 + 0.06 * math.sin(t * 0.27 + 1.4), 0.88 + 0.03 * math.cos(t * 0.44), 0.66, (28, 80, 220, 96)),
        ]
        for fx, fy, fr, color in blobs:
            r = max(sw, sh) * fr
            cx, cy = fx * sw, fy * sh
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        small = small.filter(ImageFilter.GaussianBlur(max(sw, sh) * 0.15))
        return small.resize((w, h), Image.BILINEAR)

    def grid(self, w: int, h: int, t: float, strength: float = 1.0) -> Image.Image:
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer, "RGBA")
        s = min(w, h) / 720
        horizon = h * 0.74
        for i in range(-7, 8):
            xt = w / 2 + i * w * 0.024
            xb = w / 2 + i * w * 0.46
            d.line([(xt, horizon), (xb, h + 2)], fill=(96, 168, 255, int(20 * strength)), width=max(1, int(s)))
        for k in range(15):
            p = ((k + (t * 0.26) % 1.0) / 15) ** 2.0
            y = horizon + p * (h - horizon + 30)
            d.line([(0, y), (w, y)], fill=(96, 168, 255, int(2 + 30 * p * strength)), width=1)
        return layer

    def stars_layer(self, w: int, h: int, t: float) -> Image.Image:
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer, "RGBA")
        k = min(w, h) / 720
        for fx, fy, size, phase in self.stars:
            x = (fx * w + t * 5 * (0.4 + size * 0.2)) % w
            y = (fy * h - t * 8 * (0.3 + size * 0.15)) % h
            tw = 0.5 + 0.5 * math.sin(t * 1.6 + phase)
            a = int(24 + 90 * tw)
            r = 0.9 * size * k
            d.ellipse([x - r, y - r, x + r, y + r], fill=(170, 226, 255, a))
        for i in range(6):
            fx, fy, size, phase = self.stars[(i * 13) % len(self.stars)]
            r = (16 + 26 * size) * k * (0.9 + 0.1 * math.sin(t * 0.9 + phase))
            sprite = self._bokeh.resize((max(8, int(r * 2)), max(8, int(r * 2))), Image.BILINEAR)
            layer.alpha_composite(sprite, (int(fx * w - r), int(fy * h - r)))
        return layer

    def glow(self, w: int, h: int, blobs, blur_ratio: float = 0.10) -> Image.Image:
        q = 5
        small = Image.new("RGBA", (max(2, w // q), max(2, h // q)), (0, 0, 0, 0))
        d = ImageDraw.Draw(small, "RGBA")
        for (cx, cy, rx, ry, color) in blobs:
            d.ellipse([(cx - rx) / q, (cy - ry) / q, (cx + rx) / q, (cy + ry) / q], fill=color)
        small = small.filter(ImageFilter.GaussianBlur(max(1.0, min(w, h) * blur_ratio / q)))
        return small.resize((w, h), Image.BILINEAR)

    def base(self, w: int, h: int, t: float, grid_strength: float = 1.0) -> Image.Image:
        img = self.bg(w, h).convert("RGBA")
        img = Image.alpha_composite(img, self.aurora(w, h, t))
        img = Image.alpha_composite(img, self.grid(w, h, t, grid_strength))
        img = Image.alpha_composite(img, self.stars_layer(w, h, t))
        return img.convert("RGB")

    # -------------------------------------------------------------- اجزا
    def card(self, img, box, radius: int, fill=(10, 22, 46, 214), border=(96, 168, 255, 72)) -> Image.Image:
        w, h = img.size
        q = 5
        small = Image.new("RGBA", (max(2, w // q), max(2, h // q)), (0, 0, 0, 0))
        d = ImageDraw.Draw(small, "RGBA")
        x0, y0, x1, y1 = [v / q for v in box]
        d.rounded_rectangle([x0, y0 + 8 / q, x1, y1 + 10 / q], radius / q, fill=(1, 5, 14, 165))
        shadow = small.filter(ImageFilter.GaussianBlur(24 / q)).resize((w, h), Image.BILINEAR)
        img = over(img, shadow)
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer, "RGBA")
        ld.rounded_rectangle(box, radius=radius, fill=fill, outline=border, width=max(1, int(min(w, h) / 720)))
        return over(img, layer)

    def pill(self, img, box, text: str, f, p: float = 1.0) -> Image.Image:
        if p <= 0.01:
            return img
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer, "RGBA")
        radius = (box[3] - box[1]) / 2
        d.rounded_rectangle(box, radius=radius, fill=(255, 255, 255, int(18 * p)),
                            outline=(120, 196, 255, int(110 * p)), width=max(1, int(min(img.size) / 640)))
        d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2 + f.size * 0.04), text, font=f,
               fill=(232, 244, 255, int(252 * p)), anchor="mm")
        return over(img, layer)

    def orb_at(self, img, cx: float, cy: float, size: float, alpha: float = 1.0) -> Image.Image:
        size = max(6, int(size))
        sprite = (self.orb512 if size > 170 else self.orb256).resize((size, size), Image.LANCZOS)
        if alpha < 0.999:
            sprite = sprite.copy()
            sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
        return paste_alpha(img, sprite, (cx - size / 2, cy - size / 2))

    def mark_at(self, img, cx: float, y: float, width: float, alpha: float = 1.0) -> float:
        """لوگوتایپ «رایان» (بدون کره) — همیشه تصویر، هرگز متن."""
        scale = width / self.mark.width
        sprite = self.mark.resize((max(2, int(self.mark.width * scale)),
                                   max(2, int(self.mark.height * scale))), Image.LANCZOS)
        if alpha < 0.999:
            sprite = sprite.copy()
            sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
        paste_alpha(img, sprite, (cx - sprite.width / 2, y))
        return sprite.height

    def orb_face(self, img, cx: float, cy: float, size: float, alpha: float = 1.0,
                 rot: float = 0.0, wink: float = 0.0) -> Image.Image:
        """کرهٔ برند با چرخش نرم و چشمک: پلک با رنگ خودِ کره کشیده می‌شود."""
        size = max(8, int(size))
        sprite = (self.orb512 if size > 170 else self.orb256).resize((size, size), Image.LANCZOS).convert("RGBA")
        if wink > 0.015:
            # چشمک: دو پلک هم‌رنگِ کره از بالا و پایین به هم می‌رسند
            ex, ey = size * 0.5938, size * 0.4990
            er = size * 0.055
            band = er * 2 * (1.0 - 0.92 * min(1.0, wink))
            layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            px_layer = layer.load()
            x0, x1 = int(ex - er * 1.16), int(ex + er * 1.16)
            xl, xr = max(0, x0 - 3), min(size - 1, x1 + 3)
            ys = range(int(ey - er * 1.08), int(ey + er * 1.08) + 1)
            for y in ys:
                if abs(y - ey) <= band / 2:
                    continue
                yy = min(size - 1, max(0, y))
                cl = sprite.getpixel((xl, yy))
                cr = sprite.getpixel((xr, yy))
                span = max(1, xr - xl)
                for x in range(x0, x1 + 1):
                    t = (x - xl) / span
                    px_layer[x, y] = (int(cl[0] + (cr[0] - cl[0]) * t),
                                      int(cl[1] + (cr[1] - cl[1]) * t),
                                      int(cl[2] + (cr[2] - cl[2]) * t), 255)
            sprite = Image.alpha_composite(sprite, layer)
        if abs(rot) > 0.05:
            sprite = sprite.rotate(rot, resample=Image.BICUBIC, center=(size / 2, size / 2))
        if alpha < 0.999:
            sprite.putalpha(sprite.getchannel("A").point(lambda v: int(v * alpha)))
        return paste_alpha(img, sprite, (cx - size / 2, cy - size / 2))

    def sweep(self, img, p: float, strength: int = 30) -> Image.Image:
        if p <= 0 or p >= 1:
            return img
        w, h = img.size
        band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        x = -w * 0.35 + p * w * 1.7
        d = ImageDraw.Draw(band, "RGBA")
        d.polygon([(x, 0), (x + w * 0.12, 0), (x + w * 0.12 - h * 0.34, h), (x - h * 0.34, h)],
                  fill=(190, 235, 255, strength))
        band = band.filter(ImageFilter.GaussianBlur(20 * min(w, h) / 720))
        return over(img, band)

    # ------------------------------------------------------------ صحنه‌ها
    def scene_ignite(self, w: int, h: int, local: float, lang: str) -> Image.Image:
        cfg = TEXT[lang]
        s = min(w, h) / 720
        portrait = h > w * 1.12
        img = self.base(w, h, local)

        # موج ضربه
        for delay in (0.0, 0.16):
            p = clamp01((local - delay) / 1.15)
            if p <= 0 or p >= 1:
                continue
            r = min(w, h) * (0.12 + 0.55 * ease_out(p))
            ring = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            rd = ImageDraw.Draw(ring, "RGBA")
            cy = h * (0.315 if not portrait else 0.30)
            rd.ellipse([w / 2 - r, cy - r, w / 2 + r, cy + r],
                       outline=(130, 220, 255, int(130 * (1 - p) ** 2)), width=max(1, int(3 * s * (1 - p) + 1)))
            img = over(img, ring.filter(ImageFilter.GaussianBlur(2.0 * s)))

        pulse = 0.9 + 0.1 * math.sin(local * 2.4)
        orb_r = min(w, h) * (0.235 if not portrait else 0.245)
        orb_cy = h * (0.33 if not portrait else 0.355)
        img = over(img, self.glow(w, h, [
            (w / 2, orb_cy, orb_r * 2.3 * pulse, orb_r * 2.3 * pulse, (32, 128, 255, 108)),
            (w / 2, orb_cy, orb_r * 1.2, orb_r * 1.2, (86, 212, 255, 84)),
        ], 0.085))

        sway = 3.4 * math.sin(local * 1.7) * clamp01((local - 0.5) / 0.8)
        wink = 0.0
        for start in (1.8, 4.0, 6.0):
            phase = (local - start) / 0.34
            if 0 <= phase <= 1:
                wink = max(wink, math.sin(math.pi * phase))
        img = self.orb_face(img, w / 2, orb_cy, orb_r * 2 * (0.4 + 0.6 * spring(local / 0.95)),
                            clamp01(local / 0.32), rot=sway, wink=wink)

        # مدار چرخان
        orbit = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(orbit, "RGBA")
        rr = orb_r * 1.75
        box = [w / 2 - rr, orb_cy - rr * 0.34, w / 2 + rr, orb_cy + rr * 0.34]
        od.ellipse(box, outline=(120, 205, 255, 48), width=max(1, int(1.4 * s)))
        for k in range(3):
            a0 = local * 55 + k * 120
            od.arc(box, a0, a0 + 38, fill=(160, 234, 255, 160), width=max(2, int(2.2 * s)))
        img = over(img, orbit)

        # لوگوتایپ (تصویر، نه متن)
        wm_w = min(w * (0.30 if not portrait else 0.58), (300 if not portrait else 420) * s)
        wm_h = wm_w * self.mark.height / self.mark.width
        wm_y = orb_cy + orb_r + h * (0.055 if not portrait else 0.042)
        wa = clamp01((local - 0.55) / 0.7)
        if wa > 0:
            self.mark_at(img, w / 2, wm_y + (1 - ease_out(wa)) * 24 * s, wm_w, wa)

        ta = clamp01((local - 1.1) / 0.75)
        if ta > 0:
            d = ImageDraw.Draw(img, "RGBA")
            txt = cfg["tagline"] if lang != "fa" else _fa(cfg["tagline"])
            put(d, (w / 2, wm_y + wm_h + 34 * s), txt, font("Medium", 26 * s),
                (192, 218, 247, int(242 * ta)))

        return self.sweep(img, clamp01((local - 1.35) / 1.35))
    def scene_statement(self, w: int, h: int, local: float, lang: str) -> Image.Image:
        cfg = TEXT[lang]
        s = min(w, h) / 720
        portrait = h > w * 1.12
        img = self.base(w, h, local + 3.4, 0.7)
        d = ImageDraw.Draw(img, "RGBA")

        f = font("Black", (60 if not portrait else 50) * s)
        lines = cfg["headline"]
        longest = max((d.textlength(_fa(x) if lang == "fa" else x, font=f) for x in lines))
        if longest > w * 0.80:
            f = font("Black", f.size * (w * 0.80) / longest)
            longest = max((d.textlength(_fa(x) if lang == "fa" else x, font=f) for x in lines))
        block_h = lh(f) * len(lines)
        top = h * (0.30 if not portrait else 0.315)
        for i, line in enumerate(lines):
            p = clamp01((local - i * 0.22) / 0.62)
            if p <= 0:
                continue
            dy = (1 - ease_out(p)) * 40 * s
            color = (255, 255, 255, int(255 * p)) if i == 0 else (150, 222, 255, int(255 * p))
            put(d, (w / 2, top + i * lh(f) + f.size * 0.52 + dy),
                _fa(line) if lang == "fa" else line, f, color)

        up = clamp01((local - 0.95) / 0.7)
        if up > 0:
            lw = min(w * 0.46, 700 * s) * ease_out(up)
            yy = top + block_h + 2 * s
            grad = Image.new("RGBA", (max(2, int(lw)), max(2, int(7 * s))), (0, 0, 0, 0))
            gd = ImageDraw.Draw(grad, "RGBA")
            gd.rounded_rectangle([0, 0, lw, 7 * s], radius=4 * s, fill=(64, 200, 255, 220))
            img = paste_alpha(img, grad.filter(ImageFilter.GaussianBlur(3.4 * s)), (w / 2 - lw / 2, yy))
            d = ImageDraw.Draw(img, "RGBA")

        # تراشه‌ها
        cf = font("Bold", (23 if not portrait else 24) * s)
        chips = cfg["chips"]
        gap = 16 * s
        labels = [_fa(c) if lang == "fa" else c for c in chips]
        widths = [d.textlength(t, font=cf) + 62 * s for t in labels]
        if not portrait:
            longest_w = max(widths)
            if sum(widths) + gap * (len(widths) - 1) > w * 0.86:
                narrow = (w * 0.86 - gap * (len(widths) - 1)) / len(widths)
                cf = font("Bold", cf.size * (narrow - 62 * s) / max(longest_w - 62 * s, 1))
                widths = [d.textlength(t, font=cf) + 58 * s for t in labels]
        if portrait:
            for i, label in enumerate(labels):
                p = clamp01((local - 1.05 - i * 0.14) / 0.55)
                if p <= 0:
                    continue
                cy = h * 0.575 + i * 62 * s
                cw = min(widths[i] + 8 * s, w * 0.84)
                box = [w / 2 - cw / 2, cy - 23 * s + (1 - ease_out(p)) * 16 * s,
                       w / 2 + cw / 2, cy + 23 * s + (1 - ease_out(p)) * 16 * s]
                img = self.pill(img, box, label, cf, p)
        else:
            total = sum(widths) + gap * (len(chips) - 1)
            x = w / 2 - total / 2
            cy = h * 0.63
            for i, label in enumerate(labels):
                p = clamp01((local - 1.0 - i * 0.15) / 0.55)
                if p > 0:
                    box = [x, cy - 24 * s + (1 - ease_out(p)) * 18 * s,
                           x + widths[i], cy + 24 * s + (1 - ease_out(p)) * 18 * s]
                    img = self.pill(img, box, label, cf, p)
                x += widths[i] + gap

        na = clamp01((local - 1.75) / 0.7)
        if na > 0:
            d = ImageDraw.Draw(img, "RGBA")
            put(d, (w / 2, h * (0.80 if not portrait else 0.845)),
                _fa(cfg["kicker"]) if lang == "fa" else cfg["kicker"],
                font("Medium", 19 * s), (146, 190, 236, int(225 * na)))
        return img

    def scene_chat(self, w: int, h: int, local: float, lang: str) -> Image.Image:
        cfg = TEXT[lang]
        s = min(w, h) / 720
        portrait = h > w * 1.12
        rtl = lang == "fa"
        img = self.base(w, h, local + 6.8, 0.55)

        p = ease_out(clamp01(local / 0.7))
        cw = min(w * (0.72 if not portrait else 0.90), 660 * s)
        ch = min(h * 0.46, (306 if not portrait else 400) * s)
        x0 = w / 2 - cw / 2
        y0 = h * (0.50 if not portrait else 0.485) - ch / 2 + (1 - p) * 60 * s
        x1 = x0 + cw
        # لبهٔ شروع (راست در فارسی، چپ در انگلیسی)
        start_x = x1 if rtl else x0
        sign = -1 if rtl else 1
        box = [x0, y0, x1, y0 + ch]
        img = over(img, self.glow(w, h, [(w / 2, y0 + ch / 2, cw * 0.58, ch * 0.72, (26, 104, 240, 84))], 0.09))
        img = self.card(img, box, int(26 * s), fill=(8, 18, 40, 228), border=(96, 168, 255, 86))
        d = ImageDraw.Draw(img, "RGBA")

        # سرصفحهٔ کارت: نشان + عنوان در سمت شروع، سه نقطه در سمت مقابل
        head_y = y0 + 33 * s
        img = self.orb_at(img, start_x + sign * 34 * s, head_y, 30 * s)
        d = ImageDraw.Draw(img, "RGBA")
        put(d, (start_x + sign * 58 * s, head_y + 1),
            _fa(cfg["chat_title"]) if rtl else cfg["chat_title"],
            font("Bold", 19 * s), (228, 241, 255, 246), anchor="lm" if not rtl else "rm")
        far_x = x0 if rtl else x1
        for i in range(3):
            cx = far_x - sign * (26 * s + i * 16 * s)
            d.ellipse([cx - 3.4 * s, head_y - 3.4 * s, cx + 3.4 * s, head_y + 3.4 * s],
                      fill=(104, 158, 220, 175))
        d.line([(x0 + 1, head_y + 27 * s), (x1 - 1, head_y + 27 * s)], fill=(96, 168, 255, 56), width=1)

        # پیام کاربر: حباب در سمت شروع
        uf = font("Medium", 20 * s)
        utxt = _fa(cfg["chat_user"]) if rtl else cfg["chat_user"]
        uw = min(d.textlength(utxt, font=uf) + 46 * s, cw - 48 * s)
        uy = head_y + 64 * s
        up = ease_out(clamp01((local - 0.5) / 0.55))
        if up > 0:
            dy = (1 - up) * 16 * s
            ub = [start_x + sign * 26 * s, 0, 0, 0]
            outer = ub[0]
            inner = outer + sign * uw
            ubox = [min(outer, inner), uy - 4 * s + dy, max(outer, inner), uy + 46 * s + dy]
            layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer, "RGBA")
            ld.rounded_rectangle(ubox, radius=int(18 * s), fill=(38, 104, 226, int(220 * up)))
            ld.text(((ubox[0] + ubox[2]) / 2, (ubox[1] + ubox[3]) / 2 + uf.size * 0.04), utxt, font=uf,
                    fill=(242, 249, 255, int(252 * up)), anchor="mm")
            img = over(img, layer)
            d = ImageDraw.Draw(img, "RGBA")

        # پاسخ دستیار: نشان در سمت شروع، متن در ادامه
        bf = font("Medium", 20 * s)
        ax = start_x + sign * 38 * s
        bx = start_x + sign * 68 * s
        by = uy + 84 * s
        speaking = 0.75 <= local <= 2.9
        wink_here = max(0.0, math.sin((local - 1.0) / 0.3 * math.pi)) if 1.0 <= local <= 1.3 else 0.0
        img = self.orb_face(img, ax, by + 11 * s, 30 * s, clamp01((local - 0.75) / 0.4),
                            rot=(2.8 * math.sin(local * 3.1) if speaking else 0.0), wink=wink_here)
        d = ImageDraw.Draw(img, "RGBA")
        text_w = cw - 120 * s
        total_words = len(cfg["chat_bot"].split())
        shown_n = int(clamp01((local - 1.1) / 1.7) * total_words)
        if shown_n <= 0:
            for i in range(3):
                a = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(local * 9 - i * 0.7))
                d.ellipse([bx + sign * i * 13 * s - 3.5 * s, by - 4 * s,
                           bx + sign * i * 13 * s + 3.5 * s, by + 3 * s],
                          fill=(150, 205, 255, int(210 * a)))
        else:
            y_line, seen, last_w = by, 0, 0.0
            for line in wrap(d, cfg["chat_bot"], bf, text_w, lang):
                if seen >= shown_n:
                    break
                take = line.split()[: max(0, shown_n - seen)]
                if not take:
                    break
                part = " ".join(take)
                if rtl:
                    visual = fa_slice(cfg["chat_bot"], part)
                    put(d, (bx, y_line), visual, bf, (226, 241, 255, 247), anchor="rm")
                else:
                    visual = part
                    put(d, (bx, y_line), visual, bf, (226, 241, 255, 247), anchor="lm")
                last_w = d.textlength(visual, font=bf)
                y_line += lh(bf)
                seen += len(take)
            if shown_n < total_words:
                caret = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(local * 8))
                cx = bx + sign * (last_w + 8 * s)
                d.rectangle([cx - 1.5 * s, y_line - lh(bf) - 9 * s, cx + 1.5 * s, y_line - lh(bf) + 9 * s],
                            fill=(90, 210, 255, int(230 * caret)))

        # نوار نوشتن پایین کارت
        foot_y = y0 + ch - 32 * s
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer, "RGBA")
        ld.rounded_rectangle([x0 + 22 * s, foot_y - 17 * s, x1 - 22 * s, foot_y + 17 * s],
                             radius=17 * s, fill=(255, 255, 255, 16), outline=(96, 168, 255, 54), width=1)
        ld.text((start_x + sign * 30 * s, foot_y), _fa(cfg["chat_hint"]) if rtl else cfg["chat_hint"],
                font=font("Regular", 17 * s), fill=(144, 184, 226, 230), anchor="lm" if not rtl else "rm")
        scx = far_x - sign * 34 * s
        ld.ellipse([scx - 13 * s, foot_y - 13 * s, scx + 13 * s, foot_y + 13 * s], fill=(46, 160, 255, 240))
        ld.polygon([(scx + sign * 4 * s, foot_y), (scx - sign * 7 * s, foot_y - 5.6 * s),
                    (scx - sign * 7 * s, foot_y + 5.6 * s)], fill=(255, 255, 255, 246))
        return over(img, layer)

    def scene_stats(self, w: int, h: int, local: float, lang: str) -> Image.Image:
        cfg = TEXT[lang]
        s = min(w, h) / 720
        portrait = h > w * 1.12
        img = self.base(w, h, local + 10.4, 0.5)

        cx, cy = w / 2, h * (0.40 if not portrait else 0.37)
        r = min(w, h) * (0.19 if not portrait else 0.23)
        prog = ease_out(clamp01((local - 0.3) / 1.5))
        img = over(img, self.glow(w, h, [(cx, cy, r * 1.7, r * 1.7, (30, 120, 255, 100))], 0.10))
        d = ImageDraw.Draw(img, "RGBA")

        put(d, (cx, h * (0.15 if not portrait else 0.14)),
            _fa(cfg["stats_title"]) if lang == "fa" else cfg["stats_title"],
            font("Bold", 26 * s), (196, 220, 248, int(248 * clamp01((local - 0.1) / 0.6))))

        ring = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        rd = ImageDraw.Draw(ring, "RGBA")
        rd.arc([cx - r, cy - r, cx + r, cy + r], 0, 360, fill=(80, 140, 220, 62), width=int(8 * s))
        rd.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * prog, fill=(86, 214, 255, 235), width=int(8 * s))
        img = over(img, ring.filter(ImageFilter.GaussianBlur(0.8 * s)))
        d = ImageDraw.Draw(img, "RGBA")

        big = cfg["stats"][0]
        bf_big = font("Black", (54 if not portrait else 60) * s)
        big_txt = num(big[0], lang)
        room = r * 1.62
        if d.textlength(big_txt, font=bf_big) > room:
            bf_big = font("Black", bf_big.size * room / d.textlength(big_txt, font=bf_big))
        put(d, (cx, cy - 6 * s), big_txt, bf_big, (255, 255, 255, 255))
        put(d, (cx, cy + 52 * s), _fa(big[1]) if lang == "fa" else big[1], font("Medium", 20 * s),
            (176, 208, 245, 235))

        tiles = cfg["stats"][1:]
        if portrait:
            bw = min(w * 0.74, 560 * s)
            for i, (value, label) in enumerate(tiles):
                ap = ease_out(clamp01((local - 0.8 - i * 0.16) / 0.6))
                if ap <= 0:
                    continue
                yy = h * 0.66 + i * 92 * s + (1 - ap) * 18 * s
                layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer, "RGBA")
                ld.rounded_rectangle([w / 2 - bw / 2, yy, w / 2 + bw / 2, yy + 74 * s], radius=18 * s,
                                     fill=(16, 34, 64, int(196 * ap)), outline=(96, 168, 255, int(74 * ap)), width=1)
                ld.text((w / 2, yy + 26 * s), num(value, lang), font=font("Black", 27 * s),
                        fill=(234, 246, 255, int(250 * ap)), anchor="mm")
                ld.text((w / 2, yy + 55 * s), _fa(label) if lang == "fa" else label, font=font("Medium", 15 * s),
                        fill=(162, 198, 240, int(232 * ap)), anchor="mm")
                img = over(img, layer)
        else:
            gap = 24 * s
            bw, bh = (w * 0.72 - gap) / 2, 96 * s
            x = w / 2 - (bw * 2 + gap) / 2
            for i, (value, label) in enumerate(tiles):
                ap = ease_out(clamp01((local - 0.8 - i * 0.18) / 0.6))
                if ap <= 0:
                    continue
                bx = x + i * (bw + gap)
                byy = h * 0.655 + (1 - ap) * 20 * s
                layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                ld = ImageDraw.Draw(layer, "RGBA")
                ld.rounded_rectangle([bx, byy, bx + bw, byy + bh], radius=20 * s,
                                     fill=(16, 34, 64, int(196 * ap)), outline=(96, 168, 255, int(74 * ap)), width=1)
                ld.text((bx + bw / 2, byy + 36 * s), num(value, lang), font=font("Black", 34 * s),
                        fill=(234, 246, 255, int(250 * ap)), anchor="mm")
                ld.text((bx + bw / 2, byy + 70 * s), _fa(label) if lang == "fa" else label,
                        font=font("Medium", 16 * s), fill=(162, 198, 240, int(232 * ap)), anchor="mm")
                img = over(img, layer)

        na = clamp01((local - 1.6) / 0.7)
        if na > 0:
            d = ImageDraw.Draw(img, "RGBA")
            put(d, (cx, h * (0.87 if not portrait else 0.905)),
                _fa(cfg["stats_note"]) if lang == "fa" else cfg["stats_note"],
                font("Regular", 17 * s), (134, 172, 216, int(222 * na)))
        return self.sweep(img, clamp01((local - 0.25) / 1.7), 24)

    def scene_cta(self, w: int, h: int, local: float, lang: str) -> Image.Image:
        cfg = TEXT[lang]
        s = min(w, h) / 720
        portrait = h > w * 1.12
        img = self.base(w, h, local + 13.4, 0.4)
        cx = w / 2
        oy = h * (0.085 if portrait else 0.0)   # در قاب عمودی بلوک را وسط می‌کشیم
        p = ease_out(clamp01(local / 0.8))
        img = over(img, self.glow(w, h, [
            (cx, h * 0.36 + oy, min(w, h) * 0.62, min(w, h) * 0.46, (30, 118, 255, int(112 * p))),
        ], 0.10))
        d = ImageDraw.Draw(img, "RGBA")

        orb_s = 84 * s if not portrait else 104 * s
        img = self.orb_face(img, cx, h * (0.105 if not portrait else 0.125) + oy, orb_s * (0.6 + 0.4 * p),
                            p, rot=2.6 * math.sin(local * 1.9),
                            wink=max(0.0, math.sin(max(0.0, local - 0.9) / 0.3 * math.pi)) if 0.9 <= local <= 1.2 else 0.0)
        wm_w = min(w * (0.31 if not portrait else 0.54), 340 * s)
        wm_top = h * (0.182 if not portrait else 0.205) + oy
        self.mark_at(img, cx, wm_top, wm_w, p)

        ta = clamp01((local - 0.3) / 0.7)
        if ta > 0:
            put(d, (cx, h * (0.472 if not portrait else 0.445) + oy),
                _fa(cfg["tagline"]) if lang == "fa" else cfg["tagline"],
                font("Black", (38 if not portrait else 40) * s), (255, 255, 255, int(252 * ta)))

        bp = ease_out(clamp01((local - 0.65) / 0.6))
        if bp > 0:
            bf = font("Bold", 25 * s)
            label = _fa(cfg["cta"]) if lang == "fa" else cfg["cta"]
            bw = d.textlength(label, font=bf) + 100 * s
            bh = 62 * s
            bx, by = cx - bw / 2, h * (0.578 if not portrait else 0.552) + oy + (1 - bp) * 22 * s
            img = over(img, self.glow(w, h, [(cx, by + bh / 2, bw * 0.62, bh * 1.2, (46, 150, 255, int(150 * bp)))], 0.05))
            layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer, "RGBA")
            ld.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh / 2, fill=(40, 132, 255, int(248 * bp)))
            # براقیت شیشه‌ای: گرادیان عمودی که با جرم دکمه بریده می‌شود
            gloss = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            gd = ImageDraw.Draw(gloss, "RGBA")
            for i in range(int(bh)):
                t = i / max(1.0, bh)
                a = int(38 * bp * max(0.0, 1 - t / 0.62) ** 1.5)
                if a <= 0:
                    continue
                gd.rectangle([bx, by + i, bx + bw, by + i + 1], fill=(255, 255, 255, a))
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([bx, by, bx + bw, by + bh], radius=bh / 2, fill=255)
            gloss.putalpha(Image.composite(gloss.getchannel("A"), Image.new("L", (w, h), 0), mask))
            ld.text((cx, by + bh / 2 + 1), label, font=bf, fill=(255, 255, 255, int(255 * bp)), anchor="mm")
            img = over(img, Image.alpha_composite(layer, gloss))
            sheen = (local * 0.85) % 1.9
            if sheen < 0.55:
                sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                sd = ImageDraw.Draw(sh, "RGBA")
                x = bx - bw * 0.25 + (sheen / 0.55) * bw * 1.5
                sd.polygon([(x, by), (x + 26 * s, by), (x + 6 * s, by + bh), (x - 20 * s, by + bh)],
                           fill=(255, 255, 255, int(96 * bp)))
                img = over(img, sh.filter(ImageFilter.GaussianBlur(2.6 * s)))
            d = ImageDraw.Draw(img, "RGBA")

        ua = clamp01((local - 1.0) / 0.7)
        if ua > 0:
            put(d, (cx, h * (0.706 if not portrait else 0.652) + oy), cfg["url"], font("Bold", 22 * s),
                (128, 216, 255, int(246 * ua)))
        fa_ = clamp01((local - 1.3) / 0.7)
        if fa_ > 0:
            put(d, (cx, h * (0.762 if not portrait else 0.705)),
                _fa(cfg["final_note"]) if lang == "fa" else cfg["final_note"],
                font("Regular", 17 * s), (150, 186, 228, int(222 * fa_)))
        return img

    def scene(self, index: int, w: int, h: int, t: float, lang: str) -> Image.Image:
        local = max(t - BOUNDS[index], 0.0)
        return getattr(self, "scene_" + self.SCENES[index])(w, h, local, lang)

    # ------------------------------------------------------------- بوم کامل
    def frame(self, w: int, h: int, t: float, lang: str, scale: float = 1.0) -> Image.Image:
        if scale != 1.0:
            rw, rh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
            return self.frame(rw, rh, t, lang).resize((w, h), Image.LANCZOS)
        return self._paint(w, h, t, lang, bar=True)

    def _paint(self, w: int, h: int, t: float, lang: str, bar: bool) -> Image.Image:
        t = min(max(t, 0.0), DURATION - 1e-3)
        index = max(0, min(bisect.bisect_right(BOUNDS, t) - 1, len(self.SCENES) - 1))
        img = self.scene(index, w, h, t, lang)

        if index > 0 and (t - BOUNDS[index]) < TRANS:
            # گذار نرم + یک تیغهٔ نور مورب که صحنه را عوض می‌کند
            prev = self.scene(index - 1, w, h, BOUNDS[index] - 0.001, lang)
            u = min(1.0, (t - BOUNDS[index]) / 0.24)
            img = Image.blend(prev, img, ease_in_out(u))
            x = (-0.30 + 1.60 * min(1.0, (t - BOUNDS[index]) / TRANS)) * w
            bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bar, "RGBA")
            bd.polygon([(x, 0), (x + w * 0.03, 0),
                        (x + w * 0.03 - h * 0.20, h), (x - h * 0.20, h)],
                       fill=(168, 232, 255, int(96 * math.sin(math.pi * min(1.0, (t - BOUNDS[index]) / TRANS)) ** 0.8)))
            img = over(img, bar.filter(ImageFilter.GaussianBlur(6 * min(w, h) / 720)))

        img = over(img, self.noise(w, h)[int(t * 12) % 3])
        img = over(img, self.vignette(w, h))

        if not bar:
            return img
        d = ImageDraw.Draw(img, "RGBA")
        prog = t / DURATION
        bar_h = max(3, int(min(w, h) / 220))
        if lang == "fa":
            x0, x1 = w - int(w * prog), w
        else:
            x0, x1 = 0, int(w * prog)
        d.rectangle([x0, h - bar_h, x1, h], fill=(64, 208, 255, 200))
        d.rectangle([x0, h - bar_h, x1, h - bar_h + max(1, bar_h // 3)], fill=(196, 242, 255, 230))
        return img

    def cover(self, w: int, h: int, t: float, lang: str, scale: float = 1.0) -> Image.Image:
        if scale != 1.0:
            rw, rh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
            return self.cover(rw, rh, t, lang).resize((w, h), Image.LANCZOS)
        return self._paint(w, h, t, lang, bar=False)


# ------------------------------------------------------------------ صدا
def synth_audio(path: str, seconds: float = DURATION, sr: int = 44100) -> None:
    n = int(seconds * sr)
    rng = np.random.default_rng(11)
    mix = np.zeros((n, 2), dtype=np.float32)
    beat = 60.0 / 96.0

    def add(sig: np.ndarray, start: float, amp: float = 1.0, pan: float = 0.0) -> None:
        i0 = int(start * sr)
        if i0 >= n or i0 < 0:
            return
        i1 = min(n, i0 + len(sig))
        s = sig[: i1 - i0] * amp
        mix[i0:i1, 0] += s * (1.0 - max(0.0, pan) * 0.6)
        mix[i0:i1, 1] += s * (1.0 + min(0.0, pan) * 0.6)

    def pad(freq: float, dur: float) -> np.ndarray:
        tt = np.arange(int(dur * sr)) / sr
        w = (np.sin(2 * np.pi * freq * tt) * 0.55
             + np.sin(2 * np.pi * freq * 1.5 * tt) * 0.16
             + np.sin(2 * np.pi * freq * 2.02 * tt) * 0.11
             + np.sin(2 * np.pi * freq * 3.01 * tt) * 0.045)
        env = np.minimum(1, tt / 0.4) * np.exp(-tt * 0.20)
        return (w * env).astype(np.float32)

    def pluck(freq: float, dur: float = 0.42) -> np.ndarray:
        tt = np.arange(int(dur * sr)) / sr
        w = np.sin(2 * np.pi * freq * tt) + 0.3 * np.sin(2 * np.pi * freq * 2 * tt)
        return ((w * np.exp(-tt * 5.5) * np.minimum(1, tt / 0.008))).astype(np.float32)

    def kick() -> np.ndarray:
        tt = np.arange(int(0.34 * sr)) / sr
        f = 132 * np.exp(-tt * 17) + 46
        return (np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt * 6.5)).astype(np.float32)

    def hat() -> np.ndarray:
        tt = np.arange(int(0.09 * sr)) / sr
        noise = rng.normal(0, 1, len(tt)).astype(np.float32)
        noise = np.diff(noise, prepend=0.0) * 0.5
        return (noise * np.exp(-tt * 46)).astype(np.float32)

    def whoosh(dur: float = 0.62) -> np.ndarray:
        tt = np.arange(int(dur * sr)) / sr
        noise = rng.normal(0, 1, len(tt)).astype(np.float32)
        kernel = np.hanning(96)
        noise = np.convolve(noise, kernel / kernel.sum(), mode="same")
        return (noise * np.sin(np.pi * tt / dur) ** 2.2).astype(np.float32)

    def boom() -> np.ndarray:
        tt = np.arange(int(1.8 * sr)) / sr
        low = np.sin(2 * np.pi * (54 * np.exp(-tt * 1.2) + 30) * tt) * np.exp(-tt * 2.4)
        thump = rng.normal(0, 1, len(tt)).astype(np.float32) * np.exp(-tt * 15) * 0.22
        return (low + thump).astype(np.float32)

    chords = [
        (110.00, 164.81, 220.00, 261.63),  # Am
        (87.31, 130.81, 174.61, 220.00),   # F
        (130.81, 196.00, 261.63, 329.63),  # C
        (98.00, 146.83, 196.00, 246.94),   # G
    ]
    bar = 4 * beat
    for b in range(int(math.ceil(seconds / bar)) + 1):
        start = b * bar
        chord = chords[b % 4]
        for f in chord[1:]:
            add(pad(f, bar + 0.4), start, amp=0.07)
        add(pad(chord[0] / 2, bar + 0.4), start, amp=0.105)

    arp = [0, 2, 1, 3, 2, 1, 3, 2]
    step = beat / 2
    tt, idx = 3.4, 0
    while tt < 13.4:
        chord = chords[int((tt - 3.4) // bar) % 4]
        add(pluck(chord[arp[idx % len(arp)]] * 2), tt, amp=0.08, pan=0.25 if idx % 2 else -0.25)
        tt += step
        idx += 1

    tt = 3.4
    while tt < 13.35:
        add(kick(), tt, amp=0.46)
        add(hat(), tt + beat / 2, amp=0.16, pan=0.3)
        tt += beat

    for mark in BOUNDS[1:-1]:
        add(whoosh(), mark - 0.58, amp=0.32, pan=-0.2)
    add(boom(), 0.04, amp=0.5)
    add(boom(), 13.32, amp=0.46)
    for f in (261.63, 329.63, 392.00, 523.25):
        add(pad(f, 3.0), 13.4, amp=0.055)

    mix = np.tanh(mix * 1.22)
    peak = float(np.abs(mix).max()) or 1.0
    mix = mix / peak * 0.88
    fn = int(0.4 * sr)
    mix[-fn:] *= np.linspace(1, 0, fn)[:, None]
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(path, "wb") as fh:
        fh.setnchannels(2)
        fh.setsampwidth(2)
        fh.setframerate(sr)
        fh.writeframes(pcm.tobytes())


# ------------------------------------------------------------------- رندر
SIZES = {"16x9": (1280, 720), "9x16": (720, 1280), "1x1": (1080, 1080)}
SS = {"16x9": 1.5, "9x16": 1.5, "1x1": 1.3}


def render(out_path: str, key: str, lang: str, renderer: Renderer, ffmpeg: str, audio: str,
           fps: int = FPS, crf: str = "21", preset: str = "medium") -> None:
    w, h = SIZES[key]
    scale = SS[key]
    # صحنه‌ها با SS برابر بزرگ‌تر ساخته و پیش از ارسال کوچک می‌شوند؛
    # ابعاد ورودی ffmpeg همان ابعاد نهایی است.
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-i", audio,
        "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-level", "4.1", "-g", "60", "-tune", "film",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(int(round(DURATION * fps))):
        frame = renderer.frame(w, h, i / fps, lang, scale=scale)
        if frame.mode != "RGB" or frame.size != (w, h):
            frame = frame.convert("RGB").resize((w, h), Image.LANCZOS) if frame.size != (w, h) else frame.convert("RGB")
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"ffmpeg failed: {out_path}")


def poster(renderer: Renderer, key: str, lang: str, path: str, at: float) -> None:
    w, h = SIZES[key]
    img = renderer.cover(w, h, at, lang, scale=SS[key])
    img.save(path, quality=90, optimize=True, progressive=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "static", "assets", "video"))
    ap.add_argument("--lang", default="fa", choices=["fa"], help="سایت تک‌زبانه است")
    ap.add_argument("--ratio", default="", help="16x9 یا 9x16 یا 1x1 (خالی = همه)")
    ap.add_argument("--preview", default="", help="زمان‌ها با کاما، مثلاً 1.6,4.6")
    ap.add_argument("--fps", type=int, default=FPS)
    ap.add_argument("--crf", default="21")
    ap.add_argument("--preset", default="medium")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    renderer = Renderer()
    langs = [args.lang]

    if args.preview:
        for lang in langs:
            for time in args.preview.split(","):
                t = float(time)
                for key in ([args.ratio] if args.ratio else ["16x9"]):
                    w, h = SIZES[key]
                    path = f"/tmp/preview-{lang}-{key}-{t:.2f}.png"
                    renderer.cover(w, h, t, lang).save(path)
                    print(path, flush=True)
        return

    keys = [args.ratio] if args.ratio else list(SIZES)
    for lang in langs:
        audio = os.path.join("/tmp", f"rayan-promo-{lang}.wav")
        synth_audio(audio)
        for key in keys:
            out = os.path.join(args.out, f"promo-{lang}-{key}.mp4")
            print(f"[promo] {lang} {key} → {out}", flush=True)
            render(out, key, lang, renderer, ffmpeg, audio, args.fps, args.crf, args.preset)
            poster(renderer, key, lang, os.path.join(args.out, f"promo-{lang}-{key}-poster.jpg"), 2.35)
        poster(renderer, "16x9", lang, os.path.join(args.out, f"promo-{lang}-poster.jpg"), 2.35)
    print("[promo] done", flush=True)


if __name__ == "__main__":
    main()
