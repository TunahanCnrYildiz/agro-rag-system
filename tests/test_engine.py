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
    monkeypatch.setattr(engine, "retrieve_context", lambda m: "")
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
    monkeypatch.setattr(engine, "retrieve_context", lambda m: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [p])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_llm("Azot eksikligi olabilir."))
    r = engine.answer("tomato nutrition")
    assert r.recommended_products == [p]
    assert r.answer == "Azot eksikligi olabilir."


def test_answer_suppresses_products_on_noproduct(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m: "ctx")
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
    assert engine._expand_query("Asmada budama") == ["Asmada budama"]


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
def _fake_stream_llm(chunks):
    """Minimal streaming client: yields chunks with .choices[0].delta.content."""
    class _Delta:
        def __init__(self, c):
            self.content = c

    class _Choice:
        def __init__(self, c):
            self.delta = _Delta(c)

    class _Chunk:
        def __init__(self, c):
            self.choices = [_Choice(c)]

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return iter([_Chunk(c) for c in chunks])

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
    monkeypatch.setattr(engine, "retrieve_context", lambda m: "ctx")
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
    monkeypatch.setattr(engine, "retrieve_context", lambda m: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_stream_llm(["Azot eksikligi ", "olabilir."]))

    out = "".join(engine.stream_answer("Bugdayda gubreleme?"))

    assert '"type": "products"' in out        # control: products still flow
    assert _sse_tokens(out) == "Azot eksikligi olabilir."
