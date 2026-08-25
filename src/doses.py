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
from src.dose_parse import ALL_GROUPS, GROUP_KEYS

KNOWN_GROUPS = frozenset(GROUP_KEYS) | {ALL_GROUPS}

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
def _load() -> tuple[dict, dict]:
    """(validated products, reviewed all-groups scope). Never raises.

    A product is dropped WHOLE when any of its groups is malformed rather than
    half-loaded: a product answering for one group and silently not for another
    is indistinguishable from one that simply has no figure there.

    The scope says which groups each `hepsi` row may answer. A scope entry
    naming a group nobody publishes is dropped rather than trusted, and a
    product with no entry gets no fallback at all - see lookup().
    """
    try:
        raw = json.loads(Path(_PATH).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}, {}
        products = raw.get("products")
        if not isinstance(products, dict):
            return {}, {}
        kept = {name: groups for name, groups in products.items()
                if isinstance(name, str) and _valid_product(groups)}
        scope_raw = raw.get("all_groups_scope")
        scope_raw = scope_raw if isinstance(scope_raw, dict) else {}
        scope = {name: frozenset(g for g in groups if g in GROUP_KEYS)
                 for name, groups in scope_raw.items()
                 if isinstance(name, str) and isinstance(groups, list)}
        return kept, scope
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}, {}


def available_products() -> tuple[str, ...]:
    """Every product carrying at least one per-area dose, sorted."""
    return tuple(sorted(_load()[0]))


def lookup(product: str, group: str) -> tuple[Dose, ...]:
    """Every per-area figure this product publishes for this crop group.

    Usually one - 37 of the 42 products with a per-area dose publish it for drip
    irrigation only. The caller prints each with its method rather than choosing
    between them, because the source decides the method, not the farmer.

    THE `hepsi` FALLBACK IS REVIEWED, NOT AUTOMATIC. `hepsi` only says the
    parser found no group heading, which happens both when the page names no
    crop AND when it names crops we do not map to groups. FLY AZOT is the
    second kind: every figure on its page is qualified by crop name, and none
    of those crops is a fruit. So the fallback fires only for the groups a
    person confirmed - and for a product nobody reviewed, not at all.
    """
    products, scope = _load()
    groups = products.get(product)
    if not groups:
        return ()
    if group not in KNOWN_GROUPS:
        # A group we do not publish is not a question we can answer. Without
        # this a typo falls straight through to the unqualified `hepsi` row for
        # any product that has one, and the caller gets a real figure back for
        # a group it never asked about.
        return ()
    methods = groups.get(group)
    if methods is None and group in scope.get(product, frozenset()):
        methods = groups.get(ALL_GROUPS)
    methods = methods or {}
    return tuple(
        Dose(low=float(d["low"]), high=float(d["high"]), unit=d["unit"], method=method)
        for method in _METHODS
        if (d := methods.get(method)) is not None
    )
