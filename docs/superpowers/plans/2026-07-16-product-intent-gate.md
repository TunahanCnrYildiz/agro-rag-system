# Product Intent Gate ([NOPRODUCT]) Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop recommending fertilizer for questions fertilizer cannot answer
(pruning, grafting, ventilation, pollination, storage, disease, pesticides), by
letting the LLM flag them with a `[NOPRODUCT]` marker the app strips.

**Architecture:** Extend the existing `[OFFSCOPE]` marker pattern. The system
prompt gains a `[NOPRODUCT]` rule; `_strip_offscope` generalises to
`_strip_markers`, returning both flags; `answer()` and `stream_answer()` clear
the product list when either fires. No new call, no new component, no latency.

**Tech Stack:** Python, OpenAI-compatible client against local LM Studio
(`gemma-4-12b-qat`), pytest.

**Spec:** `docs/superpowers/specs/2026-07-16-product-intent-gate-design.md`

## Global Constraints

- No new dependencies, no second LLM call.
- Markers are matched **case-insensitively** at the **start** of the reply, after
  `lstrip()`, and stripped along with trailing `" :\n\t"` — same as today.
- When no marker is present, the text must be returned **unchanged** (not
  lstripped) — today's `_strip_offscope` behaviour, relied on by
  `test_strip_offscope_no_marker`.
- `stream_answer`'s decision point must use the LONGEST marker:
  `[NOPRODUCT]` (11) vs `[OFFSCOPE]` (10).
- Tests stay hermetic — no live LM Studio, no live Chroma.
- Do NOT touch retrieval, `MIN_PRODUCT_SIMILARITY`, or the catalog.
- Do NOT relax eval expectations to make things green.

## File Structure

- `src/engine.py` — `_NOPRODUCT_MARKER`, `_strip_markers` (replaces
  `_strip_offscope`), `answer()`, `stream_answer()`.
- `src/config.py` — the `# PRODUCT RECOMMENDATIONS` prompt section.
- `tests/test_engine.py` — replace the two `_strip_offscope` tests; add
  `_strip_markers` + suppression tests.

---

### Task 1: `_strip_markers` (replaces `_strip_offscope`)

**Files:**
- Modify: `src/engine.py:415-424`
- Test: `tests/test_engine.py:5` (import), `:30-36` (the two existing tests)

**Interfaces:**
- Produces: `_strip_markers(text: str) -> tuple[str, bool, bool]` returning
  `(clean_text, off_scope, no_product)`. `_strip_offscope` is REMOVED.

- [ ] **Step 1: Update the import and replace the two existing tests**

In `tests/test_engine.py` line 5, change:
```python
from src.engine import _cosine, _strip_offscope, detect_language
```
to:
```python
from src.engine import _cosine, _strip_markers, detect_language
```

Then replace `test_strip_offscope_marker` and `test_strip_offscope_no_marker`
(lines 30-36) with:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k strip_markers -v`
Expected: FAIL at import — `ImportError: cannot import name '_strip_markers' from 'src.engine'`

- [ ] **Step 3: Write the implementation**

In `src/engine.py`, replace lines 415-424 (`_OFFSCOPE_MARKER` and
`_strip_offscope`) with:

```python
_OFFSCOPE_MARKER = "[OFFSCOPE]"
_NOPRODUCT_MARKER = "[NOPRODUCT]"
# stream_answer buffers until it can (dis)confirm a marker - size off the longest
_LONGEST_MARKER = max(len(_OFFSCOPE_MARKER), len(_NOPRODUCT_MARKER))


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -k strip_markers -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Generalise the offscope marker stripper to handle [NOPRODUCT]"
```

---

### Task 2: Suppress products on either marker in `answer()` and `stream_answer()`

**Files:**
- Modify: `src/engine.py:445-448` (`answer`), `:461-499` (`stream_answer`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `_strip_markers`, `_LONGEST_MARKER` (Task 1).

- [ ] **Step 1: Write the failing test** (append to `tests/test_engine.py`, next
      to `test_answer_suppresses_products_on_offscope`)

`_fake_llm(content)` already exists at `tests/test_engine.py:130` — reuse it, do
not redefine. Mirror the patching style of the neighbouring `answer()` tests
exactly (`lambda m: ...` for `retrieve_context`, `lambda m, c: ...` for
`match_products`, positional `RecommendedProduct("P", "url")`).

Only ONE new test is needed here: the "no marker keeps products" case is already
covered by the existing `test_answer_keeps_products_in_scope` (line 164) — do not
add a duplicate.

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k "noproduct or keeps_products" -v`
Expected: `test_answer_suppresses_products_on_noproduct` FAILS (products still
returned, `[NOPRODUCT]` still in the text — `answer()` only checks the off-scope
flag). `test_answer_keeps_products_in_scope` must already PASS and keep passing.

