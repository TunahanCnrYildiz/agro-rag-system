# FAO Knowledge Repository Fetcher — Design

**Date:** 2026-07-15
**Status:** Approved (ready for implementation plan)
**Module:** `src/fetch_fao.py`

## Purpose

Add a second global open-access source to the corpus: the **FAO Knowledge
Repository** (`openknowledge.fao.org`, a DSpace 7.2.1 instance). This grows the
plant-knowledge corpus alongside the existing fetchers — Internet Archive
(`ia_`), DergiPark (`dp_`), and OpenAlex (`oa_`) — adding authoritative FAO
technical publications on crop production, plant nutrition, soil, horticulture,
and organic/cultural plant health.

New PDFs land in `docs/books/` as `fao_<id>.pdf` and enter the vector store via
the existing `python -m src.ingest` pipeline. No new dependencies.

## Feasibility findings (verified 2026-07-15)

These probes drove the design; they are recorded so the implementation does not
re-litigate settled facts.

| Probe | Result | Design consequence |
|---|---|---|
| OAI-PMH `Identify` at `https://openknowledge.fao.org/server/oai/request` | HTTP 200, DSpace 7.2.1, `repositoryName=FAODocuments` | OAI-PMH is the harvest API (like DergiPark). First call can be slow (cold start) → generous timeout + retry. |
| DSpace REST `discover/search/objects?query=...` | **HTTP 403 (WAF)** | Cannot keyword-search server-side (rules out the OpenAlex-style query approach). |
| OAI `ListSets` | 17 **structural** sets (communities/collections: Publications, Technical documents, Meeting docs, Posters, Rare books...), no thematic/subject sets | Sets narrow by *document type*, not by plant subject. Subject selection must be client-side. |
| OAI `ListRecords` (oai_dc) sample record | `dc:subject` often **absent**; `dc:language` is a full word ("English"/"French"); `dc:identifier` contains a **direct `.pdf` URL** (e.g. `http://www.fao.org/3/a-x6751f.pdf`); `dc:type`, `dc:title`, `dc:description` present | Filter on **title + description** keywords (no reliable subject). Language filter on the full word. Extract the direct PDF link — no landing-page scraping. |
| Direct PDF URL download | HTTP 200, `application/pdf`, `%PDF` header, ~139 KB, 302-redirects to the DSpace bitstream `/content` URL | Reuse `pdf_fetch_utils.stream_pdf_to_file` unchanged (it follows redirects and validates `%PDF` + min size). |

## Selection strategy (Approach A)

Harvest **one set — "Publications"** (`col_20.500.14283_2`), FAO's book/technical
publication collection (highest quality; excludes meeting minutes, posters,
newsletters). The set spec is a config constant, configurable via `--set`, so
broadening to more sets later (e.g. Technical documents `col_20.500.14283_3`) is
a one-line change, not a rewrite.

Because OAI-PMH has no keyword search, we page through the set with
`resumptionToken` and filter each record **client-side**. A record becomes a
download candidate only when **all** hold:

1. **Language** — `dc:language` equals English.
2. **Plant include** — the title + description contains at least one curated
   plant/agronomy term (e.g. crop, plant, soil, nutrition, fertiliz*,
   horticulture, agronomy, irrigation, seed, pruning, graft, greenhouse,
   compost, cultivation, pest/disease *management*, pollination, propagation).
3. **Off-topic exclude** — the title + description does **not** match the
   off-topic regex (fisher/aquacult, livestock/poultry/cattle/dairy/ruminant,
   forest/forestry/timber/logging, veterinary, trade/market/economics/price).
   Mirrors the OpenAlex fetcher's nuance: do **not** exclude bare
   "poultry"/"cattle" so *manure/compost* fertilizer documents survive
   (the excludes target feed/animal-production contexts, e.g. "poultry feed").
4. **Direct PDF** — `dc:identifier` has a value ending in `.pdf`.

This is the "hybrid" the user chose, adjusted to reality: the *set* narrows the
document type; the *keyword include + off-topic exclude* narrows the plant
subject.

### Note on chemical-pesticide content
Some FAO IPM documents mention chemical pesticides. They are **not** excluded at
fetch time — they are legitimate reference material, and the assistant's
answer-time guardrails (never recommend chemical pesticides; stay within the
organic frame) already govern how that content is used. Excluding at ingest
would lose useful cultural/biological context that lives in the same documents.

## Architecture

`src/fetch_fao.py`, following `fetch_dergipark.py` / `fetch_openalex.py`:

- **Constants:** `OAI_URL`, `PUBLICATIONS_SET = "col_20.500.14283_2"`,
  `OAI_DELAY`, `PDF_DELAY`, `OAI_TIMEOUT=90`, `OAI_RETRIES=3`,
  `MIN_BYTES=60_000`, the plant-include term list, and the off-topic regex.
