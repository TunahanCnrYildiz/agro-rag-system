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
from datetime import date
from functools import lru_cache
from typing import Iterator

from openai import OpenAI

try:
    from .config import (
        EmbeddingModelMismatchError,
        PRODUCTS_JSON,
        SYSTEM_PROMPT,
        build_language_instruction,
        settings,
    )
except ImportError:  # pragma: no cover
    from config import (  # type: ignore
        EmbeddingModelMismatchError,
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
    route: str = ""
    route_how: str = ""
    form: dict | None = None
    # The dose card travels on its own key, never inside `form`. An
    # already-deployed APK reads `form` and draws a BUDGET card from it; handing
    # it dose fields would render a money form over a dose question and submit
    # the answer back under the wrong payload.
    dose_form: dict | None = None
    # The comparison card travels on its own key for the same reason the dose
    # card does: an already-deployed APK reads `form` and draws a BUDGET card
    # from whatever arrives there.
    compare_form: dict | None = None

    def as_api(self) -> dict:
        return {
            "answer": self.answer,
            "recommended_products": [p.as_api() for p in self.recommended_products],
            "form": self.form,
            "dose_form": self.dose_form,
            "compare_form": self.compare_form,
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
    except EmbeddingModelMismatchError:
        # A config error, not "unavailable": retrieval is broken until a human
        # fixes .env or re-ingests, and no retry helps. Falling back to a
        # context-free answer would hide it - surface it instead.
        raise
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


# Turkish -> ASCII fold, one character in, one character out, so a match span
# found in the normalised text maps straight back onto the original query.
# The typographic apostrophes are folded to ASCII because MOBILE KEYBOARDS EMIT
# THEM: iOS and Android Turkish layouts produce U+2019, and both real clients pass
# the text through unmodified. Without this, "Manisa'dayim" typed on a phone does
# not match the province matcher's apostrophe rule while the same text typed on a
# desktop does - the demo passes and the primary client fails.
# Still strictly 1:1 and length-preserving, which _expand_query's span slice needs.
_TR_FOLD = str.maketrans("ıİğĞüÜşŞöÖçÇIâÂ’‘ʼ",
                         "iigguussooccIaA'''")


def _normalize_tr(text: str) -> str:
    """Lowercase + fold Turkish letters to ASCII, for lexicon MATCHING only.

    Never feed the result to the embedder: stripping diacritics from the whole
    query degrades retrieval (measured - it costs the millet rescue).
    """
    return text.translate(_TR_FOLD).lower()


# Turkish crop name -> English crop name. Retrieval-only: a Turkish query about a
# crop whose literature is English-only (FAO/OpenAlex) otherwise never reaches it,
# because generic Turkish fertilization papers clear the floor and fill k.
# Measured 2026-07-16: fixes 5 of 6 known gap crops, 0 regressions.
# These entries are the crops measured as gaps - extend only with evidence.
# NOTE: crop names for FINDING BOOK CHUNKS. Unrelated to the product catalog.
CROP_LEXICON = {
    "manyok": "cassava",
    "kakao": "cocoa",
    "tatlı patates": "sweet potato",
    "yağ palmiyesi": "oil palm",
    "darı": "millet",
    "gölevez": "taro",
    "kahve": "coffee",
    "muz": "banana",
    "çeltik": "rice",
    "asma": "grapevine",
    "üzüm": "grape",
    "fındık": "hazelnut",
}

# Common Turkish inflectional suffixes, longest-first, so the matcher can see a
# crop name through a case/plural/possessive ending ("asma" in "asmada") WITHOUT
# firing on a different morpheme ("kahve" in "kahverengi" - "rengi" is not here,
# so that branch fails the trailing (?!\w)). `bağ` was deliberately kept out of
# the lexicon; the suffix list also protects the crops that ARE in it.
_TR_SUFFIXES = (
    "nda|nde|dan|den|tan|ten|lar|ler|yla|yle|nın|nin|nun|nün|sı|si|su|sü"
    "|da|de|ta|te|ya|ye|na|ne|la|le|yı|yi|yu|yü|ın|in|un|ün|ı|i|u|ü|a|e"
)

# longest first, so "tatlı patates" wins over a future "patates" entry
_LEXICON_BY_LENGTH = sorted(
    ((_normalize_tr(tr), en) for tr, en in CROP_LEXICON.items()),
    key=lambda item: -len(item[0]),
)


def _expand_query(query: str) -> list[str]:
    """Return [query, *extra queries] that reach the other language's chunks.

    The corpus is ~half Turkish (dp_) and ~half English (ia_/oa_/fao_). For a
    crop covered only in English, the Turkish query's own top-k fills with
    generic Turkish fertilization chunks that clear the floor, so the English
    content never surfaces. For each crop name found we add two searches:
    the bare English term (carries most of the benefit) and the term substituted
    into the original query (rescues the rest).

    Deliberately unconditional and LLM-free: the old translate-when-under-filled
    path was measured empty on ~half of these queries, mistranslated (darı ->
    "sorghum"), cost 4.7-38 s, and fixed only 3 of 6 gaps.
    """
    if not settings.cross_lingual_retrieval:
        return [query]
    normalized = _normalize_tr(query)
    out = [query]
    for term, english in _LEXICON_BY_LENGTH:
        match = re.search(
            rf"(?<!\w){re.escape(term)}(?:{_TR_SUFFIXES})?(?!\w)", normalized
        )
        if not match:
            continue
        out.append(english)
        # A bare short term can retrieve nothing at all - measured 2026-07-16:
        # "taro" clears the floor with ZERO chunks, while "taro cultivation" puts
        # the same FAO content at rank 1. Two words embed where one does not.
        # ADDED, never substituted: swapping the bare term out rescues taro but
        # breaks sweet potato (measured: 5/6 either way, 6/6 with both).
        out.append(f"{english} cultivation")
        # substitute into the ORIGINAL query: the fold is 1:1, so the span lines
        # up, and the untouched diacritics keep the embedding intact.
        out.append(query[:match.start()] + english + query[match.end():])
    return out


# --------------------------------------------------------------------------- #
# Product-suppression backstop
# --------------------------------------------------------------------------- #
# The catalog is fertilizer/nutrition ONLY. Products belong only on a nutrition
# answer. The model is asked to prefix [NOPRODUCT] on a non-nutrition answer, but
# not every model emits that marker reliably (measured: gemma-4-26b on OpenRouter
# showed products on 22 non-product cases). This backstop reads the ANSWER and
# suppresses products when it is CLEARLY about a non-product activity - and only
# then, so a nutrition answer is never hidden. Deterministic, no cosine (measured
# dead: product cosine cannot separate "is this an answer"), no extra LLM call.
#
# Stems are matched LEFT-boundary only and folded (see _contains_any). They were
# chosen by empirical probing (2026-07-24), NOT intuition - several intuitive
# stems had measured false positives (see the exclusions below). Bounded by the
# categories SYSTEM_PROMPT enumerates; extend only on measured evidence.
_NON_PRODUCT_ACTIVITY = (
    "budam",                               # pruning (NOT "buda": hits "budala")
    "prune", "pruning",                    # (NOT "prun": hits "Prunus" the genus)
    "aşıla", "graft",                      # grafting (NOT "aşı": hits "aşırı")
    "havaland", "ventilat",                # ventilation
    "tozla", "pollinat",                   # pollination + pollinizer (was "tozlaş";
                                           #   "tozla" also catches "tozlayıcı".
                                           #   NOT "döllen": ambiguous)
    "partenokarp",                         # self-fertility / fruit set (pear cases)
    "sula", "irrigat",                     # irrigation practice
    "çoğalt", "propagat",                  # propagation
    "anaç",                                # rootstock selection
    "ekim",                                # sowing (also "Ekim" the month, but a
                                           #   fertilize-in-October answer carries a
                                           #   nutrition term, so the rule keeps it)
    "terbiye",                             # training system
    "hasat", "depola", "muhafaza",         # harvest / storage
    "kurut",                               # post-harvest drying
    "harvest", "storag",                   # (NOT "stor": hits "restore")
    "zararlı", "yabancı ot", "ilaçla",     # pest / weed control
    "pesticid", "weed",
)
# If ANY of these appears, never suppress - the answer is about nutrition. This is
# the guarantee that a working nutrition case is never regressed.
_NUTRITION_TERMS = (
    "gübre", "besin", "besle", "azot", "fosfor", "potasyum", "npk", "doz",
    "kompost",
    # "verimli" was REMOVED (2026-07-25): it is a FALSE nutrition signal on
    # self-fertility answers ("kendine verimli" = reproductively fertile, not
    # fertilized), which cancelled suppression on the pear cases. Soil-fertility
    # nutrition answers always also carry gübre/besin/azot, so nothing is lost.
    "fertiliz", "nutrient", "nitrogen", "phosph", "potass", "compost", "feeding",
)


def _contains_any(text: str, stems: tuple[str, ...]) -> bool:
    """True if any stem occurs in `text` with a LEFT word boundary.

    Left-boundary only (no right boundary, no _TR_SUFFIXES): the stem may run into
    its own derivational/verbal tail ("gubre" -> "gubreleyin", "budam" -> "budama",
    "sula" -> "sulayin"), which the crop-lexicon pattern's right boundary blocks.
    The left boundary still prevents matching inside a larger word from the left
    ("stor" not in "restore", "sula" not in "pusula").

    BOTH sides are folded by _normalize_tr (it folds Turkish letters to ASCII), so
    a diacritic stem ("gübre") meets folded input ("gubreleyin"). Comparing a raw
    stem against folded text would never match - a silently dead gate.
    """
    folded = _normalize_tr(text)
    for stem in stems:
        fs = _normalize_tr(stem)
        if re.search(rf"(?<!\w){re.escape(fs)}", folded):
            return True
    return False


def _looks_non_product(answer_text: str) -> bool:
    """True when products should be suppressed on evidence from the answer alone.

    Suppress ONLY when the answer names a non-product activity AND carries no
    nutrition term. Both halves are required, so a nutrition answer (or a mixed
    one) is never suppressed - the safe direction. This backstops the [NOPRODUCT]
    marker for models that do not emit it reliably; it never overrides a nutrition
    answer.
    """
    return (_contains_any(answer_text, _NON_PRODUCT_ACTIVITY)
            and not _contains_any(answer_text, _NUTRITION_TERMS))


# Reciprocal-rank-fusion constant; 60 is the standard damping value.
_RRF_K = 60


def _fuse(result_lists, floor: float, k: int):
    """Fuse result lists by RANK (RRF), returning up to k Documents.

    Raw similarity scores are NOT comparable across queries: Turkish filler
    scores ~0.45-0.52 for any Turkish agronomy query, which outranks the right
    English chunk (~0.46-0.48). Ranking the merged pool by score therefore drops
    correct content by hundredths of a point (measured: cacao lost by 0.003).
    Each list contributes 1/(60 + rank) per document instead, so every list's own
    best chunks get in regardless of absolute score. The floor still gates each
    list first, which is what keeps off-scope queries empty.
    """
    scores: dict[str, float] = {}
    docs: dict[str, object] = {}
    for results in result_lists:
        kept = [(d, s) for d, s in results if s >= floor]
        for rank, (doc, _score) in enumerate(kept, start=1):
            key = doc.page_content
            docs[key] = doc
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank)
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    return [docs[key] for key, _ in ranked[:k]]


def _search(store, query: str, k: int):
    """Vector search wrapper that returns [] instead of raising."""
    try:
        return store.similarity_search_with_relevance_scores(query, k=k)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] retrieval failed: {exc}")
        return []


