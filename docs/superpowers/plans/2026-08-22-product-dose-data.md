# Product Dose Data Layer (P3a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `doses.lookup(product, group)` return the manufacturer's published per-dekar dose, with the application method it belongs to, backed by a committed file built from the product pages.

**Architecture:** A shared extractor pulls the Elementor tab panels out of a product page. A script fetches all 48 panels once and commits them raw. A converter parses those raw panels into `data/product_doses.json`, reporting by name every panel it could not parse. `src/doses.py` reads that file, validates it, and never raises. Nothing is fetched at runtime.

**Tech Stack:** Python 3.14, BeautifulSoup, requests, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-22-product-dose-design.md`
**Recon:** `docs/superpowers/2026-08-22-product-dose-findings.md`

**This is P3a.** It ships nothing user-visible. P3b builds the route and the card on `doses.lookup`; it depends on this plan's interface, not on the parse.

**A deliberate refinement of spec §6:** the spec says "`src/scraper.py` learns the Uygulama tab". The tab extractor goes into `src/scrape_utils.py` instead, where it is pure and testable offline, and a script uses it. `src/scraper.py` — the catalog crawler — is not touched at all: the catalog and the dose table are re-crawled on different cadences, and coupling them would mean a dose refresh rewrites `products.json`.

## Global Constraints

- **Run every command from the repo root.** `src/config.py` reads a root-anchored `.env`; from anywhere else unrelated tests fail.
- **Windows console cannot encode Turkish.** Prefix any command whose output shows Turkish with `PYTHONIOENCODING=utf-8`, or a `UnicodeEncodeError` masquerades as a test failure. Almost everything here is Turkish.
- Shell is PowerShell: `&&` does not work; use `;` or separate calls. Use `python -m pytest`, never a bare `pytest`.
- **Branch:** create `product-doses` off `main` before Task 1. Do not touch `demo`. `main` is shared — rebase, never force-push.
- **`src/doses.py` imports nothing from `src/engine.py`.** It is a file in, values out — the boundary `src/norms.py` and `src/budget.py` both keep, and a test pins it.
- **A missing dose is never 0.** `parse_dose` returns `None` and `doses.lookup` returns an empty tuple; neither ever returns a zero, because a zero flows into the multiplication and answers "you need 0 litres" about a purchase.
- **Nothing is invented.** A panel that does not parse yields NO row. No defaulting to another group, no borrowing another product's figure, no midpoint standing in for a range.
- **A dilution is never read as a per-area dose.** `100 litre suya 250 gram` is per 100 L of water; turning it into a per-dekar figure needs a spray volume the page does not give.
- **`_load` never raises.** A missing, malformed or wrong-shaped file yields an empty table, exactly as `src/norms.py:_load` and `src/fertplan.py:_load` do.
- **The committed JSON must be a reproducible output of the committed converter over the committed raw panels** — re-runnable and diffable. This check caught a hand-edit risk in P2a.
- All code, comments, docstrings and test names in English. User-facing strings in Turkish.
- **Commit messages:** short, natural, English, capitalised verb, roughly six to nine words. No `Co-Authored-By` trailer.
- **No eval run and no eval case.** Nothing here reaches the model.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/scrape_utils.py` (modify) | `extract_tab_panels(soup)` — the Elementor pairing, pure and offline-testable |
| `scripts/fetch_dose_panels.py` (create) | fetch the 48 product pages once, save the raw panel text |
| `data/raw/product_panels.json` (create, committed) | the raw input the converter is written against |
| `src/dose_parse.py` (create) | parse one clause, then one panel, into doses. No I/O, no network |
| `scripts/build_product_doses.py` (create) | raw panels → `data/product_doses.json`, reporting failures by name |
| `data/product_doses.json` (create, committed) | product → group → method → {low, high, unit} |
| `src/doses.py` (create) | the runtime loader: validated, never raises, absence is an empty tuple |

`src/dose_parse.py` is separate from `src/doses.py` on purpose: parsing free Turkish is the risky, iterated part and it must be unit-testable without any file; the loader is a small, boring validator. Keeping them apart means a parser change cannot break the load path and a reviewer can judge each on its own.

---

### Task 1: The tab-panel extractor

**Files:**
- Modify: `src/scrape_utils.py`
- Test: `tests/test_scrape_utils.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces: `extract_tab_panels(soup: BeautifulSoup) -> dict[str, str]` — tab label → panel text, whitespace collapsed, page furniture stripped

**Background.** Every one of the 48 product pages is a WooCommerce product rendered with Elementor **nested tabs**, and the panels are server-rendered in the HTML — no JS, no AJAX. A button `<button class="e-n-tab-title" id="e-n-tab-title-N">` pairs with `<div id="e-n-tab-content-N">` by the shared numeric suffix. Every page carries exactly three: `Açıklama`, `Uygulama (Yeri,Zamanı,Şekli,Dozu)`, `Döküman`.

**One page leaks page furniture into its panel.** `HIGRO 8 MN`'s Uygulama panel comes back 1793 characters long and ends with `Ürün Tescil Belgesi Benzer Ürünler Mikro Besinler HİGRO CUPPERS …` — the related-products rail. Left in, that text reaches the parser and offers it other products' names and numbers to misread. Cut the panel at the first furniture marker.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scrape_utils.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_scrape_utils.py -q
```

Expected: FAIL with `AttributeError: module 'src.scrape_utils' has no attribute 'extract_tab_panels'`.

- [ ] **Step 3: Implement it**

Add to `src/scrape_utils.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_scrape_utils.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest -q
git add src/scrape_utils.py tests/test_scrape_utils.py
git commit -m "Pull the Elementor tab panels out of a product page"
```

Expected: the suite count rises by 5 with no failures.

---

### Task 2: Capture the 48 panels and record their grammars

**This task has the only external dependency in the plan.** Everything after it works against the committed file, so if the site is unreachable the later tasks are still unblocked — they can be written against the fixtures in this plan.

**Files:**
- Create: `scripts/fetch_dose_panels.py`
- Create: `data/raw/product_panels.json` (committed, as fetched)
- Modify: `docs/superpowers/2026-08-22-product-dose-findings.md` (append the grammar section)

**Interfaces:**
- Consumes: `scrape_utils.extract_tab_panels` (Task 1)
- Produces: `data/raw/product_panels.json` — `{"meta": {"fetched": "YYYY-MM-DD", "source": "..."}, "panels": {product_name: uygulama_panel_text}}`

