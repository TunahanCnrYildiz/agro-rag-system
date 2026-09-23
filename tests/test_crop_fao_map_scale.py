import json
import statistics
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"
TURKIYE = "223"
LOWER, UPPER = 0.2, 5.0

# Ratios outside the band that are correct anyway. Each needs a reason that
# explains the divergence, not a note that it was observed.
ALLOWED = {
    # "crop id": "why FAOSTAT and TUIK legitimately disagree by this much",
    "biber, kuru, islenmemis": (
        "Reporting basis, not a mis-mapping. FAO 689 is the only dry pepper item "
        "there is (401 is explicitly green), and the two labels match exactly. "
        "The levels do not, because they weigh different things: our provincial "
        "series runs 841-3.128 kg/da over 2016-2025, the same band as the four fresh "
        "pepper ids on item 401, so TUIK publishes this yield on a fresh-harvest "
        "weight. FAOSTAT's 689 series for Turkiye is a flat ~234 kg/da, about an "
        "eighth of ours, which is the fresh-to-dry ratio for peppers. Mapping it "
        "anywhere else would be worse: there is no other dry pepper item, and 401 "
        "would merge the dry crop into the fresh one."
    ),
}


@pytest.fixture(scope="module")
def world():
    return json.loads((DATA / "world_norms.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms():
    return json.loads((DATA / "crop_norms.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def crop_map():
    return json.loads((DATA / "crop_fao_map.json").read_text(encoding="utf-8"))["map"]


def _turkish_median(entry: dict, years: list[int], year: int) -> float | None:
    measure = entry.get("yield_kg_da") or {}
    if not isinstance(measure, dict) or year not in years:
        return None
    position = years.index(year)
    values = [
        series[position]
        for name, series in measure.items()
        if name != "scope" and isinstance(series, list)
        and len(series) > position and series[position] is not None
    ]
    return statistics.median(values) if values else None


def _ratios(world, norms, crop_map):
    years = norms["meta"]["years"]
    for crop_id, mapping in crop_map.items():
        code = mapping["fao"]
        if code is None:
            continue
        cell = world["yield"].get(f"{code}|{TURKIYE}")
        entry = norms["crops"].get(crop_id)
        if not cell or entry is None:
            continue
        shared = sorted(set(cell) & {str(year) for year in years}, reverse=True)
        if not shared:
            continue
        year = int(shared[0])
        ours = _turkish_median(entry, years, year)
        theirs = cell[str(year)][0]
        # `is None`, not falsiness: a reported 0.0 is a measurement that should
        # be screened, not a missing cell. The world file ships 19 zero yields.
        if ours is None or theirs is None:
            continue
        # A zero on our side is a disagreement, not a missing cell, so it has to
        # reach the band rather than divide.
        yield crop_id, code, year, theirs, ours, theirs / ours if ours else float("inf")


def test_the_screen_actually_covers_something(world, norms, crop_map):
    """A screen that silently compares nothing would pass forever. The floor
    sits just under the 125 pairs measured on 2026-09-23, so losing a chunk of
    the comparison — a renamed key, a dropped year — fails here instead of
    quietly shrinking the screen to nothing."""
    assert sum(1 for _ in _ratios(world, norms, crop_map)) >= 110


def test_no_mapping_disagrees_with_our_own_turkish_figure_by_an_order_of_magnitude(
    world, norms, crop_map
):
    offenders = [
        f"{crop_id} -> FAO {code} ({year}): FAOSTAT {theirs:.1f} vs ours {ours:.1f}"
        f" = {ratio:.2f}x"
        for crop_id, code, year, theirs, ours, ratio in _ratios(world, norms, crop_map)
        if not (LOWER <= ratio <= UPPER) and crop_id not in ALLOWED
    ]
    assert offenders == [], "\n".join(offenders)
