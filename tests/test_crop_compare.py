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
