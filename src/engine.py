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
        ARTICLES_JSON,
        EmbeddingModelMismatchError,
        PRODUCTS_JSON,
        SYSTEM_PROMPT,
        build_language_instruction,
        settings,
    )
    from .language import detect_language
except ImportError:  # pragma: no cover
    from config import (  # type: ignore
        ARTICLES_JSON,
        EmbeddingModelMismatchError,
        PRODUCTS_JSON,
        SYSTEM_PROMPT,
        build_language_instruction,
        settings,
    )
    from language import detect_language  # type: ignore


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
class RecommendedArticle:
    """An Akademi article from the company's own blog. `link` is its
    source_url - the key the mobile app's article screen looks it up by."""
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
    # At most one, and only under a model answer. Optional on the wire, so an
    # already-deployed client, which never reads it, is unaffected.
    article: RecommendedArticle | None = None
    # Crops the farmer may add to their profile with one tap - only when they
    # are deciding what to plant (see _crop_offer). The CLIENT asks; nothing is
    # saved here. Optional on the wire, like the cards.
    crop_offer: tuple[str, ...] = ()
    # The season-calendar card, on its own key like the other cards.
    season_form: dict | None = None

    def as_api(self) -> dict:
        return {
            "answer": self.answer,
            "recommended_products": [p.as_api() for p in self.recommended_products],
            "form": self.form,
            "dose_form": self.dose_form,
            "compare_form": self.compare_form,
            "article": self.article.as_api() if self.article else None,
            "crop_offer": list(self.crop_offer),
            "season_form": self.season_form,
        }


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
# Akademi article matching (embedding-based, same client as the catalog)
# --------------------------------------------------------------------------- #
# MEASURED 2026-10-29 on bge-m3, against a labelled set kept in
# evals/article_set.py (run: python -m evals.run_article_match). Two choices
# came out of it, neither obvious:
#
# The QUESTION ALONE is embedded - not question + retrieved context, as
# match_products does. Context dragged every query toward the generic
# fertilizer articles: at every threshold it showed 5-23 wrong articles where
# the question alone showed 0.
#
# 0.65 is the threshold, and it is set for NO WRONG ARTICLE rather than for
# reach. The highest-scoring wrong match seen was 0.627, so nothing lower holds
# that line. The price is reach: 16 of 24 labelled questions got their article
# on the set it was picked on, and 3 of 14 on a held-out set written afterwards -
# 0 wrong on both. A question that gets nothing is answered as before; a wrong
# article under an answer is the failure the PDF rules out ("cevaba uymuyorsa
# hiçbir ürün gösterilmez"). Re-measure before lowering it.
MIN_ARTICLE_SIMILARITY = 0.65

# Seven of the blog's posts are written for DEALERS - motivation, e-commerce,
# sales FAQs - and none belongs under a farmer's answer. Matched on the folded
# title, so a new dealer post is excluded without a code change. Folded "satış"
# is "satis", the head of English "satisfy"/"satisfaction" too - hence (?!f).
_DEALER_ARTICLE = re.compile(r"\b(?:bayi|satis(?!f)|e-ticaret)")


def _eligible_articles(data: list[dict]) -> list[dict]:
    """Articles that may be shown to a farmer: not addressed to dealers, and
    each title once - the scrape holds one post twice under two URLs."""
    seen: set[str] = set()
    out: list[dict] = []
    for a in data:
        title = _normalize_tr(str(a.get("title", "")))
        if not title or not a.get("source_url") or _DEALER_ARTICLE.search(title) \
                or title in seen:
            continue
        seen.add(title)
        out.append(a)
    return out


@lru_cache(maxsize=1)
def _load_articles() -> tuple[dict, ...]:
    """Load the eligible articles and embed each one once. The blob is title,
    excerpt and the head of the body: the body's opening carried the topic where
    a short excerpt did not (22 of 24 right at top-1, against 21)."""
    if not ARTICLES_JSON.exists():
        print(f"[engine] articles not found at {ARTICLES_JSON}")
        return ()
    try:
        data = json.loads(ARTICLES_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[engine] could not read articles: {exc}")
        return ()
    articles = _eligible_articles(data if isinstance(data, list) else [])
    if not articles:
        return ()
    blobs = [f"{a['title']}\n{a.get('excerpt') or ''}\n{(a.get('content') or '')[:800]}"
             for a in articles]
    try:
        embeddings = _get_embeddings_client().embed_documents(blobs)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] article embedding failed: {exc}")
        return ()
    return tuple({**a, "_embedding": emb} for a, emb in zip(articles, embeddings))


def match_article(query: str) -> RecommendedArticle | None:
    """The one Akademi article that clears MIN_ARTICLE_SIMILARITY, or None."""
    articles = _load_articles()
    if not articles or not query.strip():
        return None
    try:
        query_embedding = _get_embeddings_client().embed_query(query)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] query embedding failed: {exc}")
        return None
    score, best = max(((_cosine(query_embedding, a["_embedding"]), a) for a in articles),
                      key=lambda x: x[0])
    if score < MIN_ARTICLE_SIMILARITY:
        return None
    return RecommendedArticle(title=best["title"], link=best["source_url"])


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

def _label_head(label: str) -> str:
    """A crop label cut back to its family's name, as the table spells it.

    "Buğday, Durum Buğdayı Hariç" -> "Buğday"; "Domates (Salçalık)" ->
    "Domates"; "Fasulye" -> "Fasulye". The exclusion clause and the
    parenthetical variant both narrow a label to one id INSIDE a family, and
    every caller is asking which family a label belongs to.

    ONE COPY OF THIS SPLIT, because there were SIX and one of them was written
    one wave ago - three in this module, two in src/crop_compare.py, one in the
    country guard that has since been deleted. They can diverge silently and in
    the dangerous direction: change the split set in one place and a label stops
    being recognised as its family's, which reads as "not this crop" and opens
    whatever gate was asking. The module argues against exactly this twenty
    lines from one of the copies, in `_code_aliases`' docstring ("a second copy
    of the fold would be a second thing to keep in step").
    """
    return re.split(r"\s*[(,]", label)[0].strip()


