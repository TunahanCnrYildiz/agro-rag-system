"""Tests for the eval answer log (evals/answer_log.py)."""

import json

from evals import answer_log
from evals.answer_log import AnswerLog
from src.engine import ChatResult, RecommendedProduct

CASE = {"id": "probe", "category": "nutrition", "query": "azot nasil verilir?"}


def _result(answer="azot verin.", products=("FLY AZOT",)):
    return ChatResult(answer, [RecommendedProduct(p, "http://x") for p in products])


def _log(tmp_path, monkeypatch, mode="full", provider="local:test-model"):
    """RUNS_DIR is read in __init__, so it must be patched BEFORE constructing."""
    monkeypatch.setattr(answer_log, "RUNS_DIR", tmp_path / "runs")
    return AnswerLog(mode=mode, provider=provider)


def _rows(log):
    return [json.loads(line)
            for line in log.path.read_text(encoding="utf-8").strip().splitlines()]


def test_record_writes_one_json_line_with_the_answer_and_products(tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch)

    log.record(case=CASE, repeat_index=0, ablated=False, result=_result(),
               grounding=True, guardrail=True, products_ok=True, no_answer=None)

    rows = _rows(log)
    assert len(rows) == 1
    row = rows[0]
    assert row["case_id"] == "probe"
    assert row["category"] == "nutrition"
    assert row["query"] == "azot nasil verilir?"
    assert row["answer"] == "azot verin."
    assert row["products"] == ["FLY AZOT"]
    assert row["grounding"] is True
    assert row["guardrail"] is True
    assert row["products_ok"] is True
    assert row["no_answer"] is None
    assert row["ablated"] is False
    assert row["mode"] == "full"
    assert row["provider"] == "local:test-model"
    assert row["repeat_index"] == 0
    assert row["ts"]
    assert log.count == 1


def test_rows_are_readable_before_the_run_ends(tmp_path, monkeypatch):
    """run_faithfulness() sys.exit()s mid-run on an unanswered sample, so a
    buffered writer would lose the whole file exactly when it matters most."""
    log = _log(tmp_path, monkeypatch)

    log.record(case=CASE, repeat_index=0, ablated=False, result=_result("bir"),
               grounding=True, guardrail=True, products_ok=True, no_answer=None)
    on_disk_after_first = log.path.read_text(encoding="utf-8")

    log.record(case=CASE, repeat_index=1, ablated=False, result=_result("iki"),
               grounding=False, guardrail=True, products_ok=True, no_answer=None)

    assert json.loads(on_disk_after_first.strip())["answer"] == "bir"
    assert [r["answer"] for r in _rows(log)] == ["bir", "iki"]


def test_ablated_samples_are_distinguishable(tmp_path, monkeypatch):
    log = _log(tmp_path, monkeypatch, mode="faithfulness")

    log.record(case=CASE, repeat_index=0, ablated=False, result=_result(),
               grounding=True, guardrail=True, products_ok=None, no_answer=None)
    log.record(case=CASE, repeat_index=0, ablated=True, result=_result(),
               grounding=False, guardrail=True, products_ok=None, no_answer=None)

    rows = _rows(log)
    assert [r["ablated"] for r in rows] == [False, True]
    assert rows[0]["mode"] == "faithfulness"
    assert rows[0]["products_ok"] is None


def test_no_file_until_the_first_record(tmp_path, monkeypatch):
    """A run that generates nothing (e.g. --fast) leaves no empty file behind."""
    log = _log(tmp_path, monkeypatch)

    assert not log.path.exists()
    assert log.count == 0


def test_a_write_failure_never_raises_and_warns_once(tmp_path, monkeypatch, capsys):
    """The binding constraint: losing a 25-minute run to a disk error would be a
    worse bug than the missing answer texts this module exists to fix."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")     # a FILE where a dir must go
    monkeypatch.setattr(answer_log, "RUNS_DIR", blocker / "runs")
    log = AnswerLog(mode="full", provider="local:test-model")

    for i in range(3):
        log.record(case=CASE, repeat_index=i, ablated=False, result=_result(),
                   grounding=True, guardrail=True, products_ok=True, no_answer=None)

    assert log.count == 0
    assert capsys.readouterr().out.count("[answers] WARNING") == 1
