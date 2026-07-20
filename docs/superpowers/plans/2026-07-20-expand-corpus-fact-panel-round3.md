# Expand the corpus_fact Panel, Round 3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add up to 4 new live-validated `corpus-carried` cases to the eval's `corpus_fact` panel (14 → 18), drawn from sources, crops, and claim shapes not already concentrated in the panel.

**Architecture:** Pure DATA authoring on existing machinery. Mine candidate findings from the vector store, author each as an eval case with a pre-registered assertion, then validate it live in BOTH directions (`--faithfulness --repeat 4 --only <id>`): it must ground with the corpus and lose grounding without it. Only `corpus-carried` results ship; everything else is recorded as a drop-log finding. **No code changes** — `run_eval.py`, `engine.py`, the prompt, and `_classify` are untouched.

**Tech Stack:** Python 3.14, chromadb (vector store, gitignored at `data/vector_store/`), LM Studio serving `text-embedding-bge-m3` + gemma at `:1234`, pytest.

**Spec:** `docs/superpowers/specs/2026-07-20-expand-corpus-fact-panel-round3-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **NO code changes.** Only `evals/eval_set.py` is modified. `pytest -q` must read **180** at every commit; a different number means something is wrong.
- **Rule 1 — source paper new to the panel.** Banned: `dp_19393`, `dp_21747`, `dp_1292456`, `dp_1797532`, `dp_19373`, `dp_19394`, `dp_19531`, `dp_21735`, `dp_30475`, `dp_1399494`, `dp_21748`, `dp_1004550`.
- **Rule 2 — crop new or represented at most once.** **Pear is banned outright.** Apple, persimmon, pomegranate, carob, grape, wheat, rangeland/forage: at most ONE further case each across this whole round. Any other crop is open.
- **Rule 3 — claim-shape cap of 3 panel-wide.** New cases allowed per shape: self-fertility verdict **0**; storage duration/condition **1**; nitrogen dose **1**; harvest timing 2; drying pretreatment 2; resistant-cultivar list 2; biocontrol-agent list 2; minimum-diameter threshold 2; bud load 2; any brand-new shape 3.
- **Assertion is frozen before the first run.** Broadening is legitimate ONLY as an alternate notation of the SAME value (`2±0,5` / `2 ± 0.5`). A looser noun or a different claim is forbidden. **The test: same value, or different claim?**
- **Answer-naturalness test.** Would a good answer to this question state this value out loud? A results-table-only cell is dropped BEFORE it is run.
- **`context_any` must be source-specific**, not an echo of the query wording. Exception by convention: local-cultivar cases may use the bare cultivar name (deveci precedent).
- **A normal read of exactly 2/4 does not decide** — escalate to `--repeat 8`.
- **Target +4 is not a commitment.** Budget exhausted at 2 → ship 2 and record why. Never loosen an assertion to reach the number.
- **Ops:** LM Studio must be running with gemma's Max Concurrent Predictions = **1** (parallel 4 overflows the RX 9070 XT VRAM, ~3.5× slower). Run all commands from the repo root (`config.py` uses a relative `env_file=".env"`).
- **Subagents run in the SHARED working tree on branch `expand-corpus-fact-panel-round3`, strictly SEQUENTIALLY — never in a git worktree, never in the background.** A fresh worktree gets tracked files only, and both `data/vector_store/` (the corpus) and `.env` (the model config) are gitignored and untracked — an isolated worktree therefore cannot mine or run the eval at all, which is every task here. Item 32's anti-pattern was **concurrency**, not subagents: a BACKGROUND spawned task switched the branch under the controlling session and its eval fought the main session's eval over the single LM Studio (both ran 1–2.5 h). Sequential foreground subagents on one branch reproduce none of that.
- **Exactly one eval process at a time.** No parallel subagents; the controller runs nothing while a subagent is active. This is the constraint item 32 actually violated.
- **A paused subagent's provisional `corpus_class` labels are untrustworthy** (item 32). If a subagent stops mid-validation, re-run its candidates directly rather than trusting the labels it left behind.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `evals/eval_set.py` | The eval case list (`CASES`) — new case dicts + drop-log comments | **Modified** (only file committed) |
| `<scratchpad>/mine_candidates.py` | One-off mining helper: lists eligible sources + conclusion chunks | Created, **NOT committed** (scratch, per the item-1 precedent) |
| `<scratchpad>/slate.md` | The 15-candidate slate with rule-checks and frozen assertions | Created, **NOT committed** |

`<scratchpad>` = `C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\6d2143f9-0017-40b0-961b-3cfd73d2c194\scratchpad`

---

## Task 1: Mine and rule-check the candidate slate

**Files:**
- Create: `<scratchpad>/mine_candidates.py` (not committed)
- Create: `<scratchpad>/slate.md` (not committed)
- Modify: none

**Interfaces:**
- Consumes: nothing.
- Produces: `slate.md`, a table of up to 15 candidates. Each row: `source_id`, `crop`, `claim_shape`, `proposed_query`, `frozen_answer_any`, `frozen_context_any`, `source_quote`. Tasks 2–4 consume these rows in order and may not invent candidates outside the slate.

**Context:** The store holds 76,798 chunks; metadata keys are `source` (e.g. `dp_1000173.pdf`), `year`, `era`, `page`, `chunk_index`. A verified scan found **353** `dp_` sources outside the banned list that contain a conclusion-marked chunk, so there is ample raw material — the constraint is assertion quality, not supply.

- [ ] **Step 1: Write the mining helper**

Create `<scratchpad>/mine_candidates.py`:

```python
"""One-off: list eligible sources whose conclusion section holds a concrete finding."""
import re
from src.ingest import get_vector_store

