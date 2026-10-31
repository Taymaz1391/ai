"""ساخت پیکرهٔ آموزش پارسیا از منابع فارسی (خبر، کتاب، شعر و گفتگوی آغازین).

منابع خام در پوشهٔ بیرونی نگه داشته می‌شوند و خروجی پاک‌شده در data/ نوشته می‌شود.

    python data/build_corpus.py --sources /home/user/corpora --out data

خروجی:
    data/train.txt       متن آموزش با جداکنندهٔ <|doc|>
    data/val.txt         متن اعتبارسنجی
    data/corpus_stats.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsia.text import (  # noqa: E402
    is_clean_persian,
    normalize,
    persian_ratio,
    remove_boilerplate,
    word_count,
)

DOC = "<|doc|>"
VERSE = "<|verse|>"

SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+")


@dataclass
class Pools:
    news: list[str] = field(default_factory=list)
    poetry: list[str] = field(default_factory=list)
    chat: list[str] = field(default_factory=list)

    def chars(self) -> dict[str, int]:
        return {k: sum(len(x) for x in getattr(self, k)) for k in ("news", "poetry", "chat")}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = hashlib.blake2b(item[:220].encode("utf-8"), digest_size=8).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _split_long(text: str, max_chars: int = 1400) -> list[str]:
    """پاراگراف‌های بلند را در مرز جمله به قطعه‌های قابل‌آموزش می‌شکند."""
    if len(text) <= max_chars:
        return [text] if text else []
    pieces, current = [], ""
    for sentence in SENTENCE_END.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return [p for p in pieces if len(p) >= 80]


def add_news(pool: list[str], title: str, body: str) -> None:
    title = normalize(title)
    body = normalize(body)
    body = remove_boilerplate(body)
    if len(title) < 12 or len(body) < 60:
        return
    # اگر توضیح با تیتر شروع می‌شود، تکرارش نکن.
    if body.startswith(title[:40]):
        text = body
    else:
        text = f"{title}.\n{body}"
    if not is_clean_persian(text, min_ratio=0.78):
        return
    if word_count(text) < 18:
        return
    # متن‌های پرشماره یا فهرست‌وار ارزش آموزش کمی دارند.
    if text.count("|") > 2 or text.count("\n") > 12:
        return
    for piece in _split_long(text):
        if persian_ratio(piece) >= 0.75 and word_count(piece) >= 18:
            pool.append(piece)


def load_news(path: str) -> list[str]:
    pool: list[str] = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            add_news(pool, row.get("title") or "", row.get("description") or "")
    return pool


def load_hamshahri(path: str) -> list[str]:
    pool: list[str] = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            add_news(pool, row.get("Title") or "", row.get("Text") or "")
    return pool


def load_poetry(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    poems: list[str] = []
    items = data if isinstance(data, list) else [data]
    for item in items:
        if not isinstance(item, dict):
            continue
        for value in item.values():
            if not isinstance(value, dict):
                continue
            raw = value.get("Poem") or ""
            lines = [normalize(line) for line in raw.split("\n")]
            lines = [line for line in lines if word_count(line) >= 2]
            if len(lines) < 2:
                continue
            doc = f" {VERSE} ".join(lines)
            if len(doc) < 40 or len(doc) > 1600:
                continue
            if not is_clean_persian(doc, min_ratio=0.62):
                continue
            poems.append(doc)
    return poems


def load_chat(path: str) -> list[str]:
    docs: list[str] = []
    if not os.path.exists(path):
        return docs
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            user = normalize(item["user"])
            assistant = normalize(item["assistant"])
            if user and assistant:
                docs.append(f"<|user|> {user} <|bot|> {assistant}")
    return docs


def sample_chars(items: list[str], target_chars: int, rng: random.Random) -> list[str]:
    if sum(len(x) for x in items) <= target_chars:
        return list(items)
    shuffled = list(items)
    rng.shuffle(shuffled)
    out: list[str] = []
    total = 0
    for item in shuffled:
        out.append(item)
        total += len(item) + len(DOC) + 2
        if total >= target_chars:
            break
    return out


def write_split(docs: list[str], out_dir: str) -> int:
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(20261031)
    rng.shuffle(docs)
    val_size = max(1, int(len(docs) * 0.02))
    val, train = docs[:val_size], docs[val_size:]
    for name, part in (("train.txt", train), ("val.txt", val)):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            f.write((f"\n{DOC}\n").join(part))
            f.write("\n")
    return len(train)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="/home/user/corpora")
    parser.add_argument("--out", default="data")
    parser.add_argument("--news-chars", type=int, default=13_500_000)
    parser.add_argument("--poetry-chars", type=int, default=9_000_000)
    parser.add_argument("--chat-repeat", type=int, default=18)
    args = parser.parse_args()

    root = args.sources
    p = Pools()
    news_files = [
        ("milad-4274_persian_news/persian_news-master/main_news.csv", load_news),
        ("danialfarsi_hamshahri_corpus/hamshahri_corpus-main/train_data_encoded.csv", load_hamshahri),
    ]
    for rel, loader in news_files:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            print(f"[!] missing {path}")
            continue
        docs = loader(path)
        print(f"[+] {rel}: {len(docs):,} docs, {sum(map(len, docs))/1e6:.1f} MB")
        p.news.extend(docs)

    poem_dir = os.path.join(root, "namnamir_JSON_of_Classic_Persian_Poems/JSON_of_Classic_Persian_Poems-master")
    for name in ("poem.json", "Molana.json", "Saadi.json", "Hafez.json", "Khayam.json"):
        path = os.path.join(poem_dir, name)
        if not os.path.exists(path):
            print(f"[!] missing {path}")
            continue
        docs = load_poetry(path)
        print(f"[+] {name}: {len(docs):,} poems, {sum(map(len, docs))/1e6:.1f} MB")
        p.poetry.extend(docs)

    p.chat = load_chat(os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_seed.jsonl"))
    print(f"[+] chat seeds: {len(p.chat)} docs")

    p.news = _dedupe(p.news)
    p.poetry = _dedupe(p.poetry)

    rng = random.Random(7)
    news = sample_chars(p.news, args.news_chars, rng)
    poetry = sample_chars(p.poetry, args.poetry_chars, rng)
    chat = p.chat * args.chat_repeat

    docs = news + poetry + chat
    rng.shuffle(docs)
    n_train = write_split(docs, args.out)

    stats = {
        "news_chars": sum(len(x) for x in news),
        "poetry_chars": sum(len(x) for x in poetry),
        "chat_chars": sum(len(x) for x in p.chat),
        "train_docs": n_train,
        "val_docs": len(docs) - n_train,
        "train_chars": os.path.getsize(os.path.join(args.out, "train.txt")),
        "val_chars": os.path.getsize(os.path.join(args.out, "val.txt")),
        "news_docs": len(news),
        "poetry_docs": len(poetry),
        "chat_docs": len(chat),
        "sources": {
            "news": "Persian News Dataset (milad-4274) + Hamshahri corpus",
            "poetry": "JSON of Classic Persian Poems (namnamir, from ganjoor.net)",
        },
    }
    with open(os.path.join(args.out, "corpus_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
