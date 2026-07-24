# NOPRODUCT Backstop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Suppress product recommendations when the answer is clearly about a non-product activity, without depending on the model emitting the `[NOPRODUCT]` marker.

**Architecture:** A deterministic, LLM-free function `_looks_non_product(answer)` inspects the answer text and returns True only when it names a non-product activity (pruning, grafting, storage, …) AND carries no nutrition term. It is wired into both `answer()` and `stream_answer()` beside the existing marker check. The marker stays the primary signal; this is a second line of defence.

**Tech Stack:** Python 3.11+, the `openai` SDK, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-24-noproduct-backstop-design.md`

## Global Constraints

- **No cosine, no extra LLM call.** The backstop is deterministic keyword matching over the answer text. Cosine threshold tuning is measured-dead (`do-not-rechase`).
- **Direction is the SAFE framing:** suppress only when the answer is CLEARLY non-product. An answer is suppressed iff it contains a non-product activity term AND no nutrition term. A nutrition answer must never be suppressed — that is the one new regression risk.
- **The marker stays primary and `SYSTEM_PROMPT` is unchanged.** The backstop completes the marker, it does not replace it.
- **Matching is LEFT-boundary only** (`(?<!\w){stem}` over folded text), NOT the `_expand_query` pattern. `_TR_SUFFIXES` carries only noun case-endings, and the full pattern's right boundary blocks derivational/verbal forms the backstop must catch — measured 2026-07-24: with the full pattern `gubre` does NOT match "gübreleyin". Left-boundary-only catches the derivational tail while still blocking mid-word-from-left hits (`stor`↛"restore", `sula`↛"pusula").
- **Both sides must be folded.** `_normalize_tr` lowercases and folds Turkish letters to ASCII (`ş→s`, `ü→u`, `ç→c`, `ğ→g`, `ı→i`, `ö→o`). `_contains_any` folds each stem before matching. A raw (diacritic) stem compared against folded text silently never matches — a dead gate that looks green.
- **The exact stems were chosen by empirical probing** (2026-07-24), not intuition: `aşıla` not `aşı` (`aşı`→"aşırı"), `prune`/`pruning` not `prun` (`prun`→"Prunus"), `budam` not `buda` (`buda`→"budala"). Do not "simplify" them back.
- **Term lists start SMALL**, bounded by the categories `SYSTEM_PROMPT` already enumerates (`config.py:247-249`). No speculative terms. A measured gap is a *finding*, not a cue to inflate the lists.
- Existing user-facing Turkish strings in `engine.py` are ASCII-only in source (`Uzgunum`), but the term stems and test fixtures use real Turkish text (the answer text is real Turkish). That is fine — `_normalize_tr` folds it.
- CI runs `pytest -q` only. No test may make a network call. Run everything from the repo root.
- Baseline before this work: `pytest -q` = **210 passing**.

---

### Task 1: The matcher, the rule, and the two term sets

**Files:**
- Modify: `src/engine.py` (add after `_expand_query`'s machinery, near `CROP_LEXICON` / `_TR_SUFFIXES` around `engine.py:254-295`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `_normalize_tr` and `_TR_SUFFIXES` (already in `engine.py`).
- Produces:
  - `engine._NON_PRODUCT_ACTIVITY: tuple[str, ...]` and `engine._NUTRITION_TERMS: tuple[str, ...]`
  - `engine._contains_any(text: str, stems: tuple[str, ...]) -> bool`
  - `engine._looks_non_product(answer_text: str) -> bool`

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k "contains_any or looks_non_product" -v`
Expected: FAIL — `engine` has no attribute `_contains_any` / `_looks_non_product` / `_NON_PRODUCT_ACTIVITY`.

- [ ] **Step 3: Add the term sets, the matcher, and the rule**

In `src/engine.py`, after the `_expand_query` block (the machinery around `engine.py:254-295`), add:

```python
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
    "tozlaş", "pollinat",                  # pollination (NOT "döllen": ambiguous)
    "sula", "irrigat",                     # irrigation practice
    "çoğalt", "propagat",                  # propagation
    "hasat", "depola", "muhafaza",         # harvest / storage
    "harvest", "storag",                   # (NOT "stor": hits "restore")
    "zararlı", "yabancı ot", "ilaçla",     # pest / weed control
    "pesticid", "weed",
)
# If ANY of these appears, never suppress - the answer is about nutrition. This is
# the guarantee that a working nutrition case is never regressed.
_NUTRITION_TERMS = (
    "gübre", "besin", "besle", "azot", "fosfor", "potasyum", "npk", "doz",
    "kompost", "verimli",
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
```

