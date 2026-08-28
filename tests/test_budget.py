"""Unit tests for src/budget.py (no store, no model, no network)."""

from src import budget
from src.norms import CropNorm, NormValue


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
    assert budget.format_qty(12.995052770448549) == "13"
    assert budget.format_qty(400.0000000001) == "400"
    assert budget.format_qty(2.5) == "2,5"
    assert budget.format_qty(10.05) == "10,05"


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


def _payload(**over):
    """A complete, valid field-crop submission. Overrides replace one entry."""
    base = {
        "area": {"value": "10", "unit": "donum", "source": "user"},
        "yield_total": {"value": "4000", "unit": "kg", "source": "user"},
        "price": {"value": "12,50", "unit": "tl_kg", "source": "user"},
    }
    base.update(over)
    return base


def test_a_per_tree_value_without_a_tree_count_is_refused():
    """The exact mirror of the per-area rule: refused, never multiplied by a
    guessed count and never zeroed."""
    inputs, errors = budget.validate(_payload(
        yield_total={"value": "31", "unit": "kg_agac", "source": "user"}))
    assert inputs is None
    assert [e.field for e in errors] == ["yield_total"]
    assert errors[0].message == (
        "Ürün miktarı için ağaç başına değer girdiniz; "
        "önce ağaç sayısını doldurun.")


def test_a_per_tree_value_is_multiplied_by_the_tree_count():
    inputs, errors = budget.validate(_payload(
        yield_total={"value": "31", "unit": "kg_agac", "source": "user"},
        tree_count={"value": "120", "unit": "adet", "source": "user"}))
    assert errors == []
    assert inputs.yield_kg.amount == 3720.0


def test_a_tree_count_is_optional_for_a_field_crop():
    """A wheat budget must not be made to name a number of trees."""
    inputs, errors = budget.validate(_payload())
    assert errors == []
    assert inputs.yield_kg.amount == 4000.0


def test_a_tree_count_of_zero_is_refused():
    """Both errors, exactly as a zero AREA reports both its own and the
    per-area unit's. validate() reports ALL errors rather than the first, and
    the two out-of-order reads are mirrors of each other - a reader who
    understands one must not be surprised by the other."""
    inputs, errors = budget.validate(_payload(
        yield_total={"value": "31", "unit": "kg_agac", "source": "user"},
        tree_count={"value": "0", "unit": "adet", "source": "user"}))
    assert inputs is None
    assert [e.field for e in errors] == ["tree_count", "yield_total"]
    assert errors[0].message == "Ağaç sayısı sıfırdan büyük olmalı."
    assert errors[1].message == (
        "Ürün miktarı için ağaç başına değer girdiniz; "
        "önce ağaç sayısını doldurun.")


def test_a_zero_area_and_a_zero_tree_count_report_the_same_shape():
    """The two out-of-order reads in validate() are mirrors. This pins that:
    a divergence here was introduced once already, to satisfy a test that was
    itself wrong."""
    area = budget.validate(_payload(
        area={"value": "0", "unit": "donum", "source": "user"},
        yield_total={"value": "400", "unit": "kg_da", "source": "user"}))[1]
    trees = budget.validate(_payload(
        yield_total={"value": "31", "unit": "kg_agac", "source": "user"},
        tree_count={"value": "0", "unit": "adet", "source": "user"}))[1]
    assert [e.field for e in area] == ["area", "yield_total"]
    assert [e.field for e in trees] == ["tree_count", "yield_total"]


def test_the_tree_count_is_read_before_the_field_loop():
    """FIELDS order is a layout decision, not a contract - the same reason
    `area` is read out of order. Moving tree_count to the end of FIELDS must
    not break a per-tree conversion."""
    order = [f.id for f in budget.FIELDS]
    assert "tree_count" in order
    inputs, errors = budget.validate({
        "area": {"value": "10", "unit": "donum", "source": "user"},
        "tree_count": {"value": "120", "unit": "adet", "source": "user"},
        "yield_total": {"value": "31", "unit": "kg_agac", "source": "user"},
        "price": {"value": "12,50", "unit": "tl_kg", "source": "user"},
    })
    assert errors == [] and inputs.yield_kg.amount == 3720.0


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


