"""The budget route inside the engine: it must compute, and it must not
retrieve, match products, or call the model."""

import pytest

from src import budget, engine


BUDGET_Q = "5 dönüm domates ektim, ne kadar kâr ederim?"


@pytest.fixture
def no_llm(monkeypatch):
    """Make every expensive path explode, so a test passes only if the route
    genuinely avoided it."""
    def boom(*args, **kwargs):
        raise AssertionError("the budget route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return monkeypatch


def _payload(cost="5000"):
    raw = {
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "2", "unit": "ton"},
        "price": {"value": "10", "unit": "tl_kg"},
    }
    if cost is not None:
        raw["cost"] = {"value": cost, "unit": "tl"}
    return raw


def test_a_budget_question_without_inputs_returns_the_form(no_llm):
    result = engine.answer(BUDGET_Q)
    assert result.route == "budget"
    assert result.answer == budget.ASK_FOR_NUMBERS
    assert result.form is not None
    assert [f["id"] for f in result.form["fields"]] == [f.id for f in budget.FIELDS]


def test_a_fresh_form_carries_no_errors(no_llm):
    """Nothing was submitted yet, so 'this field is required' would be scolding
    a user who has not been shown the field."""
    result = engine.answer(BUDGET_Q)
    assert all(f["error"] is None for f in result.form["fields"])


def test_a_budget_question_recommends_no_products(no_llm):
    assert engine.answer(BUDGET_Q).recommended_products == []


def test_a_complete_payload_is_computed(no_llm):
    result = engine.answer(BUDGET_Q, None, _payload())
    assert result.form is None
    assert "15.000,00 TL" in result.answer


def test_an_incomplete_payload_returns_the_form_with_field_errors(no_llm):
    bad = _payload()
    bad["price"] = {"value": "on lira", "unit": "tl_kg"}
    result = engine.answer(BUDGET_Q, None, bad)
    assert result.form is not None
    errors = {f["id"]: f["error"] for f in result.form["fields"]}
    assert errors["price"] is not None
    assert errors["area"] is None


def test_a_failing_computation_goes_silent_rather_than_guessing(no_llm, monkeypatch):
    """No fallback to the model path: an LLM answer about money is exactly what
    this route removes."""
    def boom(_inputs):
        raise ValueError("nope")

    monkeypatch.setattr(budget, "compute", boom)
    result = engine.answer(BUDGET_Q, None, _payload())
    assert result.answer == budget.COMPUTE_FAILED
    assert result.form is None


def test_a_submitted_payload_is_computed_even_if_the_router_disagrees(no_llm):
    """Turn 2 must not bet on the router a second time. If a complete payload
    arrives, it is computed whatever the route says."""
    result = engine.answer("Elma ağacı ne zaman budanır?", None, _payload())
    assert result.route == "budget"
    assert "15.000,00 TL" in result.answer


def test_a_non_budget_question_is_untouched(monkeypatch):
    """The corpus path must behave exactly as before for every other route."""
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda *a, **k: "Budama şöyle.")
    result = engine.answer("Elma ağacı ne zaman budanır?")
    assert result.route != "budget"
    assert result.form is None
    assert "Budama" in result.answer


def test_budget_still_takes_zero_false_entries_in_the_frozen_routing_set():
    """The whole design rests on no unrelated question reaching this route. If a
    future router rule breaks that, a budget form card appears under a question
    about leaf spot - so it fails here instead."""
    from src import router
    from evals.routing_set import ROUTING_CASES

    intruders = [c["query"] for c in ROUTING_CASES
                 if c["route"] != "budget"
                 and router.classify(c["query"], None)[0] == "budget"]
    assert intruders == []


import json


def _events(chunks):
    """Parse the SSE lines the engine yields back into payload dicts."""
    out = []
    for chunk in chunks:
        for line in chunk.split("\n"):
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def test_the_stream_emits_the_sentence_the_form_and_done(no_llm):
    events = _events(engine.stream_answer(BUDGET_Q))
    assert [e["type"] for e in events] == ["token", "form", "done"]
    assert events[0]["content"] == budget.ASK_FOR_NUMBERS
    assert [f["id"] for f in events[1]["form"]["fields"]] == [
        f.id for f in budget.FIELDS]


def test_a_computed_answer_streams_without_a_form_event(no_llm):
    events = _events(engine.stream_answer(BUDGET_Q, None, _payload()))
    assert [e["type"] for e in events] == ["token", "done"]
    assert "15.000,00 TL" in events[0]["content"]


def test_the_stream_recommends_no_products(no_llm):
    events = _events(engine.stream_answer(BUDGET_Q))
    assert not any(e["type"] == "products" for e in events)


def test_streaming_and_non_streaming_agree_without_inputs(no_llm):
    """THE test. Wiring the form into answer() and forgetting stream_answer() is
    the defect this project already shipped once, in this exact place."""
    unified = engine.answer(BUDGET_Q)
    events = _events(engine.stream_answer(BUDGET_Q))
    streamed = "".join(e["content"] for e in events if e["type"] == "token")
    form = next(e["form"] for e in events if e["type"] == "form")
    assert streamed == unified.answer
    assert form == unified.form


def test_streaming_and_non_streaming_agree_on_a_computed_answer(no_llm):
    unified = engine.answer(BUDGET_Q, None, _payload())
    events = _events(engine.stream_answer(BUDGET_Q, None, _payload()))
    streamed = "".join(e["content"] for e in events if e["type"] == "token")
    assert streamed == unified.answer
    assert not any(e["type"] == "form" for e in events)


def test_an_old_client_that_skips_unknown_event_types_still_completes(no_llm):
    """mobile-app/src/api.ts only branches on 'products' and 'token'; an
    unknown type falls through. The deployed APK must still see its sentence
    and a clean end of stream."""
    events = _events(engine.stream_answer(BUDGET_Q))
    known = [e for e in events if e["type"] in ("token", "products", "done")]
    assert [e["type"] for e in known] == ["token", "done"]


def test_the_stream_computes_a_submitted_payload_even_if_the_router_disagrees(no_llm):
    """Turn 2 must not bet on the router a second time. A complete payload
    is computed on the streaming path whatever the route says."""
    events = _events(engine.stream_answer("Elma ağacı ne zaman budanır?", None, _payload()))
    assert [e["type"] for e in events] == ["token", "done"]
    assert "15.000,00 TL" in events[0]["content"]
