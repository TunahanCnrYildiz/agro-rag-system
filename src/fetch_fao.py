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
