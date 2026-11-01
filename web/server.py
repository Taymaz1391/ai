"""سرور وب رایان — FastAPI، مدل محلی، حساب کاربری و گفتگوهای ذخیره‌شده.

    python web/server.py --port 8000 --host 0.0.0.0

هیچ درخواستی به سرویس هوش مصنوعی بیرونی فرستاده نمی‌شود؛ مدل روی همین دستگاه
اجرا می‌شود و داده‌ها در SQLite محلی می‌مانند.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import signal
from collections import OrderedDict
import sys
import threading
import time
from contextlib import asynccontextmanager
from collections import deque
from typing import Literal

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, RedirectResponse,
                               StreamingResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# وقتی این فایل مستقیم اجرا می‌شود، پوشهٔ web اول sys.path است و ماژول‌های خودی
# (مثل web/locale.py) جای ماژول‌های استاندارد پایتون را می‌گیرند. ریشه را اول می‌آوریم
# و پوشهٔ خودِ اسکریپت را برمی‌داریم تا `locale` استاندارد درست پیدا شود.
_HERE = os.path.dirname(os.path.abspath(__file__))
while _HERE in sys.path:
    sys.path.remove(_HERE)
sys.path.insert(0, ROOT)

from rayan.generate import MODES, Engine, polish  # noqa: E402
from rayan.text import normalize, prepare_user_input  # noqa: E402
from rayan.thinking import deep_reply  # noqa: E402
from web.store import store  # noqa: E402
from web import admin as admin_module  # noqa: E402
from web import lang as locale_module  # noqa: E402
from web import owner as owner_module  # noqa: E402
from web import search as search_module  # noqa: E402
from web import skills as skills_module
from web import tutor as tutor_module  # noqa: E402
from web import writer as writer_module  # noqa: E402
from web import mailer as mailer_module  # noqa: E402
from web import knowledge as knowledge_module  # noqa: E402
from web import tools as tools_module  # noqa: E402
from web import security as security_module  # noqa: E402
from web import answer as answer_module  # noqa: E402
from web import guard as guard_module  # noqa: E402
from web import retrieval as retrieval_module  # noqa: E402
from web import reason as reason_module  # noqa: E402

STATIC_DIR = os.path.join(ROOT, "web", "static")
# هر checkpoint توکنایزر خودش را دارد؛ جفت‌ها به‌ترتیب اولویت آمده‌اند.
CHECKPOINT_CANDIDATES = [
    (os.path.join(ROOT, "checkpoints", "last.npz"), os.path.join(ROOT, "tokenizer", "rayan_bpe_16k.json")),
    (os.path.join(ROOT, "checkpoints", "rayan-2-base.npz"), os.path.join(ROOT, "tokenizer", "rayan_bpe_16k.json")),
    (os.path.join(ROOT, "checkpoints", "rayan-1-small.npz"), os.path.join(ROOT, "tokenizer", "rayan_bpe.json")),
]
CHECKPOINTS = [path for path, _ in CHECKPOINT_CANDIDATES]
TOKENIZER_BY_VOCAB = {16000: os.path.join(ROOT, "tokenizer", "rayan_bpe_16k.json"),
                      10000: os.path.join(ROOT, "tokenizer", "rayan_bpe.json")}
TOKENIZER_PATH = CHECKPOINT_CANDIDATES[0][1]
METRICS_CANDIDATES = [
    os.path.join(ROOT, "logs", "metrics-v2.jsonl"),
    os.path.join(ROOT, "logs", "metrics.jsonl"),
]
METRICS_PATH = next((p for p in METRICS_CANDIDATES if os.path.exists(p)), METRICS_CANDIDATES[0])
RUN_CONFIG_PATH = os.path.join(ROOT, "configs", "training_run.json")
CORPUS_STATS_PATH = os.path.join(ROOT, "data", "corpus_stats.json")

SESSION_COOKIE = "rayan_session"
GUEST_COOKIE = "rayan_guest"
# هوش فقط با حساب کاربری: هر درخواست گفتگو باید نشست ثبت‌نام‌شده داشته باشد.
REQUIRE_SIGNUP = os.environ.get("RAYAN_REQUIRE_SIGNUP", "1") != "0"
SIGNUP_GATE = ("برای استفاده از هوش رایان باید حساب بسازی. ثبت‌نام رایگان است و "
               "چند ثانیه طول می‌کشد؛ بعد از ثبت‌نام ویدیوی کوتاه آموزش را می‌بینی.")
SESSION_DAYS = 30
IS_PROD = os.environ.get("RAYAN_ENV", "dev").strip().lower() in ("prod", "production")

STARTED = time.time()
engine: Engine | None = None
engine_error: str | None = None
sessions: dict[str, list[tuple[str, str]]] = {}
sessions_lock = threading.Lock()
request_count = 0
stats_lock = threading.Lock()

# ------------------------------------------------------------------ میزان تأخیر
# تأخیر واقعیِ همین سرویس برای صفحهٔ «میزان»؛ پنجرهٔ لغزان تا حافظه رشد نکند.
_LATENCY_WINDOW = int(os.environ.get("RAYAN_LATENCY_WINDOW", "500"))
_recent_latencies: deque = deque(maxlen=_LATENCY_WINDOW)
_recent_times: deque = deque(maxlen=_LATENCY_WINDOW)
_latency_lock = threading.Lock()


def _note_latency(seconds: float | None) -> None:
    """هر پاسخ واقعیِ کاربر یک نمونه است؛ هیچ عددی دستی نوشته نمی‌شود."""
    if seconds is None or seconds < 0:
        return
    with _latency_lock:
        _recent_latencies.append(round(float(seconds), 3))
        _recent_times.append(time.time())

# --------------------------------------------------------------- محدودیت‌ها
LIMITS = {
    "guest": {"chat": 25, "deep": 10},
    "free": {"chat": 200, "deep": 80},
    "pro": {"chat": 3000, "deep": 1200},
}

# مدل‌های آرشیوی/آینده ثابت‌اند؛ مدل فعالِ فهرست از خودِ checkpoint ساخته می‌شود
# تا هیچ پارامتر یا عددی در متن سایت دستی نوشته نشود.
ARCHIVE_MODELS = [
    {
        "id": "rayan-1-small",
        "name": "رایان ۱ — کوچک",
        "tagline": "نسخهٔ قبلی، بازنشسته",
        "params": 6_574_848,
        "context": 256,
        "status": "archived",
        "badge": "قبلی",
        "desc": "مدل اول پروژه: ۵ لایه، ۴ سر و واژگان ۱۰هزارتایی. با توکنایزر قدیمی آموزش دید و دیگر پیش‌فرض سایت نیست.",
        "latency": "—",
        "strengths": ["گفتگوی کوتاه فارسی", "ادامهٔ متن", "بیت کلاسیک"],
    },
    {
        "id": "rayan-3",
        "name": "رایان ۳",
        "tagline": "در نقشهٔ راه",
        "params": 0,
        "context": 1024,
        "status": "planned",
        "badge": "نقشهٔ راه",
        "desc": "نسخهٔ بعدی با آموزش دستوری و ارزیابی استاندارد فارسی؛ روی GPU، نه CPU.",
        "latency": "—",
        "strengths": ["پیروی از دستور", "ارزیابی استاندارد", "گفتگوی چندنوبتی"],
    },
]


def _run_config() -> dict:
    try:
        with open(RUN_CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _fa_number(value: float, digits: int = 1) -> str:
    """عدد با جداکنندهٔ هزارگان و ارقام فارسی."""
    text = f"{value:,.{digits}f}".replace(",", "٬")
    return text.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _active_params() -> int:
    """شمار پارامترهای مدلِ بارگذاری‌شده (۰ اگر هنوز نیامده)."""
    info = engine.info() if engine is not None else {}
    return int(info.get("params") or 0)


def _run_config_for_active() -> dict:
    """تنظیمات اجرا فقط اگر به همان مدلی تعلق داشته باشد که در حال گفتگوست.

    گزارش‌های آموزشِ یک اجرای دیگر (مثلاً پایهٔ بزرگ‌تر) نباید روی کارت مدلِ
    فعال بنشینند؛ عدد بی‌ربط، عدد نادرست است.
    """
    run = _run_config()
    if not run:
        return {}
    owned = int(run.get("params") or 0)
    active = _active_params()
    if owned and active and owned != active:
        return {}
    return run


def active_model_card() -> dict:
    """کارت مدل فعال، مستقیم از checkpoint و تنظیمات اجرای همان مدل."""
    run = _run_config_for_active()
    info = engine.info() if engine is not None else {}
    meta = info.get("meta") or {}
    cfg = (info.get("config") or {})
    params = info.get("params") or run.get("params") or 0
    layers = cfg.get("n_layer") or run.get("layers")
    heads = cfg.get("n_head") or run.get("heads")
    embed = cfg.get("n_embd") or run.get("embed")
    vocab = cfg.get("vocab_size") or run.get("vocab")
    tokens_seen = run.get("tokens_seen")
    val_loss = run.get("val_loss") or (info.get("meta") or {}).get("val_loss")
    bpc = run.get("bits_per_char") or (info.get("meta") or {}).get("bits_per_char")
    stage_labels = {"sft": "تنظیم دستورمحور", "dpo": "بهینه‌سازی ترجیح",
                    "base": "پیش‌آموزش"}
    parts = []
    if meta.get("stage"):
        parts.append(f"مرحلهٔ {stage_labels.get(meta['stage'], meta['stage'])}")
    if layers and heads and embed:
        parts.append(f"{_fa_number(layers, 0)} لایه، {_fa_number(heads, 0)} سر، بُعد {_fa_number(embed, 0)}")
    if params:
        parts.append(f"{_fa_number(params / 1e6)} میلیون پارامتر")
    if vocab:
        parts.append(f"واژگان {_fa_number(vocab, 0)}")
    if tokens_seen:
        parts.append(f"آموزش روی {_fa_number(tokens_seen / 1e6)} میلیون توکن")
    desc = "همین مدل که در حال گفتگوست: " + "، ".join(parts) + "."
    if bpc:
        desc += f" خطای نگه‌داشته {_fa_number(bpc, 3)} بیت بر نویسه است."
    return {
        "id": run.get("id") or "active",
        "name": info.get("name") or run.get("name") or "رایان",
        "tagline": "مدل از صفر، روی CPU",
        "params": params,
        "context": cfg.get("block_size") or run.get("block_size") or 256,
        "status": "ready" if engine is not None else "loading",
        "badge": "فعال" if engine is not None else "در حال بارگذاری",
        "desc": desc,
        "checkpoint": os.path.relpath(engine.checkpoint, ROOT) if engine is not None else None,
        "metrics": {"val_loss": val_loss, "bits_per_char": bpc, "ppl": run.get("ppl"),
                    "chat_ppl": meta.get("chat_ppl"),
                    "rubric_mean": meta.get("rubric_mean")},
        "latency": (f"~{_fa_number(run['inference_tokens_per_second'], 0)} توکن/ثانیه"
                    if run.get("inference_tokens_per_second") else "—"),
        "strengths": ["گفتگوی کوتاه فارسی", "ادامهٔ متن", "بیت کلاسیک"],
    }


SAMPLES = [
    {"mode": "chat", "title": "پایتخت ایران", "text": "پایتخت ایران کجاست؟"},
    {"mode": "chat", "title": "بلندترین قله", "text": "بلندترین قلهٔ ایران کجاست؟"},
    {"mode": "chat", "title": "طولانی‌ترین رود", "text": "طولانی‌ترین رودخانهٔ جهان کدام است؟"},
    {"mode": "chat", "title": "دربارهٔ خودت", "text": "خودت را معرفی کن"},
    {"mode": "continue", "title": "ادامهٔ متن", "text": "در دل کویر، شب‌ها آسمان پر از ستاره است و"},
    {"mode": "poetry", "title": "بیت‌سازی", "text": ""},
]

_SHUTDOWN = threading.Event()
_BOOT_LOCK = threading.Lock()
_BOOTED = {"done": False}


def boot() -> None:
    """آماده‌سازی سرور بدون توجه به این‌که با uvicorn یا `python -m web.server` بالا بیاید."""
    with _BOOT_LOCK:
        if _BOOTED["done"]:
            return
        _BOOTED["done"] = True
    global engine, engine_error
    try:
        store()
    except Exception as exc:  # pragma: no cover
        print(f"[rayan] store init failed: {exc}", flush=True)
    try:
        admin_module.admin_credentials()
        admin_module.start_scheduler()
        # حساب مالک همیشه هست: بعد از هر به‌روزرسانی یا پایگاه‌دادهٔ تازه،
        # ورودِ مدیر بی‌درنگ کار می‌کند و پنل مدیریت ۴۰۴ نمی‌شود.
        owner_module.credentials()
        admin_module._ensure_admin_user("owner@rayan.local")  # noqa: SLF001
    except Exception as exc:  # pragma: no cover
        print(f"[rayan] admin bootstrap skipped: {exc}", flush=True)
    if engine is None:
        def _load() -> None:
            global engine, engine_error
            try:
                engine = load_engine()
                engine_error = None
                print(f"[rayan] loaded {engine.checkpoint} | step={engine.meta.get('step')}", flush=True)
            except Exception as exc:
                engine_error = str(exc)
                print(f"[rayan] model not loaded: {exc}", flush=True)

        threading.Thread(target=_load, name="rayan-loader", daemon=True).start()
    if os.environ.get("RAYAN_WATCH", "1") != "0":
        threading.Thread(target=watcher, args=(_SHUTDOWN,), name="rayan-watch", daemon=True).start()
    # کارگر تقویت تدریجی: پرسش‌های بی‌جواب را از وب یاد می‌گیرد و دانش را می‌گستراند
    try:
        from web import learn as learn_module
        learn_module.start_worker(interval=float(os.environ.get("RAYAN_GROW_INTERVAL", "240")))
    except Exception as exc:  # pragma: no cover
        print(f"[rayan] learn worker skipped: {exc}", flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    boot()
    try:
        yield
    finally:
        _SHUTDOWN.set()


app = FastAPI(title="رایان", version="3.0.0", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
_PUBLIC_ORIGINS = {o.strip() for o in os.environ.get("RAYAN_ORIGINS", "").split(",") if o.strip()}
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_PUBLIC_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-RayAn-CSRF", "x-rayan-csrf", "X-API-Key", "Authorization", "X-Admin-Key"],
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
    web: bool = False


class HumanEvidence(BaseModel):
    """شواهد رفتاری مرورگر برای «من ربات نیستم»؛ همه اختیاری‌اند."""
    moves: int = Field(default=0, ge=0, le=100000)
    keys: int = Field(default=0, ge=0, le=100000)
    elapsed_ms: int = Field(default=0, ge=0, le=3600000)
    honeypot: str = Field(default="", max_length=120)
    webdriver: bool = False


class HumanProof(BaseModel):
    token: str = Field(min_length=20, max_length=300)
    nonce: str = Field(min_length=1, max_length=24)
    evidence: HumanEvidence | None = None


class RegisterRequest(BaseModel):
    name: str = Field(default="", max_length=60)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    captcha: HumanProof | None = None


class VerificationConfirm(BaseModel):
    code: str = Field(min_length=4, max_length=8)


class LoginRequest(BaseModel):
    """ورود با ایمیل یا نام کاربری. فیلد ``identifier`` تازه است و ``email``
    برای سازگاری با کلاینت‌های قدیمی پذیرفته می‌شود."""
    email: str | None = Field(default=None, max_length=160)
    identifier: str | None = Field(default=None, max_length=160)
    password: str = Field(min_length=1, max_length=128)
    captcha: HumanProof | None = None


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class PasswordChange(BaseModel):
    """تغییر گذرواژه از پنل تنظیمات؛ گذرواژهٔ کنونی الزامی است."""
    current: str = Field(min_length=1, max_length=128)
    new: str = Field(min_length=8, max_length=128)


class ConversationCreate(BaseModel):
    title: str = Field(default="گفتگوی تازه", max_length=120)
    model: str = Field(default="rayan-1-small", max_length=40)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    pinned: bool | None = None


class SupportRequest(BaseModel):
    name: str = Field(default="", max_length=80)
    email: EmailStr
    plan: Literal["pro", "team", "enterprise"] = "pro"
    topic: str = Field(default="", max_length=80)
    message: str = Field(min_length=10, max_length=2000)


class FeedbackRequest(BaseModel):
    message_id: int | None = None
    value: int = Field(ge=-1, le=1)
    comment: str = Field(default="", max_length=500)


# --------------------------------------------------------------- ابزارها
def checkpoint_vocab(path: str) -> int:
    """اندازهٔ واژگان را از سرصفحهٔ checkpoint می‌خواند، بدون بارگذاری وزن‌ها."""
    try:
        with np.load(path, allow_pickle=False) as data:
            return int(json.loads(str(data["__config__"]))["vocab_size"])
    except Exception:
        return 0


def active_pair() -> tuple[str, str]:
    """اولین جفت (checkpoint، توکنایزر) موجود؛ توکنایزر همیشه با checkpoint هم‌واژگان است.

    مدل منتشرشده با انتخاب مرحلهٔ هم‌ترازسازی عوض می‌شود و ممکن است واژگان
    متفاوتی داشته باشد؛ پس توکنایزر از روی واژگان خودِ checkpoint برداشته
    می‌شود، نه از ترتیب ثابت فهرست.
    """
    for path, tokenizer in CHECKPOINT_CANDIDATES:
        if os.path.exists(path):
            vocab = checkpoint_vocab(path)
            return path, TOKENIZER_BY_VOCAB.get(vocab, tokenizer)
    return "", TOKENIZER_PATH


def load_engine(checkpoint: str | None = None) -> Engine:
    if checkpoint:
        if not os.path.exists(checkpoint):
            raise FileNotFoundError(f"checkpoint پیدا نشد: {checkpoint}")
        tokenizer = TOKENIZER_BY_VOCAB.get(checkpoint_vocab(checkpoint), TOKENIZER_PATH)
        return Engine(checkpoint, tokenizer)
    path, tokenizer = active_pair()
    if not path:
        raise FileNotFoundError("هیچ checkpointی پیدا نشد. ابتدا مدل را آموزش دهید.")
    return Engine(path, tokenizer)


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
    """پنجرهٔ لغزان در حافظه برای هر IP.

    سقفِ پیش‌فرض ۴۵ درخواست در دقیقه است و با ``RAYAN_RATE_PER_MINUTE`` برای
    آزمونِ بار و سنجشِ کیفیت قابل تنظیم است (بدونِ دست‌زدن به سقفِ کاربرِ واقعی).
    """

    def __init__(self, per_minute: int | None = None):
        if per_minute is None:
            per_minute = int(os.environ.get("RAYAN_RATE_PER_MINUTE", "45") or 45)
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

# حداکثر تولید هم‌زمان؛ درخواست‌های بیشتر به‌جای صف بی‌پایان ۵۰۳ می‌گیرند.
MAX_CONCURRENCY = max(1, int(os.environ.get("RAYAN_MAX_CONCURRENCY", "4")))
_generation_slots = threading.BoundedSemaphore(MAX_CONCURRENCY)
_queue_depth = {"value": 0}
_queue_lock = threading.Lock()


def _acquire_slot(wait: float = 6.0) -> bool:
    """جای تولید می‌گیرد؛ اگر صف پر باشد False."""
    with _queue_lock:
        _queue_depth["value"] += 1
    try:
        return _generation_slots.acquire(timeout=wait)
    finally:
        with _queue_lock:
            _queue_depth["value"] = max(0, _queue_depth["value"] - 1)


def _release_slot() -> None:
    try:
        _generation_slots.release()
    except ValueError:  # pragma: no cover - آزادسازی تکراری
        pass


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _owner(request: Request) -> dict:
    """هویت مالک گفتگو: کاربر وارد‌شده یا مهمان با شناسهٔ کوکی.

    کلید API و توکن Bearer وجود ندارند: هوش فقط از داخل همین سایت در دسترس است.
    """
    user = store().session_user(request.cookies.get(SESSION_COOKIE, ""))
    if user:
        return {"user_id": user["id"], "guest_id": None, "plan": user.get("plan", "free"), "user": user}
    guest = request.cookies.get(GUEST_COOKIE, "")
    valid_guest = bool(guest and re.fullmatch(r"[A-Za-z0-9_-]{16,64}", guest))
    if not valid_guest:
        guest = secrets.token_urlsafe(18)
    return {"user_id": None, "guest_id": guest, "plan": "guest", "user": None,
            "guest_cookie": valid_guest}


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


def _flag(name: str, default: str = "1") -> bool:
    return store().setting(name, default) == "1"


def _require_account(owner: dict) -> None:
    """هیچ درخواست هوشی بدون حساب کاربری پاسخ نمی‌گیرد (بدون کلید و بدون مهمان)."""
    if owner.get("user_id") is not None:
        return
    if not REQUIRE_SIGNUP:
        return
    raise HTTPException(401, detail=SIGNUP_GATE, headers={"X-Rayan-Need": "signup"})


def _guard_flags(kind: str | None = None, signup: bool = False, deep: bool = False) -> None:
    if _flag("maintenance", "0"):
        raise HTTPException(503, "سرویس در حال به‌روزرسانی است؛ چند دقیقهٔ دیگر برگردید.")
    if signup and not _flag("signup_open"):
        raise HTTPException(403, "ثبت‌نام موقتاً بسته است.")
    if deep and not _flag("deep_enabled"):
        raise HTTPException(403, "اندیشهٔ ژرف موقتاً خاموش است.")


WEAK_PASSWORDS = {"password", "12345678", "123456789", "qwertyui", "iloveyou",
                  "admin123", "welcome1", "passw0rd", "1234567890", "abc12345"}


HUMAN_ERRORS = {
    "honeypot": "درخواست خودکار تشخیص داده شد؛ صفحه را تازه کنید.",
    "automation": "مرورگر خودکار اجازهٔ ساخت حساب ندارد.",
    "too_fast": "فرم بسیار سریع پر شد؛ یک لحظه صبر کنید و دوباره بزنید.",
    "no_interaction": "تعامل انسانی دیده نشد؛ کادر «من ربات نیستم» را دوباره تأیید کنید.",
    "invalid_proof": "تأیید «من ربات نیستم» منقضی شده است؛ دوباره تأیید کنید.",
}


def _require_human(proof: HumanProof | None, request: Request, ip: str) -> None:
    """«من ربات نیستم» اجباری و سرور-محور: امضا، اثر انگشت، شواهد رفتاری، مصرف یک‌باره."""
    if not security_module.captcha_limiter.allow(f"human:{ip}", cost=1):
        retry = security_module.captcha_limiter.retry_after(f"human:{ip}")
        raise HTTPException(429, f"تلاش‌های زیاد؛ {retry} ثانیهٔ دیگر دوباره امتحان کنید.")
    if proof is None:
        raise HTTPException(400, "تأیید «من ربات نیستم» لازم است؛ صفحه را تازه کنید و دوباره تلاش کنید.")
    fp = security_module.fingerprint(ip, request.headers.get("user-agent", ""))
    evidence = proof.evidence.model_dump() if proof.evidence else None
    ok, reason = security_module.human.assess(proof.token, proof.nonce, evidence, fp)
    if not ok:
        security_module.human.note_failure(fp)
        security_module.captcha_limiter.allow(f"fail:{ip}", cost=1)
        raise HTTPException(400, HUMAN_ERRORS.get(reason, HUMAN_ERRORS["invalid_proof"]))


def _check_password(password: str) -> None:
    weak = password.lower() in WEAK_PASSWORDS
    if weak or len(set(password)) < 4:
        raise HTTPException(400, "گذرواژهٔ ساده است؛ ترکیبی از حرف و رقم با تنوع بیشتر بگذارید.")


def _check_quota(owner: dict, ip: str, kind: str) -> None:
    used, limit = _quota(owner, ip, kind)
    if used >= limit:
        label = "اندیشهٔ ژرف" if kind == "deep" else "پیام"
        raise HTTPException(
            429,
            f"سهمیهٔ {label} امروز تمام شد ({used}/{limit}). "
            "با ساخت حساب رایگان سهمیهٔ بیشتری بگیرید.",
        )


MUTATING = {"POST", "PATCH", "DELETE", "PUT"}


@app.middleware("http")
async def origin_guard(request: Request, call_next):
    """درخواست‌های تغییردهنده فقط از همین دامنه پذیرفته می‌شوند."""
    if request.method in MUTATING and not request.url.path.startswith("/api/admin"):
        origin = request.headers.get("origin")
        if origin:
            host = request.headers.get("host", "")
            host_name = host.split(":")[0]
            allowed = {f"https://{host}", f"http://{host}", f"https://{host_name}", f"http://{host_name}"}
            allowed.update(_PUBLIC_ORIGINS)
            if origin.rstrip("/") not in {a.rstrip("/") for a in allowed}:
                return JSONResponse({"detail": "مبدأ درخواست مجاز نیست."}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def body_limit(request: Request, call_next):
    """سقف حجم بدنه؛ درخواست بزرگ پیش از خواندن رد می‌شود."""
    raw = request.headers.get("content-length")
    limit = 512 * 1024 if request.url.path.startswith("/api/") else 2 * 1024 * 1024
    if raw and raw.isdigit() and int(raw) > limit:
        return JSONResponse({"detail": "حجم درخواست بیش از حد مجاز است."}, status_code=413)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    # پاسخ‌های حساب و پیکربندی هرگز نباید از کش مرورگر بیایند؛ وگرنه کاربر
    # پس از ساخت حساب همچنان «مهمان» دیده می‌شود.
    if path.startswith(("/api/auth", "/api/admin", "/api/me", "/api/config", "/api/health")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(self), geolocation=(), payment=(), usb=(), browsing-topics=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; "
        "connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
    )
    if IS_PROD:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if path.startswith("/static/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.startswith("/api/"):
        if "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
    elif path in ("/sw.js", "/manifest.webmanifest") or path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "no-cache"

    # هر بازدیدکنندهٔ صفحه، شناسهٔ مهمان امضاشده می‌گیرد تا گفتگو از خودِ سایت
    # ممکن باشد و فراخوانی مستقیم API بدون هویت رد شود.
    ctype = response.headers.get("content-type", "")
    if (ctype.startswith("text/html") and "rayan_guest" not in request.cookies
            and SESSION_COOKIE not in request.cookies):
        response.set_cookie(GUEST_COOKIE, secrets.token_urlsafe(18), max_age=180 * 86400,
                            httponly=True, samesite="lax", secure=IS_PROD, path="/")
    return response


# --------------------------------------------------------------- سد تهاجم
_CHAT_PATHS = ("/api/chat", "/api/chat/stream", "/api/search")


@app.middleware("http")
async def attack_filter(request: Request, call_next):
    """فیلتر حمله‌های رایج: تراورسال، تزریق، اسکن‌گر و بستن موقت IP پرخطر."""
    ip = client_ip(request)
    wait = guard_module.strikes.banned(ip)
    if wait:
        return JSONResponse(
            {"detail": f"دسترسی این نشانی موقتاً بسته است؛ {wait} ثانیهٔ دیگر تلاش کنید."},
            status_code=403, headers={"Retry-After": str(wait), "x-rayan-guard": "banned"},
        )

    path = request.url.path
    verdict = guard_module.screen(path=path, query=request.url.query,
                                  user_agent=request.headers.get("user-agent", ""),
                                  method=request.method)
    if not verdict.blocked and request.method in MUTATING and path not in _CHAT_PATHS:
        raw = await request.body()
        if raw:
            try:
                text = raw.decode("utf-8", "replace")
            except Exception:  # pragma: no cover
                text = ""
            verdict = guard_module.screen(path=path, query=request.url.query, body=text,
                                          user_agent=request.headers.get("user-agent", ""),
                                          method=request.method)
    if verdict.blocked:
        banned, wait = guard_module.strikes.hit(ip, verdict.score or 1)
        guard_module.log_event(ip, path, request.method, verdict,
                               request.headers.get("user-agent", ""), 403)
        detail = verdict.detail or "درخواست به‌دلیل الگوی ناامن مسدود شد."
        if banned:
            detail = f"تلاش‌های ناامن تکرار شد؛ دسترسی این نشانی {wait // 60 or 1} دقیقه بسته شد."
        return JSONResponse({"detail": detail, "code": "blocked_by_guard", "rule": verdict.rule},
                            status_code=403, headers={"x-rayan-guard": verdict.rule})
    return await call_next(request)


def _page(name: str, status_code: int = 200) -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, name), media_type="text/html",
                        status_code=status_code)


# ------------------------------------------------------------------ صفحه‌ها
def _with_lang_cookie(response: Response, request: Request) -> Response:
    """انتخاب دستی زبان را در کوکی نگه می‌دارد تا دفعهٔ بعد هم بماند."""
    lang = (request.query_params.get("lang") or "").lower()
    if lang in locale_module.LANGS:
        response.set_cookie("rayan_lang", lang, max_age=365 * 24 * 3600,
                            samesite="lax", path="/")
    return response


@app.get("/")
def landing(request: Request):
    # سایت تک‌زبانه است: همیشه فارسی و راست‌چین
    return _with_lang_cookie(_page("index.html"), request)


@app.get("/api/locale")
def api_locale(request: Request) -> dict:
    """زبان، جهت و نسخهٔ ویدیوی پیشنهادی برای این بازدیدکننده."""
    return locale_module.detect(request)


@app.get("/chat", response_class=HTMLResponse)
def chat_page() -> FileResponse:
    return _page("app.html")


@app.get("/login", response_class=HTMLResponse)
def login_page() -> FileResponse:
    return _page("auth.html")


@app.get("/auth", include_in_schema=False)
def auth_alias() -> RedirectResponse:
    """نشانیِ کوتاهِ ورود: هر کس /auth را بزند به فرم ورود می‌رسد، نه ۴۰۴."""
    return RedirectResponse("/login", status_code=307)


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


@app.get("/compare", response_class=HTMLResponse)
def compare_page() -> FileResponse:
    """میزانِ رایان: سرعت و دقت سنجیده‌شده، در برابر دیگر دستیارها."""
    return _page("compare.html")


# صفحه‌های «پشت صحنه» بسته شده‌اند: هیچ سند، کد، بستهٔ نصب یا منبعی منتشر نمی‌شود.
_CLOSED = ("/course", "/docs", "/download", "/summary", "/developer", "/install")


@app.get("/en")
@app.get("/en/course")
@app.get("/en/docs")
def english_removed() -> RedirectResponse:
    """نسخهٔ انگلیسی حذف شده است؛ همه‌چیز فارسی و راست‌چین است."""
    return RedirectResponse("/", status_code=302)


@app.get("/course")
@app.get("/docs")
@app.get("/download")
@app.get("/summary")
@app.get("/developer")
@app.get("/install")
def closed_pages() -> RedirectResponse:
    """این بخش‌ها عمداً وجود ندارند؛ بازدیدکنندهٔ قدیمی به خانه برمی‌گردد."""
    return RedirectResponse("/", status_code=302)


@app.get("/academy")
def academy_removed() -> RedirectResponse:
    """آکادمی حذف شده است؛ بازدیدکنندهٔ قدیمی به خانه برمی‌گردد."""
    return RedirectResponse("/", status_code=302)


@app.get("/support", response_class=HTMLResponse)
def support_page() -> FileResponse:
    return _page("support.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> FileResponse:
    """پوستهٔ ورود مدیر؛ هیچ داده‌ای پیش از ورود در آن نیست."""
    res = _page("admin.html")
    res.headers["X-Robots-Tag"] = "noindex, nofollow"
    res.headers["Cache-Control"] = "no-store"
    return res


@app.get("/settings", response_class=HTMLResponse)
def settings_page() -> FileResponse:
    res = _page("settings.html")
    res.headers["Cache-Control"] = "no-store"
    return res


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page() -> FileResponse:
    return _page("about.html")


@app.get("/offline", response_class=HTMLResponse)
def offline_page() -> FileResponse:
    return _page("offline.html")


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
    body = ("User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin\n"
            "Sitemap: /sitemap.xml\n")
    return Response(body, media_type="text/plain")


@app.get("/sitemap.xml")
def sitemap(request: Request) -> Response:
    base = os.environ.get("RAYAN_PUBLIC_URL", str(request.base_url).rstrip("/"))
    pages = ["", "chat", "pricing", "models", "about", "docs", "course", "download",
             "summary", "developer", "support"]
    urls = "".join(f"<url><loc>{base}/{p}</loc></url>" for p in pages)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(xml, media_type="application/xml")


# ------------------------------------------------------------------- سلامت
@app.get("/api/captcha")
def api_captcha(request: Request) -> dict:
    """چالش «من ربات نیستم»؛ بدون هیچ سرویس بیرونی."""
    ip = client_ip(request)
    if not security_module.captcha_limiter.allow(f"issue:{ip}"):
        raise HTTPException(429, "درخواست چالش زیاد است؛ یک دقیقه بعد دوباره تلاش کنید.")
    fp = security_module.fingerprint(ip, request.headers.get("user-agent", ""))
    challenge = security_module.human.issue(fp, bonus=security_module.human.difficulty_bonus(fp))
    challenge["required"] = ["sha256-proof", "browser-evidence", "same-origin"]
    return challenge


@app.post("/api/support")
def api_support(req: SupportRequest, request: Request) -> dict:
    ip = client_ip(request)
    if not limiter.allow(f"support:{ip}"):
        raise HTTPException(429, "درخواست‌های زیاد؛ یک دقیقه بعد دوباره تلاش کنید.")
    owner = _owner(request)
    rid = store().add_support_request(req.name, req.email, req.plan, req.topic, req.message,
                                     owner.get("user_id"), ip)
    store().record_event("support", user_id=owner.get("user_id"), ip=ip)
    return {"ok": True, "id": rid,
            "note": "درخواست ثبت شد؛ پاسخ در ۱ روز کاری روی همان ایمیل می‌آید."}


@app.get("/api/health")
def health() -> dict:
    """وضعیت عمومی: فقط «آماده است یا نه»؛ هیچ مسیر، فایل یا جزئیات داخلی بیرون نمی‌رود."""
    return {"ok": engine is not None, "ready": engine is not None,
            "uptime_s": round(time.time() - STARTED, 1),
            "signup_required": REQUIRE_SIGNUP}


@app.get("/api/health/detail")
def health_detail(request: Request) -> dict:
    """همان وضعیت، کامل — فقط برای مدیر."""
    admin_module.require_admin(request)
    info = engine.info() if engine is not None else {}
    meta = info.get("meta") or {}
    metrics = _read_metrics(limit=1)
    return {
        "ok": engine is not None, "error": engine_error,
        "uptime_s": round(time.time() - STARTED, 1),
        "model": {"params": info.get("params"), "stage": meta.get("stage"),
                  "step": meta.get("step")},
        "training_active": metrics["active"],
        "index": retrieval_module.stats(),
        "learned": _learn_stats(),
        "qa": _qa_report(),
        "latency": _speed_summary(),
    }


def _learn_stats() -> dict:
    """آمار دانشِ خوانده‌شده از وب (لایهٔ آنلاین)."""
    try:
        from web import learn as learn_module
        return learn_module.stats()
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "error": str(exc)}


def _qa_report() -> dict | None:
    """نتیجهٔ سنجش صادقانهٔ پرسش‌های دانشی (scripts/eval_qa.py) — بدون دست‌کاری.

    اگر ایندکس دانش روی این ماشین ساخته نشده باشد، عدد گزارش مربوط به اجرای دیگری
    است و تکرارپذیر نیست؛ در آن حالت سنجه نشان داده نمی‌شود تا عدد کهنه جای واقعیت
    ننشیند.
    """
    path = os.path.join(ROOT, "reports", "qa.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    try:
        ready = bool(retrieval_module.stats().get("ready"))
    except Exception:  # noqa: BLE001
        ready = False
    if not ready:
        return {"available": False,
                "note": "ایندکس دانش روی این ماشین ساخته نشده؛ عدد گزارش تکرارپذیر نیست."}
    return {
        "available": True,
        "run_at": data.get("run_at"),
        "total": data.get("total"),
        "correct": data.get("correct"),
        "answered": data.get("answered"),
        "accuracy_on_all": data.get("accuracy_on_all"),
        "accuracy_on_answered": data.get("accuracy_on_answered"),
    }


def _final_eval() -> dict | None:
    """سنجه‌های کاملِ اعتبارسنجی از اجرای منتشرشده (finalize_run)."""
    run = _run_config_for_active()
    if not run or run.get("val_loss") is None:
        return None
    return {
        "step": run.get("steps"),
        "val_loss": run.get("val_loss"),
        "ppl": run.get("ppl"),
        "bits_per_char": run.get("bits_per_char"),
        "tokens": run.get("tokens_seen"),
        "scope": "full_validation",
    }


def _source_cards() -> list[dict]:
    """کارت منابع پیکره از آمار واقعی ادغام، نه فهرست دستی."""
    stats = _corpus_stats()
    sources = stats.get("sources") or {}
    titles = {
        "train-v1.txt": "پیکرهٔ اول رایان",
        "wiki.txt": "ویکی‌پدیای فارسی",
        "mizan_fa.txt": "کتاب‌های فارسی (میزان)",
        "normalized": "شعر کلاسیک فارسی",
        "miras-sample.txt": "نمونهٔ متون میراث",
    }
    cards = []
    for name, info in sources.items():
        chars = int(info.get("chars") or 0)
        cards.append({
            "title": titles.get(name, name),
            "detail": f"{_fa_number(info.get('docs') or 0, 0)} سند، {_fa_number(chars / 1e6)} میلیون نویسه",
            "chars": chars,
            "docs": int(info.get("docs") or 0),
        })
    cards.sort(key=lambda c: -c["chars"])
    return cards


def _limitations(params: int) -> list[str]:
    items = []
    if params:
        items.append(
            f"مدل {_fa_number(params / 1e6)} میلیون پارامتر دارد؛ با مدل‌های میلیاردپارامتری قابل مقایسه نیست."
        )
    items.extend([
        "هیچ اتصال اینترنتی یا جست‌وجوی زنده ندارد و دانش آن از پیکرهٔ آموزش می‌آید.",
        "ممکن است جمله‌های نادرست یا تکراری بسازد؛ پاسخ‌ها را بررسی کنید.",
        "آموزش روی CPU انجام شده، نه با خوشهٔ GPU.",
        "«اندیشهٔ ژرف» جست‌وجوی چندمسیره و امتیازدهی است، نه تفکر آگاهانه.",
    ])
    return items


@app.get("/api/model")
def model_info() -> dict:
    """کارت عمومی: چه کاری می‌کند، نه چطور ساخته شده."""
    if engine is None:
        raise HTTPException(503, "سرویس در حال آماده‌سازی است.")
    abilities = [
        "پاسخ دانشی به فارسی",
        "نوشتن و بازنویسی متن",
        "محاسبهٔ دقیق و تاریخ شمسی",
        "پاسخ از وب با منبع (کلید وب)",
        "اندیشهٔ ژرف برای پرسش‌های چندلایه",
    ]
    return {"name": "رایان", "version": "3.0.0", "status": "ready",
            "abilities": abilities, "languages": ["fa"],
            "note": "برای دیدن جزئیات فنی، دسترسی مدیر لازم است."}


@app.get("/api/model/detail")
def model_detail(request: Request) -> dict:
    admin_module.require_admin(request)
    if engine is None:
        raise HTTPException(503, engine_error or "مدل بارگذاری نشده است.")
    info = engine.info()
    metrics = _read_metrics(limit=200)
    return {"name": info.get("name"), "params": info.get("params"),
            "config": info.get("config"), "architecture": info.get("architecture"),
            "hardware": _hardware(), "corpus": _corpus_stats(),
            "metrics": {"final_eval": _final_eval()},
            "limitations": _limitations(info.get("params") or 0)}


@app.get("/api/models")
def models_catalog() -> dict:
    """فهرست عمومی نسخه‌ها؛ بدون مسیر فایل، بدون اعداد داخلی."""
    card = active_model_card()
    public = {"id": card.get("id"), "name": card.get("name"),
              "tagline": card.get("tagline"), "status": card.get("status"),
              "badge": card.get("badge")}
    others = [{"id": m.get("id"), "name": m.get("name"), "tagline": m.get("tagline"),
               "status": m.get("status")} for m in ARCHIVE_MODELS]
    return {"models": [public, *others], "default": public["id"]}


_EVAL_FIELDS = ("step", "val_loss", "ppl", "bits_per_char", "top1", "top5", "at")
_TRAIN_FIELDS = ("tokens", "tokens_per_second")


def _public_eval(record: dict | None) -> dict | None:
    """از گزارش آموزش فقط همان چند عددی را بیرون می‌دهیم که سایت به آن‌ها ارجاع می‌دهد."""
    if not record:
        return None
    return {k: record.get(k) for k in _EVAL_FIELDS if record.get(k) is not None}


def _public_train(record: dict | None) -> dict | None:
    if not record:
        return None
    return {k: record.get(k) for k in _TRAIN_FIELDS if record.get(k) is not None}


@app.get("/api/compare")
def api_compare() -> dict:
    """عددهای میزان: سرعت واقعی همین سرویس + امتیاز آزمون فارسی خودمان."""
    return {"speed": _speed_summary(), "arena": _arena_summary(),
            "uptime_pct": _uptime_percent()}


def _speed_summary() -> dict:
    now = time.time()
    with _latency_lock:
        samples = list(_recent_latencies)
        times = list(_recent_times)
    if not samples:
        # هنوز ترافیک واقعی نبوده؛ عددِ سنجش رسمی خودمان را با برچسب روشن نشان بده
        measured = _arena_summary().get("latency_p50_s")
        return {"median_s": measured, "p95_s": None, "per_minute": None,
                "samples": 0, "source": "benchmark" if measured else None}
    ordered = sorted(samples)
    median = ordered[len(ordered) // 2]
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    # نرخ واقعی: چند پاسخ در ۶۰ ثانیهٔ گذشته — نه تقسیم بر میانه که عدد بی‌معنا می‌داد
    per_minute = sum(1 for moment in times if now - moment <= 60)
    return {"median_s": round(median, 3), "p95_s": round(p95, 3),
            "per_minute": per_minute, "samples": len(samples), "source": "live"}


def _uptime_percent() -> float | None:
    """درصد زمانی که سرویس در ۲۴ ساعت گذشته پاسخ داده است (از پایش خودمان)."""
    path = os.path.join(ROOT, "data", "uptime.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return round(float(data.get("percent", 100.0)), 2)
    except (OSError, ValueError):
        return None


def _arena_summary() -> dict:
    """امتیاز آزمون فارسی از گزارش واقعی؛ اگر اجرا نشده باشد، عددی ساخته نمی‌شود."""
    path = os.path.join(ROOT, "reports", "arena.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    models = data.get("models") or []
    if not models:
        return {}
    best = max(models, key=lambda m: m.get("score") or 0)
    return {"tasks": best.get("tasks"), "score": best.get("score"),
            "by_category": best.get("by_category") or {},
            "latency_p50_s": best.get("latency_p50_s"),
            "speed_note": "امتیاز از اجرای واقعی روی همین ماشین می‌آید.",
            "note": "این آزمون را خودمان نوشته‌ایم و پرسش‌هایش از هیچ مجموعهٔ دیگری کپی نشده است."}


@app.get("/api/metrics")
def metrics(request: Request) -> dict:
    """سنجه‌های داخلی؛ فقط مدیر."""
    admin_module.require_admin(request)
    data = _read_metrics(limit=50)
    return {
        "latest_eval": _public_eval(data["latest_eval"]),
        "best_eval": _public_eval(data["best_eval"]),
        "evals": len(data["eval"]),
        "training_active": data["active"],
    }


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


@app.get("/api/samples")
def samples() -> dict:
    return {"samples": SAMPLES, "modes": list(MODES.keys())}


@app.get("/api/stats")
def public_stats() -> dict:
    return {"stats": store().public_stats(), "uptime_s": round(time.time() - STARTED, 1)}


# ------------------------------------------------------------------- حساب
@app.post("/api/auth/register")
def register(req: RegisterRequest, request: Request, response: Response) -> dict:
    _guard_flags(signup=True)
    ip = client_ip(request)
    if not limiter.allow(f"auth:{ip}"):
        raise HTTPException(429, "تلاش‌های زیاد؛ یک دقیقه بعد دوباره امتحان کنید.")
    _check_password(req.password)
    _require_human(req.captcha, request, ip)
    if not mailer_module.valid_address(req.email):
        raise HTTPException(400, "نشانی ایمیل درست نیست.")
    user = store().create_user(req.email, req.password, req.name)
    if user is None:
        raise HTTPException(409, "این ایمیل قبلاً ثبت شده است.")
    token = store().create_session(user_id=user["id"], user_agent=request.headers.get("user-agent", ""), ip=ip)
    _set_session_cookie(response, token)
    store().record_event("signup", user_id=user["id"], ip=ip)

    # کد تأیید واقعی؛ اگر ایمیل پیکربندی نشده باشد، ثبت‌نام متوقف نمی‌شود
    verification = {"sent": False, "required": False}
    try:
        verification = _issue_code(req.email, purpose="signup", ip=ip)
    except mailer_module.MailError as exc:
        verification = {"sent": False, "required": False, "error": str(exc)}
    return {"user": user, "verification": verification, "admin": user.get("role") == "owner"}


def _issue_code(email: str, purpose: str = "signup", ip: str = "") -> dict:
    """ساخت و ارسال کد تأیید؛ محدودیت ارسال دوباره و حالت توسعه را رعایت می‌کند."""
    email = mailer_module.normalize(email)
    if not mailer_module.configured() and not mailer_module.dev_mode():
        raise mailer_module.MailError("ارسال ایمیل هنوز پیکربندی نشده است.")
    pending = store().get_code(email)
    wait = mailer_module.seconds_until_resend(pending)
    if wait > 0 and pending and pending.get("purpose") == purpose:
        raise HTTPException(429, f"{wait} ثانیهٔ دیگر می‌توانی کد تازه بگیری.")
    code = mailer_module.new_code()
    salt = secrets.token_hex(16)
    store().save_code(email, mailer_module.hash_code(code, salt), salt,
                      time.time() + mailer_module.CODE_TTL)
    result = {"sent": False, "required": True, "ttl": mailer_module.CODE_TTL,
              "resend": mailer_module.RESEND_SECONDS}
    if mailer_module.dev_mode():
        result.update({"sent": True, "dev_code": code})
        return result
    mailer_module.send(email, code, purpose)
    result["sent"] = True
    return result


@app.get("/api/auth/verification")
def verification_status(request: Request) -> dict:
    """وضعیت تأیید ایمیلِ کاربرِ واردشده + آیا سرویس ارسال آماده است."""
    owner = _owner(request)
    user = (owner or {}).get("user") or {}
    return {"email": user.get("email"), "verified": bool(user.get("verified")),
            "service": mailer_module.status()}


@app.post("/api/auth/verification/send")
def verification_send(request: Request) -> dict:
    """ارسال (یا ارسال دوبارهٔ) کد تأیید به ایمیل کاربر واردشده."""
    owner = _owner(request)
    user = (owner or {}).get("user") or {}
    email = user.get("email")
    if not email:
        raise HTTPException(401, "برای دریافت کد، وارد حساب شو.")
    if user.get("verified"):
        return {"sent": False, "already": True}
    ip = client_ip(request)
    if not limiter.allow(f"code:{ip}"):
        raise HTTPException(429, "درخواست‌های زیاد؛ یک دقیقه بعد دوباره تلاش کن.")
    try:
        return _issue_code(email, purpose="signup", ip=ip)
    except mailer_module.MailError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/auth/verification/confirm")
def verification_confirm(payload: VerificationConfirm, request: Request) -> dict:
    """بررسی کد؛ پس از تأیید، حساب تأییدشده علامت می‌خورد."""
    owner = _owner(request)
    user = (owner or {}).get("user") or {}
    email = user.get("email")
    if not email:
        raise HTTPException(401, "برای تأیید، وارد حساب شو.")
    ip = client_ip(request)
    if not limiter.allow(f"verify:{ip}"):
        raise HTTPException(429, "تلاش‌های زیاد؛ یک دقیقه بعد دوباره امتحان کن.")
    pending = store().get_code(email)
    ok, why = mailer_module.check_code(pending, payload.code)
    if not ok:
        store().bump_code_tries(email)
        raise HTTPException(400, why)
    store().clear_code(email)
    store().mark_verified(email)
    store().record_event("email_verified", user_id=user.get("id"), ip=ip)
    fresh = store().get_user(int(user["id"]))
    return {"verified": True, "user": fresh}


def _owner_login(req: LoginRequest, request: Request, response: Response, ident: str, ip: str) -> dict:
    """ورود مالک با نام کاربری: هم نشست مدیر و هم نشست کاربر معمولی صادر می‌شود."""
    key = f"owner:{ip}"
    if store().note_attempt(key) > admin_module.MAX_ATTEMPTS:
        admin_module.audit("owner_locked", request, detail="too many attempts")
        raise HTTPException(429, "تلاش‌های ناموفق زیاد؛ ۱۵ دقیقه بعد دوباره امتحان کنید.")
    if not owner_module.matches_username(ident) or not owner_module.verify(req.password):
        admin_module.audit("owner_login_failed", request, detail=ident[:40])
        raise HTTPException(401, "نام کاربری یا رمز عبور نادرست است.")
    store().clear_attempts(key)

    info = owner_module.status()
    admin_id = admin_module._ensure_admin_user("owner@rayan.local")  # noqa: SLF001
    if info.get("name"):
        store().update_user(admin_id, name=info["name"])  # نام نمایشی مالک

    user = store().get_user(admin_id)
    token = store().create_session(user_id=admin_id, user_agent=request.headers.get("user-agent", ""), ip=ip)
    _set_session_cookie(response, token)

    csrf = secrets.token_urlsafe(24)
    admin_token = store().create_admin_session(admin_id, csrf, ip=ip,
                                               user_agent=request.headers.get("user-agent", ""))
    response.set_cookie(admin_module.ADMIN_COOKIE, admin_token, max_age=2 * 3600, httponly=True,
                        samesite="strict", secure=os.environ.get("RAYAN_ENV") == "prod", path="/")
    store().record_event("owner_login", user_id=admin_id, ip=ip)
    admin_module.audit("owner_login", request, target=str(admin_id))
    return {
        "user": user,
        "admin": True,
        "csrf": csrf,
        "redirect": "/admin",
        "owner": {"name": info.get("name"), "default_password": info.get("default_password")},
    }


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response) -> dict:
    _guard_flags()
    ip = client_ip(request)
    if not limiter.allow(f"auth:{ip}"):
        raise HTTPException(429, "تلاش‌های زیاد؛ یک دقیقه بعد دوباره امتحان کنید.")
    _require_human(req.captcha, request, ip)
    ident = (req.identifier or req.email or "").strip()
    if not ident:
        raise HTTPException(422, "ایمیل یا نام کاربری لازم است.")

    # مسیر مالک: نام کاربری فارسی؛ گذرواژه فقط با هش محلی مقایسه می‌شود.
    if "@" not in ident and owner_module.matches_username(ident):
        return _owner_login(req, request, response, ident, ip)

    key = f"login:{ident.lower()}:{ip}"
    if store().note_attempt(key) > 8:
        raise HTTPException(429, "تلاش‌های ناموفق زیاد است؛ ۱۵ دقیقه بعد دوباره امتحان کنید.")
    if "@" in ident and not store().email_exists(ident):
        # ایمیل ساخته نشده است؛ کاربر باید به پنل ثبت‌نام برود.
        raise HTTPException(404, detail={
            "code": "account_not_found",
            "message": "با این ایمیل حسابی ساخته نشده است؛ می‌توانی همین حالا ثبت‌نام کنی.",
            "email": ident,
            "next": "/signup",
        })
    user = store().verify_user(ident, req.password)
    if user is None:
        if "@" not in ident:
            # نام کاربریِ ناشناخته: بگو با چه چیزی می‌تواند وارد شود.
            raise HTTPException(401, detail={
                "code": "unknown_username",
                "message": ("با این نام کاربری حسابی نیست. برای پنل مدیریت نام کاربریِ "
                            f"«{owner_module.status().get('name')}» (یا admin) و برای حساب "
                            "کاربری، ایمیلِ ثبت‌شده را وارد کن."),
                "owner_username": owner_module.status().get("name"),
            })
        raise HTTPException(401, "ایمیل یا رمز عبور نادرست است.")
    store().clear_attempts(key)
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
        "signed_in": owner.get("user_id") is not None,
        # رابط کاربری با این پرچم می‌داند باید پردهٔ ثبت‌نام را نشان دهد
        "signup_required": REQUIRE_SIGNUP and owner.get("user_id") is None,
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


@app.post("/api/auth/password")
def change_my_password(req: PasswordChange, request: Request) -> dict:
    """تغییر گذرواژه؛ فقط با دانستن گذرواژهٔ کنونی."""
    owner = _owner(request)
    user = (owner or {}).get("user") or {}
    if not user.get("id"):
        raise HTTPException(401, "برای تغییر گذرواژه وارد حساب شو.")
    email = user.get("email") or ""
    if store().verify_user(email, req.current) is None:
        store().record_event("password_change_failed", user_id=user.get("id"), ip=client_ip(request))
        raise HTTPException(403, "گذرواژهٔ کنونی درست نیست.")
    if req.new.strip() == req.current:
        raise HTTPException(400, "گذرواژهٔ تازه باید متفاوت باشد.")
    store().change_password(int(user["id"]), req.new)
    store().record_event("password_changed", user_id=user.get("id"), ip=client_ip(request))
    return {"changed": True}


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


CACHE_SIZE = int(os.environ.get("RAYAN_CACHE_SIZE", "512") or 0)


def _cache_key(message: str) -> str:
    """کلید کش: پرسش نرمال‌شده + اثرانگشت مدلِ فعال (نسخهٔ مدل بخشی از کلید است)."""
    if CACHE_SIZE <= 0 or engine is None:
        return ""
    text = " ".join((message or "").split()).strip(" ؟?.!")
    if not text or len(text) > 160:
        return ""
    stamp = f"{engine.checkpoint}:{engine.meta.get('step')}"
    return hashlib.sha1(f"{stamp}|{text}".encode("utf-8")).hexdigest()


def _prepare(req: ChatRequest, owner: dict, ip: str) -> tuple[Engine, str, list[tuple[str, str]], str | None]:
    _guard_flags(deep=req.deep)
    # دسترسی به هوش فقط از داخل سایت و فقط با حساب ثبت‌نام‌شده؛ هیچ کلید API نیست.
    _require_account(owner)
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
                  stats: dict, trace: dict | None, deep: bool,
                  tool: dict | None = None,
                  sources: list[dict] | None = None) -> tuple[str | None, int | None]:
    """پیام کاربر و پاسخ را ذخیره می‌کند؛ شناسهٔ گفتگو و پیام پاسخ را برمی‌گرداند."""
    title = message.strip().replace("\n", " ")[:60] or "گفتگوی تازه"
    if conv_id is None:
        conv_id = store().create_conversation(owner, title)["id"]
    store().add_message(conv_id, "user", message)
    meta = {"stats": stats, "deep": deep, "trace": trace, "tool": tool}
    if sources:
        meta["sources"] = sources
    msg_id = store().add_message(conv_id, "assistant", answer, meta)
    existing = store().get_conversation_meta(conv_id)
    if existing and existing["title"] in ("گفتگوی تازه", ""):
        store().rename_conversation(conv_id, title)
    return conv_id, msg_id


def _record_usage(owner: dict, ip: str, kind: str) -> None:
    store().record_event(kind, user_id=owner.get("user_id"), guest_id=owner.get("guest_id"), ip=ip)


def _think(message: str, req, history=None) -> dict | None:
    """لایهٔ «فکر کردن»: بازیابی شاهد از پیکره و ساختن پاسخ مستند.

    فقط برای سؤال‌های دانشی در حالت گفتگو اجرا می‌شود و هیچ پاسخی از پیش
    نوشته نشده؛ اگر شاهدی پیدا نشود None برمی‌گردد تا مسیرهای بعدی امتحان شوند.
    """
    if req.mode != "chat" or req.web:
        return None
    if not retrieval_module.index_exists():
        return None
    question = retrieval_module.resolve_followup(message, history) if history else message
    if not retrieval_module.looks_factual(question):
        return None
    try:
        return retrieval_module.think(question)
    except Exception as exc:  # noqa: BLE001 - بازیابی نباید چت را بشکند
        print(f"[rayan] retrieval failed: {exc}", flush=True)
        return None


def _instant_turn(owner: dict, ip: str, req: ChatRequest, response: Response,
                  conv_id: str | None, message: str, answer: str,
                  tool_result: dict | None, started: float,
                  engine: str, extra: dict | None = None) -> dict:
    """پاسخ آماده (مهارت/دانشنامه) را بدون دخالت مدل ثبت و برمی‌گرداند."""
    global request_count
    stats = {
        "prompt_tokens": 0, "tokens": 0, "seconds": round(time.time() - started, 3),
        "tokens_per_second": 0.0, "confidence": 1.0, "entropy": 0.0,
        "finish_reason": engine, "seed": 0,
    }
    extra = extra or {}
    sources = extra.get("sources") or []
    conv_id, msg_id = _persist_turn(owner, conv_id, message, answer, stats,
                                    extra.get("thought"), False, tool_result, sources or None)
    _remember(req.session_id, message, answer)
    _record_usage(owner, ip, "chat")
    _set_guest_cookie(response, owner)
    with stats_lock:
        request_count += 1
    _note_latency(time.time() - started)
    used, limit = _quota(owner, ip, "chat")
    return {
        "answer": answer, "mode": req.mode, "deep": False, "trace": None,
        "stats": stats, "latency_s": round(time.time() - started, 3),
        "session_id": req.session_id, "conversation_id": conv_id,
        "message_id": msg_id, "usage": {"used": used, "limit": limit},
        "tool": tool_result, "sources": sources, "engine": engine, "extra": extra or {},
    }


@app.get("/api/benchmark")
def api_benchmark() -> dict:
    """نتیجهٔ آخرین اجرای بنچمارک شفاف (scripts/benchmark.py)."""
    path = os.path.join(ROOT, "reports", "benchmark.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        raise HTTPException(404, "هنوز بنچمارکی اجرا نشده است.") from None
    return {
        "model": data.get("model"),
        "params": data.get("params"),
        "run_at": data.get("run_at"),
        "tasks": data.get("tasks"),
        "accuracy": data.get("accuracy"),
        "latency": data.get("latency"),
        "engine_mix": data.get("engine_mix"),
        "cost_usd_per_million_tokens": data.get("cost_usd_per_million_tokens"),
        "opus_reference": data.get("opus_reference"),
    }


@app.get("/api/search")
def api_search(request: Request, q: str = "", limit: int = 5) -> dict:
    """جست‌وجوی وب سمت سرور؛ کلید API لازم نیست و هیچ داده‌ای به سرویس بیرونی نمی‌رود."""
    if not admin_module.flags().get("web_search", True):
        raise HTTPException(503, "جست‌وجوی وب توسط مدیر خاموش شده است.")
    ip = client_ip(request)
    if not limiter.allow(f"search:{ip}"):
        raise HTTPException(429, "جست‌وجوهای زیاد؛ چند لحظه بعد دوباره تلاش کنید.")
    query = (q or "").strip()
    if len(query) < 2:
        raise HTTPException(422, "عبارت جست‌وجو خیلی کوتاه است.")
    return search_module.search(query, limit=max(1, min(int(limit), 8)))


def _reveal_chunks(text: str, budget: float = 0.45) -> list[str]:
    """متن را به تکه‌های کوچک می‌شکند تا در رابط، واژه‌به‌واژه نوشته شود.

    تعداد تکه‌ها سقف دارد تا پاسخِ فوری واقعاً فوری بماند (حدود نیم‌ثانیه).
    """
    text = text or ""
    if not text:
        return [""]
    words = text.split(" ")
    limit = max(1, int(budget / 0.012))
    size = max(1, -(-len(words) // limit))
    return [" ".join(words[i:i + size]) + (" " if i + size < len(words) else "")
            for i in range(0, len(words), size)]


def _ground_if_weak(message: str, answer: str, history, owner: dict, req,
                    tried_local: bool = False) -> tuple[str, list[dict]]:
    """اگر پاسخ مدل بی‌ربط بود: جست‌وجوی وب، و اگر نشد پاسخ صادقانهٔ مخصوص سؤال.

    این‌کار پاسخ‌های درهم مدل کوچک را با منبع واقعی جایگزین می‌کند؛ چیزی از پیش
    نوشته نشده و متنِ منبع‌دار عیناً از نتایج جست‌وجو ساخته می‌شود.
    """
    if not answer_module.weak(message, answer, history):
        return answer_module.enhance(message, answer, history, owner), []

    found: list[dict] = []

    def resolver(query: str) -> str | None:
        # ۱) شاهد از پیکرهٔ محلی (بدون شبکه و بدون هزینه) — اگر همین حالا
        #    برای همین پیام آزموده شده، دوباره انجام نشود (پاسخ کند می‌شد).
        if (not tried_local and reason_module.retrieval.index_exists()
                and reason_module.retrieval.looks_factual(query)):
            thought = reason_module.retrieval.think(query)
            if thought.get("answer"):
                found.extend(thought.get("sources") or [])
                return thought["answer"]
        # ۲) جست‌وجوی وب: فقط وقتی کاربر کلید «وب» را زده یا مدیر خودکارسازی را
        #    روشن کرده باشد. پیش‌فرض خاموش است تا پاسخ فوری بماند، نه ۵ ثانیه منتظر وب.
        if not req.web or not admin_module.flags().get("web_search", True):
            return None
        results = search_module.search(query, limit=4).get("results") or []
        if not results:
            return None
        found.extend(results)
        return search_module.compose(query, results)

    text = answer_module.enhance(message, answer, history, owner, resolver=resolver)
    if not found and answer_module.weak(message, text, history):
        # هیچ شاهدی نبود: پیش از هر عذرخواهی، راهنمای موضوعی جواب می‌دهد
        guided = None
        try:
            from web import guide as guide_module
            guided = guide_module.answer(message)
        except Exception:  # noqa: BLE001 - این لایه نباید پاسخ را بشکند
            guided = None
        if guided:
            text = guided["answer"]
        else:
            near = reason_module._near_subjects(message)  # noqa: SLF001 - همان ماژول داخلی
            text = reason_module.honest(message, near)
    return text, found


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request, response: Response) -> dict:
    global request_count
    owner = _owner(request)
    ip = client_ip(request)
    model, message, history, conv_id = _prepare(req, owner, ip)
    tool_result = None if req.mode != "chat" else tools_module.detect(message)
    started = time.time()
    kwargs = _generation_kwargs(req)

    if req.mode == "chat":
        # ابزار اول: هر محاسبه یا تاریخ، بدون مدل و بدون تأخیر پاسخ می‌گیرد.
        if tool_result and tool_result.get("ok"):
            spoken = tools_module.phrase(tool_result)
            if spoken:
                return _instant_turn(owner, ip, req, response, conv_id, message, spoken,
                                     tool_result, started, "tool")
        # ترجمه و مسائل کلامی پیش از مهارت‌های عمومی؛ پاسخِ مستقیم می‌دهند
        for module_name in ("translate", "mathword"):
            try:
                module = __import__(f"web.{module_name}", fromlist=["answer"])
                solved = module.answer(message)
            except Exception:  # noqa: BLE001 - یک لایه نباید چت را بشکند
                solved = None
            if solved:
                return _instant_turn(owner, ip, req, response, conv_id, message,
                                     solved["answer"], tool_result, started,
                                     solved.get("engine", module_name))
        # دانشنامهٔ بررسی‌شده پیش از لایه‌های نوشتاری و آموزشی: اگر پاسخِ قطعی
        # داریم، نباید لایهٔ دیگری موضوع را به خودش بگیرد.
        knowledge_hit = knowledge_module.answer(message)
        if knowledge_hit:
            return _instant_turn(owner, ip, req, response, conv_id, message,
                                 knowledge_hit["answer"], tool_result, started, "knowledge",
                                 {"sources": [{"title": "پاسخ بررسی‌شده",
                                               "source": "رایان", "score": 1.0}],
                                  "curated": True})

        written = writer_module.answer(message)
        if written:
            return _instant_turn(owner, ip, req, response, conv_id, message, written["answer"],
                                 tool_result, started, written["engine"])
        taught = tutor_module.answer(message)
        if taught:
            return _instant_turn(owner, ip, req, response, conv_id, message, taught["answer"],
                                 tool_result, started, taught["engine"])
        skill = skills_module.match(message)
        if skill:
            skill = answer_module.personalize(skill, owner)
            return _instant_turn(owner, ip, req, response, conv_id, message, skill["answer"],
                                 tool_result, started, "skill", {"skill": skill["skill"]})

        if not req.web:
            # کش پاسخ دانشی: پرسش‌های تکراری (سهم بزرگی از ترافیک واقعی) بدون
            # جست‌وجو و بدون هزینهٔ مدل پاسخ می‌گیرند. کلید شامل مدلِ فعال است،
            # پس بعد از هر به‌روزرسانی مدل خودبه‌خود بی‌اعتبار می‌شود.
            key = _cache_key(message)
            hit = _PROMPT_CACHE.get(key) if key else None
            if hit:
                _PROMPT_CACHE.move_to_end(key)
                return _instant_turn(owner, ip, req, response, conv_id, message,
                                     hit["answer"], tool_result, started, "think",
                                     {"thought": {"steps": hit["trace"],
                                                  "confidence": hit.get("confidence", 0.9),
                                                  "cached": True},
                                      "sources": hit["sources"]})
            thought = _think(message, req, history)
            if thought and thought.get("answer"):
                if key:
                    _PROMPT_CACHE[key] = {"answer": thought["answer"],
                                          "trace": thought["trace"],
                                          "sources": thought["sources"],
                                          "confidence": thought["confidence"]}
                    _PROMPT_CACHE.move_to_end(key)
                    while len(_PROMPT_CACHE) > CACHE_SIZE:
                        _PROMPT_CACHE.popitem(last=False)
                return _instant_turn(owner, ip, req, response, conv_id, message,
                                     thought["answer"], tool_result, started, "think",
                                     {"thought": {"steps": thought["trace"],
                                                  "confidence": thought["confidence"]},
                                      "sources": thought["sources"]})

    web_results: list[dict] = []
    if req.web and req.mode == "chat" and admin_module.flags().get("web_search", True):
        web_results = search_module.search(message, limit=5).get("results") or []
        if web_results:
            answer = search_module.compose(message, web_results)
            stats = {
                "prompt_tokens": 0, "tokens": 0, "seconds": round(time.time() - started, 2),
                "tokens_per_second": 0.0, "confidence": 0.0, "entropy": 0.0,
                "finish_reason": "web", "seed": 0,
            }
            conv_id, msg_id = _persist_turn(owner, conv_id, message, answer, stats, None, False,
                                            tool_result, web_results)
            _remember(req.session_id, message, answer)
            _record_usage(owner, ip, "chat")
            _set_guest_cookie(response, owner)
            with stats_lock:
                request_count += 1
            used, limit = _quota(owner, ip, "chat")
            return {
                "answer": answer, "mode": req.mode, "deep": False, "trace": None,
                "stats": stats, "latency_s": round(time.time() - started, 2),
                "session_id": req.session_id, "conversation_id": conv_id,
                "message_id": msg_id, "usage": {"used": used, "limit": limit},
                "tool": tool_result, "sources": web_results, "engine": "web",
            }

    if not _acquire_slot():
        raise HTTPException(503, "سرور شلوغ است؛ چند لحظه بعد دوباره تلاش کنید.")
    try:
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
    finally:
        _release_slot()
    stats = _stats(generation, prompt_ids)
    auto_sources: list[dict] = []
    if req.mode == "chat":
        tried = bool(req.mode == "chat" and reason_module.retrieval.index_exists()
                     and reason_module.retrieval.looks_factual(message))
        answer, auto_sources = _ground_if_weak(message, answer, history, owner, req,
                                               tried_local=tried)
        _remember(req.session_id, message, answer)
    conv_id, msg_id = _persist_turn(owner, conv_id, message, answer, stats, trace, req.deep,
                                    tool_result, auto_sources or None)
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
        "tool": tool_result,
        "sources": auto_sources or web_results,
        "engine": "chat",
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    global request_count
    started = time.time()
    owner = _owner(request)
    ip = client_ip(request)
    if req.deep:
        raise HTTPException(400, "برای اندیشهٔ ژرف از /api/chat استفاده کنید.")
    model, message, history, conv_id = _prepare(req, owner, ip)
    tool_result = None if req.mode != "chat" else tools_module.detect(message)
    tool_answer = ""
    if tool_result and tool_result.get("ok"):
        tool_answer = tools_module.phrase(tool_result)
    kb = None if (tool_answer or req.mode != "chat" or req.web) else knowledge_module.answer(message)
    written = None if tool_answer or kb or req.mode != "chat" else writer_module.answer(message)
    taught = None if (tool_answer or kb or written or req.mode != "chat") else tutor_module.answer(message)
    skill = None if (tool_answer or kb or taught or written) else (
        skills_module.match(message) if req.mode == "chat" else None)
    thought = None
    if req.mode == "chat" and not skill and not taught and not kb:
        thought = _think(message, req, history)
    instant_answer = (tool_answer or (written or {}).get("answer") or (taught or {}).get("answer")
                      or (skill or {}).get("answer")
                      or (thought or {}).get("answer") or (kb or {}).get("answer") or "")
    instant_engine = ("tool" if tool_answer else (written or {}).get("engine") or
                      (taught or {}).get("engine") or
                      "skill" if skill else "think" if thought else
                      "knowledge" if kb else "")
    kwargs = _generation_kwargs(req)
    kwargs["seed"] = req.seed
    kwargs = {k: v for k, v in kwargs.items() if v is not None}

    def generate_events():
        global request_count
        if instant_answer:
            stats = {"prompt_tokens": 0, "tokens": 0, "seconds": 0.0,
                     "tokens_per_second": 0.0, "confidence": 1.0, "entropy": 0.0,
                     "finish_reason": instant_engine, "seed": 0}
            new_conv, msg_id = _persist_turn(owner, conv_id, message, instant_answer,
                                             stats, None, False, tool_result, None)
            _remember(req.session_id, message, instant_answer)
            _record_usage(owner, ip, "chat")
            with stats_lock:
                request_count += 1
            _note_latency(time.time() - started)
            used, limit = _quota(owner, ip, "chat")
            yield json.dumps({"type": "start", "prompt_tokens": 0}, ensure_ascii=False) + "\n"
            if thought:
                yield json.dumps({"type": "think", "steps": thought["trace"],
                                  "sources": thought.get("sources") or []},
                                 ensure_ascii=False) + "\n"
            # پاسخ‌های قطعی هم واژه‌به‌واژه روی صفحه می‌آیند (افکت نوشتن)
            for chunk in _reveal_chunks(instant_answer):
                yield json.dumps({"type": "token", "text": chunk}, ensure_ascii=False) + "\n"
                time.sleep(0.012)   # مولدِ همگام در رشتهٔ کارگر اجرا می‌شود
            yield json.dumps({
                "type": "done", "answer": instant_answer, "stats": stats,
                "sources": (thought or {}).get("sources") or [],
                "conversation_id": new_conv, "message_id": msg_id,
                "usage": {"used": used, "limit": limit}, "tool": tool_result,
                "engine": instant_engine,
                "skill": (skill or {}).get("skill"),
                "knowledge": (kb or {}).get("knowledge"),
                "thought": {"steps": (thought or {}).get("trace", []),
                            "confidence": (thought or {}).get("confidence")} if thought else None,
            }, ensure_ascii=False) + "\n"
            return

        if not _acquire_slot(wait=12.0):
            yield json.dumps({"type": "error", "error": "سرور شلوغ است؛ چند لحظه بعد دوباره تلاش کنید."},
                             ensure_ascii=False) + "\n"
            return
        try:
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
                auto_sources: list[dict] = []
                if req.mode == "chat":
                    answer, auto_sources = _ground_if_weak(message, answer, history, owner, req)
                    _remember(req.session_id, message, answer)
                stats = _stats(generation, ids)
                new_conv, msg_id = _persist_turn(owner, conv_id, message, answer, stats, None, False,
                                                 tool_result, auto_sources or None)
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
                    "tool": tool_result,
                    "sources": auto_sources,
                }, ensure_ascii=False) + "\n"
        finally:
            _release_slot()

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    response = StreamingResponse(generate_events(), media_type="application/x-ndjson", headers=headers)
    _set_guest_cookie(response, owner)
    return response


# =============================================================== تبلیغات
class AdClick(BaseModel):
    id: int


@app.get("/api/ads")
def ads_public(slot: str = "") -> dict:
    if not admin_module.flags()["ads_enabled"]:
        return {"ads": []}
    if slot:
        ad = store().pick_ad(slot)
        return {"ads": [ad] if ad else []}
    return {"ads": store().list_ads(only_active=True)}


@app.post("/api/ads/{ad_id}/click")
def ads_click(ad_id: int, request: Request) -> dict:
    if not limiter.allow(f"adclick:{client_ip(request)}"):
        raise HTTPException(429, "درخواست زیاد است.")
    url = store().click_ad(ad_id)
    if url is None:
        raise HTTPException(404, "این تبلیغ فعال نیست.")
    return {"ok": True, "url": url}


# ============================================================== مدیریت
app.include_router(admin_module.router)


@app.get("/api/flags")
def public_flags() -> dict:
    return {"flags": admin_module.flags()}


PLAN_TEXTS = {
    "free": {
        "name": "رایگان",
        "tag": "پیشنهادی",
        "desc": "حساب کامل: تاریخچهٔ همیشگی و سهمیهٔ بیشتر.",
        "features": ["تاریخچهٔ دائمی و جست‌وجو", "اشتراک‌گذاری عمومی گفتگو",
                     "خروجی Markdown", "استودیو تصویر و ابزارها"],
    },
    "pro": {
        "name": "حرفه‌ای",
        "tag": "پولی",
        "desc": "همان رایان، با سهمیهٔ بیشتر برای کار روزمره.",
        "features": ["سهمیهٔ چندبرابری گفتگو", "اندیشهٔ ژرف بیشتر",
                     "پشتیبانی از توسعهٔ مدل", "دسترسی زودهنگام به مدل‌های بعدی"],
    },
}


def _num_setting(raw: dict, key: str, default: int) -> int:
    try:
        return max(0, int(float(raw.get(key, default))))
    except (TypeError, ValueError):
        return default


@app.get("/api/plans")
def public_plans() -> dict:
    """تعرفهٔ عمومی: از تنظیمات مدیر خوانده می‌شود تا بدون کد بتوان قیمت گذاشت."""
    raw = store().all_settings()
    pro_price = _num_setting(raw, "plan_pro_price", 0)
    pro_days = _num_setting(raw, "plan_pro_days", 30) or 30
    payments_enabled = raw.get("payments_enabled", "0") == "1"
    provider = (raw.get("payment_provider", "") or "").strip()
    link = (raw.get("payment_link", "") or "").strip()
    note = (raw.get("payment_note", "") or "").strip()
    plans = []
    for pid in ("guest", "free", "pro"):
        limits = LIMITS.get(pid.replace("guest", "guest"), {})
        base = PLAN_TEXTS.get(pid, PLAN_TEXTS["free"])
        price = pro_price if pid == "pro" else 0
        plans.append({
            "id": pid,
            "name": "مهمان" if pid == "guest" else base["name"],
            "tag": "بدون ثبت‌نام" if pid == "guest" else base["tag"],
            "price": price,
            "period": f"{pro_days} روز" if pid == "pro" and price else "همیشه",
            "desc": "برای امتحان کردن؛ تاریخچه در همین مرورگر می‌ماند." if pid == "guest" else base["desc"],
            "features": (["۲۵ پیام در روز", "هر سه حالت گفتگو، ادامهٔ متن و شعر"] if pid == "guest"
                         else base["features"]),
            "limits": limits,
            "for_sale": bool(pid == "pro" and price > 0 and payments_enabled),
        })
    return {
        "ok": True,
        "currency": (raw.get("currency_label", "تومان") or "تومان")[:16],
        "plans": plans,
        "payments": {
            "enabled": payments_enabled,
            "provider": provider[:40],
            "link": link[:300] if re.match(r"^(https?://|/)", link) else "",
            "note": note[:200],
        },
    }


# ================================================================ ابزارها
class ToolRequest(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    args: dict = Field(default_factory=dict)


@app.get("/api/tools")
def tools_catalog() -> dict:
    return {"tools": tools_module.catalog()}


@app.post("/api/tools/run")
def tools_run(req: ToolRequest, request: Request) -> dict:
    if not limiter.allow(f"tool:{client_ip(request)}"):
        raise HTTPException(429, "درخواست زیاد است.")
    return tools_module.run(req.name, req.args)


# ======================================================= خودآزمون و پایش
@app.get("/api/selftest")
def selftest(request: Request) -> dict:
    admin_module.require_admin(request)
    checks = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    try:
        row = store()._one("SELECT 1 AS one")  # noqa: SLF001
        add("database", bool(row), "sqlite ok")
    except Exception as exc:
        add("database", False, str(exc))
    add("model", engine is not None, engine_error or "loaded")
    active_checkpoint, active_tokenizer = active_pair()
    add("checkpoint", bool(active_checkpoint), active_checkpoint or "not found")
    add("tokenizer", os.path.exists(active_tokenizer), active_tokenizer)
    add("static_dir", os.path.isdir(STATIC_DIR), STATIC_DIR)
    add("admin", bool(admin_module.admin_credentials().get("pw_hash")), "credentials ready")
    # سلامتِ ورود: مالک پیکربندی‌شده، گذرواژهٔ پیش‌فرض، و حسابِ مالک در پایگاه‌داده
    owner_info = owner_module.status()
    add("owner", bool(owner_info.get("configured")),
        f"username={owner_info.get('name')} default_password={owner_info.get('default_password')}")
    try:
        owner_row = store()._one("SELECT id FROM users WHERE email=?", ("owner@rayan.local",))  # noqa: SLF001
        add("owner_account", bool(owner_row), "admin user exists")
    except Exception as exc:  # pragma: no cover
        add("owner_account", False, str(exc))
    mail_status = mailer_module.status()
    add("mailer", bool(mail_status.get("configured") or mail_status.get("dev")),
        "ایمیل پیکربندی نشده است؛ ثبت‌نام بی‌درنگ انجام می‌شود و کدِ تأیید فقط "
        "وقتی SMTP تنظیم شود فرستاده می‌شود." if not mail_status.get("configured")
        else f"{mail_status.get('mode')} · {mail_status.get('sender')}")
    free = -1
    try:
        import shutil
        free = int(shutil.disk_usage(ROOT).free / (1024 ** 2))
    except Exception:
        pass
    add("disk", free > 50, f"{free} MB free")
    ok = all(item["ok"] for item in checks)
    return {"ok": ok, "checks": checks, "uptime_s": round(time.time() - STARTED, 1),
            "version": app.version}


@app.get("/api/status")
def status() -> dict:
    """نمای عمومی سلامت برای بنر سایت و مانیتورینگ."""
    flags = admin_module.flags()
    return {
        "ok": engine is not None,
        "version": app.version,
        "model_loaded": engine is not None,
        "maintenance": flags["maintenance"],
        "announcement": flags["announcement"],
        "uptime_s": round(time.time() - STARTED, 1),
        "requests": request_count,
        "max_concurrency": MAX_CONCURRENCY,
        "queue": _queue_depth["value"],
        "db_bytes": os.path.getsize(os.environ.get("RAYAN_DB", "data/rayan.sqlite3"))
        if os.path.exists(os.environ.get("RAYAN_DB", "data/rayan.sqlite3")) else 0,
    }



# ------------------------------------------------------- به‌روزرسانی بی‌وقفه
_MASTER_PID = {"value": 0}
# کش پاسخ‌های تکراری (پرسش یکسان، پاسخ یکسان) — با هر به‌روزرسانی خالی می‌شود
_PROMPT_CACHE: "OrderedDict[str, dict]" = OrderedDict()


def soft_reload() -> dict:
    """مدل را از نو بار می‌کند و میان‌برها را پاک می‌کند؛ سرویس قطع نمی‌شود.

    ابتدا مدل تازه ساخته می‌شود و فقط اگر سالم بود جای مدل قبلی می‌نشیند؛ در
    صورت خطا، مدل قبلی سر جایش می‌ماند. کش‌های وابسته به مدل هم خالی می‌شوند.
    """
    global engine, engine_error
    started = time.time()
    try:
        fresh = load_engine()
    except Exception as exc:  # noqa: BLE001
        engine_error = str(exc)
        return {"reloaded": False, "error": str(exc), "seconds": round(time.time() - started, 3)}
    previous = engine.checkpoint if engine is not None else None
    engine, engine_error = fresh, None
    cleared = 0
    for cache in (sessions, _PROMPT_CACHE):
        try:
            cleared += len(cache)
            cache.clear()
        except Exception:  # noqa: BLE001
            continue
    return {"reloaded": True, "checkpoint": os.path.relpath(fresh.checkpoint, ROOT),
            "previous": os.path.relpath(previous, ROOT) if previous else None,
            "step": fresh.meta.get("step"), "caches_cleared": cleared,
            "seconds": round(time.time() - started, 3)}


def restart_workers() -> dict:
    """SIGHUP به سرورِ مادر: uvicorn کارگرها را یکی‌یکی و بی‌قطع سرویس نو می‌کند.

    فقط pid ثبت‌شده در ``data/server.pid`` (که در حالت ``--workers`` نوشته می‌شود)
    سیگنال می‌گیرد؛ در حالت تک‌کارگری سیگنال دادن به والد می‌تواند خودِ سرویس را
    بکشد، پس به‌جایش «بارگذاری دوباره» را پیشنهاد می‌دهیم.
    """
    pid_file = os.path.join(ROOT, "data", "server.pid")
    pid = _MASTER_PID["value"]
    if not pid and os.path.exists(pid_file):
        try:
            with open(pid_file, encoding="utf-8") as fh:
                pid = int(fh.read().strip() or 0)
        except (OSError, ValueError):
            pid = 0
    if not pid or pid <= 1:
        return {"signalled": False, "mode": "single",
                "reason": "در حالت تک‌کارگری کافی است «بارگذاری دوبارهٔ مدل» را بزنی؛ "
                          "برای راه‌اندازی دوبارهٔ کامل، سرور را با --workers ۲ یا بیشتر اجرا کن."}
    try:
        os.kill(pid, signal.SIGHUP)
    except OSError as exc:
        return {"signalled": False, "reason": str(exc), "pid": pid}
    return {"signalled": True, "pid": pid, "mode": "workers",
            "note": "کارگرها یکی‌یکی نو می‌شوند؛ درخواست‌های جاری نیمه‌کاره نمی‌مانند."}


def _worker_count() -> int:
    """چند کارگر همین حالا سرو می‌کنند — از خط فرمان خودِ فرایند، نه از یک عدد ثابت."""
    try:
        declared = int(os.environ.get("RAYAN_WORKERS", "") or -1)
    except ValueError:
        declared = -1
    if declared > 0:
        return declared
    for pid in (os.getppid(), os.getpid()):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                parts = fh.read().decode("utf-8", "replace").split("\x00")
        except OSError:
            continue
        for index, part in enumerate(parts):
            if part == "--workers" and index + 1 < len(parts):
                try:
                    return max(1, int(parts[index + 1]))
                except ValueError:
                    pass
            if part.startswith("--workers="):
                try:
                    return max(1, int(part.split("=", 1)[1]))
                except ValueError:
                    pass
    return 1


def capacity_report() -> dict:
    """ظرفیت سنجیده‌شدهٔ همین ماشین — بدون عدد آرمانی و بدون ادعا.

    عددها از خود سرور می‌آیند: چند کارگر، چند درخواست در صف، اندازهٔ کش و
    میانگین تأخیر واقعیِ ثبت‌شده در نشست جاری.
    """
    from web import network
    stats = _stats_snapshot() if "_stats_snapshot" in globals() else {}
    return {
        "workers": _worker_count(),
        "queue_depth": _queue_depth["value"],
        "concurrency_limit": MAX_CONCURRENCY,
        "cache_size": CACHE_SIZE,
        "cache_used": len(_PROMPT_CACHE),
        "requests_served": request_count,
        "hardware": _hardware(),
        "network": network.stats(),
        "database": _db_info(),
        "honest_note": ("ظرفیت واقعی به یک میلیون کاربر با یک ماشین و یک لایهٔ SQLite "
                        "نمی‌رسد؛ برای آن مقیاس چند سرور + پایگاه‌دادهٔ شبکه‌ای لازم است. "
                        "عددهای همین گزارش، اندازه‌گیری همین ماشین است."),
        **stats,
    }


def _db_info() -> dict:
    path = os.environ.get("RAYAN_DB", os.path.join(ROOT, "data", "rayan.sqlite3"))
    size = os.path.getsize(path) if os.path.exists(path) else 0
    index = os.path.join(ROOT, "data", "index.sqlite3")
    wiki = os.path.join(ROOT, "data", "wiki.sqlite3")
    return {
        "users_db_bytes": size,
        "index_bytes": os.path.getsize(index) if os.path.exists(index) else 0,
        "wiki_bytes": os.path.getsize(wiki) if os.path.exists(wiki) else 0,
    }


def main() -> None:
    global engine, engine_error
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--no-reload", action="store_true")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("RAYAN_WORKERS", "1") or 1))
    args = parser.parse_args()
    if args.checkpoint:
        try:
            engine = load_engine(args.checkpoint)
            print(f"[rayan] loaded {engine.checkpoint} | step={engine.meta.get('step')} "
                  f"| params={sum(p.size for p in engine.params.values()):,}", flush=True)
        except Exception as exc:
            engine_error = str(exc)
            print(f"[rayan] model not loaded: {exc}", flush=True)
    boot()
    import uvicorn
    if args.workers > 1:
        # حالت چندکارگری: فرمان «راه‌اندازی دوباره» با SIGHUP بی‌وقفه اعمال می‌شود.
        _MASTER_PID["value"] = os.getpid()
        try:
            with open(os.path.join(ROOT, "data", "server.pid"), "w", encoding="utf-8") as fh:
                fh.write(str(os.getpid()))
        except OSError:
            pass
        uvicorn.run("web.server:app", host=args.host, port=args.port, log_level="info",
                    workers=args.workers)
        return
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
