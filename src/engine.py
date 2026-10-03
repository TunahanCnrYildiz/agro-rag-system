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

    `fert_plan` DOES NOT CONSULT THE WORLD LAYER, and that is a decision rather
    than an oversight - a foreign grower asking a fertiliser question is still
    told his province is unknown and still asked for it. Written down here
    because `crop_choice` right below does the opposite, so the asymmetry would
    otherwise look like one branch having been forgotten.

    The reason is that there is nothing to put in the ask's place. The world
    layer carries two measures, yield and producer price (see
    data/world_norms.json), and neither answers a fertiliser question: there is
    no dose, no soil-analysis norm and no phenology in it. `weather.forecast` is
    keyed on the 81 Turkish provinces and has no row for anywhere else, and
    `_framing_suffix` ties a fert_plan answer with rows behind it to a reviewed
    TURKISH programme. Suppressing the ask would therefore delete the one
    sentence that keeps the answer general, and put nothing where it was - the
    model would be left free to read Turkish doses as if they applied.

    So the cost is named rather than removed: a grower outside Türkiye is asked
    one question he cannot answer on this route, and the assistant's advice stays
    general. That costs a turn. Printing a country's yield beside a fertiliser
    dose would cost the dose's provenance.
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


# FAOSTAT's flag letters, in Turkish. data/world_norms.json's meta.flags carries
# the English glosses; these are their twins, and they live here because this is
# the only surface that says them out loud.
#
# THERE IS NO ENTRY FOR None, and there must not be. A TÜİK figure carries no
# flag at all, and a word for "no flag" would read as a provenance claim nobody
# made. An UNKNOWN letter is printed as itself (see _flag_note) rather than
# dropped: a flag FAOSTAT adds later must show up as an unexplained letter, not
# vanish into silence.
#
# EVERY GLOSS SAYS ONLY WHAT ITS LETTER SAYS. Two of them used to say more:
#
#  * `B` was glossed "resmi deger, seride kopus var". FAOSTAT's own meta.flags
#    reads "Time series break" and nothing else - the letter marks a
#    discontinuity in the series, not who produced the cell, so calling the
#    value official was a provenance claim the flag does not make. Harmless on
#    the shipped file and only there: measured 2026-10-02 against
#    data/world_norms.json, all 43 `B` cells are in the price table, none of
#    them is the latest non-null year of its series, so `_pick_world` returns
#    none of them today. A rebuild that lands one last would print the claim.
#  * `I` was glossed "FAO'nun atadigi deger" for "Value imputed by a receiving
#    agency" - which narrows "a receiving agency" to FAO and softens "imputed"
#    to "assigned". Same file, 3 `I` cells, all in the price table and none
#    latest, so this one is unreachable today too.
_FAO_FLAGS = {
    "A": "ulkenin resmi bildirimi",
    "B": "seride kopus var, deger onceki yillarla karsilastirilamaz",
    "E": "FAO tahmini, ulkenin kendi bildirimi degil",
    "I": "veriyi alan kurulusun tamamladigi deger",
    "X": "dis kurulustan alinmis deger",
}


def _flag_note(flag: str | None) -> str:
    """The provenance clause for one FAOSTAT cell, or "" when there is none."""
    if not flag:
        return ""
    return _FAO_FLAGS.get(flag, f"FAOSTAT isareti {flag}")


def _world_amount(amount: float) -> str:
    """One world figure, Turkish-formatted, without rounding it into a lie.

    Yields run to five digits and prices sit below one dollar - measured on the
    shipped file, the smallest latest price is 0,0088 USD/kg - so a single
    decimal count cannot serve both: two decimals prints that price as "0,01"
    and four prints a yield as "597,3500". Split at 1, which is the only place
    the two ranges meet.

    NO THOUSANDS SEPARATOR, and this is the part that matters for a figure a
    language model reads. `format_tr` writes Turkish convention - thousands dot,
    decimal comma - so `format_qty(4000.0)` is "4.000", which under English
    convention reads as four, not four thousand. That is a 1000x error with
    nothing in the string to disambiguate it, because a whole number has no
    decimal comma following to mark the dot as a group separator. It is not a
    corner either: measured 2026-10-02 over data/world_norms.json, 3.104 of the
    8.453 latest yield cells are >= 1000 and 206 of those are whole numbers, the
    exact "4.000" shape. Dropping the separator leaves "4000" and "47889,02",
    which read the same under both conventions.
    `.replace(".", "")` is safe rather than blunt: `format_tr` emits "." ONLY as
    the group separator - the decimals go after a comma - so there is no other
    dot in the string to eat.

    FIXED HERE AND NOT IN src/budget.py: `format_tr` and `format_qty` write the
    budget form and the comparison card, which are read by a person on a screen
    where the Turkish convention is right and the surrounding text supplies the
    convention. This is the only surface whose reader is the model.
    """
    from src.budget import format_qty, format_tr
    text = format_qty(amount) if amount >= 1 else format_tr(amount, 4)
    return text.replace(".", "")


