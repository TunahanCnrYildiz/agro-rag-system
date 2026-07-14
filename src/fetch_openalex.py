"""Harvest English open-access PDFs for tropical/global gap crops from OpenAlex.

OpenAlex (openalex.org) is a free scholarly index. We query its /works endpoint
per curated gap crop (open-access + English), take well-cited candidates that
expose an OA PDF URL, drop off-topic (livestock/economics) ones by title, and
stream each PDF into docs/books/ as ``oa_<OpenAlexID>.pdf`` alongside the
DergiPark (dp_) and Internet Archive (ia_) corpora.

    python -m src.fetch_openalex --list-crops
    python -m src.fetch_openalex --dry-run --max 25 --per-crop 4
    python -m src.fetch_openalex --max 25 --per-crop 4
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

try:
    from .config import BOOKS_DIR
    from .pdf_fetch_utils import pdf_session, stream_pdf_to_file
    from .fetch_dergipark import _OFFTOPIC_REC
except ImportError:  # pragma: no cover
    from config import BOOKS_DIR  # type: ignore
    from pdf_fetch_utils import pdf_session, stream_pdf_to_file  # type: ignore
    from fetch_dergipark import _OFFTOPIC_REC  # type: ignore

OPENALEX_URL = "https://api.openalex.org/works"
POLITE_MAILTO = "agrobotanybot@ekolojiktarim.com.tr"  # OpenAlex polite pool

OA_DELAY = 0.3     # between API calls
OA_TIMEOUT = 30
OA_RETRIES = 3
PDF_DELAY = 1.5    # between PDF downloads
MIN_BYTES = 60_000  # skip tiny stubs

# Curated tropical/global gap crops under-covered by the TR/US corpus.
CROP_TERMS = [
    "cassava", "plantain", "sorghum", "pearl millet", "finger millet",
    "cowpea", "yam", "taro", "sweet potato", "rice", "teff",
    "pigeon pea", "groundnut", "banana",
]


def _work_to_candidate(work: dict) -> tuple[str, str, str, str] | None:
    """Return (oa_id, pdf_url, doi, title) for an English OA work with a PDF,
    or None (non-English, no OA PDF, bad id, or off-topic title)."""
    if (work.get("language") or "") != "en":
        return None
    loc = work.get("best_oa_location") or {}
    pdf_url = loc.get("pdf_url") or (work.get("open_access") or {}).get("oa_url")
    if not pdf_url:
        return None
    oa_id = (work.get("id") or "").rsplit("/", 1)[-1]
    if not oa_id.startswith("W"):
        return None
    title = work.get("title") or work.get("display_name") or ""
    if _OFFTOPIC_REC.search(title):
        return None
    return oa_id, pdf_url, work.get("doi") or "", title


def _oa_get(session: requests.Session, params: dict) -> dict | None:
    """Call the OpenAlex /works endpoint (with mailto) and return parsed JSON,
    retrying with backoff on 429 / 5xx."""
    query = {**params, "mailto": POLITE_MAILTO}
    for attempt in range(1, OA_RETRIES + 1):
        try:
            resp = session.get(OPENALEX_URL, params=query, timeout=OA_TIMEOUT)
            if resp.status_code in (429, 500, 502, 503):
                raise requests.RequestException(f"http {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == OA_RETRIES:
                print(f"[openalex] API failed ({params.get('filter', '')}): {exc}")
                return None
            time.sleep(2 * attempt)
    return None


def search_crop(
    session: requests.Session, crop: str, max_per_crop: int
) -> list[tuple[str, str, str, str]]:
    """Return up to max_per_crop (oa_id, pdf_url, doi, title) candidates for a
    crop: English, open-access, PDF-bearing, on-topic; well-cited first."""
    out: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    cursor = "*"
    flt = f"title_and_abstract.search:{crop},open_access.is_oa:true,language:en"
    while len(out) < max_per_crop and cursor:
        data = _oa_get(session, {
            "filter": flt,
            "sort": "cited_by_count:desc",
            "per-page": 50,
            "cursor": cursor,
        })
        if not data:
            break
        for work in data.get("results", []):
            cand = _work_to_candidate(work)
            if cand and cand[0] not in seen:
                seen.add(cand[0])
                out.append(cand)
        cursor = (data.get("meta") or {}).get("next_cursor")
        time.sleep(OA_DELAY)
    return out[:max_per_crop]
