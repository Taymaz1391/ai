#!/usr/bin/env python3
"""بستنِ یک اجرای آموزش: ارزیابی نهایی، انتشار checkpoint و نوشتن کارت واقعی اجرا.

این اسکریپت هیچ عددی از خودش نمی‌سازد؛ همهٔ سنجه‌ها را از checkpoint، فایل
متریک‌ها و آمار پیکره می‌خواند.

    python scripts/finalize_run.py \\
        --checkpoint checkpoints/rayan-2-last.npz \\
        --tokenizer tokenizer/rayan_bpe_16k.json \\
        --metrics logs/metrics-v2.jsonl \\
        --name "رایان ۲"

خروجی‌ها:
    checkpoints/last.npz         (همان وزن‌ها + متادیتای کامل؛ سایت همین را بار می‌کند)
    configs/training_run.json    (کارتی که /api/health و /api/model می‌خوانند)
    reports/final-metrics.json   (سنجه‌های نهایی، مستقل از متریک‌های آموزش)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import shutil
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rayan.model import load_checkpoint, save_checkpoint  # noqa: E402
from rayan.tokenizer import BPETokenizer  # noqa: E402


def load_evaluate_module():
    path = os.path.join(ROOT, "scripts", "evaluate.py")
    spec = importlib.util.spec_from_file_location("rayan_evaluate_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def read_metrics(path: str) -> tuple[list[dict], list[dict]]:
    train, evals = [], []
    if not os.path.exists(path):
        return train, evals
    with open(path, encoding="utf-8") as fh:
        for line in fh:
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
    return train, evals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="checkpoints/rayan-2-last.npz")
    parser.add_argument("--tokenizer", default="tokenizer/rayan_bpe_16k.json")
    parser.add_argument("--metrics", default="logs/metrics-v2.jsonl")
    parser.add_argument("--val", default="data/val.txt")
    parser.add_argument("--name", default="رایان ۲")
    parser.add_argument("--previous", default="rayan-1-small")
    parser.add_argument("--publish", default="checkpoints/last.npz")
    parser.add_argument("--run-config", default="configs/training_run.json")
    parser.add_argument("--report", default="reports/final-metrics.json")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--reuse-eval", default="", help="ارزیابی کاملِ آماده را از همین گزارش بخوان")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--min-lr", type=float, default=1e-4)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--corpus-note", default="")
    args = parser.parse_args()

    checkpoint = os.path.join(ROOT, args.checkpoint) if not os.path.isabs(args.checkpoint) else args.checkpoint
    tokenizer_path = os.path.join(ROOT, args.tokenizer) if not os.path.isabs(args.tokenizer) else args.tokenizer
    metrics_path = os.path.join(ROOT, args.metrics) if not os.path.isabs(args.metrics) else args.metrics
    val_path = os.path.join(ROOT, args.val) if not os.path.isabs(args.val) else args.val

    cfg, params, meta = load_checkpoint(checkpoint)
    tokenizer = BPETokenizer.load(tokenizer_path)
    if cfg.vocab_size != tokenizer.vocab_size:
        raise SystemExit(f"vocab mismatch: {cfg.vocab_size} vs {tokenizer.vocab_size}")
    n_params = int(sum(p.size for p in params.values()))
    train_records, evals = read_metrics(metrics_path)
    print(f"checkpoint step={meta.get('step')} params={n_params:,} evals={len(evals)}", flush=True)

    # ------------------------------------------------ ارزیابی مستقل روی کل نگه‌داشته
    evaluation = None
    if args.reuse_eval and os.path.exists(os.path.join(ROOT, args.reuse_eval)):
        previous = read_json(os.path.join(ROOT, args.reuse_eval), {})
        evaluation = previous.get("independent_evaluation")
        if evaluation:
            print(f"[=] reused independent evaluation from {args.reuse_eval}", flush=True)
    if evaluation is None and not args.skip_eval and os.path.exists(val_path):
        module = load_evaluate_module()
        text = open(val_path, encoding="utf-8").read()
        ids = np.asarray(tokenizer.encode(text), dtype=np.uint16)
        print(f"evaluating {len(ids):,} validation tokens ...", flush=True)
        evaluation = module.evaluate_loss(cfg, params, ids, cfg.block_size, args.batch_size)
        chars_per_token = len(text) / max(1, len(ids))
        evaluation["bits_per_char"] = round(evaluation["val_loss"] / math.log(2) / chars_per_token, 4)
        evaluation["chars_per_token"] = round(chars_per_token, 3)
        evaluation["chars"] = len(text)
        print(json.dumps(evaluation, ensure_ascii=False, indent=2), flush=True)

    # ------------------------------------------------ سرعت استنتاج روی همین ماشین
    inference_tps = None
    try:
        from rayan.generate import Engine
        engine = Engine(checkpoint, tokenizer_path)
        prompt_ids, _ = engine.build_prompt("سلام، خودت را معرفی کن", "chat")
        engine.generate(prompt_ids, mode="chat", seed=7, max_new_tokens=32)
        started = time.time()
        generation = engine.generate(prompt_ids, mode="chat", seed=11, max_new_tokens=48)
        elapsed_gen = max(1e-6, time.time() - started)
        inference_tps = round(len(generation.tokens) / elapsed_gen, 1)
        print(f"inference speed: {inference_tps} tok/s", flush=True)
    except Exception as exc:  # pragma: no cover - اندازه‌گیری اختیاری است
        print(f"[!] inference speed skipped: {exc}", flush=True)

    # ------------------------------------------------ کارت واقعی اجرا برای سایت
    stats = read_json(os.path.join(ROOT, "data", "corpus_stats.json"), {})
    token_stats = read_json(os.path.join(ROOT, "data", "tokenized_stats.json"), {})
    tokens_seen = int(meta.get("tokens_seen") or (train_records[-1]["tokens"] if train_records else 0))
    segments: list[dict] = []
    for record in train_records:
        elapsed_s = float(record.get("elapsed_s") or 0.0)
        if not segments or elapsed_s < segments[-1]["max_elapsed"]:
            segments.append({"start_step": record["step"], "max_elapsed": elapsed_s,
                             "steps": record["step"], "tokens": record.get("tokens", 0)})
        segments[-1]["max_elapsed"] = max(segments[-1]["max_elapsed"], elapsed_s)
        segments[-1]["end_step"] = record["step"]
        segments[-1]["tokens"] = record.get("tokens", 0)
    elapsed = sum(s["max_elapsed"] for s in segments) if segments else float(meta.get("trained_seconds") or 0)
    last_eval = evals[-1] if evals else {}
    # بهترین سنجه فقط بین ارزیابی‌های همان اجرای منتشرشده (نه اجرای قبلی) معنا دارد
    final_start = segments[-1]["start_step"] if segments else 0
    final_evals = [e for e in evals if e.get("step", 0) > final_start] or evals
    best_eval = min(final_evals, key=lambda r: r.get("val_loss", 9e9)) if final_evals else {}
    final = evaluation or {
        "val_loss": last_eval.get("val_loss"),
        "ppl": last_eval.get("ppl"),
        "bits_per_char": last_eval.get("bits_per_char"),
    }

    train_info = stats.get("train.txt") or {}
    val_info = stats.get("val.txt") or {}
    raw_sources = stats.get("sources") or stats.get("breakdown") or {}
    if isinstance(raw_sources, dict):
        source_caps = [{"name": name, **info} for name, info in raw_sources.items()]
    else:
        source_caps = list(raw_sources)
    run_config = {
        "name": args.name,
        "id": "rayan-2-base",
        "previous": args.previous,
        "steps": int(meta.get("step") or (train_records[-1]["step"] if train_records else 0)),
        "steps_planned": int(meta.get("steps_planned") or 0) or None,
        "batch_size": args.batch_size,
        "block_size": cfg.block_size,
        "tokens_per_step": args.batch_size * cfg.block_size,
        "tokens_seen": tokens_seen,
        "layers": cfg.n_layer,
        "heads": cfg.n_head,
        "embed": cfg.n_embd,
        "vocab": cfg.vocab_size,
        "params": n_params,
        "lr": args.lr,
        "min_lr": args.min_lr,
        "warmup": args.warmup,
        "hardware": "2 vCPU · NumPy · no GPU",
        "train_seconds": round(elapsed, 1),
        "train_minutes": round(elapsed / 60, 1),
        "segments": [{"from": seg["start_step"], "to": seg.get("end_step", seg["start_step"]),
                      "seconds": round(seg["max_elapsed"], 1)} for seg in segments],
        # سرعت از آخرین رکورد آموزش همان اجرا خوانده می‌شود، نه از تقسیم توکن تجمعی
        "tokens_per_second": (train_records[-1].get("tok_s") if train_records else None),
        "inference_tokens_per_second": inference_tps,
        "val_loss": final.get("val_loss"),
        "ppl": final.get("ppl"),
        "bits_per_char": final.get("bits_per_char"),
        "best_val_loss": best_eval.get("val_loss"),
        "tokenizer": {
            "path": os.path.relpath(tokenizer_path, ROOT),
            **tokenizer.stats(),
        },
        "corpus": {
            "train_tokens": (token_stats.get("train") or {}).get("tokens"),
            "val_tokens": (token_stats.get("val") or {}).get("tokens"),
            "train_chars": int(train_info.get("chars") or sum(s.get("chars", 0) for s in source_caps)),
            "val_chars": int(val_info.get("chars") or 0),
            "docs": int(train_info.get("docs") or 0),
            "sources": source_caps,
        },
        "note": args.corpus_note or meta.get("corpus") or "",
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    run_path = os.path.join(ROOT, args.run_config)
    os.makedirs(os.path.dirname(run_path), exist_ok=True)
    with open(run_path, "w", encoding="utf-8") as fh:
        json.dump(run_config, fh, ensure_ascii=False, indent=2)
    print(f"[=] wrote {os.path.relpath(run_path, ROOT)}", flush=True)

    # ------------------------------------------------ انتشار checkpoint با متادیتای کامل
    publish_path = os.path.join(ROOT, args.publish)
    os.makedirs(os.path.dirname(publish_path), exist_ok=True)
    if os.path.abspath(publish_path) != os.path.abspath(checkpoint):
        shutil.copyfile(checkpoint, publish_path)
    save_checkpoint(publish_path, cfg, params, {
            **meta,
            "name": args.name,
            "model_id": "rayan-2-base",
            "params": n_params,
            "steps_planned": run_config["steps_planned"],
            "tokens_seen": tokens_seen,
            "val_loss": final.get("val_loss"),
            "ppl": final.get("ppl"),
            "bits_per_char": final.get("bits_per_char"),
            "tokenizer": os.path.relpath(tokenizer_path, ROOT),
            "corpus": run_config["note"],
            "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    print(f"[=] published {os.path.relpath(publish_path, ROOT)}", flush=True)

    report = {
        "model": args.name,
        "checkpoint": args.checkpoint,
        "params": n_params,
        "config": cfg.to_dict(),
        "independent_evaluation": evaluation,
        "training_metrics": {
            "last_eval": last_eval,
            "best_eval": best_eval,
            "steps_logged": len(train_records),
            "tokens_seen": tokens_seen,
            "seconds": round(elapsed, 1),
        },
    }
    report_path = os.path.join(ROOT, args.report)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"[=] wrote {os.path.relpath(report_path, ROOT)}", flush=True)


if __name__ == "__main__":
    main()
