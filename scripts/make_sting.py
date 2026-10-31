"""ویدیوی کوتاه «استینگ» برند رایان — ۶ ثانیه، حلقه‌پذیر، تمام‌محلی.

کره بالا می‌آید، چشمک می‌زند، لوگوتایپ «رایان» زیرش می‌نشیند و شعار
«هوش مصنوعی، به زبان فارسی» ظاهر می‌شود. همه‌چیز تصویر است؛ هیچ نامی
با فونت تایپ نمی‌شود (جز متن شعار).

اجرا:
    .venv/bin/python scripts/make_sting.py --lang both --ratio 16x9
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_promo import (  # noqa: E402
    BRAND, ROOT, SIZES, SS, TEXT, Renderer, _fa, clamp01, ease_out, font, over, put,
    synth_audio,
)

DURATION = 6.0
FPS = 30


def scene(renderer: Renderer, w: int, h: int, t: float, lang: str) -> Image.Image:
    cfg = TEXT[lang]
    s = min(w, h) / 720
    portrait = h > w * 1.12
    square = abs(w - h) < 2
    img = renderer.base(w, h, t + 1.2, 0.55)

    cx = w / 2
    # چیدمان: کره بالا، لوگوتایپ پایین (همان ساختار نشان برند)
    orb_size = min(w, h) * (0.20 if not portrait else 0.22)
    if square:
        orb_size = min(w, h) * 0.185
    orb_cy = h * (0.30 if not portrait else 0.285) - orb_size * 0.15
    mark_w = min(w * (0.34 if not portrait else 0.52), 360 * s)
    if square:
        mark_w = min(w * 0.42, 380 * s)
    mark_h = mark_w * renderer.mark.height / renderer.mark.width
    mark_top = orb_cy + orb_size * 0.5 + h * 0.045

    # ۱) هالهٔ ورود
    enter = ease_out(clamp01(t / 0.85))
    bloom = clamp01((t - 0.05) / 1.0)
    img = over(img, renderer.glow(w, h, [
        (cx, orb_cy, orb_size * 1.9 * (0.6 + 0.4 * bloom), orb_size * 1.9 * (0.6 + 0.4 * bloom),
         (32, 128, 255, int(120 * bloom))),
        (cx, orb_cy, orb_size * 0.95, orb_size * 0.95, (96, 222, 255, int(92 * bloom))),
    ], 0.085))

    # ۲) موج ضربه هنگام ورود
    for delay in (0.1, 0.28):
        ring = clamp01((t - delay) / 1.05)
        if 0 < ring < 1:
            r = min(w, h) * (orb_size / min(w, h) * 0.5 + 0.46 * ease_out(ring))
            layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer, "RGBA")
            ld.ellipse([cx - r, orb_cy - r, cx + r, orb_cy + r],
                       outline=(150, 228, 255, int(118 * (1 - ring) ** 2)),
                       width=max(1, int(2.4 * s * (1 - ring) + 1)))
            img = over(img, layer)

    # ۳) کره: پرواز نرم، تاب خوردن و دو چشمک
    wink = 0.0
    for start in (1.45, 3.85):
        ph = (t - start) / 0.34
        if 0 <= ph <= 1:
            wink = max(wink, math.sin(math.pi * ph))
    sway = 3.6 * math.sin(max(0.0, t - 0.9) * 1.9) * clamp01((t - 0.9) / 0.8)
    size = orb_size * (0.72 + 0.28 * enter)
    img = renderer.orb_face(img, cx + math.sin(t * 1.3) * orb_size * 0.02,
                            orb_cy - (1 - enter) * h * 0.05, size, clamp01(t / 0.45),
                            rot=sway, wink=wink)

    # ۴) لوگوتایپ با بالا آمدن نرم
    mp = ease_out(clamp01((t - 0.55) / 0.85))
    if mp > 0:
        renderer.mark_at(img, cx, mark_top + (1 - mp) * h * 0.055, mark_w * (0.965 + 0.035 * mp), mp)

    # ۵) شعار
    tag_p = ease_out(clamp01((t - 1.55) / 0.75))
    if tag_p > 0:
        d = ImageDraw.Draw(img, "RGBA")
        put(d, (cx, mark_top + mark_h + h * 0.075),
            _fa(cfg["tagline"]) if lang == "fa" else cfg["tagline"],
            font("Medium", (27 if not portrait else 26) * s), (190, 220, 250, int(242 * tag_p)))

    # ۶) تیغهٔ نور از روی نشان عبور می‌کند
    sp = (t - 2.5) / 1.25
    if 0 < sp < 1:
        x = (-0.35 + 1.7 * sp) * w
        band = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(band, "RGBA")
        bd.polygon([(x, 0), (x + w * 0.055, 0), (x + w * 0.055 - h * 0.3, h), (x - h * 0.3, h)],
                   fill=(180, 236, 255, int(64 * math.sin(math.pi * sp) ** 0.7)))
        from PIL import ImageFilter
        img = over(img, band.filter(ImageFilter.GaussianBlur(11 * s)))

    # ۷) خروج نرم برای حلقهٔ تمیز
    fade = clamp01((t - (DURATION - 0.55)) / 0.55)
    if fade > 0:
        dark = Image.new("RGB", (w, h), (6, 14, 34))
        img = Image.blend(img, dark, fade * 0.94)

    img = over(img, renderer.noise(w, h)[int(t * 12) % 3])
    img = over(img, renderer.vignette(w, h))
    return img


def cover(renderer: Renderer, w: int, h: int, t: float, lang: str, scale: float = 1.0) -> Image.Image:
    if scale != 1.0:
        rw, rh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
        return cover(renderer, rw, rh, t, lang).resize((w, h), Image.LANCZOS)
    return scene(renderer, w, h, t, lang)


def render(out_path: str, key: str, lang: str, renderer: Renderer, ffmpeg: str, audio: str,
           crf: str = "23", preset: str = "veryfast") -> None:
    w, h = SIZES[key]
    scale = SS[key]
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-",
        "-i", audio,
        "-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-level", "4.1", "-g", "60", "-tune", "film",
        "-c:a", "aac", "-b:a", "112k", "-shortest", "-movflags", "+faststart",
        out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(int(round(DURATION * FPS))):
        frame = cover(renderer, w, h, i / FPS, lang, scale=scale)
        if frame.size != (w, h):
            frame = frame.resize((w, h), Image.LANCZOS)
        proc.stdin.write(frame.convert("RGB").tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit(f"ffmpeg failed: {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "static", "assets", "video"))
    ap.add_argument("--lang", default="fa", choices=["fa"])
    ap.add_argument("--ratio", default="", help="16x9 یا 1x1 (خالی = هر دو)")
    ap.add_argument("--preview", default="", help="زمان‌ها با کاما")
    ap.add_argument("--crf", default="23")
    ap.add_argument("--preset", default="veryfast")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    renderer = Renderer()
    langs = [args.lang]
    keys = [args.ratio] if args.ratio else ["16x9", "1x1"]

    if args.preview:
        for lang in langs:
            for t in args.preview.split(","):
                for key in keys:
                    w, h = SIZES[key]
                    path = f"/tmp/sting-{lang}-{key}-{float(t):.2f}.png"
                    cover(renderer, w, h, float(t), lang, scale=SS[key]).save(path)
                    print(path, flush=True)
        return

    for lang in langs:
        audio = os.path.join("/tmp", f"rayan-sting-{lang}.wav")
        synth_audio(audio, seconds=DURATION)
        for key in keys:
            out = os.path.join(args.out, f"sting-{lang}-{key}.mp4")
            print(f"[sting] {lang} {key} → {out}", flush=True)
            render(out, key, lang, renderer, ffmpeg, audio, args.crf, args.preset)
            w, h = SIZES[key]
            poster = os.path.join(args.out, f"sting-{lang}-{key}-poster.jpg")
            cover(renderer, w, h, 3.1, lang, scale=SS[key]).save(
                poster, quality=90, optimize=True, progressive=True)
    print("[sting] done", flush=True)


if __name__ == "__main__":
    main()
