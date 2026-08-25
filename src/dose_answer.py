"""The product-dose route: the manufacturer's own per-dekar figure, times the
farmer's area, and nothing else.

THE MODEL PERFORMS NO ARITHMETIC AND MAKES NO APPEARANCE. Every number a user
sees from this route is computed here, in Python, from a figure the
manufacturer published and an area the user selected. The route does not call
the LLM at all.

NOTHING IS READ OUT OF THE QUESTION. "5 donumum var, ne kadar alirim?" has
exactly the shape P1 removed from the budget route - a number in a sentence
that must reach arithmetic - so it gets exactly the same treatment: labelled
fields, a unit that is a SELECTION, no inference.

THE METHOD IS AN ATTRIBUTE OF THE ANSWER, NOT AN INPUT. 37 of the 42 products
with a per-area dose publish it for drip irrigation only, so a method selector
would offer a choice in appearance only. Every figure that exists for the
product and group is printed, each labelled with the method the source
attached to it.

This module imports nothing from src/engine.py - the boundary src/norms.py,
src/budget.py and src/doses.py all keep.
"""
from __future__ import annotations

from dataclasses import dataclass

from src import doses
from src.budget import FieldError, UnitOption, coerce_number, format_qty
from src.dose_parse import GROUP_KEYS

# The three groups the panels segment by, with the label the card prints. The
# ids come from the parser rather than being restated, so a group the data can
# carry and a button the farmer can press cannot drift apart.
_GROUP_LABELS = {"sebze": "Sebze", "meyve": "Meyve", "tarla": "Tarla bitkisi"}
GROUPS: tuple[tuple[str, str], ...] = tuple((key, _GROUP_LABELS[key])
                                            for key in GROUP_KEYS)
_GROUP_IDS = frozenset(GROUP_KEYS)

# P1's area control, unchanged, including the unit-as-selection rule.
AREA_UNITS: tuple[UnitOption, ...] = (UnitOption("donum", "dönüm", 1.0),
                                      UnitOption("hektar", "hektar", 10.0))

AREA_LABEL = "Alan"


@dataclass(frozen=True)
class DoseInputs:
    """Canonical throughout: dekar."""
    product: str
    group: str
    area_da: float


def _read_area(raw: dict) -> tuple[float | None, FieldError | None]:
    entry = raw.get("area")
    if not isinstance(entry, dict) or entry.get("value") in (None, ""):
        return None, FieldError("area", f"{AREA_LABEL} alanını doldurun.")
    amount = coerce_number(entry.get("value"))
    if amount is None:
        return None, FieldError(
            "area", f"{AREA_LABEL} bir sayı olmalı. Ondalık için virgül kullanın.")
    unit = next((u for u in AREA_UNITS if u.id == entry.get("unit")), None)
    if unit is None:
        return None, FieldError("area", f"{AREA_LABEL} için birimi seçin.")
    if amount <= 0:
        return None, FieldError("area", f"{AREA_LABEL} sıfırdan büyük olmalı.")
    return amount * unit.factor, None


def validate(raw: object) -> tuple[DoseInputs | None, list[FieldError]]:
    """Read every field, collect every error. Never raises.

    The product is checked against the table rather than believed, for the same
    reason budget._verify looks the crop up: it arrives from a client, and a
    name we hold no figure for must become a field error rather than an empty
    answer with no explanation.
    """
    raw = raw if isinstance(raw, dict) else {}
    errors: list[FieldError] = []

    product = raw.get("product")
    product = product.strip() if isinstance(product, str) else ""
    if not product:
        errors.append(FieldError("product", "Ürünü seçin."))
    elif product not in doses.available_products():
        errors.append(FieldError(
            "product",
            "Bu ürünün sayfasında dekara doz yayımlanmamış; elimde bir rakam yok."))

    group = raw.get("group")
    if not isinstance(group, str) or group not in _GROUP_IDS:
        errors.append(FieldError(
            "group", "Tarlanızın grubunu seçin: sebze, meyve veya tarla bitkisi."))

    area_da, area_error = _read_area(raw)
    if area_error is not None:
        errors.append(area_error)

    if errors:
        return None, errors
    return DoseInputs(product=product, group=group, area_da=area_da), []


