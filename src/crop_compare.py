"""Two crops the farmer picked, side by side, and no verdict.

THE MODEL PERFORMS NO ARITHMETIC AND MAKES NO APPEARANCE. Every number a user
sees from this route is computed here, in Python, from figures TUIK published.

WHAT THIS ROUTE REFUSES IS THE POINT. It prints gross revenue per dekar for
each crop and says, in a sentence written by code, that gross revenue is not
profit - because this project holds NO cost data at all, and two crops' costs
can differ by more than the difference the farmer is looking at. Measured on
Konya 2025: domates 115.664 TL/da against biber 125.841 TL/da, nine percent
apart, which says nothing at all about which one pays better.

NOTHING THAT REACHES ARITHMETIC IS READ FROM THE QUESTION. named_crops() below
reads the message, but only to decide WHICH ANSWER to show; the figures come
from two explicit card selections. A wrong detection costs a card the farmer
can ignore. `Biber` alone is five different rows in the table, with five
different yields - which row is meant is the card's question, never ours.

This module imports `_normalize_tr` and `_TR_SUFFIXES` from src/engine.py the
same way src/router.py does, and for the same reason: the engine imports THIS
module lazily, inside the function that uses it, so the cycle is never real.
"""
from __future__ import annotations

import re
from functools import lru_cache

from src import norms
from src.engine import _TR_SUFFIXES, _normalize_tr


@lru_cache(maxsize=1)
def _families() -> tuple[tuple[str, str], ...]:
    """(folded family name, display family) for every crop the table carries.

    A crop FAMILY is the label with its variant stripped: `Domates (Sofralık)`
    and `Domates (Salçalık)` are both `Domates`, `Buğday, Durum Buğdayı Hariç`
    is `Buğday`. The farmer types the family; the card asks which row.

    Sorted longest first so a two-word family is tested before the one-word
    family inside it.
    """
    out: dict[str, str] = {}
    for _crop_id, label in norms.available_crops():
        family = re.split(r"\s*[(,]", label)[0].strip()
        if family:
            out.setdefault(_normalize_tr(family), family)
    return tuple(sorted(out.items(), key=lambda item: -len(item[0])))


def named_crops(message: str) -> tuple[str, ...]:
    """Every crop family this message names, in the order they appear.

    The matcher is the bounded-suffix one the crop lexicon already uses: a name
    may run into a Turkish case ending ("domatesi") but not into a different
    word ("arpacık" is a stye, not barley).

    A family contained inside a longer matched family is dropped: "tatlı
    patates" names ONE crop, and counting "patates" as a second would invent a
    comparison the farmer never asked for.
    """
    folded = _normalize_tr(message or "")
    if not folded:
        return ()

    hits: list[tuple[int, str, str]] = []
    for folded_family, display in _families():
        match = re.search(
            rf"(?<!\w){re.escape(folded_family)}(?:{_TR_SUFFIXES})?(?!\w)", folded)
        if match:
            hits.append((match.start(), folded_family, display))

    kept = [hit for hit in hits
            if not any(hit[1] != other[1] and hit[1] in other[1] for other in hits)]
    kept.sort(key=lambda hit: hit[0])
    return tuple(display for _start, _folded, display in kept)
