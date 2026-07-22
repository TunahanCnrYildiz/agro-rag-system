# DergiPark Local Harvest (Round 7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harvest ~120 new Turkish DergiPark agronomy PDFs, ingest them, prove the existing eval panel did not regress, then run one targeted mining pass and either ship a clean corpus-carried case or record the harvest as dry.

**Architecture:** This is an OPERATIONAL / measurement pipeline, not a code feature. The harvest, ingest, and eval tools already exist (`src/fetch_dergipark.py`, `src/ingest.py`, `evals/run_eval.py`). The only code that may be written is ONE new eval-case dict in `evals/eval_set.py` (only if a candidate ships) and a throwaway mining scan script. Every stage ends with a concrete command, an expected output, and a decision gate.

**Tech Stack:** Python 3.14, Chroma vector store, LM Studio (bge-m3 embeddings + gemma chat at :1234), OAI-PMH harvest.

## Global Constraints

- Run every command from the repo root: `D:/Claude Projects/Agro-Botany RAG & Product Linker System` (`config.py` reads a relative `.env`).
- `.env` embedding model MUST be bge-m3 (the embedding guard raises otherwise); never re-ingest with nomic.
- LM Studio must be serving bge-m3 + gemma at :1234 for any eval that calls `answer()`.
- Prefix Python commands with `PYTHONIOENCODING=utf-8` (console is cp1252; Turkish output crashes otherwise).
- One eval process at a time; eval generations are slow (~20-30s each). Keep gemma Max Concurrent Predictions = 1.
- Commit messages: concise, English, natural, NO `Co-Authored-By` trailer, no verbose AI body.
- A red/model-carried candidate is DROPPED and recorded, NEVER tuned to green.
- Do NOT change any rule/cap, any FAO/OpenAlex path, or any retrieval/prompt code. Scope is harvest + mine + record only.
- Scratchpad for throwaway snapshots/scripts this round: `C:/Users/tunah/AppData/Local/Temp/claude/D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System/a6e204ab-49ff-4f2b-8f3f-9aebc131cf68/scratchpad` (referred to below as `SCRATCH`). The round is meant to complete in one working session; if it spans sessions, re-create the pre-snapshot from git/store history.

---

### Task 1: Pre-harvest baseline (snapshot + clean `--fast` panel)

**Files:**
- Create: `SCRATCH/dp_before.txt` (list of existing dp_ PDFs)
- Create: `SCRATCH/fast_before.txt` (pre-harvest ret/ctx for all 54 cases)

**Interfaces:**
- Produces: `SCRATCH/dp_before.txt` (Task 2 diffs against it to find new files; Task 4 uses it for rollback), `SCRATCH/fast_before.txt` (Task 4 diffs ctx against it).

- [ ] **Step 1: Snapshot the current dp_ PDF set**

Run:
```bash
ls docs/books/dp_*.pdf > "$SCRATCH/dp_before.txt"; wc -l < "$SCRATCH/dp_before.txt"
```
Expected: a count around 619 (the current dp_ file count). Record the exact number.

- [ ] **Step 2: Confirm the store and models are up**

Run:
```bash
curl -s -m 4 http://localhost:1234/v1/models | grep -o 'bge-m3\|gemma' | sort -u
```
Expected: both `bge-m3` and `gemma` appear. If not, start LM Studio before continuing.

- [ ] **Step 3: Capture the clean `--fast` baseline (no LLM, deterministic ret/ctx)**

Run:
```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval --fast | tee "$SCRATCH/fast_before.txt" | tail -5
```
Expected: a per-case `ret=.. ctx=..` table for all 54 cases and a summary line. This is the pre-harvest truth Task 4 compares against. Every `corpus_fact` case that is currently corpus-carried MUST read `ctx=True` here.

- [ ] **Step 4: (no commit)** — baseline artifacts live in SCRATCH; nothing to commit yet.

---

### Task 2: Harvest new PDFs + off-topic cleanup

