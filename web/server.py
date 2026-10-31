"""سرور وب پارسیا — FastAPI + مدل محلی.

    python web/server.py --port 8000 --host 0.0.0.0

همه‌چیز روی همین دستگاه اجرا می‌شود؛ هیچ درخواستی به سرویس هوش مصنوعی بیرونی
فرستاده نمی‌شود.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import threading
import time
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from parsia.generate import MODES, Engine, polish  # noqa: E402
from parsia.text import normalize, prepare_user_input  # noqa: E402
from parsia.thinking import deep_reply  # noqa: E402
from parsia.tokenizer import BPETokenizer  # noqa: E402

STATIC_DIR = os.path.join(ROOT, "web", "static")
CHECKPOINTS = [
    os.path.join(ROOT, "checkpoints", "last.npz"),
    os.path.join(ROOT, "checkpoints", "parsia-1-small.npz"),
]
TOKENIZER_PATH = os.path.join(ROOT, "tokenizer", "parsia_bpe.json")
METRICS_PATH = os.path.join(ROOT, "logs", "metrics.jsonl")
RUN_CONFIG_PATH = os.path.join(ROOT, "configs", "training_run.json")
CORPUS_STATS_PATH = os.path.join(ROOT, "data", "corpus_stats.json")

STARTED = time.time()
engine: Engine | None = None
engine_error: str | None = None
sessions: dict[str, list[tuple[str, str]]] = {}
sessions_lock = threading.Lock()
request_count = 0
stats_lock = threading.Lock()

SAMPLES = [
    {"mode": "chat", "title": "خودت را معرفی کن", "text": "تو کی هستی و چه کارهایی می‌توانی انجام دهی؟"},
    {"mode": "chat", "title": "یک شعر", "text": "یک شعر بگو"},
    {"mode": "chat", "title": "دربارهٔ ایران", "text": "دربارهٔ ایران برایم بگو"},
    {"mode": "chat", "title": "پرسش فنی", "text": "مدل زبانی چیست؟"},
    {"mode": "continue", "title": "ادامهٔ متن", "text": "در دل کویر، شب‌ها آسمان پر از ستاره است و"},
    {"mode": "poetry", "title": "بیت‌سازی", "text": ""},
]

app = FastAPI(title="پارسیا", version="1.0.0", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class HistoryTurn(BaseModel):
    user: str = Field(default="", max_length=1200)
    assistant: str = Field(default="", max_length=2400)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)
    session_id: str = Field(default="default", max_length=80)
    mode: Literal["chat", "continue", "poetry"] = "chat"
    deep: bool = False
    candidates: int = Field(default=4, ge=2, le=6)
    temperature: float | None = Field(default=None, ge=0.1, le=1.6)
    top_p: float | None = Field(default=None, ge=0.5, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=200)
    max_new_tokens: int | None = Field(default=None, ge=16, le=220)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


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
    """تاریخچهٔ ارسالی مرورگر، وگرنه تاریخچهٔ نشست سرور."""
    client = [(turn.user, turn.assistant) for turn in req.history if turn.user][-2:]
    return client or _history(req.session_id)


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
            run = json.load(open(RUN_CONFIG_PATH, encoding="utf-8"))
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
        for line in open("/proc/cpuinfo", encoding="utf-8"):
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
                print(f"[parsia] checkpoint appeared; loaded step={engine.meta.get('step')}", flush=True)
            elif engine.maybe_reload():
                print(f"[parsia] checkpoint reloaded at step {engine.meta.get('step')}", flush=True)
        except Exception as exc:  # pragma: no cover
            print(f"[parsia] reload skipped: {exc}", flush=True)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors *"
    )
    return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/favicon.svg")
def favicon() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "assets", "favicon.svg"))


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"))


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
    model = _engine()
    info = model.info()
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
            {"title": "گفتگوهای آغازین پارسیا", "detail": "۸۰ نمونهٔ دست‌نویس برای قالب گفتگو و خودشناسی"},
        ],
        "limitations": [
            "مدل فقط ۶٫۶ میلیون پارامتر دارد؛ با مدل‌های میلیاردپارامتری قابل مقایسه نیست.",
            "هیچ اتصال اینترنتی یا جست‌وجوی زنده ندارد و دانش آن از پیکرهٔ آموزش می‌آید.",
            "ممکن است جمله‌های نادرست یا تکراری بسازد؛ پاسخ‌ها را بررسی کنید.",
            "آموزش روی CPU و در چند ساعت انجام شده، نه با خوشهٔ GPU.",
            "«اندیشهٔ ژرف» جست‌وجوی چندمسیره و امتیازدهی است، نه تفکر آگاهانه.",
        ],
    }


@app.get("/api/metrics")
def metrics() -> dict:
    return _read_metrics()


@app.get("/api/showcase")
def showcase() -> dict:
    path = os.path.join(ROOT, "reports", "showcase.json")
    if not os.path.exists(path):
        return {"examples": []}
    try:
        data = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError:
        return {"examples": []}
    return {"examples": data.get("examples", []), "generated_at": data.get("generated_at")}


@app.get("/api/download/checkpoint")
def download_checkpoint() -> FileResponse:
    model = _engine()
    if not os.path.exists(model.checkpoint):
        raise HTTPException(404, "checkpoint پیدا نشد.")
    return FileResponse(
        model.checkpoint,
        media_type="application/octet-stream",
        filename="parsia-1-small.npz",
    )


@app.get("/api/samples")
def samples() -> dict:
    return {"samples": SAMPLES, "modes": list(MODES.keys())}


@app.delete("/api/session/{session_id}")
def clear_session(session_id: str) -> dict:
    with sessions_lock:
        sessions.pop(session_id, None)
    return {"ok": True}


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    global request_count
    model = _engine()
    message = _clean_message(req.message) if req.mode != "poetry" else (normalize(req.message) or "یک شعر بگو")
    history = _history_for(req) if req.mode == "chat" else []
    started = time.time()
    generation_kwargs = {
        "temperature": req.temperature,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "max_new_tokens": req.max_new_tokens,
    }
    generation_kwargs = {k: v for k, v in generation_kwargs.items() if v is not None}
    with model.lock:
        if req.deep:
            answer, generation, trace = deep_reply(
                model, message, mode=req.mode, history=history,
                n_candidates=req.candidates, **generation_kwargs,
            )
            prompt_ids, _prompt = model.build_prompt(message, req.mode, history)
        else:
            answer, generation, _prompt = model.reply(
                message, mode=req.mode, history=history,
                seed=req.seed, **generation_kwargs,
            )
            prompt_ids = model.tokenizer.encode(_prompt)
            trace = None
    if req.mode == "chat":
        _remember(req.session_id, message, answer)
    with stats_lock:
        request_count += 1
    return {
        "answer": answer,
        "mode": req.mode,
        "deep": req.deep,
        "trace": trace,
        "stats": _stats(generation, prompt_ids),
        "latency_s": round(time.time() - started, 2),
        "session_id": req.session_id,
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    global request_count
    model = _engine()
    if req.deep:
        raise HTTPException(400, "برای اندیشهٔ ژرف از /api/chat استفاده کنید.")
    message = _clean_message(req.message) if req.mode != "poetry" else (normalize(req.message) or "یک شعر بگو")
    history = _history_for(req) if req.mode == "chat" else []
    kwargs = {
        "temperature": req.temperature,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "max_new_tokens": req.max_new_tokens,
        "seed": req.seed,
    }
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
            with stats_lock:
                request_count += 1
            yield json.dumps({
                "type": "done",
                "answer": answer,
                "stats": _stats(generation, ids),
            }, ensure_ascii=False) + "\n"

    return StreamingResponse(
        generate_events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        print(f"[parsia] loaded {engine.checkpoint} | step={engine.meta.get('step')} "
              f"| params={sum(p.size for p in engine.params.values()):,}", flush=True)
    except Exception as exc:
        engine_error = str(exc)
        print(f"[parsia] model not loaded: {exc}", flush=True)
    stop = threading.Event()
    if not args.no_reload:
        threading.Thread(target=watcher, args=(stop,), daemon=True).start()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
