import pytest

from src import norms

TURKIYE, FRANCE = 223, 68
WHEAT = "bugday, durum bugdayi haric"


@pytest.fixture(autouse=True)
def _clear_the_world_caches():
    """`_load_world` and `_load_fao_map` are `@lru_cache`d the same way
    `_load` is, for the same reason: a broken-file test elsewhere in the
    suite must not leave a poisoned `{}` behind for these tests, and these
    tests must not leave real data behind for a test that expects a broken
    file. See `tests/test_norms.py`'s `_clear_the_norms_cache` for the shape
    this copies."""
    yield
    norms._load_world.cache_clear()
    norms._load_fao_map.cache_clear()


def test_a_country_figure_is_served_when_no_province_resolves():
    norm = norms.lookup(WHEAT, None, country=FRANCE)
    assert norm is not None
    assert norm.yield_kg_da is not None
    assert norm.yield_kg_da.scope == "ulke"
    assert norm.yield_kg_da.region == "France"
    assert norm.yield_kg_da.unit == "kg/da"


def test_a_country_price_is_in_dollars_and_says_so():
    norm = norms.lookup(WHEAT, None, country=FRANCE)
    assert norm.price_per_kg is not None
    assert norm.price_per_kg.unit == "USD/kg"


def test_a_province_always_wins_over_a_country():
    """The world layer never overrides TÜİK. A province figure is provincial
    even when a country was also named."""
    norm = norms.lookup(WHEAT, "Konya", country=FRANCE)
    assert norm.yield_kg_da.scope == "il"
    assert norm.yield_kg_da.region == "Konya"
    assert norm.price_per_kg.unit == "TL/kg"


def test_turkiye_as_a_country_never_reaches_the_world_layer():
    """FAOSTAT carries Türkiye (area 223) too, and it is a cross-check rather
    than a source - so naming Türkiye must not fetch it.

    What comes back is a CropNorm with empty measures, not a FAOSTAT figure,
    because `data/crop_norms.json`'s national row is empty BY CONSTRUCTION:
    553 measures carry a "TR" key and not one holds a value.
    `scripts/build_crop_norms.py` ships it that way on purpose - "a mean of the
    provinces is a number nobody published". A Turkish user who has not named
    a province therefore gets nothing and the assistant asks, which is the same
    thing `location.py` already does and yields better data than an average.

    Do not "fix" this by averaging the provinces."""
    norm = norms.lookup(WHEAT, None, country=TURKIYE)
    assert norm is not None
    for measure in (norm.yield_kg_da, norm.price_per_kg, norm.yield_kg_tree):
        assert measure is None or measure.scope != "ulke"


def test_no_country_and_no_province_is_todays_behaviour():
    before = norms.lookup(WHEAT, None)
    after = norms.lookup(WHEAT, None, country=None)
    assert before == after


def test_a_crop_with_no_fao_counterpart_has_no_country_figure():
    """105 of our 246 crop ids map to null with a stated reason. `salep` is
    one; if it has gained a mapping, pick another null entry from
    data/crop_fao_map.json and say which in your report."""
    norm = norms.lookup("salep", None, country=FRANCE)
    assert norm is not None          # the crop exists
    assert norm.yield_kg_da is None  # the world layer has nothing for it


def test_a_country_that_does_not_grow_the_crop_yields_nothing():
    """A real code with no cell for this item. Find one with the command in
    Step 3 and name it in your report."""
    norm = norms.lookup("cay yapraklari", None, country=FRANCE)
    assert norm is None or norm.yield_kg_da is None


def test_an_unknown_crop_is_still_none():
    assert norms.lookup("bu bir urun degil", None, country=FRANCE) is None


def test_the_world_year_is_the_cells_own_year():
    """FAOSTAT ends at 2024 where TÜİK reaches 2025. A world figure must
    never borrow the Turkish file's latest year."""
    norm = norms.lookup(WHEAT, None, country=FRANCE)
    assert norm.yield_kg_da.year <= 2024


EGYPT, RUSSIA = 59, 185


def test_a_country_table_is_every_crop_resolved_for_that_country():
    """The budget card's crop list for a farmer abroad - lookup() for each crop,
    sorted by label, the same contract province_table() keeps for TÜİK, so a
    submitted figure is verified against the very row the card was built from."""
    table = norms.country_table(FRANCE)
    assert len(table) == len(norms.available_crops())
    assert [row.label for row in table] == sorted(row.label for row in table)
    for row in table[:40]:
        assert row == norms.lookup(row.crop, None, country=FRANCE)


def test_turkiye_has_no_country_table():
    """Türkiye is TÜİK's, never FAOSTAT's area 223 - see _resolve."""
    assert norms.country_table(TURKIYE) == ()


@pytest.mark.parametrize("country, year", [(FRANCE, 2024), (EGYPT, 2023), (RUSSIA, 2022)])
def test_a_country_price_year_is_its_own_latest(country, year):
    """Countries report prices on different lags - measured 2026-10-29: France
    2024, Egypt 2023, Russia 2022. One cutoff for all (the dataset's 2024) would
    serve Egypt no price at all; each country's own latest year serves the
    figures it last published, and no older ones mixed in."""
    assert norms.country_price_year(country) == year


def test_a_price_year_far_behind_the_dataset_is_no_year():
    """More than two years behind FAOSTAT's own latest is too old to prefill a
    price from - nominal prices drift - so the card offers none."""
    world = norms._load_world()
    latest = world["meta"]["years"][-1]
    stale = {k: v for k, v in world["price"].items() if not k.endswith(f"|{FRANCE}")}
    stale[f"{next(iter(norms._load_fao_map().values()))['fao']}|{FRANCE}"] = {
        str(latest - 3): [1.0, "A"]}
    norms._load_world.cache_clear()
    import unittest.mock
    with unittest.mock.patch.object(norms, "_load_world", lambda: {**world, "price": stale}):
        assert norms.country_price_year(FRANCE) is None
