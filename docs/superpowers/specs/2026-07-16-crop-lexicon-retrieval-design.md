# Crop-Lexicon Cross-Lingual Retrieval — Design

**Date:** 2026-07-16
**Status:** Approved (ready for plan + implementation)
**Supersedes:** `2026-07-16-cross-lingual-retrieval-design.md` (translation-based)
**Files touched:** `src/engine.py`, `src/config.py`, `tests/test_engine.py`

## Problem

A Turkish query about a crop whose literature exists **only in the English corpus**
(`fao_`/`oa_`/`ia_`) never reaches that content. The Turkish corpus is dense with
generic fertilization papers that clear the 0.36 floor and fill `k`, so the
on-topic English chunks never make the cut.

**Evidence** (2026-07-16, probed 7 crops; EN content confirmed present for each):

| TR query | EN content exists | TR query reaches it |
|---|---|---|
| Manyok (cassava) | ✅ | ❌ (top-4 = yonca, şeker mısırı) |
| Kakao (cocoa) | ✅ | ❌ |
| Tatlı patates (sweet potato) | ✅ | ❌ |
| Yağ palmiyesi (oil palm) | ✅ | ❌ |
| Darı (millet) | ✅ | ❌ |
| Gölevez (taro) | ✅ | ❌ |
| Kahve (coffee) | ✅ | ✅ (control) |

**6 of 7 are gaps.** This is systematic, not an edge case: the FAO (95 PDFs) and
OpenAlex global-crop corpora were imported *for* these crops, and Turkish users
are the audience — the gap makes that investment largely unreachable.

Eval cases `cassava_nutrition_tr`, `gap_*_tr` encode this; `coffee_tr_control`
guards against mistaking a general regression for the gap.

## Why the current (translation) approach cannot fix it

`_translate_query` asks the local chat model (`google/gemma-4-12b-qat`) to
translate the query. Measured 2026-07-16:

| Failure | Evidence |
|---|---|
| Returns **empty** | `finish_reason="length"`, `content=""`, all 512 tokens spent on `reasoning_content` (2114 chars). Hits ~half of the gap queries. |
| **Not fixable by budget** | sweet potato is empty at 512, 1024 **and 2048** tokens — and takes **38.2 s** at 2048. |
| **Mistranslates** | "Darı" → **"sorghum"** (correct: millet) → retrieves the wrong crop, silently. |
| **Reasoning can't be disabled** | `chat_template_kwargs={"enable_thinking": False}` and a `/no_think` prefix both still return empty. |
| **No alternative model** | LM Studio serves exactly one chat model. |
| **Slow** | 4.7 s median (3.2–7.3), ~+17% on a ~28 s answer. |
| **Weak result anyway** | Always-translating fixes only **3 of 6** gaps. |
| **Rewires products** | Changes the product list in **9 of 25** cases (incl. `tomato_disease_organic` 0→3, `banana_sigatoka` 3→0) — noise, not improvement. |

The prior spec's claim *"512 is reliable across query lengths (verified)"* is
**false**; it generalised from a few queries.

Also disproven along the way (all measured, do not re-chase):

- **Score-threshold trigger** — `prim_top` does not separate good from bad:
  cassava (needs rescue) **0.455** vs. tomato_nutrition (healthy) **0.454**.
- **Lexical-overlap trigger** — *inverted* signal: cassava **0.67**, healthy
  compost **0.00**. "Wrong content" and "right content in another language" look
  identical lexically.
- **"bge-m3 is multilingual, it bridges anyway"** — no cassava chunk in the TR
  query's **top 30**.
- **Bigger k / reranking** — nothing to rerank: the right chunks aren't in the
  candidate pool at all.
- **RRF alone (with translation)** — 2/6.

## Solution

A **deterministic TR→EN crop-name lexicon** feeding extra vector searches, fused
by **rank** (RRF). No LLM on the retrieval path.

1. `CROP_LEXICON: dict[str, str]` — Turkish crop name → English crop name.
2. `_expand_query(query)` returns extra queries for every lexicon term found:
   - **bare English term** (`"cassava"`) — carries most of the benefit (4/6 alone);
   - **substituted query** — the term swapped inside the *original* query
     (`"cassava yetiştiriciliğinde gübreleme nasıl olmalı?"`) — adds millet (5/6).
3. `_fuse` becomes **RRF**: each list contributes `1/(60 + rank)` per document;
   the floor is applied **per list, before ranking**. Raw scores are never
   compared across lists — they are not comparable (Turkish filler ~0.45–0.52
   outscores the right English chunk ~0.46–0.48, which is why score-fusion
   dropped cacao by 0.003).

**Measured result** (all 31 eval cases, word-boundary matching):
**5 of 6 gaps fixed, 0 regressions, 0 product-count changes.**

### Matching rules

- **Normalise for detection only:** fold Turkish letters to ASCII and lowercase
  (`Darı`→`dari`, `Gölevez`→`golevez`), so diacritic-free typing still matches.
  The fold is **1:1 per character**, so match spans map back to the original.
- **Substitute into the ORIGINAL query**, never the normalised one — folding the
  whole query strips diacritics and degrades the embedding (measured: drops
  millet, 5/6 → 4/6).
- **Word-boundary match** (`(?<!\w)term(?!\w)`), longest term first. Substring
  matching produces real collisions: **`kahve` inside `kahverengi`** (fires on
  the tomato-disease query) and **`muz` inside `domuz`**.

## Decisions / constraints

- **No new dependencies.** Two extra vector searches per lexicon hit (~ms).
- **Unconditional:** expansion is cheap, so the "only when under-filled" trigger
  is **removed**. That trigger was measured firing on just 1 of 25 realistic
  cases, and it is exactly what made cassava fail (junk *fills* `k`).
- **Toggle kept:** `settings.cross_lingual_retrieval` keeps its name and default
  (`True`); `False` restores single-query retrieval and keeps tests hermetic.
- **Off-scope preserved:** the floor still gates every list, so off-scope queries
  keep returning empty/irrelevant context and the LLM still refuses. Product
  suppression is untouched (measured: 0 product changes).
- **Products are not involved.** The lexicon maps *crop* names for **retrieval
  only**. The 48-product catalog and its embedding match are untouched.
- **`_translate_query` is deleted**, not kept as a fallback: it is measurably
  broken, slow, and its failure mode is silent.

## Out of scope / known gaps

- **`gap_taro_tr` stays failing.** Bare `"taro"` doesn't surface the content
  (short terms embed weakly); the English *sentence* did. Documented, not fixed.
- **EN→TR reverse gap: unmeasured.** Every English eval case passes today, so no
  reverse gap is demonstrated. Lexicon is TR→EN only until one is measured.
- **Suffixed forms not matched** (`"Manyokta gübreleme"`): word-boundary matching
  trades agglutination coverage for collision safety. Revisit only with evidence.
- **Curation is a maintenance surface.** A gap crop absent from the lexicon gains
  nothing — this is bounded coverage, not a general solution. The entries are the
  crops measured as gaps; a generated TR→EN glossary from corpus crop names is a
  future option, not part of this change.
