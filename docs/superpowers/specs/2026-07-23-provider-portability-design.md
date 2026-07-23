# Provider portability: a selectable hosted chat backend, and a measurement of it

**Date:** 2026-07-23
**Status:** design approved, ready for an implementation plan

## Why this, and why now

Every measurement this project has made about answer quality, guardrails and
`corpus_fact` grounding was taken against **one** model: a local gemma build served by
LM Studio. The project's stated north star — *the RAG must be full enough that most
answers come from the corpus, on ANY model* — has therefore never actually been tested
on any other model.

At the same time the productive work on the corpus side is finished. Rounds 5, 6 and 7
all measured dry, and round 7 established that the binding constraint is the rule
structure, not paper supply (`docs/superpowers/2026-07-22-round7-harvest-findings.md`).
Retrieval and prompt leads are closed with evidence. Portability is the one open,
unmeasured question whose answer changes what the product can do.

Going live is blocked on infrastructure — there is no server. That blocks *deployment*,
not this work: the eval runs locally and only the chat call leaves the machine. A hosted
model is not a hosted server.

### What this buys, concretely

1. **The guardrail risk gets measured.** Chemical/brand/diagnosis refusal was measured
   to be **prompt-carried** — it held fully green against an empty corpus. That is a
   statement about gemma's instruction-following, not about the prompt in general. On a
   different model it may not hold. This is a genuine safety unknown and it is the one
   blocking criterion below.
2. **The demo stops depending on LM Studio.** Today a demo needs the maintainer's
   machine with the local server running.
3. **Two local-model workarounds may become unnecessary** — the blank-answer retry and
   the streaming warm-up buffer both exist for gemma's reasoning-exhaustion behaviour.

## Scope

**In scope:** a second, explicitly selected chat provider (OpenRouter), the eval
harness gaining a provider/model dimension, and one staged measurement across three
models with a pre-registered decision rule.

**Out of scope:** per-request model selection in the API; streaming behaviour
differences; automatic fallback between providers; the embedding provider (stays local,
see below); anything that requires a server.

## Architecture

### Configuration surface

New settings in `src/config.py`, added **alongside** the existing `lm_studio_*` fields:

| setting | default | note |
|---|---|---|
| `chat_provider` | `"local"` | `"local"` \| `"openrouter"` |
| `openrouter_base_url` | `https://openrouter.ai/api/v1` | |
| `openrouter_api_key` | `""` | from `.env`, gitignored |
| `openrouter_model` | `""` | an OpenRouter model id, e.g. `anthropic/…` |

The default stays `local` deliberately: an existing install, a fresh clone without a
`.env`, and CI all keep behaving exactly as they do today. Hosted mode is entered
explicitly, never by accident.

### `ChatProfile` — everything provider-dependent in one place

A frozen dataclass resolved once from settings:

| field | `local` | `openrouter` |
|---|---|---|
| `base_url` / `api_key` | `lm_studio_*` | `openrouter_*` |
| `model` | `chat_model` | `openrouter_model` |
| `sampling` | temperature, top_p, max_tokens **+ `extra_body{min_p, repeat_penalty}`** | temperature, top_p, max_tokens (**no `extra_body`**) |
| `unavailable_hint` | "check the local server is running" | "check the internet connection / OpenRouter credit" |

`_get_llm()`, `_sampling_kwargs()` and `_llm_unavailable_message()` read this profile.
Both `chat.completions.create` call sites (`engine.py:458` unified, `engine.py:614`
streaming) take the model from the profile rather than `settings.chat_model` directly.

`min_p` and `repeat_penalty` are LM Studio extensions. Most hosted providers reject
unknown body fields with a 400. Putting sampling **inside** the profile solves this
structurally, rather than as an `if provider == ...` sprinkled through `engine.py`; a
third provider becomes one more profile.

### Three details, each guarding a known trap

1. **Embedding settings deliberately keep the `lm_studio_*` name.** `src/ingest.py`
   builds its embeddings client from `lm_studio_base_url`. Renaming those fields to
   something provider-neutral would make embeddings follow the chat provider — and the
   store is stamped bge-m3, so the embedding-model guard would fire (or, worse, a
   same-dimension wrong model would not). The separation is protected by the *name*,
   not by a comment.
2. **Fail loud on incomplete config.** `chat_provider="openrouter"` with an empty
   `openrouter_api_key` or `openrouter_model` raises at startup. Same rationale as the
   embedding-model guard: a misconfiguration must never silently serve garbage.
3. **`_get_llm()` is `lru_cache(maxsize=1)`.** The eval override path must call
   `cache_clear()` after changing settings. Existing tests monkeypatch `_get_llm`
   directly and are unaffected.

`/health` (`src/main.py:99`) currently returns only `chat_model`; it will also return
the active provider. Never the key.

### A bug this design would introduce, and its fix

`_has_advice()` (`engine.py:434`) recognises the LLM-unavailable fallback by testing
whether the text **starts with `_LLM_UNAVAILABLE_PREFIX`**, and uses that to decide
whether products may be shown underneath. If the prefix itself became
provider-dependent, an OpenRouter outage message would fail that test, count as real
advice, and **fertilizer products would be recommended under an error message**.

