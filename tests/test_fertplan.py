"""Fertilization table lookup. The TABLE'S CONTENT is not tested here - correctness
of agronomy cannot be established by unit test, only by review. What is tested is
that the mechanism handles an empty table, an unknown crop, and a reviewed row."""

import json

import pytest

from src import fertplan


@pytest.fixture(autouse=True)
def _clear_load_cache():
    """`_load` is `lru_cache`d, but `monkeypatch.setattr(_TABLE_PATH, ...)` only
    restores the path at teardown - it never touches the cache. Without this,
    a fixture written by test N can still be sitting in the cache when test
    N+1 runs, so tests would pass or fail depending on execution order. Clear
    both before (so this test reads its own fixture) and after (so the next
    test doesn't inherit this one's)."""
    fertplan._load.cache_clear()
    yield
    fertplan._load.cache_clear()


def test_table_ships_empty_until_reviewed():
    # Guards the constraint directly: no unreviewed agronomy reaches a user.
    assert fertplan.available_crops() == ()


def test_unknown_crop_returns_no_rows():
    assert fertplan.lookup("domates", None) == []


def test_lookup_reads_reviewed_rows(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "Fide döneminde ..."},
        {"stage": "çiçeklenme", "reviewed_by": "Z. Müh.", "note": "Çiçeklenmede ..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    rows = fertplan.lookup("domates", None)
    assert len(rows) == 2
    assert fertplan.lookup("domates", "fide")[0]["stage"] == "fide"


def test_rows_without_a_reviewer_are_dropped(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "note": "onaysız"},
        {"stage": "çiçeklenme", "reviewed_by": "Z. Müh.", "note": "onaylı"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    rows = fertplan.lookup("domates", None)
    assert [r["stage"] for r in rows] == ["çiçeklenme"]


def test_a_missing_table_file_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(fertplan, "_TABLE_PATH", tmp_path / "nope.json")
    assert fertplan.lookup("domates", None) == []


def test_framing_sentence_exists_and_says_it_is_an_estimate():
    assert "tahmin" in fertplan.FRAMING.lower()


def test_detect_crop_finds_nothing_while_the_table_is_empty():
    assert fertplan.detect_crop("Domatese ne zaman gübre vermeliyim?") is None


def test_detect_crop_matches_a_reviewed_crop_with_turkish_suffixes(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    assert fertplan.detect_crop("Domatese ne zaman gübre vermeliyim?") == "domates"
    assert fertplan.detect_crop("domatesin gübrelemesi") == "domates"
    assert fertplan.detect_crop("Buğdaya ne zaman gübre vereyim?") is None


def test_top_level_json_array_yields_an_empty_table(monkeypatch, tmp_path):
    # A malformed file (wrong top-level shape) must never raise - it must
    # just yield nothing, same as a missing file.
    table = tmp_path / "t.json"
    table.write_text(json.dumps(["domates", "bugday"]), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    assert fertplan.available_crops() == ()
    assert fertplan.lookup("domates", None) == []


def test_crop_value_that_is_not_a_list_yields_an_empty_table(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": "not-a-list"}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    assert fertplan.available_crops() == ()
    assert fertplan.lookup("domates", None) == []


def test_a_row_that_is_not_a_dict_is_skipped_not_fatal(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        "not-a-dict",
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    rows = fertplan.lookup("domates", None)
    assert [r["stage"] for r in rows] == ["fide"]


def test_detect_crop_matches_a_short_crop_bare_and_with_suffix(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"nar": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    assert fertplan.detect_crop("Nar bahçeme ne zaman gübre vereyim?") == "nar"
    assert fertplan.detect_crop("Nara ne zaman gübre vereyim?") == "nar"


def test_detect_crop_does_not_fire_inside_a_longer_word(monkeypatch, tmp_path):
    # The short-stem trap the router already paid for: "nar" must not match
    # inside "narenciye" just because it's a left-boundary prefix.
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"nar": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    assert fertplan.detect_crop("Narenciye bahçeme ne zaman gübre vereyim?") is None
