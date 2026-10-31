"""آزمون صحت پس‌انتشار دستی و حافظهٔ KV.

    python tests/gradcheck.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsia.model import (  # noqa: E402
    GPTConfig, InferenceModel, backward, forward, init_params,
)


def numeric_grad(params, cfg, x, y, name, index, eps=1e-4):
    original = params[name][index]
    params[name][index] = original + eps
    _, loss_plus = forward(params, cfg, x, y)
    params[name][index] = original - eps
    _, loss_minus = forward(params, cfg, x, y)
    params[name][index] = original
    return (loss_plus - loss_minus) / (2 * eps)


def gradcheck() -> None:
    cfg = GPTConfig(vocab_size=50, block_size=8, n_layer=2, n_head=2, n_embd=16)
    params = init_params(cfg, seed=3, dtype=np.float64)
    rng = np.random.default_rng(0)
    x = rng.integers(0, cfg.vocab_size, (2, 8))
    y = rng.integers(0, cfg.vocab_size, (2, 8))
    _, loss, cache = forward(params, cfg, x, y, keep_cache=True)
    grads = backward(params, cfg, cache)
    print(f"loss = {loss:.6f}")
    worst = 0.0
    for name in params:
        analytic = grads[name]
        for _ in range(3):
            index = tuple(rng.integers(0, s) for s in params[name].shape)
            numeric = numeric_grad(params, cfg, x, y, name, index)
            a = float(analytic[index])
            denom = max(1e-8, abs(a) + abs(numeric))
            rel = abs(a - numeric) / denom
            worst = max(worst, rel)
            if rel > 2e-4:
                print(f"  MISMATCH {name}{index}: analytic={a:.6e} numeric={numeric:.6e} rel={rel:.2e}")
    print(f"worst relative error = {worst:.2e}")
    assert worst < 2e-4, "gradient check failed"
    print("gradcheck OK")


def kvcheck() -> None:
    cfg = GPTConfig(vocab_size=64, block_size=16, n_layer=2, n_head=2, n_embd=16)
    params = init_params(cfg, seed=5)
    model = InferenceModel(cfg, params)
    ids = [3, 9, 11, 2, 7]
    logits_full, _ = forward(params, cfg, np.array([ids]))
    logits_kv, kv = model.logits_for_prompt(ids)
    err = np.abs(logits_full[0, -1] - logits_kv).max()
    print(f"prompt KV gap = {err:.2e}")
    assert err < 2e-4, "KV-cache prompt mismatch"
    nxt = 13
    logits_full2, _ = forward(params, cfg, np.array([ids + [nxt]]))
    logits_kv2, _ = model.next_logits(nxt, len(ids), kv)
    err2 = np.abs(logits_full2[0, -1] - logits_kv2).max()
    print(f"next-token KV gap = {err2:.2e}")
    assert err2 < 2e-4, "KV-cache step mismatch"
    print("kvcheck OK")


if __name__ == "__main__":
    gradcheck()
    kvcheck()
