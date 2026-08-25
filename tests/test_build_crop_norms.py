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
    silently wrong by more than an order of magnitude. Evidence only."""
    rows = [R("Manisa", "Elma", 2025, "verim_agac", 80.0)]
    out = bcn.build(rows)
    assert out["crops"]["elma"]["yield_kg_da"] == {"scope": "tr", "TR": [None]}


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
