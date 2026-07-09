"""Download Turkish agriculture papers from DergiPark into docs/books/.

DergiPark (dergipark.org.tr) is Turkey's open-access academic journal platform.
Its ``/search`` endpoint is disallowed by robots.txt, so instead we harvest via
the sanctioned **OAI-PMH** interface (allowed): discover agriculture journals
from ListSets, list their article records, then follow each article's public
landing page to its ``/download/article-file/`` PDF. This adds Turkey-sourced,
peer-reviewed agronomy/soil/plant-nutrition content alongside the (mostly
English) Internet Archive corpus from ``fetch_books.py``.

    python -m src.fetch_dergipark --list-sets          # show matched journals
    python -m src.fetch_dergipark --dry-run --max 40   # preview, download nothing
    python -m src.fetch_dergipark --max 120            # harvest PDFs
    python -m src.fetch_dergipark --set akdenizfderg   # limit to one journal
"""

from __future__ import annotations

import argparse
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

try:
    from .config import BOOKS_DIR
except ImportError:  # pragma: no cover
    from config import BOOKS_DIR  # type: ignore

BASE = "https://dergipark.org.tr"
OAI_URL = f"{BASE}/api/public/oai/"
USER_AGENT = "AgroBotanyBot/0.1 (+https://ekolojiktarim.com.tr/)"

OAI_DELAY = 0.5   # polite delay between OAI API calls
PDF_DELAY = 1.0   # polite delay between PDF downloads
MIN_BYTES = 60_000  # skip tiny stubs / cover-only fragments

# OAI-PMH XML namespaces.
_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# A journal is kept when its name matches one of these (plant/soil-side
# agriculture faculties and agronomy journals).
_AGRI_SET_TERMS = re.compile(
    r"ziraat|tar[ıi]m|agric|agronom|bah[çc]e|bitki|toprak|horticultur|"
    r"field crop|plant|soil",
    re.IGNORECASE,
)
# Within those journals, drop records clearly outside our plant-nutrition /
# soil / botany scope (animal science, fisheries, pure economics, food eng.).
_OFFTOPIC_REC = re.compile(
    r"hayvan|veteriner|zootekni|bal[ıi]k|su [üu]r[üu]nleri|fisher|aquacult|"
    r"ekonomi|pazarlama|market|dairy|poultry|meat",
    re.IGNORECASE,
)

_ARTICLE_URL = re.compile(r"/pub/[^/]+/article/(\d+)")
_DOWNLOAD_LINK = re.compile(r"/[a-z]{2}/download/article-file/\d+")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "tr,en"})
    return s


def _oai(session: requests.Session, params: dict) -> ET.Element | None:
    """Call the OAI-PMH endpoint and return the parsed root element."""
    try:
        resp = session.get(OAI_URL, params=params, timeout=30)
        resp.raise_for_status()
        return ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError) as exc:
        print(f"[dergipark] OAI request failed ({params}): {exc}")
        return None


# --------------------------------------------------------------------------- #
# Journal (set) discovery
# --------------------------------------------------------------------------- #
def discover_sets(session: requests.Session, max_pages: int) -> list[tuple[str, str]]:
    """Page through ListSets and return (setSpec, name) for agriculture journals."""
    out: list[tuple[str, str]] = []
    params = {"verb": "ListSets"}
    for _ in range(max_pages):
        root = _oai(session, params)
        if root is None:
            break
        for s in root.findall(".//oai:set", _NS):
            spec = (s.findtext("oai:setSpec", default="", namespaces=_NS) or "").strip()
            name = (s.findtext("oai:setName", default="", namespaces=_NS) or "").strip()
            if spec and _AGRI_SET_TERMS.search(name):
                out.append((spec, name))
        token = root.findtext(".//oai:resumptionToken", default="", namespaces=_NS)
        if not token:
            break
        params = {"verb": "ListSets", "resumptionToken": token}
        time.sleep(OAI_DELAY)
    # Dedupe, keep order.
    seen: set[str] = set()
    uniq = [(s, n) for s, n in out if not (s in seen or seen.add(s))]
    return uniq


# --------------------------------------------------------------------------- #
# Record (article) listing
# --------------------------------------------------------------------------- #
def _article_from_record(rec: ET.Element) -> tuple[str, str] | None:
    """Return (article_id, landing_url) for a record, filtering off-topic ones."""
    ids = [e.text or "" for e in rec.findall(".//dc:identifier", _NS)]
    landing = next((u for u in ids if _ARTICLE_URL.search(u)), "")
    m = _ARTICLE_URL.search(landing)
    if not m:
        return None
    blob = " ".join(
        (e.text or "")
        for tag in ("dc:title", "dc:subject")
        for e in rec.findall(f".//{tag}", _NS)
    )
    if _OFFTOPIC_REC.search(blob):
        return None
    return m.group(1), landing


