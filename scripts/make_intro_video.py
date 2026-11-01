#!/usr/bin/env python3
"""ساخت ویدیوی آموزش استفاده با گویندهٔ فارسی — بدون هیچ سرویس بیرونی.

قطعه‌های گفتار از پیش ساخته‌شده (``data/intro/*.mp3``) خوانده می‌شوند، تصویر
فریم‌به‌فریم با NumPy و Matplotlib ساخته می‌شود و همه با ffmpeg (نسخهٔ همراهِ
``imageio-ffmpeg``) در یک MP4 کنار هم می‌نشیند. مدت هر صحنه از مدت گفتارِ همان
صحنه می‌آید، پس صدا و تصویر همیشه هم‌زمان‌اند.

    python scripts/make_intro_video.py --check        # فقط بررسی ابزارها
    python scripts/make_intro_video.py                # ساخت ویدیو
    python scripts/make_intro_video.py --silent       # بی‌صدا (آزمون تصویر)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FONT_DIR = os.path.join(ROOT, "web", "static", "assets", "fonts")
BUILD_FONTS = os.path.join(ROOT, "data", "intro", "fonts")
SCRIPT_PATH = os.path.join(ROOT, "data", "intro", "script.json")
AUDIO_DIR = os.path.join(ROOT, "data", "intro", "voice")
OUT_DIR = os.path.join(ROOT, "web", "static", "assets", "video")
OUT_VIDEO = os.path.join(OUT_DIR, "intro.mp4")
OUT_POSTER = os.path.join(OUT_DIR, "intro-poster.jpg")

FPS = 25
WIDTH, HEIGHT = 1280, 720
SAMPLE_RATE = 44100
LEAD_IN = 0.6      # سکوت آغاز
GAP = 0.45         # فاصلهٔ بین جمله‌ها
TAIL = 1.6         # سکوت پایان

# رنگ‌های برند (بدون خاکستری خنثی)
INK = (10, 27, 61)
DEEP = (6, 18, 44)
BLUE = (26, 99, 240)
CYAN = (56, 210, 255)
MINT = (32, 200, 170)
WHITE = (234, 243, 255)
SOFT = (169, 198, 238)


# --------------------------------------------------------------- ابزار فونت
def ttf_fonts() -> dict[str, str]:
    """woff2های سایت را یک‌بار به TTF تبدیل می‌کند (Matplotlib فقط TTF می‌خواند)."""
    os.makedirs(BUILD_FONTS, exist_ok=True)
    out: dict[str, str] = {}
    try:
        from fontTools.ttLib import TTFont
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"fonttools لازم است: pip install fonttools brotli ({exc})")
    for weight in ("Regular", "Bold", "ExtraBold"):
        source = os.path.join(FONT_DIR, f"Vazirmatn-{weight}.woff2")
        target = os.path.join(BUILD_FONTS, f"Vazirmatn-{weight}.ttf")
        if not os.path.exists(target) or os.path.getmtime(target) < os.path.getmtime(source):
            font = TTFont(source)
            font.flavor = None
            font.save(target)
        out[weight] = target
    return out


def ffmpeg_bin() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover
        return "ffmpeg"


# --------------------------------------------------------------- متن فارسی
def text_layer(text: str, *, size: int, color: tuple[int, int, int], weight: str = "Bold",
               max_width: int = 1080, fonts: dict[str, str] | None = None,
               line_gap: float = 1.62) -> np.ndarray:
    """متن فارسی را به لایهٔ RGBA کوچک و دقیقاً به اندازهٔ خودِ متن تبدیل می‌کند.

    Matplotlib خودش شکل‌دهی حروف و راست‌به‌چپ را با فونت وزیرمتن انجام می‌دهد؛
    پس هیچ pre-shaping دستی لازم نیست (و اگر بشود، متن برعکس می‌شود). خروجی
    با tight bbox بریده می‌شود تا جای‌گذاری روی فریم دقیق باشد و سطرها روی هم نیفتند.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm

    fonts = fonts or ttf_fonts()
    fm.fontManager.addfont(fonts[weight])
    prop = fm.FontProperties(fname=fonts[weight])

    words = text.split()
    lines: list[str] = []
    current = ""
    budget = max(12, int(max_width / (size * 0.52)))
    for word in words:
        trial = f"{current} {word}".strip()
        if len(trial) <= budget:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    dpi = 100
    fig = plt.figure(figsize=(WIDTH / dpi, 2 * HEIGHT / dpi), dpi=dpi)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(0, 2 * HEIGHT)
    total = len(lines)
    rub = (color[0] / 255, color[1] / 255, color[2] / 255)
    for index, line in enumerate(lines):
        y = HEIGHT + (total - 1) / 2 * size * line_gap - index * size * line_gap
        ax.text(WIDTH / 2, y, line, ha="center", va="center", fontproperties=prop,
                fontsize=size, color=rub)
    fig.canvas.draw()
    buffer = np.asarray(fig.canvas.buffer_rgba()).astype(np.float32) / 255.0
    plt.close(fig)
    # برش دقیق روی پیکسل‌های مرئی (bbox خودِ Matplotlib کل محور را برمی‌گرداند)
    mask = buffer[..., 3] > 0.02
    if not mask.any():
        return np.zeros((1, 1, 4), dtype=np.float32)
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    pad = 6
    y0, y1 = max(0, rows[0] - pad), min(buffer.shape[0], rows[-1] + 1 + pad)
    x0, x1 = max(0, cols[0] - pad), min(buffer.shape[1], cols[-1] + 1 + pad)
    return buffer[y0:y1, x0:x1]


