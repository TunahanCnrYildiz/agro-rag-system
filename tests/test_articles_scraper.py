from bs4 import BeautifulSoup

from src import articles_scraper

TITLE = "Toprak Canlılığı ve Mikroorganizmalar: Sağlam Köklerin Temeli"

# Real shape of an ekolojiktarim.com.tr academy article (probed 2026-07-30):
# the body repeats the post title in an <h3>, section headings are <p><b>...</b></p>,
# and everything else is a plain <p>. Flattening this with get_text(" ") is what
# produced 60 articles with zero newlines and 26 with a duplicated title.
HTML_REAL_SHAPE = f"""
<html><head><meta name="description" content="Toprağın biyolojik canlılığı."></head><body>
  <div class="elementor-widget-theme-post-content">
    <div class="elementor-widget-container">
      <h3>{TITLE}</h3>
      <p>“{TITLE}”, bitkilerinizin çevresel faktörlere karşı doğal direncini artıran
         en hayati biyolojik sistemdir.</p>
      <p><b>Görünmez İşçiler: Topraktaki Yaşam Ağı</b></p>
      <p>Sağlıklı bir toprağın bir çay kaşığında milyarlarca mikroorganizma bulunur.</p>
      <ul><li>Kompost uygulaması</li><li>Yeşil gübreleme</li></ul>
    </div>
  </div>
</body></html>
"""

HTML_NO_META = """
<html><head></head><body>
  <div class="elementor-widget-theme-post-content">
    <div class="elementor-widget-container">
      <p>Birinci paragraf burada yer alıyor ve makalenin özetini taşıyor.</p>
      <p>İkinci paragraf ise bambaşka bir konudan söz ediyor.</p>
    </div>
  </div>
</body></html>
"""


def _patch_fetch(monkeypatch, html):
    monkeypatch.setattr(
        articles_scraper,
        "fetch",
        lambda session, url, who: BeautifulSoup(html, "html.parser"),
    )


def test_content_separates_paragraphs_with_blank_lines(monkeypatch):
    """The bug this guards: every one of the 60 stored articles had zero newlines,
    so the app rendered a long article as one unbroken wall of text."""
    _patch_fetch(monkeypatch, HTML_REAL_SHAPE)

    _, content = articles_scraper._fetch_content(None, "https://example.test/a/", TITLE)

    paragraphs = content.split("\n\n")
    assert len(paragraphs) >= 4
    assert paragraphs[1].startswith("**Görünmez İşçiler")


def test_content_drops_the_body_heading_that_repeats_the_title(monkeypatch):
    """26 of 60 articles began with their own title, which the detail screen
    already renders above the body."""
    _patch_fetch(monkeypatch, HTML_REAL_SHAPE)

    _, content = articles_scraper._fetch_content(None, "https://example.test/a/", TITLE)

    # Also guard the marked-up form - **Title** would still be a duplicate.
    assert not content.lstrip("*").startswith(TITLE)
    # The title quoted inside the opening sentence is the site's own prose - keep it.
    assert f"“{TITLE}”" in content


def test_drops_a_body_heading_that_extends_the_listing_title(monkeypatch):
    """Two posts head their body with a longer variant of the listing title
    ("Toprakta Neden Gübreye İhtiyaç Olur?" vs "... Bitki Beslenmesi ve
    Verimlilik Artışının Sırları"), so exact equality left the duplicate in."""
    html = """
    <div class="elementor-widget-theme-post-content"><div class="elementor-widget-container">
      <h3>Toprakta Neden Gübreye İhtiyaç Olur? Bitki Beslenmesi ve Verimlilik Artışının Sırları</h3>
      <p>Toprak, bitkinin ihtiyaç duyduğu besinleri sınırsız biçimde sunmaz.</p>
    </div></div>
    """
    _patch_fetch(monkeypatch, html)

    _, content = articles_scraper._fetch_content(
        None, "https://example.test/a/", "Toprakta Neden Gübreye İhtiyaç Olur?"
    )

    assert content.startswith("Toprak, bitkinin")


def test_keeps_a_first_sentence_that_merely_opens_with_the_title(monkeypatch):
    """Three posts genuinely open their prose with the title text - dropping that
    would eat the first sentence."""
    html = """
    <div class="elementor-widget-theme-post-content"><div class="elementor-widget-container">
      <p>Tarımsal Üretimde Fosfor ile Güçlü Çiçeklenme, bitkilerin verim
         potansiyelini doğrudan belirleyen en kritik faktörlerden biridir.</p>
    </div></div>
    """
    _patch_fetch(monkeypatch, html)

    _, content = articles_scraper._fetch_content(
        None, "https://example.test/a/", "Tarımsal Üretimde Fosfor ile Güçlü Çiçeklenme"
    )

    assert content.startswith("Tarımsal Üretimde Fosfor ile Güçlü Çiçeklenme, bitkilerin")


