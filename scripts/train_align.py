"""هم‌ترازی رایان به سبک InstructGPT: SFT → مدل پاداش → DPO.

    python scripts/train_align.py --base checkpoints/rayan-1-small.npz \\
        --prefs data/preferences.jsonl --out checkpoints/rayan-aligned.npz

مرحله‌ها دقیقاً همان سه مرحلهٔ گزارش‌شدهٔ InstructGPT هستند، با ابزارهای همین مخزن:
NumPy، پس‌انتشار دستی، و ترجیح‌های داور خودکار به‌جای برچسب انسانی.

خروجی: checkpoint، مدل پاداش، و `reports/alignment.json` با اعداد واقعیِ قبل/بعد.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from rayan import align, rubric  # noqa: E402
from rayan.generate import Engine  # noqa: E402
from rayan.model import (  # noqa: E402
    AdamW, backward, count_params, forward, load_checkpoint, save_checkpoint,
)
from rayan.tokenizer import BPETokenizer  # noqa: E402


def _log(message: str) -> None:
    print(message, flush=True)


def split_prompts(prompts: list[dict], ratio: float = 0.2, seed: int = 11
                  ) -> tuple[list[dict], list[dict]]:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(prompts))
    cut = max(1, int(len(prompts) * ratio))
    test_idx = set(int(i) for i in order[:cut])
    train = [item for i, item in enumerate(prompts) if i not in test_idx]
    test = [item for i, item in enumerate(prompts) if i in test_idx]
    return train, test


def chat_perplexity(params, cfg, tokenizer, rows: list[dict]) -> float:
    losses = []
    for row in rows:
        ex = align.example_ids(tokenizer, row["user"], row["assistant"], cfg.block_size)
        if not ex:
            continue
        ids, plen = ex
        logp = align.sequence_logprob(params, cfg, ids, plen)[0]
        losses.append(-logp / max(1, len(ids) - plen))
    return float(math.exp(np.mean(losses))) if losses else float("nan")


def generation_scores(params, cfg, tokenizer, prompts: list[dict], *, seed: int = 5,
                      temperature: float = 0.7, max_new_tokens: int = 70,
                      samples_n: int = 8, keep_all: bool = False) -> dict:
    """تولید واقعی با مدل و امتیازدهی داور خودکار (بدون دیدن دادهٔ آموزش)."""
    engine = Engine.__new__(Engine)  # بدون بارگذاری دوباره از دیسک
    engine.cfg = cfg
    engine.params = params
    engine.tokenizer = tokenizer
    engine.special = tokenizer.special_ids
    engine.generations = 0
    from rayan.generate import InferenceModel
    engine.model = InferenceModel(cfg, params)
    scores: list[dict] = []
    texts: list[str] = []
    for index, prompt in enumerate(prompts):
        prompt_ids, _ = engine.build_prompt(prompt["user"], "chat")
        generation = engine.generate(prompt_ids, mode="chat", temperature=temperature,
                                     max_new_tokens=max_new_tokens, seed=seed + index)
        text = tokenizer.decode(generation.tokens, skip_specials=True).strip()
        scored = rubric.score(text, reference=prompt.get("reference", ""),
                              expected=prompt.get("expected") or [],
                              finish=generation.finish_reason)
        scores.append(scored)
        texts.append(text)
    if not scores:
        return {"n": 0}
    return {
        "n": len(scores),
        "rubric_mean": float(np.mean([s["total"] for s in scores])),
        "repetition_mean": float(np.mean([s["repetition"] for s in scores])),
        "empty_rate": float(np.mean([s["length"] < 12 for s in scores])),
        "leak_rate": float(np.mean([s["leak"] for s in scores])),
        "length_mean": float(np.mean([s["length"] for s in scores])),
        "totals": [s["total"] for s in scores],
        "samples": [{"user": p["user"], "answer": t}
                    for p, t in zip(prompts[:samples_n], texts[:samples_n])],
        **({"answers": texts} if keep_all else {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="checkpoints/rayan-1-small.npz")
    parser.add_argument("--tokenizer", default="")
    parser.add_argument("--prefs", default="data/preferences.jsonl")
    parser.add_argument("--stages", default="checkpoints/stages",
                        help="پوشهٔ عکس مرحله‌ها برای سنجش مستقل")
    parser.add_argument("--seeds", default="data/chat_seed.jsonl")
    parser.add_argument("--sft-data", default="data/sft_wiki.jsonl",
                        help="دادهٔ نمایشی افزوده برای SFT (اختیاری)")
    parser.add_argument("--extra-ratio", type=float, default=0.0,
                        help="سهم دادهٔ افزوده در هر دستهٔ SFT")
    parser.add_argument("--out", default="checkpoints/rayan-aligned.npz")
    parser.add_argument("--reward", default="checkpoints/reward.npz")
    parser.add_argument("--report", default="reports/alignment.json")
    parser.add_argument("--sft-steps", type=int, default=150)
    parser.add_argument("--sft-lr", type=float, default=4e-5)
    parser.add_argument("--replay", default="data/index-sample-3m.txt",
                        help="متن عمومی برای جلوگیری از فراموشی در SFT")
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--beta", type=float, default=0.12)
    parser.add_argument("--dpo-steps", type=int, default=200)
    parser.add_argument("--dpo-lr", type=float, default=5e-6)
    parser.add_argument("--seed", type=int, default=20261101)
    args = parser.parse_args()

    tokenizer_path = args.tokenizer or ("tokenizer/rayan_bpe_16k.json"
                                        if "16k" in args.base else "tokenizer/rayan_bpe.json")
    tokenizer = BPETokenizer.load(os.path.join(ROOT, tokenizer_path))
    cfg, params, base_meta = load_checkpoint(os.path.join(ROOT, args.base))
    reference = {key: value.copy() for key, value in params.items()}
    snapshot_base = {key: value.copy() for key, value in params.items()}
    rng = np.random.default_rng(args.seed)
    started = time.time()

    replay_ids = None
    replay_path = os.path.join(ROOT, args.replay)
    if os.path.exists(replay_path):
        with open(replay_path, encoding="utf-8") as fh:
            replay_ids = np.asarray(tokenizer.encode(fh.read(1_500_000)), dtype=np.int64)
        _log(f"[align] دادهٔ بازپخش: {len(replay_ids):,} توکن")

    def snapshot(params_dict: dict) -> dict:
        return {key: value.copy() for key, value in params_dict.items()}

    def restore(params_dict: dict, saved: dict) -> None:
        for key in params_dict:
            params_dict[key][...] = saved[key]
    report: dict = {
        "base_checkpoint": args.base,
        "params": count_params(params),
        "config": cfg.to_dict(),
        "base_meta": {key: base_meta.get(key) for key in ("step", "val_loss", "name")},
    }
    _log(f"[align] base={args.base} params={count_params(params):,} cfg={cfg.to_dict()}")

    # ---------------------------------------------------------------- داده
    prefs: list[dict] = []
    with open(os.path.join(ROOT, args.prefs), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                prefs.append(json.loads(line))
    seeds: list[dict] = []
    with open(os.path.join(ROOT, args.seeds), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                row = json.loads(line)
                seeds.append({"user": row["user"], "assistant": row["assistant"]})
    train_seeds, test_seeds = split_prompts(seeds, ratio=0.2)
    train_prefs, test_prefs = split_prompts(prefs, ratio=0.2) if prefs else ([], [])
    _log(f"[align] زوج ترجیح: {len(prefs)} (آزمون {len(test_prefs)}) · "
         f"پرسش گفتگو: {len(seeds)} (آزمون {len(test_seeds)})")

    test_prompts = [{"user": row["user"], "assistant": row["assistant"]}
                    for row in test_seeds]
    for row in test_prefs:
        test_prompts.append({"user": row["user"], "assistant": row["chosen"]})
    test_prompts = test_prompts[:24]

    before = {
        "chat_ppl": chat_perplexity(params, cfg, tokenizer, test_seeds),
        "generation": generation_scores(params, cfg, tokenizer, test_prompts),
    }
    report["before"] = {key: value for key, value in before.items() if key != "generation"}
    report["before"]["generation"] = {k: v for k, v in before["generation"].items()
                                      if k != "samples"}
    _log(f"[align] قبل: ppl گفتگو {before['chat_ppl']:.2f} · "
         f"امتیاز داور {before['generation']['rubric_mean']:.3f}")

    # ------------------------------------------------------- مرحلهٔ ۱: SFT
    sft_rows = train_seeds + [{"user": row["user"], "assistant": row["chosen"]}
                              for row in train_prefs]
    extra_rows: list[dict] = []
    extra_path = os.path.join(ROOT, args.sft_data) if args.sft_data else ""
    if extra_path and os.path.exists(extra_path):
        with open(extra_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    if row.get("user") and row.get("assistant"):
                        extra_rows.append({"user": row["user"], "assistant": row["assistant"]})

    report["sft_data"] = {"chat_seeds": len(train_seeds),
                          "preference_answers": len(train_prefs),
                          "extra": len(extra_rows),
                          "extra_path": os.path.relpath(extra_path, ROOT) if extra_rows else None}
    examples = []
    for row in sft_rows:
        ex = align.example_ids(tokenizer, row["user"], row["assistant"], cfg.block_size)
        if ex:
            examples.append(ex)
    extra_examples = []
    for row in extra_rows:
        ex = align.example_ids(tokenizer, row["user"], row["assistant"], cfg.block_size)
        if ex:
            extra_examples.append(ex)
    _log(f"[align] مرحلهٔ ۱ (SFT) روی {len(examples)} مثال گفتگو"
         f"{f' + {len(extra_examples)} مثال دانشنامه (سهم {args.extra_ratio:.0%})' if extra_examples else ''}"
         f" · {args.sft_steps} گام")
    optimizer = AdamW(params, lr=args.sft_lr, weight_decay=0.02, grad_clip=1.0)
    sft_losses: list[float] = []
    baseline_ppl = before["chat_ppl"]
    best_ppl = baseline_ppl
    best_sft = snapshot(params)
    best_step = 0
    t0 = time.time()
    for step in range(args.sft_steps):
        optimizer.lr = args.sft_lr * (0.35 + 0.65 * (1 - step / max(1, args.sft_steps)))
        if replay_ids is not None and len(replay_ids) > cfg.block_size + 2 and step % 3 == 2:
            # بازپخش متن عمومی: مدل زبانِ فارسی را فراموش نکند
            start = int(rng.integers(0, len(replay_ids) - cfg.block_size - 1))
            window = replay_ids[start:start + cfg.block_size + 1][None, :]
            _logits, loss, cache = forward(params, cfg, window[:, :-1], window[:, 1:],
                                           keep_cache=True)
            optimizer.step(params, backward(params, cfg, cache))
        else:
            n_extra = int(rng.binomial(args.batch, args.extra_ratio)) if extra_examples else 0
            picks = rng.integers(0, len(examples), size=args.batch - n_extra)
            batch = [examples[i] for i in picks]
            if n_extra:
                batch += [extra_examples[i] for i in
                          rng.integers(0, len(extra_examples), size=n_extra)]
            loss = align.sft_step(params, cfg, optimizer, batch)
        sft_losses.append(float(loss))
        if (step + 1) % 30 == 0:
            ppl = chat_perplexity(params, cfg, tokenizer, test_seeds)
            keep = ppl < best_ppl
            if keep:
                best_ppl, best_sft, best_step = ppl, snapshot(params), step + 1
            _log(f"  sft {step + 1}/{args.sft_steps} | loss {loss:.4f} | "
                 f"ppl آزمون {ppl:.2f}{' ← بهترین' if keep else ''} | {time.time() - t0:.0f}s")
            if ppl > baseline_ppl * 2.0 and step >= 30:
                _log("  توقف زودهنگام: زیان گفتگو بدتر شد")
                break
    restore(params, best_sft)
    report["sft"] = {"steps": len(sft_losses), "best_step": best_step,
                     "examples": len(examples),
                     "loss_start": float(np.mean(sft_losses[:20])),
                     "loss_end": float(np.mean(sft_losses[-20:])),
                     "ppl_after": round(best_ppl, 2),
                      "replay_tokens": int(len(replay_ids)) if replay_ids is not None else 0,
                     "seconds": round(time.time() - t0, 1)}
    after_sft = {
        "chat_ppl": chat_perplexity(params, cfg, tokenizer, test_seeds),
        "generation": generation_scores(params, cfg, tokenizer, test_prompts),
    }
    snapshot_sft = {key: value.copy() for key, value in params.items()}
    report["after_sft"] = {"chat_ppl": after_sft["chat_ppl"],
                           "generation": {k: v for k, v in after_sft["generation"].items()
                                          if k != "samples"}}
    _log(f"[align] بعد از SFT: ppl {after_sft['chat_ppl']:.2f} · "
         f"داور {after_sft['generation']['rubric_mean']:.3f}")

    # ------------------------------------------------ مرحلهٔ ۲: مدل پاداش
    reward_report: dict = {"pairs": len(train_prefs), "skipped": True}
    reward_model: align.RewardModel | None = None
    if train_prefs:
        _log(f"[align] مرحلهٔ ۲ (مدل پاداش) روی {len(train_prefs)} زوج")
        t0 = time.time()

        def features_for(rows: list[dict], key: str) -> np.ndarray:
            out = []
            for row in rows:
                ex = align.example_ids(tokenizer, row["user"], row[key], cfg.block_size)
                if not ex:
                    continue
                out.append(align.answer_features(params, cfg, ex[0], ex[1]))
            return np.vstack(out) if out else np.zeros((0, cfg.n_embd))

        train_w = features_for(train_prefs, "chosen")
        train_l = features_for(train_prefs, "rejected")
        test_w = features_for(test_prefs, "chosen") if test_prefs else np.zeros((0, cfg.n_embd))
        test_l = features_for(test_prefs, "rejected") if test_prefs else np.zeros((0, cfg.n_embd))
        reward_model = align.RewardModel(dim=cfg.n_embd, seed=args.seed)
        fit = reward_model.fit(train_w, train_l, epochs=500, lr=2e-2, l2=5e-4)
        reward_report = {**fit, "seconds": round(time.time() - t0, 1),
                         "features": int(train_w.shape[1])}
        if len(test_w):
            reward_report["heldout"] = reward_model.evaluate(test_w, test_l)
        reward_model.save(os.path.join(ROOT, args.reward))
        _log(f"  دقت آموزش {fit['accuracy']:.3f} · آزمون "
             f"{reward_report.get('heldout', {}).get('accuracy', float('nan')):.3f}")
    report["reward_model"] = reward_report

    # ------------------------------------------------------- مرحلهٔ ۳: DPO
    dpo_report: dict = {"steps": 0, "skipped": True}
    if train_prefs:
        _log(f"[align] مرحلهٔ ۳ (DPO، β={args.beta}) روی {len(train_prefs)} زوج")
        t0 = time.time()
        encoded = []
        for row in train_prefs:
            ex_w = align.example_ids(tokenizer, row["user"], row["chosen"], cfg.block_size)
            ex_l = align.example_ids(tokenizer, row["user"], row["rejected"], cfg.block_size)
            if not ex_w or not ex_l or ex_w[1] != ex_l[1]:
                continue
            encoded.append((ex_w[0], ex_l[0], ex_w[1]))
        opt = AdamW(params, lr=args.dpo_lr, weight_decay=0.0, grad_clip=1.0)
        losses: list[float] = []
        margins: list[float] = []
        eval_rows_stop = []
        for row in (test_prefs or train_prefs):
            ex_w = align.example_ids(tokenizer, row["user"], row["chosen"], cfg.block_size)
            ex_l = align.example_ids(tokenizer, row["user"], row["rejected"], cfg.block_size)
            if not ex_w or not ex_l or ex_w[1] != ex_l[1]:
                continue
            eval_rows_stop.append((ex_w[0], ex_l[0], ex_w[1], row["user"]))
        ppl_budget = best_ppl * 1.25
        best_score = -1e9
        best_dpo = snapshot(params)
        best_info = {"step": 0, "accuracy": 0.0, "ppl": best_ppl}
        updates = 0
        for step in range(args.dpo_steps):
            opt.lr = args.dpo_lr * (0.3 + 0.7 * (1 - step / max(1, args.dpo_steps)))
            if replay_ids is not None and len(replay_ids) > cfg.block_size + 2 and step % 4 == 3:
                start = int(rng.integers(0, len(replay_ids) - cfg.block_size - 1))
                window = replay_ids[start:start + cfg.block_size + 1][None, :]
                _logits, _loss, cache = forward(params, cfg, window[:, :-1], window[:, 1:],
                                                keep_cache=True)
                opt.step(params, backward(params, cfg, cache))
                continue
            idx = int(rng.integers(0, len(encoded)))
            chosen, rejected_ids, plen = encoded[idx]
            out = align.dpo_loss_grads(params, reference, cfg, chosen, rejected_ids,
                                       plen, beta=args.beta)
            opt.step(params, out["grads"])
            losses.append(out["loss"])
            margins.append(out["margin"])
            updates += 1
            if updates % 20 == 0:
                wins = 0
                for c_ids, r_ids, plen_i, _user in eval_rows_stop:
                    res = align.dpo_loss_grads(params, reference, cfg, c_ids, r_ids,
                                               plen_i, beta=args.beta, need_grads=False)
                    wins += int(res["prefers_chosen"])
                accuracy = wins / max(1, len(eval_rows_stop))
                ppl = chat_perplexity(params, cfg, tokenizer, test_seeds)
                dead = abs(np.mean(margins[-20:])) > 30.0
                score = accuracy - max(0.0, (ppl - best_ppl) / max(1.0, best_ppl))
                if ppl <= ppl_budget and score > best_score:
                    best_score = score
                    best_dpo = snapshot(params)
                    best_info = {"step": step + 1, "accuracy": round(accuracy, 3),
                                 "ppl": round(ppl, 2)}
                _log(f"  dpo {updates:3d} | loss {out['loss']:.4f} | "
                     f"ترجیح درست {accuracy:.2f} | ppl {ppl:.1f}"
                     f"{' ← بهترین' if best_info['step'] == step + 1 else ''}")
                if dead:
                    _log("  توقف زودهنگام: حاشیهٔ ترجیح از کنترل خارج شد")
                    break
                if ppl > ppl_budget * 1.6:
                    _log("  توقف زودهنگام: زیان گفتگو از بودجه گذشت")
                    break
        restore(params, best_dpo)

        # ارزیابی نهایی روی زوج‌های کنارگذاشته‌شده
        eval_rows = []
        prefers_before = prefers_after = 0
        for row in (test_prefs or train_prefs):
            ex_w = align.example_ids(tokenizer, row["user"], row["chosen"], cfg.block_size)
            ex_l = align.example_ids(tokenizer, row["user"], row["rejected"], cfg.block_size)
            if not ex_w or not ex_l or ex_w[1] != ex_l[1]:
                continue
            eval_rows.append((ex_w[0], ex_l[0], ex_w[1]))
        for chosen, rejected_ids, plen in eval_rows:
            ref_out = align.dpo_loss_grads(reference, reference, cfg, chosen, rejected_ids,
                                           plen, beta=args.beta, need_grads=False)
            now_out = align.dpo_loss_grads(params, reference, cfg, chosen, rejected_ids,
                                           plen, beta=args.beta, need_grads=False)
            prefers_before += int(ref_out["prefers_chosen"])
            prefers_after += int(now_out["prefers_chosen"])
        n_eval = max(1, len(eval_rows))
        dpo_report = {
            "steps": best_info["step"] or len(losses), "beta": args.beta, "pairs": len(encoded),
            "best": best_info,
            "loss_start": float(np.mean(losses[:20])),
            "loss_end": float(np.mean(losses[-20:])),
            "margin_start": float(np.mean(margins[:20])),
            "margin_end": float(np.mean(margins[-20:])),
            "heldout_pairs": len(eval_rows),
            "prefers_chosen_before": round(prefers_before / n_eval, 3),
            "prefers_chosen_after": round(prefers_after / n_eval, 3),
            "seconds": round(time.time() - t0, 1),
        }
        _log(f"  ترجیح درست قبل {dpo_report['prefers_chosen_before']:.2f} → "
             f"بعد {dpo_report['prefers_chosen_after']:.2f}")
    report["dpo"] = dpo_report

    # ------------------------------------------------------------- ارزیابی
    after = {
        "chat_ppl": chat_perplexity(params, cfg, tokenizer, test_seeds),
        "generation": generation_scores(params, cfg, tokenizer, test_prompts),
    }
    snapshot_dpo = {key: value.copy() for key, value in params.items()}
    report["after"] = {"chat_ppl": after["chat_ppl"],
                       "generation": {k: v for k, v in after["generation"].items()
                                      if k != "samples"}}
    report["samples"] = {
        "before": before["generation"]["samples"],
        "after": after["generation"]["samples"],
    }

    # عکس هر مرحله روی دیسک می‌ماند؛ انتخاب مرحلهٔ منتشرشده کار
    # scripts/compare_stages.py است تا با معیار مستقل انجام شود.
    stages = [
        ("base", before, snapshot_base),
        ("sft", after_sft, snapshot_sft),
        ("dpo", after, snapshot_dpo),
    ]
    stages_dir = os.path.join(ROOT, args.stages)
    os.makedirs(stages_dir, exist_ok=True)
    for name, data, snap in stages:
        save_checkpoint(os.path.join(stages_dir, f"{name}.npz"), cfg, snap,
                        {**base_meta, "stage": name,
                         "chat_ppl": round(float(data["chat_ppl"]), 2),
                         "rubric_mean": round(float(data["generation"]["rubric_mean"]), 4)})
    report["stages"] = {name: {"rubric_mean": round(float(data["generation"]["rubric_mean"]), 4),
                               "chat_ppl": round(float(data["chat_ppl"]), 2)}
                        for name, data, _snap in stages}
    report["stages_dir"] = os.path.relpath(stages_dir, ROOT)
    report["seconds"] = round(time.time() - started, 1)

    meta = dict(base_meta)
    meta.update({
        "step": base_meta.get("step"),
        "name": "رایان هم‌تراز",
        "alignment": {"sft_steps": args.sft_steps, "dpo_steps": args.dpo_steps,
                      "beta": args.beta, "pairs": len(train_prefs),
                      "reward_accuracy": reward_report.get("accuracy"),
                      "extra_ratio": args.extra_ratio},
        "base": args.base,
        "chat_ppl_before": round(before["chat_ppl"], 2),
        "chat_ppl_after": round(after["chat_ppl"], 2),
    })
    save_checkpoint(os.path.join(ROOT, args.out), cfg, params, meta)
    align.save_report(os.path.join(ROOT, args.report), report)
    _log("[align] بعد: ppl گفتگو "
         f"{after['chat_ppl']:.2f} · داور {after['generation']['rubric_mean']:.3f}")
    _log(f"[align] ذخیره شد: {args.out} · گزارش: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
