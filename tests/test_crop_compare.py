"""Unit tests for src/crop_compare.py (no network, no store, no model)."""

import json

import pytest

from src import crop_compare, norms


TABLE = {
    # FOUR years, not two, and that is load-bearing: norms._recent_range needs at
    # least TWO values before the picked year or it returns (None, None), and the
    # five-year range would silently never reach the answer.
    "meta": {"generated": "2026-08-26", "years": [2022, 2023, 2024, 2025]},
    "crops": {
        "domates (sofralik)": {
            "label": "Domates (Sofralık)",
            "yield_kg_da": {"scope": "il", "Konya": [4930.6, 5100.0, 6473.1, 5492.1],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [12.0, 15.0, 18.0, 21.06],
                            "TR": [None, None, None, None]},
        },
        "biber (salcalik, kapya)": {
            "label": "Biber (Salçalık, Kapya)",
            "yield_kg_da": {"scope": "il", "Konya": [2997.5, 3100.0, 3732.6, 3154.7],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [20.0, 25.0, 30.0, 39.89],
                            "TR": [None, None, None, None]},
        },
        "tatli patates": {
            "label": "Tatlı Patates",
            "yield_kg_da": {"scope": "il", "Konya": [1900.0, 2000.0, 2050.0, 2100.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [8.0, 9.0, 10.0, 12.0],
                            "TR": [None, None, None, None]},
        },
        "arpa (biralik)": {
            "label": "Arpa (Biralık)",
            "yield_kg_da": {"scope": "il", "Konya": [380.0, 395.0, 410.0, 420.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [6.0, 7.0, 8.0, 9.5],
                            "TR": [None, None, None, None]},
        },
        "bugday, durum bugdayi haric": {
            "label": "Buğday, Durum Buğdayı Hariç",
            "yield_kg_da": {"scope": "il", "Konya": [430.0, 445.0, 460.0, 470.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [7.0, 8.0, 9.0, 10.5],
                            "TR": [None, None, None, None]},
        },
        "kara bugday": {
            "label": "Kara Buğday",
            "yield_kg_da": {"scope": "il", "Konya": [280.0, 290.0, 300.0, 310.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [11.0, 12.0, 13.0, 14.5],
                            "TR": [None, None, None, None]},
        },
    },
}


@pytest.fixture(autouse=True)
def table(tmp_path, monkeypatch):
    """Every test here runs against a fixture table, never the shipped file:
    a real crop's figures changing must not turn these red."""
    path = tmp_path / "crop_norms.json"
    path.write_text(json.dumps(TABLE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    crop_compare._families.cache_clear()
    yield
    norms._load.cache_clear()
    crop_compare._families.cache_clear()


def test_two_crops_are_found_in_a_comparison_question():
    assert crop_compare.named_crops(
        "Bu yıl domates mi biber mi ekmeliyim?") == ("Domates", "Biber")


def test_a_crop_is_found_through_a_turkish_suffix():
    """'domatesi', 'bibere' - the matcher must see the name through a case
    ending, the same way the retrieval lexicon's matcher does."""
    assert crop_compare.named_crops("Domatesi mi bibere mi yatırım yapsam?") == (
        "Domates", "Biber")


def test_a_name_inside_a_longer_word_is_not_a_crop():
    """The bounded-suffix matcher exists so 'arpa' does not fire inside
    'arpacık' - a stye, not a barley field."""
    assert crop_compare.named_crops("Gözümde arpacık çıktı, ne yapmalıyım?") == ()


def test_a_two_word_crop_is_one_crop_not_two():
    """'Tatlı Patates' contains 'Patates'. Counting both would turn one crop
    into a comparison the farmer never asked for."""
    assert crop_compare.named_crops("Tatlı patates ekmeyi düşünüyorum") == (
        "Tatlı Patates",)


def test_an_open_question_names_no_crop():
    assert crop_compare.named_crops("Bu yıl tarlama ne eksem iyi olur?") == ()


def test_the_same_crop_twice_is_one_crop():
    assert crop_compare.named_crops("Domates mi domates mi?") == ("Domates",)


def test_a_crop_the_table_does_not_carry_is_not_found():
    assert crop_compare.named_crops("Kahve mi kakao mu yetiştirsem?") == ()


def test_detection_never_raises_on_junk():
    for junk in ("", None, "?!.", "12345"):
        assert crop_compare.named_crops(junk) == ()


def test_a_shorter_crop_named_separately_is_not_swallowed():
    """The dedup is about POSITION, not spelling: `buğday` here is its own
    mention, not part of `kara buğday`. Dropping it meant the comparison card
    never appeared for a natural two-crop question."""
    assert crop_compare.named_crops(
        "Buğday mı kara buğday mı ekmeliyim?") == ("Buğday", "Kara Buğday")


def test_a_crop_covered_once_and_free_once_is_still_named():
    """`buğday` occurs twice - inside `kara buğday`, and alone. One free
    occurrence is enough."""
    assert crop_compare.named_crops(
        "Kara buğday mı buğday mı?") == ("Kara Buğday", "Buğday")


def _table():
    return norms.province_table("Konya")


def _raw(first="domates (sofralik)", second="biber (salcalik, kapya)"):
    return {"first": first, "second": second}


def test_two_chosen_crops_validate():
    inputs, errors = crop_compare.validate(_raw(), _table())
    assert errors == []
    assert (inputs.first, inputs.second) == (
        "domates (sofralik)", "biber (salcalik, kapya)")


def test_both_crops_are_required():
    inputs, errors = crop_compare.validate({}, _table())
    assert inputs is None
    assert {e.field for e in errors} == {"first", "second"}


def test_the_same_crop_twice_is_refused():
    """A comparison needs two different crops; the same row twice is a form
    the user filled wrong, not a question we can answer."""
    inputs, errors = crop_compare.validate(
        _raw(second="domates (sofralik)"), _table())
    assert inputs is None
    assert [e.field for e in errors] == ["second"]


def test_a_crop_the_province_does_not_carry_is_a_field_error():
    inputs, errors = crop_compare.validate(_raw(first="yok bir urun"), _table())
    assert inputs is None
    assert [e.field for e in errors] == ["first"]


def test_validate_never_raises_on_junk():
    for junk in (None, [], "domates", {"first": 7, "second": None}):
        inputs, errors = crop_compare.validate(junk, _table())
        assert inputs is None and errors


def test_a_fresh_card_lists_every_crop_the_province_carries():
    spec = crop_compare.form_spec([], _table())
    assert spec["kind"] == "crop_compare"
    labels = [c["label"] for c in spec["crops"]]
    assert "Domates (Sofralık)" in labels and "Biber (Salçalık, Kapya)" in labels
    assert spec["first"] == "" and spec["second"] == ""
    assert all(v is None for v in spec["errors"].values())


def test_the_card_carries_only_ids_and_labels():
    """The budget card ships a whole province of prefill cells because it
    prefills; this one only fills two selects, and 246 rows of figures on the
    wire would be dead weight."""
    spec = crop_compare.form_spec([], _table())
    assert all(set(c) == {"id", "label"} for c in spec["crops"])


def test_a_rejected_card_echoes_what_was_chosen():
    raw = _raw(second="domates (sofralik)")
    _inputs, errors = crop_compare.validate(raw, _table())
    spec = crop_compare.form_spec(errors, _table(), raw)
    assert spec["first"] == "domates (sofralik)"
    assert spec["errors"]["second"]


def test_the_card_names_the_province_it_was_built_for():
    """The farmer has to be able to see which province's figures they are
    about to be shown - a wrong province is a wrong answer that reads right."""
    spec = crop_compare.form_spec([], _table(), None, "Konya")
    assert spec["province"] == "Konya"


def test_gross_revenue_is_yield_times_price():
    inputs, _ = crop_compare.validate(_raw(), _table())
    first, second = crop_compare.compute(inputs, _table(), 2025)
    assert round(first.revenue_tl_da) == 115664      # 5492,1 x 21,06
    assert round(second.revenue_tl_da) == 125841     # 3154,7 x 39,89


def test_a_price_older_than_the_latest_year_yields_no_revenue():
    """Lira is nominal: P2b measured a 2018 price prefilling nine times too
    low. An older price is not a smaller figure, it is a different currency."""
    inputs, _ = crop_compare.validate(_raw(), _table())
    first, _second = crop_compare.compute(inputs, _table(), 2026)
    assert first.revenue_tl_da is None
    assert first.missing == "fiyat"


def test_a_missing_half_is_never_zero():
    """Absence, not 0: a zero flows into a revenue line as "this crop earns
    nothing", which is a claim we never measured."""
    inputs, _ = crop_compare.validate(_raw(), _table())
    first, _second = crop_compare.compute(inputs, _table(), 2026)
    assert first.revenue_tl_da is None


def test_each_figure_keeps_its_year_and_region():
    inputs, _ = crop_compare.validate(_raw(), _table())
    first, _second = crop_compare.compute(inputs, _table(), 2025)
    assert (first.yield_value.year, first.yield_value.region) == (2025, "Konya")


def test_the_answer_prints_both_crops_with_their_figures():
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    assert "Domates (Sofralık)" in text and "Biber (Salçalık, Kapya)" in text
    assert "115.664 TL" in text and "125.841 TL" in text


def test_the_answer_says_whose_figures_these_are():
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    assert crop_compare.ATTRIBUTION in text
    assert "TÜİK" in text and "2025" in text


def test_every_answer_refuses_the_profit_comparison():
    """The binding one. Two gross figures side by side read as a ranking, and
    the cost that would decide it is not in this project at all."""
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    assert crop_compare.NOT_PROFIT in text
    assert "masraf" in text


def test_the_answer_never_names_a_winner():
    """No sentence may recommend one of the two. The figures are the answer."""
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    for verdict in ("öneririm", "tercih edin", "daha kârlı", "daha iyi",
                    "tavsiye ederim", "seçin"):
        assert verdict not in text.lower(), verdict


def test_a_crop_with_a_missing_half_says_which_half():
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2026))
    assert "fiyat" in text
    assert "115.663" not in text and "115.664" not in text


def test_the_five_year_range_reaches_the_answer():
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    assert "önceki" in text