def _family_head(label: str) -> str:
    """`_label_head` folded, which is the form every comparison wants."""
    return _normalize_tr(_label_head(label))


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
        # THIS ROUTE ASKS FOR THE PROVINCE ONLY, and `_ASK_LOCATION`'s invitation
        # to name a country deliberately does NOT reach it. `_country_lines` has
        # exactly one caller - `_crop_choice_block` - so a `fert_plan` user who
        # answered "Fransa'dayim" would be asked again on the next turn, having
        # been told to say the thing this route cannot read. A question whose
        # answer is discarded is worse than a narrower question.
        #
        # The world layer reaching `fert_plan` is a separate round: that route
        # serves a fertilization and irrigation plan, and FAOSTAT publishes
        # neither - it publishes yield and price, which is what `crop_choice`
        # needs. See docs/client-requirements.md §8 on the season programme.
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
#   "Amerika'da bugday fiyatlari nasil, ben bugday ekeyim mi"      -> USA
#
# All three are plausibly Turkish farmers, and the country each one names is a
# buyer, a greenhouse they admire and a price reference. The recall that resolves
# them belongs to src/context/country.py; what belongs HERE is that a resolved
# country was allowed to REPLACE the province question.
#
# TWO PATTERNS, AND NEITHER OF THEM INFERS ANYTHING. This guard is the smallest
# it has ever been, and that is the decision this wave carries out rather than an
# accident of pruning. Over five waves it grew rules that worked out from Turkish
# morphology WHERE THE SPEAKER IS: a window of N words after the locative, a
# tense, a participle shape, a residence-verb whitelist, an owned-land branch, a
# bare-name branch gated on the assistant's own question. FOUR REVIEWS WERE RUN
# AND ALL FOUR FOUND A CRITICAL IN THIS GUARD, and every one was one defect:
#
#   THE MEASUREMENT THAT LICENSED A RULE DID NOT TEST THE DECISION IT MADE.
#
#   * the shape branch's "0 of 27 refusals"  - 1 of the 27 could reach it
#   * its successor's "0 of 42"              - NONE reached the shipped gate
#   * the land branch's "16 reach / 0 admitted" - the 16 reach the `<possessed>
#     var` SHAPE. Its real decision was to read the WHOLE CLAUSE with no
#     adjacency, and 0 of the 86 refusals put a whitelisted land noun behind an
#     object locative, so nothing could fail: "Fransa'da uretilen tohumu ektigim
#     bir tarlam var" and eleven like it were admitted, 12 of 12.
#   * the verb whitelist's "20 of 86"        - 20 SIMPLE verbs and not one
#     light-verb construction, so `-mAyA calis-` was free and "Almanya'da satmaya
#     calisiyorum", the canonical Turkish exporter, was placed in Germany.
#   * the volitional skip's "0 accepts and 0 refusals either way" - a SKIP can
#     only ever ADMIT, and 0 of the 86 put an `ist`-prefixed word in a participle
#     slot, so `istenen` and `istedigim` rode in free.
#
# None of those zeros was wrong arithmetic. Each counted the inputs that ENTER
# the branch instead of the inputs that could BREAK the decision under test - and
# from inside a rule that reads a sentence it cannot parse, that difference is
# not visible. So the inference is gone, and what remains are the two patterns
# whose decision is small enough for a refuse set to test:
#
#  * _SELF_TR - the LOCATIVE person suffix FUSED TO THE NAME, nothing in
#    between: "Fransa'dayim", "Ganadayim". It reads no window, no verb, no
#    clause, no conversation. Across five waves it produced ZERO Criticals, and
#    it is the only branch here that produced none. Its `-lI` arm - the
#    nationality - was dropped afterwards; see the comment on the pattern.
#  * _SELF_EN - its English twin: an enumerated first-person subject, then
#    `in`/`at`/`from`, then the name, adjacent.
#
# WHAT THIS COSTS: 39 OF THE 41 TURKISH ACCEPTS. They are counted, listed and
# pinned as costs in `_SURRENDERED_ACCEPTS` (tests/test_engine.py).
# "Fransa'da yasiyorum", "Fransa'da ciftciyim", "Fransa'da tarlam var",
# "Fransa'da yasayan bir ciftciyim" and 35 more are real statements of location,
# and every one of them now gets the location question back instead of figures.
# That is the largest single loss on this branch and the direction is deliberate:
#
#   A REFUSAL COSTS ONE QUESTION. A WRONG ADMISSION IS SILENT, WRONG AND STICKY.
#   `_country_lines` asks every user turn, so a sentence read wrongly once
#   carries the rest of the conversation and prints "hangi ilde oldugunu SORMA"
#   beside another country's average figures to a grower in Turkiye, with nothing
#   to retract it. The question is recovered the moment the user writes
#   "Fransa'dayim" - and `_ASK_LOCATION` now asks for exactly that spelling,
#   which is why the question text changed in the same commit as the deletion.
#
# THE REFUSE SET IS 99 AND 0 OF IT IS ADMITTED. Deleting rules cannot admit
# anything, so every one of the 86 refusals the five waves earned still refuses;
# five of the thirteen new ones are the suffix's own near misses, listed below,
# four are the `-lI` nationality dropped after this wave, and four are the name's
# RIGHT boundary (see below again). Re-measured
# PER BRANCH rather than as a pair, because deleting a rule moves which rule
# refuses a sentence even when it admits nothing: each surviving pattern admits
# 0 of the 99 on its own, so neither is carrying a class only the other held.
#
# REJECTED: keeping the bare-name branch - "Fransa" alone, counted as a location
# because the assistant had just asked where the user is. The idea is right and
# ITS EVIDENCE CANNOT EXIST. The assistant's question is generated, not a string
# this repo owns, so the gate had to match place WORDS - and then it fires on any
# turn that merely mentions a place. Measured: 10 of 10 realistic non-asking
# turns opened it, and one of the ten is `crop_compare.ASK_FOR_CROPS`, a SHIPPED
# literal returned verbatim as an assistant turn - it asks which two CROPS and
# contains "ilinizde". With that turn in the history, "Fransa" typed as an answer
# to the CROP question placed the user in France for the conversation. A gate
# that a shipped string of our own defeats is not a gate, and no test could have
# caught it from the gate's side: its refuse set held six negatives and not one
# of them used a place word in a non-asking role. The recovery lives in
# `_ASK_LOCATION` instead, which costs one extra turn and cannot misfire.
#
# REJECTED: accepting the place-noun form src/context/location.py accepts
# ("Fransa kosullarinda"). For a province it is how growers state where they are;
# for a country "Fransa kosullarinda bugday ekilir mi" is a Turkish grower asking
# ABOUT France, which is the class of the three sentences above.
#
# REJECTED: adding the country lines and keeping a SOFTENED ask beside them. The
# ask is for a Turkish province, and no softening of that question is not still
# wrong to put to a grower in France.
#
# NOT GATED ON WHETHER THE ALIAS IS SPELLED IN TURKISH, which country.py does
# gate its own suffix branch on. This test can only NARROW a code that module has
# already returned, so a Turkish suffix admitted on an English spelling cannot
# introduce a country that was not resolved.
#
# THE REACH COUNT THAT BELONGS BESIDE THIS BRANCH'S ZERO, and it counts the
# inputs that could break THIS decision rather than the inputs that reach the
# branch. The decision is "the person suffix sits on the NAME, with nothing in
# between". What could break it is a `-yIm`-shaped word somewhere ELSE in the
# sentence, because a rule that read the clause instead of the name would admit
# those. Measured over the 99 refusals: 44 carry one - `dayim`, `tayim`,
# `koyum`, `sayim`, `payim`, `soyum`, `yayim`, `ekeyim`, `kurayim`, `ekmeliyim`,
# `ciftciyim`, `ureticiyim`, `sucluyum`, `tohumcuyum` - and _SELF_TR admits 0 of
# the 99. That is the measurement the five deleted rules never had: the 44 are
# exactly the inputs a looser reading of this one decision would get wrong.
# FOURTEEN FORMS, AND THE LIST USED TO NAME THIRTEEN: restricted to the thirteen
# it printed the count is 41, not 44, and the form it left out is `yayim`
# ("Hollanda'da cikan bir yayim var"). The number was derived by a test and the
# enumeration was prose, so only the prose went stale - and the enumeration is
# the half a reader uses.
#
# AND THE NAME HAS A RIGHT BOUNDARY TOO, which is the third way this one decision
# can fail and the refuse set could not reach it until now. `(?<!\w)<alias>`
# anchors the LEFT side; nothing anchors the right side of the NAME, so a token
# that merely STARTS with an alias and runs on into the locative letters would be
# read as that country. Measured: 4 of the 99 refusals are of that shape, 0 of
# them admitted, and before they were written down the count was 0 - so this
# branch's zero said nothing about its right boundary. The four, and each is a
# sentence a grower could type:
#   Cine'deyim          `cin` + `e'deyim`  - a district of Aydin, not China
#   Nijerya'dayim       `nijer` + `ya'dayim` - Nigeria, handed Niger's aliases
#   Maliyedeyim         `mali` + `yedeyim` - the Treasury, not Mali
#   Cadirdayim          `cad` + `irdayim`  - a tent, not Chad
# The project's own Turkish corpus was swept for the leak as well
# (data/vector_store/chroma.sqlite3, 81 426 documents, all 418 folded aliases):
# 0 documents match this pattern at all, and of the tokens that end in the
# locative-plus-person letters not one has a country alias as its prefix. So the
# decision was already sound; what was missing was the evidence.
#
# REJECTED HERE, RECORDED AS A LEAD: the `-n` buffer, `'?n?[dt][ae]y[iu][mz]`.
# A Turkish compound name carrying a 3sg possessive takes it, and THE WIDENING
# THIS PARAGRAPH USED TO DEFER IS NOW SHIPPED - see `_alias_key`, which spells
# the buffer and gates it by name length. What it defers to is written below,
# because the condition it set was met rather than waived.
#
# The hole it closes: 22 `tr` aliases over 19 FAO codes end in a 3sg possessive,
# so their case ending needs a buffer `n` - "Rusya Federasyonu'ndayim", "Cin
# Halk Cumhuriyeti'ndeyim", "Amerika Birlesik Devletleri'ndeyim" and 19 more.
# `extract_country` resolved every one of them and this guard refused every one,
# so the assistant asked a Russian grower which Turkish province he farms in.
# (The figure read "18 countries" here until 2026-10-08 and in two other
# comments; it is 22 aliases / 19 codes, counted from the table by
# tests/test_country.py and no longer written down anywhere by hand.)
#
# THE ZERO THIS WIDENING WAS NOT ALLOWED TO RIDE IN ON: it leaks 0 of the 99,
# and that zero is worthless, exactly as the previous revision of this paragraph
# said - 0 of the 99 refusals put an `n` between the name and the locative, so
# not one of them could break the decision the `n?` makes. The refuse set was
# not widened to make the zero look better; it was widened until it could FAIL.
#
# WHAT IT WAS MEASURED AGAINST INSTEAD, built to reach the buffer branch and
# kept in tests/test_engine.py beside the 99 rather than folded into it - five
# other measurements here quote that denominator for other decisions:
#  * 220 NEAR MISSES, the five in `_SUFFIX_NEAR_MISSES` re-spelled on all 22
#    compounds in both spellings - `…ndaydim` (past), `…ndayken` (while),
#    `…ndalar` (3pl), `…ndaki` (relativiser), `…ndan` (ablative). Reported in
#    tiers, because only the leak is a zero: 220 of 220 ENTER the buffer branch,
#    88 of them reach the PERSON SLOT (`…n[dt][ae]y`, where only the person
#    vowel turns them away), and 0 are admitted. Those 88 are the first
#    non-vacuous denominator this branch has ever had.
#  * 88 ACCEPTS, `-ndayim`/`-ndayiz` with and without the apostrophe on all 22.
#    0 admitted before, 88 now. THE APOSTROPHE COLUMN IS HALF THE DEFECT: that
#    spelling was never broken in country.py, so it is easy to read this as a
#    fix for the apostrophe-less form arriving late - but this guard refused
#    both, so the apostrophe user was no better off either.
#  * 72 SHORT-ALIAS REFUSALS, which is what turned an `n?` in the pattern into
#    `_alias_key`'s gated buffer. See that function; the leak was reachable.
#  * PARITY WITH THE NON-BUFFER TWIN on every shape the shipped corpus holds:
#    whatever this guard does to "Fransa'daydim" it must do to "Rusya
#    Federasyonu'ndaydim". 63 source sentences x the 22 compounds = 1.386
#    twins, 0 disagreeing - and the test asserts that product rather than this
#    sentence, so neither figure can go stale again. Parity is the right test
#    and absolute refusal is not: the Turkish arm carries no left veto, so
#    "sanki Fransa'dayim gibi" is admitted at this tip, and the buffer must not
#    change that in either direction.
#  * AND THE 792 FROM country.py's SIDE ARE NOT ENOUGH, which is worth saying
#    because they were offered: those sentences put a SPACE after the locative
#    ("…nda calisan bir dayim var"), so 792 of 792 enter the buffer branch and
#    0 reach the person slot. They cannot test this decision at all.
#  * THE RIGHT BOUNDARY, re-swept with the buffer in place, over
#    data/vector_store/chroma.sqlite3: 81.426 documents, folded with
#    `_normalize_tr` and tokenised as `[a-z0-9]+`, giving 262.439 distinct words
#    and 10.934.980 tokens. THE TOKENISATION IS STATED BECAUSE IT MOVES THE
#    FIRST RUNG: counting `[a-z0-9']+` instead keeps "turkiye'nin" as one token
#    and reads 271.768 distinct words, and an earlier revision of this comment
#    quoted the first rung from that run without saying so, which made it
#    irreproducible.
#
#    Reported as a ladder over the 391 LONG folded aliases - the set
#    `_alias_key` actually buffers - because only the last rungs are zeros and a
#    zero on its own says nothing:
#      <alias> + n + anything       42 tokens, 752 occurrences
#      <alias> + n + [dt][ae]        0 tokens
#      <alias> + n + [dt][ae] + y    0 tokens
#      the full shape, placed        0 tokens
#    So for every alias that gets the buffer, the attested collision count is
#    already 0 at the second rung, and 42 tokens / 752 occurrences is the set
#    that could have made it otherwise.
#
#    THE SAME LADDER OVER ALL 418 ALIASES IS WHERE THE GATE SHOWS ITS WORK,
#    because the gate's whole claim is that the danger sits in the short keys:
#      <alias> + n + anything       88 tokens, 1.031 occurrences
#      <alias> + n + [dt][ae]        2 tokens,     7 occurrences
#      <alias> + n + [dt][ae] + y    0 tokens
#    Both second-rung tokens are on FOUR-character keys, which is exactly what
#    `_alias_key` refuses to buffer: `malinda` x5 is `mali` + `nda`, the
#    ordinary word "malında", and `korentajar` x2 is `kore` + `ntajar`.
#    `silindir` x38 (`sili` + `ndir`) is a near miss one rung lower - it never
#    reaches the second rung at all, because `i` is not `[ae]` - and is named
#    here only because it is the most frequent `<short alias> + n` token in the
#    corpus. `_NAME_BOUNDARY_REFUSALS` is what the same sweep produced for the
#    un-buffered branch. See `_alias_key` for what the gate costs and buys.
#
# WHAT IT COSTS, named rather than discovered later: ten long aliases have an
# attested Turkish word at `<alias>n` - `amerikan`, `italyan`, `kenyan` and
# seven more - so "amerikandayim" now PLACES a speaker where it only resolved
# before. `-n` there is a DEMONYM, not a possessive, and this is the same
# question `-lI` was decided on one commit earlier: a nationality is not a
# location. The two differ in what follows, and it decides them differently.
# "Amerikaliyim" predicates the SPEAKER - he is American, wherever he stands -
# while "amerikandayim" predicates a PLACE and says the speaker is in it; a
# demonym cannot take a locative without a head noun, so the only Turkish
# reading of the string is "I am at the American('s)", which is not a
# nationality claim at all. It is admitted, as a measured cost of 10 aliases out
# of the 209 long TURKISH ones and 0 attested occurrences in 10.9M words, and
# ALL TEN are pinned by `_DEMONYM_LOCATIVE_COSTS` - not as evidence of presence,
# but because refusing it would need a rule that reads the word before the name
# to notice the missing head noun, which is the inference this branch spent four
# waves taking out. The list carried four of the ten for one commit while this
# sentence claimed ten, which is the drift that list now exists to stop.
#
# AND THE CODE'S REACH IS WIDER THAN THAT COST, which is worth saying because
# the two numbers are easy to read as the same one. `country.py` gates its
# Turkish suffix branch per alias with `if turkish else never`; THIS GUARD HAS
# NO LANGUAGE GATE and applies `_SELF_TR` to every alias of the resolved code,
# English spellings included - that is pre-existing, not something the buffer
# brought. What the buffer does is widen it: of the 391 long aliases 182 are
# English-only, and 41 of those have an attested `<alias>n` word in the corpus
# (`american` x1.257, `indian` x757, `australian` x476, `russian` x245 …), so
# this guard would place a speaker on "americandayim" for all 41. NONE OF IT IS
# REACHABLE and that is measured rather than assumed: `extract_country` returns
# None for all 41, because its own Turkish branch is gated by language, so
# `_country_lines` never gets as far as asking this guard. The cost above is
# scoped to the Turkish aliases for that reason, and the reach is written here
# so the next reader does not have to re-derive the difference.
#
# WHAT THE WHOLE CHANGE BUYS, end to end and through the one caller. The figure
# worth quoting is the one the suite pins, because it is the one made of Turkish
# a grower would actually type: the 88 grammatical self-statements in
# `_BUFFER_LOCATIVE_ACCEPTS` - the 22 compounds, both spellings, singular and
# plural - go from 0 placed to 88 placed.
#
# A WIDER SWEEP READS LARGER AND IS WORTH LESS: over 924 conversations built by
# forcing the buffer onto every compound in six message shapes and seven
# histories, `_country_lines` produced 78 country lines before and 439 after.
# Most of that 361 is `Israil'ndeyim`-shaped - a buffer on a name that carries
# no possessive, so a typo rather than a sentence - and quoting it as the gain
# overstates what a user gets by roughly four times. 88 is the honest number.
#
# EITHER WAY THE RESOLVER'S HALF ALONE BOUGHT 0 LINES, against 287 resolves,
# which is why the two halves shipped together; see the ledger's `ee43c18`,
# where the same pair had to.
# 0 of 194 supplier or third-party conversations gained a line. The 88 that do
# gain one all have an earlier user turn stating the location, which is the
# leniency `_country_lines` documents at its `said` list and not a leak.
#
# AND THE SUFFIX'S OWN NEAR MISSES, the other way one decision can fail - the
# letters `[dt][ae]` followed by something that is not `-yIm`. All five refused,
# and pinned in `test_the_fused_suffix_is_the_whole_decision`:
#   Fransa'daydim   PAST, "I was in France"     `y` then `d`, not a vowel
#   Fransa'dayken   "while I was in France"     `y` then `k`
#   Fransa'dalar    THIRD person plural         no `y` at all
#   Fransa'daki     the relativiser             no `y` at all
#   Fransa'dan      ablative                    not a locative
#
# `-lI` IS A NATIONALITY AND IS NOW REFUSED. "Hollandaliyim" is "I am Dutch",
# not "I am in the Netherlands" - it states where the speaker is FROM, and a
# Dutch grower farming in Antalya says it truthfully while standing in Turkiye.
# It was admitted for four waves and declared in every revision of this comment
# as "weaker evidence of presence", which is the shape of a thing nobody had
# decided. It is decided now, on this wave's own rule: a nationality is an
# INFERENCE about location, and inference is what came out.
#
# IT IS THE SAME TRADE AS THE BARE NAME, and taken for the same reason: the
# speaker writes "Fransaliyim", gets `_ASK_LOCATION` back, writes "Fransa'dayim"
# and is placed. One turn, against a class of silent wrong placements for every
# foreign national living in Turkiye who has not named a province.
#
# WHAT STAYS IS THE LOCATIVE ALONE - `-da/-de/-ta/-te` fused to the name and
# carrying the person. One decision, one shape, and the reach count above is
# measured against it.
#
# THE BUFFER `n` IS NOT IN THIS PATTERN, and that is deliberate rather than an
# omission: it is spelled in `_alias_key`, because it belongs to the NAME. A
# possessive's linking consonant is part of the possessive, the case ending is
# `-da` either way - and, the reason that matters here, the buffer is only legal
# on a name long enough to carry a possessive. Read `_alias_key` for the
# reachable leak an ungated `n?` in this line was measured to open.
_SELF_TR = r"'?[dt][ae]y[iu][mz](?!\w)"

