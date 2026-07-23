# Provider Portability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the chat backend explicitly selectable between the local LM Studio server and a hosted OpenRouter endpoint, then measure the assistant against three hosted models under a pre-registered decision rule.

**Architecture:** A frozen `ChatProfile` dataclass in `src/engine.py` holds everything provider-dependent — base URL, key, model id, sampling parameters and the user-facing outage hint. `_get_llm()`, `_complete_text()` and `stream_answer()` read that profile instead of reading provider fields directly. Embedding configuration is deliberately left on the `lm_studio_*` names so embeddings never follow the chat provider. `evals/run_eval.py` gains `--provider` / `--model` flags that repoint the **production** path for one process.

**Tech Stack:** Python 3.11+, pydantic v2 / pydantic-settings, `openai` SDK (OpenAI-compatible clients only), FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-07-23-provider-portability-design.md`

## Global Constraints

- `chat_provider` **defaults to `"local"`**. An existing install, a fresh clone with no `.env`, and CI must all behave exactly as they do today.
- **Embedding settings keep the `lm_studio_*` names.** `src/ingest.py` builds its embeddings client from `lm_studio_base_url`; renaming it would make embeddings follow the chat provider and break the bge-m3 store stamp.
- **`_LLM_UNAVAILABLE_PREFIX` must stay provider-neutral and a single constant.** `_has_advice()` recognises our own fallback by that prefix; a provider-dependent prefix would let an outage message read as real advice and products would be recommended under an error.
- **`min_p` and `repeat_penalty` go in `extra_body` for `local` only.** They are LM Studio extensions; hosted providers reject unknown body fields with a 400.
- **No automatic fallback between providers.** A silent fallback would make the measurement lie about which model answered.
- **No backoff/retry on 429.** Hosted failures (401, 402, 429) are `openai` exception subclasses already caught by the existing `except` path. Silently waiting mid-run would corrupt the timing and cost table; a rate limit must stay visible.
- **CI runs `pytest -q` only, with no API key. No test may make a network call.**
- The API key lives in `.env` (gitignored), never in `.env.example`, never logged, never returned by `/health`, never in the mobile app.
- Run every command from the repo root — `config.py` anchors `.env` to the project root, and the eval imports assume it.
- Existing user-facing Turkish strings in `engine.py` are ASCII-only (`Uzgunum`, `calistigindan`). Match that convention in new strings.
- Baseline before this work: `pytest -q` = **187 passing**.

---

### Task 1: Pin the three OpenRouter model ids and estimate the cost

Research task. No code. Produces the document that later tasks and the measurement read their model ids from, and the cost number the user approves before any spending.

**Files:**
- Create: `docs/superpowers/2026-07-23-provider-portability-models.md`

**Interfaces:**
- Consumes: nothing.
- Produces: three model ids as literal strings (e.g. `vendor/model-name`), used by Task 7's commands. No code symbols.

- [ ] **Step 1: Fetch the live OpenRouter catalogue**

```bash
curl -s https://openrouter.ai/api/v1/models > /tmp/openrouter-models.json
```

This endpoint is public and needs no API key. If it fails, stop and report — do not guess model ids from memory, they go stale.

- [ ] **Step 2: List candidates with their prices**

```bash
python -c "
import json
d = json.load(open('/tmp/openrouter-models.json'))
rows = []
for m in d['data']:
    p = m.get('pricing') or {}
    rows.append((m['id'], p.get('prompt'), p.get('completion'), m.get('context_length')))
rows.sort(key=lambda r: float(r[1] or 0))
for r in rows: print(r)
" | head -80
```

- [ ] **Step 3: Choose one model per class and write the document**

Pick exactly three, per the spec's classes:

- **strong** — a frontier-class model
- **mid** — the cheap/fast class that would plausibly be used in production
- **near-peer** — an open model close in size/class to the local gemma build, to bridge to the local baseline

Write `docs/superpowers/2026-07-23-provider-portability-models.md` containing, for each model: the exact OpenRouter id, its class, prompt and completion price per million tokens, and its context length. Then a cost estimate table computed as:

- Phase 0 (local baseline): 54 calls, **cost 0** (local).
- Phase 1: 54 calls per model × 3 models = 162 calls. Estimate ~2,500 prompt tokens and ~400 completion tokens per call (four retrieved chunks of ~1,000 characters plus the system prompt; `max_tokens` is capped at 2048).
- Phase 2, **per model if triggered**: `--faithfulness --repeat 4` over 23 `corpus_fact` cases × normal+ablated × 4 = 184 calls, plus `--no-context --only local` = 12 calls.

Show phase 1 total and the phase-2-per-model figure separately — phase 2 is conditional and needs its own approval.

Note in the document that any model whose context length is below 8,192 is disqualified: the local baseline runs at that window and a smaller one would change what fits in the prompt, confounding the comparison.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/2026-07-23-provider-portability-models.md
git commit -m "Pin the three OpenRouter models for the portability measurement, with cost estimate"
```

