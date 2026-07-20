# Expand the corpus_fact panel, round 3 — source/crop diversity — design

**Date:** 2026-07-20
**Status:** design (approved in brainstorming)
**Extends:** the corpus-dependence map (handoff item 31, spec
`2026-07-18-corpus-dependence-map-design.md`) and its first expansion round
(handoff item 32, spec `2026-07-19-expand-corpus-fact-panel-design.md`).
Those built the `--faithfulness` map + drift guard + `corpus_class`, and grew the
panel to 14 `corpus_fact` cases (13 corpus-carried, 1 model-carried). This work
only AUTHORS MORE cases on that existing machinery.

## 1. Purpose & success criteria

The north star is unchanged (handoff item 26, stated by the user): the RAG must be
full and accurate enough that MOST answers come from the corpus, on ANY model.
The tracked metric is the number of eval cases that genuinely guard retrieval.

But this round adds a second, corrective goal. **The panel's 14 cases are not 14
independent signals.**

| Axis | Concentration |
|------|---------------|
| Source paper | `dp_19393` alone supplies **4** cases (santamaria, ankara, beurrehardy, bpmorettini) |
| Crop | **pear supplies 6** (those 4 + deveci + fireblight-resistant) |
| Claim shape | self-fertility verdict **×5** |

Four cases drawn from one paper share a retrieval path and a chunk family: they go
red together. As a drift guard, correlated cases are worth roughly one independent
signal, so the panel counts 13 corpus-carried while carrying materially fewer.
Continuing to mine the same vein would raise the number without raising the
information.

**This is pure data authoring. No code path changes** — the map, the drift guard,
`_classify`, `corpus_class`, and `_matches` word-boundary anchoring all already
exist and are unchanged.

**Success =**
- Up to **15 candidates** mined and validated in BOTH directions.
- Target **+4 new `corpus-carried` cases** in `evals/eval_set.py`
  (panel 14 → 18; retrieval-guard 14/45 → 18/49).
- Every shipped case satisfies the diversity rule in §2 and records a
  `corpus_class` at its live-validated quadrant.
- `python -m evals.run_eval --faithfulness --repeat 4` exits 0 — no recorded
  corpus-carried case regresses.
- Dropped candidates recorded in-file as findings, the way items 31 and 32 did.

**Expected cost, stated up front so it is not misread as failure:** rule 2 bans
pear, which is where the corpus is RICHEST (the Eğirdir station papers). Mining
where the corpus is thinner is the POINT of this round, and it will lower the hit
rate and raise retrieval-broken drops relative to item 32. **+4 is an optimistic
target, not a commitment.**

**Explicit NON-goals:**
- "All candidates corpus-carried." A **model-carried** result is a legitimate map
  finding (item 28), kept as data, not shipped as a carried guard.
- **Hitting +4 by loosening an assertion.** If the budget is exhausted at 2, we
  ship 2 and record why. A case tuned until green asserts nothing — the rule this
  project has re-learned at cherry, vetch, and guarbean.
- Adding corpus data. Three independent measurements (items 1, 28a, 30) found no
  genuine data gap; this round does not reopen that.
