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

    Cached on the assumption the underlying table never changes mid-process.
    If a caller ever reloads the table (as the test fixture does), it must
    also call `_families.cache_clear()` or this keeps answering from the
    stale one.
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

    The containment rule is about POSITION, not spelling. "tatlı patates"
    names ONE crop because its "patates" match sits INSIDE the "tatlı
    patates" match's span. A family that is a spelling-substring of another
    (e.g. "Buğday" inside "Kara Buğday") is NOT dropped on that account -
    if "buğday" also occurs somewhere the "kara buğday" match does not
    cover, that occurrence names a crop of its own. So every occurrence of
    every family is found (not just the first), a family is kept if at
    least one of its occurrences is not covered by another matched family's
    span, and the result is ordered by each surviving family's earliest
    surviving occurrence.
    """
    folded = _normalize_tr(message or "")
    if not folded:
        return ()

    occurrences: list[tuple[int, int, str, str]] = []  # start, end, folded family, display
    for folded_family, display in _families():
        pattern = rf"(?<!\w){re.escape(folded_family)}(?:{_TR_SUFFIXES})?(?!\w)"
        for match in re.finditer(pattern, folded):
            occurrences.append((match.start(), match.end(), folded_family, display))

    def covered(occurrence: tuple[int, int, str, str]) -> bool:
        start, end, family, _display = occurrence
        return any(other[2] != family and other[0] <= start and end <= other[1]
                   for other in occurrences)

    displays: dict[str, str] = {}
    earliest_free_start: dict[str, int] = {}
    for occurrence in occurrences:
        start, _end, family, display = occurrence
        if covered(occurrence):
            continue
        displays[family] = display
        if family not in earliest_free_start or start < earliest_free_start[family]:
            earliest_free_start[family] = start

    order = sorted(earliest_free_start, key=earliest_free_start.__getitem__)
    return tuple(displays[family] for family in order)
