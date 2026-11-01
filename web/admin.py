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


ADMIN_HEADER = "x-rayyan-admin"


def current_admin(request: Request) -> dict | None:
    """نشستِ مدیر از کوکی یا سرصفحهٔ اختصاصی؛ دومی وقتی کوکی مسدود است."""
    token = request.cookies.get(ADMIN_COOKIE, "")
    session = store().admin_session(token) if token else None
    if session:
        return session
    header = (request.headers.get(ADMIN_HEADER) or "").strip()
    return store().admin_session(header) if header else None


def require_admin(request: Request, csrf: bool = False) -> dict:
    session = current_admin(request)
    if session is None:
        raise HTTPException(401, "دسترسی مدیریت لازم است.")
    user = session["user"]
    if (user.get("plan") != "admin" and user.get("role") != "owner"
            and str(user.get("id")) not in admin_ids()):
        raise HTTPException(403, "این حساب دسترسی مدیریت ندارد.")
    # با احرازِ سرصفحه‌ای، CSRF معنا ندارد (مرورگر آن سرصفحه را خودبه‌خود نمی‌فرستد)
    if csrf and not (request.headers.get(ADMIN_HEADER) or "").strip():
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


class MailConfig(BaseModel):
    """پیکربندیِ سرویس ایمیل از پنل؛ گذرواژه خالی یعنی «همان قبلی بماند»."""
    host: str = Field(default="", max_length=120)
    port: int = Field(default=587, ge=1, le=65535)
    user: str = Field(default="", max_length=160)
    password: str = Field(default="", max_length=200)
    sender: str = Field(default="", max_length=200)
    mode: str = Field(default="starttls", max_length=12)


class MailTest(BaseModel):
    to: str = Field(min_length=3, max_length=160)


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


