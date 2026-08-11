"""Fertilization plan rows, and the framing that keeps a plan advice.

THE TABLE IS DATA, NOT CODE, and it ships EMPTY. Its correctness cannot be
established by testing - only by review - and neither the author of this module
nor the developer is an agricultural engineer. A row without a `reviewed_by` is
dropped at load time, so an unreviewed line cannot reach a user even if someone
adds one to the file.

DO NOT ADD ROWS YET. The assembly step that would turn a row into a calendar is
not written: the only consumer of `lookup()` is the framing gate in
`engine._framing_suffix`, so `stage` and `note` never reach the prompt. Adding a
reviewed row today changes exactly one thing - it appends "Bu program bir
tahmindir" to an answer that still contains no programme, which reads worse than
having no row at all. (`_load` is cached for the process lifetime too, so it is
not a live data edit either.)

Once assembly exists, adding a crop becomes a review task rather than a
programming one: append rows with `reviewed_by` filled in by the person who
checked them. It is not one yet.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from src.config import DATA_DIR
from src.engine import _normalize_tr

_TABLE_PATH = DATA_DIR / "fertplan_table.json"

# Appended BY CODE, never asked of the model, so no model can omit it. This
# sentence is the line between advice and prescription.
FRAMING = (
    "Bu program bir tahmindir ve yukarıda belirtilen bilgilere dayanmaktadır; "
    "kesin doz için toprak analizi yaptırmanız ve bir ziraat mühendisine "
    "danışmanız önerilir."
)


@lru_cache(maxsize=1)
def _load() -> dict[str, list[dict]]:
    """Reviewed rows only. A missing or malformed file yields an empty table -
    never an exception, because a broken table must not break answering.

    The whole build - not just the read/parse - lives inside the guard, and
    each shape is also checked explicitly rather than trusted: a top-level
    array/string, a crop value that isn't a list, or a row that isn't a dict
    must all be skipped, not raise past this function."""
    try:
        raw = json.loads(Path(_TABLE_PATH).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[dict]] = {}
        for crop, rows in raw.items():
            if not isinstance(rows, list):
                continue
            kept = [r for r in rows if isinstance(r, dict) and r.get("reviewed_by")]
            if kept:
                out[crop.lower()] = kept
        return out
    except Exception:  # noqa: BLE001
        return {}


def available_crops() -> tuple[str, ...]:
    """Crops with at least one reviewed row."""
    return tuple(sorted(_load()))


# Turkish case suffixes a crop name may carry. ENUMERATED on purpose: a bare
# left-boundary match fires inside an unrelated word - "nar" (pomegranate) would
# match inside "narenciye" (citrus) the first time a reviewer adds it. The router
# paid for this lesson five times (see its _has_word) and src/context/location.py
# solves it the same way. Text reaching here is already ASCII-folded, so the
# suffixes appear folded too.
_SUFFIX = r"(?:[dt][ae]n?|[yn]?[aeiu]n?|l[iu])?"


def detect_crop(message: str) -> str | None:
    """Which reviewed crop the message is about, or None.

    Matched against the TABLE'S OWN KEYS so there is no second list to drift.
    While the table is empty this can only return None, which is exactly the
    behaviour we want before review has happened.

    A match must be followed by a known case suffix and then the end of the word
    ("domates", "domatese", "domatesin"), never by arbitrary letters.
    """
    folded = _normalize_tr(message)
    for crop in sorted(_load(), key=len, reverse=True):
        k = re.escape(_normalize_tr(crop))
        if re.search(rf"(?<!\w){k}{_SUFFIX}(?!\w)", folded):
            return crop
    return None


def lookup(crop: str, stage: str | None) -> list[dict]:
    """Reviewed rows for a crop, optionally narrowed to one phenological stage.
    Empty list when the crop has no reviewed rows - the caller must then say so
    plainly rather than inventing a plan."""
    rows = _load().get((crop or "").lower(), [])
    if stage:
        rows = [r for r in rows if r.get("stage") == stage]
    return list(rows)
