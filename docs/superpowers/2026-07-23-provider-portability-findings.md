# Provider portability findings

**Date:** 2026-07-23
**Status:** rule pre-registered; measurement not yet run

Spec: `docs/superpowers/specs/2026-07-23-provider-portability-design.md`
Plan: `docs/superpowers/plans/2026-07-23-provider-portability.md`
Models and costs: `docs/superpowers/2026-07-23-provider-portability-models.md`

> Everything in this section was written and committed **before** any measurement
> was taken. It is pre-registration, not interpretation.

## What is being measured, and why

Every quality, guardrail and `corpus_fact` measurement this project has made was
taken against one model: a local Gemma build served by LM Studio. The stated north
star — *the RAG must be full enough that most answers come from the corpus, on ANY
model* — has therefore never been tested on any other model. This measurement tests
it against three hosted models through OpenRouter.

## The models

| class | id |
|---|---|
| strong | `openai/gpt-5.1` |
| mid | `google/gemini-2.5-flash-lite` |
| near-peer | `google/gemma-3-12b-it` |

The near-peer is a hosted Gemma of the same class as the local build, so it bridges
the hosted results back to the local baseline.

## The decision rule

**The only blocking criterion is the guardrail.** No model may leak chemical, brand
or diagnosis advice. A leak confirmed at `--repeat 8` disqualifies that model, full
stop.

**Everything else is map data, not failure.** `corpus_fact` and product-gating
differences are recorded as findings. In particular, a stronger model turning
ablated-red cases green is an **expected finding, not a regression** — it is the
direct test of "corpus carries local/specific, model carries general". This is
accepted in advance precisely so the result cannot be reinterpreted once seen.

Parity was considered and rejected as a criterion: the panel is a **drift guard**,
and its count was explicitly measured not to be a coverage metric. Requiring a hosted
model to match it would misread what the panel is.

## Known-flaky cases — frozen before measurement

These read red in a meaningful fraction of ordinary local runs. If one reads red on a
hosted model it does **not** count as divergence unless confirmed at `--repeat 8`.
This list is frozen and may not be extended after seeing results.

- `local_deveci_pear`
- `local_bpmorettini_pear`
- `local_scarletspur_apple`
- `quant_rose_pot_fertilizer_dose`

## Phase structure

- **Phase 0** — a fresh local baseline on the measurement day. Previously recorded
  numbers are deliberately not used: during the round-4 gate run the whole panel read
  low at once and the cause was never measured, so a cross-day comparison could read
  that effect as a provider difference.
- **Phase 1** — full eval (54 cases) on each of the three models.
- **Phase 2** — only if triggered: a confirmed guardrail leak, or ≥3 `corpus_fact`
  cases diverging from baseline on one model (excluding the frozen flaky list).

## Recorded limitation

The local baseline runs with `min_p` and `repeat_penalty`; the hosted runs do not,
because those are LM Studio extensions that hosted providers reject. **The comparison
is therefore not exactly like-for-like.** This is recorded here, before the
measurement, as a constraint on what the result can prove — not held in reserve as an
explanation for an inconvenient outcome.

---

## Results

*Not yet measured.*
