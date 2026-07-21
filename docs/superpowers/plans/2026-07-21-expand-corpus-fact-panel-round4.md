# Expand the corpus_fact Panel, Round 4 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add up to 4 new live-validated `corpus-carried` cases to the eval's `corpus_fact` panel (18 → 22), drawn from documents, crops, and claim shapes the panel does not already carry.

**Architecture:** Pure DATA authoring on existing machinery. Mine candidate findings from the vector store, author each as an eval case with a frozen assertion, then validate live in a fixed order — anchor uniqueness, ablated direction, normal direction, normal-run `ctx` check, source confirmation. Only `corpus-carried` results ship; everything else becomes a recorded drop-log finding. **No code changes.**

**Tech Stack:** Python 3.14, chromadb (gitignored store at `data/vector_store/`), LM Studio serving `text-embedding-bge-m3` + `google/gemma-4-12b-qat` at :1234, pytest.

**Spec:** `docs/superpowers/specs/2026-07-21-expand-corpus-fact-panel-round4-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **NO code changes.** Only `evals/eval_set.py` is modified. `pytest -q` must read **180** at every commit — that number is the tripwire proving no code changed.
- **Rule 1 — banned sources (already in the panel):** `dp_1399494`, `dp_21748`, `dp_1004550`, `dp_21747`, `dp_19393`, `dp_1292456`, `dp_1797532`, `dp_19373`, `dp_1514564`, `dp_30474`, `dp_1559843`, `dp_19394`, `dp_19531`, `dp_21713`, `dp_21735`, `dp_30475`.
- **Rule 2 — crop cap is ABSOLUTE: no crop may exceed 2 cases panel-wide, ever.** Pear is BANNED (grandfathered at 6). At 1 and may take ONE more each: apple, persimmon, pomegranate, safflower, raspberry, chickpea, carob, grape, maize, wheat, rangeland/forage. Any other crop may take up to 2. `disease_rhizoctonia_biocontrol` is crop-free and consumes no crop slot.
- **Rule 3 — claim-shape cap of 3 panel-wide.** New cases allowed: self-fertility verdict **0** (already at 4, grandfathered); storage duration/condition **1**; nitrogen dose **1**; resistant-cultivar list **1**; region-adapted cultivar rec. **1**; harvest timing 2; drying pretreatment 2; biocontrol-agent list 2; minimum-diameter threshold 2; bud load 2; sowing date 2; any brand-new shape 3.
- **Assertion frozen before the first run.** Broadening is legitimate ONLY as an alternate NOTATION of the SAME value. **The test: same value, or different claim?**
- **Answer-naturalness test:** would a good answer state this value out loud? A results-table-only cell is dropped BEFORE it runs.
- **`context_any` must be source-specific**, not a query echo. Bare cultivar name allowed for local-cultivar cases (deveci precedent).
- **Every `context_any` anchor must be verified UNIQUE to its source before the case runs**, checked **case-insensitively**.
- **`--faithfulness` alone cannot validate a case.** Every case must ALSO pass a normal `run_eval --only <id>` with `ret=True ctx=True`.
- **A normal read of exactly 2/4 does not decide** — escalate to `--repeat 8`.
- **A red case is a map finding to DROP, never to tune green.** Target +4 is not a commitment; budget exhausted at 2 → ship 2 and record why.
- **DO NOT re-mine these** (already measured and dropped): Şebin walnut `dp_1089365`, Hacıhaliloğlu apricot `dp_1217921`, 0900 Ziraat cherry `dp_1154776`, Antalya avocado `dp_19510`, Akça pear `dp_19393`, guar bean `dp_257760`, vetch phosphorus `dp_30458`, Ege durum wheat `dp_21741`, pea sowing date `dp_21712`, plus every source in `docs/superpowers/2026-07-20-round3-candidate-slate.md` §"Rejected at slate time".
- **Execution:** shared working tree, strictly SEQUENTIAL, **exactly one eval process at a time**. Worktree isolation is impossible here — a fresh worktree gets tracked files only and both `data/vector_store/` and `.env` are gitignored.
- **Ops:** run from the repo root (`config.py` reads a relative `.env`). LM Studio at :1234, gemma's Max Concurrent Predictions = 1. Prefix every command with `PYTHONIOENCODING=utf-8` — the Windows console is cp1252 and Turkish characters raise `UnicodeEncodeError`. Scripts placed in the scratchpad need `PYTHONPATH` including the repo root, and on Windows the separator is `;` not `:`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `evals/eval_set.py` | The eval case list (`CASES`) — new case dicts + drop-log comments | **Modified** (the only code-tree file touched) |
| `docs/superpowers/2026-07-21-round4-candidate-slate.md` | The candidate slate + every source rejected before running | **Created and COMMITTED** in Task 1 |
| `<scratchpad>/mine_round4.py` | One-off mining helper | Created, NOT committed |

`<scratchpad>` = `C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\6d2143f9-0017-40b0-961b-3cfd73d2c194\scratchpad`

---

## Task 1: Mine and rule-check the candidate slate

**Files:**
- Create: `<scratchpad>/mine_round4.py` (not committed)
- Create + commit: `docs/superpowers/2026-07-21-round4-candidate-slate.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the committed slate. Each row carries `source_id`, `crop`, `claim_shape`, `proposed_query`, `frozen_answer_any`, `frozen_context_any`, `source_quote`. Tasks 2–3 consume these rows in order and may not invent candidates outside the slate.

