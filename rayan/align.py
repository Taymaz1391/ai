"""هم‌ترازی رایان با روش InstructGPT — سه مرحله، بدون کتابخانهٔ بیرونی.

| مرحله | در InstructGPT | این‌جا |
|---|---|---|
| ۱ | SFT روی نمایش‌های انسانی (~۱۳ هزار) | `sft_step` روی زوج‌های پرسش–پاسخ فارسی |
| ۲ | مدل پاداش با مقایسهٔ زوجی (Bradley–Terry) | `RewardModel` روی ویژگی‌های لایهٔ آخر مدلِ ثابت |
| ۳ | PPO با مدل پاداش | **DPO**: بهینه‌سازی مستقیم ترجیح، بدون حلقهٔ RL |

DPO به‌جای PPO انتخاب شده چون نیازی به چهار مدل هم‌زمان، critic و حلقهٔ نمونه‌گیری
ندارد و با دو vCPU و ۳ گیگابایت رم اجرا می‌شود؛ هدف ریاضی‌اش همان است: احتمال مدل
برای پاسخِ ترجیح‌داده‌شده بالا برود و برای پاسخِ رد‌شده پایین بیاید، با جریمهٔ KL ضمنی
نسبت به مدل مرجع.

نکتهٔ صادقانه: ترجیح‌ها در این پروژه از **داور خودکار** (rubric) می‌آیند، نه از
برچسب‌گذار انسانی؛ همان کاری که در RLAIF/Constitutional AI انجام می‌شود. با ۲ vCPU
نمی‌توان ۳۳ هزار مقایسهٔ انسانی جمع کرد، ولی می‌توان همان ریاضیات را روی ترجیح‌های
قابل‌بازتولید اجرا کرد.
"""
from __future__ import annotations

import json
import math
import os
import time

import numpy as np

from .model import GPTConfig, AdamW, backward, forward, load_checkpoint

PROMPT_TEMPLATE = "<|doc|> <|user|> {user} <|bot|> "
# توکن پایان نوبت: مدل یاد می‌گیرد بعد از پاسخ، خودش گفتگو را ببندد
TURN_END = " <|doc|>"


# ------------------------------------------------------------------ داده
def example_ids(tokenizer, user: str, assistant: str, block_size: int = 256,
                close_turn: bool = True) -> tuple[list[int], int] | None:
    """(شناسه‌ها، طول پرسش) برای یک زوج پرسش–پاسخ؛ اگر بلند بود None."""
    prompt = PROMPT_TEMPLATE.format(user=user.strip())
    answer = assistant.strip() + (TURN_END if close_turn else "")
    prompt_ids = tokenizer.encode(prompt)
    answer_ids = tokenizer.encode(answer)
    ids = prompt_ids + answer_ids
    if len(ids) > block_size or len(answer_ids) < 2:
        return None
    return ids, len(prompt_ids)


