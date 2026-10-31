"""دانشنامهٔ کوچک و قطعی رایان.

پاسخ‌های کوتاه و بررسی‌شده برای پرتکرارترین پرسش‌ها، تا مدل ۶٫۵ میلیون پارامتری
لازم نباشد دربارهٔ چیزهایی که «جواب درست و ثابت» دارند حدس بزند.

این دانشنامه جای مدل را نمی‌گیرد؛ یک لایهٔ کمکی است که با `data/knowledge.jsonl`
تغذیه می‌شود و مدیر/توسعه‌دهنده می‌تواند بی‌نیاز از آموزش دوباره، آن را کامل کند.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = Path(__import__("os").environ.get("RAYAN_KNOWLEDGE_FILE") or ROOT / "data" / "knowledge.jsonl")

_STOP = {"از", "به", "در", "را", "که", "و", "یا", "با", "برای", "چه", "چی", "چیست",
         "کجاست", "کجا", "کی", "است", "هست", "می", "شود", "کن", "کنم", "بگو",
         "درباره", "یک", "این", "آن", "تو", "من", "the", "a", "is", "what", "where"}

_ENTRIES: list[dict] | None = None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("\u200c", " ")
    text = text.translate(str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"}))
    return re.sub(r"[^\w\s]", " ", text.casefold()).strip()


def _tokens(text: str) -> set[str]:
    return {t for t in _norm(text).split() if t not in _STOP and len(t) > 1}


def load() -> list[dict]:
    global _ENTRIES
    if _ENTRIES is not None:
        return _ENTRIES
    entries: list[dict] = []
    try:
        for line in FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            keys = row.get("keys") or [row.get("q", "")]
            row["_tokens"] = _tokens(" ".join(keys) + " " + row.get("q", ""))
            entries.append(row)
    except (OSError, ValueError):
        entries = []
    _ENTRIES = entries
    return entries


def lookup(message: str, min_score: float = 0.62) -> dict | None:
    """بهترین ورودی دانشنامه را برمی‌گرداند، اگر شباهت کافی باشد."""
    query = _tokens(message)
    if not query:
        return None
    best, best_score = None, 0.0
    for entry in load():
        keys = entry["_tokens"]
        if not keys:
            continue
        overlap = len(query & keys)
        score = overlap / max(1, min(len(query), len(keys)))
        if score > best_score:
            best, best_score = entry, score
    if best is None or best_score < min_score:
        return None
    return {"entry": best, "score": round(best_score, 2)}


def answer(message: str) -> dict | None:
    hit = lookup(message)
    if not hit:
        return None
    entry = hit["entry"]
    body = entry["a"]
    if entry.get("source"):
        body += f"\n\nمنبع: {entry['source']}"
    return {"knowledge": entry.get("id", entry.get("q", "")), "answer": body, "score": hit["score"]}
