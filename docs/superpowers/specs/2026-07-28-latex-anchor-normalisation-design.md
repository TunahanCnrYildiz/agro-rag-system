# LaTeX anchor normalisation — design

**Date:** 2026-07-28
**Status:** Approved design, pending implementation.
**Goal:** Stop the eval reporting a false red when the model states the right value in LaTeX
notation. This is an instrument fix, not a case fix.

## The defect, with proof

Full run 2026-07-28 (55 cases, `local:google/gemma-4-12b-qat`): **54/55**, single red
`local_deveci_pear` with `ground=False` and `ret/ctx/prod/guard` all True.

The logged answer shows the model stated the fact correctly:

```
... $2\pm0,5^\circ\text{C}$ sıcaklıktaki soğuk hava depolarının ...
```

The case's anchors are the Unicode spellings — `2±0,5`, `2±0.5`, `2 ± 0,5`, `2 ± 0.5` — so
`_matches` could not see it. Replaying the logged answer through a de-LaTeXed copy makes the
anchor match (verified, not assumed).

**So this is not a grounding failure.** It is the same class as the round-4 dead-anchor lesson:
*an anchor the matcher cannot see does not fail loudly — it reads as a finding about the
corpus rather than as a defect in the instrument.*

**Scope, measured across all 55 logged answers:** 2 answers contain LaTeX markup.
`cassava_fert_en` carries `$P_2O_5$` / `$K_2O$` but grounds anyway (its anchors are words);
only `local_deveci_pear` is harmed. So the defect is narrow **today**, and specific to
numeric/symbolic anchors — which is precisely the panel's most-invested family (`quant_*`,
`local_*` value claims like `6 g/saksı`, `1 kg/ha`, `%75 tarla kapasitesi`).

## Why fix the instrument rather than widen the one anchor

- Widening `local_deveci_pear`'s `answer_any` with the LaTeX spelling is whack-a-mole: it
  fixes one anchor and one spelling, and it buries an instrument defect inside a case's claim
  list. **An anchor list should describe the claim, not the model's formatting habits.**
- The standing rule permits this: *"Broadening is legitimate ONLY as an alternate NOTATION of
  the same value. The test: same value, or different claim?"* `$2\pm0,5$` and `2±0,5` are the
  same value. This is unlike the two dropped cases (`P2O5`→`fosfor`, `20 veya 40 cm`→`20-40 cm`),
  which changed the claim.
- This is **not** "tuning to green". The model produced the right answer; the instrument was
  blind to it.

## Design

Add `_normalize_latex(text: str) -> str` to `evals/run_eval.py`, applied to the **text**
argument inside `_matches` — never to the anchors.

Handled (the observed defect plus its obvious neighbours):

| LaTeX | becomes |
|---|---|
| `\pm` | `±` |
| `\circ` | `°` |
| `\times` | `×` |
| `\approx` `\leq` `\geq` | `≈` `≤` `≥` |
| `\text{...}` / `\mathrm{...}` | the braces' contents |
| `\,` `\;` `\!` (spacing) | removed |
| `$` (math delimiters) | removed |

Deliberately NOT handled: general `_` subscripts and `{}` outside `\text`/`\mathrm`. They add
risk for no measured benefit — the only observed subscript case (`$P_2O_5$`) grounds fine.

### Blast radius: two call sites, and the guardrail is untouched

`_matches` has exactly two production callers: `_context_ok` (`context_any`) and `_answer_ok`'s
grounding half (`answer_any`). **`answer_none` (the guardrail) uses plain substring matching and
does NOT go through `_matches`** — so guardrail semantics are unchanged by this design. That is
deliberate: the guardrail's plain-substring behaviour is a documented choice ("a boundary here
would let a banned phrase hide inside a bigger token"), and changing it is a separate decision.

### Safety property that must survive

Normalisation happens **before** the existing regex, so the left-boundary and trailing-digit
guards still apply to the normalised text. In particular `2±0,50` must still NOT match `2±0,5`.
This is the property most at risk from a careless "just strip symbols" implementation and is
tested explicitly.

## Verification

1. **Unit tests** (committed): the LaTeX form matches; the digit-guard survives normalisation;
   plain text is unaffected; a `\text{}` wrapper unwraps.
2. **Whole-panel replay, no LLM** (one-off, reported not committed): re-score all 55 answers
   from `evals/runs/20260728T110725Z-full.jsonl` under the old and new matcher and confirm
   **only `local_deveci_pear` changes**. This is the safety net that makes an instrument change
   affordable — it costs seconds instead of a 20-minute re-run, and it exists only because the
   answer log was added earlier the same day.
3. `python -m pytest -q` green.

## Recorded open question — do NOT treat as settled

The panel's recorded flake statistics were computed from red/green counts that could include
notation misses: `local_deveci_pear` is recorded as grounding ~6-7/8, and
`quant_rose_pot_fertilizer_dose` at `p ≈ 0.625` — the latter carries an explicit drop trigger
tied to that falling `p`, and the two-stage gate's false-alarm arithmetic is derived from these
numbers. **If some historical reds were instrument artifacts, those `p` values are understated.**
This design does not attempt to re-derive them. The answer log now records every sample, so the
question answers itself over future runs — revisit before acting on the rose drop trigger.
