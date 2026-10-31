#!/usr/bin/env python3
"""ساخت ویدیوهای تبلیغاتی رایان — افکت، حرکت و موسیقی، همه محلی.

    python scripts/make_promo.py --out web/static/assets/video --lang fa

خروجی برای هر زبان سه نسبت تصویر است (۱۶:۹، ۹:۱۶، ۱:۱) به‌همراه پوستر.
موسیقی با numpy ساخته می‌شود و با ffmpeg (بستهٔ imageio-ffmpeg) روی تصویر
سوار می‌شود؛ هیچ فایل صوتی یا تصویری بیرونی لازم نیست.
"""
from __future__ import annotations

import argparse
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

from make_brand import _fa, _font, orb  # noqa: E402

FPS = 30
DURATION = 12.0
NAVY = (5, 11, 26)
NAVY_2 = (8, 20, 44)
CYAN = (56, 210, 255)
BLUE = (26, 99, 240)
WHITE = (255, 255, 255)
MUTED = (150, 178, 214)

TEXT = {
    "fa": {
        "tagline": "هوش مصنوعی، به زبان فارسی",
        "scene_b_title": "یک محصول کامل، بدون هیچ API بیرونی",
        "scene_b_items": ["گفتگو و استریم", "ابزارهای محلی", "استودیو تصویر", "پنل مدیریت"],
        "scene_c_big": "۶٫۵۷ میلیون",
        "scene_c_sub": "پارامتر، آموزش‌دیده از صفر",
        "scene_c_items": ["بدون API خارجی", "۸۰ توکن بر ثانیه", "امن و خودمیزبان"],
        "cta": "همین حالا امتحان کن",
        "url": "taymaz1391.github.io/ai",
    },
    "en": {
        "tagline": "Persian AI, built from scratch",
        "scene_b_title": "A complete product, zero external APIs",
        "scene_b_items": ["Chat + streaming", "Local tools", "Image studio", "Admin panel"],
        "scene_c_big": "6.57 million",
        "scene_c_sub": "parameters, trained from zero",
        "scene_c_items": ["0 external APIs", "80 tokens/sec", "self-hosted & secure"],
        "cta": "Try it now",
        "url": "taymaz1391.github.io/ai",
    },
}


# ------------------------------------------------------------------ کمکی‌ها
def ease(t: float) -> float:
    return 1 - (1 - t) ** 3


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_center(draw, cx, cy, text, font, fill, spacing=0):
    w, h = text_size(draw, text, font)
    if spacing:
        total = w + spacing * max(len(text) - 1, 0)
        x = cx - total / 2
        for ch in text:
            draw.text((x, cy - h / 2), ch, font=font, fill=fill)
            x += draw.textlength(ch, font=font) + spacing
        return
    draw.text((cx - w / 2, cy - h / 2), text, font=font, fill=fill)


_BG_CACHE: dict[tuple[int, int], Image.Image] = {}
_ORB_BASE: Image.Image | None = None


def _base_bg(w: int, h: int) -> Image.Image:
    key = (w, h)
    if key not in _BG_CACHE:
        ys = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        top = np.array(NAVY, dtype=np.float32)
        bottom = np.array((3, 7, 18), dtype=np.float32)
        arr = (top * (1 - ys) + bottom * ys)[:, None, :].repeat(w, axis=1)
        _BG_CACHE[key] = Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")
    return _BG_CACHE[key].copy()


def background(w: int, h: int, t: float) -> Image.Image:
    """گرادیان عمودی + دو هالهٔ نورانی متحرک."""
    img = _base_bg(w, h)

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx = w * (0.30 + 0.03 * math.sin(t * 0.7))
    cy = h * (0.24 + 0.02 * math.cos(t * 0.9))
    r = max(w, h) * 0.55
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(14, 72, 170, 120))
    cx2 = w * (0.78 + 0.04 * math.cos(t * 0.6))
    cy2 = h * (0.82 + 0.03 * math.sin(t * 0.8))
    r2 = max(w, h) * 0.45
    gd.ellipse([cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2], fill=(8, 44, 120, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(max(w, h) * 0.08))
    img = Image.alpha_composite(img, glow)

    # نقطه‌های ریز شبکه‌ای
    dots = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    step = max(28, int(min(w, h) / 22))
    off = int((t * 12) % step)
    for x in range(-step, w + step, step):
        for y in range(-step, h + step, step):
            dd.point((x + off, y + off), fill=(120, 190, 255, 26))
    img = Image.alpha_composite(img, dots)
    return img


def sparkles(img: Image.Image, t: float, seed: int = 7) -> Image.Image:
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rnd = random.Random(seed)
    for _ in range(46):
        x = rnd.random() * w
        y = rnd.random() * h
        phase = (t * 0.9 + rnd.random() * 6.28)
        a = int(40 + 90 * (0.5 + 0.5 * math.sin(phase)))
        r = rnd.random() * 2.2 + 0.6
        d.ellipse([x - r, y - r, x + r, y + r], fill=(150, 220, 255, a))
    return Image.alpha_composite(img, layer)


def sweep(img: Image.Image, progress: float) -> Image.Image:
    """نوار نور مورب که صحنه را جارو می‌کند."""
    w, h = img.size
    band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = -w * 0.4 + progress * (w * 1.8)
    d = ImageDraw.Draw(band)
    d.polygon([(x, 0), (x + w * 0.16, 0), (x + w * 0.16 - h * 0.3, h), (x - h * 0.3, h)],
              fill=(190, 235, 255, 26))
    band = band.filter(ImageFilter.GaussianBlur(18))
    return Image.alpha_composite(img, band)


def vignette(img: Image.Image) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-w * 0.25, -h * 0.25, w * 1.25, h * 1.25], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * 0.12))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 120))
    dark.putalpha(Image.eval(mask, lambda v: 255 - v))
    return Image.alpha_composite(img, dark)