- [ ] **Step 3: Update `answer()`**

In `src/engine.py`, replace:
```python
    answer_text, off_scope = _strip_offscope(answer_text)
    if off_scope:
        products = []  # no product suggestions under an off-scope refusal
```
with:
```python
    answer_text, off_scope, no_product = _strip_markers(answer_text)
    if off_scope or no_product:
        # off-scope refusal, or an in-scope question the fertilizer catalog
        # cannot answer (pruning, pests, storage...) - see the product intent
        # gate spec.
        products = []
```

- [ ] **Step 4: Update `stream_answer()`**

Replace the marker-buffering block. The comment, the flag init, the decision
threshold and both `_strip_offscope` calls all change:

```python
    # Buffer the opening tokens so we can detect+strip a leading control marker
    # before streaming it to the client, and drop products if one fired.
    off_scope = False
    no_product = False
    buffer = ""
    checked = False
```

Decision point — replace:
```python
            if len(buffer.lstrip()) >= len(_OFFSCOPE_MARKER) or len(buffer) > 40:
                clean, off_scope = _strip_offscope(buffer)
```
with:
```python
            if len(buffer.lstrip()) >= _LONGEST_MARKER or len(buffer) > 40:
                clean, off_scope, no_product = _strip_markers(buffer)
```

Leftover flush — replace:
```python
    if not checked and buffer:
        clean, off_scope = _strip_offscope(buffer)
```
with:
```python
    if not checked and buffer:
        clean, off_scope, no_product = _strip_markers(buffer)
```

Product emission — replace:
```python
    if not off_scope:
```
with:
```python
    if not (off_scope or no_product):
```

- [ ] **Step 5: Cover `stream_answer` — the PRODUCTION path**

`/api/chat` uses `stream_answer` whenever `stream=true` (`src/main.py:132-137`),
but **no test touches its marker handling** and the eval only calls `answer()`.
Without this test, a broken Step 4 edit would leave the eval green at 30/31 while
real users still see fertilizer under a pruning answer. Append to
`tests/test_engine.py`:

```python
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
    assert "Azot eksikligi olabilir." in out
```

Run: `python -m pytest tests/test_engine.py -k stream_answer -v`
Expected: PASS (2 tests). If `test_stream_answer_suppresses_products_on_noproduct`
fails, the Step 4 edits are wrong — fix them, not the test.

- [ ] **Step 6: Run the full unit suite**

Run: `python -m pytest -q`
Expected: PASS, all green. Any failure is real — fix it, do not skip.

- [ ] **Step 7: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Hide products when the answer is flagged [NOPRODUCT]"
```

---

### Task 3: Teach the model when to emit `[NOPRODUCT]`

**Files:**
- Modify: `src/config.py:181-185` (the `# PRODUCT RECOMMENDATIONS` block)

**Interfaces:**
- Consumes: nothing. Produces the marker `answer()`/`stream_answer()` already act on.

- [ ] **Step 1: Replace the prompt section**

