# DergiPark local harvest (round 7) — design

**Date:** 2026-07-22
**Goal:** one small, time-boxed harvest of new Turkish DergiPark agronomy PDFs to
refresh the `corpus_fact` mining pool, then a single mining pass targeting the
under-cap claim shapes on new crops. Ship any clean corpus-carried candidate; if
none, record the harvest as dry and stop.

## Why this, and why bounded

Rounds 5 (DergiPark existing pool) and 6 (FAO/OpenAlex) both measured **dry** for
`corpus_fact` growth. The productive vein that remains is not more scanning of the
corpus as it stands — it is **new source material**. But the value is deliberately
modest and must not be over-invested in:

- The high-yield veins are **closed or full**: the named-plant-material family
  (cultivar / rootstock / variety / resistant-cultivar / region-cultivar
  recommendations) is grandfathered at 5 and closed; input-application-rate (dose)
  is full at 3/3. A harvest CANNOT reopen these.
- The `corpus_fact` panel is a **drift guard, not coverage** ([[do-not-rechase]]):
  a higher count does not mean the corpus answers more real questions. So the honest
  expected value of this harvest is **+1 to +3 drift-guard cases at most**, in the
  low-yield technique/quantitative/storage/irrigation shapes.
- Broad "coverage" harvesting was rejected on evidence: three independent
  measurements found **zero genuine content gaps**, and RAG was measured **not more
  accurate than the model, only more specific/citable**.

Conclusion: harvest is worth ONE small time-boxed round with a pre-committed stopping
rule. It is not worth an open-ended program.

## Scope (YAGNI)

IN: harvest ~120 new PDFs, ingest, a whole-panel regression gate, one targeted mining
pass, ship-or-record.
OUT: any rule/cap change; any FAO/OpenAlex work; any retrieval/prompt change; a second
harvest round (that is a separate future decision if this one proves productive).

## Step 1 — Harvest

Pre-snapshot the current `dp_*.pdf` file list so this round's NEW files are exactly
identifiable (needed for the rollback in Step 2).

```
python -m src.fetch_dergipark --max 120
```
- OAI-PMH over the 16 curated agronomy journals + title/subject scope filter
  (livestock/off-scope dropped by `_OFFTOPIC_REC`).
- Incremental: files already in `docs/books/` or `_offtopic/` are skipped
  (`_is_pruned`), so only genuinely new PDFs download.
- Rate limits: DergiPark returns HTTP 429 hard on PDF downloads; the fetcher honors
  Retry-After + backoff (PDF_DELAY=2s, 4 retries). Slow — run in the background.

Off-topic cleanup (the OAI title/subject filter misses ~16% of livestock papers):
```
python -m src.fetch_dergipark --clean-offtopic          # report-only first
python -m src.fetch_dergipark --clean-offtopic --apply  # move leaks to _offtopic/, delete chunks
```

**Signal to record:** `--max 120` is a ceiling; incremental skipping may land far
fewer. If very few new files download (e.g. <20), that itself means the curated
DergiPark list is exhausting — record it.

## Step 2 — Ingest + regression gate (safety)

New papers added to the store can create sibling collisions that regress an EXISTING
corpus-carried case (a new paper outranks the old verdict chunk — the dp_19448→dp_19426
failure from round 5). The gate proves "we broke nothing" BEFORE mining for new gains.

```
python -m src.ingest        # embeds only new PDFs (incremental); .env must be bge-m3
```

Three layers, cheap → expensive:

1. **`python -m evals.run_eval --fast`** (no LLM, seconds) — ret+ctx for all 54 cases.
   ctx is **deterministic** (retrieval), so this cheaply catches a collision: any
   corpus-carried case flipping `ctx=True → False` means a new paper displaced its
   verdict chunk. **Take a `--fast` baseline BEFORE the harvest** and diff.
2. **`python -m evals.run_eval --faithfulness --repeat 4`** (whole panel, the
   pre-registered drift guard) — grounding re-classification. Every flagged case is
   measured once at `--repeat 8 --only <id>`; that verdict is final (two-stage gate).
   A recorded `corpus-carried` case re-classifying = real regression.
