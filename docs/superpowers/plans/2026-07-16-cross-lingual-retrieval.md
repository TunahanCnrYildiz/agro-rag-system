# Cross-Lingual Retrieval — Implementation Plan

**Goal:** Bridge the TR/EN corpus split by translating each query to the other
major language and fusing retrieval results, so Turkish queries reach the English
content (and vice-versa).

**Spec:** `docs/superpowers/specs/2026-07-16-cross-lingual-retrieval-design.md`

**Approach:** Add `_translate_query`, `_expand_query`, `_fuse` to `src/engine.py`;
rewrite `retrieve_context` to expand→retrieve-per-query→fuse. Add a config toggle.
TDD with a mocked LLM so tests stay hermetic (no live LM Studio).

## Global constraints
- No new dependencies (LM Studio chat + bge-m3 embedding only).
- Translation is temperature-0, `max_tokens<=100`, output-only prompt.
- Fusion dedups by `Document.page_content`, keeps max score, applies the 0.36
  floor (`MIN_RETRIEVAL_RELEVANCE`), returns up to `settings.retrieval_k`.
- Any translation failure → single-query fallback `[query]`.

---

### Task 1: Config toggle

- Add to `src/config.py` `Settings`:
  ```python
  # Cross-lingual retrieval: translate the query to the other major corpus
  # language (TR<->EN) and fuse results, so a query reaches content stored in
  # the other language. Set False to restore single-query retrieval.
  cross_lingual_retrieval: bool = Field(default=True)
  ```
- Commit: `feat: add cross_lingual_retrieval config toggle`

---

### Task 2: `_expand_query` + `_translate_query` (TDD)

**Test first** (append to `tests/test_engine.py`):
```python
def test_expand_query_translates_turkish_to_english(monkeypatch):
    seen = {}
    def fake_tr(q, target):
        seen["target"] = target
        return "grape pruning"
    monkeypatch.setattr(engine, "_translate_query", fake_tr)
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    out = engine._expand_query("asma budama")
    assert out == ["asma budama", "grape pruning"]
    assert seen["target"] == "English"

def test_expand_query_translates_english_to_turkish(monkeypatch):
    monkeypatch.setattr(engine, "_translate_query", lambda q, t: "asma budama")
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    assert engine._expand_query("grape pruning")[1] == "asma budama"

def test_expand_query_fallback_on_failure(monkeypatch):
    def boom(q, t): raise RuntimeError("no llm")
    monkeypatch.setattr(engine, "_translate_query", boom)
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    assert engine._expand_query("asma budama") == ["asma budama"]

def test_expand_query_disabled(monkeypatch):
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", False)
    assert engine._expand_query("asma budama") == ["asma budama"]

def test_expand_query_skips_noop_translation(monkeypatch):
    monkeypatch.setattr(engine, "_translate_query", lambda q, t: "asma budama")
    monkeypatch.setattr(engine.settings, "cross_lingual_retrieval", True)
    # translation identical to input -> no second query
    assert engine._expand_query("asma budama") == ["asma budama"]
```

**Then implement** (in `src/engine.py`, near `retrieve_context`):
```python
def _translate_query(query: str, target_lang: str) -> str:
    """Translate a search query to target_lang via the chat model (output-only,
    deterministic). Raises on LLM error - the caller handles fallback."""
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
        max_tokens=100,
    )
    return (completion.choices[0].message.content or "").strip()


def _expand_query(query: str) -> list[str]:
    """Return [query, translation] to bridge the TR/EN corpus split, or [query]
    if cross-lingual retrieval is off or translation is unavailable/a no-op."""
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
```

- Run: `python -m pytest tests/test_engine.py -k expand_query -v` → PASS
- Commit: `feat: add cross-lingual query expansion (translate to other language)`

---

### Task 3: `_fuse` + `retrieve_context` rewrite (TDD)

**Test first** (append to `tests/test_engine.py`; reuses `_Doc`/`_Store`):
```python
def test_fuse_dedups_keeping_max_score_and_applies_floor():
    d_good = _Doc("good chunk", "a.pdf", 1)
    d_dup = _Doc("good chunk", "a.pdf", 1)      # same content, different list
    d_noise = _Doc("noise", "b.pdf", 2)
    fused = engine._fuse(
        [[(d_good, 0.40)], [(d_dup, 0.55), (d_noise, 0.20)]],
        floor=0.36, k=4,
    )
    contents = [d.page_content for d, _ in fused]
    assert contents == ["good chunk"]           # noise dropped, dup collapsed
    assert fused[0][1] == 0.55                   # max score kept

class _MultiStore:
    """Returns different results per query, to prove both are retrieved+fused."""
    def __init__(self, mapping): self.mapping = mapping
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
    assert "tr chunk" in ctx and "en chunk" in ctx      # both languages surfaced
    assert "[Kaynak: ia_2.pdf, s.5]" in ctx
```

**Also update the two existing hermetic tests** so the new translation step is
not exercised against a live LLM:
```python
# in test_retrieve_context_filters_below_threshold and
# test_retrieve_context_empty_when_store_unavailable, add:
    monkeypatch.setattr(engine, "_expand_query", lambda q: [q])
```

**Then implement** — replace the body of `retrieve_context`:
```python
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


def retrieve_context(query: str, k: int | None = None) -> str:
    """Return concatenated botany chunks relevant to the query (across the TR/EN
    corpus split via query expansion), or "" if nothing clears the floor."""
    k = k or settings.retrieval_k
    store = _get_retriever_store()
    if store is None:
        return ""
    result_lists = []
    for q in _expand_query(query):
        try:
            result_lists.append(store.similarity_search_with_relevance_scores(q, k=k))
        except Exception as exc:  # noqa: BLE001
            print(f"[engine] retrieval failed: {exc}")
    parts = []
    for d, _score in _fuse(result_lists, MIN_RETRIEVAL_RELEVANCE, k):
        src = d.metadata.get("source", "?")
        page = d.metadata.get("page", "?")
        parts.append(f"[Kaynak: {src}, s.{page}]\n{d.page_content}")
    return "\n\n---\n\n".join(parts)
```

- Run: `python -m pytest tests/test_engine.py -v` → all PASS
- Run: `python -m pytest -q` → full suite green
- Commit: `feat: fuse cross-lingual retrieval results in retrieve_context`

---

### Task 4: Live verification + measurement

- **Diagnostic before/after:** `python -m evals.inspect_retrieval --queries hard`
  → confirm the Turkish `bordo` / `sigatoka`-style rows now clear more chunks at
  higher scores than the 2026-07-16 baseline (0/6, 2/6).
- **Quality gate:** `python -m evals.run_eval` → must stay **25/25** (off-scope
  still empty/refused, guardrail intact).
- If off-scope regresses (translation surfaces spurious chunks), tighten the
  translate prompt or rely on the floor; do not lower the floor.
- No commit unless a fix was needed (code already committed in Tasks 1-3).

## Notes for the implementer
- `retrieve_context` is called by `answer()` and `stream_answer()`; both already
  monkeypatch it in their own tests, so they're unaffected.
- Keep the translate prompt short and output-only; a chatty model that adds
  "Here is the translation:" would pollute the second query (the floor still
  guards, but it wastes the retrieval).