# The shapes in which a user says THEY ARE in a country, as opposed to merely
# naming one. Lives here rather than in src/context/country.py because that
# module resolves a country from five different shapes and returns only an area
# code - nothing it exposes says WHICH shape answered, or where in the text it
# matched - and that module is not this change's to alter.
#
# WHAT GOES WRONG WITHOUT THIS TEST, measured on e021bca:
#
#   "gecen yil Almanyaya bugday sattim, bu yil bugday mi eksem"
#       -> Germany: "Kullanici Turkiye disinda", Germany's wheat figures, and
#          the province question gone.
#   "Hollanda'daki gibi sera kurmak istiyorum, domates ekeyim mi"  -> Netherlands
#   "Amerika'da buğday fiyatları nasıl, ben buğday ekeyim mi"      -> USA
#
# All three are plausibly Turkish farmers, and the country each one names is a
# buyer, a greenhouse they admire and a price reference. The recall that resolves
# them belongs to src/context/country.py; what belongs HERE is that a resolved
# country was allowed to REPLACE the province question. So it may only do that
# when the country is the user's own stated location, and every other mention
# loses the country lines and keeps the ask - which is byte-for-byte the block
# this branch produced before the world layer existed.
#
# WHAT DISTINGUISHES THEM IS THE CASE ENDING ON THE NAME, not the presence of a
# first-person verb - all three of the sentences above contain one (`sattim`,
# `istiyorum`, `ekeyim`). So the name has to be in the LOCATIVE:
#
#   Fransa'da yasiyorum              locative                        admitted
#   Almanya'ya bugday sattim         DATIVE, and `sattim` is 1sg     refused
#   Hollanda'dan tohum aldim         ABLATIVE                        refused
#   Hollanda'daki gibi ... istiyorum locative + the relativiser -ki  refused
#   Amerika'da bugday fiyatlari nasil  locative, no 1st-person head  refused
#
# REJECTED: a first-person verb anywhere in the sentence, with no case test. It
# admits all three of the sentences this guard exists to refuse.
#
# THE CASE ENDING IS NOT ENOUGH EITHER - THE TENSE MATTERS TOO. A locative plus a
# first-person PAST verb says something was DONE there, not that the speaker is
# there, and that is the same class again: "Amerika'da bugday aldim, ben bugday
# mi eksem", "Fransa'da staj yaptim", "Hollanda'da fuara katildim". So the
# predicate test below reads the present continuous and the copula only; see
# _TR_FIRST_PERSON for the four tenses measured out of it.
#
# THREE TURKISH BRANCHES, because the copula attaches in two places and one
# shape needs naming outright:
#
#  * _SELF_TR - the copula FUSED to the name's own suffix: "Fransa'dayım",
#    "Ganadayim", "Fransalıyım". The suffix runs straight into `-yım`.
#  * _TR_LOCATIVE plus _first_person_follows - the dominant Turkish pattern,
#    which puts the case ending on the NAME and the person on the VERB:
#    "Fransa'da yaşıyorum", "Fransa'da çiftçilik yapıyorum", "Fransada
#    çiftçiyim". An earlier revision of this guard had only the first branch and
#    refused every one of these - real sentences a grower in France would write,
#    measured resolving to France in `extract_country` and then losing every
#    figure here.
#  * _TR_RELATIVE_SELF - "Fransa'da yaşayan bir çiftçiyim". The second branch
#    reached this one only by looking three words out, and that width also let
#    through eleven measured sentences where the locative belongs to an OBJECT
#    ("Fransa'da üretilen tohum kullanıyorum"). The width is two now and this
#    sentence is admitted by its shape instead.
#
# The apostrophe is optional in all three, because Turkish speakers omit it
# ("Ganadayim", "Fransada ciftciyim") and country.py's own suffix branch accepts
# either.
#
# REJECTED: accepting the place-noun form src/context/location.py accepts
# ("Fransa kosullarinda"). For a province it is how growers state where they are;
# for a country "Fransa kosullarinda bugday ekilir mi" is a Turkish grower asking
# about France, which is the same class as the three sentences this guard exists
# to refuse.
#
# REJECTED: adding the country lines and keeping a SOFTENED ask beside them. The
# ask is for a Turkish province, and there is no softening of that question which
# is not still wrong to put to a grower in France - which is the contradiction
# the replacement was introduced to avoid in the first place.
#
# NOT GATED ON WHETHER THE ALIAS IS SPELLED IN TURKISH, which country.py does
# gate its own suffix branch on. This test can only NARROW a code that module has
# already returned, so a Turkish suffix admitted on an English spelling cannot
# introduce a country that was not resolved - and the shapes below state a
# location whichever spelling they sit on.
_SELF_TR = r"'?(?:[dt][ae]|l[iu])y[iu][mz](?!\w)"

# The locative, and it must END THE WORD - that `(?!\w)` is what separates the
# three cases in the table above that share the letters `da`:
#   "fransa'da yasiyorum"  -> `da` then a space      admitted here
#   "hollanda'daki gibi"   -> `da` then `k`          refused
#   "hollanda'dan tohum"   -> `da` then `n`          refused (ablative)
# It also keeps the two branches disjoint: "fransadayim" is `da` then `y`, so it
# fails here and is caught by _SELF_TR, which is where it belongs.
_TR_LOCATIVE = r"'?[dt][ae](?!\w)"

# First-person endings, word-final on folded text. PRESENT CONTINUOUS AND THE
# COPULA ONLY, because those are the tenses "where I am" is said in. This set and
# the window below BOTH hold part of the refuse set out, and neither covers for
# the other - see _TR_CLAUSE_WORDS, where the table that said the window was free
# is corrected.
#
# Measured 2026-10-03 against the corpus the test suite carries in full - 6
# Turkish accepts and 27 refusals - adding one ending at a time and changing
# nothing else. All six accepts pass with the set as it stands, so every one of
# these costs refusals and buys nothing:
#
#   ending added           wrongly admitted
#   -dim/-tim  (past)           5/27
#   -im/-um/-iz (nominal)      10/27
#   -arim/-erim (aorist)        1/27
#   -acagim/-ecegim (future)    0/27
#
#  * the PAST `-dim/-tim` reads a FINISHED ACTION in a place as being in that
#    place, which is the whole class CRITICAL 3 exists to refuse. The five it
#    admitted: "Amerika'da bugday aldim, ben bugday mi eksem" - the Turkish
#    farmer citing a US price, exactly the shape - plus "Hollanda'da sera
#    gordum, domates ekeyim mi", "Fransa'da staj yaptim, bugday ekeyim mi",
#    "Fransa'da okudum" and "Hollanda'da fuara katildim". Worse than a one-turn
#    error, because the caller asks every user turn: one "Fransa'da staj yaptım"
#    in the first turn kept the grower in France for the rest of the conversation.
#  * the bare nominal `-im/-um/-iz` admits the five above and five more, because
#    Turkish is full of ordinary nouns with that ending and three of them are
#    agricultural - "Amerika'da tohum fiyatlari nasil" (tohum), "Fransa'da ekim
#    zamani gecti mi" (ekim), "Fransa'da verim yuksek diye duydum" (verim). The
#    `y` in `y[iu][mz]` is exactly what keeps those out while `ciftciyim` passes.
#    It also reaches one of the object-locative eleven, "Fransa'da uretilen tohum
#    kullaniyorum", on `tohum` - which the window refuses on distance alone, so
#    that sentence is held out twice over and neither hold is redundant.
#  * the aorist `-arim/-erim` fails for the same reason one letter along: the
#    agricultural noun `verim` ENDS in those very letters, so
#    "Fransa'da verim yuksek diye duydum" is read as a first-person verb.
#  * the FUTURE `-acagim/-ecegim` admits NOTHING in this corpus, so it is left
#    out on the argument rather than on a measurement: a plan to plant somewhere
#    is not a statement of being there. It also buys no accept - the one sentence
#    that would need it, "Fransa'da bu yil bugday ekecegim", sits outside the
#    window below in any case. If a future accept ever turns up, this is the
#    entry to revisit, and it is the cheapest of the four to re-measure.
_TR_FIRST_PERSON = re.compile(r"(?:[iu]yor[iu][mz]|y[iu][mz])$")

