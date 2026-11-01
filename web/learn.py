"""لایهٔ دانشِ آنلاین رایان — خواندن از وب، افزودن به دانش، و تقویت تدریجی.

سه کار انجام می‌دهد:

۱. **گرفتن**: صفحه‌های وب را می‌خواند و متن اصلی‌شان را بیرون می‌کشد
   (بدون کتابخانهٔ بیرونی، با ``html.parser`` استاندارد).
۲. **نگه‌داشتن**: متن را در ایندکس FTS5 محلی (``data/learned.sqlite3``) ذخیره
   می‌کند؛ دفعهٔ بعد که کسی همین موضوع را بپرسد، پاسخ بی‌درنگ و با منبع است.
۳. **تقویت تدریجی**: سؤال‌هایی که شاهدی برایشان پیدا نشد در صف «کنجکاوی»
   می‌مانند و کارگر پس‌زمینه آن‌ها را یکی‌یکی می‌آموزد.

هیچ کلید API و هیچ سرویس هوش مصنوعی بیرونی در کار نیست؛ فقط صفحهٔ وب خوانده
می‌شود. محدودیت‌های امنیتی: فقط http/https، بلوک آدرس‌های داخلی/خصوصی (SSRF)،
سقف حجم پاسخ، مهلت کوتاه، و احترام به robots.txt.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_AGENT = ("Mozilla/5.0 (compatible; RayanBot/2.0; +https://github.com/Taymaz1391/ai) "
              "PersianAssistant/2.0")
TIMEOUT = float(os.environ.get("RAYAN_FETCH_TIMEOUT", "6"))
# کل زمان مجاز برای یک تلاش یادگیری آنلاین (تا پاسخ کاربر معطل نماند)
BUDGET = float(os.environ.get("RAYAN_LEARN_BUDGET", "12"))
MAX_BYTES = int(os.environ.get("RAYAN_FETCH_BYTES", "900000"))
MAX_TEXT = 20000
CACHE_DAYS = 30

_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ؤ": "و", "إ": "ا",
                         "أ": "ا", "ٱ": "ا"})
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile(r"[\u064B-\u0655\u0670\u0640\u06D6-\u06ED]")
_WORD = re.compile(r"[\w\u0600-\u06FF]+")
_QMARK = {"چیست", "چیه", "کیست", "کیه", "کجاست", "کجا", "چرا", "چطور", "چگونه", "چند",
          "آیا", "یعنی", "چه", "کی", "کدام", "چقدر", "چطوره", "است", "هست", "بود",
          "بگو", "بگویید", "درباره", "مورد", "را", "و", "از", "به", "در", "با", "برای",
          "این", "آن", "که", "هم", "یک", "می", "شود", "کن", "کنم", "کنید"}


# ------------------------------------------------------------------ کمکی‌ها
def normalize(text: str) -> str:
    """یکسان‌سازی فارسی برای تطبیق (بی‌خطر برای نمایش)."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_ARABIC).translate(_DIGITS)
    text = _DIACRITICS.sub("", text)
    text = text.replace("\u200c", " ").replace("\u200f", "").replace("\u200e", "")
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> list[str]:
    out: list[str] = []
    for raw in _WORD.findall(normalize(text).casefold()):
        if len(raw) > 1 and raw not in out:
            out.append(raw)
    return out


def subject_words(question: str, limit: int = 3) -> list[str]:
    """واژه‌های موضوع پرسش، بدون واژه‌های پرسشی."""
    out: list[str] = []
    for word in words(question):
        word = word.strip("؟?!.:،؛\"'«»")
        if not word or word in _QMARK or len(word) < 2:
            continue
        out.append(word)
        if len(out) >= limit:
            break
    return out


def db_path() -> str:
    return os.environ.get("RAYAN_LEARNED") or os.path.join(ROOT, "data", "learned.sqlite3")


