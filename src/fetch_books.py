"""Bulk-download open-access / public-domain botany & plant-nutrition books
from the Internet Archive into ``docs/books/``.

Reliability first
-----------------
The user needs an *academically / professionally trustworthy* corpus, not a
random pile of PDFs. So instead of a broad popularity search (which surfaces
folk herbals, astrology "medicine", dictionaries and town histories), this tool
pulls from a curated set of AUTHORITATIVE sources:

  * USDA (U.S. Department of Agriculture) publications  — public-domain, peer/gov reviewed
  * Agricultural Experiment Station bulletins           — university research stations
  * Classic academic botany / plant-physiology texts    — with unreliable subjects excluded

Only freely downloadable, non-restricted items are fetched (borrow-only / DRM
items are skipped) and each PDF is validated (real ``%PDF`` header + minimum
size) before it is kept.

Usage::

    python -m src.fetch_books --dry-run --max 40    # preview quality, download nothing
    python -m src.fetch_books --max 250             # download up to 250 books
    python -m src.fetch_books --source usda --max 100
    python -m src.fetch_books --list-sources
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

try:
    from .config import BOOKS_DIR
except ImportError:  # pragma: no cover
    from config import BOOKS_DIR  # type: ignore

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{name}"
USER_AGENT = "AgroBotanyBot/0.1 (+https://ekolojiktarim.com.tr/)"

# Common tail appended to every curated query: only real, downloadable PDFs,
# never borrow-only/restricted items, and never unreliable/off-topic subjects.
_UNRELIABLE = (
    "medicinal OR medicine OR herbal OR herbals OR therapeutics OR "
    "pharmacology OR homeopathy OR homoeopathy OR astrology OR occult OR "
    "alchemy OR folklore OR divination OR drug OR drugs"
)
_OFFTOPIC = (
    "dictionary OR dictionaries OR language OR biography OR genealogy OR "
    "fiction OR poetry OR religion OR cookery OR travel"
)
# Title-level noise: hydrology/fisheries/administrative docs that match "soil"
# or "water" loosely, plus the highly repetitive USDA "plant inventory" series.
_NOISE_TITLES = (
    'pond OR ponds OR fish OR fishing OR flood OR "flood plain" OR watershed OR '
    'river OR climate OR rainfall OR "wind erosion" OR directory OR "plant inventory"'
)
_COMMON = (
    "AND mediatype:texts AND format:(PDF) "
    "AND -collection:inlibrary AND -access-restricted-item:true "
    f"AND -subject:({_UNRELIABLE}) AND -subject:({_OFFTOPIC}) "
    f"AND -title:({_UNRELIABLE}) AND -title:({_NOISE_TITLES})"
)

# Curated authoritative sources. Each maps a short name to an Archive.org query.
CURATED_SOURCES: dict[str, str] = {
    # USDA publications on soil health, fertility, and plant nutrition.
    "usda_soil": (
        'publisher:("United States. Department of Agriculture") '
        'AND (soil OR fertility OR fertilizer OR fertilizers OR manure OR '
        'compost OR nitrogen OR phosphorus OR potassium OR "plant nutrition" '
        'OR lime OR humus) ' + _COMMON
    ),
    # USDA publications on crops, soil-building plants, and plant growth.
    "usda_crops": (
        'publisher:("United States. Department of Agriculture") '
        'AND (crop OR crops OR legume OR legumes OR "green manure" OR '
        '"cover crop" OR "plant growth" OR seed OR germination OR pasture OR '
        'forage OR rotation) ' + _COMMON
    ),
    # Agricultural experiment station research bulletins.
    "experiment_station": (
        'title:("experiment station") '
        'AND (soil OR fertility OR fertilizer OR crop OR nitrogen OR plant OR '
        'nutrition OR manure) ' + _COMMON
    ),
    # Classic academic botany / plant-physiology / soil-science texts.
    "botany_texts": (
        'subject:("plant physiology" OR "plant anatomy" OR "plant morphology" '
        'OR "soil science" OR "soil fertility" OR agronomy OR "plant nutrition" '
        'OR "vegetable physiology" OR "economic botany") ' + _COMMON
    ),
}

SKIP_TOKENS = ("_index", "_contents", "_advertis", "_cover", "_toc")
MIN_BYTES = 150_000  # skip tiny stubs / single-page fragments


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def search_items(session: requests.Session, query: str, rows: int) -> list[dict]:
    """Return candidate items (identifier + title + year + downloads)."""
    resp = session.get(
        SEARCH_URL,
        params={
            "q": query,
            "fl[]": ["identifier", "title", "year", "downloads"],
            "sort[]": "downloads desc",  # popular-within-source => better scans
            "rows": str(rows),
            "output": "json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    docs = resp.json().get("response", {}).get("docs", [])
    return [d for d in docs if "identifier" in d]


def _title(item: dict) -> str:
    t = item.get("title", "(untitled)")
    return t[0] if isinstance(t, list) else t


def _resolve_sources(source: str | None) -> list[tuple[str, str]]:
    if source:
        if source not in CURATED_SOURCES:
            raise SystemExit(
                f"unknown source '{source}'. Options: {', '.join(CURATED_SOURCES)}"
            )
        return [(source, CURATED_SOURCES[source])]
    return list(CURATED_SOURCES.items())


def _collect_candidates(
    session: requests.Session, sources: list[tuple[str, str]], per_source: int
) -> list[tuple[str, dict]]:
    """Gather (source_name, item) pairs across sources, deduped by identifier."""
    seen: set[str] = set()
    out: list[tuple[str, dict]] = []
    for name, query in sources:
        items = search_items(session, query, rows=per_source)
        kept = 0
        for it in items:
            ident = it["identifier"]
            if ident in seen:
                continue
            seen.add(ident)
            out.append((name, it))
            kept += 1
        print(f"[fetch] source '{name}': {kept} unique candidates")
    return out


def preview(session: requests.Session, source: str | None, max_books: int) -> None:
    """Dry-run: list candidate titles/years per source, download nothing."""
    sources = _resolve_sources(source)
    per_source = max(12, (max_books * 3) // len(sources))
    candidates = _collect_candidates(session, sources, per_source)
    print(f"\n{'#':>3}  {'source':<18} {'year':<6} {'downloads':>9}  title")
    print("-" * 92)
    for i, (name, it) in enumerate(candidates[: max_books], 1):
        print(f"{i:>3}  {name:<18} {str(it.get('year','?')):<6} "
              f"{it.get('downloads', 0):>9}  {_title(it)[:44]}")
    print(f"\n[fetch] preview only ({min(len(candidates), max_books)} shown, "
          f"{len(candidates)} total candidates). Re-run without --dry-run to download.")


def pick_pdf(session: requests.Session, identifier: str) -> str | None:
    """Choose the best downloadable PDF file name for an item, or None."""
    resp = session.get(METADATA_URL.format(identifier=identifier), timeout=30)
    if resp.status_code != 200:
        return None
    files = resp.json().get("files", [])
    candidates = []
    for f in files:
        low = f.get("name", "").lower()
        if not low.endswith(".pdf"):
            continue
        if "_encrypted" in low or "_bw" in low:
            continue
        if any(tok in low for tok in SKIP_TOKENS):
            continue
        candidates.append((int(f.get("size", 0) or 0), f["name"]))
    if not candidates:
        return None
    candidates.sort(reverse=True)  # largest PDF = full text, not a fragment
    return candidates[0][1]


def download(session: requests.Session, identifier: str, name: str, dest: Path) -> bool:
    """Stream a PDF to disk; validate header + size. Returns True on success."""
    url = DOWNLOAD_URL.format(identifier=identifier, name=name)
    try:
        resp = session.get(url, stream=True, timeout=180)
    except requests.RequestException as exc:
        print(f"[fetch]   ! request error: {exc}")
        return False
    if resp.status_code != 200:
        print(f"[fetch]   ! http {resp.status_code}, skipping")
        return False

    tmp = dest.with_suffix(".part")
    written = 0
    first = b""
    try:
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                if not first:
                    first = chunk[:4]
                    if first != b"%PDF":
                        print("[fetch]   ! not a real PDF, skipping")
                        break
                fh.write(chunk)
                written += len(chunk)
    finally:
        resp.close()

    if first == b"%PDF" and written >= MIN_BYTES:
        tmp.replace(dest)
        print(f"[fetch]   + saved {dest.name} ({written // 1024} KB)")
        return True
    tmp.unlink(missing_ok=True)
    if first == b"%PDF":
        print(f"[fetch]   ! too small ({written // 1024} KB), skipping")
    return False


def run(source: str | None, max_books: int, delay: float) -> int:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    session = _session()
    sources = _resolve_sources(source)

    # Over-fetch candidates since some are filtered out during download.
    per_source = max(20, (max_books * 3) // len(sources))
    candidates = _collect_candidates(session, sources, per_source)
    print(f"[fetch] {len(candidates)} total candidates; downloading up to {max_books}\n")

    saved = 0
    for name, it in candidates:
        if saved >= max_books:
            break
        ident = it["identifier"]
        dest = BOOKS_DIR / f"ia_{ident}.pdf"
        if dest.exists():
            print(f"[fetch]   = already have {dest.name}, skipping")
            continue
        pdf_name = pick_pdf(session, ident)
        if not pdf_name:
            continue
        print(f"[fetch] [{name}] {_title(it)[:55]}")
        if download(session, ident, pdf_name, dest):
            saved += 1
        time.sleep(delay)  # be polite to archive.org

    print(f"\n[fetch] DONE. downloaded {saved} book(s) into {BOOKS_DIR}")
    if saved:
        print("[fetch] next: python -m src.ingest --reset")
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download open-access botany books from the Internet Archive."
    )
    parser.add_argument("--max", type=int, default=25, help="Max books to keep.")
    parser.add_argument("--source", default=None,
                        help="Limit to one curated source (see --list-sources).")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between items (s).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview candidate titles without downloading.")
    parser.add_argument("--list-sources", action="store_true",
                        help="List curated source names and exit.")
    args = parser.parse_args()

    if args.list_sources:
        print("Curated sources:")
        for name in CURATED_SOURCES:
            print(f"  - {name}")
        return
    if args.dry_run:
        preview(_session(), args.source, args.max)
    else:
        run(source=args.source, max_books=args.max, delay=args.delay)


if __name__ == "__main__":
    main()
