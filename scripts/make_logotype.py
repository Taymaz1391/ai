"""ساخت لوگوتایپ برند «رایان» از تصویر رسمی.

منبع، تصویر تأییدشدهٔ برند است (``web/static/assets/brand/mark-source.png``):
پس‌زمینهٔ سرمه‌ای، حروف سفید و لهجه‌های آبی. این ابزار پس‌زمینه را شفاف می‌کند،
دو نسخهٔ جوهری و سفید می‌سازد، و از همان فایل آیکون‌ها، تصویر اشتراک‌گذاری،
پس‌زمینهٔ ویدیو و نشان ترکیبی کره+نام را بیرون می‌دهد تا همه‌جای سایت یک برند
دیده شود.

    python scripts/make_logotype.py
    python scripts/make_logotype.py --check     # فقط بررسی نسبت‌ها
"""
from __future__ import annotations

import argparse
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "web", "static", "assets", "brand")
VIDEO = os.path.join(ROOT, "web", "static", "assets", "video")
ICONS = os.path.join(ROOT, "web", "static", "assets", "icons")

# برگهٔ رسمی برند ۱۲۵۴×۱۲۵۴ است؛ خود نشانه با کیفیت ۵۱۰×۲۵۸ داخل آن است.
SHEET = os.path.join(BRAND, "logo-source.jpg")
WORDMARK_BOX = (366, 474, 888, 802)
REFERENCE = os.path.join(BRAND, "mark-source.png")   # تصویر تأییدشدهٔ کاربر
ORB = os.path.join(BRAND, "orb-512.png")

INK = (10, 23, 48)          # سرمه‌ای برند
SNOW = (247, 250, 255)      # سفید برند
BLUE = (26, 99, 240)        # آبی برند
SCALE = 2                   # عرض نهایی ≈ ۱۰۲۰ پیکسل


# ------------------------------------------------------------------ استخراج
ACCENT_A = (0, 196, 255)    # ابتدای گرادیان آبی (نقطهٔ بالای «ر»)
ACCENT_B = (10, 92, 245)    # انتهای گرادیان (زیر «یا»)
# لهجه‌ها اشکال ساده‌اند؛ دوباره و تمیز کشیده می‌شوند تا لبهٔ فشرده‌شدهٔ JPEG
# نقطه‌های آبی سرگردان روی حروف نگذارد. مختصات در دستگاه برش ۵۲۲×۳۲۸.
ACCENTS = (
    (6, 32, 59, 79, 10),      # نقطهٔ بالای «ر»
    (193, 245, 343, 289, 12), # خط زیر «یا»
)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """سوراخ‌های ریز داخل حروف را پر می‌کند (پیکسل آبی جامانده از فشرده‌سازی)."""
    from collections import deque

    h, w = mask.shape
    outside = np.zeros((h, w), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                q.append((ny, nx))
    filled = mask.copy()
    filled[~outside] = True
    return filled


def _mask(channel_ok: np.ndarray, saturation_ok: np.ndarray) -> np.ndarray:
    """ماسک تمیز: آستانه، صاف‌سازی و پرشدن سوراخ‌های ریز."""
    m = Image.fromarray(((channel_ok & saturation_ok) * 255).astype(np.uint8))
    m = m.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.GaussianBlur(0.6))
    arr = np.asarray(m).astype(np.float32) / 255.0
    solid = _fill_holes(arr > 0.45)
    # فقط سوراخ‌های محصور پر می‌شوند؛ لبهٔ بیرونی همان نرمی خودش را دارد
    arr = np.where(solid & (arr < 0.45), 0.45, arr)
    return arr


