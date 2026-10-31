"""نرمال‌سازی متن فارسی — قلب پیش‌پردازش رایان.

این ماژول هیچ وابستگی بیرونی ندارد و هم در ساخت پیکره، هم در زمان اجرا
(ورودی کاربر) استفاده می‌شود تا توزیع متن آموزش و استنتاج یکی بماند.
"""
from __future__ import annotations

import re

ZWNJ = "\u200c"

# حروف عربی که در فارسی معیار به شکل دیگری نوشته می‌شوند.
_CHAR_MAP = str.maketrans({
    "ي": "ی", "ك": "ک", "ة": "ه", "ى": "ی", "ٱ": "ا",
    "ﻻ": "لا", "ﻷ": "لأ", "ﻹ": "لإ",
})

# اعراب، تنوین، تشدید، علامت‌های قرآنی و کشیده.
_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
# نویسه‌های نامرئی و کنترلی جهت‌دهی.
_INVISIBLES = re.compile(r"[\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069\u00ad\ufeff]")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# نویسه‌های مجاز: حروف فارسی/عربی، لاتین، ارقام، فاصله، نیم‌فاصله و نشانه‌ها.
_ALLOWED = re.compile(
    r"[^\u0621-\u063a\u0641-\u064a\u067e\u0686\u0698\u06a9\u06af\u06cc\u06c0"
    r"A-Za-z0-9\u200c\s\.\,\:\;\!\?\(\)\[\]\{\}«»\"'،؛؟\-–—…/%+*=<>]"
)

_URL = re.compile(r"(https?://\S+|www\.\S+|\S+@\S+\.\S+|\b(?:t|telegram)\.me/\S+)", re.I)
_TAGS = re.compile(r"<[^>]{1,80}>")
_SPACES = re.compile(r"[ \t\u00a0]+")
_NEWLINES = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([،؛:!?\.\)\]\}»])")
_SPACE_AFTER_OPEN = re.compile(r"([\(\{\[«])\s+")
_ZWNJ_SPACES = re.compile(r"\s*\u200c\s*")

# عبارت‌های زائد خبری/تبلیغاتی که معمولاً به متن آسیب می‌زنند.
_BOILERPLATE = (
    "بیشتر بخوانید", "ادامه مطلب", "کلیک کنید", "اینجا کلیک", "برای دانلود",
    "خرید پکیج", "تبلیغات", "کد خبر", "خبرنگار تسنیم", "خبرنگار فارس",
    "خبرنگار ایسنا", "خبرنگار مهر", "منبع: تسنیم", "منبع: فارس",
    "منبع: ایسنا", "منبع: مهر", "منبع: ایرنا", "کپی لینک", "اشتراک‌گذاری",
)

PERSIAN_LETTERS = re.compile(r"[\u0621-\u063a\u0641-\u064a\u067e\u0686\u0698\u06a9\u06af\u06cc\u06c0]")
_LATIN_LETTERS = re.compile(r"[A-Za-z]")
_WORD = re.compile(r"[\w\u200c]+")


def normalize(text: str) -> str:
    """متن خام را به شکل معیار فارسی رایان درمی‌آورد."""
    if not text:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    text = _TAGS.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _INVISIBLES.sub("", text)
    text = text.translate(_CHAR_MAP).translate(_DIGITS)
    text = _DIACRITICS.sub("", text)
    text = _ALLOWED.sub(" ", text)
    text = _SPACES.sub(" ", text)
    text = _ZWNJ_SPACES.sub(ZWNJ, text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN.sub(r"\1", text)
    text = _NEWLINES.sub("\n\n", text)
    # فاصله‌های ابتدا/انتهای خطوط
    text = "\n".join(line.strip() for line in text.split("\n"))
    # تکرار نشانه‌ها مثل «!!!» را به یک «!» کاهش می‌دهیم.
    text = re.sub(r"([!؟?])\1{1,}", r"\1", text)
    text = re.sub(r"([.،;:])\1{2,}", r"\1", text)
    return text.strip()


def remove_boilerplate(text: str) -> str:
    """خطوط تبلیغاتی/تشریفاتی رایج خبرگزاری‌ها را حذف می‌کند."""
    kept = []
    for line in text.split("\n"):
        if any(token in line for token in _BOILERPLATE) and len(line) < 160:
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def letter_stats(text: str) -> tuple[int, int, int]:
    """(تعداد حروف فارسی، تعداد حروف لاتین، تعداد کل نویسه‌های غیرفاصله)"""
    persian = len(PERSIAN_LETTERS.findall(text))
    latin = len(_LATIN_LETTERS.findall(text))
    visible = len(re.sub(r"\s", "", text))
    return persian, latin, visible


def persian_ratio(text: str) -> float:
    persian, latin, _ = letter_stats(text)
    total = persian + latin
    return persian / total if total else 0.0


def is_clean_persian(text: str, min_ratio: float = 0.72) -> bool:
    """آیا متن به‌قدر کافی فارسی و سالم است؟"""
    if not text:
        return False
    persian, latin, visible = letter_stats(text)
    if persian < 20:
        return False
    if visible and persian / visible < 0.45:
        return False
    return persian_ratio(text) >= min_ratio


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def prepare_user_input(text: str, limit: int = 1200) -> str:
    """ورودی کاربر را با همان قواعد پیکره پاک می‌کند."""
    cleaned = normalize(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit]
