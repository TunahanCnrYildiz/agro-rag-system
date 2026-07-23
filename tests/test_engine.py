"""Unit tests for the RAG engine core (deterministic; the LLM, vector store and
embedding clients are all monkeypatched)."""

import json

from src import engine
from src.engine import _cosine, _strip_markers, detect_language


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_cosine():
    assert _cosine([1, 0], [1, 0]) == 1.0
    assert _cosine([1, 0], [0, 1]) == 0.0
    assert _cosine([0, 0], [1, 1]) == 0.0  # zero vector -> 0, no divide error


def test_detect_language_turkish_by_diacritics():
    assert detect_language("Domates yapraklarım sararıyor") == "Turkish"


def test_detect_language_turkish_by_stopword_and_stem():
    # 'bir' stopword + 'gubre' stem, no diacritics
    assert detect_language("bir gubre onerisi lazim") == "Turkish"


def test_detect_language_english():
    assert detect_language("how to improve soil health") == "English"


def test_strip_markers_offscope():
    assert _strip_markers("[OFFSCOPE] Ben asistanim") == ("Ben asistanim", True, False)
    assert _strip_markers("  [offscope]: foo") == ("foo", True, False)


def test_strip_markers_noproduct():
    assert _strip_markers("[NOPRODUCT] Budama kis aylarinda yapilir") == (
        "Budama kis aylarinda yapilir", False, True)
    assert _strip_markers("  [noproduct]: foo") == ("foo", False, True)


def test_strip_markers_both_in_either_order():
    assert _strip_markers("[OFFSCOPE][NOPRODUCT] foo") == ("foo", True, True)
    assert _strip_markers("[NOPRODUCT] [OFFSCOPE] foo") == ("foo", True, True)


def test_strip_markers_no_marker_returns_text_unchanged():
    assert _strip_markers("Domates icin azot") == ("Domates icin azot", False, False)
    # a marker in the MIDDLE is prose, not a control marker
    assert _strip_markers("Bak [NOPRODUCT] dedi") == ("Bak [NOPRODUCT] dedi", False, False)


# --------------------------------------------------------------------------- #
# Product matching (threshold gating)
# --------------------------------------------------------------------------- #
class _Emb:
    def __init__(self, vec):
        self._vec = vec

    def embed_query(self, text):
        return self._vec


def test_match_products_threshold(monkeypatch):
    products = (
        {"product_name": "A", "source_url": "urlA", "_embedding": [1.0, 0.0]},
        {"product_name": "B", "source_url": "urlB", "_embedding": [0.0, 1.0]},
    )
    monkeypatch.setattr(engine, "_load_products", lambda: products)
    monkeypatch.setattr(engine, "_get_embeddings_client", lambda: _Emb([1.0, 0.05]))
    out = engine.match_products("query", "", k=3)
    # A is near-parallel (cos~1.0 >= 0.45); B is near-orthogonal (cos~0.05 < 0.45)
    assert [p.title for p in out] == ["A"]
    assert out[0].link == "urlA"


def test_match_products_empty_when_no_catalog(monkeypatch):
    monkeypatch.setattr(engine, "_load_products", lambda: ())
    assert engine.match_products("query", "") == []


# --------------------------------------------------------------------------- #
# Retrieval (relevance-threshold filtering + citation formatting)
# --------------------------------------------------------------------------- #
class _Doc:
    def __init__(self, content, source, page):
        self.page_content = content
        self.metadata = {"source": source, "page": page}


class _Store:
    def __init__(self, results):
        self._results = results

    def similarity_search_with_relevance_scores(self, query, k):
        return self._results


def test_retrieve_context_filters_below_threshold(monkeypatch):
    store = _Store([
        (_Doc("good chunk", "bookA.pdf", 3), 0.50),
        (_Doc("noise chunk", "bookB.pdf", 1), 0.20),  # below MIN_RETRIEVAL_RELEVANCE
    ])
    monkeypatch.setattr(engine, "_get_retriever_store", lambda: store)
    monkeypatch.setattr(engine, "_expand_query", lambda q: [q])  # hermetic (no LLM)
    ctx = engine.retrieve_context("q")
    assert "good chunk" in ctx
    assert "noise chunk" not in ctx
    assert "[Kaynak: bookA.pdf, s.3]" in ctx


