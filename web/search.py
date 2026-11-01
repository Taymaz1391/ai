"""جست‌وجوی وب رایان — بدون هیچ API تجاری و بدون کلید.

سه مسیر پشتیبانی می‌شود و هر کدام که در دسترس باشد استفاده می‌شود:

1. ``RAYAN_SEARX_URL`` — نمونهٔ خودمیزبان SearXNG (بهترین گزینه برای استقرار).
2. DuckDuckGo (نسخهٔ HTML و Lite) — بدون کلید.
3. Wikipedia API فارسی/انگلیسی — بدون کلید و پایدارترین منبع.

همهٔ درخواست‌ها با ``urllib`` استاندارد و مهلت کوتاه انجام می‌شوند، در حافظه
کش می‌شوند و هیچ داده‌ای به سرویس هوش مصنوعی بیرونی نمی‌رود. اگر شبکه بسته
باشد، تابع ``search`` فهرست خالی برمی‌گرداند و چت به مدل محلی برمی‌گردد.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from html import unescape

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 RayanBot/1.0")
TIMEOUT = float(os.environ.get("RAYAN_SEARCH_TIMEOUT", "7"))
DEADLINE = float(os.environ.get("RAYAN_SEARCH_DEADLINE", "5"))
CACHE_TTL = 600
CACHE_MAX = 128
SNIPPET_CHARS = 260

_CACHE: dict[tuple, tuple[float, list[dict]]] = {}
_LOCK = threading.Lock()

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ------------------------------------------------------------------ کمکی‌ها
def clean(text: str) -> str:
    """برچسب‌های HTML را برمی‌دارد و فاصله‌ها را یکدست می‌کند."""
    text = unescape(_TAG_RE.sub(" ", text or ""))
    text = _WS_RE.sub(" ", text).strip()
    return text


def domain(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _network_ok() -> bool:
    """در حالت ملی هیچ درخواست بیرونی زده نمی‌شود؛ پاسخ از دانش محلی می‌آید."""
    from web import network
    return network.allow_outbound()


def _get(url: str, accept: str = "text/html") -> str:
    if not _network_ok():
        return ""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": accept,
        "Accept-Language": "fa,en;q=0.8",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)  # noqa: S310 - دامنه‌های ثابت
    except Exception as exc:  # noqa: BLE001 - شبکه نباید صفحه را بشکند
        from web import network
        network.report_failure(f"search: {exc}")
        return ""
    with resp:
        raw = resp.read(1_500_000)
        charset = resp.headers.get_content_charset() or "utf-8"
        from web import network
        network.report_success()
    return raw.decode(charset, "replace")


def _cached(key: tuple, builder) -> list[dict]:
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return [dict(item) for item in hit[1]]
    items = builder()
    with _LOCK:
        if len(_CACHE) > CACHE_MAX:
            oldest = sorted(_CACHE, key=lambda k: _CACHE[k][0])[:32]
            for k in oldest:
                _CACHE.pop(k, None)
        _CACHE[key] = (now, [dict(item) for item in items])
    return items


def _result(title: str, url: str, snippet: str, source: str) -> dict | None:
    title, snippet = clean(title), clean(snippet)
    if not title or not url:
        return None
    return {
        "title": title[:160],
        "url": url,
        "snippet": snippet[:SNIPPET_CHARS],
        "source": source,
        "domain": domain(url),
    }


# ------------------------------------------------------------------ ارائه‌دهنده‌ها
def _ddg(query: str, limit: int) -> list[dict]:
    """DuckDuckGo نسخهٔ HTML؛ لینک‌ها گاهی با /l/?uddg= ریدایرکت می‌شوند."""
    html = _get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
    out: list[dict] = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'(?:<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>)',
        re.S,
    )
    for href, title, snip_a, snip_b in pattern.findall(html):
        url = unescape(href)
        if "uddg=" in url:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            url = parsed.get("uddg", [url])[0]
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("http"):
            continue
        item = _result(title, url, snip_a or snip_b, "duckduckgo")
        if item and item["url"] not in {r["url"] for r in out}:
            out.append(item)
        if len(out) >= limit:
            break
    return out


def _ddg_lite(query: str, limit: int) -> list[dict]:
    html = _get("https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query))
    out: list[dict] = []
    links = re.findall(r"<a[^>]+class=['\"]result-link['\"][^>]+href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", html, re.S)
    snippets = re.findall(r"<td[^>]+class=['\"]result-snippet['\"][^>]*>(.*?)</td>", html, re.S)
    for index, (href, title) in enumerate(links[:limit]):
        url = unescape(href)
        if "uddg=" in url:
            url = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("uddg", [url])[0]
        snip = snippets[index] if index < len(snippets) else ""
        item = _result(title, url, snip, "duckduckgo")
        if item:
            out.append(item)
    return out


def _wiki(query: str, limit: int, lang: str = "fa") -> list[dict]:
    code = "fa" if lang.startswith("fa") else "en"
    api = (f"https://{code}.wikipedia.org/w/api.php?action=query&list=search&format=json"
           f"&utf8=1&srlimit={max(1, min(limit, 8))}&srsearch=" + urllib.parse.quote(query))
    data = json.loads(_get(api, accept="application/json"))
    out: list[dict] = []
    for row in (data.get("query", {}).get("search") or []):
        title = row.get("title", "")
        url = f"https://{code}.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        item = _result(title, url, row.get("snippet", ""), f"wikipedia-{code}")
        if item:
            out.append(item)
    return out


def _searx(query: str, limit: int) -> list[dict]:
    base = os.environ.get("RAYAN_SEARX_URL", "").rstrip("/")
    if not base:
        return []
    data = json.loads(_get(f"{base}/search?format=json&language=fa&q=" + urllib.parse.quote(query),
                           accept="application/json"))
    out = []
    for row in (data.get("results") or [])[:limit]:
        item = _result(row.get("title", ""), row.get("url", ""), row.get("content", ""), "searx")
        if item:
            out.append(item)
    return out


def providers() -> list[str]:
    raw = os.environ.get("RAYAN_SEARCH_PROVIDERS", "")
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return ["searx", "ddg", "wiki"]


# ------------------------------------------------------------------ عمومی
def search(query: str, limit: int = 5, lang: str = "fa") -> dict:
    """جست‌وجو می‌کند؛ خروجی همیشه یک دیکشنری با کلید results است."""
    query = (query or "").strip()[:200]
    if len(query) < 2:
        return {"query": query, "results": [], "provider": "", "cached": False}

    def one(name: str) -> list[dict]:
        try:
            if name == "searx":
                return _searx(query, limit)
            if name == "ddg":
                return _ddg(query, limit) or _ddg_lite(query, limit)
            if name == "wiki":
                return _wiki(query, limit, lang) or _wiki(query, limit, "en")
        except Exception:  # noqa: BLE001 - یک منبع خراب نباید جست‌وجو را بکشد
            return []
        return []

    def build() -> list[dict]:
        """همهٔ منابع هم‌زمان؛ هر کدام زودتر آمد، همان جواب می‌دهد.

        مهلت کلی کوتاه است تا کاربر پشت «در حال جست‌وجو» نماند؛ اگر هیچ منبعی
        تا آن مهلت جواب نداد، خالی برمی‌گردیم و مدل محلی جواب می‌دهد.
        """
        names = providers()
        if not names:
            return []
        results: dict[str, list[dict]] = {}
        lock = threading.Lock()
        done = threading.Event()

        def worker(name: str) -> None:
            found = one(name)
            with lock:
                results[name] = found
                if found:
                    done.set()

        threads = [threading.Thread(target=worker, args=(name,), daemon=True)
                   for name in names]
        for thread in threads:
            thread.start()
        deadline = time.time() + min(TIMEOUT, DEADLINE)
        while time.time() < deadline and not done.is_set():
            done.wait(0.05)
        gathered: list[dict] = []
        seen: set[str] = set()
        with lock:
            snapshot = dict(results)
        for name in names:                      # ترتیب اولویت حفظ می‌شود
            for item in snapshot.get(name, []):
                if item["url"] in seen:
                    continue
                seen.add(item["url"])
                gathered.append(item)
                if len(gathered) >= limit:
                    return gathered[:limit]
        return gathered[:limit]

    key = ("search", query.casefold(), limit, lang)
    cached_flag = False
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            cached_flag = True
    results = _cached(key, build)
    provider = results[0]["source"] if results else ""
    return {"query": query, "results": results, "provider": provider, "cached": cached_flag}


_SEARCH_HINTS = (
    "جستجو", "جست‌وجو", "سرچ", "search", "آخرین خبر", "اخبار امروز", "قیمت امروز",
    "نرخ امروز", "آب و هوا", "هوای امروز", "جدیدترین", "لینک بده", "منبع بده",
    "کیست", "چیست",
)


def wants_search(message: str) -> bool:
    """آیا کاربر خودش جست‌وجو خواسته است؟ (برای پیشنهاد دکمهٔ وب)"""
    text = (message or "").casefold()
    return any(hint.casefold() in text for hint in _SEARCH_HINTS)


_NUM = "۰۱۲۳۴۵۶۷۸۹"


def to_fa(value: int) -> str:
    return str(value).translate(str.maketrans("0123456789", _NUM))


def compose(query: str, results: list[dict], *, lang: str = "fa") -> str:
    """پاسخ استخراجی از منابع وب: نقل مستقیم + ارجاع، بدون ساختن ادعای تازه."""
    if not results:
        if lang.startswith("fa"):
            return ("به منابع وب دسترسی پیدا نکردم. یا شبکهٔ سرور بسته است یا سرویس جست‌وجو "
                    "پاسخ نداد؛ می‌توانم از دانش محلی مدل استفاده کنم، اما بدون منبع است.")
        return ("I could not reach any web source. The server may be offline or the search "
                "provider unavailable; I can answer from the local model, without citations.")

    lines: list[str] = []
    if lang.startswith("fa"):
        lines.append(f"بر اساس {to_fa(len(results))} منبع وب دربارهٔ «{query}»:")
        lines.append("")
        for index, item in enumerate(results, 1):
            snippet = item.get("snippet") or "—"
            lines.append(f"{to_fa(index)}. **{item['title']}** — {snippet}")
            lines.append(f"   {item['url']}")
        lines.append("")
        lines.append("این متن، خلاصهٔ عین منابع است؛ برای جزئیات هر لینک را باز کن.")
    else:
        lines.append(f"Based on {len(results)} web sources about “{query}”:")
        lines.append("")
        for index, item in enumerate(results, 1):
            lines.append(f"{index}. **{item['title']}** — {item.get('snippet') or '—'}")
            lines.append(f"   {item['url']}")
        lines.append("")
        lines.append("This is an extractive summary; open the links for the full text.")
    return "\n".join(lines)