def load_pairs(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("user") and row.get("assistant"):
                rows.append({"user": row["user"], "assistant": row["assistant"]})
    return rows


def load_preferences(path: str) -> list[dict]:
    """زوج‌های ترجیح (پرسش، پاسخ برنده، پاسخ بازنده) با پالایش سطرهای ناقص."""
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("user") and row.get("chosen") and row.get("rejected"):
                rows.append(row)
    return rows


# ------------------------------------------------------------------ احتمالات
def _log_softmax(x: np.ndarray) -> np.ndarray:
    shifted = x - x.max(-1, keepdims=True)
    return shifted - np.log(np.exp(shifted).sum(-1, keepdims=True))


def sequence_logprob(params: dict, cfg: GPTConfig, ids: list[int], prompt_len: int,
                     keep_cache: bool = False) -> tuple[float, dict | None, np.ndarray, np.ndarray]:
    """مجموع log p برای توکن‌های پاسخ (نه میانگین) و کش لازم برای پس‌انتشار."""
    arr = np.asarray([ids], dtype=np.int64)
    if keep_cache:
        logits, _loss, cache = forward(params, cfg, arr, None, keep_cache=True)
    else:
        logits, _loss = forward(params, cfg, arr, None)
        cache = None
    logits = logits[0]
    n = len(ids) - prompt_len
    if n <= 0:
        raise ValueError("پاسخ خالی است")
    pred = logits[prompt_len - 1:len(ids) - 1]
    targets = np.asarray(ids[prompt_len:], dtype=np.int64)
    logp = _log_softmax(pred)
    total = float(logp[np.arange(n), targets].sum())
    return total, cache, logp, targets


def answer_features(params: dict, cfg: GPTConfig, ids: list[int], prompt_len: int) -> np.ndarray:
    """میانگین حالت پنهان لایهٔ آخر روی توکن‌های پاسخ (ویژگی مدل پاداش)."""
    arr = np.asarray([ids], dtype=np.int64)
    _logits, _loss, cache = forward(params, cfg, arr, None, keep_cache=True)
    hidden = cache["xhatf"][0]  # (T, C) پس از لایه‌نرم نهایی
    span = hidden[prompt_len - 1:len(ids) - 1]
    if span.size == 0:
        span = hidden[-1:]
    return span.mean(0).astype(np.float64)


# ------------------------------------------------------------------ مرحلهٔ ۱: SFT
def sft_step(params: dict, cfg: GPTConfig, optimizer: AdamW,
             batch: list[tuple[list[int], int]], answer_only: bool = True) -> float:
    """یک گام تنظیم دستورمحور؛ زیان فقط روی توکن‌های پاسخ.

    مثل InstructGPT، توکن‌های پرسش در زیان شمرده نمی‌شوند؛ وگرنه مدل بخشی از
    ظرفیتش را صرف بازتولید متن کاربر می‌کند و «پاسخ‌دادن» را کمتر یاد می‌گیرد.
    """
    total_grads: dict[str, np.ndarray] | None = None
    total_tokens = 0
    total_loss = 0.0
    for ids, prompt_len in batch:
        arr = np.asarray([ids], dtype=np.int64)
        # ورودی x = توکن‌های ۰..T-۲ و هدف y = توکن‌های ۱..T-۱ (پیش‌بینی توکن بعدی)
        x = arr[:, :-1]
        logits, _, cache = forward(params, cfg, x, None, keep_cache=True)
        start = max(0, prompt_len - 1) if answer_only else 0
        targets = np.asarray(ids[start + 1:], dtype=np.int64)
        n = int(targets.size)
        if n <= 0:
            continue
        pred = logits[0, start:len(ids) - 1]
        logp = _log_softmax(pred)
        rows = np.arange(n)
        total_loss += float(-logp[rows, targets].sum())
        total_tokens += n
        dlogits = np.zeros_like(logits)
        block = dlogits[0, start:start + n]
        block += np.exp(logp) / n
        block[rows, targets] -= 1.0 / n
        grads = backward(params, cfg, {**cache, "dlogits": dlogits})
        if total_grads is None:
            total_grads = {k: v * n for k, v in grads.items()}
        else:
            for key, value in grads.items():
                total_grads[key] += value * n
    if total_grads is None:
        return float("nan")
    for key in total_grads:
        total_grads[key] /= max(1, total_tokens)
    optimizer.step(params, total_grads)
    return total_loss / max(1, total_tokens)


# ------------------------------------------------------------------ مرحلهٔ ۲: مدل پاداش
class RewardModel:
    """پاداش = w·φ + b روی ویژگی‌های مدل پایه، آموزش‌دیده با زیان Bradley–Terry.

    این همان ایدهٔ مدل پاداش InstructGPT در مقیاس کوچک است: یک سر خطی روی بازنمایی
    مدل ثابت، نه یک شبکهٔ بزرگ جداگانه. ``φ`` میانگین حالت پنهان لایهٔ آخر است.
    """

    def __init__(self, dim: int, seed: int = 7) -> None:
        rng = np.random.default_rng(seed)
        self.w = rng.normal(0.0, 0.01, size=dim)
        self.b = 0.0

    # ------------------------------------------------------------- پیش‌بینی
    def score(self, features: np.ndarray) -> float:
        return float(features @ self.w + self.b)

    def scores(self, matrix: np.ndarray) -> np.ndarray:
        return matrix @ self.w + self.b

    # ------------------------------------------------------------- آموزش
    def fit(self, chosen: np.ndarray, rejected: np.ndarray, *, epochs: int = 400,
            lr: float = 3e-2, l2: float = 1e-3, verbose: bool = False) -> dict:
        """آموزش با گرادیان دسته‌ای روی زوج‌های ({φ_برنده}, {φ_بازنده})."""
        if len(chosen) == 0:
            raise ValueError("هیچ زوجی برای آموزش مدل پاداش نیست")
        history: list[float] = []
        m_w = np.zeros_like(self.w)
        v_w = np.zeros_like(self.w)
        m_b = v_b = 0.0
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        for epoch in range(1, epochs + 1):
            diff = self.scores(chosen) - self.scores(rejected)
            # σ(-x) = 1 - σ(x) با پایدارسازی
            p = 1.0 / (1.0 + np.exp(-diff))
            loss = float(-np.log(np.clip(p, 1e-9, 1.0)).mean())
            history.append(loss)
            g = (p - 1.0) / len(diff)          # dL/d(diff)
            gw = g @ (chosen - rejected) + l2 * self.w
            gb = float(g.sum())
            m_w = beta1 * m_w + (1 - beta1) * gw
            v_w = beta2 * v_w + (1 - beta2) * (gw ** 2)
            m_b = beta1 * m_b + (1 - beta1) * gb
            v_b = beta2 * v_b + (1 - beta2) * (gb ** 2)
            mw_hat = m_w / (1 - beta1 ** epoch)
            vw_hat = v_w / (1 - beta2 ** epoch)
            self.w -= lr * mw_hat / (np.sqrt(vw_hat) + eps)
            self.b -= lr * (m_b / (1 - beta1 ** epoch)) / (
                math.sqrt(v_b / (1 - beta2 ** epoch)) + eps)
            if verbose and epoch % 100 == 0:
                print(f"  reward epoch {epoch:4d} | loss {loss:.4f}", flush=True)
        accuracy = float((diff > 0).mean())
        return {"loss_start": history[0], "loss_end": history[-1],
                "accuracy": accuracy, "pairs": int(len(diff))}

    def evaluate(self, chosen: np.ndarray, rejected: np.ndarray) -> dict:
        diff = self.scores(chosen) - self.scores(rejected)
        p = 1.0 / (1.0 + np.exp(-diff))
        return {"accuracy": float((diff > 0).mean()),
                "margin_mean": float(diff.mean()),
                "logloss": float(-np.log(np.clip(p, 1e-9, 1.0)).mean())}

    # ------------------------------------------------------------- ذخیره
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        np.savez(path, w=self.w, b=np.asarray(self.b))

    @classmethod
    def load(cls, path: str) -> "RewardModel":
        data = np.load(path)
        model = cls(dim=int(data["w"].shape[0]))
        model.w = data["w"].astype(np.float64)
        model.b = float(data["b"])
        return model


# ------------------------------------------------------------------ مرحلهٔ ۳: DPO
def dpo_loss_grads(policy: dict, reference: dict, cfg: GPTConfig,
                   chosen: list[int], rejected: list[int], prompt_len: int,
                   beta: float = 0.1, need_grads: bool = True) -> dict:
    """زیان DPO و گرادیانش روی پارامترهای سیاست.

    L = -log σ(β[(log π(y_w) − log π_ref(y_w)) − (log π(y_l) − log π_ref(y_l))])

    گرادیان نسبت به logits: برای پاسخ برنده ``βσ(−z)(softmax − onehot)`` و برای
    پاسخ بازنده با علامت مخالف. چون ``backward`` گرادیان را جمع می‌زند، ضریب‌ها
    همین‌جا اعمال می‌شوند.
    """
    lw, cache_w, logp_w, targets_w = sequence_logprob(
        policy, cfg, chosen, prompt_len, keep_cache=need_grads)
    ll, cache_l, logp_l, targets_l = sequence_logprob(
        policy, cfg, rejected, prompt_len, keep_cache=need_grads)
    ref_w = sequence_logprob(reference, cfg, chosen, prompt_len)[0]
    ref_l = sequence_logprob(reference, cfg, rejected, prompt_len)[0]
    margin = (lw - ref_w) - (ll - ref_l)
    z = beta * margin
    # -log σ(z) = log(1+exp(-z))، پایدار
    if z >= 0:
        loss = float(math.log1p(math.exp(-z)))
        sigma_neg = math.exp(-z) / (1 + math.exp(-z))       # σ(−z)
    else:
        loss = float(-z + math.log1p(math.exp(z)))
        sigma_neg = 1.0 / (1 + math.exp(z))                 # σ(−z)
    out = {"loss": loss, "margin": float(margin), "logp_chosen": lw, "logp_rejected": ll,
           "ref_chosen": ref_w, "ref_rejected": ref_l,
           "prefers_chosen": bool(lw > ll)}
    if not need_grads:
        return out

    coef_w = beta * sigma_neg
    coef_l = -beta * sigma_neg
    dlogits_w = np.zeros((1, len(chosen), cfg.vocab_size), dtype=np.float64)
    dlogits_l = np.zeros((1, len(rejected), cfg.vocab_size), dtype=np.float64)
    start = prompt_len - 1
    n_w = len(chosen) - prompt_len
    block_w = dlogits_w[0, start:start + n_w]
    block_w += coef_w * np.exp(logp_w)
    block_w[np.arange(n_w), targets_w] -= coef_w
    n_l = len(rejected) - prompt_len
    block_l = dlogits_l[0, start:start + n_l]
    block_l += coef_l * np.exp(logp_l)
    block_l[np.arange(n_l), targets_l] -= coef_l

    grads = backward(policy, cfg, {**cache_w, "dlogits": dlogits_w})
    grads_l = backward(policy, cfg, {**cache_l, "dlogits": dlogits_l})
    for key in grads:
        grads[key] += grads_l[key]
    out["grads"] = grads
    return out


# ------------------------------------------------------------------ گزارش
def summarize(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    arr = np.asarray(values, dtype=np.float64)
    return {"n": int(arr.size), "mean": float(arr.mean()),
            "min": float(arr.min()), "max": float(arr.max())}


def save_report(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {**payload, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def load_base(path: str) -> tuple[GPTConfig, dict]:
    """بارگذاری checkpoint پایه (همان چیزی که سایت سرو می‌کند)."""
    cfg, params, _meta = load_checkpoint(path)
    return cfg, params
