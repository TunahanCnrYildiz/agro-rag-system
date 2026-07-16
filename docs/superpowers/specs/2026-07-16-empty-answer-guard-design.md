# Never Return an Empty Answer — Design

**Date:** 2026-07-16
**Status:** Approved (ready for plan + implementation)
**Files touched:** `src/engine.py`, `src/config.py`, `.env` (local, gitignored),
`tests/test_engine.py`

## Problem

The assistant sometimes returns a **completely empty answer** to the user — not a
refusal, not an error, just nothing.

**Measured 2026-07-16 on the real production path** (`engine.answer()`, 10 runs
of the same query):

| Query | Empty |
|---|---|
| `"Domates yapraklarım sararıyor, ne önerirsiniz?"` (eval case #1) | **2 / 10** |
| `"Antep fıstığında periyodisite nasıl azaltılır?"` | 0 / 10 |

The failing one is the **most ordinary question in the eval**: rich context, 3
matched products. Roughly **1 user in 5** gets a blank reply.

`answer()` cannot see it: the LLM returns HTTP 200 with `content=""` and raises
nothing, so the `except` branch and `_llm_unavailable_message` never fire. The
empty string is stripped, `.strip()`ed, and handed to the client.

### Two distinct modes (measured)

1. **Budget exhaustion.** `finish_reason="length"`, `completion_tokens=2048`,
   `reasoning_content` **8135 chars** — the model spent the whole budget
   "thinking" and never emitted the visible answer. `max_tokens` is shared
   between reasoning and answer.
2. **Fast empty.** At `max_tokens=4096` one run still came back empty **in 21.2 s
   — the fastest of the batch** (the others took 25–46 s). A budget-exhausted run
   is the *slowest*, so this is a different cause. **Not diagnosed.**

Same failure class as the (deleted) translation path: this model burns budget on
`reasoning_content`. It is `temperature=0.4`, so it is stochastic — the same
prompt succeeds and fails across runs.

## Why raising max_tokens is NOT the fix

| max_tokens | empty |
|---|---|
| 2048 | 2 / 10 |
| 4096 | 1 / 10 |

**No conclusion can be drawn from 2/10 vs 1/10** — at n=10 those are
indistinguishable. The measurement does not show that 4096 helps, and mode 2
above proves at least one empty is not about the budget at all. So budget tuning
cannot be the fix.

## Why the eval missed it

`evals/run_eval.py` runs each case **once**. A ~20% stochastic failure is
invisible to a single sample. Four full evals today all reported
`grounding: 31/31`; for the tomato case alone, P(4 clean samples | 20% failure) =
0.8⁴ ≈ **41%** — so the green was partly luck, not evidence.

This is a separate blind spot from the vacuity fixed earlier today: the
assertions are now real, but they are still single-sample.

## Solution

**Guard first, because it is correct regardless of the unknown root cause:** the
user must never receive an empty reply.

1. `_complete_text(messages) -> str` in `engine.py`: call the chat model; if the
   returned content is blank, **retry once**; if it is still blank, return
   `_empty_answer_message()`.
   - Retry is justified by the measurement: failures scatter across runs of the
     *identical* prompt (runs 1 and 3 of 10), i.e. they look independent — so a
     second attempt should usually succeed. **This is an inference, not a
     measurement; the plan verifies it.**
   - Existing exception handling is unchanged: `_llm_unavailable_message` still
     covers "LM Studio unreachable".
2. `_empty_answer_message()`: a distinct, honest user-facing message (Turkish,
   matching the existing fallback's tone). It must NOT claim the model is
   unreachable — it answered, it just produced nothing.
3. `stream_answer()`: track whether any visible token was emitted. If the stream
   ends having emitted nothing, retry once; if still nothing, emit the fallback
   as a token event. Safe because nothing reached the client yet.

## Decisions / constraints

- **No new dependency, no new component.** Same OpenAI-compatible client.
- **Retry only on blank output**, never on a non-empty-but-short answer — the
  model legitimately gives short refusals (`[OFFSCOPE]`).
- **Cost is paid only on failure:** ~20% of calls pay one extra generation
  (~25 s). An empty reply is worse.
- **Markers still apply after the guard**: the retry's text goes through
  `_strip_markers` exactly like a first-attempt answer.
- **`max_tokens` is NOT changed by this work.** 4096 is not demonstrated to help;
  changing it would be a guess dressed as a fix.
- **`.env` drift, fixed in passing:** `.env` (gitignored) sets `TEMPERATURE=0.4`
  and `MAX_TOKENS=2048`, while `config.py` defaults to `temperature=0.2`. Anyone
  cloning the repo — and CI — runs 0.2; the maintainer runs 0.4. Same code,
  different behaviour, and `config.py`'s comment describes 0.2. Align the default
  to the value actually in use and say so in the comment.

## Expected outcome (the verification)

- Unit tests: blank content → retry; blank twice → fallback message, never `""`.
  Both for `answer()` and `stream_answer()`.
- **Live check, 20 runs of the tomato query through `answer()`**: **0 empty**
  answers. Baseline is 2/10 without the guard.
  - If empties remain, the retry does not help and the failures are correlated,
    not independent — report that; do not raise `max_tokens` to paper over it.
- Full eval must stay **31/31** (the guard must not disturb normal answers).

## Out of scope

- **Mode 2 (fast empty) is not diagnosed.** The guard covers it by construction
  but the cause is unknown. Worth a separate look if it survives the retry.
- **Single-sample eval.** Making the eval repeat cases N times would surface
  stochastic failures, but it multiplies a ~20-minute run. Recorded as a known
  blind spot, not addressed here.
