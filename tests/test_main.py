"""API tests for the FastAPI app (engine is monkeypatched; no LLM/store)."""

from fastapi.testclient import TestClient

from src import main
from src.engine import ChatResult, RecommendedProduct

client = TestClient(main.app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_unified(monkeypatch):
    fake = ChatResult(answer="cevap metni",
                      recommended_products=[RecommendedProduct("P", "url")])
    # Mirrors engine.answer's real signature, which grew an optional budget
    # payload: a stub narrower than the code under test fails as a TypeError
    # that reads like a routing bug rather than a stale double.
    monkeypatch.setattr(main.engine, "answer",
                        lambda msg, hist, budget=None, dose=None, compare=None: fake)
    r = client.post("/api/chat", json={"message": "soru", "stream": False})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "cevap metni"
    assert body["recommended_products"] == [{"title": "P", "link": "url"}]


def test_chat_rejects_empty_message():
    r = client.post("/api/chat", json={"message": "", "stream": False})
    assert r.status_code == 422  # min_length=1 validation


def test_chat_stream_sets_sse_content_type(monkeypatch):
    monkeypatch.setattr(main.engine, "stream_answer",
                        lambda msg, hist, budget=None, dose=None, compare=None:
                        iter(['data: {"type": "done"}\n\n']))
    r = client.post("/api/chat", json={"message": "soru", "stream": True})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]


def test_products_503_when_catalog_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "PRODUCTS_JSON", tmp_path / "nope.json")
    r = client.get("/api/products")
    assert r.status_code == 503


def test_health_reports_the_active_provider_but_never_the_key(monkeypatch):
    """local branch: the key never enters the profile here at all, so this only
    proves /health doesn't dump unrelated settings wholesale."""
    sentinel = "sk-or-SENTINEL-DO-NOT-LEAK"
    monkeypatch.setattr(main.settings, "chat_provider", "local")
    monkeypatch.setattr(main.settings, "openrouter_api_key", sentinel)

    r = client.get("/health")
    body = r.json()

    assert r.status_code == 200
    assert body["status"] == "ok"
    assert body["provider"] == "local"
    assert body["model"]
    # No field is literally named "key" ...
    assert "key" not in " ".join(body.keys()).lower()
    # ... and the actual key value never appears anywhere in the raw
    # response body, no matter which field it might hide behind.
    assert sentinel not in r.text


def test_health_on_openrouter_never_leaks_the_active_key(monkeypatch):
    """The branch the local-only test above cannot exercise: with
    chat_provider=openrouter the sentinel key genuinely IS the active
    credential used to build the profile, not an inert unrelated setting."""
    sentinel = "sk-or-SENTINEL-DO-NOT-LEAK"
    monkeypatch.setattr(main.settings, "chat_provider", "openrouter")
    monkeypatch.setattr(main.settings, "openrouter_model", "vendor/model-x")
    monkeypatch.setattr(main.settings, "openrouter_api_key", sentinel)

    r = client.get("/health")
    body = r.json()

    assert r.status_code == 200
    assert body["status"] == "ok"
    assert body["provider"] == "openrouter"
    assert body["model"] == "vendor/model-x"
    assert "key" not in " ".join(body.keys()).lower()
    assert sentinel not in r.text


def test_warn_if_open_cors_warns_on_wildcard(capsys):
    main._warn_if_open_cors(["*"])
    out = capsys.readouterr().out
    assert "WARNING" in out and "CORS" in out


def test_warn_if_open_cors_silent_when_narrowed(capsys):
    main._warn_if_open_cors(["https://example.com"])
    assert capsys.readouterr().out == ""


def test_a_dose_card_reaches_the_json_transport(monkeypatch):
    monkeypatch.setattr(
        main.engine, "answer",
        lambda msg, hist, budget=None, dose=None, compare=None:
            ChatResult(answer="x", recommended_products=[],
                       dose_form={"kind": "product_dose"}))
    body = client.post("/api/chat", json={"message": "doz"}).json()
    assert body["dose_form"] == {"kind": "product_dose"}