BANNED = {
    "dp_19393", "dp_21747", "dp_1292456", "dp_1797532", "dp_19373",
    "dp_19394", "dp_19531", "dp_21735", "dp_30475", "dp_1399494",
    "dp_21748", "dp_1004550",
}
# Conclusion/recommendation section markers (TR).
MARK = re.compile(r"sonu[cç] ve [oö]neri|4\. *sonu[cç]|sonu[cç]lar", re.I)
# A concrete finding: a number with a unit, or a named-cultivar recommendation.
VALUE = re.compile(
    r"\d+[.,]?\d*\s*(kg/da|kg/ha|mm|cm|g|°c|gün|ay|hafta|adet|göz|%)", re.I
)

def scan():
    coll = get_vector_store()._collection
    out, off = {}, 0
    while True:
        # Paginate: the store errors with "too many SQL variables" on a full get.
        r = coll.get(limit=5000, offset=off, include=["metadatas", "documents"])
        if not r["ids"]:
            break
        for meta, doc in zip(r["metadatas"], r["documents"]):
            src = meta["source"].replace(".pdf", "")
            if not src.startswith("dp_") or src in BANNED:
                continue
            if MARK.search(doc or "") and VALUE.search(doc or ""):
                out.setdefault(src, []).append((meta.get("year"), doc))
        off += 5000
    return out

if __name__ == "__main__":
    found = scan()
    print(f"{len(found)} eligible sources with a valued conclusion chunk")
    for src, rows in sorted(found.items())[:60]:
        year, doc = rows[0]
        print(f"\n=== {src} ({year}) — {len(rows)} chunk(s)")
        print(doc[:700].replace("\n", " "))
```

- [ ] **Step 2: Run the miner and read real sources**

Run: `python <scratchpad>/mine_candidates.py > <scratchpad>/mined.txt`
Expected: a count line, then source blocks with conclusion text.

**Read the printed conclusion text for every candidate you shortlist.** Do not shortlist on a match count. Item 22(e): `amasya`'s 33 hits were a province name in a beetle survey and `gemlik`'s were olive-oil authenticity — both looked like strong candidates by number and were worthless. If the printed text does not contain the finding, re-run with a wider slice or open the source PDF under `docs/books/`.

- [ ] **Step 3: Draft the slate with frozen assertions**

Create `<scratchpad>/slate.md` with up to 15 rows. For each candidate record, in this order:

1. `source_id` and year
2. `crop`
3. `claim_shape` (which Global-Constraint bucket it falls in)
4. **Rule check:** R1 pass (source not banned) / R2 pass (crop allowed, and count the crop against any candidate already on the slate) / R3 pass (shape still under the cap, counting slate-mates)
5. `proposed_query` — a natural question a real user would ask, in Turkish
6. `frozen_answer_any` — the value, plus alternate NOTATIONS of the same value only
7. `frozen_context_any` — a source-specific phrase from the retrieved chunk, absent from the query wording
8. `source_quote` — the paper's own sentence, copied from the mined text

Apply the answer-naturalness test now and drop failures here, before any run: if the value would only ever appear in a results table, it is not a candidate.

- [ ] **Step 4: Self-check the slate against the rules**

Verify by counting across the WHOLE slate, not per-row:
- No banned source appears.
- Pear appears zero times.
- Apple / persimmon / pomegranate / carob / grape / wheat / rangeland appear **at most once each** across the slate.
- Self-fertility shape appears zero times; storage-duration at most once; nitrogen-dose at most once.

Expected: every check passes. Fix the slate if not — it is cheaper to fix here than after a validation run.

- [ ] **Step 5: Report the slate**

Do NOT commit (scratch files). Report to the reviewer: candidate count, the crop distribution, and the shape distribution. This is the gate before any LM Studio time is spent.

---

## Task 2: Author and validate candidates 1–5

**Files:**
- Modify: `evals/eval_set.py`
- Test: live validation via `evals/run_eval.py` (no unit-test file changes)

**Interfaces:**
- Consumes: `slate.md` rows 1–5 from Task 1.
- Produces: 0–5 new case dicts appended to `CASES` in `evals/eval_set.py`, each with `"corpus_fact": True` and a `"corpus_class"` recorded at its live-measured quadrant; plus drop-log comments for candidates that did not ship.

**Context:** Case dicts live in `evals/eval_set.py` in themed blocks (`# --- local: ...`, `# --- horticulture technique ...`, `# --- Zone-4 ...`). Append each new case to the block matching its category. Existing cases in that file are the format reference — match their comment style, which records the source id, the paper's own finding, and the live-measured counts.

