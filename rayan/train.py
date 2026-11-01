"""آموزش مدل رایان از صفر روی پیکرهٔ فارسی.

    python -m rayan.train --tokenizer tokenizer/rayan_bpe.json \
        --train data/train.txt --val data/val.txt --steps 2000

هیچ GPU یا frameworkای لازم نیست؛ همین فایل با NumPy روی CPU آموزش می‌دهد.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time

import numpy as np

from .model import (
    GPTConfig, AdamW, backward, count_params, forward, init_params,
    load_checkpoint, save_checkpoint,
)
from .tokenizer import BPETokenizer


def encode_file(path: str, tokenizer: BPETokenizer, dtype=np.uint16, verbose: bool = True) -> np.ndarray:
    text = open(path, encoding="utf-8").read()
    if verbose:
        print(f"encoding {path} ({len(text)/1e6:.1f} MB) ...", flush=True)
    ids = tokenizer.encode(text)
    if not ids:
        raise ValueError(f"no tokens produced from {path}")
    arr = np.asarray(ids, dtype=np.int64)
    if arr.max() > np.iinfo(dtype).max:
        dtype = np.uint32
    return arr.astype(dtype)


def measure_chars_per_token(args, val_data) -> float:
    """نویسه بر توکن اعتبارسنجی، از آمار توکن‌سازی یا از خود فایل متن.

    عدد دستی ممنوع است: گزارش «بیت بر نویسه» فقط با نسبت واقعی همان داده معنا دارد.
    """
    if args.chars_per_token and args.chars_per_token > 0:
        return float(args.chars_per_token)
    try:
        with open("data/tokenized_stats.json", encoding="utf-8") as fh:
            stats = json.load(fh)
        val = stats.get("val") or {}
        ratio = float(val["chars"]) / max(1, int(val["tokens"]))
        if ratio > 0:
            return ratio
    except (OSError, KeyError, ValueError, ZeroDivisionError):
        pass
    try:
        text = open(args.val, encoding="utf-8").read()
        ratio = len(text) / max(1, len(val_data))
        if ratio > 0:
            return ratio
    except OSError:
        pass
    print("[!] chars/token نامعلوم؛ ۴٫۲۵ فرض می‌شود (عدد گزارش‌شده معتبر نیست)", flush=True)
    return 4.25


def cfg_block_guard(block_size: int) -> int:
    return block_size + 2


def get_batch(data: np.ndarray, batch_size: int, block_size: int, rng: np.random.Generator):
    starts = rng.integers(0, len(data) - block_size - 1, size=batch_size)
    x = np.stack([data[i:i + block_size] for i in starts]).astype(np.int64)
    y = np.stack([data[i + 1:i + 1 + block_size] for i in starts]).astype(np.int64)
    return x, y


def lr_at(step: int, total: int, base_lr: float, min_lr: float, warmup: int) -> float:
    if step < warmup:
        return base_lr * (step + 1) / max(1, warmup)
    progress = (step - warmup) / max(1, total - warmup)
    progress = min(1.0, max(0.0, progress))
    return min_lr + 0.5 * (base_lr - min_lr) * (1 + math.cos(math.pi * progress))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Rayan from scratch")
    parser.add_argument("--tokenizer", default="tokenizer/rayan_bpe.json")
    parser.add_argument("--train", default="data/train.txt")
    parser.add_argument("--val", default="data/val.txt")
    parser.add_argument("--out", default="checkpoints/rayan-1-small.npz")
    parser.add_argument("--latest", default="checkpoints/last.npz")
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--block-size", type=int, default=256)
    parser.add_argument("--layers", type=int, default=5)
    parser.add_argument("--heads", type=int, default=4)
    parser.add_argument("--embed", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1.2e-3)
    parser.add_argument("--min-lr", type=float, default=1e-4)
    parser.add_argument("--warmup", type=int, default=150)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--eval-every", type=int, default=100)
    parser.add_argument("--eval-batches", type=int, default=3)
    parser.add_argument("--save-every", type=int, default=100)
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--resume", default="")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--metrics", default="logs/metrics.jsonl")
    parser.add_argument("--chars-per-token", type=float, default=0.0,
                        help="اگر صفر باشد، از آمار توکن‌سازی همین اجرا اندازه‌گیری می‌شود")
    parser.add_argument("--name", default="rayan", help="نام مدل برای متادیتا و کارت سایت")
    parser.add_argument("--corpus-note", default="Persian web, news, Wikipedia, books and poetry", help="توضیح پیکره")
    parser.add_argument("--train-ids", default="", help="فایل uint16 توکن‌های آموزش (np.memmap)")
    parser.add_argument("--val-ids", default="", help="فایل uint16 توکن‌های اعتبارسنجی")
    parser.add_argument("--max-minutes", type=float, default=0)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.latest) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.metrics) or ".", exist_ok=True)

    tokenizer = BPETokenizer.load(args.tokenizer)
    print(f"tokenizer: {tokenizer.stats()}", flush=True)
    if args.train_ids:
        # پیکرهٔ بزرگ: شناسه‌ها از پیش ساخته شده‌اند و با memmap خوانده می‌شوند
        train_data = np.memmap(args.train_ids, dtype=np.uint16, mode="r")
        if args.val_ids:
            val_data = np.memmap(args.val_ids, dtype=np.uint16, mode="r")
        else:
            val_data = encode_file(args.val, tokenizer)
    else:
        train_data = encode_file(args.train, tokenizer)
        val_data = encode_file(args.val, tokenizer)
    if len(train_data) <= cfg_block_guard(args.block_size):
        raise ValueError("پیکرهٔ آموزش از یک پنجره کوتاه‌تر است")
    print(f"train tokens: {len(train_data):,} | val tokens: {len(val_data):,}", flush=True)

    cfg = GPTConfig(
        vocab_size=tokenizer.vocab_size,
        block_size=args.block_size,
        n_layer=args.layers,
        n_head=args.heads,
        n_embd=args.embed,
    )
    start_step = 0
    if args.resume and os.path.exists(args.resume):
        cfg, params, meta = load_checkpoint(args.resume)
        start_step = int(meta.get("step", 0))
        print(f"resumed from {args.resume} at step {start_step}", flush=True)
    else:
        params = init_params(cfg, seed=args.seed)
    opt = AdamW(params, lr=args.lr, weight_decay=args.weight_decay, grad_clip=1.0)
    n_params = count_params(params)
    print(f"model: {cfg.to_dict()} | params={n_params:,}", flush=True)

    rng = np.random.default_rng(args.seed + start_step)
    last_metrics: dict = {}
    last_step = start_step
    eval_rng = np.random.default_rng(999)
    eval_sets = [get_batch(val_data, args.batch_size, cfg.block_size, eval_rng)
                 for _ in range(args.eval_batches)]

    def evaluate() -> float:
        losses = []
        for x, y in eval_sets:
            _, loss = forward(params, cfg, x, y)
            losses.append(float(loss))
        return float(np.mean(losses))

    chars_per_token = measure_chars_per_token(args, val_data)
    print(f"chars/token (val): {chars_per_token:.3f}", flush=True)
    tokens_done = start_step * args.batch_size * cfg.block_size
    run_tokens = 0
    start_time = time.time()
    best_val = float("inf")
    metrics_fh = open(args.metrics, "a", encoding="utf-8")

    def emit(record: dict) -> None:
        metrics_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        metrics_fh.flush()

    planned = max(1, args.steps - start_step)
    for step in range(start_step, args.steps):
        lr = lr_at(step - start_step, planned, args.lr, args.min_lr, args.warmup)
        opt.lr = lr
        x, y = get_batch(train_data, args.batch_size, cfg.block_size, rng)
        t0 = time.time()
        _, loss, cache = forward(params, cfg, x, y, keep_cache=True)
        grads = backward(params, cfg, cache)
        grad_norm = opt.step(params, grads)
        dt = time.time() - t0
        tokens_done += x.size
        run_tokens += x.size

        if step % args.log_every == 0:
            elapsed = time.time() - start_time
            tok_s = run_tokens / max(1e-9, elapsed)
            print(
                f"step {step:5d}/{args.steps} | loss {float(loss):.4f} | lr {lr:.2e} | "
                f"gnorm {grad_norm:.2f} | {tok_s:6.0f} tok/s | {elapsed/60:5.1f} min",
                flush=True,
            )
            emit({
                "step": step, "loss": round(float(loss), 4), "lr": lr,
                "grad_norm": round(grad_norm, 3), "tokens": int(tokens_done),
                "elapsed_s": round(elapsed, 1), "tok_s": round(tok_s, 1),
                "kind": "train",
            })

        if (step + 1) % args.eval_every == 0 or step + 1 == args.steps:
            val_loss = evaluate()
            improved = val_loss < best_val
            best_val = min(best_val, val_loss)
            ppl = math.exp(val_loss)
            bpc = val_loss / math.log(2) / chars_per_token
            print(f"  ── eval step {step+1}: val_loss={val_loss:.4f} | ppl={ppl:.1f} | bits/char={bpc:.3f}",
                  flush=True)
            emit({
                "step": step + 1, "val_loss": round(val_loss, 4), "ppl": round(ppl, 2),
                "bits_per_char": round(bpc, 4), "kind": "eval",
                "tokens": int(tokens_done), "elapsed_s": round(time.time() - start_time, 1),
            })
            last_metrics = {
                "val_loss": round(val_loss, 4),
                "ppl": round(ppl, 2),
                "bits_per_char": round(bpc, 4),
            }
            last_step = step + 1
            meta = {
                "step": step + 1,
                "steps_planned": args.steps,
                "tokens_seen": int(tokens_done),
                "name": args.name,
                "params": n_params,
                "trained_seconds": round(time.time() - start_time, 1),
                "tokenizer": args.tokenizer,
                "corpus": args.corpus_note,
                "config": cfg.to_dict(),
                **last_metrics,
            }
            save_checkpoint(args.latest, cfg, params, meta)
            if improved:
                save_checkpoint(args.out, cfg, params, meta)

        if (step + 1) % args.save_every == 0 and (step + 1) % args.eval_every != 0:
            last_step = step + 1
            save_checkpoint(args.latest, cfg, params, {
                "step": step + 1,
                "steps_planned": args.steps,
                "tokens_seen": int(tokens_done),
                "name": args.name,
                "params": n_params,
                "tokenizer": args.tokenizer,
                "corpus": args.corpus_note,
                "config": cfg.to_dict(),
                **last_metrics,
            })

        if args.max_minutes and (time.time() - start_time) / 60 >= args.max_minutes:
            print("time budget reached; stopping early", flush=True)
            break

    final_val = evaluate()
    meta = {
        "step": last_step,
        "steps_planned": args.steps,
        "tokens_seen": int(tokens_done),
        "val_loss": round(final_val, 4),
        "ppl": round(math.exp(final_val), 2),
        "bits_per_char": round(final_val / math.log(2) / chars_per_token, 4),
        "params": n_params,
        "trained_seconds": round(time.time() - start_time, 1),
        "tokenizer": args.tokenizer,
        "name": args.name,
        "corpus": args.corpus_note,
        "best_val": round(best_val, 4),
        "config": cfg.to_dict(),
        "finished": True,
    }
    if final_val <= best_val + 1e-9:
        save_checkpoint(args.out, cfg, params, meta)
        print(f"done. final val_loss={final_val:.4f} -> {args.out}", flush=True)
    else:
        print(f"done. best val_loss={best_val:.4f} kept in {args.out} (final {final_val:.4f})", flush=True)
    metrics_fh.close()


if __name__ == "__main__":
    main()
