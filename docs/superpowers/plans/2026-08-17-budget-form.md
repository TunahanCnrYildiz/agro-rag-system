# Budget Form (P1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer a farmer's money question from four form inputs, with every figure computed in Python and no model call on the route.

**Architecture:** A new dependency-free `src/budget.py` owns the field spec, parsing, validation, arithmetic and rendering. `src/engine.py` gains one short-circuit on `route == "budget"` in *both* entry points, returning either a form spec or a computed answer without touching retrieval, product matching or the LLM. `src/main.py` carries the payload in and the form out; the mobile client renders the card.

**Tech Stack:** Python 3.14, FastAPI + Pydantic v2, pytest. React Native / Expo (TypeScript) for the client.

**Spec:** `docs/superpowers/specs/2026-08-17-budget-form-design.md`

## Global Constraints

- **Run every command from the repo root.** `src/config.py` reads a root-anchored `.env`; from anywhere else the embedding model silently falls back and unrelated tests fail.
- **Windows console cannot encode Turkish.** Prefix any command that prints Turkish with `PYTHONIOENCODING=utf-8`, or keep stdout ASCII.
- **No model call and no retrieval on the `budget` route.** This is the property the whole design rests on; Task 5 pins it with a test.
- **All new API fields are optional.** The deployed APK does not know about forms and must keep working.
- **`FRAMING` is appended by code, never asked of the model** — same pattern as `fertplan.FRAMING`.
- **All user-facing text is Turkish.** All code, comments, docstrings, test names and commit messages are English.
- **No eval run is required for this plan** and no eval case is added. The route makes no model call, so an eval case would read green while asserting nothing.
- **Commit messages:** short, natural, English. No `Co-Authored-By` trailer.
- **Branch:** create `budget-form` off `main` before Task 1. Do not touch `demo`.

---

### Task 1: Turkish number parsing and formatting

The two leaf helpers everything else uses. No dependencies.

**Files:**
- Create: `src/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: nothing
- Produces: `parse_tr_number(text: str) -> float | None`, `format_tr(value: float, decimals: int) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_budget.py`:

```python
"""Unit tests for src/budget.py (no store, no model, no network)."""

from src import budget


def test_parse_accepts_a_turkish_decimal():
    assert budget.parse_tr_number("12,5") == 12.5


def test_parse_accepts_a_thousands_group():
    assert budget.parse_tr_number("1.250") == 1250.0
    assert budget.parse_tr_number("1.250,75") == 1250.75


def test_parse_accepts_a_plain_integer():
    assert budget.parse_tr_number("5") == 5.0


def test_parse_refuses_an_english_decimal():
    """'1.5' is ambiguous between 1,5 and a malformed thousands group. A visible
    field error is the right direction to fail - guessing is what this whole
    module exists to remove."""
    assert budget.parse_tr_number("1.5") is None


def test_parse_refuses_junk():
    assert budget.parse_tr_number("abc") is None
    assert budget.parse_tr_number("") is None
    assert budget.parse_tr_number("12,5,3") is None
    assert budget.parse_tr_number("-5") is None


def test_parse_tolerates_surrounding_space():
    assert budget.parse_tr_number("  5  ") == 5.0


def test_format_groups_thousands_and_uses_a_decimal_comma():
    assert budget.format_tr(20000, 2) == "20.000,00"
    assert budget.format_tr(1234567.891, 2) == "1.234.567,89"


def test_format_with_no_decimals_omits_the_comma():
    assert budget.format_tr(400, 0) == "400"
    assert budget.format_tr(5000, 0) == "5.000"


def test_format_keeps_the_sign_outside_the_grouping():
    assert budget.format_tr(-5000, 2) == "-5.000,00"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_budget.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'src.budget'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/budget.py`:

```python
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
    sign = "-" if value < 0 else ""
    rounded = abs(round(value, decimals))
    whole = int(rounded)
    groups = f"{whole:,}".replace(",", ".")
    if decimals <= 0:
        return f"{sign}{groups}"
    frac = round((rounded - whole) * (10 ** decimals))
    return f"{sign}{groups},{frac:0{decimals}d}"
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_budget.py -q
```

Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Parse and format Turkish numbers for the budget route"
```

---

### Task 2: Field spec and validation

**Files:**
- Modify: `src/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `parse_tr_number` from Task 1
- Produces:
  - `FIELDS: tuple[FieldSpec, ...]` with `FieldSpec(id, label, required, min_value, min_exclusive, units)` and `UnitOption(id, label, factor)`
  - `Value(amount: float, source: str)`
  - `BudgetInputs(area_da: Value, yield_kg: Value, price_tl_kg: Value, cost_tl: Value | None, crop: str | None)`
  - `FieldError(field: str, message: str)`
  - `validate(raw: dict) -> tuple[BudgetInputs | None, list[FieldError]]`
  - `form_spec(errors: list[FieldError]) -> dict`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_budget.py`:

```python
def _raw(area="5", area_unit="donum", total="2", total_unit="ton",
         price="10", price_unit="tl_kg", cost="5000"):
    """A complete, valid payload; each argument overrides one field."""
    raw = {
        "area": {"value": area, "unit": area_unit},
        "yield_total": {"value": total, "unit": total_unit},
        "price": {"value": price, "unit": price_unit},
    }
    if cost is not None:
        raw["cost"] = {"value": cost, "unit": "tl"}
    return raw


def test_validate_converts_every_unit_to_the_canonical_one():
    inputs, errors = budget.validate(_raw())
    assert errors == []
    assert inputs.area_da.amount == 5.0
    assert inputs.yield_kg.amount == 2000.0
    assert inputs.price_tl_kg.amount == 10.0
    assert inputs.cost_tl.amount == 5000.0


def test_validate_converts_hectares_and_tonne_prices():
    inputs, errors = budget.validate(
        _raw(area="2", area_unit="hektar", price="10000", price_unit="tl_ton"))
    assert errors == []
    assert inputs.area_da.amount == 20.0
    assert inputs.price_tl_kg.amount == 10.0


def test_validate_marks_supplied_values_as_user_sourced():
    """P2 will set 'norm' on prefilled fields; nothing sets it in P1."""
    inputs, _ = budget.validate(_raw())
    assert inputs.area_da.source == "user"


def test_cost_is_optional_and_its_absence_is_not_an_error():
    inputs, errors = budget.validate(_raw(cost=None))
    assert errors == []
    assert inputs.cost_tl is None


def test_area_must_be_greater_than_zero():
    inputs, errors = budget.validate(_raw(area="0"))
    assert inputs is None
    assert [e.field for e in errors] == ["area"]


def test_zero_harvest_is_valid_because_a_total_loss_is_a_real_answer():
    inputs, errors = budget.validate(_raw(total="0"))
    assert errors == []
    assert inputs.yield_kg.amount == 0.0


def test_a_missing_required_field_names_itself():
    raw = _raw()
    del raw["price"]
    inputs, errors = budget.validate(raw)
    assert inputs is None
    assert [e.field for e in errors] == ["price"]
    assert errors[0].message


def test_an_unparseable_value_is_a_field_error_not_an_exception():
    inputs, errors = budget.validate(_raw(price="on lira"))
    assert inputs is None
    assert [e.field for e in errors] == ["price"]


def test_an_unrecognised_unit_is_an_error_never_a_silent_default():
    """Silently assuming a unit is exactly the inference this design removes."""
    inputs, errors = budget.validate(_raw(total="2", total_unit="cuval"))
    assert inputs is None
    assert [e.field for e in errors] == ["yield_total"]


def test_a_missing_unit_is_an_error_too():
    inputs, errors = budget.validate(_raw(total="2", total_unit=""))
    assert inputs is None
    assert [e.field for e in errors] == ["yield_total"]


def test_validate_accepts_a_json_number_as_well_as_a_string():
    raw = _raw()
    raw["area"]["value"] = 5
    inputs, errors = budget.validate(raw)
    assert errors == []
    assert inputs.area_da.amount == 5.0


def test_validate_refuses_a_boolean_masquerading_as_a_number():
    """bool is a subclass of int in Python; True must not become 1 dekar."""
    raw = _raw()
    raw["area"]["value"] = True
    inputs, errors = budget.validate(raw)
    assert inputs is None
    assert [e.field for e in errors] == ["area"]


def test_crop_is_carried_through_but_never_required():
    raw = _raw()
    raw["crop"] = "domates"
    inputs, errors = budget.validate(raw)
    assert errors == []
    assert inputs.crop == "domates"
    inputs2, _ = budget.validate(_raw())
    assert inputs2.crop is None


def test_an_empty_payload_reports_every_required_field():
    inputs, errors = budget.validate({})
    assert inputs is None
    assert {e.field for e in errors} == {"area", "yield_total", "price"}


def test_form_spec_covers_exactly_the_fields_validate_knows():
    """The client draws the form from this and the server validates from FIELDS.
    If they ever come from different places they drift, and the user sees an
    error with no cause."""
    spec = budget.form_spec([])
    assert [f["id"] for f in spec["fields"]] == [f.id for f in budget.FIELDS]


def test_form_spec_carries_units_and_the_required_flag():
    spec = budget.form_spec([])
    area = next(f for f in spec["fields"] if f["id"] == "area")
    assert area["required"] is True
    assert [u["id"] for u in area["units"]] == ["donum", "hektar"]
    cost = next(f for f in spec["fields"] if f["id"] == "cost")
    assert cost["required"] is False


def test_form_spec_carries_an_empty_value_and_source_on_every_field():
    """These ship empty in P1 and exist so P2 can prefill from the norm layer
    without changing the wire format, the card, or the arithmetic."""
    spec = budget.form_spec([])
    assert all(f["value"] == "" for f in spec["fields"])
    assert all(f["source"] == "empty" for f in spec["fields"])


def test_form_spec_attaches_an_error_to_its_own_field_only():
    spec = budget.form_spec([budget.FieldError("price", "Geçersiz sayı.")])
    by_id = {f["id"]: f for f in spec["fields"]}
    assert by_id["price"]["error"] == "Geçersiz sayı."
    assert by_id["area"]["error"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_budget.py -q
```

Expected: FAIL, `AttributeError: module 'src.budget' has no attribute 'validate'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/budget.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_budget.py -q
```

Expected: `27 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Validate budget inputs from labelled fields with explicit units"
```

---

### Task 3: The arithmetic

**Files:**
- Modify: `src/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `BudgetInputs`, `validate` from Task 2
- Produces: `BudgetResult(yield_kg_da, revenue_tl, cost_tl, margin_tl, margin_pct)`, `compute(inputs: BudgetInputs) -> BudgetResult`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_budget.py`:

