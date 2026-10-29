"""The crop-comparison route inside the engine: it must compute, and it must
not retrieve, match products, or call the model. The open 'ne eksem?' question
must keep the answer it has today."""

import json

import pytest

from src import crop_compare, engine


COMPARE_Q = "Konya'dayım, bu yıl domates mi biber mi ekmeliyim?"
OPEN_Q = "Konya'dayım, bu yıl tarlama ne eksem iyi olur?"


@pytest.fixture
def no_llm(monkeypatch):
    """Make every expensive path explode, so a test passes only if the route
    genuinely avoided it."""
    def boom(*args, **kwargs):
        raise AssertionError("the comparison route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return monkeypatch


def _payload(first="domates (sofralik)", second="biber (salcalik, kapya)"):
    return {"first": first, "second": second}


def test_a_two_crop_question_returns_the_card(no_llm):
    result = engine.answer(COMPARE_Q)
    assert result.route == "crop_choice"
    assert result.answer == crop_compare.ASK_FOR_CROPS
    assert result.compare_form["kind"] == "crop_compare"
    assert result.form is None and result.dose_form is None


def test_the_card_is_built_for_the_province_in_the_conversation(no_llm):
    assert engine.answer(COMPARE_Q).compare_form["province"] == "Konya"


def test_an_open_question_keeps_todays_answer(monkeypatch):
    """THE SHIPPED REFUSAL. 'Ne eksem?' still goes down the corpus path with
    the factors context block - this route does not take it over."""
    seen = {}

    def fake_context(message, history=None):
        seen["retrieved"] = True
        return ""

    monkeypatch.setattr(engine, "retrieve_context", fake_context)
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda *a, **k: "faktörler...")
    result = engine.answer(OPEN_Q)
    assert result.compare_form is None
    assert seen.get("retrieved") is True


def test_a_one_crop_question_keeps_todays_answer(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda *a, **k: "faktörler...")
    result = engine.answer("Konya'dayım, domates ekmeli miyim?")
    assert result.compare_form is None


def test_a_complete_payload_is_computed(no_llm):
    result = engine.answer(COMPARE_Q, None, None, None, _payload())
    assert result.compare_form is None
    assert crop_compare.NOT_PROFIT in result.answer


def test_a_rejected_payload_comes_back_as_a_card_with_errors(no_llm):
    result = engine.answer(COMPARE_Q, None, None, None,
                           _payload(second="domates (sofralik)"))
    assert result.compare_form["errors"]["second"]


def test_a_submitted_payload_is_computed_whatever_the_router_says(no_llm):
    """Turn 2 does not bet on the classifier a second time.

    NOTE: the brief's literal call passed no history, which leaves the
    province unresolved and the route correctly falls back to NO_PROVINCE
    (an explicit, repeatedly-documented design choice: never guess a
    province). A real turn 2 carries the province-bearing turn 1 in
    history, so this test supplies it - that is the only change from the
    brief's test body; see task-4-report.md.
    """
    history = [{"role": "user", "content": COMPARE_Q}]
    result = engine.answer("teşekkürler", history, None, None, _payload())
    assert result.compare_form is None
    assert crop_compare.NOT_PROFIT in result.answer


def test_no_province_asks_for_one_rather_than_guessing(no_llm):
    result = engine.answer("Domates mi biber mi ekmeliyim?")
    assert result.answer == crop_compare.NO_PROVINCE
    assert result.compare_form is None


def test_a_broken_computation_never_becomes_a_guess(no_llm, monkeypatch):
    monkeypatch.setattr(crop_compare, "compute", lambda *a: 1 / 0)
    result = engine.answer(COMPARE_Q, None, None, None, _payload())
    assert result.answer == crop_compare.COMPUTE_FAILED
    assert result.compare_form is None


def _events(chunks):
    return [json.loads(c.split("data: ", 1)[1]) for c in chunks if "data: " in c]


def test_the_stream_serves_the_same_card(no_llm):
    events = _events(list(engine.stream_answer(COMPARE_Q)))
    assert [e["type"] for e in events] == ["token", "compare_form", "done"]


def test_both_transports_answer_identically(no_llm):
    direct = engine.answer(COMPARE_Q, None, None, None, _payload()).answer
    streamed = "".join(e["content"] for e in
                       _events(list(engine.stream_answer(
                           COMPARE_Q, None, None, None, _payload())))
                       if e["type"] == "token")
    assert direct == streamed


def test_a_computed_comparison_offers_both_crops_by_family(no_llm):
    """PDF p5: the crop the farmer settles on goes into the profile. The client
    asks before saving; the server only offers - by family, so TÜİK's
    "Domates (Sofralık)" reaches the profile as "Domates"."""
    result = engine.answer(COMPARE_Q, None, None, None, _payload())
    assert result.crop_offer == ("Domates", "Biber")


def test_the_card_itself_offers_nothing(no_llm):
    """The farmer has not compared anything yet."""
    assert engine.answer(COMPARE_Q).crop_offer == ()


def test_the_stream_offers_the_same_crops_after_the_comparison(no_llm):
    events = _events(list(engine.stream_answer(COMPARE_Q, None, None, None, _payload())))
    assert [e["type"] for e in events][-2:] == ["crop_offer", "done"]
    assert events[-2]["crops"] == ["Domates", "Biber"]