- **`_oai_list_records(session, set_spec, resumption_token)`** → parsed XML page
  (retry with backoff on timeout / 429 / 5xx), returning records + next token.
- **`_record_to_candidate(record_el)`** → `(fao_id, pdf_url, title)` or `None`.
  Pure function over one parsed OAI record; applies the 4 filters above.
  `fao_id` = handle tail from the OAI header identifier
  (`oai:openknowledge.fao.org:20.500.14283/x6751f` → `x6751f`).
- **`_collect_candidates(session, set_spec, max_books, max_scan)`** → pages
  through the set, dedupes by `fao_id`, stops when `max_books` candidates found
  or `max_scan` records scanned (prevents unbounded walking of a huge set).
- **`_is_pruned(fao_id)`** → skip if already moved to `docs/books/_offtopic/`.
- **`download(session, url, dest)`** → reuse `stream_pdf_to_file`.
- **`run(set_spec, max_books, max_scan, dry_run)`** → orchestrates; skips
  existing `fao_<id>.pdf`; prints a `--dry-run` preview table; on success prints
  `next: python -m src.ingest`.
- **`main()`** → argparse CLI.

**Reused (no duplication):** `pdf_session`, `stream_pdf_to_file`, `MIN_BYTES`
convention, `BOOKS_DIR` — all from existing modules. Same `try/except ImportError`
dual-import shim as the other `src/` modules.

## Data flow

```
OAI ListRecords (set=Publications, paged via resumptionToken)
  -> for each record: _record_to_candidate  (lang + include + exclude + .pdf)
  -> dedupe by fao_id, cap at max_books / max_scan
  -> download direct .pdf via stream_pdf_to_file (validates %PDF + size)
  -> docs/books/fao_<id>.pdf   (skip if exists or previously pruned)
  -> python -m src.ingest      (existing incremental ingest adds to store)
```

## CLI

```
python -m src.fetch_fao --list-sets              # show the 17 OAI sets and exit
python -m src.fetch_fao --dry-run --max 100      # preview candidates, download nothing
python -m src.fetch_fao --max 100                # harvest (default)
python -m src.fetch_fao --set col_20.500.14283_3 # harvest a different set
python -m src.fetch_fao --max-scan 8000          # cap records scanned
```

| Flag | Default | Meaning |
|---|---|---|
| `--max` | 100 | Max PDFs to download. |
| `--max-scan` | 8000 | Max OAI records to scan before stopping. |
| `--set` | `col_20.500.14283_2` (Publications) | OAI setSpec to harvest. |
| `--dry-run` | off | Preview candidates; download nothing. |
| `--list-sets` | off | Print `ListSets` and exit. |

## Error handling

- **Slow/failed OAI page** — retry with backoff (`OAI_RETRIES`); on final
  failure, log and stop paging gracefully (keep what was gathered).
- **Bad PDF** (not `%PDF`, too small, HTTP != 200) — `stream_pdf_to_file`
  rejects it; `.part` temp is removed; continue to next candidate.
- **Malformed record** (missing identifier / handle / pdf) —
  `_record_to_candidate` returns `None`; skip.
- **Politeness** — `OAI_DELAY` between OAI calls, `PDF_DELAY` between downloads;
  crawler `User-Agent` from `pdf_fetch_utils`.

## Testing

`tests/test_fetch_fao.py` (matches existing pure-unit-test style; network
mocked, no real HTTP):

- English plant record (crop/soil in title/description) with a `.pdf`
  identifier → candidate returned; `fao_id` parsed correctly from the handle.
- French record → `None` (language filter).
- Forestry / fisheries title → `None` (off-topic exclude).
- "poultry manure" fertilizer record → candidate (exclude nuance preserved).
- Record with no `.pdf` identifier → `None`.
- Plant-relevant but non-English → `None`.

## Quality gate

After harvesting and `python -m src.ingest`, run `python -m evals.run_eval` to
confirm the baseline (12/12: retrieval, product-gating, grounding, guardrail)
has not regressed.

## Documentation

- Module docstring with runnable examples (like the other fetchers).
- Add a `fao_` row to the fetcher list in `README.md`.
- Update the `handoff-next-steps` memory (FAO fetcher done; next source / step).

## Out of scope (YAGNI)

- Multi-language harvesting (English only for this pass; bge-m3 is multilingual,
  so a language can be added later by relaxing the filter).
- Multiple sets in one run (single `--set`; broaden later if recall is low).
- DSpace REST API usage (WAF-blocked; OAI-PMH is sufficient).
- Landing-page / bitstream-API resolution (direct `.pdf` link is in the record).
```
