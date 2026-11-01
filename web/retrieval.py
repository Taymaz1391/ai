"""بازیابی و استدلال محلی رایان — پاسخ از شاهد، نه از حافظهٔ قالبی.

ایدهٔ اصلی: مدل کوچک نمی‌تواند دانش جهان را در وزن‌هایش نگه دارد،
اما «فکر کردن» را می‌توان متفاوت ساخت: سؤال را بفهم، کلیدواژه‌ها را بساز، در
پیکرهٔ ۹۷ میلیون نویسه‌ای جست‌وجو کن، جمله‌های شاهد را رتبه بده، و پاسخ را از
همان شاهدها بساز — با ارجاع. اگر شاهدی نبود، صادقانه بگو و موضوع‌های نزدیک را
نشان بده. هیچ پاسخی از پیش نوشته نشده است.

اجزا:

* ``build_index``  — ساخت索引 FTS5 از پیکره (فقط یک‌بار، در ``scripts/build_index.py``)
* ``search``       — جست‌وجوی BM25 با چند پرس‌وجوی موازی
* ``compose``      — انتخاب جمله‌های شاهد و چیدن پاسخ با ارجاع
* ``think``        — همان مسیر کامل + ردپای فکر (برای نمایش در رابط کاربری)
"""
from __future__ import annotations

import math
import os
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "index.sqlite3")


def default_path() -> str:
    """مسیر ایندکس؛ هر بار از محیط خوانده می‌شود تا آزمون‌ها ایندکس خودشان را بدهند."""
    return os.environ.get("RAYAN_INDEX") or DB_PATH

# ------------------------------------------------------------------ نرمال‌سازی
_DIACRITICS = re.compile(r"[\u064B-\u0655\u0670\u0640\u06D6-\u06ED]")
_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "ؤ": "و", "ئ": "ی"})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_WORD = re.compile(r"[^\w\u200c]+")

STOPWORDS = {
    "از", "به", "در", "را", "که", "و", "یا", "با", "برای", "چه", "چی", "چیست", "است", "هست",
    "می", "می‌شود", "شود", "کن", "کنم", "کنی", "کنید", "یک", "این", "آن", "تو", "من", "ما",
    "شما", "او", "های", "ها", "هم", "اما", "اگر", "تا", "بر", "شد", "بود", "دارد", "دارم",
    "داری", "خودت", "خودم", "خودش", "لطفا", "لطفاً", "سلام", "کی", "کجا", "چرا", "چطور",
    "چگونه", "چند", "آیا", "یعنی", "بگو", "بگویید", "درباره", "مورد", "کدام", "نیست",
    "کجاست", "چیست", "کیست", "چیه", "کیه", "چقدر", "چطوره", "بفرمایید", "بفرما",
    "مرا", "برایم", "برام", "ازم", "شما", "لطفا", "می‌خواهم", "میخوام", "می‌خواستم",
    "بوده", "باشد", "باشند", "شده", "کرد", "کرده", "می‌کند", "می‌کنند", "همین", "دیگر",
    "the", "a", "an", "is", "are", "of", "to", "in", "what", "who", "where",
}


def normalize(text: str) -> str:
    """یکسان‌سازی فارسی: حروف عربی، اعراب، ارقام و نیم‌فاصله."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_ARABIC).translate(_DIGITS)
    text = _DIACRITICS.sub("", text)
    text = text.replace("\u200c", " ").replace("\u200f", "").replace("\u200e", "")
    return re.sub(r"\s+", " ", text).strip()


def stem(word: str) -> str:
    """ریشهٔ تقریبی فارسی: پیشوند «می/نمی» و پسوندهای رایج."""
    if len(word) > 4 and word.startswith("نمی"):
        word = word[3:]
    elif len(word) > 3 and word.startswith("می"):
        word = word[2:]
    for suffix in ("های", "هایی", "شان", "مان", "تان", "هایم", "هاست", "تر", "ها", "اش", "ات"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return word


def words(text: str) -> list[str]:
    """واژه‌های معنادار متن، ریشه‌گرفته و بدون تکرار (با حفظ ترتیب)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in _WORD.split(normalize(text).casefold()):
        raw = raw.strip()
        if len(raw) < 2 or raw in STOPWORDS or raw.isdigit():
            continue
        root = stem(raw)
        if len(root) < 2 or root in STOPWORDS or root in seen:
            continue
        seen.add(root)
        out.append(root)
    return out


# --------------------------------------------------------------------- ایندکس
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
    body, source, title,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


def index_exists(path: str | None = None) -> bool:
    path = path or default_path()
    if not os.path.exists(path):
        return False
    try:
        with sqlite3.connect(path) as db:
            row = db.execute("SELECT count(*) FROM passages").fetchone()
        return bool(row and row[0])
    except sqlite3.Error:
        return False


def connect(path: str | None = None) -> sqlite3.Connection:
    db = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    db.execute("PRAGMA query_only = 0")
    return db


