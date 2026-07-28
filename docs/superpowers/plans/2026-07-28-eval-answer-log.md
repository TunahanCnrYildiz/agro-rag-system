# Eval Answer Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every answer the eval generates (text + recommended products + verdicts) as one JSON line per sample, so a case's behaviour can be diagnosed after the run instead of guessed at.

**Architecture:** A new focused module `evals/answer_log.py` owns all logging I/O behind an `AnswerLog` class; `evals/run_eval.py` constructs one per run and calls `record()` at the two places answers are generated (`run()`'s repeat loop and `run_faithfulness()`'s `grounded_hits()`). Writes are appended and flushed per sample, and every failure is swallowed inside the module so the log can never affect a verdict or fail a run.

**Tech Stack:** Python 3.12, stdlib `json` / `pathlib` / `datetime`, pytest.

## Global Constraints

- **The log is a PURE SIDE EFFECT.** It feeds no verdict, rate, label, or exit code. No scoring rule, threshold, or exit code changes in this plan.
- **A write failure must NEVER fail the run.** All I/O is wrapped; on error the log warns **once** and the run continues.
- **JSONL, one line per sample, appended and flushed immediately** — never buffered to the end. `run_faithfulness()` calls `sys.exit()` mid-run (`evals/run_eval.py:380`), and a buffered writer would lose the file exactly when it matters most.
- **Location:** `evals/runs/<UTC-timestamp>-<mode>.jsonl`; `evals/runs/` is gitignored.
- **The provider stamp goes INSIDE each row, never into the filename** — model ids contain `/` (e.g. `google/gemma-4-26b-a4b-it`).
- **`ablated` is never inferred from `mode`.** Both modes can produce either value: `run(no_context=True)` is ablated `full`, and `run_faithfulness()` produces both.
- **`products_ok` is `null` under `--faithfulness`**, which does not gate products.
- **`--fast` writes nothing and creates no file** (it never calls `answer()`).
- Row fields, exactly: `ts`, `mode`, `provider`, `case_id`, `category`, `query`, `repeat_index`, `ablated`, `answer`, `products`, `grounding`, `guardrail`, `products_ok`, `no_answer`.
- Commit style: short natural English message, **no `Co-Authored-By` trailer**.
- Run everything from the repo root with `python -m pytest` (Windows, Python 3.12).

## File Structure

| File | Responsibility |
|---|---|
| `evals/answer_log.py` (create) | All answer-logging state and I/O. Single class `AnswerLog`; nothing else imports the filesystem for this feature. |
| `tests/test_answer_log.py` (create) | Unit tests for the module in isolation, including the never-fail-the-run guarantee. |
| `tests/conftest.py` (create) | One autouse fixture redirecting `RUNS_DIR` to a tmp dir, so the suite never litters the real `evals/runs/`. |
| `evals/run_eval.py` (modify) | Constructs the log and calls `record()` at the two answer-generating sites. No other change. |
| `tests/test_run_eval.py` (modify) | Wiring tests: rows written, failure isolation, fast mode, faithfulness normal/ablated + abort. |
| `.gitignore` (modify) | Ignore `evals/runs/`. |

**Baseline before this plan:** `pytest -q` = **237 passing**.

---

### Task 1: The `AnswerLog` module

**Files:**
- Create: `evals/answer_log.py`
- Test: `tests/test_answer_log.py`