**Files:**
- Modify: `docs/books/` (new `dp_*.pdf` downloaded here)
- Create: `SCRATCH/dp_after.txt`, `SCRATCH/dp_new.txt` (this round's new files)

**Interfaces:**
- Consumes: `SCRATCH/dp_before.txt` (Task 1).
- Produces: `SCRATCH/dp_new.txt` (the exact new files — Task 3 ingests them, Task 4 rolls them back if needed, Task 5 scans only them).

- [ ] **Step 1: Dry-run the harvest to preview scope**

Run:
```bash
PYTHONIOENCODING=utf-8 python -m src.fetch_dergipark --max 120 --dry-run 2>&1 | tail -20
```
Expected: a list of candidate articles that would download, minus already-present/pruned files. If the previewed new-download count is very small (<20), note it — it is the "curated list exhausting" signal for Task 7.

- [ ] **Step 2: Run the harvest (background — it is slow due to 429 backoff)**

Run (background):
```bash
PYTHONIOENCODING=utf-8 python -m src.fetch_dergipark --max 120
```
Expected: downloads trickle in past many HTTP 429 + Retry-After waits. Wait for completion (a `--max 150` run previously took a long time pushing through ~254 429s). Do not start the ingest until this finishes.

- [ ] **Step 3: Compute the exact set of new files**

Run:
```bash
ls docs/books/dp_*.pdf > "$SCRATCH/dp_after.txt"
comm -13 "$SCRATCH/dp_before.txt" "$SCRATCH/dp_after.txt" > "$SCRATCH/dp_new.txt"
wc -l < "$SCRATCH/dp_new.txt"
```
Expected: the number of genuinely new PDFs (≤120). Record it. If 0, skip to Task 7 and record "no new material — DergiPark curated list is exhausted."

- [ ] **Step 4: Off-topic cleanup — report first, then apply**

Run:
```bash
PYTHONIOENCODING=utf-8 python -m src.fetch_dergipark --clean-offtopic 2>&1 | tail -20
```
Expected: a report to `docs/offtopic_candidates.txt` of livestock/aquaculture leaks among downloaded PDFs. Review it; then apply:
```bash
PYTHONIOENCODING=utf-8 python -m src.fetch_dergipark --clean-offtopic --apply 2>&1 | tail -20
```
Expected: leaked papers moved to `docs/books/_offtopic/` and their chunks (if any) deleted. Files moved here are removed from `dp_new.txt`'s effective set — re-run Step 3's `comm` if any were applied AFTER a partial ingest (here they are moved before ingest, so `dp_new.txt` minus `_offtopic/` is what ingests).

- [ ] **Step 5: Commit the harvested PDFs (if the repo tracks docs/books)**

Run:
```bash
git status -s docs/books | head
```
If new PDFs show as untracked/tracked changes, commit them:
```bash
git add docs/books
git commit -m "Harvest round 7: add <N> new DergiPark agronomy PDFs"
```
If `docs/books` is gitignored, skip — nothing to commit (record N in Task 7 instead).

---

### Task 3: Ingest the new PDFs

**Files:**
- Modify: `data/vector_store/` (Chroma; gitignored) — new embeddings added.

**Interfaces:**
- Consumes: the new PDFs in `docs/books/` (Task 2).
- Produces: new chunks in the store, keyed by `source` filename (Task 4 gates on them; Task 5 scans them).

- [ ] **Step 1: Record the pre-ingest chunk count**

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "from src import engine; print('chunks before:', engine._get_retriever_store()._collection.count())"
```
Expected: ~76,798 (the current count). Record it.

- [ ] **Step 2: Ingest (incremental — embeds only new PDFs)**

Run (background if large):
```bash
PYTHONIOENCODING=utf-8 python -m src.ingest 2>&1 | tail -15
```
Expected: it skips all files already in the store and embeds only the new dp_ files. Watch for the bge-m3 guard passing (no embedding-model raise).

- [ ] **Step 3: Confirm the new chunks landed**

Run:
```bash
PYTHONIOENCODING=utf-8 python -c "from src import engine; print('chunks after:', engine._get_retriever_store()._collection.count())"
```
Expected: count increased by roughly (new files × ~80 chunks/file). Record the delta — it is the "new chunk count" for Task 7.

---

### Task 4: Regression gate (prove nothing broke) — BEFORE mining

**Files:**
- Create: `SCRATCH/fast_after.txt`

**Interfaces:**
- Consumes: `SCRATCH/fast_before.txt` (Task 1), `SCRATCH/dp_new.txt` (Task 2).
- Produces: a PASS/ROLLBACK decision. Mining (Task 5) only starts on PASS.

- [ ] **Step 1: Re-run `--fast` and diff ctx against the baseline (deterministic collision check)**

Run:
```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval --fast | tee "$SCRATCH/fast_after.txt" | tail -5
diff <(grep -oE '\w+ +ret=\w+ ctx=\w+' "$SCRATCH/fast_before.txt") \
     <(grep -oE '\w+ +ret=\w+ ctx=\w+' "$SCRATCH/fast_after.txt")
```
Expected: **empty diff** for every `corpus_fact` case. Any case flipping `ctx=True → False` means a newly-ingested paper displaced its verdict chunk (the dp_19448→dp_19426 collision class). If that happens, go to Step 4 (rollback).

- [ ] **Step 2: Run the pre-registered drift guard (whole panel, grounding re-classification)**

Run (slow — background):
```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 4 2>&1 | tail -30
```
Expected: exit 0, and every case recorded `corpus-carried` still classifies corpus-carried. If any recorded-corpus-carried case is flagged, measure it once:
```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval --repeat 8 --only <flagged_id> 2>&1 | tail -5
```
A repeat-8 read that stays corpus-carried (normal ≥ n/2, ablated low) clears the flag (a known flaky case: deveci/rose/bpmorettini). A repeat-8 red is a REAL regression → Step 4.

- [ ] **Step 3: Run pytest**

Run:
```bash
PYTHONIOENCODING=utf-8 python -m pytest -q 2>&1 | tail -3
```
Expected: `187 passed`.

- [ ] **Step 4: ROLLBACK (only if Step 1 or Step 2 found a real regression)**

Delete the new files' chunks and move their PDFs out of ingest range:
```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
from pathlib import Path
from src import engine
new = [l.strip() for l in open(r"<SCRATCH>/dp_new.txt", encoding="utf-8") if l.strip()]
names = [Path(p).name for p in new]
col = engine._get_retriever_store()._collection
for n in names:
    col.delete(where={"source": n})
print("deleted chunks for", len(names), "files")
PY
mkdir -p docs/books/_offtopic/round7_rollback
# then: move each file in dp_new.txt into docs/books/_offtopic/round7_rollback/
```
Re-run Step 1's `--fast` diff to confirm the panel is back to the baseline. Record the rollback in Task 7 and STOP (do not mine a corpus you just rolled back).

- [ ] **Step 5: Gate decision** — if Steps 1-3 all pass, the harvest is safe. Proceed to Task 5. If rollback happened, skip to Task 7.

---

### Task 5: Mining pass (new files only)

**Files:**
- Create: `SCRATCH/mine_round7.py` (throwaway scan, scoped to `dp_new.txt`)
- Create: `SCRATCH/hits7.txt` (scan output for manual review)

**Interfaces:**
- Consumes: `SCRATCH/dp_new.txt` (Task 2), the store (Task 3).
- Produces: a hand-filtered shortlist of candidate assertions (query + answer_any + context_any + crop + shape) for Task 6, or an empty shortlist.

- [ ] **Step 1: Write the scan (own-voice conclusion + value, over NEW files only)**

Create `SCRATCH/mine_round7.py`:
```python
import re, sys
from pathlib import Path
from collections import defaultdict
ROOT = Path(r"D:/Claude Projects/Agro-Botany RAG & Product Linker System")
sys.path.insert(0, str(ROOT))
from src import engine
SCRATCH = Path(r"<SCRATCH>")
new_names = {Path(l.strip()).name for l in open(SCRATCH/"dp_new.txt", encoding="utf-8") if l.strip()}
CONCL = re.compile(r"(sonuç olarak|sonucuna var|önerilebilir|önerilmektedir|tavsiye edil|"
                   r"kullanılabileceği|uygulanabileceği|yapılmalıdır|olmalıdır)", re.I)
NUM = re.compile(r"\b\d+([.,]\d+)?\s*(kg|g|ppm|cm|mm|ton|°c|ºc|gün|ay|adet|%|da|lt|l|m|hafta|göz|derece)", re.I)
TECH = re.compile(r"(sistemi|yöntemi|tekniği|gömücü ayak|terbiye|malç|örtü|budama|aşı|dikim|sulama)", re.I)
store = engine._get_retriever_store(); col = store._collection; total = col.count()
by_src = defaultdict(list); off, B = 0, 4000
while off < total:
    got = col.get(include=["metadatas", "documents"], limit=B, offset=off)
    for m, d in zip(got["metadatas"], got["documents"]):
        s = m.get("source", "?")
        if s in new_names: by_src[s].append(d)
    off += B
out = []
for src, chunks in sorted(by_src.items()):
    text = "\n".join(chunks)
    for m in CONCL.finditer(text):
        w = re.sub(r"\s+", " ", text[max(0, m.start()-160):m.start()+220]).strip()
        if NUM.search(w) or TECH.search(w):
            out.append(f"### {src}\n{w}"); break
(SCRATCH/"hits7.txt").write_text("\n\n".join(out), encoding="utf-8")
print("new files scanned:", len(by_src), "| hits:", len(out))
```

- [ ] **Step 2: Run the scan**

Run:
```bash
PYTHONIOENCODING=utf-8 python "$SCRATCH/mine_round7.py"
```
Expected: a hit count. Read `SCRATCH/hits7.txt` in full.

- [ ] **Step 3: Hand-filter each hit against the target window**

For each hit, KEEP only if ALL hold (drop otherwise, noting the reason):
- claim shape is UNDER-CAP and non-plant-material: graft-material state, harvest-timing, drying, biocontrol-list, min-diameter, bud-load, sowing-date, training-system, irrigation-level, storage, OR a brand-new shape. (SKIP input-application-rate/dose and any cultivar/rootstock/variety/resistant-cultivar/region-cultivar recommendation.)
- crop is NOT maize / forage / grape / pear; prefer a brand-new crop.
- answer-natural (a value a good answer states out loud, not a results-table cell).
- own voice (the paper's own conclusion, not cited literature).

Produce a shortlist: for each survivor write `{crop, shape, proposed_query, frozen_answer_any, candidate context anchors, source_quote}`. If the shortlist is empty, skip to Task 7 (dry).

---

### Task 6: Validate and ship (per shortlisted candidate)

**Files:**
- Modify: `evals/eval_set.py` (add the case, in the technique/quant corpus_fact region)

**Interfaces:**
- Consumes: the Task 5 shortlist.
- Produces: a shipped `corpus_fact` case (with `corpus_class: "corpus-carried"`) OR a drop-log comment.

- [ ] **Step 1: Freeze anchors against the STORED CHUNK TEXT**

Run (per candidate, substitute the anchor and source):
```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
from src import engine
from collections import Counter
col = engine._get_retriever_store()._collection
anchor = "<candidate context anchor>"
off, B, total = 0, 4000, col.count(); hits = Counter()
while off < total:
    g = col.get(include=["metadatas","documents"], limit=B, offset=off)
    for m,d in zip(g["metadatas"], g["documents"]):
        if anchor.lower() in d.lower(): hits[m.get("source","?")]+=1
    off += B
print(anchor, "->", dict(hits))
PY
```
Expected: the anchor occurs in EXACTLY the candidate's source (source-unique, case-insensitive). If it spans a line break or uses U+2019, adjust the anchor to the exact stored form (or use an explicit `’` escape in the case). Reject any anchor that is not source-unique.

- [ ] **Step 2: Add the case to `evals/eval_set.py` (NO corpus_class yet)**

Insert into the technique/quant corpus_fact region, e.g.:
```python
    {"id": "<shape>_<crop>_<detail>", "category": "horticulture", "corpus_fact": True,
     "query": "<proposed_query>",
     "retrieval": "nonempty", "products": "none",
     # <source_id> (<crop>, <shape>; round 7 harvest): own-voice conclusion
     # "<source_quote>". Frozen before the first run. Anchors verified source-unique
     # against the stored chunk text (Step 1).
     "context_any": ["<anchor1>", "<anchor2>"],
     "answer_any": ["<value notation 1>", "<value notation 2>"]},
```

- [ ] **Step 3: Measure the normal direction (ret + ctx + grounding)**

Run:
```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval --only <id> 2>&1 | tail -5
```
Expected to SHIP: `ret=True ctx=True ... ground=True`. If `ctx=False` (retrieval-broken / sibling collision) or `ground=False`, this is a DROP — replace the case dict with a drop-log comment recording the measured evidence, and move to the next candidate.

- [ ] **Step 4: Measure the ablated direction (corpus-dependence)**

Run:
```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 4 --only <id> 2>&1 | tail -5
```
Expected to SHIP: `corpus-carried  normal 4/4  ablated 0/4` (decisive; no repeat-8 needed). If `model-carried` (ablated also green), record it as a drop-log DATA finding (the model already knew it), do not ship. If an exact 2/4 borderline, escalate once with `--repeat 8 --only <id>`.

- [ ] **Step 5: Stamp corpus_class and add the measurement note (shipping candidates only)**

Add `"corpus_class": "corpus-carried",` after the id line and a note recording `normal N/N ablated 0/N, ret/ctx True (live <date>)`.

- [ ] **Step 6: Whole-panel verification**

Run:
```bash
PYTHONIOENCODING=utf-8 python -m evals.run_eval --fast | tail -3
PYTHONIOENCODING=utf-8 python -m pytest -q 2>&1 | tail -3
```
Expected: no ctx regression; `188 passed` if one case shipped (or 187 if none, +1 per shipped case only if a test counts cases — otherwise pytest stays 187; the case count lives in eval_set, not pytest). Record the eval panel count (54 → 55 per shipped case).

- [ ] **Step 7: Commit**

```bash
git add evals/eval_set.py
git commit -m "Round 7: ship <id> corpus_fact case from DergiPark harvest"
```

---

### Task 7: Record and close

**Files:**
- Create: `docs/superpowers/2026-07-22-round7-harvest-findings.md`
- Modify: the `handoff-next-steps` and `do-not-rechase` memory files (outside the repo)

**Interfaces:**
- Consumes: the outcomes of Tasks 2-6.
- Produces: the durable round-7 record.

- [ ] **Step 1: Write the findings doc**

Create `docs/superpowers/2026-07-22-round7-harvest-findings.md` recording: PDFs previewed vs downloaded (and whether the curated list is exhausting), new chunk count, the regression-gate result (pass / rollback), the mining hit count, each candidate's verdict (shipped corpus-carried / dropped retrieval-broken / dropped model-carried), and the harvest's net yield (new corpus-carried cases, or 0).

- [ ] **Step 2: Update memory**

Update `handoff-next-steps` (round-7 outcome, current panel + chunk counts, head commit) and `do-not-rechase`. **If the harvest was dry or downloaded very few new files, record in `do-not-rechase` that DergiPark harvesting no longer opens the vein and the corpus_fact program is exhausted across all paths** — so a future session does not re-propose it.

- [ ] **Step 3: Commit and push the findings doc**

```bash
git add docs/superpowers/2026-07-22-round7-harvest-findings.md
git commit -m "Record round 7 harvest findings: <shipped N / dry>"
git push origin main
```

---

## Self-Review

**Spec coverage:** Step 1 harvest → Task 2; off-topic cleanup → Task 2 Step 4; ingest → Task 3; three-layer regression gate (`--fast` / `--faithfulness --repeat 4` / pytest) → Task 4 Steps 1-3; rollback → Task 4 Step 4; mining new-files-only on under-cap shapes → Task 5; per-candidate quality gate (anchors / own-voice / both directions / collision) → Task 6; ship-or-record + findings doc + memory → Tasks 6-7. All spec sections map to a task.

**Placeholder scan:** `<...>` tokens in Tasks 5-6 are intentional per-candidate substitutions (the specific crop/anchor/id are unknowable until the scan runs), not TODO placeholders — each is accompanied by the exact command that produces its value. No "add error handling" / "write tests for the above" style gaps.

**Type/name consistency:** `SCRATCH/dp_before.txt` → `dp_after.txt` → `dp_new.txt` chain is consistent across Tasks 1, 2, 4, 5. `fast_before.txt`/`fast_after.txt` consistent across Tasks 1, 4. The `--faithfulness --repeat 4` two-stage escalation matches the spec's pre-registered gate. `corpus_class` stamped only after a corpus-carried measurement, matching the established eval_set convention.
