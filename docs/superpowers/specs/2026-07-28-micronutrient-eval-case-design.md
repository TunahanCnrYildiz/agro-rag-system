# Micronutrient eval case — design

**Date:** 2026-07-28
**Status:** Approved design, pending implementation.
**Goal:** Close a measured coverage gap — the eval panel has no micronutrient case, so the
guarantee "a micronutrient nutrition question keeps its product recommendations" has never
been exercised.

## Why

Measured 2026-07-28 (`docs/superpowers/2026-07-28-micronutrient-suppression-findings.md`):
the macro-only `_NUTRITION_TERMS` watch item is **not** a defect — 5/5 micronutrient
questions kept their products. But that measurement also surfaced a gap it could not close:

> The eval panel contains no micronutrient case at all. The `local 54/54` result that
> originally accompanied this watch item therefore never exercised it.

The panel carries 18 `nutrition` cases; every one is macronutrient or general fertilization.
So the NOPRODUCT backstop (`_looks_non_product`, `src/engine.py:381`) has no regression guard
for the micronutrient shape. That matters because `_NON_PRODUCT_ACTIVITY` has already been
extended twice (2026-07-24, 2026-07-25) and each extension widens the set of answers that can
be suppressed. A future extension that wrongly suppresses a micronutrient answer would be
caught by nothing.

The catalog genuinely serves these questions — it has a `mikro-besinler` category, and the
verification run below returned **`HİGRO FERRY`**, an iron product.

## The case

Added to `CASES` in `evals/eval_set.py`, alongside the other `nutrition` cases:

```python
{
    "id": "micronutrient_iron_deficiency",
    "category": "nutrition",
    "query": "Bitkilerde demir eksikliği nasıl giderilir?",
    "retrieval": "nonempty",
    "products": "some",
    "context_any": ["demir", "çinko", "mikro"],
    "answer_any": ["demir", "gübre", "toprak", "şelat"],
},
```

**`products: "some"` is what this case exists for.** The other assertions exist so a failure
is attributable: without `retrieval`/`context_any`, a red case could not distinguish "the
backstop wrongly suppressed" from "retrieval drifted off-topic".

## Verification already performed (live, not assumed)

Run against `local:google/gemma-4-12b-qat` with the real `engine.answer()` path:

- **Retrieval:** 4080 chars from on-topic Turkish agronomy sources (`dp_19583`, `dp_405065`,
  `dp_1225168`).
- **`context_any` anchors verified present in the LIVE retrieved context:** `demir` ✓,
  `çinko` ✓, `mikro` ✓.
- **Deliberately excluded:** `iron` and `kloroz` — both ABSENT from the retrieved context.
  Including them would have shipped dead anchors, the failure mode this project has hit
  before (a dead anchor yields `ctx=False`, which reads as a corpus finding rather than a
  typo).
- **`answer_any` terms verified present in the live answer:** `demir` ✓, `gübre` ✓,
  `toprak` ✓, `şelat` ✓. `besin`, `ph`, `yaprak` did NOT appear and are excluded.
- **Products returned:** `HİGRO FERRY`, `HİGRO® SPEED`, `HIGRO DENGELİ`;
  `_looks_non_product()` returned `False` (no suppression).

Query framing matters and was chosen deliberately: **"Bitkilerde ..."** keeps retrieval in
plant agronomy. The unframed "demir eksikliği belirtileri" drifts to FAO *human* nutrition
content (protein/lysine deficiency) — measured during the same session.

## Out of scope (YAGNI)

- **No second case** (zinc, or an English variant). One case closes the gap; a second doubles
  the flake surface for no additional guarantee. The `corpus_fact` caps do not apply here —
  this is a product-gating case, not a `corpus_fact` case — but the panel's own history of
  intermittent cases does.
- **No change to `_NUTRITION_TERMS` or `_NON_PRODUCT_ACTIVITY`.** The measurement said the
  lists are correct as they stand; extending them with micronutrient names would be actively
  harmful (`demir` would match the surname "Demir", a false nutrition signal of exactly the
  class that got `verimli` removed on 2026-07-25).
- **No `answer_none`.** There is no banned phrase specific to this question.

## Verification after implementation

- `python -m evals.run_eval --only micronutrient_iron_deficiency` → PASS with
  `ret=True ctx=True` and `prod=True`. This is the only mode that checks `ctx`.
- `python -m pytest -q` unchanged (the eval set is data; no test asserts the case count).
- Panel becomes 55 cases / 19 `nutrition`. `corpus_fact` count is unchanged at 23 — this case
  is **not** `corpus_fact` and must not be counted as one.

## Risk

The generation-dependent half is `answer_any`, which is satisfied by any one of four terms and
was verified against a real answer; `demir` alone is near-certain for this query. The
corpus-dependent half (`retrieval`/`context_any`) is deterministic — embedding search, no
sampling — and was verified live. If the case still reads red on a later run, treat it as a
map finding and investigate, per the standing rule: never tune a case to green.