def _last_user_turn(history: list[dict] | None) -> str:
    """The most recent user message in the conversation, or ""."""
    for turn in reversed(history or []):
        if turn.get("role") == "user" and turn.get("content"):
            return str(turn["content"])
    return ""


def retrieve_context(
    query: str, k: int | None = None, history: list[dict] | None = None
) -> str:
    """Return concatenated botany chunks relevant to the query, or "" if nothing
    clears the floor.

    Every expanded query (see `_expand_query`) is searched and the results are
    fused by rank. Expansion used to be conditional on the primary search
    under-filling; that trigger was removed because it is exactly wrong for the
    case it was meant to catch - generic Turkish chunks FILL k while being
    off-topic, so the rescue never fired (measured: it fired on 1 of 25 cases).
    Expansion is now LLM-free, so there is no latency reason to gate it.
    """
    k = k or settings.retrieval_k
    store = _get_retriever_store()
    if store is None:
        return ""

    queries = _expand_query(query)
    # A follow-up ("Toprak nasıl olmalı?") carries none of the conversation's
    # subject, so on its own it reaches generic chunks while the LLM - which DOES
    # get the history - talks about something the context never mentions. Search
    # the prior turn joined to this one as an EXTRA list; _fuse ranks by RRF, so
    # a self-contained question keeps its own top hits either way.
    prior = _last_user_turn(history)
    if prior:
        queries = [*queries, f"{prior} {query}"]

    result_lists = [_search(store, q, k) for q in queries]

    parts: list[str] = []
    for d in _fuse(result_lists, MIN_RETRIEVAL_RELEVANCE, k):
        src = d.metadata.get("source", "?")
        page = d.metadata.get("page", "?")
        parts.append(f"[Kaynak: {src}, s.{page}]\n{d.page_content}")
    return "\n\n---\n\n".join(parts)


