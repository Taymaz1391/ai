#!/usr/bin/env python3
"""رایان — ساخت دارایی‌های متحرک برند از فایل‌های منبع.

منبع‌ها در `assets_src/brand-motion/` هستند (GIF‌هایی که کاربر داده است):

- `orb-spin.gif`    → کرهٔ دستیار با پلک‌زدن، پس‌زمینهٔ سرمه‌ای
- `logo-motion.gif` → نشانِ رایان که واژه‌به‌واژه ظاهر می‌شود
- `logo-loading.gif`→ همان نشان در حالت بارگذاری

خروجی‌ها (همه با پس‌زمینهٔ شفاف، تا در تم روشن و تیره درست بنشینند):

- `web/static/assets/brand/orb-live.webp`      کرهٔ متحرک ۲۵۶ پیکسل
- `web/static/assets/brand/orb-live-sm.webp`   کرهٔ متحرک ۶۴ پیکسل (آواتار گفتگو)
- `web/static/assets/brand/orb-{128,256,512}.png`  کرهٔ ثابت
- `web/static/assets/brand/logo-motion.webp`   نشان متحرک، نسخهٔ روشن (سرمه‌ای)
- `web/static/assets/brand/logo-motion-dark.webp`  نشان متحرک، نسخهٔ تیره (سفید)
- `web/static/assets/brand/logo-loading.webp`  نشانِ بارگذاری

اجرا:  ``.venv/bin/python scripts/build_brand_motion.py``
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets_src" / "brand-motion"
OUT = ROOT / "web" / "static" / "assets" / "brand"

INK = np.array([10, 23, 48], dtype=np.float32)
SNOW = np.array([247, 250, 255], dtype=np.float32)
ACCENT = np.array([26, 99, 240], dtype=np.float32)
GLOW_BLUE = np.array([70, 150, 255], dtype=np.float32)

SKIP = int(os.environ.get("RAYAN_MOTION_STRIDE", "2"))  # هر چند فریم یکی بماند


# ----------------------------------------------------------------- ابزارها
def _frames(path: Path) -> list[Image.Image]:
    im = Image.open(path)
    out: list[Image.Image] = []
    for index in range(getattr(im, "n_frames", 1)):
        im.seek(index)
        out.append(im.convert("RGBA"))
    return out


def _save_webp(frames: list[Image.Image], path: Path, duration: int, quality: int = 82) -> int:
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, quality=quality, method=5,
                   allow_mixed=True, minimize_size=True)
    return os.path.getsize(path)


def _unmultiply(rgb: np.ndarray, alpha: np.ndarray, bg: np.ndarray) -> np.ndarray:
    a = np.maximum(alpha, 1e-3)[..., None]
    return np.clip((rgb - bg * (1 - a)) / a, 0, 255)


# ------------------------------------------------------------------- کره
def orb_frame(img: Image.Image, size: int) -> Image.Image:
    """کره را از پس‌زمینهٔ سرمه‌ای جدا می‌کند و هالهٔ نرم دورش می‌سازد."""
    arr = np.asarray(img).astype(np.float32)
    h, w = arr.shape[:2]
    crop = arr[34: min(h, 554), 34: min(w, 554)]  # قاب واقعی کره در ۶۰۰×۶۰۰
    ch, cw = crop.shape[:2]
    ys, xs = np.mgrid[0:ch, 0:cw]
    cx, cy = (cw - 1) / 2, (ch - 1) / 2
    radius = np.hypot(xs - cx, ys - cy)
    scale = min(ch, cw) / 520.0
    core = np.clip((198 * scale - radius) / (38 * scale), 0, 1) ** 1.25
    glow = np.clip((300 * scale - radius) / (102 * scale), 0, 1) ** 2 * 0.55
    alpha = np.maximum(core, glow)
    edge = np.clip((radius - (172 * scale)) / (40 * scale), 0, 1)[..., None]
    rgb = crop[..., :3] * (1 - edge) + GLOW_BLUE * edge
    out = np.dstack([np.clip(rgb, 0, 255), np.clip(alpha * 255, 0, 255)]).astype(np.uint8)
    img = Image.fromarray(out, "RGBA")
    if img.width != size:
        img = img.resize((size, size), Image.LANCZOS)
    return img


def build_orb() -> None:
    raw = _frames(SRC / "orb-spin.gif")
    small, large = [], []
    for index in range(0, len(raw), SKIP):
        frame = orb_frame(raw[index], 256)
        large.append(frame)
        small.append(frame.resize((64, 64), Image.LANCZOS))
    step_ms = int(round(6000 / len(raw) * SKIP))
    size_l = _save_webp(large, OUT / "orb-live.webp", step_ms, quality=84)
    size_s = _save_webp(small, OUT / "orb-live-sm.webp", step_ms, quality=78)
    still = orb_frame(raw[0], 512)
    still.save(OUT / "orb-512.png")
    still.resize((256, 256), Image.LANCZOS).save(OUT / "orb-256.png")
    still.resize((128, 128), Image.LANCZOS).save(OUT / "orb-128.png")
    print(f"orb: {len(large)} frames · live {size_l // 1024}KB · avatar {size_s // 1024}KB")


# ------------------------------------------------------------------ نشان
def _logo_layers(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """پوشش (alpha) و «آبی‌بودن» هر پیکسل نشان را برمی‌گرداند.

    منبع، نشانِ سفید روی پس‌زمینهٔ سرمه‌ای است؛ حروفِ سفید خنثی‌اند و
    نوارها و نقطهٔ نشان آبی. از همین تفاوت رنگ، دو نسخهٔ روشن و تیره ساخته می‌شود.
    """
    rgb = rgba[..., :3]
    peak = rgb.max(axis=2)
    alpha = np.clip((peak - 70.0) / 90.0, 0, 1)
    blueness = np.clip((rgb[..., 2] - rgb[..., 0] - 35.0) / 110.0, 0, 1)
    return alpha, blueness


def logo_frame(img: Image.Image, width: int, ink: np.ndarray, accent: np.ndarray) -> Image.Image:
    arr = np.asarray(img).astype(np.float32)
    alpha, blueness = _logo_layers(arr)
    tone = ink[None, None, :] * (1 - blueness[..., None]) + accent[None, None, :] * blueness[..., None]
    out = np.dstack([np.clip(tone, 0, 255), np.clip(alpha * 255, 0, 255)]).astype(np.uint8)
    frame = Image.fromarray(out, "RGBA")
    if frame.width != width:
        frame = frame.resize((width, int(frame.height * width / frame.width)), Image.LANCZOS)
    box = frame.getbbox()
    if box:
        frame = frame.crop(box)
    return frame


def _pad(frames: list[Image.Image]) -> list[Image.Image]:
    w = max(f.width for f in frames)
    h = max(f.height for f in frames)
    out = []
    for frame in frames:
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.alpha_composite(frame, ((w - frame.width) // 2, (h - frame.height) // 2))
        out.append(canvas)
    return out


def build_logo(name: str, target: str, width: int, total_ms: int,
               ink: np.ndarray, accent: np.ndarray, quality: int = 82) -> None:
    raw = _frames(SRC / name)
    frames = _pad([logo_frame(raw[i], width, ink, accent) for i in range(0, len(raw), SKIP)])
    step_ms = int(round(total_ms / len(raw) * SKIP))
    size = _save_webp(frames, OUT / target, step_ms, quality=quality)
    print(f"{target}: {len(frames)} frames · {size // 1024}KB · {frames[0].size}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if os.environ.get("RAYAN_SKIP_ORB") != "1":
        build_orb()
    build_logo("logo-motion.gif", "logo-motion.webp", 640, 3200, INK, ACCENT)
    build_logo("logo-motion.gif", "logo-motion-dark.webp", 640, 3200, SNOW, GLOW_BLUE)
    build_logo("logo-loading.gif", "logo-loading.webp", 520, 2400, SNOW, GLOW_BLUE)


if __name__ == "__main__":
    main()
