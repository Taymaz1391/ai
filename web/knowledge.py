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
# بستهٔ دانشِ عمومی جدا نگه داشته می‌شود تا ویرایشِ مدیر در پنل آن را بازنویسی نکند
PACK = Path(__import__("os").environ.get("RAYAN_KNOWLEDGE_PACK") or FILE.with_name("knowledge-pack.jsonl"))
# بستهٔ ساختاریافته (پایتخت‌ها، قله‌ها، مرجع‌های سلامت…) که با
# scripts/build_knowledge_facts.py از جدول ساخته می‌شود؛ جدا نگه داشته می‌شود تا
# ویرایشِ دستیِ دو فایلِ دیگر آن را پاک نکند.
FACTS = Path(__import__("os").environ.get("RAYAN_KNOWLEDGE_FACTS") or FILE.with_name("knowledge-facts.jsonl"))

_STOP = {"از", "به", "در", "را", "که", "و", "یا", "با", "برای", "چه", "چی", "چیست",
         "کجاست", "کجا", "کی", "کیست", "است", "هست", "می", "شود", "کن", "کنم", "بگو",
         "درباره", "یک", "این", "آن", "تو", "من", "the", "a", "is", "what", "where",
         # صورت‌های فعلی و پسوندهایی که موضوع را نمی‌سازند
         "بود", "بودند", "شد", "شده", "کرد", "کرده", "کند", "کنند", "دارد", "دارند",
         "کاری", "کارها", "هایی", "های", "نوشت", "گفت", "داریم", "کنیم", "بده",
         # واژه‌های رابطه که موضوع نمی‌سازند («بوف کور اثر کیست»)
         "اثر", "آثار", "خلق", "پدیدآورنده", "پدیدآور",
         # واژه‌های پرسشی که موضوع نمی‌سازند
         "کسی", "کسانی", "آیا", "چرا", "چگونه", "چطور", "چند", "چندمین", "کدام", "ترین",
         # واژه‌های «جنبه» که موضوع نمی‌سازند («اسید چه ویژگی‌ای دارد»)
         "ویژگی", "ویژگی‌ای", "ویژگیهای", "ویژگی‌های", "خصوصیت", "خصوصیات", "مشخصات",
         "ای", "هایی", "ایست"}

_ENTRIES: list[dict] | None = None


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").replace("\u200c", " ")
    # «ب.م.م» → «بمم»: نقطه‌ها و فاصله‌های درونِ سرواژه‌ها یک واژه می‌سازند
    text = re.sub(r"(?<=\w)\.(?=\w)", " ", text)
    text = re.sub(r"\b(?:[^\W\d_]\s){2,}[^\W\d_]\b",
                  lambda match: match.group(0).replace(" ", ""), text)
    text = text.translate(str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"}))
    return re.sub(r"[^\w\s]", " ", text.casefold()).strip()


# هم‌معنی‌ها: پرسشِ آدم «کوه» و «قله» را یکی می‌بیند، واژه‌نامه هم باید.
_SYNONYMS = {
    "قله": "کوه", "قلل": "کوه", "قله‌ها": "کوه", "ارتفاع": "بلندی",
    "درگذشت": "فوت", "وفات": "فوت", "مرگ": "فوت", "درگذشته": "فوت",
    "برج": "ساختمان", "آسمان‌خراش": "ساختمان",
    "همسایگان": "همسایه", "همسایه‌های": "همسایه",
    "مصرع": "مصراع", "مصرع‌ها": "مصراع",
    "ساسانیان": "ساسانی", "هخامنشیان": "هخامنشی", "صفویان": "صفوی",
    "اشکانیان": "اشکانی", "سلجوقیان": "سلجوقی", "قاجاریه": "قاجار",
    "اعراب": "عرب", "روس‌ها": "روس", "مغول‌ها": "مغول",
    "پرتغالی‌ها": "پرتغال", "عثمانیان": "عثمانی",
    "بزرگسال": "بالغ", "بزرگسالان": "بالغ",
    "دریا": "دریاچه", "دریای": "دریاچه",
}


def _canon(token: str) -> str:
    return _SYNONYMS.get(token, token)


def _tokens(text: str) -> set[str]:
    return {_canon(t) for t in _norm(text).split() if t not in _STOP and len(t) > 1}


def load() -> list[dict]:
    global _ENTRIES
    if _ENTRIES is not None:
        return _ENTRIES
    entries: list[dict] = []
    seen: set[str] = set()
    for path in (FILE, PACK, FACTS):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            ident = str(row.get("id") or row.get("q") or "")
            if ident and ident in seen:
                continue
            seen.add(ident)
            keys = row.get("keys") or [row.get("q", "")]
            row["_tokens"] = _tokens(" ".join(keys) + " " + row.get("q", ""))
            entries.append(row)
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
            if (token not in _GENERIC and token not in _STOP and len(token) > 1
                and not token.endswith("ترین"))}


