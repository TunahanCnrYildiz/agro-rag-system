"""Tests for the offline converter.

It runs by hand, about once a year, so its job is to fail loudly rather than to
be convenient. Every row it cannot use must be reported, never quietly zeroed -
a zero flows into the budget arithmetic and comes out as a confident wrong figure.
"""
import pytest

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
    # Undo the cache poisoning, not just the monkeypatch: _load is an
    # lru_cache, so leaving the cache holding this tmp_path's tiny table
    # would answer every later test - in this file and any other - from a
    # fixture with only "durum bugdayi" in it, long after _PATH is back.
    norms._load.cache_clear()


def test_parse_label_reads_the_measure_the_name_and_the_unit():
    assert bcn.parse_label("Verim ve 01.11.11.00.00. (Durum Buğdayı) - Kg/Dekar") == (
        "verim", "Durum Buğdayı", "Kg/Dekar")
    assert bcn.parse_label("Ekilen Alan ve 01.11.61.00.01. (Fasulye, Taze) - Dekar") == (
        "alan", "Fasulye, Taze", "Dekar")
    assert bcn.parse_label("Üretim Miktarı ve 01.13.34.00.00. (Domates) - Ton") == (
        "uretim", "Domates", "Ton")


def test_a_per_tree_yield_is_read_under_its_own_measure():
    """TÜİK publishes orchard fruit yield ONLY as Kg/Meyve Veren Ağaç. It is
    read - the density gate needs it as evidence - but under a measure name of
    its own, so no code path can mistake it for a per-dekar figure."""
    assert bcn.parse_label(
        "Verim ve 01.24.10.00.00. (Elma) - Kg/Meyve Veren Ağaç") == (
        "verim_agac", "Elma", "Kg/Meyve Veren Ağaç")


