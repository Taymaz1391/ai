"""پنل مدیریت رایان — احراز هویت جدا، CSRF، لاگ حسابرسی و ابزارهای خودکار.

این ماژول هیچ وابستگی بیرونی ندارد: نشست مدیریت در SQLite ذخیره می‌شود،
توکن CSRF تصادفی است و کلید ورود از متغیر محیطی یا فایل محلی خوانده می‌شود.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from web.store import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_COOKIE = "rayan_admin"
CSRF_HEADER = "x-rayan-csrf"
ADMIN_FILE = os.environ.get("RAYAN_ADMIN_FILE") or os.path.join(ROOT, "data", "admin.json")
LOGIN_WINDOW = 900
MAX_ATTEMPTS = 5
# گذرواژهٔ پیش‌فرض پنل مدیریت (با متغیر محیطی RAYAN_ADMIN_PASSWORD عوض می‌شود)
DEFAULT_PASSWORD = os.environ.get("RAYAN_ADMIN_DEFAULT", "13911391")


def _hash(value: str, salt: str) -> str:
    import hashlib
    return hashlib.scrypt(value.encode("utf-8"), salt=bytes.fromhex(salt),
                          n=2 ** 14, r=8, p=1, dklen=32).hex()


# ------------------------------------------------------------------ پیکربندی
def _load_local() -> dict:
    try:
        with open(ADMIN_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_local(data: dict) -> None:
    os.makedirs(os.path.dirname(ADMIN_FILE), exist_ok=True)
    tmp = ADMIN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, ADMIN_FILE)
    try:
        os.chmod(ADMIN_FILE, 0o600)
    except OSError:
        pass


_ENV_CREDS: dict[str, dict] = {}


def _env_credentials(password: str) -> dict:
    """گذرواژهٔ مدیریت از متغیر محیطی — برای استقرار و آزمون، بدون نوشتن فایل."""
    if password not in _ENV_CREDS:
        import hashlib
        salt = hashlib.sha256(("rayan-admin-env:" + password).encode("utf-8")).hexdigest()[:32]
        _ENV_CREDS[password] = {
            "email": os.environ.get("RAYAN_ADMIN_EMAIL", "admin@rayan.local"),
            "pw_hash": _hash(password, salt),
            "pw_salt": salt,
            "source": "env",
        }
    return _ENV_CREDS[password]


def admin_credentials() -> dict:
    """گذرواژهٔ مدیر: متغیر محیطی بر فایل محلی اولویت دارد."""
    env_hash = os.environ.get("RAYAN_ADMIN_HASH", "").strip()
    env_salt = os.environ.get("RAYAN_ADMIN_SALT", "").strip()
    if env_hash and env_salt:
        return {"pw_hash": env_hash, "pw_salt": env_salt, "email": os.environ.get("RAYAN_ADMIN_EMAIL", "admin@rayan.local")}
    env_password = os.environ.get("RAYAN_ADMIN_PASSWORD", "").strip()
    if env_password:
        return _env_credentials(env_password)
    local = _load_local()
    if local.get("pw_hash") and local.get("pw_salt"):
        return local
    # راه‌اندازی نخست: گذرواژهٔ پیش‌فرض مالک، ذخیرهٔ محلی و هشدار تغییر
    password = os.environ.get("RAYAN_ADMIN_PASSWORD") or DEFAULT_PASSWORD
    salt = secrets.token_hex(16)
    data = {
        "email": os.environ.get("RAYAN_ADMIN_EMAIL", "admin@rayan.local"),
        "pw_hash": _hash(password, salt),
        "pw_salt": salt,
        "created_at": time.time(),
        "generated_password": password,
    }
    _save_local(data)
    print(f"[rayan-admin] گذرواژهٔ مدیریت تنظیم شد (پیش‌فرض={DEFAULT_PASSWORD}). "
          f"برای امنیت بیشتر RAYAN_ADMIN_PASSWORD را عوض کن. فایل: {ADMIN_FILE}", flush=True)
    return data


def using_default_password() -> bool:
    """آیا گذرواژهٔ مدیریت همان مقدار پیش‌فرض است؟ (هشدار در پنل)"""
    try:
        creds = admin_credentials()
        salt = creds.get("pw_salt", "")
        return bool(salt) and hmac.compare_digest(_hash(DEFAULT_PASSWORD, salt), creds.get("pw_hash", ""))
    except Exception:  # pragma: no cover
        return False


def set_admin_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(400, "گذرواژهٔ مدیر باید حداقل ۸ نویسه باشد.")
    salt = secrets.token_hex(16)
    data = _load_local()
    data.update({"pw_hash": _hash(password, salt), "pw_salt": salt, "updated_at": time.time()})
    data.pop("generated_password", None)
    _save_local(data)


# ------------------------------------------------------------------ نشست‌ها
def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def current_admin(request: Request) -> dict | None:
    token = request.cookies.get(ADMIN_COOKIE, "")
    return store().admin_session(token)


def require_admin(request: Request, csrf: bool = False) -> dict:
    session = current_admin(request)
    if session is None:
        raise HTTPException(401, "دسترسی مدیریت لازم است.")
    user = session["user"]
    if user.get("plan") != "admin" and str(user.get("id")) not in admin_ids():
        raise HTTPException(403, "این حساب دسترسی مدیریت ندارد.")
    if csrf:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, session["csrf"]):
            raise HTTPException(403, "توکن امنیتی نامعتبر است؛ صفحه را دوباره بارگذاری کنید.")
    return session


def admin_ids() -> set[str]:
    return {x.strip() for x in os.environ.get("RAYAN_ADMIN_IDS", "").split(",") if x.strip()}


def audit(action: str, request: Request, target: str = "", detail: str = "", actor: str = "admin") -> None:
    store().audit(action=action, actor=actor, target=target, detail=detail, ip=_client_ip(request))


# ------------------------------------------------------------------- مدل‌ها
class AdminLogin(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AdPayload(BaseModel):
    slot: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(default="", max_length=300)
    cta: str = Field(default="بیشتر بدانید", max_length=40)
    url: str = Field(min_length=1, max_length=400)
    weight: int = Field(default=1, ge=1, le=100)
    active: bool = True
    starts_at: float = 0
    ends_at: float = 0


class AdPatch(BaseModel):
    slot: str | None = Field(default=None, min_length=2, max_length=40)
    title: str | None = Field(default=None, min_length=1, max_length=120)
    body: str | None = Field(default=None, max_length=300)
    cta: str | None = Field(default=None, max_length=40)
    url: str | None = Field(default=None, min_length=1, max_length=400)
    weight: int | None = Field(default=None, ge=1, le=100)
    active: bool | None = None
    starts_at: float | None = None
    ends_at: float | None = None


class SettingsPayload(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class UserAction(BaseModel):
    action: str = Field(pattern="^(ban|unban|promote|demote|plan)$")
    plan: str = Field(default="free", max_length=20)


SAFE_URL = re.compile(r"^(https?://|/)[^\s\"'<>]+$")


# ------------------------------------------------------------------- مسیرها
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/session")
def session_info(request: Request) -> dict:
    session = current_admin(request)
    if session is None:
        return {"authenticated": False}
    session = require_admin(request)
    from web import owner as owner_module
    owner = owner_module.status()
    return {
        "authenticated": True,
        "csrf": session["csrf"],
        "user": {"id": session["user"]["id"], "name": session["user"]["name"], "email": session["user"]["email"]},
        "expires_at": session["expires_at"],
        "owner": {"name": owner["name"], "default_password": owner["default_password"]},
    }


@router.post("/login")
def admin_login(req: AdminLogin, request: Request, response: Response) -> dict:
    ip = _client_ip(request)
    attempts = store().note_attempt(f"admin:{ip}")
    if attempts > MAX_ATTEMPTS:
        audit("login_locked", request, detail=f"attempts={attempts}")
        raise HTTPException(429, "تلاش‌های ناموفق زیاد؛ ۱۵ دقیقه بعد دوباره امتحان کنید.")
    creds = admin_credentials()
    candidate = _hash(req.password, creds["pw_salt"])
    if not hmac.compare_digest(candidate, creds["pw_hash"]):
        audit("login_failed", request, detail=f"attempt={attempts}")
        raise HTTPException(401, "گذرواژهٔ مدیریت نادرست است.")

    store().clear_attempts(f"admin:{ip}")
    admin_id = _ensure_admin_user(creds.get("email", "admin@rayan.local"))
    csrf = secrets.token_urlsafe(24)
    token = store().create_admin_session(admin_id, csrf, ip=ip, user_agent=request.headers.get("user-agent", ""))
    response.set_cookie(ADMIN_COOKIE, token, max_age=2 * 3600, httponly=True, samesite="strict",
                        secure=os.environ.get("RAYAN_ENV") == "prod", path="/")
    audit("login", request, target=str(admin_id))
    return {"ok": True, "csrf": csrf, "expires_in": 7200}


@router.post("/logout")
def admin_logout(request: Request, response: Response) -> dict:
    require_admin(request, csrf=True)
    store().delete_admin_session(request.cookies.get(ADMIN_COOKIE, ""))
    response.delete_cookie(ADMIN_COOKIE, path="/")
    audit("logout", request)
    return {"ok": True}


@router.get("/overview")
def overview(request: Request, days: int = 14) -> dict:
    require_admin(request)
    days = max(3, min(int(days), 60))
    stats = store().admin_stats(days)
    ads = store().list_ads()
    return {
        "stats": stats,
        "ads": ads,
        "settings": store().all_settings(),
        "flags": flags(),
        "system": system_info(),
    }


@router.get("/security")
def security_stats(request: Request) -> dict:
    """آمار سد تهاجم و انسان‌سنجی برای پنل مدیریت."""
    require_admin(request)
    from web import guard
    data = guard.stats()
    data["human_checks"] = {
        "allowance_per_minute": 24,
        "min_fill_ms": 900,
        "bound_to_browser": True,
        "single_use": True,
    }
    data["default_admin_password"] = using_default_password()
    return data


@router.get("/users")
def users(request: Request, q: str = "", limit: int = 200) -> dict:
    require_admin(request)
    return {"users": store().list_users(limit=max(1, min(int(limit), 500)), query=q.strip())}


@router.post("/users/{user_id}/action")
def user_action(user_id: int, req: UserAction, request: Request) -> dict:
    require_admin(request, csrf=True)
    if req.action == "ban":
        store().ban_user(user_id)
    elif req.action == "unban":
        store().set_plan(user_id, "free")
    elif req.action == "promote":
        store().set_plan(user_id, "admin")
    elif req.action == "demote":
        store().set_plan(user_id, "free")
    elif req.action == "plan":
        if req.plan not in {"guest", "free", "pro", "banned", "admin"}:
            raise HTTPException(400, "پلن نامعتبر است.")
        store().set_plan(user_id, req.plan)
    audit(f"user_{req.action}", request, target=str(user_id), detail=req.plan)
    return {"ok": True, "user": store().get_user(user_id)}


@router.get("/ads")
def ads_list(request: Request) -> dict:
    require_admin(request)
    return {"ads": store().list_ads()}


@router.post("/ads")
def ads_create(req: AdPayload, request: Request) -> dict:
    require_admin(request, csrf=True)
    if not SAFE_URL.match(req.url):
        raise HTTPException(400, "نشانی تبلیغ باید با http(s):// یا / شروع شود.")
    ad = store().create_ad(req.slot, req.title, req.body, req.url, req.cta, req.weight,
                           req.starts_at, req.ends_at)
    if not req.active:
        store().update_ad(ad["id"], active=0)
    audit("ad_create", request, target=str(ad.get("id")), detail=req.title)
    return {"ad": ad}


@router.patch("/ads/{ad_id}")
def ads_update(ad_id: int, req: AdPatch, request: Request) -> dict:
    """ویرایش جزئی: هر فیلدی که فرستاده شود به‌روز می‌شود (مثلاً فقط active)."""
    require_admin(request, csrf=True)
    existing = next((a for a in store().list_ads() if int(a["id"]) == ad_id), None)
    if existing is None:
        raise HTTPException(404, "این تبلیغ پیدا نشد.")
    data = req.model_dump(exclude_unset=True)
    if "url" in data and not SAFE_URL.match(data["url"]):
        raise HTTPException(400, "نشانی تبلیغ نامعتبر است.")
    if "active" in data:
        data["active"] = 1 if data["active"] else 0
    store().update_ad(ad_id, **data)
    audit("ad_update", request, target=str(ad_id), detail=",".join(sorted(data)))
    updated = next((a for a in store().list_ads() if int(a["id"]) == ad_id), None)
    return {"ok": True, "ad": updated}


@router.delete("/ads/{ad_id}")
def ads_delete(ad_id: int, request: Request) -> dict:
    require_admin(request, csrf=True)
    store().delete_ad(ad_id)
    audit("ad_delete", request, target=str(ad_id))
    return {"ok": True}


@router.get("/audit")
def audit_list(request: Request, limit: int = 100) -> dict:
    require_admin(request)
    return {"entries": store().audit_log(limit=max(1, min(int(limit), 500)))}


@router.get("/settings")
def settings_get(request: Request) -> dict:
    require_admin(request)
    return {"settings": store().all_settings(), "flags": flags()}


@router.post("/settings")
def settings_set(req: SettingsPayload, request: Request) -> dict:
    require_admin(request, csrf=True)
    for key, value in req.values.items():
        if not re.fullmatch(r"[a-z0-9_.-]{2,48}", key):
            raise HTTPException(400, f"کلید نامعتبر: {key}")
        store().set_setting(key, str(value)[:400])
    audit("settings_update", request, detail=",".join(req.values.keys())[:200])
    return {"settings": store().all_settings()}


class LearnPayload(BaseModel):
    url: str = Field(default="", max_length=2000)
    query: str = Field(default="", max_length=200)
    pages: int = Field(default=2, ge=1, le=5)


@router.get("/knowledge")
def knowledge(request: Request) -> dict:
    """وضعیت دانشِ آنلاین: چند صفحه خوانده شده و چند پرسش در انتظار است."""
    from web import learn as learn_module
    require_admin(request)
    stats = learn_module.stats()
    rows: list[dict] = []
    try:
        with learn_module._connect() as db:  # noqa: SLF001 - همان ماژول داخلی
            rows = [
                {"title": title, "url": url, "chars": len(body or ""), "learned_at": stamp}
                for title, url, body, stamp in db.execute(
                    "SELECT title, url, body, learned_at FROM pages ORDER BY learned_at DESC "
                    "LIMIT 25").fetchall()
            ]
    except Exception:  # noqa: BLE001 - فهرست نباید صفحه را بشکند
        rows = []
    return {"stats": stats, "recent": rows,
            "waiting": learn_module.pending(20)}


@router.post("/knowledge/learn")
def knowledge_learn(req: LearnPayload, request: Request) -> dict:
    """آموختن از یک نشانی یا گشتن دربارهٔ یک موضوع و خواندن نتیجه‌ها."""
    from web import learn as learn_module
    require_admin(request, csrf=True)
    if req.url:
        page = learn_module.learn_url(req.url)
        if not page:
            raise HTTPException(422, "خواندن این نشانی ممکن نشد.")
        audit("knowledge_learn_url", request, detail=req.url[:160])
        return {"ok": True, "page": {"title": page["title"], "url": page["url"],
                                     "chars": len(page["body"]),
                                     "stored": page["stored"]}}
    if not req.query:
        raise HTTPException(422, "نشانی یا موضوع لازم است.")
    pages = learn_module.learn_query(req.query, pages=req.pages)
    audit("knowledge_learn_query", request, detail=req.query[:160])
    return {"ok": bool(pages), "learned": [
        {"title": page["title"], "url": page["url"], "chars": len(page["body"])}
        for page in pages
    ]}


@router.post("/knowledge/grow")
def knowledge_grow(request: Request, limit: int = 3) -> dict:
    """اجرای دستی کارگر تقویت تدریجی روی صف کنجکاوی."""
    from web import learn as learn_module
    require_admin(request, csrf=True)
    result = learn_module.grow(max(1, min(int(limit), 10)))
    audit("knowledge_grow", request, detail=str(result))
    return result


@router.post("/maintenance")
def maintenance(request: Request, task: str = "vacuum") -> dict:
    require_admin(request, csrf=True)
    result: dict[str, Any] = {"task": task}
    if task == "vacuum":
        store().vacuum()
    elif task == "purge":
        result.update(store().purge(30))
    elif task == "backup":
        name = time.strftime("rayan-%Y%m%d-%H%M%S.sqlite3")
        path = os.path.join(ROOT, "data", "backups", name)
        store().backup_to(path)
        result["path"] = os.path.relpath(path, ROOT)
    else:
        raise HTTPException(400, "کار ناشناخته.")
    audit(f"maintenance_{task}", request)
    return result


@router.post("/owner-password")
def owner_password(req: AdminLogin, request: Request) -> dict:
    """گذرواژهٔ مالک (ورود با نام کاربری) را عوض می‌کند."""
    require_admin(request, csrf=True)
    from web import owner as owner_module
    if len(req.password) < owner_module.MIN_LENGTH:
        raise HTTPException(400, f"گذرواژهٔ مالک باید حداقل {owner_module.MIN_LENGTH} نویسه باشد.")
    if req.password == owner_module.DEV_DEFAULT_PASSWORD:
        raise HTTPException(400, "همان گذرواژهٔ پیش‌فرض قابل قبول نیست.")
    try:
        owner_module.set_password(req.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    audit("owner_password_changed", request)
    return {"ok": True, "owner": owner_module.status()}


@router.post("/password")
def change_password(req: AdminLogin, request: Request) -> dict:
    require_admin(request, csrf=True)
    set_admin_password(req.password)
    audit("password_change", request)
    return {"ok": True}


# --------------------------------------------------------------- تبلیغ عمومی
def flags() -> dict:
    raw = store().all_settings()
    return {
        "ads_enabled": raw.get("ads_enabled", "1") == "1",
        "signup_open": raw.get("signup_open", "1") == "1",
        "guest_chat": raw.get("guest_chat", "1") == "1",
        "deep_enabled": raw.get("deep_enabled", "1") == "1",
        "studio_enabled": raw.get("studio_enabled", "1") == "1",
        "maintenance": raw.get("maintenance", "0") == "1",
        "web_search": raw.get("web_search", "1") == "1",
        "auto_learn": raw.get("auto_learn", "1") == "1",
        "announcement": raw.get("announcement", ""),
    }


def system_info() -> dict:
    import platform
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": os.cpu_count(),
        "uptime_s": round(time.time() - _BOOT),
        "pid": os.getpid(),
        "admin_configured": bool(admin_credentials().get("pw_hash")),
        "admin_email": admin_credentials().get("email", ""),
    }


_BOOT = time.time()
_started = False


def _ensure_admin_user(email: str) -> int:
    user = store()._one("SELECT id FROM users WHERE email=?", (email,))  # noqa: SLF001
    if user:
        store().set_plan(int(user["id"]), "admin")
        return int(user["id"])
    created = store().create_user(email, secrets.token_urlsafe(24), "مدیر رایان")
    if created is None:
        user = store()._one("SELECT id FROM users WHERE email=?", (email,))  # noqa: SLF001
        assert user is not None
        store().set_plan(int(user["id"]), "admin")
        return int(user["id"])
    store().set_plan(created["id"], "admin")
    return int(created["id"])


# ------------------------------------------------------------- زمان‌بند خودکار
def start_scheduler(interval: int = 3600) -> None:
    """نگهداری خودکار: پاک‌سازی، بکاپ روزانه و VACUUM هفتگی — بدون نیاز به مدیر."""
    global _started
    if _started:
        return
    _started = True

    def loop() -> None:
        last_backup = 0.0
        last_vacuum = 0.0
        while True:
            try:
                now = time.time()
                store().purge(30)
                if now - last_backup > 86400:
                    name = time.strftime("rayan-%Y%m%d.sqlite3")
                    store().backup_to(os.path.join(ROOT, "data", "backups", name))
                    last_backup = now
                    backups = sorted(os.listdir(os.path.join(ROOT, "data", "backups")))
                    for old in backups[:-7]:
                        try:
                            os.remove(os.path.join(ROOT, "data", "backups", old))
                        except OSError:
                            pass
                if now - last_vacuum > 7 * 86400:
                    store().vacuum()
                    last_vacuum = now
            except Exception as exc:  # pragma: no cover - نگهبان
                print(f"[rayan-scheduler] {exc}", flush=True)
            time.sleep(interval)

    threading.Thread(target=loop, name="rayan-scheduler", daemon=True).start()
