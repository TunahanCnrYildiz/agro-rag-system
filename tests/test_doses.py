"""Unit tests for src/doses.py (no network, no store, no model)."""

import ast
import json
from pathlib import Path

import pytest

from src import doses


def _write(tmp_path, monkeypatch, payload):
    path = tmp_path / "product_doses.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    return path


GOOD = {
    "meta": {"generated": "2026-08-22"},
    "products": {
        "HİGRO FUBBY": {"sebze": {"damlama": {"low": 250.0, "high": 250.0, "unit": "gr"}},
                        "meyve": {"damlama": {"low": 250.0, "high": 250.0, "unit": "gr"}}},
        "HIGRO 8 MN": {"hepsi": {"damlama": {"low": 2.0, "high": 2.5, "unit": "litre"}}},
        "FLY AZOT": {"hepsi": {"yaprak": {"low": 200.0, "high": 250.0, "unit": "cc"}}},
    },
    "all_groups_scope": {"HIGRO 8 MN": ["sebze", "meyve", "tarla"],
                         "FLY AZOT": ["tarla", "sebze"]},
}


def test_a_dose_is_found_for_its_group(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    found = doses.lookup("HİGRO FUBBY", "sebze")
    assert len(found) == 1
    assert (found[0].low, found[0].high, found[0].unit, found[0].method) == (
        250.0, 250.0, "gr", "damlama")


def test_a_group_the_product_does_not_cover_returns_nothing(tmp_path, monkeypatch):
    """Nothing, never another group's figure: a fruit dose handed to a field
    grower is a wrong number that reads entirely plausibly."""
    _write(tmp_path, monkeypatch, GOOD)
    assert doses.lookup("HİGRO FUBBY", "tarla") == ()


def test_an_unqualified_dose_answers_every_group_it_was_reviewed_for(tmp_path, monkeypatch):
    """'hepsi' means the parser saw no group heading. When a reviewer confirmed
    the page names no crop either, the figure is the answer for any group."""
    _write(tmp_path, monkeypatch, GOOD)
    for group in ("sebze", "meyve", "tarla"):
        found = doses.lookup("HIGRO 8 MN", group)
        assert len(found) == 1 and found[0].high == 2.5


def test_a_reviewed_row_stays_out_of_the_groups_its_page_never_named(tmp_path, monkeypatch):
    """FLY AZOT's page qualifies every figure by crop and names no fruit. The
    fallback used to hand a fruit grower a cereal figure."""
    _write(tmp_path, monkeypatch, GOOD)
    assert doses.lookup("FLY AZOT", "meyve") == ()
    assert len(doses.lookup("FLY AZOT", "tarla")) == 1
    assert len(doses.lookup("FLY AZOT", "sebze")) == 1


def test_an_unreviewed_unqualified_row_answers_nothing(tmp_path, monkeypatch):
    """No review, no fallback. A row nobody read must not answer three groups
    on the strength of a missing heading."""
    payload = {"products": {"YENİ ÜRÜN": {"hepsi": {"damlama": {"low": 1.0, "high": 2.0, "unit": "litre"}}}},
               "all_groups_scope": {}}
    _write(tmp_path, monkeypatch, payload)
    for group in ("sebze", "meyve", "tarla"):
        assert doses.lookup("YENİ ÜRÜN", group) == ()


def test_an_unknown_product_returns_nothing(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert doses.lookup("YOK BÖYLE BİR ÜRÜN", "sebze") == ()


def test_a_missing_file_is_an_empty_table(tmp_path, monkeypatch):
    """A broken data file must never break answering - fertplan._load's rule."""
    monkeypatch.setattr(doses, "_PATH", tmp_path / "nope.json")
    doses._load.cache_clear()
    assert doses._load() == ({}, {})
    assert doses.available_products() == ()
    assert doses.lookup("HİGRO FUBBY", "sebze") == ()


def test_malformed_json_is_an_empty_table(tmp_path, monkeypatch):
    path = tmp_path / "product_doses.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    assert doses._load() == ({}, {})


@pytest.mark.parametrize("bad", [
    {"products": {"X": {"sebze": {"damlama": {"low": 3.0, "high": 1.0, "unit": "litre"}}}}},
    {"products": {"X": {"sebze": {"damlama": {"low": None, "high": 1.0, "unit": "litre"}}}}},
    {"products": {"X": {"sebze": {"damlama": {"low": 1.0, "high": 2.0}}}}},
    {"products": {"X": "not a mapping"}},
])
def test_a_malformed_row_is_dropped_whole(tmp_path, monkeypatch, bad):
    """Dropped whole rather than half-loaded: a product carrying one good group
    and one broken one would answer for the first and silently say nothing for
    the second, with no way to tell that apart from a product that simply has
    no figure for it."""
    _write(tmp_path, monkeypatch, bad)
    assert doses.lookup("X", "sebze") == ()


def test_a_products_GOOD_groups_go_down_with_its_bad_one(tmp_path, monkeypatch):
    """The drop has to be WHOLE, and only a product with a good group ALONGSIDE
    a bad one can tell that apart from dropping just the bad group.

    Without this case every malformed fixture has exactly one group, so
    "drop the product" and "drop the group" leave identical observable results
    and a regression to per-group filtering passes the whole suite. That
    regression is the failure the module exists to prevent: a product that
    answers for one group and silently not for another is indistinguishable
    from one that simply has no figure there."""
    _write(tmp_path, monkeypatch, {"products": {"X": {
        "sebze": {"damlama": {"low": 1.0, "high": 2.0, "unit": "litre"}},
        "meyve": {"damlama": {"low": 3.0, "high": 1.0, "unit": "litre"}},
    }}})
    assert doses.lookup("X", "meyve") == ()
    assert doses.lookup("X", "sebze") == ()
    assert doses.available_products() == ()


def test_a_non_finite_value_is_refused(tmp_path, monkeypatch):
    """json.loads accepts NaN and Infinity by default, and either would reach a
    purchase quantity as nan."""
    path = tmp_path / "product_doses.json"
    path.write_text('{"products": {"X": {"sebze": {"damlama": '
                    '{"low": NaN, "high": 2.0, "unit": "litre"}}}}}', encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    assert doses.lookup("X", "sebze") == ()


def test_available_products_is_sorted(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert list(doses.available_products()) == sorted(GOOD["products"])


def test_the_all_groups_key_is_shared_with_the_converter():
    """One spelling, one definition. Two that drifted apart would make every
    unqualified dose silently unfindable, with nothing failing."""
    from src import dose_parse
    assert doses.ALL_GROUPS is dose_parse.ALL_GROUPS


def test_doses_does_not_import_the_engine():
    """A data lookup has no business dragging the engine in - the boundary
    src/norms.py and src/budget.py both keep."""
    tree = ast.parse(Path("src/doses.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any("engine" in name for name in imported)
    # src.dose_parse is allowed and expected - it is where ALL_GROUPS lives.
    assert "src.dose_parse" in imported


def test_the_shipped_file_loads_and_carries_products():
    """Against the real data, not a fixture: a converter regression that
    empties the file would leave every fixture-based test above green."""
    doses._load.cache_clear()
    assert len(doses.available_products()) >= 35


def test_a_group_nobody_publishes_is_not_answered(tmp_path, monkeypatch):
    """Without this a typo falls through to the unqualified `hepsi` row and the
    caller gets a real figure back for a group it never asked about."""
    _write(tmp_path, monkeypatch, GOOD)
    assert doses.lookup("HIGRO 8 MN", "muz") == ()
    assert doses.lookup("HIGRO 8 MN", "tarla") != ()
