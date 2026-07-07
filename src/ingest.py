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
        if p.suffix.lower() in {".pdf", ".txt"} and p.is_file()
    )
    return files


def _load_file_text(path: Path) -> Iterator[tuple[str, dict]]:
    """Yield (text, metadata) per logical unit (PDF page or whole TXT file)."""
    if path.suffix.lower() == ".txt":
        text = path.read_text(encoding="utf-8", errors="ignore")
        if text.strip():
            yield text, {"source": path.name, "page": 0}
        return

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


def _stable_chunk_id(source: str, page: int, index: int, text: str) -> str:
    """Deterministic id so re-ingesting the same content updates in place
    instead of creating duplicates."""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{source}:{page}:{index}:{digest}"


def iter_chunks(splitter: RecursiveCharacterTextSplitter) -> Iterator[Document]:
    """Lazily yield chunked Documents across all source files."""
    files = _iter_source_files()
    if not files:
        print(f"[ingest] no .pdf/.txt files found under {BOOKS_DIR}")
        return
    print(f"[ingest] found {len(files)} source file(s)")

    for path in files:
        print(f"[ingest] processing {path.name}")
        for text, meta in _load_file_text(path):
            for i, chunk in enumerate(splitter.split_text(text)):
                chunk = chunk.strip()
                if not chunk:
                    continue
                meta_out = dict(meta)
                meta_out["chunk_index"] = i
                yield Document(page_content=chunk, metadata=meta_out)


# --------------------------------------------------------------------------- #
# Ingestion driver
# --------------------------------------------------------------------------- #
def ingest(reset: bool = False) -> int:
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

    for doc in iter_chunks(splitter):
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
    args = parser.parse_args()
    ingest(reset=args.reset)


if __name__ == "__main__":
    main()
