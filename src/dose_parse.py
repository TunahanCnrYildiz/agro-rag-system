"""Read a per-dekar dose out of a manufacturer's free-Turkish application text.

NOTHING IS INVENTED. Text this module cannot read yields None, never a zero and
never a midpoint: a wrong number here becomes a wrong purchase quantity.

A DILUTION IS NOT A DOSE. "100 litre suya 250 gram" is an amount per 100 litres
of water. Converting it to a per-dekar figure needs the spray volume per dekar,
which the pages do not publish, so those clauses are refused rather than guessed.

THE PAGES DO NOT SAY "DEKAR". They say "/ 1000m²", and 1000 m2 is one dekar.
Matching only dekar/donum finds 2 products of 48; including the area forms below
finds 42. That was measured, not assumed - see the recon findings doc.
"""
from __future__ import annotations

import re

# Units as the pages actually spell them, longest first so "litre" is not eaten
# by "l" and "gram" not by "gr". The value is the key stored in the data file.
_UNITS = (("litre", "litre"), ("gram", "gr"), ("lt", "litre"), ("kg", "kg"),
          ("cc", "cc"), ("ml", "cc"), ("gr", "gr"), ("l", "litre"), ("g", "gr"))
_UNIT_RE = "|".join(spelling for spelling, _ in _UNITS)

# A figure or a range. The dash may be a hyphen or an en dash, spaced or not.
# Between the figure and its unit a page sometimes spells the number out in
# parentheses ("3 (üç) litre"), so that gloss is tolerated but not captured.
_NUMBER = r"\d+(?:[.,]\d+)?"
_AMOUNT = (rf"(?P<low>{_NUMBER})\s*(?:[-–]\s*(?P<high>{_NUMBER}))?\s*"
           rf"(?:\([^)]*\)\s*)?(?P<unit>{_UNIT_RE})\b")

# One dekar, in every form the pages use. Hectares are deliberately EXCLUDED:
# a per-hectare figure is ten times a per-dekar one, and reading one as the
# other multiplies every answer by ten with nothing to show for it.
_AREA = r"(?:dekar[ae]?|d[oö]n[uü]m[ae]?|1[.\s]?000\s*m\s*[²2]|1000\s*m\s*[²2])"

# The same amount with NO named groups. A pattern may only name a group once,
# so reusing _AMOUNT on both sides of the dilution alternation below raises
# re.PatternError at import time - verified, not guessed.
_AMOUNT_BARE = rf"{_NUMBER}\s*(?:[-–]\s*{_NUMBER})?\s*(?:{_UNIT_RE})"

# Water, so a dilution can be recognised and refused.
_WATER = r"\d+\s*(?:litre|lt|l)\s*su"

# The amount sits on either side of the area, and up to ~40 characters away
# ("1000m² alan için damla sulama ile 2 – 2.5 litre" is 26). Stop at any clause
# punctuation, THE COMMA INCLUDED, so a dose cannot borrow a number from the
# next clause: the panels separate the foliar and drip halves of one sentence
# with a comma and nothing else.
_GAP = r"[^.;:,]{0,40}?"
_AMOUNT_THEN_AREA = re.compile(_AMOUNT + _GAP + _AREA, re.I)
_AREA_THEN_AMOUNT = re.compile(_AREA + _GAP + _AMOUNT, re.I)
_DILUTION = re.compile(
    rf"(?:{_AMOUNT_BARE}{_GAP}{_WATER}|{_WATER}{_GAP}{_AMOUNT_BARE})", re.I)


def _number(text: str) -> float:
    """Turkish decimal comma. The pages also use a dot for the same purpose
    ("2.5 litre" appears beside "2,5 litre" on different products), and no
    amount on any panel reaches four digits, so both are read as decimals."""
    return float(text.replace(",", "."))


def _unit(spelling: str) -> str:
    lowered = spelling.lower()
    for written, key in _UNITS:
        if lowered == written:
            return key
    return lowered


def parse_dose(text: str) -> tuple[float, float, str] | None:
    """One clause's per-dekar dose as (low, high, unit), or None.

    A DILUTION DISQUALIFIES ITS OWN AMOUNT, NOT THE WHOLE CLAUSE. Refusing the
    clause outright was tried and measured: it drops the count from 42 products
    to 10, because panels like HİGRO BARF write

        Yapraktan uygulama ile 100 cc / 100 litre suya
        Damlama sulama ile 2-2,5 litre / 1000m² (da)

    as ONE unpunctuated sentence. The dilution and the dose sit side by side, so
    the test has to be per-figure: an amount that is bound to a volume of water
    is not a per-area dose, and an amount that is bound to an area is - even
    when both appear in the same breath.
    """
    diluted = [m.span() for m in _DILUTION.finditer(text)]
    for pattern in (_AMOUNT_THEN_AREA, _AREA_THEN_AMOUNT):
        for match in pattern.finditer(text):
            start, end = match.span("low")
            if any(a <= start and end <= b for a, b in diluted):
                continue
            low = _number(match.group("low"))
            high = _number(match.group("high")) if match.group("high") else low
            if high < low:
                low, high = high, low
            return low, high, _unit(match.group("unit"))
    return None
