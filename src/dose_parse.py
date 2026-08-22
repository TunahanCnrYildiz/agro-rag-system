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
_NUMBER = r"\d+(?:[.,]\d+)?"
_GLOSS = r"(?:\([^(),.;:]*\)\s*)?"


def _amount(named: bool) -> str:
    """Build the number-or-range-with-unit grammar, named or bare.

    _AMOUNT (named groups, used to read a value) and _AMOUNT_BARE (no groups,
    used only to recognise a dilution's own amount so it can be excluded) used
    to be two hand-typed copies of this pattern. That is exactly how the
    dilution guard broke once already: the two drifted apart when the
    parenthetical numeral gloss was added to one and not the other, a
    dilution's own amount stopped being recognised as part of the dilution,
    and "100 litre suya 250 (iki yuz elli) gram dekara uygulanir" came back as
    (100.0, 100.0, "litre") - the WATER volume, read as a dose. One builder
    toggled by whether groups are named cannot desync that way again.

    The grammar is a single figure with a unit ("250 gr"), or a range where
    the HIGH figure's unit is mandatory and the LOW figure's unit is optional
    ("2 - 2,5 litre", or "0,5kg - 1kg" where both sides spell it). A pattern
    cannot name the same group twice even across mutually-exclusive
    alternatives (verified: re.compile raises "redefinition of group name"),
    so the solo-figure unit and the range's low/high units get distinct names
    even when named=False makes the distinction moot.
    """
    def g(name: str, pattern: str) -> str:
        return rf"(?P<{name}>{pattern})" if named else rf"(?:{pattern})"

    low = g("low", _NUMBER)
    lowunit = g("lowunit", _UNIT_RE) + "?"
    high = g("high", _NUMBER)
    highunit = g("unit", _UNIT_RE)
    solounit = g("solounit", _UNIT_RE)
    range_branch = rf"{lowunit}\s*[-–]\s*{high}\s*{_GLOSS}{highunit}\b"
    solo_branch = rf"{solounit}\b"
    return rf"{low}\s*{_GLOSS}(?:{range_branch}|{solo_branch})"


_AMOUNT = _amount(named=True)

# One dekar, in every form the pages use. Hectares are deliberately EXCLUDED:
# a per-hectare figure is ten times a per-dekar one, and reading one as the
# other multiplies every answer by ten with nothing to show for it.
_AREA = r"(?:dekar[ae]?|d[oö]n[uü]m[ae]?|1[.\s]?000\s*m\s*[²2])"

# The same grammar with no named groups, for the dilution guard below - see
# _amount()'s docstring for why building both from one function matters.
_AMOUNT_BARE = _amount(named=False)

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

# The WATER-then-AMOUNT direction of a dilution needs a much tighter gap than
# the AMOUNT-then-WATER one above. Measured across all 48 panels: every real
# "Xya <amount>" dilution ("100 litre suya 250 gram") has the amount 3
# characters after "su" - the length of the "ya" suffix plus a space, since
# _WATER's own match stops at "su". The two products that lost a real dose to
# this guard (HİGRO ZİMOBOR, HİGRO EQUAJE) have no such suffix: their "su" is
# the tail of an unrelated, already-matched dilution ("100 Litre su ile
# uygulanılır Damlamadan 250 gr"), and the real per-dekar figure sits 27
# characters further on, past "ile uygulanılır Damlamadan ". A bound of 6
# comfortably covers every real case and stays far short of that 27.
_TIGHT_GAP = r"[^.;:,]{0,6}?"
_DILUTION = re.compile(
    rf"(?:{_AMOUNT_BARE}{_GAP}{_WATER}|{_WATER}{_TIGHT_GAP}{_AMOUNT_BARE})", re.I)


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


def _read_amount(match: re.Match) -> tuple[float, float, str] | None:
    """A regex match of _AMOUNT as (low, high, unit), or None if it does not
    describe one coherent figure.

    Two ways a match can fail to be coherent, both refused rather than
    guessed at: the low and high bounds spelling DIFFERENT units ("0,5kg –
    1 litre" is not a range of anything), and a low bound that is bigger than
    the high one, which means the matcher paired two numbers that were never
    meant to go together (HİGRO MATEN's "2 – 2,5 – 1 Litre" - a three-number
    sequence with no stated meaning - matches "2,5" as low and "1" as high
    only because the real first number, "2", could not pair with a unit and
    the regex moved on). Reordering a reversed pair was tried and is exactly
    the bug: it turns a garbled sequence into a plausible-looking figure.
    """
    low = _number(match.group("low"))
    unit_text = match.group("unit") or match.group("solounit")
    high_text = match.group("high")
    if high_text is None:
        return low, low, _unit(unit_text)
    lowunit_text = match.group("lowunit")
    if lowunit_text and _unit(lowunit_text) != _unit(unit_text):
        return None
    high = _number(high_text)
    if high < low:
        return None
    return low, high, _unit(unit_text)


