# Eval answer log — design

**Date:** 2026-07-28
**Status:** Approved design, pending implementation plan.
**Goal:** Persist the answer text (and recommended products) the eval generates, so a case's
behaviour can be diagnosed after the run instead of guessed at.

## Why

The eval scores each sample into booleans and **discards the answer text**. `run()` calls
`engine.answer()` (`evals/run_eval.py:246`) and keeps only `grounding`/`guardrail`/`products`;
`run_faithfulness()` keeps only `.answer` long enough to score it (`:372`).

That cost a real diagnosis. The NOPRODUCT-backstop round-2 measurement closed with **two
leakers unresolved** — `pollination_squash` (`tozla`) and `local_hachiya_persimmon` (`kurut`)
— cases whose activity terms ARE in the coverage list yet still surfaced products. The
recorded finding literally reads "harness doesn't save answer texts, so exact cause
unresolved." The same gap blocks the open micronutrient watch item (`_NUTRITION_TERMS` is
macro-only; a demir/çinko answer could be wrongly suppressed) — that is a question about what
the answer *said*, unanswerable from booleans.

Eval runs are expensive (~25 min locally; hosted runs are capped by a daily free-tier quota),
so a run that throws away its own evidence is the costly kind of waste.

## Binding constraint: do not damage the measuring instrument

This project has been bitten twice by harness defects — a vacuously-passing guardrail and a
crashed ablation stub — and both were invisible for a while. The answer log is therefore a
**pure side effect**:

- It feeds NO value into any verdict, rate, label, or exit code.
- **A write failure must never fail the run.** All I/O is wrapped; on error the log warns
  once and the eval continues. Losing a 25-minute run to a disk error would be a worse bug
  than the one this fixes.

## Architecture

### New module: `evals/answer_log.py`

`evals/run_eval.py` is already 493 lines; the recorder lives in its own focused module.

```python
class AnswerLog:
    def __init__(self, mode: str, provider: str) -> None
    def record(self, *, case: dict, repeat_index: int, ablated: bool,
               result: ChatResult, grounding: bool, guardrail: bool,
               products_ok: bool | None, no_answer: str | None) -> None
    @property
    def path(self) -> Path
    @property
    def count(self) -> int
```

- The file is created lazily on the first `record()`, so a run that writes nothing (e.g.
  `--fast`) leaves no empty file behind.
- `record()` appends one JSON object and flushes immediately.

### Format: JSONL, appended incrementally

**Not a single JSON document written at the end.** `run_faithfulness()` calls `sys.exit()`
mid-run when a sample comes back unanswered (`evals/run_eval.py:380`) — a buffered design
would lose everything precisely in the run whose failure you most need to inspect. One
flushed line per sample survives any abort.

**Location:** `evals/runs/<UTC-timestamp>-<mode>.jsonl`, with `evals/runs/` added to
`.gitignore`. Model ids contain `/` (e.g. `google/gemma-4-26b-a4b-it`), so the provider stamp
goes INSIDE each row, never into the filename.

**Row fields:**

| field | notes |
|---|---|
| `ts` | ISO-8601 UTC, per sample |
| `mode` | `full` (any `run()` call) \| `faithfulness` |
| `provider` | the `_provider_stamp()` value, e.g. `local:google/gemma-4-12b-qat` |
| `case_id`, `category`, `query` | which case produced this |
| `repeat_index` | 0-based sample number within the case |
| `ablated` | `true` for samples generated with the corpus ablated — i.e. the `--no-context` flag in `run()`, and the ablated half of `run_faithfulness()`. Never inferred from `mode`; both modes can produce either value |
| `answer` | the full answer text — the point of the feature |
| `products` | list of recommended product titles (`RecommendedProduct.title`) |
| `grounding`, `guardrail`, `products_ok` | the verdicts as scored, so text and verdict sit together |
| `no_answer` | the `_no_answer_reason()` value, or `null` |

`products_ok` is `null` under `--faithfulness`, which does not gate products.

## Wiring

- **`run()`** — record inside the repeat loop, after `g, gr` are computed, passing
  `ablated=no_context`. `no_answer` samples are recorded too: an unanswered case is exactly
  what someone will want to read.
- **`run_faithfulness()`** — record inside `grounded_hits()`, which takes an `ablated` flag so
  normal and ablated samples land in one file and can be compared directly. Requires a small
  local change: it currently keeps only `.answer`, and must hold the full `ChatResult` to log
  products.
- **`--fast`** — never calls `answer()`; nothing is written and no file is created.
- **End of run** — one summary line: `[answers] wrote N samples -> evals/runs/<file>.jsonl`.

## Testing

- A recorded row contains the expected fields and values for a known case/result (real
  behaviour, not a mock assertion).
- **A failing writer does not propagate:** with I/O forced to raise, the run completes and
  its verdicts are unchanged. This is the constraint above, tested directly.
- Rows are flushed per sample (readable before the run ends) — the property the `sys.exit()`
  abort path depends on.
- Ablated samples are distinguishable (`ablated: true`).
- `--fast` creates no file.

## Out of scope (YAGNI)

No retention/rotation of old run files (~50 KB per run), and no reader/analysis tool — `grep`
and `jq` cover the diagnosis this exists for. No change to any scoring rule, threshold, or
exit code.
