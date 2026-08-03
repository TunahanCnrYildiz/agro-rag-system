#!/bin/sh
# POC-only bootstrap: if data/vector_store is empty (fresh volume / fresh
# container), fetch the botany corpus and ingest it before serving. Once a
# pre-built store ships from object storage instead, this step goes away.
set -eu

VECTOR_STORE_DIR="data/vector_store"

if [ ! -d "$VECTOR_STORE_DIR" ] || [ -z "$(ls -A "$VECTOR_STORE_DIR" 2>/dev/null)" ]; then
    echo "[entrypoint] $VECTOR_STORE_DIR is empty - fetching + ingesting the corpus (first boot only)"
    python -m src.fetch_fao --max "${FETCH_FAO_MAX:-40}"
    python -m src.fetch_dergipark --max "${FETCH_DERGIPARK_MAX:-40}"
    python -m src.fetch_openalex --max "${FETCH_OPENALEX_MAX:-20}"
    python -m src.fetch_books --max "${FETCH_BOOKS_MAX:-20}"
    python -m src.ingest
else
    echo "[entrypoint] $VECTOR_STORE_DIR already populated - skipping fetch+ingest"
fi

exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
