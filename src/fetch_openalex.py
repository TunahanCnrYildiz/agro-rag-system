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
