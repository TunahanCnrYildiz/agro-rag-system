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
_TURKISH_HINT = re.compile(r"[çÇğĞıİöÖşŞüÜ]")

# Function words unlikely to collide with common English words (excludes
# e.g. "her", "kim", "once", "mi" which are also everyday English tokens/names).
_TURKISH_STOPWORDS = {
    "bir", "ve", "bu", "su", "cok", "gibi", "icin", "için", "ile", "ama",
    "fakat", "ancak", "veya", "degil", "değil", "var", "yok",
    "nasil", "nasıl", "neden", "nicin", "niçin", "nerede",
    "iyi", "kotu", "kötü", "buyuk", "büyük", "kucuk", "küçük",
    "sonra", "simdi", "şimdi", "tum", "tüm", "kendi", "benim", "senin",
    "lutfen", "lütfen", "merhaba", "selam", "tesekkur", "teşekkür",
    "evet", "hayir", "hayır", "mumkun", "mümkün", "gerek", "lazim", "lazım",
}

# Agriculture/botany word stems, matched as token prefixes so suffixed forms
# (yapraklarim, topragim, sarariyor, ...) are caught even without diacritics.
_TURKISH_STEMS = (
    "yapra", "topra", "gubre", "gübre", "bitki", "sarar", "sari", "sarı",
    "besin", "domates", "cice", "çiçe", "tohum", "hastal", "zararl", "sera",
    "meyve", "sebze", "urun", "ürün", "hasat", "ekim", "sulama", "mahsul",
    "verim",
)


def detect_language(text: str) -> str:
    """Return a coarse language hint ('Turkish' / 'English') used only to
    nudge the model; the model still does its own detection."""
    if _TURKISH_HINT.search(text):
        return "Turkish"
    tokens = re.findall(r"[a-zA-ZçÇğĞıİöÖşŞüÜ]+", text.lower())
    if set(tokens) & _TURKISH_STOPWORDS:
        return "Turkish"
    if any(t.startswith(stem) for t in tokens for stem in _TURKISH_STEMS):
        return "Turkish"
    return "English"


# --------------------------------------------------------------------------- #
# Product catalog matching (embedding-based, language-agnostic)
# --------------------------------------------------------------------------- #
# Below this cosine similarity, a product is considered unrelated to the query
# rather than forced into the top-k. Tuned empirically against bge-m3.
MIN_PRODUCT_SIMILARITY = 0.35


@lru_cache(maxsize=1)
def _get_embeddings_client():
    try:
        from .ingest import get_embeddings
    except ImportError:
        from ingest import get_embeddings  # type: ignore
    return get_embeddings()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@lru_cache(maxsize=1)
def _load_products() -> tuple[dict, ...]:
    """Load the catalog and embed each product's text blob once."""
    if not PRODUCTS_JSON.exists():
        print(f"[engine] product catalog not found at {PRODUCTS_JSON}")
        return ()
    try:
        data = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[engine] could not read product catalog: {exc}")
        return ()
    if not data:
        return ()

    blobs = [
        " ".join(str(p.get(k, "")) for k in ("product_name", "description", "category"))
        for p in data
    ]
    try:
        embeddings = _get_embeddings_client().embed_documents(blobs)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] product embedding failed: {exc}")
        return ()

    return tuple({**p, "_embedding": emb} for p, emb in zip(data, embeddings))


def match_products(query: str, botany_context: str = "", k: int | None = None) -> list[RecommendedProduct]:
    """Rank catalog products by embedding similarity to the query, so matches
    work regardless of the query's language versus the (Turkish) catalog.

    Requires non-empty botany_context (i.e. retrieval already found the query
    on-topic) - otherwise there's nothing to genuinely ground a recommendation
    in, so we return no products rather than guess from the query alone.
    """
    k = k or settings.product_match_k
    if not botany_context or not botany_context.strip():
        return []
    products = _load_products()
    if not products:
        return []

    embed_input = f"{query}\n{botany_context[:1000]}"
    try:
        query_embedding = _get_embeddings_client().embed_query(embed_input)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] query embedding failed: {exc}")
        return []

    scored = [(_cosine(query_embedding, p["_embedding"]), p) for p in products]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RecommendedProduct(title=p["product_name"], link=p["source_url"])
        for score, p in scored[:k]
        if score >= MIN_PRODUCT_SIMILARITY
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


# Below this relevance score, a retrieved chunk is treated as noise (the
# vector store always returns its k nearest neighbors, even for off-topic
# queries). On-topic queries have consistently scored ~0.38+; some generic
# off-topic phrasings ("bilgisayar ile ilgili bilgi ver") can drift up to
# ~0.34 against administrative/boilerplate scan text, so 0.30 wasn't quite
# enough margin - raised to sit clearly between the two.
MIN_RETRIEVAL_RELEVANCE = 0.36


def retrieve_context(query: str, k: int | None = None) -> str:
    """Return concatenated botany chunks relevant to the query, or an empty
    string if nothing clears the relevance threshold (i.e. off-topic)."""
    k = k or settings.retrieval_k
    store = _get_retriever_store()
    if store is None:
        return ""
    try:
        results = store.similarity_search_with_relevance_scores(query, k=k)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] retrieval failed: {exc}")
        return ""

    parts: list[str] = []
    for d, score in results:
        if score < MIN_RETRIEVAL_RELEVANCE:
            continue
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
def _sampling_kwargs() -> dict:
    """Shared generation params. top_p is a standard OpenAI field; min_p and
    repeat_penalty are LM Studio extensions passed via extra_body."""
    return {
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "max_tokens": settings.max_tokens,
        "extra_body": {
            "min_p": settings.min_p,
            "repeat_penalty": settings.repeat_penalty,
        },
    }


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
            stream=False,
            **_sampling_kwargs(),
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
            stream=True,
            **_sampling_kwargs(),
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