_SUFFIXES = ("هایی", "های", "ها", "ای", "ی", "ش", "اش")


_AUTHOR_ASK = re.compile(
    r"نویسنده|مولف|مؤلف|سراینده|اثر\s*(?:کیست|کی\s*است|چه\s*کسی|چه\s*کس)|"
    r"(?:چه\s*کسی|کی|چه\s*کسانی)\s+(?:نوشت|سرود|ساخت|کشف|فرمول|ارائه|بنیان)|"
    r"(?:سروده|نوشته|ساخته|کشفِ?|کارِ?)\s*(?:کیست|کی\s*است|چه\s*کسی)|"
    r"از\s*(?:کی|چه\s*کسی)\s*(?:است|بود)"
)

_AUTHOR_KEY = re.compile(r"نوشت|سرود|نویسند|مولف|مؤلف|چه کسی|سراینده|اثر|"
                         r"کشف|فرمول|ارائه داد|بنیان")
_SUMMARY_KEY = re.compile(r"درباره|خلاصه|چیست$")
# پرسشِ سال/تاریخ، پاسخِ تاریخی می‌خواهد؛ نه اینکه «کجاست» را جواب بدهیم
# مرزِ واژه لازم است: «بزرگسال چند دندان» نباید «سال چند» خوانده شود
_YEAR_ASK = re.compile(r"(?<![\w\u200c])(?:(?:در\s*)?چه\s*سالی?|سالِ?\s*چند|کدام\s*سال|"
                       r"چندمین\s*سال|چه\s*سالی)")
# گفت‌وگوی کوتاه، پرسش دانشی نیست
# «شروع» یا «پایان»: دو پاسخِ متفاوت برای یک موضوع
_SUMMARY_ASK = re.compile(r"درباره|موضوع|حکایت|داستان|قصه|محتوای|دربارهٔ")
# «مرکز استان …»/«پایتخت …» پاسخِ جغرافیایی می‌خواهد، نه هر ورودی که آن نام را دارد
_PLACE_ASK = re.compile(r"مرکز\s*استان|مرکزِ\s*استان|پایتخت|مرکز\s*کشور")
_PLACE_KEY = re.compile(r"پایتخت|مرکز\s*استان|مرکز\s*کشور|استانِ|شهرِ")
_START_ASK = re.compile(r"شروع|آغاز|اعلام|رخ داد|وقوع|به قدرت رسید")
_END_ASK = re.compile(r"پایان|تمام شد|خاتمه|سقوط|فروپاش|شکست خورد")

_SMALL_TALK = re.compile(r"^(?:سلام|درود|خوبی|خوبید|چطوری|چطورید|چه خبر|ممنون|مرسی|سپاس|"
                         r"خداحافظ|بدرود|صبح بخیر|شب بخیر|وقت بخیر|سلامت باشی|"
                         r"عافیت باشه|خسته نباشی|دستت درد نکنه)"
                         r"(?:[\s،,]+.{0,40})?[\s!.,،؟?]*$")


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


_YEAR_TOKEN = re.compile(r"(?<![0-9])(1[2-9][0-9]{2}|20[0-9]{2})(?![0-9])")
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _latin_digits(text: str) -> str:
    return (text or "").translate(_DIGIT_MAP)
_EVENT_ASK = re.compile(r"اتفاق|رخ\s*داد|رویداد|واقعه|چه\s*شد|چه\s*گذشت|رخداد|"
                        r"انقلاب|کودتا|جنگ|پیروزی|سقوط")