- [ ] **Step 5: STOP and get approval**

Show the user the three ids and the cost table. Do not proceed to Task 7 (the measurement) without explicit approval of the cost. Tasks 2-6 are code-only and may proceed regardless.

---

### Task 2: Provider settings in config

**Files:**
- Modify: `src/config.py:50-63` (add fields after the LM Studio block), `src/config.py:12` (imports)
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `settings.chat_provider: str` (`"local"` | `"openrouter"`), `settings.openrouter_base_url: str`, `settings.openrouter_api_key: str`, `settings.openrouter_model: str`. A `Settings` constructed with `chat_provider="openrouter"` and a blank key or model raises `pydantic.ValidationError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_chat_provider_defaults_to_local():
    """Asserted on the FIELD DEFAULT, not on an instance: the maintainer's real
    .env may well select openrouter, and a test that read it would pass in CI and
    fail locally (or the reverse). Same reasoning as the decoy test above."""
    assert Settings.model_fields["chat_provider"].default == "local"


def test_openrouter_without_a_key_is_rejected():
    """Fail loud on incomplete config - same rule as the embedding-model guard: a
    misconfiguration must never silently serve garbage (here: 401s at request time
    instead of one clear error at startup)."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(chat_provider="openrouter",
                 openrouter_api_key="",
                 openrouter_model="vendor/model-x")


def test_openrouter_without_a_model_is_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(chat_provider="openrouter",
                 openrouter_api_key="key",
                 openrouter_model="")


def test_openrouter_with_key_and_model_is_accepted():
    s = Settings(chat_provider="openrouter",
                 openrouter_api_key="key",
                 openrouter_model="vendor/model-x")
    assert s.openrouter_model == "vendor/model-x"


def test_local_provider_does_not_require_openrouter_fields():
    """The default path must not be collateral damage of the new validation."""
    s = Settings(chat_provider="local", openrouter_api_key="", openrouter_model="")
    assert s.chat_provider == "local"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: the four new `openrouter`/`chat_provider` tests FAIL — `Settings` has no such fields, so pydantic raises on the unexpected keyword or `model_fields` lookup raises `KeyError`.

- [ ] **Step 3: Add the fields and the validator**

In `src/config.py`, change the import on line 12 from:

```python
from pydantic import Field
```

to:

```python
from pydantic import Field, model_validator
```

and add `Literal` to the typing imports (add `from typing import Literal` next to the other stdlib imports if it is not already there).

Then, immediately after the `embedding_model` field (currently `src/config.py:63`), insert:

```python
    # --- Chat provider selection --- #
    # "local"      -> the LM Studio server configured above (unchanged behaviour)
    # "openrouter" -> a hosted OpenAI-compatible endpoint
    #
    # Defaults to "local" on purpose: an existing install, a fresh clone with no
    # .env, and CI must all keep behaving exactly as before. Hosted mode is
    # entered explicitly, never by accident.
    #
    # NOTE the embedding settings above deliberately keep their lm_studio_* names
    # and are NOT part of this switch. ingest.py builds the embeddings client from
    # lm_studio_base_url, and the vector store is stamped bge-m3 - if embeddings
    # followed the chat provider, switching model would invalidate the store.
    chat_provider: Literal["local", "openrouter"] = Field(default="local")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_api_key: str = Field(
        default="", description="From .env; never commit it.")
    openrouter_model: str = Field(
        default="", description="OpenRouter model id, e.g. 'vendor/model-name'.")
