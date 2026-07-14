# OpenAlex Fetcher — Design Spec

**Date:** 2026-07-14
**Status:** Approved design, ready for planning
**Scope:** new file `src/fetch_openalex.py` (+ tests)

## Background

The RAG corpus is biased toward Turkish (DergiPark) and US/temperate (Internet
Archive) agriculture. Now that the assistant's scope is "any plant topic", it
should also cover tropical/global gap crops (cassava, plantain, sorghum, millet,
cowpea, yam, rice, …). OpenAlex is the chosen first global source: free API, no
key, rich open-access + topic/crop filtering, direct OA PDF URLs. This fetcher
mirrors the proven `fetch_dergipark.py` pattern.

## Decisions (locked during brainstorming)

- **Target:** curated **gap crops** (not broad agronomy) — approach A.
- **Language:** **English only** for the first source.
- **Scale:** small **validation harvest first** (~20-30 PDFs), then scale.
- **Query strategy:** per-crop keyword search (mirrors the per-journal loop).

## OpenAlex API facts (from research)

- Endpoint: `https://api.openalex.org/works`
- Polite pool: add `mailto=<email>` param (faster, reliable) — no API key needed.
- Filters (comma-separated in `filter=`): `title_and_abstract.search:<crop>`,
  `open_access.is_oa:true`, `language:en`.
- Sort: `sort=cited_by_count:desc` (prefer well-cited/established work).
- Paging: `per-page` (max 200) + cursor paging (`cursor=*` → `meta.next_cursor`).
- Per work: `id` (`https://openalex.org/W…` → short id `W…`), `doi`,
  `best_oa_location.pdf_url` (may be null), `open_access.oa_url` (fallback,
  often a landing page), `language`.

## Design

### File & reuse
`src/fetch_openalex.py`, reusing `pdf_fetch_utils.pdf_session` /
`stream_pdf_to_file` and `config.BOOKS_DIR`. Imports
`fetch_dergipark._OFFTOPIC_REC` as the single source of truth for off-topic
(livestock/economics) terms.

### Constants
- `OPENALEX_URL = "https://api.openalex.org/works"`
- `POLITE_MAILTO` — contact email for the polite pool (e.g.
  `agrobotanybot@ekolojiktarim.com.tr`).
- `CROP_TERMS` — curated gap-crop search terms, e.g.: cassava, plantain,
  sorghum, "pearl millet", "finger millet", cowpea, yam, taro, "sweet potato",
  rice, teff, "pigeon pea", groundnut, banana. (Curated list = `CURATED_JOURNALS`
  equivalent; editable.)
- `PDF_DELAY` (polite delay between PDF downloads), `OA_DELAY` (between API
  calls), `OA_RETRIES`, `MIN_BYTES = 60_000` (reuse dergipark value).

### Components
- `_oa_get(session, params) -> dict | None` — GET `/works` with `mailto` added;
  retry with backoff on 429 / 5xx; return parsed JSON or None.
- `_work_to_candidate(work) -> tuple[str, str, str, str] | None` — return
  `(oa_id, pdf_url, doi, title)`; return None when: no OA `pdf_url`
  (`best_oa_location.pdf_url` then `open_access.oa_url`), language != en, or the
  title matches `_OFFTOPIC_REC`.
- `search_crop(session, crop, max_per_crop) -> list[candidate]` — query works
  with `filter=title_and_abstract.search:<crop>,open_access.is_oa:true,
  language:en` + `sort=cited_by_count:desc`, page until `max_per_crop`
  candidates collected.
- `_collect_candidates(session, crops, per_crop) -> list[candidate]` — across
  crops, **dedup by oa_id AND doi**.
- `_is_pruned(oa_id) -> bool` — True if `oa_<oa_id>.pdf` already sits under
  `docs/books/_offtopic/` (don't re-download), mirroring dergipark's `_is_pruned`.
- `download(session, url, dest) -> bool` — thin wrapper over `stream_pdf_to_file`
  (`%PDF` header + `MIN_BYTES` validation); a landing-page HTML response fails
  the `%PDF` check and is skipped.
- `run(crop, max_books, per_crop, dry_run)` + `main()` with CLI: `--max`,
  `--per-crop`, `--crop`, `--dry-run`, `--list-crops` (same shape as
  `fetch_dergipark`).

### File naming & data flow
`oa_<OpenAlexID>.pdf` (e.g. `oa_W2755950973.pdf`) in `BOOKS_DIR`. Flow:
CROP_TERMS → per-crop OpenAlex search (is_oa, en) → candidates (off-topic-title
filtered) → cross-crop dedup (id+doi) → download+validate → `oa_*.pdf` →
`python -m src.ingest` picks them up incrementally.

### Dedup
- Within-source: skip if `oa_<id>.pdf` exists, or `_is_pruned(id)`.
- Within-batch: dedup candidates by oa_id and doi.
- Cross-source (dp_/ia_): NOT handled — we don't store DOIs for those, and
  tropical-English papers are unlikely to overlap Turkish DergiPark / US IA.
  Rare duplicates accepted (documented tradeoff).

### Error handling & politeness
- API 429/5xx → backoff + retry; `mailto` param for the polite pool.
- Missing `pdf_url` → skip candidate.
- Non-PDF (landing page) response → `%PDF` check in `stream_pdf_to_file` skips it.
- Publisher block / timeout → skip, continue; `PDF_DELAY` between downloads.

## Out of scope (v1, deliberate)
- Cross-source DOI dedup against dp_/ia_.
- Landing-page → PDF resolution (add only if success rate proves too low).
- A dedicated `--clean-offtopic` pass (the title off-topic filter + crop-name
  search should keep it clean; add if a leak is observed).
- Non-English / multilingual harvest.

## Testing
- **Unit (TDD):** `_work_to_candidate` — mock work JSON: has OA pdf_url → tuple;
  no OA location → None; off-topic title (e.g. "cattle feed from cassava") →
  None; language "fr" → None. `_collect_candidates` dedup by id and doi.
  `_is_pruned` (temp `_offtopic/` with an `oa_*.pdf`). `download` relies on the
  already-tested `stream_pdf_to_file`.
- **Manual/integration:** `--dry-run --max 25` against the real API (read-only)
  to confirm candidate parsing and PDF-url availability.

## Success criteria
- `python -m src.fetch_openalex --max 25 --per-crop 4` downloads ~25 valid
  English OA PDFs across gap crops into `docs/books/` as `oa_*.pdf`.
- After `python -m src.ingest`, a query like "cassava fertilization" or "sorghum
  nutrient management" returns a grounded answer citing an `oa_*` source.
- No off-topic (livestock) papers pass the title filter into the corpus.
