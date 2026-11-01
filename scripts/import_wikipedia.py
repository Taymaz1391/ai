#!/usr/bin/env python3
"""استخراج متن مقاله‌های ویکی‌پدیای فارسی از zipهای مخزن Text-Mining.

ورودی، پوشه‌ای است که فایل‌های ``fawiki-*.zip`` (هرکدام یک JSONL با فیلد ``Text``)
در آن قرار دارد. خروجی یک فایل متنی یک‌پارچه است که پیکرهٔ آموزش رایان را غنی می‌کند.

    python scripts/import_wikipedia.py --src ../corpora/_wiki/repo \\
        --out ../corpora/wiki.txt --max-chars 300000000

قواعد پاک‌سازی عمداً محافظه‌کارانه‌اند: فقط نشانه‌گذاری ویکی برداشته می‌شود و متن
انسان‌نوشته دست‌نخورده می‌ماند. صفحه‌های رده/الگو/تغییرمسیر و ابهام‌زدایی حذف
می‌شوند و مقالهٔ کوتاه‌تر از حد آستانه کنار می‌رود.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

DOC_SEP = "<|doc|>"

# ---------------------------------------------------------------- پاک‌سازی ویکی
_RE_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}", re.S)
_RE_REF = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
_RE_TABLE = re.compile(r"\{\|.*?\|\}", re.S)
_RE_TAG = re.compile(r"<[^>]{1,120}>")
_RE_FILE = re.compile(r"\[\[(?:پرونده|تصویر|File|Image):[^\]]*\]\]", re.I)
_RE_LINK_LABEL = re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]")
_RE_LINK = re.compile(r"\[\[([^\]]*)\]\]")
_RE_EXT_LINK = re.compile(r"\[https?://\S+\s*([^\]]*)\]")
_RE_HEADING = re.compile(r"^=+\s*(.*?)\s*=+\s*$", re.M)
_RE_QUOTE = re.compile(r"^[*#:;]+\s*", re.M)
_RE_ENTITY = re.compile(r"&(?:nbsp|amp|lt|gt|quot);")
_RE_SPACES = re.compile(r"[ \t\u00a0]+")
_RE_BLANKS = re.compile(r"\n{3,}")

_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"'}


def clean_wiki(text: str) -> str:
    """نشانه‌گذاری ویکی را می‌زداید و متن خوانا برمی‌گرداند."""
    if not text:
        return ""
    text = _RE_COMMENT.sub("", text) if (_RE_COMMENT := re.compile(r"<!--.*?-->", re.S)) else text
    text = _RE_REF.sub("", text)
    text = _RE_TABLE.sub("", text)
    for _ in range(3):                      # الگوهای تودرتو
        text = _RE_TEMPLATE.sub("", text)
    text = _RE_FILE.sub("", text)
    text = _RE_LINK_LABEL.sub(r"\1", text)
    text = _RE_LINK.sub(r"\1", text)
    text = _RE_EXT_LINK.sub(r"\1", text)
    text = _RE_HEADING.sub(r"\1", text)
    text = _RE_QUOTE.sub("", text)
    text = _RE_TAG.sub("", text)
    text = _RE_ENTITY.sub(lambda m: _ENTITIES[m.group(0)], text)
    text = text.replace("'''", "").replace("''", "")
    text = _RE_SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _RE_BLANKS.sub("\n\n", text).strip()


def iter_zip(path: str):
    """مقاله‌های یک zip را یکی‌یکی می‌خواند (بدون بار کردن کل فایل)."""
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            with zf.open(name) as fh:
                for raw in fh:
                    try:
                        item = json.loads(raw)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    yield item


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=os.path.join(ROOT, "..", "corpora", "_wiki", "repo"))
    parser.add_argument("--out", default=os.path.join(ROOT, "..", "corpora", "wiki.txt"))
    parser.add_argument("--max-chars", type=int, default=300_000_000)
    parser.add_argument("--min-article-chars", type=int, default=400)
    args = parser.parse_args()

    zips: list[str] = []
    for base, _dirs, files in os.walk(args.src):
        for name in sorted(files):
            if name.endswith(".zip") and name.startswith("fawiki"):
                zips.append(os.path.join(base, name))
    if not zips:
        raise SystemExit(f"هیچ zip ویکی‌ای در {args.src} پیدا نشد")
    zips.sort()

    written = 0
    docs = 0
    skipped = {"category": 0, "redirect": 0, "disambig": 0, "short": 0, "empty": 0}
    started = time.time()

    with open(args.out, "w", encoding="utf-8") as out:
        for path in zips:
            print(f"[+] {os.path.basename(path)}", flush=True)
            for item in iter_zip(path):
                if item.get("Namespace") not in (0, None):
                    skipped["category"] += 1
                    continue
                if item.get("RedirectList") or item.get("IsRedirect"):
                    skipped["redirect"] += 1
                    continue
                if item.get("IsDisambiguationPage"):
                    skipped["disambig"] += 1
                    continue
                body = clean_wiki(item.get("Text") or "")
                title = (item.get("Title") or "").strip()
                if len(body) < args.min_article_chars:
                    skipped["short"] += 1
                    continue
                block = f"{title}\n{body}" if title else body
                if not block.strip():
                    skipped["empty"] += 1
                    continue
                out.write(block)
                out.write(f"\n{DOC_SEP}\n")
                written += len(block) + len(DOC_SEP) + 2
                docs += 1
                if written >= args.max_chars:
                    break
            if written >= args.max_chars:
                print(f"[=] به سقف {args.max_chars:,} نویسه رسیدیم", flush=True)
                break

    elapsed = time.time() - started
    print(json.dumps({
        "chars": written, "docs": docs, "seconds": round(elapsed, 1),
        "docs_per_s": round(docs / max(elapsed, 0.1), 1),
        "chars_per_s": round(written / max(elapsed, 0.1)),
        "skipped": skipped, "out": os.path.abspath(args.out),
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
