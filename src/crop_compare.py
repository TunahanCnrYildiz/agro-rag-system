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
from dataclasses import dataclass
from functools import lru_cache

from src import norms
from src.budget import FieldError, format_qty, format_tr
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


@dataclass(frozen=True)
class CompareInputs:
    """Two crop ids the farmer chose, and the province their figures come from."""
    first: str
    second: str
    province: str | None = None


def _known(table) -> dict[str, str]:
    """crop id -> label, for the crops this province actually carries."""
    return {row.crop: row.label for row in (table or ())}


def validate(raw: object, table) -> tuple[CompareInputs | None, list[FieldError]]:
    """Read both selections, collect every error. Never raises.

    The ids are checked against the table rather than believed: they arrive
    from a client, and a crop we hold no row for must become a field error
    rather than an empty answer with no explanation.
    """
    raw = raw if isinstance(raw, dict) else {}
    known = _known(table)
    errors: list[FieldError] = []
    chosen: list[str] = []

    for field, label in (("first", "Birinci ürün"), ("second", "İkinci ürün")):
        value = raw.get(field)
        value = value.strip() if isinstance(value, str) else ""
        if not value:
            errors.append(FieldError(field, f"{label} seçin."))
        elif value not in known:
            errors.append(FieldError(
                field, f"{label} için bu ilde yayımlanmış bir rakam yok."))
        else:
            chosen.append(value)

    if len(chosen) == 2 and chosen[0] == chosen[1]:
        errors.append(FieldError(
            "second", "Karşılaştırma için iki farklı ürün seçin."))

    if errors:
        return None, errors
    return CompareInputs(first=chosen[0], second=chosen[1]), []


def form_spec(errors: list[FieldError], table, submitted: object = None,
              province: str | None = None) -> dict:
    """Serialise the card for the client, attaching each error to its field.

    Only ids and labels travel. The budget card ships a province of prefill
    cells because it prefills two fields from them; this card fills two selects
    and nothing else, and 246 rows of figures would be dead weight on the wire.
    """
    submitted = submitted if isinstance(submitted, dict) else {}
    by_field = {e.field: e.message for e in errors}
    first = submitted.get("first")
    second = submitted.get("second")
    return {
        "kind": "crop_compare",
        "province": province,
        "crops": [{"id": row.crop, "label": row.label} for row in (table or ())],
        "first": first if isinstance(first, str) else "",
        "second": second if isinstance(second, str) else "",
        "errors": {"first": by_field.get("first"),
                   "second": by_field.get("second")},
    }


@dataclass(frozen=True)
class CropFigures:
    """One crop's published figures, and what they come to per dekar.

    `missing` names the half we do not hold - "verim" or "fiyat" - so the
    answer can say which one rather than printing a blank.
    """
    label: str
    yield_value: object | None       # norms.NormValue
    price_value: object | None       # norms.NormValue
    revenue_tl_da: float | None
    missing: str | None
    # TUIK publishes this crop's yield per TREE, so no per-dekar money figure
    # exists for it. NOT folded into `missing`: that field names the half we
    # do not HOLD, and here both halves are held and cannot be combined.
    per_tree: bool = False


def _figures(row, latest_year: int | None) -> CropFigures:
    # A row is served PER TREE exactly when its yield_kg_tree resolved - the
    # same test, character for character, that src/budget.py's _yield_cell
    # uses. The two surfaces decide this separately and disagreed on 1.568
    # cells for a round; a test pins them together.
    per_tree = row.yield_kg_tree is not None
    yield_value = row.yield_kg_tree if per_tree else row.yield_kg_da
    price = row.price_tl_kg
    # A price from an older year is not a smaller number, it is a different
    # currency: P2b measured Ordu's `Arpa (Diğer)` prefilling a 2018 price nine
    # times too low into a bold revenue figure. Yield is left alone - it does
    # not inflate, and its five-year range is where an outlier shows.
    if price is not None and (latest_year is None or price.year != latest_year):
        price = None
    missing = None
    if yield_value is None:
        missing = "verim"
    elif price is None and not per_tree:
        # A per-tree row never blames the PRICE for its missing revenue. That
        # branch's message is "there is a yield but no price, so I am not
        # computing revenue", which here names a false cause - the revenue was
        # refused for the unit - and suggests a price would fix it.
        missing = "fiyat"
    revenue = (None if (missing is not None or per_tree)
               else yield_value.amount * price.amount)
    return CropFigures(label=row.label, yield_value=yield_value,
                       price_value=price, revenue_tl_da=revenue,
                       missing=missing, per_tree=per_tree)