def test_render_restates_a_non_default_unit_selection_in_canonical_units():
    """A hektar area and a ton total must read back converted to the canonical
    dönüm/kg units, not echoed in the unit the user picked - the restated line
    is what proves the selection was honoured rather than guessed."""
    inputs, result = _computed(area="2", area_unit="hektar",
                               total="10", total_unit="ton")
    text = budget.render(inputs, result)
    assert "**20 dönüm**" in text
    assert "toplam **10.000 kg**" in text
    assert "dekara 500 kg" in text
    assert "hektar" not in text
    assert "ton" not in text


def test_render_names_the_crop_when_one_was_selected():
    raw = _raw()
    raw["crop"] = "domates"
    inputs, errors = budget.validate(raw)
    assert errors == []
    assert "domates" in budget.render(inputs, budget.compute(inputs))


def test_render_prefers_the_crop_label_over_its_id():
    """The id ('findik') is a lookup key, not a word - a farmer reads the label
    ('Fındık'), and printing the id raw is what this test guards against."""
    raw = _raw()
    raw["crop"] = "findik"
    table = (CropNorm("findik", "Fındık", None, None),)
    inputs, errors = budget.validate(raw, table)
    assert errors == []
    text = budget.render(inputs, budget.compute(inputs))
    assert "Fındık için" in text
    assert "findik için" not in text


def test_render_falls_back_to_the_crop_id_when_no_table_resolves_it():
    """No table, or a crop the table does not carry: still name something
    rather than printing nothing, using the id as it always did in P1."""
    raw = _raw()
    raw["crop"] = "domates"
    inputs, errors = budget.validate(raw)
    assert errors == []
    assert "domates için" in budget.render(inputs, budget.compute(inputs))


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


def test_a_per_dekar_yield_equals_the_same_total_entered_directly():
    per_area = {
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "100", "unit": "kg_da"},
        "price": {"value": "10", "unit": "tl_kg"},
    }
    total = {
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "500", "unit": "kg"},
        "price": {"value": "10", "unit": "tl_kg"},
    }
    a, errs_a = budget.validate(per_area)
    b, errs_b = budget.validate(total)
    assert errs_a == [] and errs_b == []
    assert a.yield_kg.amount == b.yield_kg.amount == 500.0
    assert budget.compute(a).revenue_tl == budget.compute(b).revenue_tl


def test_a_per_dekar_yield_without_an_area_is_a_field_error_not_a_zero():
    """The binding rule: a value we cannot convert is refused, never quietly
    turned into 0 - a zero flows into the arithmetic and comes out confident."""
    inputs, errors = budget.validate({
        "yield_total": {"value": "100", "unit": "kg_da"},
        "price": {"value": "10", "unit": "tl_kg"},
    })
    assert inputs is None
    assert "yield_total" in {e.field for e in errors}


def test_a_per_dekar_yield_with_an_unparseable_area_is_also_refused():
    inputs, errors = budget.validate({
        "area": {"value": "beş", "unit": "donum"},
        "yield_total": {"value": "100", "unit": "kg_da"},
        "price": {"value": "10", "unit": "tl_kg"},
    })
    assert inputs is None
    assert {"area", "yield_total"} <= {e.field for e in errors}


def test_the_yield_label_reads_correctly_under_every_unit_it_offers():
    """'Toplam' is wrong for kg/dekar, and a label that contradicts the selected
    unit is the mismatch the selector exists to prevent."""
    spec = next(f for f in budget.FIELDS if f.id == "yield_total")
    assert "toplam" not in spec.label.lower()
    assert [u.id for u in spec.units] == ["kg", "ton", "kg_da", "kg_agac"]
    assert [u.per_area for u in spec.units] == [False, False, True, False]
    assert [u.per_tree for u in spec.units] == [False, False, False, True]


def test_the_original_units_are_untouched():
    """P1 regression: 2 ton off 5 donum is still 2000 kg."""
    inputs, errors = budget.validate({
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "2", "unit": "ton"},
        "price": {"value": "10", "unit": "tl_kg"},
        "cost": {"value": "5000", "unit": "tl"},
    })
    assert errors == []
    assert inputs.yield_kg.amount == 2000.0
    assert budget.compute(inputs).margin_tl == 15000.0


