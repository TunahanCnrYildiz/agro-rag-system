# Cross-Lingual Retrieval — Design

**Date:** 2026-07-16
**Status:** Approved (ready for plan + implementation)
**File touched:** `src/engine.py`, `src/config.py`, `tests/test_engine.py`

## Problem

The corpus is roughly half Turkish (`dp_`) and half English (`ia_`/`oa_`/`fao_`).
Dense retrieval with bge-m3 scores cross-lingual matches lower than same-language
ones, so a **Turkish query about an English-covered topic scores below the 0.36
relevance floor** and its relevant chunks are dropped as "noise". The content is
present; retrieval just fails to surface it.

**Evidence** (2026-07-16, via `evals/inspect_retrieval` + direct probes):

| Query | cleared floor / top |
|---|---|
| 🇹🇷 "Bağda bordo bulamacı nasıl hazırlanır?" | 0/6, top 0.353 |
| 🇬🇧 "bordeaux mixture copper sulfate lime" | 1/6, top 0.366 |
| 🇹🇷 "Muz ... Sigatoka organik" | 2/6, top 0.368 |
| 🇬🇧 "black sigatoka banana leaf spot control" | **6/6, top 0.450** |

Corpus counts confirm the content exists: `bordeaux` 281 chunks, `sigatoka` 34
chunks (+ FAO `fao_as087e`). The gap is language, not coverage.

## Solution

**Query translation + multi-query fusion**, inside `retrieve_context`:

1. `_expand_query(q)` → `[q, translation]`. Translation target = **English** when
   `detect_language(q) == "Turkish"`, else **Turkish**. Translation is produced
   by the LM Studio chat model with a short, temperature-0 prompt.
2. Retrieve top-`k` for each query in the list.
3. `_fuse(result_lists, floor, k)`: pool `(Document, score)`, dedup by chunk text
   keeping the **max** score, apply the floor, sort by score desc, take top `k`.

Rendering (the `[Kaynak: src, s.page]` headers) is unchanged.

## Decisions / constraints

- **Local-only:** chat model translates, bge-m3 embeds. No new dependencies.
- **Fallback:** if translation raises, returns empty, or equals the original, use
  `[q]` only — retrieval never breaks because of the new step.
- **Off-scope preserved:** the floor is still applied per fused result, so an
  off-scope query (e.g. "Bitcoin price") returns empty context and the LLM still
  refuses. Verified by the eval off-scope + guardrail cases.
- **Config toggle:** `settings.cross_lingual_retrieval: bool = True`; set False to
  restore single-query behaviour (also used to keep some unit tests hermetic).
- **Latency:** +1 short translate call and 2× search per query. Accepted; the
  translation is cacheable later if needed.

## Success criteria

- `evals/inspect_retrieval`: the Turkish bordo / Sigatoka rows improve (more
  chunks clear the floor, higher top score) after the change.
- `python -m evals.run_eval` stays **25/25** (especially off-scope `products:none`
  and the guardrail cases — the new step must not leak or over-retrieve).

## Out of scope (YAGNI)

BM25 hybrid, cross-encoder reranking, relevance-floor tuning, and per-language
targeting beyond the TR↔EN pair (other languages translate to English via the
`detect_language=="English"` branch, which is good enough for this pass).