```python
def _computed(**kwargs):
    inputs, errors = budget.validate(_raw(**kwargs))
    assert errors == [], errors
    return inputs, budget.compute(inputs)


def test_the_critical_that_named_this_spec():
    """The extraction module reported a margin of 95.000 for this exact case.
    5 donum, 2 ton total, 10 TL/kg, 5.000 TL cost:
    2.000 kg x 10 = 20.000 revenue, minus 5.000 = 15.000."""
    _, result = _computed()
    assert result.revenue_tl == 20000.0
    assert result.margin_tl == 15000.0


def test_the_critical_that_read_a_price_as_a_cost():
    """'Kilosunu 12,5 TL, masrafim 20000 TL' put 12.5 in the cost slot. With
    labelled fields the two cannot collide; the test stays as a guard against a
    future design quietly removing that separation."""
    _, result = _computed(price="12,5", cost="20000")
    assert result.revenue_tl == 25000.0
    assert result.cost_tl == 20000.0
    assert result.margin_tl == 5000.0


def test_per_dekar_yield_is_derived_not_asked_for():
    inputs, result = _computed()
    assert result.yield_kg_da == 400.0


def test_hectares_convert_before_the_arithmetic():
    _, result = _computed(area="1", area_unit="hektar", total="10", total_unit="ton")
    assert result.yield_kg_da == 1000.0
    assert result.revenue_tl == 100000.0


def test_a_tonne_price_converts_before_the_arithmetic():
    _, result = _computed(price="10000", price_unit="tl_ton")
    assert result.revenue_tl == 20000.0


def test_a_total_loss_gives_a_margin_of_minus_the_cost():
    _, result = _computed(total="0")
    assert result.revenue_tl == 0.0
    assert result.margin_tl == -5000.0


def test_zero_revenue_yields_no_percentage_rather_than_infinity():
    _, result = _computed(total="0")
    assert result.margin_pct is None


def test_without_a_cost_only_revenue_is_reported():
    _, result = _computed(cost=None)
    assert result.revenue_tl == 20000.0
    assert result.cost_tl is None
    assert result.margin_tl is None
    assert result.margin_pct is None


def test_margin_percent_is_of_revenue():
    _, result = _computed()
    assert result.margin_pct == 75.0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_budget.py -q
```

Expected: FAIL, `AttributeError: module 'src.budget' has no attribute 'compute'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/budget.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_budget.py -q
```

Expected: `36 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Compute revenue and margin from the validated inputs"
```

---

### Task 4: Rendering and framing

**Files:**
- Modify: `src/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `BudgetInputs`, `BudgetResult`, `format_tr`
- Produces: `render(inputs: BudgetInputs, result: BudgetResult) -> str`, `FRAMING: str`, `ASK_FOR_NUMBERS: str`, `COMPUTE_FAILED: str`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_budget.py`:

```python
def test_render_restates_what_it_computed_from():
    """This is what replaces an upper bound on the inputs. A user who meant 5
    and typed 5000 reads '5.000 donum' in the first line, and a wrong unit
    selection shows up in the derived per-dekar figure."""
    inputs, result = _computed()
    text = budget.render(inputs, result)
    assert "5 dönüm" in text
    assert "dekara 400 kg" in text


def test_render_states_the_money_in_turkish_format():
    inputs, result = _computed()
    text = budget.render(inputs, result)
    assert "20.000,00 TL" in text
    assert "15.000,00 TL" in text


def test_render_includes_the_margin_percentage():
    inputs, result = _computed()
    assert "%75" in budget.render(inputs, result)


def test_render_omits_the_percentage_when_revenue_is_zero():
    inputs, result = _computed(total="0")
    assert "%" not in budget.render(inputs, result)


def test_render_without_a_cost_reports_revenue_and_no_margin():
    inputs, result = _computed(cost=None)
    text = budget.render(inputs, result)
    assert "20.000,00 TL" in text
    assert "Marj" not in text


def test_render_names_the_crop_when_one_was_selected():
    raw = _raw()
    raw["crop"] = "domates"
    inputs, errors = budget.validate(raw)
    assert errors == []
    assert "domates" in budget.render(inputs, budget.compute(inputs))


def test_framing_is_always_appended():
    """Appended by code so no model can drop it - the fertplan.FRAMING pattern."""
    inputs, result = _computed()
    assert budget.render(inputs, result).endswith(budget.FRAMING)
    inputs2, result2 = _computed(cost=None)
    assert budget.render(inputs2, result2).endswith(budget.FRAMING)


def test_framing_calls_the_figure_an_estimate_from_the_users_own_numbers():
    assert "tahmin" in budget.FRAMING.lower()


def test_the_ask_sentence_stands_on_its_own():
    """An already-deployed client cannot draw the form and shows only this
    sentence, so it has to be an honest answer rather than a widget caption."""
    assert len(budget.ASK_FOR_NUMBERS) > 40
    assert "form" not in budget.ASK_FOR_NUMBERS.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_budget.py -q
```

Expected: FAIL, `AttributeError: module 'src.budget' has no attribute 'render'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/budget.py`:

```python
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


def render(inputs: BudgetInputs, result: BudgetResult) -> str:
    """Code-written Turkish. Restates its inputs before stating its result."""
    crop = f" {inputs.crop} için" if inputs.crop else ""
    given = [
        f"**{format_tr(inputs.area_da.amount, 0)} dönüm**",
        f"toplam **{format_tr(inputs.yield_kg.amount, 0)} kg** "
        f"(dekara {format_tr(result.yield_kg_da, 0)} kg)",
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_budget.py -q
```

Expected: `45 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Render the budget result in Turkish with the estimate framing"
```

---

### Task 5: Short-circuit the budget route in `answer()`

**Files:**
- Modify: `src/engine.py:50-61` (`ChatResult`), `src/engine.py:846-891` (`answer`)
- Test: `tests/test_budget_route.py` (create)

