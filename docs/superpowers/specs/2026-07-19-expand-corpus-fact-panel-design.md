# Expand the corpus_fact panel — design

**Date:** 2026-07-19
**Status:** design (approved in brainstorming)
**Extends:** the corpus-dependence map (handoff item 31, spec
`2026-07-18-corpus-dependence-map-design.md`). That work built the `--faithfulness`
map + drift guard + the `corpus_class` field and shipped 8 `corpus_fact` cases
(7 corpus-carried, 1 model-carried). This work only AUTHORS MORE cases on that
existing machinery.

## 1. Purpose & success criteria

The user's goal, stated directly: **raise the corpus-carried count.** Today the eval
guards retrieval/corpus in **8 of 39 cases** (7 recorded `corpus-carried` + 1
`model-carried`). Every other case passes on gemma's own knowledge + the prompt
(the item-25 ablation: grounding/guardrail stayed green with an EMPTY corpus). More
validated corpus-carried cases = a wider, drift-protected retrieval guard, and a
larger, honest dependence-map scoreboard.

**This is pure data authoring. No code path changes** — the map, the drift guard,
`_classify`, and the `corpus_class` field all already exist and are unchanged.

**Success =**
- ~10 candidate `corpus_fact` cases mined + validated BOTH directions.
- Target **+4 to +6 new `corpus-carried` cases** shipped into `evals/eval_set.py`
  (panel 8 → ~12–14; retrieval-guard 8/39 → ~12–14/39).
- Every shipped case has a `corpus_class` recorded at its live-validated quadrant.
- `python -m evals.run_eval --faithfulness --repeat 4` still exits 0 (no drift): all
  cases recorded `corpus-carried` classify corpus-carried live.
- Dropped candidates recorded as findings (in-file comments + handoff item), the way
  item 31 recorded its drops.

**Explicit NON-goal — unchanged from item 31:** "all cases corpus-carried." A
candidate that validates **model-carried** is a legitimate map finding (the model
already knows it — item 28's whole result), kept as DATA, not shipped as a carried
guard. And the corpus-carried count is NOT a coverage meter: "13/39 corpus-carried"
means "13 of the 39 cases we built to need the corpus do", NOT "the corpus carries
33% of user questions". The denominator is small and self-selected (the false-metric
this project keeps catching — items 4, 12, 22e, 31).

## 2. Candidate zones — bias to the proven winners

Every case that validated corpus-carried to date is one of two shapes: a
**Turkey-specific cultivar fact** (deveci / santamaria / ankara pears) or a
**specific technique/quant threshold** (carob graft ≥10 mm, grape 18 göz, wheat
16 kg/da N). Every case that fell to model-carried or was dropped was a **generic**
fact the model already knew (rhizoctonia biocontrol agents, apricot "kurutmalık")
or a non-answer-natural table cell (cherry 8.91 g, walnut protandry).

So this round targets the winning shapes and largely avoids the losers:

| Priority | Zone | What to mine | Why |
|----------|------|--------------|-----|
| PRIMARY | Local Turkish cultivar | a `dp_` paper's cultivar-specific finding (harvest window, self-fertility, a named regional standard) | highest measured hit-rate |
| SECONDARY | Horticulture technique threshold | a corpus-specific parameter a practical answer states (spacing, depth, dose, count) | medium — both technique cases carried |
| CAUTION | Gap-crop / quantitative | a specific rate/ratio/figure | hardest — the model often knows rough rates (item 31: Zone-4 is where drops cluster) |
| AVOID | Generic disease/pest organic | biocontrol agents, generic cultural control | model-carried (measured: rhizoctonia) |

No new harvesting — coverage is measured-complete (items 1, 28a, 30). We mine what is
already in the store.

## 3. Per-candidate authoring + validation protocol (item 25/31, non-negotiable)

For each candidate:

1. **Read the real source chunk.** Page through the store (`store.get`, paginated —
   93k chunks at once errors "too many SQL variables"), find a `dp_` chunk, extract
   a specific finding. No guessing from a paper title (item 31, lesson 22e: candidates
   picked by chunk-count keyword without reading gave bogus facts — "amasya" the
   province, "gemlik" olive-oil authenticity).
