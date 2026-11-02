#!/usr/bin/env python3
"""ساخت پیکرهٔ train/val از چند منبع متنی، جریانی و با سقف مشخص برای هر منبع.

    python scripts/merge_corpus.py --out data \\
        --inputs data/train-v1.txt:20000000 ../corpora/wiki.txt:26000000 \\
                 ../corpora/mizan/ext/mizan/mizan_fa.txt:40000000 \\
                 ../corpora/poems/normalized:25000000 ../corpora/miras-sample.txt:6600000

* ``file:cap`` یعنی حداکثر نویسهٔ بردار از آن منبع؛ اگر پوشه بدهی همهٔ ``*.txt`` آن
  به‌ترتیب نام خوانده می‌شود.
* متنی که جداکنندهٔ ``<|doc|>`` دارد همان‌طور سندبه‌سند شکسته می‌شود؛ وگرنه به
  قطعه‌های ``--chunk-chars`` نویسه‌ای (روی مرز خط) تقسیم می‌شود.
* تکراری‌ها با هش ۶۴ بیتی حذف می‌شوند و سندهای کوتاه کنار می‌روند.
* هیچ عددی از پیش پر نمی‌شود؛ آمار واقعی در ``data/corpus_stats.json`` می‌نشیند.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_SEP = "<|doc|>"


def expand(path: str) -> list[str]:
    if os.path.isdir(path):
        files = []
        for base, _dirs, names in os.walk(path):
            for name in sorted(names):
                if name.endswith(".txt"):
                    files.append(os.path.join(base, name))
        return sorted(files)
    return [path]


def stream_docs(path: str, cap: int, chunk_chars: int, min_chars: int):
    """سندهای یک فایل را بی‌آنکه کل فایل در حافظه بیاید، تولید می‌کند."""
    used = 0
    buf: list[str] = []
    size = 0

    def flush():
        nonlocal buf, size
        doc = "".join(buf).strip()
        buf, size = [], 0
        return doc

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if used >= cap:
                break
            stripped = line.strip()
            if stripped == DOC_SEP:
                doc = flush()
                if len(doc) >= min_chars:
                    used += len(doc)
                    yield doc
                continue
            buf.append(line)
            size += len(line)
            if size >= chunk_chars:
                doc = flush()
                if len(doc) >= min_chars:
                    used += len(doc)
                    yield doc
    doc = flush()
    if doc and len(doc) >= min_chars and used < cap:
        yield doc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True, help="path:cap یا path")
    parser.add_argument("--out", default=os.path.join(ROOT, "data"))
    parser.add_argument("--val-ratio", type=float, default=0.01)
    parser.add_argument("--chunk-chars", type=int, default=2000)
    parser.add_argument("--min-chars", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()

    started = time.time()
    docs: list[str] = []
    seen: set[str] = set()
    sources: dict[str, dict] = {}

    for spec in args.inputs:
        path, _, cap_raw = spec.rpartition(":")
        if not path or not cap_raw.isdigit():
            path, cap = spec, 10 ** 12
        else:
            cap = int(cap_raw)
        files = expand(path)
        label = os.path.basename(path.rstrip("/")) or path
        got_docs = got_chars = 0
        remaining = cap
        for file_path in files:
            if remaining <= 0:
                break
            share = remaining if len(files) == 1 else max(1, remaining // max(1, len(files)))
            for doc in stream_docs(file_path, share, args.chunk_chars, args.min_chars):
                digest = hashlib.blake2b(doc.encode("utf-8"), digest_size=8).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                docs.append(doc)
                got_docs += 1
                got_chars += len(doc)
            remaining -= share
        sources[label] = {"files": len(files), "docs": got_docs, "chars": got_chars,
                          "cap": None if cap == 10 ** 12 else cap}
        print(f"[+] {label}: {got_docs:,} سند · {got_chars:,} نویسه", flush=True)

    rng = random.Random(args.seed)
    rng.shuffle(docs)
    val_n = max(1, int(len(docs) * args.val_ratio))
    val, train = docs[:val_n], docs[val_n:]

    os.makedirs(args.out, exist_ok=True)
    stats: dict = {"sources": sources, "seed": args.seed, "val_ratio": args.val_ratio,
                   "chunk_chars": args.chunk_chars, "min_chars": args.min_chars,
                   "docs_total": len(docs)}
    for name, part in (("train.txt", train), ("val.txt", val)):
        out_path = os.path.join(args.out, name)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write((f"\n{DOC_SEP}\n").join(part))
            fh.write("\n")
        chars = sum(len(d) for d in part)
        stats[name] = {"docs": len(part), "chars": chars,
                       "bytes": os.path.getsize(out_path)}
        print(f"[=] {name}: {len(part):,} سند · {chars:,} نویسه · "
              f"{os.path.getsize(out_path)/1e6:.1f}MB", flush=True)

    stats["seconds"] = round(time.time() - started, 1)
    with open(os.path.join(args.out, "corpus_stats.json"), "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: stats[k] for k in ("docs_total", "train.txt", "val.txt", "seconds")},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