# The English twin, and it is NARROWER than country.py's `(?:in|at)\s+`: a bare
# preposition says where something is, not where the USER is. "I buy seed from
# India" and "the protein in Turkey feed" are the shapes that rule exists for,
# and country.py's own _EN_ORIGIN comment records measuring them. Only an
# enumerated first-person subject counts here, and the preposition after it must
# be `in` or `at`.
#
# `from` USED TO BE ADMITTED BESIDE THEM AND IS NOW REFUSED, on the same rule
# that dropped `-lI` from _SELF_TR: `from` STATES AN ORIGIN, AND AN ORIGIN IS NOT
# A LOCATION. "I am from Kenya" is this branch's own old justification and it is
# the English translation of "Hollandaliyim" - a grower says it truthfully while
# standing somewhere else, so placing him on it is an INFERENCE, which is the
# thing this guard stopped making. The sentence that settled it:
#
#   "I am from the Netherlands, my farm is in Antalya"
#
# was admitted, resolved 150, and printed "Kullanici Turkiye disinda: Netherlands
# (Kingdom of the) ... hangi ilde oldugunu SORMA" to a grower who had written
# where his field is IN THE SAME SENTENCE - and `_country_lines` asks every user
# turn, so it stuck for the whole conversation. The arm survived the `-lI`
# decision by one commit because the zero that licensed it was taken over inputs
# that could not break it: 0 of the 25 refusals put a whitelisted subject
# immediately before `from`, and the two that carried the word `from` at all were
# refused by the SUBJECT decision instead. That is the fifth instance of the
# family named above _SELF_TR, and the refuse set now has a class for it.
#
# Dropping it cost nothing measurable: 0 of the 14 accepts pinned AT THE TIME
# used `from` (the set is 16 now and still 0, re-measured this wave),
# and 0 of the 25 refusals were being held by it. `extract_country` still
# RESOLVES "I am from Kenya" - resolving a name and placing a speaker are
# different questions and only the second one is this guard's, which is the same
# split the `-lI` decision drew.
#
# THE POSSESSED-NOUN SUBJECTS ARE GONE, and this is where the paragraph
# recommending them used to stand. It said `my farm is in` / `my field is in` /
# `our farm is in` "are the same whitelist logic one step along ... the
# possessive is what does the work", in the present tense and affirmatively,
# a hundred lines above its own refutation - for one commit, because the commit
# that deleted them was a single hunk at the bottom of this comment. What
# replaced them, why, and what it cost are below.
#
# ITS REFUSE SET IS 58 NOW, AND IT HAD NONE AT ALL FIVE WAVES AGO. It is one of
# the two surviving branches, so it is measured the way the Turkish side is,
# with the reach counts beside the zero rather than the entry counts. THERE ARE
# FOUR DECISIONS HERE AND NOT THREE - the subject, the adjacency, WHICH
# PREPOSITION COUNTS AS PRESENCE, and WHOSE `i` IT IS - and the fourth had no
# count beside it at all until the seventh review. Each is counted against the
# NAME, because a count taken over the sentence instead inflates on a second
# clause that says nothing about the decision:
#
#   refusals                                                         58
#   admitted by the branch                                            0
#   naming a country extract_country resolves (the rest test nothing) 54
#   ANY SUBJECT, THEN `in`/`at`, THEN THE NAME -                      35
#     the only inputs that can break the PERSON decision. Partitioned
#     below, because a total can be right while its cells lie.
#   A FIRST-PERSON SUBJECT IN THE SENTENCE AND A BARE `in`/`at` IN
#   FRONT OF THE NAME -                                               23
#     the only inputs that can break the ADJACENCY decision: a verb and
#     an object stand between the subject and the preposition, as in "I
#     sell wheat in Germany" or "I studied in France". 5 of the 23 are
#     that shape; the other 18 are the two classes below, which this
#     wording also reaches and says nothing about.
#   A WHITELISTED SUBJECT, THEN `from`, THEN THE NAME -               10
#     the only inputs that can break the PREPOSITION decision, and this
#     count was 0 until `from` was dropped: "I am from Kenya", "we are
#     from France", "I am from the Netherlands, my farm is in Antalya"
#     and seven more.
#   THE PATTERN MATCHES AND A MOOD WORD OR AN ATTRIBUTING VERB TOUCHES
#   THE SUBJECT -                                                     18
#     the only inputs that can break the MOOD and ATTRIBUTION
#     decisions, i.e. what a rule without `_EN_NOT_THE_SPEAKER` would
#     admit. Over the 42 that shipped `(?<!if\s)` this count was 2, and
#     both carried the literal `if` the code happened to read - which is
#     how four other spellings of the mood and a whole attribution class
#     were admitted under a comment claiming the line was the mood.
#
# THE PERSON COUNT WENT 13 -> 19 -> 35 AND THE PARTITION IS THE MEASUREMENT.
# A reach count can be neither stale nor vacuous and still lie by being
# partitioned wrongly, which the sixth review found and the seventh found again
# one level down. The 35 splits by the sub-decision each refusal can break, and
# it splits exactly:
#
#   13  (a) a THIRD PARTY in the subject slot - "he is in France", "the
#           farm is in France", "the company is based in France"
#    5  (b) a first-person possessive inside a LARGER subject - "the
#           supplier of my farm is in France"; the sixth review's Critical
#    8  (c) an ATTRIBUTED `i`, which is somebody ELSE's - "he said 'i am
#           in France'"; the seventh review's Important 1
#    9  (d) a SUPPOSED mood - "assuming i am in France"; the seventh
#           review's Critical. 9 and not 10 because "if i'm in France the
#           prices are different" has no space before the `'m`, so the
#           loose person frame does not model it.
#
# Cells (c) and (d) were the EMPTY ones at `4a1af74`: (c) held nothing at all
# and (d) held the single `if` sentence the code read, and both had measured
# live admissions placing a grower abroad and suppressing the province question
# for the rest of the conversation. An empty cell under a correct total is the
# shape this guard has now been reviewed for seven times.
#
# THE ADJACENCY COUNT READ 8, THEN 5, AND READS 23 NOW, and the reader is owed
# the partition rather than the total: 5 (a) + 0 (b) + 8 (c) + 10 (d). The 5
# measure adjacency; the 18 would be admitted by a rule that relaxed adjacency
# alone, so they belong in the count by its own definition while testing
# nothing about adjacency. That overlap is the argument FOR the fourth count,
# not against the third. The old wording - "a first-person word anywhere in the
# sentence AND a preposition anywhere in the sentence" - returns 27 over the 58
# and 5 over the old 25, and "I buy seed from France" satisfies it while being
# refused by the SUBJECT decision; the same for the person count, whose loose
# wording returns 39 over the 58 against 13 over the old 25. (43, not 39, if the
# loose wording is taken with the preposition set the old rule actually had:
# before `c218ae0` this branch admitted `from`. Two reviews printed that number
# measured with the NEW set, which is neither the old rule nor anything shipped.
# The point it serves is stronger at 43.)
#
# TEMPORARY PRESENCE IS ADMITTED, AND THAT IS A DECISION, not a gap. "I am in
# France for the fair", "I am in France this week", "we are in France visiting a
# supplier" all resolve France, and the fifth class a review found missing from
# this set is missing because it belongs on the OTHER side. Two reasons, and the
# first is the stronger: the Turkish twin "Fransa'dayim, fuara geldim" is
# admitted by _SELF_TR and cannot be refused without reading the rest of the
# sentence, which is the inference this wave deleted - so refusing the English
# one would make the two surviving branches disagree about the same speaker. And
# a grower who IS in France this week is in France: FAOSTAT's French figures are
# the right context for the question he is asking from there. What is wrong
# about it is only that `_country_lines` makes it stick for the whole
# conversation, which is that function's own recorded open item and not this
# pattern's to fix. Pinned as accepts in `_ENGLISH_ACCEPTS`, not as a gap.
#
# AND SO ARE THE FUTURE AND THE FIRST WORD OF A LONGER FOREIGN PLACE NAME -
# THREE DECLARED ACCEPTS, DOWN FROM FOUR. They are declared on the same rule as
# temporary presence and for one measured reason: REFUSING THEM NEEDS THE TAIL
# OF THE SENTENCE, and reading the tail is what this branch's history rejected
# with a table.
#
#   I am in India tomorrow                                100
#   I am in Lebanon, Ohio                                 121
#   we are in Peru, Indiana                               170
#
# `tomorrow` and `, Ohio` ARE the tail, and every candidate tail word was
# measured damaging - `and`, the comma and the full stop included - because "my
# field is in Egypt for..." and "the protein in turkey for..." have the same
# tail. Bringing the tail back brings back the inference the wave before this
# one deleted. `I am in Lebanon, Ohio` is one level down from the `Georgia`
# decision in `country._NOT_THIS_PLACE`: FAOSTAT has no US-state area, and US
# towns named after countries are the same hazard with a comma instead of a word
# boundary. These two were written with `my farm is` until the sixth review,
# which made them refusals of the SUBJECT rule and stopped them measuring the
# tail decision they exist for.
#
# THE CONDITIONAL USED TO BE THE FOURTH AND IS A REFUSAL NOW, and the argument
# that kept it was written here: "the damage is also small ... a grower asking
# 'If I am in France next year, should I plant wheat' IS THINKING ABOUT FRANCE,
# and FAOSTAT's French figures are the right context". It lost on the second
# half. He is thinking about France and he is not IN it, so the block prints
# "Kullanici Turkiye disinda: France ... hangi ilde oldugunu SORMA" - it tells a
# grower in Turkiye not to say which province he is in - and `_country_lines`
# asks every user turn, so it sticks for the conversation. That is the same harm
# the `from` arm was deleted for, and it was sitting under a paragraph calling
# it small.
#
# THE SUBJECT MUST BE A FIRST-PERSON PRONOUN. The possessed-noun subjects -
# `my farm is`, `our farm is`, `my field is`, `my fields are` - were dropped
# after the sixth review, and they were dropped as a CLASS rather than patched:
#
#   `(?<!\w)` IS A WORD BOUNDARY, NOT A CLAUSE BOUNDARY, so a possessed-noun
#   subject can sit at the tail of a larger phrase whose real subject is
#   somebody else. Measured at the sixth review:
#
#     refuse  my supplier is in France              <- pinned refusal
#     ADMIT   the supplier of my farm is in France  <- same meaning, one genitive away
#     refuse  the farm is in France                 <- pinned refusal
#     ADMIT   the owner of my farm is in France
#     ADMIT   the man who rents my farm is in France
#
#   "The company that owns my farm is in the Netherlands, my field is in
#   Antalya" placed the user in the Netherlands and printed "hangi ilde
#   oldugunu SORMA" - the exact harm the previous commit deleted `from` to
#   stop, reached through a different door, and sticky for the conversation
#   because `_country_lines` asks every user turn.
#
# A PRONOUN SUBJECT CANNOT BE THE TAIL OF ANOTHER SUBJECT: `my farm` can be
# possessed by a larger phrase, `i` cannot be possessed by anything. THAT CLAIM
# IS ABOUT POSSESSION AND IT IS TRUE; THE CONCLUSION DRAWN FROM IT - "so the
# whitelisted subject is the writer" - IS FALSE, and the seventh review measured
# it. A pronoun cannot be possessed but it can be ATTRIBUTED, and attribution
# puts somebody else's `i` in the subject slot without possessing anything:
#
#     ADMIT   he says i am in France
#     ADMIT   he said "i am in France" in his email
#     ADMIT   my supplier wrote: i am in France, send the order
#     ADMIT   the form says i live in France
#     ADMIT   translate "i am in France" into Turkish
#     ADMIT   he said "i am in the Netherlands", my field is in Antalya
#
# The last is the sixth review's own Critical sentence with an attribution in
# place of the genitive, and it reached the prompt end to end. 0 of the 42
# refusals carried an attributing verb at all, so nothing in the suite could
# break this sub-decision - which is why the claim could carry the whole class
# cut for a commit. `_ATTRIBUTED_SUBJECT_REFUSALS` is that cell now, and the
# comment says which half of the claim was measured: possession was, speakerhood
# was argued.
#
# WHAT THE PRONOUN RULE COSTS, counted: 2 of the English accepts - "my farm is
# in France" and "my field is in France" - both pinned as costs. They say where
# the speaker's land is, which is exactly what this guard wants to know. The
# reason written here used to be that "nothing distinguishes them from the five
# admissions above without parsing the clause", AND THAT IS MEASURABLY FALSE by
# the same argument that overturned the `if` claim one paragraph down. A
# CONSUMED clause-start alternative is not a lookbehind, so its width is free:
#
#   (?:^|(?<=[.,;!?]\s))(?:my\s+farm\s+is|our\s+farm\s+is
#                         |my\s+field\s+is|my\s+fields\s+are)\s+(?:in|at)\s+
#
# Measured beside the left veto: both costs recovered, 0 of the 58 refusals
# leaked, 0 of the 5 `_POSSESSED_SUBJECT_LEAKS` admitted, and the fresh
# attribution leak the seventh review warned this anchor would open - "Ahmet
# said, my farm is in France", "he wrote: my farm is in France" - is refused,
# because `_EN_NOT_THE_SPEAKER` reads that token too. SO THE REASON THEY ARE
# STILL REFUSED IS THE ORDER OF THE WAVES AND NOT THE PARSE: this wave narrowed
# the English arm twice, and narrowing and widening in the same wave is the
# mistake this branch made three times. Measured, written down, next round. In
# the meantime the speaker writes "I am in France" and is placed.
#
# `if` WAS REFUSED BY THE WORD AND IS REFUSED BY THE MOOD NOW. The sixth review
# overturned the claim that refusing the conditional "means reading the tail" -
# correctly, `if` stands immediately to the LEFT of the subject - and shipped
# `(?<!if\s)`, under a comment saying the line was "the mood rather than the
# length of the word". IT WAS THE WORD, and the seventh review measured the
# difference: `suppose`, `supposing`, `assuming`, `in case`, `unless` and
# `whether` were all admitted, placed the speaker abroad, suppressed the
# province question and stuck for the conversation; and `if  i am in France`
# with two spaces was admitted too, because a lookbehind in `re` must be
# FIXED-WIDTH and `_normalize_tr` does not collapse runs of space. One spelling
# at one width is what a lookbehind can say.
#
# SO THE DECISION MOVED OUT OF THE PATTERN AND INTO ONE TOKEN. `_GUARDS` carries
# a left veto per guard and `_guard_hits` applies it to the text to the LEFT of
# the match, anchored with `$`: a mood word or an attributing verb TOUCHING the
# subject, through any run of space and through the comma, colon or quote a
# writer puts between. That is not reading the sentence - it is the same fixed
# window the lookbehind read, with the width free, which is the half a
# lookbehind could not express. Measured: 0 of the 16 accepts lost, 0 of the 58
# refusals leaked, and `(?<!if\s)`'s own two false blocks - "the tarif i am in
# France", "a motif i am in France", the only shapes that could collide - are
# admitted again, which is a side effect and not the reason.
#
# AND THE COST SIDE OF THAT VETO HAD ONE INPUT BEFORE THIS WAVE. Every one of
# the twelve accepts began at the start of the message, so there was nothing to
# the left of the subject to veto and any left rule at all would have measured
# free - except `When I am in France I plant wheat`, which is 1 of 12.
# `_LEFT_CONTEXT_ACCEPTS` puts a token there on purpose, so the count is 5 of 16
# now: `actually i am in France`, `the buyer said nothing, i am in France` (an
# attributing verb in the sentence but not touching the subject) and `when the
# fair opens, i am in France` (a whole clause between the mood slot and the
# subject), beside `when` and `whenever`.
#
# `when I am in France` AND `whenever I am in France` STAY ADMITTED, and that is
# a decision: the mood words suppose a country the speaker is not in, while the
# temporals say he does go there. Both are pinned as declared accepts, because
# they are the only two inputs that can break the mood decision in the admitting
# direction.
#
# WHAT THE VETO DOES NOT CLOSE, written down rather than implied. The token must
# TOUCH the subject, so an attribution at a distance - "he told me that, in his
# email, i am in France" - is not read; reading further is reading the clause.
# And THE TURKISH ARM HAS NO LEFT VETO AT ALL, which is not an omission: Turkish
# is verb-final, so "Fransa'dayim dedi" puts the attributing verb to the RIGHT
# of the match where a left veto cannot see it. The mood asymmetry is the other
# way round and is now CLOSED rather than declared - "Fransa'daysam ne ekerim"
# and "Fransa'da olsaydim bugday ekerdim" are refused for free by morphology,
# and English refuses its twins now, so the two branches agree about a speaker
# who supposes a country. They differ about one who is QUOTED, and only the
# English one gets that.
_EN_SUBJECT = (r"(?<!\w)(?:i\s+am|i'm|we\s+are|we're|i\s+live"
               r"|we\s+live|i\s+farm|we\s+farm)(?:\s+based)?\s+")

