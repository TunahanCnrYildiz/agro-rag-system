# Spec: viticulture cross-lingual lexicon entry + suffix-aware matcher

**Date:** 2026-07-18
**Status:** design

## Problem (measured 2026-07-18)

A 30-probe retrieval audit found exactly one true 0-chunk case among natural TR
questions: **"Asmada kış budaması nasıl yapılır?"** returns empty context. The
grape-pruning content EXISTS in the store (31 English `oa_` chunks, reachable at
0.52-0.53 by English queries) but the TR query's top-20 never includes it (best
raw score 0.3469, just under the 0.36 floor), so nothing survives.

Two independent causes:
1. **`CROP_LEXICON` has no grape entry** (`asma`/`üzüm`/`bağ` -> grape), so
   cross-lingual expansion never adds an English search that would reach `oa_`.
2. Even with an entry, **the matcher `(?<!\w){term}(?!\w)` can't match a suffixed
   word**: "Asma**da**" (asma + locative -da) fails the trailing `(?!\w)` guard.
   Measured: the same bug blocks "muzda", "kahvede" for existing lexicon crops.

Both are needed: an entry alone won't fire on "asmada"; a suffix-aware matcher
alone has no grape term to add.

## Constraint that shapes the matcher

A naive suffix-aware matcher (`{term}\w*`) REGRESSES a guarded case: "kahve" would
then fire inside "**kahve**rengi" (brown), a common disease query. The existing
test `test_expand_query_requires_word_boundary` encodes this guard and must stay
green. So the matcher must distinguish a Turkish inflectional SUFFIX (asma+**da**)
from a different morpheme (kahve+**rengi**).

## Design

1. **Add two entries to `CROP_LEXICON`:** `asma -> grapevine`, `üzüm -> grape`.
   Skip `bağ` (ambiguous: bağ = tie/bond, bağırsak = intestine, bağlamak = to
   tie) — the measured gap is fixed by `asma` alone, and the lexicon's doctrine is
   "extend only with evidence". `üzüm -> grape` is a low-risk add for grape-fruit
   queries.
2. **Make the matcher suffix-aware via a bounded suffix list**, not `\w*`:
   `(?<!\w){term}(?:<TR inflectional suffixes>)?(?!\w)`, suffixes ordered
   longest-first. Matches term + at most one common case/plural/possessive ending
   + word end. "asmada" ✓ (asma+da); "kahverengi" ✗ ("rengi" not a suffix, and the
   empty-suffix branch hits `(?!\w)` on 'r'); "muzip" ✗; "domuz" ✗ (leading guard);
   "muzda" ✓; "kahvede" ✓.
   The matched span (term + suffix) still drives the existing substitution branch,
   so "asmada kış budaması" -> substituted "grapevine kış budaması".

## Out of scope / rejected
- **Lowering the global floor:** measured — at 0.34 the off-scope "bilgisayar…"
  query pulls 20 chunks (best 0.4065). Floor alone can't separate on/off-scope.
- **Corpus expansion:** coverage is fine; this is an access problem.
- **`bağ` entry:** deferred until a measured gap needs it.

## Verification
- `pytest -q` green (new + existing `_expand_query` tests, esp. the boundary guard).
- `python -m evals.run_eval` stays 33/33 (or 32/33 with the known deveci flake).
- Live probe: `engine.retrieve_context("Asmada kış budaması nasıl yapılır?")`
  returns non-empty context reaching `oa_`/`fao_` viticulture chunks.