def _table():
    return (
        CropNorm("findik", "Fındık",
                 NormValue(28.4, 2025, "il", "Ordu", 73.7, 105.6),
                 NormValue(202.26, 2025, "il", "Ordu", None, None)),
        CropNorm("misir", "Mısır",
                 NormValue(1100.0, 2024, "tr", "Türkiye", 900.0, 1200.0),
                 None),
    )


def test_the_form_with_no_table_is_pinned_as_a_literal():
    """An old deployed client reads this dict, so it is pinned as a LITERAL.

    Rebuilding the expected value from budget.FIELDS with the same comprehension
    form_spec uses would assert only that the function is itself - it would
    follow any change to a label, a unit id or the key set rather than catch it.
    A wire contract is pinned by writing it out.

    Changed 2026-08-28: `tree_count` and the `kg/ağaç` unit were added. The
    client renders `form.fields` and each field's `units` generically, so both
    appear on an already-deployed build without a release."""
    assert budget.form_spec([]) == {
        "fields": [
            {"id": "area", "label": "Alan", "required": True,
             "units": [{"id": "donum", "label": "dönüm"},
                       {"id": "hektar", "label": "hektar"}],
             "value": "", "source": "empty", "error": None},
            {"id": "tree_count", "label": "Ağaç sayısı", "required": False,
             "units": [{"id": "adet", "label": "adet"}],
             "value": "", "source": "empty", "error": None},
            {"id": "yield_total", "label": "Ürün miktarı", "required": True,
             "units": [{"id": "kg", "label": "kg"},
                       {"id": "ton", "label": "ton"},
                       {"id": "kg_da", "label": "kg/dekar"},
                       {"id": "kg_agac", "label": "kg/ağaç"}],
             "value": "", "source": "empty", "error": None},
            {"id": "price", "label": "Fiyat", "required": True,
             "units": [{"id": "tl_kg", "label": "TL/kg"},
                       {"id": "tl_ton", "label": "TL/ton"}],
             "value": "", "source": "empty", "error": None},
            {"id": "cost", "label": "Masraf", "required": False,
             "units": [{"id": "tl", "label": "TL"}],
             "value": "", "source": "empty", "error": None},
        ]
    }


def test_a_table_ships_every_crop_with_its_figures():
    spec = budget.form_spec([], _table())
    assert [c["id"] for c in spec["crops"]] == ["findik", "misir"]
    cell = spec["crops"][0]["yield"]
    assert cell["value"] == "28,4"
    assert cell["unit"] == "kg_da"
    assert cell["note"] == "TÜİK 2025, Ordu"
    assert cell["recent"] == "önceki 5 yıl: 73,7–105,6 kg/da"


def _tree_table():
    """Ayva carries a per-tree figure; Mısır does not."""
    return (
        CropNorm("ayva", "Ayva",
                 NormValue(13419.4, 2025, "il", "Karabük", None, None),
                 NormValue(19.0, 2025, "il", "Karabük", None, None),
                 NormValue(31.0, 2025, "il", "Karabük", 27.0, 28.0)),
        CropNorm("misir", "Mısır",
                 NormValue(1100.0, 2024, "tr", "Türkiye", 900.0, 1200.0),
                 NormValue(8.0, 2025, "tr", "Türkiye", None, None)),
    )


def test_a_row_with_a_per_tree_figure_prefills_it_instead_of_the_derived_one():
    """THE POINT OF THE CHANGE. Karabük's derived kg/da is 13.419 - a quince
    yield roughly four times any real one, because the numerator counts every
    tree in the province and the denominator counts 31 dekars of compact
    orchard. The published 31 kg/agac needs no denominator at all."""
    spec = budget.form_spec([], _tree_table())
    cell = spec["crops"][0]["yield"]
    assert cell["value"] == "31"
    assert cell["unit"] == "kg_agac"
    assert cell["note"] == "TÜİK 2025, Karabük"


def test_the_per_tree_cell_shows_its_own_five_year_range():
    spec = budget.form_spec([], _tree_table())
    assert spec["crops"][0]["yield"]["recent"] == "önceki 5 yıl: 27–28 kg/ağaç"


def test_a_row_without_a_per_tree_figure_still_prefills_kg_da():
    spec = budget.form_spec([], _tree_table())
    cell = spec["crops"][1]["yield"]
    assert cell["value"] == "1.100"
    assert cell["unit"] == "kg_da"


