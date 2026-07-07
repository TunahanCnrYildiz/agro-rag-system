"""Core RAG query engine.

Retrieves botany chunks from Chroma, matches catalog products, builds the system
prompt (persona + guardrails + language rule), and calls the LM Studio chat
model. If the vector store or LM Studio is down it falls back instead of
erroring, so the API stays up.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator

from openai import OpenAI

try:
    from .config import (
        PRODUCTS_JSON,
        SYSTEM_PROMPT,
        build_language_instruction,
        settings,
    )
except ImportError:  # pragma: no cover
    from config import (  # type: ignore
        PRODUCTS_JSON,
        SYSTEM_PROMPT,
        build_language_instruction,
        settings,
    )


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class RecommendedProduct:
    title: str
    link: str

    def as_api(self) -> dict:
        return {"title": self.title, "link": self.link}


@dataclass
class ChatResult:
    answer: str
    recommended_products: list[RecommendedProduct]

    def as_api(self) -> dict:
        return {
            "answer": self.answer,
            "recommended_products": [p.as_api() for p in self.recommended_products],
        }


# --------------------------------------------------------------------------- #
# Language detection (lightweight, dependency-free)
# --------------------------------------------------------------------------- #
_TURKISH_HINT = re.compile(r"[çğıöşü]", re.IGNORECASE)
_TURKISH_WORDS = {
    "bitki", "toprak", "gübre", "gubre", "yaprak", "sarar", "besin",
    "nasıl", "nasil", "neden", "için", "icin", "ve", "bir", "sulama",
}


def detect_language(text: str) -> str:
    """Return a coarse language hint ('Turkish' / 'English') used only to
    nudge the model; the model still does its own detection."""
    lowered = text.lower()
    if _TURKISH_HINT.search(text):
        return "Turkish"
    tokens = set(re.findall(r"[a-zçğıöşü]+", lowered))
    if tokens & _TURKISH_WORDS:
        return "Turkish"
    return "English"


# --------------------------------------------------------------------------- #
# Product catalog matching
# --------------------------------------------------------------------------- #
_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "is", "are",
    "my", "how", "what", "why", "ve", "bir", "icin", "için", "nasil", "nasıl",
    "neden", "ile", "bu", "da", "de", "mi", "mı",
}


def _tokenize(text: str) -> set[str]:
    tokens = re.findall(r"[a-zçğıöşü0-9]+", text.lower())
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


@lru_cache(maxsize=1)
def _load_products() -> tuple[dict, ...]:
    """Load and cache the scraped product catalog. Returns () if missing."""
    if not PRODUCTS_JSON.exists():
        print(f"[engine] product catalog not found at {PRODUCTS_JSON}")
        return ()
    try:
        data = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[engine] could not read product catalog: {exc}")
        return ()
    # Pre-compute a searchable token blob per product.
    enriched: list[dict] = []
    for p in data:
        blob = " ".join(
            str(p.get(k, ""))
            for k in ("product_name", "description", "category")
        )
        enriched.append({**p, "_tokens": _tokenize(blob)})
    return tuple(enriched)


def match_products(query: str, botany_context: str = "", k: int | None = None) -> list[RecommendedProduct]:
    """Score catalog products against the user's query (+ retrieved context)
    using token overlap. Purely lexical => fast and fully offline."""
    k = k or settings.product_match_k
    products = _load_products()
    if not products:
        return []

    query_tokens = _tokenize(query) | _tokenize(botany_context)
    if not query_tokens:
        return []

    scored: list[tuple[float, dict]] = []
    for p in products:
        overlap = query_tokens & p["_tokens"]
        if not overlap:
            continue
        # Weight name/category hits a little higher via a simple length-norm.
        score = len(overlap) / (1 + len(p["_tokens"]) ** 0.5)
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RecommendedProduct(title=p["product_name"], link=p["source_url"])
        for _, p in scored[:k]
    ]


# --------------------------------------------------------------------------- #
# Botany retrieval
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _get_retriever_store():
    """Open the Chroma store once. Returns None if it's unavailable (langchain
    not installed, or nothing ingested yet) so callers can fall back."""
    try:
        try:
            from .ingest import get_vector_store  # type: ignore
        except ImportError:
            from ingest import get_vector_store  # type: ignore
        return get_vector_store()
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] vector store unavailable: {exc}")
        return None


def retrieve_context(query: str, k: int | None = None) -> str:
    """Return concatenated botany chunks relevant to the query."""
    k = k or settings.retrieval_k
    store = _get_retriever_store()
    if store is None:
        return ""
    try:
        docs = store.similarity_search(query, k=k)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] retrieval failed: {exc}")
        return ""

    parts: list[str] = []
    for d in docs:
        src = d.metadata.get("source", "?")
        page = d.metadata.get("page", "?")
        parts.append(f"[Kaynak: {src}, s.{page}]\n{d.page_content}")
    return "\n\n---\n\n".join(parts)


# --------------------------------------------------------------------------- #
# LLM client
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _get_llm() -> OpenAI:
    return OpenAI(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        timeout=settings.request_timeout,
    )


def _build_messages(
    message: str,
    history: list[dict] | None,
    context: str,
    products: list[RecommendedProduct],
) -> list[dict]:
    language_hint = detect_language(message)
    products_block = (
        "\n".join(f"- {p.title} -> {p.link}" for p in products)
        if products
        else "(no candidate products)"
    )
    system_content = SYSTEM_PROMPT.format(
        language_instruction=build_language_instruction(language_hint),
        context=context or "(no botany context retrieved)",
        products=products_block,
    )

    messages: list[dict] = [{"role": "system", "content": system_content}]
    # Carry prior turns for conversational continuity.
    for turn in history or []:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return messages


# --------------------------------------------------------------------------- #
# Public API: full (unified) and streaming answers
# --------------------------------------------------------------------------- #
def answer(message: str, history: list[dict] | None = None) -> ChatResult:
    """Retrieve, match products, and produce a unified JSON-ready result."""
    context = retrieve_context(message)
    products = match_products(message, context)
    messages = _build_messages(message, history, context, products)

    try:
        client = _get_llm()
        completion = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            stream=False,
        )
        answer_text = completion.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        answer_text = (
            "Uzgunum, su anda dil modeline (LM Studio) ulasamiyorum. "
            "Lutfen yerel sunucunun calistigindan emin olun. "
            f"(teknik detay: {exc})"
        )

    return ChatResult(answer=answer_text.strip(), recommended_products=products)


def stream_answer(
    message: str, history: list[dict] | None = None
) -> Iterator[str]:
    """Yield Server-Sent-Event lines. First event carries product metadata,
    subsequent events stream the answer text token-by-token."""
    context = retrieve_context(message)
    products = match_products(message, context)
    messages = _build_messages(message, history, context, products)

    # Emit product recommendations up front so clients can render them early.
    yield _sse(
        {"type": "products", "recommended_products": [p.as_api() for p in products]}
    )

    try:
        client = _get_llm()
        stream = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield _sse({"type": "token", "content": delta})
    except Exception as exc:  # noqa: BLE001
        yield _sse(
            {
                "type": "token",
                "content": (
                    "Uzgunum, dil modeline ulasamiyorum. LM Studio calisiyor mu? "
                    f"(teknik detay: {exc})"
                ),
            }
        )

    yield _sse({"type": "done"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# --------------------------------------------------------------------------- #
# Manual smoke test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "Domates yapraklari sararıyor, ne yapabilirim?"
    print(f"Q: {q}\n")
    result = answer(q)
    print("ANSWER:\n", result.answer, "\n")
    print("PRODUCTS:")
    for p in result.recommended_products:
        print(f"  - {p.title}: {p.link}")
