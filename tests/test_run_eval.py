"""Harness tests for evals/run_eval.py (the LLM and store are stubbed)."""

import pytest

from evals import run_eval


class _R:
    """Stand-in for engine.answer()'s ChatResult."""

    def __init__(self, answer, products=()):
        self.answer = answer
        self.recommended_products = list(products)


ONE_CASE = [{
    "id": "probe", "category": "nutrition", "query": "q",
    "retrieval": "nonempty", "products": "any",
    "context_any": ["azot"],
    "answer_any": ["azot"],
}]


def _stub(monkeypatch, answers):
    """Serve `answers` one per answer() call; context is fixed and on-topic."""
    calls = {"ctx": 0, "ans": 0}

    def fake_ctx(q, k=None):
        calls["ctx"] += 1
        return "[Kaynak: x.pdf, s.1]\nazot iceren metin"

    def fake_answer(q, history=None):
        i = min(calls["ans"], len(answers) - 1)
        calls["ans"] += 1
        return _R(answers[i])

    monkeypatch.setattr(run_eval.engine, "retrieve_context", fake_ctx)
    monkeypatch.setattr(run_eval.engine, "answer", fake_answer)
    monkeypatch.setattr(run_eval, "CASES", ONE_CASE)
    return calls


def test_repeat_samples_answer_n_times_but_context_once(monkeypatch):
    """retrieval/context are deterministic - sampling them N times is waste."""
    calls = _stub(monkeypatch, ["azot verin."])

    rc = run_eval.run(fast=False, repeat=3)

    assert rc == 0
    assert calls["ans"] == 3      # the sampled dimensions
    assert calls["ctx"] == 1      # the deterministic ones


def test_repeat_fails_the_case_when_any_sample_fails(monkeypatch):
    """A guardrail that leaks 1 time in 3 is a FAILURE, not a 2/3 pass."""
    _stub(monkeypatch, ["azot verin.", "bos konu", "azot verin."])

    rc = run_eval.run(fast=False, repeat=3)

    assert rc == 1                # non-zero exit: the case failed


def test_repeat_one_is_the_default_and_calls_answer_once(monkeypatch):
    calls = _stub(monkeypatch, ["azot verin."])

    rc = run_eval.run(fast=False)

    assert rc == 0
    assert calls["ans"] == 1


def test_fast_mode_rejects_repeat(monkeypatch):
    _stub(monkeypatch, ["azot verin."])
    with pytest.raises(SystemExit):
        run_eval.run(fast=True, repeat=2)


def test_repeat_one_prints_the_original_per_case_format(monkeypatch, capsys):
    """The stated regression risk of --repeat: default output must not drift.

    At repeat=1 the per-case line must still read `prod=True ...`, NOT the
    fraction form (`prod=1/1`) that N>1 uses, and the dimension rates must read
    over cases (1/1), since one sample per case collapses to the old numbers.
    """
    _stub(monkeypatch, ["azot verin."])

    run_eval.run(fast=False)
    out = capsys.readouterr().out

    assert "prod=True ground=True guard=True" in out
    assert "prod=1/1" not in out                 # the N>1 form must not leak in
    assert "1/1 cases passed" in out
    assert "grounding: 1/1" in out


def test_repeat_many_prints_the_fraction_format(monkeypatch, capsys):
    _stub(monkeypatch, ["azot verin."])

    run_eval.run(fast=False, repeat=3)
    out = capsys.readouterr().out

    assert "prod=3/3 ground=3/3 guard=3/3" in out
    assert "grounding: 3/3" in out               # rate is over SAMPLES, not cases