def form_spec(errors: list[FieldError], submitted: object = None) -> dict:
    """Serialise the card for the client, attaching each error to its field.

    `submitted` is the payload that failed validation. Echoing it back is not a
    nicety: the card seeds its state from this dict, so without it a single bad
    field wipes the product and the group along with the area.

    `kind` is here so a client that grows a second card type can tell them
    apart. The dose form travels on its own SSE event and its own response key,
    so an already-deployed build never receives one at all - see src/engine.py.
    """
    submitted = submitted if isinstance(submitted, dict) else {}
    by_field = {e.field: e.message for e in errors}

    entry = submitted.get("area")
    entry = entry if isinstance(entry, dict) else {}
    value = entry.get("value")
    unit = entry.get("unit")

    product = submitted.get("product")
    group = submitted.get("group")
    return {
        "kind": "product_dose",
        "products": list(doses.available_products()),
        "groups": [{"id": key, "label": label} for key, label in GROUPS],
        "product": product if isinstance(product, str) else "",
        "group": group if isinstance(group, str) else "",
        "area": {
            "label": AREA_LABEL,
            # A number that arrived as JSON becomes text, because that is what
            # a text input holds and what the parser reads.
            "value": "" if value is None else str(value),
            # An unrecognised unit falls back to the first, or the card renders
            # with no chip selected and no way to tell why.
            "unit": unit if any(u.id == unit for u in AREA_UNITS) else AREA_UNITS[0].id,
            "units": [{"id": u.id, "label": u.label} for u in AREA_UNITS],
        },
        "errors": {"product": by_field.get("product"),
                   "group": by_field.get("group"),
                   "area": by_field.get("area")},
    }


@dataclass(frozen=True)
class DoseTotal:
    """One published figure and what it comes to over the farmer's area.

    The published figure travels alongside the total because the answer quotes
    it: "dekara 250 gr" is the manufacturer's sentence, "1,25 kg" is ours.
    """
    method: str
    dose_low: float
    dose_high: float
    dose_unit: str
    total_low: float
    total_high: float
    total_unit: str


# The only conversion this route performs, and it is a pure one: 1000 of a
# sub-unit is the unit above it, on any page, with no density involved. A gram
# figure is NEVER turned into a litre one - that needs a density the pages do
# not give.
_PROMOTE = {"gr": ("kg", 1000.0), "cc": ("litre", 1000.0)}


def _promote(low: float, high: float, unit: str) -> tuple[float, float, str]:
    """Promote BOTH ends or neither, decided by the larger one.

    Deciding per end would print "1000 cc - 1,25 litre" for a single range,
    which reads as two different figures rather than one span.
    """
    target = _PROMOTE.get(unit)
    if target is None:
        return low, high, unit
    name, factor = target
    if max(low, high) < factor:
        return low, high, unit
    return low / factor, high / factor, name


def compute(inputs: DoseInputs) -> tuple[DoseTotal, ...]:
    """All arithmetic for this route lives here: two multiplications per figure.

    Empty when the product publishes nothing for that group - which is an
    answer ("we hold no figure"), not a zero. A zero would flow into a purchase
    quantity and say "you need 0 litres".
    """
    out = []
    for dose in doses.lookup(inputs.product, inputs.group):
        low, high, unit = _promote(dose.low * inputs.area_da,
                                   dose.high * inputs.area_da, dose.unit)
        out.append(DoseTotal(method=dose.method,
                             dose_low=dose.low, dose_high=dose.high,
                             dose_unit=dose.unit,
                             total_low=low, total_high=high, total_unit=unit))
    return tuple(out)


# Written out rather than derived by .capitalize()/.lower() at runtime: Turkish
# casing has a dotted/dotless I trap, and these strings appear inside sentences
# where the right form is not the one a case function would produce.
METHOD_LABELS = {"damlama": "Damlamadan",
                 "yaprak": "Yapraktan",
                 "toprak": "Topraktan"}