- Touching the prompt / grounding discipline (item 26's layer 3). That is a
  separate and larger piece of work.
- A zone quota. Zone is recorded as an outcome, not constrained as an input.

## 2. The diversity rule — pre-registered, applies to NEW cases only

A candidate must clear all three before its first line is written. The existing 14
cases are untouched; every one remains a valid guard.

**Rule 1 — the source paper is new to the panel.** Banned:
`dp_19393`, `dp_21747`, `dp_1292456`, `dp_1797532`, `dp_19373`, `dp_19394`,
`dp_19531`, `dp_21735`, `dp_30475`, `dp_1399494`, `dp_21748`, `dp_1004550`.

**Rule 2 — the crop is new, or represented at most once.**
- **Pear is banned outright** (6 cases).
- Apple, persimmon, pomegranate, carob, grape, wheat, and rangeland/forage are at
  1 each: **at most one further case each**, panel-wide across this round.
- Any other crop is open.

**Rule 3 — claim-shape cap of 3, panel-wide.** No claim shape may exceed three
cases in the panel. Current counts, and what each permits:

| Claim shape | Now | New allowed |
|---|---|---|
| self-fertility verdict | 5 | **0** |
| storage duration / condition | 2 | 1 |
| nitrogen dose | 2 | 1 |
| harvest timing | 1 | 2 |
| drying pretreatment | 1 | 2 |
| resistant-cultivar list | 1 | 2 |
| biocontrol-agent list | 1 | 2 |
| minimum-diameter threshold | 1 | 2 |
| bud load | 1 | 2 |
| (any new shape) | 0 | 3 |

**Why a cap and not a ban** — this was the one point revised during brainstorming,
and the reasoning is binding on future rounds. A blanket ban on repeating a claim
shape was rejected for three reasons: (a) "same shape" is a judgment call
("150 gün sonra hasat" vs "7 ay depolanabilir" are both durations in a conclusion
sentence), and a rule applied by judgment is a rule that bends under mining
pressure — exactly how guarbean and vetch went wrong; (b) it targets the wrong
correlation, since two cases from different papers on different crops do not fail
together even when they share a shape, and rules 1–2 already close the correlation
that matters; (c) worst, it bans the *validated* selection criterion — "a concrete
value standing in the paper's own conclusion sentence" is not a shortcut, it is the
answer-naturalness test derived from the cherry drop (item 25). Banning it would
mean deliberately choosing less answer-natural assertions, which is the mechanism
that killed cherry, guarbean, vetch, akça, and şebin. The cap keeps the productive
mechanism while closing the one real pile-up (self-fertility ×5).

## 3. Mining → validation pipeline

**Candidate mining (budget: 15 candidates).** Scan the corpus for sources clearing
rules 1–3 and locate **a concrete finding standing in the paper's own
conclusion/recommendation sentence.** Read the source chunk before trusting any
ranking — item 22(e): `amasya`'s 33 hits were a province in a beetle survey and
`gemlik`'s were olive-oil authenticity. A retired metric stays seductive because it
is cheap.

**Assertion discipline — pre-registered, no stretching:**
- `answer_any` is written and **frozen before the first run**.
- Broadening is legitimate **only for an alternate notation of the same value**
  (`2±0,5` / `2 ± 0.5`; mera's "10 kg azot" for "10 kg/da" with "/da" supplied by
  the query). A looser noun or a different claim is forbidden — the vetch
  ("P2O5" → "fosfor") and guarbean ("20 veya 40 cm" → "20-40 cm") rule.
  **The test: same value, or different claim?**
- **Answer-naturalness test:** would a good answer to this question state this
  value out loud? If it would only appear in a results table, drop the candidate
  before running it (cherry).
- `context_any` must be source-specific, not an echo of the query wording (mera).
  **Exception, by established convention:** local-cultivar cases keep the bare
  cultivar name (the deveci precedent) — that echo is accepted, not a defect.

**Validation — every candidate, both directions:**
- `python -m evals.run_eval --faithfulness --repeat 4 --only <id>`, recording the
  normal and ablated hit counts and the `_classify` label.
- **`--faithfulness` alone cannot validate a case (learned in Task 2, confirmed
  at `run_eval.py:323-325`).** It classifies on `answer_any` grounding only and
  never reads `context_any`. A case can read a textbook `corpus-carried 4/4 vs
  0/4` while retrieval never surfaces the source's finding at all — the grounding
  firing on a list-echo (a trial's methods section names every cultivar tested,
  and the model recites the roster). Slate rank 1 died exactly this way.
  **Every candidate must ALSO pass a normal `python -m evals.run_eval --only <id>`
  run with `ret=True ctx=True` before it ships.** This is doubly binding for the
  cultivar-naming claim shape: there the asserted value is structurally present in
  the source's own trial ROSTER as well as in its verdict — a trial's methods
  section names every cultivar it tested — so `--faithfulness` alone can never
  distinguish verdict from roster for that shape. The normal-run `ctx` check is
  what proves retrieval landed on the verdict chunk and not the roster, which
  makes it mandatory there, not merely advisable.
- **Every `context_any` anchor must be verified UNIQUE to its source before the
  case runs.** `context_any` is ANY-semantics, so one non-unique anchor makes a
  green `ctx` meaningless — it cannot prove the intended document was retrieved.
  Task 2 shipped an anchor occurring in the very paper Task 1 had rejected. Check
  uniqueness by paginating the store, **case-insensitively** (the harness's
  `_matches` is case-insensitive, and a source sentence starting "En düşük…" reads
  as zero hits under a naive case-sensitive scan).
- **A normal read of exactly 2/4 does not decide.** Escalate to `--repeat 8`:
  bpmorettini read 2/4 and was noise (7/8 real); guarbean read 2/4 and was
  retrieval-broken (0/8). `--repeat N` is all-or-nothing per sample, so mid reads
  are genuinely ambiguous at n=4.
- Only **corpus-carried** candidates ship. model-carried / retrieval-broken /
  corpus-harmful candidates are recorded in an in-file drop-log comment with their
  measured counts and the reason. These are map data, not failures, and the record
  exists so a future session does not re-chase them as data gaps.

## 4. Deliverable & exit gates

**Deliverable:** edits to `evals/eval_set.py` only — new case dicts plus drop-log
comments. No other file changes.

**Gates, all three must pass before merge:**
1. `python -m evals.run_eval --faithfulness --repeat 4` — whole panel; drift guard
   exits 0 (none of the 13 recorded corpus-carried cases regressed).
2. `python -m evals.run_eval --no-context --only local` — exits 0 (every local case
   loses grounding under ablation).
3. `python -m pytest -q` — **180**, unchanged. No code changed, so a different
   number means something is wrong.

**Process constraint (item 32's anti-pattern).** **Subagents run in the SHARED
working tree on branch `expand-corpus-fact-panel-round3`, strictly SEQUENTIALLY —
never in a git worktree, never in the background.** A fresh worktree gets tracked
files only, and both `data/vector_store/` (the corpus) and `.env` (the model
config) are gitignored and untracked — an isolated worktree therefore cannot mine
or run the eval at all, which is every task here. Item 32's anti-pattern was
**concurrency**, not subagents: a BACKGROUND spawned task switched the branch under
the controlling session and its eval fought the main session's eval over the single
LM Studio (both ran 1–2.5 h). Sequential foreground subagents on one branch
reproduce none of that. **Exactly one eval process at a time** — the controller runs
nothing while a subagent is active; this is the constraint item 32 actually
violated. Also: a subagent that pauses mid-validation leaves provisional
`corpus_class` labels that are untrustworthy; re-validate its work directly rather
than trusting its labels.

**Ops reminder:** validation needs LM Studio serving bge-m3 + gemma at :1234, with
gemma's Max Concurrent Predictions = 1 (parallel 4 overflows the RX 9070 XT VRAM
and costs ~3.5× throughput).

## 5. What this does and does not prove

Unchanged from item 31, and worth restating because the number invites misreading:
the panel is a **guard and a scoreboard over self-selected cases, not a coverage
meter.** "17/18 corpus-carried" would mean "17 of the 18 cases we built to need the
corpus do" — NOT "the corpus carries 94% of user questions." The denominator is
small and chosen by us.

What this round adds beyond raw count: after it, the panel's signal is spread
across more source papers and more crops, so a retrieval regression in one document
family can no longer take down a third of the guard at once — and the count is
closer to the number of independent signals it claims to be.
