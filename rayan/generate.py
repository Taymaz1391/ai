"""موتور استنتاج رایان: بارگذاری مدل، تولید متن، گفتگو و ادامهٔ متن."""
from __future__ import annotations

import math
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from .model import GPTConfig, InferenceModel, load_checkpoint, sample_from_logits
from .text import normalize, prepare_user_input, persian_ratio
from .tokenizer import SPECIAL_TOKENS, BPETokenizer

MODES = {
    "chat": {
        "temperature": 0.82, "top_p": 0.90, "top_k": 40,
        "repetition_penalty": 1.15, "max_new_tokens": 110,
        "min_new_tokens": 6,  # جلوگیری از پاسخ‌های یک‌کلمه‌ای
    },
    "continue": {
        "temperature": 0.85, "top_p": 0.92, "top_k": 40,
        "repetition_penalty": 1.05, "max_new_tokens": 140,
    },
    "poetry": {
        "temperature": 0.92, "top_p": 0.95, "top_k": 50,
        "repetition_penalty": 1.06, "max_new_tokens": 120,
    },
}

_PUNCT_END = "،؛.!؟…»)\n"


@dataclass
class Generation:
    tokens: list[int]
    logprobs: list[float]
    entropies: list[float]
    finish_reason: str
    seconds: float = 0.0
    seed: int = 0

    @property
    def mean_logprob(self) -> float:
        return float(np.mean(self.logprobs)) if self.logprobs else -99.0

    @property
    def mean_entropy(self) -> float:
        return float(np.mean(self.entropies)) if self.entropies else 0.0

    @property
    def tokens_per_second(self) -> float:
        return len(self.tokens) / max(1e-6, self.seconds)

    @property
    def confidence(self) -> float:
        """اطمینان تقریبی: میانگین احتمال توکن‌های انتخاب‌شده."""
        return float(math.exp(self.mean_logprob)) if self.logprobs else 0.0


def _trim_to_sentence(text: str) -> str:
    """اگر جملهٔ آخر نیمه‌کاره است، تا آخرین پایان جملهٔ کامل کوتاه می‌کند."""
    stripped = text.rstrip()
    if not stripped or stripped[-1] in _PUNCT_END:
        return stripped
    cut = max(stripped.rfind(ch) for ch in ".!؟…")
    if cut > 28 and cut > len(stripped) - 45:
        return stripped[:cut + 1].strip()
    last_space = stripped.rfind(" ")
    if last_space > 20:
        return stripped[:last_space].rstrip() + "…"
    return stripped