# --------------------------------------------------------------------------- #
# LLM client
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChatProfile:
    """Everything that depends on WHICH chat backend is in use.

    Sampling lives here rather than in one global dict on purpose: min_p and
    repeat_penalty are LM Studio extensions, and a hosted provider rejects
    unknown body fields with a 400. Keeping them beside the endpoint they belong
    to makes a third provider one more branch instead of a scattered `if`.
    """
    base_url: str
    api_key: str
    model: str
    sampling: dict
    unavailable_hint: str


def _chat_profile() -> ChatProfile:
    """Build the active profile. Deliberately NOT cached: the eval repoints
    settings mid-process (see evals/run_eval.py --provider) and must see the
    change. It is only a few dict literals."""
    if settings.chat_provider == "openrouter":
        return ChatProfile(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            sampling={
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "max_tokens": settings.max_tokens,
            },
            unavailable_hint=(
                "Lutfen internet baglantinizi ve OpenRouter kredinizi kontrol edin."
            ),
        )
    return ChatProfile(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        model=settings.chat_model,
        sampling={
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "max_tokens": settings.max_tokens,
            # LM Studio extensions - see ChatProfile's docstring.
            "extra_body": {
                "min_p": settings.min_p,
                "repeat_penalty": settings.repeat_penalty,
            },
        },
        unavailable_hint=(
            "Lutfen yerel sunucunun (LM Studio) calistigindan emin olun."
        ),
    )


# Cached because constructing the client is the expensive part. Callers that
# change the provider mid-process MUST call _get_llm.cache_clear().
@lru_cache(maxsize=1)
def _get_llm() -> OpenAI:
    profile = _chat_profile()
    # max_retries=0: the openai SDK defaults to DEFAULT_MAX_RETRIES=2 and retries
    # 429s (and 5xx) itself, with backoff, entirely invisibly to our code. That
    # violates a binding project constraint - a rate limit must stay visible,
    # never silently absorbed - because an eval run measures timing and request
    # budget, and a hidden retry-with-backoff corrupts both. This also disables
    # retry-on-5xx; that is accepted as the same tradeoff, a visible failure
    # beats a silent wait.
    return OpenAI(
        base_url=profile.base_url,
        api_key=profile.api_key,
        timeout=settings.request_timeout,
        max_retries=0,
    )