def test_a_per_tree_norm_claim_is_confirmed_against_the_per_tree_cell():
    """_verify compares the served TEXT and unit. A claim must be checked
    against the very cell that was sent, or a per-tree submission would be
    compared to a kg/da cell, never match, and silently downgrade to "user" -
    the answer would then drop TUIK's name from a figure that is TUIK's."""
    inputs, errors = budget.validate({
        "area": {"value": "10", "unit": "donum", "source": "user"},
        "tree_count": {"value": "120", "unit": "adet", "source": "user"},
        "yield_total": {"value": "31", "unit": "kg_agac", "source": "norm"},
        "price": {"value": "19,00", "unit": "tl_kg", "source": "user"},
        "crop": "ayva",
    }, _tree_table())
    assert errors == []
    assert inputs.yield_kg.source == "norm"
    assert inputs.yield_kg.note == "TÜİK 2025, Karabük"
    assert inputs.yield_kg.amount == 3720.0


def test_a_per_tree_claim_that_does_not_match_what_we_served_downgrades():
    """The farmer's own figure wearing TUIK's name is the thing this guard
    exists to stop."""
    inputs, errors = budget.validate({
        "area": {"value": "10", "unit": "donum", "source": "user"},
        "tree_count": {"value": "120", "unit": "adet", "source": "user"},
        "yield_total": {"value": "45", "unit": "kg_agac", "source": "norm"},
        "price": {"value": "19,00", "unit": "tl_kg", "source": "user"},
        "crop": "ayva",
    }, _tree_table())
    assert errors == []
    assert inputs.yield_kg.source == "user"
    assert inputs.yield_kg.note is None


def test_a_price_cell_carries_two_decimals_and_its_own_unit():
    spec = budget.form_spec([], _table(), latest_year=2025)
    cell = spec["crops"][0]["price"]
    assert cell["value"] == "202,26"
    assert cell["unit"] == "tl_kg"
    assert cell["recent"] is None


def test_a_measure_with_no_norm_is_none_not_zero():
    """The binding rule, on the wire this time: absence is absence."""
    spec = budget.form_spec([], _table())
    assert spec["crops"][1]["price"] is None


def test_a_national_figure_names_turkiye_rather_than_looking_provincial():
    spec = budget.form_spec([], _table())
    assert spec["crops"][1]["yield"]["note"] == "TÜİK 2024, Türkiye"


def test_a_price_from_the_latest_year_is_served():
    """The dataset's cutoff year is 2025 here, and findik's price is from 2025
    - it must prefill."""
    spec = budget.form_spec([], _table(), latest_year=2025)
    assert spec["crops"][0]["price"] is not None
    assert spec["crops"][0]["price"]["value"] == "202,26"


def test_a_price_older_than_the_latest_year_is_absent_not_zero():
    """Measured on Ordu: Arpa (Diğer) prefills 1,10 TL/kg from 2018 - nine
    times too low once rendered as revenue. Lira is nominal, so an old price
    is not a meaningful quantity the way an old yield still is; it is dropped
    entirely rather than shown stale."""
    table = (CropNorm("arpa", "Arpa (Diğer)",
                       NormValue(1500.0, 2025, "il", "Ordu", 1400.0, 1600.0),
                       NormValue(1.10, 2018, "il", "Ordu", None, None)),)
    spec = budget.form_spec([], table, latest_year=2025)
    assert spec["crops"][0]["price"] is None
    assert spec["crops"][0]["yield"] is not None


def test_no_latest_year_serves_no_price_cell_at_all():
    """Not knowing the dataset's cutoff is not a reason to guess a price is
    fresh - absence beats risking a stale figure. Yield is untouched."""
    spec = budget.form_spec([], _table(), latest_year=None)
    assert all(c["price"] is None for c in spec["crops"])
    assert spec["crops"][0]["yield"] is not None