def test_retrieve_context_empty_when_store_unavailable(monkeypatch):
    monkeypatch.setattr(engine, "_get_retriever_store", lambda: None)
    assert engine.retrieve_context("q") == ""


# --- cross-lingual query expansion + fusion --- #
class _MultiStore:
    """Returns different results per query, to prove both are retrieved + fused."""

    def __init__(self, mapping):
        self.mapping = mapping

    def similarity_search_with_relevance_scores(self, query, k):
        return self.mapping[query]


def test_retrieve_context_fuses_both_languages(monkeypatch):
    store = _MultiStore({
        "asma budama": [(_Doc("tr chunk", "dp_1.pdf", 1), 0.40)],
        "grape pruning": [(_Doc("en chunk", "ia_2.pdf", 5), 0.50)],
    })
    monkeypatch.setattr(engine, "_get_retriever_store", lambda: store)
    monkeypatch.setattr(engine, "_expand_query",
                        lambda q: ["asma budama", "grape pruning"])
    ctx = engine.retrieve_context("asma budama")
    assert "tr chunk" in ctx and "en chunk" in ctx     # both languages surfaced
    assert "[Kaynak: ia_2.pdf, s.5]" in ctx


# --------------------------------------------------------------------------- #
# answer() — off-scope product suppression + marker stripping
# --------------------------------------------------------------------------- #
def _fake_llm(content):
    class _Msg:
        pass
    msg = _Msg()
    msg.content = content

    class _Choice:
        message = msg

    class _Comp:
        choices = [_Choice()]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return _Comp()

    return _Client()


def test_answer_suppresses_products_on_offscope(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_llm("[OFFSCOPE] Ben bir bitki asistaniyim."))
    r = engine.answer("what movie should I watch")
    assert r.recommended_products == []           # suppressed under refusal
    assert "[OFFSCOPE]" not in r.answer           # marker stripped
    assert r.answer == "Ben bir bitki asistaniyim."


def test_answer_keeps_products_in_scope(monkeypatch):
    p = engine.RecommendedProduct("P", "url")
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [p])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_llm("Azot eksikligi olabilir."))
    r = engine.answer("tomato nutrition")
    assert r.recommended_products == [p]
    assert r.answer == "Azot eksikligi olabilir."


def test_answer_suppresses_products_on_noproduct(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_llm("[NOPRODUCT] Budama kis sonunda yapilir."))
    r = engine.answer("Asmada budama ne zaman yapilir?")
    assert r.recommended_products == []           # fertilizer cannot answer this
    assert "[NOPRODUCT]" not in r.answer          # marker stripped
    assert r.answer == "Budama kis sonunda yapilir."


# --------------------------------------------------------------------------- #
# _build_messages structure
# --------------------------------------------------------------------------- #
def test_build_messages_structure():
    msgs = engine._build_messages(
        "soru", [{"role": "user", "content": "onceki"}], "CTX", [])
    assert msgs[0]["role"] == "system"
    assert "CTX" in msgs[0]["content"]          # retrieved context injected
    assert msgs[-1] == {"role": "user", "content": "soru"}
    assert {"role": "user", "content": "onceki"} in msgs


def test_normalize_tr_folds_and_preserves_length():
    assert engine._normalize_tr("Darı") == "dari"
    assert engine._normalize_tr("Gölevez") == "golevez"
    assert engine._normalize_tr("Yağ Palmiyesi") == "yag palmiyesi"
    assert engine._normalize_tr("Tatlı Patates") == "tatli patates"
    # 1:1 per character, so match spans map back onto the original query
    for s in ("Darı", "Gölevez", "Yağ Palmiyesi", "İğne", "ÇELTİK"):
        assert len(engine._normalize_tr(s)) == len(s)


