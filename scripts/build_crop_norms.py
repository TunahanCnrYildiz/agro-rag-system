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
import statistics
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

REVIEW = DATA_DIR / "crop_area_review.json"


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


# THE BAND IS ARGUED, NOT DISCOVERED. Measured over the 16.392 derived fruit
# cells, the implied density is unimodal - median 40 trees/da, which is a
# 5m x 5m orchard grid - with a long, smoothly decaying tail and NO natural cut
# to read a threshold off. So the bounds rest on geometry, not on horticultural
# judgement nobody here has:
#   444 trees/da is a 1,5m x 1,5m grid, 2,25 m2 of ground per tree. A
#   fruit-bearing tree does not stand at that spacing, so the recorded area
#   cannot be the ground the production came from.
#   Below 5 trees/da the area is recorded and almost nothing comes off it - an
#   orchard not yet in bearing. That understates the yield rather than inflating
#   it: safer, still wrong in a revenue line.
# THIS RAISES THE FLOOR ON WRONGNESS, IT DOES NOT REMOVE IT. A mulberry cell
# implying 200 trees/da is still mostly scattered trees and still passes.
_MAX_TREES_PER_DA = 444
_MIN_TREES_PER_DA = 5

# A zero recorded area implies a density no bound can hold. It enters the
# PROVINCE median as this and never the CROP median - see both docstrings for
# why the same figure belongs in one and not the other. On an odd-length list
# the median is a placement and an unbounded member is never touched; on an
# even one it is averaged with its neighbour, and that average is itself
# unbounded. Either way an unbounded member ranks above every finite one, so
# it can only push the median UP, never down - but whether it reaches the
# bound depends on how many zero years the province carries against how many
# finite ones. A province with more finite years than zero can still be
# judged sound: measured, 40 of the 336 zero-carrying (crop, province) pairs
# land under the bound and keep serving.
_UNBOUNDED_DENSITY = float("inf")


def _density_verdict(tons: float, dekar: float,
                     per_tree: float | None) -> str | None:
    """Why this derived cell must not be written, or None to write it.

    All three numbers are TUIK's own. Nothing is assumed about the crop.
    """
    if not per_tree:
        # This crop publishes per-tree yields, so the cell SHOULD have been
        # judged - this province-year simply carries nothing to judge it with.
        # Refused rather than written unchecked: an unjudged figure and a judged
        # one must not look the same in the output.
        return "no_per_tree_figure"
    trees_per_da = (tons * 1000.0 / per_tree) / dekar
    if trees_per_da > _MAX_TREES_PER_DA:
        return "density_above_ceiling"
    if trees_per_da < _MIN_TREES_PER_DA:
        return "density_below_floor"
    return None


# A median over one or two provincial administrations describes THEM, not the
# crop, so it cannot carry a statement about how the crop is RECORDED nationally.
# The cut is insensitive rather than tuned: the crops whose median clears the
# ceiling rest on 29, 18 and 2 provinces, so every minimum from 3 to 18 selects
# the same two.
_MIN_PROVINCES_TO_JUDGE_A_CROP = 10


def _area_never_orchard(published: dict, uretim: dict, alan: dict,
                        per_tree: dict) -> bool:
    """Whether this crop's area column fails to describe it ANYWHERE.

    THE CEILING ONE LEVEL UP, AND NO NEW CONSTANT. The cell gate asks whether
    THIS province's area can hold its trees. When the MEDIAN province cannot,
    the question was never about a province: `Toplu Meyveliklerin Alani` is not
    recording this crop's ground at all, and the cells that happen to fall under
    the bound are no sounder than the ones above it - they are the same
    bookkeeping, less extreme.

    Measured on the real exports: kizilcik's median province implies 837
    trees/da (1,2 m2 of ground per tree) and igde's 727 (1,4 m2). Both are past
    the very bound `_MAX_TREES_PER_DA` already rests on. Their served yields
    read 12.312 and 11.571 kg/da, which no cornelian cherry or oleaster grows.

    The MEDIAN, so that a handful of scattered-tree provinces costs those cells
    and never the crop - apple is recorded properly nearly everywhere and must
    survive whole.

    A YEAR OF ZERO RECORDED AREA DOES NOT COUNT HERE, though it does in
    `_province_area_never_orchard`. The two rules ask different questions. That
    one asks whether a province records this crop's ground, and a zero answers
    it. This one asks whether the COLUMN describes the crop anywhere, and
    zeros concentrated in scattered-tree provinces answer a question about those
    provinces. Measured: counting them here removes 264 served cells including
    the whole of Musmula/Bursa - 24 to 63 trees/da, an area growing smoothly
    from 127 to 1.389 dekars, not one zero year of its own - which is exactly
    the "apple must survive whole" failure the median was chosen to prevent.
    """
    densities, provinces = [], set()
    for province, by_year in uretim.items():
        for year, tons in by_year.items():
            dekar = alan.get(province, {}).get(year)
            tree = per_tree.get(province, {}).get(year)
            if (tons and dekar and tree
                    and published.get(province, {}).get(year) is None):
                densities.append((tons * 1000.0 / tree) / dekar)
                provinces.add(province)
    if len(provinces) < _MIN_PROVINCES_TO_JUDGE_A_CROP:
        return False
    return statistics.median(densities) > _MAX_TREES_PER_DA