def test_a_price_range_is_never_shown_even_when_the_norm_carries_one():
    """Currency is nominal: a fresh price sits ABOVE its own five-year window
    for nearly every real crop (inflation, not an anomaly - measured 95 of 103
    Manisa price cells, 45 of 48 in Ordu), so showing the range there would
    read as a false outlier warning. Yield keeps its range, where a stale
    figure really can be an outlier."""
    table = (CropNorm("x", "X",
                       NormValue(100.0, 2025, "tr", "Türkiye", 60.0, 90.0),
                       NormValue(50.0, 2025, "tr", "Türkiye", 20.0, 40.0)),)
    spec = budget.form_spec([], table, latest_year=2025)
    assert spec["crops"][0]["yield"]["recent"] is not None
    assert spec["crops"][0]["price"]["recent"] is None


def test_no_raw_float_reaches_the_wire():
    """Every figure is Turkish-formatted text. A float would arrive with a DOT
    decimal and parse_tr_number refuses those, so 28.4 would come back as a
    field error - or worse, as 284."""
    spec = budget.form_spec([], _table())
    for crop in spec["crops"]:
        for key in ("yield", "price"):
            if crop[key] is not None:
                assert isinstance(crop[key]["value"], str)


def test_a_rejected_form_carries_back_what_was_typed():
    """Without this, the error Task 3 introduces - a per-dekar yield with no
    area - throws away the crop and every other field the user filled."""
    submitted = {
        "crop": "findik",
        "area": {"value": "", "unit": "donum"},
        "yield_total": {"value": "100", "unit": "kg_da"},
        "price": {"value": "202,26", "unit": "tl_kg"},
    }
    _, errors = budget.validate(submitted)
    spec = budget.form_spec(errors, _table(), submitted)
    fields = {f["id"]: f for f in spec["fields"]}
    assert fields["yield_total"]["value"] == "100"
    assert fields["yield_total"]["unit"] == "kg_da"
    assert fields["price"]["value"] == "202,26"
    assert spec["crop"] == "findik"
    assert fields["area"]["error"]


def test_a_rejected_form_echoes_the_raw_source_claim():
    """The claim being echoed back, not a re-derived verdict - see the next
    test for why re-deriving it from value/unit was the bug."""
    submitted = {
        "crop": "findik",
        "yield_total": {"value": "28,4", "unit": "kg_da", "source": "norm"},
        "price": {"value": "202,26", "unit": "tl_kg", "source": "user"},
    }
    spec = budget.form_spec([], _table(), submitted)
    fields = {f["id"]: f for f in spec["fields"]}
    assert fields["yield_total"]["source"] == "norm"
    assert fields["price"]["source"] == "user"


def test_a_users_own_value_equal_to_the_norm_still_echoes_as_user():
    """The bug this fixes: re-deriving source by comparing the echoed value
    and unit to the crop's cell would mark this "norm" because the numbers
    happen to match, attributing a figure the farmer typed to TUIK."""
    submitted = {
        "crop": "findik",
        "yield_total": {"value": "28,4", "unit": "kg_da", "source": "user"},
    }
    spec = budget.form_spec([], _table(), submitted)
    fields = {f["id"]: f for f in spec["fields"]}
    assert fields["yield_total"]["source"] == "user"


def test_an_unsubmitted_form_still_has_empty_source_on_every_field():
    """No submitted payload at all - the redisplay path never runs, so every
    field keeps the "empty" default."""
    spec = budget.form_spec([], _table())
    assert all(f["source"] == "empty" for f in spec["fields"])


def test_the_framing_joins_two_different_notes_with_a_middle_dot():
    """Reachable on real data: Arpa (Diğer) in Ordu renders '(TÜİK 2025, Ordu ·
    TÜİK 2018, Ordu)' when the yield and price norms come from different
    years. Fix 1 changes which cases can still reach this (a stale price is
    never offered as a norm cell), but a fresh yield and a fresh price from
    different provinces or years still can, so the join stays reachable."""
    table = (CropNorm("findik", "Fındık",
                       NormValue(28.4, 2025, "il", "Ordu", 73.7, 105.6),
                       NormValue(202.26, 2024, "il", "Ordu", None, None)),)
    inputs, errors = budget.validate({
        "crop": "findik",
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "28,4", "unit": "kg_da", "source": "norm"},
        "price": {"value": "202,26", "unit": "tl_kg", "source": "norm"},
    }, table)
    assert errors == []
    text = budget.framing(inputs)
    assert "TÜİK 2025, Ordu · TÜİK 2024, Ordu" in text