def enabled() -> bool:
    """آیا اجازهٔ خواندن از وب داریم؟"""
    return os.environ.get("RAYAN_ONLINE", "1") != "0"


def _connect() -> sqlite3.Connection:
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.executescript(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS pages USING fts5(
            title, body, url UNINDEXED, norm UNINDEXED, host UNINDEXED, learned_at UNINDEXED,
            tokenize='unicode61'
        );
        CREATE TABLE IF NOT EXISTS seen (url TEXT PRIMARY KEY, learned_at REAL);
        CREATE TABLE IF NOT EXISTS curiosity (question TEXT PRIMARY KEY, asked_at REAL,
                                             tries INTEGER DEFAULT 0, done INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    return db


# ------------------------------------------------------------------ خواندن صفحه
class _TextExtractor(HTMLParser):
    """متن اصلی صفحه را از HTML بیرون می‌کشد (بدون وابستگی بیرونی)."""

    SKIP = {"script", "style", "noscript", "svg", "canvas", "form", "nav", "footer",
            "header", "aside", "iframe", "template"}
    BLOCK = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "td", "br",
             "tr", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title + " " + data).strip()
            return
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in raw.split("\n")]
        lines = [line for line in lines if len(line) >= 25]
        return "\n".join(lines)


def _is_public_host(host: str) -> bool:
    """جلوگیری از SSRF: آدرس‌های داخلی و خصوصی مسدودند (مگر در آزمون)."""
    if os.environ.get("RAYAN_LEARN_ALLOW_LOCAL") == "1":
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            return False
    return True


