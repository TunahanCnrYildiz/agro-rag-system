# Year/Era Metadata at Ingest — Design

**Date:** 2026-07-18
**Status:** Draft (ready for plan)
**Files touched:** `src/ingest.py`, `tests/test_ingest.py`, a one-time backfill
script under `scripts/` (or `evals/`), an override sidecar `data/source_years.json`.
**Follows:** the 2026-07-18 freshness audit (handoff item 26/(b)) — which had to
DERIVE every source's year at runtime because the store carries none.

## Problem

Chunk metadata today is only `{"source", "page", "chunk_index"}` (`ingest.py`
~104/114). There is **no publication year or era**. Two concrete costs, both
observed on 2026-07-18:

1. **The freshness audit is not repeatable.** Establishing "36% of chunks are
   `ia_`, ~20% pre-1950, and the early-20thC pathology bulletins are the prune
   target" required a bespoke read-only script that paged the whole store and
   regex-guessed a year from each source's first pages. That characterisation now
   lives only in a memory note, not in the data. The next time someone asks "how
   old is the corpus now?" (e.g. after the (b) prune, or a future harvest) the
   whole derivation must be redone from scratch.
2. **Freshness cannot inform retrieval.** The accuracy map (item 28) found the
   corpus wins on local/specific facts (deveci pear) but a 1910 `ia_` source
   (Hopkins) is worse than the model on general physiology. Any future attempt to
   act on that — down-weight or flag old sources — needs a per-chunk age it can
   read. There is nowhere to read it from.

## Scope — a pure data enrichment, NOTHING else

This spec adds `year` and `era` to chunk metadata and backfills the existing
store. **It changes no retrieval or answer behaviour.** Consuming the field
(freshness-weighted retrieval, an "as of YEAR" note in citations, a UI badge) is
explicitly OUT OF SCOPE and gated on separate measurement — see "Deliberately
deferred" below. Keeping this change behaviour-neutral is what makes it low-risk:
the eval must stay byte-identical (33/33) because no code reads the new field yet.

## What we can and cannot know about a source's year

Per-prefix reliability, measured in the (b) audit:

| Prefix | Files | Year signal | Confidence |
|---|---|---|---|
| `dp_` | ~619 | Printed in the PDF text (Turkish journals stamp "Derg. (2012)…"); all 1990+ | HIGH via text |
| `fao_` | ~93 | In text / doc code; all modern | HIGH (1 known mis-parse: `fao_bt155e`→"1907") |
| `oa_` | 27 | OpenAlex `publication_year` via the `W…` id; all modern | HIGH via API, or text |
| `ia_` | ~210 (post-prune) | **NOISY** — scan-date digitization stamps ("2000", "2014") leak into the text and mis-age old books as modern; filename sometimes encodes it (`soilfertilityper00hopkiala`, `…128nanc`) | LOW via text; needs care |

The honest constraint: **an exact year is not reliably recoverable for `ia_` from
text alone**, and the bias direction is known (pre-1950 UNDER-counted, modern
OVER-counted). So the design must not pretend to precision it does not have.

## Design

### 1. Granularity: derive a best-effort `year` (int|null) AND a coarse `era`
- `year`: best integer estimate, or `null` when undeterminable. Never fabricate.
- `era`: one of `pre-1950 | 1950-1989 | 1990-2009 | 2010+ | unknown` (the audit's
  buckets). The era is what downstream logic should key on; the raw `year` is kept
  for transparency/debugging but is explicitly "best effort".

### 2. Year is computed ONCE PER SOURCE, not per chunk
All chunks of a file share its year. A `derive_source_year(source_name, first_pages_text)`
pure function returns `(year|None, confidence)` where confidence ∈
`{"text", "filename", "api", "override"}`. Attach the result to every chunk's
metadata in the Document builder (`ingest.py` ~227).

### 3. Prefix-aware derivation, cheapest-reliable-first
- `dp_`/`fao_`: extract the earliest plausible 4-digit year (1850–current) from
  the first ~2 pages of text. (Earliest-plausible beats most-frequent: it dodges
  a reference-list year while catching the header year. Verify on a sample.)