**Interfaces:**
- Consumes: `budget.validate`, `budget.compute`, `budget.render`, `budget.form_spec`, `budget.ASK_FOR_NUMBERS`, `budget.COMPUTE_FAILED`
- Produces: `engine.answer(message, history=None, budget_payload=None) -> ChatResult` with `ChatResult.form: dict | None`; `engine._budget_result(payload: dict | None) -> ChatResult`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_budget_route.py`:

```python
"""The budget route inside the engine: it must compute, and it must not
retrieve, match products, or call the model."""

import pytest

from src import budget, engine


BUDGET_Q = "5 dönüm domates ektim, ne kadar kâr ederim?"


@pytest.fixture
def no_llm(monkeypatch):
    """Make every expensive path explode, so a test passes only if the route
    genuinely avoided it."""
    def boom(*args, **kwargs):
        raise AssertionError("the budget route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return monkeypatch


def _payload(cost="5000"):
    raw = {
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "2", "unit": "ton"},
        "price": {"value": "10", "unit": "tl_kg"},
    }
    if cost is not None:
        raw["cost"] = {"value": cost, "unit": "tl"}
    return raw


def test_a_budget_question_without_inputs_returns_the_form(no_llm):
    result = engine.answer(BUDGET_Q)
    assert result.route == "budget"
    assert result.answer == budget.ASK_FOR_NUMBERS
    assert result.form is not None
    assert [f["id"] for f in result.form["fields"]] == [f.id for f in budget.FIELDS]


def test_a_fresh_form_carries_no_errors(no_llm):
    """Nothing was submitted yet, so 'this field is required' would be scolding
    a user who has not been shown the field."""
    result = engine.answer(BUDGET_Q)
    assert all(f["error"] is None for f in result.form["fields"])


def test_a_budget_question_recommends_no_products(no_llm):
    assert engine.answer(BUDGET_Q).recommended_products == []


def test_a_complete_payload_is_computed(no_llm):
    result = engine.answer(BUDGET_Q, None, _payload())
    assert result.form is None
    assert "15.000,00 TL" in result.answer


def test_an_incomplete_payload_returns_the_form_with_field_errors(no_llm):
    bad = _payload()
    bad["price"] = {"value": "on lira", "unit": "tl_kg"}
    result = engine.answer(BUDGET_Q, None, bad)
    assert result.form is not None
    errors = {f["id"]: f["error"] for f in result.form["fields"]}
    assert errors["price"] is not None
    assert errors["area"] is None


def test_a_failing_computation_goes_silent_rather_than_guessing(no_llm, monkeypatch):
    """No fallback to the model path: an LLM answer about money is exactly what
    this route removes."""
    def boom(_inputs):
        raise ValueError("nope")

    monkeypatch.setattr(budget, "compute", boom)
    result = engine.answer(BUDGET_Q, None, _payload())
    assert result.answer == budget.COMPUTE_FAILED
    assert result.form is None


def test_a_submitted_payload_is_computed_even_if_the_router_disagrees(no_llm):
    """Turn 2 must not bet on the router a second time. If a complete payload
    arrives, it is computed whatever the route says."""
    result = engine.answer("Elma ağacı ne zaman budanır?", None, _payload())
    assert result.route == "budget"
    assert "15.000,00 TL" in result.answer


def test_a_non_budget_question_is_untouched(monkeypatch):
    """The corpus path must behave exactly as before for every other route."""
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda *a, **k: "Budama şöyle.")
    result = engine.answer("Elma ağacı ne zaman budanır?")
    assert result.route != "budget"
    assert result.form is None
    assert "Budama" in result.answer


def test_budget_still_takes_zero_false_entries_in_the_frozen_routing_set():
    """The whole design rests on no unrelated question reaching this route. If a
    future router rule breaks that, a budget form card appears under a question
    about leaf spot - so it fails here instead."""
    from src import router
    from evals.routing_set import CASES

    intruders = [c["query"] for c in CASES
                 if c["route"] != "budget"
                 and router.classify(c["query"], None)[0] == "budget"]
    assert intruders == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_budget_route.py -q
```

Expected: FAIL — `test_a_budget_question_without_inputs_returns_the_form` raises `AssertionError: the budget route must not reach this`, because `answer()` still calls `retrieve_context`.

- [ ] **Step 3: Write the minimal implementation**

In `src/engine.py`, add the `form` field to `ChatResult` (currently at lines 50-61):

```python
@dataclass
class ChatResult:
    answer: str
    recommended_products: list[RecommendedProduct]
    route: str = ""
    route_how: str = ""
    form: dict | None = None

    def as_api(self) -> dict:
        return {
            "answer": self.answer,
            "recommended_products": [p.as_api() for p in self.recommended_products],
            "form": self.form,
        }
