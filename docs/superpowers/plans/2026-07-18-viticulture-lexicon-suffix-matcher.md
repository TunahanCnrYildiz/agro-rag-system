# Plan: viticulture lexicon entry + suffix-aware matcher

Spec: `../specs/2026-07-18-viticulture-lexicon-suffix-matcher-design.md`. TDD.

## Task 1 — RED: tests for the new behavior
In `tests/test_engine.py`, around the existing `_expand_query` tests:
- MODIFY `test_expand_query_no_lexicon_hit_returns_query_only`: "Asmada budama" is
  no longer a no-hit example — replace its query with a genuine non-lexicon one
  (e.g. "Domateste yaprak sararması neden olur?").
- ADD `test_expand_query_viticulture_suffix`: `_expand_query("Asmada kış budaması
  nasıl yapılır?")` includes "grapevine" AND the substituted "grapevine kış
  budaması nasıl yapılır?". (RED: no asma entry + suffix can't match.)
- ADD `test_expand_query_uzum_entry`: `_expand_query("Üzümde ben düşmesi")`
  includes "grape". (RED.)
- ADD `test_expand_query_suffix_generalizes`: `_expand_query("Muzda leke var")`
  includes "banana". (RED: current `(?!\w)` blocks the -da suffix.)
- KEEP AS-IS (must stay green — these are the guard): the boundary test asserting
  "kahverengi" and "domuz" do NOT expand; longest-term; disabled; no-LLM; the
  manyok substitution test.

Run `pytest -q tests/test_engine.py -k expand` -> the 3 new + modified fail.

## Task 2 — GREEN: implement in `src/engine.py`
- Add to `CROP_LEXICON`: `"asma": "grapevine"`, `"üzüm": "grape"`.
- Replace the match regex in `_expand_query` with a bounded-suffix version:
  a module-level `_TR_SUFFIXES` alternation (longest-first: nda|nde|dan|den|tan|
  ten|lar|ler|yla|yle|nın|nin|nun|nün|sı|si|su|sü|da|de|ta|te|ya|ye|na|ne|la|le|
  ın|in|un|ün|ı|i|u|ü|a|e|yı|yi|yu|yü), used as
  `rf"(?<!\w){re.escape(term)}(?:{_TR_SUFFIXES})?(?!\w)"`.
- Keep the substitution using `match.start()/match.end()` (now spans the suffix).

Run `pytest -q` -> all green (suite was 143; expect 143 + new).

## Task 3 — VERIFY end-to-end (needs LM Studio + store)
- `python -m evals.run_eval` -> 33/33 (accept 32/33 iff only `local_deveci_pear`
  is red — the known flake; confirm with `--repeat 8 --only local_deveci_pear`).
- Scratch probe: `retrieve_context("Asmada kış budaması nasıl yapılır?")` is
  non-empty and cites `oa_`/`fao_` viticulture sources. Record char count + sources.
