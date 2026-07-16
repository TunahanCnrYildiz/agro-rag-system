# Crop-Lexicon Cross-Lingual Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Turkish queries reach English-only crop content by expanding the
query through a deterministic TR→EN crop-name lexicon and fusing results by rank,
replacing the measurably broken LLM translation path.

**Architecture:** `_expand_query` stops calling the chat model and instead returns
extra search queries derived from `CROP_LEXICON` (bare English term + the term
substituted into the original query). `_fuse` switches from raw-score ranking to
RRF, applying the relevance floor per list before ranking. `retrieve_context`
drops its "only when under-filled" trigger and always expands. `_translate_query`
is deleted.

**Tech Stack:** Python, ChromaDB + bge-m3 via LM Studio (embeddings only — no chat
model on the retrieval path any more), pytest.

**Spec:** `docs/superpowers/specs/2026-07-16-crop-lexicon-retrieval-design.md`

## Global Constraints

- No new dependencies.
- Normalisation folds Turkish letters to ASCII **1:1 per character** and lowercases;
  it is used for **detection only**. Substitution always targets the **original** query.
- Matching is **word-boundary** (`(?<!\w)term(?!\w)`), **longest term first**.
- `_fuse` applies the floor (`MIN_RETRIEVAL_RELEVANCE = 0.36`) **per list, before**
  ranking; RRF constant `K = 60`; returns at most `settings.retrieval_k` documents.
- `settings.cross_lingual_retrieval` keeps its name and `True` default; `False`
  ⇒ `_expand_query` returns `[query]`.
- Tests must stay hermetic — no live LM Studio, no live Chroma.
- The 48-product catalog and `match_products` are **not touched**.

## File Structure

- `src/engine.py` — all retrieval changes: `CROP_LEXICON`, `_normalize_tr`,
  `_expand_query` (rewritten), `_fuse` (rewritten to RRF), `retrieve_context`
  (trigger removed), `_translate_query` (deleted).
- `src/config.py` — comment update only; the field stays.
- `tests/test_engine.py` — replace the five translation tests with lexicon tests;
  update the `_fuse` test for RRF.

---

### Task 1: Turkish normalisation helper

**Files:**
- Modify: `src/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Produces: `_normalize_tr(text: str) -> str` — ASCII-folded, lowercased, **same
  length as input**.

- [ ] **Step 1: Write the failing test** (append to `tests/test_engine.py`)

```python
def test_normalize_tr_folds_and_preserves_length():
    assert engine._normalize_tr("Darı") == "dari"
    assert engine._normalize_tr("Gölevez") == "golevez"
    assert engine._normalize_tr("Yağ Palmiyesi") == "yag palmiyesi"
    assert engine._normalize_tr("Tatlı Patates") == "tatli patates"
    # 1:1 per character, so match spans map back onto the original query
    for s in ("Darı", "Gölevez", "Yağ Palmiyesi", "İğne", "ÇELTİK"):
        assert len(engine._normalize_tr(s)) == len(s)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine.py::test_normalize_tr_folds_and_preserves_length -v`
Expected: FAIL with `AttributeError: module 'src.engine' has no attribute '_normalize_tr'`

- [ ] **Step 3: Write minimal implementation** (add to `src/engine.py`, above `_expand_query`)

```python
# Turkish -> ASCII fold, one character in, one character out, so a match span
# found in the normalised text maps straight back onto the original query.
_TR_FOLD = str.maketrans("ıİğĞüÜşŞöÖçÇI", "iigguussooccI")


def _normalize_tr(text: str) -> str:
    """Lowercase + fold Turkish letters to ASCII, for lexicon MATCHING only.

    Never feed the result to the embedder: stripping diacritics from the whole
    query degrades retrieval (measured - it costs the millet rescue).
    """
    return text.translate(_TR_FOLD).lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine.py::test_normalize_tr_folds_and_preserves_length -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Add Turkish ASCII-fold helper for crop lexicon matching"