```

Add `_budget_result` immediately above `def answer(` (line 846):

```python
def _budget_result(payload: dict | None) -> ChatResult:
    """The budget route: no retrieval, no product match, no model call.

    Every figure is computed in src/budget.py from values the user typed into
    labelled fields. When the payload is absent or incomplete we return the form
    instead of an answer; a payload that was never submitted gets a clean form
    rather than a list of "required" errors.
    """
    # Deferred like the router import below: keep engine's import graph flat.
    from src import budget

    submitted = bool(payload)
    inputs, errors = budget.validate(payload or {})
    if inputs is not None:
        try:
            result = budget.compute(inputs)
        except Exception:  # noqa: BLE001 - a broken sum must not become a guess
            return ChatResult(answer=budget.COMPUTE_FAILED,
                              recommended_products=[], route="budget")
        return ChatResult(answer=budget.render(inputs, result),
                          recommended_products=[], route="budget")

    return ChatResult(answer=budget.ASK_FOR_NUMBERS, recommended_products=[],
                      route="budget",
                      form=budget.form_spec(errors if submitted else []))
```

Change `answer`'s signature and insert the short-circuit directly after the routing block (after line 858, before `context = retrieve_context(...)`):

```python
def answer(message: str, history: list[dict] | None = None,
           budget_payload: dict | None = None) -> ChatResult:
    """Retrieve, match products, and produce a unified JSON-ready result."""
    try:
        from src import router
        route, route_how = router.classify(message, history)
    except Exception:  # noqa: BLE001 - routing must never break answering
        route, route_how = "", ""

    # The budget route short-circuits BEFORE retrieval: a money question was
    # paying for a corpus search that cannot hold its answer. Safe to diverge
    # because `budget` takes zero false entries in the frozen routing set.
    #
    # `or budget_payload`: turn 2 does not bet on the router a second time. A
    # submitted form is computed whatever the classifier says about the question
    # it was attached to.
    if route == "budget" or budget_payload:
        result = _budget_result(budget_payload)
        result.route_how = route_how
        return result

    context = retrieve_context(message, history=history)
```

The rest of `answer` is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_budget_route.py -q
python -m pytest -q
```

Expected: `9 passed` for the new file, and the full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/engine.py tests/test_budget_route.py
git commit -m "Answer a budget question from the form instead of the corpus"
```

---

### Task 6: The same short-circuit in `stream_answer()`

**This is the load-bearing task.** The project has already paid for this exact
mistake once: `stream_answer()` did not route while **both clients streamed**, so
the router ran on zero production traffic and the eval shield exercised
`answer()` — the path users never hit. `mobile-app/app/(tabs)/chat.tsx:138` calls
`sendChatMessageStream`, so streaming is the production path today.

**Files:**
- Modify: `src/engine.py:894-907` (`stream_answer`)
- Test: `tests/test_budget_route.py`

**Interfaces:**
- Consumes: `_budget_result` from Task 5
- Produces: `engine.stream_answer(message, history=None, budget_payload=None) -> Iterator[str]`, emitting `{"type": "form", "form": {...}}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_budget_route.py`:

```python
import json


def _events(chunks):
    """Parse the SSE lines the engine yields back into payload dicts."""
    out = []
    for chunk in chunks:
        for line in chunk.split("\n"):
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def test_the_stream_emits_the_sentence_the_form_and_done(no_llm):
    events = _events(engine.stream_answer(BUDGET_Q))
    assert [e["type"] for e in events] == ["token", "form", "done"]
    assert events[0]["content"] == budget.ASK_FOR_NUMBERS
    assert [f["id"] for f in events[1]["form"]["fields"]] == [
        f.id for f in budget.FIELDS]


def test_a_computed_answer_streams_without_a_form_event(no_llm):
    events = _events(engine.stream_answer(BUDGET_Q, None, _payload()))
    assert [e["type"] for e in events] == ["token", "done"]
    assert "15.000,00 TL" in events[0]["content"]


def test_the_stream_recommends_no_products(no_llm):
    events = _events(engine.stream_answer(BUDGET_Q))
    assert not any(e["type"] == "products" for e in events)


def test_streaming_and_non_streaming_agree_without_inputs(no_llm):
    """THE test. Wiring the form into answer() and forgetting stream_answer() is
    the defect this project already shipped once, in this exact place."""
    unified = engine.answer(BUDGET_Q)
    events = _events(engine.stream_answer(BUDGET_Q))
    streamed = "".join(e["content"] for e in events if e["type"] == "token")
    form = next(e["form"] for e in events if e["type"] == "form")
    assert streamed == unified.answer
    assert form == unified.form


def test_streaming_and_non_streaming_agree_on_a_computed_answer(no_llm):
    unified = engine.answer(BUDGET_Q, None, _payload())
    events = _events(engine.stream_answer(BUDGET_Q, None, _payload()))
    streamed = "".join(e["content"] for e in events if e["type"] == "token")
    assert streamed == unified.answer
    assert not any(e["type"] == "form" for e in events)


def test_an_old_client_that_skips_unknown_event_types_still_completes(no_llm):
    """mobile-app/src/api.ts only branches on 'products' and 'token'; an
    unknown type falls through. The deployed APK must still see its sentence
    and a clean end of stream."""
    events = _events(engine.stream_answer(BUDGET_Q))
    known = [e for e in events if e["type"] in ("token", "products", "done")]
    assert [e["type"] for e in known] == ["token", "done"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_budget_route.py -q
```

Expected: FAIL — the new tests raise `AssertionError: the budget route must not reach this`, because `stream_answer` still retrieves.

- [ ] **Step 3: Write the minimal implementation**

In `src/engine.py`, change `stream_answer`'s signature and insert the short-circuit right after its routing block (after line 907):

```python
def stream_answer(
    message: str, history: list[dict] | None = None,
    budget_payload: dict | None = None
) -> Iterator[str]:
    """Yield Server-Sent-Event lines. Answer text streams token-by-token first;
    once it's complete a single event carries the product recommendations, then
    a final 'done' event closes the stream."""
    try:
        from src import router
        route, route_how = router.classify(message, history)
    except Exception:  # noqa: BLE001 - routing must never break answering
        route, route_how = "", ""

    # Must mirror answer() exactly, including the `or budget_payload` clause.
    # Both clients stream, so a form wired only into answer() would reach no user
    # at all - and the tests would still pass.
    if route == "budget" or budget_payload:
        result = _budget_result(budget_payload)
        yield _sse({"type": "token", "content": result.answer})
        if result.form is not None:
            yield _sse({"type": "form", "form": result.form})
        yield _sse({"type": "done"})
        return
```

The rest of `stream_answer` is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_budget_route.py -q
python -m pytest -q
```

Expected: `15 passed` for the new file, and the full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/engine.py tests/test_budget_route.py
git commit -m "Serve the budget form on the streaming path clients actually use"
```

---

### Task 7: The API contract

**Files:**
- Modify: `src/main.py:40-56` (schemas), `src/main.py:147-161` (`chat`)
- Test: `tests/test_api_budget.py` (create)

**Interfaces:**
- Consumes: `engine.answer`, `engine.stream_answer` from Tasks 5-6
- Produces: `ChatRequest.budget: BudgetPayload | None`, `ChatResponse.form: dict | None`, and the `budget` payload forwarded to both engine entry points

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_budget.py`:

```python
"""The /api/chat contract for the budget route."""

import json

import pytest
from fastapi.testclient import TestClient

from src import engine, main


BUDGET_Q = "5 dönüm domates ektim, ne kadar kâr ederim?"


@pytest.fixture
def client(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the budget route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return TestClient(main.app)


PAYLOAD = {
    "area": {"value": "5", "unit": "donum"},
    "yield_total": {"value": "2", "unit": "ton"},
    "price": {"value": "10", "unit": "tl_kg"},
    "cost": {"value": "5000", "unit": "tl"},
}


def test_a_budget_question_returns_a_form(client):
    resp = client.post("/api/chat", json={"message": BUDGET_Q, "history": []})
    assert resp.status_code == 200
    body = resp.json()
    assert body["form"] is not None
    assert body["recommended_products"] == []
    assert body["answer"]


def test_a_submitted_payload_is_computed(client):
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "budget": PAYLOAD})
    body = resp.json()
    assert body["form"] is None
    assert "15.000,00 TL" in body["answer"]


def test_an_invalid_value_is_a_field_error_not_a_422(client):
    """A bad number is a user typo, not a client bug. It must come back on the
    field, inside a 200, rather than as a validation failure mid-conversation."""
    bad = dict(PAYLOAD, price={"value": "on lira", "unit": "tl_kg"})
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "budget": bad})
    assert resp.status_code == 200
    errors = {f["id"]: f["error"] for f in resp.json()["form"]["fields"]}
    assert errors["price"] is not None


def test_a_structurally_wrong_body_is_still_a_422(client):
    """A genuine client bug must stay loud."""
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "budget": "five donum"})
    assert resp.status_code == 422


def test_a_request_without_a_budget_field_still_works(client):
    """The deployed APK never sends one."""
    resp = client.post("/api/chat", json={"message": BUDGET_Q})
    assert resp.status_code == 200


def test_the_streaming_endpoint_carries_the_form_event(client):
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "stream": True})
    assert resp.status_code == 200
    types = [json.loads(line[6:])["type"]
             for line in resp.text.split("\n") if line.startswith("data: ")]
    assert types == ["token", "form", "done"]


def test_the_streaming_endpoint_forwards_a_submitted_payload(client):
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "stream": True, "budget": PAYLOAD})
    text = "".join(json.loads(line[6:]).get("content", "")
                   for line in resp.text.split("\n")
                   if line.startswith("data: "))
    assert "15.000,00 TL" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_api_budget.py -q
```

Expected: FAIL — `test_a_budget_question_returns_a_form` raises `KeyError: 'form'`, because `ChatResponse` has no such field.

- [ ] **Step 3: Write the minimal implementation**

In `src/main.py`, add the payload schemas above `ChatRequest` (line 40) and extend the two models:

```python
class BudgetField(BaseModel):
    # Deliberately loose: a text input produces strings, and src/budget.py does
    # the real checking. A bad value must come back as a field error inside a
    # 200, not as a 422 in the middle of a conversation.
    value: str | int | float = ""
    unit: str = ""


class BudgetPayload(BaseModel):
    area: BudgetField | None = None
    yield_total: BudgetField | None = None
    price: BudgetField | None = None
    cost: BudgetField | None = None
    crop: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user query.")
    history: list[ChatTurn] = Field(default_factory=list)
    stream: bool = Field(
        default=False, description="If true, respond with an SSE token stream."
    )
    budget: BudgetPayload | None = Field(
        default=None, description="Filled budget form, when the user submitted one."
    )


class ProductOut(BaseModel):
    title: str
    link: str


class ChatResponse(BaseModel):
    answer: str
    recommended_products: list[ProductOut]
    # Optional so an already-deployed client, which never reads it, is unaffected.
    form: dict | None = None
```

Replace the body of `chat` (lines 147-161):

```python
@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Primary endpoint. Returns unified JSON, or an SSE stream when
    ``stream=true``."""
    history = [t.model_dump() for t in req.history]
    budget_payload = req.budget.model_dump() if req.budget else None

    if req.stream:
        return StreamingResponse(
            engine.stream_answer(req.message, history, budget_payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result = engine.answer(req.message, history, budget_payload)
    return ChatResponse(**result.as_api())
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_api_budget.py -q
python -m pytest -q
```

Expected: `7 passed` for the new file, and the full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_api_budget.py
git commit -m "Carry the budget payload in and the form spec out of /api/chat"
```

---

### Task 8: Mobile API client

**Files:**
- Modify: `mobile-app/src/api.ts:50-101`

**Interfaces:**
- Consumes: the SSE `form` event from Task 6
- Produces: `FormSpec`, `FormField`, `BudgetPayload` types; `ChatStreamHandlers.onForm`; a fourth `budget` argument on `sendChatMessageStream`

- [ ] **Step 1: Add the types and the handler**

There is no JS test runner in this repo, so this task is verified by the type
checker and by Task 9's manual run. Keep the change mechanical.

In `mobile-app/src/api.ts`, add above `ChatStreamHandlers` (line 50):

```typescript
export interface BudgetFieldValue {
  value: string;
  unit: string;
}

export interface BudgetPayload {
  area?: BudgetFieldValue;
  yield_total?: BudgetFieldValue;
  price?: BudgetFieldValue;
  cost?: BudgetFieldValue;
  crop?: string | null;
}

export interface FormUnit {
  id: string;
  label: string;
}

export interface FormField {
  id: string;
  label: string;
  required: boolean;
  units: FormUnit[];
  // Empty in P1; P2 fills these from the norm layer without a wire change.
  value: string;
  source: "user" | "norm" | "empty";
  error: string | null;
}

export interface FormSpec {
  fields: FormField[];
}
```

Extend the handlers and the function signature:

```typescript
export interface ChatStreamHandlers {
  onToken: (content: string) => void;
  onProducts: (products: RecommendedProduct[]) => void;
  onForm?: (form: FormSpec) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}

export function sendChatMessageStream(
  message: string,
  history: ChatTurn[],
  handlers: ChatStreamHandlers,
  budget?: BudgetPayload
): void {
```

In `processUpTo`, add a branch beside the existing two:

```typescript
      if (evt.type === "products") {
        handlers.onProducts(evt.recommended_products);
      } else if (evt.type === "token") {
        handlers.onToken(evt.content);
      } else if (evt.type === "form") {
        handlers.onForm?.(evt.form);
      }
```

And send the payload (line 100):

```typescript
  xhr.send(JSON.stringify({ message, history, stream: true, budget }));
```

`budget` is `undefined` when not passed, and `JSON.stringify` omits undefined
keys, so an ordinary question sends exactly the body it sends today.

- [ ] **Step 2: Verify the types compile**

```bash
cd mobile-app && npx tsc --noEmit
```

Expected: no errors. If `npx` fails on the path spaces, use
`node node_modules/typescript/bin/tsc --noEmit`.

- [ ] **Step 3: Commit**

```bash
git add mobile-app/src/api.ts
git commit -m "Let the mobile client receive a form event and send a filled one"
```

---

### Task 9: The budget card in the chat

**Files:**
- Create: `mobile-app/src/BudgetCard.tsx`
- Modify: `mobile-app/app/(tabs)/chat.tsx:28-33` (`Message`), `:134-170` (send), `:212-226` (render)

**Interfaces:**
- Consumes: `FormSpec`, `BudgetPayload`, `sendChatMessageStream` from Task 8
- Produces: `<BudgetCard form={...} onSubmit={(payload: BudgetPayload) => void} />`

- [ ] **Step 1: Create the card**

Create `mobile-app/src/BudgetCard.tsx`:

```tsx
// The budget form, rendered inline in the chat. Every field carries a unit
// selector because the unit has to be a SELECTION: a farmer who harvested 2
// tons from 5 donum thinks "2 ton", and typing that into a per-dekar field
// would be five times too high and completely silent.
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { BudgetPayload, FormSpec } from "./api";
import { colors } from "./theme";

interface Props {
  form: FormSpec;
  // `summary` is what the chat shows as the user's bubble for this turn. The
  // request still carries the original question, but echoing it again would
  // read as the user asking twice.
  onSubmit: (payload: BudgetPayload, summary: string) => void;
}

export default function BudgetCard({ form, onSubmit }: Props) {
  // Seeded from the server's `value`, which is empty in P1 and prefilled by the
  // norm layer in P2 - so this card needs no change when that lands.
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(form.fields.map((f) => [f.id, f.value]))
  );
  const [units, setUnits] = useState<Record<string, string>>(() =>
    Object.fromEntries(form.fields.map((f) => [f.id, f.units[0].id]))
  );

  function submit() {
    const payload: Record<string, { value: string; unit: string }> = {};
    const parts: string[] = [];
    for (const f of form.fields) {
      const v = (values[f.id] ?? "").trim();
      if (!v) continue;
      payload[f.id] = { value: v, unit: units[f.id] };
      const unit = f.units.find((u) => u.id === units[f.id]);
      parts.push(`${f.label}: ${v} ${unit ? unit.label : ""}`.trim());
    }
    onSubmit(payload as BudgetPayload, parts.join(" · "));
  }

  return (
    <View style={styles.card}>
      {form.fields.map((f) => (
        <View key={f.id} style={styles.row}>
          <Text style={styles.label}>
            {f.label}
            {f.required ? "" : " (isteğe bağlı)"}
          </Text>
          <View style={styles.inputRow}>
            <TextInput
              style={styles.input}
              keyboardType="numeric"
              value={values[f.id] ?? ""}
              onChangeText={(t) => setValues((p) => ({ ...p, [f.id]: t }))}
              placeholder="0"
              placeholderTextColor="#9aa"
            />
            <View style={styles.units}>
              {f.units.map((u) => (
                <Pressable
                  key={u.id}
                  onPress={() => setUnits((p) => ({ ...p, [f.id]: u.id }))}
                  style={[
                    styles.unit,
                    units[f.id] === u.id && styles.unitActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.unitText,
                      units[f.id] === u.id && styles.unitTextActive,
                    ]}
                  >
                    {u.label}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
          {f.error ? <Text style={styles.error}>{f.error}</Text> : null}
        </View>
      ))}
      <Pressable style={styles.submit} onPress={submit}>
        <Text style={styles.submitText}>Hesapla</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e2e8e2",
    padding: 14,
    marginTop: 8,
    gap: 12,
  },
  row: { gap: 6 },
  label: { fontSize: 13, fontWeight: "600", color: colors.dark },
  inputRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: "#e2e8e2",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    color: colors.dark,
  },
  units: { flexDirection: "row", gap: 6 },
  unit: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e2e8e2",
  },
  unitActive: { backgroundColor: colors.green, borderColor: colors.green },
  unitText: { fontSize: 12, color: colors.dark },
  unitTextActive: { color: "#fff", fontWeight: "600" },
  error: { fontSize: 12, color: "#c0392b" },
  submit: {
    backgroundColor: colors.green,
    borderRadius: 8,
    paddingVertical: 11,
    alignItems: "center",
  },
  submitText: { color: "#fff", fontWeight: "700" },
});
```

- [ ] **Step 2: Split `handleSend` so a form can send a turn too**

`handleSend()` (line 107) takes no arguments: it reads `input`, clears it, and
appends the user's bubble itself. A form submission must do none of those three
things, so the network half is extracted and the two callers each do their own
bookkeeping.

In `mobile-app/app/(tabs)/chat.tsx`, extend `Message` (line 28):

```tsx
interface Message {
  id: string;
  role: "user" | "bot";
  text: string;
  products?: RecommendedProduct[];
  form?: FormSpec;
  // The question this form was a reply to. Turn 2 resends it so history stays
  // coherent and the router still classifies the turn the same way.
  question?: string;
}
```

Add `BudgetPayload` and `FormSpec` to the imports from `../../src/api`, and
`import BudgetCard from "../../src/BudgetCard";`.

Replace `handleSend`'s opening (lines 107-111) so it delegates:

```tsx
  function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { id: newId(), role: "user", text }]);
    sendTurn(text);
  }

  // The network half, shared by a typed message and a submitted budget form.
  // The caller owns the user bubble: a form turn shows the values entered, not
  // the question repeated.
  function sendTurn(text: string, budget?: BudgetPayload) {
```

Everything from the `requestHistory` comment block (line 112) to the end of the
old `handleSend` now lives in `sendTurn`. Pass `budget` through as the fourth
argument of the streaming call (line 138):

```tsx
    sendChatMessageStream(text, requestHistory, {
```

becomes

```tsx
    sendChatMessageStream(text, requestHistory, {
```
with the handlers object gaining `onForm` beside `onProducts` (line 155):

```tsx
      onForm: (form) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, form, question: text } : m))
        );
      },
