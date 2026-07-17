# Faithfulness dimension: measure whether the corpus actually carries the answer

**Date:** 2026-07-17
**Status:** design, approved
**Files touched:** `evals/run_eval.py`, `evals/eval_set.py`, `tests/test_run_eval.py`
**Follows:** item 25/26 (the ablation showing the eval cannot see the corpus) and
the `--no-context` flag (`c91ab3e`), whose `_corpus_ablated()` primitive this reuses.

## The problem, measured

The ablation on 2026-07-17 proved the eval cannot tell whether retrieval
contributes: with `engine.retrieve_context` forced to `""`, grounding stayed
31/31 and guardrail stayed 31/31. The corpus-dependence map (6 probes, normal vs
ablated `answer()`, content compared) found the answer robustly corpus-carried in
exactly **one** of six probes (deveci); everything general was model-carried,
including cassava, the gap crop the corpus was built for.

The user's north star: the RAG must be full and accurate enough that MOST answers
come from the corpus, on ANY model. If the model carries the bulk, "the RAG works"
is false — we are only filling small gaps, which is not what they want. Stated as
a metric: drive **corpus-carried** cases up from today's 2.

This spec does NOT drive that number up. It builds the **guard** that verifies
each claimed corpus-carried case genuinely is one, and catches the case where the
corpus makes an answer WORSE. Growing the number is separate work (authoring more
corpus-specific cases — the item-25 extension). This dimension makes each such
case honest.

## What it measures: contribution, not support; scored over opt-in cases only

Two independent decisions, both taken with the user. **Decision 1 — what to
measure:** contribution (chosen) vs support. **Decision 2 — over which cases:**
all 33 vs opt-in only (opt-in chosen).

Two things "faithfulness" could mean:
- **Contribution (chosen):** does removing the corpus degrade the answer? Directly
  serves "corpus should carry the bulk", and needs no LLM-judge — this project has
  measured the local model returning empty (~3%, item 20) and mistranslating (item
  11), so a judge is an untrustworthy instrument.
- **Support (rejected):** are the answer's claims traceable to the retrieved
  context? Classic RAG faithfulness, but needs a judge or brittle n-gram overlap.

Chosen: **contribution, via ablation-delta.**

And it is scored **only over opted-in cases** (scope B), not all 33. A generic
assertion like `answer_any: ["tozla","polen"]` passes both normally and ablated —
but that does not distinguish "the corpus did not help" from "the assertion is too
weak to detect help". Counting those would conflate two things into one number,
which is the vacuity class this project keeps getting burned by (items 4, 12). So
a case must OPT IN by declaring its assertion is a corpus-specific fact.

## Design

### The opt-in marker

