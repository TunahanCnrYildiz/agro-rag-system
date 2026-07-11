# DergiPark Ingest Pipeline — Quality & Performance Fixes

**Date:** 2026-07-11
**Status:** Approved design, ready for planning
**Scope:** `src/fetch_dergipark.py`, `src/ingest.py`

## Background

The DergiPark harvester downloads Turkish agriculture papers into `docs/books/`
as `dp_<id>.pdf` (currently 201 files), and `src/ingest.py` chunks, filters, and
embeds every PDF/TXT under `docs/books/` into a Chroma store (already ~330 MB).

A sampling audit of 5 DergiPark PDFs found that Turkish text extraction,
header/footer filtering, and glyph-garbage rejection already work well. It also
surfaced three concrete defects, confirmed against real corpus data. This spec
fixes those three. It explicitly does **not** change the embedding model,
two-column PDF handling, or header/footer filtering.

## Confirmed problems (evidence)

1. **Off-topic documents leak in.** `dp_1002002.pdf` is an animal-science paper
   ("Estimation of Growth Curves of Awassi Sheep" / "İvesi Koyunlarının Büyüme
   Eğrileri") that passed the fetcher's `_OFFTOPIC_REC` filter because the regex
   lacks livestock terms (koyun, sheep, ivesi, …). It is now embedded in a
   plant-nutrition store, polluting retrieval.

2. **Valuable NPK/table content dropped as "junk."** In `dp_1000590.pdf`, the
   chunk `"Complete 14-14-14 … Urea [CO(NH2)2] 46-0-0 …"` — a fertilizer NPK
   composition table, the single most product-relevant content for a fertilizer
   company — is discarded by `_is_junk_chunk` because it is digit-heavy and fails
   `MIN_ALPHA_RATIO`.

3. **No incremental ingest.** `iter_chunks` re-reads and re-embeds every file in
   `docs/books/` on every run. With a growing corpus and a 330 MB store this is
   the reason the current workflow relies on a manual "move existing PDFs aside"
   trick.

## Design

### Fix 1 — Strengthen off-topic filter + clean existing store

**Fetcher filter (`fetch_dergipark.py`).** Extend `_OFFTOPIC_REC` with
word-boundary-anchored livestock/animal-science terms:

```
koyun, sheep, kuzu, lamb, keçi, goat, sığır, cattle, inek, buzağı,
ivesi, awassi, broyler, broiler, kanatlı, rasyon, besi, karkas, carcass,
arıcılık, ipekböceği
```

Constraints:
- Anchor short roots with `\b` so substrings like `et`/`süt` are **not** added
  (they would wrongly match `metabolizma`, `etki`, …). Only add `et`/`süt` if
  expressed as safe multiword tokens; default is to omit them.
- Do **not** add `büyüme eğrisi` / `growth curve` — plant growth curves are
  legitimate in-scope content. Rely on animal nouns for discrimination.

**Cleanup pass (new `--clean-offtopic` command in `fetch_dergipark.py`).**
Local, no network:
1. For each `docs/books/dp_*.pdf`, extract first-page text (pypdf).
2. If `_OFFTOPIC_REC` matches the title/first-page text, flag the file.
3. Move the PDF to `docs/books/_offtopic/` (reversible; never delete).
4. Delete its chunks from Chroma via `where={"source": <name>}`.
5. Print a summary (files moved, chunks deleted). Support `--dry-run` to preview
   without moving/deleting.

`docs/books/_offtopic/` must be excluded from ingestion (see Fix 3 note).

### Fix 2 — Preserve NPK / tabular content

Restructure `_is_junk_chunk` in `ingest.py` into ordered stages:

1. **Always reject (hard junk):**
   - shorter than `MIN_CHUNK_CHARS`;
   - contains glyph-map artifacts (regex `/g\d+`);
   - fails `MIN_SPACE_RATIO` (words run together = OCR garbage).
   These catch OCR/glyph noise regardless of numeric content.

2. **Rescue (new):** keep the chunk even if digit-heavy when it shows an
   agronomy numeric signal **and** enough real words:
   - **numeric signal:** matches NPK ratio `\b\d{1,3}-\d{1,3}-\d{1,3}\b`
     **or** a unit token from `(kg/ha|mg/kg|g/kg|ppm|P2O5|K2O|%)`
     (case-insensitive); **and**
   - **real-word floor:** at least **5** tokens with ≥3 alphabetic characters.
   A chunk meeting both bypasses the alpha-ratio and avg-word-length checks.

3. **Otherwise:** apply the existing `MIN_ALPHA_RATIO`, `MAX_AVG_WORD_LEN`, and
   boilerplate-marker checks unchanged.

Net effect: OCR/glyph garbage still filtered; digit-heavy fertilizer tables with
real words are retained.

### Fix 3 — Incremental ingest

Treat the Chroma store as the single source of truth for what is already
ingested. In `ingest.py`, before chunking a file:

- Query `store.get(where={"source": path.name}, limit=1)`; if it returns any id,
  skip the file (it is already ingested).
- Add a `--force` flag that bypasses the skip and re-ingests everything.
- `--reset` keeps its current behavior (drops the collection, then ingests all).
- Exclude `docs/books/_offtopic/` from `_iter_source_files()`.

Because ids are content-derived and stable, re-ingesting an unchanged file was
already a no-op at the DB level; this change skips the expensive **embedding**
call for those files, which is the actual cost.

Edge case: a file interrupted mid-ingest looks "present" and is skipped; users
resolve this with `--force`. Acceptable.

## Out of scope (deliberate)

- Embedding model change (English-centric `nomic-embed-text-v1.5` → multilingual)
  — biggest quality lever, but requires a full re-index; separate decision.
- Two-column PDF extraction — audit found no garbling.
- Additional header/footer filtering — already handled by existing junk filter.

## Testing

- **Fix 1:** unit-test `_OFFTOPIC_REC` against the Awassi title (matches) and
  against in-scope titles containing `etki`, `metabolizma`, `bitki büyüme`
  (must NOT match). Test the cleanup pass on a temp dir with one off-topic and
  one in-scope stub PDF, asserting the off-topic file is moved and the in-scope
  one is left in place.
- **Fix 2:** unit-test `_is_junk_chunk` — the `14-14-14 … 46-0-0` chunk is kept;
  a glyph-garbage chunk (`/g32/g14…`) is dropped; a pure-number chunk with no
  real words is dropped; a normal prose chunk is kept.
- **Fix 3:** ingest a temp file twice; assert the second run performs zero
  embedding calls (skipped), and that `--force` re-ingests it.

## Success criteria

- The Awassi sheep paper (and similar livestock papers) no longer get harvested,
  and `--clean-offtopic` removes already-ingested ones from the store.
- NPK/fertilizer table chunks survive ingestion.
- A second `ingest` run over an unchanged corpus skips already-ingested files and
  finishes in seconds instead of re-embedding the whole corpus.
