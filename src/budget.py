"""Budget inputs, arithmetic, and the framing that keeps a figure an estimate.

THE MODEL PERFORMS NO ARITHMETIC AND MAKES NO APPEARANCE. Every number a user
sees from this route is computed here, in Python, from values the user typed
into a form. The route does not call the LLM at all.

NOTHING IS READ OUT OF THE QUESTION. The previous attempt inferred which number
in a sentence belonged to which slot; its review found five wrong money figures.
That inference is gone: values arrive from labelled fields.

THE UNIT IS A SELECTION, NOT AN INFERENCE. A form alone does not fix this. A
farmer who harvested 2 tons from 5 donum holds "2 ton" in mind, not "400 kg/da",
and would type 2000 into a per-dekar field - five times too high, and silent.
So the form asks for the TOTAL harvest with a kg/ton selector and derives the
per-dekar figure itself. Area and price get the same treatment.

This module imports nothing from src/engine.py: with no text parsing there is
nothing to normalise, so it is values in, text out.
"""
from __future__ import annotations

import re

# A complete Turkish number token, with BOTH boundaries anchored. The pattern is
# inherited from the reviewed extraction module: it refuses "1.5" and "1.2.3"
# outright rather than re-parsing them from the middle, which is how a scanning
# regex turns "250.000" into "000".
_NUM_RE = re.compile(r"^(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)$")


def parse_tr_number(text: str) -> float | None:
    """Read one FIELD's contents. Never a sentence - that is the point."""
    token = (text or "").strip()
    if not _NUM_RE.match(token):
        return None
    return float(token.replace(".", "").replace(",", "."))


def format_tr(value: float, decimals: int) -> str:
    """Turkish number formatting: thousands dot, decimal comma.

    Written out rather than delegated to a locale library, which needs the
    locale to be installed on the host and fails differently per platform.
    """
    rounded = round(value, decimals)
    # Derive sign from rounded value, not raw value: values that round to
    # zero display as "0" not "-0", since -0.0 < 0 is False in Python
    sign = "-" if rounded < 0 else ""
    rounded = abs(rounded)
    whole = int(rounded)
    groups = f"{whole:,}".replace(",", ".")
    if decimals <= 0:
        return f"{sign}{groups}"
    frac = round((rounded - whole) * (10 ** decimals))
    return f"{sign}{groups},{frac:0{decimals}d}"


from dataclasses import dataclass


@dataclass(frozen=True)
class UnitOption:
    id: str
    label: str
    factor: float          # multiply by this to reach the canonical unit
    # A per-area unit needs the area before it means anything. Kept a property
    # of the UNIT rather than a second field, so the conversion stays one line
    # and a new per-area unit needs no new branch.
    per_area: bool = False


@dataclass(frozen=True)
class FieldSpec:
    id: str
    label: str
    required: bool
    min_value: float
    min_exclusive: bool
    units: tuple[UnitOption, ...]


# The single source of truth. The form the client draws and the validation the
# server runs are both derived from this tuple; deriving them separately is how
# a client stops marking a field required while the server keeps rejecting it.
FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("area", "Alan", True, 0.0, True,
              (UnitOption("donum", "dönüm", 1.0),
               UnitOption("hektar", "hektar", 10.0))),
    # "Toplam" would be wrong under kg/dekar, so the label is neutral across all
    # three units. The per-dekar unit exists because TUIK publishes yields that
    # way and P2b prefills them; a farmer stating their own harvest still picks
    # kg or ton and states a total, exactly as in P1.
    FieldSpec("yield_total", "Ürün miktarı", True, 0.0, False,
              (UnitOption("kg", "kg", 1.0),
               UnitOption("ton", "ton", 1000.0),
               UnitOption("kg_da", "kg/dekar", 1.0, per_area=True))),
    FieldSpec("price", "Fiyat", True, 0.0, False,
              (UnitOption("tl_kg", "TL/kg", 1.0),
               UnitOption("tl_ton", "TL/ton", 0.001))),
    # Cost has no second plausible unit, so it carries one option rather than a
    # selector. Optional: without it we compute no margin figure, though the
    # answer still invites the user to supply one.
    FieldSpec("cost", "Masraf", False, 0.0, False,
              (UnitOption("tl", "TL", 1.0),)),
)

_FIELDS_BY_ID = {f.id: f for f in FIELDS}


@dataclass(frozen=True)
class Value:
    amount: float
    source: str            # "user" | "norm" | "empty"; nothing sets "norm" yet