# WHICH PREPOSITIONS MEAN PRESENCE, in one place because three reach counts and
# `_SELF_EN` all have to mean the same thing by it. Two of those counts used to
# spell `(?:in|at)` inline in the test, so widening this would have left them
# measuring the old rule, green - the sixth review's finding, and the one-line
# fix it asked for. `from` is deliberately absent; see above.
_EN_PREP = r"(?:in|at)"

# Split from the preposition so the reach counts above can be taken against the
# REAL subject list rather than a copy of it: the preposition decision's count is
# measured by composing this with `from`, and a second copy of the subject list
# in the test would drift from this one silently.
_SELF_EN = _EN_SUBJECT + _EN_PREP + r"\s+"

# THE TOKEN IMMEDIATELY LEFT OF THE SUBJECT, and what it can take back. This is
# not a reading of the sentence: it is the one token touching the match, read
# with the width free, which is the only thing a fixed-width lookbehind could
# not do. See the two paragraphs above `_EN_SUBJECT` for the two decisions it
# makes and what each one measured.
_SUPPOSED_MOOD = r"if|unless|suppose|supposing|assuming|whether|in\s+case"
_ATTRIBUTING_VERB = (r"say|says|said|saying|write|writes|wrote|written"
                     r"|tell|tells|told|claim|claims|claimed"
                     r"|reply|replies|replied|state|states|stated"
                     r"|add|adds|added|mention|mentions|mentioned|translate")