# HAZARD: `iste-` is first-person and is not a location. "Hollanda'da sera kurmak
# istiyorum" is a plan, and it is the apostrophe-less twin of one of the three
# sentences this guard exists to refuse.
#
# IT NO LONGER EARNS ITS PLACE AT THE SHIPPED WIDTH, and that is said here rather
# than left for the next reader to discover. Re-measured 2026-10-03 over the 27
# refusals, varying only this line: at _TR_CLAUSE_WORDS = 2 it changes nothing,
# because `istiyorum` is the THIRD word of "Hollanda'da sera kurmak istiyorum"
# and the window never reaches it. At 3, 4, 5 and 6 it is worth exactly that one
# sentence, every time. The earlier revision of this comment claimed the measured
# admission unconditionally; it was true at the width of the day and is kept, in
# corrected form, because it is what makes the window safe to widen - the same
# bargain _TR_CLAUSE below is kept on.
#
# It SKIPS the word rather than failing the clause, so a sentence that states a
# location and then wants something ("Fransa'da yasiyorum, bugday ekmek
# istiyorum") is still read off its first predicate.
#
# NOT EXTENDED to the hearsay verbs `duy-`, `oku-`, `gor-`. They were the shape
# "Fransa'da verim yuksek diye duydum" and "Hollanda'da sera gordum" take - the
# locative belongs to an embedded clause or a finished action, not to the speaker
# - and all of them are refused now by _TR_FIRST_PERSON dropping the past tense,
# which is a tense rule rather than a word list. Adding them would be a list with
# no measured failure left to justify it.
_TR_VOLITIONAL = re.compile(r"ist[ei]")

# TWO WORDS. Measured 2026-10-03 over the corpus the test suite now carries in
# full - 27 refusals and 6 Turkish accepts (the two English ones are _SELF_EN's
# and no window affects them) - varying only this:
#
#   window   accepted   wrongly admitted
#     1        5/6            0/27
#     2        6/6            0/27
#     3        6/6            7/27
#     4        6/6           10/27
#     5        6/6           10/27
#     6        6/6           10/27
#
# WHAT THE WINDOW CANNOT SEE is WHOSE the locative is. This scan reads the first
# first-person predicate in reach and never asks whether the place attaches to
# the SUBJECT or to an OBJECT, so an intervening participle phrase rides in free:
# "Fransa'da uretilen tohum kullaniyorum" has a first-person verb and the seed,
# not the speaker, is in France. Eleven such sentences were measured; seven of
# them reach a predicate at word 3 and three more at word 4, which is the whole
# of that column above. They are in
# `test_a_locative_that_belongs_to_an_object_is_not_a_stated_location`.
#
# SO THE WINDOW IS NOT THE REFUSE SET'S ONLY KEEPER ANY MORE, which is the
# correction to the revision this comment replaces. That one measured 0/17 all
# the way down the column and concluded the ending set held everything out and
# the width was free; its refuse set simply had no participle sentence in it. On
# the corpus with those eleven, two is the only width that is both free and
# complete.
#
# TWO REACHES EVERY ACCEPT because _TR_RELATIVE_SELF below carries the one
# sentence it cannot: "Fransa'da yasayan bir ciftciyim" puts its predicate three
# words out, and it is admitted by SHAPE rather than by distance. That split is
# deliberate - the sentence the old window 3 bought is the one participle shape
# that attaches to the subject, so it is cheaper to name the shape than to widen
# the window for all of them.
#
# WHAT TWO COSTS beyond what three already cost, measured: nothing in the accept
# set. Still refused, as at three: a location sentence whose predicate sits
# further out - "Fransa'da uzun suredir ciftcilik yapiyorum" (4 words),
# "Fransa'da kucuk bir arazide ciftcilik yapiyorum" (5) - and
# "Fransa'da bir ciftligim var", for a different reason: `ciftligim` carries the
# bare nominal ending _TR_FIRST_PERSON rejects, and `var` is not first person at
# all. NEW AT TWO, measured: "Fransa'da ben bugday ekiyorum" and "Fransa'da iki
# yildir ciftciyim", both predicate at word 3, both admitted at three. They are
# real statements of location and the loss is real - and it is not recoverable by
# a window, because they stand at exactly the distance
# "Fransa'da uretilen tohum kullaniyorum" stands at. The width cannot tell a
# speaker from a seed; only a shape can, which is what _TR_RELATIVE_SELF does for
# the one shape that was mandated. Admitting these two would mean naming their
# shapes too, and a refusal that hands a Turkish grower another country's figures
# for the whole conversation is the dearer of the two errors.
_TR_CLAUSE_WORDS = 2

# The scan stops at a clause boundary as well as at the word count, because the
# clause - not a span of two words - is the unit a predicate belongs to.
#
# IT IS NOT LOAD-BEARING AT TWO, and saying so is the point. Re-measured
# 2026-10-03 over the 27 refusals, boundary on against off at each width:
#
#   window   with boundary   without
#     2         0/27          0/27
#     3         7/27          7/27
#     4        10/27         12/27
#     5        10/27         12/27
#     6        10/27         14/27
#
# It starts earning its place at 4, where without it "Fransa'da staj yaptim,
# bugday ekeyim mi" and "Hollanda'da sera gordum, domates ekeyim mi" reach across
# the comma into the next clause's predicate, and at 6 it is also the only thing
# refusing "Amerika'da bugday fiyatlari nasil, ben bugday ekeyim mi" - one of the
# three sentences this guard exists to refuse - and "Almanya'da calisan bir
# arkadasim var, ona soruyorum". It is kept because that is what makes
# _TR_CLAUSE_WORDS safe to widen, not because it earns its place today.
_TR_CLAUSE = re.compile(r"[,;:.!?\n]")

