# Micronutrient suppression watch item — measured, CLOSED

**Date:** 2026-07-28
**Backend:** `local:google/gemma-4-12b-qat`
**Raw rows:** `2026-07-28-micronutrient-suppression-raw.jsonl` (full answer texts, UTF-8)

## The watch item

Open since the NOPRODUCT-backstop round-2 work:

> `_NUTRITION_TERMS` is macro-only — a micronutrient answer (demir/çinko + an
> activity term, no listed nutrition term) could be WRONGLY suppressed. Unmeasured.

`_looks_non_product(answer)` (`src/engine.py:381`) suppresses products when the answer
names a non-product activity **and** carries no nutrition term. If the nutrition half
could not recognise a micronutrient answer, the backstop would strip products from a
genuine nutrition question — the *safety* direction the design promised to protect. The
catalog has a `mikro-besinler` category, so these are questions products genuinely serve.

## Verdict: NOT a defect. Do not extend `_NUTRITION_TERMS`.

**5/5 micronutrient questions kept their products; 0 suppressed by the backstop.**
Macro controls: 2/2 kept, 0 suppressed.

| group | query | raw | final | activity | nutrition | cause |
|---|---|---|---|---|---|---|
| micro | demir eksikliği belirtileri | 3 | 3 | no | yes | — |
| micro | çinko eksikliği | 3 | 3 | no | yes | — |
| micro | bor eksikliği | 3 | 3 | no | yes | — |
| micro | mangan eksikliği | 3 | 3 | no | yes | — |
| micro | demir klorozu | 3 | 3 | **yes** (`havaland`) | yes | — |
| macro | azot eksikliği (control) | 3 | 3 | yes (`sula`) | yes | — |
| macro | potasyum eksikliği (control) | 3 | 3 | yes (`sula`) | yes | — |

## Why — the risk was mis-stated, and that is the durable lesson

**`_NUTRITION_TERMS` is not "macro-only" in the sense that matters.** It does contain
macronutrient names (`azot`, `fosfor`, `potasyum`), but it also contains *nutrient-agnostic*
vocabulary: **`gübre`, `besin`, `besle`, `doz`, `kompost`**. A micronutrient answer is still a
*nutrition* answer, so it reaches for exactly those words.

Observed nutrition hits per micronutrient answer — note the redundancy, this is not a
one-word escape:

- `gübre, besle, doz`
- `gübre, besin, besle`
- `gübre, besin, besle, doz`
- `gübre, besle, azot, doz`
- `besin, besle` ← the only answer that also carried an activity term

Two independent reasons suppression cannot easily reach these answers:
1. **4 of 5 carried no activity term at all** — the first half of the AND never fires.
2. **All 5 carried 2-4 nutrition terms** — the second half cancels with margin.

## Why extending the list would be actively WRONG, not merely unnecessary

Adding `demir` / `çinko` etc. is tempting but harmful. `_contains_any` is left-boundary
only and case-folded, so `demir` would match the **surname "Demir"** — common in Turkish
agronomy citations, and already present in this corpus (`evals/eval_set.py` quotes
"Konak ve Demir"). That would inject a FALSE nutrition signal into non-nutrition answers
and cancel suppression that should fire.

This is precisely the `verimli` mistake, which was removed on 2026-07-25 for being a false
nutrition signal (`kendine verimli` = reproductively fertile, not fertilised). Re-introducing
the same class of bug to fix a problem that does not occur would be a net loss.

## Honest limits of this measurement

- **n = 5 micronutrient queries, one sample each.** Generation is stochastic
  (`temperature=0.4`), so this shows the failure is *not reached in practice with a
  comfortable margin*, not that it is impossible.
- The margin is what carries the conclusion: every answer cleared the nutrition half by
  2-4 independent terms, and most never armed the activity half at all.
- Single backend (`gemma-4-12b-qat`). A terser model that answers a deficiency question
  without ever saying gübre/besin/doz could in principle still trip it — the shape to
  watch, if it is ever watched again.

## Related gap found while measuring (NOT closed here)

**The eval panel contains no micronutrient case at all.** The `local 54/54` result that
originally accompanied this watch item therefore never exercised it — the panel could not
have caught this either way. Adding a micronutrient product-gating case is a separate,
still-open option; it is not `corpus_fact` work and the `corpus_fact` caps do not apply.

## Method note (worth reusing)

The first run of this probe reported a clean **`0/5 wrongly suppressed`** while **every
single query had timed out** and returned the LLM-unavailable fallback. The number was an
artifact of an outage, not a finding — the same vacuity defect the eval harness itself
shipped once (`guardrail: 54/54` for models that never spoke). The probe now reuses
`evals.run_eval._no_answer_reason` and **aborts** on an unanswered sample rather than
scoring it. Two incidental fixes were needed to get real data: `request_timeout` 120 → 400s
(RAG answers here take 170-210s), and writing results as UTF-8 to a file because the
Windows console cannot encode Turkish characters.
