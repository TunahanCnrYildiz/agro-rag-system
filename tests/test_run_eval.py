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


TWO_CATEGORIES = [
    {"id": "nut_a", "category": "nutrition", "query": "q1",
     "retrieval": "nonempty", "products": "any",
     "context_any": ["azot"], "answer_any": ["azot"]},
    {"id": "chem_a", "category": "chemical", "query": "q2",
     "retrieval": "nonempty", "products": "any",
     "context_any": ["azot"], "answer_any": ["azot"]},
]


def test_only_selects_by_category(monkeypatch, capsys):
    _stub(monkeypatch, ["azot verin."])
    monkeypatch.setattr(run_eval, "CASES", TWO_CATEGORIES)

    rc = run_eval.run(fast=False, only="chemical")
    out = capsys.readouterr().out

    assert rc == 0
    assert "chem_a" in out
    assert "nut_a" not in out
    assert "1/1 cases passed" in out


def test_only_selects_by_case_id(monkeypatch, capsys):
    _stub(monkeypatch, ["azot verin."])
    monkeypatch.setattr(run_eval, "CASES", TWO_CATEGORIES)

    run_eval.run(fast=False, only="nut_a")
    out = capsys.readouterr().out

    assert "nut_a" in out
    assert "chem_a" not in out


def test_only_that_matches_nothing_is_an_error(monkeypatch):
    """A silent '0/0 cases passed' would be a green that means nothing."""
    _stub(monkeypatch, ["azot verin."])
    monkeypatch.setattr(run_eval, "CASES", TWO_CATEGORIES)

    with pytest.raises(SystemExit):
        run_eval.run(fast=False, only="typo")


def test_only_defaults_to_every_case(monkeypatch, capsys):
    _stub(monkeypatch, ["azot verin."])
    monkeypatch.setattr(run_eval, "CASES", TWO_CATEGORIES)

    run_eval.run(fast=False)
    out = capsys.readouterr().out

    assert "2/2 cases passed" in out


def test_ablation_verdict_all_local_cases_lost_grounding():
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "local_b", "cat": "local", "grounding": False}]
    assert run_eval._ablation_verdict(rows) == (0, [])


def test_ablation_verdict_flags_a_local_case_that_survives_ablation():
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "local_b", "cat": "local", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (1, ["local_b"])


def test_ablation_verdict_ignores_non_local_cases():
    """Ordinary cases fail under ablation by construction - if they moved the
    exit code it would be 1 on every run and mean nothing."""
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "tomato_nutrition", "cat": "nutrition", "grounding": True},
            {"id": "compost", "cat": "nutrition", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (0, [])


def test_ablation_verdict_with_no_local_case_fails_rather_than_passing_vacuously():
    """'0 of 0 discriminate' must not read as success - same shape as the
    all([]) bug this project already shipped once."""
    rows = [{"id": "compost", "cat": "nutrition", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (1, [])


def test_corpus_ablated_empties_the_path_answer_uses(monkeypatch):
    from src import engine
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "REAL")
    assert engine.retrieve_context("x") == "REAL"
    with run_eval._corpus_ablated():
        assert engine.retrieve_context("x") == ""
    assert engine.retrieve_context("x") == "REAL"


LOCAL_CASE = [{
    "id": "local_probe", "category": "local", "query": "q",
    "retrieval": "nonempty", "products": "none",
    "context_any": ["deveci"],
    "answer_any": ["2±0,5"],
}]


def test_no_context_reports_retrieval_and_context_as_n_a(monkeypatch, capsys):
    """The flag EMPTIES those two dimensions, so scoring them would print a wall
    of tautological FAILs and bury the ablation's actual signal."""
    _stub(monkeypatch, ["genel bir cevap"])
    monkeypatch.setattr(run_eval, "CASES", LOCAL_CASE)

    run_eval.run(fast=False, no_context=True)
    out = capsys.readouterr().out

    assert "ret=n/a ctx=n/a" in out
    assert "ret=False" not in out
    assert "retrieval: n/a" in out


def test_no_context_rejects_fast(monkeypatch):
    """--fast never calls answer(), so there is nothing to ablate."""
    _stub(monkeypatch, ["azot verin."])
    with pytest.raises(SystemExit):
        run_eval.run(fast=True, no_context=True)