```

---

### Task 2: Crop lexicon + `_expand_query` rewrite

**Files:**
- Modify: `src/engine.py` (replace `_translate_query` and `_expand_query`)
- Test: `tests/test_engine.py` (delete the five translation tests listed in Step 1)

**Interfaces:**
- Consumes: `_normalize_tr` (Task 1), `settings.cross_lingual_retrieval`.
- Produces: `CROP_LEXICON: dict[str, str]`, `_expand_query(query: str) -> list[str]`
  returning `[query, *extras]` (query first, extras in lexicon-hit order).

- [ ] **Step 1: Delete the obsolete translation tests**

In `tests/test_engine.py`, delete these five tests (they assert LLM translation,
which no longer exists):
`test_expand_query_translates_turkish_to_english`,
`test_expand_query_translates_english_to_turkish`,
`test_expand_query_fallback_on_failure`,
`test_expand_query_skips_noop_translation`,
`test_expand_query_disabled`.

- [ ] **Step 2: Write the failing tests** (append to `tests/test_engine.py`)

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k expand_query -v`
Expected: FAIL — `AttributeError: module 'src.engine' has no attribute 'CROP_LEXICON'`
(or assertion failures from the old translation-based `_expand_query`).

- [ ] **Step 4: Delete `_translate_query`**

Remove the whole `_translate_query` function from `src/engine.py` (the one with
the `max_tokens=512` translation-budget comment). Nothing else calls it.

- [ ] **Step 5: Write the implementation** (replace `_expand_query` in `src/engine.py`)

```python
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
}

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
        match = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized)
        if not match:
            continue
        out.append(english)
        # substitute into the ORIGINAL query: the fold is 1:1, so the span lines
        # up, and the untouched diacritics keep the embedding intact.
        out.append(query[:match.start()] + english + query[match.end():])
    return out
```

Ensure `import re` is present at the top of `src/engine.py` (add it if missing).

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -k expand_query -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Replace LLM query translation with TR->EN crop lexicon"
```

---

### Task 3: RRF fusion

**Files:**
- Modify: `src/engine.py` (`_fuse`)
- Test: `tests/test_engine.py` (replace `test_fuse_dedups_keeping_max_score_and_applies_floor`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `_fuse(result_lists, floor: float, k: int) -> list[Document]` —
  **note the changed return type**: documents only, no scores (RRF scores are not
  comparable to similarity scores and no caller used them).

- [ ] **Step 1: Delete the obsolete fusion test**

Delete `test_fuse_dedups_keeping_max_score_and_applies_floor` from
`tests/test_engine.py` — it asserts max-score fusion, which is exactly what we
are removing.

- [ ] **Step 2: Write the failing tests** (append to `tests/test_engine.py`)

`_Doc(content, source, page)` already exists in this file (all three args
required) — do **not** redefine it.

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k fuse -v`
Expected: FAIL — `test_fuse_ranks_by_rank_not_raw_score` fails (score fusion keeps
the two Turkish chunks), and the others fail on `AttributeError: 'tuple' object
has no attribute 'page_content'` because the old `_fuse` returns `(doc, score)`.

- [ ] **Step 4: Write the implementation** (replace `_fuse` in `src/engine.py`)

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -k fuse -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Fuse retrieval results by rank (RRF) instead of raw score"
```

---

### Task 4: Wire `retrieve_context` — drop the under-fill trigger

**Files:**
- Modify: `src/engine.py:280-308` (`retrieve_context`)
- Modify: `src/config.py:72-75` (comment only)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `_expand_query` (Task 2), `_fuse` (Task 3 — returns Documents, not tuples).

- [ ] **Step 1: Delete the obsolete trigger test**

Delete `test_retrieve_context_skips_translation_when_primary_fills` from
`tests/test_engine.py` (~line 180). It asserts `_expand_query` is **skipped** when
the primary search fills `k` — that is precisely the trigger this task removes,
and it is why cassava failed. `test_retrieve_context_fuses_both_languages` stays:
it still passes under RRF.

- [ ] **Step 2: Write the failing test** (append to `tests/test_engine.py`)

```python
def test_retrieve_context_searches_every_expanded_query(monkeypatch):
    seen = []

    def fake_search(store, query, k):
        seen.append(query)
        return [(_Doc(f"chunk for {query}", "x.pdf", 1), 0.50)]

    monkeypatch.setattr(engine, "_get_retriever_store", lambda: object())
    monkeypatch.setattr(engine, "_search", fake_search)
    monkeypatch.setattr(engine, "_expand_query", lambda q: [q, "cassava"])

    ctx = engine.retrieve_context("Manyok gübreleme", k=4)

    # expansion is unconditional now: the primary list filling k must NOT skip it
    assert seen == ["Manyok gübreleme", "cassava"]
    assert "chunk for cassava" in ctx
    assert "[Kaynak: x.pdf, s.1]" in ctx
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_engine.py::test_retrieve_context_searches_every_expanded_query -v`
Expected: FAIL — `seen == ["Manyok gübreleme"]` only, because the current code
expands only when `len(kept) < k`.

- [ ] **Step 4: Write the implementation** (replace the body of `retrieve_context`)

```python
def retrieve_context(query: str, k: int | None = None) -> str:
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

    result_lists = [_search(store, q, k) for q in _expand_query(query)]

    parts: list[str] = []
    for d in _fuse(result_lists, MIN_RETRIEVAL_RELEVANCE, k):
        src = d.metadata.get("source", "?")
        page = d.metadata.get("page", "?")
        parts.append(f"[Kaynak: {src}, s.{page}]\n{d.page_content}")
    return "\n\n---\n\n".join(parts)