- [ ] **Step 1: Write the case dict for candidate 1 — assertion frozen**

Append to the matching block in `evals/eval_set.py`. Shape (fill from the slate row; `corpus_class` is deliberately NOT yet written — it records a measurement that has not happened):

```python
    {"id": "<zone>_<subject>_<fact>", "category": "<local|horticulture|nutrition|disease>",
     "corpus_fact": True,
     "query": "<slate proposed_query>",
     "retrieval": "nonempty", "products": "none",
     "context_any": [<slate frozen_context_any>],
     # <source_id> (<authors; region>): the study's own conclusion states
     # "<source_quote>" - a <finding type> a natural answer states, not a
     # results-table cell.
     "answer_any": [<slate frozen_answer_any>]},
```

Note `"products"`: use `"none"` unless the question is genuinely about plant nutrition, in which case use `"some"` (the `quant_wheat_nitrogen_dose` and `quant_mera_nitrogen_dose` precedent).

- [ ] **Step 2: Run the ablated direction FIRST**

Run: `python -m evals.run_eval --faithfulness --repeat 4 --only <id>`

Read both numbers off the output: the normal hit count and the ablated hit count, plus the `_classify` label.

Running the ablated direction first matters conceptually: **a case that grounds with an empty corpus is already dead**, whatever it does normally. That is the cherry/apricot failure mode, and it is cheaper to see it immediately.

Expected for a shipping candidate: ablated **0/4** (or 1/4), normal **≥2/4**, label `corpus-carried`.

- [ ] **Step 3: Escalate if the normal read is exactly 2/4**

If and only if normal read exactly 2/4, run: `python -m evals.run_eval --faithfulness --repeat 8 --only <id>`

Expected: a decisive read. `≥4/8` with ablated ≤1 → genuine (the bpmorettini precedent: 2/4 was sampling noise, 7/8 real). `0–1/8` → retrieval-broken (the guarbean precedent: 2/4 read, 0/8 real). Record whichever count you acted on.

- [ ] **Step 4: Ship it or drop it — do not retune**

**If `corpus-carried`:** add the measured line to the case's comment and add the class field:

```python
     "corpus_class": "corpus-carried",
```
```python
     # corpus-carried (live 2026-07-20): normal 4/4, ablated 0/4.
```

**If NOT corpus-carried:** delete the case dict and replace it with a drop-log comment in the same block, following the existing drop-log format in the file:

```python
    # DROPPED 2026-07-20: <id>, "<query>" asserting <source_id>'s <finding>.
    # <label> (normal N/4, ablated M/4): <one sentence on why>. Not retuned.
```

**Forbidden:** widening `answer_any` to rescue a red case. If the model will not state the value with the corpus present, the assertion is not answer-natural and the case measures nothing — the cherry, vetch, and guarbean rule. A model-carried result is a legitimate map finding, not a failure to fix.

- [ ] **Step 5: Repeat Steps 1–4 for candidates 2, 3, 4, 5**

One candidate at a time, each fully validated before starting the next. Do not batch the runs — a shared run makes it ambiguous which case produced which count.

- [ ] **Step 6: Verify no code drift**

Run: `python -m pytest -q`
Expected: `180 passed`. Any other number means a non-data change slipped in; find and revert it.

- [ ] **Step 7: Commit**

```bash
git add evals/eval_set.py
git commit -m "Add round-3 corpus_fact cases from slate 1-5"
```

- [ ] **Step 8: Check the stopping rule**

Count corpus-carried cases shipped so far this round. **If it is already 4, STOP — skip Tasks 3 and 4** and go to Task 5. The 15-candidate budget is a cap, not a quota.