# The separator is everything that can stand between that token and the subject:
# any run of space, the comma a writer puts after `if`, the colon before a quoted
# line, and both the ASCII and the phone's curly quotes. It is a RUN and not one
# character, which is the half of this that a lookbehind cannot express at all.
_EN_NOT_THE_SPEAKER = (rf"(?<!\w)(?:{_SUPPOSED_MOOD}|{_ATTRIBUTING_VERB})"
                       r"[\s,:;\"'‘’“”(]*$")

# THE LOCATION QUESTION, in one place because it is asked from two routes and
# must read the same in both. It used to be written out twice, as
# "Kullanicinin ili BILINMIYOR - cevabinda hangi ilde oldugunu sor" plus a route
# suffix on one of them.
#
# IT NOW ASKS FOR THE COUNTRY TOO, AND IT ASKS FOR IT IN ONE SPELLING. That is
# the recovery for the bare-name branch this wave deleted: a user outside Turkiye
# cannot answer "which province", and a bare "Fransa" is no longer read as an
# answer, so the question itself has to steer the reply into the one shape the
# guard above still accepts. "Fransa'dayim" is _SELF_TR's own pattern, which is
# why the example is written out rather than described - the model copies an
# example and paraphrases an instruction.
#
# WHAT IT COSTS, counted: ONE EXTRA TURN for a foreign grower who answers the
# location question with a bare country name. He writes "Fransa", gets the
# question again, writes "Fransa'dayim", and is placed. Against that: the gate
# that used to read the bare "Fransa" also read it after
# `crop_compare.ASK_FOR_CROPS`, so the turn it saved was bought with a class of
# wrong placements nothing in the suite could see.
#
# "yurt disindaysa" RATHER THAN "Turkiye disindaysa", deliberately: the string
# "Turkiye disinda" is what the answer block prints when a country IS settled,
# and four tests assert it is absent from a block that asks this question. Two
# meanings for one substring would make those tests pass for the wrong reason.
#
# USED BY `crop_choice` ONLY. `fert_plan` asks for the province in its own words
# and does not invite a country, because `_country_lines` has one caller and it
# is not that route - see the comment at that call site.
#
# SO THE INVITATION IS RE-ASKED ACROSS ROUTES, AND THIS WAVE CREATED THAT. The
# same-route loop is closed: a `fert_plan` user is never told to write
# "Fransa'dayim", and that route's string is byte-identical to main's. But
# ROUTING IS PER MESSAGE. A grower invited to name his country on a `crop_choice`
# turn, who answers "Fransa'dayim" and then asks when to fertilise, is routed to
# `fert_plan` and asked for a TURKISH PROVINCE - the question he cannot answer,
# one turn after answering the one we asked him to. Measured in one conversation
# and pinned in `test_answering_the_country_invitation_is_re_asked_on_fert_plan`;
# before this wave the invitation did not exist, so the contradiction is new even
# though the `fert_plan` ask is not.
#
# IT IS NOT FIXED BY WIDENING `_country_lines` TO `fert_plan`, because that is a
# separate round rather than a line of code: `fert_plan` serves a fertilisation
# and irrigation plan and FAOSTAT publishes neither, so there is nothing for the
# world layer to say on that route - only a province question to stop asking,
# with nothing to put in its place. See the call site in `_context_block`.
#
# AND THE RECOVERY THIS QUESTION CARRIES IS MEASURED IN ONE LINK OF THREE. The
# whole compensation for the 39 surrendered accepts is this instruction, and the
# chain is: (1) the model must relay the example rather than paraphrase it,
# (2) the user must comply, (3) the spelling must generalise to his own country.
# Only (3) is measurable in this repo and it measures 198 of 198 countries
# placeable in this shape, robust to wrong vowel harmony and to the phone's
# U+2019. (1) AND (2) ARE UNMEASURED - they are prompt behaviour and belong in
# the eval harness - so the sentence below is where 39 accepts went, and nothing
# here tests that they come back.
#
# THE EXAMPLE IS NOW ORDERED VERBATIM, because "gibi" was measured not to be
# enough. On 2026-10-28, 5 crop_choice messages x 4 samples on
# gemma-4-12b-qat, with every example the model wrote fed back to the guard:
# 20/20 answers asked where the user is and 20/20 invited a country, but only
# 4/20 gave "Fransa'dayim". 14/20 gave no example at all, and 2/20 wrote
# "ornegin Fransa gibi" - a BARE name, which the guard refuses, so the model was
# steering the user into a reply that gets this question asked again. The line
# therefore names the failure it is guarding against: the suffix is the part
# that does the work, and the model dropped it. Re-measured on the same 20:
# 20/20 close the loop, 0 refused, 0 with no example.
#
# THE EXAMPLE IS WRITTEN WITH TURKISH LETTERS, unlike the rest of this line, and
# that is not an oversight. The rest is ASCII by habit - `_normalize_tr` folds
# for MATCHING only, nothing requires prompt text to be folded - and the example
# is the one word the model is told to copy verbatim. Written as "Fransa'dayim"
# it was copied verbatim, misspelling and all, in 6 of 20 answers a Turkish user
# would read. The guard folds, so both spellings place; the dotless i is for the
# reader.
_ASK_LOCATION = ("Kullanicinin ili BILINMIYOR - cevabinda hangi ilde oldugunu "
                 "sor; yurt disindaysa ulkesini yazmasini iste ve cevabina su "
                 "ornegi tirnak icinde AYNEN koy: \"Fransa'dayım\". Ornegi "
                 "kisaltma: yalnizca ulke adi (Fransa) yetmez, sonundaki -dayım "
                 "eki gerekli. Tavsiyeni genel tut.")