def compute(inputs: CompareInputs, table,
            latest_year: int | None) -> tuple[CropFigures, CropFigures]:
    """All arithmetic for this route: one multiplication per crop.

    Never a comparison, a ratio or a difference. The two figures sit beside
    each other and the reader draws their own conclusion - which is the whole
    design, because the cost that would decide it is not in this project.
    """
    rows = {row.crop: row for row in (table or ())}
    return tuple(_figures(rows[crop_id], latest_year)
                 for crop_id in (inputs.first, inputs.second))


# Appended BY CODE on every computed answer, never asked of a model - the
# fertplan.FRAMING pattern.
ATTRIBUTION = (
    "Rakamlar TÜİK'in yayımladığı il ortalamalarıdır; tek bir tarlanın verimi "
    "veya sizin alacağınız fiyat için öngörü değildir."
)

# THE SENTENCE THIS ROUTE EXISTS FOR. Two gross figures side by side read as a
# ranking, and the number that would decide it - what each crop COSTS to grow -
# is not in this project at all. Measured on Konya 2025: domates 115.664 TL/da
# against biber 125.841 TL/da, nine percent apart, which tells a farmer nothing
# about which one pays better.
NOT_PROFIT = (
    "Bu rakamlar dekara BRÜT gelirdir, masraf içermez. İki ürünün girdi ve "
    "işçilik masrafı aradaki farktan çok daha fazla ayrışabilir, bu yüzden "
    "kârlılık sıralamasını bu tablodan söyleyemem. Kendi masrafınızı "
    "girerek bütçe hesabı yaptırırsanız kâr karşılaştırmasını yapabilirsiniz."
)

# The half of NOT_PROFIT that is true of a SINGLE figure too. NOT_PROFIT does
# two jobs - warn that the figure is gross, and refuse a ranking - and only the
# second needs two figures. Printed whenever any revenue reached the page and
# NOT_PROFIT did not.
GROSS_ONLY = (
    "Basılan gelir rakamı dekara BRÜT gelirdir, masraf içermez."
)

# Only when one crop showed a revenue AND the other is per-tree. A crop can
# also lack a revenue because the province publishes nothing for it, and this
# sentence would then assert a per-tree reason that is untrue - the failure
# this route has already shipped two fixes for.
ONLY_ONE_REVENUE = (
    "Bu tabloda tek bir gelir rakamı var, dolayısıyla bir karşılaştırma değil: "
    "diğer ürünün verimi ağaç başına yayımlandığı için aynı birime "
    "getirilemiyor."
)

# Written BY CODE and printed under the crop it explains, never at the foot of
# the answer - a reader must not have to work out which crop it refers to.
PER_TREE_NOTE = (
    "TÜİK bu ürünün verimini ağaç başına yayımlıyor; dekara çevirmek "
    "yayımlanmayan bir dikim sıklığı gerektirdiği için dekara gelir "
    "hesaplamıyorum."
)

ASK_FOR_CROPS = (
    "Karşılaştırayım: hangi iki ürünü düşünüyorsunuz? İkisini seçerseniz "
    "ilinizde yayımlanmış verim ve fiyat rakamlarını yan yana koyarım."
)

# Written to stand alone: without a province there is no provincial figure to
# print, and guessing one produces confidently wrong numbers.
NO_PROVINCE = (
    "Karşılaştırma yapabilmem için hangi ilde olduğunuzu bilmem gerekiyor; "
    "verim ve fiyat rakamları ilden ile değişiyor. İlinizi yazarsanız o ilin "
    "yayımlanmış rakamlarını yan yana koyarım."
)

# The failure mode of this route is silence, never a guess.
COMPUTE_FAILED = (
    "Karşılaştırmayı tamamlayamadım. Lütfen seçimlerinizi kontrol edip tekrar "
    "deneyin."
)