# --------------------------------------------------------------- پس‌زمینه
def background() -> np.ndarray:
    """گرادیان سرمه‌ای عمودی + هالهٔ نرم بالا (بدون نویز تصادفی، قابل تکرار)."""
    rows = np.linspace(0.0, 1.0, HEIGHT, dtype=np.float32)[:, None]
    cols = np.linspace(0.0, 1.0, WIDTH, dtype=np.float32)[None, :]
    base = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
    for channel in range(3):
        base[..., channel] = DEEP[channel] / 255 * (1 - rows) + INK[channel] / 255 * rows
    glow = np.exp(-(((cols - 0.5) ** 2) / 0.18 + ((rows - 0.18) ** 2) / 0.05))
    for channel, amount in enumerate((0.10, 0.22, 0.40)):
        base[..., channel] += glow * amount
    return np.clip(base, 0, 1)


def orb(size: int = 300) -> tuple[np.ndarray, np.ndarray]:
    """کرهٔ برند: هستهٔ روشن، هالهٔ آبی و حلقهٔ نازک — به‌صورت RGBA آمادهٔ ترکیب."""
    canvas = size * 3
    yy, xx = np.mgrid[0:canvas, 0:canvas].astype(np.float32)
    cx = cy = canvas / 2
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (size / 2)
    rgba = np.zeros((canvas, canvas, 4), dtype=np.float32)
    core = np.clip(1.4 - dist, 0, 1) ** 0.6
    halo = np.exp(-(dist ** 1.6) * 1.3)
    for channel, (inner, outer) in enumerate(((0.20, 0.02), (0.72, 0.12), (1.0, 0.34))):
        rgba[..., channel] = np.clip(core * inner + halo * outer, 0, 1)
    ring = np.exp(-((dist - 1.02) ** 2) / 0.006) * 0.55
    for channel, amount in enumerate((0.28, 0.62, 1.0)):
        rgba[..., channel] = np.clip(rgba[..., channel] + ring * amount, 0, 1)
    rgba[..., 3] = np.clip(core + halo * 0.9 + ring, 0, 1)
    return rgba, dist


def composite_orb(frame: np.ndarray, sprite: np.ndarray, center: tuple[int, int],
                  scale: float, alpha: float) -> None:
    """کره را با اندازه و شفافیت دلخواه روی فریم می‌نشاند (نزدیک‌ترین همسایه)."""
    if alpha <= 0.001 or scale <= 0.01:
        return
    height, width = sprite.shape[:2]
    new_h = max(2, int(height * scale))
    new_w = max(2, int(width * scale))
    ys = (np.arange(new_h) * (height / new_h)).astype(np.int32)
    xs = (np.arange(new_w) * (width / new_w)).astype(np.int32)
    small = sprite[ys][:, xs]
    top = int(center[1] - new_h / 2)
    left = int(center[0] - new_w / 2)
    y0, x0 = max(0, top), max(0, left)
    y1, x1 = min(HEIGHT, top + new_h), min(WIDTH, left + new_w)
    if y1 <= y0 or x1 <= x0:
        return
    patch = small[y0 - top:y1 - top, x0 - left:x1 - left]
    src_alpha = patch[..., 3:4] * alpha
    frame[y0:y1, x0:x1, :3] = (frame[y0:y1, x0:x1, :3] * (1 - src_alpha)
                               + patch[..., :3] * src_alpha)