**Background.** This mirrors P2a's first task: obtain the real input and commit it, so the converter can be re-run and reviewed without the network. The 48 URLs are in `docs/products/products.json` under `source_url`. Be polite — `scrape_utils.REQUEST_DELAY_SECONDS` is 1.0 and exists for this.

- [ ] **Step 1: Write the fetch script**

Create `scripts/fetch_dose_panels.py`:

```python
"""Fetch the 'Uygulama' panel from every product page, once, into data/raw.

The panels are committed raw so the converter can be re-run and reviewed
offline. This is the same arrangement data/raw/README.md describes for the
TUIK exports: a fetch nobody has to repeat to check the output.

    python -m scripts.fetch_dose_panels
"""
from __future__ import annotations

import json
import time
from datetime import date

from src.config import DATA_DIR, PRODUCTS_JSON
from src.scrape_utils import REQUEST_DELAY_SECONDS, extract_tab_panels, fetch, make_session

OUT = DATA_DIR / "raw" / "product_panels.json"
DOSE_TAB = "Uygulama"


def main() -> None:
    products = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    session = make_session()
    panels: dict[str, str] = {}
    missing: list[str] = []

    for i, product in enumerate(products, 1):
        name = product["product_name"]
        soup = fetch(session, product["source_url"], "dose-panels")
        # The delay is owed to the site whatever the outcome, so it is taken
        # before any branch can skip it. A run of failures must not turn into
        # a burst of requests.
        time.sleep(REQUEST_DELAY_SECONDS)
        if soup is None:
            missing.append(name)
            print(f"[{i}/{len(products)}] FETCH FAILED {name}")
            continue
        tabs = extract_tab_panels(soup)
        text = next((v for k, v in tabs.items() if DOSE_TAB in k), "")
        if not text:
            # An empty panel is a finding, and it must travel WITH the file.
            # Writing it as an entry would leave a later run that silently lost
            # two products looking complete: the count would still read 48.
            missing.append(name)
            print(f"[{i}/{len(products)}] NO PANEL {name}")
            continue
        panels[name] = text
        print(f"[{i}/{len(products)}] {name[:40]:40} {len(text):5} chars")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"meta": {"fetched": date.today().isoformat(),
                  "source": "ekolojiktarim.com.tr product pages, Uygulama tab",
                  # Both numbers, so the file says on its face whether anything
                  # was lost. A single count cannot distinguish "48 products,
                  # all read" from "48 products, two of them empty".
                  "products_read": len(products),
                  "panels_captured": len(panels),
                  "no_panel": missing},
         "panels": panels},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {len(panels)} panels -> {OUT}")
    if missing:
        print(f"NO PANEL for {len(missing)}: {', '.join(missing)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
PYTHONIOENCODING=utf-8 python -m scripts.fetch_dose_panels
```

Expected: 48 lines, every one with a non-zero character count, and no `FETCH FAILED`. Measured on 2026-08-22 the panels ran from 173 to 1793 characters. If any line reads 0 chars, stop and report it — a page whose layout changed is a finding, not something to work around.

- [ ] **Step 3: Record the grammars you actually see**

Read a dozen panels and append a section to `docs/superpowers/2026-08-22-product-dose-findings.md` recording, with counts, which grammars appear. Measured on 2026-08-22 there are at least three, and the converter in Task 4 is written against exactly this:

| Grammar | Example | Count |
| --- | --- | --- |
| Group-first, method inline | `Sebzelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, Damlamadan 250 gr/ 1000m² alana uygulanılır.` | ~42 |
| Method-first, uppercase, no group | `YAPRAKTAN: … DAMLAMA SULAMA: bir dekara (1.000 m²) 2 – 2,5 litre` | `HIGRO 8 MN` |
| Crop-named prose, no group heading | `Tahıllarda ve Hububatlarda kıraç üretimde dekara 200 cc yapraktan 2 uygulama yapılır.` | `FLY AZOT` |

**The colon after the group word is optional** — `HİGRO CUFİT` and `ZİNCER` write `Sebzelerde Yapraktan …` with no colon, and a pattern that requires one loses them.

- [ ] **Step 4: Commit the raw panels unchanged**

```bash
git add scripts/fetch_dose_panels.py data/raw/product_panels.json docs/superpowers/2026-08-22-product-dose-findings.md
git commit -m "Fetch and commit the raw dose panels the converter reads"
```

Commit them as fetched. A converter whose input is not in the repo cannot be re-run or reviewed.

---

### Task 3: Parse one dose clause

**Files:**
- Create: `src/dose_parse.py`
- Test: `tests/test_dose_parse.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces: `parse_dose(text: str) -> tuple[float, float, str] | None` — `(low, high, unit)` in the unit the page published, `unit` one of `"litre"`, `"cc"`, `"kg"`, `"gr"`. A single figure returns `low == high`. Text with no per-area dose returns `None`.

**Background — this is the risky part of the whole plan, and it has already bitten twice.** The reconnaissance that established "42 of 48" produced **two false negatives from its own regexes** before the number settled:

- The pages almost never write "dekar". They write **`/ 1000m²`**, and 1000 m² *is* one dekar. Searching for `dekar|dönüm` finds **2** products, not 42. They also write `1.000 m²` with a Turkish thousands dot.
- The amount appears on **either side** of the area: `250 gr/ 1000m²` but also `1000m² alan için damla sulama ile 2 – 2.5 litre`, where 26 characters separate them.
- `gram` spelled out was missed by a pattern carrying `gr` and `g`.

And the trap in the other direction: **a dilution must never be read as a per-area dose.** `100 litre suya 250 gram` contains a number, a unit, and the word `litre`; it is per 100 L of water, not per dekar.

**Two more defects surfaced while this task was executed — recorded so the code below is not
re-read as finished.** The pages also write a numeral gloss between the figure and its unit
(`bir dekara (1.000 m²) 3 (üç) litre`), so `_AMOUNT` needs to tolerate a parenthetical. Widening it
WITHOUT widening `_AMOUNT_BARE` reopens the dilution hole: a dilution carrying the same gloss
becomes invisible to `_DILUTION`, the skip never fires, and the parser returns the **water's own
volume** as a per-dekar dose. The two patterns must stay in lock-step, and a comment on each should
say so.

And the sharper lesson: **none of this task's tests exercised the per-figure skip.** Deleting the
whole mechanism left all of them passing, because `_GAP`'s comma bound was doing the work. A test
that credits a mechanism has to fail when the mechanism is removed — verify that by disabling it
and watching the test go red, or the coverage is decorative. That gap is exactly how the defect
above survived a full task review.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dose_parse.py`:

```python
"""Unit tests for src/dose_parse.py. Every input here is verbatim from a real
product page, fetched 2026-08-22 - not invented, because the shapes that break
a pattern are exactly the ones nobody invents."""

import pytest

from src.dose_parse import parse_dose


@pytest.mark.parametrize("text, expected", [
    # The common shape: amount, slash, 1000m2.
    ("Damlamadan 250 gr/ 1000m² alana uygulanılır.", (250.0, 250.0, "gr")),
    # A range, with the area written as 1000m2 and glossed as (da).
    ("Damlama sulama ile 2-2,5 litre / 1000m² (da)", (2.0, 2.5, "litre")),
    # The area FIRST, the amount 26 characters later. The recon's own pattern
    # used a 25-character window and lost this one.
    ("1000m² alan için damla sulama ile 2 – 2.5 litre uygulayın.", (2.0, 2.5, "litre")),
    # A Turkish thousands dot inside the area, and the amount after it.
    ("bir dekara (1.000 m²) 2 – 2,5 litre dozunda uygulama yapılabilir.", (2.0, 2.5, "litre")),
    # The word "dekara" with the amount after it.
    ("Damlama sulama sistemi ile bir dekara (1.000 m²) 3 (üç) litre tabandan uygulanılır.",
     (3.0, 3.0, "litre")),
    # "dekara" with the amount before it.
    ("Tahıllarda kıraç üretimde dekara 200 cc yapraktan 2 uygulama yapılır.",
     (200.0, 200.0, "cc")),
    # An en dash with spaces, and a decimal comma.
    ("dekara (1000m²) 1 – 1,5 litre", (1.0, 1.5, "litre")),
])
def test_a_per_area_dose_is_read(text, expected):
    assert parse_dose(text) == expected


@pytest.mark.parametrize("text", [
    # A DILUTION, not a dose. Per 100 litres of water, and turning it into a
    # per-dekar figure needs a spray volume the page never gives.
    "Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır",
    "5 gün ara ile 100 litre suya 250 gram dozunda 2 defa uygulama yapılmalıdır.",
    "100 litre suya 200 – 250 cc Higro 8 Mn ilave edilerek uygulama yapılabilir.",
    "gübrelerle 100 litre suya 100cc karıştılarak kullanılır.",
    # No numbers at all.
    "etikette önerilen uygulama dozajlarına dikkat edilmesi gerekmektedir.",
    # A number, but nothing tying it to an area.
    "Bekleme süresi 0 (sıfır) gündür.",
    # An interval, not a dose.
    "Sezon boyunca 3 hafta ara ile uygulamaya devam edilir.",
])
def test_text_with_no_per_area_dose_returns_none(text):
    """None, never a guess and never a zero: a wrong number here is a wrong
    purchase."""
    assert parse_dose(text) is None


def test_a_dose_survives_beside_a_dilution_in_the_same_sentence():
    """HİGRO BARF writes both halves as one unpunctuated sentence. Refusing the
    whole clause on sight of a dilution was measured and drops the catalog from
    42 products to 10."""
    text = ("Yapraktan uygulama ile 100 cc / 100 litre suya "
            "Damlama sulama ile 2-2,5 litre / 1000m² (da)")
    assert parse_dose(text) == (2.0, 2.5, "litre")


def test_the_dilutions_own_amount_is_still_refused():
    """The 100 cc belongs to the water, not to the dekar - and it is the figure
    that appears FIRST, so a matcher that stops at the first amount takes it."""
    assert parse_dose("Yapraktan uygulama ile 100 cc / 100 litre suya") is None


def test_the_low_bound_is_never_above_the_high_bound():
    low, high, _ = parse_dose("Damlama sulama ile 2,5-3 litre / 1000m²(da)")
    assert low <= high


def test_a_decimal_comma_is_turkish_not_a_thousands_separator():
    """2,5 is two and a half litres, not twenty-five."""
    assert parse_dose("Damlamadan 2,5 litre / 1000m²") == (2.5, 2.5, "litre")


def test_hectares_are_not_read_as_dekars():
    """A per-hectare figure is ten times a per-dekar one. Reading it as dekars
    would multiply every answer by ten, silently."""
    assert parse_dose("hektara 20 litre uygulanır") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_dose_parse.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.dose_parse'`.

- [ ] **Step 3: Implement it**

Create `src/dose_parse.py`:

```python
"""Read a per-dekar dose out of a manufacturer's free-Turkish application text.

NOTHING IS INVENTED. Text this module cannot read yields None, never a zero and
never a midpoint: a wrong number here becomes a wrong purchase quantity.

A DILUTION IS NOT A DOSE. "100 litre suya 250 gram" is an amount per 100 litres
of water. Converting it to a per-dekar figure needs the spray volume per dekar,
which the pages do not publish, so those clauses are refused rather than guessed.

THE PAGES DO NOT SAY "DEKAR". They say "/ 1000m²", and 1000 m2 is one dekar.
Matching only dekar/donum finds 2 products of 48; including the area forms below
finds 42. That was measured, not assumed - see the recon findings doc.
"""
from __future__ import annotations

import re

# Units as the pages actually spell them, longest first so "litre" is not eaten
# by "l" and "gram" not by "gr". The value is the key stored in the data file.
_UNITS = (("litre", "litre"), ("gram", "gr"), ("lt", "litre"), ("kg", "kg"),
          ("cc", "cc"), ("ml", "cc"), ("gr", "gr"), ("l", "litre"), ("g", "gr"))
_UNIT_RE = "|".join(spelling for spelling, _ in _UNITS)

# A figure or a range. The dash may be a hyphen or an en dash, spaced or not.
_NUMBER = r"\d+(?:[.,]\d+)?"
_AMOUNT = rf"(?P<low>{_NUMBER})\s*(?:[-–]\s*(?P<high>{_NUMBER}))?\s*(?P<unit>{_UNIT_RE})\b"

# One dekar, in every form the pages use. Hectares are deliberately EXCLUDED:
# a per-hectare figure is ten times a per-dekar one, and reading one as the
# other multiplies every answer by ten with nothing to show for it.
_AREA = r"(?:dekar[ae]?|d[oö]n[uü]m[ae]?|1[.\s]?000\s*m\s*[²2]|1000\s*m\s*[²2])"

# The same amount with NO named groups. A pattern may only name a group once,
# so reusing _AMOUNT on both sides of the dilution alternation below raises
# re.PatternError at import time - verified, not guessed.
_AMOUNT_BARE = rf"{_NUMBER}\s*(?:[-–]\s*{_NUMBER})?\s*(?:{_UNIT_RE})"

# Water, so a dilution can be recognised and refused.
_WATER = r"\d+\s*(?:litre|lt|l)\s*su"

# The amount sits on either side of the area, and up to ~40 characters away
# ("1000m² alan için damla sulama ile 2 – 2.5 litre" is 26). Stop at any clause
# punctuation, THE COMMA INCLUDED, so a dose cannot borrow a number from the
# next clause: the panels separate the foliar and drip halves of one sentence
# with a comma and nothing else.
_GAP = r"[^.;:,]{0,40}?"
_AMOUNT_THEN_AREA = re.compile(_AMOUNT + _GAP + _AREA, re.I)
_AREA_THEN_AMOUNT = re.compile(_AREA + _GAP + _AMOUNT, re.I)
_DILUTION = re.compile(
    rf"(?:{_AMOUNT_BARE}{_GAP}{_WATER}|{_WATER}{_GAP}{_AMOUNT_BARE})", re.I)


def _number(text: str) -> float:
    """Turkish decimal comma. The pages also use a dot for the same purpose
    ("2.5 litre" appears beside "2,5 litre" on different products), and no
    amount on any panel reaches four digits, so both are read as decimals."""
    return float(text.replace(",", "."))


def _unit(spelling: str) -> str:
    lowered = spelling.lower()
    for written, key in _UNITS:
        if lowered == written:
            return key
    return lowered


def parse_dose(text: str) -> tuple[float, float, str] | None:
    """One clause's per-dekar dose as (low, high, unit), or None.

    A DILUTION DISQUALIFIES ITS OWN AMOUNT, NOT THE WHOLE CLAUSE. Refusing the
    clause outright was tried and measured: it drops the count from 42 products
    to 10, because panels like HİGRO BARF write

        Yapraktan uygulama ile 100 cc / 100 litre suya
        Damlama sulama ile 2-2,5 litre / 1000m² (da)

    as ONE unpunctuated sentence. The dilution and the dose sit side by side, so
    the test has to be per-figure: an amount that is bound to a volume of water
    is not a per-area dose, and an amount that is bound to an area is - even
    when both appear in the same breath.
    """
    diluted = [m.span() for m in _DILUTION.finditer(text)]
    for pattern in (_AMOUNT_THEN_AREA, _AREA_THEN_AMOUNT):
        for match in pattern.finditer(text):
            start, end = match.span("low")
            if any(a <= start and end <= b for a, b in diluted):
                continue
            low = _number(match.group("low"))
            high = _number(match.group("high")) if match.group("high") else low
            if high < low:
                low, high = high, low
            return low, high, _unit(match.group("unit"))
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_dose_parse.py -q
```

Expected: PASS.

If a case fails, **fix the pattern, never the expected value** — every input in that file is verbatim from a real page, so a disagreement means the pattern is wrong.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest -q
git add src/dose_parse.py tests/test_dose_parse.py
git commit -m "Read a per-dekar dose, and refuse a dilution"
```

---

### Task 4: Parse a whole panel into groups and methods

**Files:**
- Modify: `src/dose_parse.py`
- Test: `tests/test_dose_parse.py`

**Interfaces:**
- Consumes: `parse_dose` (Task 3)
- Produces: `parse_panel(text: str) -> dict[str, dict[str, tuple[float, float, str]]]` — `{group: {method: (low, high, unit)}}`, where group is `"sebze"`, `"meyve"`, `"tarla"` or `"hepsi"`, and method is `"damlama"` or `"yaprak"`. A panel with no per-area dose returns `{}`.

**Background.** The panels come in three grammars, measured 2026-08-22:

- **Group-first, method inline** (~42 products): `Sebzelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, Damlamadan 250 gr/ 1000m² alana uygulanılır. Meyvelerde : …`. **The colon is optional** — `HİGRO CUFİT` and `ZİNCER` write `Sebzelerde Yapraktan …`.
- **Method-first, uppercase, no group** (`HIGRO 8 MN`): `YAPRAKTAN: … DAMLAMA SULAMA: bir dekara (1.000 m²) 2 – 2,5 litre`. With no group named, the dose applies to all three — group `"hepsi"`.
- **Crop-named prose** (`FLY AZOT`): `Tahıllarda ve Hububatlarda kıraç üretimde dekara 200 cc yapraktan 2 uygulama yapılır.` No group heading either, so `"hepsi"`.

Where a clause names no method, the dose is stored under `"damlama"`: 37 of the 42 per-area figures are drip, and the three method-less panels all describe soil or drip application. **That is a documented default, not an inference about the text** — record it in the docstring so a reader can find it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dose_parse.py`:

```python
from src.dose_parse import parse_panel


# Verbatim, HİGRO FUBBY, fetched 2026-08-22.
FUBBY = ("Sebzelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
         "Damlamadan 250 gr/ 1000m² alana uygulanılır. "
         "Meyvelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
         "Damlamadan 250 gr/ 1000m² alana uygulanılır. "
         "Tarla bitkilerinde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
         "Damlamadan 250 gr/ 1000m² alana uygulanılır.")

# Verbatim, HİGRO BARF. Different figures per group - the case that makes
# group segmentation load-bearing rather than decorative.
BARF = ("Çiçek öncesi ve sonrası dönemlerde uygulama dozları : "
        "Sebzelerde : Yapraktan uygulama ile 100 cc / 100 litre suya "
        "Damlama sulama ile 2-2,5 litre / 1000m² (da) "
        "Meyve Ağaçlarında: Yapraktan uygulama ile 200-250 cc / 100 litre suya "
        "Damlama sulama ile 2,5-3 litre / 1000m²(da)")

# Verbatim, BİNGO. Area first, and no method word at all.
BINGO = ("Sebzeler İçin: 1000m² alan için damla sulama ile 2 – 2.5 litre uygulayın. "
         "Meyve Ağaçları İçin: 1000m² alan için damla sulama ile 2 – 3 litre uygulayın. "
         "Tarla Bitkileri İçin: 1000m² alan için damla sulama ile 2 – 2.5 litre uygulayın.")

# Verbatim, HIGRO 8 MN, with the page furniture already cut by Task 1.
MN = ("YAPRAKTAN: Mangan eksikliği görüldüğü her dönemde; 100 litre suya 200 – 250 cc "
      "Higro 8 Mn ilave edilerek uygulama yapılabilir. DAMLAMA SULAMA: Mangan "
      "eksikliğinde bir dekara (1.000 m²) 2 – 2,5 litre dozunda Higro 8 Mn "
      "uygulaması yapılabilir.")

# Verbatim, HİGRO ABS. No dose anywhere.
ABS = ("HİGRO ABS, Kullanılacak çeşitlerde, etikette önerilen uygulama dozajlarına "
       "dikkat edilmesi gerekmektedir. Sadece Topraktan uygulama yapılmalıdır, bu "
       "uyarıya dikkat edilmelidir.")


def test_each_group_gets_its_own_dose():
    parsed = parse_panel(FUBBY)
    assert set(parsed) == {"sebze", "meyve", "tarla"}
    for group in parsed:
        assert parsed[group]["damlama"] == (250.0, 250.0, "gr")


def test_groups_with_different_figures_stay_different():
    """If segmentation silently merged them, a fruit grower would be given the
    vegetable dose - a wrong number that looks entirely plausible."""
    parsed = parse_panel(BARF)
    assert parsed["sebze"]["damlama"] == (2.0, 2.5, "litre")
    assert parsed["meyve"]["damlama"] == (2.5, 3.0, "litre")


def test_the_foliar_dilution_is_not_stored_as_a_dose():
    """Both panels put a 100-litre dilution in the same sentence as the
    per-dekar figure. Only the per-dekar one is a dose."""
    parsed = parse_panel(FUBBY)
    assert "yaprak" not in parsed["sebze"]


def test_a_group_heading_without_a_colon_is_still_a_heading():
    """HİGRO CUFİT and ZİNCER write 'Sebzelerde Yapraktan ...' with no colon;
    a pattern that requires one loses both products."""
    text = ("Sebzelerde Damlamadan 1 litre / 1000m² uygulanır. "
            "Meyvelerde Damlamadan 2 litre / 1000m² uygulanır.")
    parsed = parse_panel(text)
    assert parsed["sebze"]["damlama"] == (1.0, 1.0, "litre")
    assert parsed["meyve"]["damlama"] == (2.0, 2.0, "litre")


def test_an_area_first_clause_is_read():
    parsed = parse_panel(BINGO)
    assert parsed["sebze"]["damlama"] == (2.0, 2.5, "litre")
    assert parsed["meyve"]["damlama"] == (2.0, 3.0, "litre")


def test_a_panel_with_no_group_headings_applies_to_all():
    """HIGRO 8 MN names methods, not groups. With no group stated we must not
    invent one, so the dose is recorded as applying to all of them."""
    parsed = parse_panel(MN)
    assert set(parsed) == {"hepsi"}
    assert parsed["hepsi"]["damlama"] == (2.0, 2.5, "litre")
    assert "yaprak" not in parsed["hepsi"]


def test_a_comma_separates_the_foliar_clause_from_the_drip_one():
    """One sentence, two halves, a comma between them. Without splitting on the
    comma the drip figure is credited to 'yaprak', because that word comes
    first in the sentence."""
    parsed = parse_panel(FUBBY)
    assert parsed["sebze"]["damlama"] == (250.0, 250.0, "gr")
    assert "yaprak" not in parsed["sebze"]


def test_two_figures_for_one_method_become_the_span_they_cover():
    """FLY AZOT publishes 200 cc for dry farming and 250 cc for irrigated in one
    unqualified block. Keeping the first would silently choose between two
    published figures."""
    text = ("kıraç üretimde dekara 200 cc yapraktan uygulanır. "
            "Sulu üretimde dekara 250 cc yapraktan uygulanır.")
    assert parse_panel(text)["hepsi"]["yaprak"] == (200.0, 250.0, "cc")


def test_a_panel_with_no_dose_yields_nothing():
    assert parse_panel(ABS) == {}


def test_an_empty_panel_yields_nothing():
    assert parse_panel("") == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_dose_parse.py -k panel -q
```

Expected: FAIL with `ImportError: cannot import name 'parse_panel'`.

- [ ] **Step 3: Implement it**

Add to `src/dose_parse.py`:

```python
# The three crop groups, as the panels head them. The colon is optional: two
# products write "Sebzelerde Yapraktan ..." and a pattern that requires one
# loses them both.
_GROUPS = (
    ("sebze", r"sebze\w*"),
    ("meyve", r"meyve\s*a[ğg]a[çc]\w*|meyve\w*"),
    ("tarla", r"tarla\s*bitki\w*"),
)
_GROUP_RE = re.compile(
    r"(?P<head>" + "|".join(pattern for _, pattern in _GROUPS) + r")\s*(?:i[çc]in)?\s*:?",
    re.I)

_METHODS = (("damlama", r"damlama\w*|damla\s+sulama"), ("yaprak", r"yaprak\w*"))

# THE COMMA IS A CLAUSE BOUNDARY HERE. The panels write
# "Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, Damlamadan 250 gr/ 1000m²"
# as one sentence, so splitting on . and ; alone leaves the dilution and the
# dose in the same clause and the method attribution picks whichever word came
# first. Measured: without the comma the drip figure is credited to "yaprak".
_CLAUSE = re.compile(r"(?<=[.;,])\s+")


def _widen(existing, dose):
    """Several figures for one group and method: keep the span they cover.

    One product does this - FLY AZOT publishes 200 cc for dry farming and
    250 cc for irrigated in the same unqualified block. Keeping the first would
    silently pick one of two published figures; the span the source's own
    numbers cover states both, and invents nothing between them.

    Units that disagree are NOT merged - there is no conversion from a gram to
    a litre without a density the page never gives - so the first unit wins and
    the other figure is dropped. No panel does this today; if one starts to, the
    converter's coverage report is where it will show up.
    """
    if existing is None:
        return dose
    if existing[2] != dose[2]:
        return existing
    return (min(existing[0], dose[0]), max(existing[1], dose[1]), existing[2])

# No group named anywhere means the dose is not qualified by one. Recording it
# under every group would claim the page said something it did not; this key
# says plainly that it applies to all.
ALL_GROUPS = "hepsi"


def _method_of(clause: str) -> str:
    """Which application method this clause describes.

    Defaults to drip, and that is a DOCUMENTED DEFAULT rather than a reading of
    the text: of the 42 products publishing a per-area figure, 37 attach it to
    drip only, and the three panels naming no method describe soil or drip
    application. Foliar figures are almost always dilutions, which parse_dose
    refuses anyway.
    """
    for key, pattern in _METHODS:
        if re.search(pattern, clause, re.I):
            return key
    return "damlama"


def _segments(text: str) -> list[tuple[str, str]]:
    """Split a panel into (group, text) pairs at its group headings."""
    matches = list(_GROUP_RE.finditer(text))
    if not matches:
        return [(ALL_GROUPS, text)]
    out = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        head = match.group("head").lower()
        group = next(key for key, pattern in _GROUPS
                     if re.fullmatch(pattern, head, re.I))
        out.append((group, text[match.end():end]))
    return out


def parse_panel(text: str) -> dict[str, dict[str, tuple[float, float, str]]]:
    """A whole Uygulama panel as {group: {method: (low, high, unit)}}.

    Only per-dekar figures survive; dilutions are dropped by parse_dose. A
    panel yielding nothing returns an empty mapping, which is how the converter
    learns to report it rather than write an empty row.
    """
    result: dict[str, dict[str, tuple[float, float, str]]] = {}
    for group, segment in _segments(text):
        for clause in _CLAUSE.split(segment):
            dose = parse_dose(clause)
            if dose is None:
                continue
            slot = result.setdefault(group, {})
            method = _method_of(clause)
            slot[method] = _widen(slot.get(method), dose)
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_dose_parse.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest -q
git add src/dose_parse.py tests/test_dose_parse.py
git commit -m "Split a panel by crop group and application method"
```

---

### Task 5: The converter and the committed dose file

**Files:**
- Create: `scripts/build_product_doses.py`
- Create: `data/product_doses.json` (committed)
- Test: `tests/test_build_product_doses.py` (create)

**Interfaces:**
- Consumes: `parse_panel` (Task 4), `data/raw/product_panels.json` (Task 2)
- Produces: `data/product_doses.json` —
  `{"meta": {...}, "products": {name: {group: {method: {"low": f, "high": f, "unit": s}}}}}`

**Background.** This mirrors `scripts/build_crop_norms.py`. Two rules from P2a carry over and both earned their place: the converter must **report by name** every panel it could not parse, because a silent skip is how a coverage collapse ships unnoticed; and the committed file must be a **reproducible output** of the committed converter over the committed input, so a reviewer can re-run and diff rather than take it on trust.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_build_product_doses.py`:

```python
"""Unit tests for scripts/build_product_doses.py (no network)."""

import json

from scripts.build_product_doses import build


PANELS = {
    "HİGRO FUBBY": ("Sebzelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
                    "Damlamadan 250 gr/ 1000m² alana uygulanılır."),
    "HİGRO ABS": ("HİGRO ABS, etikette önerilen uygulama dozajlarına dikkat "
                  "edilmesi gerekmektedir."),
}


def test_a_parsable_panel_becomes_a_row():
    table, unparsed = build(PANELS)
    assert table["HİGRO FUBBY"]["sebze"]["damlama"] == {
        "low": 250.0, "high": 250.0, "unit": "gr"}


def test_an_unparsable_panel_has_no_row_and_is_reported():
    """Absence, never a guessed figure - and never silent, because a silent
    skip is how a coverage collapse ships unnoticed."""
    table, unparsed = build(PANELS)
    assert "HİGRO ABS" not in table
    assert "HİGRO ABS" in unparsed


def test_an_empty_input_yields_an_empty_table_not_an_error():
    table, unparsed = build({})
    assert table == {} and unparsed == []


def test_every_row_has_low_no_greater_than_high():
    """A reversed range would print '3 - 2 litre' and, worse, would mean the
    parser paired two unrelated numbers."""
    table, _ = build(PANELS)
    for groups in table.values():
        for methods in groups.values():
            for dose in methods.values():
                assert dose["low"] <= dose["high"]


def test_the_shipped_file_is_what_the_converter_produces():
    """Re-run the committed converter over the committed raw panels and diff
    against the committed output. This is the check that proves the data file
    was generated, not hand-edited - the one P2a's final review ran by hand."""
    from src.config import DATA_DIR
    raw = json.loads((DATA_DIR / "raw" / "product_panels.json").read_text(encoding="utf-8"))
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    rebuilt, _ = build(raw["panels"])
    assert rebuilt == shipped["products"]


def test_the_shipped_file_still_covers_most_of_the_catalog():
    """A guard on the real data. If a parser change or a site redesign empties
    the file, every other test here keeps passing on its fixtures. Measured
    2026-08-22: 42 of 48 products publish a per-area dose, so the floor is set
    well below that and still catches a collapse."""
    from src.config import DATA_DIR
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    assert len(shipped["products"]) >= 35
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_build_product_doses.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.build_product_doses'`.

- [ ] **Step 3: Implement it**

Create `scripts/build_product_doses.py`:

```python
"""Turn the committed raw panels into data/product_doses.json.

Offline and re-runnable: the input is committed, so anyone can regenerate the
output and diff it. A panel that does not parse produces NO row and is named in
the report - absence is never a guessed figure, and never a silent one.

    python -m scripts.build_product_doses
"""
from __future__ import annotations

import json
from datetime import date

from src.config import DATA_DIR
from src.dose_parse import parse_panel

RAW = DATA_DIR / "raw" / "product_panels.json"
OUT = DATA_DIR / "product_doses.json"


def build(panels: dict[str, str]) -> tuple[dict, list[str]]:
    """(table, unparsed names). Pure - no file access, so it is testable."""
    table: dict = {}
    unparsed: list[str] = []
    for name, text in panels.items():
        parsed = parse_panel(text or "")
        if not parsed:
            unparsed.append(name)
            continue
        table[name] = {
            group: {method: {"low": low, "high": high, "unit": unit}
                    for method, (low, high, unit) in methods.items()}
            for group, methods in parsed.items()
        }
    return table, unparsed


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    table, unparsed = build(raw["panels"])

    OUT.write_text(json.dumps(
        {"meta": {"generated": date.today().isoformat(),
                  "source": raw["meta"],
                  "products_with_a_dose": len(table),
                  "products_read": len(raw["panels"])},
         "products": table},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[doses] {len(table)} of {len(raw['panels'])} products carry a per-area dose")
    print(f"[doses] wrote {OUT}")
    if unparsed:
        print(f"[doses] NO PER-AREA DOSE for {len(unparsed)} products:")
        for name in unparsed:
            print(f"          {name}")


if __name__ == "__main__":
    main()
```