# The two patterns and WHICH SIDE OF THE NAME each one sits on. `_SELF_TR` is a
# suffix, `_SELF_EN` a prefix, so the word boundary goes on the name's free side
# in each case - and that composition is what `_states_location` actually
# searches for, which is why it has one reader (`_guard_regex`) rather than being
# spelled out at every place that needs it. The per-pattern test used to
# re-compose both itself: a change to the COMPOSITION - adding a boundary on the
# English side, say - would have left that test green while it measured a regex
# nobody ships, which is this guard's own standing defect in miniature.
#
# AND EACH ONE CARRIES ITS OWN LEFT VETO, which is where the mood and the
# attribution decisions live. They cannot live in the pattern: Python's `re`
# wants a FIXED width behind a lookbehind, and the two things that have to be
# read - a mood word of two to nine letters, and a run of whitespace or
# punctuation after it - are both variable. So the fourth field is a regex
# matched against the text to the LEFT of the match, anchored with `$` so it
# reads only what touches the match. `None` for the Turkish side, and that is a
# decision rather than an omission: the Turkish arm is a SUFFIX, so the token
# that would carry attribution ("Fransa'dayim dedi") stands to the RIGHT of the
# match and this field cannot see it. Written down in `_SELF_TR`'s own terms,
# and not repaired here - see the asymmetry paragraph above `_EN_SUBJECT`.
_GUARDS: tuple[tuple[str, str, str, str | None], ...] = (
    ("_SELF_TR", "suffix", _SELF_TR, None),
    ("_SELF_EN", "prefix", _SELF_EN, _EN_NOT_THE_SPEAKER),
)


def _alias_key(name: str, side: str) -> str:
    """The escaped alias as a guard should look for it - WITH the buffer `n` on
    the Turkish side when the name is long enough to carry a 3sg possessive.

    THE BUFFER BELONGS TO THE NAME, NOT TO THE SUFFIX, which is why it is spelled
    here and not in `_SELF_TR`. Turkish inserts it between a 3rd-person
    possessive and a case ending, so the `n` in "Rusya Federasyonu'nda" is the
    possessive's linking consonant; the case ending is `-da` either way.

    AND IT IS GATED BY LENGTH, which is the whole reason this function exists
    rather than an `n?` in the pattern. Measured with the buffer ungated:
    `_states_location("malindayim", <Mali's aliases>)` was True, because `mali`
    + `n` + `da` + `yim` is also the ordinary Turkish word "malında" ("in his
    goods") plus a copula - and `mali` is the Turkish adjective for fiscal, which
    is why it sits in country.py's `_AMBIGUOUS_EN` already. It was REACHABLE, not
    merely theoretical: "Mali'de buğday verimi nedir" with an earlier user turn
    "tarlamın malındayım" printed Mali's yield figures and asked no province,
    where the un-buffered guard printed nothing. `korentajar` x2 (`kore` +
    `ntajar`) is the second attested token of this shape, one letter short of
    the person slot; `silindir` x38 (`sili` + `ndir`) is a rung lower still,
    since `i` is not `[ae]`, and is named only for being the commonest
    `<short alias> + n` token in the corpus. See `_SELF_TR`'s ladder.

    `malında` IS ATTESTED, 5 times in the project's own Turkish corpus; the
    copula form that actually fires is attested 0 times in 10.9M words. So the
    gate closes a class whose instance is real and whose firing shape is not,
    which is the direction this guard has been wrong in six times.

    THE LENGTH IS READ FROM country.py, NOT RESTATED, because this is the same
    decision `_SHORT` already makes there: aliases of four characters and fewer
    get `_STRICT_SUFFIX` precisely because they collide with ordinary words once
    folded, and not one of them ends in a 3sg possessive, so none can carry a
    buffer. Importing the constant is what stops the two from drifting into
    disagreeing about which names are the dangerous ones.
    """
    key = re.escape(name)
    if side != "suffix":
        return key
    from src.context import country as country_ctx
    if len(name) <= country_ctx._SHORT:
        return key
    # `(?:'?n)?` AND NOT `n?`: Turkish puts the apostrophe BEFORE the buffer on a
    # proper noun - "Rusya Federasyonu'nda", never "Federasyonun'da" - so the
    # group has to be able to swallow the apostrophe with the `n`. A bare `n?`
    # here reads the apostrophe form as no buffer at all and refuses it, which is
    # the spelling that was already working before this change.
    #
    # `_SELF_TR` keeps its own leading `'?` and the two do not collide: on
    # "Fransa'dayim" this group fails (no `n` after the `'`) and matches empty,
    # and the pattern's `'?` takes the apostrophe as it always did.
    return key + r"(?:'?n)?"


def _guard_regex(side: str, pattern: str, key: str) -> str:
    """The regex one guard pattern searches for around the escaped name `key`.

    `side` is "suffix" when the pattern follows the name and "prefix" when it
    precedes it; the boundary assertion goes on whichever side of the NAME the
    pattern does not already cover. Read `_GUARDS` for both, and do not pass a
    pattern that is not in it - the boundaries here are the only thing stopping
    an alias from matching inside a longer word, and they are decided per side.
    """
    if side == "suffix":
        return rf"(?<!\w){key}{pattern}"
    return rf"{pattern}{key}(?!\w)"


def _guard_hits(guard: tuple[str, str, str, str | None], key: str,
                folded: str) -> bool:
    """Whether one `_GUARDS` entry fires on `folded` around the escaped `key`.

    THE WHOLE DECISION ONE GUARD MAKES, in one reader, because it is no longer
    just a regex: the pattern says what shape places a speaker, and the entry's
    fourth field says what token standing immediately to the LEFT of that shape
    takes it back. `_states_location` and the per-pattern test both call this,
    so neither can be green over a rule nobody ships - which is the standing
    defect this guard has been reviewed for seven times, and it has already been
    this test's own defect once.

    EVERY MATCH IS TRIED, not the first: a vetoed match refuses that match and
    not the sentence. "he said i am in Germany, but i am in France" is placed in
    France and not in Germany, because the veto reads the left of the match it
    is deciding rather than the left of the sentence.
    """
    _label, side, pattern, veto = guard
    for match in re.finditer(_guard_regex(side, pattern, key), folded):
        if veto is not None and re.search(veto, folded[:match.start()]):
            continue
        return True
    return False


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


def _states_location(text: str, aliases: tuple[str, ...]) -> bool:
    """Whether `text` says the SPEAKER is in the country `aliases` names.

    TWO PATTERNS AND NO INFERENCE: the Turkish person suffix fused to the name
    itself, and the English self-declaration. Anything else is refused and the
    assistant asks where the user is. See _SELF_TR for the five waves of rules
    that tried to work this out from the rest of the sentence, the four
    Criticals they produced, and what deleting them cost.

    PLUS ONE TOKEN TO THE LEFT, and that is not a reading of the sentence: a
    mood word or an attributing verb TOUCHING the match says the `i` is supposed
    or is somebody else's, and `_guard_hits` takes the match back. One token,
    with its width free, which is the whole difference from the fixed-width
    lookbehind this replaced. See the two paragraphs above `_EN_SUBJECT`.

    One text, not a conversation. The `asked` parameter this used to take - and
    with it the bare-name branch it served - is gone: there was no evidence for
    it that could exist, because the question it depended on is written by the
    model and not by this repo. See _SELF_TR.
    """
    folded = _normalize_tr(text or "")
    if not folded:
        return False
    for name in aliases:
        for guard in _GUARDS:
            if _guard_hits(guard, _alias_key(name, guard[1]), folded):
                return True
    return False