def chip(img: Image.Image, box, label: str, font, alpha: float, accent=CYAN) -> Image.Image:
    if alpha <= 0.01:
        return img
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    radius = (y1 - y0) / 2
    d.rounded_rectangle(box, radius=radius, fill=(255, 255, 255, int(16 * alpha)),
                        outline=accent + (int(90 * alpha),), width=2)
    a = int(235 * alpha)
    draw_center(d, (x0 + x1) / 2, (y0 + y1) / 2, label, font, (235, 245, 255, a))
    return Image.alpha_composite(img, layer)


# -------------------------------------------------------------------- صحنه‌ها
def frame(w: int, h: int, t: float, lang: str, wordmark_white: Image.Image,
          wordmark_ink: Image.Image, bar: bool = True) -> Image.Image:
    cfg = TEXT[lang]
    s = min(w, h) / 720.0
    img = background(w, h, t)
    img = sparkles(img, t, seed=int(w + h))

    # ----- صحنهٔ ۱: لوگو
    if t < 3.4:
        p = ease(clamp(t / 1.4))
        zoom = 1.0 + 0.06 * math.sin(t * 2.0)
        size = int(min(w, h) * (0.30 + 0.35 * p) * zoom)
        global _ORB_BASE
        if _ORB_BASE is None:
            _ORB_BASE = orb(512)
        icon = _ORB_BASE.resize((max(size, 8), max(size, 8)), Image.LANCZOS)
        halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        rr = size * 0.95
        hd.ellipse([w / 2 - rr, h * 0.40 - rr, w / 2 + rr, h * 0.40 + rr],
                   fill=(30, 130, 255, int(90 * p)))
        halo = halo.filter(ImageFilter.GaussianBlur(size * 0.12))
        img = Image.alpha_composite(img, halo)
        img.alpha_composite(icon, (int(w / 2 - icon.width / 2), int(h * 0.40 - icon.height / 2)))

        wm = wordmark_white.copy()
        target_w = int(min(w * 0.52, 560 * s))
        ratio = target_w / wm.width
        wm = wm.resize((target_w, int(wm.height * ratio)), Image.LANCZOS)
        wa = int(255 * clamp((t - 0.8) / 0.9))
        if wa > 0:
            wm.putalpha(wm.getchannel("A").point(lambda v: int(v * wa / 255)))
            img.alpha_composite(wm, (int(w / 2 - wm.width / 2), int(h * 0.63)))
        ta = clamp((t - 1.5) / 0.8)
        if ta > 0:
            d = ImageDraw.Draw(img)
            draw_center(d, w / 2, h * 0.80, _fa(cfg["tagline"]) if lang == "fa" else cfg["tagline"],
                        _font("Vazirmatn-Medium.ttf", int(30 * s)),
                        (176, 205, 240, int(240 * ta)))
        img = sweep(img, clamp((t - 1.9) / 1.2))

    # ----- صحنهٔ ۲: فهرست قابلیت‌ها
    elif t < 6.6:
        local = t - 3.4
        d = ImageDraw.Draw(img)
        p = ease(clamp(local / 0.7))
        title = cfg["scene_b_title"]
        if lang == "fa":
            title = _fa(title)
        title_y = h * (0.22 if h > w else 0.17)
        draw_center(d, w / 2, title_y, title, _font("Vazirmatn-Bold.ttf", int(34 * s)),
                    (255, 255, 255, int(255 * p)))
        cols = 2 if w < h else 4
        rows = math.ceil(len(cfg["scene_b_items"]) / cols)
        cw = w * (0.84 if h > w else 0.78) / cols
        ch = (124 if h > w else 96) * s
        y0 = h * (0.46 if h > w else 0.44)
        for i, item in enumerate(cfg["scene_b_items"]):
            ap = ease(clamp((local - 0.25 - i * 0.18) / 0.5))
            if ap <= 0:
                continue
            row, col = divmod(i, cols)
            cx = w / 2 + (col - (cols - 1) / 2) * cw
            cy = y0 + row * (ch + (30 if h > w else 22) * s)
            box = (cx - cw * 0.46, cy - ch / 2, cx + cw * 0.46, cy + ch / 2)
            label = _fa(item) if lang == "fa" else item
            img = chip(img, box, label, _font("Vazirmatn-Bold.ttf", int(24 * s)), ap)
        if h <= w:
            if _ORB_BASE is None:
                _ORB_BASE = orb(512)
            icon = _ORB_BASE.resize((int(min(w, h) * 0.12),) * 2, Image.LANCZOS)
            img.alpha_composite(icon, (int(w * 0.06), int(h * 0.78)))
        else:
            wm = wordmark_white.copy()
            tw = int(w * 0.42)
            wm = wm.resize((tw, int(wm.height * tw / wm.width)), Image.LANCZOS)
            img.alpha_composite(wm, (int(w / 2 - wm.width / 2), int(h * 0.845)))

    # ----- صحنهٔ ۳: عدد بزرگ
    elif t < 9.8:
        local = t - 6.6
        d = ImageDraw.Draw(img)
        p = ease(clamp(local / 0.6))
        big = cfg["scene_c_big"]
        if lang == "fa":
            big = _fa(big)
        draw_center(d, w / 2, h * 0.36, big, _font("Vazirmatn-Black.ttf", int(86 * s)),
                    (255, 255, 255, int(255 * p)))
        sub = cfg["scene_c_sub"]
        if lang == "fa":
            sub = _fa(sub)
        draw_center(d, w / 2, h * 0.49, sub, _font("Vazirmatn-Medium.ttf", int(28 * s)),
                    (170, 200, 238, int(235 * p)))
        # نوار اکولایزر
        bars = 40
        bw = w * 0.5 / bars
        for i in range(bars):
            level = 0.25 + 0.75 * abs(math.sin(local * 3.1 + i * 0.6)) * (0.4 + 0.6 * p)
            x = w * 0.25 + i * bw
            bh = 60 * s * level
            d.rounded_rectangle([x, h * 0.62 - bh / 2, x + bw * 0.55, h * 0.62 + bh / 2],
                                radius=bw * 0.3, fill=CYAN + (170,))
        for i, item in enumerate(cfg["scene_c_items"]):
            ap = ease(clamp((local - 0.5 - i * 0.22) / 0.5))
            label = _fa(item) if lang == "fa" else item
            d = ImageDraw.Draw(img)
            draw_center(d, w / 2, h * 0.76 + i * 44 * s, label,
                        _font("Vazirmatn-Medium.ttf", int(23 * s)),
                        (206, 224, 247, int(220 * ap)))

    # ----- صحنهٔ ۴: فراخوان
    else:
        local = t - 9.8
        d = ImageDraw.Draw(img)
        p = ease(clamp(local / 0.6))
        img = sweep(img, clamp(local / 1.1))
        d = ImageDraw.Draw(img)
        cta = cfg["cta"]
        if lang == "fa":
            cta = _fa(cta)
        draw_center(d, w / 2, h * 0.42, cta, _font("Vazirmatn-Black.ttf", int(52 * s)),
                    (255, 255, 255, int(255 * p)))
        url = cfg["url"]
        draw_center(d, w / 2, h * 0.56, url, _font("Vazirmatn-Bold.ttf", int(26 * s)),
                    CYAN + (int(235 * p),))
        wm = wordmark_white.copy()
        target_w = int(min(w * 0.34, 360 * s))
        wm = wm.resize((target_w, int(wm.height * target_w / wm.width)), Image.LANCZOS)
        wa = int(255 * clamp((local - 0.2) / 0.6))
        wm.putalpha(wm.getchannel("A").point(lambda v: int(v * wa / 255)))
        img.alpha_composite(wm, (int(w / 2 - wm.width / 2), int(h * 0.70)))

    # نوار پیشرفت پایین + وینیت
    if bar:
        d = ImageDraw.Draw(img)
        d.rectangle([0, h - 5, int(w * (t / DURATION)), h], fill=CYAN + (200,))
    return vignette(img).convert("RGB")


