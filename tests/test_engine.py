"""Unit tests for the RAG engine core (deterministic; the LLM, vector store and
embedding clients are all monkeypatched)."""

import json
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


def test_a_country_with_no_crop_named_is_unchanged():
    """The country's NAME only exists on a figure - it is FAOSTAT's label,
    carried on the value - so a question that names no crop has nothing to
    print and keeps today's behaviour."""
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
