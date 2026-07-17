# Plan: year/era metadata at ingest

Spec: `../specs/2026-07-18-year-era-metadata-design.md`. TDD throughout. The whole
change is behaviour-neutral: **the eval must stay 33/33 by construction** (no code
reads the new field yet). Open decisions resolved to the spec's recommendations:
- `oa_` year: a hand-checked 27-entry constant `_OA_YEARS` in `ingest.py`.
- override sidecar: `data/source_years.json` (git-tracked data, not code).
- `year=null`: omit the `year` key, set `era="unknown"` (Chroma rejects None
  metadata values anyway — omission is both honest and required).

## Task 1 — Data: override sidecar + oa_ constant
- Create `data/source_years.json` seeded ONLY with the audit's known corrections:
  `{"fao_bt155e.pdf": <modern>, "ia_soilfertilityper00hopkiala.pdf": 1908,
  "ia_plantphysiologyw00dugg.pdf": 1911, "ia_morphologyofangi00couluoft.pdf": 1903}`
  (+ any other spot-checked-wrong file). Keep it SMALL; it is the auditable record
  of manual overrides, not a full map.
- Add `_OA_YEARS: dict[str, int]` to `ingest.py` — the 27 `oa_W….pdf` publication
  years. Build it once by hand from OpenAlex (offline; no network at ingest). If a
  couple are uncertain, leave them out (they fall through to text derivation).

## Task 2 — RED: pure-function tests (`tests/test_ingest.py`)
Add tests that fail against no implementation:
- `test_year_to_era_buckets`: `_year_to_era` maps 1908→"pre-1950", 1975→"1950-1989",
  2001→"1990-2009", 2018→"2010+", None→"unknown"; boundary years 1950/1990/2010
  land in the newer bucket.
- `test_derive_year_override_wins`: with a patched sidecar mapping "x.pdf"→1911,
  `derive_source_year("x.pdf", "…lots of 2003 text…")` returns `(1911, "override")`.
- `test_derive_year_oa_constant`: an `oa_W….pdf` in `_OA_YEARS` returns that year,
  confidence `"api"`, WITHOUT scanning text.
- `test_derive_year_dp_from_text`: `derive_source_year("dp_19411.pdf", "Akd. Univ.
  Ziraat Fak. Derg. (2012) 25(1): 53-57 … references 1999, 2006 …")` returns
  `(2012, "text")` — earliest-plausible HEADER year, not a later reference year.
  (Pick the rule that satisfies this on the real sample; verify against 2-3 real
  dp_ first-pages before locking the regex.)
- `test_derive_year_garbled_returns_none`: text with no plausible 1850–current year
  → `(None, ...)`, never a fabricated number.

Run `pytest -q tests/test_ingest.py -k "year or era or derive"` → all fail.

## Task 3 — GREEN: derivation functions in `src/ingest.py`
- `_load_source_year_overrides() -> dict` (lazy, reads `data/source_years.json`;
  `{}` if absent).
- `derive_source_year(source_name: str, text: str) -> tuple[int | None, str]`:
  1. override sidecar → `(year, "override")`
  2. `oa_` prefix and in `_OA_YEARS` → `(year, "api")`
  3. else earliest plausible 4-digit year (1850..current) in `text` → `(year,
     "text")`; for `ia_` also try a clear filename-encoded year first if present.
  4. else `(None, "none")`.
- `_year_to_era(year: int | None) -> str` with the four buckets + "unknown".
Run the Task-2 tests → green.

## Task 4 — RED: ingest attaches era/year to chunk metadata
- `test_iter_chunks_tags_era`: drive `iter_chunks` over a hermetic fixture
  (monkeypatch `_iter_source_files` → one fake path, `_load_file_text` → yields a
  page whose text carries a year, and `_first_pages_text` if used). Assert every
  yielded Document has `metadata["era"]` set and `metadata["year"]` present when
  the year is known. Fails today.

## Task 5 — GREEN: wire derivation into `iter_chunks` (`src/ingest.py` ~213-229)
- Per `path`, BEFORE the chunk loop, derive the source year ONCE from its first
  ~2 pages of text (add/reuse `_first_pages_text(path, n=2)` — handoff item 10
  notes a `_first_page_text` already exists for the clean-offtopic path; generalise
  or add a sibling). Compute `era = _year_to_era(year)`.
- In the `meta_out` build (~224): `meta_out["era"] = era`; `if year is not None:
  meta_out["year"] = year`. Do NOT set `year=None` (Chroma rejects None).
Run full `pytest -q` → green (suite 147 + new).

## Task 6 — Backfill the existing store (no re-embedding)
- Add `scripts/backfill_years.py` (default DRY-RUN, `--apply` gated), whose core is
  a tested pure helper (reuse `derive_source_year`/`_year_to_era` so backfill and
  ingest can never disagree — spec requirement):
  1. page the collection, group chunk ids by `source`;
  2. for each source, locate its PDF under `docs/books/` (skip `_offtopic`), read
     first pages, derive `(year, era)` ONCE;
  3. `collection.update(ids=[...], metadatas=[...])` in batches — vectors
     untouched. Idempotent.
  - DRY-RUN prints: sources, derived era histogram, count of `era="unknown"`, and
    any source whose PDF is missing (tag `unknown`, do not crash).
- `test_backfill_core_groups_and_derives`: unit-test the grouping+derivation core
  on a fake store (no real Chroma), asserting the id→metadata patch it WOULD write.
- Review the DRY-RUN histogram against audit b (~20% pre-1950 chunks; dp_/fao_/oa_
  modern; ia_ bimodal) BEFORE `--apply`. Then run `--apply`.

## Task 7 — VERIFY (evidence, not assertion)
- `pytest -q` green.
- `python -m evals.run_eval` → **33/33 unchanged** (accept the known `local_deveci`
  flake; anything else moving means the field leaked into behaviour — investigate).
- Post-backfill sanity: a scratch scan of the store confirms era histogram ≈ audit
  b; spot-check `ia_soilfertilityper00hopkiala`→pre-1950, `ia_EsausPlantAnatomy`→
  1990-2009, a `dp_`→2010+.
- Report the `era="unknown"` share; it must be small and dominated by genuinely
  undatable `ia_` scans (name them).

## Commit shape (per project: batched, English, no co-author)
1. data + derivation functions + their tests (Tasks 1-3).
2. ingest wiring + test (Tasks 4-5).
3. backfill script + test (Task 6). Backfill RUN is a store mutation (not git) —
   note it in the memory handoff like the (b) prune, with before/after counts.
Do NOT push unless asked. Store mutation (backfill) is reversible only by
re-deriving; it adds metadata, deletes nothing.
