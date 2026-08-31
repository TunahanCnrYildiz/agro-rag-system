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


Row = namedtuple("Row", "label province value card block per_tree")


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
                per_tree=row.yield_kg_tree is not None,
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


def test_both_surfaces_choose_the_same_measure_for_every_row():
    """They disagreed on 1.568 cells for a whole round: the form prefilled
    Karabük/Ayva at 31 kg/ağaç while the comparison printed 13.419 kg/da.
    Checked against `row.yield_kg_tree` - the shipped table's own verdict -
    rather than card against block: two surfaces wrong in the same direction
    would still agree with each other, so a surface-against-surface check
    only catches them diverging, never both drifting off the data the same
    way. A failure here means one surface picked the wrong measure for a row,
    whichever surface it is."""
    mismatched = [
        r.label for r in _sweep()
        if r.card is not None
        and ((r.card["unit"] == "kg_agac") != r.per_tree
             or ("kg/ağaç" in r.block[0]) != r.per_tree)
    ]
    assert mismatched == [], mismatched[:10]


def test_no_per_tree_row_prints_a_per_dekar_unit_anywhere():
    """The derived kg/da for a tree crop divides a province's whole production
    by the few dekars of COMPACT orchard it records. It still exists in the data
    file; no surface may show it. Selected by `row.yield_kg_tree`, the shipped
    table's own verdict, NOT by `r.card["unit"] == "kg_agac"`: that would ask
    the code under test which rows to check it on, so a mutation that stops
    tagging per-tree cells as `kg_agac` would also erase them from this
    test's own filter, and the assertion would pass over an empty list
    instead of catching the leak. The card side also checks `card["unit"]`
    directly, not just `card["recent"]`: `recent` is None for 747 cells, and
    for those the unit is the only evidence a leak would leave behind. A
    failure here means a per-tree row is showing its derived per-dekar figure
    somewhere a farmer would read it."""
    leaked = [
        (r.label, r.province) for r in _sweep()
        if r.per_tree
        and ("kg/da" in " ".join(r.block)
             or (r.card is not None
                 and ("kg/da" in (r.card["recent"] or "")
                      or r.card["unit"] != "kg_agac")))
    ]
    assert leaked == [], leaked[:10]


def test_both_surfaces_reach_the_same_far_below_verdict():
    """One predicate, two callers. Checked only where the comparison prints a
    range at all - its `missing` branches print none, and by the design's own
    rule they carry no warning either."""
    disagreed = []
    for r in _sweep():
        if r.card is None or not any("önceki 5 yıl" in ln for ln in r.block):
            continue
        on_card = "çok altında" in (r.card["recent"] or "")
        in_block = any(
            crop_compare.FAR_BELOW_NOTE.format(year=r.value.year) in ln
            for ln in r.block)
        if on_card != in_block:
            disagreed.append((r.label, r.province))
    assert disagreed == [], disagreed[:10]


def test_no_warned_cell_sits_at_or_above_its_own_range_minimum():
    """The sentence says the figure is far below the range printed beside it.
    Before this was fixed, six cells were warned while sitting ON their range's
    minimum - K.Maraş/Fındık served 1 under a printed range of 1-12.
    `far_below_recent` is False whenever `recent_min is None`, so a warned row
    is guaranteed to carry a range - this check does not need to guard for it."""
    violations = [
        (r.label, r.province, r.value.amount, r.value.recent_min)
        for r in _sweep()
        if norms.far_below_recent(r.value)
        and r.value.amount >= r.value.recent_min
    ]
    assert violations == [], violations[:10]


def test_the_file_still_serves_most_of_its_yields():
    """FLOORS, not the measured counts. Measured today: 2.097 cells served
    per tree and 6.177 served per dekar. The floors sit at roughly two thirds, the same
    reasoning tests/test_build_crop_norms.py already uses: an order-of-magnitude
    collapse trips them, normal year-to-year drift in the TÜİK exports does not.
    A pinned exact count would go red on every yearly regeneration and teach
    whoever regenerates it to edit the number rather than read it.

    Counted from `r.per_tree` and `r.value` - the shipped table's own verdict,
    resolved straight off `row.yield_kg_tree` / `row.yield_kg_da` - not from
    `card["unit"]`: this test's name says "the file", and counting from the
    derived card would let a regression in src/budget.py trip it too, which
    is not what the name promises. `r.value` is None when the table itself
    carries no figure for a cell, so a served-but-empty row still doesn't count.
    """
    rows = _sweep()
    per_tree = sum(1 for r in rows if r.per_tree)
    per_dekar = sum(1 for r in rows if not r.per_tree and r.value is not None)
    assert per_tree > 1400, per_tree
    assert per_dekar > 4000, per_dekar