# Stable opening of the unavailable message; the tail carries the provider hint
# and the exception text, so `_has_advice` matches on this prefix rather than the
# whole string.
#
# DELIBERATELY provider-neutral and a SINGLE constant. `_has_advice` uses it to
# tell our own fallback from a real answer, and suppresses product suggestions
# under it. A per-provider prefix would make a hosted outage message read as real
# advice - and fertilizer products would be recommended under an error message.
_LLM_UNAVAILABLE_PREFIX = "Uzgunum, su anda dil modeline ulasamiyorum."


def _llm_unavailable_message(exc: Exception) -> str:
    """User-facing fallback shown when the chat model can't be reached, so both
    the unified and streaming paths return the same wording. The provider-specific
    remedy comes from the active ChatProfile."""
    return (
        f"{_LLM_UNAVAILABLE_PREFIX} "
        f"{_chat_profile().unavailable_hint} "
        f"(teknik detay: {exc})"
    )


def _empty_answer_message() -> str:
    """Shown when the model REPLIED but produced no visible text.

    Deliberately does not claim the model is unreachable - it answered, it just
    produced nothing. Measured 2026-07-16: this happens ~2 in 10 on an ordinary
    query; the model can spend the whole token budget on reasoning_content
    (finish_reason="length"), and at least one other, faster mode exists that is
    not diagnosed.
    """
    return (
        "Uzgunum, bu soruya su anda bir yanit uretemedim. "
        "Lutfen sorunuzu biraz daha kisa ya da farkli bir sekilde tekrar sorun."
    )


