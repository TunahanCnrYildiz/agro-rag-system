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
2. ~~**Fast empty.**~~ **RETRACTED 2026-07-16 — not reproduced.** The claim was
   that a blank at `max_tokens=4096` returning in 21.2 s (the fastest of its
   batch) could not be budget exhaustion, so a second mode existed. It rested on
   **one observation whose `finish_reason` was never recorded** — the field that
   identifies the mode — and on timing alone.
   A dedicated hunt then produced **0 blanks in 40 raw runs** under the
   production config (2048/0.4): `finish_reason` = stop x39, length x1 (that one
   truncated, not blank). Nothing to characterise. Treat "two modes" as
   unconfirmed: the 21.2 s run may have been server state or measurement noise.
   One mode is established: budget exhaustion.

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

## Outcome — MEASURED 2026-07-16

Implemented in `729dd7e`..`e509943`. Suite 114/114.

**Live: the guard is verified end to end.** Across 50 post-guard runs of the
tomato query through `answer()`:

| | runs | result |
|---|---|---|
| first check | 20 | 0 blank first attempts — guard never fired, no regression |
| second check | 30 | **1 blank rescued by the retry**, 0 fallback, 0 blank to the user |

The rescue (run #27) took **70.2 s** against ~21-32 s for its neighbours —
exactly two generations, so the mechanism is confirmed, not inferred: the first
attempt came back blank, the retry produced a normal 1239-char answer, and the
user saw no gap. `fallback: 0` also supports (one observation, right direction)
this spec's inference that the blanks are independent rather than correlated.

**Full eval after the guard: 31/31**, every dimension 31/31 — normal answers
undisturbed.

**Correction to this spec's own framing.** The "2 / 10" above was written up as
"roughly 1 user in 5". That was over-confident: two events at n=10 give a 95% CI
of roughly **[2.5%, 56%]**. Pooling every `answer()` run of this query — **3
blanks in 60** — puts the real rate near **5%**, CI ≈ [1%, 14%]: a quarter of
the number first claimed. The bug is real (3 blanks and 1 truncation directly
observed) but its *frequency* was overstated.

Note the asymmetry worth remembering: this spec correctly refuses to read 2/10
vs 1/10 as evidence that `max_tokens=4096` helps — then built its own headline
number the same way. It is easy to apply that discipline to a hypothesis you are
rejecting and skip it for one you are advancing.

The guard stands regardless, and the rate is why: at ~5% a blank screen is rare
enough to never show up in a single-sample eval, and common enough that users hit
it. The cost is paid only when the model actually returns nothing.

## Out of scope

- **Root cause of the blank.** Budget exhaustion is established; the retry and
  fallback work without needing to explain every blank, which is the point of a
  guard. The "fast empty" second mode was chased and did not reproduce (see
  above) — do not re-open it without a NEW observation that records
  `finish_reason`.
- ~~**Single-sample eval.**~~ Addressed after this work: see
  `2026-07-16-eval-repeat-design.md` (`--repeat` / `--only`).

## Final rate (all first-attempt samples of the tomato query, 2026-07-16)

**3 blanks / 100 runs = 3%**, CI ≈ [0.6%, 8.5%]. The estimate walked
20% → 7% → 5% → 3% as n grew from 10 to 100: the opening 2/10 was variance, and
every intermediate number in this document's history was over-confident. 3% is
also precisely the band a single-sample eval can never see — which is why the
guard is right even though the bug is rare.