def _fao_item(crop_id: str) -> object:
    """The FAOSTAT item `crop_id` reads, or None when the map holds none for it.

    ONE READER OF data/crop_fao_map.json'S SHAPE, for the two tests below. Both
    of them used to write this walk out, identically, so the file's shape was
    recorded in two places and a change to it needed finding in both.

    A broken entry reads as no mapping rather than raising: `norms._resolve_world`
    takes the same table and produces no figure without an item, so the callers'
    answer to "no item" is already the right answer to "unusable item".
    """
    from src import norms
    mapping = norms._load_fao_map().get(crop_id)
    return mapping.get("fao") if isinstance(mapping, dict) else None


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
    items = {item for crop_id in crop_ids
             if (item := _fao_item(crop_id)) is not None}
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

    Re-measured 2026-10-03 over the shipped tables - 187 families against every
    FAOSTAT area, 8425 (family, country) rows that produce a figure - 321 rows
    are in that third case, over three families: `Biber` (item 401, 131 rows,
    four ids), `Fasulye` (176, 127, two) and `Bakla` (181, 63, two).

    THE REVISION OF THIS NUMBER SAID 331, AND THAT WAS THE COUNT BEFORE THE
    CANDIDATE PREFERENCE at the call site existed. Both changes shipped in the
    same commit: once a candidate carrying BOTH measures is preferred over an
    earlier one carrying only a yield, ten rows answer through a DIFFERENT id and
    leave the third case. 331 is still reproducible by asking this question of
    the old first-match candidate, which is not the one the caller passes.

    `Bakla, Kuru (Yemlik)` was the worst of them, because
    data/crop_fao_map.json's own note on item 181 says FAOSTAT does not separate
    food-grade broad beans from feed-grade ones - so the printed name was
    contradicted by the map that supplied the figure.

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
    item = _fao_item(answering)
    if item is None:
        return None
    if sum(1 for crop_id in crop_ids if _fao_item(crop_id) == item) <= 1:
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

    AND THAT CHANGE MOVED THE PRICE OF A WRONG ADMISSION BY `_states_location`
    FROM NOTHING TO EVERY TURN, which is the half of the trade the revision
    introducing it did not write down. Before it, a message with no crop name
    returned [] whatever the guard said, so a wrong admission on such a message
    was INVISIBLE - the province question stood and the user saw no difference.
    Now every wrong admission prints "Kullanici Turkiye disinda ... hangi ilde
    oldugunu SORMA", and because `said` below is every user turn it sticks for
    the rest of the conversation with no way to retract it.

    This is still the right trade: the turn it fixes - "hangi ildesiniz?"
    answered with "Fransa'dayım" - is a certainty, where a wrong admission is a
    guard's error rate, and the guard's refuse set is measured for exactly that
    reason. But it is why a defect in `_states_location` is Critical on this
    branch and was merely Important before it, and why the same wave that made
    this change should not have ALSO widened that guard: it added a second
    Turkish branch in the same commit, and that branch admitted twelve sentences
    of the class the first branch had just been narrowed to refuse. Measure the
    guard's refuse set against any new branch BEFORE widening it, and measure it
    against the DECISION the branch makes - see _SELF_TR, where four reviews in
    a row found a rule licensed by a zero none of the refusals could break.

    AND IT IS WHY THAT GUARD IS A WHITELIST NOW. Four waves patched it as a
    refuse-list and each one left a class open; the bare-name class in
    particular was invisible for exactly the reason above, since `Mısır` as a
    whole message names no crop this function would have printed before the
    figure-less line existed. See _SELF_TR for the inversion, and for why the
    whitelist that followed it has since been cut to two patterns that infer
    nothing.

    NO TURN CARRIES A QUESTION CONTEXT ANY MORE. This function used to pair each
    user turn with the assistant turn in front of it, because the bare-name
    branch counted "Fransa" only after the assistant had asked where the user
    is. That branch is gone - see _SELF_TR for the shipped literal of our own
    that defeated its gate - so every turn is now asked on its own text and this
    function reads no assistant turn at all.

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
        # NO TURN NEEDS THE TURN IN FRONT OF IT any more. The pairing that used
        # to live here existed for the bare-name branch alone, which is deleted -
        # see _SELF_TR - so each turn is now asked on nothing but its own text.
        said = [message] + [turn.get("content", "") for turn in (history or [])
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
            "Turkce adini kullan. TUIK il verisi bu ulke icin yok, hangi ilde "
            "oldugunu SORMA. Bu blokta bu ulke icin verim veya fiyat rakami "
            "YOK - kendin rakam yazma, gerekirse kullanicinin kendi "
            "rakamlarini sor.",
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
            if _family_head(name) not in aliases
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
        family_name = _label_head(families[0])
        family = _normalize_tr(family_name)
        matched = [(crop_id, label) for crop_id, label in norms.available_crops()
                   if _family_head(label) == family]
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
        # and peppers, green". 321 of the 8425 rows are in this case, across
        # `Biber` (401, four ids), `Fasulye` (176, two) and `Bakla` (181, two) -
        # counted for the candidate the preference above actually chooses, which
        # is what makes it 321 and not the 331 an earlier revision wrote here.
        # There the cell has its OWN name and FAOSTAT publishes it, so the choice
        # is not between two wrong Turkish names - see _shared_item_label.
        crop_ids = [crop_id for crop_id, _label in matched]
        if _one_fao_item(crop_ids):
            crop_name, item_label = family_name, None
        else:
            # Kept, rather than folded into the expression below, because the
            # line after `*figures` must know whether the name beside the figure
            # is FAOSTAT's English one or a Turkish label - the two need opposite
            # instructions, and `crop_name` alone cannot tell them apart.
            item_label = _shared_item_label(crop_ids, norm.crop)
            crop_name = item_label or norm.label

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
            "Cevabinda ulkenin Turkce adini kullan ve yanina parantez icinde "
            "FAOSTAT'in bu adini aynen ekle. TUIK il verisi bu ulke icin yok, "
            "hangi ilde oldugunu SORMA.",
            *figures,
            # THE CROP NAME GETS THE COUNTRY NAME'S OWN INSTRUCTION, and only in
            # the one case that needs it. `_shared_item_label` prints FAOSTAT's
            # English name for the cell - `Chillies and peppers, green (Capsicum
            # spp. and Pimenta spp.)` - because no file here publishes a Turkish
            # name for an FAO item, which is the same reason the country line
            # prints `France`. But the country line also TELLS the model what to
            # do with that name, and this one did not: a name chosen for
            # provenance was handed over with no instruction, so the English
            # label could reach a Turkish grower verbatim.
            #
            # IT IS CONDITIONAL, and that is the point. In every other case the
            # name beside the figure is already Turkish - `Buğday` from the
            # family or `Domates (Salçalık)` from the id - and asking for
            # "FAOSTAT's name in parentheses" there would have the model invent
            # one. Only `item_label` is FAOSTAT's own.
            #
            # THE SECOND SENTENCE IS NOT DECORATION: this name is printed
            # precisely because the item is BROADER than any one Turkish variety
            # - item 401 is shared by four Turkish peppers - so a model that
            # translates it back to the narrowest variety undoes the fix.
            #
            # The nested parentheses in the ANSWER are a cost accepted here the
            # way the country line already accepts them for `Netherlands
            # (Kingdom of the)`: the alternative is an answer that cannot say
            # which cell the number came from.
            *(["Rakamlarin yanindaki urun adi FAOSTAT'in kendi kalem adi, "
               "Ingilizce. Cevabinda urunun Turkce adini kullan ve yanina "
               "parantez icinde FAOSTAT'in bu adini aynen ekle. Bu kalem "
               "birden fazla Turkce cesidi birlikte sayar, rakami tek bir "
               "ceside mal etme."] if item_label else []),
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
            lines.append(_ASK_LOCATION)
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
    # Carry prior turns for conversational continuity - the most recent ones that
    # fit the history budget. See _within_history_budget.
    messages.extend(_within_history_budget(history, settings.history_budget_chars))
    messages.append({"role": "user", "content": message})
    return messages


def _within_history_budget(history: list[dict] | None, budget: int) -> list[dict]:
    """The newest whole turns whose content fits in `budget` characters.

    THIS IS THE ONLY PLACE THE CONVERSATION IS BOUNDED for the model. Before it,
    the 3,000-character budget lived in the mobile client alone; the web widget
    sends its entire history and nothing here capped it. Measured 2026-10-28 on
    LM Studio, +290 prompt tokens per web exchange: at 7 exchanges prompt +
    max_tokens passed the 8,192 window, at 11 the answer was cut at the window
    edge, and from 16 the server returned 200 having silently dropped the middle
    of the prompt. See config.py's history_budget_chars.

    THE SAME RULE AS mobile-app/src/chatStore.ts's recentWithinBudget, on
    purpose: walk back from the newest turn and STOP at the first that would
    overflow, rather than skip it and keep going - dropping a turn from the
    middle hands the model a conversation that jumps. A turn is never cut in
    half.

    THE MOBILE PROFILE TURN IS EXEMPT, and the budget applies to the rest.
    chat.tsx sends profileTurns + recentWithinBudget: the profile FIRST, then a
    conversation already trimmed to 3,000. That payload is over 3,000 whenever
    the conversation is full, and a plain walk back drops its oldest turn - the
    profile - first: measured 2026-10-29 at 7 exchanges (3,076 chars), the name
    and the crops left the model's view. With the exemption a mobile payload
    passes through unchanged. It is bounded (see _is_profile_turn), so it is
    not a way around the budget.

    It bounds the MODEL'S VIEW ONLY. Callers still hand the full history to the
    router, to retrieval and to _context_block, so a location stated in a turn
    this drops is still found - and lands in the system prompt, which no budget
    here touches.
    """
    turns = [{"role": t.get("role"), "content": t.get("content")}
             for t in history or []
             if t.get("role") in ("user", "assistant") and t.get("content")]
    pinned = turns[:1] if turns and _is_profile_turn(turns[0]) else []
    kept: list[dict] = []
    used = 0
    for turn in reversed(turns[len(pinned):]):
        cost = len(turn["content"])
        if used + cost > budget:
            break
        used += cost
        kept.insert(0, turn)
    return pinned + kept


# mobile-app/app/(tabs)/chat.tsx's profileTurns ends the profile turn with this
# sentence, word for word; it is how the server tells that turn from the rest.
_PROFILE_SENTINEL = "Bunu aklında tut, her cevapta tekrar etme."
# Any client can end a turn with that sentence, so the exemption is capped. A
# profile with a name, a province and a few crops is around 100 characters;
# the profile form sets no length limit, so a longer one is budgeted like any
# other turn. Its tokens sit on top of the history budget: re-measure the
# window (config.py's max_tokens) before raising this.
_PROFILE_TURN_MAX_CHARS = 400


def _is_profile_turn(turn: dict) -> bool:
    content = turn["content"]
    return (turn["role"] == "user"
            and content.rstrip().endswith(_PROFILE_SENTINEL)
            and len(content) <= _PROFILE_TURN_MAX_CHARS)


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
    # Lira unless the farmer is abroad. Decided apart from the table, so a
    # broken norm layer costs the prefill but never turns a dollar card into a
    # lira one.
    currency = "TRY"
    try:
        from src import norms
        from src.context import location
        province = location.extract_province(message, history)
        country = None
        if province is None:
            from src.context import country as country_ctx
            country = country_ctx.extract_country(message, history)
        if country is not None and country != norms.TURKIYE_AREA:
            # A farmer abroad (PDF p14): their country's FAOSTAT figures, in the
            # dollars FAOSTAT publishes. A province always wins - it is asked
            # first, and TÜİK is the better source wherever it applies.
            currency = "USD"
            table = norms.country_table(country)
            latest_year = norms.country_price_year(country)
        else:
            table = norms.province_table(province)
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
        inputs, errors = budget.validate(payload or {}, table, currency)
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
                                            latest_year, currency))


