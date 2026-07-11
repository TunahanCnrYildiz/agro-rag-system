# IA Scan PDF Extraction (pypdfium2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 117 space-less English Internet Archive scans (`ia_*.pdf`) searchable by extracting their PDF text with `pypdfium2` instead of `pypdf`, which restores the word spacing the junk filter needs.

**Architecture:** One touch point — the PDF branch of `_load_file_text` in `src/ingest.py` is factored into a new `_extract_pdf_pages` helper backed by `pypdfium2`, plus a pure `_normalize_text` line-ending helper. The junk filter, chunking, batching, incremental-skip, and all DergiPark logic are unchanged. Because the 117 broken books have 0 chunks in the store, a normal `python -m src.ingest` run re-processes exactly them and skips everything already ingested.

**Tech Stack:** Python 3, pytest, pypdfium2 (Apache-2.0/BSD PDFium wrapper), langchain-text-splitters, Chroma.

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-07-11-ia-scan-pdf-extraction-design.md`.
- **Do not modify** `src/fetch_dergipark.py` or any DergiPark-specific logic.
- **Do not modify** `_is_junk_chunk` or any of its thresholds/regexes — the filter must stay byte-for-byte identical (existing tests are the regression guard).
- Keep `pypdf` in `requirements.txt`; it is still used by the DergiPark cleanup path. **Add** `pypdfium2`, do not remove `pypdf`.
- `pypdfium2` page/textpage/document objects each hold native resources — always `.close()` them.
- Run tests from the project root so `src` imports as a package: `python -m pytest`.
- Commit messages: English, short, no AI-style body, no `Co-Authored-By` trailer.

---

### Task 1: Swap PDF extraction to pypdfium2

**Files:**
- Modify: `requirements.txt` (add `pypdfium2`)
- Create: `tests/fixtures/ia_301ento00unit.pdf` (committed test fixture, ~214 KB, public-domain USDA doc)
- Modify: `src/ingest.py` (add `_normalize_text` + `_extract_pdf_pages`; rewrite the PDF branch of `_load_file_text` at lines 86-100)
- Modify: `tests/test_ingest.py` (add extraction tests)

**Interfaces:**
- Consumes: `MIN_SPACE_RATIO`, `_is_junk_chunk`, `settings` (existing).
- Produces:
  - `_normalize_text(text: str) -> str` — maps `\r\n` and `\r` to `\n`.
  - `_extract_pdf_pages(path: Path) -> Iterator[tuple[str, dict]]` — yields
    `(page_text, {"source": path.name, "page": page_num})` for each non-empty
    page, using `pypdfium2`. Unreadable PDFs print the existing skip message and
    yield nothing.

- [ ] **Step 1: Add the dependency and install it**

Append to `requirements.txt` under the `# --- Document ingestion ---` section (below the `pypdf>=4.2.0` line):

```
pypdfium2>=4.0
```

Run: `python -m pip install "pypdfium2>=4.0"`
Expected: pypdfium2 installs successfully.

- [ ] **Step 2: Add the test fixture**

Copy the sample scan from the corpus into a committed fixtures dir:

```bash
mkdir -p tests/fixtures
cp "D:/Claude Projects/Agro-Botany RAG & Product Linker System/docs/books/ia_301ento00unit.pdf" tests/fixtures/ia_301ento00unit.pdf
```

Expected: `tests/fixtures/ia_301ento00unit.pdf` exists (~214 KB). It is NOT
gitignored (`.gitignore` only excludes `docs/books/*.pdf`).

- [ ] **Step 3: Write the failing tests**

Add to `tests/test_ingest.py` (top-level imports and new tests):

```python
from pathlib import Path

from src.ingest import (
    _extract_pdf_pages,
    _is_junk_chunk,
    _normalize_text,
    MIN_SPACE_RATIO,
)
from src.config import settings
from langchain_text_splitters import RecursiveCharacterTextSplitter

FIXTURE = Path(__file__).parent / "fixtures" / "ia_301ento00unit.pdf"


def test_normalize_text_collapses_crlf():
    assert _normalize_text("a\r\nb\rc\nd") == "a\nb\nc\nd"


def test_extract_pdf_pages_yields_page_metadata():
    pages = list(_extract_pdf_pages(FIXTURE))
    assert pages, "fixture should yield at least one page"
    text, meta = pages[0]
    assert meta["source"] == "ia_301ento00unit.pdf"
    assert meta["page"] == 0
    assert text.strip()


def test_extract_pdf_pages_restores_word_spacing():
    pages = list(_extract_pdf_pages(FIXTURE))
    full = " ".join(text for text, _ in pages)
    assert full, "fixture should produce text"
    # pypdf gave ~0.001 here (words run together); pypdfium2 restores spacing.
    assert full.count(" ") / len(full) >= MIN_SPACE_RATIO


def test_extract_pdf_pages_survives_junk_filter():
    # Under pypdf this file yielded 0 kept chunks; pypdfium2 must yield >= 1.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    kept = 0
    for text, _ in _extract_pdf_pages(FIXTURE):
        for chunk in splitter.split_text(text):
            chunk = chunk.strip()
            if chunk and not _is_junk_chunk(chunk):
                kept += 1
    assert kept >= 1
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python -m pytest tests/test_ingest.py -k "normalize or extract_pdf" -v`
Expected: FAIL with `ImportError: cannot import name '_extract_pdf_pages'`
(and `_normalize_text`) — the helpers do not exist yet.

