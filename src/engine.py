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
# rather than forced into the top-k. Tuned empirically against bge-m3; kept
# fairly strict so only products that genuinely match the answer are shown
# (better to recommend none than something off-topic).
MIN_PRODUCT_SIMILARITY = 0.45


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

    Relevance is gated by MIN_PRODUCT_SIMILARITY alone: only products that
    genuinely match the query clear the threshold, so off-topic questions
    naturally get none. Retrieved botany_context, when present, is folded into
    the embedding to sharpen the match, but its absence no longer suppresses
    recommendations - an explicit on-topic request ("Fındık için gübre önerir
    misin?") should still surface products even when the reference books don't
    happen to cover that exact crop.
    """
    k = k or settings.product_match_k
    products = _load_products()
    if not products:
        return []

    embed_input = f"{query}\n{botany_context[:1000]}" if botany_context.strip() else query
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


def _translate_query(query: str, target_lang: str) -> str:
    """Translate a search query to target_lang via the chat model (output-only,
    deterministic). Raises on LLM error - the caller handles the fallback."""
    prompt = (
        f"Translate this agriculture/botany search query to {target_lang}. "
        f"Output ONLY the translation, no quotes, no notes.\n\nQuery: {query}"
    )
    client = _get_llm()
    completion = client.chat.completions.create(
        model=settings.chat_model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
        temperature=0.0,
        # Reasoning-capable local builds (e.g. Gemma QAT) spend tokens "thinking"
        # before the visible answer, so a tight budget returns empty/truncated
        # content with finish_reason="length"; 512 reliably leaves room for the
        # reasoning + the short translation across query lengths (verified 2026-07-16).
        max_tokens=512,
    )
    return (completion.choices[0].message.content or "").strip()


def _expand_query(query: str) -> list[str]:
    """Return [query, translation] to bridge the TR/EN corpus split, or [query]
    if cross-lingual retrieval is off or the translation is unavailable/a no-op.

    The corpus is ~half Turkish (dp_) and ~half English (ia_/oa_/fao_); bge-m3
    scores cross-lingual matches lower, so a Turkish query about English-covered
    content can fall below the relevance floor. Searching the translated query
    too, then fusing, lets each query reach the other language's chunks.
    """
    if not settings.cross_lingual_retrieval:
        return [query]
    target = "English" if detect_language(query) == "Turkish" else "Turkish"
    try:
        translated = _translate_query(query, target)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] query translation failed: {exc}")
        return [query]
    if not translated or translated.strip().lower() == query.strip().lower():
        return [query]
    return [query, translated]


def _fuse(result_lists, floor: float, k: int):
    """Merge per-query result lists: dedup by chunk text keeping the max score,
    drop anything below the floor, return the top-k by score."""
    best: dict[str, tuple] = {}
    for results in result_lists:
        for doc, score in results:
            key = doc.page_content
            if key not in best or score > best[key][1]:
                best[key] = (doc, score)
    ranked = sorted(best.values(), key=lambda x: x[1], reverse=True)
    return [(d, s) for d, s in ranked if s >= floor][:k]


def _search(store, query: str, k: int):
    """Vector search wrapper that returns [] instead of raising."""
    try:
        return store.similarity_search_with_relevance_scores(query, k=k)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] retrieval failed: {exc}")
        return []


def retrieve_context(query: str, k: int | None = None) -> str:
    """Return concatenated botany chunks relevant to the query, or "" if nothing
    clears the floor.

    Cross-lingual rescue is CONDITIONAL: we first search in the query's own
    language, and only translate + re-search + fuse when that under-fills the
    context (fewer than k chunks clear the floor). That is the TR/EN gap case;
    well-covered queries skip the (slow, local-LLM) translation entirely.
    """
    k = k or settings.retrieval_k
    store = _get_retriever_store()
    if store is None:
        return ""

    primary = _search(store, query, k)
    kept = [(d, s) for d, s in primary if s >= MIN_RETRIEVAL_RELEVANCE]

    result_lists = [primary]
    if settings.cross_lingual_retrieval and len(kept) < k:
        # under-filled: bring in the other-language content via translation.
        for translated in _expand_query(query)[1:]:
            result_lists.append(_search(store, translated, k))

    parts: list[str] = []
    for d, _score in _fuse(result_lists, MIN_RETRIEVAL_RELEVANCE, k):
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


def _llm_unavailable_message(exc: Exception) -> str:
    """User-facing fallback shown when the LM Studio chat model can't be
    reached, so both the unified and streaming paths return the same wording."""
    return (
        "Uzgunum, su anda dil modeline (LM Studio) ulasamiyorum. "
        "Lutfen yerel sunucunun calistigindan emin oldugunuzu kontrol edin. "
        f"(teknik detay: {exc})"
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


# The model prefixes off-scope refusals with this marker (see SYSTEM_PROMPT) so
# we can strip it and drop product suggestions - recommending catalog products
# under a "that's outside my scope" reply would be incoherent.
_OFFSCOPE_MARKER = "[OFFSCOPE]"


def _strip_offscope(text: str) -> tuple[str, bool]:
    """Return (clean_text, is_off_scope). Detects the leading off-scope marker
    (case-insensitive) and removes it along with any trailing separators."""
    lead = text.lstrip()
    if lead[: len(_OFFSCOPE_MARKER)].upper() == _OFFSCOPE_MARKER:
        return lead[len(_OFFSCOPE_MARKER):].lstrip(" :\n\t"), True
    return text, False


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
        answer_text = _llm_unavailable_message(exc)

    answer_text, off_scope = _strip_offscope(answer_text)
    if off_scope:
        products = []  # no product suggestions under an off-scope refusal
    return ChatResult(answer=answer_text.strip(), recommended_products=products)


def stream_answer(
    message: str, history: list[dict] | None = None
) -> Iterator[str]:
    """Yield Server-Sent-Event lines. Answer text streams token-by-token first;
    once it's complete a single event carries the product recommendations, then
    a final 'done' event closes the stream."""
    context = retrieve_context(message)
    products = match_products(message, context)
    messages = _build_messages(message, history, context, products)

    # Buffer the opening tokens so we can detect+strip a leading [OFFSCOPE]
    # marker before streaming it to the client, and drop products if present.
    off_scope = False
    buffer = ""
    checked = False
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
            if not delta:
                continue
            if checked:
                yield _sse({"type": "token", "content": delta})
                continue
            buffer += delta
            # Decide once we have enough leading text to (dis)confirm the marker.
            if len(buffer.lstrip()) >= len(_OFFSCOPE_MARKER) or len(buffer) > 40:
                clean, off_scope = _strip_offscope(buffer)
                checked = True
                if clean:
                    yield _sse({"type": "token", "content": clean})
                buffer = ""
    except Exception as exc:  # noqa: BLE001
        yield _sse({"type": "token", "content": _llm_unavailable_message(exc)})
    # Flush any leftover (very short answers that never hit the decision point).
    if not checked and buffer:
        clean, off_scope = _strip_offscope(buffer)
        if clean:
            yield _sse({"type": "token", "content": clean})

    # Emit product recommendations only after the full answer has streamed (and
    # only for in-scope answers), so clients render them beneath the reply.
    if not off_scope:
        yield _sse(
            {"type": "products",
             "recommended_products": [p.as_api() for p in products]}
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
