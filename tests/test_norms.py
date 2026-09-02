"""Unit tests for src/norms.py (no network, no store, no model)."""

import json

import pytest

from src import norms


@pytest.fixture(autouse=True)
def _clear_the_norms_cache():
    """`norms._load` is an lru_cache and `_write` below repoints `norms._PATH`
    at a temp file. monkeypatch puts the path back at teardown; it cannot put
    the cache back, so a two-crop fixture table would answer every later test
    in the process - in this file and in any file that runs after it.

    Until this fixture existed the file stayed clean by ACCIDENT: the last
    `_write` test happened to be followed by real-data tests that cleared the
    cache for their own reasons. Reordering the file was enough to break it.
    This fixture clears only AFTER each test, and that side is deliberate
    because it is the side that can be proved: delete the line below and four
    real-data tests go red on a leaked fixture table. The entry side stays
    with `_write`, which has always had it. `tests/test_crop_compare.py`
    clears on both sides.
    """
    yield
    norms._load.cache_clear()


def _write(tmp_path, monkeypatch, payload):
    """Point norms at a temporary file and clear its cache."""
    path = tmp_path / "crop_norms.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    return path


GOOD = {
    "meta": {
        "generated": "2026-08-17",
        "years": [2023, 2024, 2025],
        "sources": {"yield": {"name": "TUIK"}, "price": {"name": "TUIK"}},
    },
    "crops": {
        "domates": {
            "label": "Domates",
            "yield_kg_da": {"scope": "il", "Manisa": [5900, None, 6500],
                            "TR": [5500, 5600, 5700]},
            "price_tl_kg": {"scope": "tr", "TR": [6.05, 9.40, 12.40]},
        }
    },
}


