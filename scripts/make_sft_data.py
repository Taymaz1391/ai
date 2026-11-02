#!/usr/bin/env python3
"""ساخت دادهٔ نمایشی (demonstration) برای مرحلهٔ SFT از پیکرهٔ دانشنامه.

ChatGPT با حدود ۱۳٬۰۰۰ پرسش–پاسخِ نوشتهٔ انسان تنظیم دستورمحور شد. این‌جا
انسان در دسترس نیست، پس داده از سرنخِ مقاله‌های دانشنامه ساخته می‌شود:
عنوان مقاله پرسش می‌شود و بندِ نخستِ مقاله پاسخ است. این «نمایشِ انسانی» نیست
و در گزارش هم همین‌طور گفته می‌شود؛ ولی مدل یاد می‌گیرد به پرسش «چیست؟»
با توضیح واقعی پاسخ بدهد، نه با ادامهٔ تصادفی متن.

    python scripts/make_sft_data.py --limit 4000 --out data/sft_wiki.jsonl
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

DOC_SEP = "<|doc|>"
BAD = re.compile(r"[\[\]{}<>|=*#\\]|https?://|رده:|پرونده:")
PERSIAN = re.compile(r"[\u0600-\u06FF]")
SENTENCE_END = "۔.!؟?؛"

TEMPLATES = (
    "{title} چیست؟",
    "{title} را توضیح بده.",
    "دربارهٔ {title} توضیح بده.",
    "{title} چه چیزی است؟",
)


def eval_titles() -> set[str]:
    """موضوع‌هایی که در مجموعهٔ سنجش هستنذ تا آلودگی وارد نشود."""
    from eval_qa import CASES

    words: set[str] = set()
    for question, expected in CASES:
        words.update(word.strip("؟?.!،") for word in question.split() if len(word) > 2)
        words.update(expected)
    return words


def clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("ي", "ی").replace("ك", "ک")


def lead_sentences(body: str, limit: int = 2) -> str:
    out: list[str] = []
    for raw in re.split(r"(?<=[.!؟?])\s+", body):
        sentence = clean(raw)
        if len(sentence) < 12:
            continue
        out.append(sentence)
        if len(out) >= limit or sum(len(s) for s in out) >= 180:
            break
    return " ".join(out)


def iter_docs(path: str):
    with open(path, encoding="utf-8") as fh:
        for block in fh.read().split(DOC_SEP):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if len(lines) < 3:
                continue
            yield lines[0], " ".join(lines[1:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wiki", default="/home/user/corpora/wiki.txt")
    parser.add_argument("--out", default="data/sft_wiki.jsonl")
    parser.add_argument("--limit", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=21)
    args = parser.parse_args()

    blocked = eval_titles()
    rng = random.Random(args.seed)
    rows: list[dict] = []
    seen_titles: set[str] = set()
    for title, body in iter_docs(args.wiki):
        title = clean(title)
        if not (2 <= len(title) <= 40) or len(title.split()) > 6:
            continue
        if not PERSIAN.search(title) or BAD.search(title) or title in seen_titles:
            continue
        if any(word and word in title for word in blocked):
            continue
        answer = lead_sentences(body)
        if not (40 <= len(answer) <= 260) or BAD.search(answer):
            continue
        if not PERSIAN.search(answer):
            continue
        seen_titles.add(title)
        rows.append({"user": rng.choice(TEMPLATES).format(title=title),
                     "assistant": answer, "source": "wiki", "title": title})
        if len(rows) >= args.limit:
            break
    if not rows:
        print("هیچ نمونه‌ای ساخته نشد؛ مسیر پیکره را بررسی کن")
        return 1

    path = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    lengths = sorted(len(row["assistant"]) for row in rows)
    print(json.dumps({
        "pairs": len(rows),
        "out": os.path.relpath(path, ROOT),
        "answer_chars_median": lengths[len(lengths) // 2],
        "answer_chars_max": lengths[-1],
        "examples": rows[:3],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