```
and the call closing with the new argument:

```tsx
    }, budget);
```

`onForm` arrives after the first `onToken`, so the bot message already exists.

Render the card under its bot bubble, directly after the products block
(line 226):

```tsx
              {m.form && (
                <BudgetCard
                  form={m.form}
                  onSubmit={(payload, summary) => {
                    setMessages((prev) => [
                      // The card is consumed: replace it, so a stale form cannot
                      // be submitted twice.
                      ...prev.map((x) =>
                        x.id === m.id ? { ...x, form: undefined } : x
                      ),
                      { id: newId(), role: "user", text: summary },
                    ]);
                    // `question` is written in the same setState as `form`, so
                    // it is always there; `summary` is the fallback only because
                    // /api/chat requires a non-empty message. Either is safe -
                    // turn 2 no longer depends on how the message routes.
                    sendTurn(m.question ?? summary, payload);
                  }}
                />
              )}
```

- [ ] **Step 3: Do not persist an interactive card**

The chat is restored across restarts, and a live form attached to a stale turn
would be wrong. Strip `form` before saving: wherever `saveChat` is called with
the message list, pass `messages.map(({ form, ...rest }) => rest)` instead of
`messages`.

- [ ] **Step 4: Verify against the running stack**

```bash
python -m src.main
```

Then start the app (`cd mobile-app && node node_modules/expo/bin/cli start`),
ask *"5 dönüm domates ektim, ne kadar kâr ederim?"*, fill 5 dönüm / 2 ton /
10 TL/kg / 5000 TL, and confirm the reply states **Marj 15.000,00 TL**. Set
`EXPO_PUBLIC_API_BASE` in the SHELL if the device cannot reach the LAN IP —
never in `mobile-app/.env`, which is baked into the APK.

- [ ] **Step 5: Commit**

```bash
git add mobile-app/src/BudgetCard.tsx "mobile-app/app/(tabs)/chat.tsx"
git commit -m "Show the budget form as a card inside the chat"
```

---

## Finishing

- [ ] Run the whole suite from the repo root: `python -m pytest -q`. Expected: the pre-existing 489 plus 67 new tests — **556**, all green.
- [ ] Run the routing eval to confirm nothing moved: `python -m evals.run_routing`. Expected: unchanged at 37/42, and `budget` still listed under *sevke uygun rotalar*. The gate stays red for reasons that predate this work.
- [ ] **Do not run the 59-case eval.** This route makes no model call; a run would measure the corpus path, which this plan does not touch.
- [ ] Merge to `main` with `--no-ff`. **Do not touch `demo`** — it is Emirhan's deploy branch.
- [ ] Tell Emirhan a new APK is needed: the client sends a new request field and reads a new SSE event. An old APK keeps working, but it cannot draw the card.