def test_expand_query_adds_bare_term_and_substituted_query(monkeypatch):
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    out = engine._expand_query("Manyok yetiştiriciliğinde gübreleme nasıl olmalı?")
    assert out[0] == "Manyok yetiştiriciliğinde gübreleme nasıl olmalı?"
    assert "cassava" in out
    # substitution goes into the ORIGINAL query, diacritics intact
    assert "cassava yetiştiriciliğinde gübreleme nasıl olmalı?" in out


def test_expand_query_adds_english_phrase_not_just_the_bare_term(monkeypatch):
    """A bare short term can retrieve nothing at all: measured 2026-07-16, "taro"
    returns 0 chunks above the floor, while "taro cultivation" puts the same FAO
    content at rank 1. The phrase is ADDED, never substituted - replacing the
    bare term rescues taro but breaks sweet potato."""
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    out = engine._expand_query("Gölevez yetiştiriciliğinde gübreleme nasıl olmalı?")
    assert "taro" in out                 # bare term still there
    assert "taro cultivation" in out     # ...and the phrase alongside it


def test_expand_query_matches_without_diacritics(monkeypatch):
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    assert "millet" in engine._expand_query("Dari yetistiriciliginde gubreleme")


def test_expand_query_requires_word_boundary(monkeypatch):
    """'kahve' must not fire inside 'kahverengi', 'muz' not inside 'domuz'."""
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    assert engine._expand_query(
        "Domates yapraklarında kahverengi lekeler var") == [
        "Domates yapraklarında kahverengi lekeler var"]
    assert engine._expand_query("Domuz gübresi nasıl kullanılır?") == [
        "Domuz gübresi nasıl kullanılır?"]
    # the bare words still match
    assert "banana" in engine._expand_query("Muz yapraklarında leke var")


def test_expand_query_prefers_longest_term(monkeypatch):
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    out = engine._expand_query("Tatlı patates yetiştiriciliği")
    assert "sweet potato" in out


def test_expand_query_no_lexicon_hit_returns_query_only(monkeypatch):
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    q = "Domateste yaprak sararması neden olur?"
    assert engine._expand_query(q) == [q]


def test_expand_query_viticulture_suffix(monkeypatch):
    """The one measured 0-chunk case (2026-07-18): 'Asmada kış budaması' reaches
    no context because CROP_LEXICON had no grape entry AND the matcher couldn't
    see through the -da suffix. Needs BOTH the asma->grapevine entry and the
    suffix-aware match."""
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    out = engine._expand_query("Asmada kış budaması nasıl yapılır?")
    assert "grapevine" in out
    # the suffixed word is replaced whole in the substituted query
    assert "grapevine kış budaması nasıl yapılır?" in out


def test_expand_query_uzum_entry(monkeypatch):
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    assert "grape" in engine._expand_query("Üzümde ben düşmesi")


def test_expand_query_findik_entry(monkeypatch):
    """Fındık is a major Turkish crop; its English literature (fao_/ia_) is
    otherwise unreachable from a TR query. Measured 2026-07-18: the entry lifts
    'Fındık bahçesi nasıl kurulur?' from 1 to 4 grounded chunks (modern sources)."""
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    assert "hazelnut" in engine._expand_query("Fındık bahçesi nasıl kurulur?")


def test_expand_query_suffix_generalizes(monkeypatch):
    """Suffix-awareness is not grape-specific: an existing crop with a Turkish
    case suffix ('muzda' = muz + -da) must now match too."""
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    assert "banana" in engine._expand_query("Muzda leke var")


def test_expand_query_disabled(monkeypatch):
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", False)
    assert engine._expand_query("Manyok gübreleme") == ["Manyok gübreleme"]


def test_expand_query_makes_no_llm_call(monkeypatch):
    """Retrieval must not touch the chat model any more."""
    def boom(*a, **k):
        raise AssertionError("chat model must not be called from retrieval")
    monkeypatch.setattr(engine, "_get_llm", boom)
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    assert "cassava" in engine._expand_query("Manyok gübreleme")