# --------------------------------------------------------------------- صدا
def synth_audio(path: str, seconds: float = DURATION, sr: int = 44100) -> None:
    n = int(seconds * sr)
    t = np.arange(n) / sr
    mix = np.zeros(n, dtype=np.float32)

    def note(freq, start, dur, amp=0.18, kind="pad"):
        i0 = int(start * sr)
        i1 = min(n, int((start + dur) * sr))
        if i0 >= i1:
            return
        tt = np.arange(i1 - i0) / sr
        if kind == "pad":
            wave_ = (np.sin(2 * np.pi * freq * tt) * 0.6 +
                     np.sin(2 * np.pi * freq * 2 * tt) * 0.22 +
                     np.sin(2 * np.pi * freq * 3 * tt) * 0.08)
            env = np.minimum(1, tt / 0.25) * np.exp(-tt * 0.35)
        elif kind == "pluck":
            wave_ = np.sin(2 * np.pi * freq * tt) + 0.25 * np.sin(2 * np.pi * freq * 2 * tt)
            env = np.exp(-tt * 4.5) * np.minimum(1, tt / 0.01)
        else:  # kick-ish
            wave_ = np.sin(2 * np.pi * (freq * np.exp(-tt * 9)) * tt)
            env = np.exp(-tt * 7)
        mix[i0:i1] += (wave_ * env * amp).astype(np.float32)

    # آکوردها: Am, F, C, G
    chords = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63),
              (261.63, 329.63, 392.0), (196.0, 246.94, 293.66)]
    for i, chord in enumerate(chords):
        start = i * 3.0
        for f in chord:
            note(f, start, 3.0, amp=0.10, kind="pad")
    # آرپژ
    arp = [0, 1, 2, 1, 2, 1, 0, 1]
    for beat in range(32):
        chord = chords[min(3, int(beat / 8))]
        f = chord[arp[beat % len(arp)]]
        note(f * 2, beat * 0.375, 0.34, amp=0.055, kind="pluck")
    # ضرب
    for beat in range(int(seconds / 0.75)):
        note(70, beat * 0.75, 0.25, amp=0.20, kind="kick")
    # رایزر پیش از هر صحنه
    for mark in (3.2, 6.4, 9.6):
        i0 = max(0, int((mark - 0.6) * sr)); i1 = min(n, int(mark * sr))
        if i0 >= i1:
            continue
        tt = np.arange(i1 - i0) / sr
        noise = np.random.default_rng(int(mark * 100)).normal(0, 1, i1 - i0).astype(np.float32)
        env = (tt / max(tt[-1], 1e-6)) ** 2 * 0.08
        mix[i0:i1] += noise * env
    # آکورد پایانی
    for f in (261.63, 329.63, 392.0, 523.25):
        note(f, 9.9, 2.0, amp=0.07, kind="pad")

    mix = np.tanh(mix * 1.4)
    mix = mix / max(np.abs(mix).max(), 1e-6) * 0.85
    st = np.stack([mix, mix * 0.98], axis=1)
    pcm = (st * 32767).astype(np.int16)
    with wave.open(path, "wb") as fh:
        fh.setnchannels(2)
        fh.setsampwidth(2)
        fh.setframerate(sr)
        fh.writeframes(pcm.tobytes())


