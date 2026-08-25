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

from scripts._console import use_utf8_console
from src.config import DATA_DIR, PRODUCTS_JSON
from src.scrape_utils import REQUEST_DELAY_SECONDS, extract_tab_panels, fetch, make_session

OUT = DATA_DIR / "raw" / "product_panels.json"
DOSE_TAB = "Uygulama"


def main() -> None:
    use_utf8_console()
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
