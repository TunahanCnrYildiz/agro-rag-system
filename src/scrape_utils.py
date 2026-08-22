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


# Where the page's own furniture starts. One product page (HIGRO 8 MN) renders
# the related-products rail inside its tab panel; everything from here on
# belongs to the page, not to the product being described.
_FURNITURE = ("Ürün Tescil Belgesi", "Benzer Ürünler", "Hızlı Menü")


def extract_tab_panels(soup: BeautifulSoup) -> dict[str, str]:
    """Elementor nested-tab panels, keyed by their tab label.

    The panels are rendered server-side, so no browser is needed: a button
    `#e-n-tab-title-N` pairs with a div `#e-n-tab-content-N` by the shared
    numeric suffix. A button whose panel is missing is skipped rather than
    guessed at, and a page with no tabs yields an empty mapping - a layout
    change must show up as "found nothing", never as an exception.
    """
    panels: dict[str, str] = {}
    for button in soup.select("button.e-n-tab-title"):
        button_id = button.get("id") or ""
        suffix = button_id.rsplit("-", 1)[-1]
        if not suffix:
            continue
        panel = soup.select_one(f"#e-n-tab-content-{suffix}")
        if panel is None:
            continue
        label = " ".join(button.get_text(" ", strip=True).split())
        text = " ".join(panel.get_text(" ", strip=True).split())
        for marker in _FURNITURE:
            cut = text.find(marker)
            if cut != -1:
                text = text[:cut]
        panels[label] = text.strip()
    return panels
