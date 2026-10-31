"""سرور وب رایان — FastAPI، مدل محلی، حساب کاربری و گفتگوهای ذخیره‌شده.

    python web/server.py --port 8000 --host 0.0.0.0

هیچ درخواستی به سرویس هوش مصنوعی بیرونی فرستاده نمی‌شود؛ مدل روی همین دستگاه
اجرا می‌شود و داده‌ها در SQLite محلی می‌مانند.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import secrets
import sys
import threading
import time
from collections import deque
from typing import Literal

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rayan.generate import MODES, Engine, polish  # noqa: E402
from rayan.text import normalize, prepare_user_input  # noqa: E402
from rayan.thinking import deep_reply  # noqa: E402
from web.store import store  # noqa: E402

STATIC_DIR = os.path.join(ROOT, "web", "static")
CHECKPOINTS = [
    os.path.join(ROOT, "checkpoints", "last.npz"),
    os.path.join(ROOT, "checkpoints", "rayan-1-small.npz"),
]
TOKENIZER_PATH = os.path.join(ROOT, "tokenizer", "rayan_bpe.json")
METRICS_PATH = os.path.join(ROOT, "logs", "metrics.jsonl")
RUN_CONFIG_PATH = os.path.join(ROOT, "configs", "training_run.json")
CORPUS_STATS_PATH = os.path.join(ROOT, "data", "corpus_stats.json")

SESSION_COOKIE = "rayan_session"
GUEST_COOKIE = "rayan_guest"
SESSION_DAYS = 30
IS_PROD = os.environ.get("RAYAN_ENV", "dev") == "prod"

STARTED = time.time()
engine: Engine | None = None
engine_error: str | None = None
sessions: dict[str, list[tuple[str, str]]] = {}
sessions_lock = threading.Lock()
request_count = 0
stats_lock = threading.Lock()

# --------------------------------------------------------------- محدودیت‌ها
LIMITS = {
    "guest": {"chat": 25, "deep": 10},
    "free": {"chat": 200, "deep": 80},
    "pro": {"chat": 3000, "deep": 1200},
}

MODELS = [
    {
        "id": "rayan-1-small",
        "name": "رایان ۱ — کوچک",
        "tagline": "مدل از صفر، روی CPU",
        "params": 6_574_848,
        "context": 256,
        "status": "ready",
        "badge": "فعال",
        "desc": "همین مدل که در حال گفتگوست: ۵ لایه، ۴ سر، آموزش‌دیده روی ۱۶٫۹ میلیون نویسهٔ فارسی.",
        "latency": "~۴۵ توکن/ثانیه",
        "strengths": ["گفتگوی کوتاه فارسی", "ادامهٔ متن", "بیت کلاسیک"],
    },
    {
        "id": "rayan-1-medium",
        "name": "رایان ۱ — متوسط",
        "tagline": "در حال آموزش",
        "params": 0,
        "context": 512,
        "status": "planned",
        "badge": "به‌زودی",
        "desc": "نسخهٔ بزرگ‌تر با ۳۰ تا ۵۰ میلیون پارامتر؛ همان پشته، دادهٔ بیشتر و زمینهٔ بلندتر.",
        "latency": "—",
        "strengths": ["جمله‌های بلندتر", "انسجام بهتر", "دانش بیشتر"],
    },
    {
        "id": "rayan-1-pro",
        "name": "رایان ۱ — حرفه‌ای",
        "tagline": "در نقشهٔ راه",
        "params": 0,
        "context": 1024,
        "status": "planned",
        "badge": "نقشهٔ راه",
        "desc": "نسخهٔ حرفه‌ای با آموزش دستوری و ارزیابی استاندارد فارسی؛ روی GPU، نه CPU.",
        "latency": "—",
        "strengths": ["پیروی از دستور", "ارزیابی استاندارد", "گفتگوی چندنوبتی"],
    },
]

SAMPLES = [
    {"mode": "chat", "title": "خودت را معرفی کن", "text": "خودت را معرفی کن"},
    {"mode": "chat", "title": "یک شعر", "text": "یک شعر بگو"},
    {"mode": "chat", "title": "دربارهٔ ایران", "text": "دربارهٔ ایران برایم بگو"},
    {"mode": "chat", "title": "پرسش فنی", "text": "مدل زبانی چیست؟"},
    {"mode": "continue", "title": "ادامهٔ متن", "text": "در دل کویر، شب‌ها آسمان پر از ستاره است و"},
    {"mode": "poetry", "title": "بیت‌سازی", "text": ""},
]

app = FastAPI(title="رایان", version="2.0.0", docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ------------------------------------------------------------------ مدل‌ها
class HistoryTurn(BaseModel):
    user: str = Field(default="", max_length=1200)
    assistant: str = Field(default="", max_length=2400)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)
    session_id: str = Field(default="default", max_length=80)
    conversation_id: str | None = Field(default=None, max_length=64)
    model: str = Field(default="rayan-1-small", max_length=40)
    mode: Literal["chat", "continue", "poetry"] = "chat"
    deep: bool = False
    candidates: int = Field(default=4, ge=2, le=6)
    temperature: float | None = Field(default=None, ge=0.1, le=1.6)
    top_p: float | None = Field(default=None, ge=0.5, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=200)
    max_new_tokens: int | None = Field(default=None, ge=16, le=220)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class RegisterRequest(BaseModel):
    name: str = Field(default="", max_length=60)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class ConversationCreate(BaseModel):
    title: str = Field(default="گفتگوی تازه", max_length=120)
    model: str = Field(default="rayan-1-small", max_length=40)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None


class FeedbackRequest(BaseModel):
    message_id: int | None = None
    value: int = Field(ge=-1, le=1)
    comment: str = Field(default="", max_length=500)


# --------------------------------------------------------------- ابزارها
def load_engine(checkpoint: str | None = None) -> Engine:
    path = checkpoint or next((p for p in CHECKPOINTS if os.path.exists(p)), "")
    if not path or not os.path.exists(path):
        raise FileNotFoundError("هیچ checkpointی پیدا نشد. ابتدا مدل را آموزش دهید.")
    return Engine(path, TOKENIZER_PATH)


def _engine() -> Engine:
    if engine is None:
        raise HTTPException(503, engine_error or "مدل هنوز بارگذاری نشده است.")
    return engine


def _clean_message(raw: str) -> str:
    cleaned = prepare_user_input(raw, limit=1200)
    if not cleaned:
        raise HTTPException(400, "متن خالی یا نامعتبر است.")
    return cleaned


def _history(session_id: str) -> list[tuple[str, str]]:
    with sessions_lock:
        return list(sessions.get(session_id, []))


def _history_for(req: ChatRequest) -> list[tuple[str, str]]:
    client = [(turn.user, turn.assistant) for turn in req.history if turn.user][-2:]
    if client:
        return client
    return _history(req.session_id)


def _remember(session_id: str, user: str, bot: str) -> None:
    with sessions_lock:
        history = sessions.setdefault(session_id, [])
        history.append((user, bot))
        del history[:-6]


def _stats(generation, prompt_ids: list[int]) -> dict:
    return {
        "prompt_tokens": len(prompt_ids),
        "tokens": len(generation.tokens),
        "seconds": round(generation.seconds, 2),
        "tokens_per_second": round(generation.tokens_per_second, 1),
        "confidence": round(generation.confidence, 3),
        "entropy": round(generation.mean_entropy, 3),
        "finish_reason": generation.finish_reason,
        "seed": generation.seed,
    }


def _read_metrics(limit: int = 400) -> dict:
    train, evals = [], []
    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("kind") == "eval":
                    evals.append(record)
                elif record.get("kind") == "train":
                    train.append(record)
    run = {}
    if os.path.exists(RUN_CONFIG_PATH):
        try:
            with open(RUN_CONFIG_PATH, encoding="utf-8") as fh:
                run = json.load(fh)
        except json.JSONDecodeError:
            run = {}
    active = False
    if os.path.exists(METRICS_PATH):
        active = (time.time() - os.path.getmtime(METRICS_PATH)) < 180
    mtime = os.path.getmtime(METRICS_PATH) if os.path.exists(METRICS_PATH) else 0
    return {
        "train": train[-limit:],
        "eval": evals[-limit:],
        "latest_eval": evals[-1] if evals else None,
        "latest_train": train[-1] if train else None,
        "best_eval": min(evals, key=lambda r: r.get("val_loss", 9e9)) if evals else None,
        "run": run,
        "active": active,
        "metrics_mtime": mtime,
    }


def _hardware() -> dict:
    cpu = platform.processor() or platform.machine()
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    mem_gb = None
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal"):
                    mem_gb = round(int(line.split()[1]) / 1024 / 1024, 1)
                    break
    except OSError:
        pass
    return {
        "cpu": cpu,
        "cores": os.cpu_count(),
        "memory_gb": mem_gb,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "os": platform.system(),
    }


def _corpus_stats() -> dict:
    if os.path.exists(CORPUS_STATS_PATH):
        try:
            with open(CORPUS_STATS_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def watcher(stop: threading.Event) -> None:
    global engine, engine_error
    while not stop.wait(20):
        try:
            if engine is None:
                engine = load_engine()
                engine_error = None
                print(f"[rayan] checkpoint appeared; loaded step={engine.meta.get('step')}", flush=True)
            elif engine.maybe_reload():
                print(f"[rayan] checkpoint reloaded at step {engine.meta.get('step')}", flush=True)
        except Exception as exc:  # pragma: no cover
            print(f"[rayan] reload skipped: {exc}", flush=True)


# ------------------------------------------------------- هویت و نشست‌ها
class RateLimiter:
    """پنجرهٔ لغزان در حافظه برای هر IP."""

    def __init__(self, per_minute: int = 45):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            bucket = self.hits.setdefault(key, deque())
            while bucket and now - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= self.per_minute:
                return False
            bucket.append(now)
            if len(self.hits) > 5000:  # جلوگیری از رشد بی‌پایان حافظه
                for k in list(self.hits)[:1000]:
                    if not self.hits[k]:
                        self.hits.pop(k, None)
            return True


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _owner(request: Request) -> dict:
    """هویت مالک گفتگو: کاربر واردشده یا مهمان با شناسهٔ کوکی."""
    user = store().session_user(request.cookies.get(SESSION_COOKIE, ""))
    if user:
        return {"user_id": user["id"], "guest_id": None, "plan": user.get("plan", "free"), "user": user}
    guest = request.cookies.get(GUEST_COOKIE, "")
    if not guest or not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", guest):
        guest = secrets.token_urlsafe(18)
    return {"user_id": None, "guest_id": guest, "plan": "guest", "user": None}


def _set_guest_cookie(response: Response, owner: dict) -> None:
    if owner.get("user_id") is None and owner.get("guest_id"):
        if _needs_guest_cookie(response, owner):
            response.set_cookie(GUEST_COOKIE, owner["guest_id"], max_age=180 * 86400,
                                httponly=True, samesite="lax", secure=IS_PROD, path="/")


def _needs_guest_cookie(_response: Response, _owner: dict) -> bool:
    return True


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_DAYS * 86400,
                        httponly=True, samesite="lax", secure=IS_PROD, path="/")


def _quota(owner: dict, ip: str, kind: str) -> tuple[int, int]:
    plan = owner.get("plan", "guest")
    limit = LIMITS.get(plan, LIMITS["guest"])[kind]
    used = store().usage_today(kind, user_id=owner.get("user_id"),
                               guest_id=owner.get("guest_id"), ip=ip)
    return used, limit


def _check_quota(owner: dict, ip: str, kind: str) -> None:
    used, limit = _quota(owner, ip, kind)
    if used >= limit:
        label = "اندیشهٔ ژرف" if kind == "deep" else "پیام"
        raise HTTPException(
            429,
            f"سهمیهٔ {label} امروز تمام شد ({used}/{limit}). "
            "با ساخت حساب رایگان سهمیهٔ بیشتری بگیرید.",
        )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'self'"
    )
    if request.url.path.startswith("/static/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def _page(name: str, status_code: int = 200) -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, name), media_type="text/html",
                        status_code=status_code)


# ------------------------------------------------------------------ صفحه‌ها
@app.get("/", response_class=HTMLResponse)
def landing() -> FileResponse:
    return _page("index.html")


@app.get("/chat", response_class=HTMLResponse)
def chat_page() -> FileResponse:
    return _page("app.html")


@app.get("/login", response_class=HTMLResponse)
def login_page() -> FileResponse:
    return _page("auth.html")


@app.get("/signup", response_class=HTMLResponse)
def signup_page() -> FileResponse:
    return _page("auth.html")


@app.get("/pricing", response_class=HTMLResponse)
def pricing_page() -> FileResponse:
    return _page("pricing.html")


@app.get("/models", response_class=HTMLResponse)
def models_page() -> FileResponse:
    return _page("models.html")


@app.get("/about", response_class=HTMLResponse)
def about_page() -> FileResponse:
    return _page("about.html")


@app.get("/docs", response_class=HTMLResponse)
def docs_page() -> FileResponse:
    return _page("docs.html")


@app.get("/s/{token}", response_class=HTMLResponse)
def shared_page(token: str) -> FileResponse:
    if store().shared_conversation(token) is None:
        raise HTTPException(404, "این گفتگوی اشتراکی پیدا نشد.")
    return _page("share.html")


@app.get("/favicon.ico")
@app.get("/favicon.svg")
def favicon() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "assets", "favicon.svg"),
                        media_type="image/svg+xml")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"),
                        media_type="application/manifest+json")


@app.get("/robots.txt")
def robots() -> Response:
    body = "User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: /sitemap.xml\n"
    return Response(body, media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap(request: Request) -> Response:
    base = os.environ.get("RAYAN_PUBLIC_URL", str(request.base_url).rstrip("/"))
    pages = ["", "chat", "pricing", "models", "about", "docs"]
    urls = "".join(f"<url><loc>{base}/{p}</loc></url>" for p in pages)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(xml, media_type="application/xml")


# ------------------------------------------------------------------- سلامت
@app.get("/api/health")
def health() -> dict:
    info = engine.info() if engine is not None else {}
    metrics = _read_metrics(limit=1)
    return {
        "ok": engine is not None,
        "error": engine_error,
        "uptime_s": round(time.time() - STARTED, 1),
        "model": {
            "params": info.get("params"),
            "step": info.get("meta", {}).get("step"),
            "val_loss": info.get("meta", {}).get("val_loss"),
            "ppl": info.get("meta", {}).get("ppl"),
        },
        "training_active": metrics["active"],
        "latest_eval": metrics["latest_eval"],
        "latest_train": metrics["latest_train"],
        "requests": request_count,
    }


@app.get("/api/model")
def model_info() -> dict:
    if engine is None:
        raise HTTPException(503, engine_error or "مدل بارگذاری نشده است.")
    info = engine.info()
    metrics = _read_metrics(limit=200)
    return {
        **info,
        "hardware": _hardware(),
        "corpus": _corpus_stats(),
        "metrics": {
            "latest_eval": metrics["latest_eval"],
            "best_eval": metrics["best_eval"],
            "train_tail": metrics["train"][-12:],
        },
        "sources": [
            {"title": "Persian News Dataset", "detail": "بیش از ۱۷۵ هزار خبر از خبرگزاری‌های ایرانی (milad-4274)"},
            {"title": "Hamshahri Corpus", "detail": "پیکرهٔ روزنامهٔ همشهری (danialfarsi)"},
            {"title": "JSON of Classic Persian Poems", "detail": "شعر کلاسیک فارسی از گنجور (namnamir)"},
            {"title": "گفتگوهای آغازین رایان", "detail": "۱۴۰ نمونهٔ دست‌نویس برای قالب گفتگو و خودشناسی"},
        ],
        "limitations": [
            "مدل فقط ۶٫۵۷ میلیون پارامتر دارد؛ با مدل‌های میلیاردپارامتری قابل مقایسه نیست.",
            "هیچ اتصال اینترنتی یا جست‌وجوی زنده ندارد و دانش آن از پیکرهٔ آموزش می‌آید.",
            "ممکن است جمله‌های نادرست یا تکراری بسازد؛ پاسخ‌ها را بررسی کنید.",
            "آموزش روی CPU و در چند ساعت انجام شده، نه با خوشهٔ GPU.",
            "«اندیشهٔ ژرف» جست‌وجوی چندمسیره و امتیازدهی است، نه تفکر آگاهانه.",
        ],
    }


@app.get("/api/models")
def models_catalog() -> dict:
    return {"models": MODELS, "default": "rayan-1-small"}


@app.get("/api/metrics")
def metrics() -> dict:
    return _read_metrics()


@app.get("/api/showcase")
def showcase() -> dict:
    path = os.path.join(ROOT, "reports", "showcase.json")
    if not os.path.exists(path):
        return {"examples": []}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError:
        return {"examples": []}
    return {"examples": data.get("examples", []), "generated_at": data.get("generated_at")}


@app.get("/api/download/checkpoint")
def download_checkpoint() -> FileResponse:
    if engine is None:
        raise HTTPException(503, "مدل بارگذاری نشده است.")
    if not os.path.exists(engine.checkpoint):
        raise HTTPException(404, "checkpoint پیدا نشد.")
    return FileResponse(engine.checkpoint, media_type="application/octet-stream",
                        filename="rayan-1-small.npz")


@app.get("/api/samples")
def samples() -> dict:
    return {"samples": SAMPLES, "modes": list(MODES.keys())}


@app.get("/api/stats")
def public_stats() -> dict:
    return {"stats": store().public_stats(), "uptime_s": round(time.time() - STARTED, 1)}


# ------------------------------------------------------------------- حساب
@app.post("/api/auth/register")
def register(req: RegisterRequest, request: Request, response: Response) -> dict:
    ip = client_ip(request)
    if not limiter.allow(f"auth:{ip}"):
        raise HTTPException(429, "تلاش‌های زیاد؛ یک دقیقه بعد دوباره امتحان کنید.")
    user = store().create_user(req.email, req.password, req.name)
    if user is None:
        raise HTTPException(409, "این ایمیل قبلاً ثبت شده است.")
    token = store().create_session(user_id=user["id"], user_agent=request.headers.get("user-agent", ""), ip=ip)
    _set_session_cookie(response, token)
    store().record_event("signup", user_id=user["id"], ip=ip)
    return {"user": user}


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response) -> dict:
    ip = client_ip(request)
    if not limiter.allow(f"auth:{ip}"):
        raise HTTPException(429, "تلاش‌های زیاد؛ یک دقیقه بعد دوباره امتحان کنید.")
    user = store().verify_user(req.email, req.password)
    if user is None:
        raise HTTPException(401, "ایمیل یا رمز عبور نادرست است.")
    token = store().create_session(user_id=user["id"], user_agent=request.headers.get("user-agent", ""), ip=ip)
    _set_session_cookie(response, token)
    store().record_event("login", user_id=user["id"], ip=ip)
    return {"user": user}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict:
    store().delete_session(request.cookies.get(SESSION_COOKIE, ""))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request) -> dict:
    owner = _owner(request)
    used_chat, limit_chat = _quota(owner, client_ip(request), "chat")
    used_deep, limit_deep = _quota(owner, client_ip(request), "deep")
    return {
        "user": owner.get("user"),
        "plan": owner.get("plan", "guest"),
        "usage": {
            "chat": {"used": used_chat, "limit": limit_chat},
            "deep": {"used": used_deep, "limit": limit_deep},
        },
    }


@app.post("/api/auth/guest")
def guest_session(request: Request, response: Response) -> dict:
    """شناسهٔ مهمان پایدار برای ذخیرهٔ گفتگو بدون ثبت‌نام."""
    owner = _owner(request)
    if owner.get("user_id") is None:
        response.set_cookie(GUEST_COOKIE, owner["guest_id"], max_age=180 * 86400,
                            httponly=True, samesite="lax", secure=IS_PROD, path="/")
    return {"guest_id": owner.get("guest_id"), "plan": owner.get("plan")}


@app.patch("/api/auth/me")
def update_me(req: ProfileRequest, request: Request) -> dict:
    owner = _owner(request)
    if not owner.get("user_id"):
        raise HTTPException(401, "برای ویرایش حساب وارد شوید.")
    store().update_user(owner["user_id"], name=req.name)
    return {"user": store().get_user(owner["user_id"])}


# --------------------------------------------------------------- گفتگوها
@app.get("/api/conversations")
def list_conversations(request: Request) -> dict:
    owner = _owner(request)
    rows = store().list_conversations(owner)
    return {"conversations": [
        {k: r[k] for k in ("id", "title", "model", "created_at", "updated_at", "pinned", "msg_count", "share_token")}
        for r in rows
    ]}


@app.post("/api/conversations")
def create_conversation(req: ConversationCreate, request: Request, response: Response) -> dict:
    owner = _owner(request)
    if owner.get("user_id") is None:
        response.set_cookie(GUEST_COOKIE, owner["guest_id"], max_age=180 * 86400,
                            httponly=True, samesite="lax", secure=IS_PROD, path="/")
    conv = store().create_conversation(owner, req.title, req.model)
    return {"conversation": conv}


@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str, request: Request) -> dict:
    owner = _owner(request)
    if not store().owns(owner, conv_id):
        raise HTTPException(404, "گفتگو پیدا نشد.")
    conv = store().get_conversation_meta(conv_id)
    assert conv is not None
    conv["messages"] = store().get_messages(conv_id)
    return {"conversation": conv}


@app.patch("/api/conversations/{conv_id}")
def patch_conversation(conv_id: str, req: ConversationPatch, request: Request) -> dict:
    owner = _owner(request)
    if not store().owns(owner, conv_id):
        raise HTTPException(404, "گفتگو پیدا نشد.")
    if req.title is not None:
        store().rename_conversation(conv_id, req.title)
    if req.pinned is not None:
        store().set_pinned(conv_id, req.pinned)
    return {"conversation": store().get_conversation_meta(conv_id)}


@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str, request: Request) -> dict:
    owner = _owner(request)
    if not store().owns(owner, conv_id):
        raise HTTPException(404, "گفتگو پیدا نشد.")
    store().delete_conversation(conv_id)
    return {"ok": True}


@app.delete("/api/conversations")
def delete_all_conversations(request: Request) -> dict:
    owner = _owner(request)
    removed = store().clear_conversations(owner)
    return {"ok": True, "removed": removed}


@app.post("/api/conversations/{conv_id}/share")
def share_conversation(conv_id: str, request: Request) -> dict:
    owner = _owner(request)
    if not store().owns(owner, conv_id):
        raise HTTPException(404, "گفتگو پیدا نشد.")
    token = store().share(conv_id)
    return {"token": token, "url": f"/s/{token}"}


@app.delete("/api/conversations/{conv_id}/share")
def unshare_conversation(conv_id: str, request: Request) -> dict:
    owner = _owner(request)
    if not store().owns(owner, conv_id):
        raise HTTPException(404, "گفتگو پیدا نشد.")
    store().unshare(conv_id)
    return {"ok": True}


@app.get("/api/share/{token}")
def get_shared(token: str) -> dict:
    conv = store().shared_conversation(token)
    if conv is None:
        raise HTTPException(404, "این گفتگوی اشتراکی پیدا نشد.")
    return {"conversation": conv}


@app.post("/api/feedback")
def feedback(req: FeedbackRequest, request: Request) -> dict:
    owner = _owner(request)
    store().add_feedback(req.message_id, req.value, owner.get("user_id"), req.comment)
    return {"ok": True}


@app.get("/api/usage")
def usage(request: Request) -> dict:
    owner = _owner(request)
    ip = client_ip(request)
    chat_used, chat_limit = _quota(owner, ip, "chat")
    deep_used, deep_limit = _quota(owner, ip, "deep")
    return {
        "plan": owner.get("plan", "guest"),
        "chat": {"used": chat_used, "limit": chat_limit},
        "deep": {"used": deep_used, "limit": deep_limit},
    }


@app.delete("/api/session/{session_id}")
def clear_session(session_id: str) -> dict:
    with sessions_lock:
        sessions.pop(session_id, None)
    return {"ok": True}


# ---------------------------------------------------------------- چت
def _generation_kwargs(req: ChatRequest) -> dict:
    kwargs = {
        "temperature": req.temperature,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "max_new_tokens": req.max_new_tokens,
    }
    return {k: v for k, v in kwargs.items() if v is not None}


def _prepare(req: ChatRequest, owner: dict, ip: str) -> tuple[Engine, str, list[tuple[str, str]], str | None]:
    if not limiter.allow(f"chat:{ip}"):
        raise HTTPException(429, "درخواست‌های پیاپی زیاد است؛ چند لحظه صبر کنید.")
    model = _engine()
    _check_quota(owner, ip, "deep" if req.deep else "chat")
    history: list[tuple[str, str]] = []
    conv_id = None
    if req.conversation_id and store().owns(owner, req.conversation_id):
        conv_id = req.conversation_id
        prior = store().get_messages(conv_id, limit=100)
        turns: list[tuple[str, str]] = []
        buf_user = None
        for msg in prior:
            if msg["role"] == "user":
                buf_user = msg["content"]
            elif msg["role"] == "assistant" and buf_user is not None:
                turns.append((buf_user, msg["content"]))
                buf_user = None
        history = turns[-2:]
    if not history and req.mode == "chat":
        history = _history_for(req)
    message = _clean_message(req.message) if req.mode != "poetry" else (normalize(req.message) or "یک شعر بگو")
    return model, message, history, conv_id


def _persist_turn(owner: dict, conv_id: str | None, message: str, answer: str,
                  stats: dict, trace: dict | None, deep: bool) -> tuple[str | None, int | None]:
    """پیام کاربر و پاسخ را ذخیره می‌کند؛ شناسهٔ گفتگو و پیام پاسخ را برمی‌گرداند."""
    title = message.strip().replace("\n", " ")[:60] or "گفتگوی تازه"
    if conv_id is None:
        conv_id = store().create_conversation(owner, title)["id"]
    store().add_message(conv_id, "user", message)
    meta = {"stats": stats, "deep": deep, "trace": trace}
    msg_id = store().add_message(conv_id, "assistant", answer, meta)
    existing = store().get_conversation_meta(conv_id)
    if existing and existing["title"] in ("گفتگوی تازه", ""):
        store().rename_conversation(conv_id, title)
    return conv_id, msg_id


def _record_usage(owner: dict, ip: str, kind: str) -> None:
    store().record_event(kind, user_id=owner.get("user_id"), guest_id=owner.get("guest_id"), ip=ip)


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request, response: Response) -> dict:
    global request_count
    owner = _owner(request)
    ip = client_ip(request)
    model, message, history, conv_id = _prepare(req, owner, ip)
    started = time.time()
    kwargs = _generation_kwargs(req)
    with model.lock:
        if req.deep:
            answer, generation, trace = deep_reply(
                model, message, mode=req.mode, history=history,
                n_candidates=req.candidates, **kwargs,
            )
            prompt_ids, _prompt = model.build_prompt(message, req.mode, history)
        else:
            answer, generation, _prompt = model.reply(
                message, mode=req.mode, history=history, seed=req.seed, **kwargs,
            )
            prompt_ids = model.tokenizer.encode(_prompt)
            trace = None
    stats = _stats(generation, prompt_ids)
    if req.mode == "chat":
        _remember(req.session_id, message, answer)
    conv_id, msg_id = _persist_turn(owner, conv_id, message, answer, stats, trace, req.deep)
    _record_usage(owner, ip, "deep" if req.deep else "chat")
    _set_guest_cookie(response, owner)
    with stats_lock:
        request_count += 1
    used, limit = _quota(owner, ip, "deep" if req.deep else "chat")
    return {
        "answer": answer,
        "mode": req.mode,
        "deep": req.deep,
        "trace": trace,
        "stats": stats,
        "latency_s": round(time.time() - started, 2),
        "session_id": req.session_id,
        "conversation_id": conv_id,
        "message_id": msg_id,
        "usage": {"used": used, "limit": limit},
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    global request_count
    owner = _owner(request)
    ip = client_ip(request)
    if req.deep:
        raise HTTPException(400, "برای اندیشهٔ ژرف از /api/chat استفاده کنید.")
    model, message, history, conv_id = _prepare(req, owner, ip)
    kwargs = _generation_kwargs(req)
    kwargs["seed"] = req.seed
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    def generate_events():
        global request_count
        with model.lock:
            ids, _prompt = model.build_prompt(message, req.mode, history)
            session = model.stream(ids, mode=req.mode, **kwargs)
            yield json.dumps({"type": "start", "prompt_tokens": len(ids)}, ensure_ascii=False) + "\n"
            try:
                for piece in session:
                    yield json.dumps({"type": "token", "text": piece}, ensure_ascii=False) + "\n"
            except Exception as exc:
                yield json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False) + "\n"
                return
            generation = session.result
            answer = polish(model.tokenizer.decode(generation.tokens), req.mode)
            if req.mode == "chat":
                _remember(req.session_id, message, answer)
            stats = _stats(generation, ids)
            new_conv, msg_id = _persist_turn(owner, conv_id, message, answer, stats, None, False)
            _record_usage(owner, ip, "chat")
            with stats_lock:
                request_count += 1
            used, limit = _quota(owner, ip, "chat")
            yield json.dumps({
                "type": "done",
                "answer": answer,
                "stats": stats,
                "conversation_id": new_conv,
                "message_id": msg_id,
                "usage": {"used": used, "limit": limit},
            }, ensure_ascii=False) + "\n"

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    response = StreamingResponse(generate_events(), media_type="application/x-ndjson", headers=headers)
    _set_guest_cookie(response, owner)
    return response


def main() -> None:
    global engine, engine_error
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    try:
        engine = load_engine(args.checkpoint or None)
        print(f"[rayan] loaded {engine.checkpoint} | step={engine.meta.get('step')} "
              f"| params={sum(p.size for p in engine.params.values()):,}", flush=True)
    except Exception as exc:
        engine_error = str(exc)
        print(f"[rayan] model not loaded: {exc}", flush=True)
    store()
    stop = threading.Event()
    if not args.no_reload:
        threading.Thread(target=watcher, args=(stop,), daemon=True).start()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