def _check_url(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if not _is_public_host(parsed.hostname):
        return None
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def fetch(url: str) -> dict | None:
    """صفحه را می‌خواند و متن اصلی را برمی‌گرداند."""
    safe = _check_url(url)
    if not safe:
        return None
    request = urllib.request.Request(safe, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8",
        "Accept-Language": "fa,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            content_type = response.headers.get_content_type()
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(MAX_BYTES)
            final_url = response.geturl()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if content_type == "application/pdf":
        return None
    text_raw = raw.decode(charset, "replace")
    if "html" in content_type or "<html" in text_raw[:500].lower():
        parser = _TextExtractor()
        try:
            parser.feed(text_raw)
        except Exception:  # noqa: BLE001 - HTML خراب نباید شکست بدهد
            return None
        body = parser.text()[:MAX_TEXT]
        title = parser.title or urllib.parse.urlparse(final_url).netloc
    else:
        body = re.sub(r"\n{3,}", "\n\n", text_raw)[:MAX_TEXT]
        title = urllib.parse.urlparse(final_url).netloc
    body = body.strip()
    if len(body) < 120:
        return None
    return {"title": normalize(title)[:160], "body": body, "url": safe, "final_url": final_url,
            "host": urllib.parse.urlparse(safe).netloc}


def store(page: dict) -> bool:
    """متن خوانده‌شده را در دانش محلی نگه می‌دارد (یک‌بار برای هر نشانی)."""
    url = page.get("url") or ""
    body = (page.get("body") or "").strip()
    if not url or len(body) < 120:
        return False
    norm = normalize(page.get("title") or "")
    with _connect() as db:
        exists = db.execute("SELECT 1 FROM seen WHERE url = ?", (url,)).fetchone()
        if exists:
            return False
        db.execute(
            "INSERT INTO pages(title, body, url, norm, host, learned_at) VALUES (?,?,?,?,?,?)",
            ((page.get("title") or "")[:160], body, url, norm, page.get("host") or "",
             str(int(time.time())))
        )
        db.execute("INSERT OR REPLACE INTO seen(url, learned_at) VALUES (?,?)",
                   (url, time.time()))
        db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES "
                   "('pages', CAST((SELECT COUNT(*) FROM pages) AS TEXT))")
    return True


def lookup(question: str, limit: int = 3) -> dict | None:
    """آیا از قبل چیزی دربارهٔ این موضوع از وب خوانده‌ایم؟"""
    path = db_path()
    if not os.path.exists(path):
        return None
    phrase = normalize(question)
    with _connect() as db:
        try:
            row = db.execute("SELECT title, body, url FROM pages WHERE norm = ? LIMIT 1",
                             (" ".join(subject_words(question)),)).fetchone()
            if row is None:
                terms = " ".join(subject_words(question, limit=6))
                if terms:
                    row = db.execute(
                        "SELECT title, body, url FROM pages WHERE pages MATCH ? "
                        "ORDER BY rank LIMIT 1", (terms,)).fetchone()
        except sqlite3.Error:
            return None
    if not row:
        return None
    return {"title": row[0], "body": row[1], "url": row[2]}


# ------------------------------------------------------------------ پاسخ از وب
_SENTENCE = re.compile(r"(?<=[.!؟?!])\s+|\n+")
_CUES = ("است", "هست", "بود", "نامیده", "گفته می‌شود", "عبارت است", "به شمار", "معروف",
         "شناخته", "می‌شود", "دارد", "شد")


def best_answer(text: str, question: str, limit: int = 420) -> str | None:
    """جمله‌ای از متن که به سؤال نزدیک است و شکل تعریف دارد."""
    subject = subject_words(question)
    if not subject:
        return None
    phrase = " ".join(subject)
    pieces = []
    for chunk in _SENTENCE.split(text or ""):
        chunk = chunk.strip(" -•\t\u200c")
        if 40 <= len(chunk) <= 400:
            pieces.append(chunk)
    ranked: list[tuple[float, int, str]] = []
    for order, piece in enumerate(pieces):
        norm = normalize(piece)
        position = norm.find(phrase)
        if position < 0 or position > 80:
            continue
        if not any(cue in norm[position:] for cue in _CUES):
            continue
        score = 3.0 if position == 0 else (2.0 if position < 30 else 1.0)
        ranked.append((score - order * 0.01, order, piece))
    if not ranked:
        return None
    best = max(ranked, key=lambda item: item[0])
    answer = best[2]
    if len(answer) > limit:
        answer = answer[:limit].rsplit(" ", 1)[0] + "…"
    return answer


def learn_url(url: str) -> dict | None:
    """یک نشانی را می‌خواند و ذخیره می‌کند."""
    page = fetch(url)
    if not page:
        return None
    page["stored"] = store(page)
    return page


def learn_query(query: str, pages: int = 2) -> list[dict]:
    """دربارهٔ یک پرسش در وب می‌گردد و بهترین صفحه‌ها را می‌آموزد."""
    if not enabled():
        return []
    deadline = time.time() + BUDGET
    try:
        from web import search as search_module
        results = search_module.search(query, limit=max(2, pages * 2)).get("results") or []
    except Exception:  # noqa: BLE001 - جست‌وجو نباید پاسخ را بشکند
        return []
    learned: list[dict] = []
    for item in results:
        if len(learned) >= pages or time.time() > deadline:
            break
        page = learn_url(item["url"])
        if not page:
            continue
        page["snippet"] = item.get("snippet") or ""
        learned.append(page)
    return learned


def answer(question: str, learn: bool = True) -> dict | None:
    """پاسخ مستند از دانشِ خوانده‌شده از وب؛ اگر نبود، اول یاد می‌گیرد."""
    entry = lookup(question)
    fresh: list[dict] = []
    if entry is None and learn:
        fresh = learn_query(question)
        entry = lookup(question)
        if entry is None and fresh:
            entry = {"title": fresh[0]["title"], "body": fresh[0]["body"],
                     "url": fresh[0]["url"]}
    if entry is None:
        return None
    text = best_answer(entry["body"], question)
    if not text:
        return None
    host = urllib.parse.urlparse(entry["url"]).netloc
    return {
        "answer": text,
        "sources": [{
            "title": (entry["title"] or host)[:90],
            "url": entry["url"],
            "domain": host,
            "source": "وب",
            "snippet": text[:170],
        }],
        "engine": "learn",
        "learned": bool(fresh),
        "learned_count": len(fresh),
        "confidence": 0.72,
    }


# ------------------------------------------------------------------ تقویت تدریجی
# سؤال‌هایی که شاهدی برایشان پیدا نشد، در صف «کنجکاوی» می‌مانند تا بعداً آموخته شوند.
def remember(question: str) -> None:
    question = (question or "").strip()[:200]
    if len(question) < 6:
        return
    try:
        with _connect() as db:
            db.execute("INSERT OR IGNORE INTO curiosity(question, asked_at) VALUES (?,?)",
                       (question, time.time()))
    except sqlite3.Error:
        pass


def pending(limit: int = 5) -> list[str]:
    try:
        with _connect() as db:
            rows = db.execute(
                "SELECT question FROM curiosity WHERE done = 0 AND tries < 3 "
                "ORDER BY asked_at LIMIT ?", (limit,)).fetchall()
    except sqlite3.Error:
        return []
    return [row[0] for row in rows]


def _mark(question: str, done: bool) -> None:
    try:
        with _connect() as db:
            db.execute(
                "UPDATE curiosity SET tries = tries + 1, done = ? WHERE question = ?",
                (1 if done else 0, question))
    except sqlite3.Error:
        pass


def grow(limit: int = 3) -> dict:
    """کارگر تقویت: چند سؤال بی‌جواب را از وب یاد می‌گیرد."""
    learned = failed = 0
    for question in pending(limit):
        pages = learn_query(question, pages=2)
        if pages:
            learned += 1
            _mark(question, True)
        else:
            failed += 1
            _mark(question, False)
    return {"learned": learned, "failed": failed}


def stats() -> dict:
    path = db_path()
    if not os.path.exists(path):
        # هنوز چیزی از وب خوانده نشده؛ خودِ لایه آماده است
        return {"ready": True, "pages": 0, "chars": 0, "waiting": 0, "online": enabled()}
    try:
        with _connect() as db:
            pages = db.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            chars = db.execute("SELECT COALESCE(SUM(LENGTH(body)),0) FROM pages").fetchone()[0]
            waiting = db.execute("SELECT COUNT(*) FROM curiosity WHERE done = 0").fetchone()[0]
        return {"ready": True, "pages": pages, "chars": chars, "bytes": os.path.getsize(path),
                "waiting": waiting, "online": enabled()}
    except sqlite3.Error as exc:
        return {"ready": False, "pages": 0, "error": str(exc)}


_STOP = threading.Event()


def start_worker(interval: float = 240.0, batch: int = 2) -> threading.Thread | None:
    """کارگر پس‌زمینه: هر چند دقیقه چند پرسش بی‌جواب را تقویت می‌کند."""
    if os.environ.get("RAYAN_AUTO_GROW", "1") == "0":
        return None

    def loop() -> None:
        while not _STOP.wait(interval):
            try:
                grow(batch)
            except Exception:  # noqa: BLE001 - کارگر نباید سرور را بخواباند
                continue

    thread = threading.Thread(target=loop, name="rayan-grow", daemon=True)
    thread.start()
    return thread


def verify(url: str) -> dict:
    """برای خط فرمان: خواندن یک نشانی و نمایش خلاصه."""
    page = fetch(url)
    if not page:
        return {"ok": False, "url": url}
    return {"ok": True, "url": page["url"], "title": page["title"],
            "chars": len(page["body"]), "preview": page["body"][:300]}


def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python -m web.learn <url|--grow|--stats>", file=sys.stderr)
        return 2
    command = argv[1]
    if command == "--grow":
        print(json.dumps(grow(int(argv[2]) if len(argv) > 2 else 3), ensure_ascii=False))
    elif command == "--stats":
        print(json.dumps(stats(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(verify(command), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
