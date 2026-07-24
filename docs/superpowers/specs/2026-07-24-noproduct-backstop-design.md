# A code-side backstop for product suppression, independent of the `[NOPRODUCT]` marker

**Date:** 2026-07-24
**Status:** design approved, ready for an implementation plan

## Why this, and why now

The provider-portability measurement (2026-07-24, findings in
`docs/superpowers/2026-07-23-provider-portability-findings.md`) established that the
text guardrail transfers across models but **product suppression does not**. On the
hosted `google/gemma-4-26b-a4b:free`, all 22 product-gating failures were
`products='none'` cases: the model showed fertilizer products where they should have
been suppressed, because it did not reliably emit the `[NOPRODUCT]` marker the
suppression depends on.

The local production model (`gemma-4-12b-qat`) emits the marker reliably (54/54), so
there is no bug in the current deployment. This work is **architectural hardening**:
product suppression should not rest on a single point of failure — the model prefixing
one control token — because that is exactly the kind of instruction-following that
varies between models and could occasionally lapse even locally.

## The core constraint that shapes everything

The obvious fix — raise the product-similarity threshold in `match_products` — is
**measured dead** and recorded in `do-not-rechase`: product cosine scores OVERLAP
between "should show" and "should not" (0.495-0.639 vs 0.443-0.583); `offscope_livestock`
scores 0.583, beating 11 of 15 real nutrition cases. **Cosine cannot encode "is this
product an answer."** The `[NOPRODUCT]` marker exists precisely because the model's
semantic judgment does what cosine provably cannot. So the backstop cannot be a
threshold, and it cannot use cosine.

## Scope

**In scope:** a single, deterministic, LLM-free function that inspects the *answer text*
and suppresses products when the answer clearly belongs to a non-product activity;
wired into both `answer()` and `stream_answer()` alongside the existing marker check.

**Out of scope, each deliberately:**
- A separate LLM classification call (extra latency/quota; the project's extra-gemma-call
  history is bad — query translation returned empty ~half the time).
- Cosine threshold tuning (measured dead, above).
- Any change to `SYSTEM_PROMPT` or the marker instruction. The marker stays the **primary**
  signal; the backstop **completes** it, it does not replace it.
- Inverting the marker to an opt-in `[PRODUCT]` (same formatting fragility, no gain).

## Design decisions, all made during brainstorming

1. **Goal: architectural robustness** — suppression must not depend on the model emitting
   a token; the code decides from the answer itself.
2. **Mechanism: content rule + marker backstop** — the marker remains primary (local
   behaviour unchanged); the code-side rule is a second line of defence for when the
   marker is absent. No cosine, no extra LLM call.
3. **Direction: suppress only when the answer is CLEARLY non-product** (the safe framing).
   Products survive unless there is positive evidence the answer is about a non-product
   activity. This guarantees no regression on working nutrition cases: an answer can only
   be suppressed if it lacks any nutrition term, so a nutrition answer is never hidden.

## Architecture

### The rule

A new function in `src/engine.py`, next to `CROP_LEXICON` and the existing
suffix-matching machinery:

```
_looks_non_product(answer_text: str) -> bool
```

returns True — meaning "suppress products" — iff:

```
_contains_any(answer_text, _NON_PRODUCT_ACTIVITY) and not _contains_any(answer_text, _NUTRITION_TERMS)
```

Both halves are required. An answer is suppressed only when it names a non-product
activity **and** carries no nutrition term. Consequences:

- pure nutrition answer ("azot verin") → False (kept)
- mixed ("gübreleyin, sonra budayın") → False, nutrition term present (kept)
- pure pruning answer, no nutrition term → True (suppressed)
- neutral answer with neither signal → False (shown — "when in doubt, show")

### The matcher

`_contains_any(text: str, stems: tuple[str, ...]) -> bool` reuses the exact
Turkish-inflection-aware pattern already used by `_expand_query`
(`engine.py:293`): `(?<!\w){stem}(?:{_TR_SUFFIXES})?(?!\w)` over `_normalize_tr(text)`.
This sees a stem through Turkish case/plural/possessive endings ("budamada",
"depolamada", "sulamada") without firing on an unrelated morpheme. It is small and
testable in isolation.

**CRITICAL — both sides must be folded.** `_normalize_tr` lowercases *and folds Turkish
letters to ASCII* (`ş→s`, `ü→u`, `ç→c`, `ğ→g`, `ı→i`, `ö→o`), the same as
`_LEXICON_BY_LENGTH` does to the crop lexicon (`engine.py:268`). So "Aşılama" becomes
"asilama". Each stem must therefore be matched in **folded** form — `_contains_any`
applies `_normalize_tr` to every stem before building its pattern (mirroring how the
lexicon keys are pre-folded). If the stems were compared raw (with diacritics) against
folded text, "aşı" would never match "asilama" and the gate would be **silently dead** —
the "a dead anchor does not fail loudly" trap this project has hit before. A unit test
MUST cover a diacritic stem end to end (a stem like `aşı`/`gübre` matching "aşılama"/
"gübreleyin" in real input), so a folding regression fails loudly.

### The two term sets

