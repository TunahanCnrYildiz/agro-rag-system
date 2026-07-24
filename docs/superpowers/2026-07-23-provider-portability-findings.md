# Provider portability findings

**Date:** 2026-07-23 (rule); 2026-07-24 (measurement)
**Status:** measured — guardrail transfers (blocking criterion passed); product suppression does not

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

Measured 2026-07-24 after the free-tier quota reset. The originally-pinned three-model
slate was replaced by a single free model (see the models doc's revision): the account
has no OpenRouter credits, the free tier caps at **50 requests/day**, and phase 1's 162
calls exhausted it. User ruling: measure one model, `google/gemma-4-26b-a4b-it:free`,
full 54 cases, against the same-day local baseline.

### Local baseline (phase 0) vs hosted (phase 1)

| dimension | local `gemma-4-12b-qat` | hosted `gemma-4-26b-a4b:free` |
|---|---|---|
| retrieval | 54/54 | 54/54 |
| context | 54/54 | 54/54 |
| **guardrail** | **54/54** | **52/52** |
| grounding | 53/54 | 51/52 |
| product-gating | 54/54 | **30/52** |
| cases passed | 53/54 | 30/54 |

Two cases (`local_ankara_pear`, `technique_grape_bud_load`) returned `[ERROR]
NO ANSWER (unavailable)` — transient free-endpoint failures mid-run, surfaced rather
than hidden because `max_retries=0`. They are excluded from every rate (denominator 52),
which is exactly the harness fix from task 8 working. `usage_daily` read 0 and the two
errors fell in the middle of the run, so they are endpoint flakiness, not the daily cap.

### The verdict under the pre-registered rule

**The blocking criterion PASSED. `gemma-4-26b-a4b:free` is not disqualified.**
Guardrail read **52/52** — no chemical, brand or diagnosis phrase leaked, on a model
from a different build than every prior measurement. This is the headline the whole
exercise existed to test: **the text guardrail is genuinely prompt-carried and it
transfers.** It was measured 54/54 against an empty corpus before; now it holds on a
different model too.

**Grounding transfers too: 51/52 ≈ the local 53/54.** Corpus grounding is not a
property of the one local model.

### The one real divergence — map data, not failure (as pre-registered)

**All 22 product-gating failures are `products='none'` cases: the hosted model showed
fertilizer products where they should have been suppressed.** Not one `'some'` case
failed — the model shows products fine, it fails to *withhold* them. Product
suppression works via a `[NOPRODUCT]` marker the model must emit at the start of its
answer; the engine strips it and hides products. The local `gemma-4-12b` emits that
marker reliably (54/54); the hosted `gemma-4-26b-a4b` does not. **So product
suppression, unlike the text guardrail, is prompt-carried in a way that does NOT
transfer cleanly across models.** This is the single most useful thing the measurement
found.

**A precise safety nuance inside this.** `chemical_brand_push` and `diagnosis_push` are
guardrail-adjacent — the *text* refusal held (guard=True on both), but products were
still shown underneath. The answer correctly says "I won't name a chemical/brand," and
then a fertilizer product is recommended below it. That is incoherent rather than
dangerous (it is fertilizer, not the banned chemical), but it means the *product* half
of the safety intent does not hold on this model even though the *text* half does. If
this model were ever put in production, the `[NOPRODUCT]` marker path would need
hardening — a code-side gate, not just a prompt instruction.

### What remains unmeasured

- **Only one model, one pass.** The three-model design (system-failure vs
  model-capacity discrimination) was not realised; a single model cannot separate those.
  Re-running the full slate needs either credits or spreading free runs across days.
- The `min_p`/`repeat_penalty` like-for-like limitation recorded above still stands.
- `quant_wheat_nitrogen_dose`, the one red in the local baseline, passed on the hosted
  model — inside single-run noise, not a signal either way.

### Practical, measurement-independent finding

Hosted answers landed in 3-53s (median well under the local ~20-30s). An eval round
drops from ~25 min to a few minutes, and a demo stops needing LM Studio on the machine.
