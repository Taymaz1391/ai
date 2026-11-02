#!/usr/bin/env python3
"""آزمونِ سرتاسریِ سایت — مثل یک کاربر واقعی، همهٔ مسیرها را می‌زند.

    python scripts/smoke_site.py --api http://127.0.0.1:8000

هر گام یا ✓ است یا ✗ با دلیل. خروجی غیرصفر یعنی رفتاری خراب است.
"""
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import secrets
import sys
import time
import urllib.error
import urllib.request

PASS, FAIL = "✓", "✗"
results: list[tuple[bool, str, str]] = []


class Client:
    """کلاینتِ ساده با کوکی و CSRF."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def request(self, method: str, path: str, body: dict | None = None,
                headers: dict | None = None) -> tuple[int, dict | str]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data:
            req.add_header("content-type", "application/json")
        if self.csrf:
            req.add_header("X-RayAn-CSRF", self.csrf)
            req.add_header("x-rayan-csrf", self.csrf)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with self.opener.open(req, timeout=45) as rsp:
                raw = rsp.read()
                self.csrf = self.csrf or rsp.headers.get("x-rayan-csrf", "")
                return rsp.status, _decode(raw)
        except urllib.error.HTTPError as exc:
            return exc.code, _decode(exc.read())
        except Exception as exc:  # noqa: BLE001
            return 0, str(exc)

    def get(self, path: str, **kw):
        return self.request("GET", path, **kw)

    def post(self, path: str, body: dict | None = None, **kw):
        return self.request("POST", path, body, **kw)


def _decode(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return raw.decode("utf-8", "ignore")


def step(ok: bool, name: str, detail: str = "") -> bool:
    results.append((ok, name, detail))
    print(f" {PASS if ok else FAIL} {name}" + (f" — {detail}" if detail else ""))
    return ok


def captcha(client: Client) -> dict:
    _, data = client.get("/api/captcha")
    if not isinstance(data, dict):
        return {}
    return data


def solve(challenge: dict) -> str:
    """معما همان sha256(salt:nonce) است؛ جوابش با آزمونِ صفرهای ابتدایی پیدا می‌شود."""
    salt = challenge.get("salt") or ""
    bits = int(challenge.get("bits") or 12)
    for nonce in range(0, 2000000):
        digest = hashlib.sha256(f"{salt}:{nonce}".encode()).digest()
        if int.from_bytes(digest, "big") >> (256 - bits) == 0:
            return str(nonce)
    return ""


EVIDENCE = {"moves": 12, "keys": 8, "elapsed_ms": 2600, "honeypot": "", "webdriver": False}


def proof(challenge: dict) -> dict:
    """همان ساختاری که human.js می‌سازد: {token, nonce, evidence}."""
    return {"token": challenge.get("token", ""), "nonce": solve(challenge),
            "evidence": dict(EVIDENCE)}


def register(base: str, email: str, password: str, name: str) -> tuple[Client, dict]:
    client = Client(base)
    chal = captcha(client)
    payload = {"email": email, "password": password, "name": name,
               "captcha": proof(chal)}
    status, data = client.post("/api/auth/register", payload)
    return client, {"status": status, "data": data, "captcha": chal}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-password", default="13911391")
    args = parser.parse_args()
    base = args.api.rstrip("/")

    # ── ۱) سلامت و صفحه‌ها
    anon = Client(base)
    status, health = anon.get("/api/health")
    step(status == 200 and isinstance(health, dict), "سلامت سرویس", f"{status} {health}")

    for path in ("/", "/chat", "/login", "/signup", "/pricing", "/models", "/about",
                 "/compare", "/support", "/settings", "/admin", "/offline", "/privacy"):
        code, body = anon.get(path)
        size = len(body) if isinstance(body, str) else 0
        step(code == 200 and size > 500, f"صفحهٔ {path}", f"{code} · {size} بایت")

    for path in ("/api/models", "/api/plans", "/api/samples", "/api/flags", "/api/tools",
                 "/api/status", "/api/locale", "/api/ads", "/api/benchmark"):
        code, data = anon.get(path)
        step(code == 200, f"API {path}", str(code))

    # ── ۲) مهمان بدونِ حساب باید درِ ورود بگیرد
    code, data = anon.post("/api/chat", {"message": "پایتخت فرانسه چیست؟"})
    gate = code in (401, 403) or (isinstance(data, dict) and "detail" in (data or {}))
    step(gate, "گفتگو بدونِ حساب بسته است", f"{code} {str(data)[:60]}")

    # ── ۳) ثبت‌نام
    stamp = secrets.token_hex(4)
    email = f"smoke-{stamp}@example.com"
    password = "Smoke-Test-9x"
    user, info = register(base, email, password, "آزمون")
    ok = info["status"] in (200, 201)
    step(ok, "ثبت‌نام", f"{info['status']} {str(info['data'])[:80]}")
    if not ok:
        return report()
    client = user
    code, me = client.get("/api/auth/me")
    step(code == 200 and isinstance(me, dict) and (me.get("user") or me.get("email")),
         "نشست پس از ثبت‌نام", f"{code} {str(me)[:80]}")

    # ── ۴) گفتگو
    questions = [
        ("پایتخت فرانسه چیست؟", "پاریس"),
        ("۲۵ درصد از ۱۲۰۰ چند است؟", "۳۰۰"),
        ("در پایتون چطور یک فایل JSON بخوانم؟", "json"),
        ("ترجمه کن به انگلیسی: کتاب روی میز است", "book"),
        ("یک پاراگراف دربارهٔ اهمیت کتاب‌خواندن بنویس", "کتاب"),
    ]
    conversation_id = None
    for question, needle in questions:
        started = time.time()
        code, data = client.post("/api/chat", {"message": question})
        took = time.time() - started
        answer = (data or {}).get("answer", "") if isinstance(data, dict) else ""
        conversation_id = (data or {}).get("conversation_id") or conversation_id
        step(code == 200 and needle.lower() in answer.lower(),
             f"پاسخ: {question[:34]}", f"{code} · {took:.2f}s · {answer[:50]}")
        if took > 3:
            step(False, f"سرعت: {question[:26]}", f"{took:.1f} ثانیه")

    code, listing = client.get("/api/conversations")
    convs = (listing or {}).get("conversations") if isinstance(listing, dict) else None
    step(code == 200 and isinstance(convs, list) and convs, "فهرستِ گفتگوها",
         f"{code} · {len(convs or [])} مورد")
    if conversation_id:
        code, one = client.get(f"/api/conversations/{conversation_id}")
        step(code == 200, "خواندنِ یک گفتگو", str(code))
        code, _ = client.request("PATCH", f"/api/conversations/{conversation_id}",
                                 {"title": "گفتگوی آزمون"})
        step(code == 200, "تغییرِ عنوانِ گفتگو", str(code))
        code, shared = client.post(f"/api/conversations/{conversation_id}/share")
        token = (shared or {}).get("token") if isinstance(shared, dict) else ""
        step(code == 200 and bool(token), "ساختِ لینکِ اشتراک", f"{code} · {token}")
        if token:
            code, page = anon.get(f"/s/{token}")
            step(code == 200, "بازکردنِ لینکِ اشتراک بدونِ ورود", str(code))
            code, payload = anon.get(f"/api/share/{token}")
            step(code == 200, "API لینکِ اشتراک", str(code))
        code, _ = client.request("DELETE", f"/api/conversations/{conversation_id}/share")
        step(code == 200, "حذفِ لینکِ اشتراک", str(code))

    code, _ = client.post("/api/feedback", {"message_id": None, "rating": "up"})
    step(code in (200, 201, 422), "ثبتِ بازخورد", str(code))

    # ── ۵) تنظیماتِ حساب
    code, _ = client.request("PATCH", "/api/auth/me", {"name": "آزمون دو"})
    step(code == 200, "تغییرِ نام", str(code))
    code, usage = client.get("/api/usage")
    step(code == 200, "مصرفِ حساب", str(code))

    # ── ۶) خروج و ورود دوباره
    code, _ = client.post("/api/auth/logout", {})
    step(code == 200, "خروج", str(code))
    fresh = Client(base)
    chal = captcha(fresh)
    code, data = fresh.post("/api/auth/login", {
        "identifier": email, "password": password, "captcha": proof(chal)})
    step(code == 200, "ورود دوباره", f"{code} {str(data)[:70]}")

    # ── ۷) پنلِ مدیریت
    admin = Client(base)
    chall = captcha(admin)
    code, data = admin.post("/api/admin/login", {"password": args.admin_password})
    step(code == 200, "ورودِ مدیر", f"{code} {str(data)[:70]}")
    for path in ("/api/admin/session", "/api/admin/overview", "/api/admin/users",
                 "/api/admin/settings", "/api/admin/knowledge", "/api/admin/security",
                 "/api/admin/audit", "/api/admin/ops", "/api/admin/capacity",
                 "/api/admin/quality", "/api/admin/flags", "/api/admin/conversations"):
        code, data = admin.get(path)
        step(code == 200, f"مدیر {path}", f"{code} {str(data)[:50]}")

    # ── ۸) ابزارها و جست‌وجو
    code, data = client.post("/api/tools/run", {"name": "calc", "args": {"expression": "2+2"}})
    step(code in (200, 422), "اجرای ابزار حساب", str(code))
    code, data = client.get("/api/search?q=تهران")
    step(code in (200, 401, 403, 503), "جست‌وجوی وب", str(code))

    return report()


def report() -> int:
    bad = [name for ok, name, _ in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} گام سبز")
    if bad:
        print("شکست‌خورده: " + "، ".join(bad[:10]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
