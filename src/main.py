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


class BudgetField(BaseModel):
    # Deliberately loose: a text input produces strings, and src/budget.py does
    # the real checking. A bad value must come back as a field error inside a
    # 200, not as a 422 in the middle of a conversation. bool is listed here
    # too: without it, Pydantic's smart union coerces a JSON `true` into the
    # int 1 before src/budget.py ever sees it, defeating the bool guard there
    # and silently turning it into 1 of whatever unit. Listing bool keeps the
    # value a bool so that guard can reject it as a field error instead.
    value: str | int | float | bool = ""
    unit: str = ""
    # Which figures the client prefilled from the norm table and the user left
    # alone. The server does not take this on trust - see budget._verify - but
    # it cannot ask the client after the fact either. Defaulting to "user" keeps
    # an already-deployed build, which sends nothing here, on P1's framing.
    source: str = "user"


class BudgetPayload(BaseModel):
    area: BudgetField | None = None
    yield_total: BudgetField | None = None
    price: BudgetField | None = None
    cost: BudgetField | None = None
    crop: str | None = None


class DoseField(BaseModel):
    # Loose at the wire for the same reason BudgetField is, bool included: it
    # must reach src/dose_answer.py as a bool so the guard there can reject it,
    # rather than being smart-unioned into the int 1 on the way.
    value: str | int | float | bool = ""
    unit: str = ""


class DosePayload(BaseModel):
    product: str | None = None
    group: str | None = None
    area: DoseField | None = None


class ComparePayload(BaseModel):
    first: str | None = None
    second: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user query.")
    history: list[ChatTurn] = Field(default_factory=list)
    stream: bool = Field(
        default=False, description="If true, respond with an SSE token stream."
    )
    budget: BudgetPayload | None = Field(
        default=None, description="Filled budget form, when the user submitted one."
    )
    dose: DosePayload | None = Field(
        default=None, description="Filled product-dose card, when the user submitted one."
    )
    compare: ComparePayload | None = Field(
        default=None, description="Filled crop-comparison card, when the user submitted one."
    )


class ProductOut(BaseModel):
    title: str
    link: str


class ChatResponse(BaseModel):
    answer: str
    recommended_products: list[ProductOut]
    # Optional so an already-deployed client, which never reads it, is unaffected.
    form: dict | None = None
    # Optional so an already-deployed client, which never reads it, is unaffected.
    dose_form: dict | None = None
    # Optional so an already-deployed client, which never reads it, is unaffected.
    compare_form: dict | None = None


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
        "Advisory plant-science chatbot: organic plant nutrition guidance "
        "grounded in botany references, with linked company products. Answers "
        "in the style of an agricultural engineer; it is an AI, not a licensed "
        "professional."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _warn_if_open_cors(origins: list[str]) -> None:
    """One-time startup reminder when CORS is wide open. Fine for local/dev; a
    public deploy should narrow CORS_ALLOW_ORIGINS to the real site origins."""
    if origins == ["*"]:
        print(
            "[main] WARNING: CORS_ALLOW_ORIGINS='*' allows all origins - fine for "
            "local/dev, but narrow it before a public deploy."
        )


_warn_if_open_cors(settings.cors_origins_list)


@app.get("/health")
def health() -> dict:
    # The model comes from the active profile, not settings.chat_model, so this
    # tells the truth in hosted mode too. The API key is never included.
    return {
        "status": "ok",
        "provider": settings.chat_provider,
        "model": engine._chat_profile().model,
    }


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
    budget_payload = req.budget.model_dump() if req.budget else None
    dose_payload = req.dose.model_dump() if req.dose else None
    compare_payload = req.compare.model_dump() if req.compare else None

    if req.stream:
        return StreamingResponse(
            engine.stream_answer(req.message, history, budget_payload,
                                 dose_payload, compare_payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result = engine.answer(req.message, history, budget_payload, dose_payload,
                           compare_payload)
    return ChatResponse(**result.as_api())


def main() -> None:
    import uvicorn

    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
