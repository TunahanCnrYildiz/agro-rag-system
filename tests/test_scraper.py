from bs4 import BeautifulSoup

from src import scraper

# Real shape of an ekolojiktarim.com.tr product page (probed 2026-07-16):
# Yoast fills <meta name="description"> from the product TITLE when the product
# has no excerpt, so the meta tag is a decoy - the real text lives in the
# WooCommerce short-description block.
HTML_META_IS_JUST_THE_TITLE = """
<html><head><meta name="description" content="FLY AZOT"></head><body>
  <div class="woocommerce-product-details__short-description">
    <p>FLY AZOT, Bitki bunyesine hizli alinan ve uzun sureli etki gosteren,
       ekonomik olan konsantre bir Azottur.</p>
  </div>
  <p>Bu sayfadaki diger uzun paragraf metni burada yer alir ve kirk karakteri asar.</p>
</body></html>
"""

HTML_NO_SHORT_DESCRIPTION = """
<html><head><meta name="description" content="Gercek bir meta aciklamasi burada."></head>
<body><p>Kirk karakterden uzun bir paragraf metni burada yer aliyor.</p></body></html>
"""

HTML_NOTHING_USEFUL = """
<html><head></head><body><p>kisa</p></body></html>
"""


def _patch_fetch(monkeypatch, html):
    monkeypatch.setattr(
        scraper, "fetch", lambda session, url, who: BeautifulSoup(html, "html.parser")
    )


def test_fetch_description_prefers_short_description_over_title_meta(monkeypatch):
    """The bug this guards: preferring meta stored "FLY AZOT" as FLY AZOT's own
    description for 22 of 48 products, leaving nothing for the embedder to match
    a nitrogen query against."""
    _patch_fetch(monkeypatch, HTML_META_IS_JUST_THE_TITLE)

    out = scraper._fetch_description(None, "https://example.test/product/fly-azot/")

    assert "Azottur" in out
    assert out != "FLY AZOT"


def test_fetch_description_falls_back_to_meta_when_no_short_description(monkeypatch):
    _patch_fetch(monkeypatch, HTML_NO_SHORT_DESCRIPTION)

    out = scraper._fetch_description(None, "https://example.test/product/x/")

    assert out == "Gercek bir meta aciklamasi burada."


def test_fetch_description_returns_empty_when_page_has_nothing(monkeypatch):
    _patch_fetch(monkeypatch, HTML_NOTHING_USEFUL)

    assert scraper._fetch_description(None, "https://example.test/product/x/") == ""


def test_fetch_description_returns_empty_when_page_unreachable(monkeypatch):
    monkeypatch.setattr(scraper, "fetch", lambda session, url, who: None)

    assert scraper._fetch_description(None, "https://example.test/product/x/") == ""
