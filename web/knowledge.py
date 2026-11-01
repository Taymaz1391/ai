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
         "کجاست", "کجا", "کی", "کیست", "است", "هست", "می", "شود", "کن", "کنم", "بگو",
         "درباره", "یک", "این", "آن", "تو", "من", "the", "a", "is", "what", "where",
         # صورت‌های فعلی و پسوندهایی که موضوع را نمی‌سازند
         "بود", "بودند", "شد", "شده", "کرد", "کرده", "کند", "کنند", "دارد", "دارند",
         "کاری", "کارها", "هایی", "های", "نوشت", "گفت", "داریم", "کنیم", "بده",
         # واژه‌های پرسشی که موضوع نمی‌سازند
         "کسی", "کسانی", "آیا", "چرا", "چگونه", "چطور", "چند", "چندمین", "کدام"}

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


# واژه‌های فراگیر که موضوع را مشخص نمی‌کنند
_GENERIC = {"کدام", "کدامیک", "جهان", "دنیا", "بزرگ‌ترین", "بزرگترین", "بلندترین",
            "کوچک‌ترین", "کوچکترین", "بهترین", "معروف‌ترین", "معروفترین", "اولین",
            "نخستین", "نزدیک‌ترین", "نزدیکترین", "درازترین", "عمیق‌ترین", "عمیقترین",
            "پرجمعیت‌ترین", "پرجمعیتترین", "گران‌ترین", "زیباترین", "مهم‌ترین"}


def _subjects(message: str) -> set[str]:
    """واژه‌های موضوعیِ پرسش: بدونِ واژه‌های پرسشی و صفت‌های برتر."""
    return {token for token in _tokens(message)
            if token not in _GENERIC and token not in _STOP and len(token) > 2}


_SUFFIXES = ("هایی", "های", "ها", "ای", "ی")


_AUTHOR_ASK = re.compile(r"چه کسی|چه کسانی|نویسنده|مولف|مؤلف|سراینده|"
                         r"کی (?:نوشت|سرود|ساخت|کشف|فرمول)|چه کسی .*(?:کشف|فرمول|ارائه|بنیان)")
_AUTHOR_KEY = re.compile(r"نوشت|سرود|نویسند|مولف|مؤلف|چه کسی|سراینده|"
                         r"کشف|فرمول|ارائه داد|بنیان")
_SUMMARY_KEY = re.compile(r"درباره|خلاصه|چیست$")


def _stem(token: str) -> str:
    """ریشهٔ سادهٔ واژه: «اثری» → «اثر»، «کتاب‌ها» → «کتاب»."""
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _stems(tokens: set[str]) -> set[str]:
    return {_stem(token) for token in tokens}


def _rarity(tokens: set[str]) -> float:
    """کمیابیِ واژه‌ها: واژه‌ای که در ورودی‌های کمتری آمده، ارزشِ موضوعیِ بیشتری دارد."""
    if not tokens:
        return 0.0
    counts = [sum(1 for entry in load() if token in entry["_tokens"]) for token in tokens]
    rarest = min(counts)
    return 1.0 / (1.0 + rarest)


def lookup(message: str, min_score: float = 0.62) -> dict | None:
    """بهترین ورودی دانشنامه را برمی‌گرداند، اگر شباهت و موضوع کافی باشد.

    امتیاز از سه بخش ساخته می‌شود: چه بخشی از پرسش پوشش داده شده (بازخوانی)، چه بخشی
    از کلیدهای ورودی در پرسش آمده (دقت) و پاداشِ تطبیقِ عبارتِ کامل. سپس نگهبانِ
    موضوع بررسی می‌کند که واژه‌های کم‌بسامدِ پرسش در ورودی آمده باشند.
    """
    query = _tokens(message)
    if not query:
        return None
    flat = " " + " ".join(_norm(message).split()) + " "
    author_intent = bool(_AUTHOR_ASK.search(flat))
    subjects = _subjects(message)
    subjects_all = subjects | _stems(subjects) if subjects else set()
    ranked: list[tuple[float, dict]] = []
    for entry in load():
        keys = entry["_tokens"]
        if not keys:
            continue
        overlap = len(query & keys)
        if not overlap:
            continue
        recall = overlap / len(query)          # چه بخشی از پرسش پوشش دارد
        precision = overlap / len(keys)        # چه بخشی از کلیدها آمده
        # تطبیقِ عبارتِ کامل («پروین اعتصامی»، «غزل‌سرای شیراز») وزنِ بیشتری دارد
        phrase = any(f" {_norm(key)} " in flat for key in (entry.get("keys") or [])
                     if len(_norm(key).split()) > 1 or len(_norm(key)) >= 5)
        score = recall + 0.6 * precision + (0.5 if phrase else 0.0)
        # نیتِ پرسش: «چه کسی نوشت» پاسخِ پدیدآورنده می‌خواهد، نه خلاصهٔ اثر
        if author_intent:
            if not _AUTHOR_KEY.search(" ".join(keys) + " " + entry.get("q", "")):
                continue            # پرسش از پدیدآورنده است؛ ورودیِ توصیفی پاسخ نیست
            score += 0.5
        elif _SUMMARY_KEY.search(" ".join(keys)):
            score -= 0.1
        if score >= 1.0:
            ranked.append((score, entry))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    for score, entry in ranked[:5]:
        if not subjects_all:
            return {"entry": entry, "score": round(min(score, 2.0), 2)}
        body = f"{entry.get('a', '')} {' '.join(entry.get('keys') or [])} {entry.get('q', '')}"
        body_tokens = _tokens(body) | _stems(_tokens(body))
        if not (subjects_all & body_tokens):
            continue                        # پاسخ به موضوعِ دیگری است
        # واژه‌های کم‌بسامد موضوع را می‌سازند؛ یا یکی از آن‌ها در ورودی باشد،
        # یا پوششِ واژه‌های پرسش آن‌قدر بالا باشد که موضوع روشن باشد
        rare = {token for token in subjects_all
                if sum(1 for row in load() if token in row["_tokens"]) <= 2}
        coverage = len(subjects_all & body_tokens) / len(subjects_all)
        if rare and not (rare & body_tokens) and coverage < 0.75:
            continue
        return {"entry": entry, "score": round(min(score, 2.0), 2)}
    return None


def answer(message: str) -> dict | None:
    """پاسخِ بررسی‌شدهٔ دانشنامه؛ منبع هیچ‌گاه نامِ فایل یا مخزن نیست."""
    hit = lookup(message)
    if not hit:
        return None
    entry = hit["entry"]
    return {"knowledge": entry.get("id", entry.get("q", "")), "answer": entry["a"],
            "score": hit["score"], "engine": "knowledge", "curated": True}