def extract() -> tuple[Image.Image, Image.Image]:
    """حروف و لهجهٔ آبی را جدا برمی‌گرداند؛ هر دو با لبهٔ نرم و اندازهٔ برابر."""
    rgb = np.asarray(Image.open(SHEET).convert("RGB").crop(WORDMARK_BOX)).astype(np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    blue = (b - r > 35) & (b > 90)
    white = (mn > 100) & (mx > 150)
    letter_a = _mask(white, ~blue)
    # لهجه‌ها به‌صورت هندسی کشیده می‌شوند (گرد‌گوشهٔ تمیز، بدون نویز JPEG)
    acc = Image.new("L", (rgb.shape[1], rgb.shape[0]), 0)
    d = ImageDraw.Draw(acc)
    for x0, y0, x1, y1, r in ACCENTS:
        d.rounded_rectangle((x0, y0, x1, y1), radius=r, fill=255)
    accent_a = np.asarray(acc).astype(np.float32) / 255.0
    return letter_a, accent_a


def gradient(width: int, height: int, x0: float = 0.0, x1: float = 1.0) -> Image.Image:
    """گرادیان افقی آبی برند؛ نقطه سمت چپ فیروزه‌ای، زیرِ نام به آبی می‌رسد."""
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
    x = np.clip((x - x0) / max(x1 - x0, 1e-4), 0, 1)
    a = np.array(ACCENT_A, dtype=np.float32)[None, None, :]
    b = np.array(ACCENT_B, dtype=np.float32)[None, None, :]
    arr = a + (b - a) * x ** 0.85
    arr = np.repeat(arr, height, axis=0)
    return Image.fromarray(arr.round().astype(np.uint8), "RGB")


def compose(letter_a: np.ndarray, accent_a: np.ndarray, letter_rgb: tuple[int, int, int], factor: int = SCALE) -> Image.Image:
    h, w = letter_a.shape
    W, H = w * factor, h * factor
    la = Image.fromarray((letter_a * 255).round().astype(np.uint8)).resize((W, H), Image.BICUBIC)
    aa = Image.fromarray((accent_a * 255).round().astype(np.uint8)).resize((W, H), Image.BICUBIC)
    la = la.filter(ImageFilter.GaussianBlur(factor * 0.35))
    aa = aa.filter(ImageFilter.GaussianBlur(factor * 0.35))
    A = np.asarray(la).astype(np.float32) / 255.0
    B = np.asarray(aa).astype(np.float32) / 255.0
    alpha = np.clip(np.maximum(A, B) * 1.06, 0, 1)
    # گرادیان روی خط زیرِ نام کشیده می‌شود؛ نقطه همان فیروزه‌ای می‌ماند
    bar = max(ACCENTS, key=lambda a: a[2] - a[0])
    grad = np.asarray(gradient(W, H, bar[0] / w, bar[2] / w)).astype(np.float32)
    base = np.zeros((H, W, 3), dtype=np.float32) + np.array(letter_rgb, dtype=np.float32)
    # هرجا لهجه غالب است رنگ گرادیان، وگرنه رنگ حرف
    wgt = (B / np.clip(A + B + 1e-4, 1e-4, 1)).clip(0, 1)[..., None]
    rgb = base * (1 - wgt) + grad * wgt
    out = np.dstack([rgb, alpha * 255]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def trim(im: Image.Image) -> Image.Image:
    bbox = im.split()[-1].point(lambda v: 255 if v > 8 else 0).getbbox()
    return im.crop(bbox) if bbox else im


# ------------------------------------------------------------------ ترکیب‌ها
def stack(mark: Image.Image, orb_path: str = ORB, gap: float = 0.18, orb_ratio: float = 0.46) -> Image.Image:
    """کره بالای نام؛ برای فوتر، صفحهٔ خانه و کارت‌های اشتراک‌گذاری."""
    orb = Image.open(orb_path).convert("RGBA")
    orb = orb.resize((max(1, int(mark.width * orb_ratio)),) * 2, Image.LANCZOS)
    gap_px = int(mark.height * gap)
    width = max(mark.width, orb.width)
    canvas = Image.new("RGBA", (width, orb.height + gap_px + mark.height), (0, 0, 0, 0))
    canvas.alpha_composite(orb, ((width - orb.width) // 2, 0))
    canvas.alpha_composite(mark, ((width - mark.width) // 2, orb.height + gap_px))
    return canvas


def on_background(im: Image.Image, width: int, height: int, radius: int = 56) -> Image.Image:
    """کارت سرمه‌ای با هالهٔ نرم؛ برای OG و آیکون."""
    base = Image.new("RGB", (width, height), (6, 14, 32))
    glow = Image.new("RGB", (width, height), (6, 14, 32))
    d = ImageDraw.Draw(glow)
    cx, cy = width * 0.5, height * 0.36
    for i in range(24, 0, -1):
        t = i / 24
        rr = int(min(width, height) * 0.62 * t)
        col = (int(16 + 40 * (1 - t)), int(60 + 70 * (1 - t)), int(150 + 60 * (1 - t)))
        d.ellipse((cx - rr, cy - rr * 0.8, cx + rr, cy + rr * 0.8), fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=width // 18))
    base = Image.blend(base, glow, 0.55)
    return base


def logo_card(im: Image.Image, width: int, height: int, pad: float = 0.72) -> Image.Image:
    bg = on_background(im, width, height)
    room_w, room_h = width * pad, height * pad
    k = min(room_w / im.width, room_h / im.height)
    small = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    bg.paste(small, ((width - small.width) // 2, (height - small.height) // 2), small)
    return bg


def _fa(text: str) -> str:
    from make_brand import _fa as shape

    return shape(text)


def og_image(mark: Image.Image, path: str) -> None:
    """۱۲۰۰×۶۳۰ برای شبکه‌های اجتماعی؛ نام برند تصویر است، نه متن."""
    W, H = 1200, 630
    bg = on_background(mark, W, H)
    d = ImageDraw.Draw(bg)
    # حباب‌های نور
    rng = np.random.default_rng(7)
    for _ in range(38):
        x, y = rng.integers(0, W), rng.integers(0, H)
        r = int(rng.integers(1, 3))
        a = int(rng.integers(40, 130))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(150, 200, 255, a))
    stack_img = stack(mark, orb_ratio=0.34, gap=0.22)
    k = min((W * 0.46) / stack_img.width, (H * 0.62) / stack_img.height)
    small = stack_img.resize((int(stack_img.width * k), int(stack_img.height * k)), Image.LANCZOS)
    bg.paste(small, ((W - small.width) // 2, int(H * 0.08)), small)
    from fontcache import ensure_fonts

    fonts = ensure_fonts()
    tag = ImageFont.truetype(os.path.join(fonts, "Vazirmatn-Bold.ttf"), 34)
    url = ImageFont.truetype(os.path.join(fonts, "Vazirmatn-Medium.ttf"), 22)
    line = _fa("هوش مصنوعی، به زبان فارسی")
    tw = d.textlength(line, font=tag)
    d.text(((W - tw) / 2, H * 0.735), line, font=tag, fill=(236, 244, 255))
    link = "taymaz1391.github.io/ai"
    uw = d.textlength(link, font=url)
    d.text(((W - uw) / 2, H * 0.83), link, font=url, fill=(120, 186, 255))
    bg.save(path, quality=94)


def icons(mark: Image.Image) -> None:
    os.makedirs(ICONS, exist_ok=True)
    tile = logo_card(mark, 512, 512, pad=0.62)
    tile.save(os.path.join(ICONS, "icon-512.png"))
    for size in (192, 180, 32, 64):
        tile.resize((size, size), Image.LANCZOS).save(os.path.join(ICONS, f"icon-{size}.png"))
    # نام‌هایی که HTML و manifest صدا می‌زنند
    tile.resize((192, 192), Image.LANCZOS).save(os.path.join(ICONS, "favicon-192.png"))
    tile.resize((180, 180), Image.LANCZOS).save(os.path.join(ICONS, "apple-touch-icon.png"))
    tile.resize((32, 32), Image.LANCZOS).save(os.path.join(ICONS, "favicon-32.png"))
    # maskable: حاشیهٔ امن ۲۰٪
    mask = logo_card(mark, 512, 512, pad=0.46)
    mask.save(os.path.join(ICONS, "maskable-512.png"))
    fav = logo_card(mark, 64, 64, pad=0.74)
    fav.save(os.path.join(ICONS, "favicon-64.png"))
    # .ico چنداندازه
    fav.resize((32, 32), Image.LANCZOS).save(
        os.path.join(ICONS, "favicon.ico"),
        sizes=[(16, 16), (32, 32), (48, 48)],
    )


def video_poster(mark: Image.Image) -> None:
    """یک فریمِ آمادهٔ برند برای ویدیوها (پیش از رندر، جای پوستر خالی نماند)."""
    frame = logo_card(mark, 1280, 720, pad=0.66)
    frame.save(os.path.join(VIDEO, "brand-frame.png"))
    frame.resize((720, 720), Image.LANCZOS).save(os.path.join(VIDEO, "brand-frame-square.png"))


# ------------------------------------------------------------------ اجرا
def build() -> dict[str, tuple[int, int]]:
    letter_a, accent_a = extract()
    white = trim(compose(letter_a, accent_a, SNOW))
    ink = trim(compose(letter_a, accent_a, INK))
    white.save(os.path.join(BRAND, "mark-white.png"))
    ink.save(os.path.join(BRAND, "mark-ink.png"))
    stack(white).save(os.path.join(BRAND, "logotype-stack-white.png"))
    stack(ink).save(os.path.join(BRAND, "logotype-stack-ink.png"))
    og_image(white, os.path.join(BRAND, "og-image.png"))
    icons(white)
    video_poster(white)
    return {
        "mark-white.png": white.size,
        "mark-ink.png": ink.size,
        "logotype-stack-white.png": Image.open(os.path.join(BRAND, "logotype-stack-white.png")).size,
        "og-image.png": Image.open(os.path.join(BRAND, "og-image.png")).size,
    }


def check() -> int:
    for name in ("mark-ink.png", "mark-white.png", "logotype-stack-ink.png", "logotype-stack-white.png"):
        path = os.path.join(BRAND, name)
        if not os.path.exists(path):
            print(f"missing: {name}")
            return 1
        with Image.open(path) as im:
            print(f"{name:28s} {im.width}×{im.height} ratio={im.width / im.height:.3f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="ساخت دارایی‌های برند رایان")
    ap.add_argument("--check", action="store_true", help="فقط اندازه‌ها را نشان بده")
    args = ap.parse_args()
    if args.check:
        return check()
    for name, size in build().items():
        print(f"[brand] {name:28s} {size[0]}×{size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
