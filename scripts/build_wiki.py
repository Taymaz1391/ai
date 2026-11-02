"""ساخت ایندکس دانشنامه از نسخهٔ فارسی ویکی‌پدیا.

ورودی، فایل‌های zip موجود در ``corpora/_wiki`` است (هر خط یک مقالهٔ JSON با
فیلدهای ``Title`` و ``Text``؛ ``Text`` چکیدهٔ آغاز مقاله است). خروجی یک پایگاه
FTS5 است که لایهٔ «فکر کردن» پیش از جست‌وجوی عمومی، تعریف را از آن می‌گیرد.

    python scripts/build_wiki.py                 # همهٔ فایل‌ها
    python scripts/build_wiki.py --limit 50000   # برای آزمایش سریع
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from web.retrieval import normalize  # noqa: E402

SRC_GLOB = os.path.join(os.path.dirname(ROOT), "corpora", "_wiki", "repo",
                        "Json Format of Persian Wikipedia Pages", "*.zip")
OUT = os.path.join(ROOT, "data", "wiki.sqlite3")
MIN_LEAD = 80
MAX_LEAD = 600

# مقاله‌هایی که چکیده‌شان فهرست/جدول است، به‌کار تعریف نمی‌آیند
_BAD_START = re.compile(r"^(فهرست|رده:|الگو:|پرونده:|جدول|پیوست|گاه‌شمار)")
_LISTISH = re.compile(r"^(\*|\||\-|\d+\.)\s", re.M)


def clean(text: str) -> str:
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\d+\]", " ", text)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def iter_articles(path: str):
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.endswith(".json"):
                continue
            with zf.open(name) as fh:
                for raw in fh:
                    try:
                        item = json.loads(raw)
                    except Exception:  # noqa: BLE001 - یک خط خراب نباید همه را بشکند
                        continue
                    yield item


def schema(db: sqlite3.Connection) -> None:
    db.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        DROP TABLE IF EXISTS articles;
        CREATE VIRTUAL TABLE articles USING fts5(
            title, lead, norm UNINDEXED, tokenize='unicode61'
        );
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS alias (norm TEXT PRIMARY KEY, target TEXT);
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--limit", type=int, default=0, help="حداکثر تعداد مقاله")
    parser.add_argument("--min-lead", type=int, default=MIN_LEAD)
    args = parser.parse_args()

    paths = sorted(glob.glob(SRC_GLOB))
    if not paths:
        print("no wikipedia zips found", file=sys.stderr)
        return 1
    if os.path.exists(args.out):
        os.remove(args.out)
    started = time.time()
    db = sqlite3.connect(args.out)
    schema(db)

    rows: list[tuple[str, str, str]] = []
    aliases: list[tuple[str, str]] = []
    seen: set[str] = set()
    total = kept = 0
    for path in paths:
        print(f"[wiki] {os.path.basename(path)}", flush=True)
        for item in iter_articles(path):
            total += 1
            if item.get("Namespace") != 0 or item.get("IsDisambiguationPage"):
                continue
            title = (item.get("Title") or "").strip()
            if not title or _BAD_START.match(title):
                continue
            lead = clean(item.get("Text") or "")[:MAX_LEAD]
            if len(lead) < args.min_lead or _LISTISH.match(lead[:40]):
                continue
            norm = normalize(title)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            rows.append((title, lead, norm))
            for redirect in item.get("RedirectList") or []:
                alias = normalize(str(redirect))
                if alias and alias != norm:
                    aliases.append((alias, norm))
            kept += 1
            if len(rows) >= 20000:
                db.executemany("INSERT INTO articles(title, lead, norm) VALUES (?,?,?)", rows)
                db.executemany("INSERT OR IGNORE INTO alias(norm, target) VALUES (?,?)", aliases)
                db.commit()
                rows.clear()
                aliases.clear()
            if args.limit and kept >= args.limit:
                break
        if args.limit and kept >= args.limit:
            break
    if rows:
        db.executemany("INSERT INTO articles(title, lead, norm) VALUES (?,?,?)", rows)
    if aliases:
        db.executemany("INSERT OR IGNORE INTO alias(norm, target) VALUES (?,?)", aliases)
    chars = db.execute("SELECT COALESCE(SUM(LENGTH(lead)),0) FROM articles").fetchone()[0]
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", ("articles", str(kept)))
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", ("chars", str(chars)))
    db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)", ("built_at", str(int(time.time()))))
    db.commit()
    db.execute("INSERT INTO articles(articles) VALUES('optimize')")
    db.commit()
    db.close()
    print(json.dumps({
        "read": total, "kept": kept, "chars": chars,
        "bytes": os.path.getsize(args.out),
        "seconds": round(time.time() - started, 1),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
