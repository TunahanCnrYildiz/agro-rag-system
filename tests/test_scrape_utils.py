"""Unit tests for src/scrape_utils.py (no network)."""

from bs4 import BeautifulSoup

from src import scrape_utils


# The real shape, probed 2026-08-22: Elementor nested tabs, panels rendered
# server-side, button and panel paired by a shared numeric suffix.
TABS_HTML = """
<html><body>
  <div class="e-n-tabs">
    <div class="e-n-tabs-heading">
      <button class="e-n-tab-title" id="e-n-tab-title-258052051">
        <span class="e-n-tab-title-text">Açıklama</span></button>
      <button class="e-n-tab-title" id="e-n-tab-title-258052052">
        <span class="e-n-tab-title-text">Uygulama (Yeri,Zamanı,Şekli,Dozu)</span></button>
      <button class="e-n-tab-title" id="e-n-tab-title-258052053">
        <span class="e-n-tab-title-text">Döküman</span></button>
    </div>
    <div id="e-n-tab-content-258052051"><p>Ürünün   uzun açıklaması.</p></div>
    <div id="e-n-tab-content-258052052"><p>Sebzelerde : Damlamadan 250 gr/ 1000m² alana uygulanılır.</p></div>
    <div id="e-n-tab-content-258052053"><p>Ürün Tescil Belgesi</p></div>
  </div>
</body></html>
"""

FURNITURE_HTML = """
<html><body>
  <button class="e-n-tab-title" id="e-n-tab-title-1">
    <span class="e-n-tab-title-text">Uygulama (Yeri,Zamanı,Şekli,Dozu)</span></button>
  <div id="e-n-tab-content-1">
    <p>DAMLAMA SULAMA: bir dekara (1.000 m²) 2 – 2,5 litre uygulaması yapılabilir.</p>
    <p>Ürün Tescil Belgesi Benzer Ürünler Mikro Besinler HİGRO CUPPERS Makro Besinler HİGRO ABS</p>
  </div>
</body></html>
"""


def _soup(html):
    return BeautifulSoup(html, "html.parser")


def test_every_tab_is_paired_with_its_own_panel():
    panels = scrape_utils.extract_tab_panels(_soup(TABS_HTML))
    assert list(panels) == ["Açıklama", "Uygulama (Yeri,Zamanı,Şekli,Dozu)", "Döküman"]
    assert panels["Uygulama (Yeri,Zamanı,Şekli,Dozu)"].startswith("Sebzelerde")


def test_whitespace_is_collapsed():
    """The panel text is matched by regex downstream; runs of whitespace and
    newlines would break patterns that expect single spaces."""
    panels = scrape_utils.extract_tab_panels(_soup(TABS_HTML))
    assert panels["Açıklama"] == "Ürünün uzun açıklaması."


def test_page_furniture_is_cut_off():
    """One real page (HIGRO 8 MN) leaks the related-products rail into its
    panel. Left in, it hands the dose parser other products' names and numbers
    to misread as this product's dose."""
    panels = scrape_utils.extract_tab_panels(_soup(FURNITURE_HTML))
    text = panels["Uygulama (Yeri,Zamanı,Şekli,Dozu)"]
    assert text.endswith("uygulaması yapılabilir.")
    assert "Benzer Ürünler" not in text
    assert "HİGRO CUPPERS" not in text


def test_a_page_with_no_tabs_yields_an_empty_mapping():
    """A layout change must not raise; it must show up as nothing found."""
    assert scrape_utils.extract_tab_panels(_soup("<html><body><p>hi</p></body></html>")) == {}


def test_a_button_with_no_matching_panel_is_skipped():
    html = """<html><body>
      <button class="e-n-tab-title" id="e-n-tab-title-9">
        <span class="e-n-tab-title-text">Yalnız</span></button>
    </body></html>"""
    assert scrape_utils.extract_tab_panels(_soup(html)) == {}
