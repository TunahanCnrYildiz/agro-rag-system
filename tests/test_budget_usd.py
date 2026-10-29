"""The budget card for a farmer abroad: FAOSTAT figures, in US dollars.

The currency belongs to the CARD, not to a field: a price in dollars beside a
cost in lira would produce a margin in neither. A Turkish card is unchanged.
"""
import pytest

from src import budget
from src.norms import CropNorm, NormValue

FRANCE_WHEAT = CropNorm(
    crop="bugday",
    label="Buğday",
    yield_kg_da=NormValue(712.4, 2024, "ulke", "France", "kg/da", flag="A"),
    price_per_kg=NormValue(0.2134, 2024, "ulke", "France", "USD/kg", flag="A"),
)
EGYPT_RICE = CropNorm(
    crop="celtik",
    label="Çeltik",
    yield_kg_da=NormValue(950.0, 2023, "ulke", "Egypt", "kg/da", flag="E"),
    price_per_kg=NormValue(0.31, 2023, "ulke", "Egypt", "USD/kg", flag="A"),
)


def _units(spec, field_id):
    return [u["id"] for u in next(f for f in spec["fields"] if f["id"] == field_id)["units"]]


def test_a_dollar_card_prices_and_costs_in_dollars():
    spec = budget.form_spec([], (FRANCE_WHEAT,), latest_year=2024, currency="USD")
    assert _units(spec, "price") == ["usd_kg", "usd_ton"]
    assert _units(spec, "cost") == ["usd"]
    # Area and yield are physical and the same everywhere.
    assert _units(spec, "area") == ["donum", "hektar"]


def test_a_lira_card_is_unchanged():
    """The default stays exactly what an already-deployed client reads."""
    assert budget.form_spec([], None) == budget.form_spec([], None, currency="TRY")
    spec = budget.form_spec([], None)
    assert _units(spec, "price") == ["tl_kg", "tl_ton"]
    assert _units(spec, "cost") == ["tl"]


def test_a_country_figure_names_faostat_not_tuik():
    row = budget.form_spec([], (FRANCE_WHEAT,), latest_year=2024, currency="USD")["crops"][0]
    assert row["price"] == {"value": "213,40", "unit": "usd_ton",
                            "note": "FAOSTAT 2024, France", "recent": None}
    assert row["yield"]["note"] == "FAOSTAT 2024, France"
    assert "TÜİK" not in str(row)


def test_an_estimated_figure_says_it_is_an_estimate():
    """51,3% of the printed FAOSTAT yields are FAO's own estimate, not the
    country's report; a figure printed without saying so is attributed to a
    country that never reported it."""
    row = budget.form_spec([], (EGYPT_RICE,), latest_year=2023, currency="USD")["crops"][0]
    assert row["yield"]["note"] == "FAOSTAT 2023, Egypt (FAO tahmini)"
    assert row["price"]["note"] == "FAOSTAT 2023, Egypt"


def _payload(price_unit="usd_kg", cost_unit="usd", **extra):
    return {"area": {"value": "10", "unit": "donum"},
            "yield_total": {"value": "7000", "unit": "kg"},
            "price": {"value": "0,25", "unit": price_unit},
            "cost": {"value": "500", "unit": cost_unit}, **extra}


def test_a_dollar_card_computes_and_writes_dollars():
    inputs, errors = budget.validate(_payload(), (FRANCE_WHEAT,), currency="USD")
    assert errors == []
    text = budget.render(inputs, budget.compute(inputs))
    assert "Gelir **1.750,00 USD**" in text
    assert "ton fiyatı **250,00 USD**" in text
    assert "Masraf **500,00 USD**" in text
    assert "TL" not in text


def test_lira_units_are_refused_on_a_dollar_card():
    """Mixing currencies would compute a margin in neither."""
    inputs, errors = budget.validate(_payload("tl_kg", "tl"), (FRANCE_WHEAT,),
                                     currency="USD")
    assert inputs is None
    assert {e.field for e in errors} == {"price", "cost"}


def test_dollar_units_are_refused_on_a_lira_card():
    inputs, errors = budget.validate(_payload(), None)
    assert inputs is None
    assert {e.field for e in errors} == {"price", "cost"}


def test_an_accepted_country_figure_is_framed_as_a_country_average():
    raw = _payload(crop="bugday")
    raw["price"] = {"value": "213,40", "unit": "usd_ton", "source": "norm"}
    inputs, errors = budget.validate(raw, (FRANCE_WHEAT,), currency="USD")
    assert errors == []
    assert inputs.price_tl_kg.note == "FAOSTAT 2024, France"
    text = budget.framing(inputs)
    assert "ülke ortalamasıdır (FAOSTAT 2024, France)" in text
    assert "Ülke ortalaması tek bir tarlanın" in text
    assert "bölge" not in text


def test_a_figure_claimed_as_norm_but_edited_is_the_farmers_own():
    raw = _payload(crop="bugday")
    raw["price"] = {"value": "300,00", "unit": "usd_ton", "source": "norm"}
    inputs, _ = budget.validate(raw, (FRANCE_WHEAT,), currency="USD")
    assert inputs.price_tl_kg.source == "user"


@pytest.mark.parametrize("currency", ["EUR", "", None])
def test_an_unknown_currency_is_a_programming_error(currency):
    with pytest.raises(ValueError):
        budget.form_spec([], None, currency=currency)


def test_a_small_dollar_price_keeps_its_precision():
    """Per kg at two decimals, Egypt's sugar beet (0,026 USD/kg) would prefill
    as 0,03 - 15% high, and every revenue from it with it. Per ton it is exact."""
    beet = CropNorm(crop="seker pancari", label="Şeker Pancarı", yield_kg_da=None,
                    price_per_kg=NormValue(0.026, 2023, "ulke", "Egypt", "USD/kg", flag="A"))
    row = budget.form_spec([], (beet,), latest_year=2023, currency="USD")["crops"][0]
    assert (row["price"]["value"], row["price"]["unit"]) == ("26,00", "usd_ton")


def test_a_lira_price_is_still_per_kg():
    wheat = CropNorm(crop="bugday", label="Buğday", yield_kg_da=None,
                     price_per_kg=NormValue(12.5, 2025, "il", "Konya", "TL/kg"))
    row = budget.form_spec([], (wheat,), latest_year=2025)["crops"][0]
    assert (row["price"]["value"], row["price"]["unit"]) == ("12,50", "tl_kg")
