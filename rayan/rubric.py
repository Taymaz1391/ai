"""داور خودکار (rubric) برای ساختن ترجیح — معیارهای عینی، قابل بازتولید و قابل آزمون.

این ماژول نقش «برچسب‌گذار» را بازی می‌کند: چند پاسخ را با قاعده‌های روشن امتیاز
می‌دهد تا زوج (بهتر، بدتر) ساخته شود. هیچ قضاوت سلیقه‌ای و هیچ سرویس بیرونی در کار
نیست؛ همان عددها در گزارش `reports/alignment.json` ذخیره می‌شوند.

قاعده‌ها:
- قرابت با پاسخ مرجع (اگر داشته باشیم) پاداش دارد؛
- تکرار n-gram، نشت نشانه‌های قالب، متن لاتین و پاسخ خیلی کوتاه جریمه دارند؛
- پایان‌یافتن با نشانه‌گذاری و بستن نوبت پاداش کوچک دارد.
"""
from __future__ import annotations

import re
import unicodedata

_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ؤ": "و", "إ": "ا", "أ": "ا"})
_DIACRITICS = re.compile(r"[\u064B-\u0655\u0670\u0640]")
_WORD = re.compile(r"[\w\u0600-\u06FF]+")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_LEAK = re.compile(r"<\||<\|doc\|>|<\|user\|>|<\|bot\|>|\|>")
_END_OK = ("‌", ".", "!", "؟", "?", "…", "»", ")")

STOPWORDS = {"از", "به", "در", "را", "که", "و", "یا", "با", "برای", "چه", "چی", "است",
             "هست", "یک", "این", "آن", "می", "شود", "کن", "هم", "اما", "اگر", "تا",
             "بر", "شد", "بود", "دارد"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_ARABIC)
    text = _DIACRITICS.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in _WORD.findall(normalize(text).casefold()):
        if len(raw) > 1 and raw not in STOPWORDS:
            out.append(raw)
    return out


def repetition_ratio(text: str, n: int = 4) -> float:
    """نسبت چهارگانه‌های تکراری — معیار اصلی «گیرکردن» مدل."""
    words = normalize(text).split()
    if len(words) < n + 1:
        return 0.0
    grams = [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]
    unique = len(set(grams))
    return 1.0 - unique / max(1, len(grams))


def latin_ratio(text: str) -> float:
    words = normalize(text).split()
    if not words:
        return 0.0
    latin = len(_LATIN_WORD.findall(normalize(text)))
    return latin / len(words)


def overlap(text: str, reference: str) -> float:
    """F1 واژه‌ای با پاسخ مرجع (۰ تا ۱)."""
    want = set(tokens(reference))
    got = set(tokens(text))
    if not want or not got:
        return 0.0
    common = len(want & got)
    if not common:
        return 0.0
    precision = common / len(got)
    recall = common / len(want)
    return 2 * precision * recall / (precision + recall)


def has_expected(text: str, expected: list[str] | None) -> bool:
    if not expected:
        return False
    body = normalize(text)
    return any(normalize(item) in body for item in expected)


def score(text: str, *, reference: str = "", expected: list[str] | None = None,
          finish: str = "length") -> dict:
    """امتیاز عینی یک پاسخ. عدد بزرگ‌تر بهتر است."""
    body = (text or "").strip()
    length = len(body)
    leak = bool(_LEAK.search(body))
    rep = repetition_ratio(body)
    lat = latin_ratio(body)
    ov = overlap(body, reference) if reference else 0.0
    parts: dict[str, float] = {
        "base": 1.0,
        "overlap": 0.45 * ov,
        "terminated": 0.12 if body.endswith(_END_OK) else 0.0,
        "length_ok": 0.10 if 20 <= length <= 220 else 0.0,
        "stopped": 0.08 if finish == "stop" else 0.0,
        "expected": 0.40 if has_expected(body, expected) else 0.0,
        "repetition": -1.30 * rep,
        "too_short": -1.0 if length < 12 else 0.0,
        "leak": -2.0 if leak else 0.0,
        "latin": -1.2 * lat if lat > 0.34 else 0.0,
    }
    total = sum(parts.values())
    return {"total": round(total, 4), "length": length, "repetition": round(rep, 3),
            "latin": round(lat, 3), "overlap": round(ov, 3), "leak": leak,
            "finish": finish, "parts": parts}


def prefer(a: dict, b: dict, min_gap: float = 0.25) -> bool:
    """آیا a به‌اندازهٔ کافی از b بهتر است که زوج آموزشی بسازد؟"""
    return a["total"] - b["total"] >= min_gap


def reason(a: dict, b: dict) -> str:
    """توضیح کوتاه این‌که چرا a برنده شد (برای گزارش و شفافیت)."""
    bits = []
    if a["repetition"] < b["repetition"]:
        bits.append("تکرار کمتر")
    if a["leak"] != b["leak"]:
        bits.append("بدون نشت نشانهٔ قالب")
    if a["overlap"] > b["overlap"]:
        bits.append("نزدیک‌تر به پاسخ مرجع")
    if a["length"] >= 12 > b["length"]:
        bits.append("پاسخ کامل‌تر")
    if not bits:
        bits.append("امتیاز کلی بالاتر")
    return "، ".join(bits[:3])
