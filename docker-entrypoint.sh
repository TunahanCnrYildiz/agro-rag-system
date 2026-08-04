#!/bin/sh
# POC-only bootstrap: if data/vector_store is empty (fresh volume / fresh
# container), fetch the botany corpus and ingest it before serving. Once a
# pre-built store ships from object storage instead, this step goes away.
set -eu

VECTOR_STORE_DIR="data/vector_store"

if [ ! -d "$VECTOR_STORE_DIR" ] || [ -z "$(ls -A "$VECTOR_STORE_DIR" 2>/dev/null)" ]; then
    echo "[entrypoint] $VECTOR_STORE_DIR is empty - fetching + ingesting the corpus (first boot only)"
    python -m src.fetch_fao --max "${FETCH_FAO_MAX:-100}"
    python -m src.fetch_dergipark --max "${FETCH_DERGIPARK_MAX:-120}"
    python -m src.fetch_openalex --max "${FETCH_OPENALEX_MAX:-25}"
    python -m src.fetch_books --max "${FETCH_BOOKS_MAX:-250}"
    python -m src.ingest
else
    echo "[entrypoint] $VECTOR_STORE_DIR already populated - skipping fetch+ingest"
fi

echo "[entrypoint] data/ (persisted on the volume):"
du -sh data/* 2>/dev/null || echo "[entrypoint] (data/ is empty)"

echo "[entrypoint] docs/books/ (fetched PDFs staged for ingest - NOT on the volume, resets every boot):"
du -sh docs/books/* 2>/dev/null || echo "[entrypoint] (docs/books/ is empty)"

echo "[entrypoint] docs/products/ + docs/articles/ (catalog, baked into the image at build time):"
du -sh docs/products docs/articles 2>/dev/null

exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