class OpsOrder(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    kind: str = Field(default="order", pattern="^(order|note)$")


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


@router.post("/elevate")
def elevate(request: Request, response: Response) -> dict:
    """مالکِ واردشده در سایت، بدون گذرواژهٔ دوم وارد پنل می‌شود.

    فقط حسابی که نقش «owner» دارد می‌تواند این کار را بکند؛ هیچ راه دیگری برای
    دور زدن گذرواژهٔ مدیریت وجود ندارد.
    """
    cookie = request.cookies.get(os.environ.get("RAYAN_SESSION_COOKIE", "rayan_session"), "")
    if not cookie:
        raw = (request.headers.get("authorization") or "").strip()
        if raw.lower().startswith("bearer "):
            cookie = raw[7:].strip()
    user = store().session_user(cookie)
    if not user:
        raise HTTPException(401, "برای ورود به پنل، اول با حساب مالک وارد سایت شو.")
    if (user.get("role") != "owner" and user.get("plan") != "admin"
            and str(user.get("id")) not in admin_ids()):
        raise HTTPException(403, "این حساب دسترسی مدیریت ندارد.")
    csrf = secrets.token_urlsafe(24)
    token = store().create_admin_session(int(user["id"]), csrf, ip=_client_ip(request),
                                         user_agent=request.headers.get("user-agent", ""))
    response.set_cookie(ADMIN_COOKIE, token, max_age=2 * 3600, httponly=True,
                        samesite="strict", secure=os.environ.get("RAYAN_ENV") == "prod", path="/")
    store().record_event("admin_elevate", user_id=int(user["id"]), ip=_client_ip(request))
    audit("admin_elevate", request, target=str(user["id"]))
    return {"authenticated": True, "csrf": csrf, "admin_token": token}


@router.post("/login")
def admin_login(req: AdminLogin, request: Request, response: Response) -> dict:
    ip = _client_ip(request)
    attempts = store().note_attempt(f"admin:{ip}")
    if attempts > MAX_ATTEMPTS:
        audit("login_locked", request, detail=f"attempts={attempts}")
        raise HTTPException(429, "تلاش‌های ناموفق زیاد؛ ۱۵ دقیقه بعد دوباره امتحان کنید.")
    # یک گذرواژه برای همه‌چیز: گذرواژهٔ مالک (همان که در /login وارد می‌شود)
    # هم در این‌جا پذیرفته است، تا مالک هیچ‌وقت دو رمز جدا نداشته باشد.
    creds = admin_credentials()
    ok = hmac.compare_digest(_hash(req.password, creds["pw_salt"]), creds["pw_hash"])
    if not ok:
        from web import owner as owner_module
        if owner_module.verify(req.password):
            ok = True
            creds = {**creds, "email": owner_module.credentials().get("name", creds.get("email"))}
    if not ok:
        audit("login_failed", request, detail=f"attempt={attempts}")
        raise HTTPException(401, "گذرواژه نادرست است. همان گذرواژهٔ ورود به سایت را بزنید.")

    store().clear_attempts(f"admin:{ip}")
    admin_id = _ensure_admin_user(creds.get("email", "admin@rayan.local"))
    csrf = secrets.token_urlsafe(24)
    token = store().create_admin_session(admin_id, csrf, ip=ip, user_agent=request.headers.get("user-agent", ""))
    response.set_cookie(ADMIN_COOKIE, token, max_age=2 * 3600, httponly=True, samesite="strict",
                        secure=os.environ.get("RAYAN_ENV") == "prod", path="/")
    audit("login", request, target=str(admin_id))
    return {"ok": True, "csrf": csrf, "admin_token": token, "expires_in": 7200}


@router.post("/logout")
def admin_logout(request: Request, response: Response) -> dict:
    require_admin(request, csrf=True)
    store().delete_admin_session(request.cookies.get(ADMIN_COOKIE, ""))
    response.delete_cookie(ADMIN_COOKIE, path="/")
    audit("logout", request)
    return {"ok": True}


@router.get("/mail")
def mail_status(request: Request) -> dict:
    """وضعیتِ سرویس ایمیل؛ گذرواژه هرگز برنمی‌گردد."""
    require_admin(request)
    from web import mailer as mailer_module
    data = mailer_module.status()
    data["from_env"] = bool(os.environ.get("RAYAN_SMTP_HOST"))
    return data


@router.post("/mail")
def mail_save(req: MailConfig, request: Request) -> dict:
    """ذخیرهٔ پیکربندی SMTP از رابط مدیریت — بدون ویرایش فایل یا متغیر محیطی."""
    require_admin(request, csrf=True)
    from web import mailer as mailer_module
    mode = req.mode if req.mode in ("starttls", "ssl", "none") else "starttls"
    if req.host and not mailer_module.valid_address(req.sender.split("<")[-1].strip(" >") or ""):
        raise HTTPException(400, "نشانی فرستنده معتبر نیست؛ مثلاً «رایان <you@example.com>».")
    values = {"host": req.host.strip(), "port": str(req.port), "user": req.user.strip(),
              "from": req.sender.strip(), "tls": mode}
    if req.password:
        values["pass"] = req.password
    for key, value in values.items():
        store().set_setting(f"mail.{key}", value)
    audit("mail_config", request, detail=f"host={req.host[:40]} mode={mode}")
    return {"saved": True, "status": mailer_module.status()}


@router.post("/mail/test")
def mail_test(req: MailTest, request: Request) -> dict:
    """ارسالِ ایمیل آزمایشی با همین پیکربندی؛ خطا صادقانه برمی‌گردد."""
    require_admin(request, csrf=True)
    from web import mailer as mailer_module
    if not mailer_module.configured():
        raise HTTPException(503, "اول پیکربندیِ ایمیل را ذخیره کن.")
    try:
        mailer_module.send_test(req.to.strip())
    except mailer_module.MailError as exc:
        audit("mail_test_failed", request)
        raise HTTPException(502, str(exc)) from exc
    audit("mail_test", request, detail=req.to.strip()[-40:])
    return {"sent": True}


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
    """حساب مالک را تضمین می‌کند: نقشِ owner و طرح admin.

    فقط همین حساب نقش مالک می‌گیرد؛ ثبت‌نام‌های عادی همیشه کاربر معمولی‌اند.
    """
    user = store()._one("SELECT id FROM users WHERE email=?", (email,))  # noqa: SLF001
    if user is None:
        created = store().create_user(email, secrets.token_urlsafe(24), "مدیر رایان")
        if created is not None:
            user = {"id": created["id"]}
        else:
            user = store()._one("SELECT id FROM users WHERE email=?", (email,))  # noqa: SLF001
    assert user is not None
    user_id = int(user["id"])
    store().set_plan(user_id, "admin")
    store().set_owner(user_id)
    return user_id


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


# --------------------------------------------------------------- اتاق فرمان
@router.get("/ops")
def ops_list(request: Request, limit: int = 40) -> dict:
    """دستورها و پیام‌های مالک به عاملِ سازنده (فقط خواندن)."""
    require_admin(request)
    from web import ops as ops_module
    return {"orders": ops_module.listing(limit), "stats": ops_module.stats()}


@router.post("/ops")
def ops_add(req: OpsOrder, request: Request) -> dict:
    """ثبت دستور تازه؛ اجرای واقعی در نشست بعدی عامل انجام و پاسخ ثبت می‌شود."""
    session = require_admin(request, csrf=True)
    from web import ops as ops_module
    row = ops_module.add(req.text, kind=req.kind,
                         author=(session.get("user") or {}).get("name", "owner"))
    audit("ops_order", request, target=row["id"], detail=req.kind)
    return {"ok": True, "order": row}


@router.get("/ops/pending")
def ops_pending(request: Request) -> dict:
    require_admin(request)
    from web import ops as ops_module
    rows = ops_module.pending()
    return {"pending": len(rows), "orders": rows[:20]}


@router.post("/reload")
def reload_runtime(request: Request) -> dict:
    """بارگذاری دوبارهٔ مدل و پاک‌سازی حافظه‌های میانگیر — بدون قطع سرویس."""
    require_admin(request, csrf=True)
    from web import server as server_module
    info = server_module.soft_reload()
    audit("reload", request, detail=json.dumps(info, ensure_ascii=False)[:180])
    return {"ok": True, **info}


@router.post("/restart")
def restart_workers(request: Request) -> dict:
    """راه‌اندازی دوبارهٔ کارگرها با SIGHUP؛ درخواست‌های جاری کامل می‌شوند."""
    require_admin(request, csrf=True)
    from web import server as server_module
    info = server_module.restart_workers()
    audit("restart", request, detail=json.dumps(info, ensure_ascii=False)[:180])
    return {"ok": bool(info.get("signalled")), **info}


# ------------------------------------------------------------ شبکه و ظرفیت
class NetworkMode(BaseModel):
    mode: str = Field(pattern="^(auto|national|global)$")


@router.get("/network")
def network_state(request: Request) -> dict:
    """وضعیت خروج به اینترنت و ساختن امنیت در حالت ملی."""
    require_admin(request)
    from web import network
    return {"ok": True, **network.stats()}


@router.post("/network")
def network_set(req: NetworkMode, request: Request) -> dict:
    require_admin(request, csrf=True)
    from web import network
    value = network.set_mode(req.mode)
    audit("network_mode", request, detail=value)
    return {"ok": True, **network.stats()}


@router.get("/capacity")
def capacity(request: Request) -> dict:
    """ظرفیت واقعی همین ماشین: کارگرها، صف، کش و میانگین پاسخ‌گویی."""
    require_admin(request)
    from web import server as server_module
    return {"ok": True, **server_module.capacity_report()}


# ═══════════════════════════════════════════════ دانشنامهٔ بررسی‌شده (ویرایش)
KNOWLEDGE_FILE = os.environ.get("RAYAN_KNOWLEDGE_FILE") or os.path.join(ROOT, "data", "knowledge.jsonl")


def _read_knowledge() -> list[dict]:
    rows: list[dict] = []
    try:
        with open(KNOWLEDGE_FILE, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        return []
    return rows


def _write_knowledge(rows: list[dict]) -> None:
    tmp = KNOWLEDGE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, KNOWLEDGE_FILE)
    # حافظهٔ ماژول دانش پاک شود تا ویرایش‌ها بی‌درنگ دیده شوند
    try:
        from web import knowledge as knowledge_module
        knowledge_module._ENTRIES = None  # noqa: SLF001 - همان ماژول داخلی
    except Exception:  # noqa: BLE001 - نباید پنل را بشکند
        pass


class KnowledgeRow(BaseModel):
    id: str = Field(default="", max_length=80)
    q: str = Field(default="", max_length=300)
    keys: list[str] = Field(default_factory=list)
    a: str = Field(min_length=1, max_length=2000)


class KnowledgeDelete(BaseModel):
    id: str = Field(min_length=1, max_length=80)


@router.get("/knowledge/entries")
def knowledge_entries(request: Request, q: str = "", limit: int = 100) -> dict:
    require_admin(request)
    rows = _read_knowledge()
    needle = (q or "").strip().lower()
    if needle:
        rows = [r for r in rows if needle in json.dumps(r, ensure_ascii=False).lower()]
    total = len(_read_knowledge())
    return {"total": total, "rows": rows[: max(1, min(int(limit), 400))]}


@router.post("/knowledge/entries")
def knowledge_upsert(req: KnowledgeRow, request: Request) -> dict:
    """افزودن یا ویرایشِ یک ردیفِ دانش؛ پاسخ بی‌درنگ در گفتگو دیده می‌شود."""
    require_admin(request, csrf=True)
    rows = _read_knowledge()
    rid = (req.id or "").strip() or "kb-" + secrets.token_hex(4)
    entry = {"id": rid, "q": req.q.strip(), "keys": [k.strip() for k in req.keys if k.strip()],
             "a": req.a.strip(), "source": None}
    replaced = False
    for index, row in enumerate(rows):
        if row.get("id") == rid:
            rows[index] = entry
            replaced = True
            break
    if not replaced:
        rows.append(entry)
    _write_knowledge(rows)
    audit("knowledge_upsert", request, target=rid)
    try:
        from web import retrieval as retrieval_module
        retrieval_module.reload_knowledge()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "entry": entry, "total": len(rows)}


