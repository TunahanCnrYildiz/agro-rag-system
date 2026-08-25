"""Unit tests for src/dose_answer.py (no network, no store, no model)."""

import json

import pytest

from src import dose_answer, doses


TABLE = {
    "meta": {"generated": "2026-08-25"},
    "products": {
        "HİGRO FUBBY": {"sebze": {"damlama": {"low": 250.0, "high": 250.0, "unit": "gr"}},
                        "meyve": {"damlama": {"low": 1.0, "high": 1.5, "unit": "litre"}}},
        "FLY AZOT": {"hepsi": {"yaprak": {"low": 200.0, "high": 250.0, "unit": "cc"}}},
    },
    "all_groups_scope": {"FLY AZOT": ["tarla", "sebze"]},
}


@pytest.fixture(autouse=True)
def table(tmp_path, monkeypatch):
    """Every test here runs against a fixture table, never the shipped file:
    a real product's figures changing must not turn these red."""
    path = tmp_path / "product_doses.json"
    path.write_text(json.dumps(TABLE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    yield
    doses._load.cache_clear()


def _raw(product="HİGRO FUBBY", group="sebze", value="5", unit="donum"):
    return {"product": product, "group": group,
            "area": {"value": value, "unit": unit}}


def test_a_complete_payload_validates():
    inputs, errors = dose_answer.validate(_raw())
    assert errors == []
    assert (inputs.product, inputs.group, inputs.area_da) == ("HİGRO FUBBY", "sebze", 5.0)


def test_hectares_become_dekars():
    inputs, _ = dose_answer.validate(_raw(value="2", unit="hektar"))
    assert inputs.area_da == 20.0


def test_every_error_is_reported_at_once():
    """A user fixing a form should not be walked through one round trip at a
    time - budget.validate's rule."""
    inputs, errors = dose_answer.validate({})
    assert inputs is None
    assert {e.field for e in errors} == {"product", "group", "area"}


def test_a_product_we_hold_no_dose_for_is_a_field_error():
    inputs, errors = dose_answer.validate(_raw(product="YOK BÖYLE BİR ÜRÜN"))
    assert inputs is None
    assert [e.field for e in errors] == ["product"]


def test_an_unknown_group_is_a_field_error():
    inputs, errors = dose_answer.validate(_raw(group="hububat"))
    assert inputs is None
    assert [e.field for e in errors] == ["group"]


def test_a_zero_area_is_refused():
    """Never multiplied out as 0 - that answers 'you need 0 litres' about a
    purchase."""
    inputs, errors = dose_answer.validate(_raw(value="0"))
    assert inputs is None and [e.field for e in errors] == ["area"]


def test_a_true_area_is_refused_not_read_as_one_donum():
    """bool is an int subclass in Python; the budget form paid for this once."""
    raw = _raw()
    raw["area"]["value"] = True
    inputs, errors = dose_answer.validate(raw)
    assert inputs is None and [e.field for e in errors] == ["area"]


def test_a_turkish_decimal_comma_is_read():
    inputs, _ = dose_answer.validate(_raw(value="2,5"))
    assert inputs.area_da == 2.5


def test_validate_never_raises_on_junk():
    for junk in (None, [], "5 dönüm", {"area": "5"}, {"product": 7, "group": None}):
        inputs, errors = dose_answer.validate(junk)
        assert inputs is None and errors


def test_a_fresh_form_lists_every_product_and_group():
    spec = dose_answer.form_spec([])
    assert spec["kind"] == "product_dose"
    assert spec["products"] == list(doses.available_products())
    assert [g["id"] for g in spec["groups"]] == ["sebze", "meyve", "tarla"]
    assert spec["area"]["value"] == ""
    assert all(v is None for v in spec["errors"].values())


def test_a_rejected_form_echoes_what_was_entered():
    """The card seeds its state from the spec, so without the echo one bad
    field wipes the product, the group and the area together."""
    raw = _raw(value="0")
    _, errors = dose_answer.validate(raw)
    spec = dose_answer.form_spec(errors, raw)
    assert spec["product"] == "HİGRO FUBBY"
    assert spec["group"] == "sebze"
    assert spec["area"]["value"] == "0"
    assert spec["errors"]["area"]


def test_an_unrecognised_unit_falls_back_to_the_first():
    """Otherwise the card renders with no chip selected and no way to tell why."""
    spec = dose_answer.form_spec([], _raw(unit="fersah"))
    assert spec["area"]["unit"] == "donum"


def test_dose_answer_does_not_import_the_engine():
    """A file in, values out. The engine imports this module, not the reverse -
    and a cycle here raises ImportError on every startup."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/dose_answer.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("engine" in name for name in imported), imported


def test_a_single_figure_times_an_area():
    inputs, _ = dose_answer.validate(_raw(group="meyve", value="5"))
    totals = dose_answer.compute(inputs)
    assert len(totals) == 1
    assert (totals[0].total_low, totals[0].total_high, totals[0].total_unit) == (
        5.0, 7.5, "litre")


def test_a_range_stays_a_range():
    """Never a midpoint: collapsing invents a precision the source does not
    have, and the single number reads more authoritative than the range."""
    inputs, _ = dose_answer.validate(_raw(product="FLY AZOT", group="tarla", value="2"))
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_high) == (400.0, 500.0)


def test_a_thousand_grams_is_promoted_to_kilos():
    """A farmer buying fertilizer thinks in kilos. This is a pure unit
    conversion and invents nothing."""
    inputs, _ = dose_answer.validate(_raw(value="5"))     # 250 gr/da x 5 da
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_unit) == (1.25, "kg")


def test_under_a_thousand_stays_in_the_published_unit():
    inputs, _ = dose_answer.validate(_raw(value="2"))     # 250 gr/da x 2 da
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_unit) == (500.0, "gr")


def test_a_range_is_promoted_as_one_unit():
    """Printing '1000 cc – 1,25 litre' would read as two different figures."""
    inputs, _ = dose_answer.validate(_raw(product="FLY AZOT", group="sebze", value="5"))
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_high, totals[0].total_unit) == (
        1.0, 1.25, "litre")


def test_the_published_dose_survives_the_promotion():
    """The answer quotes the maker's own per-dekar figure alongside the total,
    so it must stay in the unit the page used."""
    inputs, _ = dose_answer.validate(_raw(value="5"))
    totals = dose_answer.compute(inputs)
    assert (totals[0].dose_low, totals[0].dose_unit) == (250.0, "gr")


def test_a_group_the_product_does_not_publish_computes_nothing():
    """Never another group's figure, and never zero."""
    inputs, _ = dose_answer.validate(_raw(group="tarla"))
    assert dose_answer.compute(inputs) == ()
