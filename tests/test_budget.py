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


def test_format_qty_does_not_leave_a_half_formatted_decimal():
    """A value that rounds to a whole number at two decimals must not keep
    a bare trailing zero, e.g. "13,0" - it should drop the comma entirely."""
    assert budget._format_qty(12.995052770448549) == "13"
    assert budget._format_qty(400.0000000001) == "400"
    assert budget._format_qty(2.5) == "2,5"
    assert budget._format_qty(10.05) == "10,05"


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


def test_render_restates_what_it_computed_from():
    """This is what replaces an upper bound on the inputs. A user who meant 5
    and typed 5000 reads '5.000 donum' in the first line, and a wrong unit
    selection shows up in the derived per-dekar figure."""
    inputs, result = _computed()
    text = budget.render(inputs, result)
    assert "5 dönüm" in text
    assert "dekara 400 kg" in text


def test_render_echoes_a_fractional_input_faithfully():
    """2,5 donum must read back as 2,5, not round to 2 - the restated line is
    what stands in for an upper bound on inputs, and the arithmetic below it
    already uses the true 2,5."""
    inputs, result = _computed(area="2,5")
    text = budget.render(inputs, result)
    assert "2,5 dönüm" in text
    assert "2 dönüm" not in text


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
    """The invitation sentence legitimately contains the word "marj" (lowercase,
    inflected: "marjınızı") - that word is fine. What must be absent is the
    margin FIGURE: the result line's "Marj " marker and any percentage."""
    inputs, result = _computed(cost=None)
    text = budget.render(inputs, result)
    assert "20.000,00 TL" in text
    assert "Marj " not in text
    assert "%" not in text
    assert "kâr marjınızı da hesaplayabilirim" in text


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