def _has_advice(text: str) -> bool:
    """False when `text` is one of our own fallbacks rather than a real answer.

    Both fallbacks mean "there is no advice here", so nothing should be
    recommended underneath them - same rule the [NOPRODUCT] gate applies.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    return not (stripped == _empty_answer_message()
                or stripped.startswith(_LLM_UNAVAILABLE_PREFIX))


def _complete_text(messages: list[dict]) -> str:
    """Return the model's answer text, never "".

    Two stochastic failures each get one retry, and they are not the same
    failure:

    BLANK - the model emits nothing at all. Temperature is non-zero and the
    failures scatter across runs of an identical prompt, so a second attempt
    usually lands.

    TRUNCATION (`finish_reason == "length"`) - the generation budget ran out
    while the answer was still being written, so the user receives half a
    sentence. Measured 2026-08-13: this model spends a large and VARIABLE share
    of its budget on invisible reasoning - 1076 to 2023 completion tokens on one
    identical question against a 2048 cap - so it sits under the ceiling and
    occasionally crosses it. That scatters exactly like a blank answer, so it
    retries like one.

    If both attempts truncate, the longer partial is returned rather than the
    failure message: most of an answer beats none, and it is what the caller
    already received before this retry existed, so the retry can only improve
    the outcome. A truncation that leaves no visible text at all is a blank
    answer however it is labelled, and takes the blank path.

    Raises on transport errors - the caller maps those to
    _llm_unavailable_message, which is a different failure and must stay
    distinguishable.
    """
    client = _get_llm()
    profile = _chat_profile()
    truncated = ""
    for _ in range(2):  # first attempt + one retry
        completion = client.chat.completions.create(
            model=profile.model,
            messages=messages,
            stream=False,
            **profile.sampling,
        )
        choice = completion.choices[0]
        text = choice.message.content or ""
        if not text.strip():
            print("[engine] model returned a blank answer; retrying once")
            continue
        if choice.finish_reason == "length":
            print("[engine] model ran out of budget mid-answer; retrying once")
            if len(text) > len(truncated):
                truncated = text
            continue
        return text
    return truncated or _empty_answer_message()


def _context_block(route: str, message: str, history: list[dict] | None,
                   today: date) -> str:
    """Route-specific situation lines. Empty string for the routes that have
    none, so they pay nothing and nothing about them changes.

    `fert_plan` gets where, when and what the weather is about to do.
    `crop_choice` gets where and when, plus the factors that decide what to
    plant - no weather, because the question spans a season rather than the
    next few days.

    Weather is best-effort by design (see src/context/weather.py) - its absence
    removes one line and never blocks the answer. The province is asked for in
    chat rather than guessed: a wrong province produces confidently wrong timing.
    """
    # Deferred: src/context/location.py imports _normalize_tr from THIS module at
    # load time, so a top-level import here is a real cycle.
    if route == "crop_choice":
        try:
            return _crop_choice_block(message, history, today)
        except Exception as exc:                      # noqa: BLE001
            # Spec §8: the situation lines are an enhancement. Losing them must
            # cost those lines and nothing else, so the answer still gets built
            # from the corpus exactly as it did before this route diverged.
            print(f"[engine] crop_choice context failed, continuing without it: {exc}")
            return ""

    if route != "fert_plan":
        return ""

    from src.context import location, season, weather

    lines = [f"Tarih: {season.describe(today)}."]
    province = location.extract_province(message, history)
    if province:
        lines.append(f"Kullanicinin ili: {province}.")
        # `today` is passed through so the weather cache keys on the same day the
        # season line does - one clock read per answer, not two.
        fc = weather.forecast(province, today)
        if fc:
            lines.append(f"Hava durumu: {fc}.")
    else:
        lines.append("Kullanicinin ili BILINMIYOR - cevabinda hangi ilde "
                     "oldugunu sor, tavsiyeni genel tut.")
    lines.append("Bitkinin fenolojik donemi bilinmiyorsa cevabinda sor "
                 "(fide, cicek, meyve tutumu gibi).")
    return "\n".join(lines)


def _crop_choice_block(message: str, history: list[dict] | None,
                       today: date) -> str:
    """Situation lines for the crop-choice route: where, when, and the factors
    that actually decide what to plant.

    No module and no arithmetic - province and season come from context modules
    that already shipped, and the rest is prompt text.

    The prohibition on naming a crop is a PROMPT constraint, not something this
    code can enforce; spec §5 says so and the eval measures whether it holds.
    Enforcing it here would mean detecting "recommended a crop" in Turkish free
    text, which is the same problem the product-suppression backstop already
    finds hard.
    """
    from src.context import location, season

    lines = [f"Tarih: {season.describe(today)}."]
    province = location.extract_province(message, history)
    if province:
        lines.append(f"Kullanicinin ili: {province}.")
    else:
        lines.append("Kullanicinin ili BILINMIYOR - cevabinda hangi ilde "
                     "oldugunu sor.")
    lines.append("Bu bir urun secimi sorusu. Karari belirleyen faktorleri anlat "
                 "ve eksik olanlari sor: toprak yapisi ve analiz, sulama imkani, "
                 "arazi buyuklugu, onceki urun ve munavebe, pazara mesafe, "
                 "isgucu ve makine.")
    lines.append("BELIRLI BIR URUN ONERME. Kullanicinin kosullarini bilmeden "
                 "urun onermek bir sezonluk gecim karari hakkinda temelsiz "
                 "tavsiye olur.")
    return "\n".join(lines)


def _framing_suffix(route: str, message: str) -> str:
    """The framing sentence, when this question actually has a reviewed plan
    behind it. Empty string otherwise.

    Gated on rows ACTUALLY FOUND for this question, not on the table being
    non-empty: a general corpus answer is advice already and needs no
    programme disclaimer. Appended by CODE, never asked of the model, so no
    model can drop it.
    """
    if route != "fert_plan":
        return ""
    # Deferred: src/fertplan.py imports _normalize_tr from THIS module.
    from src import fertplan
    crop = fertplan.detect_crop(message)
    if crop and fertplan.lookup(crop, None):
        return fertplan.FRAMING
    return ""


def _build_messages(
    message: str,
    history: list[dict] | None,
    context: str,
    products: list[RecommendedProduct],
    context_block: str = "",
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
    if context_block:
        # Prepended, not merged into `context`: the {context} slot is corpus
        # material the model may cite, and these are facts about the user's
        # situation. Keeping them apart stops the model attributing "Manisa" to
        # a book.
        system_content = f"{context_block}\n\n{system_content}"

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
# The model prefixes off-scope refusals with this marker (see SYSTEM_PROMPT) so
# we can strip it and drop product suggestions - recommending catalog products
# under a "that's outside my scope" reply would be incoherent.
_OFFSCOPE_MARKER = "[OFFSCOPE]"
_NOPRODUCT_MARKER = "[NOPRODUCT]"
# stream_answer buffers until it can (dis)confirm a marker - size off the longest
_LONGEST_MARKER = max(len(_OFFSCOPE_MARKER), len(_NOPRODUCT_MARKER))

# Clean characters to accumulate before the stream starts flowing to the client.
# Larger than any control marker (so the marker is fully visible and stripped
# first) and larger than a reasoning-exhaustion truncation fragment (~20 chars),
# so such a fragment never reaches the client and can be retried instead. The
# only cost is that the first paint waits for this many characters - negligible
# against generation latency.
_STREAM_WARMUP = 80


def _strip_markers(text: str) -> tuple[str, bool, bool]:
    """Return (clean_text, off_scope, no_product).

    Detects the leading control markers (case-insensitive) and removes them with
    any trailing separators. Loops, so both markers in either order are handled.
    Text without a leading marker is returned UNCHANGED (not lstripped).
    """
    lead = text.lstrip()
    off_scope = no_product = False
    while True:
        upper = lead.upper()
        if upper.startswith(_OFFSCOPE_MARKER):
            off_scope = True
            lead = lead[len(_OFFSCOPE_MARKER):].lstrip(" :\n\t")
            continue
        if upper.startswith(_NOPRODUCT_MARKER):
            no_product = True
            lead = lead[len(_NOPRODUCT_MARKER):].lstrip(" :\n\t")
            continue
        break
    if not (off_scope or no_product):
        return text, False, False
    return lead, off_scope, no_product


def _budget_result(payload: dict | None, message: str = "",
                   history: list[dict] | None = None) -> ChatResult:
    """The budget route: no retrieval, no product match, no model call.

    Every figure is computed in src/budget.py from values the user typed into
    labelled fields, or from a norm they accepted. When the payload is absent or
    incomplete we return the form instead of an answer; a payload that was never
    submitted gets a clean form rather than a list of "required" errors.

    The province is resolved from the conversation the same way weather and
    fert_plan resolve it, and the whole province's norm table travels with the
    form because the crop is selected on the client. A failure anywhere in that
    lookup costs the prefill and nothing else: the form still serves, exactly as
    it did in P1.

    validate() and compute() share one guard: either raising returns
    COMPUTE_FAILED with no form and no figures. validate() is documented never
    to raise, but on the streaming path the 200 and headers are already sent by
    the time this runs, so a raise here would break the connection mid-stream.
    """
    # Deferred like the router import below: src/context/location.py imports
    # _normalize_tr from THIS module at load time, so hoisting it makes the
    # cycle real. Same reason _context_block imports it locally.
    from src import budget

    table = ()
    latest_year = None
    try:
        from src import norms
        from src.context import location
        table = norms.province_table(location.extract_province(message, history))
        latest_year = norms.latest_year()
        if table and not any(row.yield_kg_da or row.price_tl_kg or row.yield_kg_tree
                              for row in table):
            # No province resolved (or the resolved one, and the national
            # fallback, both carry nothing): every row's yield (per-dekar or
            # per-tree) and price is null. Serving that table anyway would put
            # ~22 KB of dead rows on the wire and draw a crop picker that
            # fills nothing when tapped, with no message explaining why.
            # Treat it the same as a genuine lookup failure: no table at all.
            table = ()
    except Exception as exc:  # noqa: BLE001 - a prefill is a convenience, not the route
        # Say so. Swallowing this silently is how a broken norm layer ships as
        # "the prefill quietly stopped working": the route still serves a form,
        # so every test stays green and nothing else in the answer changes.
        print(f"[engine] no norm prefill this turn: {type(exc).__name__}: {exc}")
        table = ()
        latest_year = None

    submitted = bool(payload)
    try:
        inputs, errors = budget.validate(payload or {}, table)
        if inputs is not None:
            result = budget.compute(inputs)
            return ChatResult(answer=budget.render(inputs, result),
                              recommended_products=[], route="budget")
    except Exception:  # noqa: BLE001 - a broken validation or sum must not become a guess
        return ChatResult(answer=budget.COMPUTE_FAILED,
                          recommended_products=[], route="budget")

    return ChatResult(answer=budget.ASK_FOR_NUMBERS, recommended_products=[],
                      route="budget",
                      form=budget.form_spec(errors if submitted else [],
                                            table,
                                            payload if submitted else None,
                                            latest_year))


def _named_crops(message: str) -> tuple[str, ...]:
    """Which crops this message names. Never raises: a detector failure must
    cost the card, not the answer."""
    try:
        from src import crop_compare
        return crop_compare.named_crops(message)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] crop detection failed, no comparison this turn: {exc}")
        return ()


def _compare_result(payload: dict | None, message: str = "",
                    history: list[dict] | None = None) -> ChatResult:
    """The crop-comparison route: no retrieval, no product match, no model call.

    One multiplication per crop in src/crop_compare.py, over figures TUIK
    published. The province is resolved from the conversation the same way
    weather, fert_plan and the budget prefill resolve it - and when it cannot
    be resolved the route ASKS, because a provincial figure from the wrong
    province is a wrong answer that reads perfectly right.

    Deferred imports for the cycle src/router.py documents: crop_compare
    imports _normalize_tr from THIS module at load time.
    """
    from src import crop_compare, norms
    from src.context import location

    province = location.extract_province(message, history)
    if not province:
        return ChatResult(answer=crop_compare.NO_PROVINCE,
                          recommended_products=[], route="crop_choice")

    table = norms.province_table(province)
    submitted = bool(payload)
    try:
        inputs, errors = crop_compare.validate(payload or {}, table)
        if inputs is not None:
            inputs = crop_compare.CompareInputs(inputs.first, inputs.second, province)
            figures = crop_compare.compute(inputs, table, norms.latest_year())
            return ChatResult(answer=crop_compare.render(inputs, figures),
                              recommended_products=[], route="crop_choice")
    except Exception:  # noqa: BLE001 - a broken validation or sum must not become a guess
        return ChatResult(answer=crop_compare.COMPUTE_FAILED,
                          recommended_products=[], route="crop_choice")

    return ChatResult(answer=crop_compare.ASK_FOR_CROPS, recommended_products=[],
                      route="crop_choice",
                      compare_form=crop_compare.form_spec(
                          errors if submitted else [], table,
                          payload if submitted else None, province))


def _dose_result(payload: dict | None) -> ChatResult:
    """The dose route: no retrieval, no product match, no model call.

    Two multiplications in src/dose_answer.py over a figure the manufacturer
    published and an area the user selected. When the payload is absent or
    incomplete we return the card instead of an answer; a payload that was
    never submitted gets a clean card rather than a list of "required" errors.

    validate()/compute()/render() share one guard: any of them raising returns
    COMPUTE_FAILED with no card and no figures. They are documented never to
    raise, but on the streaming path the 200 and headers are already sent by
    the time this runs, so a raise here would break the connection mid-stream.
    """
    # Deferred like the router import: keeping engine's module-level imports
    # free of route modules is what stops the cycles the rest of this file
    # documents.
    from src import dose_answer

    submitted = bool(payload)
    try:
        inputs, errors = dose_answer.validate(payload or {})
        if inputs is not None:
            totals = dose_answer.compute(inputs)
            text = (dose_answer.render(inputs, totals) if totals
                    else dose_answer.no_dose_for_group(inputs))
            return ChatResult(answer=text, recommended_products=[],
                              route="product_dose")
    except Exception:  # noqa: BLE001 - a broken validation or sum must not become a guess
        return ChatResult(answer=dose_answer.COMPUTE_FAILED,
                          recommended_products=[], route="product_dose")

    return ChatResult(answer=dose_answer.ASK_FOR_INPUTS, recommended_products=[],
                      route="product_dose",
                      dose_form=dose_answer.form_spec(
                          errors if submitted else [],
                          payload if submitted else None))


def answer(message: str, history: list[dict] | None = None,
           budget_payload: dict | None = None,
           dose_payload: dict | None = None,
           compare_payload: dict | None = None) -> ChatResult:
    """Retrieve, match products, and produce a unified JSON-ready result."""
    # Routing is diagnostic in this release: every route still runs the corpus
    # path below. Wiring it now, with behaviour unchanged, is what lets the 55
    # eval cases prove the router is harmless before any route diverges.
    try:
        # Deferred on purpose: src/router.py imports _normalize_tr from THIS
        # module at load time, so hoisting this to a top-level import makes the
        # cycle real and raises ImportError on every startup. Keep it local.
        from src import router
        route, route_how = router.classify(message, history)
    except Exception:  # noqa: BLE001 - routing must never break answering
        route, route_how = "", ""

    # Checked before budget: a submitted dose card is answered as a dose
    # question whatever the message it rode in on classifies as. The two
    # payloads are mutually exclusive in both clients; if one ever sends both,
    # the dose card is the one the user just pressed.
    if dose_payload or route == "product_dose":
        result = _dose_result(dose_payload)
        result.route_how = route_how
        return result

    # The comparison fork lives INSIDE crop_choice rather than in the router:
    # `crop_choice` already routes these questions correctly, and a new routing
    # rule would put the pre-registered frozen set at risk for nothing. An open
    # "ne eksem?" question names no crop, falls through this branch, and keeps
    # the factors answer it has today - which is a measured decision, not an
    # oversight.
    if compare_payload or (route == "crop_choice"
                           and len(_named_crops(message)) >= 2):
        result = _compare_result(compare_payload, message, history)
        result.route_how = route_how
        return result

    # The budget route short-circuits BEFORE retrieval: a money question was
    # paying for a corpus search that cannot hold its answer. Safe to diverge
    # because `budget` takes zero false entries in the frozen routing set.
    #
    # `or budget_payload`: turn 2 does not bet on the router a second time. A
    # submitted form is computed whatever the classifier says about the question
    # it was attached to.
    if route == "budget" or budget_payload:
        result = _budget_result(budget_payload, message, history)
        result.route_how = route_how
        return result

    context = retrieve_context(message, history=history)
    products = match_products(message, context)
    messages = _build_messages(message, history, context, products,
                               _context_block(route, message, history, date.today()))

    try:
        answer_text = _complete_text(messages)
    except Exception as exc:  # noqa: BLE001
        answer_text = _llm_unavailable_message(exc)

    has_advice = _has_advice(answer_text)
    if not has_advice:
        # There is no advice for products to sit under - a "sorry, I couldn't
        # answer" reply with three fertilizers beneath it is an ad, not help.
        products = []

    answer_text, off_scope, no_product = _strip_markers(answer_text)
    if off_scope or no_product or _looks_non_product(answer_text):
        # off-scope refusal; or an in-scope non-nutrition question (pruning,
        # pests, storage...). The marker is the primary signal; _looks_non_product
        # backstops a model that did not emit it - see the backstop spec.
        products = []

    suffix = _framing_suffix(route, message)
    if suffix and not (off_scope or no_product) and has_advice:
        # Not on a refusal and not on one of our own fallback messages: telling a
        # user "this programme is an estimate" under "I could not answer" claims
        # a programme that does not exist.
        answer_text = f"{answer_text.rstrip()}\n\n{suffix}"

    return ChatResult(answer=answer_text.strip(), recommended_products=products,
                      route=route, route_how=route_how)


def stream_answer(
    message: str, history: list[dict] | None = None,
    budget_payload: dict | None = None,
    dose_payload: dict | None = None,
    compare_payload: dict | None = None
) -> Iterator[str]:
    """Yield Server-Sent-Event lines. Answer text streams token-by-token first;
    once it's complete a single event carries the product recommendations, then
    a final 'done' event closes the stream. A submitted budget form is served
    from it without a model call."""
    # Same deferred import as answer(): src/router.py imports _normalize_tr from
    # THIS module at load time, so a top-level import here is a real cycle.
    try:
        from src import router
        route, route_how = router.classify(message, history)
    except Exception:  # noqa: BLE001 - routing must never break answering
        route, route_how = "", ""

    # Must mirror answer() exactly, including the payload clause and its order.
    # Both clients stream, so a card wired only into answer() would reach no
    # user at all - and the tests would still pass.
    if dose_payload or route == "product_dose":
        result = _dose_result(dose_payload)
        yield _sse({"type": "token", "content": result.answer})
        if result.dose_form is not None:
            # A NEW event type: an already-deployed client ignores an unknown
            # `type` (see mobile-app/src/api.ts), so it shows the sentence and
            # no card rather than drawing a budget form out of dose fields.
            yield _sse({"type": "dose_form", "form": result.dose_form})
        yield _sse({"type": "done"})
        return

    # Must mirror answer() exactly, including the compare_payload clause and
    # its order. Both clients stream, so a card wired only into answer() would
    # reach no user at all - and the tests would still pass.
    if compare_payload or (route == "crop_choice"
                           and len(_named_crops(message)) >= 2):
        result = _compare_result(compare_payload, message, history)
        yield _sse({"type": "token", "content": result.answer})
        if result.compare_form is not None:
            yield _sse({"type": "compare_form", "form": result.compare_form})
        yield _sse({"type": "done"})
        return

    # Must mirror answer() exactly, including the `or budget_payload` clause.
    # Both clients stream, so a form wired only into answer() would reach no user
    # at all - and the tests would still pass.
    if route == "budget" or budget_payload:
        result = _budget_result(budget_payload, message, history)
        yield _sse({"type": "token", "content": result.answer})
        if result.form is not None:
            yield _sse({"type": "form", "form": result.form})
        yield _sse({"type": "done"})
        return

    context = retrieve_context(message, history=history)
    products = match_products(message, context)
    messages = _build_messages(message, history, context, products,
                               _context_block(route, message, history, date.today()))

    # Hold back the opening tokens until we have a WARMUP's worth of clean content
    # (marker stripped). Two jobs at once: (1) strip a leading control marker
    # before it reaches the client; (2) never emit a reasoning-exhaustion
    # truncation. The model sometimes spends its whole token budget on
    # reasoning_content and finishes with `length` after only a word or two (the
    # streaming form of the item-20 blank-answer bug). While nothing has been
    # emitted yet, that is recoverable: fall back to the non-streaming path, which
    # completes reliably. Once we have warmed up (a real answer is flowing), a
    # late truncation is no longer recoverable, but by then the user has a usable
    # answer rather than a stray fragment like "Orkideler".
    off_scope = False
    no_product = False
    buffer = ""
    warmed = False
    emitted = False
    failed = False
    finish = None
    has_advice = True   # cleared when we fall back instead of answering
    full_answer = ""    # the complete streamed answer, for the backstop
    try:
        client = _get_llm()
        profile = _chat_profile()
        stream = client.chat.completions.create(
            model=profile.model,
            messages=messages,
            stream=True,
            **profile.sampling,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            fr = getattr(chunk.choices[0], "finish_reason", None)
            if fr:
                finish = fr
            delta = chunk.choices[0].delta.content
            if not delta:
                continue
            if warmed:
                full_answer += delta
                yield _sse({"type": "token", "content": delta})
                emitted = True
                continue
            buffer += delta
            clean, off_scope, no_product = _strip_markers(buffer)
            if len(clean) >= _STREAM_WARMUP:
                full_answer += clean
                yield _sse({"type": "token", "content": clean})
                emitted = True
                warmed = True
                buffer = ""
    except Exception as exc:  # noqa: BLE001
        failed = True
        has_advice = False
        yield _sse({"type": "token", "content": _llm_unavailable_message(exc)})

    if not warmed and not failed:
        # The stream ended before a full warmup. Either a genuinely short answer
        # (finish 'stop') - emit it as-is - or a length-truncation (the reasoning-
        # exhaustion bug, zero-or-few tokens). Nothing has reached the client, so
        # a truncation retries safely on the reliable non-streaming path.
        clean, off_scope, no_product = _strip_markers(buffer)
        if finish == "length":
            try:
                text = _complete_text(messages)
            except Exception as exc:  # noqa: BLE001
                text = _llm_unavailable_message(exc)
            has_advice = _has_advice(text)
            clean, off_scope, no_product = _strip_markers(text)
        if clean:
            full_answer += clean
            yield _sse({"type": "token", "content": clean})
            emitted = True

    if not emitted and not failed:
        # Backstop: the stream produced nothing usable and finish was not
        # 'length' (e.g. an empty 'stop'). Same blank-output guard as answer().
        try:
            text = _complete_text(messages)
        except Exception as exc:  # noqa: BLE001
            text = _llm_unavailable_message(exc)
        has_advice = _has_advice(text)
        clean, off_scope, no_product = _strip_markers(text)
        if clean:
            full_answer += clean
            yield _sse({"type": "token", "content": clean})
            emitted = True

    suffix = _framing_suffix(route, message)
    # Gated on full_answer, not `emitted`: the blank-answer backstop above streams
    # a recovered answer without touching `emitted`, and framing that only lands
    # on the warm path is framing the model can drop by returning an empty stream.
    # full_answer carries real answer text only - the LLM-unavailable message is
    # deliberately not accumulated into it.
    if suffix and not (off_scope or no_product) and has_advice and full_answer:
        yield _sse({"type": "token", "content": f"\n\n{suffix}"})

    # Emit product recommendations only after the full answer has streamed (and
    # only for in-scope answers), so clients render them beneath the reply.
    # `has_advice` covers the fallbacks: there is no advice for products to sit
    # under when we could not answer at all.
    if (not (off_scope or no_product) and has_advice
            and not _looks_non_product(full_answer)):
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
