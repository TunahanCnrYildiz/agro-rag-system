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

NATIONAL_KEY = "TR"
NATIONAL_LABEL = "Türkiye"

_MEASURES = ("yield_kg_da", "price_tl_kg")
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
            if all(_valid_measure(crop.get(m), len(years)) for m in _MEASURES):
                crops[crop_id] = crop
        return {"years": years, "crops": crops}
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}
