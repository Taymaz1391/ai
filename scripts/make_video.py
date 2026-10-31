#!/usr/bin/env python3
"""ساخت ویدیوی معرفی رایان به‌صورت کامل محلی (PIL + ffmpeg).

    python scripts/make_video.py --out web/static/assets/video

شش صحنه، حدود ۳۶ ثانیه، ۲۴ فریم بر ثانیه: لوگو، گفتگو، اندیشهٔ ژرف، ابزارها،
آمار و فراخوان پایانی. هیچ سرویس ابری، هیچ مدل بیرونی و هیچ فایل موسیقی
بیرونی استفاده نمی‌شود؛ صدا به‌صورت اختیاری با --audio اضافه می‌شود.
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "web", "static", "assets", "brand")
OUT = os.path.join(ROOT, "web", "static", "assets", "video")
FONT_DIR = "/tmp"

W, H = 1280, 720
FPS = 24
NAVY = (6, 13, 30)
BLUE = (26, 99, 240)
CYAN = (56, 210, 255)
WHITE = (255, 255, 255)
Soft = (150, 172, 205)

import sys  # noqa: E402
sys.path.insert(0, ROOT)  # noqa: E402
from rayan.text import normalize  # noqa: E402

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
except Exception:  # pragma: no cover
    arabic_reshaper = None
    get_display = None


def fa(text: str) -> str:
    """آماده‌سازی متن فارسی برای PIL (شکل‌دهی + دوجهته)."""
    if arabic_reshaper is None or get_display is None:
        return text
    return get_display(arabic_reshaper.reshape(text))


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def text_size(draw, text, fnt):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=fnt)
    return right - left, bottom - top


def center(draw, box, text, fnt, fill):
    w, h = text_size(draw, text, fnt)
    x = box[0] + (box[2] - box[0] - w) / 2
    y = box[1] + (box[3] - box[1] - h) / 2
    draw.text((x, y), text, font=fnt, fill=fill)


def ease(t: float) -> float:
    return 1 - (1 - min(max(t, 0.0), 1.0)) ** 3


# ------------------------------------------------------------------ بوم
def backdrop() -> Image.Image:
    """پس‌زمینهٔ نرم با هالهٔ آبی؛ یک‌بار ساخته و کش می‌شود."""
    base = Image.new("RGB", (W, H), NAVY)
    glow = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(glow)
    d.ellipse([W * 0.42, -H * 0.55, W * 1.05, H * 0.6], fill=(10, 40, 108))
    d.ellipse([-W * 0.25, -H * 0.35, W * 0.5, H * 0.55], fill=(8, 30, 82))
    d.ellipse([W * 0.2, H * 0.55, W * 0.9, H * 1.3], fill=(7, 22, 62))
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    img = Image.blend(base, glow, 0.95)
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for x in range(0, W, 48):
        for y in range(0, H, 48):
            gd.point((x, y), fill=(120, 180, 255, 22))
    return Image.alpha_composite(img.convert("RGBA"), grid)


BACKDROP = backdrop()


def orb(scale: float = 1.0, glow: float = 1.0) -> Image.Image:
    path = os.path.join(BRAND, "orb-256.png")
    img = Image.open(path).convert("RGBA")
    size = max(8, int(190 * scale))
    img = img.resize((size, size), Image.LANCZOS)
    if glow > 0:
        halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(halo)
        d.ellipse([size * 0.02, size * 0.02, size * 0.98, size * 0.98], fill=(26, 99, 240, int(110 * glow)))
        halo = halo.filter(ImageFilter.GaussianBlur(size * 0.09))
        halo.alpha_composite(img)
        return halo
    return img


def lockup(max_w: int, max_h: int | None = None, light: bool = True) -> Image.Image:
    """قفل کامل لوگو را در کادر داده‌شده جا می‌دهد (نسبت حفظ می‌شود)."""
    name = "lockup-glow.png" if light else "lockup-ink.png"
    img = Image.open(os.path.join(BRAND, name)).convert("RGBA")
    scale = max_w / img.width
    if max_h:
        scale = min(scale, max_h / img.height)
    return img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)


def card(draw, box, radius=22, fill=(16, 28, 54), outline=(58, 96, 160)):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def fade(img: Image.Image, amount: float) -> Image.Image:
    if amount >= 0.999:
        return img
    black = Image.new("RGBA", img.size, (0, 0, 0, 0))
    return Image.blend(black, img, max(0.0, amount))


# ---------------------------------------------------------------- صحنه‌ها
def scene_intro(t: float) -> Image.Image:
    img = BACKDROP.copy()
    d = ImageDraw.Draw(img)
    p = ease(t / 2.0)
    art = lockup(760, 610)
    art.putalpha(art.getchannel("A").point(lambda v: int(v * p)))
    img.alpha_composite(art, ((W - art.width) // 2, int(H * 0.5 - art.height / 2 + (1 - p) * 24)))
    return img


def scene_chat(t: float, progress: float) -> Image.Image:
    img = BACKDROP.copy()
    d = ImageDraw.Draw(img)
    title = fa("گفتگو، جریانی و فارسی")
    center(d, (0, 40, W, 110), title, font("Vazirmatn-Black.ttf", 50), WHITE)
    # پنجرهٔ گفتگو
    box = (150, 140, W - 150, H - 90)
    card(d, box, 26, (13, 24, 48, 240), (52, 92, 160))
    d.line((box[0], 190, box[2], 190), fill=(48, 84, 146), width=2)
    for i, cx in enumerate((box[2] - 34, box[2] - 62, box[2] - 90)):
        d.ellipse((cx - 6, 156, cx + 6, 168), fill=(80, 120, 180))
    # پیام کاربر
    q = fa("یک بیت دربارهٔ پاییز بگو")
    qf = font("Vazirmatn-Bold.ttf", 27)
    qw, _ = text_size(d, q, qf)
    d.rounded_rectangle((box[2] - qw - 56, 214, box[2] - 24, 272), 18, fill=(26, 99, 240))
    d.text((box[2] - qw - 40, 228), q, font=qf, fill=WHITE)
    # پاسخ دستیار با تایپ تدریجی (راست‌چین، با شکست خط درست برای فارسی)
    answer = normalize("برگ‌ریزان است و باد، نامه‌های زرد را می‌برد؛ پاییز با خودش فصلی از سکوت می‌آورد.")
    count = int(len(answer) * min(1.0, progress))
    af = font("Vazirmatn-Regular.ttf", 26)
    right = box[2] - 30
    max_w = box[2] - box[0] - 200

    def measure(text: str) -> int:
        return text_size(d, fa(text), af)[0]

    lines: list[str] = []
    line = ""
    for word in answer[:count].split(" "):
        candidate = (line + " " + word).strip()
        if measure(candidate) > max_w and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)

    y = 320
    last_w = 0
    for text_line in lines[:4]:
        shaped = fa(text_line)
        w_line, _ = text_size(d, shaped, af)
        d.text((right - w_line, y), shaped, font=af, fill=(226, 236, 255))
        last_w = w_line
        y += 46
    # نشانگر تایپ
    if progress < 0.98 and int(t * 3) % 2 == 0:
        d.rectangle((right - last_w - 14, y - 34, right - last_w - 6, y - 8), fill=(120, 176, 255))

    # آواتار
    avatar = orb(0.30)
    img.alpha_composite(avatar, (box[0] + 22, 296))
    # فوتر: آمار
    stats = fa("۸۴ توکن بر ثانیه · اطمینان ۲۹٪ · ۵ لایه")
    center(d, (0, H - 66, W, H - 20), stats, font("Vazirmatn-Medium.ttf", 22), (150, 178, 214))
    return img


def scene_deep(t: float, progress: float) -> Image.Image:
    img = BACKDROP.copy()
    d = ImageDraw.Draw(img)
    center(d, (0, 40, W, 110), fa("اندیشهٔ ژرف: چند مسیر، بهترین پاسخ"), font("Vazirmatn-Black.ttf", 46), WHITE)
    cx, cy = W // 2, int(H * 0.56)
    # چهار مسیر
    for i in range(4):
        angle = -math.pi / 2 + i * math.pi / 2 + t * 0.3
        r = 190 - 40 * ease(progress)
        x = cx + math.cos(angle) * r
        y = cy + math.sin(angle) * r * 0.72
        node = orb(0.22, 0.4)
        img.alpha_composite(node, (int(x - node.width / 2), int(y - node.height / 2)))
        d.line((cx, cy, x, y), fill=(46, 90, 160), width=3)
    core = orb(0.62, 1.0)
    img.alpha_composite(core, (cx - core.width // 2, cy - core.height // 2))
    score = fa(f"امتیاز مسیر برتر ۰٫۸۶ · تکرار ۰٫۰۲")
    center(d, (0, H - 96, W, H - 40), score, font("Vazirmatn-Bold.ttf", 24), (140, 200, 255))
    return img


def scene_tools(t: float) -> Image.Image:
    img = BACKDROP.copy()
    d = ImageDraw.Draw(img)
    center(d, (0, 36, W, 104), fa("ابزار، فایل و تصویر — همه محلی"), font("Vazirmatn-Black.ttf", 46), WHITE)
    items = [
        ("ماشین‌حساب", "۲×۱۰² + ۵ = ۱۰۲۹"),
        ("تقویم شمسی", "شنبه ۹ آبان ۱۴۰۵"),
        ("تبدیل یکا", "۵ کیلومتر = ۳٫۱ مایل"),
        ("ساخت تصویر", "SVG · ۱۰۸۰×۱۳۵۰"),
        ("فایل و کد", "py · js · md · csv"),
        ("آمار متن", "۲۴۰ واژه · ۱۰۰٪ فارسی"),
    ]
    cols = 3
    cw, ch = 330, 150
    gap = 26
    total_w = cols * cw + (cols - 1) * gap
    x0 = (W - total_w) // 2
    y0 = 158
    for i, (title, value) in enumerate(items):
        appear = ease((t * 1.4) - i * 0.18)
        if appear <= 0:
            continue
        row, col = divmod(i, cols)
        x = x0 + col * (cw + gap)
        y = y0 + row * (ch + gap) + int((1 - appear) * 24)
        card(d, (x, y, x + cw, y + ch), 20, (14, 26, 50, 235), (54, 96, 158))
        d.text((x + 24, y + 24), fa(title), font=font("Vazirmatn-Bold.ttf", 26), fill=WHITE)
        d.text((x + 24, y + 74), fa(value), font=font("Vazirmatn-Regular.ttf", 22), fill=(150, 196, 255))
    return img


def scene_stats(t: float) -> Image.Image:
    img = BACKDROP.copy()
    d = ImageDraw.Draw(img)
    center(d, (0, 60, W, 130), fa("این‌ها ادعا نیستند؛ گزارش‌اند"), font("Vazirmatn-Black.ttf", 48), WHITE)
    stats = [("۶٫۵۷", "میلیون پارامتر"), ("۱۴٫۷", "میلیون توکن آموزش"), ("۲۰۱", "perplexity"), ("۱۰۰٪", "روی CPU")]
    width = 250
    total = len(stats) * width + (len(stats) - 1) * 20
    x = (W - total) // 2
    for i, (value, label) in enumerate(stats):
        appear = ease(t * 1.6 - i * 0.2)
        if appear <= 0:
            continue
        y = 240 + int((1 - appear) * 18)
        card(d, (x, y, x + width, y + 210), 24, (14, 26, 50, 240), (56, 100, 164))
        center(d, (x, y + 40, x + width, y + 120), fa(value), font("Vazirmatn-Black.ttf", 54), WHITE)
        center(d, (x, y + 124, x + width, y + 176), fa(label), font("Vazirmatn-Medium.ttf", 21), (150, 186, 232))
        x += width + 20
    return img


def scene_outro(t: float) -> Image.Image:
    img = BACKDROP.copy()
    d = ImageDraw.Draw(img)
    p = ease(t / 1.6)
    art = lockup(430, 330)
    img.alpha_composite(art, ((W - art.width) // 2, int(H * 0.06)))
    center(d, (0, H - 250, W, H - 190), fa("هوش مصنوعی، به زبان فارسی"), font("Vazirmatn-Bold.ttf", 38), (196, 218, 246))
    btn_w, btn_h = 340, 72
    bx = (W - btn_w) // 2
    by = H - 168
    d.rounded_rectangle((bx, by, bx + btn_w, by + btn_h), 20, fill=(26, 99, 240))
    center(d, (bx, by, bx + btn_w, by + btn_h), fa("رایان را امتحان کن"), font("Vazirmatn-Bold.ttf", 27), WHITE)
    center(d, (0, H - 78, W, H - 26), "taymaz1391.github.io/ai", font("Vazirmatn-Medium.ttf", 22), (140, 176, 220))
    return img


SCENES = [
    ("intro", 3.0),
    ("chat", 8.0),
    ("deep", 6.0),
    ("tools", 6.0),
    ("stats", 6.0),
    ("outro", 6.0),
]


def render_frame(name: str, t: float, duration: float) -> Image.Image:
    progress = min(1.0, t / max(duration - 0.8, 0.1))
    if name == "intro":
        img = scene_intro(t)
    elif name == "chat":
        img = scene_chat(t, progress)
    elif name == "deep":
        img = scene_deep(t, progress)
    elif name == "tools":
        img = scene_tools(t)
    elif name == "stats":
        img = scene_stats(t)
    else:
        img = scene_outro(t)
    # محو شدن در آغاز و پایان هر صحنه
    fade_in = ease(t / 0.45)
    fade_out = ease((duration - t) / 0.45)
    return fade(img, min(fade_in, fade_out))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--fps", type=int, default=FPS)
    parser.add_argument("--gif", action="store_true", help="ساخت نسخهٔ GIF سبک")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = tempfile.mkdtemp(prefix="rayan-video-")
    index = 0
    for name, duration in SCENES:
        frames = int(duration * args.fps)
        for i in range(frames):
            t = i / args.fps
            img = render_frame(name, t, duration)
            img.convert("RGB").save(os.path.join(tmp, f"{index:05d}.png"))
            index += 1
        print(f"  صحنهٔ {name}: {frames} فریم", flush=True)

    mp4 = os.path.join(args.out, "rayan-intro.mp4")
    webm = os.path.join(args.out, "rayan-intro.webm")
    poster = os.path.join(args.out, "rayan-intro-poster.jpg")
    common = [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(args.fps),
              "-i", os.path.join(tmp, "%05d.png")]
    subprocess.run(common + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22",
                             "-movflags", "+faststart", mp4], check=True)
    subprocess.run(common + ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", webm], check=True)
    render_frame("outro", 1.2, 6.0).convert("RGB").save(poster, quality=88, optimize=True)
    if args.gif:
        # نسخهٔ سبک برای هیرو: فقط صحنهٔ آغاز، ۴۸۰ پیکسل، پالت بهینه
        gif = os.path.join(args.out, "rayan-loop.gif")
        intro_frames = int(SCENES[0][1] * args.fps)
        subprocess.run([
            ffmpeg, "-y", "-loglevel", "error", "-framerate", str(args.fps),
            "-i", os.path.join(tmp, "%05d.png"), "-frames:v", str(intro_frames),
            "-vf", "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse=dither=bayer",
            gif,
        ], check=True)
    for name in (mp4, webm, poster):
        print(f"  {os.path.relpath(name, ROOT)}  {os.path.getsize(name) / 1024:.0f} KB")
    print("ویدیو ساخته شد.")


if __name__ == "__main__":
    main()
