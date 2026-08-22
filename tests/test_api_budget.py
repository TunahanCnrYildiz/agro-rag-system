"""The /api/chat contract for the budget route."""

import json

import pytest
from fastapi.testclient import TestClient

from src import engine, main


BUDGET_Q = "5 dönüm domates ektim, ne kadar kâr ederim?"


@pytest.fixture
def client(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the budget route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return TestClient(main.app)


PAYLOAD = {
    "area": {"value": "5", "unit": "donum"},
    "yield_total": {"value": "2", "unit": "ton"},
    "price": {"value": "10", "unit": "tl_kg"},
    "cost": {"value": "5000", "unit": "tl"},
}


def test_a_budget_question_returns_a_form(client):
    resp = client.post("/api/chat", json={"message": BUDGET_Q, "history": []})
    assert resp.status_code == 200
    body = resp.json()
    assert body["form"] is not None
    assert body["recommended_products"] == []
    assert body["answer"]


def test_a_submitted_payload_is_computed(client):
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "budget": PAYLOAD})
    body = resp.json()
    assert body["form"] is None
    assert "15.000,00 TL" in body["answer"]


def test_an_invalid_value_is_a_field_error_not_a_422(client):
    """A bad number is a user typo, not a client bug. It must come back on the
    field, inside a 200, rather than as a validation failure mid-conversation."""
    bad = dict(PAYLOAD, price={"value": "on lira", "unit": "tl_kg"})
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "budget": bad})
    assert resp.status_code == 200
    errors = {f["id"]: f["error"] for f in resp.json()["form"]["fields"]}
    assert errors["price"] is not None


def test_a_boolean_value_is_a_field_error_not_a_silent_one(client):
    """A JSON `true` must not be coerced into 1 of whatever unit; it must
    come back as a field error, same as any other bad value."""
    bad = dict(PAYLOAD, area={"value": True, "unit": "donum"})
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "budget": bad})
    assert resp.status_code == 200
    body = resp.json()
    errors = {f["id"]: f["error"] for f in body["form"]["fields"]}
    assert errors["area"] is not None
    assert "TL" not in body["answer"]


def test_a_structurally_wrong_body_is_still_a_422(client):
    """A genuine client bug must stay loud."""
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "budget": "five donum"})
    assert resp.status_code == 422


def test_an_empty_submitted_form_reports_its_required_fields(client):
    """`budget: {}` must read as a genuine empty submission, not an unopened
    form. It reaches validate() as an all-None BudgetPayload.model_dump() -
    an incidental fact of a different file that switching to
    exclude_none=True someday would silently break."""
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "budget": {}})
    assert resp.status_code == 200
    errors = {f["id"]: f["error"] for f in resp.json()["form"]["fields"]}
    assert errors["area"] is not None
    assert errors["yield_total"] is not None
    assert errors["price"] is not None


def test_a_request_without_a_budget_field_still_works(client):
    """The deployed APK never sends one."""
    resp = client.post("/api/chat", json={"message": BUDGET_Q})
    assert resp.status_code == 200


def test_the_streaming_endpoint_carries_the_form_event(client):
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "stream": True})
    assert resp.status_code == 200
    types = [json.loads(line[6:])["type"]
             for line in resp.text.split("\n") if line.startswith("data: ")]
    assert types == ["token", "form", "done"]


def test_a_payload_carrying_a_source_is_accepted(client):
    payload = dict(PAYLOAD)
    payload["yield_total"] = {"value": "2", "unit": "ton", "source": "norm"}
    response = client.post("/api/chat",
                           json={"message": BUDGET_Q, "budget": payload})
    assert response.status_code == 200


def test_a_payload_with_no_source_is_still_accepted(client):
    """An already-deployed build sends none. It must not 422 mid-conversation."""
    response = client.post("/api/chat",
                           json={"message": BUDGET_Q, "budget": PAYLOAD})
    assert response.status_code == 200


def test_the_streaming_endpoint_forwards_a_submitted_payload(client):
    resp = client.post("/api/chat", json={
        "message": BUDGET_Q, "history": [], "stream": True, "budget": PAYLOAD})
    text = "".join(json.loads(line[6:]).get("content", "")
                   for line in resp.text.split("\n")
                   if line.startswith("data: "))
    assert "15.000,00 TL" in text