def _year_event(flat: str) -> dict | None:
    """پرسشِ «در سالِ X چه شد؟» را به نزدیک‌ترین رویدادِ همان سال می‌بندد."""
    year = _YEAR_TOKEN.search(_latin_digits(flat))
    if not year:
        return None
    if not _EVENT_ASK.search(flat):
        return None
    target = year.group(1)
    best: tuple[float, dict] | None = None
    for entry in load():
        body = _latin_digits(f"{entry.get('q', '')} {' '.join(entry.get('keys') or [])} "
                             f"{entry.get('a', '')}")
        if not _YEAR_TOKEN.search(" " + body + " ") or target not in body:
            continue
        score = 1.4
        if _EVENT_ASK.search(body):
            score += 0.5
        # سال در پرسش/کلیدِ خودِ مدخل آمده باشد، نشانهٔ دقیق‌تری است تا در متنِ پاسخ
        head = _latin_digits(f"{entry.get('q', '')} {' '.join(entry.get('keys') or [])}")
        if target in head:
            score += 0.8
        if best is None or score > best[0]:
            best = (score, entry)
    if not best:
        return None
    return {"entry": best[1], "score": round(min(best[0], 2.0), 2)}


def lookup(message: str, min_score: float = 0.62) -> dict | None:
    """بهترین ورودی دانشنامه را برمی‌گرداند، اگر شباهت و موضوع کافی باشد.

    امتیاز از سه بخش ساخته می‌شود: چه بخشی از پرسش پوشش داده شده (بازخوانی)، چه بخشی
    از کلیدهای ورودی در پرسش آمده (دقت) و پاداشِ تطبیقِ عبارتِ کامل. سپس نگهبانِ
    موضوع بررسی می‌کند که واژه‌های کم‌بسامدِ پرسش در ورودی آمده باشند.
    """
    if _SMALL_TALK.match(" ".join((message or "").split())):
        return None                     # سلام و تشکر، پرسش دانشی نیستند
    query = _tokens(message)
    if not query:
        return None
    flat = " " + " ".join(_norm(message).split()) + " "

    # «سال ۱۳۵۷ چه اتفاقی افتاد؟» پرسشِ رویدادِ یک سال است، نه جست‌وجوی واژه‌ای.
    # چنین پرسشی با امتیازدهیِ واژه‌ای پیدا نمی‌شود (تنها واژهٔ مشترک خودِ سال
    # است) و پیش‌تر بی‌پاسخ می‌ماند.
    year_hit = _year_event(flat)
    if year_hit:
        return year_hit

    author_intent = bool(_AUTHOR_ASK.search(flat))
    year_intent = bool(_YEAR_ASK.search(flat))
    summary_intent = bool(_SUMMARY_ASK.search(flat))
    place_intent = bool(_PLACE_ASK.search(flat))
    start_intent = bool(_START_ASK.search(flat))
    end_intent = bool(_END_ASK.search(flat)) and not start_intent
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
        elif year_intent:
            # «در چه سالی پایتخت شد» سال می‌خواهد، نه نامِ پایتخت
            body = " ".join(keys) + " " + entry.get("q", "")
            if not re.search(r"سال|تاریخ|قرن|پیش از میلاد|هجری|میلادی|پ\.م", body):
                continue
            score += 0.4
        if place_intent:
            body = entry.get("q", "") + " " + " ".join(keys)
            if not _PLACE_KEY.search(body):
                continue            # پرسش از مرکز/پایتخت است؛ ورودیِ دریاچه پاسخ نیست
            score += 0.4
        if start_intent and not _START_ASK.search(entry.get("q", "") + " " + " ".join(keys)):
            continue                    # پرسش از شروع است؛ ورودیِ «پایان» پاسخ نیست
        if end_intent and not _END_ASK.search(entry.get("q", "") + " " + " ".join(keys)):
            continue
        elif summary_intent and _SUMMARY_KEY.search(" ".join(keys) + " " + entry.get("q", "")):
            score += 0.4            # پرسش از موضوعِ اثر است؛ ورودیِ «چه کسی سرود» پاسخ نیست
        elif _SUMMARY_KEY.search(" ".join(keys)):
            score -= 0.1
        if score < 1.0:
            continue
        # واژه‌ای که در بیشترِ ورودی‌ها هست (مثل «خوب») موضوع نمی‌سازد.
        # سقف نسبی است، نه عددِ ثابت: با بزرگ‌شدنِ دانشنامه، «پایتخت» یا «ایران»
        # از مرزِ ثابتِ ۳۰ می‌گذشتند و پاسخ‌های درست را بی‌صدا دور می‌ریختند.
        matched = query & keys
        if matched:
            entries_all = load()
            ceiling = max(30, int(len(entries_all) * 0.3))
            if all(sum(1 for row in entries_all if token in row["_tokens"]) > ceiling
                   for token in matched):
                continue
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
        # دست‌کم سه‌چهارمِ واژه‌های موضوعیِ پرسش باید در ورودی باشد؛
        # وگرنه «مرکز استان گیلان» به ورودیِ اصفهان می‌خورد.
        coverage = len(subjects_all & body_tokens) / len(subjects_all)
        if coverage < 0.75:
            continue
        return {"entry": entry, "score": round(min(score, 2.0), 2)}
    return None


