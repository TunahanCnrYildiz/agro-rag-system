"""The budget card for a farmer abroad, end to end on the shipped data (PDF p14:
"Çiftçi bir ürün seçtiğinde bulunduğu yerin verim ve fiyat rakamları forma
hazır gelir"). A province is TÜİK and lira; a country is FAOSTAT and dollars."""

import pytest

from src import engine, norms

FRANCE_Q = "Fransa'dayım, buğdaydan ne kadar gelir elde ederim?"
EGYPT_Q = "Mısır'dayım, ne kadar gelir elde ederim?"
KONYA_Q = "Konya'dayım, buğdaydan ne kadar gelir elde ederim?"
NOWHERE_Q = "Buğdaydan ne kadar gelir elde ederim?"


@pytest.fixture
def no_llm(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the budget route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return monkeypatch


def _units(form, field_id):
    return [u["id"] for u in next(f for f in form["fields"] if f["id"] == field_id)["units"]]


WHEAT = "bugday, durum bugdayi haric"   # durum wheat has no FAOSTAT counterpart


def _row(form, crop_id):
    return next(r for r in form["crops"] if r["id"] == crop_id)


def test_a_farmer_abroad_gets_a_dollar_card_with_faostat_figures(no_llm):
    form = engine.answer(FRANCE_Q).form
    assert _units(form, "price") == ["usd_kg", "usd_ton"]
    assert _units(form, "cost") == ["usd"]
    wheat = _row(form, WHEAT)
    assert wheat["yield"]["note"].startswith("FAOSTAT 2024, France")
    assert wheat["price"]["unit"] == "usd_ton"
    assert "TÜİK" not in str(form["crops"])


def test_a_country_with_a_later_reporting_lag_still_gets_prices(no_llm):
    """Egypt's latest prices are 2023; one global 2024 cutoff would serve none."""
    form = engine.answer(EGYPT_Q).form
    priced = [r for r in form["crops"] if r["price"]]
    assert len(priced) > 50
    assert all(r["price"]["note"].startswith("FAOSTAT 2023, Egypt") for r in priced)


def test_an_estimated_yield_says_so_on_the_card(no_llm):
    """Egypt: 104 of 110 printed yields are FAO's estimate."""
    form = engine.answer(EGYPT_Q).form
    notes = [r["yield"]["note"] for r in form["crops"] if r["yield"]]
    assert sum(n.endswith("(FAO tahmini)") for n in notes) > len(notes) / 2


def test_a_province_is_still_tuik_and_lira(no_llm):
    form = engine.answer(KONYA_Q).form
    assert _units(form, "price") == ["tl_kg", "tl_ton"]
    assert _row(form, WHEAT)["yield"]["note"].startswith("TÜİK")


def test_no_place_is_still_the_national_lira_card(no_llm):
    form = engine.answer(NOWHERE_Q).form
    assert _units(form, "price") == ["tl_kg", "tl_ton"]


def _dollar_payload(price_unit="usd_kg", cost_unit="usd"):
    return {"area": {"value": "10", "unit": "donum"},
            "yield_total": {"value": "7", "unit": "ton"},
            "price": {"value": "0,25", "unit": price_unit},
            "cost": {"value": "500", "unit": cost_unit}}


def test_turn_two_computes_in_dollars(no_llm):
    result = engine.answer(FRANCE_Q, None, _dollar_payload())
    assert result.form is None
    assert "Gelir **1.750,00 USD**" in result.answer
    assert " TL" not in result.answer


def test_turn_two_refuses_lira_on_a_dollar_card(no_llm):
    """A deployed lira-only client cannot slip lira into a dollar card: the card
    comes back with its own units and an error on each money field."""
    result = engine.answer(FRANCE_Q, None, _dollar_payload("tl_kg", "tl"))
    assert result.form is not None
    errored = {f["id"] for f in result.form["fields"] if f["error"]}
    assert errored == {"price", "cost"}
    assert _units(result.form, "price") == ["usd_kg", "usd_ton"]


def test_the_stream_serves_the_same_dollar_card(no_llm):
    import json
    events = [json.loads(c.split("data: ", 1)[1])
              for c in engine.stream_answer(FRANCE_Q) if "data: " in c]
    form = next(e["form"] for e in events if e["type"] == "form")
    assert _units(form, "cost") == ["usd"]


def test_a_broken_norm_layer_keeps_the_dollar_card(no_llm, monkeypatch):
    """The prefill is a convenience; the currency is not. A failing table must
    not turn a farmer abroad's card back into lira."""
    def broken(*args, **kwargs):
        raise RuntimeError("norms broken")

    monkeypatch.setattr(norms, "country_table", broken)
    form = engine.answer(FRANCE_Q).form
    assert "crops" not in form
    assert _units(form, "cost") == ["usd"]
