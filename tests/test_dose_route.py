"""The product-dose route inside the engine: it must compute, and it must not
retrieve, match products, or call the model."""

import json

import pytest

from src import dose_answer, doses, engine


DOSE_Q = "HİGRO FUBBY dekara ne kadar kullanmalıyım?"


@pytest.fixture
def no_llm(monkeypatch):
    """Make every expensive path explode, so a test passes only if the route
    genuinely avoided it."""
    def boom(*args, **kwargs):
        raise AssertionError("the dose route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return monkeypatch


def _payload(product="HİGRO FUBBY", group="sebze", value="5"):
    return {"product": product, "group": group,
            "area": {"value": value, "unit": "donum"}}


def test_a_dose_question_without_inputs_returns_the_card(no_llm):
    result = engine.answer(DOSE_Q)
    assert result.route == "product_dose"
    assert result.answer == dose_answer.ASK_FOR_INPUTS
    assert result.dose_form["kind"] == "product_dose"
    assert result.form is None, "the budget card must not be served here"


def test_a_fresh_card_carries_no_errors(no_llm):
    result = engine.answer(DOSE_Q)
    assert all(v is None for v in result.dose_form["errors"].values())


def test_a_dose_question_recommends_no_products(no_llm):
    assert engine.answer(DOSE_Q).recommended_products == []


def test_a_complete_payload_is_computed(no_llm):
    result = engine.answer(DOSE_Q, None, None, _payload())
    assert result.dose_form is None
    assert "dekara" in result.answer
    assert dose_answer.SEASON_REFUSAL in result.answer


def test_a_rejected_payload_comes_back_as_a_card_with_errors(no_llm):
    result = engine.answer(DOSE_Q, None, None, _payload(value="0"))
    assert result.dose_form["errors"]["area"]
    assert result.dose_form["area"]["value"] == "0"


def test_a_group_with_no_figure_is_said_not_guessed(no_llm):
    result = engine.answer(DOSE_Q, None, None, _payload(product="FLY AZOT", group="meyve"))
    assert result.dose_form is None
    assert "yayımlanmamış" in result.answer


def test_a_submitted_payload_is_computed_whatever_the_router_says(no_llm):
    """Turn 2 does not bet on the classifier a second time - the budget route's
    rule, for the same reason: the card is attached to the first question."""
    result = engine.answer("teşekkürler", None, None, _payload())
    assert result.route == "product_dose"
    assert result.dose_form is None


def test_a_broken_computation_never_becomes_a_guess(no_llm, monkeypatch):
    monkeypatch.setattr(dose_answer, "compute", lambda *a: 1 / 0)
    result = engine.answer(DOSE_Q, None, None, _payload())
    assert result.answer == dose_answer.COMPUTE_FAILED
    assert result.dose_form is None


def _events(chunks):
    return [json.loads(c.split("data: ", 1)[1]) for c in chunks if "data: " in c]


def test_the_stream_serves_the_same_card(no_llm):
    events = _events(list(engine.stream_answer(DOSE_Q)))
    assert [e["type"] for e in events] == ["token", "dose_form", "done"]
    assert events[1]["form"]["kind"] == "product_dose"


def test_the_stream_computes_a_submitted_payload(no_llm):
    events = _events(list(engine.stream_answer(DOSE_Q, None, None, _payload())))
    assert [e["type"] for e in events] == ["token", "done"]
    assert "dekara" in events[0]["content"]


def test_both_transports_answer_identically(no_llm):
    """answer() and stream_answer() are mirror images; a route wired into one
    reaches no user while the tests stay green."""
    direct = engine.answer(DOSE_Q, None, None, _payload()).answer
    streamed = "".join(e["content"] for e in
                       _events(list(engine.stream_answer(DOSE_Q, None, None, _payload())))
                       if e["type"] == "token")
    assert direct == streamed
