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

# Must list every method dose_parse can emit, in the order the answer should
# print them. A method missing here is silently unreadable: the row is in the
# file and lookup skips it.
_METHODS = ("damlama", "yaprak", "toprak")


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