# ------------------------------------------------------------------ رندر
def render(out_path: str, w: int, h: int, lang: str, wordmark_white, ffmpeg: str,
           audio: str) -> None:
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
        "-i", audio,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    total = int(DURATION * FPS)
    for i in range(total):
        t = i / FPS
        img = frame(w, h, t, lang, wordmark_white, wordmark_white)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"ffmpeg failed for {out_path}")


def poster(w: int, h: int, lang: str, wordmark, path: str, at: float = 2.4) -> None:
    """پوستر بدون نوار پیشرفت، از صحنهٔ لوگو یا صحنهٔ قابلیت‌ها."""
    img = frame(w, h, at, lang, wordmark, wordmark, bar=False)
    img.save(path, quality=88, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(ROOT, "web", "static", "assets", "video"))
    parser.add_argument("--lang", default="fa", choices=["fa", "en"])
    parser.add_argument("--only", default="", help="مثلاً 16x9 برای رندر فقط یک نسخه")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    wm = Image.open(os.path.join(ROOT, "web", "static", "assets", "brand", "wordmark-white.png")).convert("RGBA")

    audio = os.path.join("/tmp", f"rayan-promo-{args.lang}.wav")
    synth_audio(audio)
    sizes = {"16x9": (1280, 720), "9x16": (720, 1280), "1x1": (1080, 1080)}
    for key, (w, h) in sizes.items():
        if args.only and args.only != key:
            continue
        out = os.path.join(args.out, f"promo-{args.lang}-{key}.mp4")
        print(f"[promo] {args.lang} {key} {w}×{h} → {out}", flush=True)
        render(out, w, h, args.lang, wm, ff, audio)
        poster(w, h, args.lang, wm, os.path.join(args.out, f"promo-{args.lang}-{key}-poster.jpg"))
    # پوستر پیش‌فرض زبان (۱۶:۹)
    poster(1280, 720, args.lang, wm, os.path.join(args.out, f"promo-{args.lang}-poster.jpg"))
    print("[promo] done", flush=True)


if __name__ == "__main__":
    main()
