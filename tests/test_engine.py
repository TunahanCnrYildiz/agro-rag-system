"""Unit tests for the RAG engine core (deterministic; the LLM, vector store and
embedding clients are all monkeypatched)."""

import json
import re
from datetime import date

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
        finish_reason = "stop"      # a complete answer; see _complete_text

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


def test_answer_suppresses_products_when_answer_is_non_product_without_a_marker(
        monkeypatch):
    """The backstop's job: a model that forgets [NOPRODUCT] on a pruning answer
    must still not get products shown under it. This is the gemma-4-26b failure
    mode measured on OpenRouter."""
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_llm("Asmalarda budama kis sonunda yapilir."))
    r = engine.answer("Asmada budama ne zaman yapilir?")
    assert r.recommended_products == []          # backstop suppressed
    assert r.answer == "Asmalarda budama kis sonunda yapilir."


def test_answer_keeps_products_on_a_nutrition_answer_without_a_marker(monkeypatch):
    """The regression guard - this is the one new risk. A nutrition answer with no
    marker must keep its products; the backstop must not fire on it."""
    p = engine.RecommendedProduct("P", "url")
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [p])
    monkeypatch.setattr(
        engine, "_get_llm",
        lambda: _fake_llm("Azot eksikligi olabilir, dengeli bir gubre verin."))
    r = engine.answer("Domates yapraklarim sarariyor")
    assert r.recommended_products == [p]         # NOT suppressed


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
def _fake_llm_seq(contents, finish_reasons=None):
    """Chat client returning a different content per successive call.

    `finish_reasons` mirrors `contents` and defaults to "stop" everywhere, which
    is what a model that finished on its own returns. Pass "length" to model the
    other failure: the generation budget ran out mid-answer.
    """
    calls = {"n": 0}
    reasons = finish_reasons or ["stop"] * len(contents)

    class _Msg:
        pass

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    i = min(calls["n"], len(contents) - 1)
                    msg = _Msg()
                    msg.content = contents[i]
                    reason = reasons[min(i, len(reasons) - 1)]
                    calls["n"] += 1

                    class _Choice:
                        message = msg
                        finish_reason = reason

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


def test_complete_text_retries_a_truncated_answer(monkeypatch):
    """Measured 2026-08-13: this model spends a large and VARIABLE share of its
    budget on invisible reasoning - 1076 to 2023 completion tokens on one
    identical question against a 2048 cap - so it sits under the ceiling and
    occasionally crosses it, cutting the answer mid-sentence. Reproduced by
    lowering the cap: finish_reason 'length', 318 visible characters ending on
    "(Örneğin: Fide dönemi mi, çiçeklenme". It scatters like a blank answer, so
    it retries like one."""
    client, calls = _fake_llm_seq(
        ["Domates bitkisinde gubreleme zamani, bitkinin (",
         "Domates bitkisinde gubreleme zamani fenolojik doneme baglidir."],
        ["length", "stop"])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)
    out = engine._complete_text([])
    assert out == "Domates bitkisinde gubreleme zamani fenolojik doneme baglidir."
    assert calls["n"] == 2


def test_complete_text_keeps_the_longer_partial_when_both_truncate(monkeypatch):
    """Most of an answer beats a failure message. This is also what the caller
    already received before the retry existed, so the retry can only improve
    the outcome, never replace a partial answer with nothing."""
    client, calls = _fake_llm_seq(["Kisa parca", "Bu ikinci parca daha uzun ve"],
                                  ["length", "length"])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)
    out = engine._complete_text([])
    assert out == "Bu ikinci parca daha uzun ve"
    assert out != engine._empty_answer_message()
    assert calls["n"] == 2                    # exactly one retry, not a loop


def test_complete_text_falls_back_when_truncation_left_nothing(monkeypatch):
    """The severe case: the budget went entirely on invisible reasoning and no
    visible text survived. That is a blank answer however it is labelled, and
    the user must get the honest message rather than an empty string."""
    client, calls = _fake_llm_seq(["", ""], ["length", "length"])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)
    out = engine._complete_text([])
    assert out == engine._empty_answer_message()
    assert out.strip()
    assert calls["n"] == 2


def test_complete_text_does_not_retry_a_complete_short_answer(monkeypatch):
    """finish_reason 'stop' means the model chose to end. Short is legitimate -
    [OFFSCOPE] refusals are short - and must not be mistaken for truncation."""
    client, calls = _fake_llm_seq(["Hayir.", "ikinci"], ["stop", "stop"])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)
    assert engine._complete_text([]) == "Hayir."
    assert calls["n"] == 1