def test_fuse_applies_floor_per_list_before_ranking():
    primary = [(_Doc("keep", "a.pdf", 1), 0.50), (_Doc("drop", "a.pdf", 2), 0.10)]
    fused = engine._fuse([primary], floor=0.36, k=4)
    assert [d.page_content for d in fused] == ["keep"]


def test_fuse_ranks_by_rank_not_raw_score():
    """The whole point: a list's own #1 gets in even when the other list's
    chunks all score higher. Score-fusion dropped cacao by 0.003."""
    turkish = [(_Doc(f"tr-junk-{i}", "dp.pdf", i), s)
               for i, s in enumerate([0.459, 0.458, 0.457, 0.456])]
    english = [(_Doc("en-cocoa", "fao.pdf", 1), 0.455)]
    fused = engine._fuse([turkish, english], floor=0.36, k=2)
    assert "en-cocoa" in [d.page_content for d in fused]


def test_fuse_dedups_same_chunk_across_lists():
    doc_a = _Doc("same text", "a.pdf", 1)
    doc_b = _Doc("same text", "a.pdf", 1)
    fused = engine._fuse([[(doc_a, 0.50)], [(doc_b, 0.49)]], floor=0.36, k=4)
    assert len(fused) == 1


def test_fuse_returns_at_most_k():
    lst = [(_Doc(f"c{i}", "a.pdf", i), 0.5) for i in range(10)]
    assert len(engine._fuse([lst], floor=0.36, k=4)) == 4


def test_retrieve_context_searches_every_expanded_query(monkeypatch):
    """The primary search FILLS k with above-floor chunks - the exact case the
    old `len(kept) < k` trigger skipped, and the exact case that made cassava
    fail (generic Turkish chunks fill k while being off-topic). Expansion must
    happen anyway. Returning fewer than k here would let the old trigger pass
    this test too, proving nothing.
    """
    seen = []

    def fake_search(store, query, k):
        seen.append(query)
        return [(_Doc(f"chunk {i} for {query}", "x.pdf", i), 0.50)
                for i in range(k)]

    monkeypatch.setattr(engine, "_get_retriever_store", lambda: object())
    monkeypatch.setattr(engine, "_search", fake_search)
    monkeypatch.setattr(engine, "_expand_query", lambda q: [q, "cassava"])

    ctx = engine.retrieve_context("Manyok gübreleme", k=4)

    assert seen == ["Manyok gübreleme", "cassava"]
    assert "chunk 0 for cassava" in ctx   # the rescue list reached the context
    assert "[Kaynak: x.pdf, s.0]" in ctx


# --------------------------------------------------------------------------- #
# stream_answer() — the production path (/api/chat with stream=true)
# --------------------------------------------------------------------------- #
def _fake_stream_llm(chunks, finish=None):
    """Minimal streaming client: yields chunks with .choices[0].delta.content,
    then (if `finish` is given) a final content-less chunk carrying that
    finish_reason - exactly how the OpenAI stream signals 'length'/'stop'."""
    class _Delta:
        def __init__(self, c):
            self.content = c

    class _Choice:
        def __init__(self, c, fr=None):
            self.delta = _Delta(c)
            self.finish_reason = fr

    class _Chunk:
        def __init__(self, c, fr=None):
            self.choices = [_Choice(c, fr)]

    seq = [_Chunk(c) for c in chunks]
    if finish is not None:
        seq.append(_Chunk(None, finish))

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return iter(seq)

    return _Client()


def _sse_tokens(out):
    """Reassemble the answer text from the SSE token events (it streams split
    across events, so the raw wire text is never contiguous)."""
    return "".join(
        json.loads(line[len("data: "):])["content"]
        for line in out.splitlines()
        if line.startswith("data: ")
        and json.loads(line[len("data: "):])["type"] == "token"
    )


def test_stream_answer_suppresses_products_on_noproduct(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    # marker deliberately SPLIT across chunks - exercises the leading buffer
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_stream_llm(["[NOPRO", "DUCT] Budama ",
                                                  "kis sonunda yapilir."]))

    out = "".join(engine.stream_answer("Asmada budama ne zaman yapilir?"))

    assert "[NOPRODUCT]" not in out            # marker never reaches the client
    assert "Budama" in out                     # the answer itself still streams
    assert '"type": "products"' not in out     # no product event at all


