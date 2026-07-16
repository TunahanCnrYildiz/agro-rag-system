# Eval `--repeat` Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the eval sample each case's LLM-dependent dimensions N times, so a
stochastic failure shows up instead of hiding behind one lucky green — the way a
~5% blank-answer bug hid behind four consecutive `grounding: 31/31` runs.

**Architecture:** `run(fast, repeat)` computes the deterministic dimensions
(`retrieval`, `context`) once and loops `answer()` N times for the sampled ones
(`products`, `grounding`, `guardrail`). A case passes only if EVERY sample
passes; dimension rates are reported over **samples**, not cases.

**Tech Stack:** Python, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-16-eval-repeat-design.md`

## Global Constraints

- **Default `repeat=1` must be byte-identical to today's behaviour and output.**
  This is the regression risk of the whole change.
- `retrieval` / `context` are deterministic (embedding + vector search, no
  sampling) — sample them **once**, never N times.
- A case passes only if **all** N samples pass. A guardrail that leaks 1 time in
  8 is a failure, not a 7/8 pass.
- `--fast --repeat N>1` is a usage error: fast mode never calls the chat model.
- `evals/` has no test file today; `tests/test_run_eval.py` is new.
- Tests stay hermetic: stub `engine.retrieve_context` / `engine.answer`, never
  reach LM Studio.
- Do not touch `evals/eval_set.py` — harness only.
- **Known inefficiency, accepted:** `engine.answer()` calls `retrieve_context()`
  internally, so in production `--repeat N` re-runs retrieval N+1 times per case
  (the harness's own call plus one per sample). That is ~1.5 s each against ~30 s
  per `answer()`, so it is noise — do NOT restructure `answer()` to take a
  pre-computed context just for this. The harness's separate call is what scores
  the deterministic dimensions; the tests stub `answer()`, so they see exactly
  one `retrieve_context` call.

## File Structure

- `evals/run_eval.py` — `run()` signature + loop, `main()` arg parsing.
- `tests/test_run_eval.py` — NEW: the pass rule and the deterministic-dims rule.

---

### Task 1: `--repeat` in the harness

**Files:**
- Modify: `evals/run_eval.py:69-122`
- Test: `tests/test_run_eval.py` (create)

**Interfaces:**
- Produces: `run(fast: bool, repeat: int = 1) -> int` (exit code, unchanged
  meaning: 0 = all cases passed).

- [ ] **Step 1: Write the failing tests** (create `tests/test_run_eval.py`)

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_run_eval.py -v`
Expected: FAIL — `TypeError: run() got an unexpected keyword argument 'repeat'`

- [ ] **Step 3: Rewrite `run()`**

In `evals/run_eval.py`, replace the whole `run()` function (lines 69-114) with:

```python
def run(fast: bool, repeat: int = 1) -> int:
    if fast and repeat > 1:
        sys.exit("--repeat needs the chat model; it does nothing with --fast.")
    if not fast:
        settings.request_timeout = 400.0
    suffix = f", {repeat}x each" if repeat > 1 else ""
    print(f"Running eval on {len(CASES)} cases "
          f"({'FAST' if fast else 'FULL'}{suffix})\n")
    rows = []
    for c in CASES:
        t = time.time()
        # retrieval/context are deterministic (embedding + vector search, no
        # sampling), so they are measured once however high `repeat` is.
        ctx = engine.retrieve_context(c["query"])
        row = {"id": c["id"], "cat": c["category"],
               "retrieval": _retrieval_ok(c, ctx),
               "context": _context_ok(c, ctx)}
        if fast:
            raw = engine.match_products(c["query"], ctx)
            row["raw_products"] = len(raw)
            row["ok"] = all([row["retrieval"], row["context"]])
        else:
            samples = []
            for _ in range(repeat):
                r = engine.answer(c["query"])
                g, gr = _answer_ok(c, r.answer)
                samples.append({
                    "products": _products_ok(c, len(r.recommended_products)),
                    "grounding": g,
                    "guardrail": gr,
                })
            for dim in ("products", "grounding", "guardrail"):
                vals = [s[dim] for s in samples]
                # every sample must pass: "leaks 1 time in 8" is a failure
                row[dim] = all(vals)
                row[dim + "_hits"] = (sum(vals), len(vals))
            row["ok"] = all([row["retrieval"], row["context"],
                             row["products"], row["grounding"],
                             row["guardrail"]])
        row["secs"] = time.time() - t
        rows.append(row)
        mark = "PASS" if row["ok"] else "FAIL"
        if fast:
            detail = f"rawprod={row.get('raw_products')}"
        elif repeat > 1:
            detail = " ".join(
                f"{name}={row[dim + '_hits'][0]}/{row[dim + '_hits'][1]}"
                for name, dim in (("prod", "products"), ("ground", "grounding"),
                                  ("guard", "guardrail")))
        else:
            detail = (f"prod={row['products']} ground={row['grounding']} "
                      f"guard={row['guardrail']}")
        print(f"  [{mark}] {c['id']:<24} ret={row['retrieval']} "
              f"ctx={row['context']} " + detail + f"  ({row['secs']:.0f}s)")

    passed = sum(1 for r in rows if r["ok"])
    print(f"\n=== {passed}/{len(rows)} cases passed ===")

    def rate(key):
        vals = [r[key] for r in rows if key in r]
        return f"{sum(vals)}/{len(vals)}" if vals else "n/a"

    def sample_rate(dim):
        """Rate over SAMPLES, not cases: 'guardrail: 23/24' reads very
        differently from 'guardrail: 30/31', and that difference is the point."""
        hits = [r[dim + "_hits"] for r in rows if dim + "_hits" in r]
        if not hits:
            return "n/a"
        return f"{sum(h for h, _ in hits)}/{sum(n for _, n in hits)}"

    print(f"  retrieval: {rate('retrieval')} | context: {rate('context')}", end="")
    if not fast:
        print(f" | product-gating: {sample_rate('products')}"
              f" | grounding: {sample_rate('grounding')}"
              f" | guardrail: {sample_rate('guardrail')}")
    else:
        print()
    return 0 if passed == len(rows) else 1
```