def iter_documents(text_path: str, source: str, min_chars: int = 40) -> Iterable[tuple[str, str]]:
    """سندهای یک فایل جداشده با ``<|doc|>`` را جریان‌وار می‌خواند."""
    buffer: list[str] = []
    with open(text_path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.strip() == "<|doc|>":
                doc = "".join(buffer).strip()
                buffer = []
                if len(doc) >= min_chars:
                    yield source, doc
                continue
            buffer.append(line)
    doc = "".join(buffer).strip()
    if len(doc) >= min_chars:
        yield source, doc


def chunk(doc: str, size: int = 1000) -> list[str]:
    """سند را به قطعه‌های هم‌اندازه و هم‌تراز با شکستن خط/جمله می‌شکند.

    قطعه‌ها هم‌پوشان نیستند تا ایندکس بی‌دلیل بزرگ نشود؛ هر قطعه چند پاراگراف
    کامل است و مرزهایش روی شکستن خط یا پایان جمله می‌افتد.
    """
    doc = re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", doc.strip()))
    if not doc:
        return []
    parts: list[str] = []
    position = 0
    length = len(doc)
    while position < length:
        target = min(length, position + size)
        if target < length:
            window = doc[position + size // 2:target]
            cut = max(window.rfind("\n"), window.rfind(". "), window.rfind("؟ "))
            if cut != -1:
                target = position + size // 2 + cut + 1
        piece = doc[position:target].strip()
        if len(piece) >= 20:
            parts.append(piece)
        position = target
    return parts


def knowledge_documents(path: str) -> list[tuple[str, str]]:
    """ورودی‌های JSONL دانشنامه را به متن قابل جست‌وجو تبدیل می‌کند."""
    import json
    docs: list[tuple[str, str]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                body = (row.get("a") or "").strip()
                if body:
                    docs.append((row.get("q") or row.get("id", "")[:40], body))
    except OSError:
        pass
    return docs


def build_index(sources: list[tuple[str, str]], out_path: str | None = None,
                batch: int = 500) -> dict:
    """ایندکس را از فهرست (برچسب، مسیر متن) می‌سازد. اتمیک: ابتدا فایل موقت."""
    out_path = out_path or DB_PATH
    tmp = f"{out_path}.{os.getpid()}.tmp"
    if os.path.exists(tmp):
        os.unlink(tmp)
    started = time.time()
    docs = passages = chars = 0
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    pending: list[tuple[str, str, str]] = []

    def flush() -> None:
        nonlocal pending
        if pending:
            db.executemany("INSERT INTO passages(body, source, title) VALUES (?,?,?)", pending)
            pending = []

    for source, path in sources:
        if not os.path.exists(path):
            continue
        stream: Iterable[tuple[str, str]]
        if source == "دانشنامهٔ پروژه" or path.endswith("knowledge.jsonl"):
            stream = ((entry_id, body) for entry_id, body in knowledge_documents(path))
        else:
            stream = iter_documents(path, source)
        for entry_id, doc in stream:
            docs += 1
            first_line = next((ln.strip() for ln in doc.splitlines() if ln.strip()), "")
            # در دانشنامه، «عنوان» همان شناسهٔ مدخل است؛ در پیکره، اولین خط سند
            title = (entry_id[:80] if source == "دانشنامهٔ پروژه" else first_line)[:80]
            for piece in chunk(doc):
                pending.append((normalize(piece), source, title))
                passages += 1
                chars += len(piece)
            if len(pending) >= batch:
                flush()
        flush()
    flush()
    db.execute("INSERT INTO meta(key, value) VALUES ('built_at', ?)", (str(int(time.time())),))
    db.execute("INSERT INTO meta(key, value) VALUES ('docs', ?)", (str(docs),))
    db.execute("INSERT INTO meta(key, value) VALUES ('passages', ?)", (str(passages),))
    db.execute("INSERT INTO meta(key, value) VALUES ('chars', ?)", (str(chars),))
    db.commit()
    db.execute("INSERT INTO passages(passages) VALUES ('optimize')")
    db.commit()
    db.close()
    os.replace(tmp, out_path)
    return {
        "path": out_path, "documents": docs, "passages": passages, "chars": chars,
        "bytes": os.path.getsize(out_path), "seconds": round(time.time() - started, 1),
    }


# ------------------------------------------------------------------ جست‌وجو
@dataclass
class Hit:
    body: str
    source: str
    title: str
    score: float            # BM25 خام؛ هرچه کوچک‌تر (منفی‌تر) بهتر
    matched: set[str] = field(default_factory=set)


def _match_query(terms: list[str]) -> str:
    return " OR ".join(f'"{t}"' for t in terms)


def search(question: str, limit: int = 8, terms: list[str] | None = None,
           path: str | None = None) -> list[Hit]:
    """جست‌وجوی BM25؛ اگر ایندکس نبود، فهرست خالی."""
    terms = terms or words(question)
    if not terms:
        return []
    path = path or default_path()
    if not index_exists(path):
        return []
    query = _match_query(terms[:8])
    hits: list[Hit] = []
    try:
        with sqlite3.connect(path) as db:
            rows = db.execute(
                "SELECT body, source, title, bm25(passages, 1.0, 0.9) AS s FROM passages "
                "WHERE passages MATCH ? ORDER BY s LIMIT ?",
                (query, max(1, limit)),
            ).fetchall()
    except sqlite3.Error:
        return []
    for body, source, title, score in rows:
        body_terms = set(words(body))
        hits.append(Hit(body=body, source=source, title=title, score=float(score),
                        matched=body_terms & set(terms)))
    return hits


def search_titles(question: str, limit: int = 12, path: str | None = None) -> list[Hit]:
    """جست‌وجو فقط در ستون عنوان؛ برای مقاله‌هایی که نامشان همان موضوع است."""
    terms = words(question)
    if not terms:
        return []
    path = path or default_path()
    if not index_exists(path):
        return []
    query = " OR ".join(f'title:"{t}"' for t in terms[:4])
    try:
        with sqlite3.connect(path) as db:
            rows = db.execute(
                "SELECT body, source, title, bm25(passages, 1.0, 0.9) AS s FROM passages "
                "WHERE passages MATCH ? ORDER BY s LIMIT ?",
                (query, max(1, limit)),
            ).fetchall()
    except sqlite3.Error:
        return []
    hits = []
    for body, source, title, score in rows:
        body_terms = set(words(body))
        hits.append(Hit(body=body, source=source, title=title, score=float(score) * 0.6,
                        matched=body_terms & set(terms)))
    return hits


def search_phrase(question: str, limit: int = 10, path: str | None = None) -> list[Hit]:
    """جست‌وجوی عبارت دقیق موضوع («پایتخت فرانسه»، «زبان فارسی»)."""
    subject = subject_phrase(question)
    if len(subject) < 2:
        return []
    path = path or default_path()
    if not index_exists(path):
        return []
    phrase = " ".join(normalize(w) for w in subject)
    try:
        with sqlite3.connect(path) as db:
            rows = db.execute(
                "SELECT body, source, title, bm25(passages, 1.0, 0.9) AS s FROM passages "
                "WHERE passages MATCH ? ORDER BY s LIMIT ?",
                (f'"{phrase}"', max(1, limit)),
            ).fetchall()
    except sqlite3.Error:
        return []
    return [Hit(body=body, source=source, title=title, score=float(score) * 0.5,
                matched=set(subject)) for body, source, title, score in rows]


def wiki_path() -> str:
    """مسیر ایندکس دانشنامه (ویکی‌پدیای فارسی)."""
    return os.environ.get("RAYAN_WIKI") or os.path.join(os.path.dirname(__file__), "..",
                                                        "data", "wiki.sqlite3")


def wiki_exists(path: str | None = None) -> bool:
    path = path or wiki_path()
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 1024:
            return False
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            db.execute("SELECT 1 FROM articles LIMIT 1")
        return True
    except sqlite3.Error:
        return False


_QMARK = {"چیست", "چیه", "کیست", "کیه", "کجاست", "کجا", "چرا", "چطور", "چگونه", "چند",
          "آیا", "یعنی", "چه", "کی", "کدام", "چقدر", "چطوره", "چگونه‌است", "چه‌کسی"}


def question_subject(question: str) -> list[str]:
    """واژه‌های موضوع: هرچه پیش از نخستین واژهٔ پرسشی آمده است."""
    tokens = normalize(question).split()
    cut = len(tokens)
    for index, token in enumerate(tokens):
        if token in _QMARK:
            cut = index
            break
    before = tokens[:cut] if cut else tokens
    out: list[str] = []
    for token in before:
        token = token.strip("،؛,.؟?!«»\"'")
        if not token or token in STOPWORDS or token.isdigit() or token in out:
            continue
        out.append(token)
        if len(out) >= 3:
            break
    return out


_FOLLOWUP_START = {"و", "همچنین", "یا", "بعد", "دیگر", "بعدی", "بعدش"}


def resolve_followup(message: str, history) -> str:
    """پرسش کوتاهِ پیگیری را با موضوع گفتگو کامل می‌کند.

    «پایتخت فرانسه کجاست؟» و بعد «و ژاپن؟» ← «پایتخت ژاپن کجاست».
    """
    tokens = normalize(message or "").split()
    if not history or not tokens or len(tokens) > 3:
        return message
    try:
        previous = history[-1]
        previous = previous[0] if isinstance(previous, (list, tuple)) else str(previous)
    except (IndexError, TypeError):
        return message
    subject = question_subject(previous)
    if len(subject) < 2:
        return message
    clean = [token.strip("؟?!.،؛") for token in tokens]
    has_marker = any(token in _QMARK for token in clean)
    if not (clean and (clean[0] in _FOLLOWUP_START or (len(clean) <= 2 and not has_marker))):
        return message
    fresh = [token for token in clean
             if token and token not in STOPWORDS and token not in _QMARK and not token.isdigit()
             and token not in _FOLLOWUP_START]
    if not fresh:
        return message
    # واژهٔ تازه نباید همان موضوع قبلی باشد («و پایتختش؟»)
    if any(token in word or word in token for token in fresh for word in subject):
        return message
    marker = next((token.strip("؟?!.,،؛") for token in normalize(previous).split()
                   if token.strip("؟?!.,،؛") in _QMARK), "")
    parts = subject[:-1] + [fresh[0]] + ([marker] if marker else [])
    return " ".join(parts)


_MODIFIERS = {"پایتخت", "بلندترین", "بلند", "قله", "قلهٔ", "کشور", "شهر", "اهل", "زادگاه",
              "بنیان‌گذار", "نویسندهٔ", "نویسنده", "سازندهٔ", "سازنده", "پدیدآورنده",
              "درازترین", "بزرگ‌ترین", "کوچک‌ترین", "مهم‌ترین", "معروف‌ترین", "اولین",
              "نخستین", "کدام", "چه", "کیست", "چیست", "بود", "است", "دارد", "نام"}


def _drop_modifiers(words_: list[str]) -> list[str]:
    """واژه‌های پرسشی/توصیفی را کنار می‌گذارد تا اسمِ خاص بماند."""
    kept = [w for w in words_ if normalize(w) not in _MODIFIERS and len(w) > 2]
    return kept or words_


def wiki_lookup(question: str, path: str | None = None) -> dict | None:
    """مقالهٔ دانشنامه برای موضوع سؤال: عنوان دقیق، تغییرمسیر، یا جست‌وجوی عنوان.

    عبارت سه‌واژه‌ای، دوواژه‌ای و تک‌واژه‌ای به‌ترتیب امتحان می‌شوند تا پرسش‌هایی
    مثل «فتوسنتز چگونه انجام می‌شود؟» هم مقالهٔ «فتوسنتز» را پیدا کنند.
    """
    words_ = question_subject(question) or phrase_words(question, limit=3)
    if not words_:
        return None
    path = path or wiki_path()
    if not os.path.exists(path):
        return None
    # ترتیب امتحان: موضوعِ کامل، موضوعِ بی‌پیشوند، و در پایان تک‌واژه‌های بلند.
    # «پایتخت فرانسه» مقاله ندارد، اما «فرانسه» دارد و جملهٔ «پاریس، پایتخت
    # فرانسه...» همان جواب است.
    full = " ".join(normalize(w) for w in words_)
    phrases = [full]
    trimmed = " ".join(normalize(w) for w in _drop_modifiers(words_))
    if trimmed and trimmed != full:
        phrases.append(trimmed)
    for word in sorted({normalize(w) for w in words_ if len(w) > 3}, key=len, reverse=True):
        if word and word not in phrases:
            phrases.append(word)
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            for phrase in phrases:
                row = db.execute("SELECT title, lead FROM articles WHERE norm = ? LIMIT 1",
                                 (phrase,)).fetchone()
                if row and row[1]:
                    return {"title": row[0], "lead": row[1], "match": "عنوان دقیق",
                            "phrase": phrase}
                row = db.execute(
                    "SELECT a.title, a.lead FROM alias AS x JOIN articles AS a "
                    "ON a.norm = x.target WHERE x.norm = ? LIMIT 1", (phrase,)).fetchone()
                if row and row[1]:
                    return {"title": row[0], "lead": row[1], "match": "تغییرمسیر",
                            "phrase": phrase}
            for phrase in phrases:
                try:
                    row = db.execute(
                        "SELECT title, lead, norm FROM articles WHERE articles MATCH ? LIMIT 1",
                        (f'title:"{phrase}"',)).fetchone()
                except sqlite3.Error:
                    continue
                if row and row[1]:
                    return {"title": row[0], "lead": row[1], "match": "عنوان نزدیک",
                            "phrase": row[2] or phrase}
    except sqlite3.Error:
        return None
    return None


_CAPTION_WORDS = ("تصویری", "تصویر", "عکس", "نگاره", "نمایی", "نقشه", "نشان", "پوستر",
                  "جلد", "چپ", "راست", "بالا", "پایین", "پرونده:")


def _cut_to_phrase(piece: str, phrase: str) -> str:
    """اگر پیش از موضوع متنی مثل عنوان تصویر/جدول آمده، از موضوع شروع کن."""
    parts = [re.escape(word) for word in phrase.split() if word]
    if not parts:
        return piece
    pattern = re.compile(r"\s*".join(parts), re.I)
    match = pattern.search(piece)
    if match and 0 < match.start() < 60:
        prefix = piece[:match.start()].strip()
        if any(prefix.startswith(word) for word in _CAPTION_WORDS):
            return piece[match.start():].strip()
    return piece


WIKI_GAP_BAD = ("قرار است", "در سال", "امروز", "دیروز", "هفتهٔ گذشته", "ماه گذشته")


VERB_MARKERS = ("است", "هست", "بود", "شد", "دارد", "دارند", "کرد", "می ", "می‌",
                "نامیده", "گفته", "یابد", "شود", "کند", "دهد", "رود", "آید", "گردد")


def _wiki_sentence_ok(piece: str, phrase: str) -> bool:
    """آیا جملهٔ مقاله تعریف است، نه بازماندهٔ جعبهٔ اطلاعات؟"""
    if "=" in piece or "|" in piece:
        return False
    norm = normalize(piece)
    position = norm.find(phrase)
    if position < 0:
        # عنوان مقاله ممکن است با صورت کوتاه‌تر در جمله بیاید («فارسی» برای «زبان فارسی»)
        short = [word for word in phrase.split() if len(word) > 2]
        positions = [norm.find(word) for word in short]
        positions = [item for item in positions if item >= 0]
        if not positions or min(positions) > 2:
            return False
        position = min(positions)
    elif position > 80:
        return False
    if any(cue in norm[position:][:140] for cue in STRONG_CUES):
        return True
    tail = norm[position + len(phrase):]
    spots = [tail.find(marker) for marker in VERB_MARKERS if tail.find(marker) >= 0]
    if not spots:
        return False
    gap = tail[:min(spots)]
    if any(bad in gap for bad in WIKI_GAP_BAD):
        return False
    return len(_WORD.split(gap.strip())) <= 40


_JUNK_LEADS = ("ممکن است به یکی از موارد زیر اشاره کند", "می‌تواند به یکی از موارد",
               "به یکی از معانی زیر", "ابهام‌زدایی", "این صفحه فهرست")


def _junk(answer: str | None) -> bool:
    """پاسخ‌های فهرستی/ابهام‌زدایی جواب سؤال نیستند."""
    text = answer or ""
    return any(marker in text for marker in _JUNK_LEADS)


_GENERIC_HEADS = {"علایم", "علائم", "نشانه", "نشانه‌ها", "استان", "نویسنده", "واحد",
                  "یکا", "داستان", "جمله", "واژه", "کلمه", "مفهوم", "تعریف", "تاریخ",
                  "شهر", "کشور", "کتاب", "فیلم", "بازی", "ورزش", "غذا", "میوه", "حیوان",
                  "گیاه", "مصنوعی", "ساده", "معمولی", "مهم", "بزرگ", "کوچک", "جدید", "قدیمی"}


def _enough_overlap(answer: str, question: str, match: str = "") -> bool:
    """آیا پاسخ دست‌کم با پرسش هم‌موضوع است؟ (جلوگیری از پاسخ بی‌ربط)"""
    asked = set(words(question))
    body = set(words(answer))
    if not asked:
        return True
    overlap = len(asked & body)
    if overlap == 0:
        return False
    if match and match != "عنوان دقیق" and overlap < max(1, len(asked) // 2):
        return False
    return True


def _off_topic(answer: str, question: str, phrase: str) -> bool:
    """پاسخ دربارهٔ موضوع دیگری است؟ برای سرِواژه‌های عمومی سخت‌گیرتریم.

    مثال واقعی: «علائم کم‌آبی بدن چیست؟» با مقالهٔ «علایم» (نشانه‌گذاری نسبیت عام)
    جواب داده می‌شد. اگر سرِواژه عمومی باشد و هیچ واژهٔ دیگرِ پرسش در پاسخ نباشد،
    این پاسخ به کار نمی‌آید.
    """
    head = normalize(phrase).strip()
    if head not in _GENERIC_HEADS:
        return False
    extra = [word for word in words(question) if word not in words(phrase)]
    if not extra:
        return False
    body = normalize(answer)
    return not any(word in body for word in extra)


_RELATIONS = {
    "پایتخت": ("پایتخت",),
    "زادگاه": ("زاده", "متولد", "به دنیا آمد", "زادگاه"),
    "اهل": ("زاده", "اهل", "متولد", "شیراز", "زادگاه"),
    "قله": ("قله", "بلندترین", "ارتفاع"),
    "درازا": ("طول", "درازا", "کیلومتر"),
    "بنیان": ("بنیان", "تأسیس", "ساخته شد", "سال"),
}


def _relation_sentence(lead: str, question: str) -> str | None:
    """جمله‌ای از مقاله که دقیقاً به رابطهٔ پرسیده‌شده جواب می‌دهد.

    «پایتخت فرانسه کدام شهر است؟» جوابش در جملهٔ «... پایتخت آن پاریس است» است،
    نه در جملهٔ اول مقاله. این تابع همان جمله را پیدا می‌کند.
    """
    text = normalize(question)
    cues: tuple[str, ...] = ()
    for key, words_ in _RELATIONS.items():
        if key in text:
            cues = words_
            break
    if not cues:
        return None
    flat = re.sub(r"\s*\n\s*", " ", lead or "")
    sentences = [part.strip() for part in re.split(r"(?<=[.!؟])\s+", flat) if part.strip()]
    for sentence in sentences[:12]:
        if 20 <= len(sentence) <= 320 and any(cue in sentence for cue in cues):
            return sentence
    return None


def _wiki_kind(question: str) -> str:
    text = normalize(question)
    if any(word in text for word in ("کیست", "کیه", "چه کسی")):
        return "person"
    if any(word in text for word in ("کجاست", "کجا ")):
        return "place"
    return "thing"


def _wiki_score(piece: str, phrase: str, kind: str) -> float:
    """امتیاز یک جملهٔ مقاله برای نوع پرسش."""
    norm = normalize(piece)
    score = 1.0
    if norm.startswith(phrase):
        score += 3.0
    elif any(norm.startswith(word) for word in phrase.split() if len(word) > 2):
        score += 1.5
    if kind == "place":
        score += 2.0 * len(set(words(piece)) & LOCATION_WORDS)
        if "به شمار" in piece or "پرجمعیت" in piece:
            score -= 1.5
    elif kind == "person":
        score += 2.0 * sum(1 for cue in PERSON_CUES if cue in piece)
    return score


def _wiki_pieces(lead: str) -> list[str]:
    """خطوط مقاله را به قطعه‌های معنادار می‌شکند (بی توجه به نقطهٔ اختصاری «ح.»)."""
    lines = [line.strip() for line in re.split(r"\n+", lead or "") if line.strip()]
    merged: list[str] = []
    buffer = ""
    for line in lines:
        if len(line) < 60 or re.search(r"[،,]$", line):
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append(line)
        else:
            buffer = (buffer + " " + line).strip()
    if buffer:
        merged.append(buffer)
    pieces: list[str] = []
    for chunk in merged:
        pieces.extend(part.strip() for part in
                      re.split(r"(?<=[آ-ی]{3}[.!؟])\s+", chunk) if part.strip())
    return pieces


def _wiki_lead_answer(lead: str, phrase: str, question: str = "",
                      max_chars: int = 460) -> str | None:
    """جملهٔ تعریفِ مقاله، متناسب با نوع پرسش (چیست/کیست/کجاست)."""
    # هر خط جدا می‌شود: سرِ مقاله‌های ویکی often عنوان تصویر/جعبهٔ اطلاعات است
    text = re.sub(r"\s*\n\s*", "\n", lead or "").strip()
    text = re.sub(r"(?<=[.!؟])(?=[^\s\d\n])", " ", text)
    text = re.sub(r"\b\d+\s*px\b", " ", text)
    text = re.sub(r"(?:[A-Za-z][\w'’-]*\s+){2,}[A-Za-z][\w'’-]*", " ", text)
    text = re.sub(r"\(\s*\)", " ", text)
    if not text:
        return None
    kind = _wiki_kind(question) if question else "thing"
    pieces = _wiki_pieces(text)
    scored: list[tuple[float, int, str]] = []
    for order, piece in enumerate(pieces):
        if len(piece) < 30 or not _wiki_sentence_ok(piece, phrase):
            continue
        if kind == "person" and not any(cue in piece for cue in PERSON_CUES):
            continue
        if kind == "place" and not (set(words(piece)) & LOCATION_WORDS):
            continue
        scored.append((_wiki_score(piece, phrase, kind) - order * 0.6, order, piece))
    if not scored:
        return None
    best = max(scored, key=lambda item: item[0])
    chosen = [_cut_to_phrase(best[2], phrase)]
    total = len(chosen[0])
    for _score, order, piece in sorted(scored, key=lambda item: item[1]):
        if order <= best[1] or len(chosen) >= 2:
            continue
        if total + len(piece) > max_chars:
            break
        chosen.append(piece)
        total += len(piece)
    answer = " ".join(chosen)
    # تکرار عنوان در آغاز جمله: «برج میلاد برج میلاد نام برج …»
    double = phrase + " " + phrase
    if normalize(answer).startswith(double):
        answer = (phrase + answer[len(double):]).strip()
    answer = re.sub(r"\s+([،؛.؟!])", r"\1", answer)
    answer = re.sub(r"\s{2,}", " ", answer).strip()
    return answer or None


def expand_query(question: str) -> list[list[str]]:
    """چند پرس‌وجوی مکمل: کل کلیدواژه‌ها، دو کلیدواژهٔ اصلی، و واژه‌های بلند."""
    terms = words(question)
    queries = [terms] if terms else []
    if len(terms) > 2:
        queries.append(terms[:2])
        queries.append(sorted(terms, key=len, reverse=True)[:3])
    return queries


# ------------------------------------------------------------- ساخت پاسخ
_SENTENCE = re.compile(r"(?<=[.!؟?!])\s+|\n+")
_BAD_START = ("ویکی‌پدیا", "رده:", "الگو:", "پرونده:", "[[", "{{", "|", "http", "www.",
              "منبع:", "بیشتر بخوانید", "جستارهای وابسته", "پیوند به بیرون")
_JUNK = ("http", "www.", ".ir/", ".com/", ".jpg", ".png", ".pdf", "فیلم +", "<<", ">>", "\\u")


def sentences(text: str) -> list[str]:
    out = []
    text = re.sub(r"\*\*|__", "", text or "")
    for piece in _SENTENCE.split(text):
        piece = piece.strip(" \u200c«»\"'")
        if len(piece) < 14 or len(piece) > 400:
            continue
        if piece.startswith(_BAD_START) or piece.count("|") > 1:
            continue
        if any(junk in piece for junk in _JUNK):
            continue
        digits = sum(ch.isdigit() for ch in piece)
        if digits > len(piece) * 0.12:
            continue
        if piece.count("«") + piece.count('"') > 4:
            continue
        out.append(piece)
    return out


DEFINITION_CUES = ("است", "هست", "بود", "بودند", "نام دارد", "نامیده", "گفته می‌شود",
                   "معروف", "شناخته", "به شمار", "اطلاق", "عبارت است")
STRONG_CUES = ("نامیده", "گفته می‌شود", "عبارت است از", "اطلاق می‌شود", "معروف است",
               "شناخته می‌شود", "به شمار می", "نام دارد")

# واژه‌های پیوندی که می‌توانند پیش از موضوعِ جمله بیایند
_LINK_WORDS = {
    "و", "اما", "در", "به", "از", "با", "که", "این", "آن", "یا", "هم", "نیز", "چون",
    "زیرا", "برای", "تا", "پس", "مثلا", "مثلاً", "دیگر", "امروز", "اکنون", "ضمن",
    "بنابراین", "همچنین", "البته", "اگر", "وقتی", "چنانکه", "چراکه", "پس‌از", "سپس",
}


def _link_only(prefix: str) -> bool:
    """آیا پیش از موضوع جمله فقط واژه‌های پیوندی آمده‌اند؟"""
    for token in _WORD.split(normalize(prefix).casefold()):
        token = token.strip()
        if token and token not in _LINK_WORDS:
            return False
    return True


def phrase_words(question: str, limit: int = 3) -> list[str]:
    """واژه‌های اصلی سؤال با صورت اصلی (بدون ریشه‌گیری) برای تطبیق عبارت."""
    out: list[str] = []
    for raw in _WORD.split(normalize(question).casefold()):
        raw = raw.strip()
        if len(raw) < 2 or raw in STOPWORDS or raw.isdigit() or raw in out:
            continue
        out.append(raw)
        if len(out) >= limit:
            break
    return out


def subject_phrase(question: str) -> list[str]:
    """موضوع سؤال: واژه‌های اصلی به همان ترتیب پرسش (حداکثر سه‌تا)."""
    return phrase_words(question)


def score_sentence(sentence: str, terms: list[str], hit: Hit,
                   subject: list[str] | None = None) -> float:
    """امتیاز جمله: پوشش موضوع، نشانهٔ تعریف، عنوان سند و جایگاه در قطعه."""
    if not terms:
        return 0.0
    subject = subject or terms
    body_terms = set(words(sentence))
    subject_set = set(subject)
    subject_hits = len(subject_set & body_terms)
    if subject_hits == 0:
        return 0.0
    coverage = len(set(terms) & body_terms) / len(set(terms))
    subject_cover = subject_hits / len(subject_set)
    density = len(set(terms) & body_terms) / max(1, len(body_terms)) ** 0.5
    phrase = " ".join(normalize(w) for w in subject)
    phrase_bonus = 1.35 if phrase and phrase in normalize(sentence) else 1.0
    cue_bonus = 1.25 if any(cue in sentence[:120] for cue in DEFINITION_CUES) else 1.0
    title_terms = set(words(hit.title))
    title_bonus = 1.0 + 0.6 * (len(subject_set & title_terms) / max(1, len(subject_set)))
    position = 1.0 if sentence[:60] in hit.body[:200] else 0.9
    length_penalty = 1.0 if 50 <= len(sentence) <= 260 else 0.85
    return (subject_cover * 2.6 + coverage * 1.1 + density) * phrase_bonus * cue_bonus * \
        title_bonus * position * length_penalty


def _dedupe(items: list[str], threshold: float = 0.75) -> list[str]:
    kept: list[str] = []
    seen_sets: list[set[str]] = []
    for item in items:
        bag = set(words(item))
        if not bag:
            continue
        if any(len(bag & prev) / max(1, len(bag | prev)) >= threshold for prev in seen_sets):
            continue
        kept.append(item)
        seen_sets.append(bag)
    return kept


def _hit_group_key(hit: Hit) -> str:
    return (hit.title or hit.body[:40]).strip()


PERSON_CUES = ("شاعر", "نویسنده", "دانشمند", "فیلسوف", "متولد", "به دنیا", "پادشاه", "شاه",
               "ریاضی‌دان", "ستاره‌شناس", "مخترع", "بنیان‌گذار", "بنیانگذار", "رهبر", "سیاستمدار",
               "بازیگر", "خواننده", "مورخ", "فقیه", "عارف", "استاد", "پژوهشگر", "مجتهد", "امیر",
               "وزیر", "فرمانروا", "خلیفه", "پیامبر", "امام", "سلطان", "شهید", "روزنامه‌نگار",
               "مترجم", "معمار", "نقاش", "آهنگساز", "کارگردان", " ورزشکار", "بازیکن")


GAP_BAD = ("کرده", "شده", "بوده", "دارد", "ندارد", "نمی", "در سال", "امروز", "دیروز",
           "هفتهٔ", "ماه", "که ", "قرار است", "قرار بود", "قرار")


def _definition_gap(gap: str) -> bool:
    """آیا فاصلهٔ موضوع تا فعل اسنادی، یک تعریف ساده است (نه بند خبری)؟"""
    if any(ch.isdigit() for ch in gap):
        return False
    if any(bad in gap for bad in GAP_BAD):
        return False
    return len(_WORD.split(gap.strip())) <= 10


_TITLE_QUESTION = re.compile(r"\s*(کجاست|چیست|کیست|چه بود|چند است|کدام است|چیه|کیه|"
                             r"چه کسی است|چگونه است|چرا)[؟?]?\s*$")


LOCATION_WORDS = {"در", "شهر", "استان", "کشور", "شمال", "جنوب", "شرق", "غرب", "واقع",
                  "پایتخت", "بخش", "نزدیک", "مرکز", "کرانه", "ساحل", "منطقه", "جزیره",
                  "شهرستان", "روستا", "کوه", "دشت", "بیابان", "دریا", "دریاچه", "رود"}


def title_is_subject(title: str, phrase: str) -> bool:
    """آیا عنوان مقاله خودِ موضوع است (با/بدون توضیح پرانتزی یا صورت پرسشی)؟"""
    title = normalize(title or "")
    if not title or not phrase:
        return False
    if title == phrase:
        return True
    stripped = _TITLE_QUESTION.sub("", title).strip()
    if stripped == phrase:
        return True
    return re.fullmatch(re.escape(phrase) + r"\s*\([^)]*\)", title) is not None


def _lead_validity(sentence: str, phrase: str, title_exact: bool,
                   person_question: bool, definition_question: bool = False,
                   title: str = "", location_question: bool = False) -> tuple[str, int, str] | None:
    """آیا این جمله می‌تواند پاسخ باشد؟ «start» بهتر از «mid» است."""
    if not phrase:
        return None
    norm = normalize(sentence)
    position = norm.find(phrase)
    if position < 0 or position > 40:
        return None
    # جمله‌ای که با عنوانِ بلندتری هم‌ریشه شروع می‌شود، دربارهٔ موجودیت دیگری است
    if (title and not title_exact and title.startswith(phrase + " ")
            and norm.startswith(title)):
        return None
    if position and not _link_only(norm[:position]):
        return None
    tail = norm[position + len(phrase):]
    strong = any(cue in tail[:110] for cue in STRONG_CUES)
    match = re.search(r"(^|\s)(است|هست|بود|بودند|می‌باشد)(\s|$|[،؛.])", tail[:70])
    if not strong and not match:
        return None
    gap_len = 0
    gap_key = ""
    if match:
        if any(ch.isdigit() for ch in tail[:match.start()]):
            return None
        gap = tail[:match.start()]
        gap_len = len(gap.strip())
        if definition_question and not strong and not _definition_gap(gap):
            return None
        # موضوع تک‌واژه‌ای: فعل باید بلافاصله بیاید، وگرنه جمله دربارهٔ ترکیب دیگری است
        gap_key = " ".join(_WORD.split(gap.strip())[:3])
    if person_question:
        # پرسش از شخص: شاهد باید نشانهٔ شخص بودن را داشته باشد
        if not (title_exact or any(cue in sentence for cue in PERSON_CUES)):
            return None
    if location_question and not (title_exact or (set(words(sentence)) & LOCATION_WORDS)):
        return None
    return ("start" if position == 0 else "mid"), gap_len, gap_key


def compose(question: str, hits: list[Hit], max_sentences: int = 2,
            max_chars: int = 560) -> dict | None:
    """پاسخ را از شاهدهای پیکره می‌سازد: جملهٔ تعریف + یک جملهٔ پشتیبان.

    جمله‌ها اول اعتبارسنجی می‌شوند (موضوع نزدیک آغاز + فعل اسنادی/نشانهٔ تعریف)
    و بعد رتبه می‌گیرند؛ پس اگر بهترین جملهٔ یک سند نامعتبر بود، جملهٔ معتبر
    بعدی همان سند شانس دارد. اگر هیچ شاهدی معتبر نبود ``None`` برمی‌گردد.
    """
    subject = subject_phrase(question)
    terms = words(question)
    if not subject or not hits:
        return None
    phrase = " ".join(normalize(w) for w in subject)
    subject_set = set(subject)
    person_question = any(word in normalize(question) for word in ("کیست", "کیه", "چه کسی"))
    location_question = any(word in normalize(question) for word in ("کجاست", "کجا "))
    definition_question = any(word in normalize(question) for word in ("چیست", "چیه", "چه بود",
                                                                      "چی هست"))
    title_exact = False

    candidates: list[dict] = []
    for hit in hits:
        title = normalize(hit.title)
        title_exact = title_is_subject(hit.title, phrase)
        title_cover = len(subject_set & set(words(title))) / max(1, len(subject_set))
        for order, sentence in enumerate(sentences(hit.body)):
            validity = _lead_validity(sentence, phrase, title_exact, person_question,
                                      definition_question, title, location_question)
            if not validity:
                continue
            kind, gap_len, gap_key = validity
            score = score_sentence(sentence, terms, hit, subject)
            if score <= 0:
                continue
            # هرچه فاصلهٔ موضوع تا فعل کوتاه‌تر، تعریف خالص‌تر است
            score /= 1 + gap_len / 45.0
            if order == 0:
                score *= 1.2
            if kind == "mid":
                score *= 0.75
            candidates.append({"hit": hit, "sentence": sentence, "score": score,
                               "validity": kind, "order": order, "gap_key": gap_key,
                               "title_cover": title_cover,
                               "title_exact": title_is_subject(hit.title, phrase)})

    if not candidates:
        return None

    # اجماع: اسناد مستقل که با یک قالب تعریفی مشترک جواب می‌دهند
    agreement: dict[str, set[str]] = {}
    for cand in candidates:
        if cand["gap_key"]:
            agreement.setdefault(cand["gap_key"], set()).add(_hit_group_key(cand["hit"]))
    confirmed = [c for c in candidates
                 if c["title_exact"]
                 or len(agreement.get(c["gap_key"], ())) >= 2
                 # تعریفِ کوتاه و بی‌واسطه: «X Y است»
                 or (c["validity"] == "start" and 0 < len(c["gap_key"].split()) <= 2)]
    if not confirmed:
        return None
    candidates = confirmed

    # برای هر سند فقط بهترین جملهٔ معتبر
    per_doc: dict[str, dict] = {}
    for cand in candidates:
        key = _hit_group_key(cand["hit"])
        if key not in per_doc or cand["score"] > per_doc[key]["score"]:
            per_doc[key] = cand

    def doc_score(cand: dict) -> float:
        bonus = 2.2 if cand["title_exact"] else 1.0
        return cand["score"] * (1 + 0.4 * cand["title_cover"]) * bonus

    ranked = sorted(per_doc.values(), key=lambda c: -doc_score(c))
    top = ranked[0]
    lead = top["sentence"]
    lead_norm = normalize(lead)
    lead_terms = set(words(lead))
    lead_cover = len(subject_set & lead_terms) / max(1, len(subject_set))
    lead_starts = top["validity"] == "start"

    # جملهٔ پشتیبان از همان سند
    chosen = [lead]
    total = len(lead)
    supports = sorted((c for c in candidates if c is not top and
                       _hit_group_key(c["hit"]) == _hit_group_key(top["hit"])),
                      key=lambda c: -c["score"])
    for cand in supports:
        sentence = cand["sentence"]
        if len(chosen) >= max_sentences or total + len(sentence) > max_chars:
            break
        if set(words(sentence)) & subject_set and sentence not in chosen:
            chosen.append(sentence)
            total += len(sentence)
    chosen = _dedupe(chosen)
    if not chosen:
        return None

    hit = top["hit"]
    answer = " ".join(chosen)
    answer = re.sub(r"\s+([،؛.؟!])", r"\1", answer).strip()
    coverage = lead_cover
    confidence = min(0.97, 0.5 + 0.3 * coverage + 0.17 * min(1.0, top["score"] / 3.0))
    if not lead_starts:
        confidence = min(confidence, 0.66)
    return {
        "answer": answer,
        "sources": [{
            "title": (hit.title or hit.source)[:90],
            "source": hit.source,
            "snippet": lead[:170],
            "score": round(top["score"], 3),
        }],
        "confidence": round(confidence, 3),
        "coverage": round(coverage, 3),
        "score": round(top["score"], 3),
    }


QUESTION_WORDS = ("چیست", "چیه", "کیست", "کیه", "کجاست", "کجا", "چرا", "چطور", "چگونه",
                  "چند", "آیا", "یعنی", "تفاوت", "فرق", "چه", "کی", "چرا")


_SOCIAL = ("خوبی", "چطوری", "چه خبر", "صبح بخیر", "شب بخیر", "روز بخیر", "حالت چطور",
           "چخبر", "کجایی", "چیکار")


def looks_factual(question: str) -> bool:
    """آیا سؤال دانشی است (نه سلام/احوال‌پرسی، نه شعر، نه ادامهٔ متن)؟"""
    text = (question or "").strip()
    if not words(text):
        return False
    if any(item in text for item in _SOCIAL) and len(text.split()) <= 3:
        return False
    if any(word in text for word in QUESTION_WORDS):
        return True
    # «X را توضیح بده» / «دربارهٔ X بگو» هم پرسش دانشی است
    if any(marker in text for marker in ("توضیح بده", "توضیح دهید", "تعریف کن", "یعنی چه",
                                         "دربارهٔ", "درباره ", "چه معنایی")):
        return True
    return text.endswith(("؟", "?")) and len(text.split()) >= 3


def _online_allowed() -> bool:
    """آیا یادگیری آنلاین از تنظیمات مدیر و متغیر محیطی اجازه دارد؟"""
    if os.environ.get("RAYAN_ONLINE", "1") == "0":
        return False
    try:
        from web import admin as admin_module
        return bool(admin_module.flags().get("auto_learn", True))
    except Exception:  # noqa: BLE001 - تنظیمات نباید پاسخ را بشکند
        return True


THINK_BUDGET = float(os.environ.get("RAYAN_THINK_BUDGET", "1.2"))


def _direct_answer(question: str, path: str | None = None) -> dict | None:
    """پاسخ کوتاه و مستقیم از پیکره: جمله‌ای که خودش جوابِ همین پرسش است.

    نمونه: «پایتخت فرانسه کجاست» → «پایتخت فرانسه پاریس است.» — بی‌حشو و
    بدون ساختن جملهٔ تازه. فقط وقتی برمی‌گرداند که جمله کوتاه باشد و همهٔ
    واژه‌های موضوع را در خود داشته باشد.
    """
    try:
        hits = search(question, limit=4, path=path)
    except sqlite3.Error:
        return None
    # پرسش‌های «چطور/چگونه» دنبال راهنمای عملی‌اند، نه تعریف؛ پیکره جوابشان نیست.
    if re.search(r"(چطور|چگونه|چی\s*کار|چه\s*کار|راهنمایی|پیشنهاد)", normalize(question)):
        return None
    # تبدیل یکا کارِ ابزار است، نه پیکره
    if re.search(r"\d", normalize(question)) and re.search(
            r"(کیلومتر|متر|سانتی|میلی|مایل|گرم|کیلوگرم|پوند|ساعت|دقیقه|ثانیه)", normalize(question)):
        return None
    subject = [normalize(word) for word in (question_subject(question) or []) if len(word) > 2]
    if not subject:
        return None
    for hit in hits[:3]:
        body = (hit.body or "").replace("*", "").strip()
        body = re.sub(r"\s+", " ", body)
        if not body or len(body) > 320:
            continue
        norm_body = normalize(body)
        if not all(word in norm_body for word in subject):
            continue
        sentences = [piece.strip() for piece in re.split(r"(?<=[.!؟])\s+", body) if piece.strip()]
        for sentence in sentences:
            norm_sentence = normalize(sentence)
            if len(sentence) < 18 or len(sentence) > 240:
                continue
            if all(word in norm_sentence for word in subject):
                return {"answer": sentence,
                        "source": {"title": (hit.title or "")[:90], "source": "پیکرهٔ فارسی",
                                   "snippet": sentence[:170], "score": 1.0}}
    return None


def think(question: str, limit: int = 10, path: str | None = None,
          online: bool | None = None, budget: float | None = None) -> dict:
    """مسیر کاملِ فکر: کلیدواژه → جست‌وجو → انتخاب شاهد → پاسخ + ردپا."""
    started = time.time()
    trace: list[dict] = []
    terms = words(question)
    trace.append({"step": "کلیدواژه‌ها", "detail": "، ".join(terms[:6]) or "—",
                  "seconds": round(time.time() - started, 3)})
    if not terms:
        return {"answer": None, "sources": [], "trace": trace, "confidence": 0.0,
                "reason": "no_terms"}

    # ۰) پاسخ مستقیم: اگر جملهٔ جوابِ همین پرسش در پیکره هست، همان را بده
    direct = _direct_answer(question, path=path)
    if direct:
        trace.append({"step": "پاسخ مستقیم", "detail": direct["answer"][:70],
                      "seconds": round(time.time() - started, 3)})
        return {"answer": direct["answer"], "sources": [direct["source"]],
                "trace": trace, "confidence": 0.95, "coverage": 1.0,
                "seconds": round(time.time() - started, 3), "engine": "corpus"}

    # ۰٫۴) درخواست نوشتن (یادداشت/داستان/نامه) پاسخ دانشنامه‌ای نمی‌خواهد
    try:
        from web import writer as writer_module
        if writer_module._kind(question):
            return {"answer": None, "sources": [], "trace": trace, "confidence": 0.0,
                    "reason": "writing"}
    except Exception:  # noqa: BLE001 - این نگهبان نباید مسیر را بشکند
        pass

    # ۰٫۵) دستیار موضوعی: دستور زبان، دانش پایه و کد — قطعی، نه حدسی
    from web import tutor as tutor_module
    taught = tutor_module.answer(question)
    if taught:
        trace.append({"step": "دستیار موضوعی", "detail": taught["source"],
                      "seconds": round(time.time() - started, 3)})
        return {"answer": taught["answer"], "sources": [],
                "trace": trace, "confidence": 0.97, "coverage": 1.0,
                "seconds": round(time.time() - started, 3), "engine": taught["engine"]}

    # ۱) دانشنامه: فقط برای پرسش‌های تعریفی؛ «چطور/چگونه» مقالهٔ دانشنامه نمی‌خواهد
    # «چگونه به وجود می‌آید» پرسش تبیینی است و مقالهٔ دانشنامه می‌خواهد؛
    # «چطور بخوابم» درخواست کار است و نباید مقالهٔ «خواب» را برگرداند.
    how_to = re.search(
        r"(چطور|چگونه|چی\s*کار|چه\s*کار)\s+.{0,40}?"
        r"(کنم|کنیم|کنید|بخوابم|بپزم|بنویسم|بسازم|بخرم|بروم|بیام|شروع کنم|یاد بگیرم|"
        r"استفاده کنم|حل کنم|درست کنم|پیدا کنم)"
        r"|راهنمایی|پیشنهاد|چه کار کنم", normalize(question))
    # «پایتون» در پرسش برنامه‌نویسی یعنی زبان، نه مار
    if re.search(r"(پایتون|python)", normalize(question)) and \
            re.search(r"(کد|برنامه|تابع|حلقه|متغیر|فهرست|لیست|کلاس|کتابخانه)", normalize(question)):
        entry = wiki_lookup("پایتون (زبان برنامه‌نویسی)", path=path)
        if entry:
            answer = _wiki_lead_answer(entry["lead"], entry["phrase"], question)
            if answer and not _junk(answer):
                return {"answer": answer,
                        "sources": [{"title": entry["title"][:90], "source": "دانشنامه",
                                     "snippet": answer[:170], "score": 1.0}],
                        "trace": trace + [{"step": "دانشنامه", "detail": entry["title"],
                                           "seconds": round(time.time() - started, 3)}],
                        "confidence": 0.85, "coverage": 1.0,
                        "seconds": round(time.time() - started, 3), "engine": "wiki"}
    entry = None if how_to else wiki_lookup(question)
    if entry:
        answer = _wiki_lead_answer(entry["lead"], entry["phrase"], question)
        # رابطهٔ پرسیده‌شده (پایتخت/زادگاه/ارتفاع) اولویت دارد
        relation = _relation_sentence(entry["lead"], question)
        if relation and (not answer or relation[:60] not in answer):
            answer = (relation if not answer else f"{answer} {relation}")[:700]
        trace.append({"step": "دانشنامه", "detail": f"مقالهٔ «{entry['title']}» ({entry['match']})",
                      "seconds": round(time.time() - started, 3)})
        if answer and (_off_topic(answer, question, entry["phrase"])
                       or not _enough_overlap(answer, question, entry.get("match", ""))):
            trace.append({"step": "دانشنامه", "detail": "پاسخ دربارهٔ موضوع دیگری بود",
                          "seconds": round(time.time() - started, 3)})
            answer = None
        if answer and not _junk(answer):
            return {
                "answer": answer,
                "sources": [{"title": entry["title"][:90], "source": "ویکی‌پدیای فارسی",
                             "snippet": answer[:170], "score": 1.0}],
                "trace": trace, "confidence": 0.93, "coverage": 1.0,
                "seconds": round(time.time() - started, 3), "engine": "wiki",
            }

    found: dict[tuple[str, str], Hit] = {}
    phrase_hits = search_phrase(question, limit=limit, path=path)
    for hit in phrase_hits:
        found[(hit.source, hit.body[:80])] = hit
    if phrase_hits:
        trace.append({"step": "عبارت دقیق", "detail": f"{len(phrase_hits)} سند شامل موضوع",
                      "seconds": round(time.time() - started, 3)})
    title_hits = search_titles(question, limit=limit, path=path)
    for hit in title_hits:
        found[(hit.source, hit.body[:80])] = hit
    if title_hits:
        trace.append({"step": "عنوان", "detail": f"{len(title_hits)} مقالهٔ هم‌نام",
                      "seconds": round(time.time() - started, 3)})
    queries = expand_query(question)
    for index, query_terms in enumerate(queries):
        for hit in search(question, limit=limit, terms=query_terms, path=path):
            key = (hit.source, hit.body[:80])
            previous = found.get(key)
            if previous is None or hit.score < previous.score:
                found[key] = hit
        trace.append({"step": f"جست‌وجوی {index + 1}",
                      "detail": f"{len(query_terms)} کلیدواژه · {len(found)} شاهد یکتا",
                      "seconds": round(time.time() - started, 3)})

    hits = sorted(found.values(), key=lambda h: h.score)[: limit]
    trace.append({"step": "رتبه‌بندی", "detail": f"{len(hits)} قطعهٔ نزدیک",
                  "seconds": round(time.time() - started, 3)})
    composed = compose(question, hits)
    elapsed = round(time.time() - started, 3)
    if not composed:
        # ۵) اگر در پیکره و دانشنامه شاهدی نبود، از دانشِ پیشینِ وب استفاده کن.
        #    خواندن تازه از وب همیشه در پس‌زمینه انجام می‌شود تا پاسخ کاربر
        #    پشت شبکه معطل نماند؛ بودجهٔ زمانی (پیش‌فرض ۱٫۲ ثانیه) قطعی است.
        deadline = (budget if budget is not None else THINK_BUDGET)
        if online is None:
            online = path is None and _online_allowed()
        if online and time.time() - started < deadline:
            try:
                from web import learn as learn_module
                learned = learn_module.answer(question, learn=False)   # فقط دانشِ ذخیره‌شده
            except Exception:  # noqa: BLE001 - شبکه نباید پاسخ را بشکند
                learned = None
            if learned:
                trace.append({"step": "دانشِ خوانده‌شده",
                              "detail": f"منبع پیشین: {learned['sources'][0]['domain']}",
                              "seconds": round(time.time() - started, 3)})
                return {"answer": learned["answer"], "sources": learned["sources"],
                        "trace": trace, "confidence": learned.get("confidence", 0.7),
                        "coverage": 1.0, "seconds": round(time.time() - started, 3),
                        "engine": "learn", "learned": False}
        near = []
        for hit in hits[:3]:
            title = (hit.title or "").strip()
            if title and title not in near:
                near.append(title[:70])
        if path is None:
            # صف کنجکاوی: بعداً کارگر پس‌زمینه این موضوع را یاد می‌گیرد
            try:
                from web import learn as learn_module
                if online:
                    learn_module.remember(question)
            except Exception:  # noqa: BLE001
                pass
        return {"answer": None, "sources": [], "trace": trace, "confidence": 0.0,
                "near": near, "seconds": elapsed, "reason": "no_evidence"}

    trace.append({"step": "انتخاب شاهد",
                  "detail": f"{len(composed['sources'])} منبع · پوشش {composed['coverage']:.2f}",
                  "seconds": elapsed})
    return {
        "answer": composed["answer"],
        "sources": composed["sources"],
        "trace": trace,
        "confidence": composed["confidence"],
        "coverage": composed["coverage"],
        "seconds": elapsed,
        "engine": "retrieval",
    }


def evidence(question: str, limit: int = 3, path: str | None = None) -> list[dict]:
    """شاهدهای خامِ نزدیک به سؤال، وقتی تعریف تأییدشده‌ای پیدا نشده است.

    جمله‌هایی برگردانده می‌شوند که همهٔ واژه‌های موضوع را دارند و لحن خبری/جدولی
    ندارند؛ متن عیناً از پیکره است و هیچ چیز ساخته نمی‌شود.
    """
    subject = subject_phrase(question)
    if not subject:
        return []
    want = set(subject)
    pool = search(question, limit=max(10, limit * 6), path=path)
    try:
        pool = search_phrase(question, limit=limit * 3, path=path) + pool
    except Exception:  # noqa: BLE001
        pass
    out: list[dict] = []
    seen: set[str] = set()
    for hit in sorted(pool, key=lambda h: h.score):
        for sentence in sentences(hit.body):
            bag = set(words(sentence))
            if not want <= bag:
                continue
            if not (40 <= len(sentence) <= 220):
                continue
            key = " ".join(sorted(bag))
            if key in seen:
                continue
            if any(bad in sentence for bad in ("گفت وگو با", "به گزارش", "خبرگزاری", "گزارش تصویری")):
                continue
            seen.add(key)
            out.append({"text": sentence, "title": (hit.title or hit.source)[:80],
                        "source": hit.source})
            break
        if len(out) >= limit:
            break
    return out


def stats(path: str | None = None) -> dict:
    """آمار ایندکس‌ها (پیکره و دانشنامه) برای صفحهٔ سلامت."""
    path = path or default_path()
    out: dict = {"ready": False, "path": path}
    try:
        if os.path.exists(path):
            with sqlite3.connect(path) as db:
                meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
            out = {"ready": True, "path": path, "bytes": os.path.getsize(path), **meta}
    except sqlite3.Error as exc:
        out = {"ready": False, "path": path, "error": str(exc)}
    wiki = wiki_path()
    try:
        if os.path.exists(wiki):
            with sqlite3.connect(f"file:{wiki}?mode=ro", uri=True) as db:
                meta = dict(db.execute("SELECT key, value FROM meta").fetchall())
                aliases = db.execute("SELECT COUNT(*) FROM alias").fetchone()[0]
            out["wiki"] = {"ready": True, "bytes": os.path.getsize(wiki),
                           "articles": int(meta.get("articles") or 0),
                           "chars": int(meta.get("chars") or 0),
                           "aliases": aliases}
        else:
            out["wiki"] = {"ready": False}
    except sqlite3.Error:
        out["wiki"] = {"ready": False}
    return out