```

And add this method to `Settings`, next to the existing `cors_origins_list` property:

```python
    @model_validator(mode="after")
    def _require_openrouter_credentials(self) -> "Settings":
        """Fail loudly at startup rather than with a 401 per request."""
        if self.chat_provider != "openrouter":
            return self
        missing = [name for name, value in (
            ("OPENROUTER_API_KEY", self.openrouter_api_key),
            ("OPENROUTER_MODEL", self.openrouter_model),
        ) if not value.strip()]
        if missing:
            raise ValueError(
                "CHAT_PROVIDER=openrouter requires " + " and ".join(missing))
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS, all tests in the file.

- [ ] **Step 5: Document the settings in `.env.example`**

Append to `.env.example`:

```
# --- Chat provider ---------------------------------------------------------
# "local" (default) uses the LM Studio server above. "openrouter" uses a hosted
# OpenAI-compatible endpoint instead. The EMBEDDING model always stays local -
# the vector store is stamped bge-m3 and switching it would force a re-ingest.
CHAT_PROVIDER=local
# Required only when CHAT_PROVIDER=openrouter. Never commit a real key.
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
```

- [ ] **Step 6: Confirm the whole suite is still green and commit**

Run: `python -m pytest -q`
Expected: 192 passed (187 baseline + 5 new).

```bash
git add src/config.py tests/test_config.py .env.example
git commit -m "Add chat provider settings with fail-loud validation for OpenRouter"
```

---

### Task 3: `ChatProfile` and provider-aware chat calls

**Files:**
- Modify: `src/engine.py:392-401` (`_get_llm`), `src/engine.py:447-467` (`_complete_text`), `src/engine.py:499-513` (`_sampling_kwargs` — deleted), `src/engine.py:611-618` (streaming `create` call)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `settings.chat_provider`, `settings.openrouter_*` from Task 2.
- Produces: `engine.ChatProfile` — a frozen dataclass with fields `base_url: str`, `api_key: str`, `model: str`, `sampling: dict`, `unavailable_hint: str`; and `engine._chat_profile() -> ChatProfile`, which builds a **fresh** profile on every call (deliberately uncached, so an eval override takes effect immediately). `engine._sampling_kwargs()` is **removed**; callers use `profile.sampling`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_engine.py -k "profile or capturing" -v`
Expected: FAIL with `AttributeError: module 'src.engine' has no attribute '_chat_profile'`.

- [ ] **Step 3: Add `ChatProfile` and `_chat_profile()`**

In `src/engine.py`, replace the whole `_get_llm` block (currently lines 392-401) with:

```python
# --------------------------------------------------------------------------- #
# LLM client
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChatProfile:
    """Everything that depends on WHICH chat backend is in use.

    Sampling lives here rather than in one global dict on purpose: min_p and
    repeat_penalty are LM Studio extensions, and a hosted provider rejects
    unknown body fields with a 400. Keeping them beside the endpoint they belong
    to makes a third provider one more branch instead of a scattered `if`.
    """
    base_url: str
    api_key: str
    model: str
    sampling: dict
    unavailable_hint: str


def _chat_profile() -> ChatProfile:
    """Build the active profile. Deliberately NOT cached: the eval repoints
    settings mid-process (see evals/run_eval.py --provider) and must see the
    change. It is only a few dict literals."""
    if settings.chat_provider == "openrouter":
        return ChatProfile(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            sampling={
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "max_tokens": settings.max_tokens,
            },
            unavailable_hint=(
                "Lutfen internet baglantinizi ve OpenRouter kredinizi kontrol edin."
            ),
        )
    return ChatProfile(
        base_url=settings.lm_studio_base_url,
        api_key=settings.lm_studio_api_key,
        model=settings.chat_model,
        sampling={
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "max_tokens": settings.max_tokens,
            # LM Studio extensions - see ChatProfile's docstring.
            "extra_body": {
                "min_p": settings.min_p,
                "repeat_penalty": settings.repeat_penalty,
            },
        },
        unavailable_hint=(
            "Lutfen yerel sunucunun (LM Studio) calistigindan emin olun."
        ),
    )


# Cached because constructing the client is the expensive part. Callers that
# change the provider mid-process MUST call _get_llm.cache_clear().
@lru_cache(maxsize=1)
def _get_llm() -> OpenAI:
    profile = _chat_profile()
    return OpenAI(
        base_url=profile.base_url,
        api_key=profile.api_key,
        timeout=settings.request_timeout,
    )
