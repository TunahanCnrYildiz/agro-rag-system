import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def crop_ids() -> list[str]:
    document = json.loads((DATA / "crop_norms.json").read_text(encoding="utf-8"))
    return list(document["crops"])


@pytest.fixture(scope="module")
def world_items() -> set[int]:
    document = json.loads((DATA / "world_norms.json").read_text(encoding="utf-8"))
    return {int(code) for code in document["items"]}


@pytest.fixture(scope="module")
def crop_map() -> dict:
    return json.loads((DATA / "crop_fao_map.json").read_text(encoding="utf-8"))["map"]


def test_every_mapped_id_is_a_real_crop(crop_map, crop_ids):
    assert set(crop_map) <= set(crop_ids)


def test_every_entry_decides_something(crop_map):
    for crop_id, entry in crop_map.items():
        assert "fao" in entry, crop_id
        assert entry["fao"] is None or isinstance(entry["fao"], int), crop_id


def test_an_unmapped_crop_says_why(crop_map):
    for crop_id, entry in crop_map.items():
        if entry["fao"] is None:
            assert entry.get("reason"), crop_id


def test_a_mapped_crop_never_carries_a_reason(crop_map):
    """`reason` means 'there is no FAO item'. A mapped crop explaining itself
    uses `note`, so the two can never be confused by a reader or a filter."""
    for crop_id, entry in crop_map.items():
        if entry["fao"] is not None:
            assert "reason" not in entry, crop_id


def test_every_mapped_code_exists_in_the_world_file(crop_map, world_items):
    for crop_id, entry in crop_map.items():
        if entry["fao"] is not None:
            assert entry["fao"] in world_items, f"{crop_id} -> {entry['fao']}"


def test_every_crop_we_carry_is_decided(crop_map, crop_ids):
    """Not 'most of them'. A crop id missing from this file is a crop nobody
    made a decision about, which reads exactly like a crop with no FAO item."""
    missing = [crop_id for crop_id in crop_ids if crop_id not in crop_map]
    assert missing == []


RESIDUAL_GROUPS = {541, 542}


def test_no_crop_is_mapped_to_a_residual_fruit_group(crop_map):
    """541 `Other stone fruits` and 542 `Other pome fruits` are residual
    buckets: their shared CPC parent class 01349 is literally "Pome fruits and
    stone fruits, n.e.c.". They survived the world layer's filter only because
    that filter matched the string `n.e.c.` in the label, which these two lack.

    Mapping onto them would attach an unnamed mixture's average to a named
    crop — the harm the exclusion exists to prevent. The proof they are a
    filing convention rather than a botanical class: Türkiye reports a 541
    series and no 542 series at all, while growing both residual pomes
    (yenidünya, muşmula, üvez) and residual drupes (kızılcık, iğde, hünnap).
    So one country's 541 is not the same crop as another's.
    """
    offenders = [crop_id for crop_id, entry in crop_map.items()
                 if entry["fao"] in RESIDUAL_GROUPS]
    assert offenders == []


@pytest.mark.parametrize("ids, code", [
    (["durum bugdayi", "bugday, durum bugdayi haric"], 15),
    (["arpa (biralik)", "arpa (diger)"], 44),
    (["lahana (beyaz)", "lahana (kirmizi)", "lahana (kara yaprak)"], 358),
    (["mercimek, kuru (kirmizi)", "mercimek, kuru (yesil)"], 201),
    (["aycicegi tohumu (yaglik)", "aycicegi tohumu (cerezlik)"], 267),
])
def test_known_many_to_one_collapses_hold(crop_map, ids, code):
    """FAOSTAT is coarser than TÜİK. These collapses are deliberate; an edit
    that splits one of them is a mistake, not a refinement."""
    for crop_id in ids:
        assert crop_map[crop_id]["fao"] == code, crop_id
