"""آزمون‌های انتخاب مرحلهٔ منتشرشده و صداقت اعداد کارت مدل.

    python -m pytest tests/test_stages.py -q
"""
from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "scripts"))

import compare_stages  # noqa: E402


def stage(hits: list[int], totals: list[float], ppl: float) -> dict:
    return {"hit_flags": hits, "hit_rate": sum(hits) / len(hits),
            "rubric_totals": totals, "rubric_mean": sum(totals) / len(totals),
            "chat_ppl": ppl}


def test_hit_flags_normalises_arabic_letters():
    prompts = [{"expected": ["تهران"]}]
    assert compare_stages.hit_flags(["پایتخت ایران تهران است"], prompts) == [1]
    assert compare_stages.hit_flags(["هیچ چیزی نمی‌دانم"], prompts) == [0]


def test_clear_lead_in_hits_wins():
    results = {
        "base": stage([0] * 20 + [1] * 2, [1.2] * 22, 30.0),
        "sft": stage([1] * 20 + [0] * 2, [1.1] * 22, 25.0),
    }
    winner, decision = compare_stages.choose(results)
    assert winner == "sft"
    assert "برخورد" in decision["rule"]


def test_tie_falls_back_to_lower_perplexity():
    results = {
        "base": stage([1, 0, 1, 0, 1, 0, 1, 0], [1.30] * 8, 33.4),
        "sft": stage([1, 0, 1, 0, 1, 0, 1, 0], [1.30] * 8, 29.3),
    }
    winner, decision = compare_stages.choose(results)
    assert winner == "sft"
    assert "تساوی" in decision["rule"]
    assert decision["hit_probability"] < 0.9


def test_rubric_difference_can_decide_when_significant():
    results = {
        "base": stage([0, 1] * 10, [0.5] * 20, 33.0),
        "dpo": stage([0, 1] * 10, [2.0] * 20, 40.0),
    }
    winner, decision = compare_stages.choose(results)
    assert winner == "dpo"
    assert "داور" in decision["rule"]


def test_bootstrap_probability_bounds():
    assert compare_stages.bootstrap_probability([1.0] * 30, [0.0] * 30) > 0.99
    assert compare_stages.bootstrap_probability([0.0] * 30, [1.0] * 30) < 0.01
    assert compare_stages.bootstrap_probability([], []) == 0.0


def test_run_config_ignored_when_it_belongs_to_another_model(monkeypatch):
    from web import server

    monkeypatch.setattr(server, "_run_config", lambda: {"params": 16_889_856, "ppl": 568.5})
    monkeypatch.setattr(server, "engine",
                        types.SimpleNamespace(info=lambda: {"params": 6_574_848},
                                              checkpoint="checkpoints/last.npz"))
    assert server._run_config_for_active() == {}
    assert server._final_eval() is None


def test_run_config_used_when_parameters_match(monkeypatch):
    from web import server

    run = {"params": 6_574_848, "steps": 2400, "val_loss": 3.1, "ppl": 22.2}
    monkeypatch.setattr(server, "_run_config", lambda: run)
    monkeypatch.setattr(server, "engine",
                        types.SimpleNamespace(info=lambda: {"params": 6_574_848},
                                              checkpoint="checkpoints/last.npz"))
    assert server._run_config_for_active() == run
    assert server._final_eval()["ppl"] == pytest.approx(22.2)
