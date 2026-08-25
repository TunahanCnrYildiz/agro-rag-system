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
    a real product's figures changing must not turn these red.

    src.router._product_pattern() is an lru_cache built from
    doses.available_products(), so it must be cleared alongside doses._load -
    otherwise a test that runs after this fixture and touches the router
    keeps seeing whichever table was loaded first. Imported lazily to avoid a
    load-time import cycle (src/dose_answer.py deliberately does not import
    the router - see test_dose_answer_does_not_import_the_engine)."""
    from src import router

    path = tmp_path / "product_doses.json"
    path.write_text(json.dumps(TABLE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    router._product_pattern.cache_clear()
    yield
    doses._load.cache_clear()
    router._product_pattern.cache_clear()


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

    # Resolved from this test file's own location, not the cwd: a cwd-relative
    # path dies with FileNotFoundError instead of asserting anything the
    # moment the suite runs from somewhere other than the repo root.
    src_path = Path(__file__).resolve().parent.parent / "src" / "dose_answer.py"
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
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


def test_a_straddling_range_is_still_promoted_as_one_unit():
    """200-250 cc/da over 4,5 dönüm is 900-1125 cc: the LOW end alone stays
    under 1000 and would not promote on its own. _promote decides by the
    larger end for exactly this case, so the pair must still come out as one
    litre figure - '0,9-1,12 litre', never '900 cc-1,12 litre'."""
    inputs, _ = dose_answer.validate(_raw(product="FLY AZOT", group="sebze", value="4,5"))
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_high, totals[0].total_unit) == (
        0.9, 1.125, "litre")
    text = dose_answer.render(inputs, totals)
    assert "0,9–1,12 litre" in text
    assert "900" not in text


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


def test_the_answer_restates_what_it_computed_from():
    inputs, _ = dose_answer.validate(_raw(group="meyve", value="5"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert "HİGRO FUBBY" in text
    assert "5 dönüm" in text
    assert "Meyve" in text


def test_the_answer_names_the_method_the_figure_belongs_to():
    """The source decides the method, not the farmer - so the answer says which
    one it is showing."""
    inputs, _ = dose_answer.validate(_raw(group="meyve", value="5"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert "Damlamadan" in text


def test_the_answer_prints_the_published_dose_and_the_total():
    inputs, _ = dose_answer.validate(_raw(group="meyve", value="5"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert "1–1,5 litre" in text     # the maker's per-dekar figure
    assert "5–7,5 litre" in text     # over 5 donum


def test_a_single_figure_prints_one_number_not_a_range():
    inputs, _ = dose_answer.validate(_raw(value="2"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert "500 gr" in text
    assert "500–500" not in text


def test_every_answer_says_whose_figure_it_is():
    inputs, _ = dose_answer.validate(_raw(value="2"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert dose_answer.ATTRIBUTION in text


def test_every_answer_refuses_the_season_total_by_name():
    """A dose is per application, and only 8 of 48 panels state an interval or
    a count. Supplying one would mean authoring our own programme and
    presenting it as the manufacturer's."""
    inputs, _ = dose_answer.validate(_raw(value="2"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert dose_answer.SEASON_REFUSAL in text
    assert "sezon" in text.lower()


def test_a_missing_figure_is_named_not_guessed():
    """Says what WE hold, not what the manufacturer published: for at least
    one real product the source page does carry a per-dekar figure for the
    group asked about that our parser simply could not read - so the message
    must claim only that we have no readable number, never that none exists."""
    inputs, _ = dose_answer.validate(_raw(group="tarla"))
    text = dose_answer.no_dose_for_group(inputs)
    assert "HİGRO FUBBY" in text
    assert "tarla bitki" in text
    assert "okunabilir" in text or "okuyamadım" in text
    assert "yayımlanmamış" not in text
    assert not any(ch.isdigit() for ch in text)


def test_a_missing_figure_does_not_point_at_a_figure():
    """no_dose_for_group() says no figure exists, then must not turn around and
    say "Bu rakam..." ("this figure...") - ATTRIBUTION opens with exactly that
    demonstrative, so appending it here would have the answer point at a number
    in the same breath it just said does not exist."""
    inputs, _ = dose_answer.validate(_raw(product="FLY AZOT", group="meyve"))
    text = dose_answer.no_dose_for_group(inputs)
    assert dose_answer.ATTRIBUTION not in text
    assert "Bu rakam" not in text


def test_every_method_the_parser_can_emit_has_a_turkish_label():
    """A method with no label is a KeyError inside a rendered answer - and it
    reaches a user, not a test, because the shipped data has one of them once."""
    from src import dose_parse
    for method, _pattern in dose_parse._METHODS:
        assert method in dose_answer.METHOD_LABELS


def test_every_group_has_a_sentence_form():
    for key, _label in dose_answer.GROUPS:
        assert key in dose_answer.GROUP_IN_SENTENCE
