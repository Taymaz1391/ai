"""تشخیص زبان و نسخهٔ محتوا — بدون هیچ سرویس بیرونی.

سه منبع به ترتیب اولویت:

1. پارامتر ``?lang=`` (انتخاب دستی کاربر)
2. کوکی ``rayan_lang`` (انتخاب قبلی)
3. جدول محلی GeoIP در ``data/geoip.json`` (اگر مدیر آن را بگذارد)
4. هدر ``Accept-Language`` مرورگر

هیچ درخواستی به اینترنت زده نمی‌شود؛ در شبکهٔ ملی هم کار می‌کند.
"""
from __future__ import annotations

import ipaddress
import json
import os
import threading
import time

LANGS = ("fa", "en")

# نسخه‌های ویدیوی تبلیغاتی برای هر زبان
VIDEOS = {
    "fa": {
        "landscape": "/static/assets/video/promo-fa-16x9.mp4",
        "vertical": "/static/assets/video/promo-fa-9x16.mp4",
        "square": "/static/assets/video/promo-fa-1x1.mp4",
        "poster": "/static/assets/video/promo-fa-poster.jpg",
    },
    "en": {
        "landscape": "/static/assets/video/promo-en-16x9.mp4",
        "vertical": "/static/assets/video/promo-en-9x16.mp4",
        "square": "/static/assets/video/promo-en-1x1.mp4",
        "poster": "/static/assets/video/promo-en-poster.jpg",
    },
}

# کشورهایی که زبان پیش‌فرضشان فارسی است (سرصفحهٔ کشور را پراکسی میزبان می‌فرستد:
# Cloudflare → ``cf-ipcountry``، Vercel → ``x-vercel-ip-country``).
FA_COUNTRIES = {"IR", "AF", "TJ"}
COUNTRY_HEADERS = ("cf-ipcountry", "x-vercel-ip-country", "x-geo-country")
FA_TIMEZONES = ("Asia/Tehran", "Asia/Kabul", "Asia/Dushanbe", "Iran")

_geo_lock = threading.Lock()
_geo_cache: dict[str, object] = {"path": None, "mtime": 0.0, "ranges": [], "default": ""}


def geoip_path() -> str:
    return os.environ.get("RAYAN_GEOIP") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "geoip.json"
    )


def _load_geo() -> tuple[list[tuple[ipaddress._BaseNetwork, str]], str]:
    """جدول CIDR→زبان را با حافظهٔ نهان بر اساس زمان تغییر فایل می‌خواند."""
    path = geoip_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return [], ""
    with _geo_lock:
        if _geo_cache["path"] == path and abs(float(_geo_cache["mtime"]) - mtime) < 1e-6:
            return _geo_cache["ranges"], _geo_cache["default"]  # type: ignore[return-value]
        ranges: list[tuple[ipaddress._BaseNetwork, str]] = []
        default = ""
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            for item in data.get("ranges", []):
                lang = str(item.get("lang", "")).lower()
                if lang not in LANGS:
                    continue
                try:
                    ranges.append((ipaddress.ip_network(item["cidr"], strict=False), lang))
                except (KeyError, ValueError):
                    continue
            default = str(data.get("default", "")).lower()
            if default not in LANGS:
                default = ""
        except (OSError, json.JSONDecodeError):
            return [], ""
        _geo_cache.update({"path": path, "mtime": mtime, "ranges": ranges, "default": default})
        return ranges, default


def geo_lang(ip: str) -> str:
    """زبان پیشنهادی بر اساس IP؛ اگر جدول نبود رشتهٔ خالی."""
    ranges, default = _load_geo()
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return default
    for network, lang in ranges:
        if addr in network:
            return lang
    return default


def country_of(request) -> str:
    """کد دوحرفی کشور از سرصفحهٔ پراکسی میزبان (بدون فراخوانی سرویس بیرونی)."""
    for name in COUNTRY_HEADERS:
        value = (request.headers.get(name) or "").strip().upper()
        if len(value) == 2 and value.isalpha() and value not in ("XX", "T1"):
            return value
    return ""


def tz_lang(tz: str) -> str:
    """حدس زبان از منطقهٔ زمانی مرورگر (سیگنال جغرافیایی سمت کاربر)."""
    value = (tz or "").strip()
    if not value:
        return ""
    if any(value == item or value.startswith(item + "/") for item in FA_TIMEZONES):
        return "fa"
    if "/" in value or value in ("UTC", "GMT"):
        return "en"
    return ""


def accept_lang(header: str) -> str:
    """نخستین زبان قابل‌پشتیبانی از Accept-Language."""
    for part in (header or "").split(","):
        tag = part.split(";")[0].strip().lower()
        if not tag:
            continue
        base = tag.split("-")[0]
        if base in LANGS:
            return base
    return ""


def detect(request) -> dict:
    """زبان، منبع تشخیص و نسخه‌های ویدیو برای این درخواست."""
    query = (request.query_params.get("lang") or "").lower()
    cookie = (request.cookies.get("rayan_lang") or "").lower()
    ip = _client_ip(request)
    if query in LANGS:
        lang, source = query, "query"
    elif cookie in LANGS:
        lang, source = cookie, "cookie"
    else:
        geo = geo_lang(ip)
        hdr = accept_lang(request.headers.get("accept-language", ""))
        country = country_of(request)
        tz = request.query_params.get("tz", "")
        if geo:
            lang, source = geo, "geo"
        elif hdr:
            lang, source = hdr, "accept-language"
        elif country in FA_COUNTRIES:
            lang, source = "fa", "geo"
        elif country:
            lang, source = "en", "geo"
        elif tz_lang(tz):
            lang, source = tz_lang(tz), "timezone"
        else:
            lang, source = "fa", "default"
    return {
        "lang": lang,
        "dir": "rtl" if lang == "fa" else "ltr",
        "source": source,
        "videos": VIDEOS[lang],
        "alternate": "/en" if lang == "fa" else "/",
    }


def _client_ip(request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", "") or ""
