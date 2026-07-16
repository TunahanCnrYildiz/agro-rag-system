"""Unit tests for the RAG engine core (deterministic; the LLM, vector store and
embedding clients are all monkeypatched)."""

from src import engine
from src.engine import _cosine, _strip_offscope, detect_language


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


def test_strip_offscope_marker():
    assert _strip_offscope("[OFFSCOPE] Ben asistanim") == ("Ben asistanim", True)
    assert _strip_offscope("  [offscope]: foo") == ("foo", True)


def test_strip_offscope_no_marker():
    assert _strip_offscope("Domates icin azot") == ("Domates icin azot", False)


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


def test_retrieve_context_skips_translation_when_primary_fills(monkeypatch):
    # primary already returns k chunks above the floor -> no (slow) translation
    strong = [(_Doc(f"c{i}", "dp.pdf", i), 0.50) for i in range(4)]
    monkeypatch.setattr(engine, "_get_retriever_store", lambda: _Store(strong))
    called = {"expand": False}

    def spy(q):
        called["expand"] = True
        return [q]

    monkeypatch.setattr(engine, "_expand_query", spy)
    ctx = engine.retrieve_context("q")
    assert called["expand"] is False        # translation skipped
    assert "c0" in ctx


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
