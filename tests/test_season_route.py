"""The season card inside the engine and over the wire: no retrieval, no
product match, no model call - published stage lengths and the farmer's date."""
import json

import pytest

from src import engine, season

Q = "Domates için sezon programı çıkarır mısın?"
TOMATO = "domates (sofralik)"


@pytest.fixture
def no_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the season route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    monkeypatch.setattr(engine, "_get_llm", boom)
    return monkeypatch


def test_a_season_question_returns_the_card_with_the_named_crop(no_llm):
    result = engine.answer(Q)
    assert result.route == "season"
    assert result.answer == season.ASK_FOR_INPUTS
    form = result.season_form
    assert form["kind"] == "season"
    assert form["crop"].startswith("domates")
    assert {c["id"] for c in form["crops"]} == set(season.available_crops())


def test_a_submitted_card_is_the_calendar(no_llm):
    result = engine.answer(Q, None, None, None, None,
                           {"crop": TOMATO, "planting": "15.04.2027"})
    assert result.season_form is None
    assert "15 Nisan – 14 Mayıs (30 gün)" in result.answer
    assert season.DISCLAIMER in result.answer


def test_a_submitted_card_is_answered_whatever_the_message_routes_to(no_llm):
    result = engine.answer("tamam", None, None, None, None,
                           {"crop": TOMATO, "planting": "15.04.2027"})
    assert result.route == "season"


def test_a_bad_date_comes_back_with_its_error_and_keeps_the_crop(no_llm):
    form = engine.answer(Q, None, None, None, None,
                         {"crop": TOMATO, "planting": "31.02.2027"}).season_form
    assert form["errors"] == {"crop": None, "planting": season.DATE_ERROR}
    assert form["crop"] == TOMATO and form["planting"] == "31.02.2027"


def test_an_unknown_crop_is_a_field_error(no_llm):
    form = engine.answer(Q, None, None, None, None,
                         {"crop": "no-such", "planting": "15.04.2027"}).season_form
    assert form["errors"]["crop"]


def test_the_stream_serves_the_same_card_and_calendar(no_llm):
    events = [json.loads(c.split("data: ", 1)[1]) for c in engine.stream_answer(Q)
              if "data: " in c]
    assert [e["type"] for e in events] == ["token", "season_form", "done"]
    events = [json.loads(c.split("data: ", 1)[1]) for c in engine.stream_answer(
        Q, None, None, None, None, {"crop": TOMATO, "planting": "15.04.2027"})
        if "data: " in c]
    assert [e["type"] for e in events] == ["token", "products", "done"]
    assert "Orta dönem" in events[0]["content"]


def test_a_broken_table_is_compute_failed_never_a_guess(no_llm, monkeypatch):
    monkeypatch.setattr(season, "build", lambda *a: 1 / 0)
    result = engine.answer(Q, None, None, None, None,
                           {"crop": TOMATO, "planting": "15.04.2027"})
    assert result.answer == season.COMPUTE_FAILED


@pytest.mark.parametrize("text, ok", [
    ("15.04.2027", True), ("15/04/2027", True), ("1-4-2027", True),
    ("2027-04-15", True), ("31.02.2027", False), ("15.04.27", False),
    ("", False), (None, False), ("15.04.1990", False),
])
def test_dates_are_read_in_turkish_order(text, ok):
    assert (season.parse_date(text) is not None) is ok


def test_the_json_transport_carries_the_card():
    from fastapi.testclient import TestClient
    from src import main
    r = TestClient(main.app).post("/api/chat", json={
        "message": "x", "season": {"crop": TOMATO, "planting": "15.04.2027"}})
    assert r.status_code == 200
    body = r.json()
    assert "Orta dönem" in body["answer"] and body["season_form"] is None
    assert body["crop_offer"] == []


def test_the_programmes_products_come_as_link_chips(no_llm):
    result = engine.answer(Q, None, None, None, None,
                           {"crop": TOMATO, "planting": "15.04.2027"})
    assert [p.title for p in result.recommended_products] == [
        "ZİNCER", "HİGRO BARF", "A.P.P – ORNE", "HİGRO ROOT LEGEND"]
    assert all(p.link.startswith("https://") for p in result.recommended_products)
    events = [json.loads(c.split("data: ", 1)[1]) for c in engine.stream_answer(
        Q, None, None, None, None, {"crop": TOMATO, "planting": "15.04.2027"}) if "data: " in c]
    assert [e["type"] for e in events] == ["token", "products", "done"]


def test_a_farmer_in_season_gets_this_weeks_weather(no_llm, monkeypatch):
    from datetime import date as _date
    from src.context import weather
    calls = []
    monkeypatch.setattr(engine, "_today", lambda: _date(2027, 6, 1))
    monkeypatch.setattr(weather, "outlook",
                        lambda province, today=None: calls.append((province, today))
                        or weather.Outlook(5.0, 9, 24))
    history = [{"role": "user", "content": "Konya'dayım."}]
    result = engine.answer(Q, history, None, None, None,
                           {"crop": TOMATO, "planting": "15.04.2027"})
    assert calls == [("Konya", _date(2027, 6, 1))]
    assert "**Bu hafta** (Konya, Open-Meteo tahmini)" in result.answer
    assert season.RAIN_RULE in result.answer


def test_a_weather_failure_costs_only_the_weather(no_llm, monkeypatch):
    from src.context import weather
    monkeypatch.setattr(weather, "outlook", lambda *a, **k: 1 / 0)
    result = engine.answer(Q, [{"role": "user", "content": "Konya'dayım."}], None, None, None,
                           {"crop": TOMATO, "planting": "15.04.2027"})
    assert "Orta dönem" in result.answer and "Bu hafta" not in result.answer


def test_a_bad_date_for_a_tree_asks_for_the_season_start(no_llm):
    form = engine.answer(Q, None, None, None, None,
                         {"crop": "portakal (washington)", "planting": "yok"}).season_form
    assert form["errors"]["planting"] == season.TREE_DATE_ERROR