def overlay_text(frame: np.ndarray, layer: np.ndarray, alpha: float = 1.0,
                 offset_y: int = 0) -> None:
    """لایهٔ متن (RGBA) را وسط‌چین و با شفافیت روی فریم می‌گذارد."""
    if alpha <= 0.002:
        return
    height, width = layer.shape[:2]
    left = max(0, (WIDTH - width) // 2)
    right = min(WIDTH, left + width)
    y0 = max(0, offset_y)
    y1 = min(HEIGHT, offset_y + height)
    if y1 <= y0 or right <= left:
        return
    src = layer[y0 - offset_y:y1 - offset_y, :right - left]
    a = src[..., 3:4] * alpha
    frame[y0:y1, left:right, :3] = (frame[y0:y1, left:right, :3] * (1 - a)
                                    + src[..., :3] * a)


# --------------------------------------------------------------- صدا
def audio_duration(path: str) -> float:
    out = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", path, "-f", "s16le",
                          "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
                         capture_output=True, check=True).stdout
    return len(out) / 2 / SAMPLE_RATE


def decode_audio(path: str) -> np.ndarray:
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", path, "-f", "s16le",
                          "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def build_track(clips: list[np.ndarray]) -> np.ndarray:
    silence_gap = np.zeros(int(GAP * SAMPLE_RATE), dtype=np.float32)
    pieces = [np.zeros(int(LEAD_IN * SAMPLE_RATE), dtype=np.float32)]
    for clip in clips:
        pieces.extend([clip, silence_gap])
    pieces.append(np.zeros(int(TAIL * SAMPLE_RATE), dtype=np.float32))
    return np.concatenate(pieces)


def write_wav(path: str, samples: np.ndarray) -> None:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    gain = (0.94 / peak) if peak > 0.94 else 1.0
    data = np.clip(samples * gain, -1.0, 1.0)
    with wave.open(path, "w") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(SAMPLE_RATE)
        fh.writeframes((data * 32767).astype("<i2").tobytes())


# --------------------------------------------------------------- صحنه‌ها
def load_script() -> list[dict]:
    with open(SCRIPT_PATH, encoding="utf-8") as fh:
        return json.load(fh)["scenes"]


