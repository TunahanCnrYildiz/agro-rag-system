"""Yield and price norms, and the provenance that keeps a norm an average.

THE DATA IS A FILE, NOT A FETCH, and that was measured rather than assumed:
TUIK's download endpoint answers 403 without a browser session, MEDAS does not
respond to scripted interaction, and the figures are published once a year. A
runtime fetcher would carry real fragility for almost no freshness, and this
project has already paid once for a silent bootstrap failure. A committed file
also puts each norm's year and region in a diff.

NOTHING IS INVENTED. A province with no row falls back to the national row and
SAYS SO. A missing year walks back to the most recent one that exists and
carries THAT year, so an answer reads "TUIK 2023" rather than implying 2025.
There is no interpolation, no neighbouring-province average, and no carrying a
national figure forward as if it were provincial - each would produce a number
nobody published.

A MISSING NORM IS NEVER ZERO. Absence returns None, because a zero flows into
the budget arithmetic and comes out as a confident wrong answer.

This module imports nothing from src/engine.py, the same boundary src/budget.py
keeps: it is a file in, values out.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.config import DATA_DIR

_PATH = DATA_DIR / "crop_norms.json"
_WORLD = DATA_DIR / "world_norms.json"
_FAO_MAP = DATA_DIR / "crop_fao_map.json"
TURKIYE_AREA = 223   # FAOSTAT carries Türkiye; TÜİK is better and wins. See _resolve.

NATIONAL_KEY = "TR"
NATIONAL_LABEL = "Türkiye"

_MEASURES = ("yield_kg_da", "price_tl_kg")
# Published only for the 61 crops TUIK gives a Kg/Meyve Veren Agac figure for,
# so it is validated ONLY WHEN PRESENT. Listing it in _MEASURES instead would
# make crop.get(...) return None for every field crop, _valid_measure(None)
# return False, and the whole table empty itself in silence.
_OPTIONAL_MEASURES = ("yield_kg_tree",)
_SCOPES = ("il", "tr")


def _valid_series(series: object, n_years: int) -> bool:
    """A series must be aligned to the shared year axis, or every value in it
    would be attributed to the wrong year."""
    if not isinstance(series, list) or len(series) != n_years:
        return False
    # json.loads accepts NaN/Infinity by default; reject them as a non-finite
    # value would reach a money answer as nan.
    return all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))
               for v in series)


def _valid_measure(measure: object, n_years: int) -> bool:
    if not isinstance(measure, dict):
        return False
    if measure.get("scope") not in _SCOPES:
        return False
    if NATIONAL_KEY not in measure:
        return False
    return all(_valid_series(s, n_years)
               for k, s in measure.items() if k != "scope")


@lru_cache(maxsize=1)
def _load() -> dict:
    """Validated norms, or an empty table. Never raises.

    A crop is dropped whole when any of its measures is malformed, rather than
    half-loaded: a crop carrying a yield but a silently missing price would
    prefill one field and leave the other blank with no explanation.
    """
    try:
        raw = json.loads(Path(_PATH).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        years = raw.get("meta", {}).get("years")
        if not isinstance(years, list) or not years:
            return {}
        if not all(isinstance(y, int) and not isinstance(y, bool) for y in years):
            return {}

        crops: dict[str, dict] = {}
        for crop_id, crop in (raw.get("crops") or {}).items():
            if not isinstance(crop, dict) or not isinstance(crop.get("label"), str):
                continue
            if (all(_valid_measure(crop.get(m), len(years)) for m in _MEASURES)
                    and all(_valid_measure(crop[m], len(years))
                            for m in _OPTIONAL_MEASURES if m in crop)):
                crops[crop_id] = crop
        return {"years": years, "crops": crops}
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}


@lru_cache(maxsize=1)
def _load_world() -> dict:
    """The world layer, or an empty mapping. A broken file must not break
    answering, the same rule _load() follows for the Turkish one.

    Kept as the raw structure (meta/items/countries/yield/price) rather than
    reshaped into crop_norms.json's shape: the two files have different axes
    - a Turkish measure is a scope plus a year-indexed list, a world one is a
    "<item>|<area>" key plus a year-string-keyed dict - and forcing one shape
    onto the other would hide that difference instead of representing it.
    """
    try:
        raw = json.loads(Path(_WORLD).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        if not all(isinstance(raw.get(k), dict) for k in ("yield", "price", "countries")):
            return {}
        return raw
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}


@lru_cache(maxsize=1)
def _load_fao_map() -> dict:
    """Turkish crop id -> {"fao": item code or None, ...}, or an empty mapping.

    Returns the inner "map" table rather than the whole file: every caller
    wants one crop's entry, and the "generated" key that sits beside "map" in
    the file is provenance for a diff, not something a lookup needs.
    """
    try:
        raw = json.loads(Path(_FAO_MAP).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        table = raw.get("map")
        return table if isinstance(table, dict) else {}
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}


@dataclass(frozen=True)
class NormValue:
    """One figure and where it came from. The provenance travels with the value
    because a provincial reading and a national one must never look alike."""
    amount: float
    year: int
    scope: str          # "il" | "tr"
    region: str         # "Manisa" | "Türkiye"
    # WHICH unit, written down rather than inferred from the field name that
    # holds it. `CropNorm.price_per_kg` is lira for a Turkish figure and
    # dollars for a FAOSTAT one, and nothing else in the value says so.
    # No default: a default would let a price inherit "kg/da" in silence,
    # and a claim that is almost true is this project's recurring defect.
    unit: str
    # The spread of the five years BEFORE this one. Not the last five of the
    # series: this figure is the one being prefilled, and a range that contains
    # it cannot say whether it is typical. None when fewer than two of those
    # years carry a value - one number is not a range.
    recent_min: float | None = None
    recent_max: float | None = None
    # FAOSTAT's provenance letter for THIS cell - "A" a country's own report,
    # "E" FAO's estimate, "X" an outside organization, "B" a series break, "I"
    # imputed; data/world_norms.json's meta.flags glosses all five.
    #
    # 51,3% OF THE YIELD CELLS THAT ARE ACTUALLY PRINTED carry "E", so a world
    # figure printed without it would be attributed to a country that never
    # reported it. The population matters and an earlier revision of this
    # comment measured the wrong one: it said 41,3%, which is 29.842 of the
    # 72.335 non-null yield cells in the file and exactly right as arithmetic -
    # but `_pick_world` only ever returns the LATEST non-null cell of a series,
    # and over those 8.453 cells "E" is 4.333, 51,3%. The claim this number
    # supports is about printed figures, so the printed set is the one to count.
    # True as stated and measuring the wrong set is the "almost true" class this
    # project names as its recurring defect.
    #
    # THE PRICE TABLE IS A DIFFERENT STORY and is not covered by either figure:
    # of its 33.209 non-null cells none is "E" at all (33.163 "A", 43 "B", 3
    # "I"), and all 4.673 printed cells are "A". So the estimate gloss is a
    # yield-side concern today.
    #
    # None for every TÜİK figure: that file publishes no per-cell flag. None
    # therefore means "this source carries no flag", NEVER "official" - a
    # surface that prints a word for None would be inventing provenance.
    #
    # WHY A FIELD RATHER THAN RE-READING THE CELL AT THE POINT OF USE. Reaching
    # back into the file would mean rebuilding the "<item>|<area>" key and
    # re-running _pick_world's walk to the most recent non-null year, so the
    # rule deciding WHICH year answers would exist in two places. They agree
    # until one changes, and then a figure from one year prints a flag from
    # another, silently and provably wrong. far_below_recent's docstring records
    # what that cost the last time two surfaces decided one measure separately.
    # Defaulted, and last, so every existing positional construction stands.
    flag: str | None = None


# ONE FIFTH, AND THIS NUMBER IS TUNED RATHER THAN ARGUED. Measured over the
# 7.245 provincial yield cells that print a prior range: the distribution of
# `served / prior midpoint` decays smoothly from its mode at 0,9-1,2 with NO gap
# and no second peak, so a catastrophic year and a merely poor one lie on one
# continuum. An ordering rule does not rescue it either - "below the minimum of
# the prior five" fires on 28,8% of cells and 57% of those are near misses. All
# that can be said for one fifth is that the histogram's slope is shallowest
# across roughly 0,20-0,35, so the choice is least consequential there, and that
# it fires on 234 cells (3,2%) once paired with the ordering check below.
#
# WHY A TUNED NUMBER IS ACCEPTABLE HERE and was not for the density gates in
# scripts/build_crop_norms.py: this one drives a SENTENCE, not a refusal. Firing
# too often costs an unnecessary sentence; firing too rarely leaves today's
# behaviour. No outcome is worse than shipping nothing. The density rules delete
# data, which is why they were held to the higher "argued from geometry" bar.
_FAR_BELOW_RECENT = 0.2


def far_below_recent(value: NormValue | None) -> bool:
    """Whether this figure sits far below the five years printed beside it.

    A statement about the VALUE, not about presentation, so it lives here and
    both surfaces reach the same verdict for the same cell. The budget form and
    the comparison decided a measure separately once before and disagreed on
    1.568 cells for a round; a test pins them together.

    False without a range: the range is this warning's own evidence, and with
    nothing to compare against there is nothing to warn about.

    Magnitude alone is not enough: on a wide range, one fifth of the midpoint
    can sit ABOVE recent_min, so a value equal to the range's own printed
    minimum could pass the magnitude test - flagging the sentence "far below
    this range" onto a number that IS the range's edge. The sentence asserts
    an ordering (below the range), so the ordering is required too.
    """
    if value is None or value.recent_min is None or value.recent_max is None:
        return False
    midpoint = (value.recent_min + value.recent_max) / 2
    if midpoint <= 0:
        return False
    return (value.amount < value.recent_min
            and value.amount < _FAR_BELOW_RECENT * midpoint)


@dataclass(frozen=True)
class CropNorm:
    crop: str
    label: str
    yield_kg_da: NormValue | None
    price_per_kg: NormValue | None
    # Defaulted so the four-argument constructions in the tests keep working,
    # and because most crops genuinely do not have one.
    yield_kg_tree: NormValue | None = None


def available_crops() -> tuple[tuple[str, str], ...]:
    """(id, label) for every crop the file carries, sorted by label."""
    crops = _load().get("crops", {})
    return tuple(sorted(((cid, c["label"]) for cid, c in crops.items()),
                        key=lambda pair: pair[1]))


_RECENT_YEARS = 5


def _recent_range(series: list, index: int) -> tuple[float | None, float | None]:
    """Min and max of the non-null values in the five years before `index`.

    Two EQUAL values are not a range either: "63-63 kg/da" would dress a
    single observed level as a spread just as much as one bare value would.
    """
    window = [v for v in series[max(0, index - _RECENT_YEARS):index] if v is not None]
    if len(window) < 2:
        return None, None
    lo, hi = float(min(window)), float(max(window))
    return (None, None) if lo == hi else (lo, hi)


def _pick(measure: dict, years: list[int], province: str | None,
          unit: str) -> NormValue | None:
    """The province's row when the measure has one, otherwise the national row,
    then the most recent non-null year in it."""
    provincial = (measure.get("scope") == "il"
                  and province is not None
                  and province in measure)
    key = province if provincial else NATIONAL_KEY
    series = measure.get(key)
    if not isinstance(series, list):
        return None
    for i in range(len(series) - 1, -1, -1):
        if series[i] is not None:
            low, high = _recent_range(series, i)
            return NormValue(
                amount=float(series[i]),
                year=years[i],
                scope="il" if provincial else "tr",
                region=key if provincial else NATIONAL_LABEL,
                unit=unit,
                recent_min=low,
                recent_max=high,
            )
    return None


def _pick_world(cells: dict | None, area: int, unit: str) -> NormValue | None:
    """The most recent year in one `"<item>|<area>"` series.

    `cells` is that series already: a year-string -> [amount, flag] mapping,
    with its own year axis rather than the Turkish file's - FAOSTAT ends at
    2024 where TÜİK reaches 2025, and the year returned must be the cell's
    own, never borrowed from `years` the way `_pick` uses it.

    No `recent_min`/`recent_max`: the five-year spread printed beside a Turkish
    figure comes from the same source as the figure. Mixing a FAOSTAT range
    into a surface built for TÜİK's would put two different things behind one
    label, so the range is left None until a surface asks for it.
    """
    if not isinstance(cells, dict) or not cells:
        return None
    countries = _load_world().get("countries", {})
    country_entry = countries.get(str(area))
    region = country_entry.get("label") if isinstance(country_entry, dict) else None
    if not isinstance(region, str):
        return None
    for year_str in sorted(cells, key=lambda y: int(y), reverse=True):
        cell = cells.get(year_str)
        if (isinstance(cell, list) and len(cell) >= 1
                and isinstance(cell[0], (int, float)) and not isinstance(cell[0], bool)
                and math.isfinite(cell[0])):
            try:
                year = int(year_str)
            except (TypeError, ValueError):
                continue
            return NormValue(
                amount=float(cell[0]),
                year=year,
                scope="ulke",
                region=region,
                unit=unit,
                # cell is [amount, flag]. A cell short of a second element, or
                # carrying something that is not a letter, yields None rather
                # than a guess: an unflagged figure is printed as unflagged.
                flag=(cell[1] if len(cell) >= 2 and isinstance(cell[1], str)
                      and cell[1].strip() else None),
            )
    return None


def _resolve_world(crop_id: str, entry: dict, country: int) -> CropNorm:
    """One crop's figures from the world layer, for one country.

    `entry` is the Turkish crop_norms.json entry, kept only for its label -
    the crop is named the same way whichever layer answers for it. A crop
    with no FAO mapping, or a mapping with no cell for this area, comes back
    as a CropNorm whose measures are None rather than as None itself: the
    crop exists, the figure does not, and the caller prefills what it can.
    """
    mapping = _load_fao_map().get(crop_id)
    fao_item = mapping.get("fao") if isinstance(mapping, dict) else None
    yield_val = None
    price_val = None
    if fao_item is not None:
        world = _load_world()
        key = f"{fao_item}|{country}"
        yield_val = _pick_world(world.get("yield", {}).get(key), country, "kg/da")
        price_val = _pick_world(world.get("price", {}).get(key), country, "USD/kg")
    return CropNorm(
        crop=crop_id,
        label=entry["label"],
        yield_kg_da=yield_val,
        price_per_kg=price_val,
    )


def _resolve(crop_id: str, entry: dict, years: list[int],
             province: str | None, country: int | None = None) -> CropNorm:
    """One crop's norms for one province.

    Shared by lookup() and province_table() so the two cannot drift: the budget
    form is built from province_table() and a submitted figure is verified
    against the very row that table already served (src/budget.py's _verify
    holds onto it rather than calling lookup() again) - so a difference
    between the two functions could never surface as the server rejecting a
    figure it had itself just sent.
    """
    # A province beats a country beats nothing. Türkiye as a country resolves
    # to the national TÜİK row, never to FAOSTAT's area 223 - that series is a
    # cross-check and the previous spec settled it.
    if province is None and country is not None and country != TURKIYE_AREA:
        return _resolve_world(crop_id, entry, country)
    return CropNorm(
        crop=crop_id,
        label=entry["label"],
        yield_kg_da=_pick(entry["yield_kg_da"], years, province, "kg/da"),
        price_per_kg=_pick(entry["price_tl_kg"], years, province, "TL/kg"),
        yield_kg_tree=(_pick(entry["yield_kg_tree"], years, province, "kg/ağaç")
                       if "yield_kg_tree" in entry else None),
    )


def lookup(crop: str, province: str | None, country: int | None = None) -> CropNorm | None:
    """Norms for a crop, or None when the file does not carry it.

    A measure that resolves to nothing is None on the result rather than absent,
    so the caller prefills the fields it can and leaves the rest to the user.

    `country` is a FAOSTAT area code, consulted only when `province` resolves
    to nothing - a province is always TÜİK and always wins. See _resolve for
    why Türkiye as a country still serves TÜİK, not FAOSTAT's own area 223.
    """
    data = _load()
    entry = data.get("crops", {}).get(crop)
    if entry is None:
        return None
    years = data["years"]
    return _resolve(crop, entry, years, province, country)


def latest_year() -> int | None:
    """The most recent year on the loaded axis, or None when the table is empty.

    Read straight off `years` rather than derived from any crop's cells: this
    is the DATASET's cutoff, used by src/budget.py to decide whether a PRICE
    figure is fresh enough to prefill (see budget._crop_rows). Deriving it
    from the cells instead would let one crop's late-published figure make an
    older price elsewhere look current.
    """
    years = _load().get("years")
    return years[-1] if years else None


def province_table(province: str | None) -> tuple[CropNorm, ...]:
    """Every crop the file carries, resolved for one province, sorted by label.

    Identical to calling lookup() for each id in available_crops(), and pinned
    that way by a test - the form is built from this table and a submitted
    figure is verified against the same row, held over from here rather than
    fetched again via lookup(), so the two must never drift.

    It exists because the whole table travels to the client with the form: the
    crop is chosen there, so the server cannot know in advance which row will
    be needed and sends all of them.
    """
    data = _load()
    years = data.get("years")
    if not years:
        return ()
    rows = tuple(
        _resolve(crop_id, entry, years, province)
        for crop_id, entry in data["crops"].items()
    )
    return tuple(sorted(rows, key=lambda row: row.label))