- [ ] **Step 4: Add the CLI flag**

Replace `main()` (lines 117-122) with:

```python
def main() -> None:
    p = argparse.ArgumentParser(description="Run the RAG quality eval.")
    p.add_argument("--fast", action="store_true",
                   help="Retrieval + raw product gating only (skip chat LLM).")
    p.add_argument("--repeat", type=int, default=1, metavar="N",
                   help="Sample each case N times (full mode only). A case "
                        "passes only if EVERY sample passes. Generation is "
                        "sampled, so a single run hides intermittent failures; "
                        "N>1 costs N x ~20 min.")
    args = p.parse_args()
    sys.exit(run(fast=args.fast, repeat=args.repeat))
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_run_eval.py -v`
Expected: PASS (4 tests)

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add evals/run_eval.py tests/test_run_eval.py
git commit -m "Add --repeat to the eval: sample the stochastic dimensions N times"
```

---

### Task 2: Verify against the live model

**Files:** none (verification only).

- [ ] **Step 1: Prove `--repeat 1` is unchanged**

Needs LM Studio (chat + embeddings). ~15-20 min.

```bash
cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System"
PYTHONIOENCODING=utf-8 python -m evals.run_eval 2>&1 | grep -E "cases passed|retrieval:"
```
Expected, identical to the pre-change baseline:
```
=== 31/31 cases passed ===
  retrieval: 31/31 | context: 31/31 | product-gating: 31/31 | grounding: 31/31 | guardrail: 31/31
```
The per-case line format must be unchanged too (`prod=True ground=True guard=True`).

- [ ] **Step 2: Prove `--repeat` samples and reports**

Use a small N against a live model. ~45-60 min at N=3 — if that is too long, run
it and report what you get rather than skipping the step.

```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval --repeat 3 2>&1 | grep -E "cases passed|retrieval:|FAIL"
```
Expected (per the spec's measurement — 48 samples across the highest-stakes cases
produced **0 flips**):
```
=== 31/31 cases passed ===
  retrieval: 31/31 | context: 31/31 | product-gating: 93/93 | grounding: 93/93 | guardrail: 93/93
```
Note the denominators: **93 = 31 x 3** for the sampled dimensions, **31** for the
deterministic ones. That contrast is the feature working.

If a dimension comes back e.g. `92/93`, that is a REAL intermittent failure the
old harness could not see — report the case id and do not retry until it looks
clean.

- [ ] **Step 3: Reject the fast-mode combination**

```bash
python -m evals.run_eval --fast --repeat 3
```
Expected: exits non-zero with
`--repeat needs the chat model; it does nothing with --fast.`

- [ ] **Step 4: Record the measured outcome in the spec**

Replace the spec's "Expected outcome" section with the real numbers, marked
MEASURED with the date.

```bash
git add docs/superpowers/specs/2026-07-16-eval-repeat-design.md
git commit -m "Record measured --repeat outcome in the spec"
```

---

### Task 3: Document it

**Files:**
- Modify: `README.md` (the `## Testing & quality` section, ~line 198-214)

- [ ] **Step 1: Find the eval command block**

Run: `grep -n "run_eval" README.md`

- [ ] **Step 2: Add the flag to that block**

Alongside the existing `python -m evals.run_eval [--fast]` documentation, add:

```markdown
# Sample each case 3x instead of once. Generation is sampled (temperature > 0),
# so one run can hide an intermittent failure - a ~5% blank-answer bug once
# survived four consecutive clean evals. A case passes only if every sample
# passes; the sampled dimensions then report over samples (e.g. guardrail: 93/93).
# Costs N x the full-eval runtime.
python -m evals.run_eval --repeat 3
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document the eval --repeat flag"
```