---

## Task 3: Author and validate candidates 6–10

**Files:**
- Modify: `evals/eval_set.py`
- Test: live validation via `evals/run_eval.py`

**Interfaces:**
- Consumes: `slate.md` rows 6–10 from Task 1; the cases shipped by Task 2 (their crops and claim shapes count against the Global-Constraint caps).
- Produces: further case dicts / drop-log comments in `evals/eval_set.py`.

**Context:** Before authoring, re-count the caps including everything Task 2 shipped. A slate row that was legal when drafted may now be illegal — e.g. if Task 2 shipped the one permitted storage-duration case, a storage-duration row here is now over the cap and must be skipped, not squeezed in.

- [ ] **Step 1: Re-check the caps against what Task 2 shipped**

Run: `python -c "from evals.eval_set import CASES as C; cf=[c for c in C if c.get('corpus_fact')]; print(len(cf)); [print(c['id'], c.get('corpus_class')) for c in cf]"`

Expected: 14 + however many Task 2 shipped. Cross off any slate row whose crop or claim shape is now at its cap.

- [ ] **Step 2: Write the case dict for the next candidate — assertion frozen**

Append to the matching block in `evals/eval_set.py`, `corpus_class` deliberately omitted until measured:

```python
    {"id": "<zone>_<subject>_<fact>", "category": "<local|horticulture|nutrition|disease>",
     "corpus_fact": True,
     "query": "<slate proposed_query>",
     "retrieval": "nonempty", "products": "none",
     "context_any": [<slate frozen_context_any>],
     # <source_id> (<authors; region>): the study's own conclusion states
     # "<source_quote>" - a <finding type> a natural answer states, not a
     # results-table cell.
     "answer_any": [<slate frozen_answer_any>]},
```

- [ ] **Step 3: Run both directions**

Run: `python -m evals.run_eval --faithfulness --repeat 4 --only <id>`
Expected for a shipping candidate: ablated 0/4 (or 1/4), normal ≥2/4, label `corpus-carried`.

If normal reads exactly 2/4, escalate: `python -m evals.run_eval --faithfulness --repeat 8 --only <id>` — `≥4/8` with ablated ≤1 is genuine; `0–1/8` is retrieval-broken.

- [ ] **Step 4: Ship it or drop it — do not retune**

**If `corpus-carried`:** add `"corpus_class": "corpus-carried",` to the dict and a `# corpus-carried (live 2026-07-20): normal N/4, ablated M/4.` comment line.

**If NOT:** delete the dict, leave a drop-log comment:

```python
    # DROPPED 2026-07-20: <id>, "<query>" asserting <source_id>'s <finding>.
    # <label> (normal N/4, ablated M/4): <one sentence on why>. Not retuned.
```

Widening `answer_any` to rescue a red case is forbidden — cherry, vetch, guarbean.

- [ ] **Step 5: Repeat Steps 2–4 for the remaining candidates in rows 6–10**

One at a time, fully validated before the next.

- [ ] **Step 6: Verify no code drift**

Run: `python -m pytest -q`
Expected: `180 passed`.

- [ ] **Step 7: Commit**

```bash
git add evals/eval_set.py
git commit -m "Add round-3 corpus_fact cases from slate 6-10"
```

- [ ] **Step 8: Check the stopping rule**

If 4 corpus-carried have shipped this round, **STOP — skip Task 4** and go to Task 5.

---

## Task 4: Author and validate candidates 11–15

**Files:**
- Modify: `evals/eval_set.py`
- Test: live validation via `evals/run_eval.py`

**Interfaces:**
- Consumes: `slate.md` rows 11–15; everything Tasks 2–3 shipped (counts against the caps).
- Produces: the final case dicts / drop-log comments in `evals/eval_set.py`.

**Context:** This task exhausts the 15-candidate budget. Reaching its end with fewer than 4 shipped is an ACCEPTABLE outcome, explicitly allowed by the spec: ship what validated and record the shortfall. Do not mine a 16th candidate and do not loosen an assertion to close the gap.

- [ ] **Step 1: Re-check the caps against what Tasks 2–3 shipped**

Run: `python -c "from evals.eval_set import CASES as C; cf=[c for c in C if c.get('corpus_fact')]; print(len(cf)); [print(c['id'], c.get('corpus_class')) for c in cf]"`

Cross off any slate row now over its crop or claim-shape cap.

- [ ] **Step 2: Write the case dict for the next candidate — assertion frozen**