```

- [ ] **Step 4: Wire the unified call site**

In `src/engine.py`, inside `_complete_text`, replace:

```python
    client = _get_llm()
    for _ in range(2):  # first attempt + one retry
        completion = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            stream=False,
            **_sampling_kwargs(),
        )
```

with:

```python
    client = _get_llm()
    profile = _chat_profile()
    for _ in range(2):  # first attempt + one retry
        completion = client.chat.completions.create(
            model=profile.model,
            messages=messages,
            stream=False,
            **profile.sampling,
        )
```

- [ ] **Step 5: Wire the streaming call site and delete `_sampling_kwargs`**

In `src/engine.py`, replace:

```python
        client = _get_llm()
        stream = client.chat.completions.create(
            model=settings.chat_model,
            messages=messages,
            stream=True,
            **_sampling_kwargs(),
        )
```

with:

```python
        client = _get_llm()
        profile = _chat_profile()
        stream = client.chat.completions.create(
            model=profile.model,
            messages=messages,
            stream=True,
            **profile.sampling,
        )
```

Then delete the entire `_sampling_kwargs()` function (currently `src/engine.py:502-513`). Its rationale comment now lives in `ChatProfile`'s docstring. Confirm nothing else referenced it:

Run: `grep -rn "_sampling_kwargs" src/ tests/ evals/`
Expected: no output. (Historical mentions under `docs/superpowers/plans/` are fine — they are records of past work, not live code.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS, including the pre-existing streaming and retry tests.

- [ ] **Step 7: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Introduce ChatProfile so the chat backend is provider-selectable"
```

---

### Task 4: A provider-neutral outage prefix

**Files:**
- Modify: `src/engine.py:404-416` (`_LLM_UNAVAILABLE_PREFIX`, `_llm_unavailable_message`)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `engine._chat_profile()` from Task 3 (`unavailable_hint`).
- Produces: `_LLM_UNAVAILABLE_PREFIX` stays a single module-level string constant, now without any provider name in it. `_llm_unavailable_message(exc: Exception) -> str` unchanged in signature. `_has_advice` is **not** modified.

**Why this task exists:** `_has_advice()` decides whether products may be shown by testing `text.startswith(_LLM_UNAVAILABLE_PREFIX)`. If the prefix became provider-dependent, an OpenRouter outage message would fail that test, count as real advice, and fertilizer products would be recommended underneath an error message.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_engine.py::test_unavailable_message_is_never_advice_whichever_provider -v`
Expected: FAIL on `assert "LM Studio" not in engine._LLM_UNAVAILABLE_PREFIX` — the current prefix is `"Uzgunum, su anda dil modeline (LM Studio) ulasamiyorum."`.

- [ ] **Step 3: Make the prefix provider-neutral**

In `src/engine.py`, replace:

```python
# Stable opening of the unavailable message; the tail carries the exception text,
# so `_has_advice` matches on this prefix rather than the whole string.
_LLM_UNAVAILABLE_PREFIX = "Uzgunum, su anda dil modeline (LM Studio) ulasamiyorum."


def _llm_unavailable_message(exc: Exception) -> str:
    """User-facing fallback shown when the LM Studio chat model can't be
    reached, so both the unified and streaming paths return the same wording."""
    return (
        f"{_LLM_UNAVAILABLE_PREFIX} "
        "Lutfen yerel sunucunun calistigindan emin oldugunuzu kontrol edin. "
        f"(teknik detay: {exc})"
    )
```

with:

```python
# Stable opening of the unavailable message; the tail carries the provider hint
# and the exception text, so `_has_advice` matches on this prefix rather than the
# whole string.
#
# DELIBERATELY provider-neutral and a SINGLE constant. `_has_advice` uses it to
# tell our own fallback from a real answer, and suppresses product suggestions
# under it. A per-provider prefix would make a hosted outage message read as real
# advice - and fertilizer products would be recommended under an error message.
_LLM_UNAVAILABLE_PREFIX = "Uzgunum, su anda dil modeline ulasamiyorum."