@router.delete("/knowledge/entries/{entry_id}")
def knowledge_delete(entry_id: str, request: Request) -> dict:
    require_admin(request, csrf=True)
    rows = _read_knowledge()
    kept = [row for row in rows if row.get("id") != entry_id]
    if len(kept) == len(rows):
        raise HTTPException(404, "چنین ردیفی نیست.")
    _write_knowledge(kept)
    audit("knowledge_delete", request, target=entry_id)
    return {"ok": True, "total": len(kept)}


@router.get("/quality")
def quality(request: Request) -> dict:
    """آخرین نتیجهٔ سنجشِ کیفیت بر اساس گزارش‌های ذخیره‌شده."""
    require_admin(request)
    report_dir = os.path.join(ROOT, "reports")
    sets: dict[str, dict] = {}
    try:
        for name in sorted(os.listdir(report_dir)):
            if not (name.startswith("quality-") and name.endswith(".json")):
                continue
            key = name[len("quality-"):-len(".json")]
            try:
                with open(os.path.join(report_dir, name), encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError):
                continue
            sets[key] = {"score": data.get("score"), "passed": data.get("passed"),
                         "cases": data.get("cases"), "set": data.get("set", key)}
    except OSError:
        sets = {}
    return {"sets": sets, "reports": sorted(sets)}


