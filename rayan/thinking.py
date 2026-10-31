"""«اندیشهٔ ژرف» رایان — جست‌وجوی چندمسیره در زمان استنتاج.

این روش، برخلاف ادعاهای رایج، تفکر آگاهانه نیست: مدل چند پاسخ موازی تولید
می‌کند و سپس با امتیازهای واقعی (اطمینان مدل، تکرار، فارسی‌بودن و پایان جمله)
بهترین را برمی‌گزیند. همهٔ اعداد گزارش‌شده از خود مدل می‌آیند.
"""
from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass

from .generate import MODES, Engine, Generation, _ngram_repetition, polish
from .text import persian_ratio

_TEMPERATURES = [0.72, 0.84, 0.94, 0.88, 0.78, 0.9]

_FA_DIGITS = str.maketrans("0123456789.-%", "۰۱۲۳۴۵۶۷۸۹٫−٪")


def _fa_num(value: float, digits: int = 2) -> str:
    """عدد را با ارقام فارسی برای متن رابط برمی‌گرداند."""
    return f"{value:.{digits}f}".translate(_FA_DIGITS)


@dataclass
class Candidate:
    index: int
    text: str
    score: float
    confidence: float
    mean_logprob: float
    entropy: float
    repetition: float
    persian: float
    tokens: int
    seconds: float
    finish: str
    seed: int

    def to_dict(self) -> dict:
        data = asdict(self)
        data["preview"] = self.text[:90].replace("\n", " ")
        return data


def _score(generation: Generation, text: str) -> tuple[float, float]:
    repetition = _ngram_repetition(generation.tokens)
    persian = persian_ratio(text)
    ends_cleanly = text.endswith(tuple(".!؟…»\n"))
    length_factor = min(1.0, len(generation.tokens) / 30)
    too_short = 0.22 if len(generation.tokens) < 6 else 0.0
    score = (
        generation.mean_logprob
        - 0.75 * repetition
        - 0.02 * generation.mean_entropy
        + 0.15 * persian
        + 0.24 * length_factor
        + (0.12 if ends_cleanly else 0.0)
        - too_short
    )
    return float(score), float(repetition)


def deep_reply(
    engine: Engine,
    message: str,
    mode: str = "chat",
    history=None,
    n_candidates: int = 4,
    **kwargs,
):
    """چند پاسخ موازی می‌سازد، امتیاز می‌دهد و بهترین را برمی‌گرداند."""
    n_candidates = max(2, min(int(n_candidates), 6))
    ids, prompt = engine.build_prompt(message, mode, history)
    default_tokens = MODES.get(mode, MODES["chat"])["max_new_tokens"]
    max_tokens = int(kwargs.pop("max_new_tokens", default_tokens))
    kwargs.pop("temperature", None)  # دما در جست‌وجوی چندمسیره کنترل می‌شود
    base_seed = random.SystemRandom().randint(1, 2**30)
    candidates: list[Candidate] = []
    generations: dict[int, Generation] = {}
    started = time.time()

    for i in range(n_candidates):
        generation = engine.generate(
            ids,
            mode=mode,
            temperature=_TEMPERATURES[i % len(_TEMPERATURES)],
            max_new_tokens=max_tokens,
            seed=base_seed + i * 104_729,
            **kwargs,
        )
        text = polish(engine.tokenizer.decode(generation.tokens), mode)
        if not text:
            continue
        score, repetition = _score(generation, text)
        generations[i + 1] = generation
        candidates.append(Candidate(
            index=i + 1,
            text=text,
            score=round(score, 4),
            confidence=round(generation.confidence, 4),
            mean_logprob=round(generation.mean_logprob, 4),
            entropy=round(generation.mean_entropy, 4),
            repetition=round(repetition, 4),
            persian=round(persian_ratio(text), 4),
            tokens=len(generation.tokens),
            seconds=round(generation.seconds, 2),
            finish=generation.finish_reason,
            seed=generation.seed,
        ))

    if not candidates:
        return "…", None, {"candidates": [], "chosen": 0, "rationale": "پاسخی ساخته نشد."}

    best = max(candidates, key=lambda c: c.score)
    best_generation = generations[best.index]
    total = time.time() - started
    rationale = (
        f"{_fa_num(len(candidates), 0)} مسیر موازی بررسی شد؛ "
        f"مسیر {_fa_num(best.index, 0)} با امتیاز {_fa_num(best.score, 2)}، "
        f"اطمینان {_fa_num(best.confidence * 100, 0)}٪ و تکرار {_fa_num(best.repetition * 100, 0)}٪ انتخاب شد. "
        f"مجموع زمان: {_fa_num(total, 1)} ثانیه."
    )
    trace = {
        "candidates": [c.to_dict() for c in candidates],
        "chosen": best.index,
        "rationale": rationale,
        "total_seconds": round(total, 2),
        "method": "best-of-N + self-scoring",
    }
    return best.text, best_generation, trace