- `oa_`: prefer an offline map built once from OpenAlex (`publication_year`); only
  27 files, so this can even be a hand-checked constant. No network at ingest time.
- `ia_`: try filename-encoded year first; else earliest-plausible text year; mark
  confidence `text` (low). This is the acknowledged-noisy path.

### 4. A manual override sidecar `data/source_years.json`
`{ "<source>.pdf": 1911, ... }` — a small, git-tracked map that WINS over
derivation (confidence `override`). Seed it ONLY with the audit's known
mis-parses and high-value corrections (`fao_bt155e`, `ia_plantphysiologyw00dugg`
~1911, `ia_soilfertilityper00hopkiala` ~1908, and any others spot-checked wrong).
This is the pragmatic mitigation for `ia_` noise: don't over-engineer the parser,
correct the handful that matter by hand. The file is the auditable record of
those decisions.

### 5. Backfill the existing store WITHOUT re-embedding
The store already holds ~76,798 chunks with no year. Re-ingesting to add a
metadata field would needlessly re-embed everything. Instead a one-time script:
- pages all sources, derives each source's year once,
- calls `collection.update(ids=[...], metadatas=[...])` in batches to patch the
  metadata in place (embeddings untouched).
Chroma's `update` preserves vectors; only metadata changes. Idempotent — safe to
re-run.

## Verification
- **Behaviour unchanged:** `python -m pytest -q` green; `python -m evals.run_eval`
  stays 33/33 (nothing reads `year` yet — if the eval moves, the change leaked).
- **Derivation correctness:** unit tests for `derive_source_year` on fixed inputs —
  a `dp_` header string → its year; a filename-encoded `ia_` → its year; an
  override → the override; garbled text → `(None, ...)` not a fabricated year.
- **Distribution sanity:** after backfill, the era histogram matches the (b) audit
  within noise (~20% pre-1950 chunks; `dp_`/`fao_`/`oa_` all modern; `ia_`
  bimodal). Spot-check: Hopkins→pre-1950, `ia_EsausPlantAnatomy`→1990-2009.
- **Coverage:** report the count of `year=null` / `era=unknown` sources; it should
  be small and dominated by genuinely undatable `ia_` scans.

## Risks & caveats
- **`ia_` year noise is real and unfixable in general** — the override sidecar
  bounds it to the cases that matter; do NOT chase a perfect parser (measured: the
  scan-date leak is inherent to how these were digitized).
- **`ingest` skips already-present files** (`already ingested, skipping`), so
  turning on the metadata at ingest only affects NEW files; the backfill script is
  the mechanism for the existing store. Both paths must use the SAME
  `derive_source_year` so a re-ingest can never disagree with the backfill.
- **Do not let this grow scope.** The temptation is to also "use" the field
  immediately. Resist — see below.

## Deliberately deferred (own spec, gated on measurement)
**Freshness-weighted retrieval / age-aware ranking is NOT in this spec.** It is
gated on item 28's accuracy map, which already shows the sign is not uniform:
down-weighting old sources would HELP where the old corpus is worse than the model
(NPK physiology, Hopkins 1910) but HURT where an older corpus source is the
correct, specific answer (deveci pear storage — corpus beat the model). A blind
"newer = better" weight would degrade exactly the local-cultivar wins this project
values. That feature must be designed and measured on its own; this spec only lays
the data it would need.

## Open decisions for the plan
1. **`oa_` year source:** offline OpenAlex snapshot vs a hand-checked 27-entry
   constant. (Recommend the constant — 27 files, zero network, fully auditable.)
2. **Override sidecar location/format:** `data/source_years.json` (proposed) vs
   inline in a py module. (Recommend JSON in `data/`, git-tracked, so it is data
   not code.)
3. **`year=null` policy:** store `era="unknown"` + `year` absent, vs a sentinel.
   (Recommend: omit `year`, set `era="unknown"` — absence is honest.)