- [ ] **Step 5: Implement the helpers in `src/ingest.py`**

Add these two functions immediately above `_load_file_text` (before line 78):

```python
def _normalize_text(text: str) -> str:
    """Normalize PDF line endings to plain '\\n' (PDFium emits CRLF)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _extract_pdf_pages(path: Path) -> Iterator[tuple[str, dict]]:
    """Yield (text, metadata) per PDF page using pypdfium2, which preserves
    word spacing on old scans that pypdf runs together. Unreadable PDFs print a
    skip message and yield nothing."""
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(path))
    except Exception as exc:  # noqa: BLE001
        print(f"[ingest] skipping unreadable PDF {path.name}: {exc}")
        return
    try:
        for page_num in range(len(pdf)):
            page = pdf[page_num]
            textpage = page.get_textpage()
            try:
                text = _normalize_text(textpage.get_text_range() or "")
            finally:
                textpage.close()
                page.close()
            if text.strip():
                yield text, {"source": path.name, "page": page_num}
    finally:
        pdf.close()
```

- [ ] **Step 6: Rewrite the PDF branch of `_load_file_text`**

In `src/ingest.py`, replace the PDF block (current lines 86-100):

```python
    # PDF: stream page by page so we never hold the whole book in memory.
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001
        print(f"[ingest] skipping unreadable PDF {path.name}: {exc}")
        return
    for page_num, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            text = ""
        if text.strip():
            yield text, {"source": path.name, "page": page_num}
```

with:

```python
    # PDF: pypdfium2 preserves word spacing on old scans that pypdf runs
    # together (see docs/superpowers/specs/2026-07-11-ia-scan-pdf-extraction-design.md).
    yield from _extract_pdf_pages(path)
```

- [ ] **Step 7: Run the new tests to verify they pass**

Run: `python -m pytest tests/test_ingest.py -k "normalize or extract_pdf" -v`
Expected: all four new tests PASS.

- [ ] **Step 8: Run the full suite (filter regression guard)**

Run: `python -m pytest`
Expected: every test passes, including the untouched filter tests
(`test_npk_table_is_kept`, `test_glyph_garbage_is_dropped`,
`test_pure_numbers_dropped`, `test_normal_prose_is_kept`) and the
`fetch_dergipark` tests.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt tests/fixtures/ia_301ento00unit.pdf src/ingest.py tests/test_ingest.py
git commit -m "Extract PDFs with pypdfium2 to restore word spacing"
```

---

### Task 2: End-to-end re-ingest verification (manual)

> Requires LM Studio serving the embedding model and writes to the real Chroma
> store. No code change, no commit — this is the acceptance check that the fix
> rescues the 117 books in practice. Run it (or hand it to the user) after
> Task 1 is green.

**Files:** none (runtime verification only).

- [ ] **Step 1: Run a normal ingest**

Run: `python -m src.ingest`
Expected: the 117 previously-empty `ia_*.pdf` print `[ingest] processing <name>`
and contribute chunks (`flushed batch, total chunks so far: …` climbs);
already-ingested `dp_*.pdf` and working `ia_*.pdf` print
`= <name> already ingested, skipping`. Finishes with
`[ingest] DONE. <N> chunks persisted`.

- [ ] **Step 2: Spot-check retrieval**

Query the store for content from a rescued book (e.g. via the app / engine) and
confirm a previously-invisible IA scan (such as `ia_bluemoldoftobacc250mcgr.pdf`
or `ia_301ento00unit.pdf`) now appears in results.
Expected: at least one rescued `ia_*.pdf` source is retrievable.

---

## Self-Review

**Spec coverage:**
- Extractor swap to pypdfium2 in `ingest.py` via `_extract_pdf_pages` → Task 1 (Steps 5-6). ✓
- `_normalize_text` CRLF handling → Task 1 (Steps 3, 5). ✓
- Junk filter unchanged (regression guard) → Task 1 Step 8. ✓
- DergiPark logic untouched; `pypdf` kept, `pypdfium2` added → Global Constraints + Task 1 Step 1. ✓
- Testing: filter regression, normalization unit, fixture integration (space-ratio + survives-filter) → Task 1 Steps 3, 7, 8. ✓
- Flag-free re-ingest of the 117 zero-chunk books → Task 2. ✓
- Out-of-scope items (embedding model, two-column, `--force` full re-extract) → not planned. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows full code and every command shows expected output. ✓

**Type consistency:** `_normalize_text(text) -> str` and `_extract_pdf_pages(path) -> Iterator[tuple[str, dict]]` are named and used identically across the implementation, imports, and tests. Metadata shape `{"source": name, "page": n}` matches the contract `iter_chunks` already consumes. ✓