def test_a_submitted_dose_payload_reaches_the_engine(monkeypatch):
    seen = {}

    def fake(msg, hist, budget=None, dose=None, compare=None):
        seen["dose"] = dose
        return ChatResult(answer="x", recommended_products=[])

    monkeypatch.setattr(main.engine, "answer", fake)
    client.post("/api/chat", json={
        "message": "doz",
        "dose": {"product": "HİGRO FUBBY", "group": "sebze",
                 "area": {"value": "5", "unit": "donum"}}})
    assert seen["dose"]["product"] == "HİGRO FUBBY"
    assert seen["dose"]["area"]["value"] == "5"


def test_a_boolean_area_survives_the_wire_as_a_boolean(monkeypatch):
    """The budget form's own lesson: a guard is worthless if a layer above it
    launders the value first. Pydantic's smart union would turn a JSON `true`
    into the int 1 before src/dose_answer.py ever saw it."""
    seen = {}

    def fake(msg, hist, budget=None, dose=None, compare=None):
        seen["dose"] = dose
        return ChatResult(answer="x", recommended_products=[])

    monkeypatch.setattr(main.engine, "answer", fake)
    client.post("/api/chat", json={
        "message": "doz",
        "dose": {"product": "X", "group": "sebze",
                 "area": {"value": True, "unit": "donum"}}})
    assert seen["dose"]["area"]["value"] is True


def test_a_comparison_card_reaches_the_json_transport(monkeypatch):
    monkeypatch.setattr(
        main.engine, "answer",
        lambda msg, hist, budget=None, dose=None, compare=None:
            ChatResult(answer="x", recommended_products=[],
                       compare_form={"kind": "crop_compare"}))
    body = client.post("/api/chat", json={"message": "karşılaştır"}).json()
    assert body["compare_form"] == {"kind": "crop_compare"}


def test_a_submitted_comparison_payload_reaches_the_engine(monkeypatch):
    seen = {}

    def fake(msg, hist, budget=None, dose=None, compare=None):
        seen["compare"] = compare
        return ChatResult(answer="x", recommended_products=[])

    monkeypatch.setattr(main.engine, "answer", fake)
    client.post("/api/chat", json={
        "message": "karşılaştır",
        "compare": {"first": "domates (sofralik)", "second": "arpa (biralik)"}})
    assert seen["compare"]["first"] == "domates (sofralik)"


def test_the_chat_endpoint_refuses_once_the_ceiling_is_crossed(monkeypatch):
    """The endpoint is public and unauthenticated, so the ceiling is the only
    thing standing between a script and the model bill."""
    from src import rate_limit
    monkeypatch.setattr(main, "_chat_limit", rate_limit.SlidingWindowLimit(2))
    fake = ChatResult(answer="cevap", recommended_products=[])
    monkeypatch.setattr(main.engine, "answer",
                        lambda msg, hist, budget=None, dose=None, compare=None: fake)
    body = {"message": "soru", "stream": False}
    assert client.post("/api/chat", json=body).status_code == 200
    assert client.post("/api/chat", json=body).status_code == 200
    refused = client.post("/api/chat", json=body)
    assert refused.status_code == 429
    assert "istek" in refused.json()["detail"].lower()


def test_the_catalog_routes_are_not_rate_limited(monkeypatch):
    """The ceiling guards the expensive path. These read a JSON file: no model
    call, no money, and throttling them would only break the app's browsing."""
    from src import rate_limit
    monkeypatch.setattr(main, "_chat_limit", rate_limit.SlidingWindowLimit(1))
    for _ in range(5):
        assert client.get("/api/products").status_code in (200, 503)
        assert client.get("/api/articles").status_code in (200, 503)


def test_the_active_ceiling_is_announced_at_startup(capsys):
    from src import rate_limit
    main._announce_rate_limit(rate_limit.SlidingWindowLimit(60))
    out = capsys.readouterr().out
    assert "60" in out and "/api/chat" in out


def test_a_disabled_ceiling_is_announced_as_a_warning(capsys):
    """Silence would make an unlimited public endpoint the quiet option."""
    from src import rate_limit
    main._announce_rate_limit(rate_limit.SlidingWindowLimit(0))
    out = capsys.readouterr().out
    assert "WARNING" in out