Confirm `re` is already imported at the top of `engine.py` (it is — `_expand_query` uses `re.search`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -k "contains_any or looks_non_product" -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Full suite and commit**

Run: `python -m pytest -q`
Expected: 217 passed (210 + 7).

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Add marker-independent product-suppression backstop (rule + matcher + term sets)"
```

---

### Task 2: Wire the backstop into `answer()`

**Files:**
- Modify: `src/engine.py:633-638` (`answer()`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `engine._looks_non_product` from Task 1.
- Produces: `answer()` clears `products` when `_looks_non_product(answer_text)` is True, in addition to the existing marker/off-scope checks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k "non_product_without_a_marker or nutrition_answer_without_a_marker" -v`
Expected: the suppression test FAILS (products still `[P]` — backstop not wired); the nutrition test passes already (nothing suppresses it yet).

- [ ] **Step 3: Wire the backstop**

In `src/engine.py`, in `answer()`, change:

```python
    answer_text, off_scope, no_product = _strip_markers(answer_text)
    if off_scope or no_product:
        # off-scope refusal, or an in-scope question the fertilizer catalog
        # cannot answer (pruning, pests, storage...) - see the product intent
        # gate spec.
        products = []
```

to:

```python
    answer_text, off_scope, no_product = _strip_markers(answer_text)
    if off_scope or no_product or _looks_non_product(answer_text):
        # off-scope refusal; or an in-scope non-nutrition question (pruning,
        # pests, storage...). The marker is the primary signal; _looks_non_product
        # backstops a model that did not emit it - see the backstop spec.
        products = []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -k "non_product_without_a_marker or nutrition_answer_without_a_marker" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Full suite and commit**

Run: `python -m pytest -q`
Expected: 219 passed (217 + 2).

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Wire the product-suppression backstop into answer()"
```

---

### Task 3: Wire the backstop into `stream_answer()` with a full-answer accumulator

**Files:**
- Modify: `src/engine.py` (`stream_answer()`, the loop at `engine.py:662-731` and the product gate at `engine.py:737`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `engine._looks_non_product` from Task 1.
- Produces: `stream_answer()` accumulates the full streamed answer and suppresses the products event when `_looks_non_product(full_answer)` is True.

**Why an accumulator:** after warmup the loop yields each `delta` and discards it, so the full answer is not retained anywhere. The backstop must see the whole answer (an activity term can arrive after warmup), so the stream must accumulate it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
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
        lambda: _fake_stream_llm([head, "Once kuru dallari budayin."]))
    out = "".join(engine.stream_answer("Nasil yapilir?"))
    assert '"type": "products"' not in out           # suppressed on the late term
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k "stream_answer_suppresses_products_when_non_product or backstop_sees_the_whole" -v`
Expected: both suppression tests FAIL — `'"type": "products"'` is still present (no accumulator, gate not wired). The nutrition test passes already.

- [ ] **Step 3: Add the accumulator**

In `src/engine.py`, in `stream_answer()`, initialise the accumulator next to the other state (near `engine.py:662-669`), adding one line after `has_advice = True`:

```python
    full_answer = ""    # the complete streamed answer, for the backstop
```

Then accumulate at each answer-bearing yield. In the streaming loop, change the warmed branch:

```python
            if warmed:
                yield _sse({"type": "token", "content": delta})
                emitted = True
                continue
```

to:

```python
            if warmed:
                full_answer += delta
                yield _sse({"type": "token", "content": delta})
                emitted = True
                continue
```

and the warmup-reached branch:

```python
            if len(clean) >= _STREAM_WARMUP:
                yield _sse({"type": "token", "content": clean})
                emitted = True
                warmed = True
                buffer = ""
```

to:

```python
            if len(clean) >= _STREAM_WARMUP:
                full_answer += clean
                yield _sse({"type": "token", "content": clean})
                emitted = True
                warmed = True
                buffer = ""
```

In the not-warmed fallback (around `engine.py:717-719`), change:

```python
        if clean:
            yield _sse({"type": "token", "content": clean})
            emitted = True
```

to:

```python
        if clean:
            full_answer += clean
            yield _sse({"type": "token", "content": clean})
            emitted = True
```

In the not-emitted fallback (around `engine.py:730-731`), change:

```python
        if clean:
            yield _sse({"type": "token", "content": clean})
```

to:

```python
        if clean:
            full_answer += clean
            yield _sse({"type": "token", "content": clean})
```

- [ ] **Step 4: Wire the gate**

In `src/engine.py`, change the product-emit gate (around `engine.py:737`):

```python
    if not (off_scope or no_product) and has_advice:
```

to:

```python
    if (not (off_scope or no_product) and has_advice
            and not _looks_non_product(full_answer)):
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -k "stream_answer" -v`
Expected: PASS, including the pre-existing streaming tests (marker split across chunks, length-truncation recovery, clean short answer, provider/model wiring).

- [ ] **Step 6: Full suite and commit**

Run: `python -m pytest -q`
Expected: 222 passed (219 + 3).

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Wire the product-suppression backstop into stream_answer() with a full-answer accumulator"
```

---

### Task 4: Local no-regression validation

**Files:**
- Modify: `docs/superpowers/2026-07-23-provider-portability-findings.md` (append a validation note)

**Interfaces:**
- Consumes: the wired backstop from Tasks 2-3.
- Produces: recorded evidence that the local model's behaviour did not regress.

**Prerequisite:** LM Studio running with `gemma-4-12b-qat` (chat) and `bge-m3` (embedding), as for any local eval. Eval runs are slow (~20-30s per case) and only one may run at a time.

**Why this proves only safety, not efficacy:** locally the marker fires, so the backstop is mostly inert. This run shows it does no harm. Efficacy is the hosted re-measurement (Task 5).

- [ ] **Step 1: Run the full local eval**

Run: `python -m evals.run_eval`
Expected: the run completes. Record the summary line.

- [ ] **Step 2: Check for regression against the 2026-07-24 baseline**

The baseline (`.superpowers/sdd/phase0-baseline.txt`) was **53/54**, with **product-gating 54/54**. The backstop must not lower product-gating and must not turn any previously-passing case red.

- If product-gating stays **54/54** and the panel stays **53/54** (the one red still `quant_wheat_nitrogen_dose`, a known single-run flake, not a product case): **PASS — no regression.**
- If product-gating drops, a nutrition case was wrongly suppressed. That is a real regression: the term lists are too aggressive. **Stop and report** — do not adjust to green without surfacing it; the fix is to narrow the activity terms or widen the nutrition terms, and that decision is the user's.

- [ ] **Step 3: Record the result**

Append to `docs/superpowers/2026-07-23-provider-portability-findings.md`, under a new heading `## NOPRODUCT backstop — local no-regression check (2026-07-24)`: the eval summary line, the product-gating rate, and the explicit statement of whether any case regressed.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/2026-07-23-provider-portability-findings.md
git commit -m "Record local no-regression check for the product-suppression backstop"
```

---

### Task 5: Hosted efficacy re-measurement (gated on OpenRouter quota)

**Files:**
- Modify: `docs/superpowers/2026-07-23-provider-portability-findings.md` (append the efficacy result)

**Interfaces:**
- Consumes: the wired backstop; the `--provider openrouter --model` harness.
- Produces: the recorded efficacy result — improvement, or a finding.

**This task is gated on the OpenRouter free-tier quota (50 req/day) being available, and on `OPENROUTER_API_KEY` being present in `.env`.** It cannot run in the same day as another 54-case hosted run. If quota is unavailable, leave this task open and stop after Task 4 — the code is complete and safe regardless.

- [ ] **Step 1: Confirm quota is available**

Run:
```bash
python -c "import json,urllib.request; from src.config import settings; \
r=urllib.request.Request('https://openrouter.ai/api/v1/auth/key', headers={'Authorization':'Bearer '+settings.openrouter_api_key.strip()}); \
print('usage_daily:', json.load(urllib.request.urlopen(r,timeout=30))['data'].get('usage_daily'))"
```
Expected: `usage_daily: 0` (a full day's budget). If not near 0, stop — a 54-case run needs the headroom.

- [ ] **Step 2: Re-run the hosted model**

Run: `python -m evals.run_eval --provider openrouter --model "google/gemma-4-26b-a4b-it:free"`
Expected: the run completes with the `[openrouter:google/gemma-4-26b-a4b-it:free]` stamp.

- [ ] **Step 3: Compare product-gating against the pre-backstop 30/52**

The pre-backstop hosted run scored **product-gating 30/52** with **22 `products='none'` failures** (`docs/superpowers/2026-07-24-phase1-gemma4-26b-raw.txt`).

- If product-gating improves materially (the `products='none'` failures shrink): **the backstop works across models — the efficacy the whole task existed for.**
- If it does not improve: **that is a finding, not a bug.** The keyword approach did not transfer to the answer either. Record it plainly; do NOT inflate the term lists to force it green (the project's iron rule). A non-improvement means the model's non-product answers do not carry the enumerated activity terms — worth knowing before any further attempt.

- [ ] **Step 4: Record the result and commit**

Append the before/after product-gating numbers and the verdict (improvement or finding) to `docs/superpowers/2026-07-23-provider-portability-findings.md`.

```bash
git add docs/superpowers/2026-07-23-provider-portability-findings.md
git commit -m "Record hosted efficacy re-measurement for the product-suppression backstop"
```

---

## Post-plan checks

- [ ] `python -m pytest -q` green at 222 (210 baseline + 12 new).
- [ ] `git diff --name-only main..HEAD -- src/` shows only `engine.py`.
- [ ] `SYSTEM_PROMPT` in `config.py` is unchanged (`git diff main..HEAD -- src/config.py` is empty).
- [ ] The local no-regression check (Task 4) recorded product-gating 54/54.
