"""Fertilization plan rows, and the framing that keeps a plan advice.

THE TABLE IS DATA, NOT CODE, and it ships EMPTY. Its correctness cannot be
established by testing - only by review - and neither the author of this module
nor the developer is an agricultural engineer. A row without a `reviewed_by` is
dropped at load time, so an unreviewed line cannot reach a user even if someone
adds one to the file.

Adding a crop is therefore a review task, not a programming task: append rows
with `reviewed_by` filled in by the person who checked them. No code changes.
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
    never an exception, because a broken table must not break answering."""
    try:
        raw = json.loads(Path(_TABLE_PATH).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, list[dict]] = {}
    for crop, rows in (raw or {}).items():
        kept = [r for r in rows if r.get("reviewed_by")]
        if kept:
            out[crop.lower()] = kept
    return out


def available_crops() -> tuple[str, ...]:
    """Crops with at least one reviewed row."""
    return tuple(sorted(_load()))


def detect_crop(message: str) -> str | None:
    """Which reviewed crop the message is about, or None.

    Matched against the TABLE'S OWN KEYS so there is no second list to drift.
    While the table is empty this can only return None, which is exactly the
    behaviour we want before review has happened.

    Left-boundary match, so a crop may carry Turkish suffixes ("domatese",
    "domatesin") - the same convention the crop lexicon and the router use.
    """
    folded = _normalize_tr(message)
    for crop in sorted(_load(), key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(_normalize_tr(crop))}", folded):
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
