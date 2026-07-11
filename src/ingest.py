"""Document ingestion pipeline.

Reads every PDF/TXT under docs/books/, splits them into overlapping chunks,
embeds them with the LM Studio embedding model, and stores them in ChromaDB
under data/vector_store/. Files are streamed one at a time and flushed to Chroma
in batches, so the whole corpus never sits in memory at once.

    python -m src.ingest            # add to the store
    python -m src.ingest --reset    # wipe the collection first
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Iterator

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from .config import (
        BOOKS_DIR,
        VECTOR_STORE_DIR,
        settings,
    )
except ImportError:  # pragma: no cover
    from config import BOOKS_DIR, VECTOR_STORE_DIR, settings  # type: ignore


def get_embeddings() -> OpenAIEmbeddings:
    """Embeddings client pointed at the LM Studio OpenAI-compatible server."""
    return OpenAIEmbeddings(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        model=settings.embedding_model,
        # LM Studio embedding servers usually don't support batching well;
        # keep chunks modest and let our own batching drive throughput.
        check_embedding_ctx_length=False,
    )


def get_vector_store():
    """Open (or create) the persistent Chroma collection.

    Imported lazily so that lightweight commands (e.g. --help) don't pay the
    heavy chromadb import cost.
    """
    from langchain_chroma import Chroma

    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=get_embeddings(),
        persist_directory=str(VECTOR_STORE_DIR),
    )


# --------------------------------------------------------------------------- #
# Loading & splitting
# --------------------------------------------------------------------------- #
def _iter_source_files() -> list[Path]:
    if not BOOKS_DIR.exists():
        return []
    files = sorted(
        p
        for p in BOOKS_DIR.rglob("*")
        if p.suffix.lower() in {".pdf", ".txt"}
        and p.is_file()
        and "_offtopic" not in p.parts
    )
    return files


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


def _load_file_text(path: Path) -> Iterator[tuple[str, dict]]:
    """Yield (text, metadata) per logical unit (PDF page or whole TXT file)."""
    if path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
        if text.strip():
            yield text, {"source": path.name, "page": 0}
        return

    # PDF: pypdfium2 preserves word spacing on old scans that pypdf runs
    # together (see docs/superpowers/specs/2026-07-11-ia-scan-pdf-extraction-design.md).
    yield from _extract_pdf_pages(path)


def _stable_chunk_id(source: str, page: int, index: int, text: str) -> str:
    """Deterministic id so re-ingesting the same content updates in place
    instead of creating duplicates."""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{source}:{page}:{index}:{digest}"


MIN_CHUNK_CHARS = 40
MIN_ALPHA_RATIO = 0.6
MIN_SPACE_RATIO = 0.08
MAX_AVG_WORD_LEN = 20
MIN_RESCUE_WORDS = 5  # real words needed to rescue a digit-heavy table

# Recurring USDA scan boilerplate - real text, but metadata about the scan
# itself, not agricultural content. Filtered by substring, case-insensitive.
_BOILERPLATE_MARKERS = (
    "do not assume content reflects current scientific knowledge",
)

# pypdf glyph-mapping failures surface as "/g32" etc. - always garbage.
_GLYPH_ARTIFACT = re.compile(r"/g\d+")
# NPK ratios (14-14-14, 46-0-0) and fertilizer/agronomy unit tokens mark
# digit-heavy chunks worth keeping despite a low letter ratio.
_NPK_RATIO = re.compile(r"\b\d{1,3}-\d{1,3}-\d{1,3}\b")
_UNIT_TOKEN = re.compile(r"kg/ha|mg/kg|g/kg|ppm|p2o5|k2o|%", re.IGNORECASE)


def _real_word_count(text: str) -> int:
    """Count tokens with at least 3 alphabetic characters."""
    return sum(1 for tok in text.split() if sum(c.isalpha() for c in tok) >= 3)


def _has_agronomy_signal(text: str) -> bool:
    """True when the chunk shows fertilizer/agronomy numeric structure."""
    return bool(_NPK_RATIO.search(text) or _UNIT_TOKEN.search(text))


def _is_junk_chunk(text: str) -> bool:
    """Reject OCR-garbage chunks while preserving valuable agronomy tables.

    Stage 1 (hard junk): too short, glyph artifacts, or run-together words.
    Stage 2 (rescue): keep digit-heavy chunks that carry an agronomy numeric
    signal plus enough real words. Stage 3: the original quality heuristics.
    """
    # Stage 1: always reject, regardless of numeric content.
    if len(text) < MIN_CHUNK_CHARS:
        return True
    if _GLYPH_ARTIFACT.search(text):
        return True
    if (text.count(" ") / len(text)) < MIN_SPACE_RATIO:
        return True
    # Stage 2: rescue digit-heavy fertilizer/agronomy tables.
    if _has_agronomy_signal(text) and _real_word_count(text) >= MIN_RESCUE_WORDS:
        return False
    # Stage 3: original quality heuristics.
    letters = sum(c.isalpha() for c in text)
    if (letters / len(text)) < MIN_ALPHA_RATIO:
        return True
    words = text.split()
    if words and (len(text) / len(words)) > MAX_AVG_WORD_LEN:
        return True
    lowered = text.lower()
    if any(marker in lowered for marker in _BOILERPLATE_MARKERS):
        return True
    return False


def _already_ingested(store, source_name: str) -> bool:
    """True when the store already holds at least one chunk for this file."""
    got = store.get(where={"source": source_name}, limit=1)
    return bool(got.get("ids"))


def iter_chunks(
    splitter: RecursiveCharacterTextSplitter, store=None, force: bool = False
) -> Iterator[Document]:
    """Lazily yield chunked Documents across all source files. When ``store`` is
    given and ``force`` is False, files already present in the store are skipped
    so re-ingestion does not re-embed the whole corpus."""
    files = _iter_source_files()
    if not files:
        print(f"[ingest] no .pdf/.txt files found under {BOOKS_DIR}")
        return
    print(f"[ingest] found {len(files)} source file(s)")

    for path in files:
        if store is not None and not force and _already_ingested(store, path.name):
            print(f"[ingest]   = {path.name} already ingested, skipping")
            continue
        print(f"[ingest] processing {path.name}")
        for text, meta in _load_file_text(path):
            for i, chunk in enumerate(splitter.split_text(text)):
                chunk = chunk.strip()
                if not chunk or _is_junk_chunk(chunk):
                    continue
                meta_out = dict(meta)
                meta_out["chunk_index"] = i
                yield Document(page_content=chunk, metadata=meta_out)


# --------------------------------------------------------------------------- #
# Ingestion driver
# --------------------------------------------------------------------------- #
def ingest(reset: bool = False, force: bool = False) -> int:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    store = get_vector_store()

    if reset:
        try:
            store.delete_collection()
            print("[ingest] existing collection deleted (--reset).")
        except Exception as exc:  # noqa: BLE001
            print(f"[ingest] reset warning: {exc}")
        store = get_vector_store()

    batch_docs: list[Document] = []
    batch_ids: list[str] = []
    total = 0

    def flush() -> None:
        nonlocal total
        if not batch_docs:
            return
        store.add_documents(documents=batch_docs, ids=batch_ids)
        total += len(batch_docs)
        print(f"[ingest]   flushed batch, total chunks so far: {total}")
        batch_docs.clear()
        batch_ids.clear()

    for doc in iter_chunks(splitter, store=store, force=force):
        cid = _stable_chunk_id(
            doc.metadata.get("source", "unknown"),
            int(doc.metadata.get("page", 0)),
            int(doc.metadata.get("chunk_index", 0)),
            doc.page_content,
        )
        batch_docs.append(doc)
        batch_ids.append(cid)
        if len(batch_docs) >= settings.ingest_batch_size:
            flush()

    flush()

    if total == 0:
        print(
            "[ingest] nothing ingested. Add .pdf/.txt files to docs/books/ and "
            "ensure LM Studio is serving the embedding model."
        )
    else:
        print(f"[ingest] DONE. {total} chunks persisted to {VECTOR_STORE_DIR}")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest botany documents into Chroma")
    parser.add_argument(
        "--reset", action="store_true", help="Delete the collection before ingesting."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-ingest every file even if already in the store.",
    )
    args = parser.parse_args()
    ingest(reset=args.reset, force=args.force)


if __name__ == "__main__":
    main()
