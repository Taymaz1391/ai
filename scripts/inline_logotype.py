#!/usr/bin/env python3
"""جایگزینی نام متنی برند با لوگوتایپ تصویری در همهٔ صفحه‌ها.

    python scripts/inline_logotype.py [--check]

قاعده: هر جا نام برند **دیده می‌شود** باید تصویر لوگو باشد، نه متن.
سه جا استثناست و دست‌نخورده می‌ماند:

* ``<title>`` — تب مرورگر و نتیجهٔ جست‌وجو متن می‌خواهد، تصویر نمی‌پذیرد.
* ``alt`` و ``aria-label`` و ``title`` — برای صفحه‌خوان و موتور جست‌وجو، متن
  دقیقاً همان چیزی است که باید باشد.
* کد داخل ``<script>``/``<style>`` — منطق است، نه متن دیده‌شدنی.

با ``--check`` فقط گزارش می‌دهد و چیزی نمی‌نویسد (برای CI).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"

NAMES = ("رایان", "Rayan")
PROTECTED = re.compile(r"(<title>.*?</title>|<script.*?</script>|<style.*?</style>|<!--.*?-->)", re.S)
TEXT_NODE = re.compile(r">([^<>]*?)<")
ATTR_ONLY = re.compile(r"\b(alt|aria-label|title|aria-labelledby|content)=\"[^\"]*\"")

LOGOS = {
    "fa": (
        '<img class="wm-inline wordmark-for-light" src="/static/assets/brand/mark-ink.png" '
        'alt="رایان" width="1026" height="520" decoding="async">'
        '<img class="wm-inline wordmark-for-dark" src="/static/assets/brand/mark-white.png" '
        'alt="رایان" width="1026" height="520" decoding="async">'
    ),
    "en": (
        '<img class="wm-inline wordmark-for-light" src="/static/assets/brand/mark-ink.png" '
        'alt="Rayan" width="1026" height="520" decoding="async">'
        '<img class="wm-inline wordmark-for-dark" src="/static/assets/brand/mark-white.png" '
        'alt="Rayan" width="1026" height="520" decoding="async">'
    ),
}


def page_lang(html: str) -> str:
    match = re.search(r'<html[^>]*lang="([a-z]{2})"', html)
    return "en" if match and match.group(1) == "en" else "fa"


def convert(html: str, lang: str) -> tuple[str, int]:
    logo = LOGOS[lang]
    names = NAMES if lang == "fa" else ("Rayan",)
    count = 0

    def fix_text(match: re.Match) -> str:
        nonlocal count
        text = match.group(1)
        if not any(name in text for name in names):
            return match.group(0)
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        core = text.strip()
        for name in names:
            if name in core:
                count += core.count(name)
                core = core.replace(name, "\x00")
        core = re.sub(r"[ \t]*\x00[ \t]*", "\x00", core)
        core = core.replace("\x00", f" {logo} ")
        core = re.sub(r" {2,}", " ", core)
        return ">" + lead + core + trail + "<"

    stashed: list[str] = []

    def stash(match: re.Match) -> str:
        stashed.append(match.group(0))
        return f"\x01{len(stashed) - 1}\x01"

    body = PROTECTED.sub(stash, html)
    body = TEXT_NODE.sub(fix_text, body)
    body = re.sub(r"\x01(\d+)\x01", lambda m: stashed[int(m.group(1))], body)
    return body, count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="فقط گزارش، بدون نوشتن")
    args = ap.parse_args()

    total = 0
    problems: list[str] = []
    for path in sorted(STATIC.glob("*.html")):
        html = path.read_text(encoding="utf-8")
        lang = page_lang(html)
        new, count = convert(html, lang)
        if args.check:
            left = [
                line.strip()[:90]
                for line in new.splitlines()
                if any(n in line for n in (NAMES if lang == "fa" else ("Rayan",)))
                and "<title" not in line and "alt=" not in line and 'aria-label' not in line
                and "content=" not in line
            ]
            if left:
                problems.append(f"{path.name}: {len(left)} مورد باقی مانده")
                for line in left[:4]:
                    problems.append(f"    {line}")
            continue
        if count:
            path.write_text(new, encoding="utf-8")
            total += count
            print(f"[logotype] {path.name}: {count} جایگزین")

    if args.check:
        if problems:
            print("موارد متنی باقی‌مانده:")
            print("\n".join(problems))
            return 1
        print("logotype check ok: هیچ نام متنی دیده‌شدنی نماند")
        return 0
    print(f"[logotype] مجموع {total} جایگزین")
    return 0


if __name__ == "__main__":
    sys.exit(main())