Placed in `src/engine.py` beside `CROP_LEXICON`. Deliberately SMALL — bounded by the
categories `SYSTEM_PROMPT` already enumerates (`config.py:247-249`), no speculative
terms. Expanded only if measurement shows a gap, and such a gap is a *finding*, not a
cue to tune.

`_NON_PRODUCT_ACTIVITY` (Turkish stems + English stems):

| category | Turkish | English |
|---|---|---|
| pruning | budam | prun |
| grafting | aşı, aşıla | graft |
| ventilation | havaland | ventilat |
| pollination | tozla | pollinat |
| irrigation practice | sulam | irrigat |
| propagation | çoğalt | propagat |
| harvest/storage | hasat, depola, muhafaza | harvest, storag, stor |
| pest/weed control | zararlı, yabancı ot, ilaçla | pest, weed, pesticid |

`_NUTRITION_TERMS` (if any of these appears, never suppress):

`gübre, besin, besle, azot, fosfor, potasyum, npk, doz, kompost, verimlil`
/ `fertiliz, nutrient, nitrogen, phosph, potass, compost, feeding`

**Deliberate exclusions, each avoiding a known trap:**
- **`tozla` for pollination, not `döllen`.** "Döllenme" spans pollination *and*
  reproduction and reads close to "gübreleme"; `tozla` is unambiguous.
- **`hastalık` (disease) is NOT an activity stem.** A nutrient-deficiency answer can be
  framed as a "disease"; it must not be suppressed. It is protected twice: it carries a
  nutrition term (`azot`…) anyway, and `hastalık` is simply absent from the list.
- **`sulam` (irrigation) is included despite fertigation overlap** — a fertigation answer
  ("sıvı gübre ile sulama") contains `gübre`, so the nutrition half keeps it. The overlap
  falls to the safe side by construction.

### Wiring — two call sites, mirroring the existing marker check

**`answer()` (`engine.py:633-638`).** The full clean answer is already in `answer_text`
after `_strip_markers`. Extend the existing condition:

```python
answer_text, off_scope, no_product = _strip_markers(answer_text)
if off_scope or no_product or _looks_non_product(answer_text):
    products = []
```

**`stream_answer()` (`engine.py:737`).** The final product-emit gate is
`if not (off_scope or no_product) and has_advice:`. **Complication:** after warmup the
tokens are streamed and discarded, so the full answer text is not retained in any
variable. The stream must therefore **accumulate the full answer** into a local (e.g.
`full_answer`), appending the warmup `clean` and every post-warmup `delta`, plus the
fallback-path `clean`. The gate becomes:

```python
if not (off_scope or no_product) and has_advice and not _looks_non_product(full_answer):
    ...emit products...
```

Accumulating one answer's worth of string is negligible and localises the change; no
other streaming logic moves.

## Testing

All offline, following the `test_engine.py` monkeypatch patterns.

**Unit — `_contains_any`:**
- matches a stem through Turkish inflection ("budamada", "depolamada", "sulamada")
- matches a **diacritic** stem end to end ("aşı" fires on "aşılama", "gübre" on
  "gübreleyin") — the folding guard; would fail if stems were compared raw
- does not fire on an unrelated morpheme (no false hit inside a longer word)

**Unit — `_looks_non_product`, the four corners:**
- pure pruning answer, no nutrition term → True
- pure nutrition answer ("azot verin") → False
- mixed ("gübreleyin, sonra budayın") → False (nutrition term present)
- neutral answer, neither signal → False

**Behavioural — `answer()`:**
- no marker + pruning answer → `recommended_products == []` (the backstop's new job)
- no marker + nutrition answer → products kept (the regression guard — this test's real
  job, since false suppression on the working local model is the one new risk)
- marker present → suppressed exactly as today (existing path intact)

**Behavioural — `stream_answer()`:**
- no marker + pruning answer streamed → no `products` event emitted
- no marker + nutrition answer → `products` event emitted
- the accumulation is correct: a pruning answer whose activity term arrives *after*
  warmup is still suppressed (proves the backstop sees the whole answer, not just the
  warmup buffer)

## Validation — two stages, kept distinct

| stage | proves | when |
|---|---|---|
| local full eval | **safety** — no regression: product-gating stays 54/54, panel stays 53/54. Locally the marker fires, so the backstop is mostly inert; this run proves it does no harm. | immediately, free |
| hosted re-measurement | **efficacy** — do gemma-4-26b's 22 product-gating failures improve? This is the backstop's actual target. | needs quota (next day) |

**Honest framing, recorded in the findings, not held back:** the local eval proves only
that the backstop does no harm, **not** that it works — locally the marker already fires
and the backstop rarely engages. Efficacy is visible only in the hosted re-measurement.
And per the project's iron rule: **if the hosted re-measurement does not fix the 22
cases, that is a finding** — the keyword approach did not transfer to the answer either —
and we record it rather than inflating the term lists to force it green.

## Deliverables

1. `_contains_any`, `_looks_non_product`, and the two term sets in `src/engine.py`.
2. The backstop wired into `answer()` and `stream_answer()` (with the streaming
   accumulator), with tests.
3. A local full-eval run confirming no regression (54/54 product-gating, 53/54 panel).
4. A note in `docs/superpowers/2026-07-23-provider-portability-findings.md` recording the
   hosted re-measurement result once run — improvement or finding.
