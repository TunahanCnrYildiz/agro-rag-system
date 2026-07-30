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
import re
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

# Block elements that become their own paragraph in the stored content.
BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote")

# get_text(" ") separates inline markup with a space, which lands in front of the
# punctuation that follows it ("azot <b>, potasyum").
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?%)\]])")

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


def _normalize(text: str) -> str:
    """Fold quote styles and whitespace so a heading can be compared to a title."""
    folded = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("*", "")
    return " ".join(folded.split()).strip(" \"'").casefold()


def _block_to_text(el) -> str:
    """One block element as a line of the stored content.

    Section headings on the site are <p><b>...</b></p> rather than real heading
    tags, so a bold-only paragraph is emitted as **bold** - the app's
    MarkdownText renders that, and a plain get_text() would lose the distinction.
    """
    text = " ".join(el.get_text(" ", strip=True).split())
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    if not text:
        return ""
    if el.name == "li":
        return f"- {text}"
    bold = el.find(["b", "strong"])
    if bold is not None and _normalize(bold.get_text(" ", strip=True)) == _normalize(text):
        return f"**{text}**"
    if el.name.startswith("h"):
        return f"**{text}**"
    return text


def _repeats_the_title(line: str, title: str) -> bool:
    """Is this leading block the body's own copy of the post title?

    Only a heading block counts: three posts open their prose with the title
    text, and dropping that would eat the first sentence. Two others head the
    body with a LONGER variant of the listing title, so this is a prefix test
    rather than equality.
    """
    if not line.startswith("**"):
        return False
    head, name = _normalize(line), _normalize(title)
    return bool(name) and (head.startswith(name) or name.startswith(head))


def _extract_blocks(body, title: str) -> list[str]:
    """Block texts of an article body, minus the heading that repeats the title."""
    blocks: list[str] = []
    for el in body.find_all(BLOCK_TAGS):
        if el.find_parent(BLOCK_TAGS) is not None:
            continue  # nested block; its outer block already carries the text
        line = _block_to_text(el)
        if line:
            blocks.append(line)

    if blocks and _repeats_the_title(blocks[0], title):
        blocks.pop(0)
    return blocks


def _restates_title(text: str, title: str) -> bool:
    """Does this summary open by repeating the whole headline?

    The card renders the excerpt right under the title, so such an excerpt shows
    the headline twice. The boundary check keeps a title that merely prefixes a
    longer word ("...bağlantı" in "...bağlantıyı anlamanıza").
    """
    body, name = _normalize(text), _normalize(title)
    if not name or not body.startswith(name):
        return False
    return not body[len(name):len(name) + 1].isalnum()


def _shorten(text: str, limit: int = 200) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "..."


def _clean_excerpt(excerpt: str, title: str) -> str:
    """Drop a meta description that only restates the title.

    Yoast falls back to the post title when the author wrote no description, so
    the tag is a decoy - the same trap `scraper._fetch_description` guards for
    products. Returning "" hands the caller its first-paragraph fallback.
    """
    text = " ".join(excerpt.split())
    if not text or _normalize(text) == _normalize(title):
        return ""

    if title and text.casefold().startswith(title.casefold()):
        rest = text[len(title):].lstrip()
        # "TITLE. <intro>" repeats the headline; "TITLE, <clause>" is a sentence.
        # Some titles carry their own trailing period, so the break can sit on
        # either side of the split.
        ends_sentence = title.rstrip()[-1:] in {".", "!", "?", ":"}
        if rest[:1] in {".", "!", "?", ":"}:
            rest, ends_sentence = rest[1:].lstrip(), True
        if ends_sentence and len(rest) >= 40:
            return rest
    return text


def _pick_excerpt(meta: str, blocks: list[str], title: str) -> str:
    """The card summary: the meta description, or the first prose paragraph that
    does not simply repeat the headline. Section headings are never a summary."""
    cleaned = _clean_excerpt(meta, title)
    if cleaned and not _restates_title(cleaned, title):
        return cleaned

    for block in blocks:
        if block.startswith("**"):
            continue
        text = block.lstrip("- ").strip()
        if text and not _restates_title(text, title):
            return _shorten(text)

    return cleaned


def _fetch_content(session: requests.Session, url: str, title: str = "") -> tuple[str, str]:
    """Return (excerpt, full_content) for an article detail page."""
    soup = fetch(session, url, "articles")
    if soup is None:
        return "", ""
    body = soup.select_one(
        ".elementor-widget-theme-post-content .elementor-widget-container"
    )
    blocks = _extract_blocks(body, title) if body else []
    content = "\n\n".join(blocks)

    return _pick_excerpt(extract_meta_description(soup), blocks, title), content


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
        excerpt, content = _fetch_content(session, url, card["title"])
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