Add `scripts/__init__.py` if it does not already exist, so `from scripts.build_product_doses import build` works.

- [ ] **Step 4: Generate the file and read the report**

```bash
PYTHONIOENCODING=utf-8 python -m scripts.build_product_doses
```

Expected: around **42 of 48** products carry a per-area dose, and the "NO PER-AREA DOSE" list should be about six names long, containing `HİGRO ABS` and `HİGRO® PİNK` (no dose at all) and `HIGRO WETT`, `A.P.P® VIROXYN`, `HİGRO TRACO`, `ZİNCER` (dilution only).

**Read that list.** If it is much longer than six, the parser is losing products and Task 4 is not finished — do not proceed by lowering the coverage floor.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_build_product_doses.py -q
```

Expected: PASS.

- [ ] **Step 6: Spot-check three rows against the live pages by hand**

Open the product pages for `HİGRO BARF`, `BİNGO` and `HIGRO 8 MN` and confirm the numbers in `data/product_doses.json` match what the Uygulama tab says. The converter's tests use fixtures; this is the only step that checks the fixtures resemble reality. Record what you checked in your report.

- [ ] **Step 7: Run the full suite and commit**

```bash
python -m pytest -q
git add scripts/build_product_doses.py scripts/__init__.py data/product_doses.json tests/test_build_product_doses.py
git commit -m "Convert the raw panels into a committed dose table"
```

---

### Task 6: The runtime loader

**Files:**
- Create: `src/doses.py`
- Test: `tests/test_doses.py` (create)

**Interfaces:**
- Consumes: `data/product_doses.json` (Task 5)
- Produces:
  - `available_products() -> tuple[str, ...]` — every product carrying a dose, sorted
  - `lookup(product: str, group: str) -> tuple[Dose, ...]` — every per-area figure for that product and group, each with its method; empty when there is none
  - `@dataclass(frozen=True) Dose: low: float; high: float; unit: str; method: str`

**Background.** This mirrors `src/norms.py`, deliberately, down to the failure behaviour: `_load` is cached for the process and swallows everything, because a broken data file must not break answering.

**The `hepsi` rule.** Task 4 stores a dose under `hepsi` when the panel named no crop group. `lookup` must return a `hepsi` row for **any** group asked for — that is what the key means. It is not a fallback to be reported as one; the page simply did not qualify the figure.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_doses.py`:

```python
"""Unit tests for src/doses.py (no network, no store, no model)."""

import ast
import json
from pathlib import Path

import pytest

from src import doses


def _write(tmp_path, monkeypatch, payload):
    path = tmp_path / "product_doses.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    return path


GOOD = {
    "meta": {"generated": "2026-08-22"},
    "products": {
        "HİGRO FUBBY": {"sebze": {"damlama": {"low": 250.0, "high": 250.0, "unit": "gr"}},
                        "meyve": {"damlama": {"low": 250.0, "high": 250.0, "unit": "gr"}}},
        "HIGRO 8 MN": {"hepsi": {"damlama": {"low": 2.0, "high": 2.5, "unit": "litre"}}},
    },
}


def test_a_dose_is_found_for_its_group(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    found = doses.lookup("HİGRO FUBBY", "sebze")
    assert len(found) == 1
    assert (found[0].low, found[0].high, found[0].unit, found[0].method) == (
        250.0, 250.0, "gr", "damlama")


def test_a_group_the_product_does_not_cover_returns_nothing(tmp_path, monkeypatch):
    """Nothing, never another group's figure: a fruit dose handed to a field
    grower is a wrong number that reads entirely plausibly."""
    _write(tmp_path, monkeypatch, GOOD)
    assert doses.lookup("HİGRO FUBBY", "tarla") == ()


def test_an_unqualified_dose_answers_every_group(tmp_path, monkeypatch):
    """'hepsi' means the page named no crop group, so the figure is not
    qualified by one - it is the answer for whichever group is asked."""
    _write(tmp_path, monkeypatch, GOOD)
    for group in ("sebze", "meyve", "tarla"):
        found = doses.lookup("HIGRO 8 MN", group)
        assert len(found) == 1 and found[0].high == 2.5


def test_an_unknown_product_returns_nothing(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert doses.lookup("YOK BÖYLE BİR ÜRÜN", "sebze") == ()


def test_a_missing_file_is_an_empty_table(tmp_path, monkeypatch):
    """A broken data file must never break answering - fertplan._load's rule."""
    monkeypatch.setattr(doses, "_PATH", tmp_path / "nope.json")
    doses._load.cache_clear()
    assert doses._load() == {}
    assert doses.available_products() == ()
    assert doses.lookup("HİGRO FUBBY", "sebze") == ()


def test_malformed_json_is_an_empty_table(tmp_path, monkeypatch):
    path = tmp_path / "product_doses.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    assert doses._load() == {}


@pytest.mark.parametrize("bad", [
    {"products": {"X": {"sebze": {"damlama": {"low": 3.0, "high": 1.0, "unit": "litre"}}}}},
    {"products": {"X": {"sebze": {"damlama": {"low": None, "high": 1.0, "unit": "litre"}}}}},
    {"products": {"X": {"sebze": {"damlama": {"low": 1.0, "high": 2.0}}}}},
    {"products": {"X": "not a mapping"}},
])
def test_a_malformed_row_is_dropped_whole(tmp_path, monkeypatch, bad):
    """Dropped whole rather than half-loaded: a product carrying one good group
    and one broken one would answer for the first and silently say nothing for
    the second, with no way to tell that apart from a product that simply has
    no figure for it."""
    _write(tmp_path, monkeypatch, bad)
    assert doses.lookup("X", "sebze") == ()


def test_a_non_finite_value_is_refused(tmp_path, monkeypatch):
    """json.loads accepts NaN and Infinity by default, and either would reach a
    purchase quantity as nan."""
    path = tmp_path / "product_doses.json"
    path.write_text('{"products": {"X": {"sebze": {"damlama": '
                    '{"low": NaN, "high": 2.0, "unit": "litre"}}}}}', encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    assert doses.lookup("X", "sebze") == ()


def test_available_products_is_sorted(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert list(doses.available_products()) == sorted(GOOD["products"])


def test_the_all_groups_key_is_shared_with_the_converter():
    """One spelling, one definition. Two that drifted apart would make every
    unqualified dose silently unfindable, with nothing failing."""
    from src import dose_parse
    assert doses.ALL_GROUPS is dose_parse.ALL_GROUPS


def test_doses_does_not_import_the_engine():
    """A data lookup has no business dragging the engine in - the boundary
    src/norms.py and src/budget.py both keep."""
    tree = ast.parse(Path("src/doses.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any("engine" in name for name in imported)
    # src.dose_parse is allowed and expected - it is where ALL_GROUPS lives.
    assert "src.dose_parse" in imported


def test_the_shipped_file_loads_and_carries_products():
    """Against the real data, not a fixture: a converter regression that
    empties the file would leave every fixture-based test above green."""
    doses._load.cache_clear()
    assert len(doses.available_products()) >= 35
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_doses.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.doses'`.