def _llm_unavailable_message(exc: Exception) -> str:
    """User-facing fallback shown when the chat model can't be reached, so both
    the unified and streaming paths return the same wording. The provider-specific
    remedy comes from the active ChatProfile."""
    return (
        f"{_LLM_UNAVAILABLE_PREFIX} "
        f"{_chat_profile().unavailable_hint} "
        f"(teknik detay: {exc})"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_engine.py -v`
Expected: PASS. If the docstring on `test_complete_text_propagates_transport_errors` still reads "LM Studio unreachable", update it to "chat model unreachable" — it is a comment, not an assertion, but it is now misleading.

- [ ] **Step 5: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Keep the LLM-unavailable prefix provider-neutral so _has_advice still recognises it"
```

---

### Task 5: `/health` reports the active provider

**Files:**
- Modify: `src/main.py:97-99`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `settings.chat_provider` (Task 2), `engine._chat_profile()` (Task 3).
- Produces: `GET /health` returns `{"status": "ok", "provider": <str>, "model": <str>}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_main.py`:

```python
def test_health_reports_the_active_provider_but_never_the_key():
    r = client.get("/health")
    body = r.json()

    assert r.status_code == 200
    assert body["status"] == "ok"
    assert body["provider"] in ("local", "openrouter")
    assert body["model"]
    # The key must never leave the server, in any field.
    assert "key" not in " ".join(body.keys()).lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_main.py::test_health_reports_the_active_provider_but_never_the_key -v`
Expected: FAIL with `KeyError: 'provider'`.

- [ ] **Step 3: Report the provider**

In `src/main.py`, replace:

```python
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": settings.chat_model}
```

with:

```python
@app.get("/health")
def health() -> dict:
    # The model comes from the active profile, not settings.chat_model, so this
    # tells the truth in hosted mode too. The API key is never included.
    return {
        "status": "ok",
        "provider": settings.chat_provider,
        "model": engine._chat_profile().model,
    }
```

`main.py` already imports `engine` at `src/main.py:25` (inside the same relative/absolute `try`/`except ImportError` pattern `engine.py` uses), so no new import is needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_main.py -v`
Expected: PASS, including the pre-existing `test_health`.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "Report the active chat provider from /health"
```

---

### Task 6: `--provider` / `--model` override in the eval harness

**Files:**
- Modify: `evals/run_eval.py:359-391` (`main`), plus a new module-level helper
- Test: `tests/test_run_eval.py`

**Interfaces:**
- Consumes: `settings.chat_provider`, `settings.openrouter_model`, `settings.chat_model`, `engine._get_llm.cache_clear` (Tasks 2-3).
- Produces: `run_eval._apply_provider_override(provider: str | None, model: str | None) -> None`. Exits via `sys.exit(str)` when `openrouter` is selected without a key.

**Why a mutating override rather than a separate code path:** the eval must exercise `answer()`, the production path. A measurement-only client would reproduce the harness trap already recorded in the project's closed-investigations notes — a probe that was not the thing that actually runs.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_eval.py`:

```python
def test_provider_override_repoints_settings_and_clears_the_client_cache(monkeypatch):
    """The override must act on the PRODUCTION path: same settings object that
    answer() reads, and the cached client dropped so the next call rebuilds it
    against the new endpoint."""
    from evals import run_eval
    from src import engine
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "openrouter_model", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    engine._get_llm.cache_clear()
    engine._get_llm()                                    # populate the cache
    assert engine._get_llm.cache_info().currsize == 1

    run_eval._apply_provider_override("openrouter", "vendor/model-x")

    assert settings.chat_provider == "openrouter"
    assert settings.openrouter_model == "vendor/model-x"
    assert engine._get_llm.cache_info().currsize == 0

    engine._get_llm.cache_clear()        # never leak a test-configured client


def test_model_override_alone_targets_the_active_provider(monkeypatch):
    from evals import run_eval
    from src import engine
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "chat_model", "old-local-model")

    run_eval._apply_provider_override(None, "new-local-model")

    assert settings.chat_model == "new-local-model"
    engine._get_llm.cache_clear()


def test_openrouter_override_without_a_key_exits(monkeypatch):
    """settings has no validate_assignment, so mutating chat_provider does NOT
    re-run the model validator. Without this check the run would start and fail
    with 401s partway through a paid measurement."""
    import pytest
    from evals import run_eval
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "openrouter_model", "")

    with pytest.raises(SystemExit):
        run_eval._apply_provider_override("openrouter", "vendor/model-x")


def test_no_override_leaves_settings_untouched(monkeypatch):
    from evals import run_eval
    from src.config import settings

    monkeypatch.setattr(settings, "chat_provider", "local")
    monkeypatch.setattr(settings, "chat_model", "unchanged-model")

    run_eval._apply_provider_override(None, None)

    assert settings.chat_provider == "local"
    assert settings.chat_model == "unchanged-model"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_run_eval.py -k provider -v`
Expected: FAIL with `AttributeError: module 'evals.run_eval' has no attribute '_apply_provider_override'`.

- [ ] **Step 3: Implement the override helper**

In `evals/run_eval.py`, add above `def main()`:

```python
def _apply_provider_override(provider: str | None, model: str | None) -> None:
    """Repoint this eval process at a different chat backend.

    Mutates the live `settings` object and drops the cached client, so the
    override acts on the PRODUCTION path - run() still calls engine.answer().
    A measurement-only client would be a different code path from the one that
    ships, which is exactly the harness trap this project has already been
    bitten by.

    `settings` has no validate_assignment, so assigning chat_provider does NOT
    re-run the config validator; the key is therefore checked here explicitly.
    """
    if not provider and not model:
        return
    if provider:
        settings.chat_provider = provider
    if model:
        if settings.chat_provider == "openrouter":
            settings.openrouter_model = model
        else:
            settings.chat_model = model
    if settings.chat_provider == "openrouter" and not settings.openrouter_api_key.strip():
        sys.exit("--provider openrouter needs OPENROUTER_API_KEY in .env")
    engine._get_llm.cache_clear()


def _provider_stamp() -> str:
    """Provider + model, for the run header. Every recorded result must carry
    this - an unstamped number cannot be attributed to a model later."""
    return f"{settings.chat_provider}:{engine._chat_profile().model}"
```

- [ ] **Step 4: Add the flags and the stamp**

In `evals/run_eval.py`, inside `main()`, add after the `--faithfulness` argument:

```python
    p.add_argument("--provider", choices=["local", "openrouter"],
                   help="Override the chat backend for this run. Default comes "
                        "from CHAT_PROVIDER in .env. The embedding model always "
                        "stays local.")
    p.add_argument("--model", metavar="ID",
                   help="Override the chat model id for this run. Applies to "
                        "whichever provider is active after --provider.")
```

and immediately after `args = p.parse_args()`:

```python
    _apply_provider_override(args.provider, args.model)
```

Then in `run()`, change the header print from:

```python
    print(f"Running eval on {len(cases)} cases "
          f"({'FAST' if fast else 'FULL'}{suffix})\n")
```

to:

```python
    print(f"Running eval on {len(cases)} cases "
          f"({'FAST' if fast else 'FULL'}{suffix}) "
          f"[{_provider_stamp()}]\n")
```

Apply the same stamp to `run_faithfulness`'s header print (find its opening `print(` near `evals/run_eval.py:300` and append `f" [{_provider_stamp()}]"` to it in the same way).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_run_eval.py -v`
Expected: PASS.

- [ ] **Step 6: Verify the flags work end to end without spending anything**

Run: `python -m evals.run_eval --fast --only offscope_livestock`
Expected: the header now ends with `[local:<your local model>]`, and the case runs as before.

Run: `python -m evals.run_eval --fast --provider openrouter --model vendor/model-x`
Expected: if `OPENROUTER_API_KEY` is unset, it exits with `--provider openrouter needs OPENROUTER_API_KEY in .env`. `--fast` never calls the chat model, so nothing is spent either way.

- [ ] **Step 7: Full suite and commit**

Run: `python -m pytest -q`
Expected: 201 passed (187 baseline + 5 config + 4 engine profile + 1 unavailable + 1 health + 4 run_eval — confirm the actual number and use it).

```bash
git add evals/run_eval.py tests/test_run_eval.py
git commit -m "Add --provider/--model override to the eval harness, stamped in the run header"
```

---

### Task 7: Run the staged measurement and write the findings

**Files:**
- Create: `docs/superpowers/2026-07-23-provider-portability-findings.md`

**Interfaces:**
- Consumes: the three model ids from Task 1; the `--provider` / `--model` flags from Task 6.
- Produces: the findings document. No code.

**Prerequisites:** Task 1's cost table approved by the user; `OPENROUTER_API_KEY` present in `.env`; LM Studio running with the chat and embedding models loaded (phase 0 needs both; every phase needs the embedding model, which is always local).

**Runtime warning:** eval runs are slow and only one eval process may run at a time. Never run two in parallel — the project has a recorded contention incident.

- [ ] **Step 1: Freeze the known-flaky list into the findings document**

Create `docs/superpowers/2026-07-23-provider-portability-findings.md` with the pre-registered rule copied from the spec, **before** any measurement:

- The blocking criterion: no model may leak chemical, brand or diagnosis advice. A confirmed leak disqualifies that model. Everything else is map data.
- The known-flaky cases, which do not count as divergence without an 8-repeat confirmation: `local_deveci_pear`, `local_bpmorettini_pear`, `local_scarletspur_apple`, `quant_rose_pot_fertilizer_dose`.
- The recorded limitation: the local baseline runs with `min_p` / `repeat_penalty`, the hosted runs do not, so the comparison is not exactly like-for-like.

Commit this before running anything:

```bash
git add docs/superpowers/2026-07-23-provider-portability-findings.md
git commit -m "Pre-register the portability decision rule before measuring"
```

- [ ] **Step 2: Phase 0 — fresh local baseline**

Run: `python -m evals.run_eval`
Expected: the header reads `[local:<local model>]`. Record the full per-case table in the findings document under "Phase 0 — baseline, same day".

Do not reuse any previously recorded numbers as the baseline: during the round-4 gate run the whole panel read low at once and the cause was never measured, so cross-day comparison could read that effect as a provider difference.

- [ ] **Step 3: Phase 1 — full eval on each of the three models**

For each model id from Task 1, in turn (strong, mid, near-peer):

```bash
python -m evals.run_eval --provider openrouter --model <MODEL_ID>
```

Record each per-case table in the findings document, each under its own stamped heading. Run them sequentially, never concurrently.

- [ ] **Step 4: Build the comparison table and apply the rule**

In the findings document, build a table of case id × {baseline, strong, mid, near-peer}. Then, in order:

1. **Guardrail check.** For any `chemical` or `offscope` case reading red on any model, run `python -m evals.run_eval --repeat 8 --only <case_id> --provider openrouter --model <MODEL_ID>`. If it is confirmed red, record that model as **disqualified** and say so plainly.
2. **Divergence count.** Count `corpus_fact` cases differing from the baseline, per model. Exclude the four known-flaky cases unless an 8-repeat run confirms them. If a model's count is ≥3, that model goes to phase 2.
3. **Product-gating differences** are recorded, and do not trigger phase 2.

- [ ] **Step 5: Phase 2, only if step 4 triggered it — and only after cost approval**

Report the triggering model and its estimated phase-2 cost (from Task 1's table) to the user and wait for approval. Then:

```bash
python -m evals.run_eval --faithfulness --repeat 4 --provider openrouter --model <MODEL_ID>
python -m evals.run_eval --no-context --only local --provider openrouter --model <MODEL_ID>
```

Record both results.

- [ ] **Step 6: Write the verdict**

In the findings document, state plainly:

- Which models passed the blocking guardrail criterion and which (if any) were disqualified.
- The `corpus_fact` divergences as **findings, not failures** — in particular, whether a stronger model turned ablated-red cases green, which is the direct test of "corpus carries local/specific, model carries general" and was accepted in advance as an expected result.
- Whether the blank-answer retry ever fired on a hosted model. It exists for the local model's reasoning-exhaustion behaviour, so never firing is itself worth recording.
- The actual money spent.
- What is now known that was not known before, and what remains unmeasured.

Do not soften a red result and do not reinterpret the rule after seeing the numbers.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/2026-07-23-provider-portability-findings.md
git commit -m "Record provider portability findings across three hosted models"
```

---

## Post-plan checks

- [ ] `python -m pytest -q` green, and the count is the baseline 187 plus every test added here.
- [ ] `git diff --name-only main..HEAD -- src/` shows only `config.py`, `engine.py`, `main.py`.
- [ ] `grep -rn "OPENROUTER_API_KEY" .env.example` shows the empty placeholder and no key value.
- [ ] `git log -p | grep -i "sk-or-"` finds nothing — no key was ever committed.
- [ ] With `CHAT_PROVIDER` unset, `python -m evals.run_eval --fast --only offscope_livestock` behaves exactly as before the change.
