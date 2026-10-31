"""لایهٔ امنیتی رایان — انسان‌سنجی، محدودساز نرخ و امضای سرور.

هیچ سرویس بیرونی در کار نیست: چالش «من ربات نیستم» یک اثبات‌کار محلی است.
سرور نمکی امضاشده می‌دهد و مرورگر باید عددی پیدا کند که هش SHA-256 آن با
تعداد بیت صفرِ خواسته‌شده شروع شود. پیدا کردنش برای آدم کسری از ثانیه است،
اما برای رباتی که هزاران حساب می‌سازد پرهزینه می‌شود.

قاعده: هیچ رازی در کد نیست. کلید امضا از متغیر محیطی ``RAYAN_SECRET``
خوانده می‌شود و اگر نبود، یک‌بار ساخته و در ``data/secret.key`` با دسترسی
۶۰۰ ذخیره می‌شود.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_FILE = os.path.join(ROOT, "data", "secret.key")

DEFAULT_BITS = int(os.environ.get("RAYAN_CAPTCHA_BITS", "15"))
CAPTCHA_TTL = 15 * 60          # ثانیه
MIN_SOLVE_TIME = 0.6           # ثانیه؛ پاسخ فوری یعنی ربات
MIN_FILL_TIME = 0.6            # کمترین زمان معقول برای پر کردن فرم
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _load_secret() -> bytes:
    env = os.environ.get("RAYAN_SECRET", "").strip()
    if env:
        return env.encode("utf-8")
    os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "rb") as fh:
            data = fh.read().strip()
        if len(data) >= 32:
            return data
    token = secrets.token_hex(32).encode("ascii")
    fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(token)
    return token


SECRET = _load_secret()


def sign(payload: str) -> str:
    return hmac.new(SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(payload: str, signature: str) -> bool:
    return hmac.compare_digest(sign(payload), (signature or "").lower())


def normalize_digits(value: str) -> str:
    return (value or "").translate(_FA_DIGITS).strip()


def _coarse_ip(ip: str) -> str:
    """IP را به شبکهٔ گسترده‌تر تبدیل می‌کند تا تغییر جزئی آدرس، فرم را نشکند."""
    ip = (ip or "").strip()
    if ":" in ip:                     # IPv6: شصت‌وچهار بیت نخست
        return ":".join(ip.split(":")[:4])
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        return ".".join(parts[:3])
    return ip[:24]


def fingerprint(ip: str = "", user_agent: str = "") -> str:
    """اثر انگشت سبکِ مرورگر: شبکهٔ IP + عامل کاربر. هیچ داده‌ای ذخیره نمی‌شود."""
    raw = f"{_coarse_ip(ip)}|{(user_agent or '')[:180]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class HumanCheck:
    """چالش اثبات‌کار با امضای سرور و مصرف یک‌باره.

    >>> hc = HumanCheck()
    >>> ch = hc.issue()
    >>> nonce = hc.solve(ch["salt"], ch["bits"])        # در مرورگر انجام می‌شود
    >>> hc.redeem(ch["token"], nonce)
    True
    """

    def __init__(self, bits: int = DEFAULT_BITS, ttl: int = CAPTCHA_TTL) -> None:
        self.bits = max(10, min(22, int(bits)))
        self.ttl = ttl
        self._used: dict[str, float] = {}
        self._fails: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- صدور
    def issue(self, fp: str = "", bonus: int = 0) -> dict:
        now = time.time()
        salt = secrets.token_hex(12)
        bits = max(10, min(22, self.bits + max(0, min(6, int(bonus)))))
        body = f"{salt}:{bits}:{int(now + self.ttl)}:{(fp or '')[:20]}"
        token = f"{body}:{sign(body)}"
        self._gc(now)
        return {
            "token": token,
            "salt": salt,
            "bits": bits,
            "expires_in": self.ttl,
            "algorithm": "sha256-leading-zero-bits",
            "min_ms": int(MIN_FILL_TIME * 1000),
        }

    # ---------------------------------------------------------------- بررسی
    @staticmethod
    def solves(salt: str, nonce: str, bits: int) -> bool:
        digest = hashlib.sha256(f"{salt}:{nonce}".encode("utf-8")).digest()
        value = int.from_bytes(digest, "big")
        return value >> (256 - bits) == 0

    @classmethod
    def solve(cls, salt: str, bits: int, limit: int = 20_000_000) -> str:
        """فقط برای آزمون و ابزار خط فرمان؛ مرورگر خودش حل می‌کند."""
        for n in range(limit):
            nonce = str(n)
            if cls.solves(salt, nonce, bits):
                return nonce
        raise RuntimeError("چالش حل نشد")

    def redeem(self, token: str, nonce: str, fp: str = "") -> bool:
        parts = (token or "").split(":")
        if len(parts) != 5:
            return False
        salt, bits_raw, expires_raw, bound_fp, signature = parts
        body = f"{salt}:{bits_raw}:{expires_raw}:{bound_fp}"
        if not verify(body, signature):
            return False
        # اگر چالش به مرورگر بسته شده باشد، همان مرورگر باید پاسخ بدهد.
        if bound_fp and fp and not hmac.compare_digest(bound_fp, (fp or "")[:20]):
            return False
        try:
            bits = int(bits_raw)
            expires = float(expires_raw)
        except ValueError:
            return False
        now = time.time()
        if expires < now or expires - now > self.ttl + 60:
            return False
        nonce = normalize_digits(nonce)
        if not re.fullmatch(r"\d{1,12}", nonce or ""):
            return False
        with self._lock:
            self._gc(now)
            if token in self._used:
                return False
        if not self.solves(salt, nonce, bits):
            return False
        with self._lock:
            self._used[token] = now
        return True

    # ------------------------------------------------- ارزیابی شواهد رفتاری
    @staticmethod
    def evidence_ok(evidence: dict | None) -> tuple[bool, str]:
        """شواهد رابط کاربری را می‌سنجد: زمان پر کردن، حرکت اشاره‌گر، تلهٔ ربات."""
        ev = evidence or {}
        if str(ev.get("honeypot") or "").strip():
            return False, "honeypot"
        if ev.get("webdriver") is True:
            return False, "automation"
        try:
            elapsed = float(ev.get("elapsed_ms") or 0)
        except (TypeError, ValueError):
            elapsed = 0.0
        try:
            moves = int(ev.get("moves") or 0)
            keys = int(ev.get("keys") or 0)
        except (TypeError, ValueError):
            moves = keys = 0
        if elapsed < MIN_FILL_TIME * 1000:
            return False, "too_fast"
        if moves + keys < 2 and elapsed < 3000:
            return False, "no_interaction"
        return True, ""

    def assess(self, token: str, nonce: str, evidence: dict | None = None,
               fp: str = "") -> tuple[bool, str]:
        ok, reason = self.evidence_ok(evidence)
        if not ok:
            return False, reason
        if not self.redeem(token, nonce, fp):
            return False, "invalid_proof"
        return True, ""

    # ------------------------------------------------ سختی پویا پس از خطا
    def note_failure(self, fp: str) -> None:
        if not fp:
            return
        with self._lock:
            count, stamp = self._fails.get(fp, (0, time.time()))
            if time.time() - stamp > 1800:
                count = 0
            self._fails[fp] = (min(6, count + 1), time.time())

    def difficulty_bonus(self, fp: str) -> int:
        with self._lock:
            count, stamp = self._fails.get(fp, (0, 0))
            if time.time() - stamp > 1800:
                return 0
            return min(4, count * 2)

    def _gc(self, now: float) -> None:
        if len(self._used) < 2000:
            return
        for key, stamp in list(self._used.items()):
            if now - stamp > self.ttl * 2:
                self._used.pop(key, None)


class Window:
    """محدودساز نرخ پنجرهٔ لغزان، مستقل برای هر کلید."""

    def __init__(self, limit: int, seconds: float = 60.0) -> None:
        self.limit = limit
        self.seconds = seconds
        self.hits: dict[str, deque[float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str, cost: int = 1) -> bool:
        now = time.time()
        with self.lock:
            bucket = self.hits.setdefault(key, deque())
            while bucket and now - bucket[0] > self.seconds:
                bucket.popleft()
            if len(bucket) + cost > self.limit:
                return False
            for _ in range(cost):
                bucket.append(now)
            if len(self.hits) > 4000:
                for k in [k for k, v in self.hits.items() if not v][:1000]:
                    self.hits.pop(k, None)
            return True

    def retry_after(self, key: str) -> int:
        with self.lock:
            bucket = self.hits.get(key)
            if not bucket:
                return 0
            return max(1, int(self.seconds - (time.time() - bucket[0])))


human = HumanCheck()
captcha_limiter = Window(limit=24, seconds=60)
