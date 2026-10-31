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
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- صدور
    def issue(self) -> dict:
        now = time.time()
        salt = secrets.token_hex(12)
        body = f"{salt}:{self.bits}:{int(now + self.ttl)}"
        token = f"{body}:{sign(body)}"
        self._gc(now)
        return {
            "token": token,
            "salt": salt,
            "bits": self.bits,
            "expires_in": self.ttl,
            "algorithm": "sha256-leading-zero-bits",
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

    def redeem(self, token: str, nonce: str) -> bool:
        parts = (token or "").split(":")
        if len(parts) != 4:
            return False
        salt, bits_raw, expires_raw, signature = parts
        body = f"{salt}:{bits_raw}:{expires_raw}"
        if not verify(body, signature):
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
