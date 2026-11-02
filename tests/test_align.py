"""آزمون‌های هم‌ترازسازی (SFT، مدل پاداش، DPO) و داور خودکار.

    python -m pytest tests/test_align.py -q
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rayan import align, rubric  # noqa: E402
from rayan.model import GPTConfig, init_params  # noqa: E402
from rayan.model import AdamW  # noqa: E402


class FakeTokenizer:
    """توکن‌ساز ساده: هر نویسه یک شناسه، با واژگان محدود و پایدار."""

    def __init__(self, vocab: int = 64) -> None:
        self.vocab = vocab

    def encode(self, text: str) -> list[int]:
        return [1 + (ord(ch) % (self.vocab - 1)) for ch in text]


def tiny_cfg() -> GPTConfig:
    return GPTConfig(vocab_size=64, block_size=64, n_layer=2, n_head=2, n_embd=16)


# ------------------------------------------------------------------ شکل داده


def test_example_ids_marks_prompt_length():
    tok = FakeTokenizer()
    ids, prompt_len = align.example_ids(tok, "سلام", "سلام علیکم", block_size=128)
    assert 0 < prompt_len < len(ids)
    assert ids[:prompt_len] == tok.encode(align.PROMPT_TEMPLATE.format(user="سلام"))
    assert ids[-2:] == tok.encode(align.TURN_END)[-2:]


def test_example_ids_rejects_long_and_empty():
    tok = FakeTokenizer()
    assert align.example_ids(tok, "پ", "پ" * 500, block_size=32) is None
    # پاسخ خالی به‌طور خودکار با نشانهٔ پایان نوبت بسته می‌شود، پس پذیرفتنی است
    ids, prompt_len = align.example_ids(tok, "پرسش", "", block_size=128)
    assert ids[prompt_len:] == tok.encode(align.TURN_END)


def test_preference_file_is_well_formed():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "preferences.jsonl")
    if not os.path.exists(path):
        pytest.skip("پروندهٔ ترجیح‌ها موجود نیست")
    rows = align.load_preferences(path)
    assert rows, "پروندهٔ ترجیح‌ها خالی است"
    for row in rows:
        assert {"user", "chosen", "rejected"} <= row.keys()
        assert row["chosen"].strip() and row["rejected"].strip()
        assert row["chosen"] != row["rejected"]


# ------------------------------------------------------------------ SFT


def test_sft_step_shifts_targets():
    """اگر جابه‌جایی هدف درست باشد، با دادهٔ تکراری زیان به‌سرعت می‌افتد."""
    cfg = tiny_cfg()
    params = init_params(cfg, seed=5, dtype=np.float64)
    tok = FakeTokenizer()
    example = align.example_ids(tok, "سلام", "سلام دنیا", block_size=cfg.block_size)
    assert example is not None
    opt = AdamW(params, lr=1e-2, weight_decay=0.0, grad_clip=1.0)
    first = align.sft_step(params, cfg, opt, [example])
    for _ in range(12):
        last = align.sft_step(params, cfg, opt, [example])
    assert np.isfinite(first) and np.isfinite(last)
    assert last < first, f"زیان کاهش نیافت: {first:.3f} → {last:.3f}"


def test_sft_losses_only_answer_tokens():
    """زیان SFT روی توکن‌های پاسخ است، نه کل دنباله."""
    cfg = tiny_cfg()
    params = init_params(cfg, seed=9, dtype=np.float64)
    ids, prompt_len = align.example_ids(FakeTokenizer(), "الف", "ب پ ت ث",
                                       block_size=cfg.block_size)
    arr = np.asarray([ids], dtype=np.int64)
    logits, _ = align.forward(params, cfg, arr[:, :-1], None)
    logp = align._log_softmax(logits[0, prompt_len - 1:len(ids) - 1])
    targets = np.asarray(ids[prompt_len:], dtype=np.int64)
    manual = float(-logp[np.arange(targets.size), targets].mean())
    opt = AdamW(params, lr=0.0, weight_decay=0.0)
    assert align.sft_step(params, cfg, opt, [(ids, prompt_len)]) == pytest.approx(manual, rel=1e-9)


def test_sft_full_loss_matches_plain_forward():
    cfg = tiny_cfg()
    params = init_params(cfg, seed=9, dtype=np.float64)
    ids, _prompt = align.example_ids(FakeTokenizer(), "الف", "ب پ ت ث", block_size=cfg.block_size)
    arr = np.asarray([ids], dtype=np.int64)
    _logits, loss = align.forward(params, cfg, arr[:, :-1], arr[:, 1:])
    opt = AdamW(params, lr=0.0, weight_decay=0.0)
    measured = align.sft_step(params, cfg, opt, [(ids, 0)], answer_only=False)
    assert measured == pytest.approx(float(loss), rel=1e-9)


# ------------------------------------------------------------------ DPO


def _gradcheck_dpo(name: str, index: tuple[int, ...], eps: float = 1e-4) -> float:
    cfg = tiny_cfg()
    policy = init_params(cfg, seed=11, dtype=np.float64)
    reference = {key: value.copy() for key, value in policy.items()}
    rng = np.random.default_rng(0)
    ids_w = [1] + rng.integers(2, cfg.vocab_size, 9).tolist()
    ids_l = [1] + rng.integers(2, cfg.vocab_size, 9).tolist()
    prompt_len = 2

    out = align.dpo_loss_grads(policy, reference, cfg, ids_w, ids_l, prompt_len, beta=0.3)
    grad = out["grads"][name][index]

    original = policy[name][index]
    policy[name][index] = original + eps
    plus = align.dpo_loss_grads(policy, reference, cfg, ids_w, ids_l, prompt_len,
                                beta=0.3, need_grads=False)["loss"]
    policy[name][index] = original - eps
    minus = align.dpo_loss_grads(policy, reference, cfg, ids_w, ids_l, prompt_len,
                                 beta=0.3, need_grads=False)["loss"]
    policy[name][index] = original
    numeric = (plus - minus) / (2 * eps)
    return abs(numeric - grad) / max(1e-8, abs(numeric) + abs(grad))


@pytest.mark.parametrize("name", ["wte", "lnf_g", "h0.mlp2_w"])
def test_dpo_gradient_matches_finite_differences(name):
    worst = 0.0
    for index in [(0, 0), (1, 3), (2, 1)]:
        try:
            worst = max(worst, _gradcheck_dpo(name, index))
        except IndexError:  # pragma: no cover - بستگی به شکل پارامتر دارد
            continue
    assert worst < 1e-5, f"خطای نسبی گرادیان {name}: {worst:.2e}"


def test_dpo_is_zero_when_policy_equals_reference():
    cfg = tiny_cfg()
    params = init_params(cfg, seed=13, dtype=np.float64)
    reference = {key: value.copy() for key, value in params.items()}
    out = align.dpo_loss_grads(params, reference, cfg, [1, 2, 3, 4], [1, 5, 6, 7], 2)
    assert out["loss"] == pytest.approx(np.log(2.0), rel=1e-6)
    assert out["margin"] == pytest.approx(0.0, abs=1e-9)


def test_dpo_prefers_the_sequence_the_policy_actually_likes():
    """حاشیه هم‌علامت اختلاف درست‌نمایی سیاست است."""
    cfg = tiny_cfg()
    policy = init_params(cfg, seed=17, dtype=np.float64)
    reference = {key: value.copy() for key, value in policy.items()}
    ids_w = [1, 2, 3, 4, 5]
    ids_l = [1, 6, 7, 8, 9]
    out = align.dpo_loss_grads(policy, reference, cfg, ids_w, ids_l, 2, beta=0.5)
    expected = (out["logp_chosen"] - out["ref_chosen"]) - (out["logp_rejected"] - out["ref_rejected"])
    assert out["margin"] == pytest.approx(expected, rel=1e-9)


# ------------------------------------------------------------------ مدل پاداش


def test_reward_model_learns_separable_preferences():
    rng = np.random.default_rng(3)
    dim = 8
    good = rng.normal(1.0, 0.1, (60, dim))
    bad = rng.normal(-1.0, 0.1, (60, dim))
    model = align.RewardModel(dim=dim, seed=1)
    report = model.fit(good, bad, epochs=200, lr=0.05, l2=1e-4)
    assert report["accuracy"] > 0.95
    assert model.score(good[0]) > model.score(bad[0])


def test_reward_model_round_trip(tmp_path):
    rng = np.random.default_rng(4)
    model = align.RewardModel(dim=6, seed=2)
    model.fit(rng.normal(1, 0.1, (20, 6)), rng.normal(-1, 0.1, (20, 6)), epochs=50)
    path = tmp_path / "reward.npz"
    model.save(str(path))
    again = align.RewardModel.load(str(path))
    probe = rng.normal(0, 1, (3, 6))
    assert np.allclose(again.scores(probe), model.scores(probe))


def test_reward_model_evaluate_reports_accuracy():
    rng = np.random.default_rng(5)
    model = align.RewardModel(dim=5, seed=3)
    model.fit(rng.normal(1, 0.1, (30, 5)), rng.normal(-1, 0.1, (30, 5)), epochs=80)
    held = model.evaluate(rng.normal(1, 0.1, (10, 5)), rng.normal(-1, 0.1, (10, 5)))
    assert 0.0 <= held["accuracy"] <= 1.0
    assert 0.0 < held["logloss"] < 1.0


# ------------------------------------------------------------------ داور


def test_rubric_rewards_expected_content():
    good = rubric.score("پایتخت ایران تهران است و پرجمعیت‌ترین شهر کشور به‌شمار می‌رود.",
                        reference="تهران پایتخت ایران است.", expected=["تهران"])
    bad = rubric.score("نمی‌دانم.", reference="تهران پایتخت ایران است.", expected=["تهران"])
    assert rubric.prefer(good, bad)


def test_rubric_punishes_repetition():
    loop = rubric.score("کتاب " * 80, reference="کتاب")
    once = rubric.score("کتاب خوبی بود که خواندم.")
    assert loop["repetition"] > 0.5
    assert once["total"] > loop["total"]


def test_rubric_flags_prompt_leak_and_latin():
    leak = rubric.score("سلام <|doc|> پاسخ من این است")
    assert leak["leak"] is True and leak["total"] < 1.0
    latin = rubric.score("this answer is entirely written in english words")
    assert latin["total"] < 0


def test_rubric_short_answer_penalised():
    short = rubric.score("بله")
    assert short["parts"]["too_short"] == -1.0


def test_prefer_requires_minimum_gap():
    a = {"total": 1.2}
    b = {"total": 1.1}
    assert rubric.prefer(a, b, min_gap=0.05)
    assert not rubric.prefer(a, b, min_gap=0.25)


# ------------------------------------------------------------------ گزارش


def test_summarize_and_report(tmp_path):
    stats = align.summarize([1.0, 2.0, 3.0])
    assert stats["n"] == 3
    assert stats["mean"] == pytest.approx(2.0)
    path = tmp_path / "r.json"
    align.save_report(str(path), {"ok": True, "value": 2.0})
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True and payload["value"] == 2.0
    assert "written_at" in payload