def test_stream_answer_emits_products_without_marker(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_stream_llm(["Azot eksikligi ", "olabilir."]))

    out = "".join(engine.stream_answer("Bugdayda gubreleme?"))

    assert '"type": "products"' in out        # control: products still flow
    assert _sse_tokens(out) == "Azot eksikligi olabilir."


# --------------------------------------------------------------------------- #
# _complete_text() — never hand back a blank answer
# --------------------------------------------------------------------------- #
def _fake_llm_seq(contents):
    """Chat client returning a different content per successive call."""
    calls = {"n": 0}

    class _Msg:
        pass

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    msg = _Msg()
                    msg.content = contents[min(calls["n"], len(contents) - 1)]
                    calls["n"] += 1

                    class _Choice:
                        message = msg

                    class _Comp:
                        choices = [_Choice()]

                    return _Comp()

    return _Client(), calls


def test_complete_text_returns_first_non_blank(monkeypatch):
    client, calls = _fake_llm_seq(["Azot eksikligi olabilir."])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)
    assert engine._complete_text([]) == "Azot eksikligi olabilir."
    assert calls["n"] == 1                    # no pointless retry


def test_complete_text_retries_once_on_blank(monkeypatch):
    """Measured: the same prompt fails ~2/10 and the failures scatter, so a second
    attempt usually succeeds."""
    client, calls = _fake_llm_seq(["", "Ikinci deneme basarili."])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)
    assert engine._complete_text([]) == "Ikinci deneme basarili."
    assert calls["n"] == 2


def test_complete_text_falls_back_when_blank_twice(monkeypatch):
    client, calls = _fake_llm_seq(["", "   "])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)
    out = engine._complete_text([])
    assert out == engine._empty_answer_message()
    assert out.strip()                        # never blank
    assert calls["n"] == 2                    # exactly one retry, not a loop


def test_complete_text_does_not_retry_a_short_answer(monkeypatch):
    """Short is legitimate - [OFFSCOPE] refusals are short. Only BLANK retries."""
    client, calls = _fake_llm_seq(["Hayir.", "ikinci"])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)
    assert engine._complete_text([]) == "Hayir."
    assert calls["n"] == 1


def test_complete_text_propagates_transport_errors(monkeypatch):
    """'LM Studio unreachable' must stay distinguishable from 'model said
    nothing' - callers map the exception to _llm_unavailable_message."""
    import pytest  # this module has no module-level pytest import; keep it local

    def boom():
        raise RuntimeError("connection refused")
    monkeypatch.setattr(engine, "_get_llm", boom)
    with pytest.raises(RuntimeError):
        engine._complete_text([])


def test_answer_never_returns_empty(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    client, _ = _fake_llm_seq(["", ""])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)

    r = engine.answer("Domates yapraklarim sarariyor")

    assert r.answer == engine._empty_answer_message()
    assert r.answer.strip()          # the bug: this used to be ""


def test_answer_uses_the_retry(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [])
    client, calls = _fake_llm_seq(["", "Azot eksikligi olabilir."])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)

    r = engine.answer("Domates yapraklarim sarariyor")

    assert r.answer == "Azot eksikligi olabilir."
    assert calls["n"] == 2


def test_stream_answer_never_streams_nothing(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [])
    # the model streams no tokens at all, then the non-streaming retry is blank
    monkeypatch.setattr(engine, "_get_llm", lambda: _fake_stream_llm([]))
    monkeypatch.setattr(engine, "_complete_text",
                        lambda msgs: engine._empty_answer_message())

    out = "".join(engine.stream_answer("Domates yapraklarim sarariyor"))

    assert _sse_tokens(out) == engine._empty_answer_message()


