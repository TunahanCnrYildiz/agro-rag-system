# Never Return an Empty Answer — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop handing users a blank reply. Measured today: the most ordinary
eval query returns an empty answer **2 times in 10** through the real
`answer()` path.

**Architecture:** A `_complete_text()` helper wraps the chat call — blank output
retries once, then falls back to a message. `answer()` uses it. `stream_answer()`
tracks whether it emitted anything and, if not, falls back the same way (safe:
nothing reached the client yet). `max_tokens` is deliberately NOT touched.

**Tech Stack:** Python, OpenAI-compatible client against local LM Studio
(`gemma-4-12b-qat`), pytest.

**Spec:** `docs/superpowers/specs/2026-07-16-empty-answer-guard-design.md`

## Global Constraints

- No new dependencies, no new component.
- **Retry ONLY on blank output.** A short answer is legitimate (`[OFFSCOPE]`
  refusals are short) — never retry those.
- `_complete_text` **raises** on transport errors; callers keep their existing
  `except` → `_llm_unavailable_message`. The two failures are different and must
  stay distinguishable: "LM Studio unreachable" vs "the model replied with
  nothing".
- Do NOT change `max_tokens` (4096 measured 1/10 vs 2048's 2/10 — at n=10 that
  shows nothing, and one empty at 4096 was the *fastest* run, so it was not a
  budget problem).
- Markers still apply to whatever text comes back, retry or not.
- Tests stay hermetic — no live LM Studio.
- Existing fallback wording is diacritic-free Turkish ("Uzgunum, su anda...") —
  match that style.

## File Structure

- `src/engine.py` — `_empty_answer_message()`, `_complete_text()`, `answer()`,
  `stream_answer()`.
- `src/config.py` — align the `temperature` default with the value actually in
  use (comment + value).
- `tests/test_engine.py` — a sequence-returning fake LLM + guard tests.

---

### Task 1: `_empty_answer_message` + `_complete_text`

**Files:**
- Modify: `src/engine.py` (add next to `_llm_unavailable_message`, ~line 362)
- Test: `tests/test_engine.py`

**Interfaces:**
- Produces: `_empty_answer_message() -> str`;
  `_complete_text(messages: list[dict]) -> str` — never returns `""`, raises on
  transport errors.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_engine.py`)

`_fake_llm(content)` at `tests/test_engine.py:143` always returns the same
content, so it cannot express "blank, then good". Add a sequence variant next to
it — do NOT modify `_fake_llm`, other tests use it.

```python
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
```

Verified for the implementer: `tests/test_engine.py` imports only `json` and
`engine` — no module-level `pytest`, hence the local import above.
`_fake_stream_llm([])` yields an empty iterator, so the stream loop emits
nothing, which is exactly the "streamed nothing" case Task 2 guards.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k complete_text -v`
Expected: FAIL — `AttributeError: module 'src.engine' has no attribute '_complete_text'`

- [ ] **Step 3: Write the implementation**

In `src/engine.py`, directly below `_llm_unavailable_message` (~line 369):

```python
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


def _complete_text(messages: list[dict]) -> str:
    """Return the model's answer text, never "".

    Blank output is stochastic (temperature is non-zero and the failures scatter
    across runs of an identical prompt), so one retry usually lands. Raises on
    transport errors - the caller maps those to _llm_unavailable_message, which
    is a different failure and must stay distinguishable.
    """
    client = _get_llm()
    for _ in range(2):  # first attempt + one retry
        completion = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            stream=False,
            **_sampling_kwargs(),
        )
        text = completion.choices[0].message.content or ""
        if text.strip():
            return text
        print("[engine] model returned a blank answer; retrying once")
    return _empty_answer_message()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -k complete_text -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Add _complete_text: retry once on blank model output, never return empty"
```

---

### Task 2: Use the guard in `answer()` and `stream_answer()`

**Files:**
- Modify: `src/engine.py` — `answer()` (~line 458-468), `stream_answer()` (~line 489-524)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `_complete_text`, `_empty_answer_message` (Task 1).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_engine.py`)

`_fake_stream_llm(chunks)` already exists — reuse it. An "empty stream" is
`_fake_stream_llm([])`.

```python
def test_answer_never_returns_empty(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m: "ctx")
    monkeypatch.setattr(engine, "match_products",
                        lambda m, c: [engine.RecommendedProduct("P", "url")])
    client, _ = _fake_llm_seq(["", ""])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)

    r = engine.answer("Domates yapraklarim sarariyor")

    assert r.answer == engine._empty_answer_message()
    assert r.answer.strip()          # the bug: this used to be ""


def test_answer_uses_the_retry(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [])
    client, calls = _fake_llm_seq(["", "Azot eksikligi olabilir."])
    monkeypatch.setattr(engine, "_get_llm", lambda: client)

    r = engine.answer("Domates yapraklarim sarariyor")

    assert r.answer == "Azot eksikligi olabilir."
    assert calls["n"] == 2


def test_stream_answer_never_streams_nothing(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda m: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda m, c: [])
    # the model streams no tokens at all, then the non-streaming retry is blank
    monkeypatch.setattr(engine, "_get_llm", lambda: _fake_stream_llm([]))
    monkeypatch.setattr(engine, "_complete_text",
                        lambda msgs: engine._empty_answer_message())

    out = "".join(engine.stream_answer("Domates yapraklarim sarariyor"))

    assert _sse_tokens(out) == engine._empty_answer_message()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k "never_returns_empty or uses_the_retry or never_streams_nothing" -v`
Expected: FAIL — `answer()` returns `""` (it calls the client directly), and
`stream_answer` yields no token event at all.

- [ ] **Step 3: Rewrite `answer()`'s completion block**

Replace:
```python
    try:
        client = _get_llm()
        completion = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            stream=False,
            **_sampling_kwargs(),
        )
        answer_text = completion.choices[0].message.content or ""
    except Exception as exc:  # noqa: BLE001
        answer_text = _llm_unavailable_message(exc)
