# Eval `--repeat`: sample stochastic dimensions more than once — Design

**Date:** 2026-07-16
**Status:** Approved (ready for plan + implementation)
**Files touched:** `evals/run_eval.py`, `tests/test_inspect_retrieval.py` (no) —
**`evals/run_eval.py` only**, plus a new `tests/test_run_eval.py`.

## Problem

`run_eval.py` runs each case **once**. Generation is sampled
(`temperature=0.4`), so a failure that happens some of the time is invisible.

This is not hypothetical. The blank-answer bug (fixed today, ~5% rate) survived
**four consecutive full evals reporting `grounding: 31/31`** — for the tomato
case alone, P(4 clean samples | 5%) ≈ 81%, so the green said nothing about it.

Note the asymmetry the eval currently hides: `retrieval` and `context` are pure
embedding + vector search with **no sampling — deterministic**. Only the
LLM-dependent dimensions (`products`, `grounding`, `guardrail`) vary between
runs. Repeating the deterministic ones is pure waste.

## This is insurance, not a fix — measured

Before building this, 6 of the highest-stakes cases were sampled 8× each
(48 `answer()` runs, 2026-07-16):

| cases | samples | flips |
|---|---|---|
| `aphid_no_chemical`, `chemical_brand_push`, `herbicide_push` | 24 | **0** |
| `diagnosis_push`, `offscope_movie`, `tomato_nutrition` | 24 | **0** |

**Nothing flips today.** Shipping `--repeat` now would print "31/31, nothing
found". Its value is future: the next stochastic regression becomes visible
instead of hiding behind a lucky green, which is exactly what the blank-answer
bug did for months.

The 48 runs are themselves the first multi-sample evidence that the guardrail
holds (24/24 clean) rather than "it passed once".

## Solution

`--repeat N` (default **1** — the current behaviour, unchanged).

1. Compute `retrieve_context()` **once** per case: `retrieval` and `context` are
   deterministic, so sampling them N times buys nothing and costs nothing but
   time.
2. Call `answer()` **N times**; evaluate `products`, `grounding`, `guardrail` per
   sample.
3. **A case passes only if EVERY sample passes.** For a guardrail, "leaks 1 time
   in 8" is a failure, not a 7/8 pass.
4. Report per-dimension **rates over samples**, not over cases:
   `guardrail: 23/24` reads very differently from `guardrail: 30/31`, and the
   difference is the point.
5. `--fast --repeat N>1` is a **usage error**: fast mode never calls the chat
   model, so every sample would be identical.

## `--only` — what makes `--repeat` usable at all

`--repeat 3` over all 31 cases is ~45-60 minutes. **A tool that costs an hour
gets run approximately never** — and insurance you never invoke is not insurance.
Shipping `--repeat` alone would have let us declare the blind spot closed while
leaving it open in practice, which is the tool-level version of the "green but
vacuous" bug this whole session has been chasing.

So `--only <id|category>` ships with it: run one case, or one category.

```bash
python -m evals.run_eval --repeat 10 --only chemical    # ~15 min, where the risk is
python -m evals.run_eval --repeat 3  --only gap_taro_tr # one case, ~2 min
```

This is not a convenience: it is the difference between a feature and a used
feature. Note that the ad-hoc measurement that justified this whole spec (6 cases
x 8) was written by hand precisely because sampling all 31 was absurd — the tool
should support what the work actually needed.

- Matches a case **id** exactly, or a **category**
  (`nutrition | horticulture | disease | chemical | offscope`).
- Matching nothing is a usage error listing the valid categories — a silent
  "0/0 cases passed" would be a green that means nothing.
- Works in fast mode too (filtering is orthogonal to sampling).

## Decisions / constraints

- **Default stays 1.** No existing workflow gets slower. Full eval is ~15-20 min;
  `--repeat 3` is ~45-60 min, which is a deliberate choice, not a default.
- **No new dependency.** A loop and a counter.
- **Deterministic dims stay single-sample** — by construction, not by omission.
- **Not wired into CI.** CI has no LM Studio; this stays a local command.
- **Nothing about the eval cases changes** — this is a harness feature only.

## Expected outcome

- `--repeat 1` (default): byte-identical behaviour and output to today.
- `--repeat 3` on the current tree: **31/31**, all dimensions clean — because
  nothing flips today. That is the expected, unexciting result; it is the tool
  working, not the tool failing.
- Unit tests cover the pass rule (a single failing sample fails the case) with a
  stubbed `answer()`, so they stay hermetic and fast.

## Out of scope

- **Making CI run it.** Needs a hosted LLM; the eval stays local.
- **Auto-detecting flakiness / statistics.** No confidence intervals, no
  auto-N. If a dimension shows e.g. 23/24, a human reads it and decides.
- **The "fast empty" mode** of the blank-answer bug (undiagnosed) — unrelated.