def list_articles(
    session: requests.Session, set_spec: str, max_per_set: int
) -> list[tuple[str, str]]:
    """List (article_id, landing_url) for one journal, following resumption."""
    out: list[tuple[str, str]] = []
    params = {"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": set_spec}
    while len(out) < max_per_set:
        root = _oai(session, params)
        if root is None:
            break
        for rec in root.findall(".//oai:record", _NS):
            got = _article_from_record(rec)
            if got:
                out.append(got)
        token = root.findtext(".//oai:resumptionToken", default="", namespaces=_NS)
        if not token:
            break
        params = {"verb": "ListRecords", "resumptionToken": token}
        time.sleep(OAI_DELAY)
    return out[:max_per_set]


# --------------------------------------------------------------------------- #
# PDF download
# --------------------------------------------------------------------------- #
def _pdf_link(session: requests.Session, landing_url: str) -> str | None:
    """Fetch an article landing page and return its PDF download URL, or None."""
    try:
        resp = session.get(landing_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[dergipark]   ! landing fetch failed: {exc}")
        return None
    m = _DOWNLOAD_LINK.search(resp.text)
    return f"{BASE}{m.group(0)}" if m else None


def download(session: requests.Session, url: str, dest: Path) -> bool:
    """Stream a PDF to disk; validate %PDF header + size. Returns True on success."""
    try:
        resp = session.get(url, stream=True, timeout=120)
    except requests.RequestException as exc:
        print(f"[dergipark]   ! download error: {exc}")
        return False
    if resp.status_code != 200:
        print(f"[dergipark]   ! http {resp.status_code}, skipping")
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
                        print("[dergipark]   ! not a real PDF, skipping")
                        break
                fh.write(chunk)
                written += len(chunk)
    finally:
        resp.close()

    if first == b"%PDF" and written >= MIN_BYTES:
        tmp.replace(dest)
        print(f"[dergipark]   + saved {dest.name} ({written // 1024} KB)")
        return True
    tmp.unlink(missing_ok=True)
    if first == b"%PDF":
        print(f"[dergipark]   ! too small ({written // 1024} KB), skipping")
    return False


# --------------------------------------------------------------------------- #
# Drivers
# --------------------------------------------------------------------------- #
def _collect_candidates(
    session: requests.Session, sets: list[tuple[str, str]], per_journal: int
) -> list[tuple[str, str]]:
    """Gather (article_id, landing_url) across journals, deduped by id."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for spec, name in sets:
        arts = list_articles(session, spec, per_journal)
        kept = 0
        for aid, url in arts:
            if aid in seen:
                continue
            seen.add(aid)
            out.append((aid, url))
            kept += 1
        print(f"[dergipark] journal '{spec}' ({name[:40]}): {kept} articles")
        time.sleep(OAI_DELAY)
    return out


def run(
    set_spec: str | None, max_books: int, per_journal: int,
    set_pages: int, dry_run: bool,
) -> int:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    session = _session()

    if set_spec:
        sets = [(set_spec, set_spec)]
    else:
        print("[dergipark] discovering agriculture journals via OAI ListSets ...")
        sets = discover_sets(session, set_pages)
        print(f"[dergipark] matched {len(sets)} agriculture journal(s)")

    candidates = _collect_candidates(session, sets, per_journal)
    print(f"[dergipark] {len(candidates)} candidate articles; target {max_books}\n")

    if dry_run:
        for i, (aid, url) in enumerate(candidates[:max_books], 1):
            print(f"{i:>3}  {aid:>8}  {url}")
        print(f"\n[dergipark] preview only ({min(len(candidates), max_books)} shown). "
              "Re-run without --dry-run to download.")
        return 0

    saved = 0
    for aid, url in candidates:
        if saved >= max_books:
            break
        dest = BOOKS_DIR / f"dp_{aid}.pdf"
        if dest.exists():
            print(f"[dergipark]   = already have {dest.name}, skipping")
            continue
        pdf = _pdf_link(session, url)
        if not pdf:
            continue
        print(f"[dergipark] article {aid}")
        if download(session, pdf, dest):
            saved += 1
        time.sleep(PDF_DELAY)

    print(f"\n[dergipark] DONE. downloaded {saved} paper(s) into {BOOKS_DIR}")
    if saved:
        print("[dergipark] next: python -m src.ingest")
    return saved


def main() -> None:
    p = argparse.ArgumentParser(
        description="Harvest Turkish agriculture papers from DergiPark (OAI-PMH)."
    )
    p.add_argument("--max", type=int, default=80, help="Max PDFs to download.")
    p.add_argument("--per-journal", type=int, default=25,
                   help="Max articles pulled per journal.")
    p.add_argument("--set", default=None,
                   help="Limit to one journal setSpec (e.g. akdenizfderg).")
    p.add_argument("--set-pages", type=int, default=60,
                   help="Max ListSets pages to scan during discovery.")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview candidate articles without downloading.")
    p.add_argument("--list-sets", action="store_true",
                   help="List matched agriculture journals and exit.")
    args = p.parse_args()

    if args.list_sets:
        session = _session()
        sets = discover_sets(session, args.set_pages)
        print(f"[dergipark] {len(sets)} agriculture journal(s):")
        for spec, name in sets:
            print(f"  {spec:<24} {name}")
        return

    run(
        set_spec=args.set,
        max_books=args.max,
        per_journal=args.per_journal,
        set_pages=args.set_pages,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