@router.get("/conversations")
def conversations(request: Request, limit: int = 40) -> dict:
    """گفتگوهای تازهٔ همهٔ کاربران برای بازبینی (بدون دادهٔ حساس)."""
    require_admin(request)
    rows = store()._all(  # noqa: SLF001 - گزارشِ داخلی پنل
        "SELECT c.id, c.title, c.updated_at, u.email, c.guest_id,"
        " (SELECT COUNT(*) FROM messages m WHERE m.conv_id = c.id) AS messages"
        " FROM conversations c LEFT JOIN users u ON u.id = c.user_id"
        " ORDER BY c.updated_at DESC LIMIT ?",
        (max(1, min(int(limit), 200)),))
    return {"conversations": [dict(row) for row in rows]}


@router.get("/conversations/{conv_id}")
def conversation_detail(conv_id: str, request: Request) -> dict:
    require_admin(request)
    meta = store().get_conversation_meta(conv_id)
    if not meta:
        raise HTTPException(404, "گفتگو پیدا نشد.")
    return {"conversation": meta, "messages": store().get_messages(conv_id, limit=100)}


@router.get("/backup")
def backup(request: Request) -> dict:
    """نسخهٔ پشتیبانِ خوانا (بدون هشِ گذرواژه) برای گرفتنِ فایل."""
    require_admin(request)
    users = [{"id": u["id"], "email": u["email"], "name": u["name"], "plan": u["plan"],
              "created_at": u["created_at"]} for u in store().list_users(limit=500)]
    return {"exported_at": time.time(), "users": users,
            "knowledge": _read_knowledge(),
            "settings": store().all_settings()}