def test_answer_hides_products_under_the_empty_fallback(monkeypatch):
    """"I could not produce an answer" + 3 fertilizer ads is incoherent: there is
    no advice for the products to sit under. Same rule as [NOPRODUCT]."""
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    client, _ = _fake_llm_seq(["", ""])          # blank twice -> fallback
    monkeypatch.setattr(engine, "_get_llm", lambda: client)

    r = engine.answer("Domates yapraklarim sarariyor")

    assert r.answer == engine._empty_answer_message()
    assert r.recommended_products == []


def test_stream_answer_hides_products_under_the_empty_fallback(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    monkeypatch.setattr(engine, "_get_llm", lambda: _fake_stream_llm([]))
    monkeypatch.setattr(engine, "_complete_text",
                        lambda msgs: engine._empty_answer_message())

    out = "".join(engine.stream_answer("Domates yapraklarim sarariyor"))

    assert _sse_tokens(out) == engine._empty_answer_message()
    assert '"type": "products"' not in out


# --------------------------------------------------------------------------- #
# embedding-model guard: read path (2026-07-18)
# --------------------------------------------------------------------------- #
import pytest
from src import ingest as _ing
from src.config import EmbeddingModelMismatchError


def test_get_retriever_store_reraises_mismatch(monkeypatch):
    engine._get_retriever_store.cache_clear()
    def boom(*a, **k):
        raise EmbeddingModelMismatchError("model mismatch")
    monkeypatch.setattr(_ing, "get_vector_store", boom)
    with pytest.raises(EmbeddingModelMismatchError):
        engine._get_retriever_store()
    engine._get_retriever_store.cache_clear()


def test_get_retriever_store_none_on_generic_error(monkeypatch):
    engine._get_retriever_store.cache_clear()
    def boom(*a, **k):
        raise ValueError("boom")
    monkeypatch.setattr(_ing, "get_vector_store", boom)
    assert engine._get_retriever_store() is None
    engine._get_retriever_store.cache_clear()


class _TopicStore:
    """Returns the orchid chunk ONLY when the query carries the orchid topic."""

    def __init__(self):
        self.queries = []

    def similarity_search_with_relevance_scores(self, query, k):
        self.queries.append(query)
        if "orkide" in query.lower():
            return [(_Doc("orkide saksı harcı", "dp_19441.pdf", 2), 0.55)]
        return [(_Doc("genel toprak bilgisi", "dp_30459.pdf", 1), 0.50)]


def test_retrieve_context_uses_prior_user_turn_for_followups(monkeypatch):
    """A follow-up like "Toprak nasıl olmalı?" must still reach the topic the
    conversation is about. Retrieval used to see only the latest message, so the
    prior subject was invisible to the corpus even though the LLM got it in
    history - the answer came back generic."""
    store = _TopicStore()
    monkeypatch.setattr(engine, "_get_retriever_store", lambda: store)
    monkeypatch.setattr(engine, "_expand_query", lambda q: [q])  # hermetic

    history = [
        {"role": "user", "content": "Orkide nasıl yetiştirilir?"},
        {"role": "assistant", "content": "Orkideler için ..."},
    ]
    ctx = engine.retrieve_context("Toprak nasıl olmalı?", history=history)

    assert any("orkide" in q.lower() for q in store.queries), (
        f"retrieval never saw the prior topic; queries were {store.queries}"
    )
    assert "orkide saksı harcı" in ctx


def test_retrieve_context_without_history_searches_only_the_message(monkeypatch):
    """No history -> behaviour is unchanged (the eval's 53 cases are all
    single-turn, so this is what keeps them inert)."""
    store = _TopicStore()
    monkeypatch.setattr(engine, "_get_retriever_store", lambda: store)
    monkeypatch.setattr(engine, "_expand_query", lambda q: [q])

    engine.retrieve_context("Toprak nasıl olmalı?")

    assert store.queries == ["Toprak nasıl olmalı?"]


def test_answer_passes_history_to_retrieval(monkeypatch):
    """The production path must hand the conversation to retrieval, not just to
    the LLM - otherwise a follow-up is answered from off-topic chunks."""
    seen = {}

    def fake_retrieve(query, k=None, history=None):
        seen["query"] = query
        seen["history"] = history
        return "ctx"

    monkeypatch.setattr(engine, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(engine, "match_products", lambda *a, **kw: [])
    monkeypatch.setattr(engine, "_complete_text", lambda msgs: "cevap")

    history = [{"role": "user", "content": "Orkide nasıl yetiştirilir?"}]
    engine.answer("Toprak nasıl olmalı?", history)

    assert seen["history"] == history


def test_stream_answer_passes_history_to_retrieval(monkeypatch):
    """stream_answer is the PRODUCTION path (/api/chat?stream=true); answer()
    alone being fixed would leave the real app broken."""
    seen = {}

    def fake_retrieve(query, k=None, history=None):
        seen["history"] = history
        return "ctx"

    def boom():
        raise RuntimeError("no llm in this test")

    monkeypatch.setattr(engine, "retrieve_context", fake_retrieve)
    monkeypatch.setattr(engine, "match_products", lambda *a, **kw: [])
    # Retrieval happens before the model is touched, so a dead client is enough
    # to exercise the wiring without a live LLM.
    monkeypatch.setattr(engine, "_get_llm", boom)

    history = [{"role": "user", "content": "Orkide nasıl yetiştirilir?"}]
    list(engine.stream_answer("Toprak nasıl olmalı?", history))

    assert seen["history"] == history


def test_stream_answer_recovers_from_length_truncation_after_a_few_tokens(monkeypatch):
    """The reasoning-exhaustion bug in STREAMING form: the model emits its marker
    plus a couple of words, then finish_reason='length' with nothing more. The old
    guard only caught a ZERO-token stream, so this truncated fragment ('Orkideler')
    reached the user. stream_answer must instead fall back to the non-streaming
    path, which completes reliably, and the fragment must NOT be streamed."""
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [])
    monkeypatch.setattr(
        engine, "_get_llm",
        lambda: _fake_stream_llm(["[NOPRODUCT] Orkideler"], finish="length"))
    monkeypatch.setattr(
        engine, "_complete_text",
        lambda msgs: "[NOPRODUCT] Orkideler icin bahce topragi uygun degildir; "
                     "epifit olduklari icin agac kabugu ve perlit tercih edilir.")

    out = "".join(engine.stream_answer("Topragi nasil olmali?"))
    text = _sse_tokens(out)

    assert "bahce topragi uygun degildir" in text     # the full fallback answer
    assert text.strip() != "Orkideler"                # NOT the truncated fragment
    assert "[NOPRODUCT]" not in text                  # marker still stripped


def test_stream_answer_keeps_a_short_answer_that_finished_cleanly(monkeypatch):
    """A genuinely short answer that finishes with 'stop' (not 'length') is a real
    answer, not a truncation - it must be emitted, never retried away."""
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [])
    monkeypatch.setattr(
        engine, "_get_llm",
        lambda: _fake_stream_llm(["Evet, bu mumkundur."], finish="stop"))
    monkeypatch.setattr(
        engine, "_complete_text",
        lambda msgs: pytest.fail("must not retry a cleanly-finished short answer"))

    out = "".join(engine.stream_answer("Bu mumkun mu?"))
    assert _sse_tokens(out) == "Evet, bu mumkundur."