- [ ] **Step 3: Implement it**

Create `src/doses.py`:

```python
"""The manufacturer's published per-dekar doses, and nothing else.

THE DATA IS A FILE, NOT A FETCH. The pages change when the firm edits them, not
on a schedule, and a runtime fetch would put a scrape on the answer path. The
committed file also puts every dose in a diff, which is the only way a reader
can see one change.

A MISSING DOSE IS NEVER 0. Absence returns an empty tuple, because a zero flows
into the multiplication and answers "you need 0 litres" about a purchase.

NOTHING IS INVENTED. A product with no figure for the group asked about returns
nothing - never another group's figure, never another product's, never a
midpoint standing in for a range.

This module imports nothing from src/engine.py, the boundary src/norms.py and
src/budget.py both keep: it is a file in, values out.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.config import DATA_DIR

_PATH = DATA_DIR / "product_doses.json"

# Imported rather than restated: the converter writes this key and the loader
# reads it, and two spellings of "hepsi" that drift apart would make every
# unqualified dose silently unfindable. src.dose_parse is a leaf module - it
# imports only `re` - so this costs the runtime path nothing.
from src.dose_parse import ALL_GROUPS

_METHODS = ("damlama", "yaprak")


@dataclass(frozen=True)
class Dose:
    """One published figure and the application method it belongs to.

    The method travels with the value because a drip figure and a foliar one
    are not interchangeable, and the answer has to say which it is showing.
    """
    low: float
    high: float
    unit: str
    method: str


def _valid_dose(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    low, high, unit = entry.get("low"), entry.get("high"), entry.get("unit")
    if not isinstance(unit, str) or not unit:
        return False
    for value in (low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        # json.loads accepts NaN and Infinity by default; either would reach a
        # purchase quantity as nan.
        if not math.isfinite(value):
            return False
    return low <= high


def _valid_product(groups: object) -> bool:
    if not isinstance(groups, dict) or not groups:
        return False
    for methods in groups.values():
        if not isinstance(methods, dict) or not methods:
            return False
        if not all(_valid_dose(d) for d in methods.values()):
            return False
    return True


@lru_cache(maxsize=1)
def _load() -> dict:
    """Validated products, or an empty table. Never raises.

    A product is dropped WHOLE when any of its groups is malformed rather than
    half-loaded: a product answering for one group and silently not for another
    is indistinguishable from one that simply has no figure there.
    """
    try:
        raw = json.loads(Path(_PATH).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        products = raw.get("products")
        if not isinstance(products, dict):
            return {}
        return {name: groups for name, groups in products.items()
                if isinstance(name, str) and _valid_product(groups)}
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}


def available_products() -> tuple[str, ...]:
    """Every product carrying at least one per-area dose, sorted."""
    return tuple(sorted(_load()))


def lookup(product: str, group: str) -> tuple[Dose, ...]:
    """Every per-area figure this product publishes for this crop group.

    Usually one - 37 of the 42 products with a per-area dose publish it for drip
    irrigation only. The caller prints each with its method rather than choosing
    between them, because the source decides the method, not the farmer.
    """
    groups = _load().get(product)
    if not groups:
        return ()
    methods = groups.get(group) or groups.get(ALL_GROUPS) or {}
    return tuple(
        Dose(low=float(d["low"]), high=float(d["high"]), unit=d["unit"], method=method)
        for method in _METHODS
        if (d := methods.get(method)) is not None
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_doses.py -q
```

Expected: PASS.

- [ ] **Step 5: Read three real lookups**

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0, '.')
from src import doses
print('products with a dose:', len(doses.available_products()))
for name, group in (('HİGRO BARF', 'meyve'), ('HIGRO 8 MN', 'tarla'), ('HİGRO ABS', 'sebze')):
    print(name, '|', group, '->', doses.lookup(name, group))
"
```

Expected: around 42 products; `HİGRO BARF` / `meyve` gives roughly `2,5–3 litre` drip; `HIGRO 8 MN` / `tarla` answers from its `hepsi` row; `HİGRO ABS` gives `()`.

- [ ] **Step 6: Run the full suite and commit**

```bash
python -m pytest -q
git add src/doses.py tests/test_doses.py
git commit -m "Load the dose table, and answer nothing when there is none"
```

- [ ] **Step 7: Record the state**

Append to `.superpowers/sdd/progress.md`: the suite count, how many of the 48 products carry a per-area dose, the names the converter reported as unparsed, and the interface P3b will build on (`doses.lookup`, `doses.available_products`, `Dose`).

```bash
git add .superpowers/sdd/progress.md
git commit -m "Record what P3a shipped and what P3b builds on"
```

---

## Verification before calling this done

- [ ] `python -m pytest -q` — no failures, and the count is up by roughly 40 tests.
- [ ] `python -m scripts.build_product_doses` reproduces `data/product_doses.json` with no diff (`git status` clean afterwards).
- [ ] The converter's "NO PER-AREA DOSE" list is about six names and every one of them was checked by eye against its page.
- [ ] Three rows spot-checked by hand against the live pages (Task 5, Step 6).
- [ ] `doses.lookup` returns `()` — never a zero, never another group's figure — for a product with no figure.
- [ ] No eval run was needed and none was added.