# A median over one or two years describes THOSE YEARS, not how the province
# keeps its books, and the cell gate already judges them one by one.
_MIN_YEARS_TO_JUDGE_A_PROVINCE = 3


def _province_area_never_orchard(province: str, published: dict, uretim: dict,
                                 alan: dict, per_tree: dict) -> bool:
    """Whether THIS province's area column fails to record THIS crop's ground.

    THE MIDDLE GRANULARITY, AND STILL NO NEW CONSTANT. `_density_verdict` asks
    the geometric question of one cell and `_area_never_orchard` asks it of a
    whole crop; between them sits the case both miss - a crop that is recorded
    properly nearly everywhere, in a province that records it as scattered
    trees every single year.

    Neither existing rule can reach it. The cells are individually under the
    bound, and `_ceiling_shadow` only falls BACKWARDS, so a province whose bad
    years all precede a merely-less-bad recent one keeps serving that recent
    one. Measured: 165 of 1.917 (crop, province) pairs have a median year past
    the bound; the cell gate and the shadow already take most, so this removes
    14 SERVED cells - Erik/Tunceli at 0,8 m2 of ground per tree, Incir/Karaman
    at 0,4, Ayva/Hatay at 0,9.

    THE MEDIAN, so one wild year costs that year and never the province.

    NOTE WHAT THIS STILL DOES NOT REACH: Ayva/Karabük's median implies 2,4 m2
    per tree - past what any quince stands at, but not past the 2,25 m2 this
    bound already permits, so it survives and keeps serving 13.419 kg/da.
    Closing it means a bound somewhere in 2,25-4 m2, which sweeps 44 served
    cells and would condemn spacings that are real for super-spindle apple
    (~3,15 m2). That is the per-crop-bound path measured and closed on
    2026-08-28; see docs/superpowers/2026-08-28-ceiling-findings.md.

    A YEAR OF ZERO RECORDED AREA COUNTS, as an unbounded density. It is the
    most extreme possible answer to the question this rule asks, and leaving it
    out let a province book six consecutive years of fruit against no orchard
    at all and still be judged sound on the three years that carried an area.

    IT ALSO COUNTS TOWARD `_MIN_YEARS_TO_JUDGE_A_PROVINCE`, not only toward the
    median. A province with one real area-year and two zero years used to fall
    under the threshold on that single density and be presumed sound; now the
    two zeros supply the other two years, because a zero-area year is evidence
    about what the column records, not an absence of evidence.
    """
    densities = []
    for year, tons in uretim.get(province, {}).items():
        dekar = alan.get(province, {}).get(year)
        tree = per_tree.get(province, {}).get(year)
        if not (tons and tree
                and published.get(province, {}).get(year) is None):
            continue
        if dekar == 0:
            densities.append(_UNBOUNDED_DENSITY)
        elif dekar:
            densities.append((tons * 1000.0 / tree) / dekar)
    if len(densities) < _MIN_YEARS_TO_JUDGE_A_PROVINCE:
        return False
    return statistics.median(densities) > _MAX_TREES_PER_DA