```python
    {"id": "<zone>_<subject>_<fact>", "category": "<local|horticulture|nutrition|disease>",
     "corpus_fact": True,
     "query": "<slate proposed_query>",
     "retrieval": "nonempty", "products": "none",
     "context_any": [<slate frozen_context_any>],
     # <source_id> (<authors; region>): the study's own conclusion states
     # "<source_quote>" - a <finding type> a natural answer states, not a
     # results-table cell.
     "answer_any": [<slate frozen_answer_any>]},
```

- [ ] **Step 3: Run both directions**

Run: `python -m evals.run_eval --faithfulness --repeat 4 --only <id>`
Expected for a shipping candidate: ablated 0/4 (or 1/4), normal ≥2/4, label `corpus-carried`.

If normal reads exactly 2/4, escalate: `python -m evals.run_eval --faithfulness --repeat 8 --only <id>`.

- [ ] **Step 4: Ship it or drop it — do not retune**

Same rule as Tasks 2–3: `corpus-carried` gets `"corpus_class": "corpus-carried",` plus a measured-counts comment; anything else is deleted and replaced with a `# DROPPED 2026-07-20: ...` comment recording the label and counts. No widening.

- [ ] **Step 5: Repeat Steps 2–4 for the remaining candidates in rows 11–15**

- [ ] **Step 6: Verify no code drift**

Run: `python -m pytest -q`
Expected: `180 passed`.

- [ ] **Step 7: Commit**

```bash
git add evals/eval_set.py
git commit -m "Add round-3 corpus_fact cases from slate 11-15"
```

---

## Task 5: Full-panel gates and handoff

**Files:**
- Modify: `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md`
- Test: the three exit gates below

**Interfaces:**
- Consumes: the final state of `evals/eval_set.py` after Tasks 2–4.
- Produces: a passing gate record and a handoff memory entry. Nothing else consumes this.

**Context:** Per-case validation proves each case individually; these gates prove the panel as a whole did not drift. Gate 1 is the one that matters — it re-measures every previously-recorded `corpus-carried` case and exits 1 if any regressed. Expect this run to take a while (each case runs normal + ablated × 4 samples against a local model).

- [ ] **Step 1: Gate 1 — whole-panel drift guard**

Run: `python -m evals.run_eval --faithfulness --repeat 4`
Expected: exit 0, and a scoreboard tally showing the 13 pre-existing corpus-carried cases still corpus-carried plus whatever shipped this round.

If a PRE-EXISTING case regressed, that is a real finding, not a nuisance: nothing in this round changed code or corpus, so a regression means either sampling noise (re-run that case with `--repeat 8` before concluding anything) or a genuine drift worth investigating. Do not paper over it.

- [ ] **Step 2: Gate 2 — local ablation**

Run: `python -m evals.run_eval --no-context --only local`
Expected: exit 0, with the verdict line reporting that every `local` case lost grounding under ablation.

- [ ] **Step 3: Gate 3 — no code drift**

Run: `python -m pytest -q`
Expected: `180 passed`.

- [ ] **Step 4: Record the round in the handoff memory**

Append a new numbered item to `memory/handoff-next-steps.md` following the existing item format. It must record:
- final panel size and corpus-carried count (from `--faithfulness` output, not from memory)
- the diversity rule this round pre-registered, and that it binds future rounds
- **every dropped candidate with its measured label and counts** — so a future session does not re-chase them as data gaps
- the observed hit rate versus item 32's, since the spec predicted it would fall

State the count the way the spec's §5 requires: "N of the M cases we BUILT to need the corpus do" — **not** a percentage of user questions. The denominator is small and self-selected. Writing it the other way is the vanity-metric reflex this project keeps catching (items 4, 12, 22e, 31).

- [ ] **Step 5: Commit**

```bash
git add evals/eval_set.py
git commit -m "Record round-3 panel gates"
```

(The memory file lives outside the repo and is not committed.)

- [ ] **Step 6: Report for review**

Report: cases shipped, cases dropped with labels, the three gate results, and the final panel composition by source / crop / claim shape — the last one is what this round was actually for.

---

## Definition of Done

- [ ] Up to 15 candidates mined; every shipped case clears rules 1–3 counted panel-wide.
- [ ] Every shipped case has a live-measured `corpus_class` and a comment recording its counts.
- [ ] Every non-shipping candidate has a drop-log comment with its label and counts.
- [ ] `python -m evals.run_eval --faithfulness --repeat 4` exits 0.
- [ ] `python -m evals.run_eval --no-context --only local` exits 0.
- [ ] `python -m pytest -q` reads 180.
- [ ] `git diff main --stat` shows `evals/eval_set.py` as the only changed file (plus the spec and this plan).
- [ ] Handoff memory updated with the round's results and drops.