```
with:
```python
    try:
        answer_text = _complete_text(messages)
    except Exception as exc:  # noqa: BLE001
        answer_text = _llm_unavailable_message(exc)
```

- [ ] **Step 4: Add the emitted-nothing fallback to `stream_answer()`**

Add a flag next to the other state (`off_scope`, `no_product`, `buffer`,
`checked`):
```python
    emitted = False
    failed = False
```

Set `emitted = True` at BOTH places that yield a token from the model — the
in-loop `yield` after the marker check, and the direct `yield` when `checked` is
already True. For the marker-check site:
```python
                if clean:
                    yield _sse({"type": "token", "content": clean})
                    emitted = True
```
For the already-checked site:
```python
            if checked:
                yield _sse({"type": "token", "content": delta})
                emitted = True
                continue
```

In the `except` branch, record that the transport failed (its message is already
emitted, so no fallback should follow):
```python
    except Exception as exc:  # noqa: BLE001
        failed = True
        yield _sse({"type": "token", "content": _llm_unavailable_message(exc)})
```

In the leftover flush, mark emission too:
```python
    if not checked and buffer:
        clean, off_scope, no_product = _strip_markers(buffer)
        if clean:
            yield _sse({"type": "token", "content": clean})
            emitted = True
```

Then, immediately after the flush and BEFORE the products event, add:
```python
    if not emitted and not failed:
        # The model streamed nothing at all - the same blank-output bug answer()
        # guards against. Nothing reached the client yet, so retrying is safe.
        try:
            text = _complete_text(messages)
        except Exception as exc:  # noqa: BLE001
            text = _llm_unavailable_message(exc)
        clean, off_scope, no_product = _strip_markers(text)
        if clean:
            yield _sse({"type": "token", "content": clean})
```

- [ ] **Step 5: Run the tests, then the full suite**

Run: `python -m pytest tests/test_engine.py -k "never_returns_empty or uses_the_retry or never_streams_nothing" -v`
Expected: PASS (3 tests)

Run: `python -m pytest -q`
Expected: all green. Any failure is real — fix it, do not skip.

- [ ] **Step 6: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Never hand the user a blank reply from answer() or stream_answer()"
```

---

### Task 3: Align the temperature default with reality

**Files:**
- Modify: `src/config.py:54-56`

**Context:** `.env` (gitignored) sets `TEMPERATURE=0.4`, while `config.py`
defaults to `0.2` and its comment describes 0.2. Anyone cloning the repo, and CI,
runs a different temperature than the maintainer — same code, different
behaviour. Measured 2026-07-16 while chasing the blank-answer bug.

- [ ] **Step 1: Update the default and its comment**

Replace:
```python
    # Low temperature keeps answers grounded/consistent for a factual RAG
    temperature: float = Field(default=0.2)
```
with:
```python
    # Low temperature keeps answers grounded/consistent for a factual RAG.
    # 0.4 matches the value actually in use (.env is gitignored, so a stale
    # default here means a clone - and CI - silently runs a different model
    # configuration than the maintainer does).
    # NOTE: this is non-zero, so generation is stochastic - the same prompt can
    # succeed and fail across runs. That is why blank answers are guarded rather
    # than reasoned about; see the empty-answer-guard spec.
    temperature: float = Field(default=0.4)
```

- [ ] **Step 2: Verify the runtime value is unchanged for the maintainer**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); from src.config import settings; print(settings.temperature)"
```
Expected: `0.4` (unchanged — `.env` still wins; this only fixes the default a
clone would get).

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add src/config.py
git commit -m "Align temperature default with the value actually in use (0.4)"
```

---

### Task 4: Verify against the live model and the eval

**Files:** none (verification only).

- [ ] **Step 1: Measure the blank rate through the real path**

Needs LM Studio (chat + embeddings). ~10 minutes.

```bash
cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System"
PYTHONIOENCODING=utf-8 python - <<'PY'
import sys; sys.path.insert(0, '.')
from src import engine
from src.config import settings
settings.request_timeout = 400.0
q = "Domates yapraklarım sararıyor, ne önerirsiniz?"
empty = fallback = 0
for i in range(1, 21):
    a = engine.answer(q).answer.strip()
    if not a:
        empty += 1
    elif a == engine._empty_answer_message():
        fallback += 1
    print(i, len(a), "EMPTY" if not a else ("FALLBACK" if a == engine._empty_answer_message() else "ok"), flush=True)
print("bos:", empty, "/20   fallback:", fallback, "/20   (guard oncesi: 2/10 bos)")
PY
```

Expected: **`bos: 0/20`** — the user never gets a blank reply.
`fallback` should be ~0 too: a blank first attempt should be rescued by the
retry. A non-zero `fallback` means two blanks in a row — report the count; it
would mean the failures are correlated rather than independent, which the spec
explicitly flags as an inference to be checked.

- [ ] **Step 2: Confirm the eval is undisturbed**

```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval > /tmp/eval.txt 2>&1
grep -E "FAIL|cases passed|retrieval:" /tmp/eval.txt
```
Expected: **31/31**, every dimension 31/31 (baseline before this work).

- [ ] **Step 3: Record the measured outcome in the spec**

Replace the "Expected outcome" section of
`docs/superpowers/specs/2026-07-16-empty-answer-guard-design.md` with the real
numbers, marked MEASURED with the date. If the retry did not eliminate blanks,
say so plainly rather than softening it.

```bash
git add docs/superpowers/specs/2026-07-16-empty-answer-guard-design.md
git commit -m "Record measured empty-answer guard outcome in the spec"
```
