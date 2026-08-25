"""Turn the hand-obtained TÜİK exports into data/crop_norms.json.

Runs OFFLINE, by hand, about once a year - the figures are published annually and
TÜİK's endpoints resist automation (403 without a browser session; MEDAS does not
answer scripted interaction). So this is a script, not a service.

It fails LOUDLY. Every row it cannot use is printed to stderr and skipped,
because the alternative - a quietly zeroed cell - reaches a user as a confident
wrong figure, which is the defect class the whole budget route was rewritten to
remove.

THE THREE CROP GROUPS DO NOT HAVE THE SAME SHAPE, which is why this reads
measures first and derives second:
  - Tahıllar publish `Verim` directly, in Kg/Dekar.
  - Meyveler publish `Verim` too, but almost all of it is Kg/Meyve Veren AGAC -
    per TREE, not per dekar. Measured 2026-08-25: 61 of the 81 fruit crops in
    these exports publish only the per-tree figure, and 20 (vines, berries,
    herbs) publish Kg/Dekar. So most fruit yield is DERIVED, like a vegetable's.
  - Sebzeler publish no Verim at all: only `Üretim Miktarı` (Ton) and
    `Ekilen Alan` (Dekar), so the yield is DERIVED from the pair.
THE TWO DERIVATIONS ARE NOT EQUALLY SAFE, which is why build() gates one of
them. A vegetable's denominator is `Ekilen Alan` - the whole crop's sown area.
A fruit's is `Toplu Meyveliklerin Alani` - COMPACT ORCHARDS ONLY - while its
numerator counts fruit from every tree in the province, scattered ones
included. Where a fruit is grown as scattered trees the denominator is nearly
empty: Turunc in Adana 2025 is 2.439 tons over 2 dekars, which divides out to
1.219.500 kg/da.
A published figure always wins over a derivable one - never recompute what the
source already states.

Importing src.context.location here is fine even though src/norms.py refuses to:
this never runs in a request, so pulling the engine in costs nothing.

    python -m scripts.build_crop_norms
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import namedtuple
from datetime import date
from pathlib import Path

from scripts._console import use_utf8_console
from src.config import DATA_DIR
from src.context.location import PROVINCES
from src.engine import _normalize_tr

Row = namedtuple("Row", "province crop year measure value")

NATIONAL = "TR"

# TÜİK's spelling -> the spelling src/context/location.py uses. A mismatch does
# not raise; it silently never matches, so it has to be fixed here.
_RENAME = {"Hakkari": "Hakkâri"}

# The row label carries the measure, the product code, the name and the unit:
#   "Verim ve 01.11.31.00.01. (Arpa (Biralık)) - Kg/Dekar"
# The name group is greedy so a nested parenthesis stays inside the name.
_LABEL = re.compile(r"^(?P<measure>.+?) ve [\d.]+\s*\((?P<name>.+)\)(?: - (?P<unit>.+))?$")
# The price topic's labels carry only the code, the name and the unit.
_BARE_LABEL = re.compile(r"^[\d.]+\s*\((?P<name>.+)\)(?: - (?P<unit>.+))?$")

_MEASURES = {
    "verim": "verim",
    "ekilen alan": "alan",
    "toplu meyveliklerin alani": "alan",
    "uretim miktari": "uretim",
    # The price topic writes no measure into the row label - the measure IS the
    # Olcum, which sits in column 0. So this name is matched there instead.
    "bitkisel urun fiyatlari (tl)": "fiyat",
}

# The unit each measure must carry to be usable. Fruit `Verim` comes in TWO
# units: Kg/Dekar for vines, berries and herbs, and Kg/Meyve Veren Agac for
# every orchard tree - TUIK publishes NO per-dekar yield for apple, walnut,
# citrus, quince and the rest. The per-tree figure is read under `verim_agac`,
# a measure of its own: build() uses it as EVIDENCE for the density gate and
# never writes it as a yield, because scaling it to a dekar needs a planting
# density nobody published.
_UNITS = {"verim": {"kg/dekar"}, "verim_agac": {"kg/meyve veren agac"},
          "alan": {"dekar"}, "uretim": {"ton"},
          "fiyat": {"kilogram"}}

# How many decimals each measure keeps. A yield is tonnes over dekars, both
# rounded at the source, so 0.1 kg/da is already finer than the data. A PRICE is
# different: rounding 7.94 TL/kg to 7.9 puts a 0.5% error into every revenue
# figure computed from it.
_DECIMALS = {"verim": 1, "fiyat": 2}

SOURCES = {
    "yield": {"name": "TÜİK Bitkisel Üretim İstatistikleri",
              "level": "İBBS3 (İl Düzeyi)", "obtained": "2026-08-18"},
    "price": {"name": "TÜİK Tarımsal Ürün Fiyatları ve Üretim Değerleri",
              "olcum": "Bitkisel ürün fiyatları (TL)", "kirilim": "TAORBA",
              "level": "İBBS3 (İl Düzeyi)", "obtained": "2026-08-19"},
}


def parse_label(label: str, olcum: str = "") -> tuple[str, str, str] | None:
    """(measure, crop name, unit) or None when unusable.

    Two shapes, because the two topics disagree about where the measure lives:
      "Verim ve 01.11.11.00.00. (Durum Bugdayi) - Kg/Dekar"   <- in the label
      "01.11.11.00.00. (Durum Bugdayi) - Kilogram"            <- in the Olcum
    The label wins when it carries its own measure, so a production row can
    never be reinterpreted by whatever column 0 happens to say.

    Returns None both for a label this script does not recognise and for a
    recognised measure carried in a unit we cannot use - see _UNITS.
    """
    m = _LABEL.match(label.strip())
    if m:
        measure = _MEASURES.get(_normalize_tr(m.group("measure")))
    else:
        m = _BARE_LABEL.match(label.strip())
        measure = _MEASURES.get(_normalize_tr(olcum)) if m else None
    if m is None or measure is None:
        return None
    unit = (m.group("unit") or "").strip()
    folded = _normalize_tr(unit)
    # A `Verim` row in the per-tree unit is not an unusable row - it is a
    # different measure wearing the same label, and the gate in build() cannot
    # run without it.
    if measure == "verim" and folded in _UNITS["verim_agac"]:
        measure = "verim_agac"
    if folded not in _UNITS[measure]:
        return None
    return measure, m.group("name").strip(), unit


def _number(raw: str) -> float | None:
    """A cell to float, or None.

    The exports use a DOT decimal separator ("176.0"), not Turkish formatting -
    reading them as Turkish would turn 176.0 into 1760, every yield ten times too
    big and silently so. Non-finite values are refused for the same reason
    src/norms.py refuses them: they are not zero, but they are not a norm either.
    """
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def read_export(path: Path):
    """Yield Row(...) from one MEDAS CSV.

    Format, recorded in docs/superpowers/2026-08-17-tuik-export-findings.md:
    UTF-8 with BOM, '|' delimited, two header rows, provinces from column 3 on
    carrying a '-<plaka>' suffix, and a sticky crop label in column 1.
    """
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh, delimiter="|"))
    if len(rows) < 3:
        print(f"skipped {path.name}: too short to be an export", file=sys.stderr)
        return
    header = rows[1]
    provinces = [re.sub(r"-\d+$", "", c).strip() for c in header[3:]]
    label = None
    olcum = ""          # column 0, sticky; carries the measure in the price topic
    unrecognised = set()
    for row in rows[2:]:
        if len(row) < 4:
            continue
        if row[0].strip():
            olcum = row[0].strip()
        if row[1].strip():
            label = row[1].strip()
        if not label or not row[2].strip().isdigit():
            continue
        parsed = parse_label(label, olcum)
        if parsed is None:
            if label not in unrecognised:
                unrecognised.add(label)
                print(f"skipped unusable measure/unit in {path.name}: {label!r}",
                      file=sys.stderr)
            continue
        measure, crop, _unit = parsed
        year = int(row[2].strip())
        for province, cell in zip(provinces, row[3:]):
            if not province:
                continue
            value = _number(cell)
            if value is None:
                if cell.strip():
                    print(f"skipped unparseable cell in {path.name}: "
                          f"{crop} / {province} / {year}: {cell!r}", file=sys.stderr)
                continue
            yield Row(province, crop, year, measure, value)


def build(rows) -> dict:
    """Group Row(...) into the schema src/norms.py validates.

    Format-independent on purpose: read_export does the parsing, this does the
    shaping, and only this half can be tested without a real export.
    """
    known = set(PROVINCES)
    rows = list(rows)
    years = sorted({r.year for r in rows})
    index = {y: i for i, y in enumerate(years)}

    seen: dict[str, dict] = {}      # crop_id -> measure -> province -> {year: value}
    labels: dict[str, str] = {}
    unknown_reported: set[str] = set()

    for r in rows:
        province = _RENAME.get(r.province, r.province)
        if province not in known:
            if province not in unknown_reported:
                unknown_reported.add(province)
                print(f"skipped unknown province: {r.province!r}", file=sys.stderr)
            continue
        crop_id = _normalize_tr(r.crop)
        labels.setdefault(crop_id, r.crop)
        by_measure = seen.setdefault(crop_id, {})
        by_measure.setdefault(r.measure, {}).setdefault(province, {})[r.year] = r.value

    crops: dict[str, dict] = {}
    for crop_id, by_measure in seen.items():
        published = by_measure.get("verim", {})
        uretim = by_measure.get("uretim", {})
        alan = by_measure.get("alan", {})

        yields: dict[str, list] = {}
        for province in set(published) | (set(uretim) & set(alan)):
            series: list[float | None] = [None] * len(years)
            for year, i in index.items():
                value = published.get(province, {}).get(year)
                if value is None:
                    # Vegetables publish no Verim; derive it from the pair, and
                    # only where BOTH halves exist. Ton -> kg is the 1000.
                    tons = uretim.get(province, {}).get(year)
                    dekar = alan.get(province, {}).get(year)
                    if tons is not None and dekar:
                        value = tons * 1000.0 / dekar
                if value:
                    # `if value` and not `is not None`: a yield of exactly 0 is
                    # refused. The exports carry zeros in 0.4-12% of cells and
                    # there is no way to tell a true zero from a missing marker -
                    # but neither reading is a norm. Prefilling 0 would tell a
                    # farmer to expect no harvest and compute an income of zero,
                    # which is the confident-wrong-answer this whole route exists
                    # to prevent. No norm is the honest outcome.
                    #
                    # One decimal: a derived yield is tonnes over dekars, both
                    # already rounded at the source, so thirteen significant
                    # digits would advertise a precision nobody has.
                    series[i] = round(value, _DECIMALS["verim"])
            if any(v is not None for v in series):
                yields[province] = series

        prices: dict[str, list] = {}
        for province, by_year in by_measure.get("fiyat", {}).items():
            series = [None] * len(years)
            for year, i in index.items():
                value = by_year.get(year)
                if value:      # a price of 0 is refused for the same reason
                    series[i] = round(value, _DECIMALS["fiyat"])
            if any(v is not None for v in series):
                prices[province] = series

        # The exports are province-level only, so no national figure was
        # published. The row is required by src/norms.py and ships EMPTY rather
        # than averaged: a mean of the provinces is a number nobody published.
        yields.setdefault(NATIONAL, [None] * len(years))
        prices.setdefault(NATIONAL, [None] * len(years))

        crops[crop_id] = {
            "label": labels[crop_id],
            "yield_kg_da": {
                "scope": "il" if any(k != NATIONAL for k in yields) else "tr",
                **yields,
            },
            "price_tl_kg": {
                "scope": "il" if any(k != NATIONAL for k in prices) else "tr",
                **prices,
            },
        }

    return {"meta": {"generated": date.today().isoformat(),
                     "years": years, "sources": SOURCES},
            "crops": crops}


def main() -> None:
    use_utf8_console()
    rows = []
    for path in sorted((DATA_DIR / "raw").glob("*.csv")):
        rows.extend(read_export(path))
        print(f"read {path.name}", file=sys.stderr)
    out = DATA_DIR / "crop_norms.json"
    data = build(rows)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(data['crops'])} crops, years {data['meta']['years']}")


if __name__ == "__main__":
    main()
