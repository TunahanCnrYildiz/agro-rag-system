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
import itertools
import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from .config import (
        BOOKS_DIR,
        DATA_DIR,
        VECTOR_STORE_DIR,
        EmbeddingModelMismatchError,
        settings,
    )
except ImportError:  # pragma: no cover
    from config import (  # type: ignore
        BOOKS_DIR,
        DATA_DIR,
        VECTOR_STORE_DIR,
        EmbeddingModelMismatchError,
        settings,
    )


def get_embeddings() -> OpenAIEmbeddings:
    """Embeddings client for the configured embedding endpoint: LM Studio locally,
    or a hosted bge-m3 provider when embedding_base_url/api_key are set. The model
    stays bge-m3 either way (the store is stamped with the logical identity)."""
    return OpenAIEmbeddings(
        base_url=settings.effective_embedding_base_url,
        api_key=settings.effective_embedding_api_key,
        model=settings.embedding_model,
        # LM Studio embedding servers usually don't support batching well;
        # keep chunks modest and let our own batching drive throughput.
        check_embedding_ctx_length=False,
    )


def _check_embedding_model(recorded: str | None, configured: str) -> None:
    """Guard the store against a swapped embedding model.

    - recorded == configured -> silent (happy path).
    - recorded is None -> warn: the collection predates this check and can't be
      verified (the live store is unstamped today). Unknown is not mismatched, so
      we don't break a working setup - but we say we can't verify.
    - otherwise -> raise: query vectors from a different model land in a space the
      store was never indexed in; a same-dimension swap is silent otherwise.
    """
    if recorded == configured:
        return
    if recorded is None:
        print(
            f"[ingest] WARNING: collection '{settings.collection_name}' has no "
            f"recorded embedding model (created before this check). Configured: "
            f"{configured}. Cannot verify - re-ingest with --reset to stamp it."
        )
        return
    raise EmbeddingModelMismatchError(
        f"Store was indexed with embedding model '{recorded}' but the configured "
        f"model is '{configured}'. Retrieval would be garbage. Fix .env to match, "
        f"or re-ingest with --reset to rebuild the store with '{configured}'."
    )


def get_vector_store(verify_model: bool = True):
    """Open (or create) the persistent Chroma collection.

    Imported lazily so that lightweight commands (e.g. --help) don't pay the
    heavy chromadb import cost. Stamps the configured embedding model into the
    collection metadata at creation (a no-op on an existing collection), then
    verifies the recorded model matches - unless ``verify_model`` is False, which
    the --reset path needs so it can open a mismatched store in order to delete it.
    """
    from langchain_chroma import Chroma

    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    store = Chroma(
        collection_name=settings.collection_name,
        embedding_function=get_embeddings(),
        persist_directory=str(VECTOR_STORE_DIR),
        collection_metadata={"embedding_model": settings.embedding_identity},
    )
    if verify_model:
        recorded = (store._collection.metadata or {}).get("embedding_model")
        _check_embedding_model(recorded, settings.embedding_identity)
    return store


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


# --------------------------------------------------------------------------- #
# Publication year / era (2026-07-18)
# Behaviour-neutral metadata: nothing in retrieval reads it yet. See
# docs/superpowers/specs/2026-07-18-year-era-metadata-design.md.
# --------------------------------------------------------------------------- #

# Hand-checked OpenAlex publication_year per oa_ work (offline; no network at
# ingest). All 27 are modern (1979-2020), confirming the freshness audit.
_OA_YEARS: dict[str, int] = {
    "oa_W1602737021.pdf": 1979, "oa_W1979210892.pdf": 2002,
    "oa_W1994145712.pdf": 2007, "oa_W2001465005.pdf": 1994,
    "oa_W2047116407.pdf": 2015, "oa_W2053238406.pdf": 2008,
    "oa_W2061918046.pdf": 2012, "oa_W2088669320.pdf": 2004,
    "oa_W2103202119.pdf": 2000, "oa_W2115917750.pdf": 2009,
    "oa_W2117574536.pdf": 2007, "oa_W2118755534.pdf": 2003,
    "oa_W2124603595.pdf": 2004, "oa_W2167719861.pdf": 2011,
    "oa_W2170232199.pdf": 2003, "oa_W2175948239.pdf": 2005,
    "oa_W2469754973.pdf": 2016, "oa_W2511554536.pdf": 2016,
    "oa_W2518767628.pdf": 2016, "oa_W2609103951.pdf": 2017,
    "oa_W2791140682.pdf": 2018, "oa_W2791209575.pdf": 2018,
    "oa_W2895907234.pdf": 2018, "oa_W3006638720.pdf": 2020,
    "oa_W3020289656.pdf": 2020, "oa_W3026648603.pdf": 2020,
    "oa_W3038546650.pdf": 2020,
}

_OVERRIDES_PATH = DATA_DIR / "source_years.json"
_MIN_PLAUSIBLE_YEAR = 1850
_YEAR_RE = re.compile(r"\b(1[89]\d\d|20\d\d)\b")


