"""Convert the FAOSTAT bulk archives into `data/world_norms.json`.

The output is keyed by FAO item code rather than by our own crop ids because
our crop list is finer than FAOSTAT's: `Durum Buğdayı` and
`Buğday, Durum Buğdayı Hariç` are both FAO item 15 `Wheat`, and three of our
cabbages are all item 358. Keying by FAO code stores each series once, under
the identity its publisher gave it; `data/crop_fao_map.json` records the
collapse where a person can read it.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date
from pathlib import Path

from scripts import fetch_faostat
from scripts._console import use_utf8_console
from src.config import DATA_DIR

YIELD_ELEMENT = "5412"   # Yield, kg/ha — crops only; livestock yield is 5413/5417/5424
PRICE_ELEMENT = "5532"   # Producer Price, USD/tonne — 5530 is LCU, not comparable
FIRST_YEAR = 2016        # TÜİK's window starts here; earlier years cannot be read beside it
AGGREGATE_AREA_FLOOR = 5000   # `Africa`, `European Union (27)`, `World` …
ITEM_GROUPS = frozenset({1717, 1720, 1723, 1726, 1729, 1732, 1735, 1738,
                         1804, 1841, 17530})  # `Cereals, primary` and friends: sums, not crops
HA_PER_DA = 10           # FAOSTAT publishes per hectare; every surface here uses dekar
KG_PER_TONNE = 1000      # FAOSTAT prices per tonne; TÜİK prices per kilogram

FLAG_MEANINGS = {
    "A": "Official figure",
    "B": "Time series break",
    "E": "Estimated value",
    "I": "Value imputed by a receiving agency",
    "X": "Figure from external organization",
}

OUTPUT = DATA_DIR / "world_norms.json"


def is_crop_item(item_code: int, label: str) -> bool:
    """Reject the group totals and the `n.e.c.` residual buckets.

    `Other vegetables, fresh n.e.c.` is reported by more countries than any
    real crop, but nobody plants it; a number attached to an unnamed mixture
    is not an answer.
    """
    return item_code not in ITEM_GROUPS and "n.e.c" not in label.lower()


def _rows(archive: Path, member: str):
    with zipfile.ZipFile(archive) as bundle:
        with bundle.open(member) as raw:
            stream = io.TextIOWrapper(raw, encoding="utf-8-sig",
                                      errors="replace", newline="")
            reader = csv.reader(stream)
            header = next(reader)
            index = {name: position for position, name in enumerate(header)}
            for row in reader:
                yield row, index


def _clean(code: str) -> str:
    return code.strip().lstrip("'")


def read_yields(archive: Path, member: str):
    """Return `(cells, items, countries, dropped)` from the production archive.

    `dropped` counts the DISTINCT areas and items each filter removed, so the
    output can say what this vintage of the source actually contained rather
    than repeating the rule back at the reader.
    """
    cells: dict[str, dict[str, list]] = {}
    items: dict[int, dict] = {}
    countries: dict[int, dict] = {}
    aggregates: set[int] = set()
    groups: set[int] = set()
    residual: set[int] = set()

    for row, index in _rows(archive, member):
        if row[index["Element Code"]] != YIELD_ELEMENT:
            continue
        area_code = int(row[index["Area Code"]])
        if area_code >= AGGREGATE_AREA_FLOOR:
            aggregates.add(area_code)
            continue
        year = int(row[index["Year"]])
        if year < FIRST_YEAR:
            continue
        item_code = int(row[index["Item Code"]])
        label = row[index["Item"]]
        if not is_crop_item(item_code, label):
            (groups if item_code in ITEM_GROUPS else residual).add(item_code)
            continue

        items.setdefault(item_code, {"label": label,
                                     "cpc": _clean(row[index["Item Code (CPC)"]])})
        countries.setdefault(area_code, {"label": row[index["Area"]],
                                         "m49": _clean(row[index["Area Code (M49)"]])})
        value = float(row[index["Value"]]) / HA_PER_DA
        cells.setdefault(f"{item_code}|{area_code}", {})[str(year)] = [
            round(value, 2), row[index["Flag"]]
        ]
    dropped = {"area_aggregates": len(aggregates),
               "item_groups": len(groups),
               "nec_items": len(residual)}
    return cells, items, countries, dropped


def read_prices(archive: Path, member: str, items: dict[int, dict]):
    """Return price cells for exactly the items that already have a yield.

    The prices archive is not restricted to crops — it prices meat, eggs and
    milk too — so the item list must come from yield and prices must be looked
    up for those items, never the other way round.
    """
    cells: dict[str, dict[str, list]] = {}
    for row, index in _rows(archive, member):
        if row[index["Element Code"]] != PRICE_ELEMENT:
            continue
        item_code = int(row[index["Item Code"]])
        if item_code not in items:
            continue
        area_code = int(row[index["Area Code"]])
        if area_code >= AGGREGATE_AREA_FLOOR:
            continue
        year = int(row[index["Year"]])
        if year < FIRST_YEAR:
            continue
        value = float(row[index["Value"]]) / KG_PER_TONNE
        cells.setdefault(f"{item_code}|{area_code}", {})[str(year)] = [
            round(value, 4), row[index["Flag"]]
        ]
    return cells


def _archive_for(key: str) -> tuple[Path, str]:
    dataset = fetch_faostat.DATASETS[key]
    return fetch_faostat.fetch(key), dataset.member


def build(sources: list[dict]) -> dict:
    prod_archive, prod_member = _archive_for("production")
    price_archive, price_member = _archive_for("prices")

    yields, items, countries, dropped = read_yields(prod_archive, prod_member)
    prices = read_prices(price_archive, price_member, items)

    years = sorted({int(year) for cell in yields.values() for year in cell}
                   | {int(year) for cell in prices.values() for year in cell})
    return {
        "meta": {
            "generated": date.today().isoformat(),
            "years": [years[0], years[-1]] if years else [],
            "units": {"yield": "kg/da", "price": "USD/kg"},
            "sources": sources,
            "flags": FLAG_MEANINGS,
            "dropped": dropped,
        },
        "items": {str(code): items[code] for code in sorted(items)},
        "countries": {str(code): countries[code] for code in sorted(countries)},
        "yield": yields,
        "price": prices,
    }


def main() -> None:
    use_utf8_console()
    sources = []
    for key in fetch_faostat.DATASETS:
        fetch_faostat.fetch(key)
        sources.append(fetch_faostat.describe(key))

    document = build(sources)
    # indent=1 like build_crop_norms.py: this file is committed and refreshed
    # about once a year, and a 2 MB single line makes that diff unreadable.
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"items: {len(document['items'])}")
    print(f"countries: {len(document['countries'])}")
    print(f"yield cells: {sum(len(c) for c in document['yield'].values())}")
    print(f"price cells: {sum(len(c) for c in document['price'].values())}")
    print(f"dropped: {document['meta']['dropped']}")
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
