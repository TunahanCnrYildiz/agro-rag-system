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


def test_format_does_not_print_a_negative_zero():
    """A value that rounds away to zero should format as zero, not -0."""
    assert budget.format_tr(-0.001, 2) == "0,00"
    assert budget.format_tr(-0.001, 0) == "0"


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
