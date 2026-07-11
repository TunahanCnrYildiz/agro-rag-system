"""Shared helpers for the two PDF fetchers (Internet Archive + DergiPark).

Both fetchers stream a candidate PDF to disk and validate it the same way —
%PDF magic header plus a minimum size, written to a ``.part`` temp file first
and only promoted on success. That logic (and the crawler User-Agent) lives
here once instead of being duplicated across ``fetch_books.py`` and
``fetch_dergipark.py``. Each fetcher keeps its own source-specific URL building
and rate-limit handling.
"""

from __future__ import annotations

from pathlib import Path

import requests

USER_AGENT = "AgroBotanyBot/0.1 (+https://ekolojiktarim.com.tr/)"


def pdf_session(accept_language: str | None = None) -> requests.Session:
    """A requests session carrying the crawler's User-Agent (and an optional
    Accept-Language header)."""
    session = requests.Session()
    headers = {"User-Agent": USER_AGENT}
    if accept_language:
        headers["Accept-Language"] = accept_language
    session.headers.update(headers)
    return session


def stream_pdf_to_file(
    resp: requests.Response, dest: Path, min_bytes: int, log_prefix: str = "fetch"
) -> bool:
    """Stream an open PDF response to ``dest``, validating the %PDF header and a
    minimum size. Writes to a ``.part`` temp file and only promotes it on
    success. Always closes ``resp``. Returns True when a valid PDF was saved."""
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
                        print(f"[{log_prefix}]   ! not a real PDF, skipping")
                        break
                fh.write(chunk)
                written += len(chunk)
    finally:
        resp.close()

    if first == b"%PDF" and written >= min_bytes:
        tmp.replace(dest)
        print(f"[{log_prefix}]   + saved {dest.name} ({written // 1024} KB)")
        return True
    tmp.unlink(missing_ok=True)
    if first == b"%PDF":
        print(f"[{log_prefix}]   ! too small ({written // 1024} KB), skipping")
    return False