def _ceiling_shadow(province: str, published: dict, uretim: dict, alan: dict,
                    per_tree: dict, years) -> int | None:
    """The LATEST year the ceiling refuses this province, or None.

    WHY A REFUSAL REACHES BACKWARDS. The ceiling does not say "this year's
    figure is odd", it says the recorded area is not the ground the production
    came off - the province books scattered trees' fruit against a compact
    orchard's dekars. That is how the province KEEPS ITS BOOKS, not what the
    weather did, so it condemns the earlier derived cells too.

    Without this, refusing the recent cells only moves the damage: src/norms.py
    walks back to the most recent surviving year, and the year it lands on is
    the one that squeaked under the ceiling with the SAME broken denominator.
    Measured on the real exports - Turunc in Adana is refused in 2022, 2023,
    2024 and 2025, and 2017 was served instead at 405 trees/da: 23.098 kg/da,
    a citrus yield ten times any real one, carrying no five-year range to warn
    anyone because walking back that far leaves too few prior years to build one.

    `density_above_ceiling` casts a shadow, and so does a zero recorded area -
    the same statement with the denominator gone entirely. The others do not:
    `no_per_tree_figure` means TUIK has not published that year's per-tree
    survey yet - half of those sit in the freshest year for exactly that reason
    - and says nothing about the denominator. `density_below_floor` understates
    rather than inflates. An area of zero with no production booked against it
    says the province grew none of the crop, which is not a claim about the
    area column either.

    A PUBLISHED kg/dekar figure is never shadowed: the argument is about a
    denominator this script chose, and a published yield does not use one.

    LATEST, not earliest. The refusals are not one run at the recent end - Dut
    in Mugla is refused in 2016-2018 and again from 2020 on, because the
    recorded area lurches between 1, 46, 39 and 12 dekars. Shadowing only what
    precedes the FIRST refusal leaves the 2019 cell sitting in the hole between
    them, which is precisely the one src/norms.py walks back to.
    """
    refused = []
    for year in years:
        if published.get(province, {}).get(year) is not None:
            continue
        tons = uretim.get(province, {}).get(year)
        dekar = alan.get(province, {}).get(year)
        if tons is None:
            continue
        if dekar == 0:
            # A zero recorded area cannot be divided into, so no verdict is
            # computed - but the statement it makes is the ceiling's, at its
            # limit. Only when production was booked AGAINST it: production and
            # area both at zero say the province grew none that year, which is
            # a claim about the crop and not about the area column.
            if tons:
                refused.append(year)
        elif dekar and _density_verdict(
                tons, dekar, per_tree.get(province, {}).get(year)
        ) == "density_above_ceiling":
            refused.append(year)
    return max(refused, default=None)