def test_an_unsubmitted_form_carries_no_values_and_no_unit_key():
    """Nothing was submitted, so there is nothing to echo and P1's shape holds."""
    spec = budget.form_spec([], _table())
    for field in spec["fields"]:
        assert field["value"] == ""
        assert "unit" not in field
    assert "crop" not in spec


def test_an_unknown_unit_is_not_echoed_back():
    """A unit the field does not offer would render as no chip selected at all."""
    submitted = {"yield_total": {"value": "100", "unit": "furlong"}}
    spec = budget.form_spec([], _table(), submitted)
    fields = {f["id"]: f for f in spec["fields"]}
    assert fields["yield_total"]["unit"] == "kg"


def test_a_non_string_submitted_value_is_echoed_as_text():
    """A JSON number is a legal submission; echoing it as a float would put a
    dot decimal into a field parse_tr_number refuses."""
    spec = budget.form_spec([], None, {"area": {"value": 5, "unit": "donum"}})
    fields = {f["id"]: f for f in spec["fields"]}
    assert fields["area"]["value"] == "5"


def _submitted(value="28,4", unit="kg_da", source="norm"):
    return {
        "crop": "findik",
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": value, "unit": unit, "source": source},
        "price": {"value": "202,26", "unit": "tl_kg", "source": "norm"},
    }


def _all_typed():
    """Every figure the user's own. Note that overriding the YIELD alone is not
    enough - _submitted() claims the price is a norm too, and the price claim
    would still be confirmed."""
    raw = _submitted(value="90")
    raw["price"] = {"value": "15", "unit": "tl_kg", "source": "user"}
    return raw


def test_a_form_of_the_users_own_figures_keeps_p1s_sentence_exactly():
    inputs, _ = budget.validate(_all_typed(), _table())
    text = budget.render(inputs, budget.compute(inputs))
    assert text.rstrip().endswith(budget.FRAMING)


def test_a_norm_figure_replaces_that_sentence():
    """Leaving it would state that the calculation rests entirely on the user's
    own numbers while one of them came from TUIK."""
    inputs, _ = budget.validate(_submitted(), _table())
    text = budget.render(inputs, budget.compute(inputs))
    assert budget.FRAMING not in text
    assert "verim ve fiyat" in text
    assert "TÜİK 2025, Ordu" in text
    assert "öngörü değildir" in text


def test_the_lead_in_is_unchanged_when_every_figure_is_the_users_own():
    """P1's exact lead-in, byte for byte - an already-pinned test elsewhere
    depends on this string too, but the wording itself is the thing at risk
    here."""
    inputs, _ = budget.validate(_all_typed(), _table())
    text = budget.render(inputs, budget.compute(inputs))
    assert text.startswith("Girdiğiniz değerlere göre")


def test_the_lead_in_changes_when_a_norm_figure_is_standing_in():
    """'Girdiğiniz değerlere göre' (according to what you entered) is false
    once a TUIK figure - not the farmer's own - fed the calculation."""
    inputs, _ = budget.validate(_submitted(), _table())
    text = budget.render(inputs, budget.compute(inputs))
    assert text.startswith("Şu değerlere göre")
    assert not text.startswith("Girdiğiniz değerlere göre")


def test_the_framing_names_only_the_figures_that_are_not_the_users():
    """A sentence that says 'verim ve fiyat' while the farmer typed the price
    tells them their own number came from TUIK."""
    raw = _submitted()
    raw["price"] = {"value": "15", "unit": "tl_kg", "source": "user"}
    inputs, _ = budget.validate(raw, _table())
    text = budget.framing(inputs)
    assert text.startswith("Bu hesaptaki verim rakamı")
    assert "verim ve fiyat" not in text


def test_the_framing_uses_the_singular_for_one_norm_measure():
    """'rakamı ... ortalamasıdır' agrees in number with a single figure; the
    plural form here would read as a grammar error a farmer notices."""
    raw = _submitted()
    raw["price"] = {"value": "15", "unit": "tl_kg", "source": "user"}
    inputs, _ = budget.validate(raw, _table())
    text = budget.framing(inputs)
    assert "rakamı sizin değil" in text
    assert "ortalamasıdır" in text
    assert "rakamları" not in text
    assert "ortalamalarıdır" not in text