@router.post("/quality/run")
def quality_run(request: Request, set: str = "probe") -> dict:
    """اجرای واقعیِ سنجش روی همین سرور: پرسش‌ها از API خودمان پرسیده می‌شوند."""
    session = require_admin(request, csrf=True)
    allowed = {"probe", "holdout", "hard", "blind", "blind2", "blind3", "blind4", "blind5",
               "blind6", "all"}
    if set not in allowed:
        raise HTTPException(400, "مجموعهٔ نامعتبر است.")
    script = os.path.join(ROOT, "scripts", "quality_probe.py")
    if not os.path.exists(script):
        raise HTTPException(404, "سنجش نصب نیست.")
    import subprocess
    import sys

    # حسابِ مخصوصِ سنجش: سهمیهٔ روزانهٔ کاربرِ واقعی را مصرف نمی‌کند
    probe_email = "quality@rayan.local"
    probe_user = store().user_by_email(probe_email)
    if probe_user is None:
        probe_user = store().create_user(probe_email, secrets.token_urlsafe(24), "سنجش کیفیت")
    probe_id = int(probe_user["id"])
    store().set_plan(probe_id, "pro")
    store()._exec("DELETE FROM events WHERE user_id=? AND kind='chat'", (probe_id,))  # noqa: SLF001
    token = store().create_session(user_id=probe_id, user_agent="quality-run", ip="127.0.0.1")
    port = request.url.port or 8000
    base = f"http://127.0.0.1:{port}"
    report = os.path.join(ROOT, "reports", f"quality-live-{int(time.time())}.json")
    try:
        subprocess.run(
            [sys.executable, script, "--api", base, "--cookie", f"rayan_session={token}",
             "--set", set, "--json", "--delay", "0", "--write", "--out", report],
            capture_output=True, text=True, timeout=600, cwd=ROOT)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "سنجش بیش از حد طول کشید.")
    finally:
        store().delete_session(token)
    try:
        with open(report, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise HTTPException(500, "گزارشِ سنجش ساخته نشد؛ یک بار دیگر اجرا کن.")
    finally:
        try:
            os.remove(report)
        except OSError:
            pass
    audit("quality_run", request, target=set,
          detail=f"{data.get('score')}% ({data.get('passed')}/{data.get('cases')})")
    return {"set": set, "score": data.get("score"), "passed": data.get("passed"),
            "cases": data.get("cases"),
            "missed": [row.get("q") for row in data.get("rows", []) if not row.get("ok")][:20]}