# --------------------------------------------------------------------------- #
# ChatProfile: everything provider-dependent lives in one place
# --------------------------------------------------------------------------- #
def test_local_profile_carries_the_lm_studio_sampling_extensions(monkeypatch):
    monkeypatch.setattr(engine.settings, "chat_provider", "local")

    p = engine._chat_profile()

    assert p.model == engine.settings.chat_model
    assert p.base_url == engine.settings.lm_studio_base_url
    assert p.sampling["extra_body"] == {
        "min_p": engine.settings.min_p,
        "repeat_penalty": engine.settings.repeat_penalty,
    }


def test_openrouter_profile_omits_the_lm_studio_sampling_extensions(monkeypatch):
    """min_p / repeat_penalty are LM Studio extensions; hosted providers reject
    unknown body fields with a 400. This test's real job is FUTURE protection: if
    sampling is ever re-collapsed into one global dict, the failure would appear
    only on the hosted path, in production."""
    monkeypatch.setattr(engine.settings, "chat_provider", "openrouter")
    monkeypatch.setattr(engine.settings, "openrouter_model", "vendor/model-x")

    p = engine._chat_profile()

    assert p.model == "vendor/model-x"
    assert p.base_url == engine.settings.openrouter_base_url
    assert "extra_body" not in p.sampling
    assert p.sampling["temperature"] == engine.settings.temperature


