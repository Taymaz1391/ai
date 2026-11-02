"""ترنسفورمر رمزگشا (decoder-only) از صفر، تنها با NumPy.

هیچ framework یادگیری عمیقی استفاده نشده است: پیش‌رو، پس‌رو و بهینه‌ساز
همگی در همین فایل پیاده شده‌اند. پارامترها برای سادگی در یک dict نگه داشته
می‌شوند. مدل کوچک است تا روی CPU هم قابل آموزش باشد.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field

import numpy as np

LN_EPS = 1e-5
GELU_C = math.sqrt(2.0 / math.pi)


@dataclass
class GPTConfig:
    vocab_size: int = 10_000
    block_size: int = 256
    n_layer: int = 5
    n_head: int = 4
    n_embd: int = 256

    @property
    def head_dim(self) -> int:
        assert self.n_embd % self.n_head == 0
        return self.n_embd // self.n_head

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------- ابزار
def softmax(x: np.ndarray, axis: int = -1) -> np.ndarray:
    x = x - x.max(axis=axis, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=axis, keepdims=True)


def layernorm_forward(x: np.ndarray, g: np.ndarray, b: np.ndarray):
    mean = x.mean(-1, keepdims=True)
    var = x.var(-1, keepdims=True)
    rstd = 1.0 / np.sqrt(var + LN_EPS)
    xhat = (x - mean) * rstd
    return xhat * g + b, xhat, mean, rstd


def layernorm_backward(dy: np.ndarray, xhat: np.ndarray, rstd: np.ndarray, g: np.ndarray):
    dg = (dy * xhat).reshape(-1, dy.shape[-1]).sum(0)
    db = dy.reshape(-1, dy.shape[-1]).sum(0)
    dxhat = dy * g
    dx = rstd * (
        dxhat
        - dxhat.mean(-1, keepdims=True)
        - xhat * (dxhat * xhat).mean(-1, keepdims=True)
    )
    return dx, dg, db


def silu_forward(x: np.ndarray):
    """SiLU: x·sigmoid(x) — فعال‌ساز سریع و پرکاربرد در مدل‌های امروزی."""
    sig = 1.0 / (1.0 + np.exp(-x))
    return x * sig, sig


def silu_backward(dy: np.ndarray, x: np.ndarray, sig: np.ndarray) -> np.ndarray:
    return dy * (sig * (1.0 + x * (1.0 - sig)))


# ---------------------------------------------------------------- ساخت پارامتر
def param_shapes(cfg: GPTConfig) -> dict[str, tuple[int, ...]]:
    C, H, F = cfg.n_embd, cfg.n_head, cfg.head_dim
    shapes: dict[str, tuple[int, ...]] = {
        "wte": (cfg.vocab_size, C),
        "wpe": (cfg.block_size, C),
        "lnf_g": (C,),
        "lnf_b": (C,),
    }
    for i in range(cfg.n_layer):
        p = f"h{i}."
        shapes.update({
            p + "ln1_g": (C,), p + "ln1_b": (C,),
            p + "qkv_w": (C, 3 * C), p + "qkv_b": (3 * C,),
            p + "attn_w": (C, C), p + "attn_b": (C,),
            p + "ln2_g": (C,), p + "ln2_b": (C,),
            p + "mlp1_w": (C, 4 * C), p + "mlp1_b": (4 * C,),
            p + "mlp2_w": (4 * C, C), p + "mlp2_b": (C,),
        })
    return shapes


def init_params(cfg: GPTConfig, seed: int = 1337, dtype=np.float32) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    params: dict[str, np.ndarray] = {}
    for name, shape in param_shapes(cfg).items():
        if name.endswith(("_g",)):
            params[name] = np.ones(shape, dtype=dtype)
        elif name.endswith(("_b",)):
            params[name] = np.zeros(shape, dtype=dtype)
        else:
            scale = 0.02
            if name.endswith(("attn_w", "mlp2_w")):
                scale /= math.sqrt(2 * cfg.n_layer)
            params[name] = (rng.standard_normal(shape) * scale).astype(dtype)
    return params


def count_params(params: dict[str, np.ndarray]) -> int:
    return int(sum(p.size for p in params.values()))


# ------------------------------------------------------------------- پیش‌رو
def _attention_forward(x, params, prefix, cfg):
    B, T, C = x.shape
    H, hd = cfg.n_head, cfg.head_dim
    qkv = x @ params[prefix + "qkv_w"] + params[prefix + "qkv_b"]
    q, k, v = np.split(qkv, 3, axis=-1)
    q = q.reshape(B, T, H, hd).transpose(0, 2, 1, 3)
    k = k.reshape(B, T, H, hd).transpose(0, 2, 1, 3)
    v = v.reshape(B, T, H, hd).transpose(0, 2, 1, 3)
    scale = 1.0 / math.sqrt(hd)
    scores = (q @ k.transpose(0, 1, 3, 2)) * scale
    causal = np.tril(np.ones((T, T), dtype=bool))
    scores = np.where(causal, scores, -np.inf)
    attn = softmax(scores, -1)
    out = (attn @ v).transpose(0, 2, 1, 3).reshape(B, T, C)
    y = out @ params[prefix + "attn_w"] + params[prefix + "attn_b"]
    return y, (x, q, k, v, attn, out, scale)


def _attention_backward(dy, cache, params, prefix, cfg, grads):
    x_in, q, k, v, attn, out, scale = cache
    B, T, C = dy.shape
    H, hd = cfg.n_head, cfg.head_dim
    # لایهٔ خروجی
    grads[prefix + "attn_w"] += out.reshape(-1, C).T @ dy.reshape(-1, C)
    grads[prefix + "attn_b"] += dy.sum((0, 1))
    dout = dy @ params[prefix + "attn_w"].T
    dA = dout.reshape(B, T, H, hd).transpose(0, 2, 1, 3)          # (B,H,T,hd)
    dv = attn.transpose(0, 1, 3, 2) @ dA                           # (B,H,T,hd)
    dscores = dA @ v.transpose(0, 1, 3, 2)                         # (B,H,T,T)
    # پس‌روی softmax
    dscores = attn * (dscores - (dscores * attn).sum(-1, keepdims=True))
    dq = (dscores @ k) * scale                                     # (B,H,T,hd)
    dk = (dscores.transpose(0, 1, 3, 2) @ q) * scale               # (B,H,T,hd)
    dq = dq.transpose(0, 2, 1, 3).reshape(B, T, C)
    dk = dk.transpose(0, 2, 1, 3).reshape(B, T, C)
    dv = dv.transpose(0, 2, 1, 3).reshape(B, T, C)
    dqkv = np.concatenate([dq, dk, dv], axis=-1)
    grads[prefix + "qkv_w"] += x_in.reshape(-1, C).T @ dqkv.reshape(-1, 3 * C)
    grads[prefix + "qkv_b"] += dqkv.sum((0, 1))
    dx = dqkv @ params[prefix + "qkv_w"].T
    return dx


def forward(params: dict, cfg: GPTConfig, idx: np.ndarray, targets: np.ndarray | None = None,
            keep_cache: bool = False):
    """پیش‌روی کامل روی دنباله. idx: (B,T) از شناسه‌های توکن."""
    B, T = idx.shape
    if T > cfg.block_size:
        raise ValueError(f"sequence length {T} > block_size {cfg.block_size}")
    C = cfg.n_embd
    x = params["wte"][idx] + params["wpe"][:T][None, :, :]
    cache = {"idx": idx, "x0": x, "layers": []}
    for i in range(cfg.n_layer):
        p = f"h{i}."
        ln1, xhat1, mean1, rstd1 = layernorm_forward(x, params[p + "ln1_g"], params[p + "ln1_b"])
        attn_y, attn_cache = _attention_forward(ln1, params, p, cfg)
        x = x + attn_y
        x_attn = x
        ln2, xhat2, mean2, rstd2 = layernorm_forward(x, params[p + "ln2_g"], params[p + "ln2_b"])
        hidden = ln2 @ params[p + "mlp1_w"] + params[p + "mlp1_b"]
        act, sig = silu_forward(hidden)
        mlp_y = act @ params[p + "mlp2_w"] + params[p + "mlp2_b"]
        x = x + mlp_y
        if keep_cache:
            cache["layers"].append({
                "xhat1": xhat1, "rstd1": rstd1, "attn": attn_cache,
                "xhat2": xhat2, "rstd2": rstd2, "hidden": hidden, "act": act, "sig": sig,
            })
    xf, xhatf, meanf, rstdf = layernorm_forward(x, params["lnf_g"], params["lnf_b"])
    logits = xf @ params["wte"].T
    loss = None
    if targets is not None:
        flat = logits.reshape(-1, logits.shape[-1])
        n = targets.size
        flat_targets = targets.reshape(-1)
        row_max = flat.max(-1, keepdims=True)
        probs = np.exp(flat - row_max)
        normalizer = probs.sum(-1, keepdims=True)
        logsumexp = np.log(normalizer) + row_max
        loss = float((logsumexp[:, 0] - flat[np.arange(n), flat_targets]).mean())
        probs /= normalizer
        probs[np.arange(n), flat_targets] -= 1.0
        probs /= n  # گرادیان میانگین، بدون آرایهٔ اضافی
        dlogits = probs.reshape(logits.shape)
    else:
        dlogits = None
    if keep_cache:
        cache.update({"xhatf": xhatf, "rstdf": rstdf, "dlogits": dlogits})
        return logits, loss, cache
    return logits, loss


def backward(params: dict, cfg: GPTConfig, cache: dict, need_grads: bool = True) -> dict:
    """پس‌انتشار دستی از dlogits تا تمام پارامترها."""
    grads = {k: np.zeros_like(v) for k, v in params.items()} if need_grads else {}
    dlogits = cache["dlogits"]
    xhatf, rstdf = cache["xhatf"], cache["rstdf"]
    dxf = dlogits @ params["wte"]
    grads["wte"] += dlogits.reshape(-1, dlogits.shape[-1]).T @ xhatf.reshape(-1, cfg.n_embd)
    dx, grads["lnf_g"], grads["lnf_b"] = layernorm_backward(dxf, xhatf, rstdf, params["lnf_g"])

    for i in reversed(range(cfg.n_layer)):
        p = f"h{i}."
        c = cache["layers"][i]
        # شاخهٔ MLP
        grads[p + "mlp2_w"] += c["act"].reshape(-1, 4 * cfg.n_embd).T @ dx.reshape(-1, cfg.n_embd)
        grads[p + "mlp2_b"] += dx.sum((0, 1))
        dact = dx @ params[p + "mlp2_w"].T
        dhidden = silu_backward(dact, c["hidden"], c["sig"])
        grads[p + "mlp1_w"] += c["xhat2"].reshape(-1, cfg.n_embd).T @ dhidden.reshape(-1, 4 * cfg.n_embd)
        grads[p + "mlp1_b"] += dhidden.sum((0, 1))
        dln2 = dhidden @ params[p + "mlp1_w"].T
        dx_pre, grads[p + "ln2_g"], grads[p + "ln2_b"] = layernorm_backward(
            dln2, c["xhat2"], c["rstd2"], params[p + "ln2_g"])
        dx = dx + dx_pre
        # شاخهٔ توجه
        dattn = _attention_backward(dx, c["attn"], params, p, cfg, grads)
        dx_pre, grads[p + "ln1_g"], grads[p + "ln1_b"] = layernorm_backward(
            dattn, c["xhat1"], c["rstd1"], params[p + "ln1_g"])
        dx = dx + dx_pre

    idx = cache["idx"]
    np.add.at(grads["wte"], idx.reshape(-1), dx.reshape(-1, cfg.n_embd))
    np.add.at(grads["wpe"], np.arange(idx.shape[1]), dx.sum(0))
    return grads


# ----------------------------------------------------------------- بهینه‌ساز
class AdamW:
    def __init__(self, params: dict, lr: float = 1e-3, betas=(0.9, 0.95),
                 eps: float = 1e-8, weight_decay: float = 0.1, grad_clip: float = 1.0):
        self.lr = lr
        self.beta1, self.beta2 = betas
        self.eps = eps
        self.weight_decay = weight_decay
        self.grad_clip = grad_clip
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}
        self.t = 0

    def step(self, params: dict, grads: dict) -> float:
        self.t += 1
        # برش نرم گرادیان
        total_sq = 0.0
        for g in grads.values():
            total_sq += float(np.square(g).sum(dtype=np.float64))
        total = math.sqrt(total_sq)
        clip = self.grad_clip / (total + 1e-6) if total > self.grad_clip else 1.0
        lr_t = self.lr * math.sqrt(1 - self.beta2 ** self.t) / (1 - self.beta1 ** self.t)
        for k, p in params.items():
            g = grads[k] * clip
            if p.ndim >= 2 and self.weight_decay:
                p -= self.lr * self.weight_decay * p
            self.m[k] = self.beta1 * self.m[k] + (1 - self.beta1) * g
            self.v[k] = self.beta2 * self.v[k] + (1 - self.beta2) * (g * g)
            p -= lr_t * self.m[k] / (np.sqrt(self.v[k]) + self.eps)
        return total


# ------------------------------------------------------------------- ذخیره
def save_checkpoint(path: str, cfg: GPTConfig, params: dict, meta: dict | None = None) -> None:
    arrays = {k: v for k, v in params.items()}
    arrays["__config__"] = np.array(json.dumps(cfg.to_dict(), ensure_ascii=False))
    arrays["__meta__"] = np.array(json.dumps(meta or {}, ensure_ascii=False))
    # نوشتن در فایل موقت و جای‌گزینی اتمیک: وب‌سرور ممکن است همین لحظه در حال خواندن باشد
    tmp = f"{path}.{os.getpid()}.tmp.npz"  # پسوند .npz لازم است وگرنه numpy یکی اضافه می‌کند
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)


def load_checkpoint(path: str):
    data = np.load(path, allow_pickle=False)
    cfg = GPTConfig(**json.loads(str(data["__config__"])))
    meta = json.loads(str(data["__meta__"])) if "__meta__" in data else {}
    params = {k: data[k] for k in data.files if not k.startswith("__")}
    return cfg, params, meta


# --------------------------------------------------------------- استنتاج سریع
class InferenceModel:
    """استنتاج با حافظهٔ KV (بدون کش، هر توکن یک‌بار محاسبه می‌شود)."""

    def __init__(self, cfg: GPTConfig, params: dict):
        self.cfg = cfg
        self.params = params

    def _attend(self, x_t, pos, kv):
        """یک گام پیش‌رو برای یک توکن؛ kv: فهرست (k,v) هر لایه."""
        cfg = self.cfg
        C = cfg.n_embd
        H, hd = cfg.n_head, cfg.head_dim
        x = self.params["wte"][x_t] + self.params["wpe"][pos]
        for i in range(cfg.n_layer):
            p = f"h{i}."
            a = layernorm_forward(x, self.params[p + "ln1_g"], self.params[p + "ln1_b"])[0]
            # x به‌شکل (1,C) است؛ LN روی محور آخر درست کار می‌کند
            qkv = a @ self.params[p + "qkv_w"] + self.params[p + "qkv_b"]
            q, k, v = np.split(qkv, 3, axis=-1)
            q = q.reshape(H, hd)
            k = k.reshape(H, hd)
            v = v.reshape(H, hd)
            if kv[i] is None:
                k_cache, v_cache = k[:, None, :], v[:, None, :]
            else:
                k_cache = np.concatenate([kv[i][0], k[:, None, :]], axis=1)
                v_cache = np.concatenate([kv[i][1], v[:, None, :]], axis=1)
            kv[i] = (k_cache, v_cache)
            scores = (q[:, None, :] * k_cache).sum(-1) / math.sqrt(hd)  # (H, T)
            attn = softmax(scores, -1)
            out = (attn[:, :, None] * v_cache).sum(1).reshape(C)
            x = x + out @ self.params[p + "attn_w"] + self.params[p + "attn_b"]
            b = layernorm_forward(x, self.params[p + "ln2_g"], self.params[p + "ln2_b"])[0]
            hidden = b @ self.params[p + "mlp1_w"] + self.params[p + "mlp1_b"]
            act, _ = silu_forward(hidden)
            x = x + act @ self.params[p + "mlp2_w"] + self.params[p + "mlp2_b"]
        xf = layernorm_forward(x, self.params["lnf_g"], self.params["lnf_b"])[0]
        return xf @ self.params["wte"].T, kv

    def logits_for_prompt(self, token_ids: list[int]):
        if len(token_ids) > self.cfg.block_size:
            token_ids = token_ids[-self.cfg.block_size:]
        kv = [None] * self.cfg.n_layer
        logits = None
        for pos, tok in enumerate(token_ids):
            logits, kv = self._attend(int(tok), pos, kv)
        return logits, kv

    def next_logits(self, token: int, pos: int, kv):
        logits, kv = self._attend(int(token), pos, kv)
        return logits, kv


# -------------------------------------------------------------------- نمونه‌گیری
def sample_from_logits(logits: np.ndarray, rng: np.random.Generator, temperature: float = 0.9,
                       top_k: int = 40, top_p: float = 0.92,
                       recent: list[int] | None = None, repetition_penalty: float = 1.0):
    """نمونه‌گیری با دما، top-k، top-p و جریمهٔ تکرار. خروجی: (id، logprob، آنتروپی)."""
    logits = np.asarray(logits, dtype=np.float64).reshape(-1).copy()
    if recent and repetition_penalty != 1.0:
        for token in set(recent[-96:]):
            if logits[token] > 0:
                logits[token] /= repetition_penalty
            else:
                logits[token] *= repetition_penalty
    logits /= max(temperature, 1e-5)
    if top_k and top_k < logits.size:
        kth = np.partition(logits, -top_k)[-top_k]
        logits[logits < kth] = -np.inf
    probs = softmax(logits, -1)
    if top_p and top_p < 1.0:
        order = np.argsort(-probs)
        sorted_probs = probs[order]
        cumulative = np.cumsum(sorted_probs)
        keep = (cumulative - sorted_probs) < top_p
        sorted_probs = np.where(keep, sorted_probs, 0.0)
        total = sorted_probs.sum()
        if total <= 0:
            sorted_probs = np.zeros_like(sorted_probs)
            sorted_probs[0] = 1.0
            total = 1.0
        sorted_probs /= total
        filtered = np.zeros_like(probs)
        filtered[order] = sorted_probs
    else:
        filtered = probs
        filtered /= filtered.sum()
    token = int(rng.choice(filtered.size, p=filtered))
    prob = float(filtered[token])
    entropy = float(-(filtered * np.log(np.clip(filtered, 1e-12, None))).sum())
    return token, math.log(max(prob, 1e-12)), entropy