def test_the_framing_uses_the_plural_for_two_norm_measures():
    """With both verim and fiyat from the norm, the noun and the verb both
    have to take the plural - 'rakamı ... ortalamasıdır' would be wrong here."""
    inputs, _ = budget.validate(_submitted(), _table())
    text = budget.framing(inputs)
    assert "rakamları sizin değil" in text
    assert "ortalamalarıdır" in text


def test_the_framing_names_tuik_only_in_the_parenthetical():
    """The sentence body used to say 'TÜİK'in yayımladığı' and then repeat
    TÜİK again in the parenthetical citation - the same agency named twice in
    one sentence. It belongs in the citation only."""
    inputs, _ = budget.validate(_submitted(), _table())
    text = budget.framing(inputs)
    assert text.count("TÜİK") == 1


def test_the_framing_is_always_the_last_line():
    """It is appended by code and never asked of a model; a figure after it
    would read as a correction to it."""
    inputs, _ = budget.validate(_submitted(), _table())
    lines = [l for l in budget.render(inputs, budget.compute(inputs)).split("\n") if l]
    assert lines[-1] == budget.framing(inputs)


def test_the_p1_constant_is_untouched():
    assert budget.FRAMING == (
        "Bu hesap bir tahmindir ve tamamen sizin girdiğiniz rakamlara dayanır; "
        "fiyat veya verim öngörüsü değildir."
    )


def test_a_confirmed_claim_is_marked_as_a_norm():
    inputs, errors = budget.validate(_submitted(), _table())
    assert errors == []
    assert inputs.yield_kg.source == "norm"
    assert inputs.yield_kg.note == "TÜİK 2025, Ordu"


def test_an_edited_value_claiming_to_be_a_norm_is_downgraded():
    """The farmer's own figure must never be attributed to TUIK."""
    inputs, _ = budget.validate(_submitted(value="90"), _table())
    assert inputs.yield_kg.source == "user"
    assert inputs.yield_kg.note is None


def test_a_claim_under_a_different_unit_is_downgraded():
    """28,4 kg is not 28,4 kg/dekar, and only one of them is what we served."""
    inputs, _ = budget.validate(_submitted(unit="kg"), _table())
    assert inputs.yield_kg.source == "user"


def test_a_claim_with_no_table_is_downgraded():
    """Nothing to check it against is not the same as checking and agreeing."""
    inputs, _ = budget.validate(_submitted())
    assert inputs.yield_kg.source == "user"


def test_a_claim_for_a_crop_the_table_does_not_carry_is_downgraded():
    raw = _submitted()
    raw["crop"] = "yokolan"
    inputs, _ = budget.validate(raw, _table())
    assert inputs.yield_kg.source == "user"


def test_an_old_client_sending_no_source_gets_user():
    """Defaulting to 'user' keeps a deployed build on P1's exact framing rather
    than claiming a provenance it never asserted."""
    raw = _submitted()
    del raw["yield_total"]["source"]
    inputs, _ = budget.validate(raw, _table())
    assert inputs.yield_kg.source == "user"


def test_a_user_claim_is_never_upgraded():
    """Even when the number happens to equal the norm: the user typed it."""
    inputs, _ = budget.validate(_submitted(source="user"), _table())
    assert inputs.yield_kg.source == "user"


def test_the_arithmetic_always_uses_the_submitted_value():
    """Precedence is unchanged by any of this. A prefill is a default, never a
    lock, and a downgrade changes only the label."""
    inputs, _ = budget.validate(_submitted(value="90", unit="kg_da"), _table())
    assert inputs.yield_kg.amount == 450.0    # 90 kg/da over 5 donum


def test_a_non_dict_submitted_coerces_to_empty_rather_than_raising():
    """Untrusted payloads that fail validation must not crash form_spec; they
    degrade to an unsubmitted-shaped form instead."""
    # A bare string should not raise AttributeError
    spec = budget.form_spec([], None, "not-a-dict")
    assert "fields" in spec
    assert "crop" not in spec
    assert all(f["value"] == "" for f in spec["fields"])

    # A list should not raise AttributeError
    spec = budget.form_spec([], None, ["item"])
    assert "fields" in spec
    assert "crop" not in spec

    # An int should not raise AttributeError
    spec = budget.form_spec([], None, 42)
    assert "fields" in spec
    assert "crop" not in spec
