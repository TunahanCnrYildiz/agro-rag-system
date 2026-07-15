"""Harvest plant-relevant English open-access PDFs from the FAO Knowledge
Repository (openknowledge.fao.org, a DSpace 7 instance).

FAO's OAI-PMH sets are structural (Publications, Meeting docs, Posters...), not
thematic, and its REST search API is WAF-blocked, so we harvest one set via
OAI-PMH ``ListRecords`` (paging through ``resumptionToken``) and filter each
record client-side: English only, must mention a plant/agronomy term, must not
be off-topic (fisheries/forestry/livestock/economics). Each ``oai_dc`` record
exposes a direct ``.pdf`` link in ``dc:identifier``; we stream that to
docs/books/ as ``fao_<id>.pdf`` alongside the dp_/oa_/ia_ corpora.

    python -m src.fetch_fao --list-sets            # show the OAI sets and exit
    python -m src.fetch_fao --dry-run --max 100    # preview, download nothing
    python -m src.fetch_fao --max 100              # harvest PDFs
    python -m src.fetch_fao --set col_20.500.14283_3   # harvest a different set
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

try:
    from .config import BOOKS_DIR
    from .pdf_fetch_utils import pdf_session, stream_pdf_to_file
except ImportError:  # pragma: no cover
    from config import BOOKS_DIR  # type: ignore
    from pdf_fetch_utils import pdf_session, stream_pdf_to_file  # type: ignore

OAI_URL = "https://openknowledge.fao.org/server/oai/request"
# FAO "Publications" collection (books + technical publications). Structural set,
# not thematic - plant subject selection is done by the filters below.
PUBLICATIONS_SET = "col_20.500.14283_2"

OAI_DELAY = 0.5      # polite delay between OAI calls
PDF_DELAY = 1.5      # polite delay between PDF downloads
OAI_TIMEOUT = 90     # a ListRecords page is generated on demand and can be slow
OAI_RETRIES = 3
MIN_BYTES = 60_000   # skip tiny stubs / cover-only fragments

# OAI-PMH + Dublin Core namespaces.
_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# A record must mention at least one plant/agronomy term in its title or
# description (FAO records rarely carry a usable dc:subject).
_PLANT_INCLUDE = re.compile(
    r"\bcrop|\bplant|\bsoil|nutrition|fertiliz|fertilis|horticultur|agronom|"
    r"irrigat|\bseed|prun|graft|greenhouse|compost|cultivat|\bpest|disease|"
    r"pollinat|propagat|orchard|vegetable|cereal|legume|\bfruit|nursery|"
    r"tillage|\bweed|harvest|germinat|rootstock",
    re.IGNORECASE,
)

# Even with a plant term present, drop clearly off-scope docs. Mirrors the
# OpenAlex fetcher's nuance: match "poultry/cattle FEED" but NOT bare
# "poultry"/"cattle", so poultry/cattle MANURE fertilizer papers survive.
_OFFTOPIC_FAO = re.compile(
    r"\bfisher|\baquacult|\bfish\b|\bshrimp|\bmollusc|\baquatic|\bmarine\b|"
    r"\bforest|\btimber|\blogging|silvicultur|"
    r"\blivestock|poultry feed|cattle feed|fish feed|feed ration|"
    r"\bruminant|\bsilage|\bfodder|\bforage|\bdairy\b|\bveterinar",
    re.IGNORECASE,
)


def _record_to_candidate(rec: ET.Element) -> tuple[str, str, str] | None:
    """Return (fao_id, pdf_url, title) for an English, plant-relevant, on-topic
    record that exposes a direct .pdf link, else None."""
    langs = [(e.text or "").strip().lower()
             for e in rec.findall(".//dc:language", _NS)]
    if not any(lang in ("en", "english") for lang in langs):
        return None

    titles = [e.text or "" for e in rec.findall(".//dc:title", _NS)]
    descs = [e.text or "" for e in rec.findall(".//dc:description", _NS)]
    blob = " ".join(titles + descs)
    if not _PLANT_INCLUDE.search(blob):
        return None
    if _OFFTOPIC_FAO.search(blob):
        return None

    ids = [(e.text or "") for e in rec.findall(".//dc:identifier", _NS)]
    pdf_url = next((u for u in ids if u.lower().endswith(".pdf")), "")
    if not pdf_url:
        return None

    header_id = rec.findtext(
        "oai:header/oai:identifier", default="", namespaces=_NS
    )
    fao_id = header_id.rsplit("/", 1)[-1].strip()
    if not fao_id:
        return None

    return fao_id, pdf_url, (titles[0] if titles else "")


def _oai(session: requests.Session, params: dict) -> ET.Element | None:
    """Call the OAI-PMH endpoint and return the parsed root element, retrying a
    few times with backoff since a full page can be slow to generate."""
    for attempt in range(1, OAI_RETRIES + 1):
        try:
            resp = session.get(OAI_URL, params=params, timeout=OAI_TIMEOUT)
            resp.raise_for_status()
            return ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as exc:
            if attempt == OAI_RETRIES:
                print(f"[fao] OAI failed after {OAI_RETRIES} tries ({params}): {exc}")
                return None
            time.sleep(2 * attempt)
    return None


def _collect_candidates(
    session: requests.Session, set_spec: str, max_books: int, max_scan: int
) -> list[tuple[str, str, str]]:
    """Page through a set's records, filtering to plant-relevant candidates.

    Stops when max_books candidates are found or max_scan records are scanned
    (the latter bounds walking a very large set). Dedupes by fao_id.
    """
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    scanned = 0
    params = {"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": set_spec}
    while len(out) < max_books and scanned < max_scan:
        root = _oai(session, params)
        if root is None:
            break
        for rec in root.findall(".//oai:record", _NS):
            scanned += 1
            cand = _record_to_candidate(rec)
            if cand and cand[0] not in seen:
                seen.add(cand[0])
                out.append(cand)
                if len(out) >= max_books:
                    break
        token = root.findtext(".//oai:resumptionToken", default="", namespaces=_NS)
        if not token:
            break
        params = {"verb": "ListRecords", "resumptionToken": token}
        time.sleep(OAI_DELAY)
    return out[:max_books]


def _is_pruned(fao_id: str) -> bool:
    """True if this doc was already moved to docs/books/_offtopic/ (don't
    re-download)."""
    offtopic = BOOKS_DIR / "_offtopic"
    return offtopic.exists() and any(offtopic.rglob(f"fao_{fao_id}.pdf"))


def list_sets(session: requests.Session) -> list[tuple[str, str]]:
    """Return (setSpec, setName) for every OAI set (single page; FAO exposes ~17)."""
    root = _oai(session, {"verb": "ListSets"})
    if root is None:
        return []
    out: list[tuple[str, str]] = []
    for s in root.findall(".//oai:set", _NS):
        spec = (s.findtext("oai:setSpec", default="", namespaces=_NS) or "").strip()
        name = (s.findtext("oai:setName", default="", namespaces=_NS) or "").strip()
        if spec:
            out.append((spec, name))
    return out


def download(session: requests.Session, url: str, dest: Path) -> bool:
    """Stream a candidate PDF to disk, validating the %PDF header + size."""
    try:
        resp = session.get(url, stream=True, timeout=120)
    except requests.RequestException as exc:
        print(f"[fao]   ! download error: {exc}")
        return False
    if resp.status_code != 200:
        print(f"[fao]   ! http {resp.status_code}, skipping")
        resp.close()
        return False
    return stream_pdf_to_file(resp, dest, MIN_BYTES, "fao")


def run(set_spec: str, max_books: int, max_scan: int, dry_run: bool) -> int:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    session = pdf_session("en")
    candidates = _collect_candidates(session, set_spec, max_books, max_scan)
    print(f"[fao] {len(candidates)} candidate(s); target {max_books}\n")

    if dry_run:
        for i, (fao_id, _url, title) in enumerate(candidates, 1):
            print(f"{i:>3}  {fao_id:>10}  {title[:60]}")
        print("\n[fao] preview only. Re-run without --dry-run to download.")
        return 0

    saved = 0
    for fao_id, url, title in candidates:
        if saved >= max_books:
            break
        dest = BOOKS_DIR / f"fao_{fao_id}.pdf"
        if dest.exists():
            print(f"[fao]   = already have {dest.name}, skipping")
            continue
        if _is_pruned(fao_id):
            print(f"[fao]   = fao_{fao_id} previously pruned, skipping")
            continue
        print(f"[fao] {title[:55]}")
        if download(session, url, dest):
            saved += 1
        time.sleep(PDF_DELAY)

    print(f"\n[fao] DONE. downloaded {saved} paper(s) into {BOOKS_DIR}")
    if saved:
        print("[fao] next: python -m src.ingest")
    return saved


def main() -> None:
    # FAO set names and document titles span many scripts (Cyrillic, Chinese,
    # Arabic, accented Latin); force UTF-8 output so printing them does not crash
    # on a legacy-codepage console (e.g. Windows cp1252).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass

    p = argparse.ArgumentParser(
        description="Harvest plant-relevant open-access PDFs from the FAO "
                    "Knowledge Repository."
    )
    p.add_argument("--max", type=int, default=100, help="Max PDFs to download.")
    p.add_argument("--max-scan", type=int, default=8000,
                   help="Max OAI records to scan before stopping.")
    p.add_argument("--set", default=PUBLICATIONS_SET,
                   help="OAI setSpec to harvest (default: Publications).")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview candidates without downloading.")
    p.add_argument("--list-sets", action="store_true",
                   help="List OAI sets and exit.")
    args = p.parse_args()

    if args.list_sets:
        for spec, name in list_sets(pdf_session("en")):
            print(f"  {spec}  {name}")
        return

    run(set_spec=args.set, max_books=args.max, max_scan=args.max_scan,
        dry_run=args.dry_run)


if __name__ == "__main__":
    main()