In `src/config.py`, replace:
```
# PRODUCT RECOMMENDATIONS
- You may be given a list of the company's catalog products below. Only refer
  to products that appear in that list. Never invent product names or links.
- Weave relevant products naturally into the advice as optional suggestions,
  not prescriptions.
```
with:
```
# PRODUCT RECOMMENDATIONS
- You may be given a list of the company's catalog products below. Only refer
  to products that appear in that list. Never invent product names or links.
- Weave relevant products naturally into the advice as optional suggestions,
  not prescriptions.
- The catalog is FERTILIZER / plant-nutrition products ONLY. Recommend them only
  when the question is actually about plant nutrition or fertilization (nutrient
  deficiency, feeding, soil fertility, compost, yield via nutrition).
- If the question is in scope for plants but NOT about nutrition - e.g. pruning,
  grafting, ventilation, pollination, irrigation practice, propagation,
  harvesting/storage, or disease/pest/weed control - the catalog cannot answer
  it. Then you MUST: (a) not mention any product anywhere in your reply, and
  (b) begin your reply with the exact marker [NOPRODUCT] (with the square
  brackets). The app strips it and hides the list. Answer the question normally
  after the marker.
- Never use [NOPRODUCT] on a nutrition/fertilization question.
```

- [ ] **Step 2: Verify the prompt still renders**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); from src.config import settings; from src import engine; m = engine._build_messages('q', [], 'CTX', []); print('[NOPRODUCT]' in m[0]['content'])"
```
Expected: `True`

- [ ] **Step 3: Run the full unit suite**

Run: `python -m pytest -q`
Expected: PASS (the prompt is templated; no test asserts its exact text).

- [ ] **Step 4: Commit**

```bash
git add src/config.py
git commit -m "Tell the model to flag [NOPRODUCT] on non-nutrition questions"
```

---

### Task 4: Verify against the full eval

**Files:** none (verification only).

- [ ] **Step 1: Run the full eval**

Needs LM Studio serving BOTH the embedding model (`text-embedding-bge-m3`) and
the chat model. Takes ~15-20 minutes.

```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval > /tmp/eval.txt 2>&1
grep -E "FAIL|cases passed|retrieval:" /tmp/eval.txt
```

Baseline to beat (measured 2026-07-16 with the catalog fix in):
```
=== 19/31 cases passed ===
  retrieval: 31/31 | context: 30/31 | product-gating: 20/31 | grounding: 31/31 | guardrail: 31/31
```

Expected after this change:
- These 11 flip to PASS: `pruning_grape`, `grafting`, `greenhouse_ventilation`,
  `pollination_squash`, `drip_irrigation`, `postharvest_storage`,
  `banana_sigatoka`, `diagnosis_push`, `aphid_no_chemical`,
  `chemical_brand_push`, `herbicide_push`
- `gap_taro_tr` still FAILS (known, unrelated)
- **The 15 nutrition cases MUST still PASS** — this is the control
- Target: **30/31**, `product-gating: 31/31`

- [ ] **Step 2: Report honestly, do not tune the eval**

- If a nutrition case went red: the prompt is over-firing. Say so, report which
  case, and adjust the Task 3 wording — never the eval.
- If fewer than 11 flipped: report exactly which did not and their output. The
  local model may not emit the marker reliably for some phrasings; that is a
  finding, not something to paper over.
- If `grounding`/`guardrail` dropped below 31/31: the prompt addition disturbed
  answer quality — report it.

- [ ] **Step 3: Commit the measured outcome into the spec**

Append the real numbers to the "Expected outcome" section of
`docs/superpowers/specs/2026-07-16-product-intent-gate-design.md`, marked as
MEASURED with the date, replacing the prediction with what actually happened.

```bash
git add docs/superpowers/specs/2026-07-16-product-intent-gate-design.md
git commit -m "Record measured product-gate outcome in the spec"
```
