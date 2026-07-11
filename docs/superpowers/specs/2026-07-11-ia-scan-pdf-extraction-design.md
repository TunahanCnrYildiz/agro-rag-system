# IA Scan Ingestion — Restore Word Spacing via pypdfium2

**Date:** 2026-07-11
**Status:** Approved design, ready for planning
**Scope:** `src/ingest.py`, `requirements.txt`, `tests/`

## Background

`src/ingest.py` extracts text from every PDF under `docs/books/` with
`pypdf`'s `page.extract_text()`, chunks it, filters junk via `_is_junk_chunk`,
and embeds the survivors into Chroma. The corpus mixes Turkish DergiPark papers
(`dp_*.pdf`) with ~258 older English Internet Archive scans (`ia_*.pdf`,
USDA/agriculture books and bulletins).

The `ia_*.pdf` scans contribute **zero** chunks to the store.

## Confirmed problem (evidence)

A diagnostic run over the real corpus (junk filter + splitter unchanged, no
embeddings) found:

- **117 of 258** `ia_*.pdf` yield **0 kept chunks**.
- All 117 are dominated by the `space` drop reason (aggregate drop reasons across
  the 117: `space=4991`, `short=447`, `alpha=29`).
- **`no_text_at_all = 0`** — every one of the 117 files *has* a text layer;
  `pypdf` simply extracts it without word spacing.

Root cause: on these scans `pypdf.extract_text()` returns run-together text
(e.g. `"Donotassumecontentreflectscurrent…"`), giving a space ratio around
**0.001**. Every chunk fails the `MIN_SPACE_RATIO = 0.08` check in
`_is_junk_chunk` and is dropped as OCR garbage — even though the underlying text
is clean and correctly ordered.

Because the text layer already exists and is correct, **OCR is not required**.
The fix is a PDF text extractor that recovers word spacing from glyph positions.

### Extractor comparison (measured on the real broken files)

Four extractors were run on known-bad scans
(`bluemold` / `301ento` / `waysidewoodland` / `rootrot`), counting chunks that
survive the *unchanged* `_is_junk_chunk`:

| Extractor          | space ratio | chunks kept (was 0)   | reading order    | license           |
| ------------------ | ----------- | --------------------- | ---------------- | ----------------- |
| `pypdf` (current)  | ~0.001      | 0 / 0 / 0 / 0         | n/a              | BSD               |
| **`pypdfium2`**    | 0.15–0.16   | **160 / 8 / 494 / 502** | correct        | Apache-2.0 / BSD  |
| `pymupdf` (fitz)   | 0.10–0.13   | 151 / 7 / 450 / 506   | correct          | **AGPL-3.0**      |
| `pdfplumber`       | 0.14–0.15   | 154 / 8 / 435 / 504   | **scrambles words** | MIT            |

**No regression on the working Turkish corpus:** across 15 random `dp_*.pdf`,
`pypdfium2` matches `pypdf`'s kept-chunk counts (26/26, 84/84, 64/64, 62/62,
53/53, 65/65, …); only 1/15 is marginally lower. Switching does not degrade the
DergiPark books.

### Decision

Replace `pypdf` extraction with **`pypdfium2`** (Google's PDFium via a
permissively licensed wrapper) as a **wholesale swap** in `ingest.py`:

- Highest chunk recovery and correct reading order (unlike `pdfplumber`).
- Apache-2.0 / BSD license — no AGPL exposure for a company tool (unlike
  `pymupdf`).
- Near-parity on the Turkish corpus, so a single extraction path is safe; a
  conditional per-page fallback would add branching complexity for no benefit.

**Rejected alternatives:**
- *`wordninja` de-concatenation fallback* — a word-segmentation hack applied to
  space-less chunks. It cannot recover original casing/punctuation and risks
  corrupting good text; reading the correct text layer beats re-segmenting a
  broken extraction.
- *`ocrmypdf` re-OCR* — heavy (needs Tesseract + Ghostscript system binaries)
  and unnecessary: the evidence (`no_text_at_all = 0`) shows the text layer is
  present and correct.

## Design

### Extraction (only change to `ingest.py`)

Factor the PDF branch of `_load_file_text` into a small, testable helper:

```
_extract_pdf_pages(path: Path) -> Iterator[tuple[str, dict]]
```