Fix: the prefix stays **single and provider-neutral** ("cannot reach the language
model"); the provider-specific hint goes in the tail, which already carries the
exception text. `_has_advice` is unchanged. The current wording contains "(LM Studio)"
inside the prefix, so that string moves to the tail and the test pinning it is updated
— a deliberate change, recorded here so it is not read later as an accident.

## Measurement protocol

### Harness change

`evals/run_eval.py` gains two flags:

```
--provider {local,openrouter}
--model <id>
```

They override settings for that process and clear the client cache. The override acts
on the **production path** — `run_eval` still calls `answer()`. This is deliberate: a
separate measurement-only code path is exactly the harness trap recorded in
`do-not-rechase` (a probe that built messages with `products=[]` and was therefore not
the production prompt). Every result is stamped with provider + model; an unstamped
result is not recorded.

### Models

Three, chosen to separate *system* failures from *model-capacity* failures:

- **strong** — a frontier-class model
- **mid** — the cheap/fast class that would plausibly be used in production
- **near-peer** — an open model close to the local gemma build, bridging to the local
  baseline

A case red on all three is a system problem. A case red only on the weak model is
capacity. One model cannot make that distinction.

The classes are fixed here; the **exact model ids are pinned in the implementation
plan**, after checking OpenRouter's live catalogue and current pricing. Writing
specific ids into this document would date it and invite a stale id being used
unverified.

### Phase 0 — a fresh baseline

On the measurement day, run the full eval once against local gemma. Recorded results
from earlier days are **not** used as the baseline: during the round-4 gate run the
whole panel read low at once — several independent cases below their recorded rates in
the same run — and the cause was never measured. (That observation lives in the project
handoff notes, not in a repo document.) Comparing two numbers from different days would
risk reading that effect as a provider difference.

### Phase 1 — full eval on all three models

54 cases, single pass, per model (~160 calls plus the baseline). Guardrail cases are
already inside the panel; no separate run.

### Phase 2 — only if triggered

| observation | consequence |
|---|---|
| a guardrail case reads red | confirm with `--repeat 8 --only <id>`; if confirmed, **that model is disqualified** |
| ≥3 `corpus_fact` cases diverge from baseline on one model | run `--faithfulness --repeat 4` and `--no-context --only local` on that model |
| product-gating divergence | recorded; does **not** trigger phase 2 |

If phase 2 is entered on the strong model, its estimated cost is written down and
approved **before** the run.

### Known-flaky cases do not count as divergence

Frozen **before** measurement, and not extendable after seeing results:

- `local_deveci_pear`
- `local_bpmorettini_pear`
- `local_scarletspur_apple`
- `quant_rose_pot_fertilizer_dose`

All four read red in a meaningful fraction of ordinary local runs. If one reads red on
a hosted model it must be confirmed with `--repeat 8 --only <id>` before it enters the
divergence count.

### The pre-registered decision rule

**The only blocking criterion is the guardrail.** No model may leak chemical, brand or
diagnosis advice; a confirmed leak disqualifies that model, full stop.

**Everything else is map data, not failure.** `corpus_fact` and product-gating
differences are recorded as findings. In particular, a strong model turning
ablated-red cases green is an **expected finding, not a regression** — it is the direct
test of "corpus carries local/specific, model carries general". The rule accepts this in
advance precisely so the result cannot be reinterpreted after it is seen.

Demanding parity was considered and rejected: the panel is a **drift guard**, and its
count was explicitly measured not to be a coverage metric. Requiring a hosted model to
match it would misread what the panel is.

### Honest limitation, recorded up front

The local baseline runs with `min_p` and `repeat_penalty`; the hosted runs will not,
because those are LM Studio extensions. **The comparison is therefore not exactly
like-for-like.** This is written here, before the measurement, as a constraint on what
the result can prove — not kept in reserve as an explanation for an inconvenient
outcome.

## Testing

All tests are offline and follow the existing monkeypatch pattern in
`tests/test_engine.py`.

- **The `local` profile carries `extra_body`; the `openrouter` profile does not.** This
  test's real job is future protection: if someone later re-collapses sampling into a
  single global dict, the failure appears on the hosted path as a silent 400 — in
  production, if not in a test.
- **`_has_advice` treats both providers' unavailable messages as not-advice.** The
  regression nail for the bug described above.
- **Config validation:** `openrouter` selected with a missing key or model raises a
  clear error; the `local` default behaves identically to today.
- **`--provider` / `--model` override** actually reaches settings and clears the cache;
  a run without the flags is unchanged.
- **`/health` reports the provider** and never the key.

**CI keeps running `pytest -q` only, with no API key.** No test makes a network call.
The hosted measurement is a manual, local activity.

## Error handling

The hosted failure classes — 401 (bad key), 402 (out of credit), 429 (rate limit) — are
all `openai` exception subclasses, so the **existing** `except` path already catches
them and the technical detail reaches the user in the message tail. No new error
architecture is needed.

Deliberately **not** added: automatic backoff/retry on 429. It is unmeasured behaviour,
and silently waiting in the middle of a measurement run would corrupt the timing and
cost table. A rate limit should be visible.

The blank-answer retry in `_complete_text` stays. It will probably never fire on a
hosted model — **that is itself a finding to record**, since it exists for gemma's
reasoning-exhaustion behaviour. The streaming warm-up buffer (`_STREAM_WARMUP=80`)
is untouched; on a hosted model it costs only a slightly later first paint.

## Safety and cost

- The key lives in `.env` (gitignored). `.env.example` gets an empty placeholder only.
  The key is never logged and never returned by `/health`.
- The key does **not** go into the mobile app. The backend holds it; the mobile client
  talks to the backend, which is already the architecture.
- **No automatic local↔hosted fallback.** Tempting and poisonous: a silent fallback
  would make the measurement lie about which model produced an answer. The provider is
  chosen explicitly and errors if unavailable.
- `max_tokens=2048` already caps output per call. Phase 2 cost is estimated and
  approved before it runs.

## Deliverables

1. Provider-selectable chat layer (`config.py`, `engine.py`, `main.py`) with tests.
2. `--provider` / `--model` in `evals/run_eval.py` with tests.
3. `docs/superpowers/2026-07-23-provider-portability-findings.md` — a model × category
   table, whether phase 2 triggered, the cost, and the verdict under the pre-registered
   rule.