def _capturing_llm(seen: dict, reply: str = "Cevap."):
    """A fake client that records the kwargs passed to chat.completions.create."""
    class _Msg:
        content = reply

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    return _Resp()

    return _Client()


def test_complete_text_sends_the_profile_model_and_sampling(monkeypatch):
    """The wiring test: the provider switch is worthless if the request still
    carries settings.chat_model or the local-only extra_body."""
    seen: dict = {}
    monkeypatch.setattr(engine, "_get_llm", lambda: _capturing_llm(seen))
    monkeypatch.setattr(engine.settings, "chat_provider", "openrouter")
    monkeypatch.setattr(engine.settings, "openrouter_model", "vendor/model-x")

    assert engine._complete_text([]) == "Cevap."

    assert seen["model"] == "vendor/model-x"
    assert "extra_body" not in seen


def test_get_llm_uses_the_profile_base_url(monkeypatch):
    monkeypatch.setattr(engine.settings, "chat_provider", "openrouter")
    monkeypatch.setattr(engine.settings, "openrouter_model", "vendor/model-x")
    monkeypatch.setattr(engine.settings, "openrouter_api_key", "test-key")
    engine._get_llm.cache_clear()

    client = engine._get_llm()

    assert str(client.base_url).startswith(engine.settings.openrouter_base_url)
    engine._get_llm.cache_clear()   # never leak a test-configured client


def _capturing_stream_llm(seen: dict, chunks, finish=None):
    """Streaming counterpart of _capturing_llm: same shape as _fake_stream_llm,
    but also records the kwargs passed to chat.completions.create so the
    streaming call site's wiring can be checked the same way
    test_complete_text_sends_the_profile_model_and_sampling checks the unified
    path. _fake_stream_llm itself is left untouched - several tests depend on
    it discarding kwargs."""
    class _Delta:
        def __init__(self, c):
            self.content = c

    class _Choice:
        def __init__(self, c, fr=None):
            self.delta = _Delta(c)
            self.finish_reason = fr

    class _Chunk:
        def __init__(self, c, fr=None):
            self.choices = [_Choice(c, fr)]

    seq = [_Chunk(c) for c in chunks]
    if finish is not None:
        seq.append(_Chunk(None, finish))

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    return iter(seq)

    return _Client()


def test_stream_answer_sends_the_profile_model_and_sampling(monkeypatch):
    """Streaming counterpart of test_complete_text_sends_the_profile_model_and_
    sampling. _fake_stream_llm discards the kwargs passed to create(), so
    nothing previously proved stream_answer's chat.completions.create() call
    carries the active profile's model/sampling rather than
    settings.chat_model / a global sampling dict."""
    seen: dict = {}
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [])
    monkeypatch.setattr(engine.settings, "chat_provider", "openrouter")
    monkeypatch.setattr(engine.settings, "openrouter_model", "vendor/model-x")
    # Well over _STREAM_WARMUP (80) clean chars in a single chunk, finished
    # cleanly ("stop") - so the streaming path itself runs to completion
    # instead of falling back to _complete_text on a "length" truncation.
    answer_text = ("Bu oldukca uzun bir cevap metni, isinma tamponunu asmak "
                   "icin yeterince karakter iceriyor ve akis boyunca boyle "
                   "devam ediyor.")
    monkeypatch.setattr(
        engine, "_get_llm",
        lambda: _capturing_stream_llm(seen, [answer_text], finish="stop"))

    out = "".join(engine.stream_answer("Soru?"))

    assert seen["model"] == "vendor/model-x"
    assert "extra_body" not in seen
    assert _sse_tokens(out) == answer_text