A boolean field `corpus_fact: true` on a case whose `answer_any` is a fact only
the corpus would supply (deveci's `2±0,5`, not a generic keyword). A field, not a
category, so a future nutrition case asserting a corpus-specific NPK ratio can opt
in without being `local`. The two shipped `local` cases set it.

### The four-quadrant classification

For each opted-in case, run `answer()` normally and under `_corpus_ablated()`, and
check the case's `answer_any` (grounding) in both:

| normal | ablated | label | meaning |
|---|---|---|---|
| green | red | **corpus-carried** | the win — the corpus supplies the fact. Counted by the score. |
| green | green | **model-carried** | the assertion passed without the corpus → the model knew it (or the mark is wrong). |
| red | — | **retrieval-broken** | cannot answer even WITH the corpus. |
| red | green | **corpus-harmful** | the corpus BROKE it — the model would have been right, retrieval injected noise. Nothing catches this today. |

`corpus-harmful` is free: the same two runs produce all four quadrants; we only
label the quadrant.

### Stochasticity: reuse the existing semantics, invent no threshold

Retrieval is deterministic (embedding + vector search, no sampling — the eval
already treats it single-sample, item 21). Only answer generation is stochastic.
So for deveci the ablated side is stable (100% red — it cannot state a fact the
empty corpus lacks) and the flake lives entirely on the normal-green side (the
model states `2±0,5` ~87% of the time; measured 2-in-15 red).

The dimension reuses the eval's existing sampled-dimension rule verbatim:
`all()` ("every sample must pass") plus a visible hit fraction (`normal 13/15`).
A case is **corpus-carried** iff all N normal samples are green AND all N ablated
samples are red. At `--repeat 1` the score is as noisy as the rest of the eval is
at repeat 1 — no new philosophy. At `--repeat 8` deveci's flake surfaces honestly:
it fails unanimous normal-green and is reported with its sub-unanimous fraction
rather than silently counted or silently dropped.

No magic threshold (e.g. "normal ≥ 80% counts"). A threshold tuned against results
is the item-22(a) trap; the unanimous rule + visible fraction is the semantics this
project has already proven.

### CLI surface and exit code

`run_eval.py --faithfulness`: runs each opted-in case normal then ablated (sharing
`_corpus_ablated()` with `--no-context`), classifies, prints the report:

```
=== faithfulness (corpus contribution) ===
  local_deveci_pear       corpus-carried    normal 15/15  ablated 0/15
  local_santamaria_pear   corpus-carried    normal 15/15  ablated 0/15
  corpus-carried: 2/2  |  harmful: 0  |  retrieval-broken: 0  |  model-carried: 0
```

**Exit 1 if any opted-in case is not corpus-carried** (harmful, retrieval-broken,
or model-carried). Opting in is a claim — "this case needs the corpus" — and the
tool verifies it, exactly as `--no-context` requires every `local` case to lose
grounding. The score grows by adding *validated* opt-in cases, never by carrying
failing-but-pending ones; a case that stops discriminating is dropped or fixed
(as `local_0900ziraat_cherry` was).

Guards: `--faithfulness --fast` exits 1 (fast never calls `answer()`), mirroring
the existing `--fast --repeat` and `--fast --no-context` guards. `--faithfulness`
with no opted-in case in the selection exits 1 (a "0 of 0" success is the `all([])`
vacuity trap, item 4).

`--no-context` stays as the raw ablation primitive — useful for a quick
single-case discrimination check while authoring — and is not refactored.

## What it does NOT do — and the one caveat that must not be misread

- Does NOT change the prompt / grounding discipline. Tightening the prompt to
  "answer only from context" is the deferred, risky work: retrieval is fragile
  (santamaria retrieves 0 chars on a natural rephrase; asma budama 989 chars), so
  forcing grounding-only converts "model bluffs a decent answer" into "system
  refuses" — worse UX, colliding with the empty-answer class (item 20). Robustify
  retrieval and coverage FIRST.
- Does NOT measure the other 31 cases (scope B). They are known model-carried.
- Does NOT use an LLM-judge.
- Does NOT fix retrieval fragility or add corpus content.

**The caveat, to be stated in the report and the docstring, not buried:** this
score does NOT answer "what fraction of user questions does the corpus carry."
"2/2" looks like 100% but means "of the cases we deliberately built to need the
corpus, both do." The denominator is small and self-selected. The real
project-level number — corpus coverage of the actual question space — needs a
representative sample of real questions marked `corpus_fact`, which this does not
have. **This dimension is a regression guard on deliberate cases, not a coverage
meter.** Conflating the two would be the same false-metric this project keeps
catching.

## Testing

TDD. `tests/test_run_eval.py`, all offline (no real model):

- classify green/red → `corpus-carried`
- classify green/green → `model-carried`
- classify red/red → `retrieval-broken`
- classify red/green → `corpus-harmful`
- a case with `corpus_fact` unset is skipped by `--faithfulness`
- exit 1 when an opted-in case is model-carried
- exit 1 when an opted-in case is corpus-harmful
- exit 0 when all opted-in cases are corpus-carried
- `--faithfulness --fast` exits 1
- `--faithfulness` with no opted-in case in selection exits 1
- unanimous rule: one red normal sample under `--repeat` drops a case from
  corpus-carried (reuses the existing `all()` path)

## Verification

- On the current suite, `--faithfulness` classifies both shipped `local` cases as
  corpus-carried and exits 0.
- Deliberately weakening a `local` assertion to a generic keyword flips it to
  `model-carried` and the tool exits 1 — proving the guard has teeth.
- `--repeat 8 --faithfulness` surfaces the deveci flake as a sub-unanimous normal
  fraction rather than a silent pass or drop.
