"""فیلتر تهاجم رایان — سدِ سبک و بومی در برابر حمله‌های رایج وب.

هیچ سرویس بیرونی و هیچ فهرست سیاهِ دانلودی در کار نیست: چند قاعدهٔ
پر-confidence برای تراورسال، تزریق SQL، XSS، اجرای فرمان، SSRF،
Log4Shell و ابزارهای اسکن، به‌همراه سدِ درخواست‌های اسکن‌گر و شمارش
«ضربه» برای هر IP. بعد از چند ضربه، همان IP موقتاً بسته می‌شود.

این ماژول خالص است (وابسته به FastAPI نیست) تا مستقیم آزمون شود:

    >>> screen(path="/.env").blocked
    True
    >>> screen(path="/api/chat").blocked
    False
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.environ.get("RAYAN_SECURITY_LOG") or os.path.join(ROOT, "data", "security_events.jsonl")

BAN_STRIKES = int(os.environ.get("RAYAN_GUARD_STRIKES", "6"))
# آدرس‌های محلی بسته نمی‌شوند تا توسعه و آزمون قفل نشود (درخواستشان باز هم رد می‌شود).
BAN_EXEMPT = {"127.0.0.1", "::1", "localhost", "testclient"}
BAN_SECONDS = int(os.environ.get("RAYAN_GUARD_BAN", "900"))
MAX_BODY_SCAN = 64 * 1024          # بیشتر از این، فقط ابتدای بدنه بررسی می‌شود


# --------------------------------------------------------------------- قاعده‌ها
# (نام، الگو، توضیح فارسی) — همه با IGNORECASE اجرا می‌شوند.
_BODY_RULES: list[tuple[str, str, str]] = [
    ("sqli-union", r"\bunion\b[\s/*]+\b(?:all\b[\s/*]+)?\bselect\b", "تزریق SQL"),
    ("sqli-tautology", r"(?:'|%27|\")\s*(?:or|and)\s+(?:'|%27|\"|\d)+\s*=\s*(?:'|%27|\"|\d)+", "تزریق SQL"),
    ("sqli-comment", r"(?:'|%27)\s*(?:--|#|/\*)", "تزریق SQL"),
    ("sqli-sleep", r"\b(?:sleep|pg_sleep|benchmark|waitfor\s+delay)\s*\(", "تزریق SQL زمان‌محور"),
    ("sqli-schema", r"\binformation_schema\b|\binto\s+outfile\b|\bload_file\s*\(|\bxp_cmdshell\b", "دسترسی به schema"),
    ("xss-script", r"<\s*script\b|javascript\s*:|<\s*iframe\b|<\s*svg[^>]*onload|srcdoc\s*=", "تزریق اسکریپت"),
    ("xss-handler", r"\bon(?:error|load|click|mouseover|focus)\s*=\s*[\"']?[a-z(]", "تزریق اسکریپت"),
    ("xss-cookie", r"document\s*\.\s*cookie|window\s*\.\s*localStorage|eval\s*\(\s*atob", "سرقت نشست"),
    ("traversal", r"(?:\.\./){2,}|%2e%2e(?:%2f|/)|\.\.[\\/]\.\.", "خروج از مسیر"),
    ("lfi", r"/etc/(?:passwd|shadow|hosts)|\bboot\.ini\b|php://(?:input|filter)|expect://|file:///", "خواندن فایل سرور"),
    ("cmdi", r";\s*(?:cat|ls|wget|curl|nc|bash|sh|chmod|rm)\s|\|\s*(?:nc|bash|sh)\b|\$\(\s*[a-z]", "اجرای فرمان"),
    ("jndi", r"\$\{\s*jndi\s*:", "Log4Shell"),
    ("ssrf", r"169\.254\.169\.254|metadata\.google\.internal|\b127\.0\.0\.1:\d{2,5}/", "دسترسی به شبکهٔ داخلی"),
    ("proto", r"__proto__|constructor\s*\[\s*prototype\s*\]", "آلایش prototype"),
    ("crlf", r"%0d%0a|%0a(set-cookie|location)\s*:", "تزریق سرصفحه"),
    ("scanner", r"\b(?:nikto|sqlmap|acunetix|nessus|openvas|wpscan|masscan|zgrab)\b", "ابزار اسکن"),
]

_PATH_RULES: list[tuple[str, str, str]] = [
    ("dotfile", r"(?:^|/)\.(?:env|git|svn|hg|aws|ssh|htpasswd|htaccess|DS_Store)(?:/|$)", "پروندهٔ پنهان"),
    ("admin-scan", r"(?:wp-admin|wp-login|xmlrpc\.php|phpmyadmin|myadmin|administrator|cgi-bin|shell\.php|webshell|eval-stdin)", "اسکن پنل"),
    ("bad-ext", r"\.(?:php\d?|asp|aspx|jsp|jspx|cgi|pl|env|sql|bak|old|swp|ini|cfg|log)$", "پسوند ناشناس"),
    ("traverse-path", r"(?:\.\./)|(?:%2e%2e)", "خروج از مسیر"),
    ("long-path", r"^.{300,}$", "مسیر غیرعادی"),
]

_SCANNER_UA = re.compile(
    r"sqlmap|nikto|nmap|masscan|zgrab|acunetix|nessus|openvas|dirbuster|gobuster|wfuzz|"
    r"hydra|wpscan|feroxbuster|ffuf|nuclei|zaproxy|owasp|burpsuite|python-urllib/2",
    re.IGNORECASE,
)

_BODY_RULES_C = [(name, re.compile(pattern, re.IGNORECASE), label) for name, pattern, label in _BODY_RULES]
_PATH_RULES_C = [(name, re.compile(pattern, re.IGNORECASE), label) for name, pattern, label in _PATH_RULES]

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "POST", "PATCH", "DELETE", "PUT"}
BLOCKED_METHODS = {"TRACE", "TRACK", "CONNECT"}


@dataclass
class Verdict:
    blocked: bool = False
    rule: str = ""
    label: str = ""
    status: int = 403
    detail: str = ""
    score: int = 0
    extra: dict = field(default_factory=dict)


def _decode(text: str) -> str:
    if not text:
        return ""
    if "%" in text:
        try:
            text = urllib.parse.unquote_plus(text)
        except Exception:  # pragma: no cover - ورودی خراب
            pass
    return text.replace("\x00", "")


def screen(path: str = "", query: str = "", body: str = "",
           user_agent: str = "", method: str = "GET") -> Verdict:
    """ورودی خام درخواست را می‌سنجد؛ بدون اثر جانبی (برای آزمون)."""
    method = (method or "GET").upper()
    if method in BLOCKED_METHODS:
        return Verdict(True, "method", "روش غیرمجاز", detail="این نوع درخواست پشتیبانی نمی‌شود.", score=2)
    if method not in SAFE_METHODS:
        return Verdict(True, "method", "روش ناشناس", detail="این نوع درخواست پشتیبانی نمی‌شود.", score=2)

    if _SCANNER_UA.search(user_agent or ""):
        return Verdict(True, "scanner-ua", "ابزار اسکن", detail="دسترسی این ابزار بسته است.", score=3)

    path_l = _decode(path or "")
    for name, pattern, label in _PATH_RULES_C:
        if pattern.search(path_l):
            return Verdict(True, name, label, detail="مسیر درخواستی مجاز نیست.", score=2)

    haystack = _decode(query or "")[:4000] + "\n" + (body or "")[:MAX_BODY_SCAN]
    for name, pattern, label in _BODY_RULES_C:
        if pattern.search(haystack):
            return Verdict(True, name, label, detail="الگوی حمله در درخواست دیده شد.", score=2)
    return Verdict(False)


# ------------------------------------------------------------------- شمارش ضربه
class StrikeBook:
    """ضربه‌های هر IP و بستن موقت پس از عبور از آستانه."""

    def __init__(self, limit: int = BAN_STRIKES, seconds: int = BAN_SECONDS) -> None:
        self.limit = max(1, int(limit))
        self.seconds = max(30, int(seconds))
        self._strikes: dict[str, list[float]] = {}
        self._bans: dict[str, float] = {}
        self._lock = threading.Lock()
        self.counters: dict[str, int] = {}
        self.total = 0

    def banned(self, ip: str) -> int:
        with self._lock:
            until = self._bans.get(ip, 0)
            now = time.time()
            if until <= now:
                if until:
                    self._bans.pop(ip, None)
                return 0
            return int(until - now)

    def hit(self, ip: str, score: int = 1) -> tuple[bool, int]:
        """ضربه ثبت می‌کند؛ (مسدود شد؟، ثانیهٔ باقی‌مانده) برمی‌گرداند."""
        now = time.time()
        with self._lock:
            bucket = self._strikes.setdefault(ip, [])
            bucket[:] = [t for t in bucket if now - t < self.seconds]
            bucket.extend([now] * max(1, int(score)))
            self.total += 1
            if len(bucket) >= self.limit:
                bucket.clear()
                if ip in BAN_EXEMPT:
                    return False, 0
                self._bans[ip] = now + self.seconds
                return True, self.seconds
            return False, 0

    def reset(self, ip: str) -> None:
        with self._lock:
            self._strikes.pop(ip, None)
            self._bans.pop(ip, None)


strikes = StrikeBook()


def log_event(ip: str, path: str, method: str, verdict: Verdict, user_agent: str = "", status: int = 403) -> None:
    """ثبت رویداد در فایل JSONL با سقف اندازه (بدون دادهٔ حساس)."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        try:
            if os.path.getsize(LOG_FILE) > 2 * 1024 * 1024:
                os.replace(LOG_FILE, LOG_FILE + ".1")
        except OSError:
            pass
        row = {
            "t": round(time.time(), 3),
            "ip": ip[:64],
            "method": method[:10],
            "path": path[:180],
            "rule": verdict.rule,
            "label": verdict.label,
            "status": status,
            "ua": (user_agent or "")[:120],
        }
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:  # pragma: no cover - دیسک فقط‌خواندنی
        pass


def recent(limit: int = 40) -> list[dict]:
    """آخرین رویدادها برای پنل مدیریت."""
    rows: list[dict] = []
    try:
        with open(LOG_FILE, encoding="utf-8") as fh:
            for line in fh.readlines()[-500:]:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return list(reversed(rows[-limit:]))


def stats() -> dict:
    rows = recent(500)
    by_rule: dict[str, int] = {}
    by_ip: dict[str, int] = {}
    for row in rows:
        key = row.get("rule") or "unknown"
        by_rule[key] = by_rule.get(key, 0) + 1
        ip = row.get("ip") or "?"
        by_ip[ip] = by_ip.get(ip, 0) + 1
    return {
        "recent": rows[:30],
        "total_today": len(rows),
        "by_rule": dict(sorted(by_rule.items(), key=lambda x: -x[1])[:10]),
        "top_ips": [{"ip": ip, "hits": n} for ip, n in sorted(by_ip.items(), key=lambda x: -x[1])[:8]],
        "bans": {ip: int(until - time.time()) for ip, until in list(strikes._bans.items())[:20]  # noqa: SLF001
                 if until > time.time()},
        "rules": [label for _, _, label in _BODY_RULES] + [label for _, _, label in _PATH_RULES],
    }
