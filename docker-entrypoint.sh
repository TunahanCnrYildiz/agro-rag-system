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

# No configuration needed: the archive URL and its checksum are defaults in
# src/config.py, and VECTOR_STORE_URL / VECTOR_STORE_SHA256 override them if a
# deployment wants a different source. The "is it already populated?" decision
# lives in the Python module too, which knows a lone .gitkeep is not a store -
# keeping that judgement in one place.
#
# THE EXIT CODE DECIDES WHETHER FALLING BACK IS ALLOWED (see src/fetch_vector_store.py):
#   0  store is in place
#   1  could not obtain the archive - quota, network, no URL. Fall back; that is
#      what the fallback is for.
#   2  obtained something that is NOT the corpus - checksum mismatch, wrong or
#      empty archive. DO NOT fall back. Falling back would swap a loud problem
#      for a silent one: a corpus a tenth the size that answers badly instead of
#      failing, which is exactly what the checksum exists to prevent.
echo "[entrypoint] ensuring $VECTOR_STORE_DIR is populated"
if python -m src.fetch_vector_store; then
    fetch_status=0
else
    fetch_status=$?
fi

if [ "$fetch_status" -eq 0 ]; then
    :
elif [ "$fetch_status" -eq 2 ]; then
    echo "[entrypoint] FATAL: the prebuilt store failed its INTEGRITY check."
    echo "[entrypoint] Refusing to fall back to fetch+ingest - that would hide this"
    echo "[entrypoint] behind a corpus roughly a tenth the size, which answers badly"
    echo "[entrypoint] rather than failing. Republish the archive, or point"
    echo "[entrypoint] VECTOR_STORE_URL / VECTOR_STORE_SHA256 at a good one."
    exit 1
else
    echo "[entrypoint] prebuilt store unavailable (exit $fetch_status) - falling back to fetch+ingest"
    echo "[entrypoint] WARNING: this builds a DIFFERENT corpus, roughly a tenth the size,"
    echo "[entrypoint] because the Internet Archive returns different books over time."
    python -m src.fetch_fao --max "${FETCH_FAO_MAX:-100}"
    python -m src.fetch_dergipark --max "${FETCH_DERGIPARK_MAX:-120}"
    python -m src.fetch_openalex --max "${FETCH_OPENALEX_MAX:-25}"
    python -m src.fetch_books --max "${FETCH_BOOKS_MAX:-250}"
    python -m src.ingest
fi

echo "[entrypoint] data/ (persisted on the volume):"
du -sh data/* 2>/dev/null || echo "[entrypoint] (data/ is empty)"

echo "[entrypoint] docs/books/ (fetched PDFs staged for ingest - NOT on the volume, resets every boot):"
du -sh docs/books/* 2>/dev/null || echo "[entrypoint] (docs/books/ is empty)"

echo "[entrypoint] docs/products/ + docs/articles/ (catalog, baked into the image at build time):"
du -sh docs/products docs/articles 2>/dev/null

exec uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