2. **Answer-natural assertion.** `answer_any` must be a value *a good answer would
   naturally state out loud* — a storage temperature, a graft diameter, a
   self-fertility verdict — NOT a results-table cell (item 25 cherry drop: `8.91 g`
   is real but never spoken in a "foliar or soil?" answer). THE governing test:
   *would a good answer to this exact question say this out loud?* If it only lives
   in a table, the case goes red normally and measures nothing.
3. **Discriminating `context_any`.** The phrase must be source-unique, not one that
   appears verbatim in many corpus sources (item 31 vetch drop: "6 kg/da P2O5"
   appeared in 5 unrelated papers). Verify uniqueness by a store scan before trusting.
4. **Pre-register, then validate BOTH directions** at the eval's own config with
   `--repeat 4`:
   - **GREEN-normal:** grounds a majority normally (`2*normal_hits >= repeat`).
     Flaky-but-carried is fine (deveci ~6/8); a candidate that is a MINORITY green
     normally is retrieval-broken and DROPPED.
   - **RED-ablated:** `--no-context` (or the map's ablated pass) → a minority green
     (`2*ablated_hits < repeat`). If it grounds a majority ablated, it's
     model-carried → kept as map data, not a carried guard.
5. **Record the validated quadrant** in `corpus_class`. Ship only `corpus-carried`
   as guards; note `model-carried` findings.
6. **A candidate that fails GREEN-normal is DROPPED, not retuned** (cherry rule).
   `answer_any` broadening is legitimate ONLY for alternate notations of the SAME
   value (2±0,5 / 2 ± 0.5), never a looser or different noun (item 31 vetch: "P2O5" →
   "fosfor" is forbidden). Record every drop as a finding.

**Local cultivar cases** additionally set `category: "local"` and MUST pass the
ablation gate `python -m evals.run_eval --no-context --only local` (exit 0 = every
local case lost grounding). Technique/quant cases use their natural category
(`horticulture` / `nutrition`) + `corpus_fact: True`.

## 4. Deliverable + testing

- **Cases** appended to `evals/eval_set.py` with the same commented provenance block
  the existing cases carry (source `dp_` id, the paper's own wording, the validated
  quadrant + date). Dropped candidates recorded as `# DROPPED` comments (as item 31
  did) so they are not silently re-derived.
- **No unit-test change** — no code changed. The existing suite (170 tests) must stay
  green purely because nothing in `src/`/`evals/*.py` logic moved; a new dict in a
  list touches no tested function. Confirm with `python -m pytest -q`.
- **Live validation** (LM Studio, bge-m3 + gemma; the gitignored store):
  - `python -m evals.run_eval --faithfulness --repeat 4` → exit 0, scoreboard shows
    the new corpus-carried cases; no drift on the existing 7.
  - `python -m evals.run_eval --no-context --only local` → exit 0 (all local cases,
    old + new, lose grounding).
  - The new cases must not break the FULL eval's other dimensions
    (retrieval/context/products/answer/guardrail). A `corpus_fact` case is a full
    case; spot-run the affected cases with `--only <id>` in full mode. Existing
    dimensions are unaffected for cases we don't touch (deterministic retrieval).
- **Map artifact:** a handoff `handoff-next-steps.md` item recording the per-zone
  result — which candidates shipped corpus-carried, which fell model-carried, which
  dropped and why — the map framing's whole point.

## 5. Out of scope (do not build here)

- **Any `run_eval.py` / `engine.py` / prompt / retrieval change.** If a candidate
  only validates by changing code, it is out of scope — drop it, note it.
- Freshness-weighted retrieval (dead, item 28); grounding-discipline tightening
  (measured trap, item 26/28); retrieval-fragility fixes (separate thread, item 28a);
  more harvesting (no gaps, item 30).
- Raising the DENOMINATOR framing into a coverage claim — the count is a guard
  scoreboard, not coverage. Stated in §1 so it is not misread later.
