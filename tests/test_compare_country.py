"""The comparison card for a farmer abroad: FAOSTAT figures, in US dollars -
the budget card's rule (tests/test_budget_country_route.py) on the other card.
A province is still TÜİK and lira, and its text is unchanged."""

import json

import pytest

from src import crop_compare, engine

FRANCE_Q = "Fransa'dayım, bu yıl buğday mı arpa mı ekmeliyim?"
KONYA_Q = "Konya'dayım, bu yıl domates mi biber mi ekmeliyim?"
NOWHERE_Q = "Bu yıl buğday mı arpa mı ekmeliyim?"
WHEAT, BARLEY = "bugday, durum bugdayi haric", "arpa (diger)"


@pytest.fixture
def no_llm(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the comparison route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return monkeypatch


def test_a_farmer_abroad_gets_the_card_for_their_country(no_llm):
    result = engine.answer(FRANCE_Q)
    assert result.compare_form is not None
    assert result.compare_form["province"] == "France"
    ids = {c["id"] for c in result.compare_form["crops"]}
    assert {WHEAT, BARLEY} <= ids
    assert "ülkenizde" in result.answer


def test_the_country_comparison_is_in_dollars_from_faostat(no_llm):
    text = engine.answer(FRANCE_Q, None, None, None,
                         {"first": WHEAT, "second": BARLEY}).answer
    # 597,35 kg/da × 0,2313 USD/kg and 534,66 × 0,2393
    assert "**138,17 USD**" in text
    assert "**127,94 USD**" in text
    assert "FAOSTAT 2024, France" in text
    assert "231,30 USD/ton" in text
    assert "TÜİK" not in text and " TL" not in text
    assert "FAOSTAT'ın yayımladığı ülke ortalamalarıdır" in text
    assert crop_compare.NOT_PROFIT in text


def test_the_country_comparison_offers_both_crops(no_llm):
    result = engine.answer(FRANCE_Q, None, None, None, {"first": WHEAT, "second": BARLEY})
    assert result.crop_offer == ("Buğday", "Arpa")


def test_a_province_comparison_reads_exactly_as_before(no_llm):
    text = engine.answer(KONYA_Q, None, None, None,
                         {"first": "domates (sofralik)",
                          "second": "biber (salcalik, kapya)"}).answer
    assert "TÜİK" in text and " TL" in text
    assert "FAOSTAT" not in text and "USD" not in text
    assert crop_compare.ATTRIBUTION in text


def test_no_place_still_asks_and_now_names_the_country_option(no_llm):
    result = engine.answer(NOWHERE_Q)
    assert result.answer == crop_compare.NO_PROVINCE
    assert "Fransa'dayım" in crop_compare.NO_PROVINCE
    assert result.compare_form is None


def test_a_crop_the_country_has_no_figure_for_says_the_country(no_llm):
    form = engine.answer(FRANCE_Q).compare_form
    unknown = {"first": WHEAT, "second": "no-such-crop"}
    result = engine.answer(FRANCE_Q, None, None, None, unknown)
    assert result.compare_form["errors"]["second"] == (
        "İkinci ürün için bu ülkede yayımlanmış bir rakam yok.")
    assert form is not None


def test_the_stream_compares_in_dollars_too(no_llm):
    events = [json.loads(c.split("data: ", 1)[1]) for c in engine.stream_answer(
        FRANCE_Q, None, None, None, {"first": WHEAT, "second": BARLEY}) if "data: " in c]
    text = "".join(e["content"] for e in events if e["type"] == "token")
    assert "**138,17 USD**" in text


def test_a_country_reporting_a_year_late_still_gets_a_revenue(no_llm):
    """Egypt's latest prices are 2023. With the dataset's 2024 as the cutoff
    every Egyptian crop would read "no current price" and no revenue."""
    q = "Mısır'dayım, bu yıl buğday mı arpa mı ekmeliyim?"
    text = engine.answer(q, None, None, None, {"first": WHEAT, "second": BARLEY}).answer
    assert "FAOSTAT 2023, Egypt" in text
    assert text.count("dekara brüt gelir") == 2