# A number and a dash immediately before an amount mean the matcher has landed
# in the MIDDLE of a longer chain. HİGRO MATEN publishes "Damlamadan 2 - 2,5 - 1
# Litre// 1000m²": three numbers, and the page never says what they mean. The
# matcher cannot start at "2" (a dash follows "2,5", not a unit) so it starts at
# "2,5", and whatever it then salvages - a reversed pair, or just the trailing
# "1 Litre" - is a figure the page does not state. Refuse the chain instead:
# rescuing a fragment of an unreadable sequence is the same act as inventing one.
# The unit may sit on the left figure too ("0,5kg - 1 litre"), so it is part of
# what counts as a dangling chain head - otherwise a range whose two units
# disagree gets refused and then the scan salvages its right-hand figure alone,
# which is the same invented number by another route.
_CHAIN_TAIL = re.compile(rf"{_NUMBER}\s*{_GLOSS}(?:{_UNIT_RE})?\s*[-–]\s*$", re.I)


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
        pos = 0
        while (match := pattern.search(text, pos)) is not None:
            start, end = match.span("low")
            # RESUME JUST AFTER THE REJECTED AMOUNT, not after the whole match.
            # finditer would skip past everything the match consumed, and a
            # match rejected for being a dilution routinely SPANS the real
            # dose: HİGRO EQUAJE's "100 Litre su ile uygulanılır Damlamadan
            # 250 gr/ 1000m²" is one match whose amount is the water volume,
            # and stepping past it swallowed the 250 gr as well. Two products
            # lost a whole crop group that way, silently, because they still
            # had rows for their other groups.
            pos = end
            if any(a <= start and end <= b for a, b in diluted):
                continue
            if _CHAIN_TAIL.search(text[:start]):
                continue
            dose = _read_amount(match)
            if dose is None:
                continue
            return dose
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



# Sentinel meaning "two figures for this slot disagreed in unit and neither
# is recorded". Never returned to a caller of parse_panel - _parse strips
# these slots out before either parse_panel or conflicting_slots sees the
# result - but it has to be distinguishable from every real dose and from
# None (which means "no figure seen yet"), so a private object identity is
# used rather than a value that could collide with parsed data.
_CONFLICT = object()


