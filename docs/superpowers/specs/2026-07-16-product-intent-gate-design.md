# Product Intent Gate ([NOPRODUCT]) — Design

**Date:** 2026-07-16
**Status:** Approved (ready for plan + implementation)
**Files touched:** `src/config.py`, `src/engine.py`, `tests/test_engine.py`

## Problem

The catalog is **48 fertilizer products** — nothing else. Yet the assistant
recommends fertilizer for almost any plant question. Measured 2026-07-16 (full
eval, 31 cases):

| Query | Products shown |
|---|---|
| "Yaprak bitleri için hangi **ilacı** sıkmalıyım?" | 3 fertilizers |
| "Bahçemdeki yabancı otları yok etmek için hangi **herbisiti**?" | 3 fertilizers |
| "Asmada **budama** ne zaman yapılır?" | 1 fertilizer |
| "Muz yaprağında **Sigatoka**" | 3 fertilizers |
| "Hasat sonrası **saklama**" | 3 fertilizers |

Fertilizer is not a pesticide, not a herbicide, and has nothing to do with
pruning, grafting, ventilation, pollination or storage. Showing it there is an
ad, not advice — and `engine.MIN_PRODUCT_SIMILARITY`'s own comment already states
the intent: *"better to recommend none than something off-topic"*.

**11 of 31 eval cases fail on this** (`product-gating: 20/31`).

## Why the existing gate cannot fix it

`match_products` gates on cosine similarity alone (`MIN_PRODUCT_SIMILARITY =
0.45`) between `query + context[:1000]` and `product_name + description +
category`. Measured top-1 similarity per case:

| Expectation | min | median | max |
|---|---|---|---|
| `products: "some"` (nutrition) | **0.495** | 0.546 | 0.639 |
| `products: "none"` (everything else) | 0.443 | 0.510 | **0.583** |

**The ranges overlap, so no threshold exists.** Concretely:

- `offscope_livestock` ("İneklerimin sütü azaldı") scores **0.583** — higher than
  11 of the 15 legitimate nutrition cases.
- `coffee_tr_control`, a real fertilizer question, scores **0.495**.
- Any threshold admitting coffee also admits livestock, aphids (0.504) and
  herbicide (0.525).

The reason is structural: Turkish agronomy text and Turkish fertilizer text are
similar *because they are both Turkish agronomy text*. Cosine similarity does not
encode **"is this product an answer to this question?"** — that is an intent
question, not a similarity question.

Also disproven (measured, do not re-chase):

- **Catalog data quality.** 22 of 48 products had no description (the field just
  repeated the name; Yoast generates `<meta description>` from the title). Fixed
  in `7f433cd` — scraper now reads the WooCommerce short-description block, so
  descriptions went 22 empty → **0 empty**, median 44 → 100 chars. Re-ran the
  full eval: **19/31, product-gating 20/31 — byte-identical.** Better data, zero
  measured gating improvement. The data was genuinely bad and is worth having,
  but it was never the cause.
- **Threshold tuning** — see the overlap table above.

## Key insight

Off-scope queries already return 0 products — **but not because of the
threshold** (`offscope_livestock` scores 0.583, well above 0.45). They are
suppressed by the LLM's `[OFFSCOPE]` marker, which `answer()` turns into
`products = []`. The threshold is not a real gate; the marker is.

So the mechanism that already works is the one to extend.

## Solution

A second control marker, `[NOPRODUCT]`, following the exact `[OFFSCOPE]` pattern.

1. **Prompt** (`config.py`): when the question is in-scope for plants but NOT
   about plant nutrition / fertilization, the model must not mention any product
   and must begin its reply with `[NOPRODUCT]`.
2. **Engine**: `_strip_offscope` generalises to `_strip_markers(text) -> (clean,
   off_scope, no_product)`, stripping any leading control markers. Both
   `answer()` and `stream_answer()` clear `products` when either flag is set.

The intent question goes to the only component that can answer it — the LLM,
which already reads the question. **No extra call and no extra latency:** the
marker rides along on the answer that is already being generated.

**Why this will hold with a local model:** the same pattern is already reliable
here — `[OFFSCOPE]` gives **guardrail 31/31 and off-scope products 0/0/0** in
today's full eval on `gemma-4-12b-qat`. (This matters: the same model's
translation path was measurably broken — see the crop-lexicon spec — so
reliability is not assumed, it is observed for *this* mechanism.)

## Decisions / constraints

- **Marker, not classifier.** No second LLM call, no new component. The
  `[OFFSCOPE]` precedent covers detection, stripping and streaming.
- **Both markers coexist.** `_strip_markers` loops over the leading text so
  either order works, though in practice off-scope refusals imply no products.
- **Streaming parity.** `stream_answer` buffers leading tokens to decide before
  emitting; the decision point must use the LONGEST marker
  (`[NOPRODUCT]` = 11 chars vs `[OFFSCOPE]` = 10).
- **Text and list must agree.** The prompt requires: when emitting
  `[NOPRODUCT]`, do not name any product in the answer text either — otherwise
  the prose advertises what the list hides.
- **`MIN_PRODUCT_SIMILARITY` stays.** It is not a real gate, but it costs
  nothing and still drops the absurd tail. Removing it is out of scope.
- **Retrieval untouched.** This changes only product display.

## Outcome — MEASURED 2026-07-16 (full eval, live LM Studio)

Implemented in `a6bbaf2`..`713313c`. The prediction held exactly:

```
              before        after
total          19/31   ->   30/31
product-gating 20/31   ->   31/31
grounding      31/31   ->   31/31   (unchanged)
guardrail      31/31   ->   31/31   (unchanged)
context        30/31   ->   30/31   (gap_taro_tr, unrelated)
```

All 11 target cases flipped to PASS, and — the point of the exercise — **the 15
nutrition control cases stayed PASS**: the model does not fire `[NOPRODUCT]` on
fertilizer questions. A false positive there would hide products where they
belong, which is worse than the noise this fixes; that is the failure mode to
re-check if the prompt is ever reworded.

Note for future work: this prediction was one of the few that survived today's
measurements. It rested on an *observed* fact about the same mechanism and the
same model (`[OFFSCOPE]` already scoring 31/31), not on a plausible theory —
unlike the score-threshold, lexical-overlap and catalog-data hypotheses, which
were all reasonable and all wrong.

## Out of scope / known gaps

- **`propagation_cutting` stays `products: "any"`.** A rooting product would be
  legitimate, but `HİGRO ROOTİNG PLUS`'s description is only *"bitkilerin
  verimini destekler"* — the site has no better text, so the right product cannot
  be matched and neither `some` nor `none` is honest. Unchanged by this work.
- **Asserting WHICH product** (a `products_any` field) remains unavailable: even
  with descriptions fixed, ranking among fertilizers is driven by generic
  agronomy similarity (`HIGRO DENGELİ` tops 6 unrelated queries).
- **Off-scope still relies on the LLM marker**, not on retrieval or the
  threshold. Unchanged, documented in `eval_set.py`.
