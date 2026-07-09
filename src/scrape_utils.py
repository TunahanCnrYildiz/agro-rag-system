"""Shared HTTP scraping helpers for the ekolojiktarim.com.tr crawlers.

Both the product scraper (src/scraper.py) and the article scraper
(src/articles_scraper.py) crawl the same site, so the crawl constants, session
setup, polite fetch, and meta-description extraction live here once instead of
being duplicated (and drifting) across the two modules.
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.ekolojiktarim.com.tr/"
USER_AGENT = (
    "Mozilla/5.0 (compatible; AgroBotanyBot/0.1; +https://ekolojiktarim.com.tr/)"
)
REQUEST_DELAY_SECONDS = 1.0  # polite crawl delay between requests
REQUEST_TIMEOUT = 15


def make_session() -> requests.Session:
    """A requests session with the crawler's User-Agent and language headers."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "tr,en"})
    return session


def fetch(
    session: requests.Session, url: str, log_prefix: str = "scrape"
) -> BeautifulSoup | None:
    """GET ``url`` and return parsed soup, or None on any request error.

    ``log_prefix`` tags the failure line so each caller keeps its own label
    (e.g. "scraper" / "articles").
    """
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[{log_prefix}] request failed for {url}: {exc}")
        return None
    return BeautifulSoup(resp.text, "html.parser")


def extract_meta_description(soup: BeautifulSoup) -> str:
    """Return the page's meta description (name="description" or og:description),
    stripped, or "" if neither is present."""
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", property="og:description"
    )
    if meta_desc and meta_desc.get("content"):
        return meta_desc["content"].strip()
    return ""
