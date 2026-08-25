"""Backfill year/era metadata onto existing store chunks WITHOUT re-embedding.

    python scripts/backfill_years.py            # DRY-RUN: histogram only
    python scripts/backfill_years.py --apply    # patch metadata in place

Uses the SAME derivation as ingest (`src.ingest.derive_source_year` +
`_first_pages_text`) so a later re-ingest can never disagree. `collection.update`
touches metadata only; vectors are preserved. Idempotent. Adds fields, deletes
nothing.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts._console import use_utf8_console  # noqa: E402
from src import ingest  # noqa: E402
from src.config import BOOKS_DIR  # noqa: E402

APPLY = "--apply" in sys.argv
PAGE = 5000


def _make_year_of(missing: set):
    """source -> (year|None, era), cached per source; records PDF-missing sources."""
    cache: dict[str, tuple[int | None, str]] = {}

    def year_of(name: str) -> tuple[int | None, str]:
        if name in cache:
            return cache[name]
        hits = list(BOOKS_DIR.rglob(name))
        if not hits:
            missing.add(name)
            result = (None, "unknown")  # PDF gone; can't derive
        else:
            year, _conf = ingest.derive_source_year(
                name, ingest._first_pages_text(hits[0])
            )
            result = (year, ingest._year_to_era(year))
        cache[name] = result
        return result

    return year_of


def main() -> None:
    use_utf8_console()
    store = ingest.get_vector_store()
    col = store._collection
    total = col.count()
    print(f"{'APPLY' if APPLY else 'DRY-RUN'}: {total} chunks in store\n")

    missing: set[str] = set()
    year_of = _make_year_of(missing)
    era_hist = Counter()
    updated = 0
    offset = 0
    while offset < total:
        got = col.get(include=["metadatas"], limit=PAGE, offset=offset)
        records = [(cid, meta.get("source", "?"), meta)
                   for cid, meta in zip(got["ids"], got["metadatas"])]
        for _cid, src, _meta in records:
            era_hist[year_of(src)[1]] += 1
        ids, metas = ingest.build_backfill_metadata(records, year_of)
        if APPLY and ids:
            col.update(ids=ids, metadatas=metas)
            updated += len(ids)
        offset += PAGE

    print("era histogram (by chunk):")
    for era in ("pre-1950", "1950-1989", "1990-2009", "2010+", "unknown"):
        n = era_hist.get(era, 0)
        print(f"  {era:12s} {n:6d}  ({100*n/total:.1f}%)")
    print(f"\nsources with no PDF found (tagged unknown): {len(missing)}")
    for m in sorted(missing):
        print(f"  ! {m}")
    if APPLY:
        print(f"\n[apply] updated metadata on {updated} chunks (vectors untouched)")
    else:
        print("\n(dry-run — nothing changed; re-run with --apply)")


if __name__ == "__main__":
    main()
