"""Bulk-download open-access / public-domain botany & plant-nutrition books
from the Internet Archive into ``docs/books/``.

Only freely downloadable, non-restricted items are fetched (borrow-only /
DRM-encrypted lending items are excluded), so this stays within the Archive's
terms and copyright. Downloaded PDFs are validated (real ``%PDF`` header + a
minimum size) and low-value fragments (indexes, tables of contents, adverts)
are skipped.

Usage::

    python -m src.fetch_books                 # default plant-nutrition query, 25 books
    python -m src.fetch_books --max 100       # grab more
    python -m src.fetch_books --query "subject:(mycorrhiza)"   # custom query

After downloading, run ``python -m src.ingest --reset`` to embed everything.
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

# Focused on the plant / soil / nutrition side of agriculture. Excludes
# borrow-only lending items and access-restricted scans so every hit is
# genuinely downloadable.
DEFAULT_QUERY = (
    'subject:(botany OR "plant nutrition" OR "plant physiology" OR '
    '"soil fertility" OR fertilizers OR horticulture OR "organic farming" OR '
    'agronomy OR "plant pathology") '
    'AND mediatype:texts AND format:(PDF) '
    'AND -collection:inlibrary AND -access-restricted-item:true'
)

# Filenames / titles containing these are usually low-value fragments.
SKIP_TOKENS = ("_index", "_contents", "_advertis", "_cover", "_toc")
MIN_BYTES = 150_000  # skip tiny stubs / single-page fragments


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def search_identifiers(session: requests.Session, query: str, rows: int) -> list[str]:
    """Return candidate item identifiers for the query."""
    resp = session.get(
        SEARCH_URL,
        params={
            "q": query,
            "fl[]": ["identifier"],
            "sort[]": "downloads desc",  # popular first => better quality
            "rows": str(rows),
            "output": "json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    docs = data.get("response", {}).get("docs", [])
    print(f"[fetch] query matched {data['response'].get('numFound')} items; "
          f"scanning top {len(docs)}")
    return [d["identifier"] for d in docs if "identifier" in d]


def pick_pdf(session: requests.Session, identifier: str) -> str | None:
    """Choose the best downloadable PDF file name for an item, or None."""
    resp = session.get(METADATA_URL.format(identifier=identifier), timeout=30)
    if resp.status_code != 200:
        return None
    files = resp.json().get("files", [])
    candidates = []
    for f in files:
        name = f.get("name", "")
        low = name.lower()
        if not low.endswith(".pdf"):
            continue
        if "_encrypted" in low or "_bw" in low:
            continue
        if any(tok in low for tok in SKIP_TOKENS):
            continue
        size = int(f.get("size", 0) or 0)
        candidates.append((size, name))
    if not candidates:
        return None
    # Prefer the largest PDF (usually the full text, not a fragment).
    candidates.sort(reverse=True)
    return candidates[0][1]


def download(session: requests.Session, identifier: str, name: str, dest: Path) -> bool:
    """Stream a PDF to disk; validate header + size. Returns True on success."""
    url = DOWNLOAD_URL.format(identifier=identifier, name=name)
    try:
        resp = session.get(url, stream=True, timeout=120)
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
    # Clean up rejected download.
    tmp.unlink(missing_ok=True)
    if first == b"%PDF":
        print(f"[fetch]   ! too small ({written // 1024} KB), skipping")
    return False


def run(query: str, max_books: int, delay: float) -> int:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    session = _session()

    # Over-fetch identifiers since some will be filtered out.
    identifiers = search_identifiers(session, query, rows=max_books * 3)

    saved = 0
    for ident in identifiers:
        if saved >= max_books:
            break
        dest = BOOKS_DIR / f"ia_{ident}.pdf"
        if dest.exists():
            print(f"[fetch]   = already have {dest.name}, skipping")
            continue
        pdf_name = pick_pdf(session, ident)
        if not pdf_name:
            continue
        print(f"[fetch] {ident}")
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
    parser.add_argument("--query", default=DEFAULT_QUERY, help="Archive.org query.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between items (s).")
    args = parser.parse_args()
    run(query=args.query, max_books=args.max, delay=args.delay)


if __name__ == "__main__":
    main()