def test_complete_text_propagates_transport_errors(monkeypatch):
    """'Chat model unreachable' must stay distinguishable from 'model said
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
        finish_reason = "stop"      # a complete answer; see _complete_text

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


def test_get_llm_disables_sdk_retries(monkeypatch):
    """The project constraint is no backoff/retry on 429 - a rate limit must
    stay visible. The openai SDK's own default (DEFAULT_MAX_RETRIES=2) retries
    429s (and 5xx) silently, with backoff, so _get_llm must override it."""
    monkeypatch.setattr(engine.settings, "chat_provider", "openrouter")
    monkeypatch.setattr(engine.settings, "openrouter_model", "vendor/model-x")
    monkeypatch.setattr(engine.settings, "openrouter_api_key", "test-key")
    engine._get_llm.cache_clear()

    client = engine._get_llm()

    assert client.max_retries == 0
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


def test_unavailable_message_is_never_advice_whichever_provider(monkeypatch):
    """_has_advice recognises our own fallback by a single, provider-NEUTRAL
    prefix. If the prefix ever became provider-dependent, a hosted outage message
    would read as real advice and products would be recommended under an error."""
    messages = {}
    for provider in ("local", "openrouter"):
        monkeypatch.setattr(engine.settings, "chat_provider", provider)
        monkeypatch.setattr(engine.settings, "openrouter_model", "vendor/model-x")
        msg = engine._llm_unavailable_message(RuntimeError("connection refused"))
        messages[provider] = msg
        assert not engine._has_advice(msg)
        assert msg.startswith(engine._LLM_UNAVAILABLE_PREFIX)
        assert "connection refused" in msg      # technical detail still reaches the tail

    # The hint must actually differ, or the user is pointed at the wrong place.
    assert messages["local"] != messages["openrouter"]
    assert "LM Studio" in messages["local"]
    assert "OpenRouter" in messages["openrouter"]
    # ...and the provider name must NOT be in the shared prefix.
    assert "LM Studio" not in engine._LLM_UNAVAILABLE_PREFIX
    assert "OpenRouter" not in engine._LLM_UNAVAILABLE_PREFIX


# --------------------------------------------------------------------------- #
# Product-suppression backstop (marker-independent)
# --------------------------------------------------------------------------- #
def test_contains_any_matches_turkish_noun_and_verb_forms():
    """Left-boundary matching reaches derivational/verb tails the crop-lexicon
    pattern (right boundary + case suffixes) cannot. All verified empirically."""
    assert engine._contains_any("Asmalarda budama yapin", ("budam",))
    assert engine._contains_any("Serin yerde depolayin", ("depola",))
    assert engine._contains_any("Haftada iki kez sulayin", ("sula",))         # verb form
    assert engine._contains_any("Bitkiyi duzenli gubreleyin", ("gubre",))     # derivational


def test_contains_any_matches_a_diacritic_stem_end_to_end():
    """Folding guard: the stem carries diacritics, _normalize_tr folds the text
    (ş->s, ü->u). _contains_any must fold the stem too, or it silently never
    matches (a dead gate that looks green)."""
    assert engine._contains_any("Once agaci asilayin", ("aşıla",))
    assert engine._contains_any("Bitkiyi gubreleyin", ("gübre",))


def test_contains_any_avoids_the_measured_false_positives():
    """The three traps that killed the intuitive stems. Each MUST stay clear."""
    assert not engine._contains_any("Asiri sulama koku curutur", ("asila",))   # not "aşırı"
    assert not engine._contains_any("Prunus turleri kirazgillerdendir",
                                    ("prune", "pruning"))                       # not "Prunus"
    assert not engine._contains_any("Budala olma dediler", ("budam",))         # not "budala"
    assert not engine._contains_any("Gecmisi restore etti", ("storag",))       # not "restore"


def test_production_activity_tuple_is_locked_against_the_wrong_stems():
    """Locks the shipped _NON_PRODUCT_ACTIVITY tuple, not a local literal: each
    trap word would match only if a stem were reverted to its intuitive-but-wrong
    form (buda/aşı/prun/stor). If that regression ever lands, this fails."""
    act = engine._NON_PRODUCT_ACTIVITY
    assert not engine._contains_any("asiri miktarda su verildi", act)   # not aşı
    assert not engine._contains_any("Prunus avium bir kiraz turudur", act)  # not prun
    assert not engine._contains_any("budala olma dediler", act)         # not buda
    assert not engine._contains_any("dosyayi restore etti", act)        # not stor


def test_looks_non_product_suppresses_a_pure_pruning_answer():
    assert engine._looks_non_product(
        "Asmalarda budama kis sonunda, uyku doneminde yapilir.")


def test_looks_non_product_keeps_a_pure_nutrition_answer():
    assert not engine._looks_non_product(
        "Domates yapraklari sarariyorsa azot eksikligi olabilir, gubre verin.")


def test_looks_non_product_keeps_a_mixed_answer():
    """Nutrition term present -> never suppressed, even with an activity term."""
    assert not engine._looks_non_product(
        "Once bitkiyi gubreleyin, ardindan kuru dallari budayin.")


def test_looks_non_product_keeps_a_neutral_answer():
    """Neither signal -> when in doubt, show."""
    assert not engine._looks_non_product(
        "Bu bitki genellikle ilkbaharda cicek acar ve yari golge sever.")


# --- coverage extension (round 2, 2026-07-25): new categories + verimli removal ---
def test_looks_non_product_suppresses_the_new_activity_categories():
    """The categories the hosted measurement showed still leaking: sowing, training,
    rootstock selection, post-harvest drying, self-fertility. Each target answer must
    now suppress (activity term present, no nutrition term)."""
    assert engine._looks_non_product(
        "Misirda en uygun ekim zamani 20 Mayistir.")                    # ekim
    assert engine._looks_non_product(
        "Serada domateste atlatma terbiye sistemi onerilir.")           # terbiye
    assert engine._looks_non_product(
        "Marsh Seedless altintop icin carrizo anaci onerilir.")         # anaç
    assert engine._looks_non_product(
        "Hachiya hurmasi kurutulduktan sonra SMB uygulanmali.")         # kurut
    assert engine._looks_non_product(
        "Santa Maria armudu partenokarp bir cesittir, dolleyici gerekmez.")  # partenokarp
    assert engine._looks_non_product(
        "Beurre Hardy icin bahceye tozlayici cesit dikilmelidir.")      # tozla (pollinizer)


def test_looks_non_product_suppresses_self_fertility_after_verimli_removal():
    """The pear self-fertility answers say 'kendine verimli' - reproductive fertility,
    NOT nutrition. Before removal, 'verimli' cancelled suppression; now it must suppress
    (partenokarp / tozla is the activity term, no true nutrition term remains)."""
    assert engine._looks_non_product(
        "Santa Maria armudu partenokarp bir cesittir, kendine verimlidir.")
    assert engine._looks_non_product(
        "Asmada budama kis dinlenme doneminde, verimli surgun icin gozler birakilir.")


def test_verimli_removal_still_keeps_soil_fertility_nutrition_answers():
    """Removing 'verimli' must not regress a nutrition answer: soil-fertility answers
    always carry gübre/besin/azot/kompost, so they stay protected."""
    assert not engine._looks_non_product(
        "Toprak verimliligini artirmak icin ahir gubresi ve kompost kullanin.")
    assert not engine._looks_non_product(
        "Bu cesit icin organik gubre ve kompost onerilir.")


def test_ekim_month_is_safe_because_the_nutrition_half_keeps_it():
    """'ekim' also means October. A fertilize-in-October answer carries a nutrition
    term, so the rule keeps it despite the activity match."""
    assert not engine._looks_non_product(
        "Ekim ayinda azotlu gubre ile besleme yapin.")


def test_production_tuples_carry_the_round2_terms():
    """Locks the shipped tuples so a later edit cannot silently drop the round-2 work:
    the new activity stems are present and 'verimli' is gone from nutrition."""
    for stem in ("ekim", "terbiye", "anaç", "kurut", "partenokarp", "tozla"):
        assert stem in engine._NON_PRODUCT_ACTIVITY
    assert "tozlaş" not in engine._NON_PRODUCT_ACTIVITY   # broadened to "tozla"
    assert "verimli" not in engine._NUTRITION_TERMS


def test_stream_answer_suppresses_products_when_non_product_without_a_marker(
        monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    monkeypatch.setattr(
        engine, "_get_llm",
        lambda: _fake_stream_llm(["Asmalarda budama kis sonunda yapilir."]))
    out = "".join(engine.stream_answer("Asmada budama ne zaman?"))
    assert '"type": "products"' not in out           # backstop suppressed the event
    assert "budama" in _sse_tokens(out)              # the answer still streamed


def test_stream_answer_keeps_products_on_a_nutrition_answer_without_a_marker(
        monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    monkeypatch.setattr(
        engine, "_get_llm",
        lambda: _fake_stream_llm(["Azot eksikligi olabilir, gubre verin."]))
    out = "".join(engine.stream_answer("Yapraklar sariyor"))
    assert '"type": "products"' in out               # NOT suppressed


def test_stream_answer_backstop_sees_the_whole_answer_not_just_the_warmup(
        monkeypatch):
    """The activity term arrives AFTER warmup. If the backstop only inspected the
    warmup buffer it would miss it; it must inspect the accumulated full answer."""
    monkeypatch.setattr(engine, "retrieve_context", lambda m, **kw: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    # First chunk is >80 chars (clears _STREAM_WARMUP=80) with NO activity/nutrition
    # term; the pruning term lands only in the second chunk, post-warmup.
    head = ("Bu konuda size yardimci olabilirim ve asagida konuyu adim adim "
            "ayrintili bicimde acikliyorum simdi. ")
    assert len(head) > engine._STREAM_WARMUP
    monkeypatch.setattr(
        engine, "_get_llm",
        lambda: _fake_stream_llm([head, "Once kuru dallari budamak gerekir."]))
    out = "".join(engine.stream_answer("Nasil yapilir?"))
    assert '"type": "products"' not in out           # suppressed on the late term


def test_answer_records_the_route(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    r = engine.answer("Buğday ekmenin dekara maliyeti nedir?")
    assert r.route == "budget"
    assert r.route_how == "rule"


def test_route_is_not_exposed_over_the_api(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    # Must be a non-budget question; the budget route short-circuits before the stubs above.
    r = engine.answer("Elma ağacı ne zaman budanır?")
    assert set(r.as_api()) == {"answer", "recommended_products", "form", "dose_form",
                               "compare_form"}
    assert "Kompost" in r.answer  # Corpus path exercises the stubs, not the budget route.


def test_router_failure_does_not_break_answering(monkeypatch):
    from src import router
    monkeypatch.setattr(router, "classify",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    r = engine.answer("Herhangi bir soru")
    assert r.answer == "Kompost kullanabilirsiniz."
    assert r.route == ""


def test_stream_answer_computes_the_route(monkeypatch):
    seen = {}
    from src import router
    real = router.classify

    def spy(message, history=None):
        seen["route"] = real(message, history)
        return seen["route"]

    monkeypatch.setattr(router, "classify", spy)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    monkeypatch.setattr(engine, "_get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no stream")))
    list(engine.stream_answer("Domatese ne zaman gübre vermeliyim?"))
    assert seen["route"] == ("fert_plan", "rule")


def test_stream_answer_wire_format_has_no_route_field(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    monkeypatch.setattr(engine, "_get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no stream")))
    events = [json.loads(e[6:]) for e in engine.stream_answer("Merhaba") if e.startswith("data: ")]
    for e in events:
        assert "route" not in e, e
        assert e["type"] in ("token", "products", "done"), e


def test_stream_answer_survives_a_router_failure(monkeypatch):
    from src import router
    monkeypatch.setattr(router, "classify",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    monkeypatch.setattr(engine, "_get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no stream")))
    # The router raises. What must hold is that streaming COMPLETES and closes
    # cleanly instead of propagating - what the reply says is the LLM path's
    # business, not the router's. (With _get_llm down, stream_answer takes its
    # own unavailable-message branch and never reaches _complete_text; asserting
    # on the mocked text here would test that branch, not the router.)
    events = [json.loads(e[6:]) for e in engine.stream_answer("Herhangi bir soru")
              if e.startswith("data: ")]
    assert events[-1]["type"] == "done"
    assert any(e["type"] == "token" for e in events)


# --------------------------------------------------------------------------- #
# fert_plan context block
# --------------------------------------------------------------------------- #
def test_context_block_is_empty_off_the_fert_plan_route():
    assert engine._context_block(
        "plant_info", "Asmada budama ne zaman yapılır?", None, date(2026, 8, 10)) == ""
    assert engine._context_block(
        "", "Herhangi bir soru", None, date(2026, 8, 10)) == ""


def test_context_block_names_season_and_province(monkeypatch):
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: "yağış yok")
    out = engine._context_block(
        "fert_plan", "Manisa'dayım, domatese ne zaman gübre vermeliyim?",
        None, date(2026, 8, 10))
    assert "Manisa" in out
    assert "Ağustos" in out
    assert "yağış yok" in out


def test_context_block_asks_for_the_province_when_missing(monkeypatch):
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: "yağış yok")
    out = engine._context_block(
        "fert_plan", "Domatese ne zaman gübre vermeliyim?", None, date(2026, 8, 10))
    assert "Ağustos" in out                      # season still known
    assert "ili BILINMIYOR" in out               # and it says the province is unknown
    assert "yağış" not in out                    # no province => no weather line


def test_context_block_survives_a_weather_outage(monkeypatch):
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: None)
    out = engine._context_block(
        "fert_plan", "Manisa'dayım, domatese ne zaman gübre vermeliyim?",
        None, date(2026, 8, 10))
    assert "Manisa" in out
    assert out != ""


def test_context_block_reaches_the_system_prompt():
    # Calls _build_messages directly, which never touches weather - patching
    # src.context.weather.forecast here would make the test read as if it
    # exercised the weather path when it does not.
    msgs = engine._build_messages("soru", None, "CTX", [], "DURUM SATIRI")
    assert "DURUM SATIRI" in msgs[0]["content"]
    assert msgs[0]["role"] == "system"
    assert len(msgs) == 2                        # shape unchanged: system + user


def test_build_messages_without_a_block_is_unchanged():
    # The 4-argument call site (evals/probe_product_gate.py) must keep working
    # and must produce exactly what it produced before this task.
    a = engine._build_messages("soru", None, "CTX", [])
    b = engine._build_messages("soru", None, "CTX", [], "")
    assert a == b


# --------------------------------------------------------------------------- #
# fert_plan framing sentence
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _clear_fertplan_load_cache():
    """`fertplan._load` is `lru_cache`d, but `monkeypatch.setattr(_TABLE_PATH, ...)`
    only restores the path at teardown - it never touches the cache. Without
    this, a table written by test N can still be sitting in the cache when test
    N+1 runs, so tests would pass or fail depending on execution order. Clear
    both before (so this test reads its own fixture) and after (so the next
    test doesn't inherit this one's). Modeled on the identical fixture in
    tests/test_fertplan.py."""
    from src import fertplan
    fertplan._load.cache_clear()
    yield
    fertplan._load.cache_clear()


def test_empty_table_does_not_refuse(monkeypatch):
    from src import fertplan
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Domatese azot verebilirsiniz.")
    r = engine.answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
    assert r.route == "fert_plan"
    assert "Domatese azot verebilirsiniz." in r.answer
    assert fertplan.FRAMING not in r.answer   # no reviewed rows, so no framing


def test_reviewed_rows_add_the_framing_sentence(monkeypatch, tmp_path):
    from src import fertplan
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "Fide döneminde ..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Program: ...")
    r = engine.answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
    assert fertplan.FRAMING in r.answer


def test_framing_is_not_appended_to_a_fallback_message(monkeypatch, tmp_path):
    # The LLM is down, so the reply is our own "cannot answer" text. Appending
    # "this programme is an estimate" to it would claim a programme that does
    # not exist.
    from src import fertplan
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text",
                        lambda m: (_ for _ in ()).throw(RuntimeError("down")))
    r = engine.answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
    assert fertplan.FRAMING not in r.answer


def _fake_stream_client(text: str, chunk_size: int = 40):
    """A stand-in LM Studio client that actually streams `text`.

    Mocking _get_llm to RAISE cannot be used to exercise anything downstream of
    the stream: stream_answer then takes its own unavailable-message branch,
    sets has_advice=False, and never reaches _complete_text - so the test would
    measure the outage path instead. See the comment on
    test_stream_answer_survives_a_router_failure, which records the same trap.
    """
    from types import SimpleNamespace

    def _chunk(content, finish=None):
        return SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=content), finish_reason=finish)])

    parts = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    def create(**kwargs):
        return iter([_chunk(p) for p in parts] + [_chunk("", "stop")])

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_streaming_also_appends_the_framing_sentence(monkeypatch, tmp_path):
    # BOTH real clients stream (mobile-app/src/api.ts and
    # web-widget/widget/agro-chat-widget.js send stream:true). Framing that only
    # lands on answer() reaches no user at all.
    from src import fertplan
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_stream_client("Domateste program: " + "x" * 200))
    events = [json.loads(e[6:])
              for e in engine.stream_answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
              if e.startswith("data: ")]
    # The framing must arrive as ordinary answer text, before the stream closes,
    # and the wire format must not have grown a new event type.
    assert events[-1]["type"] == "done"
    for e in events:
        assert e["type"] in ("token", "products", "done"), e
    text = "".join(e["content"] for e in events if e["type"] == "token")
    assert fertplan.FRAMING in text
    # Ordering must be pinned on event position, not on the joined token text:
    # joining only `token` events would still pass if framing were yielded
    # AFTER the `products` event, which is exactly the ordering bug this guards.
    framing_idx = next(i for i, e in enumerate(events)
                       if e["type"] == "token" and fertplan.FRAMING in e["content"])
    products_idx = next(i for i, e in enumerate(events) if e["type"] == "products")
    assert framing_idx < products_idx


def test_streaming_does_not_append_framing_without_reviewed_rows(monkeypatch):
    from src import fertplan
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: _fake_stream_client("Cevap: " + "x" * 200))
    events = [json.loads(e[6:])
              for e in engine.stream_answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
              if e.startswith("data: ")]
    text = "".join(e["content"] for e in events if e["type"] == "token")
    assert "Cevap:" in text
    assert fertplan.FRAMING not in text


def test_streaming_does_not_frame_an_outage_message(monkeypatch, tmp_path):
    # The LLM is unreachable, so the reply is our own fallback text. Framing it
    # would claim a fertilization programme that was never produced. This is the
    # streaming twin of test_framing_is_not_appended_to_a_fallback_message.
    from src import fertplan
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_get_llm",
                        lambda: (_ for _ in ()).throw(RuntimeError("down")))
    events = [json.loads(e[6:])
              for e in engine.stream_answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
              if e.startswith("data: ")]
    text = "".join(e["content"] for e in events if e["type"] == "token")
    assert fertplan.FRAMING not in text


def test_streaming_appends_framing_on_the_blank_answer_backstop(monkeypatch, tmp_path):
    # Finding 1: the third recovery branch in stream_answer (`not emitted and
    # not failed`) streamed a recovered answer via _complete_text but never set
    # `emitted = True` - so gating framing on `emitted` silently dropped it on
    # exactly the path the backstop exists for: an empty stream that ends with
    # finish_reason 'stop'. The gate must key off `full_answer` instead, which
    # this branch does set.
    from src import fertplan
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    monkeypatch.setattr("src.context.weather.forecast", lambda p, today=None: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    # A stream that yields no content at all and closes with finish_reason
    # 'stop' - the exact blank-answer case the backstop exists for.
    monkeypatch.setattr(engine, "_get_llm", lambda: _fake_stream_llm([], finish="stop"))
    monkeypatch.setattr(engine, "_complete_text",
                        lambda m: "Domateste program: " + "x" * 200)
    events = [json.loads(e[6:])
              for e in engine.stream_answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
              if e.startswith("data: ")]
    text = "".join(e["content"] for e in events if e["type"] == "token")
    assert fertplan.FRAMING in text


def test_crop_choice_block_names_the_factors_and_forbids_a_recommendation():
    out = engine._context_block(
        "crop_choice", "Manisa'dayım, bu yıl ne eksem?", None, date(2026, 8, 11))
    assert "Manisa" in out
    assert "toprak" in out and "sulama" in out and "munavebe" in out
    assert "ONERME" in out


def test_crop_choice_block_asks_for_the_province_when_missing():
    out = engine._context_block(
        "crop_choice", "Bu yıl ne eksem?", None, date(2026, 8, 11))
    assert "BILINMIYOR" in out
    # The factors are still explained without a province - an unknown location
    # costs one line, not the answer.
    assert "toprak" in out and "ONERME" in out


def test_the_location_question_asks_for_the_country_in_a_shape_the_guard_accepts():
    """THE RECOVERY FOR THE DELETED BARE-NAME BRANCH, and the one thing that
    makes the 39 surrendered accepts survivable: the question itself steers the
    reply into the only Turkish shape the guard still reads.

    A grower outside Turkiye cannot answer "which province", and since this wave
    a bare "Fransa" is not an answer either. So the question asks for the country
    AND SHOWS THE SPELLING - "Fransa'dayim" is `_SELF_TR`'s own pattern, written
    out rather than described because a model copies an example and paraphrases
    an instruction.

    The example is asserted against the guard rather than quoted, so the two can
    never drift: if the pattern narrows, this fails."""
    assert "Fransa'dayim" in engine._ASK_LOCATION
    assert engine._states_location("Fransa'dayim", engine._code_aliases(68))
    assert "hangi ilde" in engine._ASK_LOCATION
    assert "ulkesini" in engine._ASK_LOCATION


def test_only_the_route_that_can_read_a_country_asks_for_one():
    """TWO ROUTES, TWO QUESTIONS, and the difference is the point.

    `_country_lines` has exactly ONE caller, `_crop_choice_block`. An earlier
    revision of this test pinned both routes to the same string, because the
    brief that ordered the change asked for that - and the result was a
    `fert_plan` user being told to write "Fransa'dayim" and then asked again on
    the next turn, since nothing on that route reads the answer. A question whose
    answer is discarded is worse than a narrower question.

    The world layer reaching `fert_plan` is a separate round: that route serves a
    fertilization and irrigation plan and FAOSTAT publishes neither.

    `_ASK_LOCATION` DOES NOT CONTAIN "Turkiye disinda", deliberately: that is the
    phrase the block prints when a country IS settled, and four tests assert it
    is absent from a block that is still asking. One substring with two meanings
    would make those four pass for the wrong reason."""
    fert = engine._context_block("fert_plan", "Domatese ne zaman gubre versem?",
                                 None, date(2026, 8, 10))
    crop = engine._context_block("crop_choice", "Bu yil ne eksem?", None,
                                 date(2026, 8, 10))
    assert engine._ASK_LOCATION in crop
    assert engine._ASK_LOCATION not in fert
    # Both still ask for the province; only one invites a country.
    assert "hangi ilde oldugunu sor" in fert
    assert "ulkesini" not in fert
    assert "Turkiye disinda" not in engine._ASK_LOCATION


def test_answering_the_country_invitation_is_re_asked_on_fert_plan():
    """THE LOOP THE SAME-ROUTE FIX LEFT OPEN, nailed rather than closed.

    `_ASK_LOCATION` reaches `crop_choice` only, so the question and its answer
    live on one route - but ROUTING IS PER MESSAGE, and the same conversation
    crosses routes. A grower invited to write his country, who does so, and who
    then asks when to fertilise, is routed to `fert_plan` and asked for a TURKISH
    PROVINCE: the one question he cannot answer, one turn after answering the one
    we told him to answer.

    THIS WAVE CREATED IT. Before the invitation existed the `fert_plan` ask was
    the only ask and there was nothing for it to contradict; the ask itself is
    unchanged and byte-identical to main's. So this is not a regression in
    `fert_plan`, it is a new contradiction between two routes.

    NOT FIXED HERE, AND THE REASON IS NOT COST. Widening `_country_lines` to
    `fert_plan` would replace the province question with nothing: that route
    serves a fertilisation and irrigation plan, and FAOSTAT publishes neither -
    it publishes yield and price, which is what `crop_choice` needs. The world
    layer reaching `fert_plan` is a separate round with its own data question.
    Pinned so the next wave finds the behaviour written down instead of
    rediscovering it from a user report."""
    history = [{"role": "assistant", "content": engine._ASK_LOCATION},
               {"role": "user", "content": "Fransa'dayım"}]
    crop = engine._context_block("crop_choice", "buğday mı ekmeliyim",
                                 history, date(2026, 9, 25))
    fert = engine._context_block("fert_plan", "buğdaya ne zaman gübre versem",
                                 history, date(2026, 9, 25))
    # The country was read, so crop_choice stops asking.
    assert "Turkiye disinda: France" in crop
    assert "BILINMIYOR" not in crop
    # And the very next turn asks him for a province anyway.
    assert "hangi ilde oldugunu sor" in fert
    assert "BILINMIYOR" in fert
    assert "France" not in fert


def test_the_label_fold_is_one_function_and_not_six_copies():
    """`re.split(r"\\s*[(,]", label)[0].strip()` was written out SIX times - three
    in src/engine.py, two in src/crop_compare.py, and a sixth added one wave ago
    inside the country guard's crop-collision gate, which this wave deleted.

    They diverge in the dangerous direction. The folded form answers "is this
    label this family's", so a split set that stops matching reads as "not this
    crop" - and on the gate that held the sixth copy, "not a crop" meant PLACE
    THE USER. The module argues against exactly this twenty lines from one of the
    copies, in `_code_aliases`' docstring.

    Pinned on the three label shapes the shipped table actually holds: a bare
    family name, an exclusion clause, and a parenthetical variant."""
    from src import crop_compare
    assert engine._label_head("Fasulye") == "Fasulye"
    assert engine._label_head("Buğday, Durum Buğdayı Hariç") == "Buğday"
    assert engine._label_head("Domates (Salçalık)") == "Domates"
    assert engine._family_head("Buğday, Durum Buğdayı Hariç") == "bugday"
    assert engine._family_head("Domates (Salçalık)") == "domates"
    # And crop_compare reads the same two functions rather than its own copies.
    assert crop_compare._label_head is engine._label_head
    assert crop_compare._family_head is engine._family_head


def test_crop_choice_block_carries_the_season():
    """The month comes from `today`, not from the clock, so this is stable."""
    out = engine._context_block(
        "crop_choice", "Manisa'dayım, bu yıl ne eksem?", None, date(2026, 8, 11))
    assert "Ağustos" in out


def test_a_crop_choice_failure_degrades_to_an_empty_block(monkeypatch):
    """Spec §8: a context failure must cost the situation lines, not the answer."""
    monkeypatch.setattr("src.context.season.describe",
                        lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    assert engine._context_block(
        "crop_choice", "Bu yıl ne eksem?", None, date(2026, 8, 11)) == ""


# --------------------------------------------------------------------------- #
# The world layer reaches the crop_choice block
# --------------------------------------------------------------------------- #
# These read the SHIPPED data/world_norms.json, the way tests/test_norms_world.py
# does. The figures and flags below are what that file holds today; if it is
# ever rebuilt and one of them moves, the assertion that fails names the cell -
# pick another country with the same flag rather than dropping the assertion.
def test_a_country_figure_reaches_the_prompt_with_its_source():
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "France" in block
    assert "kg/da" in block
    assert "USD/kg" in block
    # Where it came from, beside the number: the source and the cell's own year.
    assert "FAOSTAT" in block
    assert "2024" in block


def test_a_foreign_grower_is_not_asked_for_a_turkish_province():
    """The country line REPLACES the ask, it does not sit beside it. A block
    that names France and still says "ask which il he is in" would have the
    assistant asking a French grower for a Turkish province."""
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "BILINMIYOR" not in block
    # The factors are unchanged - the country costs the location line, nothing else.
    assert "toprak" in block and "ONERME" in block


def test_a_world_figure_says_when_it_is_an_estimate():
    """41,3% of the shipped world yield cells carry FAOSTAT's `E` flag - the
    figure is FAO's estimate, not a country's report. This project prints a
    number with where it came from or does not print it.

    Ghana's sorghum yield is such a cell. The caution line deliberately avoids
    the word "tahmin" so that finding it here means the FLAG reached the
    sentence, not the boilerplate."""
    block = engine._crop_choice_block("Gana'dayım, sorgum ekiyorum",
                                      None, date(2026, 9, 25))
    assert "Ghana" in block
    assert "125,99 kg/da (2024, FAO tahmini" in block


def test_a_figure_from_an_outside_source_is_not_called_an_estimate():
    """`E` is not the only flag that means "not the country's own report", and
    the two must not be collapsed. Nigeria's sorghum yield is `X`, a figure
    FAOSTAT took from an outside organization - said as that, not as a FAO
    estimate."""
    block = engine._crop_choice_block("Nijerya'dayım, sorgum ekiyorum",
                                      None, date(2026, 9, 25))
    assert "106,56 kg/da (2024, dis kurulustan alinmis deger)" in block
    assert "tahmin" not in block.lower()


def test_each_world_measure_carries_its_own_year():
    """FAOSTAT ends at 2024 where TÜİK reaches 2025, and its two measures need
    not even agree with each other: Ghana's sorghum yield is 2024 and its price
    2022. One year printed for the block would misdate one of them."""
    block = engine._crop_choice_block("Gana'dayım, sorgum ekiyorum",
                                      None, date(2026, 9, 25))
    assert "(2024," in block
    assert "0,4644 USD/kg (2022," in block


def test_a_turkish_user_still_gets_tuik():
    block = engine._crop_choice_block("Konya'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "Konya" in block
    assert "France" not in block
    assert "FAOSTAT" not in block


def test_an_unresolved_country_asks_rather_than_guessing():
    block = engine._crop_choice_block("buğday mı ekmeliyim", None,
                                      date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "FAOSTAT" not in block


def test_turkiye_named_as_a_country_still_asks_for_the_province():
    """`data/crop_norms.json`'s national row is empty BY CONSTRUCTION, so a
    Turkish user who has not named a province gets no figure and the assistant
    asks - exactly as it did before the world layer existed. Türkiye must never
    fall through to FAOSTAT's own area 223."""
    block = engine._crop_choice_block("Türkiye'deyim, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "FAOSTAT" not in block


@pytest.mark.parametrize("message", [
    # The answer to "hangi ildesiniz?", and nothing else.
    "Fransa'dayım",
    "Fransa'dayım, bu yıl ne eksem?",
])
def test_a_stated_country_with_no_crop_named_still_loses_the_province_ask(message):
    """The worst turn in the route, and the whole of it was a docstring that was
    wrong. An earlier revision returned [] whenever there was no figure, on the
    reasoning that "the country's NAME only exists on a figure". It does not: it
    is in data/world_norms.json's `countries` table. So a grower who answered
    "hangi ildesiniz?" with "Fransa'dayım" was asked the same question straight
    back, and `_country_lines` asks every user turn, so it kept happening.

    The location line now stands without figures - and prints no figure and no
    FAOSTAT provenance instruction, because there is nothing to attribute."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert "BILINMIYOR" not in block
    assert "France" in block
    assert "hangi ilde oldugunu SORMA" in block
    assert "FAOSTAT" not in block
    assert "kg/da" not in block and "USD/kg" not in block
    # The route itself is intact.
    assert "toprak" in block and "ONERME" in block


def test_a_stated_country_with_a_crop_we_hold_no_cell_for_keeps_the_location():
    """The second of the three ways a figure goes missing, and it used to take
    the location with it: a crop FAOSTAT publishes nothing for in this country
    sent the grower back to the province question."""
    block = engine._crop_choice_block("Fransa'dayım, yenidünya ekeyim mi", None,
                                      date(2026, 9, 25))
    assert "BILINMIYOR" not in block
    assert "France" in block
    assert "kg/da" not in block and "USD/kg" not in block


def test_the_figureless_line_is_dropped_when_the_country_has_no_name(monkeypatch):
    """Unreachable on the shipped tables and pinned anyway: with no name for the
    area there is no line to print, and the province ask is the honest fallback
    rather than a sentence with a hole in it."""
    monkeypatch.setattr("src.norms._load_world",
                        lambda: {"items": {}, "countries": {},
                                 "yield": {}, "price": {}})
    block = engine._crop_choice_block("Fransa'dayım, bu yıl ne eksem?", None,
                                      date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "France" not in block


def test_a_country_layer_failure_costs_only_its_own_lines(monkeypatch):
    """A context line is a convenience. The country layer failing must cost the
    country lines and leave the province ask, the season and the factors."""
    monkeypatch.setattr("src.context.country.extract_country",
                        lambda m, h=None: (_ for _ in ()).throw(RuntimeError("boom")))
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "toprak" in block and "ONERME" in block
    assert "FAOSTAT" not in block


@pytest.mark.parametrize("message,not_in_block", [
    # The coconut, found first and the only one an earlier wave closed. France's
    # WALNUT yield was printed for it.
    ("Fransa'dayım, hindistan cevizi ekeyim mi", "Ceviz"),
    # Physalis is not a cherry. France's cherry yield was 461,73 kg/da.
    ("Fransa'dayım, yer kirazı ekeyim mi", "Kiraz"),
    # Persimmon is not an apple. France's apple yield was 3722,57 kg/da.
    ("Fransa'dayım, cennet elması ekeyim mi", "Elma"),
    # Prickly pear is neither maize nor fig, and it reached the world layer by
    # two doors at once: `Mısır` is also the Turkish name of Egypt. It hides
    # behind a comma inside `Frenk İnciri (Hint, Mısır İnciri)`, which is why
    # reading the labels found the other two and not this one.
    ("Fransa'dayım, mısır inciri ekeyim mi", "FAOSTAT"),
])
def test_a_plant_the_table_has_no_family_for_gets_no_other_crops_figures(
        message, not_in_block):
    """THE WHOLE CLASS, against the SHIPPED table, which is the measurement the
    wave that closed the coconut did not take. It looked at this exact shape -
    it took `Malta Eriği` out of the hand list, correctly and for the right
    reason - and then closed the finding on one example without counting the
    set. A sweep of all 246 labels found three more, two of them live figures.

    The country line still prints, because the user did say where he is; what
    must not print is another plant's yield and price under his question."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert "Turkiye disinda: France" in block
    assert "kg/da" not in block
    assert "USD/kg" not in block
    assert not_in_block not in block


# --------------------------------------------------------------------------- #
# A country whose Turkish name is also a crop name
# --------------------------------------------------------------------------- #
def test_a_country_named_like_a_crop_does_not_supply_that_crop():
    """`Mısır` is BOTH the Turkish name for Egypt and the label for maize, so
    the crop detector read the country word as a crop and the block printed
    Egypt's maize yield and price for a question that names no crop at all -
    one crop's figures and nothing else under a "BELIRLI BIR URUN ONERME"
    instruction, on no basis.

    Measured on e021bca, this same sentence produced:
        Mısır - FAOSTAT ulke ortalama verimi: 758,53 kg/da (2024, ...)
        Mısır - FAOSTAT ulke ortalama ciftci fiyati: 0,4702 USD/kg (2023, ...)
    """
    block = engine._crop_choice_block("Mısır'dayım, bu yıl ne eksem?", None,
                                      date(2026, 9, 25))
    assert "FAOSTAT" not in block
    assert "758" not in block
    assert "kg/da" not in block and "USD/kg" not in block
    # Egypt's NAME is not the defect and is no longer dropped with the figures:
    # the user said where he is, so asking him for a Turkish province would be
    # the separate defect this file pins just above. What may not appear is a
    # crop nobody named and a figure nobody asked for.
    assert "Egypt" in block
    assert "BILINMIYOR" not in block
    assert "toprak" in block and "ONERME" in block


def test_two_crops_never_reach_the_country_block_at_all():
    """The guard above is not the only place a Turkish country name costs an
    Egyptian grower his figures, and this pins the other one so a reader of the
    guard alone does not conclude it was.

    answer() forks a message naming TWO crops to the comparison card BEFORE
    `_country_lines` is reached, and that card is province-only. So a real
    Egyptian wheat grower writing "Mısır'dayım, buğday mı ekmeliyim" names two
    crops - `Mısır` and `Buğday` - and is asked for a Turkish province by a
    route this branch never touches. The fork is older than the world layer and
    is not this change's to move."""
    assert len(engine._named_crops("Mısır'dayım, buğday mı ekmeliyim")) == 2


def test_a_country_not_named_like_a_crop_still_asks_nothing_of_the_crop():
    """The guard above drops the FAMILY NAME the resolved country answers to,
    not crop detection as a whole. France is not a crop, so a France question
    naming no crop keeps its old behaviour - which is what
    test_a_country_with_no_crop_named_is_unchanged already pins - and a France
    question naming wheat still gets wheat.

    This case sits beside the Mısır one deliberately: without it the guard could
    be satisfied by refusing every country, and the two tests would both pass.
    """
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "France" in block
    assert "597,35 kg/da" in block


# --------------------------------------------------------------------------- #
# The printed crop name may not be narrower than the FAO item
# --------------------------------------------------------------------------- #
def test_the_printed_crop_name_is_the_family_not_the_narrower_id():
    """data/crop_fao_map.json says FAOSTAT does not split durum from other wheat
    and that both Turkish wheat ids share item 15. Printing the id's own label
    beside the number - `Buğday, Durum Buğdayı Hariç - ... 597,35 kg/da` - put a
    narrowing on a figure the map explicitly disclaims, and a paraphrase of it
    ("Fransa'da durum dışı buğdayın verimi") is a claim nobody made."""
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "Buğday - FAOSTAT ulke ortalama verimi: 597,35 kg/da" in block
    assert "Durum" not in block


def test_the_tomato_item_is_not_narrowed_to_the_processing_id_either():
    """The same note on item 388: FAOSTAT does not split table from processing
    tomatoes, and the Dutch figure is overwhelmingly fresh. `Domates (Salçalık)`
    beside 47889,02 kg/da said processing tomato."""
    block = engine._crop_choice_block("Hollanda'dayım, domates ekeyim mi",
                                      None, date(2026, 9, 25))
    assert "Domates - FAOSTAT ulke ortalama verimi:" in block
    assert "Salçalık" not in block


@pytest.mark.parametrize("message,named", [
    # 403 dry / 402 fresh. The fresh id is the one that carries BOTH measures
    # for France, so the loop now reaches it - see the candidate test below.
    ("Fransa'dayım, soğan ekeyim mi", "Soğan (Taze)"),
    ("Fransa'dayım, bezelye ekeyim mi", "Bezelye, Taze"),    # 187 / 417
])
def test_a_family_spanning_two_fao_items_keeps_the_id_label(message, named):
    """The family name is only right when every mapped id in the family reads the
    SAME cell. Measured over the shipped tables, 5 of 187 families map to two
    items - a dry one and a fresh one - so there the figure belongs to half the
    family and the bare family name is the opposite failure to the one it fixed:
    not a name narrower than the figure, but a figure that belongs to half the
    name.

    These two families are the ones where the ANSWERING id's label is exactly
    right - it reads an item no other Turkish id shares - so the id's label is
    what gets printed. The three where it is not are below."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert f"{named} - FAOSTAT ulke ortalama verimi:" in block


@pytest.mark.parametrize("message,item_label,not_named", [
    # Item 401 is shared by four Turkish peppers; `Biber` spans 401 and 689, so
    # neither the family name nor the id's label describes the cell.
    ("Fransa'dayım, biber ekeyim mi",
     "Chillies and peppers, green", "Dolmalık"),
    # Item 181, two ids - and crop_fao_map's own note on it says FAOSTAT does
    # not separate food-grade broad beans from feed-grade ones, so `Yemlik`
    # beside the figure was contradicted by the map that supplied it.
    ("Fransa'dayım, bakla ekeyim mi",
     "Broad beans and horse beans, dry", "Yemlik"),
    ("Fransa'dayım, fasulye ekeyim mi", "Beans, dry", "Barbunya"),  # 176, two
])
def test_an_item_shared_by_several_ids_is_named_by_faostat(message, item_label,
                                                           not_named):
    """THE THIRD CASE, which both earlier passes missed because they asked the
    wrong question. `_one_fao_item` is asked of the FAMILY; it can fail - the
    family spans two items - and the answering id's own label STILL be narrower
    than the one item it reads, because several Turkish ids share that item.

    Measured 2026-10-03 over the shipped tables: 321 of the 8425
    (family, country) rows that produce a figure are in this case, over three
    families, and the count is pinned by the test below. `Biber (Dolmalık) -
    FAOSTAT ulke ortalama verimi: 1502,9 kg/da` named one of four peppers for a
    cell FAOSTAT calls "Chillies and peppers, green".

    The name printed is FAOSTAT's own, out of data/world_norms.json's `items`
    table - the only name in this repo that describes that cell."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert f"{item_label}" in block
    assert f"{item_label}" in block.split(" - FAOSTAT ulke ortalama verimi:")[0]
    assert not_named not in block


def test_the_world_layer_row_counts_the_two_comments_rest_on():
    """Pins the three figures `_shared_item_label` and the candidate preference
    are justified by, because one of them had already gone stale in the commit
    that shipped it.

    Both comments said 331 rows were in the third case. 331 is the count for the
    FIRST candidate with either measure - the loop as it stood BEFORE the
    candidate preference landed in the same commit - and the shipped code asks
    about a different id for ten of those rows, which leaves 321. The number
    described behaviour nobody ships.

    This is the same job `test_the_substring_pair_count_the_ordering_is_justified
    _by` does in tests/test_country.py: if a data refresh moves any of these, the
    two comments in src/engine.py move in the same commit. The integers are not
    the point; the prose staying honest is."""
    import re as _re
    from src import norms

    world = norms._load_world()
    areas = sorted({int(key.split("|")[1])
                    for measure in ("yield", "price")
                    for key in world.get(measure, {})})
    families: dict[str, list[str]] = {}
    for crop_id, label in norms.available_crops():
        family = _re.split(r"\s*[(,]", label)[0].strip()
        families.setdefault(family, []).append(crop_id)

    rows = third_case = both_measures_moved_it = 0
    for crop_ids in families.values():
        one_item = engine._one_fao_item(crop_ids)
        for area in areas:
            found = [norm for crop_id in crop_ids
                     if (norm := norms.lookup(crop_id, None, country=area))
                     is not None and (norm.yield_kg_da or norm.price_per_kg)]
            if not found:
                continue
            rows += 1
            if one_item:
                continue
            first = found[0]
            answering = next((n for n in found
                              if n.yield_kg_da and n.price_per_kg), first)
            if engine._shared_item_label(crop_ids, answering.crop):
                third_case += 1
            if answering is not first:
                both_measures_moved_it += 1

    assert rows == 8425
    assert third_case == 321
    assert both_measures_moved_it == 33


_FAO_NAME_RULE = "urunun Turkce adini kullan"


@pytest.mark.parametrize("message", [
    "Fransa'dayım, biber ekeyim mi",    # item 401, four ids
    "Fransa'dayım, bakla ekeyim mi",    # item 181, two
    "Fransa'dayım, fasulye ekeyim mi",  # item 176, two
])
def test_faostats_own_crop_name_carries_an_instruction(message):
    """The country name has been told what to do with it since this block was
    written - "write the Turkish name, add FAOSTAT's in parentheses". The crop
    name had not, and it is English for the same reason and by the same choice,
    so `Chillies and peppers, green (Capsicum spp. and Pimenta spp.)` could
    reach a Turkish grower verbatim.

    The second half of the rule matters as much as the first: this name is
    printed BECAUSE the item is broader than any one Turkish variety, so an
    answer that translates it back to the narrowest one undoes the fix."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert _FAO_NAME_RULE in block
    assert "tek bir ceside mal etme" in block


@pytest.mark.parametrize("message,named", [
    # THE FAMILY-NAME BRANCH: `_one_fao_item` holds, every mapped wheat id is
    # item 15, so `Buğday` describes the cell and the id's label would narrow it.
    ("Fransa'dayım, buğday ekeyim mi", "Buğday"),
    # THE ID-LABEL BRANCH: `_one_fao_item` fails - `Soğan` spans items 403 and
    # 402, `Bezelye` 187 and 417 - and no other Turkish id shares the item the
    # answering one reads, so `_shared_item_label` returns None and the id's own
    # Turkish label is printed. Measured 2026-10-03.
    #
    # THESE TWO PARAMETERS USED TO BE WHEAT AND TOMATO, which are the SAME
    # branch: `_one_fao_item` is True for both (items 15 and 388, each read by
    # every mapped id in its family), so the comment calling tomato "the
    # answering id's label" was wrong and the branch it described was untested.
    ("Fransa'dayım, soğan ekeyim mi", "Soğan (Taze)"),
    ("Fransa'dayım, bezelye ekeyim mi", "Bezelye, Taze"),
])
def test_a_turkish_crop_name_gets_no_faostat_instruction(message, named):
    """The instruction is CONDITIONAL, and this is the half that makes it safe.
    Where the printed name is already Turkish, asking for "FAOSTAT's name in
    parentheses" would have the model invent one - there is no FAO item name on
    these lines to add. Both branches that print a Turkish name are here."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert f"{named} - FAOSTAT ulke ortalama verimi:" in block
    assert _FAO_NAME_RULE not in block


def test_one_fao_item_separates_the_two_kinds_of_family():
    """The test that decides it, asserted directly so a rebuild of
    data/crop_fao_map.json that merges or splits an item fails here by name
    rather than through a block."""
    # Both wheat ids share item 15; the fodder id maps to nothing and cannot
    # disagree.
    assert engine._one_fao_item(["bugday, durum bugdayi haric",
                                 "bugday (hasil/yesilot)"]) is True
    # Dry and fresh bean are items 176 and 423.
    assert engine._one_fao_item(["fasulye, kuru", "fasulye, taze"]) is False
    assert engine._one_fao_item([]) is True
    # Tomato is the family-name branch too, not the id-label one. Pinned because
    # a test docstring claimed the opposite and nothing failed.
    assert engine._one_fao_item(["domates (sofralik)",
                                 "domates (salcalik)"]) is True


def test_shared_item_label_asks_about_the_cell_not_the_family():
    """The companion test, and it exists because the two questions are different:
    `_one_fao_item` is about the family, this is about the one cell that
    answered."""
    peppers = ["biber (dolmalik)", "biber (salcalik, kapya)", "biber (sivri)",
               "biber (carliston)", "biber (kurutulmus)"]
    # Four of the five share item 401, so that cell has no Turkish name.
    assert engine._shared_item_label(peppers, "biber (dolmalik)") == (
        "Chillies and peppers, green (Capsicum spp. and Pimenta spp.)")
    # The fifth is alone on item 689, so its own label describes the cell.
    assert engine._shared_item_label(peppers, "biber (kurutulmus)") is None
    # No mapping at all is not a shared cell.
    assert engine._shared_item_label(["bugday (hasil/yesilot)"],
                                     "bugday (hasil/yesilot)") is None


def test_a_candidate_carrying_both_measures_beats_an_earlier_one_with_a_yield():
    """The loop stopped at the first id with `yield or price`, which is label
    order, so a family answered with a yield and no price while a sibling id
    held both. Measured 2026-10-03: 33 of the 8425 (family, country) rows that
    produce a figure are in that position.

    Algeria (area 4) and `Bakla` is one of them: `Bakla, Kuru (Yemlik)` sorts
    first and has a yield and no price, `Bakla, Taze` has both."""
    from src import norms
    dry = norms.lookup("bakla, kuru (yemlik)", None, country=4)
    fresh = norms.lookup("bakla, taze", None, country=4)
    assert dry.yield_kg_da and not dry.price_per_kg
    assert fresh.yield_kg_da and fresh.price_per_kg
    block = engine._crop_choice_block("Cezayir'deyim, bakla ekeyim mi", None,
                                      date(2026, 9, 25))
    assert "Bakla, Taze - FAOSTAT ulke ortalama verimi:" in block
    assert "Bakla, Taze - FAOSTAT ulke ortalama ciftci fiyati:" in block
    assert "Yemlik" not in block


def test_the_first_candidate_still_answers_when_none_carries_both():
    """Only the tie is broken differently. France's bean ids carry a yield and
    no price either way, so label order still decides and the old behaviour
    stands."""
    from src import norms
    assert not any(norms.lookup(cid, None, country=68).price_per_kg
                   for cid in ("fasulye, kuru", "fasulye, kuru (barbunya haric)",
                               "fasulye, taze"))
    block = engine._crop_choice_block("Fransa'dayım, fasulye ekeyim mi", None,
                                      date(2026, 9, 25))
    assert "241,36 kg/da" in block
    assert "ortalama ciftci fiyati" not in block


# --------------------------------------------------------------------------- #
# A country only replaces the province question when the user is in it
#
# THE GUARD IS A WHITELIST, so the REFUSE SET is the real measurement here: the
# admitted shapes are a closed list and the ways of naming a country without
# being in it are open-ended. Every list below is a module-level name so the
# ablation tables in src/engine.py can be re-taken from the suite rather than
# reconstructed from prose, and so the two corpus sizes those tables are
# quoted over can be pinned - see
# `test_the_corpus_the_guards_ablation_tables_are_taken_over`.
# --------------------------------------------------------------------------- #
# Merely naming a country: a buyer, a greenhouse admired, a price reference.
_MERELY_NAMING = [
    # A buyer, not a location: dative, no person on it.
    ("gecen yil Almanyaya bugday sattim, bu yil bugday mi eksem", 79),
    # A greenhouse he admires: locative carrying the relativiser -ki.
    ("Hollanda'daki gibi sera kurmak istiyorum, domates ekeyim mi", 150),
    # A price reference: bare locative modifying "fiyatları".
    ("Amerika'da buğday fiyatları nasıl, ben buğday ekeyim mi", 231),
]


@pytest.mark.parametrize("message,code", _MERELY_NAMING)
def test_merely_naming_a_country_keeps_the_province_question(message, code):
    """All three are plausibly TURKISH farmers. Measured on e021bca, each one
    was told "Kullanici Turkiye disinda", handed that country's figures, and
    lost the province question - so the assistant stopped asking the one thing
    it needs to answer at all."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "Turkiye disinda" not in block
    assert "FAOSTAT" not in block


def test_a_stated_foreign_location_still_replaces_the_question():
    """The point of the country lines, and it has to survive the guard above: a
    grower who says he is in France must not be asked which Turkish province he
    is in."""
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "BILINMIYOR" not in block
    assert "France" in block


# THE WHOLE ACCEPT SET NOW: the person suffix fused to the country's own name,
# with and without the apostrophe. Everything else the guard used to admit is in
# `_SURRENDERED_ACCEPTS` below, pinned as a cost.
_FUSED_SUFFIX_ACCEPTS = [
    "Fransa'dayım, buğday mı ekmeliyim",
    "Fransadayim, bugday mi ekmeliyim",
    # A phone's apostrophe, U+2019. `_normalize_tr` folds it to `'`, and this
    # assertion is INHERITED from the deleted shape branch, which pinned the
    # same character on "Fransa’da yaşayan bir çiftçiyim". The character's
    # behaviour is shared with the surviving branch, so the sentence was
    # rewritten rather than dropped - the mobile app is the delivery surface and
    # a reader should not have to assume this branch inherits the fold.
    "Fransa’dayım, buğday mı ekmeliyim",
]


@pytest.mark.parametrize("message", _FUSED_SUFFIX_ACCEPTS)
def test_the_fused_suffix_is_a_stated_location(message):
    """The one Turkish shape that survives, end to end. It is the only branch of
    the five that ever stood here which produced no Critical in four reviews, and
    the reason is structural: the suffix is on the NAME, so the rule reads no
    window, no verb, no clause and no conversation. There is nothing between the
    evidence and the decision for a participle to ride in on."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert "France" in block
    assert "597,35 kg/da" in block
    assert "BILINMIYOR" not in block


# THE SUFFIX'S OWN NEAR MISSES - the other way a one-decision rule can fail.
# `[dt][ae]` on the name followed by something that is NOT `-yIm`. These are the
# inputs that break the DECISION ("the person suffix, fused, on the name") as
# opposed to the inputs that merely reach it, and that distinction is the whole
# subject of this wave: four reviews found a rule licensed by a zero taken over
# inputs that could not have broken it.
_SUFFIX_NEAR_MISSES = [
    ("Fransa'daydım, şimdi döndüm", 68),      # PAST: `y` then `d`, not a vowel
    ("Fransa'dayken buğday ektim", 68),       # `while`: `y` then `k`
    ("Fransa'dalar, ben burada kaldım", 68),  # THIRD person plural: no `y`
    ("Fransa'daki gibi sera kurayım", 68),    # the relativiser: no `y`
    ("Fransa'dan fidan getirdim", 68),        # ablative: not a locative
]


# THE NAME'S RIGHT BOUNDARY - the THIRD way `_SELF_TR`'s one decision can fail,
# and the refuse set could not reach it until these four were written. `(?<!\w)`
# anchors the LEFT side of the alias; nothing anchors the right side of the NAME,
# so a token that merely STARTS with an alias and runs on into the locative
# letters would be read as that country. Measured over the 95 that shipped: 0 of
# them are of this shape, so the branch's 0/95 said nothing at all about its
# right boundary - the fifth instance of this guard's standing defect, found by
# asking what the zero could have failed on.
#
# The decision is SOUND, and that was measured independently before these were
# written: the project's own Turkish corpus (data/vector_store/chroma.sqlite3,
# 81 426 documents) matches this pattern in 0 documents under all 418 folded
# aliases, and of the tokens that end in the locative-plus-person letters not one
# has a country alias as its prefix. What was missing was the evidence, which is
# what these four are.
_NAME_BOUNDARY_REFUSALS = [
    # A DISTRICT OF AYDIN. `çin` is China's alias and `Çine` is a Turkish town,
    # so this is a Turkish grower who would have been placed in China - the
    # dearest sentence of the four, and `extract_country` refuses it too.
    ("Çine'deyim, buğday mı ekmeliyim", 41),
    # NIGERIA, SCORED AGAINST NIGER'S ALIASES. `nijer` is a strict prefix of
    # `nijerya`, so an unanchored name would place a Nigerian grower in Niger.
    ("Nijerya'dayım, mısır ekeyim mi", 158),
    # The Treasury, not Mali: `mali` + `yedeyim`.
    ("Maliyedeyim, bu yıl ne eksem", 133),
    # A tent, not Chad: `çad` + `ırdayım`.
    ("Çadırdayım, sabah tarlaya inerim", 39),
]


@pytest.mark.parametrize("text,code", _NAME_BOUNDARY_REFUSALS)
def test_the_name_has_a_right_boundary_too(text, code):
    """Each of these hands the guard the aliases of a country whose name is a
    strict PREFIX of a word in the sentence, and the word ends in the locative's
    own letters plus the person - so a rule that anchored the left side of the
    name and then scanned to the end of the token would admit all four.

    "Çine'deyim" is the one that matters: `Çine` is a district of Aydın and
    `çin` is China, so the sentence is a Turkish grower who would have been told
    "Kullanici Turkiye disinda: China" and asked no province. The other three
    say the same thing about Nigeria against Niger's aliases, the Treasury
    against Mali's, and a tent against Chad's."""
    assert not engine._states_location(text, engine._code_aliases(code))


_NATIONALITY_REFUSALS = [
    ("Hollandalıyım, buğday mı ekmeliyim", 150),
    ("Fransalıyım", 68),
    ("Fransalıyım, buğday mı ekmeliyim", 68),
    ("hollandaliyim, bugday mi ekmeliyim", 150),
]


@pytest.mark.parametrize("text,code", _NATIONALITY_REFUSALS)
def test_a_nationality_is_not_a_location(text, code):
    """`-lI` ON THE NAME SAYS WHERE THE SPEAKER IS FROM, NOT WHERE HE IS.
    "Hollandalıyım" is "I am Dutch", and a Dutch grower farming in Antalya says
    it truthfully while standing in Türkiye - so admitting it printed the
    Netherlands' average yield beside "hangi ilde oldugunu SORMA" for a grower
    whose province we should have asked for.

    IT WAS ADMITTED FOR FOUR WAVES AND DECLARED, NEVER DECIDED: the comment
    above `_SELF_TR` called it "weaker evidence of presence" in every revision.
    A nationality is an inference about location, and this branch's last wave
    took the inference out; this is the same decision applied to the arm that
    survived it by being described rather than measured.

    THE COST IS ONE TURN, the same trade as the deleted bare-name branch:
    "Fransalıyım" gets `_ASK_LOCATION` back, which asks for "Fransa'dayım" in
    exactly that spelling, and the next turn is placed. `extract_country` still
    RESOLVES these sentences - see tests/test_country.py - because resolving a
    name and placing a speaker are different questions, and only the second one
    is this guard's."""
    assert not engine._states_location(text, engine._code_aliases(code))


@pytest.mark.parametrize("text,code", _SUFFIX_NEAR_MISSES)
def test_the_fused_suffix_is_the_whole_decision(text, code):
    """Five endings that share the locative's letters and are not a first-person
    copula on them. The past tense is the one that matters most - "Fransa'daydım"
    is "I WAS in France", the class four waves of tense rules existed for, and
    here it is refused by the same four characters that admit "Fransa'dayım"."""
    assert not engine._states_location(text, engine._code_aliases(code))


_POSSESSION_NEAR_MISSES = [
    # `<possessed noun> var` is also how a relative or a contact abroad is
    # mentioned, which is the class K2 lives in. These six are the ones whose
    # possessed noun is a PERSON; "Fransa'da bir dayım var" lives in
    # _WINDOW_PERSON_NEAR_MISSES instead, because it is the one sentence of this
    # shape that leaked through the WINDOW at 78b72a2.
    #
    # AND THE REACH COUNT THE DELETED LAND BRANCH QUOTED WAS BOTH WRONG AND
    # BESIDE THE POINT, which is worth keeping because it is this wave's whole
    # lesson in one number. The comment said "16 of the 86 refusals reach this
    # branch's shape". Re-measured: 16 under its own wording (a possessed noun
    # in `-Im`, then `var`) and 18 under the looser reading its prose also
    # suggested, since `tarlasi` and `fiyatlari` are possessed too. Neither
    # number mattered. The branch's real decision was to read the WHOLE CLAUSE
    # with no adjacency, and ZERO of the 86 put a whitelisted LAND noun behind
    # an object locative - so the only input that could have failed it was
    # absent, and twelve such sentences were admitted in production.
    ("Fransa'da bir arkadaşım var", 68),
    ("Fransa'da müşterim var", 68),
    ("Fransa'da bir tanıdığım var", 68),
    ("Hollanda'da bir ortağım var", 150),
    # A THIRD PERSON'S land: `tarlasi`, not `tarlam`.
    ("Fransa'da dayımın tarlası var", 68),
    # Not possessed at all.
    ("Fransa'da tarla fiyatları var", 68),
]


@pytest.mark.parametrize("text,code", _POSSESSION_NEAR_MISSES)
def test_possessing_something_that_is_not_land_is_not_a_location(text, code):
    """`<possessed noun> var` is how a relative or a contact abroad is mentioned,
    and for three waves this was the shape a rule tried to tell from owned land
    by whitelisting the NOUN. The land branch is deleted - its own
    whole-clause read handed back twelve object-locative sentences, licensed by
    a zero that 0 of the 86 refusals could break - so these six are now refused
    for the same reason "Fransa'da tarlam var" is: `var` is not a person suffix
    on the name. Kept, because the class is the dearest one on this path and the
    next wave to propose a land branch should find its near misses already
    written down."""
    assert not engine._states_location(text, engine._code_aliases(code))


_SUPPOSED_MOOD_REFUSALS = [
    # The two the sixth review pinned, and the only two the word `if` could see.
    ("If I am in France next year, should I plant wheat", 68),
    ("if i'm in France the prices are different", 68),
    # FOUR MORE SPELLINGS OF THE SAME MOOD, every one of them admitted while the
    # decision was keyed on the literal `if\s`. The seventh review measured all
    # four placing the speaker abroad, suppressing the province question and
    # sticking for the conversation.
    ("suppose I am in France - what do I plant", 68),
    ("supposing I am in France", 68),
    ("assuming I am in France next year, what should I plant", 68),
    ("in case I am in France next spring, which wheat", 68),
    # `unless` was named in the comment and "left out for want of a sentence
    # anyone would write"; `whether` is the indirect question and was not named
    # at all. Both are the same mood and both cost nothing.
    ("unless I am in France I plant wheat", 68),
    ("nobody knows whether I am in France", 68),
    # AND THE TWO THE WIDTH OF THE OLD LOOKBEHIND LET THROUGH. `(?<!if\s)` is
    # exactly one whitespace wide and `_normalize_tr` does not collapse runs, so
    # the mood survived a second space or a comma. No width is fixed now.
    ("if  I am in France next year", 68),
    ("if, I am in France", 68),
]


@pytest.mark.parametrize("text,code", _SUPPOSED_MOOD_REFUSALS)
def test_a_supposed_location_is_not_a_location(text, code):
    """A COMMENT'S CLAIM MEASURED AND FOUND FALSE TWICE, in opposite directions.

    The fifth wave declared "If I am in France next year" an accept because
    refusing it "means reading the tail" - untrue, `if` stands immediately LEFT
    of the subject. The sixth wave refused it with `(?<!if\\s)` and wrote that
    the line was "the mood rather than the length of the word" - also untrue,
    because a fixed-width lookbehind can only read ONE spelling at ONE width.
    `suppose`, `supposing`, `assuming`, `in case`, `unless`, `whether` and `if`
    with two spaces after it were all admitted, placed abroad and told not to
    ask the province.

    IT IS THE MOOD NOW, read as a TOKEN. `_EN_NOT_THE_SPEAKER` matches the one
    token touching the subject with its width free, so the spelling and the
    spacing are both out of the decision. 0 accepts lost, 0 refusals leaked.

    `when` AND `whenever` STAY ADMITTED, in `_DECLARED_ENGLISH_ACCEPTS`: they are
    temporal and say the speaker does go there, where the eight above suppose a
    country he is not in."""
    assert not engine._states_location(text, engine._code_aliases(code))


_ATTRIBUTED_SUBJECT_REFUSALS = [
    # A PRONOUN CANNOT BE POSSESSED, BUT IT CAN BE ATTRIBUTED, and that is the
    # other half of the class the pronoun rule was justified by. The `i` in each
    # of these is somebody else's, so the whitelisted subject is not the writer.
    ("he says I am in France", 68),
    ('he said "I am in France" in his email', 68),
    ("my supplier wrote: I am in France, send the order", 68),
    ("the buyer replied I am in France this week", 68),
    ("the seller claims we are in France", 68),
    ("the form says I live in France", 68),
    # Not reported speech at all, and the same shape: the quoted string is the
    # object of a request, not a statement about the writer.
    ('translate "I am in France" into Turkish', 68),
    # The sixth review's own Critical sentence with an attribution instead of a
    # genitive: the writer says where his field is IN THE SAME SENTENCE and was
    # placed in the Netherlands with "hangi ilde oldugunu SORMA" beside it.
    ('he said "I am in the Netherlands", my field is in Antalya', 150),
]


@pytest.mark.parametrize("text,code", _ATTRIBUTED_SUBJECT_REFUSALS)
def test_an_attributed_first_person_is_not_the_writer(text, code):
    """THE SEVENTH REVIEW'S IMPORTANT 1, and it is about a sentence in a comment
    as much as about these eight.

    The pronoun rule was carried by "A PRONOUN SUBJECT CANNOT BE THE TAIL OF
    ANOTHER SUBJECT - `my farm` can be possessed by a larger phrase; `i` cannot
    be possessed by anything". That is true about POSSESSION and the conclusion
    drawn from it - "so a whitelisted subject is always the writer" - is false:
    reported speech puts somebody else's `i` in the subject slot without
    possessing anything. All eight were admitted, and 0 of the refuse set
    carried an attributing verb at all, so nothing in the suite could see it.

    THE DECISION IS THE SAME ONE TOKEN as the mood: an attributing verb touching
    the subject, through any run of space, a colon or a quote. Measured at 0
    accepts lost and 0 refusals leaked.

    WHAT IT DOES NOT CLOSE, written down rather than implied: the verb must
    TOUCH the subject. "the buyer said nothing, I am in France" is admitted and
    pinned in `_LEFT_CONTEXT_ACCEPTS`, and an attribution further off - "he told
    me that, in his email, I am in France" - is not read. Reading further is
    reading the clause, which is the inference six waves deleted."""
    assert not engine._states_location(text, engine._code_aliases(code))


def test_the_veto_reads_the_left_of_the_match_and_not_of_the_sentence():
    """ONE SENTENCE, TWO COUNTRIES, TWO ANSWERS - which is the whole reason
    `_guard_hits` walks every match instead of asking `re.search` once.

    "he said i am in Germany, but i am in France" attributes the German clause
    and states the French one. A veto applied to the sentence would refuse both
    and lose a real self-declaration; a veto applied to the FIRST match only
    would refuse Germany and never look again."""
    text = "he said I am in Germany, but I am in France"
    assert not engine._states_location(text, engine._code_aliases(79))
    assert engine._states_location(text, engine._code_aliases(68))


_POSSESSED_SUBJECT_COSTS = [
    ("my farm is in France", 68),
    ("my field is in France", 68),
]


@pytest.mark.parametrize("text,code", _POSSESSED_SUBJECT_COSTS)
def test_the_price_of_requiring_a_pronoun_subject(text, code):
    """PINNED AS A COST. Both say where the speaker's own land is, which is
    exactly what this guard wants to know, and both are refused now.

    THE REASON WRITTEN HERE USED TO BE "nothing tells them apart from
    `_POSSESSED_SUBJECT_LEAKS` below without parsing the clause", AND THAT IS
    MEASURABLY FALSE - by the same argument that overturned the `if` claim one
    paragraph later. A CONSUMED clause-start alternative is not a lookbehind, so
    its width is free:

      (?:^|(?<=[.,;!?]\\s))(?:my\\s+farm\\s+is|our\\s+farm\\s+is
                            |my\\s+field\\s+is|my\\s+fields\\s+are)\\s+(?:in|at)\\s+

    Measured at the seventh review and re-measured here beside the left veto:
    both of these recovered, 0 of the 58 refusals leaked, 0 of the 5
    `_POSSESSED_SUBJECT_LEAKS` admitted, and the fresh attribution leak the
    seventh review warned the anchor would open - "Ahmet said, my farm is in
    France", "he wrote: my farm is in France" - is refused, because
    `_EN_NOT_THE_SPEAKER` reads that token too.

    SO THE REAL REASON THEY ARE STILL REFUSED IS THE ORDER OF THE WAVES, not the
    parse: this wave NARROWED the English arm twice, and widening it in the same
    wave is the mistake this branch made three times. The anchor is measured,
    written down, and left for the next round. What the cost is in the meantime:
    the speaker writes "I am in France" and is placed."""
    assert not engine._states_location(text, engine._code_aliases(code))


_POSSESSED_SUBJECT_LEAKS = [
    # Each one is a pinned refusal of this suite's with one genitive added, and
    # each was ADMITTED until the subject rule required a pronoun. Measured at
    # the sixth review.
    ("the supplier of my farm is in France", 68),      # cf. "my supplier is in France"
    ("the buyer of my field is in France", 68),        # cf. "my buyer is in France"
    ("the owner of my farm is in France", 68),         # cf. "the farm is in France"
    ("the man who rents my farm is in France", 68),
    ("the company that owns my farm is in the Netherlands, my field is in Antalya", 150),
]


@pytest.mark.parametrize("text,code", _POSSESSED_SUBJECT_LEAKS)
def test_a_possessed_subject_inside_a_larger_phrase_is_not_the_speaker(text, code):
    """THE SIXTH REVIEW'S CRITICAL, and the reason the subject list is pronouns.

    The last sentence is the one that decided it: the speaker says his field is
    in Antalya in the same breath, and the guard placed him in the Netherlands
    and printed "hangi ilde oldugunu SORMA" - the same harm the previous commit
    deleted `from` to stop, through a different door, and sticky for the whole
    conversation because `_country_lines` asks every user turn.

    Six waves closed the sentences they had thought of. This one closes the part
    of speech."""
    assert not engine._states_location(text, engine._code_aliases(code))


_DECLARED_ENGLISH_ACCEPTS = [
    # THE FUTURE, and the temporal `when`/`whenever`. The future has a refused
    # Turkish twin and that asymmetry is not repaired: refusing `tomorrow` means
    # reading the tail, which is the inference this branch deleted. The two
    # temporals are a decision and not a miss - they say the speaker does go to
    # France, where the eight in `_SUPPOSED_MOOD_REFUSALS` suppose a France he is
    # not in. They are the only inputs that can break the MOOD decision in the
    # admitting direction, which is why `whenever` is here rather than assumed.
    ("I am in India tomorrow", 100),
    ("When I am in France I plant wheat", 68),
    ("whenever I am in France I plant wheat", 68),
    # A COUNTRY'S NAME AS THE FIRST WORD OF A LONGER FOREIGN PLACE NAME, two US
    # towns named after countries. The level below the `Georgia` decision in
    # `country._NOT_THIS_PLACE`, and admitted for the same reason as the two
    # above: refusing them means reading the tail.
    # REWRITTEN WITH A PRONOUN SUBJECT after the possessed-noun subjects were
    # dropped: with "my farm is" these two were refused by the subject rule and
    # stopped measuring the tail decision they are here for.
    ("I am in Lebanon, Ohio", 121),
    ("we are in Peru, Indiana", 170),
]

# THE INPUTS THAT CAN BREAK THE LEFT-VETO DECISION IN THE ADMITTING DIRECTION,
# and the set had NONE until this wave: every one of the twelve accepts began at
# the start of the message, so there was nothing to the left of the subject at
# all and a veto that refused on ANY left context would have measured 0 cost.
# That is the vacuous zero this branch has shipped five Criticals on, so the
# three below put a token there on purpose.
_LEFT_CONTEXT_ACCEPTS = [
    # A word touching the subject that is neither a mood nor an attribution.
    ("actually I am in France", 68),
    # AN ATTRIBUTING VERB IN THE SENTENCE BUT NOT TOUCHING THE SUBJECT, which is
    # the minimal pair for "the buyer said I am in France" in
    # `_ATTRIBUTED_SUBJECT_REFUSALS`: the two differ in the one token the
    # decision reads and in nothing else.
    ("the buyer said nothing, I am in France", 68),
    # The same pair for the mood: `when` is temporal and a whole clause stands
    # between it and the subject, so neither half of the veto can reach.
    ("when the fair opens, I am in France", 68),
]

_ENGLISH_ACCEPTS = [
    ("I live in France", 68),
    ("I am in France", 68),
    ("I farm in France", 68),
    ("we are based in France", 68),
    # TEMPORARY PRESENCE, and it is pinned as an ACCEPT on purpose rather than
    # left out as the gap a previous review called it. See _SELF_EN: the Turkish
    # twin "Fransa'dayım, fuara geldim" is admitted and cannot be refused
    # without reading the rest of the sentence, which is the inference this wave
    # deleted - and a grower who IS in France this week is in France.
    ("I am in France for the fair", 68),
    ("I am in France this week", 68),
    ("we are in France visiting a supplier", 68),
    ("I'm in France on holiday", 68),
] + _DECLARED_ENGLISH_ACCEPTS + _LEFT_CONTEXT_ACCEPTS


@pytest.mark.parametrize("text,code", _ENGLISH_ACCEPTS)
def test_the_english_branch_admits_a_self_declaration(text, code):
    """Asserted on `_states_location` rather than through a block: the crop
    lexicon is Turkish, so "should I plant wheat" names no crop and the block
    would have nothing to print for a reason that has nothing to do with this
    guard."""
    assert engine._states_location(text, engine._code_aliases(code))


@pytest.mark.parametrize("text,code", _LEFT_CONTEXT_ACCEPTS)
def test_the_left_veto_reads_one_token_and_not_the_clause(text, code):
    """THE COST SIDE OF THE MOOD AND ATTRIBUTION DECISIONS, and it had no inputs
    before this wave: all twelve accepts started at character 0, so there was
    nothing to the left of the subject and any veto at all measured free.

    Each of these is the minimal pair of a refusal: "the buyer said nothing, I am
    in France" against "the buyer said I am in France", "when the fair opens, I
    am in France" against "if I am in France". The decision reads the ONE token
    touching the subject - a mood word or an attributing verb, through a run of
    space, a comma, a colon or a quote - and nothing further.

    Reading further would be reading the clause, which is the inference that
    produced four Criticals on this branch. So the admitted half is a declared
    limit: an attribution separated from the subject by a clause is not seen."""
    assert engine._states_location(text, engine._code_aliases(code))


@pytest.mark.parametrize("text,code", _DECLARED_ENGLISH_ACCEPTS)
def test_the_conditional_the_future_and_a_longer_place_name_are_declared_accepts(
        text, code):
    """FIVE ADMISSIONS THAT ARE A DECISION, NOT AN OVERSIGHT, and they are
    admitted for two different reasons that an earlier revision of this docstring
    ran together.

    THE FUTURE AND THE LONGER PLACE NAME need the TAIL of the sentence, and the
    tail was measured and rejected on this branch: `tomorrow` and `, Ohio` are
    the tail outright. The wave before last measured every candidate tail word as
    damaging - `and`, the comma and the full stop included - because "my field is
    in Egypt for..." and "the protein in turkey for..." have the same tail. A
    tail rule here is the inference that produced four Criticals, re-entering by
    a side door.

    `when` AND `whenever` NEED NOTHING, and that is the correction. The earlier
    claim that "`if`/`when`/`unless` do not fit in a fixed-width lookbehind" was
    false twice over: the first wave to test it refused `if` with a lookbehind,
    and the seventh replaced the lookbehind with a token read, so every spelling
    of the mood now fits. These two are admitted because they MEAN something
    else - temporal, the speaker does go there - not because they cannot be
    reached. They are the only two accepts that can break the mood decision in
    the admitting direction, which is why `whenever` is pinned beside `when`.

    THE CONDITIONAL IS NO LONGER HERE. It was in this list for one wave, on the
    argument that "a grower asking 'If I am in France next year' IS THINKING
    ABOUT FRANCE and FAOSTAT's French figures are the right context". That
    argument lost: he is thinking about France and he is NOT IN IT, so the block
    tells him not to say which province he is in, and `_country_lines` asks every
    user turn, so it sticks. See `_SUPPOSED_MOOD_REFUSALS`.

    THE TURKISH TWINS OF THE MOOD ARE REFUSED AND THAT ASYMMETRY IS NOW THE OTHER
    WAY ROUND. "Fransa'daysam ne ekerim" and "Fransa'da olsaydım buğday ekerdim"
    cost nothing to refuse because `'daysam` does not fill `[dt][ae]y[iu][mz]`,
    and English now refuses its twins too, so the two branches AGREE about a
    speaker who supposes a country. Where they still differ is attribution:
    Turkish is verb-final, so "Fransa'dayım dedi" puts the attributing verb to
    the RIGHT of the match where a left veto cannot see it. Recorded, not
    repaired - repairing it means reading the Turkish clause."""
    assert engine._states_location(text, engine._code_aliases(code))
    assert not engine._states_location("Fransa'daysam ne ekerim",
                                       engine._code_aliases(68))
    assert not engine._states_location("Fransa'da olsaydım buğday ekerdim",
                                       engine._code_aliases(68))


# THE ENGLISH BRANCH IS ONE OF TWO SURVIVORS, so its refuse set is measured the
# way the Turkish side's is - with the number of inputs that could break each
# DECISION beside the zero, not the number that reach the branch. THERE ARE THREE
# DECISIONS AND NOT TWO:
#
#   refusals                                                          35
#   admitted                                                           0
#   naming a country extract_country resolves (the rest test nothing) 31
#   any subject, then `in`/`at`, then the NAME, so able to break the
#     PERSON decision                                                 13
#   a first-person subject in the sentence and a bare `in`/`at` in
#     front of the NAME, so able to break the ADJACENCY decision        5
#   a whitelisted subject, then `from`, then the NAME, so able to
#     break the PREPOSITION decision                                  10
#
# Class (e) is the class that makes the 13 possible: before it, three sentences
# carried the whole person decision. Class (f) is the same thing for the
# preposition decision, which had NO refusal able to break it while `from` was
# admitted - that is what shipped the Critical this wave closes.

# (f) AN ORIGIN, NOT A LOCATION. `from` after a whitelisted subject was admitted
# until this wave, licensed by a zero no refusal could break - and the first of
# these is the sentence that settled it: the user says his farm is in Antalya and
# was placed in the Netherlands with "hangi ilde oldugunu SORMA" beside it. All
# ten resolve a country, so none is refused by country.py first, and all ten
# carry a FIRST-PERSON subject, so the only decision they can break is the
# preposition one.
_ENGLISH_ORIGIN_REFUSALS = [
    ("I am from the Netherlands, my farm is in Antalya", 150),
    ("We are from India but we farm in Konya", 100),
    ("I live in Antalya but I am from the Netherlands", 150),
    ("we are from the Netherlands, our greenhouse is in Antalya", 150),
    ("I am from Kenya", 114),
    ("I'm from Kenya", 114),
    ("we are from France", 68),
    ("we're from Egypt", 59),
    ("I am from Brazil", 21),
    ("I am from the Netherlands", 150),
]
_ENGLISH_NOT_A_LOCATION = [
    # (a) merely naming
    ("the yield in France is high", 68),
    ("wheat prices in France are up", 68),
    ("I buy seed from France", 68),
    ("we import fertiliser from Germany", 79),
    ("the protein in turkey feed", 223),
    ("I saw a greenhouse in the Netherlands", 150),
    ("the seed is produced in France", 68),
    # (b) somebody ELSE's place - the possessive is what _SELF_EN reads, so
    # these are the sentences that say what it must not admit
    ("my supplier is in France", 68),
    ("my uncle lives in France", 68),
    ("a friend farms in France", 68),
    # (c) a finished action
    ("I studied in France", 68),
    ("I went to a fair in the Netherlands", 150),
    # (d) a market, which is the English twin of the twenty in
    # `_ACTION_LOCATIVES`
    ("I sell wheat in Germany", 79),
    ("I am looking for a buyer in Germany", 79),
    ("we export tomatoes to the Netherlands", 150),
    # (e) A SUBJECT THAT IS NOT THE SPEAKER, in this branch's own frame. Ten
    # sentences that differ from "my farm is in France" in the subject alone, so
    # they are the only inputs that can fail the person decision - the
    # equivalent of what `_WINDOW_PERSON_NEAR_MISSES` is for the Turkish side.
    # All ten resolve France, so none of them is refused by country.py first.
    ("he is in France", 68),
    ("she lives in France", 68),
    ("my son is in France", 68),
    ("our customer is in France", 68),
    ("my buyer is in France", 68),
    ("the farm is in France", 68),
    ("his farm is in France", 68),
    ("their field is in France", 68),
    ("my brother farms in France", 68),
    ("the company is based in France", 68),
] + (_ENGLISH_ORIGIN_REFUSALS + _POSSESSED_SUBJECT_LEAKS
     + _SUPPOSED_MOOD_REFUSALS + _ATTRIBUTED_SUBJECT_REFUSALS)


@pytest.mark.parametrize("text,code", _ENGLISH_ORIGIN_REFUSALS)
def test_an_english_origin_is_not_a_location(text, code):
    """`from` STATES AN ORIGIN AND AN ORIGIN IS NOT A LOCATION - the English twin
    of `test_a_nationality_is_not_a_location`, decided on the same rule two
    commits later.

    "I am from Kenya" was `_SELF_EN`'s own written justification for admitting
    `from` beside `in`/`at`, and it is the translation of "Hollandalıyım": a
    grower says it truthfully while standing somewhere else, so placing him on it
    is an INFERENCE. The sentence that settled it is the first one here - the
    user writes that his farm is in Antalya IN THE SAME SENTENCE and was still
    placed in the Netherlands, with "hangi ilde oldugunu SORMA" printed beside
    the Dutch average, for the whole conversation.

    IT SURVIVED THE `-lI` DECISION BY ONE COMMIT BECAUSE ITS ZERO WAS VACUOUS: 0
    of the 25 refusals put a whitelisted subject immediately before `from`, and
    the two that carried the word `from` at all - "I buy seed from France", "we
    import fertiliser from Germany" - are refused by the SUBJECT decision, so
    nothing in the set could fail the preposition decision. These ten are that
    set, and the count beside the preposition decision is now 10 rather than 0.

    `extract_country` still RESOLVES all ten. Resolving a name and placing a
    speaker are different questions; see tests/test_country.py."""
    assert not engine._states_location(text, engine._code_aliases(code))


@pytest.mark.parametrize("text,code", _ENGLISH_NOT_A_LOCATION)
def test_the_english_branch_refuses_what_is_not_a_self_declaration(text, code):
    """`_SELF_EN` admits 0 of these twenty-five. Class (b) and class (e) are the
    person decision: the possessive licences the SPEAKER'S own holding and
    nothing else, so a supplier, an uncle, a friend, a son, a customer, a buyer,
    a brother, a company and two third-person pronouns all stay out, and so does
    "the farm is in France" with no possessive at all.

    Class (e) exists because this branch is now one of two, and three sentences
    were not a serious refuse set for a rule carrying half the guard."""
    assert not engine._states_location(text, engine._code_aliases(code))


def test_the_english_refuse_sets_reach_counts_are_what_they_claim():
    """THE NUMBERS BESIDE _SELF_EN'S ZERO, pinned so they cannot go stale - this
    branch has had five stale or vacuous denominators written above it.

    A reach count is only a guarantee when it counts the inputs that could break
    THE DECISION UNDER TEST. THIS BRANCH MAKES THREE DECISIONS, not two: the
    subject must be first-person, the preposition must stand between that subject
    and the name, and the preposition must be one that means PRESENCE. The third
    had no count at all while `from` was admitted, and that is how an origin
    arm survived the `-lı` decision by a commit.

    EACH COUNT IS ANCHORED ON THE NAME, and that is a correction rather than a
    restatement. The old person count matched `<subject> ... in <anything>` and
    the old adjacency count was "a first-person word somewhere AND a preposition
    somewhere": over this set the first returns 39 and the second 27, because
    nine of the ten origin refusals carry a second clause with a Turkish PROVINCE
    in it - "my farm is in Antalya" satisfies both and tests neither. (And the
    genuinely old person count is 43, not 39: before `c218ae0` the branch
    admitted `from`, so the loose wording reached over `(in|at|from)`. Two
    reviews printed that number measured with the NEW preposition set, which is
    neither the old rule nor anything shipped; the argument it serves - that the
    loose wordings inflate and test nothing - is stronger at 43.) A count that
    cannot fail is the defect this guard has been reviewed for six times, so each
    count here asks what a rule with ONE decision relaxed would admit:

      PERSON      - any subject in the frame, then `in`/`at`, then the name.
      ADJACENCY   - a first-person subject anywhere, and a BARE `in`/`at`
                    immediately before the name. That is country.py's own looser
                    rule, which is what this branch is narrower than.
      PREPOSITION - the REAL subject whitelist, then `from`, then the name.
      MOOD AND ATTRIBUTION - the shipped pattern matches and a vetoing token
                    TOUCHES it, which is what a rule without
                    `_EN_NOT_THE_SPEAKER` would admit. This is the fourth
                    decision and it had no count at all until the seventh review.

    THE SUBJECT LIST AND THE PREPOSITION SET ARE BOTH READ OUT OF `engine`, not
    copied: `engine._EN_SUBJECT` for the subject and `engine._EN_PREP` for the
    preposition. Two of these counts used to spell `(?:in|at)` inline, so
    widening the shipped set would have left them measuring the old rule while
    staying green - the sixth review's Important, taken here.

    THE PERSON COUNT MOVED 13 -> 19 -> 35, AND THE PARTITION IS THE POINT. A
    count can be neither stale nor vacuous and still lie by being partitioned
    wrongly, which is the sixth review's Critical written as a number and the
    third way a reach count fails. The 35 splits by the sub-decision each
    refusal can break:

      13  (a) a THIRD PARTY in the subject slot          - the original 13
       5  (b) a first-person possessive inside a LARGER subject  - review 6
       8  (c) an ATTRIBUTED `i`, somebody else's         - review 7
       9  (d) a SUPPOSED mood                            - review 7

    13 + 5 + 8 + 9 = 35, exactly. Cells (c) and (d) were EMPTY at `4a1af74` -
    (c) entirely, and (d) held the single `if` sentence the code happened to
    read - and both had measured live admissions, which is what made the seventh
    review's Critical the seventh instance of one family.

    THE ADJACENCY COUNT PARTITIONS THE SAME WAY and the reader should know it is
    inflated by the new classes: 23 = 5 (a) + 0 (b) + 8 (c) + 10 (d). The 5 is
    the number that measures the adjacency decision on its own; the 18 are
    refused by the veto and would be admitted by a rule that relaxed adjacency
    alone, so they belong in the count by its own definition while saying
    nothing about adjacency. That overlap is why the fourth count exists."""
    from src.context import country as country_ctx
    any_subject = (r"(?<!\w)\w+(?:\s+\w+)?\s+"
                   r"(?:is|are|am|'m|live|lives|farm|farms)"
                   r"(?:\s+based)?\s+" + engine._EN_PREP + r"\s+")
    bare_prep = r"(?<!\w)" + engine._EN_PREP + r"\s+"
    origin = engine._EN_SUBJECT + r"from\s+"
    first_person = re.compile(r"(?<!\w)(?:i|we)(?:\s|')")
    veto = re.compile(engine._EN_NOT_THE_SPEAKER)

    def before_the_name(prefix, text, code):
        folded = engine._normalize_tr(text)
        return any(re.search(rf"{prefix}{re.escape(name)}(?!\w)", folded)
                   for name in engine._code_aliases(code))

    def vetoed(text, code):
        """Whether the shipped pattern matches and the veto is what refuses it."""
        folded = engine._normalize_tr(text)
        return any(
            veto.search(folded[:match.start()])
            for name in engine._code_aliases(code)
            for match in re.finditer(
                engine._guard_regex("prefix", engine._SELF_EN,
                                    re.escape(name)), folded))

    assert len(_ENGLISH_NOT_A_LOCATION) == 58
    assert sum(1 for text, _code in _ENGLISH_NOT_A_LOCATION
               if country_ctx.extract_country(text, None) is not None) == 54
    assert sum(1 for text, code in _ENGLISH_NOT_A_LOCATION
               if before_the_name(any_subject, text, code)) == 35
    assert sum(1 for text, code in _ENGLISH_NOT_A_LOCATION
               if first_person.search(engine._normalize_tr(text))
               and before_the_name(bare_prep, text, code)) == 23
    assert sum(1 for text, code in _ENGLISH_NOT_A_LOCATION
               if before_the_name(origin, text, code)) == 10
    assert sum(1 for text, code in _ENGLISH_NOT_A_LOCATION
               if vetoed(text, code)) == 18
    # The partition of the person count, asserted rather than described: a count
    # that is right in total and wrong in its cells is invisible otherwise.
    third_party = [pair for pair in _ENGLISH_NOT_A_LOCATION
                   if pair not in _POSSESSED_SUBJECT_LEAKS
                   and pair not in _SUPPOSED_MOOD_REFUSALS
                   and pair not in _ATTRIBUTED_SUBJECT_REFUSALS]
    cells = [sum(1 for text, code in cell
                 if before_the_name(any_subject, text, code))
             for cell in (third_party, _POSSESSED_SUBJECT_LEAKS,
                          _ATTRIBUTED_SUBJECT_REFUSALS,
                          _SUPPOSED_MOOD_REFUSALS)]
    assert cells == [13, 5, 8, 9]
    assert sum(cells) == 35
    # The adjacency count's partition, for the same reason: 5 of the 23 measure
    # adjacency and the other 18 are the two new classes.
    adjacent = [sum(1 for text, code in cell
                    if first_person.search(engine._normalize_tr(text))
                    and before_the_name(bare_prep, text, code))
                for cell in (third_party, _POSSESSED_SUBJECT_LEAKS,
                             _ATTRIBUTED_SUBJECT_REFUSALS,
                             _SUPPOSED_MOOD_REFUSALS)]
    assert adjacent == [5, 0, 8, 10]
    # And each new class's count was ZERO on the set that shipped the finding it
    # closes. The old twenty-five could not break the preposition decision; the
    # forty-two could not break the mood decision except through the one
    # spelling the code read, and could not break the attribution one at all.
    old = [pair for pair in _ENGLISH_NOT_A_LOCATION
           if pair not in _ENGLISH_ORIGIN_REFUSALS
           and pair not in _POSSESSED_SUBJECT_LEAKS
           and pair not in _SUPPOSED_MOOD_REFUSALS
           and pair not in _ATTRIBUTED_SUBJECT_REFUSALS]
    assert len(old) == 25
    assert sum(1 for text, code in old
               if before_the_name(origin, text, code)) == 0
    forty_two = (old + _ENGLISH_ORIGIN_REFUSALS + _POSSESSED_SUBJECT_LEAKS
                 + _SUPPOSED_MOOD_REFUSALS[:2])
    assert len(forty_two) == 42
    assert sum(1 for text, code in forty_two if vetoed(text, code)) == 2
    # And 0 of those 42 carried an attributing verb ANYWHERE in the sentence,
    # not merely 0 in the subject slot - so no reading of them, strict or loose,
    # could have broken the attribution decision.
    attributing = re.compile(r"(?<!\w)(?:" + engine._ATTRIBUTING_VERB
                             + r")(?!\w)")
    assert sum(1 for text, _code in forty_two
               if attributing.search(engine._normalize_tr(text))) == 0
    assert sum(1 for text, _code in _ENGLISH_NOT_A_LOCATION
               if attributing.search(engine._normalize_tr(text))) == 8
    # THE LOOSE WORDINGS, derived here rather than quoted: two reviews in a row
    # found this number stale, and the second time it had been "fixed" by
    # re-measuring the OLD frame with the NEW preposition set, which is neither
    # rule. All three are asserted over both sets.
    loose_person = (r"(?<!\w)\w+(?:\s+\w+)?\s+"
                    r"(?:is|are|am|'m|live|lives|farm|farms)"
                    r"(?:\s+based)?\s+")
    loose_in_at = re.compile(loose_person + r"(?:in|at)\s+")
    loose_with_from = re.compile(loose_person + r"(?:in|at|from)\s+")
    loose_adjacency = re.compile(r"(?<!\w)(?:in|at)\s+")

    def loose(pattern, pairs):
        return sum(1 for text, _code in pairs
                   if pattern.search(engine._normalize_tr(text)))

    assert loose(loose_in_at, _ENGLISH_NOT_A_LOCATION) == 39
    assert loose(loose_with_from, _ENGLISH_NOT_A_LOCATION) == 43
    assert loose(loose_in_at, old) == 13
    assert loose(loose_with_from, old) == 13
    assert sum(1 for text, _code in _ENGLISH_NOT_A_LOCATION
               if first_person.search(engine._normalize_tr(text))
               and loose_adjacency.search(engine._normalize_tr(text))) == 27
    assert sum(1 for text, _code in old
               if first_person.search(engine._normalize_tr(text))
               and loose_adjacency.search(engine._normalize_tr(text))) == 5
    # The cost side of the veto had ONE input that could break it, and the one it
    # had is the `when` sentence. Now it has five: an accept can only break this
    # decision by having something to the LEFT of the subject at all.
    def has_left_context(text, code):
        folded = engine._normalize_tr(text)
        return any(
            folded[:match.start()].strip()
            for name in engine._code_aliases(code)
            for match in re.finditer(
                engine._guard_regex("prefix", engine._SELF_EN,
                                    re.escape(name)), folded))

    assert sum(1 for text, code in _ENGLISH_ACCEPTS
               if has_left_context(text, code)) == 5


_WIDENED_BRANCH_REFUSALS = [
    # The locative's own letters, in three endings that are not a locative.
    ("Almanya'ya buğday sattım", 79),          # dative, and `sattım` is 1sg
    ("Hollanda'dan tohum aldım", 150),         # ablative
    ("Hollanda'daki seralar çok iyi", 150),    # locative + the relativiser -ki
    # A locative with no first-person predicate in reach.
    ("Fransa'da ekim zamanı geçti mi", 68),
    ("Amerika'da tohum fiyatları nasıl, ben ne eksem", 231),
    ("Fransa'da durum buğdayı yetişir mi", 68),
    # A plan rather than a location. The volitional stem `ist-` was skipped
    # free by the deleted window, which is how `istenen` and `istedigim` got in.
    ("Hollanda'da sera kurmak istiyorum", 150),
    # Hearsay: the locative belongs to the embedded clause. `verim` also ENDS in
    # the aorist's letters, which is why no ending test was ever the right test
    # - this sentence is the one the aorist admitted.
    ("Fransa'da verim yüksek diye duydum", 68),
]


@pytest.mark.parametrize("text,code", _WIDENED_BRANCH_REFUSALS)
def test_the_widened_branch_still_refuses_what_is_not_a_location(text, code):
    """The widening may not be a first-person-verb test: all three of the
    sentences CRITICAL 3 refuses contain one. What it reads is the CASE ENDING
    and then the verb itself, and these are the endings and shapes that must
    stay out."""
    assert not engine._states_location(text, engine._code_aliases(code))


# The eleven that the window could not tell from a statement of location. They
# are kept as ONE list so the ablation tables in src/engine.py can be re-taken
# from the test suite rather than reconstructed from prose - which is what the
# wave before this one had to do, because its own 17 were never written down.
_OBJECT_LOCATIVES = [
    ("Fransa'da üretilen tohum kullanıyorum, buğday mı ekeyim", 68),
    ("Hollanda'da yetiştirilen fide alıyorum", 150),
    ("Almanya'da çalışan bir arkadaşım var, ona soruyorum", 79),
    ("Mısır'da üretilen gübreyi kullanıyorum", 59),
    ("Fransa'da satılan tohumu tercih ediyorum", 68),
    ("Hollanda'da geliştirilen seraları araştırıyorum", 150),
    ("İtalya'da yapılan zeytinyağını seviyorum", 106),
    ("İspanya'da kullanılan damlama sistemini kuruyorum", 203),
    ("Yunanistan'da yetişen pamuğu merak ediyorum", 84),
    ("Mısır'da ekilen buğdayı inceliyorum", 59),
    ("Fransa'da üretilen ilacı deniyorum", 68),
]


@pytest.mark.parametrize("text,code", _OBJECT_LOCATIVES)
def test_a_locative_that_belongs_to_an_object_is_not_a_stated_location(text, code):
    """THE CLASS THAT COST THIS GUARD ITS INFERENCE. Every rule that read the
    words after a locative had to answer "whose is this place", and none of them
    could: the SEED is produced in France, not the speaker.

    Measured at window 3 on 2526ab6, seven of these eleven were admitted. Three
    more at window 4. The leading sentence came back a fourth time at c74d9cc,
    one noun along - "Fransa'da üretilen tohumu ektiğim bir tarlam var" - because
    the land branch read the whole clause and never asked what the locative
    attached to, 12 of 12.

    They are refused by construction now: the surviving Turkish pattern never
    looks past the name, so there is no span for a participle phrase to stand
    in."""
    assert not engine._states_location(text, engine._code_aliases(code))


@pytest.mark.parametrize("message,code", [
    ("Fransa'da üretilen tohum kullanıyorum, buğday mı ekeyim", 68),
    ("Mısır'da ekilen buğdayı inceliyorum", 59),
])
def test_an_object_locative_does_not_open_the_country_block(message, code):
    """The block half of the same defect, for the two of the eleven that name a
    crop and so would have reached the figures. Measured on 2526ab6, the first
    printed France's full wheat block and the second Egypt's."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "Turkiye disinda" not in block
    assert "FAOSTAT" not in block


# THE SHAPE BRANCH'S OWN NEAR MISSES, and the reason this list exists at all:
# the wave that introduced that branch measured it against a refuse set in which
# ONE sentence out of 27 could reach its pattern, so its "0/27 refusals" was an
# empty measurement rather than a guarantee. Every sentence here reaches the
# branch's prefix - locative, a word ending in `-an/-en`, `bir` - so the tables
# in src/engine.py can fail. 26 of the 99 refusals the suite carries reach the
# deleted branch's loose prefix and 10 its shipped gate.
#
# Measured 2026-10-03 against the branch as it shipped at 12aba9e: TWELVE of
# these fifteen were admitted, and the first seven are the class
# the two-word window had just been narrowed to close - the locative belongs
# to the uncle, not to the speaker, and the user was placed abroad for the whole
# conversation.
_SHAPE_NEAR_MISSES = [
    # (a) the `-Im` word is a POSSESSED NOUN and not a predicate: the clause runs
    # on to its own `var`/`gördüm`. Every stem here ends in `y`, which is what
    # the old `\w*y[iu][mz]` could not tell from the copula `-yIm` - and
    # "Almanya'da çalışan bir arkadaşım var" above stayed out only because
    # `arkadaş` does not. Held by the clause-final rule.
    ("Fransa'da çalışan bir dayım var, ona soruyorum", 68),
    ("Almanya'da yaşayan bir dayım var, ona soruyorum", 79),
    ("Mısır'da oturan bir dayım var", 59),
    ("Fransa'da bulunan bir köyüm var", 68),
    ("Fransa'da doğan bir tayım var", 68),
    ("Hollanda'da çıkan bir yayım var", 150),
    ("Fransa'da yapılan bir sayım gördüm", 68),
    # (b) the participle's own event happens in the country; the speaker need not
    # be there. "Tanınan bir çiftçiyim" says he is KNOWN in France. Held by the
    # participle whitelist.
    ("Fransa'da tanınan bir çiftçiyim", 68),
    ("Fransa'da bilinen bir üreticiyim", 68),
    ("Fransa'da aranan bir suçluyum", 68),
    ("Hollanda'da satılan bir tohumcuyum", 150),
    ("Fransa'da ödüllendirilen bir üreticiyim", 68),
    # (c) `\w+[ae]n` was never a participle test - an ordinary noun ending in
    # -an/-en fills the slot just as well. Held by the whitelist.
    ("Fransa'da orman bir zenginliktir, ben çiftçiyim", 68),
    ("Fransa'da üretilen bir tohum kullanıyorum", 68),
    ("Fransa'da uygulanan bir yöntemi deniyorum", 68),
]


@pytest.mark.parametrize("text,code", _SHAPE_NEAR_MISSES)
def test_the_shape_branch_refuses_what_only_looks_like_its_shape(text, code):
    """THE SHAPE BRANCH WAS NOT A FIRST-PERSON TEST AND ITS REFUSE SET COULD NOT
    SAY SO. `\\w*y[iu][mz]` matches any noun whose stem ends in `y` carrying the
    bare possessive: `dayım`, `sayım`, `tayım`, `köyüm`, `yayım`. "Fransa'da
    çalışan bir dayım var" has no first-person predicate at all and was read as a
    statement of location.

    Three narrowings were added to hold these out and the branch is now deleted
    with them. Fifteen sentences are kept all the same, because the fifteen are
    the measurement the branch never had: the version before them scored "0 of
    27" on a refuse set in which ONE sentence could reach the pattern. A list
    built to reach a deleted rule is what the next proposal for one has to clear
    before it gets written."""
    assert not engine._states_location(text, engine._code_aliases(code))


# THE SAME CLASS, VERBLESS OR COMMA-CLOSED - the ten sentences that satisfy BOTH
# of the two narrowings the wave before this one added, and the reason its
# "both (shipped) 0/42" row could not fail: NONE of its 42 refusals reached the
# gate it scored. All ten of these do.
#
# The clause after the locative is exactly three words, the participle is in
# the deleted residence-participle whitelist, and the third word carries
# `-yIm` - but on a
# possessed noun, not on a copula. Measured at 78b72a2: all ten True.
_SHAPE_NEAR_MISSES_CLOSED = [
    ("Fransa'da çalışan bir dayım, ona soruyorum", 68),
    ("Fransa'da yaşayan bir dayım, buğday mı eksem", 68),
    ("Fransa'da yaşayan bir dayım, bana buğday tohumu gönderdi", 68),
    ("Almanya'da oturan bir dayım, bu yıl ne eksem", 79),
    ("Fransa'da oturan bir dayım. Bu yıl buğday mı eksem", 68),
    ("Fransa'da yaşayan bir köyüm, buğday mı eksem", 68),
    ("Fransa'da çalışan bir tayım, ne yapsam", 68),
    ("Hollanda'da oturan bir yayım, ne eksem", 150),
    ("Fransa'da yaşayan bir sayım, ne eksem", 68),
    ("Mısır'da çalışan bir dayım", 59),
]


@pytest.mark.parametrize("text,code", _SHAPE_NEAR_MISSES_CLOSED)
def test_a_possessed_noun_is_not_a_copular_predicate(text, code):
    """Take the `var` away, or close the clause with a comma, and the three-word
    rule that was credited with holding "Fransa'da çalışan bir dayım var" holds
    nothing: the clause IS three words, `çalışan` IS whitelisted, and `dayım`
    matched the inherited `y[iu][mz]$`. A Turkish grower with a relative abroad
    lost the province ask and was handed France's figures for the rest of the
    conversation.

    The derivational test that separated them - Turkish agent nouns end in
    `-cI`, so `çiftçiyim` passed and `dayım` did not - is deleted with the branch
    it gated, and it took "Fransa'da çiftçiyim" with it. The ten stay pinned
    because they are the only ten that ever reached the gate they were built for:
    the wave before measured "0 of 42" on a set where NONE of the 42 could."""
    assert not engine._states_location(text, engine._code_aliases(code))


@pytest.mark.parametrize("text,code", [
    ("Fransa'da çalışan bir dayım var, ona soruyorum", 68),
    ("Fransa'da tanınan bir çiftçiyim", 68),
    ("Fransa'da çalışan bir dayım, ona soruyorum", 68),
    ("Almanya'da oturan bir dayım, bu yıl ne eksem", 79),
])
def test_a_shape_near_miss_does_not_open_the_country_block(text, code):
    """The block half, for all three groups, and the reason this finding was
    Critical rather than Minor: since the wave that made a stated country print a
    location line with no figure, a wrong admission here is no longer invisible.
    It tells the model outright not to ask which province the user is in, and
    `_country_lines` asks every user turn, so it sticks for the conversation.

    Measured at 78b72a2, the third of these printed "Kullanici Turkiye disinda:
    France" and the fourth Germany's."""
    block = engine._crop_choice_block(text, None, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "Turkiye disinda" not in block


# THE PRESENT CONTINUOUS OF A COMMERCE, SEARCH OR TRAVEL VERB - the class no
# tense and no width can see, and the one the whitelist was built for. Every
# sentence here puts a first-person present-continuous verb within two words of
# a locative, so every one reached the deleted window branch's pattern - 20 of
# the 86 refusals did. Measured at 78b72a2: all twenty True. And the verb
# whitelist's "20 of 86" is the zero this wave deleted a rule over: twenty
# SIMPLE verbs, not one light-verb construction, so `-mAyA çalış-` was never
# tested and "Almanya'da satmaya çalışıyorum" walked through.
#
# The first four are the present-tense twins of the five pinned past-tense
# refusals below - the example was closed, the class was not. The rest is the
# whole TURKISH EXPORTER / BUYER / JOB-SEEKER class: a grower in Türkiye
# describing his market or his supplier abroad.
_ACTION_LOCATIVES = [
    ("Hollanda'da fuara katiliyorum", 150),
    ("Amerika'da bugday aliyorum, ben bugday mi eksem", 231),
    ("Fransa'da staj yapiyorum, bugday ekeyim mi", 68),
    ("Hollanda'da sera geziyorum, domates ekeyim mi", 150),
    ("Almanya'da pazar arıyorum, bu yıl ne eksem", 79),
    ("Almanya'da buğday satıyorum, bu yıl ne eksem", 79),
    ("Hollanda'da tohum alıyorum, domates mi eksem", 150),
    ("Fransa'da müşteri arıyorum, buğday mı eksem", 68),
    ("Fransa'da staj arıyorum", 68),
    ("Fransa'da ihracat yapıyorum, ne eksem", 68),
    ("Fransa'da arazi arıyorum", 68),
    ("Almanya'da fiyat soruyorum", 79),
    ("Hollanda'da sera geziyoruz", 150),
    ("Fransa'da tohum deniyorum", 68),
    ("Amerika'da makine kiralıyorum", 231),
    ("Fransa'da fuar geziyorum", 68),
    ("Hollanda'da ortak arıyorum", 150),
    ("Almanya'da gübre satıyoruz", 79),
    ("Fransa'da eğitim görüyorum", 68),
    ("Fransa'da tatil yapıyorum", 68),
]


@pytest.mark.parametrize("text,code", _ACTION_LOCATIVES)
def test_doing_business_in_a_place_is_not_being_in_it(text, code):
    """The tense rule closed "Amerika'da buğday aldım" and left "Amerika'da
    buğday alıyorum" wide open, because the present continuous is as much the
    tense of "what I am buying there" as of "where I am". The ending test of the
    day - `_TR_FIRST_PERSON`, since split in two and then deleted outright -
    justified the present continuous in its own comment as
    "the tenses 'where I am' is said in"; it is equally the tense a market, a
    supplier and a trip are described in, and then the locative attaches to them.

    Measured at 78b72a2, four of these printed the country's full figures:
    "Almanya'da buğday satıyorum" got 708,42 kg/da and 0,2051 USD/kg,
    "Hollanda'da tohum alıyorum" 47889,02 and 2,11, "Fransa'da müşteri arıyorum"
    597,35 and 0,2313. The verb whitelist refuses all twenty."""
    assert not engine._states_location(text, engine._code_aliases(code))


@pytest.mark.parametrize("message,code", [
    ("Almanya'da buğday satıyorum, bu yıl ne eksem", 79),
    ("Hollanda'da tohum alıyorum, domates mi eksem", 150),
])
def test_a_market_abroad_does_not_open_the_country_block(message, code):
    """The block half of the exporter class, for the two that name a crop. At
    78b72a2 the first printed Germany's wheat yield and farmgate price and the
    second the Netherlands' tomato figures, and the province ask was gone."""
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "Turkiye disinda" not in block
    assert "FAOSTAT" not in block


# A `-yIm`-shaped word that is a POSSESSED NOUN, standing next to the locative.
# These are the sentences the surviving Turkish pattern has to keep refusing
# while admitting "Fransa'dayım", and the distinction it draws is the one that
# matters: the suffix is on `dayım` and `tayım`, not on `Fransa`. 38 of the 86
# refusals carry such a word somewhere - see _SELF_TR for the count and why it
# is the right one to write beside that branch's zero.
_WINDOW_PERSON_NEAR_MISSES = [
    ("Fransa'da bir dayım var", 68),
    ("Fransa'da dayım oturuyor", 68),
    ("Fransa'da tayım var", 68),
    ("Fransa'da bir yayım çıktı", 68),
    ("Fransa'da payım var", 68),
    ("Fransa'da sayım yapıldı", 68),
    ("Hollanda'da köyüm var", 150),
    ("Fransa'da bir soyum var", 68),
]


@pytest.mark.parametrize("text,code", _WINDOW_PERSON_NEAR_MISSES)
def test_a_possessed_noun_in_the_window_is_not_a_predicate(text, code):
    """"Fransa'da bir dayım var" is the sentence that leaked at 78b72a2 on a
    loose `y[iu][mz]$`, and it is the clearest statement of why the suffix has
    to be fused to the NAME: `dayım` is five letters from `Fransa` and it is my
    uncle, not me.

    "Fransa'da dayım oturuyor" is here for the mirror case: `oturuyor` was a
    whitelisted stem but THIRD person, so the uncle lives there and the speaker
    does not."""
    assert not engine._states_location(text, engine._code_aliases(code))


def test_the_reach_count_beside_the_surviving_branchs_zero():
    """THE ONE NUMBER THIS WAVE EXISTS TO GET RIGHT. Four reviews in a row found
    a rule licensed by a zero that none of the refusals could have broken,
    because the count written beside it was the number of inputs that ENTER the
    branch rather than the number that could BREAK the decision under test.

    `_SELF_TR`'s decision is "the person suffix sits on the country's own name,
    with nothing in between", and it has THREE ways to fail, so it needs three
    counts rather than one.

    LEFT OF THE NAME, AND SOMEWHERE ELSE IN THE SENTENCE: an input can break the
    decision by carrying a `-yIm`-shaped word on another word, because a looser
    reading that scanned the clause would admit exactly those. 44 of the 99
    refusals do, and the words are `dayim`, `tayim`, `koyum`, `sayim`, `payim`,
    `soyum`, `yayim`, `ekeyim`, `kurayim`, `ciftciyim`, `ureticiyim`, `sucluyum`,
    `tohumcuyum` and `ekmeliyim` - possessed nouns, optatives and other people's
    agent nouns. FOURTEEN FORMS: the comment above `_SELF_TR` used to list
    thirteen of them and the missing one is `yayim`, which is why the restricted
    count is asserted here too - over the thirteen it returns 41, not 44, so the
    number was right and the enumeration was short.

    RIGHT OF THE NAME: a token that merely STARTS with an alias and runs on into
    the locative letters. 4 of the 99 are of that shape and 0 of the 95 that
    shipped were, which is why `_NAME_BOUNDARY_REFUSALS` exists.

    The third way - the locative's own letters followed by something that is not
    `-yIm` - is `_SUFFIX_NEAR_MISSES` and is counted by its own test."""
    person = re.compile(r"y[iu][mz]$")
    listed = {"dayim", "tayim", "koyum", "sayim", "payim", "soyum", "yayim",
              "ekeyim", "kurayim", "ekmeliyim", "ciftciyim", "ureticiyim",
              "sucluyum", "tohumcuyum"}

    def elsewhere(forms):
        reach = []
        for text, code in _TURKISH_REFUSALS:
            names = engine._code_aliases(code)
            words = [raw.strip(" '\"()-,;:.!?…")
                     for raw in engine._normalize_tr(text).split()]
            if any((word in forms if forms else person.search(word))
                   and not any(word.startswith(name) for name in names)
                   for word in words):
                reach.append(text)
        return reach

    assert len(elsewhere(None)) == 44, elsewhere(None)
    assert len(elsewhere(listed)) == 44
    assert len(elsewhere(listed - {"yayim"})) == 41

    boundary = []
    for text, code in _TURKISH_REFUSALS:
        folded = engine._normalize_tr(text)
        for name in engine._code_aliases(code):
            key = re.escape(name)
            if (re.search(rf"(?<!\w){key}[\w']*[dt][ae]y[iu][mz](?!\w)", folded)
                    and not re.search(
                        engine._guard_regex("suffix", engine._SELF_TR, key),
                        folded)):
                boundary.append(text)
                break
    assert len(boundary) == 4, boundary
    assert sorted(boundary) == sorted(text for text, _code
                                      in _NAME_BOUNDARY_REFUSALS)

    assert [text for text, code in _TURKISH_REFUSALS
            if engine._states_location(text, engine._code_aliases(code))] == []


# --------------------------------------------------------------------------- #
# A bare country name is a noun, and no conversation makes it a location
# --------------------------------------------------------------------------- #
_BARE_NAMES = [
    # The one crop/country collision the shipped tables hold, in every spelling
    # a one-word message can take.
    ("Mısır", 59),
    ("mısır", 59),
    ("Mısır.", 59),
    ("misir", 59),
    # And four names that are not crops.
    ("Çin", 41),
    ("Fransa", 68),
    ("fransa", 68),
    ("Hollanda", 150),
]

# THE ASSISTANT TURNS THE DELETED GATE READ WRONGLY. Ten realistic turns for
# THIS product, none of which asks where the user is, and the gate opened on
# 10 of 10 - it was a place-word MENTION detector, not a question detector.
#
# The seventh is `crop_compare.ASK_FOR_CROPS`, A SHIPPED LITERAL of our own,
# returned verbatim as `ChatResult(answer=crop_compare.ASK_FOR_CROPS)`, so it
# lands in the history as an assistant turn. It asks which two CROPS and it
# opened the location gate, through "ilinizde". That is why the gate is gone
# rather than narrowed: the evidence it needed is the model's own wording, which
# this repo does not own, and the one wording it DOES own defeated it.
_NON_ASKING_TURNS = [
    "Toprak analizini nerede yaptırabileceğinizi il tarım müdürlüğünden sorun.",
    "Sertifikalı fidanı nerede bulabileceğinizi anlatayım.",
    "Zirai ilaç bayisinin nerede olduğunu öğrenmeniz yeterli.",
    "Buğday verimi hangi bölgede olduğunuza göre değişir, genel olarak şöyle.",
    "Hangi ilçede olduğunuz önemli değil, ürün neydi?",
    "Sulama suyunun nerede biriktiğine bakın.",
    None,                                      # crop_compare.ASK_FOR_CROPS
    "Gübreyi hangi yerde depoladığınız önemli.",
    "Deneme parselini hangi köyde kurduğunuz fark etmez.",
    "Fidanı nerede saklıyorsunuz?",
]

# And the turns that DO ask. They were the gate's accepts; they are kept so the
# test below can say that a bare name is refused after these too - which is the
# behaviour change, and the cost.
_ASKING_TURNS = [
    "Hangi ilde olduğunuzu söyler misiniz?",
    "Öncelikle hangi ildesiniz?",
    "Hangi il veya bölgede tarım yapıyorsunuz?",
    "Nerede yaşıyorsunuz?",
    "Hangi şehirdesiniz?",
    "Lütfen hangi ilde olduğunuzu belirtin.",
    "Hangi ülkedesiniz?",
    "Hangi ildesiniz ve hangi ürünü düşünüyorsunuz?",
]


@pytest.mark.parametrize("text,code", _BARE_NAMES)
def test_a_bare_country_name_alone_is_not_a_stated_location(text, code):
    """A one-word message predicates nobody - it is a noun. Measured at 78b72a2,
    all eight were True unconditionally; the wave after that gated them on the
    assistant's own question, and this wave deletes the gate. EIGHT, not ten -
    the wave-3 report quoted a denominator of 10 for this list and the list
    carries 8, which is why its length is pinned below."""
    assert not engine._states_location(text, engine._code_aliases(code))


@pytest.mark.parametrize("asked", _ASKING_TURNS)
def test_a_bare_name_is_refused_even_after_the_question_it_answers(asked):
    """THE COST OF DELETING THE BARE-NAME BRANCH, pinned as a cost and not as a
    correct answer. A grower answering "hangi ildesiniz?" with "Fransa" used to
    be placed in France; he now gets the question again, and `_ASK_LOCATION`
    asks him for "Fransa'dayım" this time. That is ONE EXTRA TURN for every
    foreign grower who answers with a bare country name - eight shapes of the
    question, here, and the cost is the same after all eight.

    What it buys is in `test_the_deleted_gate_fired_on_turns_that_asked_nothing`
    below: the same gate read a bare name after a CROP question, and one of the
    turns it read that way is a string this repo ships."""
    history = [{"role": "user", "content": "bu yıl ne eksem"},
               {"role": "assistant", "content": asked}]
    block = engine._crop_choice_block("Fransa", history, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "France" not in block


def test_the_deleted_gate_fired_on_turns_that_asked_nothing():
    """WHY THE GATE COULD NOT BE NARROWED INSTEAD. Its evidence was the
    assistant's own question, which this repo does not write - the crop-choice
    block says "cevabinda hangi ilde oldugunu sor" and the model phrases it - so
    the gate had to match place WORDS, and then every turn that MENTIONS a place
    opened it. Ten realistic non-asking turns, 10 of 10 wrongly open at c74d9cc.

    One of the ten is `crop_compare.ASK_FOR_CROPS`, which this repo DOES own: it
    asks which two crops, it contains "ilinizde", and it is returned verbatim as
    an assistant turn. So the branch's declared defence - "the assistant's real
    wording is not in the repo, so no test could catch this" - was refuted by a
    string in the repo.

    Asserted as the behaviour that matters rather than on the deleted predicate:
    after any of these turns, a bare country name does not place the user."""
    from src import crop_compare
    turns = [turn if turn is not None else crop_compare.ASK_FOR_CROPS
             for turn in _NON_ASKING_TURNS]
    assert len(turns) == 10
    assert "ilinizde" in engine._normalize_tr(crop_compare.ASK_FOR_CROPS)
    for asked in turns:
        history = [{"role": "user", "content": "bu yıl ne eksem"},
                   {"role": "assistant", "content": asked}]
        block = engine._crop_choice_block("Fransa", history, date(2026, 9, 25))
        assert "BILINMIYOR" in block, asked
        assert "France" not in block, asked


@pytest.mark.parametrize("reply", ["Mısır", "mısır", "Mısır."])
def test_a_crop_name_is_not_a_location_even_after_a_location_question(reply):
    """`Mısır` is Egypt and maize at once - the ONLY such collision in the
    shipped tables, 187 crop families against 418 folded country alias keys -
    and it was the sentence that proved the bare name needed a gate at all.

    It needed TWO gates while the branch existed, because the province question
    and the crop question arrive in the same generated turn. With the branch
    gone it needs none, and the crop-name half of the guard (`_is_a_crop_name`,
    which held the fourth copy of the label fold) went with it."""
    history = [{"role": "user", "content": "bu yıl ne eksem"},
               {"role": "assistant",
                "content": "Hangi ildesiniz ve hangi ürünü düşünüyorsunuz?"}]
    block = engine._crop_choice_block(reply, history, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "Egypt" not in block


def test_a_crop_name_in_history_does_not_move_the_grower_abroad():
    """The history half, and the half that did the real damage: `_country_lines`
    asks EVERY user turn, so one turn reading `mısır` - the natural answer to
    "hangi ürünü düşünüyorsunuz?" - moved every later turn to Egypt. Measured at
    78b72a2 this printed "Kullanici Turkiye disinda: Egypt" and Egypt's wheat
    figures, 677,77 kg/da and 0,3265 USD/kg."""
    history = [{"role": "assistant", "content": "Hangi ürünü düşünüyorsunuz?"},
               {"role": "user", "content": "mısır"}]
    block = engine._crop_choice_block("buğday mı eksem", history,
                                      date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "Egypt" not in block
    assert "677,77" not in block


# --------------------------------------------------------------------------- #
# What dropping the inference costs
# --------------------------------------------------------------------------- #
# THE 39 ACCEPTS THIS WAVE GIVES UP, listed rather than described, because this
# is a SCOPE REDUCTION and the brief that ordered it said the price would be
# counted and nailed down. Every sentence here was an accept at c74d9cc, every
# one of them really does say where the speaker is, and every one of them now
# gets `_ASK_LOCATION` back instead of figures. 39 of the 41 Turkish accepts;
# the two survivors are in `_FUSED_SUFFIX_ACCEPTS`.
#
# They are grouped by the rule that used to admit them, so the price is
# attributable: if a later wave proposes any of these rules again, the group
# below is what it is buying.
_SURRENDERED_ACCEPTS = [
    # (1) THE WINDOW - a locative plus a first-person predicate within two
    # words. Deleted because it never asked WHOSE the place was: the same two
    # words hold "Fransa'da buğday ekiyorum" and "Fransa'da üretilen tohum
    # kullanıyorum", and no width tells a speaker from a seed.
    "Fransa'da yaşıyorum, buğday mı ekmeliyim",
    "Fransa'da çiftçilik yapıyorum, buğday mı ekmeliyim",
    "Fransa'da ben buğday ekiyorum, buğday mı ekmeliyim",
    # (2) THE RESIDENCE/CULTIVATION VERB WHITELIST, one per member. Deleted
    # because `-mAyA çalış-` makes `çalış-` a light verb, so "Almanya'da satmaya
    # çalışıyorum" - the canonical Turkish exporter - was placed in Germany, and
    # the "20 of 86" that licensed the list held no light-verb construction at
    # all.
    "Fransa'da yaşıyorum",
    "Fransa'da oturuyorum",
    "Fransa'da çalışıyorum",
    "Fransa'da buğday ekiyorum",
    "Fransa'da fidan dikiyorum",
    "Fransa'da domates yetiştiriyorum",
    "Fransa'da buğday üretiyorum",
    "Fransa'da tarla suluyorum",
    "Fransa'da bağ buduyorum",
    "Fransa'da hayvan besliyorum",
    "Fransa'da çiftçilik yapıyorum",
    "Fransa'da tarım yapıyorum",
    "Fransa'da ekim yapıyorum",
    "Fransa'da üretim yapıyorum",
    "Fransa'da bağcılık yapıyorum",
    "Fransa'da seracılık yapıyorum",
    "Fransa'da hayvancılık yapıyorum",
    "Fransa'da hasat yapıyorum",
    # (3) THE AGENT-NOUN COPULA, `c[iu]y[iu][mz]$`. Deleted with the window it
    # rode on: the copula is on the NOUN, so admitting it means reading words
    # after the name, which is the decision nothing could measure.
    "Fransa'da çiftçiyim",
    "Fransa'da bir çiftçiyim",
    "Fransa'da üreticiyim",
    "Fransa'da bağcıyım",
    "Fransada ciftciyim, bugday mi ekmeliyim",
    # (4) OWNED LAND, `<land noun carrying -Im> var`. Deleted because it read
    # the WHOLE CLAUSE with no adjacency and handed back 12 of 12 object-
    # locative sentences, on a "0 of 86" that 0 of the 86 could break.
    "Fransa'da tarlam var",
    "Fransa'da arazim var",
    "Fransa'da bir çiftliğim var",
    "Fransa'da bahçem var",
    "Fransa'da seram var",
    "Fransa'da bağım var",
    "Fransa'da 30 dönüm arazim var",
    # (5) THE RESIDENCE PARTICIPLE SHAPE. Deleted because its person test was a
    # morphological claim ("agent nouns end in -cI") standing in for a meaning,
    # and because a comma closing the clause walked `bir dayım` straight back
    # through it.
    "Fransa'da yaşayan bir çiftçiyim",
    "Fransa'da çalışan bir işçiyim",
    "Fransa'da yaşayan bir çiftçiyiz",
    "Fransa'da oturan bir çiftçiyim",
    "Fransa'da yaşayan bir çiftçiyim, buğday mı ekmeliyim",
    # The curly apostrophe, U+2019, on the shape branch. The character still
    # works - see `_FUSED_SUFFIX_ACCEPTS`, which inherited that assertion - so
    # this is lost to the branch and not to the fold.
    "Fransa’da yaşayan bir çiftçiyim",
]


@pytest.mark.parametrize("text", _SURRENDERED_ACCEPTS)
def test_the_price_of_dropping_the_inference(text):
    """PINNED AS A COST, NOT AS A CORRECT ANSWER - 39 sentences that say where
    the speaker is and are refused now.

    WHY THE DIRECTION IS STILL RIGHT, and it is the one sentence this test
    exists to carry: a refusal costs ONE QUESTION and the user gets the answer
    back by writing "Fransa'dayım", which `_ASK_LOCATION` now asks him for in
    exactly that spelling. A wrong admission is silent, wrong, and - because
    `_country_lines` asks every user turn - sticky for the whole conversation,
    with nothing in the product that retracts it. Four reviews found four
    Criticals of that second kind in five waves of rules built to recover these
    39, and every one of those rules was licensed by a measurement that could
    not fail.

    What would change this trade is a measurement, not an argument: a rule here
    earns its place when its refuse set contains the inputs that could break the
    DECISION it makes, not the inputs that merely reach it."""
    assert not engine._states_location(text, engine._code_aliases(68))


# COSTS THAT ARE OLDER THAN THIS WAVE and are unchanged by it: eleven sentences
# the inverted whitelist already refused. They are kept because they are still
# refused and still regrettable, and because the reason each one was refused has
# changed - every one of them is now refused for the same single reason, that
# the person suffix is not on the name.
_STANDING_COSTS = [
    # Were the price of the two-word window, and of the widths beyond it.
    "Fransa'da iki yıldır çiftçiyim",
    "Fransa'da uzun süredir çiftçilik yapıyorum",
    "Fransa'da küçük bir arazide çiftçilik yapıyorum",
    # Were the price of the shape branch's two narrowings.
    "Fransa'da yaşayan bir çiftçiyim ve buğday ekiyorum",
    "Fransa'da yerleşen bir çiftçiyim",
    # Were the price of the verb whitelist: `topl-` also heads "bilgi
    # topluyorum", `işlet-` a business run from anywhere, `kullan-` is
    # `_OBJECT_LOCATIVES`' own verb, and `oku-` is the present twin of the
    # pinned past-tense refusal "Fransa'da okudum".
    "Fransa'da zeytin topluyorum",
    "Fransa'da sera işletiyorum",
    "Fransa'da traktör kullanıyorum",
    "Fransa'da okuyorum",
    # Were the price of the agent-noun copula: a first-person nominal predicate
    # that is not an agent noun in `-cI`.
    "Fransa'da emekliyim",
    "Fransa'da yeniyim",
]


@pytest.mark.parametrize("text", _STANDING_COSTS)
def test_the_costs_the_inversion_already_paid_are_still_paid(text):
    """The eleven costs the previous wave counted, re-pinned in one place
    because the four tests that held them named four rules that no longer exist.
    No sentence was dropped in the merge; their reasons were.

    50 COSTS IN ALL on this path now: these eleven, the 39 in
    `_SURRENDERED_ACCEPTS`, and the bare name, which is pinned in its own two
    tests above because its cost is a TURN rather than an answer."""
    assert not engine._states_location(text, engine._code_aliases(68))


_PAST_TENSE_REFUSALS = [
    # The shape, and the one this guard exists for: a Turkish farmer citing a
    # foreign price.
    ("Amerika'da bugday aldim, ben bugday mi eksem", 231),
    ("Hollanda'da sera gordum, domates ekeyim mi", 150),
    ("Fransa'da staj yaptim, bugday ekeyim mi", 68),
    ("Fransa'da okudum", 68),
    ("Hollanda'da fuara katildim", 150),
]


@pytest.mark.parametrize("message,code", _PAST_TENSE_REFUSALS)
def test_a_locative_with_a_past_tense_verb_is_not_a_stated_location(message, code):
    """The case ending is not enough on its own - the TENSE matters too. A
    locative plus a first-person PAST verb says something was DONE there, not
    that the speaker is there, and all five of these were admitted while the
    person test carried `-dim/-tim`.

    Worse than a one-turn error, because `_country_lines` asks every user turn:
    one "Fransa'da staj yaptım" in the first turn kept the grower in France for
    the rest of the conversation.

    THEY ARE REFUSED TWICE OVER NOW and the second hold is the one that matters:
    the verb whitelist refuses `aldim`, `gordum`, `yaptim`, `okudum` and
    `katildim` by their stems, so the four whose present-continuous twins are in
    `_ACTION_LOCATIVES` stay out in both tenses. Closing the example is not
    closing the class."""
    assert not engine._states_location(message, engine._code_aliases(code))
    block = engine._crop_choice_block(message, None, date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "FAOSTAT" not in block


def test_a_past_tense_turn_does_not_place_the_grower_for_the_whole_chat():
    """The history half of the same defect: every user turn is asked, so a
    finished action named once would carry the rest of the conversation."""
    history = [{"role": "user", "content": "Fransa'da staj yaptım"}]
    block = engine._crop_choice_block("buğday mı ekmeliyim", history,
                                      date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "France" not in block


def test_a_country_stated_earlier_in_the_conversation_still_counts():
    """`extract_country` returns the most RECENT mention, which need not be the
    turn that stated where the user is. Every user turn is asked, so a location
    given two turns ago still carries the figures."""
    history = [{"role": "user", "content": "Fransa'dayım, merhaba"},
               {"role": "assistant", "content": "Merhaba."}]
    block = engine._crop_choice_block("buğday mı ekmeliyim", history,
                                      date(2026, 9, 25))
    assert "France" in block
    assert "BILINMIYOR" not in block


def test_the_assistant_naming_a_country_is_not_a_location():
    """Assistant turns are skipped, the way country.extract_country skips them:
    the assistant names countries while answering, and reading its own examples
    back would place the grower wherever the last one was set."""
    history = [{"role": "assistant",
                "content": "Fransa'dayım diyen çiftçiler için verim yüksektir."}]
    block = engine._crop_choice_block("buğday mı ekmeliyim", history,
                                      date(2026, 9, 25))
    assert "BILINMIYOR" in block
    assert "France" not in block


# --------------------------------------------------------------------------- #
# The corpus the guard's numbers are quoted over
# --------------------------------------------------------------------------- #
_TURKISH_ACCEPTS = list(_FUSED_SUFFIX_ACCEPTS)

_TURKISH_REFUSALS = (_MERELY_NAMING + _WIDENED_BRANCH_REFUSALS
                     + _OBJECT_LOCATIVES + _SHAPE_NEAR_MISSES
                     + _SHAPE_NEAR_MISSES_CLOSED + _ACTION_LOCATIVES
                     + _WINDOW_PERSON_NEAR_MISSES + _POSSESSION_NEAR_MISSES
                     + _PAST_TENSE_REFUSALS + _SUFFIX_NEAR_MISSES
                     + _NATIONALITY_REFUSALS + _NAME_BOUNDARY_REFUSALS)


def test_the_corpus_the_guards_numbers_are_quoted_over():
    """3 ACCEPTS AND 99 REFUSALS, pinned the way
    `test_the_world_layer_row_counts_the_two_comments_rest_on` pins 8425/321/33.

    EVERY DENOMINATOR src/engine.py's guard comment quotes IS HERE, because five
    stale numbers were found above this guard on this branch - "37 accepts" and
    "37 accepts / 92 refusals" against a real 41/86, "16 reach" against a real
    18, and a bare-name table quoted over 10 for a list of 8. A number a test
    does not derive from the suite goes stale at the next commit that touches
    what it counted.

    THE ACCEPT COLUMN FELL FROM 41 TO 3 and that is the wave's whole subject:
    the 39 sentences it lost are listed in `_SURRENDERED_ACCEPTS` and pinned as
    costs there, not deleted. The refusal column ROSE from 86 to 99 - deleting
    rules cannot admit anything, so all 86 still refuse; five of the thirteen new
    ones are `_SUFFIX_NEAR_MISSES`, built to break the one decision the
    surviving Turkish pattern makes, four are `_NATIONALITY_REFUSALS`, the
    `-lI` arm that was dropped after this wave, and four are
    `_NAME_BOUNDARY_REFUSALS`, the third way that one decision can fail.

    THE ENGLISH COLUMNS MOVED IN THE SAME WAVE: 25 refusals to 35, because the
    `from` arm was dropped and `_ENGLISH_ORIGIN_REFUSALS` is the class it used to
    admit; and 10 accepts to 14, because the conditional, the future and the two
    US towns are now DECLARED accepts rather than unwritten ones.

    AND THEY MOVED TWICE MORE SINCE: 35 to 42 when the possessed-noun subjects
    were dropped (`_POSSESSED_SUBJECT_LEAKS` plus the two conditionals), and 42
    to 58 when the left veto landed - `_SUPPOSED_MOOD_REFUSALS` grew from 2 to
    10 because the mood had seven other spellings and two other spacings, and
    `_ATTRIBUTED_SUBJECT_REFUSALS` is 8 sentences that put somebody ELSE's `i` in
    the subject slot. The accept column is 16: 14 less the two possessed-noun
    costs, plus `whenever` and the three `_LEFT_CONTEXT_ACCEPTS`.

    THE 50 PINNED COSTS ARE DELIBERATELY OUTSIDE BOTH NUMBERS: a cost is a
    sentence the guard refuses and we wish it did not, so a looser rule that
    admits one is not "wrongly" admitting it. Counting them in the refusal
    denominator would inflate every column with sentences the number is not
    about."""
    assert len(set(_TURKISH_ACCEPTS)) == len(_TURKISH_ACCEPTS) == 3
    assert len(set(_TURKISH_REFUSALS)) == len(_TURKISH_REFUSALS) == 99
    assert len(set(_ENGLISH_ACCEPTS)) == len(_ENGLISH_ACCEPTS) == 16
    assert len(set(_ENGLISH_NOT_A_LOCATION)) == len(_ENGLISH_NOT_A_LOCATION) == 58
    assert len(_ENGLISH_ORIGIN_REFUSALS) == 10
    assert len(_DECLARED_ENGLISH_ACCEPTS) == 5
    assert len(_LEFT_CONTEXT_ACCEPTS) == 3
    assert len(_NAME_BOUNDARY_REFUSALS) == 4
    assert len(_POSSESSED_SUBJECT_COSTS) == 2
    assert len(_POSSESSED_SUBJECT_LEAKS) == 5
    assert len(_SUPPOSED_MOOD_REFUSALS) == 10
    assert len(_ATTRIBUTED_SUBJECT_REFUSALS) == 8
    assert len(_BARE_NAMES) == 8
    assert len(_SURRENDERED_ACCEPTS) == 39
    assert len(_STANDING_COSTS) == 11


def test_every_accept_in_the_corpus_is_admitted_and_every_refusal_refused():
    """The two columns in one place, so a reader sees the 3/3 and 0/99 the
    guard's comment quotes without re-deriving them from the parametrizations.

    Asserted as COUNTS with the offenders named, because a parametrized failure
    reports one case and this reports the shape of a regression."""
    admitted = [text for text in _TURKISH_ACCEPTS
                if not engine._states_location(text, engine._code_aliases(68))]
    assert admitted == []
    leaked = [text for text, code in _TURKISH_REFUSALS
              if engine._states_location(text, engine._code_aliases(code))]
    assert leaked == []
    english_out = [text for text, code in _ENGLISH_ACCEPTS
                   if not engine._states_location(text,
                                                  engine._code_aliases(code))]
    assert english_out == []
    english_in = [text for text, code in _ENGLISH_NOT_A_LOCATION
                  if engine._states_location(text, engine._code_aliases(code))]
    assert english_in == []


def test_the_two_surviving_patterns_hold_the_refuse_set_on_their_own():
    r"""THE RE-MEASUREMENT THE BRIEF ASKED FOR, and it is not the same assertion
    as the one above. Deleting a rule cannot admit anything, but it CAN move
    which rule refuses a sentence - a refusal the verb whitelist used to hold
    now falls to whatever is left. So each surviving pattern is scored on its
    own against the whole refuse set, rather than the pair being scored as a
    unit: if either one were carrying a class only the other refused, a later
    change to that one would open it silently.

    Measured: each pattern admits 0 of the 99 Turkish and 0 of the 58 English by
    itself.

    THE WHOLE DECISION IS READ OUT OF `engine._GUARDS` AND APPLIED BY
    `engine._guard_hits`, NOT REBUILT HERE. This test used to spell out
    `rf"(?<!\w){key}{pattern}"` and `rf"{pattern}{key}(?!\w)"` itself, which made
    it a copy of the block under test: a change to the composition - a boundary
    added on the English side, say - would have left it green while it measured a
    regex nobody ships. That is this guard's standing defect applied to its own
    test, and the guard has been reviewed six times for exactly that shape.

    AND IT CALLS `_guard_hits` RATHER THAN `re.search`, WHICH IS THE SAME FIX ONE
    LEVEL ON. Half of what one guard decides is no longer inside its regex: the
    mood and the attribution are a veto on the text to the LEFT of the match,
    because a lookbehind in `re` must be fixed-width and neither a mood word nor
    the run of space after it is. A test that searched the pattern alone would
    call all 18 of those refusals admitted - it would be red for the right
    reason today, and green over half a rule the day someone moved the veto into
    the pattern.

    AND THE KEY COMES FROM `engine._alias_key` FOR THE SAME REASON, which is the
    third time this one test has had to stop rebuilding a piece of the shipped
    composition. The buffer `n` and its length gate live in that function, not in
    `_SELF_TR`, so a `re.escape(alias)` written here would score a regex nobody
    ships - green over a guard that places nobody on "Rusya Federasyonundayim",
    and green too if the length gate were deleted."""
    assert len(engine._GUARDS) == 2
    for guard in engine._GUARDS:
        name, side = guard[0], guard[1]
        for text, code in _TURKISH_REFUSALS + _ENGLISH_NOT_A_LOCATION:
            folded = engine._normalize_tr(text)
            for alias in engine._code_aliases(code):
                key = engine._alias_key(alias, side)
                assert not engine._guard_hits(guard, key, folded), (name, text)


# --------------------------------------------------------------------------- #
# How the figures themselves are written
# --------------------------------------------------------------------------- #
def test_a_large_yield_carries_no_thousands_separator():
    """Turkish convention writes the thousands separator as a dot, so
    `format_qty(4000.0)` is "4.000" - which under English convention reads as
    four. These lines are read by a language model, so the separator goes:
    measured over data/world_norms.json, 3.104 of the 8.453 latest yield cells
    are >= 1000 and 206 of those are whole numbers, the exact "4.000" shape."""
    block = engine._crop_choice_block("Hollanda'dayım, domates ekeyim mi",
                                      None, date(2026, 9, 25))
    assert "47889,02 kg/da" in block
    assert "47.889" not in block


def test_the_b_flag_does_not_claim_the_value_is_official():
    """FAOSTAT's `B` is a time-series break and says nothing about who produced
    the cell; data/world_norms.json's own meta.flags reads "Time series break".
    The gloss used to add "resmi deger" to it.

    Asserted on the table rather than through a block, because all 43 `B` cells
    in the shipped file sit in earlier years of the price series and none is the
    latest non-null year of its series, so `_pick_world` returns none of them -
    this gloss is unreachable today and Critical the moment a rebuild lands one
    last."""
    assert engine._flag_note("B") == ("seride kopus var, deger onceki yillarla "
                                      "karsilastirilamaz")
    assert "resmi" not in engine._flag_note("B")


def test_the_i_flag_does_not_narrow_the_receiving_agency_to_fao():
    """"Value imputed by a receiving agency" - not FAO specifically, and not
    "assigned". 3 cells in the shipped file, none of them latest."""
    assert "FAO" not in engine._flag_note("I")


def test_the_figures_may_not_be_multiplied_into_a_revenue_number():
    """Yield and price sit on adjacent lines, so 597,35 x 0,2313 is one step
    from a 138 USD/da gross-income figure with no cost side - exactly the shape
    a farmer acts on. The ULKE ORTALAMASI caution immunises each figure against
    being read as field-specific and says nothing about their product."""
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "carpip" in block and "masraf" in block


def test_the_caution_line_does_not_promise_a_source_beside_every_number():
    """`_pick_world` returns flag=None for a cell FAOSTAT ships unflagged and
    `_flag_note` prints an unknown letter as itself, so the parenthesis beside a
    figure can be nothing but its year. A line promising a source beside every
    number would have the model look for one that is not there."""
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "kaynagi belliyse" in block


def test_the_answer_is_asked_to_keep_the_faostat_label():
    """Several FAOSTAT areas collapse to one Turkish name - `Congo` and
    `Democratic Republic of the Congo` are both "Kongo", `China` and `China,
    mainland` both "Çin" - so a prompt that is right about the area can still
    produce an answer naming the wrong country, with nothing in the answer to
    tell."""
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "parantez icinde FAOSTAT'in bu adini aynen ekle" in block


def test_crop_choice_never_gets_a_framing_sentence():
    """`crop_choice` has no reviewed programme behind it, so it gets no framing
    suffix. This passes today by virtue of the `route != "fert_plan"` guard; it is
    here so that adding a second framing route later cannot silently give this one
    a sentence it has no basis for."""
    assert engine._framing_suffix("crop_choice", "Bu yıl ne eksem?") == ""


def test_other_routes_still_get_an_empty_context_block():
    """The regression that matters: adding a branch must not disturb the default."""
    for route in ("plant_info", "nutrition", "budget", "offscope"):
        assert engine._context_block(
            route, "Bu yıl ne eksem?", None, date(2026, 8, 11)) == "", route


# --------------------------------------------------------------------------- #
# The buffer `n` on the guard's side. `_alias_key` spells it; these measure the
# decision it makes. Every list is DERIVED from the shipped alias table, so a
# new alias joins the measurement instead of staling a figure.
#
# THE SHIPPED 0/99 LICENSES NOTHING HERE, which is the whole reason this block
# exists: 0 of the 99 Turkish refusals put an `n` between the name and the
# locative, so not one of them could have broken the decision `_alias_key`
# makes. `_SELF_TR`'s own comment said so and deferred the widening until a
# refuse set existed that could FAIL. This is that set.
# --------------------------------------------------------------------------- #

# HAND-KEPT - see tests/test_country.py's copy for why no property of the table
# can derive it: `Somali`, `Mali`, `Cibuti`, `Burundi`, `Haiti`, `Brunei`,
# `Fiji` and `Niue` all end in a vowel and take no buffer, and a regex over
# `-eti|-onu|-eri|-arı` misses `Ekvator Ginesi`.
_POSSESSIVE_HEADS = (
    "cumhuriyeti", "federasyonu", "emirlikleri", "devletleri", "adaları",
    "polinezyası", "sahili", "anakarası", "ginesi",
)
_BACK, _FRONT, _VOICELESS = set("aıou"), set("eiöü"), set("fstkçşhp")


def _tr_aliases():
    from src.context import country as country_ctx
    raw = json.loads(country_ctx._TABLE.read_text(encoding="utf-8"))
    return [(int(code), name.strip())
            for code, entry in raw.items()
            for name in (entry.get("tr") or ())
            if isinstance(name, str) and name.strip()]


def _loc(name):
    """The locative Turkish actually writes on `name`, harmony and the voiceless
    assimilation included. Spelled out rather than approximated: a `-de` where
    Turkish wants `-da` would make these lists agree with a looser pattern than
    the one shipped, and agree for the wrong reason."""
    low = name.lower()
    vowels = [c for c in low if c in _BACK | _FRONT]
    return (("t" if low[-1] in _VOICELESS else "d")
            + ("a" if (vowels and vowels[-1] in _BACK) else "e"))


def _possessive_family():
    return [(code, name) for code, name in _tr_aliases()
            if name.lower().endswith(_POSSESSIVE_HEADS)]


# 88 ACCEPTS: the 22 compounds x {apostrophe, bare} x {singular, plural}. The
# apostrophe column is not decoration - it is the spelling that ALREADY worked
# in country.py and that this guard refused anyway, so it is half the defect.
_BUFFER_LOCATIVE_ACCEPTS = [
    (f"{name}{apo}n{_loc(name)}{person}", code)
    for code, name in _possessive_family()
    for apo in ("'", "")
    for person in ("yım", "yız")
]

# 220 REFUSALS built to reach the buffer, the five in `_SUFFIX_NEAR_MISSES`
# re-spelled on all 22 compounds in both spellings. These are the only inputs
# that can fail the person decision this widening makes: each one gets into the
# buffer AND the locative and is turned away by what follows.
_BUFFER_NEAR_MISS_REFUSALS = [
    (frame.format(f"{name}{apo}n{_loc(name)}"), code)
    for code, name in _possessive_family()
    for apo in ("'", "")
    for frame in ("{}ydım, şimdi döndüm",        # PAST
                  "{}yken buğday ektim",        # while
                  "{}lar, ben burada kaldım",   # 3rd person plural
                  "{}ki gibi sera kurayım",     # the relativiser
                  "{}n fidan getirdim")         # the ablative
]

# 72 REFUSALS for the LENGTH GATE, which is the finding this round produced
# rather than a precaution. An `n?` written straight into `_SELF_TR` admitted
# all 72 of these; `_alias_key`'s gate admits 0.
_SHORT_ALIAS_BUFFER_REFUSALS = [
    (f"{alias}{apo}n{_loc(alias)}{person}", code)
    for code, alias in _tr_aliases()
    if len(engine._normalize_tr(alias)) <= 4
    for apo in ("'", "")
    for person in ("yım", "yız")
]

# OUTSIDE BOTH COUNTS, as every pinned cost in this file is: a cost is a
# sentence we admit and wish we did not, so it is not a refusal the guard
# "passes" by refusing.
_DEMONYM_LOCATIVE_COSTS = [
    ("amerikandayım", 231),
    ("italyandayım", 106),
    ("kenyandayım", 114),
    ("ugandandayım", 226),
]


@pytest.mark.parametrize("text,code", [
    ("Rusya Federasyonu'ndayım", 185),
    ("Rusya Federasyonundayım", 185),
    ("Rusya Federasyonu'ndayız", 185),
    ("Rusya Federasyonundayız", 185),
    ("Dominik Cumhuriyeti'ndeyim", 56),
    ("Dominik Cumhuriyetindeyim", 56),
    ("Solomon Adaları'ndayım", 25),
    ("Ekvator Ginesindeyim", 61),
    ("Amerika Birleşik Devletlerindeyim", 231),
])
def test_a_buffered_locative_places_the_speaker(text, code):
    """THE HALF OF THE ANSWER THIS GUARD WAS MISSING, and the reason it had to
    ship with country.py's half rather than after it. `extract_country` resolved
    every one of these before and this guard refused every one, so the net gain
    to a user was zero: measured over 924 conversations on the 22 compounds, the
    resolver's buffer alone bought 287 resolves and 0 country lines.

    `Rusya Federasyonu'ndayım` IS IN THE LIST ON PURPOSE. The apostrophe
    spelling was never broken in country.py, so it is easy to read this as the
    apostrophe-less fix arriving late - but this guard refused BOTH spellings,
    so the apostrophe user was no better off. He is placed now too."""
    assert engine._states_location(text, engine._code_aliases(code))


def test_every_buffered_locative_in_the_family_places_the_speaker():
    """All 88, derived, because closing the example is not closing the class and
    the nine parametrised cases above are examples. 22 compounds x two spellings
    x singular and plural, each bent into its own harmony."""
    assert len(_BUFFER_LOCATIVE_ACCEPTS) == 88
    missed = [text for text, code in _BUFFER_LOCATIVE_ACCEPTS
              if not engine._states_location(text, engine._code_aliases(code))]
    assert missed == []


@pytest.mark.parametrize("text,code", [
    ("Rusya Federasyonu'ndaydım, şimdi döndüm", 185),
    ("Rusya Federasyonundaydım, şimdi döndüm", 185),
    ("Rusya Federasyonundayken buğday ektim", 185),
    ("Rusya Federasyonundalar, ben burada kaldım", 185),
    ("Rusya Federasyonundaki gibi sera kurayım", 185),
    ("Rusya Federasyonundan fidan getirdim", 185),
])
def test_the_buffered_near_misses_are_still_refused(text, code):
    """`_SUFFIX_NEAR_MISSES` re-spelled with the buffer, which is where this
    widening could actually have broken: each of these reaches the buffer AND
    the locative and then has to be turned away by the letters after it.

    THE DENOMINATOR IS THE POINT, and
    test_the_buffered_refuse_set_can_actually_fail asserts it rather than
    describing it: 220 of these reach the buffer branch and 88 reach the person
    slot itself, against 0 of the shipped 99."""
    assert not engine._states_location(text, engine._code_aliases(code))


def test_the_buffered_refuse_set_can_actually_fail():
    """THE ASSERTION THE PREVIOUS REVISION OF `_SELF_TR`'s COMMENT ASKED FOR, and
    the one this guard has been burned six times for not making: a refuse set
    that cannot reach the rule under test measures nothing, and a zero taken
    over it is worth nothing.

    So the reach is asserted, not the leak alone. Three tiers, because only the
    last is a zero:
      * 220 of the 220 buffered near misses ENTER the buffer branch - the name,
        then `'?n`, then the locative's own letters.
      * 88 of them reach the PERSON SLOT, `…n[dt][ae]y`, where only the person
        vowel refuses them. Those 88 are the past tense and the `-ken` form.
      * 0 of the shipped 99 do either, which is why the old 0/99 licensed
        nothing and why these lists exist.

    AND THE 792-SENTENCE SET FROM country.py's SIDE IS NOT ENOUGH EITHER: those
    sentences put a SPACE after the locative ("…nda çalışan bir dayım var"), so
    all 792 enter the buffer branch and 0 reach the person slot. They are in
    `_TURKISH_REFUSALS`' spirit but they cannot test this decision, which is why
    the near misses had to be written."""
    def enters(text, code):
        folded = engine._normalize_tr(text)
        return any(re.search(r"(?<!\w)" + re.escape(alias) + r"'?n[dt][ae]",
                             folded)
                   for alias in engine._code_aliases(code))

    def person_slot(text, code):
        folded = engine._normalize_tr(text)
        return any(re.search(r"(?<!\w)" + re.escape(alias) + r"'?n[dt][ae]y",
                             folded)
                   for alias in engine._code_aliases(code))

    assert len(_BUFFER_NEAR_MISS_REFUSALS) == 220
    assert sum(1 for t, c in _BUFFER_NEAR_MISS_REFUSALS if enters(t, c)) == 220
    assert sum(1 for t, c in _BUFFER_NEAR_MISS_REFUSALS
               if person_slot(t, c)) == 88
    # and the shipped 99, which is why its zero was vacuous for this change.
    # IT IS LEFT AT 99 ON PURPOSE rather than absorbing these 292: five other
    # measurements in src/engine.py quote that denominator for OTHER decisions
    # (44 of the 99 carry a `-yIm`-shaped word, 4 are a right-boundary shape),
    # and folding a new class into it would restate all of them. These sets are
    # kept beside it the way `_STANDING_COSTS` is.
    assert len(_TURKISH_REFUSALS) == 99
    assert sum(1 for t, c in _TURKISH_REFUSALS if enters(t, c)) == 0
    assert sum(1 for t, c in _TURKISH_REFUSALS if person_slot(t, c)) == 0
    # the leak itself, over the set that can break it
    leaked = [t for t, c in _BUFFER_NEAR_MISS_REFUSALS
              if engine._states_location(t, engine._code_aliases(c))]
    assert leaked == []


def test_the_buffer_is_gated_by_the_name_length():
    """THE FINDING OF THIS ROUND, and it was a REACHABLE leak rather than a
    theoretical one. Writing the buffer as a bare `n?` in `_SELF_TR` admitted
    all 72 of these - every short alias plus `n` plus a locative plus a person -
    and the dearest is `mali`: `mali` + `nda` is the ordinary Turkish word
    "malında" ("in his goods"), and `mali` is also the adjective for fiscal,
    which is why country.py already keeps it in `_AMBIGUOUS_EN`.

    IT REACHED A USER, which is why it is closed rather than noted the way
    `chad`/`jordan` are: "Mali'de buğday verimi nedir" with an earlier user turn
    "tarlamın malındayım" printed Mali's yield figures and asked no province.
    The message resolves Mali on its own, so the only sentence that could PLACE
    the speaker was the spurious one - and `_country_lines` asks every user turn.

    THE GATE IS country.py's OWN `_SHORT`, imported rather than restated: those
    aliases get `_STRICT_SUFFIX` there for exactly this reason, and not one of
    them ends in a 3sg possessive, so none can carry a buffer. The attested
    collision is real (`malında` x5 in the project's Turkish corpus) and the
    firing shape is not (`malındayım` x0 in 10.9M words), so the gate closes a
    class whose instance exists and whose instance cannot fire - the direction
    this guard has been wrong in six times."""
    assert len(_SHORT_ALIAS_BUFFER_REFUSALS) == 72
    leaked = [t for t, c in _SHORT_ALIAS_BUFFER_REFUSALS
              if engine._states_location(t, engine._code_aliases(c))]
    assert leaked == []
    # the gate, asserted where it lives rather than through its effect
    from src.context import country as country_ctx
    assert engine._alias_key("mali", "suffix") == "mali"
    assert engine._alias_key("rusya federasyonu", "suffix") == (
        re.escape("rusya federasyonu") + r"(?:'?n)?")
    assert engine._alias_key("rusya federasyonu", "prefix") == re.escape(
        "rusya federasyonu")
    assert country_ctx._SHORT == 4
    # and the reachable conversation, pinned end to end
    assert engine._states_location("malındayım", engine._code_aliases(133)) \
        is False
    assert engine._country_lines(
        "Mali'de buğday verimi nedir",
        [{"role": "user", "content": "tarlamın malındayım"}]) == []
    # the short alias still places when it takes a locative of its own
    assert engine._states_location("Mali'deyim", engine._code_aliases(133))


@pytest.mark.parametrize("text,code", _DEMONYM_LOCATIVE_COSTS)
def test_a_demonym_locative_places_the_speaker_and_that_is_a_cost(text, code):
    """PINNED AS A COST, and it is the one question this round had to DECIDE
    rather than measure. Ten long aliases have an attested Turkish word at
    `<alias>n` - `amerikan`, `italyan`, `kenyan`, `ugandan` and six more - so
    the buffer makes `amerikandayım` place a speaker in the United States.

    IT IS NOT THE `-lI` QUESTION, although it looks like it. `-lI` was refused
    one commit earlier because a nationality is not a location: "Amerikalıyım"
    predicates the SPEAKER - he is American wherever he stands - and a Dutch
    grower in Antalya says "Hollandalıyım" truthfully. `-ndayım` predicates a
    PLACE and says the speaker is in it, so it is evidence of presence in the
    way `-lI` never was.

    WHAT IT COSTS instead is a misreading, not a wrong category: `-n` on these
    ten is a DEMONYM, and a demonym cannot take a locative without a head noun,
    so the only Turkish reading of "İtalyanda" is "at the Italian('s)".
    Measured: 0 of the 20 constructed forms occur in 10.9M words of the
    project's Turkish corpus, and 8 of the 10 stems are English demonyms that
    reach that corpus through its English abstracts and take no Turkish case
    ending at all.

    ADMITTED ANYWAY, because refusing it needs a rule that reads the word before
    the name to decide whether a head noun is missing - and inference about the
    rest of the sentence is what four waves of this guard took out. The bare
    demonym is still refused, which is the part that would actually be said."""
    assert engine._states_location(text, engine._code_aliases(code))
    assert not engine._states_location(
        text.replace("ndayım", "n").replace("ndeyim", "n"),
        engine._code_aliases(code))


def test_the_buffered_twin_gets_the_twin_verdict():
    """PARITY, which is the right test here and absolute refusal is not. The
    Turkish arm carries no left veto, so "sanki Fransa'dayım gibi" and "babam
    Fransa'dayım diyor" are ADMITTED at this tip - a standing cost of this
    branch, not something the buffer introduces. What the buffer must not do is
    change any of that in either direction.

    So every Turkish sentence the shipped corpus holds is re-spelled onto each
    of the 22 compounds, with the buffer inserted where Turkish puts it - AFTER
    the apostrophe, "Adaları'nda" and never "Adalarin'da" - and the verdict must
    match the original's. 1.760 twins, 0 disagreeing.

    The apostrophe placement is load-bearing in the TEST, not just in the code:
    the first version of this sweep inserted the buffer before the apostrophe
    and reported 44 disagreements that were all its own bug."""
    shapes = []
    for rows in (_SUFFIX_NEAR_MISSES, _PAST_TENSE_REFUSALS,
                 _NATIONALITY_REFUSALS, _SHAPE_NEAR_MISSES, _MERELY_NAMING,
                 _OBJECT_LOCATIVES, _ACTION_LOCATIVES):
        shapes.extend(rows)
    twins = 0
    disagreed = []
    for text, code in shapes:
        folded = engine._normalize_tr(text)
        aliases = sorted(engine._code_aliases(code), key=len, reverse=True)
        hit = next((a for a in aliases if a in folded), None)
        if hit is None:
            continue
        base = engine._states_location(text, engine._code_aliases(code))
        for fcode, name in _possessive_family():
            rewritten = re.sub(
                r"(?<!\w)" + re.escape(hit) + r"('?)",
                lambda m: engine._normalize_tr(name) + (
                    m.group(1) + "n" if m.group(1) else "n"),
                folded, count=1)
            twins += 1
            if engine._states_location(
                    rewritten, engine._code_aliases(fcode)) != base:
                disagreed.append((text, rewritten))
    assert twins >= 1000, twins          # the denominator must be real
    assert disagreed == []


def test_the_guard_patterns_are_scored_through_the_shipped_alias_key():
    """THE COMPOSITION IS READ OUT OF engine, NOT REBUILT - the same rule
    test_the_two_surviving_patterns_hold_the_refuse_set_on_their_own states, now
    applied to the piece that moved. Half of what the Turkish guard matches is
    no longer in its pattern: the buffer and its length gate live in
    `_alias_key`, so a test that passed `re.escape(alias)` would score a regex
    nobody ships - green over a guard that places nobody on
    "Rusya Federasyonundayım", and green too if the length gate were deleted."""
    assert len(engine._GUARDS) == 2
    for guard in engine._GUARDS:
        name, side = guard[0], guard[1]
        for text, code in _BUFFER_NEAR_MISS_REFUSALS + \
                _SHORT_ALIAS_BUFFER_REFUSALS:
            folded = engine._normalize_tr(text)
            for alias in engine._code_aliases(code):
                assert not engine._guard_hits(
                    guard, engine._alias_key(alias, side), folded), (name, text)
