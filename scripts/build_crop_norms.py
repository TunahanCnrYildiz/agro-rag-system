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
  - Tahıllar and Meyveler publish `Verim` directly, in Kg/Dekar.
  - Sebzeler publish no Verim at all: only `Üretim Miktarı` (Ton) and
    `Ekilen Alan` (Dekar), so the yield is DERIVED from the pair.
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

_MEASURES = {
    "verim": "verim",
    "ekilen alan": "alan",
    "toplu meyveliklerin alani": "alan",
    "uretim miktari": "uretim",
}

# The unit each measure must carry to be usable. Fruit `Verim` comes in TWO
# units: Kg/Dekar for vines and berries, and Kg/Meyve Veren Agac for orchard
# trees - TUIK publishes no per-dekar yield for apple, walnut, citrus and the
# rest. A per-tree figure written into a per-dekar field would be silently wrong
# by more than an order of magnitude, so it is refused here rather than scaled
# by a tree count nobody supplied.
_UNITS = {"verim": {"kg/dekar"}, "alan": {"dekar"}, "uretim": {"ton"}}

SOURCES = {
    "yield": {"name": "TÜİK Bitkisel Üretim İstatistikleri",
              "level": "İBBS3 (İl Düzeyi)", "obtained": "2026-08-18"},
    "price": {"name": "TÜİK Tarımsal Ürün Fiyatları ve Üretim Değerleri",
              "obtained": None},
}


def parse_label(label: str) -> tuple[str, str, str] | None:
    """('verim'|'alan'|'uretim', crop name, unit) or None when unusable.

    Returns None both for a label this script does not recognise and for a
    recognised measure carried in a unit we cannot use - see _UNITS.
    """
    m = _LABEL.match(label.strip())
    if not m:
        return None
    measure = _MEASURES.get(_normalize_tr(m.group("measure")))
    if measure is None:
        return None
    unit = (m.group("unit") or "").strip()
    if _normalize_tr(unit) not in _UNITS[measure]:
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
    unrecognised = set()
    for row in rows[2:]:
        if len(row) < 4:
            continue
        if row[1].strip():
            label = row[1].strip()
        if not label or not row[2].strip().isdigit():
            continue
        parsed = parse_label(label)
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
                    series[i] = round(value, 1)
            if any(v is not None for v in series):
                yields[province] = series

        # The exports are province-level only, so no national figure was
        # published. The row is required by src/norms.py and ships EMPTY rather
        # than averaged: a mean of the provinces is a number nobody published.
        yields.setdefault(NATIONAL, [None] * len(years))

        crops[crop_id] = {
            "label": labels[crop_id],
            "yield_kg_da": {
                "scope": "il" if any(k != NATIONAL for k in yields) else "tr",
                **yields,
            },
            # No price export yet. An all-null series is honest and keeps the
            # crop loadable; lookup() simply returns no price norm.
            "price_tl_kg": {"scope": "tr", NATIONAL: [None] * len(years)},
        }

    return {"meta": {"generated": date.today().isoformat(),
                     "years": years, "sources": SOURCES},
            "crops": crops}


def main() -> None:
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