```

- [ ] **Step 5: Update the config comment** (`src/config.py`, replace lines 72-75)

```python
    # Cross-lingual retrieval: expand the query through the TR->EN crop-name
    # lexicon (see engine.CROP_LEXICON) and fuse the extra searches by rank, so a
    # Turkish query reaches crop content that exists only in the English corpus.
    # Set False to restore single-query retrieval.
    cross_lingual_retrieval: bool = Field(default=True)
```

- [ ] **Step 6: Run the full unit suite**

Run: `python -m pytest -q`
Expected: PASS — all tests green. Any failure here is a real break: fix before
committing.

- [ ] **Step 7: Commit**

```bash
git add src/engine.py src/config.py tests/test_engine.py
git commit -m "Expand every query through the lexicon; drop the under-fill trigger"
```

---

### Task 5: Verify against the eval and record the outcome

**Files:**
- Modify: `evals/eval_set.py` (comment block above the gap cases only)

**Interfaces:**
- Consumes: the whole implementation.

- [ ] **Step 1: Run the fast eval**

Requires LM Studio serving `text-embedding-bge-m3`.

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --fast`

Expected, per the spec's measurement (**5 of 6 gaps fixed, 0 regressions**):
- `cassava_nutrition_tr`, `gap_cacao_tr`, `gap_sweetpotato_tr`, `gap_oilpalm_tr`,
  `gap_millet_tr` → **PASS** (were FAIL)
- `gap_taro_tr` → still **FAIL** (known, documented in the spec)
- `coffee_tr_control` and every other case → **PASS**
- Summary: **30/31 cases passed**

If any previously-passing case now fails, that is a regression the measurement did
not predict: stop and investigate rather than adjusting the expectation.

- [ ] **Step 2: Update the gap-cases comment** (`evals/eval_set.py`)

Replace the comment block above `gap_cacao_tr` (the one starting
"--- cross-lingual GAP crops") with:

```python
    # --- cross-lingual gap crops: TR query, content exists ONLY in the English
    # FAO/OpenAlex corpus. Fixed 2026-07-16 by the TR->EN crop lexicon
    # (engine.CROP_LEXICON) + RRF fusion; they FAILED before it. Kept as the
    # regression guard for that path: if the lexicon or the fusion breaks, these
    # go red while the same-language cases stay green.
    # gap_taro_tr is the known remaining gap - bare "taro" embeds too weakly to
    # surface the content (see the design spec).
```

- [ ] **Step 3: Commit**

```bash
git add evals/eval_set.py
git commit -m "Note lexicon fix in gap-crop eval cases"
```

---

### Task 6: Update the README retrieval note

**Files:**
- Modify: `README.md`

**Note:** README currently has **no** cross-lingual/translation passage (verified:
`grep -n -i "cross-lingual\|translat" README.md` returns nothing) — the previous
feature was never documented there. So this task **adds** a note rather than
rewriting one; there is nothing stale to delete.

- [ ] **Step 1: Locate the Architecture section**

Run: `grep -n "^## Architecture" README.md`
The note goes at the end of that section, before `## Safety guardrails`.

- [ ] **Step 2: Add the passage**

```markdown
**Cross-lingual retrieval.** The corpus is ~half Turkish, ~half English. A Turkish
query about a crop covered only in the English sources (FAO/OpenAlex) would
otherwise never reach it — generic Turkish fertilization chunks clear the
relevance floor and fill the result slots first. Each query is expanded through a
TR→EN crop-name lexicon (`engine.CROP_LEXICON`, e.g. `manyok → cassava`) and the
extra searches are fused by rank (RRF). It is deterministic and LLM-free; toggle
with `cross_lingual_retrieval`.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document lexicon-based cross-lingual retrieval in README"
```
