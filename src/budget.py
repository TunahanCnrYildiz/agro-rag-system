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
    FieldSpec("yield_total", "Toplam ürün", True, 0.0, False,
              (UnitOption("kg", "kg", 1.0),
               UnitOption("ton", "ton", 1000.0))),
    FieldSpec("price", "Fiyat", True, 0.0, False,
              (UnitOption("tl_kg", "TL/kg", 1.0),
               UnitOption("tl_ton", "TL/ton", 0.001))),
    # Cost has no second plausible unit, so it carries one option rather than a
    # selector. Optional: without it we report revenue and say nothing about
    # margin, which is what "yillik ne kadar gelir beklerim" actually asks.
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


def _read(spec: FieldSpec, raw: dict) -> tuple[Value | None, FieldError | None]:
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

    return Value(amount * unit.factor, "user"), None


def validate(raw: dict) -> tuple[BudgetInputs | None, list[FieldError]]:
    """Read every field, collect every error. Never raises.

    Reports ALL errors rather than the first, so a user fixing a form is not
    walked through them one round trip at a time.
    """
    raw = raw if isinstance(raw, dict) else {}
    values: dict[str, Value | None] = {}
    errors: list[FieldError] = []
    for spec in FIELDS:
        value, error = _read(spec, raw)
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
