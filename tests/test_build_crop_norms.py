"""Tests for the offline converter.

It runs by hand, about once a year, so its job is to fail loudly rather than to
be convenient. Every row it cannot use must be reported, never quietly zeroed -
a zero flows into the budget arithmetic and comes out as a confident wrong figure.
"""
from scripts import build_crop_norms as bcn


R = bcn.Row


def _rows():
    """Two provinces, two years, one cereal with a published Verim."""
    return [
        R("Adana", "Durum Buğdayı", 2024, "verim", 369.0),
        R("Adana", "Durum Buğdayı", 2025, "verim", 322.0),
        R("Adıyaman", "Durum Buğdayı", 2024, "verim", 344.0),
        R("Adıyaman", "Durum Buğdayı", 2025, "verim", 233.0),
    ]


def test_the_year_axis_is_shared_and_sorted():
    out = bcn.build(_rows())
    assert out["meta"]["years"] == [2024, 2025]


def test_series_are_aligned_to_the_year_axis():
    out = bcn.build(_rows())
    assert out["crops"]["durum bugdayi"]["yield_kg_da"]["Adana"] == [369.0, 322.0]


def test_a_missing_year_becomes_null_not_zero():
    """A gap must survive as a gap."""
    rows = [r for r in _rows() if not (r.province == "Adana" and r.year == 2024)]
    out = bcn.build(rows)
    assert out["crops"]["durum bugdayi"]["yield_kg_da"]["Adana"] == [None, 322.0]


def test_scope_is_il_when_a_province_row_exists():
    out = bcn.build(_rows())
    assert out["crops"]["durum bugdayi"]["yield_kg_da"]["scope"] == "il"


def test_the_national_row_exists_but_is_empty():
    """The exports are province-level only, so there is no published Türkiye
    figure. The row is required by src/norms.py and must be present and EMPTY
    rather than averaged - a mean of the provinces is a number nobody published."""
    out = bcn.build(_rows())
    assert out["crops"]["durum bugdayi"]["yield_kg_da"]["TR"] == [None, None]


def test_price_ships_empty_until_the_price_export_arrives():
    """src/norms.py drops a crop whose price measure is malformed, so the key has
    to be there. An all-null series is honest: lookup returns no price norm."""
    out = bcn.build(_rows())
    price = out["crops"]["durum bugdayi"]["price_tl_kg"]
    assert price["scope"] == "tr"
    assert price["TR"] == [None, None]


def test_vegetable_yield_is_derived_from_production_and_area():
    """Vegetables have no published Verim: TÜİK gives Üretim Miktarı in tons and
    Ekilen Alan in dekar. 300 ton over 100 dekar is 3000 kg/dekar."""
    rows = [
        R("Manisa", "Domates", 2025, "uretim", 300.0),
        R("Manisa", "Domates", 2025, "alan", 100.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["domates"]["yield_kg_da"]["Manisa"] == [3000.0]


def test_a_derived_yield_needs_both_halves():
    """One half alone proves nothing. The province is left out of the series
    entirely - which is the strongest form of "no norm", since there is no cell
    for a later reader to mistake for a measurement."""
    rows = [R("Manisa", "Domates", 2025, "uretim", 300.0)]
    out = bcn.build(rows)
    assert "Manisa" not in out["crops"]["domates"]["yield_kg_da"]


def test_a_zero_area_does_not_divide():
    """300 tons over 0 dekar is not a yield of any size. No division, no entry."""
    rows = [
        R("Manisa", "Domates", 2025, "uretim", 300.0),
        R("Manisa", "Domates", 2025, "alan", 0.0),
    ]
    out = bcn.build(rows)
    assert "Manisa" not in out["crops"]["domates"]["yield_kg_da"]


def test_a_published_verim_wins_over_a_derivable_one():
    """Never recompute a figure the source already publishes."""
    rows = [
        R("Manisa", "Domates", 2025, "verim", 4200.0),
        R("Manisa", "Domates", 2025, "uretim", 300.0),
        R("Manisa", "Domates", 2025, "alan", 100.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["domates"]["yield_kg_da"]["Manisa"] == [4200.0]


def test_an_unknown_province_is_skipped_loudly(capsys):
    rows = _rows() + [R("Kudüs", "Durum Buğdayı", 2025, "verim", 1.0)]
    out = bcn.build(rows)
    assert "Kudüs" in capsys.readouterr().err
    assert "Kudüs" not in out["crops"]["durum bugdayi"]["yield_kg_da"]


def test_the_output_passes_the_loader_that_will_read_it(tmp_path, monkeypatch):
    """The converter and the loader must agree, or the file is dead on arrival."""
    import json
    from src import norms
    path = tmp_path / "crop_norms.json"
    path.write_text(json.dumps(bcn.build(_rows()), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    n = norms.lookup("durum bugdayi", "Adana")
    assert n.yield_kg_da.amount == 322.0
    assert n.yield_kg_da.year == 2025
    assert n.price_tl_kg is None


def test_parse_label_reads_the_measure_and_the_name():
    assert bcn.parse_label("Verim ve 01.11.11.00.00. (Durum Buğdayı) - Kg/Dekar") == (
        "verim", "Durum Buğdayı")
    assert bcn.parse_label("Ekilen Alan ve 01.11.61.00.01. (Fasulye, Taze) - Dekar") == (
        "alan", "Fasulye, Taze")
    assert bcn.parse_label("Üretim Miktarı ve 01.13.34.00.00. (Domates) - Ton") == (
        "uretim", "Domates")


def test_parse_label_keeps_a_nested_parenthesis_in_the_name():
    """'Arpa (Biralık)' - a lazy regex would cut the name at the inner paren."""
    assert bcn.parse_label("Verim ve 01.11.31.00.01. (Arpa (Biralık)) - Kg/Dekar") == (
        "verim", "Arpa (Biralık)")


def test_hakkari_is_renamed_to_the_spelling_the_province_table_uses():
    """TÜİK writes 'Hakkari', src/context/location.py writes 'Hakkâri'. A
    mismatch does not raise - it silently never matches."""
    rows = [R("Hakkari", "Durum Buğdayı", 2025, "verim", 100.0)]
    out = bcn.build(rows)
    assert "Hakkâri" in out["crops"]["durum bugdayi"]["yield_kg_da"]


def test_a_derived_yield_is_not_given_fake_precision():
    """Tonnes over dekars, both rounded at the source. 100 ton / 3 dekar is
    33333.3 kg/da, not 33333.333333333336."""
    rows = [
        R("Manisa", "Domates", 2025, "uretim", 100.0),
        R("Manisa", "Domates", 2025, "alan", 3.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["domates"]["yield_kg_da"]["Manisa"] == [33333.3]
