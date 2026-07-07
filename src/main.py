"""Unified FastAPI server for the Agro-Botany RAG system.

Serves both the mobile app and the web widget from a single ``/api/chat``
endpoint, which supports either a unified JSON response or a streaming
Server-Sent-Events response.

Run::

    uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    # or:  python -m src.main
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

try:
    from .config import settings
    from . import engine
except ImportError:  # pragma: no cover
    from config import settings  # type: ignore
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
