"""Product scraper for ekolojiktarim.com.tr.

Crawls the storefront, extracts product name / description / category / URL,
and writes a structured JSON catalog to ``docs/products/products.json``.

Design notes
------------
* The public site structure can change or rate-limit anonymous crawlers, so
  the scraper is defensive: it tries several common selectors, honours a
  polite delay, and — critically — falls back to a curated MOCK catalog when
  the network is unavailable or no products are found. This keeps the rest of
  the pipeline (ingest / engine / API) fully runnable offline.

Run directly::

    python -m src.scraper            # real crawl, mock fallback on failure
    python -m src.scraper --mock     # force the mock catalog
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:  # allow both "python -m src.scraper" and "python src/scraper.py"
    from .config import PRODUCTS_JSON, PRODUCTS_DIR
except ImportError:  # pragma: no cover
    from config import PRODUCTS_JSON, PRODUCTS_DIR  # type: ignore

BASE_URL = "https://www.ekolojiktarim.com.tr/"
USER_AGENT = (
    "Mozilla/5.0 (compatible; AgroBotanyBot/0.1; +https://ekolojiktarim.com.tr/)"
)
REQUEST_DELAY_SECONDS = 1.0  # polite crawl delay
REQUEST_TIMEOUT = 15


@dataclass
class Product:
    """A single catalog entry. Metadata schema required by the spec."""

    product_name: str
    description: str
    category: str
    source_url: str


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "tr,en"})
    return session


def _fetch(session: requests.Session, url: str) -> BeautifulSoup | None:
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[scraper] request failed for {url}: {exc}")
        return None
    return BeautifulSoup(resp.text, "html.parser")


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _same_site(url: str) -> bool:
    return urlparse(url).netloc.endswith("ekolojiktarim.com.tr")


def _discover_product_links(soup: BeautifulSoup, base: str) -> set[str]:
    """Heuristically collect links that look like product detail pages."""
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"])
        if not _same_site(href):
            continue
        path = urlparse(href).path.lower()
        # Common e-commerce URL hints; kept broad on purpose.
        if any(tok in path for tok in ("urun", "product", "-p-", "/p/")):
            links.add(href.split("#")[0])
    return links


def _parse_product_page(soup: BeautifulSoup, url: str) -> Product | None:
    """Extract fields from a product detail page using tolerant selectors."""
    # Name: prefer <h1>, then og:title, then <title>.
    name = None
    if soup.h1 and soup.h1.get_text(strip=True):
        name = soup.h1.get_text(strip=True)
    if not name:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            name = og["content"].strip()
    if not name and soup.title:
        name = soup.title.get_text(strip=True)
    if not name:
        return None

    # Description: meta description / og:description, else first sizeable <p>.
    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", property="og:description"
    )
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()
    if not description:
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 40:
                description = text
                break

    # Category: breadcrumb links are the most reliable signal.
    category = "Genel"
    crumb = soup.select_one(
        ".breadcrumb, .breadcrumbs, nav[aria-label='breadcrumb']"
    )
    if crumb:
        crumb_links = [a.get_text(strip=True) for a in crumb.find_all("a")]
        crumb_links = [c for c in crumb_links if c and c.lower() not in ("anasayfa", "home")]
        if crumb_links:
            category = crumb_links[-1]

    return Product(
        product_name=name,
        description=description,
        category=category,
        source_url=url,
    )


def crawl(max_products: int = 60) -> list[Product]:
    """Crawl the storefront homepage + discovered product pages."""
    session = _make_session()
    home = _fetch(session, BASE_URL)
    if home is None:
        return []

    product_links = _discover_product_links(home, BASE_URL)
    print(f"[scraper] discovered {len(product_links)} candidate product links")

    products: list[Product] = []
    seen: set[str] = set()
    for link in list(product_links)[:max_products]:
        if link in seen:
            continue
        seen.add(link)
        time.sleep(REQUEST_DELAY_SECONDS)
        page = _fetch(session, link)
        if page is None:
            continue
        product = _parse_product_page(page, link)
        if product:
            products.append(product)
            print(f"[scraper]   + {product.product_name}")
    return products


# --------------------------------------------------------------------------- #
# Mock fallback catalog
# --------------------------------------------------------------------------- #
def mock_catalog() -> list[Product]:
    """Curated, plausible organic-agriculture products used when the live
    site cannot be crawled. Links point at the real domain's search so they
    remain valid entry points even in offline mode."""
    base = BASE_URL
    items: list[tuple[str, str, str]] = [
        (
            "Solucan Gubresi (Vermikompost)",
            "Organik solucan gubresi; toprak yapisini iyilestirir, bitkilere "
            "yavas salinan dogal besin saglar. Sebze, meyve ve sus bitkileri icin uygundur.",
            "Organik Gubreler",
        ),
        (
            "Deniz Yosunu Ozutu (Algae Extract)",
            "Deniz yosunu bazli sivi besin takviyesi; koklenmeyi ve stres "
            "dayanikliligini destekler, mikro besin elementleri icerir.",
            "Sivi Besinler",
        ),
        (
            "Organik Sivi Solucan Gubresi",
            "Yaprak ve kokten uygulanabilen sivi vermikompost; azot, fosfor, "
            "potasyum ve humik asit bakimindan zengindir.",
            "Sivi Besinler",
        ),
        (
            "Humik & Fulvik Asit Konsantresi",
            "Toprakta besin alimini artiran humik-fulvik asit karisimi; kok "
            "gelisimini ve mikrobiyal aktiviteyi destekler.",
            "Toprak Duzenleyiciler",
        ),
        (
            "Bitkisel Kompost (Organik)",
            "Bitkisel atiklardan uretilmis olgun kompost; toprak organik madde "
            "oranini yukseltir ve su tutma kapasitesini artirir.",
            "Organik Gubreler",
        ),
        (
            "Mikoriza Mantari Inokulanti",
            "Kok bolgesinde faydali mikoriza mantarlarini cogaltan biyolojik "
            "urun; fosfor ve su aliminda bitkilere yardimci olur.",
            "Biyolojik Urunler",
        ),
        (
            "Dogal Kaya Fosfat",
            "Yavas salinan dogal fosfor kaynagi; koklenme ve cicek/meyve "
            "olusumu doneminde toprak fosforunu destekler.",
            "Mineral Gubreler",
        ),
        (
            "Odun Kulu Bazli Potasyum Takviyesi",
            "Dogal potasyum ve kalsiyum kaynagi; meyve kalitesini ve bitki "
            "dayanikliligini desteklemek icin toprak duzenleyici olarak kullanilir.",
            "Toprak Duzenleyiciler",
        ),
    ]
    products: list[Product] = []
    for name, desc, cat in items:
        slug = name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        url = urljoin(base, f"arama?q={slug}")
        products.append(
            Product(product_name=name, description=desc, category=cat, source_url=url)
        )
    return products


# --------------------------------------------------------------------------- #
# Persistence + entrypoint
# --------------------------------------------------------------------------- #
def save_catalog(products: Iterable[Product]) -> None:
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = [asdict(p) for p in products]
    PRODUCTS_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[scraper] wrote {len(payload)} products -> {PRODUCTS_JSON}")


def run(force_mock: bool = False, max_products: int = 60) -> list[Product]:
    products: list[Product] = []
    if not force_mock:
        try:
            products = crawl(max_products=max_products)
        except Exception as exc:  # noqa: BLE001 - never let scraping crash the pipeline
            print(f"[scraper] crawl error, falling back to mock: {exc}")
            products = []

    if not products:
        reason = "forced" if force_mock else "live crawl returned no products"
        print(f"[scraper] using MOCK catalog ({reason}).")
        products = mock_catalog()

    save_catalog(products)
    return products


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape ekolojiktarim.com.tr catalog")
    parser.add_argument(
        "--mock", action="store_true", help="Force the mock catalog (offline)."
    )
    parser.add_argument(
        "--max", type=int, default=60, help="Max product pages to crawl."
    )
    args = parser.parse_args()
    run(force_mock=args.mock, max_products=args.max)


if __name__ == "__main__":
    main()