# Trailing punctuation would otherwise defeat the `$` in _TR_FIRST_PERSON:
# "yasiyorum," is a word in `clause.split()` and does not end in `m`.
_TR_WORD_TRIM = "'\"()-,;:.!?…"

# THE THIRD TURKISH BRANCH, and the only one that reads a SHAPE rather than a
# distance: locative on the name, then a participle in `-yan/-yen/-an/-en`, then
# `bir`, then a first-person NOMINAL predicate. "Fransa'da yasayan bir
# ciftciyim", "Fransa'da calisan bir isciyim".
#
# WHY A SHAPE AND NOT A WIDER WINDOW. This sequence is the one participle phrase
# that attaches the place to the SPEAKER: the relative clause modifies the noun
# the first person is predicated of, so "the farmer living in France" IS the
# speaker. Every other participle sentence measured attaches the place to an
# OBJECT - "Fransa'da uretilen tohum kullaniyorum", where the seed is in France -
# and _TR_CLAUSE_WORDS cannot separate the two because they sit at the same
# distance. So this branch exists to hold the one accept that _TR_CLAUSE_WORDS = 2
# gives up, and it adds nothing else: measured 2026-10-03, it admits 1 of the 6
# accepts and 0 of the 27 refusals on its own.
#
# WHAT HOLDS THE OBJECT SENTENCES OUT IS THE FIXED LENGTH, measured, and NOT the
# `bir` or the nominal ending. The sequence is exactly three words, so the
# first-person word must stand immediately after the participle (or after `bir`),
# and in every object sentence a noun stands there instead: "Fransa'da uretilen
# TOHUM kullaniyorum". Re-measured 2026-10-03 over the 27 refusals, three looser
# forms of this pattern - `bir` optional, the present continuous allowed, and
# both - each admit 0/27 as well. So the two narrowings do NOT earn their place
# on this corpus and are kept on the argument instead: what licenses this branch
# is a relative clause predicating the speaker, `bir X-yim` is that clause, and a
# pattern that reads "participle then any first-person word" would be claiming
# something the measurement does not support. If a future accept needs a looser
# form, this is where to look, and the table above is what to re-take.
#
# "Almanya'da calisan bir arkadasim var, ona soruyorum" is the nearest miss in
# the refuse set, and it is refused by the ending: `arkadasim` is the bare
# nominal `-im`, which _TR_FIRST_PERSON rejects for its own measured reasons and
# the `y` in `y[iu][mz]` here inherits.
_TR_RELATIVE_SELF = r"\s+\w+[ae]n\s+bir\s+\w*y[iu][mz](?!\w)"

# The English twin, and it is NARROWER than country.py's `(?:in|at)\s+`: a bare
# preposition says where something is, not where the USER is. "I buy seed from
# India" and "the protein in Turkey feed" are the shapes that rule exists for,
# and country.py's own _EN_ORIGIN comment records measuring them. Only an
# enumerated first-person subject counts here, and `from` is admitted beside
# `in`/`at` because after one of these subjects it predicates the speaker
# ("I am from Kenya") rather than a purchase.
_SELF_EN = (r"(?<!\w)(?:i\s+am|i'm|we\s+are|we're|i\s+live|we\s+live"
            r"|i\s+farm|we\s+farm)(?:\s+based)?\s+(?:in|at|from)\s+")

# Same trim set src/context/country.py uses, for the same one reason: a message
# that is NOTHING BUT the country name is the natural reply to "hangi
# ulkedesiniz?", and that reply is a statement of location even though it carries
# no suffix at all.
_SELF_TRIM = " \t\n\r.,!?;:()\"'-…"


def _code_aliases(code: int) -> tuple[str, ...]:
    """Every folded name the FAO area `code` answers to.

    Read out of src/context/country.py's own folded table rather than rebuilt
    from data/country_aliases.json: the two guards below and that module must
    agree on what counts as a name for this country, and a second copy of the
    fold would be a second thing to keep in step.

    An EMPTY TABLE yields no aliases, which is how that module degrades when its
    data file is broken - and then both guards below refuse, the country lines
    are dropped and the province question stands. That is the same direction
    country._load chose for itself.
    """
    from src.context import country as country_ctx
    return tuple(name for name, (area, _turkish) in country_ctx._FOLDED.items()
                 if area == code)


def _first_person_follows(folded: str, pos: int) -> bool:
    """Whether the clause opening at `pos` has a first-person predicate in its
    first `_TR_CLAUSE_WORDS` words.

    `pos` is the end of a locative that ended its word, so this answers "is the
    thing in that place the SPEAKER" - see _TR_CLAUSE_WORDS for the measured
    width and what it costs.

    EVERY OCCURRENCE IS ASKED by the caller, not just the first: "Fransa'da
    fiyatlar yuksek, Fransa'da yasiyorum" has two locatives and only the second
    one carries the speaker.
    """
    clause = _TR_CLAUSE.split(folded[pos:], maxsplit=1)[0]
    for word in clause.split()[:_TR_CLAUSE_WORDS]:
        word = word.strip(_TR_WORD_TRIM)
        if _TR_VOLITIONAL.match(word):
            continue
        if _TR_FIRST_PERSON.search(word):
            return True
    return False


def _states_location(text: str, aliases: tuple[str, ...]) -> bool:
    """Whether `text` says the SPEAKER is in the country `aliases` names.

    One text, not a conversation: the caller decides which texts to ask about.
    """
    folded = _normalize_tr(text or "")
    if not folded:
        return False
    whole = folded.strip(_SELF_TRIM)
    for name in aliases:
        if whole == name:
            return True
        key = re.escape(name)
        if re.search(rf"(?<!\w){key}{_SELF_TR}", folded):
            return True
        # The second Turkish branch: case ending on the name, person on the verb.
        for match in re.finditer(rf"(?<!\w){key}{_TR_LOCATIVE}", folded):
            if _first_person_follows(folded, match.end()):
                return True
        # The third: the one participle shape that places the SPEAKER rather than
        # an object. Read by shape, not by distance - see _TR_RELATIVE_SELF.
        if re.search(rf"(?<!\w){key}{_TR_LOCATIVE}{_TR_RELATIVE_SELF}", folded):
            return True
        if re.search(rf"{_SELF_EN}{key}(?!\w)", folded):
            return True
    return False


