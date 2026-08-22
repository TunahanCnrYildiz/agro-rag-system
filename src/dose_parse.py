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
# The gloss excludes clause-breaking punctuation, same as _GAP below, so it
# can never smuggle a clause boundary into the middle of an amount.
#
# _AMOUNT and _AMOUNT_BARE (below) MUST STAY IDENTICAL apart from the named
# groups - see the note on _AMOUNT_BARE for why a divergence is dangerous.
_NUMBER = r"\d+(?:[.,]\d+)?"
_GLOSS = r"(?:\([^(),.;:]*\)\s*)?"
_AMOUNT = (rf"(?P<low>{_NUMBER})\s*(?:[-–]\s*(?P<high>{_NUMBER}))?\s*"
           rf"{_GLOSS}(?P<unit>{_UNIT_RE})\b")

# One dekar, in every form the pages use. Hectares are deliberately EXCLUDED:
# a per-hectare figure is ten times a per-dekar one, and reading one as the
# other multiplies every answer by ten with nothing to show for it.
_AREA = r"(?:dekar[ae]?|d[oö]n[uü]m[ae]?|1[.\s]?000\s*m\s*[²2])"

# The same amount with NO named groups. A pattern may only name a group once,
# so reusing _AMOUNT on both sides of the dilution alternation below raises
# re.PatternError at import time - verified, not guessed.
#
# THIS MUST STAY IDENTICAL TO _AMOUNT APART FROM THE NAMED GROUPS. _DILUTION
# is built from this pattern, and if it recognises less than _AMOUNT does -
# the parenthetical numeral gloss, for instance - then a dilution's own
# amount stops being seen as part of a dilution, the skip check in
# parse_dose never fires for it, and a water volume gets read as a per-dekar
# dose. Reproduced by execution when the two had drifted apart: "100 litre
# suya 250 (iki yuz elli) gram dekara uygulanir" returned (100.0, 100.0,
# "litre") - the WATER volume, as the dose.
_AMOUNT_BARE = rf"{_NUMBER}\s*(?:[-–]\s*{_NUMBER})?\s*{_GLOSS}(?:{_UNIT_RE})\b"

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


# The three crop groups, as the panels head them. The colon is optional: two
# products write "Sebzelerde Yapraktan ..." and a pattern that requires one
# loses them both.
_GROUPS = (
    ("sebze", r"sebze\w*"),
    ("meyve", r"meyve\s*a[ğg]a[çc]\w*|meyve\w*"),
    ("tarla", r"tarla\s*bitki\w*"),
)
_GROUP_RE = re.compile(
    r"(?P<head>" + "|".join(pattern for _, pattern in _GROUPS) + r")\s*(?:i[çc]in)?\s*:?",
    re.I)

_METHODS = (("damlama", r"damlama\w*|damla\s+sulama"), ("yaprak", r"yaprak\w*"))

# THE COMMA IS A CLAUSE BOUNDARY HERE. The panels write
# "Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, Damlamadan 250 gr/ 1000m²"
# as one sentence, so splitting on . and ; alone leaves the dilution and the
# dose in the same clause and the method attribution picks whichever word came
# first. Measured: without the comma the drip figure is credited to "yaprak".
_CLAUSE = re.compile(r"(?<=[.;,])\s+")


def _widen(existing, dose):
    """Several figures for one group and method: keep the span they cover.

    One product does this - FLY AZOT publishes 200 cc for dry farming and
    250 cc for irrigated in the same unqualified block. Keeping the first would
    silently pick one of two published figures; the span the source's own
    numbers cover states both, and invents nothing between them.

    Units that disagree are NOT merged - there is no conversion from a gram to
    a litre without a density the page never gives - so the first unit wins and
    the other figure is dropped. No panel does this today; if one starts to, the
    converter's coverage report is where it will show up.
    """
    if existing is None:
        return dose
    if existing[2] != dose[2]:
        return existing
    return (min(existing[0], dose[0]), max(existing[1], dose[1]), existing[2])

# No group named anywhere means the dose is not qualified by one. Recording it
# under every group would claim the page said something it did not; this key
# says plainly that it applies to all.
ALL_GROUPS = "hepsi"


def _method_of(clause: str) -> str:
    """Which application method this clause describes.

    Defaults to drip, and that is a DOCUMENTED DEFAULT rather than a reading of
    the text: of the 42 products publishing a per-area figure, 37 attach it to
    drip only, and the three panels naming no method describe soil or drip
    application. Foliar figures are almost always dilutions, which parse_dose
    refuses anyway.
    """
    for key, pattern in _METHODS:
        if re.search(pattern, clause, re.I):
            return key
    return "damlama"


def _segments(text: str) -> list[tuple[str, str]]:
    """Split a panel into (group, text) pairs at its group headings."""
    matches = list(_GROUP_RE.finditer(text))
    if not matches:
        return [(ALL_GROUPS, text)]
    out = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        head = match.group("head").lower()
        group = next(key for key, pattern in _GROUPS
                     if re.fullmatch(pattern, head, re.I))
        out.append((group, text[match.end():end]))
    return out


def parse_panel(text: str) -> dict[str, dict[str, tuple[float, float, str]]]:
    """A whole Uygulama panel as {group: {method: (low, high, unit)}}.

    Only per-dekar figures survive; dilutions are dropped by parse_dose. A
    panel yielding nothing returns an empty mapping, which is how the converter
    learns to report it rather than write an empty row.
    """
    result: dict[str, dict[str, tuple[float, float, str]]] = {}
    for group, segment in _segments(text):
        for clause in _CLAUSE.split(segment):
            dose = parse_dose(clause)
            if dose is None:
                continue
            slot = result.setdefault(group, {})
            method = _method_of(clause)
            slot[method] = _widen(slot.get(method), dose)
    return result