def _crop_block(figures: CropFigures) -> list[str]:
    """One crop's lines. Says what is missing rather than printing a blank.

    BRANCH ORDER IS LOAD-BEARING. A genuine absence outranks everything; then
    the per-tree case; only then a missing price. Testing the price first would
    tell a per-tree crop's reader that a price is what stands between them and
    a revenue figure, which is false. `_figures` cannot currently produce a
    per-tree row with `missing == "fiyat"`, so this order is defence in depth
    rather than the only thing protecting that reader - a test pins the order
    itself, directly, so it is not "simplified" away as unreachable.
    """
    if figures.missing == "verim":
        return [f"**{figures.label}**: bu il için yayımlanmış verim rakamı yok."]

    if figures.per_tree:
        y = figures.yield_value
        head = (f"**{figures.label}**: verim {format_qty(y.amount)} kg/ağaç "
                f"(TÜİK {y.year}, {y.region})")
        if figures.price_value is not None:
            # A comma, not the revenue line's `×`: that sign announces a
            # product, and this route computes none for a per-tree crop.
            head += (f", fiyat {format_tr(figures.price_value.amount, 2)} TL/kg "
                     f"(TÜİK {figures.price_value.year})")
        lines = [head]
        if y.recent_min is not None and y.recent_max is not None:
            lines.append(f"   verimde önceki 5 yıl: {format_qty(y.recent_min)}–"
                         f"{format_qty(y.recent_max)} kg/ağaç")
        lines.append(f"   {PER_TREE_NOTE}")
        return lines

    if figures.missing == "fiyat":
        return [f"**{figures.label}**: verim {format_qty(figures.yield_value.amount)} "
                f"kg/da (TÜİK {figures.yield_value.year}, {figures.yield_value.region}), "
                f"ancak güncel yıl için yayımlanmış fiyat yok, bu yüzden gelir "
                f"hesaplamıyorum."]

    y, p = figures.yield_value, figures.price_value
    lines = [
        # Whole lira: a gross revenue per dekar in the hundred-thousands does
        # not gain anything from kurus, and the extra digits read as precision
        # a provincial average does not have.
        f"**{figures.label}** · dekara brüt gelir "
        f"**{format_tr(figures.revenue_tl_da, 0)} TL**",
        f"   verim {format_qty(y.amount)} kg/da (TÜİK {y.year}, {y.region}) × "
        f"fiyat {format_tr(p.amount, 2)} TL/kg (TÜİK {p.year})",
    ]
    if y.recent_min is not None and y.recent_max is not None:
        lines.append(f"   verimde önceki 5 yıl: {format_qty(y.recent_min)}–"
                     f"{format_qty(y.recent_max)} kg/da")
    return lines


def render(inputs: CompareInputs, figures: tuple[CropFigures, CropFigures]) -> str:
    """Code-written Turkish. Both crops, no verdict.

    NOT_PROFIT opens with "these figures ARE gross revenue" and goes on to
    refuse a RANKING, so it needs BOTH crops to have printed one. With a single
    figure there is nothing to rank and the sentence describes a page that does
    not exist; with none it names figures that were never printed.

    NOT_PROFIT bundles two claims, and only the ranking-refusal half needs two
    figures - the gross-revenue warning is just as true of one. GROSS_ONLY is
    that first half alone: printed whenever exactly one revenue reached the
    page, so the lone figure still carries its caveat even though there is
    nothing to rank against it.

    ONLY_ONE_REVENUE covers the case NOT_PROFIT no longer does - one revenue
    beside a per-tree crop - and stops the lone money figure reading as a
    default winner. It only ever appears together with GROSS_ONLY, never
    alone: a printed revenue is always gross, whether or not the OTHER crop
    happens to be per-tree.
    """
    where = f" ({inputs.province})" if inputs.province else ""
    lines = [f"İki ürünün yayımlanmış rakamları{where}:", ""]
    for crop in figures:
        lines.extend(_crop_block(crop))
        lines.append("")
    lines.append(ATTRIBUTION)
    revenues = [crop.revenue_tl_da is not None for crop in figures]
    if all(revenues):
        lines.extend(["", NOT_PROFIT])
    elif any(revenues):
        # GROSS_ONLY first, ONLY_ONE_REVENUE second - the same order NOT_PROFIT
        # itself uses internally (gross caveat, then the comparison refusal),
        # so the one-sentence and two-sentence forms read the same way.
        lines.extend(["", GROSS_ONLY])
        # The rule is "the crop with NO revenue is per-tree"; `any` asks the
        # weaker "either crop is per-tree". They coincide only because
        # `_figures` never lets a per_tree row carry a revenue - the same
        # invariant `_crop_block`'s branch order leans on. If this route ever
        # computed a per-tree revenue, `any` would start firing on the crop
        # WITH the money figure instead of the one without.
        if any(crop.per_tree for crop in figures):
            lines.append(ONLY_ONE_REVENUE)
    return "\n".join(lines)