@dataclass(frozen=True)
class BudgetInputs:
    """Canonical units throughout: dekar, kg, TL/kg, TL."""
    area_da: Value
    yield_kg: Value
    price_tl_kg: Value
    cost_tl: Value | None
    # Deliberately unwired: FIELDS has no crop entry and form_spec() never emits
    # one, so nothing but a test calling validate()/render() directly ever sets
    # this. It is not filled from the mobile profile either - profile.crops is
    # free text that may name several crops, and folding that into one slot here
    # would be exactly the kind of inference this whole route exists to remove.
    # The next phase makes crop real: it becomes the key that selects a yield
    # and price norm, and it arrives as an explicit selection, not a guess.
    crop: str | None = None


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str


def _coerce(value: object) -> float | None:
    """Accept a JSON number as readily as the string a text input produces.

    bool is checked first because it is a subclass of int in Python: without
    the guard, True would silently become 1 dekar.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return parse_tr_number(value)
    return None


def _read(spec: FieldSpec, raw: dict, area_da: float | None
          ) -> tuple[Value | None, FieldError | None]:
    entry = raw.get(spec.id)
    if not isinstance(entry, dict) or entry.get("value") in (None, ""):
        if spec.required:
            return None, FieldError(spec.id, f"{spec.label} alanını doldurun.")
        return None, None

    amount = _coerce(entry.get("value"))
    if amount is None:
        return None, FieldError(
            spec.id, f"{spec.label} bir sayı olmalı. Ondalık için virgül kullanın.")

    unit = next((u for u in spec.units if u.id == entry.get("unit")), None)
    if unit is None:
        return None, FieldError(spec.id, f"{spec.label} için birimi seçin.")

    if spec.min_exclusive and amount <= spec.min_value:
        return None, FieldError(
            spec.id, f"{spec.label} sıfırdan büyük olmalı.")
    if not spec.min_exclusive and amount < spec.min_value:
        return None, FieldError(spec.id, f"{spec.label} negatif olamaz.")

    if unit.per_area:
        if area_da is None:
            # Refused, never multiplied by a guessed area and never zeroed.
            return None, FieldError(
                spec.id,
                f"{spec.label} için dekar başına değer girdiniz; "
                f"önce alanı doldurun.")
        amount = amount * area_da

    return Value(amount * unit.factor, "user"), None


def validate(raw: dict) -> tuple[BudgetInputs | None, list[FieldError]]:
    """Read every field, collect every error. Never raises.

    Reports ALL errors rather than the first, so a user fixing a form is not
    walked through them one round trip at a time.
    """
    raw = raw if isinstance(raw, dict) else {}
    values: dict[str, Value | None] = {}
    errors: list[FieldError] = []

    # The area is read before everything else because a per-area unit cannot be
    # converted without it. Reading it out of FIELDS order rather than relying
    # on the tuple happening to list it first: that order is a layout decision,
    # not a contract, and a reorder would silently break every per-area field.
    area_spec = _FIELDS_BY_ID["area"]
    area_value, area_error = _read(area_spec, raw, None)
    values[area_spec.id] = area_value
    if area_error is not None:
        errors.append(area_error)
    area_da = area_value.amount if area_value is not None else None

    for spec in FIELDS:
        if spec.id == area_spec.id:
            continue
        value, error = _read(spec, raw, area_da)
        values[spec.id] = value
        if error is not None:
            errors.append(error)

    if errors:
        return None, errors

    crop = raw.get("crop")
    return BudgetInputs(
        area_da=values["area"],
        yield_kg=values["yield_total"],
        price_tl_kg=values["price"],
        cost_tl=values["cost"],
        crop=crop if isinstance(crop, str) and crop.strip() else None,
    ), []


def form_spec(errors: list[FieldError]) -> dict:
    """Serialise FIELDS for the client, attaching each error to its own field.

    `value` and `source` ship EMPTY in P1 and are on the wire anyway. P2 fills
    them from the norm layer, and when it does the wire format, the card and the
    arithmetic all stay exactly as they are - only the contents change.
    """
    by_field = {e.field: e.message for e in errors}
    return {
        "fields": [
            {
                "id": f.id,
                "label": f.label,
                "required": f.required,
                "units": [{"id": u.id, "label": u.label} for u in f.units],
                "value": "",
                "source": "empty",
                "error": by_field.get(f.id),
            }
            for f in FIELDS
        ]
    }


@dataclass(frozen=True)
class BudgetResult:
    yield_kg_da: float
    revenue_tl: float
    cost_tl: float | None
    margin_tl: float | None
    margin_pct: float | None


def compute(inputs: BudgetInputs) -> BudgetResult:
    """All arithmetic for this route lives here, in one place, on canonical units.

    validate() has already rejected a zero area, so the per-dekar division is
    safe; the revenue guard below is the one that is not implied by validation,
    because a zero harvest or a zero price is legitimate.
    """
    revenue = inputs.yield_kg.amount * inputs.price_tl_kg.amount
    cost = inputs.cost_tl.amount if inputs.cost_tl is not None else None
    margin = None if cost is None else revenue - cost
    pct = None if (margin is None or revenue <= 0) else margin / revenue * 100
    return BudgetResult(
        yield_kg_da=inputs.yield_kg.amount / inputs.area_da.amount,
        revenue_tl=revenue,
        cost_tl=cost,
        margin_tl=margin,
        margin_pct=pct,
    )


# Appended BY CODE, never asked of the model - the fertplan.FRAMING pattern.
# This sentence is the line between a calculation and a forecast.
FRAMING = (
    "Bu hesap bir tahmindir ve tamamen sizin girdiğiniz rakamlara dayanır; "
    "fiyat veya verim öngörüsü değildir."
)

# Written to stand alone: a deployed client that cannot draw the form shows only
# this, so it names the figures it needs instead of pointing at a widget. The
# wording also survives P2 - when norms arrive the fields come prefilled and the
# sentence still reads correctly.
ASK_FOR_NUMBERS = (
    "Hesaplayabilmem için birkaç rakama ihtiyacım var: ektiğiniz alan, aldığınız "
    "toplam ürün, ürünün satış fiyatı ve masrafınız. Bu rakamları verirseniz "
    "gelirinizi ve kâr marjınızı hesaplayabilirim."
)

# The failure mode of this route is silence, never a guess: there is no fallback
# to the model path, because an LLM answer about money is what this spec removes.
COMPUTE_FAILED = (
    "Hesaplamayı tamamlayamadım. Lütfen girdiğiniz değerleri kontrol edip "
    "tekrar deneyin."
)


def _format_qty(value: float) -> str:
    """Format a quantity for the restated line without rounding it away.

    The restated line exists so the user can check what the calculation was
    made from; it stands in for an upper bound on input values, so it has to
    echo what was typed rather than a rounded stand-in. format_tr(x, 0) would
    turn 2,5 into "2", silently disagreeing with the arithmetic underneath it,
    which still uses the true 2,5.
    """
    if value == int(value):
        return format_tr(value, 0)
    # 2,5 formats to "2,50" at two decimals, and a value that rounds to a
    # whole number at two decimals (e.g. 12.995052770448549) formats to
    # "13,00" - both are padding, not something the user typed, so strip
    # every trailing zero and then the now-bare comma. This branch only runs
    # when value != int(value), so format_tr(value, 2) always contains a
    # comma; rstrip("0") can only eat digits after it, never a whole
    # number's own trailing zeros (those go through the branch above).
    return format_tr(value, 2).rstrip("0").rstrip(",")


def render(inputs: BudgetInputs, result: BudgetResult) -> str:
    """Code-written Turkish. Restates its inputs before stating its result."""
    crop = f" {inputs.crop} için" if inputs.crop else ""
    given = [
        f"**{_format_qty(inputs.area_da.amount)} dönüm**",
        f"toplam **{_format_qty(inputs.yield_kg.amount)} kg** "
        f"(dekara {_format_qty(result.yield_kg_da)} kg)",
        f"kilogram fiyatı **{format_tr(inputs.price_tl_kg.amount, 2)} TL**",
    ]
    if result.cost_tl is not None:
        given.append(f"masraf **{format_tr(result.cost_tl, 2)} TL**")

    lines = [f"Girdiğiniz değerlere göre{crop}: " + ", ".join(given) + ".", ""]

    if result.margin_tl is None:
        lines.append(f"Gelir **{format_tr(result.revenue_tl, 2)} TL**.")
        lines.append(
            "Masrafınızı da girerseniz kâr marjınızı da hesaplayabilirim.")
    else:
        pct = ("" if result.margin_pct is None
               else f" (kâr marjı %{format_tr(result.margin_pct, 0)})")
        lines.append(
            f"Gelir **{format_tr(result.revenue_tl, 2)} TL** · "
            f"Masraf **{format_tr(result.cost_tl, 2)} TL** · "
            f"**Marj {format_tr(result.margin_tl, 2)} TL**{pct}"
        )

    lines.extend(["", FRAMING])
    return "\n".join(lines)
