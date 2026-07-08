"""Product scraper for ekolojiktarim.com.tr.

Crawls the WooCommerce product-category pages (following pagination) and
writes product name/description/category/image/URL to
docs/products/products.json. If the site is unreachable or returns nothing,
falls back to a built-in mock catalog so the rest of the pipeline still runs
offline.

    python -m src.scraper           # crawl, mock fallback on failure
    python -m src.scraper --mock    # force the mock catalog
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from typing import Iterable
from urllib.parse import urljoin

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
MAX_PAGES_PER_CATEGORY = 10  # safety cap on pagination

# Known WooCommerce category slugs (from the site's navigation).
CATEGORY_SLUGS = [
    "adjuvant",
    "makro-besinler",
    "mikro-besinler",
    "sertifikali-organik-gubreler",
    "sivi-organomineral-gubreler",
    "tuzluluk-giderici-ph-duzenleyiciler",
    "ust-segment",
]


@dataclass
class Product:
    """A single catalog entry."""

    product_name: str
    description: str
    category: str
    source_url: str
    image_url: str = ""


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
# Category listing parsing
# --------------------------------------------------------------------------- #
def _parse_category_page(soup: BeautifulSoup) -> list[dict]:
    """Extract product cards (name, url, image, category) from a WooCommerce
    category listing page."""
    cards = []
    for li in soup.select(".shop-product_grid"):
        title_a = li.select_one(".shop-product_title a")
        if not title_a:
            continue
        name = title_a.get_text(strip=True)
        url = title_a.get("href", "").split("#")[0]
        if not name or not url:
            continue

        img = li.select_one(".shop-product_photo img")
        image_url = img.get("src", "") if img else ""

        cat_a = li.select_one(".shop-product-cat")
        category = cat_a.get_text(strip=True) if cat_a else "Genel"

        cards.append(
            {"name": name, "url": url, "image_url": image_url, "category": category}
        )
    return cards


def _crawl_category(session: requests.Session, slug: str) -> list[dict]:
    """Crawl one category, following pagination until no more products."""
    all_cards: dict[str, dict] = {}
    for page_num in range(1, MAX_PAGES_PER_CATEGORY + 1):
        url = (
            f"{BASE_URL}product-category/{slug}/"
            if page_num == 1
            else f"{BASE_URL}product-category/{slug}/page/{page_num}/"
        )
        soup = _fetch(session, url)
        if soup is None:
            break
        cards = _parse_category_page(soup)
        if not cards:
            break
        new_count = 0
        for c in cards:
            if c["url"] not in all_cards:
                all_cards[c["url"]] = c
                new_count += 1
        if new_count == 0:
            break  # paginated past the end, WordPress re-served the last page
        time.sleep(REQUEST_DELAY_SECONDS)
    return list(all_cards.values())


def _fetch_description(session: requests.Session, url: str) -> str:
    """Best-effort short description from a product detail page."""
    soup = _fetch(session, url)
    if soup is None:
        return ""
    meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", property="og:description"
    )
    if meta_desc and meta_desc.get("content"):
        return meta_desc["content"].strip()
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if len(text) > 40:
            return text
    return ""


def crawl(max_products: int = 200) -> list[Product]:
    """Crawl all known product categories (with pagination), then fetch a
    short description per product."""
    session = _make_session()
    cards_by_url: dict[str, dict] = {}
    for slug in CATEGORY_SLUGS:
        print(f"[scraper] category: {slug}")
        cards = _crawl_category(session, slug)
        print(f"[scraper]   found {len(cards)} products")
        for c in cards:
            cards_by_url.setdefault(c["url"], c)
        if len(cards_by_url) >= max_products:
            break

    products: list[Product] = []
    for url, card in list(cards_by_url.items())[:max_products]:
        time.sleep(REQUEST_DELAY_SECONDS)
        description = _fetch_description(session, url)
        products.append(
            Product(
                product_name=card["name"],
                description=description,
                category=card["category"],
                source_url=url,
                image_url=card["image_url"],
            )
        )
        print(f"[scraper]   + {card['name']}")
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


def run(force_mock: bool = False, max_products: int = 200) -> list[Product]:
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
        "--max", type=int, default=200, help="Max products to crawl."
    )
    args = parser.parse_args()
    run(force_mock=args.mock, max_products=args.max)


if __name__ == "__main__":
    main()