def test_a_valid_file_loads(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    data = norms._load()
    assert data["years"] == [2023, 2024, 2025]
    assert "domates" in data["crops"]


TREE = {
    "meta": {
        "generated": "2026-08-28",
        "years": [2023, 2024, 2025],
        "sources": {"yield": {"name": "TUIK"}, "price": {"name": "TUIK"}},
    },
    "crops": {
        "bugday": {
            "label": "Buğday",
            "yield_kg_da": {"scope": "il", "Ordu": [369, 344, 322],
                            "TR": [None, None, None]},
            "price_tl_kg": {"scope": "tr", "TR": [6.05, 9.40, 12.40]},
        },
        "ayva": {
            "label": "Ayva",
            "yield_kg_da": {"scope": "il", "Ordu": [None, None, None],
                            "TR": [None, None, None]},
            "price_tl_kg": {"scope": "il", "Ordu": [11.0, 14.0, 19.0],
                            "TR": [None, None, None]},
            "yield_kg_tree": {"scope": "il", "Ordu": [25, 27, 31],
                              "TR": [None, None, None]},
        },
    },
}


def test_a_crop_without_a_per_tree_measure_still_loads(tmp_path, monkeypatch):
    """THE TRAP IN THIS DESIGN. _load drops a crop whole unless every name in
    _MEASURES validates. Field crops publish no per-tree yield, so listing
    yield_kg_tree there would make _valid_measure(None) return False for every
    one of them and empty the table - 246 crops gone, silently, with a
    green-looking file on disk.

    Proven by mutation: move "yield_kg_tree" into _MEASURES and this test must
    go red."""
    _write(tmp_path, monkeypatch, TREE)
    data = norms._load()
    assert set(data["crops"]) == {"bugday", "ayva"}


def test_a_per_tree_yield_resolves_with_its_year_and_region(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, TREE)
    row = norms.lookup("ayva", "Ordu")
    assert row.yield_kg_tree.amount == 31.0
    assert row.yield_kg_tree.year == 2025
    assert row.yield_kg_tree.scope == "il"
    assert row.yield_kg_tree.region == "Ordu"


def test_a_crop_with_no_per_tree_measure_resolves_it_to_none(tmp_path, monkeypatch):
    """Absence is absence - the module's binding rule, on the new measure."""
    _write(tmp_path, monkeypatch, TREE)
    assert norms.lookup("bugday", "Ordu").yield_kg_tree is None


def test_a_malformed_per_tree_measure_drops_the_crop_whole(tmp_path, monkeypatch):
    """The same rule the required measures get: a crop carrying one good
    measure and one malformed one would prefill a field and leave another
    blank with no explanation."""
    payload = json.loads(json.dumps(TREE))
    payload["crops"]["ayva"]["yield_kg_tree"]["Ordu"] = [25, 27]   # short series
    _write(tmp_path, monkeypatch, payload)
    assert set(norms._load()["crops"]) == {"bugday"}


def test_the_per_tree_measure_carries_its_own_five_year_range(tmp_path, monkeypatch):
    """_pick's range logic is measure-agnostic and must stay that way."""
    _write(tmp_path, monkeypatch, TREE)
    value = norms.lookup("ayva", "Ordu").yield_kg_tree
    assert value.recent_min == 25.0 and value.recent_max == 27.0


def test_a_missing_file_is_an_empty_table(tmp_path, monkeypatch):
    """A broken data file must never break answering - fertplan._load's rule."""
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms._load() == {}


def test_malformed_json_is_an_empty_table(tmp_path, monkeypatch):
    path = tmp_path / "crop_norms.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    assert norms._load() == {}


def test_a_top_level_list_is_an_empty_table(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [1, 2, 3])
    assert norms._load() == {}


def test_missing_years_is_an_empty_table(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    del payload["meta"]["years"]
    _write(tmp_path, monkeypatch, payload)
    assert norms._load() == {}


def test_a_series_of_the_wrong_length_drops_its_crop(tmp_path, monkeypatch):
    """The year axis is shared, so a mismatched series has no meaning - every
    value in it would be attributed to the wrong year."""
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["yield_kg_da"]["Manisa"] = [1, 2]
    _write(tmp_path, monkeypatch, payload)
    assert norms._load().get("crops", {}) == {}


def test_a_measure_without_a_national_row_drops_its_crop(tmp_path, monkeypatch):
    """TR is the fallback row; without it a province miss has nowhere to go."""
    payload = json.loads(json.dumps(GOOD))
    del payload["crops"]["domates"]["price_tl_kg"]["TR"]
    _write(tmp_path, monkeypatch, payload)
    assert norms._load().get("crops", {}) == {}


def test_an_unknown_scope_drops_its_crop(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["yield_kg_da"]["scope"] = "ilce"
    _write(tmp_path, monkeypatch, payload)
    assert norms._load().get("crops", {}) == {}


def test_a_bad_crop_does_not_take_the_good_ones_with_it(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["bugday"] = {"label": "Buğday", "yield_kg_da": "nonsense"}
    _write(tmp_path, monkeypatch, payload)
    assert list(norms._load()["crops"]) == ["domates"]


def test_a_non_finite_value_drops_its_crop(tmp_path, monkeypatch):
    """json.loads accepts NaN/Infinity by default; non-finite values should be rejected."""
    # Test NaN
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["yield_kg_da"]["TR"][0] = float("nan")
    _write(tmp_path, monkeypatch, payload)
    assert norms._load().get("crops", {}) == {}

    # Test infinity
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["yield_kg_da"]["TR"][0] = float("inf")
    _write(tmp_path, monkeypatch, payload)
    assert norms._load().get("crops", {}) == {}


def test_available_crops_returns_id_label_pairs(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["armut"] = {
        "label": "Armut",
        "yield_kg_da": {"scope": "tr", "TR": [1, 2, 3]},
        "price_tl_kg": {"scope": "tr", "TR": [4, 5, 6]},
    }
    _write(tmp_path, monkeypatch, payload)
    assert norms.available_crops() == (("armut", "Armut"), ("domates", "Domates"))


def test_available_crops_is_empty_without_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms.available_crops() == ()


def test_latest_year_is_the_last_year_of_the_axis(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert norms.latest_year() == 2025


def test_latest_year_is_none_for_an_empty_table(tmp_path, monkeypatch):
    """Not derived from any crop's cells - src/budget.py uses this as the
    dataset's own cutoff to decide whether a price is fresh enough to prefill,
    and an unreadable file must not silently look like a fresh one."""
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms.latest_year() is None


def test_a_province_row_is_used_and_reported_as_provincial(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    n = norms.lookup("domates", "Manisa")
    assert n.yield_kg_da.amount == 6500.0
    assert n.yield_kg_da.year == 2025
    assert n.yield_kg_da.scope == "il"
    assert n.yield_kg_da.region == "Manisa"


def test_a_province_without_a_row_falls_back_to_the_nation(tmp_path, monkeypatch):
    """And says so - the user must be able to read which one they got."""
    _write(tmp_path, monkeypatch, GOOD)
    n = norms.lookup("domates", "Rize")
    assert n.yield_kg_da.amount == 5700.0
    assert n.yield_kg_da.scope == "tr"
    assert n.yield_kg_da.region == "Türkiye"


def test_no_province_at_all_falls_back_to_the_nation(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    n = norms.lookup("domates", None)
    assert n.yield_kg_da.scope == "tr"


def test_a_national_scope_measure_ignores_the_province(tmp_path, monkeypatch):
    """price_tl_kg has scope 'tr': naming a province must not invent a
    provincial reading of a national figure."""
    _write(tmp_path, monkeypatch, GOOD)
    n = norms.lookup("domates", "Manisa")
    assert n.price_tl_kg.amount == 12.40
    assert n.price_tl_kg.scope == "tr"
    assert n.price_tl_kg.region == "Türkiye"


def test_a_null_latest_year_walks_back_and_carries_that_year(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["yield_kg_da"]["Manisa"] = [5900, 6300, None]
    _write(tmp_path, monkeypatch, payload)
    n = norms.lookup("domates", "Manisa")
    assert n.yield_kg_da.amount == 6300.0
    assert n.yield_kg_da.year == 2024


def test_an_all_null_series_yields_no_norm_rather_than_zero(tmp_path, monkeypatch):
    """The binding rule: a zero would flow into the budget arithmetic and come
    out as a confident wrong answer."""
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["price_tl_kg"]["TR"] = [None, None, None]
    _write(tmp_path, monkeypatch, payload)
    n = norms.lookup("domates", "Manisa")
    assert n.price_tl_kg is None
    assert n.yield_kg_da is not None


def test_an_unknown_crop_has_no_norm(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert norms.lookup("kivi", "Manisa") is None


def test_lookup_without_a_file_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms.lookup("domates", "Manisa") is None


def test_the_crop_label_is_carried(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert norms.lookup("domates", "Manisa").label == "Domates"


def test_the_shipped_file_uses_canonical_province_names():
    """A misspelled province does not raise - it silently never matches, so this
    test is the only thing that can see it. TUIK writes "Hakkari" where
    location.py writes "Hakkâri"; the converter renames it."""
    from src.context.location import PROVINCES
    data = norms._load()
    assert data, "data/crop_norms.json did not load - the shipped file is broken"
    allowed = set(PROVINCES) | {norms.NATIONAL_KEY}
    unknown = set()
    for crop in data["crops"].values():
        for measure in ("yield_kg_da", "price_tl_kg"):
            unknown |= {k for k in crop[measure] if k != "scope"} - allowed
    assert unknown == set(), f"unknown province keys: {sorted(unknown)}"


def test_the_shipped_file_carries_crops_and_a_decade():
    assert len(norms.available_crops()) > 100
    assert len(norms._load()["years"]) == 10


def test_a_shipped_yield_is_in_a_plausible_range():
    """Guards the unit. Reading the export as Turkish-formatted would have made
    every figure ten times too big; a wheat yield of 2840 kg/da would be absurd
    and this is what would catch it."""
    wheat = norms.lookup("durum bugdayi", "Konya")
    assert wheat is not None and wheat.yield_kg_da is not None
    assert 50 < wheat.yield_kg_da.amount < 1000


def test_norms_does_not_import_the_engine():
    """A data lookup has no business dragging the engine in - src/context/location
    imports engine._normalize_tr, so importing it here would pull the whole chat
    stack into a module that only reads a JSON file. Pinned because nothing else
    would notice the day someone adds the import."""
    import ast
    import pathlib
    tree = ast.parse(pathlib.Path("src/norms.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any("engine" in m or "location" in m for m in imported), imported


ALTERNATE = {
    "meta": {"generated": "2026-08-22", "years": [2020, 2021, 2022, 2023, 2024, 2025]},
    "crops": {
        "findik": {
            "label": "Fındık",
            # The prefilled year (28.4) is atypical; the five before it are not.
            "yield_kg_da": {"scope": "il",
                            "Ordu": [86.8, 73.7, 105.6, 87.5, 88.9, 28.4],
                            "TR": [None, None, None, None, None, None]},
            "price_tl_kg": {"scope": "il",
                            "Ordu": [None, None, None, None, None, 202.26],
                            "TR": [None, None, None, None, None, None]},
        }
    },
}


def test_the_recent_range_excludes_the_prefilled_year(tmp_path, monkeypatch):
    """Including it would make the prefill its own lower bound, which says
    nothing about whether the prefill is typical."""
    _write(tmp_path, monkeypatch, ALTERNATE)
    norm = norms.lookup("findik", "Ordu").yield_kg_da
    assert norm.amount == 28.4
    assert (norm.recent_min, norm.recent_max) == (73.7, 105.6)


def test_a_single_prior_value_yields_no_range(tmp_path, monkeypatch):
    """One number is not a range, and rendering '202,26-202,26' would dress a
    single observation as a spread."""
    _write(tmp_path, monkeypatch, ALTERNATE)
    norm = norms.lookup("findik", "Ordu").price_tl_kg
    assert norm.amount == 202.26
    assert (norm.recent_min, norm.recent_max) == (None, None)


def test_two_equal_prior_values_also_yield_no_range(tmp_path, monkeypatch):
    """Two IDENTICAL values are not a spread either - '63-63 kg/da' would dress
    a single observed level as a range just as much as one bare value would."""
    payload = {
        "meta": {"years": [2021, 2022, 2023, 2024, 2025]},
        "crops": {"x": {
            "label": "X",
            "yield_kg_da": {"scope": "il", "TR": [63.0, 63.0, None, None, 90.0]},
            "price_tl_kg": {"scope": "il", "TR": [1.0, 1.0, 1.0, 1.0, 1.0]},
        }},
    }
    _write(tmp_path, monkeypatch, payload)
    norm = norms.lookup("x", None).yield_kg_da
    assert norm.amount == 90.0
    assert (norm.recent_min, norm.recent_max) == (None, None)


def test_the_range_window_is_the_five_years_before_the_hit(tmp_path, monkeypatch):
    """Not the last five of the series: when the walk-back skips null years the
    window moves with it."""
    payload = {
        "meta": {"years": [2019, 2020, 2021, 2022, 2023, 2024, 2025]},
        "crops": {"x": {
            "label": "X",
            # Latest non-null is 2022; the window is 2019-2021, and 2023-2025
            # must not leak into it.
            "yield_kg_da": {"scope": "il", "TR": [10.0, 20.0, 30.0, 44.0, None, None, None]},
            "price_tl_kg": {"scope": "il", "TR": [1.0, 1.0, 1.0, 1.0, None, None, None]},
        }},
    }
    _write(tmp_path, monkeypatch, payload)
    norm = norms.lookup("x", None).yield_kg_da
    assert norm.year == 2022 and norm.amount == 44.0
    assert (norm.recent_min, norm.recent_max) == (10.0, 30.0)


def test_a_range_never_replaces_the_prefill(tmp_path, monkeypatch):
    """The published figure is what prefills, however atypical it is."""
    _write(tmp_path, monkeypatch, ALTERNATE)
    norm = norms.lookup("findik", "Ordu").yield_kg_da
    assert norm.amount == 28.4
    assert norm.amount < norm.recent_min


def test_the_province_table_matches_calling_lookup_for_every_crop(tmp_path, monkeypatch):
    """One pass, same answers. If these ever diverge, the form and the
    verification on submit would disagree about what the norm is."""
    payload = {
        "meta": {"years": [2024, 2025]},
        "crops": {
            "domates": {
                "label": "Domates",
                "yield_kg_da": {"scope": "il", "Manisa": [1.0, 2.0], "TR": [1.0, 2.0]},
                "price_tl_kg": {"scope": "tr", "TR": [1.0, 2.0]},
            },
            "misir": {
                "label": "Mısır",
                "yield_kg_da": {"scope": "il", "Manisa": [3.0, 4.0], "TR": [3.0, 4.0]},
                "price_tl_kg": {"scope": "tr", "TR": [3.0, 4.0]},
            },
        },
    }
    _write(tmp_path, monkeypatch, payload)
    table = norms.province_table("Manisa")
    one_by_one = tuple(norms.lookup(cid, "Manisa")
                       for cid, _ in norms.available_crops())
    assert table == one_by_one


def test_the_province_table_is_sorted_by_label(tmp_path, monkeypatch):
    payload = {
        "meta": {"years": [2024, 2025]},
        "crops": {
            "zeytin": {"label": "Zeytin",
                       "yield_kg_da": {"scope": "il", "TR": [1.0, 2.0]},
                       "price_tl_kg": {"scope": "il", "TR": [1.0, 2.0]}},
            "arpa": {"label": "Arpa",
                     "yield_kg_da": {"scope": "il", "TR": [1.0, 2.0]},
                     "price_tl_kg": {"scope": "il", "TR": [1.0, 2.0]}},
        },
    }
    _write(tmp_path, monkeypatch, payload)
    assert [r.label for r in norms.province_table(None)] == ["Arpa", "Zeytin"]


def test_a_broken_file_gives_an_empty_table_not_an_exception(tmp_path, monkeypatch):
    """A broken data file must not break answering - fertplan._load's rule."""
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms.province_table("Manisa") == ()


def test_a_national_scope_measure_reports_itself_as_national(tmp_path, monkeypatch):
    """Pinned against a synthetic fixture on purpose: the shipped file carries no
    populated TR rows today, so testing this against real data would assert
    nothing. The path must stay covered for the day those rows land."""
    payload = {
        "meta": {"years": [2024, 2025]},
        "crops": {"x": {
            "label": "X",
            "yield_kg_da": {"scope": "tr", "TR": [10.0, 11.0]},
            "price_tl_kg": {"scope": "tr", "TR": [1.0, 2.0]},
        }},
    }
    _write(tmp_path, monkeypatch, payload)
    row = norms.province_table("Manisa")[0]
    assert row.yield_kg_da.scope == "tr"
    assert row.yield_kg_da.region == "Türkiye"


def test_the_shipped_file_still_carries_provincial_yields():
    """A guard on the real data, not a fixture. If a converter change or a bad
    refresh empties the file, every prefill silently disappears and every other
    test here keeps passing on its fixtures. Measured on 2026-08-22: Manisa 142,
    Konya 147, Ordu 75, Van 73 of 246 crops. The floor is deliberately far below
    those, so an honest yearly refresh does not trip it."""
    table = norms.province_table("Manisa")
    provincial = [r for r in table
                  if r.yield_kg_da is not None and r.yield_kg_da.scope == "il"]
    assert len(table) > 200
    assert len(provincial) > 100


def test_the_shipped_file_keeps_the_two_tomatoes_apart():
    """There is no single 'domates' norm - TUIK publishes Sofralik and Salcalik
    separately, and they are different crops with different prices. The crop
    list must offer both rather than one of them standing in for the other."""
    labels = [label for _, label in norms.available_crops()]
    assert "Domates (Sofralık)" in labels
    assert "Domates (Salçalık)" in labels
    assert "Domates" not in labels


def test_a_figure_far_below_its_own_five_year_range_is_flagged():
    """Bilecik/Erik 2025: 1 kg/ağaç against a prior 20-37. Production fell from
    2.954 tons to 27 while the recorded orchard area GREW - the trees are there
    and the harvest is not. The most recent published figure is not an
    expectation when there was almost nothing to measure."""
    value = norms.NormValue(1.0, 2025, "il", "Bilecik", 20.0, 37.0)
    assert norms.far_below_recent(value) is True


def test_an_ordinary_figure_is_not_flagged():
    value = norms.NormValue(31.0, 2025, "il", "Karabük", 27.0, 28.0)
    assert norms.far_below_recent(value) is False


def test_a_figure_with_no_range_is_never_flagged():
    """With nothing to compare against there is nothing to warn about. The
    range is the warning's own evidence."""
    assert norms.far_below_recent(
        norms.NormValue(1.0, 2025, "il", "Bilecik")) is False


def test_no_value_is_not_flagged():
    assert norms.far_below_recent(None) is False


def test_the_threshold_is_exercised_from_both_sides():
    """A midpoint of 100: 19 is below one fifth of it, 21 is not. Pins the
    constant itself, so it cannot drift without a test noticing."""
    below = norms.NormValue(19.0, 2025, "il", "Bilecik", 80.0, 120.0)
    above = norms.NormValue(21.0, 2025, "il", "Bilecik", 80.0, 120.0)
    assert norms.far_below_recent(below) is True
    assert norms.far_below_recent(above) is False


def test_a_zero_range_cannot_divide_by_zero():
    """recent_min == recent_max == 0 cannot occur through _recent_range, which
    refuses a range whose ends are equal - but this function is public and must
    not raise on a value someone constructs."""
    assert norms.far_below_recent(
        norms.NormValue(1.0, 2025, "il", "Bilecik", 0.0, 0.0)) is False


def test_a_value_at_its_own_range_minimum_is_never_flagged():
    """K.Maraş/Fındık 2025: 1 kg/ağaç against a prior 1-12 - the served figure
    IS the printed minimum. One fifth of the midpoint (6.5) is 1.3, so the
    magnitude-only rule flags this even though the sentence it produces would
    call the range's own endpoint 'far below' that range. Three rounds of
    mutation testing missed this because every existing fixture keeps its
    spread under about 2x; this one is over 10x, wide enough for one fifth of
    the midpoint to sit above recent_min itself. The fix adds the ordering the
    sentence already asserts: below recent_min, not just below one fifth of
    the midpoint."""
    value = norms.NormValue(1.0, 2025, "il", "Kahramanmaraş", 1.0, 12.0)
    assert norms.far_below_recent(value) is False
