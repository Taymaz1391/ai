#!/usr/bin/env python3
"""بازبینی کنتراست رنگ‌های تم رایان (WCAG 2.1) — بدون وابستگی بیرونی.

    python scripts/theme_audit.py            # گزارش کامل
    python scripts/theme_audit.py --quiet    # فقط خطاها؛ کد خروج ۱ اگر چیزی رد شد
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "web" / "static" / "styles.css"

# جفت‌هایی که باید خوانا باشند: (توکن متن، توکن پس‌زمینه، حداقل کنتراست، توضیح)
PAIRS = [
    ("text", "bg", 7.0, "متن اصلی روی پس‌زمینه"),
    ("text-2", "bg", 4.5, "متن دوم روی پس‌زمینه"),
    ("text-3", "bg", 4.5, "متن کم‌رنگ روی پس‌زمینه"),
    ("text", "bg-2", 7.0, "متن اصلی روی پس‌زمینهٔ دوم"),
    ("text-2", "bg-2", 4.5, "متن دوم روی پس‌زمینهٔ دوم"),
    ("text-3", "bg-2", 4.5, "متن کم‌رنگ روی پس‌زمینهٔ دوم"),
    ("text", "surface-solid", 7.0, "متن روی کارت"),
    ("text-3", "surface-solid", 4.5, "متن کم‌رنگ روی کارت"),
    ("blue", "bg", 4.5, "پیوند روی پس‌زمینه"),
    ("blue", "surface-solid", 4.5, "پیوند روی کارت"),
    ("rose", "bg", 4.5, "هشدار روی پس‌زمینه"),
    ("mint", "bg", 4.5, "موفقیت روی پس‌زمینه"),
    ("amber", "bg", 4.5, "اخطار روی پس‌زمینه"),
]

HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")


def _section(css: str, selector: str) -> str:
    start = css.index(selector)
    end = css.index("}", start)
    return css[start:end]


def tokens(block: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for name, value in re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", block):
        found[name] = value.strip()
    return found


def parse_color(value: str) -> tuple[int, int, int] | None:
    m = HEX.search(value or "")
    if not m:
        return None
    raw = m.group(1)
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def gradient_stops(value: str) -> list[tuple[int, int, int]]:
    stops = [parse_color(m.group(0)) for m in HEX.finditer(value or "")]
    return [s for s in stops if s]


def audit() -> list[tuple[str, bool, str]]:
    css = CSS.read_text(encoding="utf-8")
    themes = {
        "light": tokens(_section(css, ":root {")),
        "dark": tokens(_section(css, '[data-theme="dark"] {')),
    }
    rows: list[tuple[str, bool, str]] = []

    for theme, tok in themes.items():
        for fg, bg, need, label in PAIRS:
            fg_rgb, bg_rgb = parse_color(tok.get(fg, "")), parse_color(tok.get(bg, ""))
            if not fg_rgb or not bg_rgb:
                rows.append((f"{theme}: {label}", False, f"توکن نامعتبر ({fg} روی {bg})"))
                continue
            ratio = contrast(fg_rgb, bg_rgb)
            rows.append((f"{theme}: {label}", ratio >= need, f"{ratio:.2f}:1 (حداقل {need})"))

        # متن روی دکمهٔ گرادیانی
        on_accent = parse_color(tok.get("on-accent", ""))
        stops = gradient_stops(tok.get("grad", ""))
        if on_accent and stops:
            worst = min(contrast(on_accent, stop) for stop in stops)
            rows.append((f"{theme}: متن روی گرادیان", worst >= 4.5, f"{worst:.2f}:1 (حداقل 4.5)"))
        else:
            rows.append((f"{theme}: متن روی گرادیان", False, "on-accent یا grad تعریف نشده"))

        # نوار کنار: متن روی دو سر گرادیان
        side = gradient_stops(tok.get("sidebar-bg", "")) or [parse_color(tok.get("surface-solid", "")) or (0, 0, 0)]
        text = parse_color(tok.get("text", ""))
        if text:
            worst = min(contrast(text, stop) for stop in side if stop)
            rows.append((f"{theme}: متن روی نوار کنار", worst >= 7.0, f"{worst:.2f}:1 (حداقل 7)"))

        # دکمهٔ پر رنگ
        solid, on = parse_color(tok.get("accent-solid", "")), parse_color(tok.get("on-accent", ""))
        if solid and on:
            ratio = contrast(solid, on)
            rows.append((f"{theme}: متن روی دکمهٔ رنگ اصلی", ratio >= 4.5, f"{ratio:.2f}:1 (حداقل 4.5)"))
        else:
            rows.append((f"{theme}: متن روی دکمهٔ رنگ اصلی", False, "accent-solid تعریف نشده"))

    # هیچ توکن مصرف‌شده‌ای نباید تعریف‌نشده بماند
    used = set(re.findall(r"var\(--([a-z0-9-]+)", css))
    # متغیرهای محلی (مثل --btn-rest داخل .btn) هم معتبرند
    defined = set(re.findall(r"--([a-z0-9-]+)\s*:", css))
    missing = sorted(v for v in used if v not in defined)
    rows.append(("همهٔ توکن‌های مصرف‌شده تعریف شده‌اند", not missing, ", ".join(missing) or "ok"))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    rows = audit()
    failed = [r for r in rows if not r[1]]
    if not args.quiet:
        for name, ok, detail in rows:
            print(f"{'✓' if ok else '✗'} {name} — {detail}")
    for name, _ok, detail in failed:
        print(f"FAIL {name}: {detail}")
    print(f"\n{len(rows) - len(failed)}/{len(rows)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
