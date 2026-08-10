"""Fertilization table lookup. The TABLE'S CONTENT is not tested here - correctness
of agronomy cannot be established by unit test, only by review. What is tested is
that the mechanism handles an empty table, an unknown crop, and a reviewed row."""

import json

import pytest

from src import fertplan


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
    fertplan._load.cache_clear()
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
    fertplan._load.cache_clear()
    rows = fertplan.lookup("domates", None)
    assert [r["stage"] for r in rows] == ["çiçeklenme"]


def test_a_missing_table_file_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(fertplan, "_TABLE_PATH", tmp_path / "nope.json")
    fertplan._load.cache_clear()
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
    fertplan._load.cache_clear()
    assert fertplan.detect_crop("Domatese ne zaman gübre vermeliyim?") == "domates"
    assert fertplan.detect_crop("domatesin gübrelemesi") == "domates"
    assert fertplan.detect_crop("Buğdaya ne zaman gübre vereyim?") is None