3. **`python -m pytest -q`** → must stay 187.

**Rollback if a real regression appears:** using the Step-1 snapshot, delete this
round's new dp_ chunks from the store and move their PDFs to `_offtopic/` (ingest
skips that dir). Fully reversible; `src/` is never touched, so no code rolls back.

**Ordering is load-bearing:** the collision gate (`--fast`) must pass BEFORE mining.
Prove "nothing broke" first, then look for new gains.

## Step 3 — Mining pass (new files only)

Scan ONLY this round's new dp_ files (round 5 recorded the existing pool dry — do not
re-scan it). Reuse the round-5 method: own-voice conclusion marker + value, two passes
(numeric, and technique-name excluding cultivar terms).

**Target — under-cap, non-plant-material shapes only:**

| Shape | Free slots | Crop constraint |
|---|---|---|
| graft-material state | 3 | not grape |
| harvest-timing / drying / biocontrol-list / min-diameter / bud-load / sowing-date | 2 each | technique/quantitative |
| training-system | 2 | not tomato |
| irrigation-level | 2 | not forage |
| sowing-implement | 2 | not maize |
| storage duration/condition | 1 | — |
| brand-new shape | 3 | cleanest path |

**SKIP (closed/full):** input-application-rate (dose, 3/3); named-plant-material family
(cultivar/rootstock/variety/resistant-cultivar/region-cultivar recs, 5, closed).

**Crop exclusion:** maize / forage / grape / pear. Prefer a brand-new crop (0 slots)
or one at 1.

**Per-candidate quality gate (freeze the assertion before the first run):**
1. Answer-naturalness — would a good answer state this value out loud (not a
   results-table cell)?
2. Own voice — the paper's own conclusion, not cited literature.
3. Anchors verified against the STORED CHUNK TEXT — source-unique (case-insensitive)
   AND present in the live retrieved context (guard against U+2019 / line-break death).
4. Mine-time collision check — any same-crop/same-input sibling paper that could take
   the retrieval path?
5. Measured both directions — normal `--only` (ret+ctx+ground green) AND ablated red
   via `--faithfulness --repeat 4 --only`. A model-carried read is kept as DATA, not
   shipped as corpus-carried.

## Step 4 — Decision, verification, recording

**Ship path (≥1 clean corpus-carried candidate):**
- Add the case to `eval_set.py` with NO `corpus_class` until measured; freeze-before-run
  note + anchor provenance (explicit `’`/line-break escapes where relevant).
- Measure; if corpus-carried, stamp `corpus_class: "corpus-carried"` + the measurement
  note (normal N/N, ablated 0/N, ret/ctx True).
- Whole-panel verify: `--fast` (no ctx regression) + `pytest -q` (new count) + a final
  `--faithfulness --repeat 4` green.
- Commit + push (concise English message, no co-author trailer).

**Dry path (no candidate / all model-carried or red):**
- Add no case. The new PDFs stay in the corpus (freshness) — Step 2 already proved no
  regression, so no rollback.

**Recording (either path):**
- New findings doc `docs/superpowers/2026-07-22-round7-harvest-findings.md`: PDFs
  downloaded, new chunk count, regression-gate result, mining result (ship/dry), and
  the harvest's yield (how many new corpus-carried cases, or 0).
- Memory: `handoff-next-steps` (round-7 outcome + current panel/chunk counts) and
  `do-not-rechase` (harvest attempted; productive or dry).
- **If very few PDFs downloaded OR the harvest is dry:** record in `do-not-rechase`
  that DergiPark harvesting no longer opens the vein and the `corpus_fact` program is
  exhausted across all paths — so a future session does not propose this round again.

## Success criteria

- No regression to the existing panel (the three Step-2 gates pass, pytest 187).
- Either: ≥1 new corpus-carried case shipped with both directions measured; OR a
  recorded, evidence-backed "harvest dry" finding. Both are acceptable outcomes; a
  padded or tuned-green case is not.
