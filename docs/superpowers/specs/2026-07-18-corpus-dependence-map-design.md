# Corpus-dependence map — design

**Date:** 2026-07-18
**Status:** design (approved in brainstorming)
**Supersedes/extends:** the `--faithfulness` guard (handoff item 27) and the
corpus-only eval cases (item 25). Builds on the accuracy-map findings (item 28):
the corpus is not more *accurate* than the model, but more *specific + citable*,
so its value is concentrated in local/specific/citable questions.

## 1. Purpose & success criteria

The eval guards retrieval/corpus in only **2 of 33 cases** today (both `local`
pears). That is the instrument blind spot behind every "is this corpus work worth
it?" question the project keeps hitting. This work grows the `corpus_fact` panel
from 2 to ~10 cases spanning topic types, and turns `--faithfulness` from a strict
pass/fail guard into a **corpus-dependence MAP**: a rerunnable scoreboard showing
*where* the corpus is load-bearing, plus a drift guard that protects the cases
proven to depend on it.

**Success =**
- ~8 new candidate `corpus_fact` cases authored and validated BOTH directions.
- The map (scoreboard) runs and reports a quadrant tally across all `corpus_fact`
  cases.
- A committed map artifact records which zones the corpus carries.

**Explicit NON-goal:** "all cases corpus-carried." A candidate that validates as
**model-carried** is a legitimate map finding (the model already knows that topic
— exactly item 28's result), not a failure. Reading the corpus-carried count as
"corpus coverage" is the false-metric this project keeps catching (items 4, 12,
22e); the denominator is small and self-selected.

## 2. Candidate authoring + validation protocol (the bulk of the work)

Two candidates in each of four zones where the corpus MIGHT be load-bearing:

| Zone | What to mine | Expected hit-rate |
|------|--------------|-------------------|
| Local Turkish cultivar | a `dp_` paper's cultivar-specific finding (like the pears) | high |
| Disease/pest organic | a corpus-specific detail: named biocontrol agent, resistant-cultivar list | medium |
| Horticulture technique | a corpus-specific parameter/value | low–medium |
| Gap-crop / quantitative | a specific yield figure, rate, or ratio | low–medium |

**Per candidate:**
1. **Read the source.** Find a real chunk in the store (prefer `dp_`), extract a
   specific finding. No guessing — the item-25 cherry drop happened because a
   plausible-looking assertion was never read against a natural answer.
2. **Answer-natural assertion.** `answer_any` must be a value a *good answer would
   naturally state* — e.g. a storage temperature, not a results-table cell like
   "8.91 g". THE governing lesson (item 25): the pre-registration rule ("assertion
   comes from the document") is necessary but NOT sufficient; ask "would a good
   answer to this question say this number out loud?"
3. **Validate both directions:**
   - **GREEN-normal:** case passes normally (grounding green). Flaky ones checked
     with `--repeat` (deveci is intermittently red ~1/3 — item 25).
   - **RED-ablated:** `--no-context` → the case goes red (the model alone cannot
     supply the fact).
4. **Record the validated quadrant** in `corpus_class` (see §3).
5. **A candidate that fails GREEN-normal is DROPPED, not retuned** (cherry rule) —
   and the drop is recorded in the map artifact as a finding. So ~8 candidates may
   ship as ~5–6 corpus-carried + some model-carried; both counts are the map.

## 3. Reporting + gating change (`--faithfulness` → drift guard)

**Current** (`run_faithfulness`, run_eval.py:243): runs each `corpus_fact` case
normal + ablated, classifies via `_classify`, prints a per-case label + a tally
line, and **exits 0 only if `corpus-carried == total`.** With deliberately
model-carried cases in the panel, that exit condition would fail every run.

**Change — minimal, one code path:**
- **New per-case field `corpus_class`** on every `corpus_fact` case: the quadrant
  measured at validation time (`"corpus-carried"` | `"model-carried"` |
  `"retrieval-broken"` | `"corpus-harmful"`). The 2 existing pears get
  `corpus_class: "corpus-carried"`.
- **Scoreboard:** the existing tally line stays and IS the map — `corpus-carried:
  N | harmful: H | retrieval-broken: R | model-carried: M`, plus per-case live
  labels. (Mostly already present.)
- **Drift gate (new exit condition):** exit 1 **iff any case recorded
  `corpus_class: "corpus-carried"` is live-classified as NOT corpus-carried** (a
  regression: the corpus or retrieval stopped carrying a fact it used to). Cases
  recorded as `model-carried` (or other) do NOT gate — they are data. This keeps
  the 2 pears protected exactly as item 27 intended, while letting the panel hold
  model-carried cases.
- **Flakiness:** deveci is intermittently red normally (item 25). The gate must
  not flap. `--repeat N` already averages; a `corpus-carried` case counts as
  regressed only if it fails green-normal *under the requested repeat*. Document:
  run the drift gate with `--repeat 8` when a red appears, to separate flake from
  regression (same protocol item 25 mandates).

Rejected alternative: a separate `--faithfulness-map` flag leaving `--faithfulness`
untouched. Two code paths, more surface, and the existing tally already does the
scoreboard job — folding both into one flag is simpler and was chosen.

## 4. Deliverable + testing

- **Map artifact:** a committed summary (handoff `handoff-next-steps.md` item, and
  the per-zone result table) recording which zones the corpus carries — the thing
  the "map" framing exists to produce. Includes the dropped candidates as findings.
- **Unit tests** (pure functions, run in CI — the eval itself does not): the drift
  gate's expected-vs-live comparison is a pure helper (e.g. `_drift_ok(cases,
  live_labels)`); test corpus-carried→regressed = fail, model-carried→anything =
  pass, corpus-carried→still-carried = pass. `_classify` already has coverage.
- **Case validation** is live against LM Studio (bge-m3 + gemma), not CI. The eval
  needs the gitignored `data/vector_store/` + the chat model.

## 5. Out of scope (do not build here)

- Freshness-weighted retrieval — decided dead (item 28).
- Prompt grounding-discipline tightening — measured trap (item 26/28): fragile
  retrieval + refusal risk; needs retrieval robustified first.
- Retrieval-fragility fixes — the natural *next* thread this map will inform (the
  santamaria 0-char rephrase, etc.), but a separate spec.
- More data / harvesting — no gaps (measured 3× incl. item 30).