def test_a_per_tree_yield_never_becomes_a_yield():
    """Written into a per-dekar field an apple would read 80 instead of ~2500 -
    silently wrong by more than an order of magnitude. Evidence only.

    The uretim/alan pair is what makes this test BITE, and it was missing when
    the test was first written: without a derivable figure to compete with, the
    assertion held whether or not `published` ever read the per-tree bucket.
    Here 250 tons over 100 dekars derives 2500 kg/da at an implied 31 trees/da,
    so the cell is written - and if anything ever taught `published` to read
    `verim_agac`, this reads 80.0 instead."""
    rows = [
        R("Manisa", "Elma", 2025, "verim_agac", 80.0),
        R("Manisa", "Elma", 2025, "uretim", 250.0),
        R("Manisa", "Elma", 2025, "alan", 100.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["elma"]["yield_kg_da"]["Manisa"] == [2500.0]


def test_a_per_dekar_verim_is_still_read_as_a_yield():
    """The routing must not swallow the unit it was always meant to accept."""
    assert bcn.parse_label(
        "Verim ve 01.11.11.00.00. (Durum Buğdayı) - Kg/Dekar") == (
        "verim", "Durum Buğdayı", "Kg/Dekar")


def test_the_fruit_area_measure_is_recognised():
    """Fruits call it `Toplu Meyveliklerin Alanı`, vegetables `Ekilen Alan`."""
    assert bcn.parse_label(
        "Toplu Meyveliklerin Alanı ve 01.24.10.00.00. (Elma) - Dekar") == (
        "alan", "Elma", "Dekar")


def test_parse_label_keeps_a_nested_parenthesis_in_the_name():
    """'Arpa (Biralık)' - a lazy regex would cut the name at the inner paren."""
    assert bcn.parse_label("Verim ve 01.11.31.00.01. (Arpa (Biralık)) - Kg/Dekar") == (
        "verim", "Arpa (Biralık)", "Kg/Dekar")


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


def test_a_zero_yield_is_not_a_norm():
    """The exports carry zeros, and a true zero cannot be told from a missing
    marker. Neither reading is a norm: prefilling 0 would tell a farmer to expect
    no harvest and compute an income of zero."""
    rows = [
        R("Manisa", "Domates", 2024, "verim", 0.0),
        R("Manisa", "Domates", 2025, "verim", 4200.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["domates"]["yield_kg_da"]["Manisa"] == [None, 4200.0]


def test_a_crop_whose_every_value_is_zero_is_dropped_entirely():
    rows = [R("Manisa", "Domates", 2025, "verim", 0.0)]
    out = bcn.build(rows)
    assert "Manisa" not in out["crops"]["domates"]["yield_kg_da"]


def test_parse_label_takes_the_measure_from_the_olcum_when_the_label_omits_it():
    """The price topic writes no measure into the row label - the measure is the
    Olcum, in column 0. Production writes "Verim ve ..." into the label itself."""
    assert bcn.parse_label(
        "01.11.11.00.00. (Durum Buğdayı) - Kilogram",
        "Bitkisel Ürün Fiyatları (Tl)") == ("fiyat", "Durum Buğdayı", "Kilogram")


def test_a_price_in_the_wrong_unit_is_refused():
    assert bcn.parse_label(
        "01.11.11.00.00. (Durum Buğdayı) - Ton",
        "Bitkisel Ürün Fiyatları (Tl)") is None


def test_the_olcum_is_ignored_when_the_label_carries_its_own_measure():
    """A production row must not be reinterpreted by whatever column 0 says."""
    assert bcn.parse_label(
        "Verim ve 01.11.11.00.00. (Durum Buğdayı) - Kg/Dekar",
        "Tahıllar Ve Diğer Bitkisel Ürünler") == ("verim", "Durum Buğdayı", "Kg/Dekar")


def test_price_lands_in_its_own_measure_with_a_province_scope():
    rows = [
        R("Adana", "Durum Buğdayı", 2024, "fiyat", 9.25),
        R("Adana", "Durum Buğdayı", 2025, "fiyat", 11.4),
    ]
    out = bcn.build(rows)
    price = out["crops"]["durum bugdayi"]["price_tl_kg"]
    assert price["scope"] == "il"
    assert price["Adana"] == [9.25, 11.4]
    assert price["TR"] == [None, None]


def test_a_price_of_zero_is_not_a_norm_either():
    rows = [
        R("Adana", "Durum Buğdayı", 2024, "fiyat", 0.0),
        R("Adana", "Durum Buğdayı", 2025, "fiyat", 11.4),
    ]
    out = bcn.build(rows)
    assert out["crops"]["durum bugdayi"]["price_tl_kg"]["Adana"] == [None, 11.4]


def test_price_keeps_more_decimals_than_a_yield():
    """A yield is rounded to 0.1 kg/da; a price of 7.94 TL/kg must not become
    7.9, which is a 0.5% error on every revenue figure computed from it."""
    rows = [R("Adana", "Durum Buğdayı", 2025, "fiyat", 7.94)]
    out = bcn.build(rows)
    assert out["crops"]["durum bugdayi"]["price_tl_kg"]["Adana"] == [7.94]


def test_a_crop_with_only_a_price_still_loads(tmp_path, monkeypatch):
    """Both measures must exist for src/norms.py to keep the crop, even when one
    of them is empty."""
    import json
    from src import norms
    rows = [R("Adana", "Kivi", 2025, "fiyat", 30.0)]
    path = tmp_path / "crop_norms.json"
    path.write_text(json.dumps(bcn.build(rows), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    n = norms.lookup("kivi", "Adana")
    assert n is not None
    assert n.yield_kg_da is None
    assert n.price_tl_kg.amount == 30.0
    # See the same line in test_the_output_passes_the_loader_that_will_read_it:
    # _load is an lru_cache, so this tmp_path's single-crop table would
    # otherwise answer every later test in the process.
    norms._load.cache_clear()


def test_a_tree_crop_cell_inside_the_band_is_written_unchanged():
    """Ayva in Tokat 2025: 182 tons over 155 dekars, 31 kg per tree. That is
    (182000/31)/155 = 38 trees/da - a 5m x 5m orchard, exactly what the
    denominator claims to be. The gate must not touch a figure it accepts."""
    rows = [
        R("Tokat", "Ayva", 2025, "uretim", 182.0),
        R("Tokat", "Ayva", 2025, "alan", 155.0),
        R("Tokat", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_da"]["Tokat"] == [1174.2]


def test_a_cell_whose_area_cannot_hold_its_trees_is_refused():
    """Ayva in Ordu 2025: 267 tons over 3 dekars, 31 kg per tree. That implies
    (267000/31)/3 = 2871 trees on one dekar - 0,35 m2 each. The area is not the
    ground the production came from, so 89.000 kg/da is not a yield."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert "Ordu" not in out["crops"]["ayva"]["yield_kg_da"]


def test_a_cell_with_an_area_but_almost_no_production_is_refused():
    """The mirror error: 6 tons over 766 dekars at 27 kg per tree is 0,3
    trees/da - an orchard planted but not yet bearing. It understates the yield
    instead of inflating it, which is safer and still wrong in a revenue line."""
    rows = [
        R("Adana", "Avokado", 2021, "uretim", 6.0),
        R("Adana", "Avokado", 2021, "alan", 766.0),
        R("Adana", "Avokado", 2021, "verim_agac", 27.0),
    ]
    out = bcn.build(rows)
    assert "Adana" not in out["crops"]["avokado"]["yield_kg_da"]


def test_a_tree_crop_cell_with_no_per_tree_figure_is_refused():
    """The crop publishes per-tree yields elsewhere, so it IS a tree crop and
    this cell should have been judged - but this province-year carries no
    figure to judge it with. An unjudged cell and a judged one must not be
    indistinguishable in the output."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Tokat", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert "Ordu" not in out["crops"]["ayva"]["yield_kg_da"]


def test_a_zero_area_cell_is_refused_under_its_own_reason():
    """Zerdali in Afyonkarahisar 2019-2024: the province books 322 tons of fruit
    against ZERO dekars of compact orchard. No division can be performed, so no
    yield was ever written - but nothing said so, and the file could not tell
    this from a province that grows no wild apricot at all."""
    rows = [
        R("Afyonkarahisar", "Zerdali", 2024, "uretim", 322.0),
        R("Afyonkarahisar", "Zerdali", 2024, "alan", 0.0),
        R("Afyonkarahisar", "Zerdali", 2024, "verim_agac", 42.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert {"crop": "Zerdali", "province": "Afyonkarahisar", "year": 2024,
            "reason": "area_is_zero"} in record["cells"]


def test_a_zero_area_is_refused_on_a_crop_with_no_per_tree_figure_too():
    """Every zero-area cell in today's exports belongs to a tree crop, so this
    is the case the data does not currently carry. It is pinned anyway: the
    refusal is that nothing can be divided by zero, which is as true of a
    vegetable's `Ekilen Alan` as of an orchard's `Toplu Meyveliklerin Alani`.
    A future export must not fall back into silence."""
    rows = [
        R("Sivas", "Marul (Göbekli)", 2025, "uretim", 12.0),
        R("Sivas", "Marul (Göbekli)", 2025, "alan", 0.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert [c["reason"] for c in record["cells"]] == ["area_is_zero"]


def test_a_zero_area_with_nothing_grown_against_it_records_nothing():
    """A GUARD, NOT A NEW BEHAVIOUR - it passes before this change and must keep
    passing after it. Production 0 over area 0 is not a refusal: no figure was
    discarded, the province simply grew none of the crop that year. The record
    is a record of what was thrown out, and an entry here would say the
    opposite of the truth."""
    rows = [
        R("Kastamonu", "Limon Ve Misket Limonu", 2024, "uretim", 0.0),
        R("Kastamonu", "Limon Ve Misket Limonu", 2024, "alan", 0.0),
        R("Kastamonu", "Limon Ve Misket Limonu", 2024, "verim_agac", 30.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert record["cells"] == []


def test_a_cell_older_than_a_ceiling_refusal_is_refused_too():
    """THE SHADOW RULE. A ceiling refusal is not a verdict on one cell - it says
    this province's Toplu Meyveliklerin Alani is not the ground its production
    came off, and that is bookkeeping, not weather. It does not change from year
    to year.

    Measured on the real file: Turunc in Adana is refused above the ceiling in
    2022, 2023, 2024 AND 2025, and norms._pick walked past all four to serve
    2017 - the same broken denominator, 405 trees/da, just under the 444 ceiling
    - as 23.098 kg/da with no five-year range to warn anyone.
    """
    rows = [
        # 2017: squeaks under the ceiling at 405 trees/da.
        R("Adana", "Turunç", 2017, "uretim", 2309.8),
        R("Adana", "Turunç", 2017, "alan", 100.0),
        R("Adana", "Turunç", 2017, "verim_agac", 57.0),
        # 2025: 20.325 trees/da, refused.
        R("Adana", "Turunç", 2025, "uretim", 2439.0),
        R("Adana", "Turunç", 2025, "alan", 2.0),
        R("Adana", "Turunç", 2025, "verim_agac", 60.0),
    ]
    out = bcn.build(rows)
    assert "Adana" not in out["crops"]["turunc"]["yield_kg_da"]


def test_the_shadow_is_recorded_rather_than_dropped_silently():
    """Every refusal is visible - the same promise the gate itself makes."""
    rows = [
        R("Adana", "Turunç", 2017, "uretim", 2309.8),
        R("Adana", "Turunç", 2017, "alan", 100.0),
        R("Adana", "Turunç", 2017, "verim_agac", 57.0),
        R("Adana", "Turunç", 2025, "uretim", 2439.0),
        R("Adana", "Turunç", 2025, "alan", 2.0),
        R("Adana", "Turunç", 2025, "verim_agac", 60.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert record["counts"] == {"density_above_ceiling": 1,
                                "shadowed_by_ceiling_refusal": 1}
    assert {"crop": "Turunç", "province": "Adana", "year": 2017,
            "reason": "shadowed_by_ceiling_refusal"} in record["cells"]


def test_a_passing_year_sandwiched_between_refusals_is_shadowed():
    """THE SHADOW IS CAST BY THE LATEST REFUSAL, NOT THE EARLIEST. Refusals are
    not one contiguous run at the recent end - Dut in Mugla is refused in 2016,
    2017, 2018 and again in every year from 2020 on, because the recorded area
    lurches between 1, 46, 39 and 12 dekars. 2019 is the one year that lands
    under the ceiling, and shadowing only what precedes the FIRST refusal would
    leave it standing: 403 trees/da, 12.500 kg/da of mulberry, and it is exactly
    the cell norms._pick walks back to.

    Written after the first implementation shipped `min` and this case survived
    it - every other test in this file passed either way.
    """
    rows = [
        R("Muğla", "Dut", 2018, "uretim", 557.0),      # 17.406 trees/da
        R("Muğla", "Dut", 2018, "alan", 1.0),
        R("Muğla", "Dut", 2018, "verim_agac", 32.0),
        R("Muğla", "Dut", 2019, "uretim", 575.0),      # 403 trees/da - passes
        R("Muğla", "Dut", 2019, "alan", 46.0),
        R("Muğla", "Dut", 2019, "verim_agac", 31.0),
        R("Muğla", "Dut", 2020, "uretim", 600.0),      # 466 trees/da
        R("Muğla", "Dut", 2020, "alan", 39.0),
        R("Muğla", "Dut", 2020, "verim_agac", 33.0),
    ]
    out = bcn.build(rows)
    assert "Muğla" not in out["crops"]["dut"]["yield_kg_da"]


def test_a_cell_older_than_a_zero_area_year_is_shadowed_too():
    """A zero recorded orchard makes the ceiling's own statement in the
    strongest terms available: the recorded area is not the ground the
    production came off. That is how the province keeps its books, not what the
    weather did, so it condemns the earlier derived cells exactly as a ceiling
    refusal does.

    Zerdali in Afyonkarahisar, from the real exports: 2018 is 341 tons over 28
    dekars at 41 kg per tree - 297 trees/da, under the 444 ceiling, so the cell
    gate passes it and norms._pick serves it as 12.179 kg/da. 2019 books 322
    tons against zero dekars."""
    rows = [
        R("Afyonkarahisar", "Zerdali", 2018, "uretim", 341.0),
        R("Afyonkarahisar", "Zerdali", 2018, "alan", 28.0),
        R("Afyonkarahisar", "Zerdali", 2018, "verim_agac", 41.0),
        R("Afyonkarahisar", "Zerdali", 2019, "uretim", 322.0),
        R("Afyonkarahisar", "Zerdali", 2019, "alan", 0.0),
        R("Afyonkarahisar", "Zerdali", 2019, "verim_agac", 42.0),
    ]
    out = bcn.build(rows)
    assert "Afyonkarahisar" not in out["crops"]["zerdali"]["yield_kg_da"]


def test_the_zero_area_shadow_carries_the_reason_that_already_exists():
    """A zero area is treated as a ceiling refusal throughout, so the cells it
    condemns carry the existing reason. A second shadow reason would name a
    second concept, and there is only one."""
    rows = [
        R("Afyonkarahisar", "Zerdali", 2018, "uretim", 341.0),
        R("Afyonkarahisar", "Zerdali", 2018, "alan", 28.0),
        R("Afyonkarahisar", "Zerdali", 2018, "verim_agac", 41.0),
        R("Afyonkarahisar", "Zerdali", 2019, "uretim", 322.0),
        R("Afyonkarahisar", "Zerdali", 2019, "alan", 0.0),
        R("Afyonkarahisar", "Zerdali", 2019, "verim_agac", 42.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert record["counts"] == {"area_is_zero": 1,
                                "shadowed_by_ceiling_refusal": 1}


def test_a_zero_area_with_no_production_casts_no_shadow():
    """A GUARD - it passes before this change and must keep passing after it.
    Both figures at zero make no claim about the denominator: the province grew
    none of the crop that year. Only a zero area that production was booked
    against says the area column is wrong, so only that one reaches backwards."""
    rows = [
        R("Tokat", "Ayva", 2024, "uretim", 182.0),
        R("Tokat", "Ayva", 2024, "alan", 155.0),
        R("Tokat", "Ayva", 2024, "verim_agac", 31.0),
        R("Tokat", "Ayva", 2025, "uretim", 0.0),
        R("Tokat", "Ayva", 2025, "alan", 0.0),
        R("Tokat", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_da"]["Tokat"] == [1174.2, None]


def test_publication_lag_casts_no_shadow():
    """THE PRECISION THAT KEEPS THE RULE CHEAP. `no_per_tree_figure` means TUIK
    has not published the per-tree survey for that year yet - it says nothing
    about the denominator, so an older judged cell behind it is still good. Half
    of those refusals sit in 2025 purely because that survey lags; shadowing on
    them would delete sound figures across the whole freshest year.
    """
    rows = [
        R("Ordu", "Ayva", 2024, "uretim", 182.0),
        R("Ordu", "Ayva", 2024, "alan", 155.0),
        R("Ordu", "Ayva", 2024, "verim_agac", 31.0),
        # 2025 carries no per-tree figure, so it is refused unjudged.
        R("Ordu", "Ayva", 2025, "uretim", 182.0),
        R("Ordu", "Ayva", 2025, "alan", 155.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_da"]["Ordu"] == [1174.2, None]


def test_the_shadow_falls_backwards_only():
    """A later year that passes the gate is untouched by an earlier refusal -
    an orchard really can be planted, and the direction matters: _pick reads
    from the newest end, so shadowing forwards would delete the good cell it
    would otherwise have served."""
    rows = [
        R("Adana", "Turunç", 2017, "uretim", 2439.0),
        R("Adana", "Turunç", 2017, "alan", 2.0),
        R("Adana", "Turunç", 2017, "verim_agac", 60.0),
        R("Adana", "Turunç", 2025, "uretim", 2309.8),
        R("Adana", "Turunç", 2025, "alan", 100.0),
        R("Adana", "Turunç", 2025, "verim_agac", 57.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["turunc"]["yield_kg_da"]["Adana"] == [None, 23098.0]


def _spread(crop, densities, tons=100.0, per_tree=25.0, first=0):
    """One cell per province, each at a chosen implied density.

    A UNIFORM fixture cannot test a crop-level rule: if every cell is above the
    ceiling the per-cell gate already removes them all and the crop rule is
    invisible. So the densities are spread, and the cases below check the cells
    that survive the CELL gate.
    """
    from src.context.location import PROVINCES
    trees = tons * 1000.0 / per_tree
    out = []
    for province, per_da in zip(list(PROVINCES)[first:], densities):
        out += [R(province, crop, 2025, "uretim", tons),
                R(province, crop, 2025, "alan", trees / per_da),
                R(province, crop, 2025, "verim_agac", per_tree)]
    return out


# Median 650, and FOUR cells sit under the 444 cell gate, so they survive it and
# only a crop-level rule can reach them.
_MEDIAN_ABOVE = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200]


def _provinces_served(out, crop_id):
    return [k for k in out["crops"][crop_id]["yield_kg_da"]
            if k not in ("scope", bcn.NATIONAL)]


def test_the_cell_gate_alone_leaves_the_sound_looking_cells_standing():
    """Pins WHY the crop-level rule is needed: four of these twelve cells clear
    the 444 cell gate untouched, and they are cells of a crop whose median
    province cannot hold its trees."""
    out = bcn.build(_spread("Kızılcık", [100, 200, 300, 400]))
    assert len(_provinces_served(out, "kizilcik")) == 4


def _years(crop, province, densities, tons=100.0, per_tree=25.0, start=2016):
    """One cell per year for ONE province, each at a chosen implied density."""
    trees = tons * 1000.0 / per_tree
    out = []
    for i, per_da in enumerate(densities):
        out += [R(province, crop, start + i, "uretim", tons),
                R(province, crop, start + i, "alan", trees / per_da),
                R(province, crop, start + i, "verim_agac", per_tree)]
    return out


def test_a_province_whose_median_year_cannot_hold_its_trees_is_refused():
    """THE MIDDLE GRANULARITY: cell, then PROVINCE, then crop - same geometric
    bound at each, no new constant.

    The last year here sits at 100 trees/da, so the cell gate passes it, and the
    ceiling shadow cannot reach it either because the refusals are all EARLIER
    and the shadow only falls backwards. Yet this province's median year implies
    0,7 m2 of ground per tree: its `Toplu Meyveliklerin Alani` is not recording
    where the fruit came from, and the one year that looks sound is the same
    bookkeeping on a better day.

    Measured: 165 of 1.917 (crop, province) pairs qualify; because the cell gate
    and the shadow already take most of them, this removes 14 SERVED cells -
    Erik/Tunceli at 0,8 m2 per tree, Incir/Karaman at 0,4, Ayva/Hatay at 0,9.
    """
    out = bcn.build(_years("Ayva", "Karabük", [1500, 1400, 1450, 100]))
    assert _provinces_served(out, "ayva") == []


def test_the_province_refusal_is_recorded_once_under_its_own_reason():
    record = bcn.build(_years("Ayva", "Karabük", [1500, 1400, 1450, 100]))         ["meta"]["refused_yield_cells"]
    mine = [c for c in record["cells"]
            if c["reason"] == "province_median_density_above_ceiling"]
    assert mine == [{"crop": "Ayva", "province": "Karabük", "year": 0,
                     "reason": "province_median_density_above_ceiling"}]


def test_a_sound_province_with_one_wild_year_keeps_the_rest():
    """THE MISTAKE THIS RULE MUST NOT MAKE. The median is used precisely so one
    bad year costs that year and never the province.

    The wild year is FIRST on purpose: put it in the middle and the ceiling
    shadow - which refuses everything EARLIER than a ceiling refusal - would
    blank the sound years ahead of it and the province rule would look
    innocent. This orders the fixture so only the rule under test can act."""
    out = bcn.build(_years("Ayva", "Tokat", [5000, 80, 79, 81]))
    assert out["crops"]["ayva"]["yield_kg_da"]["Tokat"] == [None, 2000.0,
                                                            1975.0, 2025.0]


def test_a_province_recorded_in_too_few_years_is_not_judged_as_a_province():
    """A median over one or two years describes those years, not how the
    province keeps its books. Those cells are left to the cell gate, which is
    what already judges them."""
    out = bcn.build(_years("Ayva", "Karabük", [1500, 100]))
    reasons = {c["reason"] for c in
               out["meta"]["refused_yield_cells"]["cells"]}
    assert "province_median_density_above_ceiling" not in reasons
    assert out["crops"]["ayva"]["yield_kg_da"]["Karabük"] == [None, 2500.0]


def test_a_published_yield_survives_the_province_gate():
    """Only the DERIVED half goes - the same line every rule in this file holds."""
    rows = _years("Ayva", "Karabük", [1500, 1400, 1450, 100])
    rows += [R("Karabük", "Ayva", 2019, "verim", 1200.0)]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_da"]["Karabük"] == [None, None,
                                                              None, 1200.0]


def test_a_crop_whose_median_province_cannot_hold_its_trees_yields_nothing():
    """THE CEILING ONE LEVEL UP. The per-cell gate asks whether THIS province's
    area can hold its trees. When the MEDIAN province cannot, the answer is not
    about a province at all - the crop's `Toplu Meyveliklerin Alani` does not
    describe how it is grown anywhere, and the cells that happen to fall under
    the bound are not sounder than the rest.

    Measured on the real exports: kizilcik's median province implies 837
    trees/da (1,2 m2 per tree) and igde's 727 (1,4 m2) - both past the same
    geometric bound `_MAX_TREES_PER_DA` already rests on. Their served yields
    read 12.312 and 11.571 kg/da, which no cornelian cherry or oleaster
    produces. This adds NO new constant: it is the 444 argument applied to the
    crop instead of the cell.
    """
    out = bcn.build(_spread("Kızılcık", _MEDIAN_ABOVE))
    assert _provinces_served(out, "kizilcik") == []


def test_a_crop_refused_whole_still_keeps_its_prices():
    """The same split the reviewed `not_field_area` crops get: a price is a
    price even where the area column is meaningless."""
    rows = _spread("Kızılcık", _MEDIAN_ABOVE)
    rows += [R("Adana", "Kızılcık", 2025, "fiyat", 31.5)]
    out = bcn.build(rows)
    assert out["crops"]["kizilcik"]["price_tl_kg"]["Adana"] == [31.5]


def test_the_whole_crop_refusal_is_recorded_once_not_per_cell():
    record = bcn.build(_spread("Kızılcık", _MEDIAN_ABOVE))["meta"]["refused_yield_cells"]
    assert record["counts"]["crop_median_density_above_ceiling"] == 1
    assert {"crop": "Kızılcık", "province": "*", "year": 0,
            "reason": "crop_median_density_above_ceiling"} in record["cells"]


def test_a_crop_recorded_in_too_few_provinces_is_not_judged_as_a_crop():
    """A median over one or two provincial administrations describes THEM, not
    the crop, so it cannot carry a statement about how the crop is recorded
    nationally. Turunç is the real case that sits just outside: median 2.480
    trees/da but only 2 provinces record it, and its bad cells are already
    removed by the per-cell gate and the ceiling shadow.

    The cut is insensitive rather than tuned - the above-ceiling crops rest on
    29, 18 and 2 provinces, so every minimum from 3 to 18 selects the same two.
    """
    out = bcn.build(_spread("Turunç", [300, 5000]))
    reasons = {c["reason"]
               for c in out["meta"]["refused_yield_cells"]["cells"]}
    assert "crop_median_density_above_ceiling" not in reasons
    # the sound-looking cell is left to the cell gate, which keeps it
    assert _provinces_served(out, "turunc") == [list(__import__(
        "src.context.location", fromlist=["PROVINCES"]).PROVINCES)[0]]


def test_a_sound_crop_with_a_few_bad_provinces_survives_whole():
    """THE MISTAKE THIS RULE MUST NOT MAKE. Apple is recorded properly nearly
    everywhere; a handful of scattered-tree provinces must cost those cells,
    never the crop. The median is used precisely because it does not move when
    a few cells are wild."""
    rows = _spread("Elma (Golden)", [30, 32, 34, 36, 38, 40, 42, 44, 46, 48])
    rows += _spread("Elma (Golden)", [3000, 4000], first=10)
    out = bcn.build(rows)
    assert len(_provinces_served(out, "elma (golden)")) == 10


def test_a_published_per_tree_yield_is_written_as_its_own_measure():
    """TUIK publishes Kg/Meyve Veren Agac for 61 tree crops and no per-dekar
    yield at all. The builder has been reading it as the density gate's
    evidence and throwing it away; it is a norm in its own right."""
    rows = [
        R("Ordu", "Ayva", 2024, "verim_agac", 27.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_tree"]["Ordu"] == [27.0, 31.0]


def test_a_crop_with_no_per_tree_figure_carries_no_such_measure():
    """A field crop must not gain an empty measure. src/norms.py validates
    this key only when present, and an empty one would be noise in every
    diff of the file."""
    rows = [
        R("Ordu", "Durum Buğdayı", 2024, "verim", 369.0),
        R("Ordu", "Durum Buğdayı", 2025, "verim", 322.0),
    ]
    out = bcn.build(rows)
    assert "yield_kg_tree" not in out["crops"]["durum bugdayi"]


def test_a_per_tree_zero_is_refused_like_every_other_measure():
    """A zero is not a norm. The exports carry zeros with no way to tell a
    true one from a missing marker."""
    rows = [
        R("Ordu", "Ayva", 2024, "verim_agac", 0.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_tree"]["Ordu"] == [None, 31.0]


def test_no_density_rule_touches_the_per_tree_series():
    """THE POINT OF THE WHOLE CHANGE. Every gate in this file defends a
    denominator the script chose; a published figure has none. Ordu here is
    refused above the ceiling for its DERIVED cell and still publishes its
    per-tree figure in full."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert "Ordu" not in out["crops"]["ayva"]["yield_kg_da"]
    assert out["crops"]["ayva"]["yield_kg_tree"]["Ordu"] == [31.0]


def test_a_reviewed_crop_still_publishes_its_per_tree_yield():
    """Dut is reviewed out of the DERIVED yield because its area column does
    not count the trees its production does. Its per-tree figure uses no area
    at all, so the review has no reason to reach it - the review restores
    mulberry rather than removing it."""
    rows = _spread("Dut", [100, 100, 100]) + [
        R("Adana", "Dut", 2025, "verim_agac", 24.0)]
    out = bcn.build(rows, area_excludes_the_trees=["Dut"])
    assert _provinces_served(out, "dut") == []
    assert out["crops"]["dut"]["yield_kg_tree"]["Adana"] == [24.0]


def test_the_per_tree_measure_carries_a_national_row_and_a_scope():
    """src/norms.py validates both. The national row ships EMPTY: the exports
    are province-level, so a mean of the provinces is a number nobody
    published."""
    rows = [R("Ordu", "Ayva", 2025, "verim_agac", 31.0)]
    measure = bcn.build(rows)["crops"]["ayva"]["yield_kg_tree"]
    assert measure["scope"] == "il"
    assert measure[bcn.NATIONAL] == [None]


def test_a_vegetable_is_never_gated():
    """THE MOST DANGEROUS MISTAKE THIS GATE CAN MAKE. Vegetables publish no
    per-tree yield anywhere, and their denominator - Ekilen Alan - really is the
    whole crop's sown area. A gate that judged them would find no evidence and
    delete every vegetable yield in the file. 300 tons over 1 dekar is a strange
    tomato figure, and it still ships, because nothing here can judge it."""
    rows = [
        R("Manisa", "Domates", 2025, "uretim", 300.0),
        R("Manisa", "Domates", 2025, "alan", 1.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["domates"]["yield_kg_da"]["Manisa"] == [300000.0]


def test_a_published_per_dekar_yield_is_never_gated():
    """A published figure beats a derived one, so the gate never runs on it -
    even for a crop that also publishes a per-tree figure."""
    rows = [
        R("Ordu", "Ayva", 2025, "verim", 1200.0),
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_da"]["Ordu"] == [1200.0]


def test_the_province_order_does_not_depend_on_the_hash_seed():
    """MEASURED 2026-08-25, and it predates this branch: build() iterates a SET
    of provinces, so the key order inside every crop changes from run to run
    (PYTHONHASHSEED=1 gives Tokat, Karabük, Düzce…; =7 gives Bolu, Mersin,
    Sinop…). The committed file is supposed to be a reproducible output of the
    committed builder; with a shuffling key order every regeneration is a
    whole-file diff, and the one thing a reader needs to see - which cells this
    gate removed - is buried in it."""
    rows = [
        R("Tokat", "Domates", 2025, "uretim", 300.0),
        R("Tokat", "Domates", 2025, "alan", 100.0),
        R("Adana", "Domates", 2025, "uretim", 300.0),
        R("Adana", "Domates", 2025, "alan", 100.0),
        R("Bolu", "Domates", 2025, "uretim", 300.0),
        R("Bolu", "Domates", 2025, "alan", 100.0),
    ]
    keys = [k for k in bcn.build(rows)["crops"]["domates"]["yield_kg_da"]
            if k not in ("scope", "TR")]
    assert keys == ["Adana", "Bolu", "Tokat"]


def test_the_verdict_names_which_bound_was_crossed():
    """The report has to say WHY, and the three reasons are not interchangeable:
    two are impossible figures, one is an unjudgeable one."""
    assert bcn._density_verdict(267.0, 3.0, 31.0) == "density_above_ceiling"
    assert bcn._density_verdict(6.0, 766.0, 27.0) == "density_below_floor"
    assert bcn._density_verdict(267.0, 3.0, None) == "no_per_tree_figure"
    assert bcn._density_verdict(182.0, 155.0, 31.0) is None


def test_a_reviewed_crop_gets_no_yield_at_all():
    """Mushroom's `ekilen alan` is a building's footprint and its beds are
    stacked in tiers, so production over area is not a yield in any unit. No
    published number says so - a person did."""
    rows = [
        R("Ordu", "Mantar (Kültür)", 2025, "uretim", 179.0),
        R("Ordu", "Mantar (Kültür)", 2025, "alan", 1.0),
    ]
    out = bcn.build(rows, not_field_area=["Mantar (Kültür)"])
    assert "Ordu" not in out["crops"]["mantar (kultur)"]["yield_kg_da"]


def test_a_reviewed_crop_keeps_its_price():
    """A mushroom price is a price. Only the area-based figure is unusable."""
    rows = [
        R("Ordu", "Mantar (Kültür)", 2025, "uretim", 179.0),
        R("Ordu", "Mantar (Kültür)", 2025, "alan", 1.0),
        R("Ordu", "Mantar (Kültür)", 2025, "fiyat", 132.18),
    ]
    out = bcn.build(rows, not_field_area=["Mantar (Kültür)"])
    assert out["crops"]["mantar (kultur)"]["price_tl_kg"]["Ordu"] == [132.18]


def test_a_crop_whose_area_excludes_its_trees_yields_nothing():
    """THE SECOND REVIEWED CATEGORY, AND IT IS NOT THE MUSHROOM ONE. Mushroom's
    area is the WRONG KIND of surface - a building's footprint. Dut's is the
    right kind and INCOMPLETE: `Toplu Meyveliklerin Alani` counts compact
    orchards while `Uretim Miktari` counts fruit from every mulberry in the
    province, roadside and garden trees included.

    The cells here sit at 100 trees/da, under `_MAX_TREES_PER_DA` and under the
    crop-level median test, so neither gate can reach them. Only the review can.
    """
    out = bcn.build(_spread("Dut", [100, 100, 100]),
                    area_excludes_the_trees=["Dut"])
    assert _provinces_served(out, "dut") == []


def test_the_two_reviewed_categories_are_recorded_apart():
    """The refusal record is a committed audit. Filing mulberry under the
    mushroom reason would put a false statement about mulberry into it - the
    same "a statement about one thing filed as a statement about another" that
    the fruit yield gate and P3a were both blocked by."""
    rows = _spread("Dut", [100, 100, 100]) + [
        R("Ordu", "Mantar (Kültür)", 2025, "uretim", 179.0),
        R("Ordu", "Mantar (Kültür)", 2025, "alan", 1.0)]
    record = bcn.build(rows, not_field_area=["Mantar (Kültür)"],
                       area_excludes_the_trees=["Dut"])["meta"]["refused_yield_cells"]
    by_crop = {c["crop"]: c["reason"] for c in record["cells"]
               if c["province"] == "*"}
    assert by_crop == {"Mantar (Kültür)": "area_is_not_field",
                       "Dut": "area_excludes_the_trees"}


def test_a_crop_whose_area_excludes_its_trees_keeps_its_price():
    rows = _spread("Dut", [100, 100, 100]) + [R("Adana", "Dut", 2025, "fiyat", 42.5)]
    out = bcn.build(rows, area_excludes_the_trees=["Dut"])
    assert out["crops"]["dut"]["price_tl_kg"]["Adana"] == [42.5]


def test_a_published_yield_survives_the_second_category():
    """Only the DERIVED half goes. The finding is about a denominator this
    script chose, and a published Kg/Dekar figure does not use one - the same
    line `_ceiling_shadow` and `_area_never_orchard` already hold."""
    rows = _spread("Dut", [100, 100]) + [R("Bursa", "Dut", 2025, "verim", 640.0)]
    out = bcn.build(rows, area_excludes_the_trees=["Dut"])
    assert out["crops"]["dut"]["yield_kg_da"]["Bursa"] == [640.0]


def test_a_stale_entry_in_the_second_category_stops_the_build():
    """Both reviewed lists carry the same promise: a review of a crop the
    exports no longer carry is a review of nothing."""
    rows = [R("Ordu", "Ayva", 2025, "verim", 1200.0)]
    with pytest.raises(ValueError, match="Dut"):
        bcn.build(rows, area_excludes_the_trees=["Dut"])


def test_a_stale_review_entry_stops_the_build():
    """A review of a crop that is no longer in the exports is a review of
    nothing, sitting in the file looking like coverage."""
    rows = [R("Ordu", "Ayva", 2025, "verim", 1200.0)]
    with pytest.raises(ValueError, match="Mantar"):
        bcn.build(rows, not_field_area=["Mantar (Kültür)"])


def test_no_review_means_no_exclusions():
    """The default must be inert: an omitted argument may not silently gate."""
    rows = [
        R("Ordu", "Mantar (Kültür)", 2025, "uretim", 179.0),
        R("Ordu", "Mantar (Kültür)", 2025, "alan", 1.0),
    ]
    assert bcn.build(rows)["crops"]["mantar (kultur)"]["yield_kg_da"]["Ordu"] == [179000.0]


def test_a_refusal_is_recorded_in_the_file_with_its_reason():
    """The finding travels WITH the data: without this there is no committed
    way to tell "this province grows no quince" from "we threw its figure out"."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert record["counts"] == {"density_above_ceiling": 1}
    assert record["cells"] == [{"crop": "Ayva", "province": "Ordu",
                                "year": 2025, "reason": "density_above_ceiling"}]


def test_the_refusal_record_is_empty_when_nothing_was_refused():
    record = bcn.build(_rows())["meta"]["refused_yield_cells"]
    assert record == {"counts": {}, "cells": []}


def test_refusals_are_sorted_so_the_committed_file_is_stable():
    """The file must be a reproducible output of the builder; a set-ordered list
    would diff differently on every run for no reason."""
    rows = [
        R("Tokat", "Erik", 2025, "uretim", 500.0),
        R("Tokat", "Erik", 2025, "alan", 1.0),
        R("Tokat", "Erik", 2025, "verim_agac", 16.0),
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    cells = bcn.build(rows)["meta"]["refused_yield_cells"]["cells"]
    assert [c["crop"] for c in cells] == ["Ayva", "Erik"]


def test_the_build_names_every_refusal_on_the_console(capsys):
    """It runs by hand once a year; its job is to fail loudly."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    bcn.build(rows)
    printed = capsys.readouterr()
    assert "Ayva" in printed.err and "Ordu" in printed.err


def test_the_shipped_file_is_what_the_builder_produces():
    """Proves the data file was generated, not hand-edited."""
    import json as _json
    from src.config import DATA_DIR
    rows = []
    for path in sorted((DATA_DIR / "raw").glob("*.csv")):
        rows.extend(bcn.read_export(path))
    review = _json.loads((DATA_DIR / "crop_area_review.json").read_text(encoding="utf-8"))
    rebuilt = bcn.build(rows, not_field_area=review["not_field_area"],
                        area_excludes_the_trees=review["area_excludes_the_trees"])
    shipped = _json.loads((DATA_DIR / "crop_norms.json").read_text(encoding="utf-8"))
    assert rebuilt["crops"] == shipped["crops"]
    assert rebuilt["meta"]["refused_yield_cells"] == shipped["meta"]["refused_yield_cells"]


def test_the_shipped_file_still_carries_most_of_its_yields():
    """A guard on the real data: if the gate ever starts refusing everything,
    every fixture test above keeps passing while the feature quietly empties."""
    import json as _json
    from src.config import DATA_DIR
    shipped = _json.loads((DATA_DIR / "crop_norms.json").read_text(encoding="utf-8"))
    cells = sum(1 for crop in shipped["crops"].values()
                for province, series in crop["yield_kg_da"].items()
                if province not in ("scope", "TR")
                for v in series if v is not None)
    assert cells >= 45000, cells
    # 45.000 is a deliberate floor, not the measured count. Measured 67.535
    # cells when this test was written; the floor sits at roughly two thirds
    # of that: an order-of-magnitude collapse trips it, normal year-to-year
    # drift in the TÜİK exports does not.


def test_the_shipped_file_carries_no_cell_the_gate_should_have_refused():
    """The file stores a yield, not a density, so this check runs the density
    test again over the committed exports rather than reading the file alone."""
    import json as _json
    from src.config import DATA_DIR
    rows = []
    for path in sorted((DATA_DIR / "raw").glob("*.csv")):
        rows.extend(bcn.read_export(path))
    per_tree, uretim, alan = {}, {}, {}
    for r in rows:
        key = (bcn._normalize_tr(r.crop), r.province, r.year)
        if r.measure == "verim_agac":
            per_tree[key] = r.value
        elif r.measure == "uretim":
            uretim[key] = r.value
        elif r.measure == "alan":
            alan[key] = r.value
    shipped = _json.loads((DATA_DIR / "crop_norms.json").read_text(encoding="utf-8"))
    years = shipped["meta"]["years"]
    bad = []
    for crop_id, crop in shipped["crops"].items():
        for province, series in crop["yield_kg_da"].items():
            if province in ("scope", "TR"):
                continue
            for i, value in enumerate(series):
                if value is None:
                    continue
                key = (crop_id, province, years[i])
                if key not in per_tree or key not in uretim or key not in alan:
                    continue
                if bcn._density_verdict(uretim[key], alan[key], per_tree[key]):
                    bad.append(key)
    assert bad == [], bad[:5]


def test_the_shipped_file_refused_the_cells_the_spec_names():
    """The three worked examples from the design doc, on the real data."""
    import json as _json
    from src.config import DATA_DIR
    shipped = _json.loads((DATA_DIR / "crop_norms.json").read_text(encoding="utf-8"))
    refused = {(c["crop"], c["province"]) for c in
               shipped["meta"]["refused_yield_cells"]["cells"]}
    assert ("Ayva", "Ordu") in refused
    assert ("Turunç", "Adana") in refused
    assert ("Mantar (Kültür)", "*") in refused
    assert ("Ayva", "Tokat") not in refused


def test_a_published_yield_of_zero_is_refused_and_recorded():
    """TUIK publishes a Verim of exactly 0 in 268 cells. It has always been
    refused - prefilling 0 would tell a farmer to expect no harvest and compute
    an income of zero - but the refusal left no trace, so the committed file
    could not tell it from a province that grows none of the crop."""
    rows = [
        R("Ordu", "Bakla, Kuru (İnsan Tüketimi İçin)", 2016, "verim", 0.0),
        R("Ordu", "Bakla, Kuru (İnsan Tüketimi İçin)", 2017, "verim", 145.0),
    ]
    out = bcn.build(rows)
    record = out["meta"]["refused_yield_cells"]
    assert {"crop": "Bakla, Kuru (İnsan Tüketimi İçin)", "province": "Ordu",
            "year": 2016,
            "reason": "published_yield_is_zero"} in record["cells"]
    assert out["crops"]["bakla, kuru (insan tuketimi icin)"] \
              ["yield_kg_da"]["Ordu"] == [None, 145.0]


def test_a_zero_production_against_a_recorded_area_is_refused_and_recorded():
    """Two dekars sown, nothing off them: the derived yield is 0,0 and has
    always been dropped. A TREE crop's zero production is already caught one
    step earlier as `density_below_floor` - 0 trees/dekar is under the floor of
    5 - so this reason reaches only the crops with no per-tree figure to judge
    with, which is where the 36 measured cells sit."""
    rows = [
        R("Sivas", "Marul (Göbekli)", 2025, "uretim", 0.0),
        R("Sivas", "Marul (Göbekli)", 2025, "alan", 2.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert [c["reason"] for c in record["cells"]] == ["production_is_zero"]