**Interfaces:**
- Consumes: `src.engine.ChatResult` / `RecommendedProduct` only as duck-typed input (`result.answer`, `result.recommended_products[].title`) — no import needed in the module.
- Produces (used by Tasks 2 and 3):
  - `evals.answer_log.RUNS_DIR: Path` — module-level, monkeypatchable in tests.
  - `AnswerLog(mode: str, provider: str)`
  - `AnswerLog.record(*, case: dict, repeat_index: int, ablated: bool, result, grounding: bool, guardrail: bool, products_ok: bool | None, no_answer: str | None) -> None` — keyword-only.
  - `AnswerLog.path -> Path`, `AnswerLog.count -> int`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_answer_log.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_answer_log.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'evals.answer_log'`.

- [ ] **Step 3: Write the module**

Create `evals/answer_log.py`:

```python
"""Per-sample answer log for the eval harness.

The eval scores each generated answer into booleans and would otherwise discard
the text. That has already cost a diagnosis: two NOPRODUCT-backstop leakers
(`pollination_squash`, `local_hachiya_persimmon`) closed as "cause unresolved"
because no answer text survived the run. This module persists every sample as
one JSON line.

DELIBERATELY a pure side effect: nothing here feeds a verdict, a rate, or an exit
code, and a write failure NEVER fails the run - a 25-minute eval must not die of
a disk error. See docs/superpowers/specs/2026-07-28-eval-answer-log-design.md.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# Module-level so tests can redirect it; read in __init__.
RUNS_DIR: Path = Path(__file__).resolve().parent / "runs"


class AnswerLog:
    """Append one JSON line per generated sample.

    The file is created lazily on the first record(), so a run that generates
    nothing (--fast never calls answer()) leaves no empty file behind.
    """

    def __init__(self, mode: str, provider: str) -> None:
        self._mode = mode
        self._provider = provider
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # The provider stamp carries '/' in hosted model ids, so it goes in the
        # ROWS, never the filename.
        self._path = RUNS_DIR / f"{stamp}-{mode}.jsonl"
        self._count = 0
        self._warned = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def count(self) -> int:
        return self._count

    def record(self, *, case: dict, repeat_index: int, ablated: bool,
               result, grounding: bool, guardrail: bool,
               products_ok: bool | None, no_answer: str | None) -> None:
        """Log one sample. `ablated` is passed in, never inferred from `mode`:
        both modes can produce either value."""
        self._write({
            "ts": datetime.now(timezone.utc).isoformat(),
            "mode": self._mode,
            "provider": self._provider,
            "case_id": case.get("id"),
            "category": case.get("category"),
            "query": case.get("query"),
            "repeat_index": repeat_index,
            "ablated": ablated,
            "answer": result.answer,
            "products": [p.title for p in result.recommended_products],
            "grounding": grounding,
            "guardrail": guardrail,
            "products_ok": products_ok,
            "no_answer": no_answer,
        })

    def _write(self, row: dict) -> None:
        """All I/O funnels here so one guard covers it. Appended and flushed per
        row: run_faithfulness() aborts mid-run, and the aborting sample is
        precisely the evidence someone will want."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._count += 1
        except Exception as exc:  # noqa: BLE001 - logging must never fail a run
            if not self._warned:
                self._warned = True
                print(f"[answers] WARNING: could not write {self._path}: {exc}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_answer_log.py -q`
Expected: PASS, 5 tests, output pristine.

- [ ] **Step 5: Commit**

```bash
git add evals/answer_log.py tests/test_answer_log.py
git commit -m "Add per-sample answer log for the eval harness"
```

---

### Task 2: Wire into `run()`, isolate tests, ignore the runs dir

**Files:**
- Modify: `evals/run_eval.py` (imports near line 24; `run()` body around lines 216-325)
- Create: `tests/conftest.py`
- Modify: `.gitignore` (append)
- Test: `tests/test_run_eval.py` (add 3 tests; add a `json` import)

**Interfaces:**
- Consumes: `evals.answer_log.AnswerLog` and `RUNS_DIR` from Task 1, with the exact keyword-only `record()` signature listed there.
- Produces: nothing new for Task 3 beyond the established pattern (Task 3 constructs its own `AnswerLog` with `mode="faithfulness"`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_run_eval.py`, change the import block at the top (currently lines 3-7) to add `json`:

```python
import json

import pytest

from evals import answer_log
from evals import run_eval
from src import engine
from src.engine import ChatResult
```

Then append these three tests to the end of the file:

```python
def test_run_records_every_sample_with_its_answer_text(monkeypatch, tmp_path):
    """The point of the log: the generated text survives the run."""
    _stub(monkeypatch, ["azot verin."])
    runs = tmp_path / "runs"
    monkeypatch.setattr(answer_log, "RUNS_DIR", runs)

    run_eval.run(fast=False, repeat=2)

    files = list(runs.glob("*.jsonl"))
    assert len(files) == 1
    rows = [json.loads(line) for line
            in files[0].read_text(encoding="utf-8").strip().splitlines()]
    assert [r["answer"] for r in rows] == ["azot verin.", "azot verin."]
    assert [r["repeat_index"] for r in rows] == [0, 1]
    assert rows[0]["case_id"] == "probe"
    assert rows[0]["mode"] == "full"
    assert rows[0]["ablated"] is False


def test_a_broken_answer_log_does_not_change_the_run(monkeypatch, tmp_path):
    """Binding constraint: the log is a pure side effect. With writing forced to
    fail, the run still completes and its exit code is unchanged."""
    _stub(monkeypatch, ["azot verin."])
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(answer_log, "RUNS_DIR", blocker / "runs")

    rc = run_eval.run(fast=False)

    assert rc == 0


def test_fast_mode_writes_no_answer_log(monkeypatch, tmp_path):
    """--fast never calls answer(), so there is nothing to log."""
    _stub(monkeypatch, ["azot verin."])
    runs = tmp_path / "runs"
    monkeypatch.setattr(answer_log, "RUNS_DIR", runs)

    run_eval.run(fast=True)

    assert not runs.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_run_eval.py -k "answer_log or records_every_sample" -q`
Expected: FAIL — no `.jsonl` file is produced (`assert len(files) == 1` fails with 0), because `run()` does not log yet.

- [ ] **Step 3: Create the test isolation fixture**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures."""

import pytest

from evals import answer_log


@pytest.fixture(autouse=True)
def _isolate_answer_log(tmp_path, monkeypatch):
    """Keep the suite from littering the real evals/runs/ directory.

    The answer log is always-on in run()/run_faithfulness(), and this suite calls
    both dozens of times. Tests that inspect the log patch RUNS_DIR themselves;
    this fixture just guarantees nothing lands in the repo.
    """
    monkeypatch.setattr(answer_log, "RUNS_DIR", tmp_path / "runs")
```

- [ ] **Step 4: Wire the log into `run()`**

In `evals/run_eval.py`, add the import after the existing `from evals.eval_set import CASES` line (line 24):

```python
from evals.answer_log import AnswerLog  # noqa: E402
```

In `run()`, construct the log immediately after the `print(f"Running eval on ...")` header block (the statement ending `f"[{_provider_stamp()}]\n")`) and before `rows = []`:

```python
    # Always-on: eval runs are expensive (~25 min locally, quota-capped hosted),
    # so a run must not be able to throw away its own evidence. Constructing it
    # creates no file - --fast records nothing and leaves none.
    log = AnswerLog(mode="full", provider=_provider_stamp())
```

Then replace the sampling loop (currently `for _ in range(repeat):` through the `samples.append({...})` block) with:

```python
            samples = []
            no_answer = None
            for i in range(repeat):
                r = engine.answer(c["query"])
                reason = _no_answer_reason(r.answer)
                if reason and no_answer is None:
                    no_answer = reason
                g, gr = _answer_ok(c, r.answer)
                p_ok = _products_ok(c, len(r.recommended_products))
                log.record(case=c, repeat_index=i, ablated=no_context,
                           result=r, grounding=g, guardrail=gr,
                           products_ok=p_ok, no_answer=reason)
                samples.append({
                    "products": p_ok,
                    "grounding": g,
                    "guardrail": gr,
                })
```

- [ ] **Step 5: Print the log summary**

In `run()`, immediately after the rates block (the `if not fast: print(...) else: print()` pair) and **before** `if no_context:`, insert:

```python
    if log.count:
        print(f"[answers] wrote {log.count} samples -> {log.path}")
```

- [ ] **Step 6: Ignore the runs directory**

Append to `.gitignore`:

```
# Per-run eval answer logs (from evals.answer_log)
evals/runs/
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_run_eval.py -q`
Expected: PASS, all tests in the file including the 3 new ones.

- [ ] **Step 8: Confirm the suite leaves no litter**

Run: `python -m pytest -q`
Expected: all pass, and `evals/runs/` does NOT exist afterwards.

Verify with: `python -c "import pathlib; print('runs dir exists:', pathlib.Path('evals/runs').exists())"`
Expected: `runs dir exists: False`

- [ ] **Step 9: Commit**

```bash
git add evals/run_eval.py tests/conftest.py tests/test_run_eval.py .gitignore
git commit -m "Log every answer sample from run(); isolate the log in tests"
```

---

### Task 3: Wire into `run_faithfulness()`

**Files:**
- Modify: `evals/run_eval.py` — `run_faithfulness()` (around lines 343-412), specifically `grounded_hits()` and its two call sites
- Test: `tests/test_run_eval.py` (add 2 tests)

**Interfaces:**
- Consumes: `AnswerLog` from Task 1 (already imported by Task 2), same keyword-only `record()` signature.
- Produces: nothing further.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_eval.py`:

```python
def test_faithfulness_logs_normal_and_ablated_samples(monkeypatch, tmp_path):
    """Normal and ablated samples land in one file so they can be compared
    directly - that comparison IS the diagnosis this log exists for."""
    runs = tmp_path / "runs"
    monkeypatch.setattr(answer_log, "RUNS_DIR", runs)
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)      # respects _corpus_ablated
        return ChatResult("depo 2±0,5 derece" if ctx else "genel tavsiye", [])
    monkeypatch.setattr(engine, "answer", fake)

    run_eval.run_faithfulness()

    rows = [json.loads(line) for line
            in list(runs.glob("*.jsonl"))[0]
            .read_text(encoding="utf-8").strip().splitlines()]
    assert [r["ablated"] for r in rows] == [False, True]
    assert rows[0]["answer"] == "depo 2±0,5 derece"
    assert rows[1]["answer"] == "genel tavsiye"
    assert rows[0]["mode"] == "faithfulness"
    assert rows[0]["products_ok"] is None       # faithfulness does not gate products


def test_faithfulness_logs_the_sample_it_aborts_on(monkeypatch, tmp_path):
    """The abort path is exactly when the evidence is wanted, so the unanswered
    sample must reach disk BEFORE sys.exit()."""
    runs = tmp_path / "runs"
    monkeypatch.setattr(answer_log, "RUNS_DIR", runs)
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    monkeypatch.setattr(
        engine, "answer",
        lambda msg, history=None: ChatResult(
            engine._llm_unavailable_message(RuntimeError("429")), []))

    with pytest.raises(SystemExit):
        run_eval.run_faithfulness()

    rows = [json.loads(line) for line
            in list(runs.glob("*.jsonl"))[0]
            .read_text(encoding="utf-8").strip().splitlines()]
    assert len(rows) == 1
    assert rows[0]["no_answer"] == "unavailable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_run_eval.py -k faithfulness_logs -q`
Expected: FAIL — `IndexError: list index out of range` on `list(runs.glob("*.jsonl"))[0]`, because `run_faithfulness()` writes no log yet.

- [ ] **Step 3: Construct the log and record inside `grounded_hits()`**

In `evals/run_eval.py`, `run_faithfulness()`: after `settings.request_timeout = 400.0`, add:

```python
    log = AnswerLog(mode="faithfulness", provider=_provider_stamp())
```

Then replace the whole `grounded_hits` function with:

```python
    def grounded_hits(case: dict, ablated: bool) -> int:
        hits = 0
        for i in range(repeat):
            result = engine.answer(case["query"])
            answer = result.answer
            reason = _no_answer_reason(answer)
            grounding, guardrail = _answer_ok(case, answer)
            # Recorded BEFORE the abort below: the sample that kills the run is
            # exactly the one someone will want to read.
            log.record(case=case, repeat_index=i, ablated=ablated,
                       result=result, grounding=grounding, guardrail=guardrail,
                       products_ok=None, no_answer=reason)
            if reason:
                # An unanswered sample reads as "ungrounded", which would
                # silently mislabel this case as model-carried or
                # retrieval-broken - worse than a wrong score, since the label
                # is recorded as a finding and quoted later. Abort the whole
                # map rather than presenting a partial one as complete.
                sys.exit(f"[faithfulness] {case['id']} produced NO ANSWER "
                          f"({reason}) - aborting rather than misclassifying "
                          f"it as ungrounded.")
            hits += grounding
        return hits
```

- [ ] **Step 4: Update the two call sites**

In `run_faithfulness()`'s per-case loop, replace:

```python
        normal_hits = grounded_hits(c)
        with _corpus_ablated():
            ablated_hits = grounded_hits(c)
```

with:

```python
        normal_hits = grounded_hits(c, ablated=False)
        with _corpus_ablated():
            ablated_hits = grounded_hits(c, ablated=True)
```

- [ ] **Step 5: Print the log summary**

In `run_faithfulness()`, immediately before the final `return code`, insert:

```python
    if log.count:
        print(f"[answers] wrote {log.count} samples -> {log.path}")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_run_eval.py -q`
Expected: PASS, all tests in the file including the 2 new ones.

- [ ] **Step 7: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS. Baseline was 237; this plan adds 5 (Task 1) + 3 (Task 2) + 2 (Task 3) = **247 expected**. If the observed number differs, do NOT trust the arithmetic — confirm the ten new test names are present and passing and that nothing regressed, and report the actual number.

- [ ] **Step 8: Commit**

```bash
git add evals/run_eval.py tests/test_run_eval.py
git commit -m "Log normal and ablated samples from the faithfulness map"
```

---

## Self-Review

**Spec coverage:**
- New module `evals/answer_log.py` with `AnswerLog` (class, lazy file, `path`/`count`) → Task 1. ✓
- JSONL appended/flushed per sample, survives `sys.exit()` → Task 1 (`_write`) + tested in Task 1 and Task 3's abort test. ✓
- Location `evals/runs/<UTC-timestamp>-<mode>.jsonl`, provider inside rows → Task 1; `.gitignore` → Task 2 Step 6. ✓
- All 14 row fields → Task 1 `record()`, asserted in Task 1 Step 1. ✓
- Wiring into `run()` with `ablated=no_context`, `no_answer` samples recorded → Task 2 Step 4. ✓
- Wiring into `run_faithfulness()` with the `ablated` flag and full `ChatResult` for products → Task 3 Steps 3-4. ✓
- `--fast` writes nothing → Task 2 test + the always-construct/lazy-file design. ✓
- End-of-run summary line → Task 2 Step 5, Task 3 Step 5. ✓
- Write failure never propagates → Task 1 `_write` + tests at both module (Task 1) and run (Task 2) level. ✓
- No scoring change → no task touches a verdict, threshold, or exit code; `p_ok` is the same value that already went into `samples`. ✓

**Placeholder scan:** none — every step carries complete code or an exact command. The one estimate (247) is explicitly flagged as reconcilable, not a gate.

**Type consistency:** `record()`'s keyword-only signature is identical in Task 1's definition and both call sites (Tasks 2, 3). `RUNS_DIR`, `AnswerLog`, `.path`, `.count` are spelled the same throughout. `grounded_hits(case, ablated)` is defined and called consistently in Task 3.

**Noted for the implementer:** Task 2's autouse fixture in `tests/conftest.py` patches `RUNS_DIR` for the whole suite; tests that inspect the log patch it again to their own `tmp_path / "runs"`, which is the same directory the fixture chose (same `tmp_path` instance per test). Both patches are therefore consistent, and the explicit patch in each test is kept for readability.