# واژه‌های حوزه که موضوع را مشخص نمی‌کنند؛ «بلندترین کوه» + «جهان» موضوع نیست
_DOMAIN = {"کوه", "پایتخت", "کشور", "شهر", "کتاب", "آبشار", "رود", "دریاچه", "برج",
           "ساختمان", "ورزش", "غذا", "حیوان", "درخت", "میوه", "فیلم", "شاعر", "نویسنده",
           "سازمان", "شرکت", "دارو", "بیماری", "استان", "قاره", "اقیانوس", "جزیره"}


def _distinctive(subjects: set[str]) -> set[str]:
    """واژه‌هایی که موضوع را واقعاً مشخص می‌کنند.

    «پایتخت»، «کشور» و «کتاب» در صدها مدخل آمده‌اند؛ اگر آن‌ها را معیار بگیریم،
    «پایتخت آفریقای جنوبی» به مدخلِ «پایتخت کرهٔ جنوبی» می‌چسبد. پس واژه‌های
    پربسامد کنار گذاشته می‌شوند و فقط واژه‌های کم‌بسامد معیار می‌مانند.
    """
    entries = load()
    gate = max(6, len(entries) // 25)
    kept = {token for token in subjects
            if token not in _DOMAIN
            and sum(1 for entry in entries if token in entry["_tokens"]) <= gate}
    return kept


def related(message: str, limit: int = 2) -> list[dict]:
    """ورودی‌هایی که دربارهٔ *همان* موضوعِ پرسش‌اند، نه موضوعِ هم‌خانواده.

    فقط برای پاسخِ صادقانهٔ جزئی به کار می‌رود؛ اگر ورودی موضوع را نداشته باشد،
    چیزی برنمی‌گردد تا پاسخ به موضوعِ دیگری نرود.
    """
    subjects = _distinctive(_subjects(message))
    if not subjects:
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for entry in load():
        body = f"{entry.get('a', '')} {' '.join(entry.get('keys') or [])} {entry.get('q', '')}"
        tokens = _tokens(body)
        # واژهٔ شناسا باید در *عنوان/کلید* مدخل باشد، نه یک اشارهٔ گذرا در متن؛
        # «صحرای آفریقا» نباید پاسخِ «بلندترین کوه آفریقا» شود.
        headline = _tokens(f"{' '.join(entry.get('keys') or [])} {entry.get('q', '')}")
        if not subjects <= headline:
            continue
        if len(subjects & tokens) / len(subjects) < 0.8:
            continue
        if entry.get("q") in seen:
            continue
        seen.add(entry.get("q", ""))
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def answer(message: str) -> dict | None:
    """پاسخِ بررسی‌شدهٔ دانشنامه؛ منبع هیچ‌گاه نامِ فایل یا مخزن نیست."""
    hit = lookup(message)
    if not hit:
        return None
    entry = hit["entry"]
    return {"knowledge": entry.get("id", entry.get("q", "")), "answer": entry["a"],
            "score": hit["score"], "engine": "knowledge", "curated": True}