def build(rows, not_field_area=(), area_excludes_the_trees=()) -> dict:
    """Group Row(...) into the schema src/norms.py validates.

    Format-independent on purpose: read_export does the parsing, this does the
    shaping, and only this half can be tested without a real export.

    TWO REVIEWED LISTS, AND THEY SAY DIFFERENT THINGS. Both answer a question no
    published number can settle, and both are recorded under their own reason so
    the committed audit does not attribute one crop's finding to another:

      `not_field_area` - the recorded area is the WRONG KIND of surface.
        Mushroom's `Ekilen Alan` is a building's footprint and its beds are
        stacked in tiers, so production over area is not a yield in any unit.
        Nothing survives: not the derived figure, not a published one.

      `area_excludes_the_trees` - the area is the right kind and INCOMPLETE.
        `Toplu Meyveliklerin Alani` counts compact orchards while `Uretim
        Miktari` counts fruit from every tree in the province. Where a crop is
        grown as scattered trees almost everywhere, the ratio is not a yield -
        but a PUBLISHED Kg/Dekar figure still is, so only the derived half goes.
        This is what the density gate cannot see: it judges cell by cell, and
        `_area_never_orchard` only reaches crops whose median already clears the
        geometric ceiling. Dut's median implies 3,0 m2 of ground per tree, which
        no fruiting mulberry stands at, yet it sits UNDER that bound.

    Prices are untouched in both. A reviewed crop that no longer appears in the
    exports RAISES rather than sitting in the file looking like coverage.
    """
    known = set(PROVINCES)
    rows = list(rows)
    refused: list[dict] = []
    excluded = {_normalize_tr(name): name for name in not_field_area}
    derived_only = {_normalize_tr(name): name
                    for name in area_excludes_the_trees}
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

    stale = sorted(name for crop_id, name in (excluded | derived_only).items()
                   if crop_id not in seen)
    if stale:
        raise ValueError(
            f"data/crop_area_review.json reviews {stale}, which the exports do "
            f"not carry - a review of nothing, sitting in the file looking like "
            f"coverage")

    crops: dict[str, dict] = {}
    for crop_id, by_measure in seen.items():
        published = by_measure.get("verim", {})
        uretim = by_measure.get("uretim", {})
        alan = by_measure.get("alan", {})
        # A tree crop is one TUIK publishes a per-tree yield for ANYWHERE. That
        # is a property of the CROP, not of the cell, and it is what says "this
        # crop's area column is Toplu Meyveliklerin Alani". Vegetables never
        # publish one, so the gate below cannot touch them - and must not:
        # their denominator really is the whole crop's sown area.
        per_tree = by_measure.get("verim_agac", {})

        # A reviewed crop yields nothing at all: not a gated figure, not a
        # figure with a caveat. Its price survives - a mushroom price is a price.
        if crop_id in excluded:
            published, uretim, alan = {}, {}, {}
            refused.append({"crop": labels[crop_id], "province": "*",
                            "year": 0, "reason": "area_is_not_field"})

        # Reviewed as scattered-tree: the derived half goes, a published
        # Kg/Dekar figure stays. Recorded under its OWN reason - mulberry's
        # finding is not mushroom's.
        if crop_id in derived_only:
            uretim, alan = {}, {}
            refused.append({"crop": labels[crop_id], "province": "*",
                            "year": 0, "reason": "area_excludes_the_trees"})

        # Only the DERIVED half is dropped: the finding is about the area
        # column, and a published Kg/Dekar figure does not use one.
        if per_tree and _area_never_orchard(published, uretim, alan, per_tree):
            uretim, alan = {}, {}
            refused.append({"crop": labels[crop_id], "province": "*",
                            "year": 0,
                            "reason": "crop_median_density_above_ceiling"})

        yields: dict[str, list] = {}
        for province in sorted(set(published) | (set(uretim) & set(alan))):
            # Verdicts before values: a ceiling refusal condemns every EARLIER
            # derived cell in this province, so it has to be known before one
            # can be written.
            shadow = (_ceiling_shadow(province, published, uretim, alan,
                                      per_tree, index) if per_tree else None)
            # Recorded once for the province, not once per cell - the finding
            # is about the column, and a per-cell line would say the wrong thing.
            no_orchard = bool(per_tree) and _province_area_never_orchard(
                province, published, uretim, alan, per_tree)
            if no_orchard:
                refused.append({"crop": labels[crop_id], "province": province,
                                "year": 0,
                                "reason": "province_median_density_above_ceiling"})
            series: list[float | None] = [None] * len(years)
            for year, i in index.items():
                value = published.get(province, {}).get(year)
                if value == 0:
                    # TUIK published a yield of exactly zero. Refused for the
                    # reason argued at `if value` below - a true zero and a
                    # missing marker are indistinguishable here, and neither
                    # reading is a norm - and recorded, so the file does not
                    # present a discarded figure as a crop nobody grows.
                    refused.append({"crop": labels[crop_id],
                                    "province": province, "year": year,
                                    "reason": "published_yield_is_zero"})
                    continue
                if value is None:
                    # Vegetables publish no Verim, and most fruits publish only
                    # a per-tree one; derive from the pair, and only where BOTH
                    # halves exist. Ton -> kg is the 1000.
                    tons = uretim.get(province, {}).get(year)
                    dekar = alan.get(province, {}).get(year)
                    if no_orchard:
                        continue          # already refused, once, above
                    if tons and dekar == 0:
                        # THE CEILING'S OWN FINDING AT ITS LIMIT. The province
                        # books fruit from scattered trees against a compact
                        # orchard's dekars, and here those dekars reached zero:
                        # the implied density is past every bound rather than
                        # merely past 444. The cell was already dropped - by the
                        # truthiness of `dekar` on the next line, which forms no
                        # verdict and leaves no trace.
                        #
                        # Recorded whether or not the crop publishes a per-tree
                        # figure: the refusal is that nothing can be divided by
                        # zero, which is as true of a vegetable's `Ekilen Alan`.
                        # Today every such cell is a tree crop, so this costs
                        # nothing and closes the hole a future export would fall
                        # into.
                        refused.append({"crop": labels[crop_id],
                                        "province": province,
                                        "year": year,
                                        "reason": "area_is_zero"})
                        continue
                    if tons is not None and dekar:
                        reason = (_density_verdict(
                                      tons, dekar,
                                      per_tree.get(province, {}).get(year))
                                  if per_tree else None)
                        if reason is None and shadow is not None and year < shadow:
                            reason = "shadowed_by_ceiling_refusal"
                        if reason is not None:
                            refused.append({"crop": labels[crop_id],
                                            "province": province,
                                            "year": year,
                                            "reason": reason})
                            continue
                        value = tons * 1000.0 / dekar
                if value:
                    # `if value` and not `is not None`: a yield of exactly 0 is
                    # refused, and the `elif` below records it. The exports
                    # carry zeros in 0.4-12% of cells and there is no way to
                    # tell a true zero from a missing marker - but neither
                    # reading is a norm. Prefilling 0 would tell a farmer to
                    # expect no harvest and compute an income of zero, which is
                    # the confident-wrong-answer this whole route exists to
                    # prevent. No norm is the honest outcome.
                    #
                    # One decimal: a derived yield is tonnes over dekars, both
                    # already rounded at the source, so thirteen significant
                    # digits would advertise a precision nobody has.
                    series[i] = round(value, _DECIMALS["verim"])
                elif value is not None:
                    # A derived 0,0: an area is recorded and nothing came off
                    # it. Most tree crops never arrive here either - a
                    # zero-production year carries no per-tree survey of its
                    # own, so `no_per_tree_figure` takes it one step earlier
                    # as an unjudged cell - which leaves this reason for the
                    # crops that publish no per-tree figure anywhere.
                    # `value is not None` keeps the genuinely absent cell
                    # silent: nothing was thrown out there.
                    refused.append({"crop": labels[crop_id],
                                    "province": province, "year": year,
                                    "reason": "production_is_zero"})
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

        # The published per-tree yield, as a measure rather than as evidence.
        # NO GATE RUNS ON IT, and that is the whole point: every rule in this
        # file defends a denominator this script chose, and this figure has
        # none. The reviewed exclusions above do not reach it either - Dut is
        # reviewed out of the DERIVED yield because its AREA does not count
        # the trees its production does, which says nothing about kg per tree.
        trees: dict[str, list] = {}
        for province, by_year in per_tree.items():
            series = [None] * len(years)
            for year, i in index.items():
                value = by_year.get(year)
                if value:      # a zero is refused for the same reason as above
                    series[i] = round(value, _DECIMALS["verim"])
            if any(v is not None for v in series):
                trees[province] = series

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
        # Added only for crops that publish one. An empty measure on every
        # field crop would be noise in the file and in every diff of it.
        if trees:
            trees.setdefault(NATIONAL, [None] * len(years))
            crops[crop_id]["yield_kg_tree"] = {
                "scope": "il" if any(k != NATIONAL for k in trees) else "tr",
                **trees,
            }

    refused.sort(key=lambda r: (r["crop"], r["province"], r["year"]))
    counts: dict[str, int] = {}
    for cell in refused:
        counts[cell["reason"]] = counts.get(cell["reason"], 0) + 1
    for cell in refused:
        print(f"refused yield cell: {cell['crop']} / {cell['province']} / "
              f"{cell['year']}: {cell['reason']}", file=sys.stderr)

    return {"meta": {"generated": date.today().isoformat(),
                     "years": years, "sources": SOURCES,
                     # The finding travels WITH the file. Without this record
                     # there is no committed way to tell a province that grows
                     # none of a crop from one whose figure we threw out.
                     "refused_yield_cells": {"counts": counts,
                                             "cells": refused}},
            "crops": crops}


def main() -> None:
    use_utf8_console()
    rows = []
    for path in sorted((DATA_DIR / "raw").glob("*.csv")):
        rows.extend(read_export(path))
        print(f"read {path.name}", file=sys.stderr)
    out = DATA_DIR / "crop_norms.json"
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    data = build(rows, not_field_area=review["not_field_area"],
                 area_excludes_the_trees=review["area_excludes_the_trees"])
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    record = data["meta"]["refused_yield_cells"]
    print(f"wrote {out}: {len(data['crops'])} crops, years {data['meta']['years']}")
    if record["counts"]:
        total = sum(record["counts"].values())
        print(f"refused {total} yield cell(s), reported here rather than silently:")
        for reason, n in sorted(record["counts"].items()):
            print(f"          {reason}: {n}")


if __name__ == "__main__":
    main()