- Opens the PDF with `pypdfium2.PdfDocument`, iterates pages, and reads text via
  `page.get_textpage().get_text_range()`.
- Normalizes line endings `\r\n` / `\r` → `\n` (PDFium emits CRLF) through a
  pure helper `_normalize_text(text: str) -> str`.
- Yields `(text, {"source": path.name, "page": n})` for non-empty pages only —
  the exact contract `_load_file_text` yields today.
- Wraps open/extract in `try/except`: an unreadable PDF prints the existing
  `[ingest] skipping unreadable PDF <name>: <exc>` message and yields nothing
  (same resilience as the current code). Closes the `PdfDocument` to release
  native resources.

`_load_file_text` keeps its `.txt` branch and delegates the PDF branch to
`_extract_pdf_pages`. Chunking, batching, stable IDs, `_is_junk_chunk`, the
incremental-skip logic, and every threshold are **unchanged**.

### Junk filter — unchanged (deliberate)

`_is_junk_chunk` and all constants (`MIN_SPACE_RATIO`, `MIN_ALPHA_RATIO`,
glyph/NPK/unit regexes, rescue stage) stay byte-for-byte identical. Genuine
run-together OCR garbage is still rejected by the same `MIN_SPACE_RATIO` gate;
`pypdfium2` simply stops producing false run-together output on these scans.

### DergiPark logic — untouched (deliberate)

`src/fetch_dergipark.py` is not modified. Its `_first_page_text` /
`--clean-offtopic` classification keeps using `pypdf`. The off-topic filter and
the recently shipped incremental-ingest / NPK-rescue behavior are out of scope.

### Dependencies

`requirements.txt` gains `pypdfium2` (`>=4.0`). `pypdf` stays — it is still used
by the DergiPark cleanup path.

## Re-ingest flow (no new flags)

The 117 broken books have 0 chunks in the store, so `_already_ingested` returns
False for them. A plain:

```
python -m src.ingest
```

re-processes exactly those 117 (now succeeding via `pypdfium2`) and skips every
already-ingested `dp_`/`ia_` file. Expected console signature: 117 files print
`processing`, the rest print `= <name> already ingested, skipping`. No `--force`
or `--reset` required. `--force` remains available if someone later wants to
re-extract the entire corpus under `pypdfium2` — a separate, optional decision,
not part of this change.

## Testing

Failing-test-first, three layers:

1. **Filter regression guard.** The existing `tests/test_ingest.py` cases
   (`test_npk_table_is_kept`, `test_glyph_garbage_is_dropped`,
   `test_pure_numbers_dropped`, `test_normal_prose_is_kept`) stay green,
   proving the junk filter is untouched.

2. **Normalization unit test (no fixture).** Assert `_normalize_text` maps
   `"a\r\nb\rc"` → `"a\nb\nc"`. Fast, pure, no PDF.

3. **Fixture integration test (the actual fix).** Commit
   `tests/fixtures/ia_301ento00unit.pdf` (~214 KB, public-domain USDA quarantine
   notice, one of the files named in the original diagnosis). Assert that
   `_extract_pdf_pages` on it:
   - produces text whose overall space ratio ≥ `MIN_SPACE_RATIO`, and
   - yields at least one chunk that survives `_is_junk_chunk`.

   This test fails on the current `pypdf` code (0 chunks) and passes after the
   swap.

**End-to-end verification (manual, after tests green):** run
`python -m src.ingest` with LM Studio serving the embedding model; confirm the
117 `ia_*.pdf` are processed and produce chunks while `dp_*.pdf` are skipped.

## Out of scope (deliberate)

- Changing `fetch_dergipark.py` or any DergiPark-specific logic.
- Modifying `_is_junk_chunk` thresholds or the NPK-rescue stage.
- Re-extracting already-ingested files (available via `--force`, not run here).
- Embedding-model changes and two-column layout handling.

## Success criteria

- The 117 space-less `ia_*.pdf` scans yield chunks and become searchable after a
  normal `python -m src.ingest` run.
- Turkish `dp_*.pdf` retrieval quality is unchanged (near-identical chunk
  counts).
- The junk filter still rejects genuine OCR/glyph garbage (existing tests green).
- No changes to DergiPark harvesting or cleanup behavior.