def build(args) -> int:
    fonts = ttf_fonts()
    ffmpeg = ffmpeg_bin()
    scenes = load_script()
    bg = background()
    sprite, _ = orb()

    clips: list[np.ndarray] = []
    durations: list[float] = []
    if not args.silent:
        for scene in scenes:
            path = os.path.join(AUDIO_DIR, f"{scene['id']}.mp3")
            if not os.path.exists(path):
                print(f"[intro] گفتار صحنهٔ {scene['id']} نیست: {path}")
                return 2
            clips.append(decode_audio(path))
            durations.append(audio_duration(path))
    else:
        durations = [max(3.0, 0.055 * len(scene["caption"])) for scene in scenes]

    if clips:
        track = build_track(clips)
    else:
        total = LEAD_IN + TAIL + sum(d + GAP for d in durations)
        track = np.zeros(int(total * SAMPLE_RATE), dtype=np.float32)
    audio_path = os.path.join(ROOT, "data", "intro", "voice", "_track.wav")
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    write_wav(audio_path, track)

    # زمان‌بندی صحنه‌ها روی محور صدا
    starts: list[float] = []
    cursor = LEAD_IN
    for duration in durations:
        starts.append(cursor)
        cursor += duration + GAP
    timeline = cursor + TAIL
    total_frames = int(round(timeline * FPS))

    layers = {scene["id"]: text_layer(scene["caption"], size=scene.get("size", 44),
                                     color=WHITE, weight=scene.get("weight", "Bold"),
                                     fonts=fonts)
              for scene in scenes}
    title_layer = text_layer("آموزش استفاده از رایان", size=30, color=SOFT, weight="Medium"
                             if "Medium" in fonts else "Regular", fonts=fonts)
    hint_layer = text_layer("برای شروع، دکمهٔ «شروع گفتگو» را بزن", size=26, color=SOFT,
                            weight="Regular", fonts=fonts)

    os.makedirs(OUT_DIR, exist_ok=True)
    poster: np.ndarray | None = None
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "-",
           "-i", audio_path, "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest",
           "-movflags", "+faststart", OUT_VIDEO]
    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)
    for index in range(total_frames):
        t = index / FPS
        frame[:] = bg
        # پرده: در ۰٫۴ ثانیهٔ اول از سیاهی روشن می‌شود
        fade = min(1.0, t / 0.4)

        # نقطهٔ فعال روی محور صدا
        active = None
        for order, scene in enumerate(scenes):
            begin = starts[order] - 0.15
            end = starts[order] + durations[order] + 0.15
            if begin <= t <= end:
                active = (order, scene, (t - begin) / max(0.001, end - begin))
                break
        if active is None:
            order = len(scenes) - 1
            scene = scenes[-1]
            local = 1.0
            last_start = starts[-1]
            if t < starts[0]:
                order, scene, local = -1, scenes[0], 0.0
            elif t > last_start + durations[-1]:
                order, scene, local = len(scenes), scenes[-1], 1.0
        else:
            order, scene, local = active

        # کره: نفس‌کشیدن آرام + ضربان هنگام شروع جملهٔ تازه
        pulse = 0.5 + 0.5 * np.sin(2 * np.pi * 0.22 * t)
        pop = max(0.0, 1.0 - ((t - starts[max(0, min(order, len(starts) - 1))]) / 0.45)) if 0 <= order < len(starts) else 0.0
        orb_scale = 0.52 + 0.04 * pulse + 0.10 * pop
        orb_center = (WIDTH // 2, int(HEIGHT * 0.33))
        composite_orb(frame, sprite, orb_center, orb_scale, 0.95 * fade + 0.05)

        # عنوان بالا
        overlay_text(frame, title_layer, alpha=0.85 * fade, offset_y=int(HEIGHT * 0.055))
        # جملهٔ صحنه: پرش می‌کند، می‌ماند و محو می‌شود
        if 0 <= order < len(scenes):
            appear = min(1.0, max(0.0, (t - starts[order] + 0.15) / 0.28))
            remain = (starts[order] + durations[order] + 0.15) - t
            vanish = min(1.0, max(0.0, remain / 0.25))
            layer = layers[scene["id"]]
            overlay_text(frame, layer, alpha=appear * vanish,
                         offset_y=int(HEIGHT * 0.60) - layer.shape[0] // 2)
        else:
            overlay_text(frame, hint_layer, alpha=0.9 * fade,
                         offset_y=int(HEIGHT * 0.60) - hint_layer.shape[0] // 2)

        # نوار پیشرفت پایین
        progress = min(1.0, t / timeline)
        bar_w = int(WIDTH * progress)
        frame[HEIGHT - 6:HEIGHT - 2, :bar_w, :] = np.array(CYAN, dtype=np.float32) / 255
        frame[HEIGHT - 6:HEIGHT - 2, bar_w:, :] = np.array(BLUE, dtype=np.float32) / 255 * 0.18

        if poster is None and t >= (starts[0] + 1.2 if starts else 1.2):
            poster = (np.clip(frame, 0, 1) * 255).astype(np.uint8).copy()

        process.stdin.write((np.clip(frame, 0, 1) * 255).astype(np.uint8).tobytes())
        if index % 250 == 0:
            print(f"[intro] فریم {index}/{total_frames} ({t:.1f}s)", flush=True)

    process.stdin.close()
    code = process.wait()
    if code != 0:
        print(f"[intro] ffmpeg با کد {code} تمام شد")
        return code

    if poster is not None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.imsave(OUT_POSTER, poster)

    size_mb = os.path.getsize(OUT_VIDEO) / 1e6
    summary = {"video": os.path.relpath(OUT_VIDEO, ROOT), "poster": os.path.relpath(OUT_POSTER, ROOT),
               "seconds": round(timeline, 2), "frames": total_frames, "fps": FPS,
               "resolution": f"{WIDTH}x{HEIGHT}", "scenes": len(scenes),
               "bytes": os.path.getsize(OUT_VIDEO), "size_mb": round(size_mb, 2),
               "narrated": not args.silent}
    with open(os.path.join(ROOT, "reports", "intro-video.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def check() -> int:
    info = {"ffmpeg": ffmpeg_bin(), "fonts": ttf_fonts(),
            "script": os.path.exists(SCRIPT_PATH)}
    info["voice_clips"] = sorted(
        name for name in os.listdir(AUDIO_DIR) if name.endswith(".mp3")
    ) if os.path.isdir(AUDIO_DIR) else []
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--silent", action="store_true")
    args = parser.parse_args()
    return check() if args.check else build(args)


if __name__ == "__main__":
    raise SystemExit(main())