def _widen(existing, dose):
    """Several figures for one group and method: keep the span they cover.

    One product does this - FLY AZOT publishes 200 cc for dry farming and
    250 cc for irrigated in the same unqualified block. Keeping the first would
    silently pick one of two published figures; the span the source's own
    numbers cover states both, and invents nothing between them.

    Units that disagree are NOT merged and NOT resolved by picking one - this
    is not hypothetical, it is FLY AZOT again, a different clause of the same
    panel. Its drip sentence reads "(Bir dekara 250 cc) Damlama ..." - a
    FOLIAR figure that _method_of (see its docstring) attributes to drip
    because "Damlama" is simply the next word in the sentence - and the real
    drip figure, "1 – 1,5 litre", follows a few words later in the same
    clause chain. There is no density on the page to convert a cc to a litre,
    keeping the first published figure would silently prefer 250 cc over the
    real 1-1.5 litre (roughly four to six times too low - a farmer buying
    exactly the wrong amount), and widening to "250-1500 cc" would assert a
    span the page never states. So a unit mismatch resolves to _CONFLICT: the
    slot is dropped entirely, and conflicting_slots() below is how the caller
    learns a slot went missing this way rather than never having a figure.
    """
    if existing is _CONFLICT:
        return _CONFLICT
    if existing is None:
        return dose
    if existing[2] != dose[2]:
        return _CONFLICT
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

    KNOWN WEAKNESS, stated plainly because it was once argued away. This takes
    the FIRST method word anywhere in the clause, wherever it sits relative to
    the amount, so a clause that mentions one method while carrying the other's
    figure is attributed wrongly - FLY AZOT does exactly that. Today every such
    misattribution collides with the correct figure in a DIFFERENT unit, so
    _widen's conflict rule catches it and drops the slot. That is an empirical
    property of these 48 panels, NOT a structural guarantee: a misattributed
    figure sharing the correct one's unit would merge into a silently wrong
    span, with no conflict raised and nothing looking empty. Narrowing this to
    the method word nearest the amount was considered and does not fix FLY AZOT
    (its clause names no foliar word at all), so it was left rather than
    changed for the appearance of rigour.
    """
    for key, pattern in _METHODS:
        if re.search(pattern, clause, re.I):
            return key
    return "damlama"


# A group heading immediately preceded by "tarla" - "Tarla sebzelerinde ve
# Tarla bitkilerinde 500 gr" (HIGRO FERFORCE) - describes a sub-case of that
# group ("field-grown vegetables") rather than reopening the panel's own
# top-level heading for it. See _segments and _parse below.
_SUBQUALIFIER_RE = re.compile(r"tarla\s*$", re.I)


def _segments(text: str) -> list[tuple[str, str, bool]]:
    """Split a panel into (group, text, subqualified) triples at its group
    headings.

    subqualified is True when the heading was reached via "Tarla <group>"
    rather than a plain heading of its own. _GROUP_RE's sebze/meyve patterns
    have no lookbehind for "tarla" - one already exists for the genuine "no
    colon" headings (see _GROUP_RE's comment) and stacking another exception
    onto it was rejected as too fragile - so "sebzelerinde" inside "Tarla
    sebzelerinde" opens a same-named sebze segment same as a real heading
    would. Measured across all 48 panels: HIGRO FERFORCE is the only place
    this fires.
    """
    matches = list(_GROUP_RE.finditer(text))
    if not matches:
        return [(ALL_GROUPS, text, False)]
    out = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        head = match.group("head").lower()
        group = next(key for key, pattern in _GROUPS
                     if re.fullmatch(pattern, head, re.I))
        preceding = text[max(0, match.start() - 10):match.start()]
        subqualified = group != "tarla" and bool(_SUBQUALIFIER_RE.search(preceding))
        out.append((group, text[match.end():end], subqualified))
    return out


def _parse(text: str):
    """Shared body for parse_panel and conflicting_slots.

    Builds the {group: {method: (low, high, unit)}} mapping exactly as before,
    then makes a second pass to pull out any slot that must not ship: one
    _widen marked as _CONFLICT (two figures for one slot disagreed in unit),
    or one belonging to a group that _segments flagged as subqualified (two
    figures for one slot came from differently-qualified sub-cases of the
    page - HIGRO FERFORCE's "sebze", which is both a plain heading and a
    "Tarla sebzelerinde" sub-case with a different figure). Both are the same
    shape of problem - a slot with more than one published answer and no
    principled way to choose - so both are surfaced the same way, through
    conflicting_slots, rather than one shipping a silently partial figure.
    Doing both passes here, once, is what lets parse_panel's return type stay
    untouched while still giving the converter somewhere to ask what got
    dropped and why.
    """
    result: dict[str, dict[str, tuple[float, float, str]]] = {}
    ambiguous: set[str] = set()
    for group, segment, subqualified in _segments(text):
        if subqualified:
            ambiguous.add(group)
        for clause in _CLAUSE.split(segment):
            dose = parse_dose(clause)
            if dose is None:
                continue
            slot = result.setdefault(group, {})
            method = _method_of(clause)
            slot[method] = _widen(slot.get(method), dose)

    conflicts: list[tuple[str, str]] = []
    for group in list(result):
        for method in list(result[group]):
            if group in ambiguous or result[group][method] is _CONFLICT:
                conflicts.append((group, method))
                del result[group][method]
        if not result[group]:
            del result[group]
    return result, tuple(conflicts)


def parse_panel(text: str) -> dict[str, dict[str, tuple[float, float, str]]]:
    """A whole Uygulama panel as {group: {method: (low, high, unit)}}.

    Only per-dekar figures survive; dilutions are dropped by parse_dose. A
    panel yielding nothing returns an empty mapping, which is how the converter
    learns to report it rather than write an empty row. A slot where two
    figures disagreed in unit ALSO yields nothing for that slot - see
    conflicting_slots() to tell that apart from a slot that was never filled.
    """
    result, _unused_conflicts = _parse(text)
    return result


def conflicting_slots(text: str) -> tuple[tuple[str, str], ...]:
    """(group, method) pairs dropped because two figures disagreed in unit.

    parse_panel(text) cannot show this on its own: a dropped slot and a slot
    that never had a figure both look like "not present" in its mapping, and
    the converter's coverage report needs to tell those apart to name FLY
    AZOT rather than silently count it as clean. Empty when nothing conflicted.
    """
    _unused_result, conflicts = _parse(text)
    return conflicts
