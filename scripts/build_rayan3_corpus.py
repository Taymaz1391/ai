#!/usr/bin/env python3
"""ساختِ پیکرهٔ رایان ۳ از داده‌های خودِ پروژه.

هدف: مدلِ صفرآموختهٔ رایان به‌جای «ادامهٔ متن»، *پاسخ‌دادن* را یاد بگیرد.
همهٔ داده از مخزن خودِ پروژه است؛ هیچ مدل یا سرویسِ بیرونی در کار نیست.

    python scripts/build_rayan3_corpus.py --out-dir data/rayan3

خروجی:
    train.txt  متنِ آموزش با نشانه‌های گفتگو
    val.txt    پرسش–پاسخ‌های کنارگذاشته (۱۰٪)، برای سنجشِ دستورپذیری
    val_raw.txt متنِ خامِ کنارگذاشته، برای سنجشِ زبان‌مدلِ عمومی
    stats.json تعداد نمونه‌ها و نویسه‌ها
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DOC = "<|doc|>"
USER = "<|user|>"
BOT = "<|bot|>"
NL = "<|nl|>"

_SPACES = re.compile(r"[ \t\u200c]+")
_BAD = re.compile(r"[<>{}|]|https?://|رده:|پرونده:|\[\[|\]\]")


def clean(text: str) -> str:
    """نویسه‌های فارسی، فاصله‌های یکسان و حذفِ نشانه‌های ویکی."""
    text = (text or "").replace("ي", "ی").replace("ك", "ک").replace("\u200f", "")
    text = _SPACES.sub(" ", text.replace("\r", " "))
    return text.strip()


def usable(question: str, answer: str) -> bool:
    q, a = clean(question), clean(answer)
    if len(q) < 4 or len(a) < 20:
        return False
    if _BAD.search(q) or _BAD.search(a):
        return False
    if len(q) > 180 or len(a) > 900:
        return False
    # پاسخ باید بیشترش فارسی باشد
    persian = sum(1 for ch in a if "\u0600" <= ch <= "\u06FF")
    return persian / max(1, len(a)) > 0.55


def pair(q: str, a: str) -> str:
    return f"{DOC} {USER} {clean(q)} {BOT} {clean(a)} {NL}"


def load_pairs() -> list[tuple[str, str, str]]:
    """(پرسش، پاسخ، منبع) از فایل‌های خودِ مخزن."""
    rows: list[tuple[str, str, str]] = []

    path = os.path.join(ROOT, "data", "sft_wiki.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            q, a = row.get("user") or row.get("instruction") or "", row.get("assistant") or row.get("output") or ""
            if usable(q, a):
                rows.append((q, a, "wiki"))

    path = os.path.join(ROOT, "data", "chat_seed.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            q, a = row.get("user", ""), row.get("assistant", "")
            if usable(q, a):
                rows.append((q, a, "chat"))

    path = os.path.join(ROOT, "data", "knowledge-pack.jsonl")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            q, a = row.get("q", ""), row.get("a", "")
            if usable(q, a):
                rows.append((q, a, "pack"))

    # حذفِ تکراری‌ها بر اساسِ پرسشِ نرمال‌شده
    seen: set[str] = set()
    unique: list[tuple[str, str, str]] = []
    for q, a, src in rows:
        key = clean(q).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append((q, a, src))
    return unique


def raw_blocks(path: str, max_chars: int) -> list[str]:
    """متنِ خام را به بندهای کوتاه می‌شکند تا پنجره‌های آموزش متنوع شوند."""
    if not os.path.exists(path):
        return []
    text = open(path, encoding="utf-8", errors="ignore").read(max_chars)
    blocks: list[str] = []
    for chunk in text.split("\n\n"):
        chunk = clean(chunk)
        if len(chunk) < 120:
            continue
        while len(chunk) > 700:
            cut = chunk.rfind("۔", 200, 700)
            if cut < 0:
                cut = chunk.rfind(".", 200, 700)
            if cut < 0:
                cut = 700
            blocks.append(chunk[:cut + 1])
            chunk = chunk[cut + 1:].strip()
        if len(chunk) >= 120:
            blocks.append(chunk)
    return blocks


def main() -> None:
    parser = argparse.ArgumentParser(description="ساختِ پیکرهٔ رایان ۳")
    parser.add_argument("--out-dir", default="data/rayan3")
    parser.add_argument("--raw", default="data/index-sample-3m.txt")
    parser.add_argument("--raw-chars", type=int, default=2_400_000)
    parser.add_argument("--val-share", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    out_dir = os.path.join(ROOT, args.out_dir) if not os.path.isabs(args.out_dir) else args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(args.seed)

    pairs = load_pairs()
    rng.shuffle(pairs)
    cut = max(50, int(len(pairs) * args.val_share))
    val_pairs, train_pairs = pairs[:cut], pairs[cut:]

    blocks = raw_blocks(os.path.join(ROOT, args.raw), args.raw_chars)
    rng.shuffle(blocks)
    raw_cut = max(20, int(len(blocks) * 0.05))
    val_blocks, train_blocks = blocks[:raw_cut], blocks[raw_cut:]

    # در آموزش، هر گفتگو دو بار (با ترتیبِ ثابت) می‌آید و متنِ خام در میان‌شان
    chat_lines = [pair(q, a) for q, a, _src in train_pairs]
    raw_lines = [f"{DOC} {block} {NL}" for block in train_blocks]
    lines = chat_lines + raw_lines
    rng.shuffle(lines)
    train_text = "\n".join(lines) + "\n"

    val_chat = "\n".join(pair(q, a) for q, a, _src in val_pairs) + "\n"
    val_raw = "\n".join(f"{DOC} {block} {NL}" for block in val_blocks) + "\n"

    for name, text in (("train.txt", train_text), ("val.txt", val_chat),
                       ("val_raw.txt", val_raw)):
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    by_source: dict[str, int] = {}
    for _q, _a, src in train_pairs:
        by_source[src] = by_source.get(src, 0) + 1
    stats = {
        "pairs_total": len(pairs),
        "pairs_train": len(train_pairs),
        "pairs_val": len(val_pairs),
        "pairs_by_source": by_source,
        "raw_blocks_train": len(train_blocks),
        "raw_blocks_val": len(val_blocks),
        "train_chars": len(train_text),
        "val_chars": len(val_chat),
        "val_raw_chars": len(val_raw),
    }
    with open(os.path.join(out_dir, "stats.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1)
    print(json.dumps(stats, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
