"""کمک‌کننده‌های حساب کاربری برای آزمون‌های API.

از این نسخه، هوش فقط با حساب ثبت‌نام‌شده در دسترس است؛ پس هر آزمونی که با
``/api/chat`` کار می‌کند باید اول یک کاربر بسازد. این ماژول همان کار را یک‌جا
انجام می‌دهد تا تکرار در فایل‌های آزمون نماند.
"""
from __future__ import annotations

import itertools

_COUNTER = itertools.count(1)


def _challenge(client) -> dict:
    """چالش تازه؛ اگر محدودیتِ نرخ آزمون‌ها را گرفته باشد، یک‌بار آزاد می‌کند."""
    from web import security

    challenge = client.get("/api/captcha").json()
    if "token" not in challenge:
        with security.captcha_limiter.lock:
            security.captcha_limiter.hits.clear()
        challenge = client.get("/api/captcha").json()
    if "token" not in challenge:
        raise AssertionError(f"چالش امنیتی صادر نشد: {challenge}")
    return challenge


def human_proof(client) -> dict:
    """چالش «من ربات نیستم» را مثل مرورگر حل می‌کند."""
    from web import security

    challenge = _challenge(client)
    return {"token": challenge["token"],
            "nonce": security.HumanCheck.solve(challenge["salt"], challenge["bits"]),
            "evidence": {"moves": 14, "keys": 7, "elapsed_ms": 2400}}


def signup(client, email: str = "", password: str = "test-password",
           name: str = "کاربر آزمون") -> dict:
    """حساب می‌سازد و کوکی نشست را روی همان کلاینت نگه می‌دارد."""
    client.get("/chat")  # کوکی پایه، مثل باز کردن سایت در مرورگر
    address = email or f"user{next(_COUNTER)}@example.com"
    res = client.post("/api/auth/register", json={
        "name": name, "email": address, "password": password,
        "captcha": human_proof(client),
    })
    if res.status_code not in (200, 201):
        raise AssertionError(f"ثبت‌نام آزمون شکست خورد: {res.status_code} {res.text[:200]}")
    return res.json()