GROUP_IN_SENTENCE = {"sebze": "sebzede",
                     "meyve": "meyvede",
                     "tarla": "tarla bitkisinde"}

# Appended BY CODE, never asked of the model - the fertplan.FRAMING pattern.
# This sentence is the line between quoting a maker's dose and authoring one.
ATTRIBUTION = (
    "Bu rakam ürünün kendi sayfasında üreticinin yayımladığı dozdur; bizim "
    "önerimiz değildir."
)

# The refusal is a feature, not a shortfall. Only 8 of 48 panels state an
# interval or a number of applications, so for the other 40 the season total is
# simply not in the source; supplying one would mean authoring a programme and
# presenting it as the manufacturer's. It is unconditional rather than triggered
# by the question, because deciding "did they ask for a season total?" would put
# a Turkish text matcher back on the path this route exists to keep clear of one.
SEASON_REFUSAL = (
    "Doz TEK bir uygulama içindir. Sayfa kaç uygulama yapılacağını yazmadığı "
    "için sezon boyunca gereken toplam miktarı hesaplayamıyorum; onu söylemek "
    "üreticinin yazmadığı bir programı ona mal etmek olurdu."
)

# Written to stand alone: a deployed client that cannot draw the card shows only
# this, so it names what it needs instead of pointing at a widget.
ASK_FOR_INPUTS = (
    "Hangi üründen ne kadar almanız gerektiğini hesaplayabilirim. Üç şeye "
    "ihtiyacım var: ürün, tarlanızın grubu (sebze, meyve veya tarla bitkisi) ve "
    "alanı. Bunları verirseniz üreticinin dekara yayımladığı dozu alanınızla "
    "çarpar, bir uygulamada gereken miktarı söylerim."
)

# The failure mode of this route is silence, never a guess: there is no fallback
# to the model path, because an invented purchase quantity is what it removes.
COMPUTE_FAILED = (
    "Hesaplamayı tamamlayamadım. Lütfen seçimlerinizi kontrol edip tekrar deneyin."
)


def _amount(low: float, high: float, unit: str) -> str:
    """A range as a range; a single figure as one number."""
    if low == high:
        return f"{format_qty(low)} {unit}"
    return f"{format_qty(low)}–{format_qty(high)} {unit}"


def no_dose_for_group(inputs: DoseInputs) -> str:
    """Said, not guessed - and it names both halves of the combination.

    Deliberately prints no figure at all: the temptation this message exists to
    refuse is showing the group next door's number "for reference".

    ATTRIBUTION is NOT appended here, unlike in render(). ATTRIBUTION opens "Bu
    rakam..." - "this figure" - a demonstrative that points at a number. This
    message's whole point is that no number was printed. Appending it would
    have the answer point at a figure in the same breath it just said does not
    exist.
    """
    return (
        f"**{inputs.product}** için {GROUP_IN_SENTENCE[inputs.group]} dekara bir "
        f"doz yayımlanmamış. Bu ürünün sayfasında bu gruba ait bir rakam yok, "
        f"başka bir grubun rakamını da buraya taşımıyorum."
    )


def render(inputs: DoseInputs, totals: tuple[DoseTotal, ...]) -> str:
    """Code-written Turkish. Restates its inputs before stating its result."""
    lines = [
        f"**{inputs.product}** · {_GROUP_LABELS[inputs.group]} · "
        f"**{format_qty(inputs.area_da)} dönüm**",
        "",
    ]
    for total in totals:
        dose = _amount(total.dose_low, total.dose_high, total.dose_unit)
        whole = _amount(total.total_low, total.total_high, total.total_unit)
        lines.append(
            f"{METHOD_LABELS[total.method]} dekara **{dose}**: "
            f"{format_qty(inputs.area_da)} dönüm için bir uygulamada "
            f"**{whole}**."
        )
    lines.extend(["", ATTRIBUTION, "", SEASON_REFUSAL])
    return "\n".join(lines)
