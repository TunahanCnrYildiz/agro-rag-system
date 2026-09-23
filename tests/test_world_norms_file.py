"""Invariants of the committed `data/world_norms.json`, not of the builder.

`tests/test_build_world_norms.py` proves the rules hold on fixtures. Nothing
proved they hold on the 4.8 MB file we actually ship: a regeneration that lost
the group filter would put `Fruit Primary` and `Vegetables Primary` in `items`
as if they were crops, and every other test in the suite would still pass.

The constants come from the builder rather than being restated here, so the
file and the rule that produced it cannot drift apart silently.
"""

import json
from pathlib import Path

import pytest

from scripts import build_world_norms as bwn
from scripts import fetch_faostat as ff

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def world() -> dict:
    return json.loads((DATA / "world_norms.json").read_text(encoding="utf-8"))


def _cells(world: dict):
    for section in ("yield", "price"):
        for key, series in world[section].items():
            for year, value in series.items():
                yield section, key, year, value


def test_every_cell_is_a_value_and_a_known_flag(world):
    flags = world["meta"]["flags"]
    assert flags, "meta.flags is what makes the second element readable"
    for section, key, year, value in _cells(world):
        where = f"{section} {key} {year}"
        assert isinstance(value, list) and len(value) == 2, where
        number, flag = value
        assert isinstance(number, (int, float)) and not isinstance(number, bool), where
        assert isinstance(flag, str) and flag in flags, f"{where}: flag {flag!r}"


def test_no_item_is_a_residual_bucket(world):
    """The filter matches the label, so a relabelled `n.e.c.` item would pass
    the builder's own unit tests and land here."""
    offenders = [f"{code} {item['label']}" for code, item in world["items"].items()
                 if "n.e.c" in item["label"].lower()]
    assert offenders == []


def test_no_item_is_a_group_total(world):
    offenders = [code for code in world["items"] if int(code) in bwn.ITEM_GROUPS]
    assert offenders == []


def test_every_country_is_a_country_and_not_an_aggregate(world):
    offenders = [code for code in world["countries"]
                 if int(code) >= bwn.AGGREGATE_AREA_FLOOR]
    assert offenders == []


def test_every_cell_names_a_declared_item_and_country(world):
    for section, key, _year, _value in _cells(world):
        item, area = key.split("|")
        assert item in world["items"], f"{section} {key}"
        assert area in world["countries"], f"{section} {key}"


def test_no_price_belongs_to_an_item_that_has_no_yield(world):
    """The crop rule, end to end: the prices archive also prices meat, eggs and
    milk, and only the yield side decides what an item is."""
    offenders = [key for key in world["price"]
                 if key.split("|")[0] not in world["items"]]
    assert offenders == []


def test_every_year_is_inside_the_declared_window(world):
    first, last = world["meta"]["years"]
    assert first >= bwn.FIRST_YEAR
    for section, key, year, _value in _cells(world):
        assert first <= int(year) <= last, f"{section} {key} {year}"


def test_the_units_are_the_ones_the_rest_of_the_project_reads(world):
    assert world["meta"]["units"] == {"yield": "kg/da", "price": "USD/kg"}


def test_provenance_is_recorded_for_every_dataset(world):
    """Without this the file is an unattributable 4.8 MB blob: no way to tell
    which vintage of FAOSTAT produced it, or whether it was refreshed at all."""
    sources = {source["dataset"]: source for source in world["meta"]["sources"]}
    assert set(sources) == {dataset.key for dataset in ff.DATASETS.values()}
    for key, source in sources.items():
        assert source["url"].startswith("https://"), key
        assert source["last_modified"].strip(), key
        assert isinstance(source["bytes"], int) and source["bytes"] > 0, key