@lru_cache(maxsize=1)
def _source_year_overrides() -> dict[str, int]:
    """Manual source->year map that WINS over derivation. Missing file -> {}."""
    try:
        raw = json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: int(v) for k, v in raw.items() if not k.startswith("_")}


def derive_source_year(source_name: str, text: str) -> tuple[int | None, str]:
    """Best-effort publication year for a source, with a confidence tag.

    Order (cheapest-reliable-first): manual override -> oa_ constant -> the first
    plausible 4-digit year (1850..current) scanning the text left-to-right (a
    title/header year appears before reference-list years) -> None. Never
    fabricates: garbled text yields (None, "none"), not a guess.
    """
    override = _source_year_overrides().get(source_name)
    if override is not None:
        return override, "override"
    if source_name in _OA_YEARS:
        return _OA_YEARS[source_name], "api"
    current = date.today().year
    for m in _YEAR_RE.finditer(text):
        year = int(m.group(1))
        if _MIN_PLAUSIBLE_YEAR <= year <= current:
            return year, "text"
    return None, "none"


def _year_to_era(year: int | None) -> str:
    if year is None:
        return "unknown"
    if year < 1950:
        return "pre-1950"
    if year < 1990:
        return "1950-1989"
    if year < 2010:
        return "1990-2009"
    return "2010+"


def _first_pages_text(path: Path, n: int = 6) -> str:
    """Concatenated text of a source's first ``n`` logical units, for year
    derivation. Shares `_load_file_text` so backfill and ingest can't disagree.

    n=6, not 2: measured 2026-07-18, FAO guides and many IA scans print the year
    on a later imprint/copyright page, not the cover. Widening 2->6 rescued 65
    sources / ~11k chunks from `unknown` (18.3% -> ~4%), at 4 extra page reads."""
    parts = [text for text, _meta in itertools.islice(_load_file_text(path), n)]
    return "\n".join(parts)


def build_backfill_metadata(records, year_of):
    """Pure core of the backfill (tested without Chroma).

    ``records`` is an iterable of (chunk_id, source, existing_metadata);
    ``year_of`` maps a source name -> (year|None, era). Returns (ids, metadatas)
    where each metadata is the FULL existing dict plus era (+ year when known),
    so `collection.update` never drops a field it isn't setting.
    """
    ids: list[str] = []
    metas: list[dict] = []
    for cid, source, meta in records:
        year, era = year_of(source)
        new = dict(meta)
        new["era"] = era
        if year is not None:
            new["year"] = year
        else:
            new.pop("year", None)
        ids.append(cid)
        metas.append(new)
    return ids, metas


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
    splitter: RecursiveCharacterTextSplitter, store=None, force: bool = False,
    zero_chunk_out: list[str] | None = None,
) -> Iterator[Document]:
    """Lazily yield chunked Documents across all source files. When ``store`` is
    given and ``force`` is False, files already present in the store are skipped
    so re-ingestion does not re-embed the whole corpus.

    Files that are processed but yield no usable chunks (image-only scans with no
    text layer) are appended to ``zero_chunk_out`` so the driver can surface them
    instead of letting them vanish silently as dead weight.
    """
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
        year, _conf = derive_source_year(path.name, _first_pages_text(path))
        era = _year_to_era(year)
        emitted = 0
        for text, meta in _load_file_text(path):
            for i, chunk in enumerate(splitter.split_text(text)):
                chunk = chunk.strip()
                if not chunk or _is_junk_chunk(chunk):
                    continue
                meta_out = dict(meta)
                meta_out["chunk_index"] = i
                meta_out["era"] = era
                if year is not None:
                    meta_out["year"] = year
                emitted += 1
                yield Document(page_content=chunk, metadata=meta_out)
        if emitted == 0 and zero_chunk_out is not None:
            zero_chunk_out.append(path.name)


# --------------------------------------------------------------------------- #
# Ingestion driver
# --------------------------------------------------------------------------- #
def ingest(reset: bool = False, force: bool = False) -> int:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # --reset must open a possibly-mismatched store in order to delete it, so the
    # guard would deadlock the one command that fixes a mismatch: skip it here.
    store = get_vector_store(verify_model=not reset)

    if reset:
        try:
            store.delete_collection()
            print("[ingest] existing collection deleted (--reset).")
        except Exception as exc:  # noqa: BLE001
            print(f"[ingest] reset warning: {exc}")
        store = get_vector_store()  # fresh collection: stamped + verified by default

    batch_docs: list[Document] = []
    batch_ids: list[str] = []
    zero_chunk: list[str] = []
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

    for doc in iter_chunks(splitter, store=store, force=force,
                           zero_chunk_out=zero_chunk):
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
    if zero_chunk:
        print(f"[ingest] WARNING: {len(zero_chunk)} file(s) produced 0 chunks "
              f"(image-only scan? need OCR):")
        for name in zero_chunk:
            print(f"[ingest]   ! {name}")
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