def polish(text: str, mode: str = "chat") -> str:
    text = text.replace("</w>", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\s+([،؛:.!؟])", r"\1", text)
    text = re.sub(r"([«(])\s+", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    text = re.sub(r"^[<|>]+\s*", "", text)
    if mode == "chat":
        text = _trim_to_sentence(text)
    return text.strip()


def _ngram_repetition(tokens: list[int], n: int = 4) -> float:
    if len(tokens) < n * 2:
        return 0.0
    grams = [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]
    return 1.0 - len(set(grams)) / len(grams)


class Engine:
    """نگه‌دارندهٔ مدل در حافظه با امکان بارگذاری دوباره (هات‌ریلود)."""

    def __init__(self, checkpoint: str, tokenizer_path: str):
        self.checkpoint = checkpoint
        self.tokenizer_path = tokenizer_path
        self.lock = threading.Lock()
        self.tokenizer = BPETokenizer.load(tokenizer_path)
        self.cfg, self.params, self.meta = load_checkpoint(checkpoint)
        if self.cfg.vocab_size != self.tokenizer.vocab_size:
            raise ValueError("tokenizer/checkpoint vocabulary mismatch")
        self.model = InferenceModel(self.cfg, self.params)
        self.loaded_at = time.time()
        self.mtime = os.path.getmtime(checkpoint)
        self.special = self.tokenizer.special_ids
        self.generations = 0

    # ------------------------------------------------------------- بارگذاری
    def maybe_reload(self) -> bool:
        try:
            mtime = os.path.getmtime(self.checkpoint)
        except OSError:
            return False
        if mtime <= self.mtime + 1e-6 or time.time() - mtime < 2.0:
            return False
        with self.lock:
            try:
                cfg, params, meta = load_checkpoint(self.checkpoint)
            except Exception:
                return False
            if cfg.vocab_size != self.tokenizer.vocab_size:
                return False
            self.cfg, self.params, self.meta = cfg, params, meta
            self.model = InferenceModel(cfg, params)
            self.mtime = mtime
            self.loaded_at = time.time()
        return True

    # ------------------------------------------------------------- تولید متن
    def _stop_ids(self, mode: str) -> set[int]:
        stop = {self.special["<|doc|>"], self.special["<|user|>"], self.special["<|bot|>"]}
        return stop

    def generate(
        self,
        prompt_ids: list[int],
        *,
        mode: str = "chat",
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        repetition_penalty: float | None = None,
        max_new_tokens: int | None = None,
        min_new_tokens: int | None = None,
        seed: int | None = None,
        on_token=None,
    ) -> Generation:
        base = MODES.get(mode, MODES["chat"])
        temperature = base["temperature"] if temperature is None else temperature
        top_p = base["top_p"] if top_p is None else top_p
        top_k = base["top_k"] if top_k is None else top_k
        repetition_penalty = base["repetition_penalty"] if repetition_penalty is None else repetition_penalty
        max_new_tokens = base["max_new_tokens"] if max_new_tokens is None else max_new_tokens
        min_new_tokens = base.get("min_new_tokens", 0) if min_new_tokens is None else min_new_tokens
        seed = int(time.time_ns() % 2**31) if seed is None else int(seed)

        cfg = self.cfg
        max_new_tokens = max(1, min(int(max_new_tokens), 220, cfg.block_size))
        prompt = list(prompt_ids)
        keep = max(8, cfg.block_size - max_new_tokens)
        if len(prompt) > keep:
            prompt = prompt[-keep:]
        start = time.time()
        rng = np.random.default_rng(seed)
        stop_ids = self._stop_ids(mode)
        logits, kv = self.model.logits_for_prompt(prompt)
        out_tokens: list[int] = []
        logprobs: list[float] = []
        entropies: list[float] = []
        finish = "length"
        recent = prompt[-48:]
        for i in range(max_new_tokens):
            step_logits = logits
            if i < min_new_tokens:
                step_logits = logits.copy()
                step_logits[list(stop_ids)] = -1e9
            token, lp, entropy = sample_from_logits(
                step_logits, rng, temperature=temperature, top_k=top_k, top_p=top_p,
                recent=recent, repetition_penalty=repetition_penalty,
            )
            if token in stop_ids:
                finish = "stop"
                break
            out_tokens.append(token)
            if on_token is not None:
                on_token(self.tokenizer.decode([token], skip_specials=True))
            logprobs.append(lp)
            entropies.append(entropy)
            recent = (recent + [token])[-64:]
            pos = len(prompt) + i
            if pos + 1 >= cfg.block_size:
                finish = "context"
                break
            logits, kv = self.model.next_logits(token, pos, kv)
        self.generations += 1
        return Generation(
            tokens=out_tokens, logprobs=logprobs, entropies=entropies,
            finish_reason=finish, seconds=time.time() - start, seed=seed,
        )

    # --------------------------------------------------------------- قالب‌ها
    def build_prompt(self, message: str, mode: str = "chat",
                     history: list[tuple[str, str]] | None = None) -> tuple[list[int], str]:
        doc = "<|doc|> "
        if mode == "chat":
            parts = [doc]
            for user, bot in (history or [])[-2:]:
                parts.append(f"<|user|> {normalize(user)} <|bot|> {normalize(bot)} ")
            parts.append(f"<|user|> {prepare_user_input(message)} <|bot|> ")
            prompt = "".join(parts)
        elif mode == "poetry":
            prompt = f"{doc}<|user|> یک شعر بگو <|bot|> "
        else:
            prompt = f"{doc}{normalize(message)} "
        return self.tokenizer.encode(prompt), prompt

    def reply(self, message: str, mode: str = "chat", history=None, **kwargs):
        ids, prompt = self.build_prompt(message, mode, history)
        generation = self.generate(ids, mode=mode, **kwargs)
        text = polish(self.tokenizer.decode(generation.tokens), mode)
        if not text:
            text = "…"
        return text, generation, prompt

    def stream(self, prompt_ids: list[int], **kwargs) -> "StreamSession":
        return StreamSession(self, prompt_ids, **kwargs)

    # -------------------------------------------------------------- اطلاعات
    def info(self) -> dict:
        meta = dict(self.meta)
        return {
            "name": "رایان ۱ — کوچک",
            "params": int(sum(p.size for p in self.params.values())),
            "config": self.cfg.to_dict(),
            "tokenizer": self.tokenizer.stats(),
            "meta": meta,
            "generations": self.generations,
            "loaded_at": self.loaded_at,
            "checkpoint_mtime": self.mtime,
            "architecture": "decoder-only Transformer · NumPy · manual backprop",
            "specials": list(SPECIAL_TOKENS),
        }


class StreamSession:
    """تولید در یک رشتهٔ جدا تا توکن‌ها هم‌زمان به مرورگر فرستاده شوند."""

    def __init__(self, engine: Engine, prompt_ids: list[int], **kwargs):
        self.engine = engine
        self.prompt_ids = prompt_ids
        self.kwargs = kwargs
        self.result: Generation | None = None
        self._q: queue.Queue = queue.Queue()

    def _run(self) -> None:
        try:
            self.result = self.engine.generate(
                self.prompt_ids, on_token=lambda piece: self._q.put(("token", piece)), **self.kwargs
            )
        except Exception as exc:  # pragma: no cover - به کلاینت گزارش می‌شود
            self._q.put(("error", repr(exc)))
        finally:
            self._q.put(("end", None))

    def __iter__(self):
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        while True:
            kind, payload = self._q.get()
            if kind == "end":
                break
            if kind == "error":
                raise RuntimeError(payload)
            yield payload