def _named_crops(message: str) -> tuple[str, ...]:
    """Which crops this message names. Never raises: a detector failure must
    cost the card, not the answer."""
    try:
        from src import crop_compare
        return crop_compare.named_crops(message)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] crop detection failed, no comparison this turn: {exc}")
        return ()


# A farmer saying they will plant something - folded, so typed with or without
# Turkish letters. Questions that only NAME a crop ("domatesimin yapraklari
# sariyor") are information, not a choice, and get no offer.
_PLANT_INTENT = re.compile(
    r"(?<!\w)(?:ek|dik)(?:ecegim|ecegiz|meye karar|meyi dusun|meyi planl"
    r"|mek istiyorum|meli miyim|sem mi|eyim)")
# At most this many crops are offered at once: a message listing seven crops
# is not a decision about seven crops.
_MAX_CROP_OFFER = 2


def _crop_offer(route: str, message: str) -> tuple[str, ...]:
    """The crops a model answer may offer for the profile (PDF p5: "asistanla
    konuşarak ürününü seçer; seçim profiline işlenir"): those the message
    names, when it is a crop-choice question or says the farmer will plant.
    Never raises - a detector failure costs the offer, not the answer."""
    try:
        if route != "crop_choice" and not _PLANT_INTENT.search(_normalize_tr(message)):
            return ()
        crops = _named_crops(message)
        # "Mısır" is maize and Egypt: in "Mısır'dayım, ne eksem?" it is where
        # the farmer is, not what they will plant. A crop that is also the
        # country this message places them in is not offered.
        from src.context import country as country_ctx
        code = country_ctx.extract_country(message, [])
        if code is not None:
            places = set(_code_aliases(code))
            crops = tuple(c for c in crops if _normalize_tr(c) not in places)
        return crops if len(crops) <= _MAX_CROP_OFFER else ()
    except Exception:  # noqa: BLE001
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
    currency = "TRY"
    latest_year = norms.latest_year()
    if province:
        table = norms.province_table(province)
        place = province
    else:
        # A farmer abroad (PDF p14): their country's FAOSTAT figures, in
        # dollars, by the budget card's rule (see _budget_result). A province
        # is asked first and always wins.
        from src.context import country as country_ctx
        country = country_ctx.extract_country(message, history)
        if country is None or country == norms.TURKIYE_AREA:
            return ChatResult(answer=crop_compare.NO_PROVINCE,
                              recommended_products=[], route="crop_choice")
        currency = "USD"
        table = norms.country_table(country)
        latest_year = norms.country_price_year(country)
        place = norms.country_label(country)

    submitted = bool(payload)
    try:
        inputs, errors = crop_compare.validate(payload or {}, table, currency)
        if inputs is not None:
            inputs = crop_compare.CompareInputs(inputs.first, inputs.second, place,
                                                currency)
            figures = crop_compare.compute(inputs, table, latest_year)
            # By family, not TÜİK's row label: "Domates (Sofralık)" goes into a
            # profile as "Domates".
            labels = crop_compare._known(table)
            offer = tuple(dict.fromkeys(
                (crop_compare.named_crops(labels.get(c, "")) or (labels.get(c, ""),))[0]
                for c in (inputs.first, inputs.second) if labels.get(c)))
            return ChatResult(answer=crop_compare.render(inputs, figures),
                              recommended_products=[], route="crop_choice",
                              crop_offer=offer)
    except Exception:  # noqa: BLE001 - a broken validation or sum must not become a guess
        return ChatResult(answer=crop_compare.COMPUTE_FAILED,
                          recommended_products=[], route="crop_choice")

    return ChatResult(answer=(crop_compare.ASK_FOR_CROPS_COUNTRY if currency == "USD"
                              else crop_compare.ASK_FOR_CROPS),
                      recommended_products=[],
                      route="crop_choice",
                      # The card's "province" is the place it shows ("France
                      # için yayımlanmış rakamlar"); a country fits it as is.
                      compare_form=crop_compare.form_spec(
                          errors if submitted else [], table,
                          payload if submitted else None, place))


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


def _season_crop(message: str) -> str | None:
    """The season card's crop, when the question named one it can draw:
    "domates için sezon programı" preselects the first tomato row."""
    try:
        from src import season
        options = season.crop_options()
        for family in _named_crops(message):
            folded = _normalize_tr(family)
            for option in options:
                if _normalize_tr(option["label"]).startswith(folded):
                    return option["id"]
    except Exception:  # noqa: BLE001 - a preselection is a convenience
        pass
    return None


def _season_result(payload: dict | None, message: str = "") -> ChatResult:
    """The season-calendar route (PDF p5): no retrieval, no product match, no
    model call. Published FAO-56 stage lengths added to the farmer's own
    planting date in src/season.py; the card when the payload is absent or
    incomplete. Any failure is COMPUTE_FAILED, never a guess."""
    from src import season

    submitted = bool(payload)
    try:
        inputs, errors = season.validate(payload or {})
        if inputs is not None:
            crop_id, label, planting = inputs
            return ChatResult(answer=season.render(season.build(crop_id, label, planting)),
                              recommended_products=[], route="season")
        return ChatResult(answer=season.ASK_FOR_INPUTS, recommended_products=[],
                          route="season",
                          season_form=season.form_spec(
                              errors if submitted else {},
                              payload if submitted else None,
                              None if submitted else _season_crop(message)))
    except Exception:  # noqa: BLE001 - a broken table must not become a guess
        return ChatResult(answer=season.COMPUTE_FAILED, recommended_products=[],
                          route="season")


def answer(message: str, history: list[dict] | None = None,
           budget_payload: dict | None = None,
           dose_payload: dict | None = None,
           compare_payload: dict | None = None,
           season_payload: dict | None = None) -> ChatResult:
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

    # A submitted season card is answered as one whatever its message routes
    # to - the `or payload` rule every card follows.
    if season_payload or route == "season":
        result = _season_result(season_payload, message)
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

    # Not under a refusal and not under one of our own fallback messages - the
    # same two gates as the products. NOT gated on [NOPRODUCT]: that marker says
    # the CATALOG has nothing for a pruning or pest question, and the Akademi
    # has posts on exactly such topics.
    article = match_article(message) if has_advice and not off_scope else None
    # The same two gates: nothing to add under a refusal or a fallback.
    offer = _crop_offer(route, message) if has_advice and not off_scope else ()

    return ChatResult(answer=answer_text.strip(), recommended_products=products,
                      route=route, route_how=route_how, article=article,
                      crop_offer=offer)


def stream_answer(
    message: str, history: list[dict] | None = None,
    budget_payload: dict | None = None,
    dose_payload: dict | None = None,
    compare_payload: dict | None = None,
    season_payload: dict | None = None
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

    # Must mirror answer(): a card wired only into answer() reaches no user.
    if season_payload or route == "season":
        result = _season_result(season_payload, message)
        yield _sse({"type": "token", "content": result.answer})
        if result.season_form is not None:
            # A NEW event type, ignored by a client that predates it - which
            # then shows ASK_FOR_INPUTS, written to stand alone.
            yield _sse({"type": "season_form", "form": result.season_form})
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
        if result.crop_offer:
            yield _sse({"type": "crop_offer", "crops": list(result.crop_offer)})
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

    # answer()'s gates, on the streamed answer. A new event type: both clients
    # skip an event they do not know, so an already-deployed build is unaffected.
    if has_advice and not off_scope and full_answer:
        article = match_article(message)
        if article is not None:
            yield _sse({"type": "article", "article": article.as_api()})
        offer = _crop_offer(route, message)
        if offer:
            yield _sse({"type": "crop_offer", "crops": list(offer)})

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