def _one_fao_item(crop_ids: list[str]) -> bool:
    """Whether every one of these crop ids that maps to FAOSTAT at all maps to
    the SAME item - i.e. whether they all read one cell.

    Asked of a crop FAMILY, to decide whether the family's name describes the
    figure or only half of it. See the call site for the five families that fail
    this and what printing the family name cost them.

    An id with no FAO mapping is not counted: `Buğday (Hasıl/Yeşilot)` is green
    fodder and maps to nothing, so it cannot disagree with item 15 about what a
    wheat cell holds.

    A BROKEN OR EMPTY MAP RETURNS True, and that is unreachable rather than a
    chosen default: `norms._resolve_world` reads the same table and produces no
    figure at all without an item, so the caller has already returned [] before
    this can be asked.
    """
    from src import norms
    table = norms._load_fao_map()
    items = set()
    for crop_id in crop_ids:
        mapping = table.get(crop_id)
        item = mapping.get("fao") if isinstance(mapping, dict) else None
        if item is not None:
            items.add(item)
    return len(items) <= 1


def _shared_item_label(crop_ids: list[str], answering: str) -> str | None:
    """FAOSTAT's own name for the item `answering` reads, but ONLY when more than
    one of `crop_ids` reads that same item. None otherwise.

    THE QUESTION _one_fao_item ASKS IS ABOUT THE FAMILY; this one is about the
    CELL, and the two are not the same question. `_one_fao_item` says whether the
    family's name describes the figure. It can say no - the family spans two
    items - and the answering id's own label STILL be narrower than the cell,
    because that one item is shared by several Turkish ids. `Biber` spans items
    401 and 689, so the family name is too broad; and item 401 is shared by four
    Turkish peppers, so `Biber (Dolmalık)` beside 401's figure is too narrow. The
    third case is neither name, and this is the test for it.

    Measured 2026-10-03 over the shipped tables - 187 families against every
    FAOSTAT area, 8425 (family, country) rows that produce a figure - 331 rows
    were in that third case, over three families: `Biber` (item 401, four ids),
    `Bakla` (181, two) and `Fasulye` (176, two). `Bakla, Kuru (Yemlik)` was the
    worst of them, because data/crop_fao_map.json's own note on item 181 says
    FAOSTAT does not separate food-grade broad beans from feed-grade ones - so
    the printed name was contradicted by the map that supplied the figure.

    THE LABEL COMES FROM data/world_norms.json's `items` TABLE, which carries
    FAOSTAT's name for every item it ships figures for - `{"401": {"label":
    "Chillies and peppers, green ..."}}`. It is English, and that is the same
    choice the country name on the first line makes for the same reason: the name
    is part of the figure's provenance, and no file here publishes a Turkish name
    for an FAOSTAT item.

    A MISSING LABEL RETURNS None and the caller falls back to the id's label.
    Measured: of every item with a yield or price cell in the shipped world
    layer, zero are absent from the `items` table and zero carry an empty label,
    so this path is unreachable today - and the fallback is the narrow name
    rather than [] because a figure with a name that is too precise still answers
    the question, where no figure at all does not.
    """
    from src import norms
    table = norms._load_fao_map()

    def item_of(crop_id: str) -> object:
        mapping = table.get(crop_id)
        return mapping.get("fao") if isinstance(mapping, dict) else None

    item = item_of(answering)
    if item is None:
        return None
    if sum(1 for crop_id in crop_ids if item_of(crop_id) == item) <= 1:
        return None
    entry = norms._load_world().get("items", {}).get(str(item))
    label = entry.get("label") if isinstance(entry, dict) else None
    return label or None