**Context:** The store holds 76,798 chunks; metadata keys are `source` (e.g. `dp_1000173.pdf`), `year`, `era`, `page`, `chunk_index`. A full `.get()` fails with "too many SQL variables" — paginate. Round 3's identical filter found 237 eligible sources, and the binding constraint was assertion QUALITY, not supply.

- [ ] **Step 1: Write the mining helper**

Create `<scratchpad>/mine_round4.py`:

```python
"""One-off: list eligible sources whose conclusion section holds a concrete finding."""
import re
from src.ingest import get_vector_store

# Sources already in the panel (rule 1) plus everything already measured and dropped.
BANNED = {
    "dp_1399494", "dp_21748", "dp_1004550", "dp_21747", "dp_19393",
    "dp_1292456", "dp_1797532", "dp_19373", "dp_1514564", "dp_30474",
    "dp_1559843", "dp_19394", "dp_19531", "dp_21713", "dp_21735", "dp_30475",
    # measured and dropped in earlier rounds - do not re-mine
    "dp_1089365", "dp_1217921", "dp_1154776", "dp_19510", "dp_257760",
    "dp_30458", "dp_21741", "dp_21712",
}
MARK = re.compile(r"sonu[cç] ve [oö]neri|4\. *sonu[cç]|sonu[cç]lar", re.I)
VALUE = re.compile(
    r"\d+[.,]?\d*\s*(kg/da|kg/ha|mm|cm|g|°c|gün|ay|hafta|adet|göz|%)", re.I
)


def scan():
    coll = get_vector_store()._collection
    out, off = {}, 0
    while True:
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
    for src, rows in sorted(found.items())[:80]:
        year, doc = rows[0]
        print(f"\n=== {src} ({year}) — {len(rows)} chunk(s)")
        print(doc[:700].replace("\n", " "))
```

- [ ] **Step 2: Run the miner and READ the sources**

Run:
```bash
cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System" && \
SP="C:/Users/tunah/AppData/Local/Temp/claude/D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System/6d2143f9-0017-40b0-961b-3cfd73d2c194/scratchpad" && \
PYTHONIOENCODING=utf-8 PYTHONPATH="D:/Claude Projects/Agro-Botany RAG & Product Linker System;$SP" \
python "$SP/mine_round4.py" > "$SP/mined_round4.txt" && head -3 "$SP/mined_round4.txt"
```
Expected: a count line, then source blocks with conclusion text.

**Read the printed conclusion text for every candidate you shortlist.** Never shortlist on a match count: `amasya`'s 33 hits were a province in a beetle-fauna survey and `gemlik`'s were olive-oil authenticity. If the printed slice does not contain the finding, open the source PDF under `docs/books/`.

- [ ] **Step 3: Draft up to 15 candidate rows**

