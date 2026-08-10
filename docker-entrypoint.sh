#!/bin/sh
# First-boot bootstrap for data/vector_store.
#
# PREFERRED: set VECTOR_STORE_URL to a prebuilt store archive. Re-fetching and
# re-ingesting does NOT reproduce the corpus - the Internet Archive returns
# different books over time - so a container that builds its own store ends up
# with a different, much smaller knowledge base than the one the system was
# measured against. Downloading the same archive everywhere is what makes
# deployments comparable. Set VECTOR_STORE_SHA256 too: a truncated download
# yields a store that opens and answers badly rather than failing.
#
# FALLBACK: with no URL configured the old fetch+ingest path still runs, so
# nothing that works today stops working. It takes ~1.5 h and produces a corpus
# roughly a tenth the size.
set -eu

VECTOR_STORE_DIR="data/vector_store"

if [ -n "${VECTOR_STORE_URL:-}" ]; then
    # The "is it already populated?" decision lives in the Python module, which
    # knows a lone .gitkeep is not a store. Running it unconditionally keeps
    # that judgement in one place.
    echo "[entrypoint] VECTOR_STORE_URL set - fetching the prebuilt store"
    python -m src.fetch_vector_store
elif [ ! -d "$VECTOR_STORE_DIR" ] || [ -z "$(ls -A "$VECTOR_STORE_DIR" 2>/dev/null)" ]; then
    echo "[entrypoint] no VECTOR_STORE_URL and $VECTOR_STORE_DIR is empty"
    echo "[entrypoint] falling back to fetch+ingest - this builds a DIFFERENT, smaller corpus"
    python -m src.fetch_fao --max "${FETCH_FAO_MAX:-100}"
    python -m src.fetch_dergipark --max "${FETCH_DERGIPARK_MAX:-120}"
    python -m src.fetch_openalex --max "${FETCH_OPENALEX_MAX:-25}"
    python -m src.fetch_books --max "${FETCH_BOOKS_MAX:-250}"
    python -m src.ingest
else
    echo "[entrypoint] $VECTOR_STORE_DIR already populated - nothing to do"
fi

echo "[entrypoint] data/ (persisted on the volume):"
du -sh data/* 2>/dev/null || echo "[entrypoint] (data/ is empty)"

echo "[entrypoint] docs/books/ (fetched PDFs staged for ingest - NOT on the volume, resets every boot):"
du -sh docs/books/* 2>/dev/null || echo "[entrypoint] (docs/books/ is empty)"

echo "[entrypoint] docs/products/ + docs/articles/ (catalog, baked into the image at build time):"
du -sh docs/products docs/articles 2>/dev/null

exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
