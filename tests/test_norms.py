"""Unit tests for src/norms.py (no network, no store, no model)."""

import json

import pytest

from src import norms


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