def test_bold_only_paragraph_becomes_a_markdown_heading(monkeypatch):
    _patch_fetch(monkeypatch, HTML_REAL_SHAPE)

    _, content = articles_scraper._fetch_content(None, "https://example.test/a/", TITLE)

    assert "**Görünmez İşçiler: Topraktaki Yaşam Ağı**" in content


def test_list_items_become_bullet_lines(monkeypatch):
    _patch_fetch(monkeypatch, HTML_REAL_SHAPE)

    _, content = articles_scraper._fetch_content(None, "https://example.test/a/", TITLE)

    assert "- Kompost uygulaması" in content
    assert "- Yeşil gübreleme" in content


def test_no_stray_space_before_punctuation(monkeypatch):
    """Inline markup makes get_text(" ") insert a space before the punctuation that
    follows it - 57 such gaps across 30 of the 60 stored articles."""
    html = """
    <div class="elementor-widget-theme-post-content"><div class="elementor-widget-container">
      <p>Özellikle <b>azot</b>, potasyum ve kalsiyum <i>önemlidir</i>.</p>
    </div></div>
    """
    _patch_fetch(monkeypatch, html)

    _, content = articles_scraper._fetch_content(None, "https://example.test/a/", "Başlık")

    assert content == "Özellikle azot, potasyum ve kalsiyum önemlidir."


def test_excerpt_ignores_a_meta_description_that_is_just_the_title(monkeypatch):
    """Same Yoast decoy the product scraper already guards against: with no
    hand-written description the meta tag echoes the title, which summarises
    nothing. Two of the 60 academy posts land here."""
    html = """
    <html><head><meta name="description"
        content="TOPRAK KALSİYUMLA DOLU. BİTKİLER HÂLÂ KALSİYUM AÇLIĞI ÇEKİYOR. NEDEN?"></head>
    <body><div class="elementor-widget-theme-post-content"><div class="elementor-widget-container">
      <p>Bitkilerin sağlıklı gelişimi için temel besin maddelerine ihtiyacı bulunur.</p>
    </div></div></body></html>
    """
    _patch_fetch(monkeypatch, html)

    excerpt, _ = articles_scraper._fetch_content(
        None,
        "https://example.test/a/",
        "TOPRAK KALSİYUMLA DOLU. BİTKİLER HÂLÂ KALSİYUM AÇLIĞI ÇEKİYOR. NEDEN?",
    )

    assert excerpt.startswith("Bitkilerin sağlıklı gelişimi")


def test_excerpt_drops_a_leading_title_sentence(monkeypatch):
    """One meta description runs "TITLE <intro>" - next to the title the card
    already shows, the repeat is noise. This post's title carries its own
    trailing period, so the intro follows with no separator of its own."""
    title = "SARARAN YAPRAKLAR DEMİR EKSİKLİĞİ DEĞİL OLABİLİR. FARKI ŞÖYLE ANLARSINIZ."
    html = f"""
    <html><head><meta name="description"
        content="{title} Bitkilerinizin yapraklarında sararma fark ettiğinizde akla ilk gelen demir eksikliğidir."></head>
    <body><div class="elementor-widget-theme-post-content"><div class="elementor-widget-container">
      <p>Gövde metni burada.</p>
    </div></div></body></html>
    """
    _patch_fetch(monkeypatch, html)

    excerpt, _ = articles_scraper._fetch_content(None, "https://example.test/a/", title)

    assert excerpt.startswith("Bitkilerinizin yapraklarında")


def test_excerpt_keeps_a_title_that_opens_a_sentence(monkeypatch):
    """21 excerpts open with the title as the sentence's subject - cutting there
    would leave a fragment starting with a comma."""
    title = "Toprak Canlılığı ve Mikroorganizmalar: Sağlam Köklerin Temeli"
    html = f"""
    <html><head><meta name="description"
        content="{title}, bitkilerinizin çevresel faktörlere karşı direncini artıran biyolojik sistemdir."></head>
    <body><div class="elementor-widget-theme-post-content"><div class="elementor-widget-container">
      <p>Gövde metni burada.</p>
    </div></div></body></html>
    """
    _patch_fetch(monkeypatch, html)

    excerpt, _ = articles_scraper._fetch_content(None, "https://example.test/a/", title)

    assert excerpt.startswith(title + ",")


def test_excerpt_falls_back_to_the_first_paragraph_without_markup(monkeypatch):
    """The old fallback sliced content[:200], which now would carry newlines and
    '**' markers into the one-line card summary."""
    _patch_fetch(monkeypatch, HTML_NO_META)

    excerpt, _ = articles_scraper._fetch_content(None, "https://example.test/a/", "Başlık")

    assert excerpt.startswith("Birinci paragraf")
    assert "\n" not in excerpt
    assert "*" not in excerpt


def test_returns_empty_when_page_unreachable(monkeypatch):
    monkeypatch.setattr(articles_scraper, "fetch", lambda session, url, who: None)

    assert articles_scraper._fetch_content(None, "https://example.test/a/", "Başlık") == ("", "")