For each candidate record, in order: `source_id` + year; `crop`; `claim_shape` (which Global-Constraint bucket); **rule check** (R1 source not banned / R2 crop under the absolute cap of 2, counting slate-mates / R3 shape under its cap, counting slate-mates); `proposed_query` (a natural Turkish question a real grower would ask); `frozen_answer_any` (the value plus alternate NOTATIONS of the same value only); `frozen_context_any`; `source_quote` (the paper's own sentence).

Apply the answer-naturalness test HERE and drop failures before any run: if the value would only appear in a results table, it is not a candidate.

- [ ] **Step 4: Self-check the slate by COUNTING across the whole slate**

Not per row — across all rows together:
- No banned source appears, and no previously-dropped source appears.
- Pear appears zero times.
- No crop reaches 3 panel-wide (each of apple, persimmon, pomegranate, safflower, raspberry, chickpea, carob, grape, maize, wheat, rangeland is at 1, so **at most one slate row each**).
- Self-fertility shape appears zero times. Storage, nitrogen dose, resistant-cultivar list, region-adapted cultivar rec: **at most one slate row each**.

Fix the slate if any check fails — cheaper here than after a validation run.

- [ ] **Step 5: Write and commit the slate**

Create `docs/superpowers/2026-07-21-round4-candidate-slate.md` with a header stating it is the round-4 pre-registration, the candidate rows, and a section listing **every source rejected at mining time with the reason** (so round 5 does not re-mine them).

```bash
git add docs/superpowers/2026-07-21-round4-candidate-slate.md
git commit -m "Freeze round-4 candidate slate"
```

- [ ] **Step 6: Report**

Report the candidate count, crop distribution, and claim-shape distribution. This is the gate before any LM Studio time is spent.

---

## Task 2: Author and validate candidates 1–5

**Files:**
- Modify: `evals/eval_set.py`

**Interfaces:**
- Consumes: slate rows 1–5 from Task 1.
- Produces: 0–5 new case dicts in `CASES`, each with `"corpus_fact": True` and a `"corpus_class"` recorded at its live-measured quadrant; drop-log comments for the rest.

**Context:** Case dicts live in themed blocks (`# --- local: ...`, `# --- horticulture technique ...`, `# --- Zone-4 ...`). Append each new case to the block matching its category and match the existing comment style: source id, the paper's own conclusion sentence, why the value is answer-natural, the live-measured counts.

- [ ] **Step 1: Verify the candidate's `context_any` anchors are UNIQUE — before any run**

Run, substituting the candidate's anchors and source:
```bash
cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System" && PYTHONIOENCODING=utf-8 python -c "
from src.ingest import get_vector_store
from collections import Counter
coll = get_vector_store()._collection
anchors = ['<anchor one>', '<anchor two>']
hits = {a: Counter() for a in anchors}
off = 0
while True:
    r = coll.get(limit=5000, offset=off, include=['metadatas','documents'])
    if not r['ids']: break
    for m, d in zip(r['metadatas'], r['documents']):
        low = (d or '').lower()
        for a in anchors:
            if a.lower() in low: hits[a][m['source']] += 1
    off += 5000
for a in anchors: print(repr(a), '->', dict(hits[a]))
"
```
Expected: every anchor maps to the candidate's source ONLY. If an anchor appears in another document, replace it with a longer source-specific phrase from the same chunk **now**, before the first run. Note the scan is case-insensitive on purpose — a sentence starting "En düşük…" reads as zero hits under a naive case-sensitive check.

- [ ] **Step 2: Write the case dict — assertion frozen, `corpus_class` deliberately omitted**

Append to the matching block in `evals/eval_set.py`:

```python
    {"id": "<zone>_<subject>_<fact>", "category": "<local|horticulture|nutrition|disease>",
     "corpus_fact": True,
     "query": "<slate proposed_query>",
     "retrieval": "nonempty", "products": "none",
     "context_any": [<verified-unique anchors>],
     # <source_id> (<authors; region>): the study's own conclusion states
     # "<source_quote>" - a <finding type> a natural answer states, not a
     # results-table cell.
     "answer_any": [<slate frozen_answer_any>]},
```

Use `"products": "some"` only if the question is genuinely about plant nutrition (the `quant_wheat_nitrogen_dose` / `quant_mera_nitrogen_dose` precedent); otherwise `"none"`.

- [ ] **Step 3: Run the ablated direction first**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 4 --only <id>`

Read the normal and ablated hit counts and the `_classify` label. The ablated direction is read first on purpose: **a case that grounds with an EMPTY corpus is already dead** whatever it does normally, and that is the cheapest elimination.

Expected for a shipping candidate: ablated **0/4** (or 1/4), normal **≥2/4**, label `corpus-carried`.

- [ ] **Step 4: Escalate if the normal read is exactly 2/4**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 8 --only <id>`

Expected: decisive. `≥4/8` with ablated ≤1 → genuine (bpmorettini read 2/4, was 7/8). `0–1/8` → retrieval-broken (guar bean read 2/4, was 0/8). Record whichever count you acted on.

- [ ] **Step 5: Run the normal-run ctx check — the step that catches false guards**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --only <id>`
Expected: `ret=True ctx=True`.

If `ctx=False`, the case does NOT ship even if `--faithfulness` called it corpus-carried: the grounding is firing on something other than the source's finding — a list-echo off a methods roster. Round 3's Ege durum wheat candidate read a textbook 4/4 vs 0/4 and died exactly here.

- [ ] **Step 6: Ship it or drop it — never retune**

**If corpus-carried AND `ctx=True`:** add the class field and the measured lines:
```python
     "corpus_class": "corpus-carried",
```
```python
     # corpus-carried (live 2026-07-21): normal 4/4, ablated 0/4. Normal run also
     # reads ret=True ctx=True, so the grounding is not a list-echo artifact.
```
Then confirm the finding in the source PDF under `docs/books/` before moving on.

**If not:** delete the dict and leave a drop-log comment in the same block:
```python
    # DROPPED 2026-07-21: <id>, "<query>" asserting <source_id>'s <finding>.
    # <label> (normal N/4, ablated M/4): <one sentence on why>. Not retuned.
```

**Forbidden:** widening `answer_any` to rescue a red case. If the model will not state the value with the corpus present, the assertion is not answer-natural and the case measures nothing — the cherry, vetch and guar bean rule.

- [ ] **Step 7: Repeat Steps 1–6 for candidates 2, 3, 4, 5**

One candidate at a time, fully validated before the next. Do not batch runs — a shared run makes it ambiguous which case produced which count.

- [ ] **Step 8: Verify no code drift and commit**

Run: `cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System" && python -m pytest -q`
Expected: `180 passed`.

```bash
git add evals/eval_set.py
git commit -m "Add round-4 corpus_fact cases from slate 1-5"
```

- [ ] **Step 9: Check the stopping rule**

Count corpus-carried cases shipped this round. **If it is 4, STOP — skip Task 3** and go to Task 4.

---

## Task 3: Author and validate the remaining candidates

**Files:**
- Modify: `evals/eval_set.py`

**Interfaces:**
- Consumes: the remaining slate rows; everything Task 2 shipped (which counts against the caps).
- Produces: further case dicts / drop-log comments.

**Context:** Re-count the caps INCLUDING everything Task 2 shipped. A slate row legal when drafted may now be illegal — if Task 2 shipped the one permitted storage-duration case, a storage-duration row here is over the cap and must be skipped, not squeezed in.

- [ ] **Step 1: Re-count the caps against the current panel**

Run:
```bash
cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System" && PYTHONIOENCODING=utf-8 python -c "
from evals.eval_set import CASES as C
cf = [c for c in C if c.get('corpus_fact')]
print('corpus_fact:', len(cf))
for c in cf: print(' ', c['id'], c.get('corpus_class'))
"
```
Cross off any slate row whose crop or claim shape is now at its cap.

- [ ] **Step 2: Verify the next candidate's anchors are UNIQUE — before any run**

Run the same corpus-wide case-insensitive anchor scan as Task 2 Step 1, substituting this candidate's anchors. Expected: every anchor maps to this candidate's source only. Replace a non-unique anchor with a longer source-specific phrase from the same chunk before the first run.

- [ ] **Step 3: Write the case dict — assertion frozen, `corpus_class` omitted**

```python
    {"id": "<zone>_<subject>_<fact>", "category": "<local|horticulture|nutrition|disease>",
     "corpus_fact": True,
     "query": "<slate proposed_query>",
     "retrieval": "nonempty", "products": "none",
     "context_any": [<verified-unique anchors>],
     # <source_id> (<authors; region>): the study's own conclusion states
     # "<source_quote>" - a <finding type> a natural answer states, not a
     # results-table cell.
     "answer_any": [<slate frozen_answer_any>]},
```

- [ ] **Step 4: Run the ablated direction first, then escalate if 2/4**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 4 --only <id>`
Expected for a shipping candidate: ablated 0/4 (or 1/4), normal ≥2/4, `corpus-carried`.

If the normal read is exactly 2/4, run
`PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 8 --only <id>` —
`≥4/8` with ablated ≤1 is genuine; `0–1/8` is retrieval-broken.

- [ ] **Step 5: Run the normal-run ctx check**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --only <id>`
Expected: `ret=True ctx=True`. If `ctx=False` the case does NOT ship, whatever `--faithfulness` said.

- [ ] **Step 6: Ship it or drop it — never retune**

Shipping adds `"corpus_class": "corpus-carried",` plus a comment recording `normal N/4, ablated M/4` and the `ret/ctx` result, then confirm the finding in the source PDF. Anything else is deleted and replaced with:
```python
    # DROPPED 2026-07-21: <id>, "<query>" asserting <source_id>'s <finding>.
    # <label> (normal N/4, ablated M/4): <one sentence on why>. Not retuned.
```
Widening `answer_any` to reach green is forbidden.

- [ ] **Step 7: Repeat Steps 2–6 for the remaining slate rows, or until 4 have shipped**

Reaching the end of the slate with fewer than 4 shipped is an ACCEPTABLE outcome the spec allows. Do not mine a replacement candidate and do not loosen an assertion to close the gap.

- [ ] **Step 8: Verify no code drift and commit**

Run: `cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System" && python -m pytest -q`
Expected: `180 passed`.

```bash
git add evals/eval_set.py
git commit -m "Add round-4 corpus_fact cases from the remaining slate"
```

---

## Task 4: Whole-panel gates and handoff

**Files:**
- Modify: `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md`

**Interfaces:**
- Consumes: the final state of `evals/eval_set.py`.
- Produces: a passing gate record and the memory entry.

**Context:** Per-case validation proves each case individually; these gates prove the panel as a whole did not drift. Gate 1 re-measures every previously-recorded corpus-carried case and takes a while — 22 cases × 2 directions × 4 samples against a local model. Run it in the background and wait rather than running anything else against LM Studio meanwhile.

- [ ] **Step 1: Gate 1 — whole-panel drift guard**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 4`
Expected: exit 0, with the scoreboard showing every previously recorded corpus-carried case still corpus-carried, plus whatever shipped this round.

If a PRE-EXISTING case regressed, that is a real finding: nothing here changed code or corpus, so it is either sampling noise (re-run that case with `--repeat 8` before concluding anything) or genuine drift. Known-noisy cases: `local_deveci_pear`, `local_bpmorettini_pear`, `local_scarletspur_apple`. Do not paper over it.

- [ ] **Step 2: Gate 2 — local ablation**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --no-context --only local`
Expected: exit 0, every `local` case losing grounding under ablation.

- [ ] **Step 3: Gate 3 — no code drift**

Run: `cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System" && python -m pytest -q && git diff --stat main..HEAD`
Expected: `180 passed`, and the only changed files are `evals/eval_set.py`, the spec, this plan, and the round-4 slate. **No file under `src/` may appear.**

- [ ] **Step 4: Update the handoff memory**

Record in `handoff-next-steps.md`: the final panel size and corpus-carried count (read from the `--faithfulness` output, not from memory); that the crop cap is now ABSOLUTE at 2 and binds future rounds; **every dropped candidate with its measured label and counts**; and the observed hit rate versus round 3's ~40%, since the spec predicted it would fall.

State the count the way the spec requires: "N of the M cases we BUILT to need the corpus do" — never as a percentage of user questions.

- [ ] **Step 5: Report for review**

Report: cases shipped, cases dropped with labels, the three gate results, and the final panel composition by source / crop / claim shape.

---

## Definition of Done

- [ ] Up to 15 candidates mined; the slate committed including mining-time rejections.
- [ ] Every shipped case clears rules 1–3 counted panel-wide, has verified-unique anchors, a live-measured `corpus_class`, and a recorded `ret=True ctx=True`.
- [ ] Every non-shipping candidate has a drop-log comment with its label and counts.
- [ ] `python -m evals.run_eval --faithfulness --repeat 4` exits 0.
- [ ] `python -m evals.run_eval --no-context --only local` exits 0.
- [ ] `python -m pytest -q` reads 180 and no `src/` file changed.
- [ ] Handoff memory updated.
