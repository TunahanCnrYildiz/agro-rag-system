"""Smoke tests over the REAL data/crop_norms.json.

Three code reviews established these properties by sweeping the shipped file
by hand and then left the evidence in review transcripts nobody re-reads. Every
other test of these two surfaces runs on a fixture, so a regression in any of
them would keep the whole suite green.

THIS FILE MUST STAY SEPARATE. tests/test_crop_compare.py has an autouse fixture
that writes a fixture table to a temp file and points norms._PATH at it; a "real
data" test placed there would silently read the fixture and pass vacuously.
"""
from collections import namedtuple

from src import budget, crop_compare, norms
from src.config import DATA_DIR
from src.context.location import PROVINCES


Row = namedtuple("Row", "label province value card block")


def _sweep():
    """Every (crop, province) the shipped table serves, through BOTH surfaces.

    The comparison side goes through `_figures` + `_crop_block` rather than
    `render`, because `render` takes a TWO-crop answer: covering every row
    through it would mean building ~10.000 pairings and would say nothing extra.
    `_crop_block` is the function that produces one crop's lines; `render` only
    joins them and appends the closing sentences, which this file does not
    assert about.

    Measured at 0,15 s for 19.926 rows, so one sweep serves every test here.
    """
    latest = norms.latest_year()
    rows = []
    for province in PROVINCES:
        for row in norms.province_table(province):
            value = (row.yield_kg_tree if row.yield_kg_tree is not None
                     else row.yield_kg_da)
            rows.append(Row(
                label=row.label,
                province=province,
                value=value,
                card=budget._yield_cell(row),
                block=crop_compare._crop_block(
                    crop_compare._figures(row, latest)),
            ))
    return rows


def test_the_sweep_really_reads_the_shipped_file():
    """PROVE THE INSTRUMENT BEFORE TRUSTING IT. norms._load is an
    lru_cache(maxsize=1) and several test modules repoint norms._PATH at a temp
    table. A leaked repoint would make norms._PATH some tmp_path fixture file -
    which, because every fixture writes to tmp_path / "crop_norms.json" too,
    still has the right file NAME. Comparing to DATA_DIR / "crop_norms.json"
    catches that; a bare name check would not. If this assertion ever fails,
    a previous test's monkeypatch of norms._PATH outlived its teardown and
    every test in this file would silently be sweeping a fixture instead of
    the shipped data. If the crop-count assertion below ever fails on its
    own, the shipped file shrank to a fixture-sized table - a data-loss bug,
    not a test bug.
    """
    norms._load.cache_clear()
    assert norms._PATH == DATA_DIR / "crop_norms.json", norms._PATH
    assert len(norms.available_crops()) > 200, len(norms.available_crops())


def test_the_sweep_covers_the_whole_table():
    """A sweep that quietly collected nothing would make every assertion in this
    file vacuously true."""
    rows = _sweep()
    assert len(rows) > 15000, len(rows)
    assert sum(1 for r in rows if r.card is not None) > 5000