def _country_lines(message: str, history: list[dict] | None) -> list[str]:
    """Where the user is when it is not a Turkish province, and what FAOSTAT
    publishes for the crop they named there. Empty list when the location itself
    is missing - and it NEVER raises, the way _named_crops does not.

    Read only after `extract_province` came back empty: a province is TÜİK and
    TÜİK always wins, which is the rule `norms.lookup` states and this caller
    must not contradict.

    A STATED LOCATION ALONE IS WORTH A LINE, with no figure under it. An earlier
    revision returned [] whenever there was no figure to print and justified it
    in this docstring by saying "the country's NAME only exists on a figure - it
    is FAOSTAT's label, carried on the value". THAT IS FALSE, and it cost the
    worst turn in the route: a grower answered "hangi ildesiniz?" with
    "Fransa'dayım" and was asked the same question straight back, because he had
    named no crop and the country line went with the figures. The name is in
    data/world_norms.json's `countries` table - `{"68": {"label": "France",
    "m49": "250"}}` - and needs no figure to exist. So the location line stands
    on its own, and the three ways a figure can be missing - no crop named, no
    cell for the crop in this country, nothing positive in the cell - all now
    print it without figures instead of falling back to the province question.

    THE FIGURE-LESS LINE DOES NOT SAY "FAOSTAT" and does not ask the answer to
    carry FAOSTAT's spelling, which the full first line does. The parenthesis
    there exists because several FAOSTAT areas collapse to one Turkish name
    (`Congo`, `Çin`) and a figure must be attributable to the right one. With no
    figure there is nothing to attribute, so the instruction would be noise - and
    it would put the word FAOSTAT in a block holding no FAOSTAT figure.

    TÜRKİYE AS A COUNTRY IS NOT A COUNTRY HERE. `data/crop_norms.json`'s
    national row is empty by construction, so a Turkish user who has not named
    a province resolves to no figure and the assistant asks - exactly today's
    behaviour, and this function returns [] before it can change it.

    A COUNTRY STICKS FOR THE WHOLE CONVERSATION AND THERE IS NO WAY TO TAKE IT
    BACK. `said` below is every user turn, not just this one, so once a grower
    has stated his country anywhere in the history, every later turn carries it -
    and that is deliberate (see the guard's own comment: `extract_country`
    returns the most RECENT mention, which need not be the turn that stated where
    he is, so stopping at the resolving turn would throw the conversation away).

    The cost is that nothing retracts it. A user who writes "Fransa'dayım" and
    then "aslında Konya'dayım" is served by TÜİK, because a resolved province
    wins before this function is called at all - but one who corrects himself to
    another COUNTRY, or who was placed abroad by a sentence he did not mean that
    way, keeps the first country for as long as the conversation lasts. There is
    no "I am not there any more" to write. Shortening the window to the resolving
    turn was measured and rejected for the reason above; the live protection is
    `_states_location`, which is why its refuse set is measured as carefully as
    it is. A new session is the only reset.

    ONE CROP, THE FIRST NAMED. A crop_choice message naming two crops never
    reaches this block at all: answer() forks it to the comparison card above.
    So the choice between families only ever decides which of the ids INSIDE
    one family answers.

    WHICH ID INSIDE THE FAMILY ANSWERS IS NOT ALWAYS DECIDED BY THE DATA, and an
    earlier revision of this docstring claimed it was - "settled by whichever of
    them FAOSTAT holds a cell for". That holds where exactly one id in the family
    maps to an FAO item: `Buğday (Hasıl/Yeşilot)` is green fodder and maps to
    nothing, `Buğday, Durum Buğdayı Hariç` maps to item 15. It does NOT hold
    where two ids SHARE one item, which data/crop_fao_map.json says happens -
    item 15 carries the note that FAOSTAT does not split durum from other wheat
    and both Turkish wheat ids point at it, and item 388 carries the same note
    for table against processing tomatoes. There the loop below returns whichever
    id `norms.available_crops()` happens to reach first, which is label order.
    It does not matter for the FIGURE, because the two ids read the same cell -
    which is why the printed name is the FAMILY's and not the id's; see below.

    THE PRINTED CROP NAME MUST DESCRIBE THE CELL, WHICH IS SOMETIMES THE
    FAMILY'S NAME AND SOMETIMES THE ID'S. Both halves of this were got wrong in
    turn, and the two failures point opposite ways:

      * The id's label can be NARROWER than the cell. `Buğday, Durum Buğdayı
        Hariç - FAOSTAT ulke ortalama verimi: 597,35 kg/da` for France, where
        item 15 is all wheat durum included, and `Domates (Salçalık) - ...
        47.889,02 kg/da` for the Netherlands, where item 388 is all tomatoes and
        overwhelmingly fresh. A paraphrase - "Fransa'da durum dışı buğdayın
        verimi 597 kg/da" - is a claim data/crop_fao_map.json disclaims in
        writing, on both items.
      * The family's name can be BROADER than the cell. Five of the 187 families
        map to TWO items, so the figure belongs to half the family: measured,
        `Fasulye - ... 241,36 kg/da` for France is its DRY bean where its fresh
        bean is 1242,07 the same year.

    So the name is chosen per family by `_one_fao_item`, not by a rule about
    names. See the call site, which carries the five families and their figures.

    REJECTED: keeping the id's label everywhere and adding a sentence saying the
    FAO item is broader. It needs the model to carry a qualification through a
    paraphrase, which is the thing prompt text is worst at; a name that describes
    the cell needs it to carry nothing.

    THE COUNTRY IS PRINTED AS FAOSTAT SPELLS IT - `France`, not `Fransa` - and
    that is deliberate rather than laziness. The label is part of the figure's
    provenance and travels on the value itself; translating it here would mint
    a Turkish name for `Iran (Islamic Republic of)` and `China, mainland` that
    no file in this repo publishes, and the alias table cannot supply one
    either - it is folded lowercase and holds several spellings per country.
    These lines are PROMPT context, not user-facing text, so the model is told
    in the same line to write the country's Turkish name in its answer.
    """
    try:
        from src import norms
        from src.context import country as country_ctx

        code = country_ctx.extract_country(message, history)
        if code is None or code == norms.TURKIYE_AREA:
            return []
        aliases = _code_aliases(code)

        # GUARD: a resolved country may only REPLACE the province question when
        # the user said that is where they are. See _SELF_TR for the three
        # measured sentences this refuses and what the refusal costs.
        #
        # EVERY USER TURN IS ASKED, not only the one `extract_country` resolved
        # from, and that leniency is deliberate. The code that came back is the
        # most RECENT mention; a statement of location made earlier in the same
        # conversation is still the user's. "Fransa'dayım" / "Fransa'da fiyatlar
        # nasıl" / "buğday mı eksem" resolves France off the middle turn, which
        # is not a location statement, while the first turn plainly is - and
        # stopping at the resolving turn would throw that conversation away.
        # It cannot admit the wrong country: only `code`'s own aliases are
        # tested, so a France statement can never licence Germany.
        #
        # Assistant turns are skipped for the reason country.extract_country
        # skips them: the assistant names countries while answering, and reading
        # its own words back would place the grower wherever its last example was.
        said = [message] + [turn.get("content", "")
                            for turn in reversed(history or [])
                            if turn.get("role") == "user"]
        if not any(_states_location(text, aliases) for text in said):
            return []

        # FROM HERE THE LOCATION IS SETTLED, SO THE PROVINCE QUESTION IS WRONG
        # WHATEVER ELSE IS MISSING. This is the whole return value when there is
        # no figure to print, and it is returned at all three of the exits below
        # rather than []. The figure is a bonus; the location is the finding.
        #
        # The worst turn it fixes: "hangi ildesiniz?" answered with
        # "Fransa'dayım" used to get "Kullanicinin ili BILINMIYOR - cevabinda
        # hangi ilde oldugunu sor" - the same question straight back, because no
        # crop was named and the country line travelled with the figures.
        #
        # The name is read from the `countries` table, which is the same string
        # `region` carries on a value, so the two paths cannot drift apart; see
        # the docstring for why this line says less than the full one.
        country_entry = norms._load_world().get("countries", {}).get(str(code))
        country_label = (country_entry.get("label")
                         if isinstance(country_entry, dict) else None)
        if not country_label:
            # Unreachable while the world layer answers at all - `_load_world`
            # refuses a file without a `countries` dict, and every area with a
            # cell is in it. Without a name there is no line to print, so this
            # degrades to the old behaviour rather than to a nameless sentence.
            return []
        located = [
            f"Kullanici Turkiye disinda: {country_label}. Cevabinda ulkenin "
            f"Turkce adini kullan. TUIK il verisi bu ulke icin yok, hangi ilde "
            f"oldugunu SORMA. Bu blokta bu ulke icin verim veya fiyat rakami "
            f"YOK - kendin rakam yazma, gerekirse kullanicinin kendi "
            f"rakamlarini sor.",
        ]

        # GUARD: a country whose Turkish name is ALSO a crop name must not supply
        # that crop. Measured on e021bca, "Mısır'dayım, bu yıl ne eksem?" - which
        # names no crop at all - printed Egypt's MAIZE yield and price, because
        # `Mısır` is the label for maize as well as the Turkish name for Egypt.
        # That handed the model one crop's figures and nothing else for an open
        # "what should I plant", against the same block's own
        # "BELIRLI BIR URUN ONERME", and on no basis whatever. Worse, `Mısır`
        # printed directly under `Egypt` reads as Egypt's own name, so the model
        # may report the maize yield as the country's.
        #
        # WHAT IS DROPPED is a family whose name folds to a name this RESOLVED
        # country answers to - not any country's name. `Fas` inside `Fasulye` and
        # `Hindistan` inside `Hindistan Cevizi` are untouched, because the family
        # names are `Fasulye` and `Hindistan Cevizi` and neither is an alias of
        # Morocco or India. Only the whole-name collisions go, which on the
        # shipped tables means `Mısır`.
        #
        # THE SPAN WOULD BE BETTER AND IS NOT AVAILABLE: dropping only the
        # OCCURRENCE the country resolver consumed needs to know where it
        # matched, and src/context/country.py returns an area code and nothing
        # else. So the cost is a measured over-refusal: "Mısır'dayım, mısır mı
        # ekmeliyim" names Egypt and maize, and loses the figures for both,
        # falling back to the province question. That is the same outcome
        # `test_a_country_with_no_crop_named_is_unchanged` already accepts for a
        # country named with no crop, and it is the safe direction - a question
        # instead of a figure nobody asked for.
        families = tuple(
            name for name in _named_crops(message)
            if _normalize_tr(re.split(r"\s*[(,]", name)[0].strip()) not in aliases
        )
        # AND THE FORK UPSTREAM COSTS MORE THAN ONE SENTENCE. answer() sends a
        # message naming TWO crops to the comparison card before this function is
        # reached, and that card is province-only - so a real Egyptian wheat
        # grower writing "Mısır'dayım, buğday mı ekmeliyim" never arrives here at
        # all and gets `crop_compare.NO_PROVINCE`, which asks for a Turkish
        # province. The fork is older than this branch and is not this change's
        # to move; it is written down because the drop above is not the only
        # place a Turkish country name costs an Egyptian grower his figures, and
        # a reader of this guard alone would conclude it was.
        if not families:
            return located
        family_name = re.split(r"\s*[(,]", families[0])[0].strip()
        family = _normalize_tr(family_name)
        matched = [(crop_id, label) for crop_id, label in norms.available_crops()
                   if _normalize_tr(re.split(r"\s*[(,]", label)[0].strip()) == family]
        # A CANDIDATE CARRYING BOTH MEASURES IS PREFERRED OVER AN EARLIER ONE
        # CARRYING ONE. The loop used to stop at the first id with `yield or
        # price`, which is label order, so a family whose dry id has only a yield
        # answered with that yield and no price while a sibling id held both.
        # Measured 2026-10-03 over the shipped tables - 187 families against every
        # FAOSTAT area, 8425 (family, country) rows that produce a figure at all -
        # 33 rows are in exactly that position, `Bakla` and `Bezelye` across most
        # of them.
        #
        # ONLY THE TIE IS BROKEN DIFFERENTLY. If no candidate carries both, the
        # first with either one still answers, which is the old behaviour
        # unchanged; and a candidate with both is still taken in label order, so
        # nothing here invents a preference between two complete ids.
        #
        # IT MOVES THE FIGURE AS WELL AS THE SECOND LINE, because a different id
        # can read a different FAO cell - that is the point, not a side effect:
        # one cell answering both questions is a coherent pair, where a yield from
        # one cell beside no price at all leaves the block half-built for no
        # reason the data gives.
        candidates = []
        for crop_id, _label in matched:
            candidate = norms.lookup(crop_id, None, country=code)
            if candidate is not None and (candidate.yield_kg_da
                                          or candidate.price_per_kg):
                candidates.append(candidate)
        norm = next((c for c in candidates
                     if c.yield_kg_da and c.price_per_kg),
                    candidates[0] if candidates else None)
        if norm is None:
            return located

        # WHICH NAME GOES BESIDE THE FIGURE, and it is NOT unconditionally the
        # family's. The family name is right only when every mapped id in the
        # family reads the SAME FAO cell, which is the wheat and tomato case -
        # item 15 does not split durum from other wheat and item 388 does not
        # split table from processing tomatoes, so `Buğday` and `Domates` describe
        # the cell exactly and the id's own label would narrow it.
        #
        # FIVE FAMILIES SPAN TWO ITEMS, measured 2026-10-02 over
        # data/crop_fao_map.json and data/crop_norms.json - 187 families, 5 of
        # them: `Fasulye` (176 dry / 423 fresh), `Soğan` (403 / 402), `Bezelye`
        # (187 / 417), `Bakla` (181 / 420), `Biber` (401 fresh / 689 dried). There
        # the bare family name is WORSE than the id's label, because the figure
        # itself belongs to half the family. `available_crops()` is sorted by
        # label, so which half answers is label order, not the question: measured,
        # "Fransa'dayim, fasulye ekeyim mi" printed `Fasulye - … 241,36 kg/da`,
        # which is France's DRY bean, where its fresh bean in the same year is
        # 1242,07 - five times as much, and a bare Turkish "fasulye" in a planting
        # question is usually the fresh one. `Soğan` printed 3363,2 (dry) against
        # 2105,36 fresh, `Bezelye` 292,48 (dry) against 637,42.
        #
        # So the two failures are opposite and both real: the id's label can be
        # narrower than the cell, and the family name can be broader than it. The
        # test is the mapping, asked per family, and it keeps each name on a cell
        # it actually describes.
        #
        # AND THERE IS A THIRD CASE, WHERE NEITHER NAME DESCRIBES THE CELL. The
        # family test above is asked of the family; it can fail - the family spans
        # two items - and the answering id's label still be narrower than the one
        # item it reads, because several Turkish ids share that item. `Biber`
        # spans 401 and 689, so the family name is too broad, and item 401 is
        # shared by four Turkish peppers, so `Biber (Dolmalık)` is too narrow:
        # measured, "Fransa'dayim, biber ekmek istiyorum" printed
        # `Biber (Dolmalık) - … 1502,9 kg/da` for a cell FAOSTAT calls "Chillies
        # and peppers, green". 331 of the 8425 rows are in this case, across
        # `Biber` (401, four ids), `Bakla` (181, two) and `Fasulye` (176, two).
        # There the cell has its OWN name and FAOSTAT publishes it, so the choice
        # is not between two wrong Turkish names - see _shared_item_label.
        crop_ids = [crop_id for crop_id, _label in matched]
        crop_name = (family_name if _one_fao_item(crop_ids)
                     else _shared_item_label(crop_ids, norm.crop) or norm.label)

        measures = [("ortalama verimi", norm.yield_kg_da),
                    ("ortalama ciftci fiyati", norm.price_per_kg)]
        figures = []
        for what, value in measures:
            # A figure that is not positive is not printed. FAOSTAT publishes
            # a handful of zero yields and this module's own rule is that a
            # missing norm is never zero - "ulke ortalama verimi 0 kg/da" in a
            # prompt is an invitation to answer that nothing grows there.
            if value is None or value.scope != "ulke" or value.amount <= 0:
                continue
            note = _flag_note(value.flag)
            # THE YEAR IS THE CELL'S OWN and is printed beside every figure,
            # never once for the block: FAOSTAT ends at 2024 where TÜİK reaches
            # 2025, and the two measures need not even share a year with each
            # other - Ghana's sorghum yield is 2024 and its price 2022.
            figures.append(
                f"{crop_name} - FAOSTAT ulke {what}: "
                f"{_world_amount(value.amount)} {value.unit} "
                f"({value.year}{', ' + note if note else ''})."
            )
        if not figures:
            return located

        region = (norm.yield_kg_da or norm.price_per_kg).region
        return [
            # THE FAOSTAT LABEL IS ASKED FOR IN THE ANSWER TOO, in parentheses
            # beside the Turkish name, and that is not decoration. Several
            # FAOSTAT areas collapse to ONE Turkish name - `Congo` and
            # `Democratic Republic of the Congo` are both "Kongo", `China` and
            # `China, mainland` are both "Çin" - so a prompt that is right about
            # which area the figure came from can still produce an answer that
            # names the wrong country, with nothing in the answer to tell. The
            # label travels into the answer so the reader can see which one.
            #
            # The label is NOT repeated a second time in this sentence: it
            # already stands at the head of the line, and `Netherlands (Kingdom
            # of the)` printed again inside parentheses nests them.
            f"Kullanici Turkiye disinda: {region} - FAOSTAT'in yazdigi ad. "
            f"Cevabinda ulkenin Turkce adini kullan ve yanina parantez icinde "
            f"FAOSTAT'in bu adini aynen ekle. TUIK il verisi bu ulke icin yok, "
            f"hangi ilde oldugunu SORMA.",
            *figures,
            # "tahmin" is deliberately NOT used in these two sentences, although
            # it is the natural Turkish word for it: the E flag's own clause
            # above is the only place that word may appear, so a test can tell an
            # estimate apart from a country's own report by looking for it.
            #
            # "kaynagi belliyse" RATHER THAN "kaynagi", because the older
            # unconditional wording was false for part of its own output. An
            # unflagged cell and an unknown letter both exist - _pick_world
            # returns flag=None for a cell FAOSTAT ships without one, and
            # _flag_note prints an unrecognised letter as itself - so the
            # parenthesis beside such a figure is just "(2024)". A line promising
            # a source beside every number would have the model look for one that
            # is not there, or invent it.
            "Bu rakamlar ULKE ORTALAMASIDIR, tarlaya ozel bir rakam degil; her "
            "rakamin yani sira kendi yili, kaynagi belliyse kaynagi da yazili - "
            "rakami baska bir yila veya TUIK'e mal etme.",
            # THE TWO FIGURES MUST NOT BE MULTIPLIED, and the caution line above
            # does not close this on its own: it immunises each figure against
            # being read as field-specific, and says nothing about their product.
            # Verim and fiyat sit on adjacent lines, so 597,35 x 0,2313 is one
            # step away and reads as 138 USD/da of income - a gross figure with
            # no cost side at all, which is exactly the shape a farmer acts on.
            # This project's own budget route exists because money answers need
            # both sides; see src/budget.py.
            "Verimle fiyati carpip donum basi gelir hesaplama ve yazma: masraf "
            "tarafi bu satirlarda yok, boyle bir carpim kazanc gibi okunur.",
        ]
    except Exception as exc:  # noqa: BLE001
        # The same bargain _named_crops makes: a failure here costs these lines
        # and nothing else, and it SAYS SO rather than looking like a country
        # that simply did not resolve.
        print(f"[engine] country context failed, continuing without it: {exc}")
        return []


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
        # Only once the province came back empty, and only as a REPLACEMENT for
        # the line that asks for one: a block that both names France and asks a
        # French grower which Turkish province he is in contradicts itself.
        # With no country, or with a country we hold no figure for, nothing
        # changes - the ask stands exactly as it did.
        #
        # AND ONLY WHEN THE USER SAID THAT IS WHERE HE IS. Replacing the ask on
        # any mention of any country was measured wrong three times over - see
        # _SELF_TR, which names the sentences and what refusing them costs.
        # _country_lines returns [] for those now, so they land in the else
        # branch below and get the ask back, unchanged.
        world = _country_lines(message, history)
        if world:
            lines.extend(world)
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
        if table and not any(row.yield_kg_da or row.price_per_kg or row.yield_kg_tree
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
