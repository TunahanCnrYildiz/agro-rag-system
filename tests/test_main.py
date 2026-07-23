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
    monkeypatch.setattr(main.engine, "answer", lambda msg, hist: fake)
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
                        lambda msg, hist: iter(['data: {"type": "done"}\n\n']))
    r = client.post("/api/chat", json={"message": "soru", "stream": True})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]


def test_products_503_when_catalog_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "PRODUCTS_JSON", tmp_path / "nope.json")
    r = client.get("/api/products")
    assert r.status_code == 503


def test_health_reports_the_active_provider_but_never_the_key():
    r = client.get("/health")
    body = r.json()

    assert r.status_code == 200
    assert body["status"] == "ok"
    assert body["provider"] in ("local", "openrouter")
    assert body["model"]
    # The key must never leave the server, in any field.
    assert "key" not in " ".join(body.keys()).lower()
