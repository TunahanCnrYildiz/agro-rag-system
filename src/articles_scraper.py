"""Tarim Akademisi (blog) scraper for ekolojiktarim.com.tr.

Crawls the academy category listing (and its subcategories) and writes
article title/excerpt/date/category/image/URL/content to
docs/articles/articles.json.

    python -m src.articles_scraper           # crawl
    python -m src.articles_scraper --max 40  # limit article count
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass

import requests
from bs4 import BeautifulSoup

try:
    from .config import DOCS_DIR
    from .scrape_utils import (
        BASE_URL,
        REQUEST_DELAY_SECONDS,
        extract_meta_description,
        fetch,
        make_session,
    )
except ImportError:  # pragma: no cover
    from config import DOCS_DIR  # type: ignore
    from scrape_utils import (  # type: ignore
        BASE_URL,
        REQUEST_DELAY_SECONDS,
        extract_meta_description,
        fetch,
        make_session,
    )

ARTICLES_DIR = DOCS_DIR / "articles"
ARTICLES_JSON = ARTICLES_DIR / "articles.json"

# Academy category + its subcategories (from the site's navigation).
CATEGORY_SLUGS = [
    "akademi",
    "akademi/tarim",
    "akademi/gubre",
    "akademi/tarim-teknolojileri",
    "akademi/bayi-onerileri",
    "akademi/genel",
]


@dataclass
class Article:
    title: str
    excerpt: str
    category: str
    date: str
    source_url: str
    image_url: str = ""
    content: str = ""


def _parse_listing_page(soup: BeautifulSoup) -> list[dict]:
    cards = []
    for art in soup.select("article.elementor-post"):
        title_a = art.select_one(".elementor-post__title a")
        if not title_a:
            continue
        title = title_a.get_text(strip=True)
        url = title_a.get("href", "").split("#")[0]
        if not title or not url:
            continue

        img = art.select_one(".elementor-post__thumbnail img")
        image_url = img.get("src", "") if img else ""

        badge = art.select_one(".elementor-post__badge")
        category = badge.get_text(strip=True) if badge else "Genel"

        date_el = art.select_one(".elementor-post-date")
        date = date_el.get_text(strip=True) if date_el else ""

        cards.append(
            {
                "title": title,
                "url": url,
                "image_url": image_url,
                "category": category,
                "date": date,
            }
        )
    return cards


def _crawl_category(session: requests.Session, slug: str, max_pages: int = 3) -> list[dict]:
    cards: dict[str, dict] = {}
    for page_num in range(1, max_pages + 1):
        url = (
            f"{BASE_URL}category/{slug}/"
            if page_num == 1
            else f"{BASE_URL}category/{slug}/page/{page_num}/"
        )
        soup = fetch(session, url, "articles")
        if soup is None:
            break
        page_cards = _parse_listing_page(soup)
        if not page_cards:
            break
        new_count = 0
        for c in page_cards:
            if c["url"] not in cards:
                cards[c["url"]] = c
                new_count += 1
        if new_count == 0:
            break
        time.sleep(REQUEST_DELAY_SECONDS)
    return list(cards.values())


def _fetch_content(session: requests.Session, url: str) -> tuple[str, str]:
    """Return (excerpt, full_content) for an article detail page."""
    soup = fetch(session, url, "articles")
    if soup is None:
        return "", ""
    body = soup.select_one(
        ".elementor-widget-theme-post-content .elementor-widget-container"
    )
    content = body.get_text(" ", strip=True) if body else ""

    excerpt = extract_meta_description(soup)
    if not excerpt and content:
        excerpt = content[:200].rsplit(" ", 1)[0] + "..."

    return excerpt, content


def crawl(max_articles: int = 60) -> list[Article]:
    session = make_session()
    cards_by_url: dict[str, dict] = {}
    for slug in CATEGORY_SLUGS:
        print(f"[articles] category: {slug}")
        cards = _crawl_category(session, slug)
        print(f"[articles]   found {len(cards)} articles")
        for c in cards:
            cards_by_url.setdefault(c["url"], c)
        if len(cards_by_url) >= max_articles:
            break

    articles: list[Article] = []
    for url, card in list(cards_by_url.items())[:max_articles]:
        time.sleep(REQUEST_DELAY_SECONDS)
        excerpt, content = _fetch_content(session, url)
        articles.append(
            Article(
                title=card["title"],
                excerpt=excerpt,
                category=card["category"],
                date=card["date"],
                source_url=url,
                image_url=card["image_url"],
                content=content,
            )
        )
        print(f"[articles]   + {card['title']}")
    return articles


def save_articles(articles: list[Article]) -> None:
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    payload = [asdict(a) for a in articles]
    ARTICLES_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[articles] wrote {len(payload)} articles -> {ARTICLES_JSON}")


def run(max_articles: int = 60) -> list[Article]:
    articles = crawl(max_articles=max_articles)
    save_articles(articles)
    return articles


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape ekolojiktarim.com.tr academy articles")
    parser.add_argument("--max", type=int, default=60, help="Max articles to crawl.")
    args = parser.parse_args()
    run(max_articles=args.max)


if __name__ == "__main__":
    main()
