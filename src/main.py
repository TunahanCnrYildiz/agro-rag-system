"""Unified FastAPI server for the Agro-Botany RAG system.

Serves both the mobile app and the web widget from a single ``/api/chat``
endpoint, which supports either a unified JSON response or a streaming
Server-Sent-Events response.

Run::

    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    # or:  python -m src.main
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:
    from .config import settings, PRODUCTS_JSON
    from .articles_scraper import ARTICLES_JSON
    from . import engine
except ImportError:  # pragma: no cover
    from config import settings, PRODUCTS_JSON  # type: ignore
    from articles_scraper import ARTICLES_JSON  # type: ignore
    import engine  # type: ignore


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
class ChatTurn(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user query.")
    history: list[ChatTurn] = Field(default_factory=list)
    stream: bool = Field(
        default=False, description="If true, respond with an SSE token stream."
    )


class ProductOut(BaseModel):
    title: str
    link: str


class ChatResponse(BaseModel):
    answer: str
    recommended_products: list[ProductOut]


class CatalogProduct(BaseModel):
    product_name: str
    description: str
    category: str
    source_url: str
    image_url: str = ""


class ArticleOut(BaseModel):
    title: str
    excerpt: str
    category: str
    date: str
    source_url: str
    image_url: str = ""
    content: str = ""


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
app = FastAPI(
    title="Agro-Botany RAG & Product Linker",
    version="0.1.0",
    description=(
        "Expert Agricultural Engineer chatbot: organic plant nutrition advice "
        "grounded in botany references, with linked company products."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": settings.chat_model}


@app.get("/api/products", response_model=list[CatalogProduct])
def products(category: str | None = None):
    """Real product catalog scraped from ekolojiktarim.com.tr (src/scraper.py).
    Optionally filter by exact category name."""
    if not PRODUCTS_JSON.exists():
        raise HTTPException(status_code=503, detail="Product catalog not available yet.")
    data = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    if category:
        data = [p for p in data if p.get("category") == category]
    return data


@app.get("/api/articles", response_model=list[ArticleOut])
def articles(category: str | None = None):
    """Tarim Akademisi articles scraped from ekolojiktarim.com.tr
    (src/articles_scraper.py). Optionally filter by exact category name."""
    if not ARTICLES_JSON.exists():
        raise HTTPException(status_code=503, detail="Articles not available yet.")
    data = json.loads(ARTICLES_JSON.read_text(encoding="utf-8"))
    if category:
        data = [a for a in data if a.get("category") == category]
    return data


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Primary endpoint. Returns unified JSON, or an SSE stream when
    ``stream=true``."""
    history = [t.model_dump() for t in req.history]

    if req.stream:
        return StreamingResponse(
            engine.stream_answer(req.message, history),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result = engine.answer(req.message, history)
    return ChatResponse(**result.as_api())


def main() -> None:
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
