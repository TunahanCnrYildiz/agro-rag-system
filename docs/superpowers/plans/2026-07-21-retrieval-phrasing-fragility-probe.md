# Retrieval Phrasing-Fragility Probe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure how often a natural rewording of a question fails to reach a corpus document that demonstrably contains its answer, and apply a pre-registered rule to decide whether the fragility is worth fixing.

**Architecture:** Author 54 paraphrases (3 per `corpus_fact` case) BLIND and commit them before any probe exists, so the freeze is provable by git history. Then build a retrieval-only probe harness, prove the harness works by running the 18 ORIGINAL eval queries through it (all must HIT), and only then run the frozen paraphrases. Classify each as HIT / MISS-EMPTY / MISS-WRONG and apply the spec's thresholds.

**Tech Stack:** Python 3.14, chromadb (gitignored store at `data/vector_store/`), LM Studio serving `text-embedding-bge-m3` at :1234. **No chat model is used** — this is retrieval only.

**Spec:** `docs/superpowers/specs/2026-07-21-retrieval-phrasing-fragility-probe-design.md`

## Global Constraints

- **MEASUREMENT ONLY. No fix, no retrieval code change, no eval case change, no corpus change.** `evals/` and `src/` are READ-ONLY for this whole plan. `python -m pytest -q` must read **180** at every commit.
- **Task order is a bias control, not a convenience.** Paraphrases are authored in Task 1, BEFORE the probe harness exists, so they cannot be tested-and-tuned while being written. Do not build the harness early. Do not run any retrieval before Task 2.
- **The 54 paraphrases are FROZEN once committed.** After Task 1's commit, none may be edited, added, or removed — whatever the results look like.
- **Success is SOURCE HIT, not context length.** 4000 chars from the wrong paper is a failure. A case citing multiple sources counts as HIT if ANY of its cited sources is retrieved.
- **Pre-registered decision rule** (failures = MISS-EMPTY + MISS-WRONG, out of 54):
  **≤2 → CLOSE it, build nothing.** **≥6 → worth fixing, write a separate mechanism spec.** **3-5 → undecidable, extend the set by +54 and re-apply.**
- **The SHAPE of failures does not affect go/no-go** — only which mechanism to design if the threshold is met. "The rate is low but the pattern is clear, let's build anyway" is ruled out in advance.
- **Paraphrase validity:** same information need, natural Turkish. Narrowing, broadening, or hinting at the answer or source is forbidden (a leading query inflates the result — the `local_sebin_walnut` precedent).
- **Ops:** run everything from the repo root (`config.py` reads a relative `.env`; elsewhere it silently loads the wrong embedding model and every retrieval dies). LM Studio must be serving at :1234 — if not listening, `lms server start --port 1234`. Set `PYTHONIOENCODING=utf-8` on every command; the Windows console is cp1252 and Turkish characters raise `UnicodeEncodeError`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `docs/superpowers/2026-07-21-fragility-paraphrase-set.md` | The 54 frozen paraphrases + expected source set per case | **Created and COMMITTED in Task 1** (the freeze) |
| `<scratchpad>/probe_fragility.py` | Retrieval-only probe harness + classifier | Created, NOT committed |
| `<scratchpad>/fragility_results.md` | Raw per-probe results | Created, NOT committed |
| `docs/superpowers/2026-07-21-fragility-findings.md` | The measured result + the decision the rule produced | **Created and COMMITTED in Task 4** |

`<scratchpad>` = `C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\6d2143f9-0017-40b0-961b-3cfd73d2c194\scratchpad`

---

## Task 1: Author and freeze the 54 paraphrases

**Files:**
- Create + commit: `docs/superpowers/2026-07-21-fragility-paraphrase-set.md`
- Modify: none

**Interfaces:**
- Consumes: the 18 `corpus_fact` cases in `evals/eval_set.py` (READ-ONLY).
- Produces: the frozen paraphrase set. Task 3 reads exactly these 54 strings and the per-case expected source sets; it may not invent or adjust any.

**Context:** No probe harness exists yet, deliberately. Authoring blind is the bias control — if you could run a paraphrase you would be tempted to reword it until it worked, which would measure your persistence rather than the system's fragility. **Do not run any retrieval in this task.**

- [ ] **Step 1: Extract the 18 cases and their sources**

Run:
```bash
cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System" && PYTHONIOENCODING=utf-8 python -c "
from evals.eval_set import CASES as C
for c in C:
    if c.get('corpus_fact'):
        print(c['id'], '|', c['query'])
"
```
Expected: 18 lines, id and the eval query.

For each case's SOURCE, read its explanatory comment in `evals/eval_set.py` — the comment names the source document (e.g. `dp_1399494`). `disease_rhizoctonia_biocontrol` cites TWO (`dp_21748` + `dp_1004550`); record both. Do NOT parse the sources with a regex over the file — comments now mention other documents too (the safflower case's comment lists 4 sources where a rejected anchor occurred, and only `dp_1514564` is its actual source).

- [ ] **Step 2: Write three paraphrases per case**

Each case gets exactly three, one per category:

1. **`colloquial`** — short, how a grower would type it. Drop academic framing.
   Example shape for the deveci case: *"Deveci armudu kaç ay dayanır?"*
2. **`inflected`** — same question with different Turkish case/possessive/plural
   endings on the key nouns. This is the axis that broke the lexicon matcher.
3. **`synonym`** — swap the key domain term for a natural alternative
   ("muhafaza" ↔ "depolama", "tozlayıcı" ↔ "dölleyici", "çeşit" ↔ "tip").

Forbidden in all three: naming the source, naming the cultivar if the eval query
does not, or including the asserted value. Those make a leading query.

- [ ] **Step 3: Write the frozen set file**

Create `docs/superpowers/2026-07-21-fragility-paraphrase-set.md`. Header states that
this file is a PRE-REGISTRATION: written before the probe harness existed, frozen on
commit, and that the git commit timestamp is the evidence it predates the results.
Then one section per case:

```markdown
### <case_id>
- **Expected sources:** `dp_XXXXX` (any one counts as HIT)
- **Eval query (control):** <the original query>
- **P1 colloquial:** <paraphrase>
- **P2 inflected:** <paraphrase>
- **P3 synonym:** <paraphrase>
```

- [ ] **Step 4: Self-check the set against the validity rule**

Re-read all 54 and confirm each one: carries the SAME information need as its eval
query; names no source; hints at no answer value; is natural Turkish. Fix any that
fail — this is the last moment they may be changed.

Count: exactly 18 cases × 3 = 54 paraphrases, and every case has an expected source set.

- [ ] **Step 5: Commit the freeze**

```bash
git add docs/superpowers/2026-07-21-fragility-paraphrase-set.md
git commit -m "Freeze 54 fragility paraphrases (pre-registration, authored blind)"
```

- [ ] **Step 6: STOP — user review gate**

Present the set to the user for review. **This is a hard gate: no probe may run until
the user approves.** The user asked to review the paraphrases before any run,
specifically because the author writing them is also the party whose bias they
control for. If the user requests changes, amend and re-commit BEFORE Task 2 — after
Task 2 the set is frozen for good.

---

## Task 2: Build the probe harness and prove it works

**Files:**
- Create: `<scratchpad>/probe_fragility.py` (not committed)

**Interfaces:**
- Consumes: nothing from Task 1 yet (the control run uses the ORIGINAL eval queries).
- Produces: `classify(query, expected_sources) -> dict` with keys `outcome`
  (`"HIT"` / `"MISS-EMPTY"` / `"MISS-WRONG"`), `n_chunks` (int), `max_raw_score`
  (float), `sources` (list[str]), `ctx_len` (int). Task 3 calls exactly this.

**Context:** `engine.retrieve_context()` returns only a formatted string, so chunk
count, scores, and sources must come from the internals it wraps. The relevant pieces,
verified present in `src/engine.py`: `_get_retriever_store()`, `_expand_query(query)
-> list[str]`, `_search(store, q, k) -> [(Document, score)]`,
`_fuse(result_lists, floor, k) -> [Document]`, and the constant
`MIN_RETRIEVAL_RELEVANCE = 0.36`. `settings.retrieval_k` is 4.

`max_raw_score` is the best score across ALL expanded queries BEFORE the floor is
applied. It is what distinguishes "just missed the floor" from "nowhere close", which
the spec requires for failures.

- [ ] **Step 1: Write the harness**

Create `<scratchpad>/probe_fragility.py`:

```python
"""Retrieval-only fragility probe. No chat model is used."""
from src import engine
from src.config import settings


def classify(query: str, expected_sources: set[str]) -> dict:
    """Run the real retrieval path and classify the outcome."""
    store = engine._get_retriever_store()
    k = settings.retrieval_k
    result_lists = [engine._search(store, q, k) for q in engine._expand_query(query)]

    # Best similarity seen anywhere, BEFORE the floor gates anything.
    max_raw = 0.0
    for results in result_lists:
        for _doc, score in results:
            max_raw = max(max_raw, score)

    docs = engine._fuse(result_lists, engine.MIN_RETRIEVAL_RELEVANCE, k)
    sources = [d.metadata.get("source", "?") for d in docs]
    ctx_len = sum(len(d.page_content) for d in docs)

    # Sources are stored with the .pdf suffix; expected ids are bare.
    hit = any(s.replace(".pdf", "") in expected_sources for s in sources)
    if not docs:
        outcome = "MISS-EMPTY"
    elif hit:
        outcome = "HIT"
    else:
        outcome = "MISS-WRONG"

    return {
        "outcome": outcome,
        "n_chunks": len(docs),
        "max_raw_score": round(max_raw, 4),
        "sources": sources,
        "ctx_len": ctx_len,
    }
```

- [ ] **Step 2: Run the harness control — the 18 ORIGINAL eval queries**

This is the gate that proves the instrument works before it is trusted. Every original
eval query is known to reach its source (each case was live-validated), so all 18 must
classify HIT. Append to the script and run:

```python
if __name__ == "__main__":
    from evals.eval_set import CASES
    SOURCES = {}  # fill from the Task 1 frozen file: case_id -> {"dp_XXXXX", ...}
    for c in CASES:
        if not c.get("corpus_fact"):
            continue
        r = classify(c["query"], SOURCES[c["id"]])
        print(f"{r['outcome']:11} {c['id']:38} chunks={r['n_chunks']} "
              f"max={r['max_raw_score']} {r['sources']}")
```

Run: `PYTHONIOENCODING=utf-8 python <scratchpad>/probe_fragility.py`
Expected: **18 lines, all `HIT`.**

- [ ] **Step 3: If any control line is not HIT, STOP and diagnose**

Do NOT proceed to Task 3 and do NOT treat it as a finding about fragility. A control
failure means either the harness is wrong (most likely: expected-source ids mistyped,
`.pdf` suffix handling, LM Studio not serving bge-m3, or the command was run outside
the repo root so the wrong embedding model loaded) or a panel case has genuinely
regressed. Either way the instrument cannot be trusted yet.

Cross-check a failing case against the eval itself:
`PYTHONIOENCODING=utf-8 python -m evals.run_eval --only <case_id>` — if that reports
`ret=True ctx=True`, the harness is at fault, not the case. Fix and re-run the control.

- [ ] **Step 4: Record the control result**

Note in `<scratchpad>/fragility_results.md` that the control passed 18/18, with the
per-case `max_raw_score` values. Those baselines make the paraphrase numbers readable
(a paraphrase scoring 0.34 against a control of 0.52 is a big drop; against 0.38 it is
a small one).

---

## Task 3: Run the 54 frozen paraphrases and classify

**Files:**
- Modify: `<scratchpad>/probe_fragility.py` (add the paraphrase run)
- Create: `<scratchpad>/fragility_results.md` (raw results, not committed)

**Interfaces:**
- Consumes: `classify()` from Task 2; the 54 paraphrases and expected source sets from Task 1's committed file.
- Produces: a per-probe result table and the three-class tally that Task 4 applies the rule to.

**Context:** The paraphrases are FROZEN. If one looks wrong now, that is a finding to
record, not a thing to fix — editing it after seeing a result is exactly what the
freeze exists to prevent.

- [ ] **Step 1: Load the frozen paraphrases and run all 54**

Read the paraphrases from `docs/superpowers/2026-07-21-fragility-paraphrase-set.md`
(transcribe them into the script or parse the file — either is fine, but the strings
must match the committed file exactly). Run each through `classify()` with its case's
expected source set, recording case id, category (`colloquial`/`inflected`/`synonym`),
outcome, `n_chunks`, `max_raw_score`, and `sources`.

Run: `PYTHONIOENCODING=utf-8 python <scratchpad>/probe_fragility.py`
Expected: 54 result lines. This takes minutes, not hours — embeddings only.

- [ ] **Step 2: Write the results table**

Write `<scratchpad>/fragility_results.md`: one row per probe, plus the tally
(HIT / MISS-EMPTY / MISS-WRONG counts out of 54).

- [ ] **Step 3: Characterise the failures**

For every non-HIT probe record:
- the **gap to the floor**: `0.36 - max_raw_score` (negative means it cleared the floor
  but the right source still lost — a different defect from not clearing it at all)
- the **drop from its control**: the case's original-query `max_raw_score` minus this one
- which **category** it came from (`colloquial` / `inflected` / `synonym`)

Report the per-category breakdown. **This characterisation does NOT feed the go/no-go
decision** — the spec fixes that on the count alone. It exists only to inform mechanism
design if Task 4's rule says to proceed.

- [ ] **Step 4: Report the raw tally**

Report to the reviewer: the three-class counts, the count restricted to the 17
corpus-carried cases (excluding the model-carried `disease_rhizoctonia_biocontrol`,
which the spec requires be separable), and the per-category breakdown. **Do not apply
the decision rule yet and do not recommend a direction** — that is Task 4, deliberately
separated so the number is stated before it is argued about.

---

## Task 4: Apply the pre-registered rule and record the finding

**Files:**
- Create + commit: `docs/superpowers/2026-07-21-fragility-findings.md`
- Modify: `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md` and, if the answer is CLOSE, `memory\do-not-rechase.md`

**Interfaces:**
- Consumes: Task 3's tally.
- Produces: the decision and the durable record. Nothing else consumes this.

**Context:** The rule was fixed before any probe ran. Apply it as written. If the
result feels wrong, that feeling is not grounds to override it — record the discomfort
in the findings file instead, where a future reader can weigh it.

- [ ] **Step 1: Apply the rule**

Failures = MISS-EMPTY + MISS-WRONG, out of 54:

| Result | Decision |
|---|---|
| ≤ 2 | **CLOSE.** Fragility is not a practical problem. Build nothing. |
| ≥ 6 | **PROCEED.** Worth fixing; a separate mechanism spec follows. |
| 3-5 | **UNDECIDABLE.** Extend the set by +54 paraphrases and re-apply. |

If the answer is UNDECIDABLE, do not argue it either way — say so and stop for the
user's decision on whether to spend the extra round.

- [ ] **Step 2: Write the findings file**

Create `docs/superpowers/2026-07-21-fragility-findings.md` containing: the tally, the
per-category breakdown, the failure characterisation, the rule applied, the decision
it produced, and — importantly — the count over the 17 corpus-carried cases alongside
the count over all 18, so the decision can be re-derived under a stricter reading.

State the limitation the spec pre-registered: these paraphrases derive from queries
that were AUTHORED to work, so the number is a **lower bound** on real-user fragility,
not an estimate of it.

Also state the set's document coverage: four cases (`santamaria`, `ankara`,
`beurrehardy`, `bpmorettini`) share the source `dp_19393`, so the 18 cases cover **16
distinct documents**. This does not bias the per-probe measurement, but it means a
systematic problem with `dp_19393` would appear up to 4 times and inflate the failure
count. If two or more failures trace to `dp_19393`, report the tally both with and
without them.

- [ ] **Step 3: Update the memory record**

Add the result to `handoff-next-steps.md`. **If the decision is CLOSE, also add it to
`do-not-rechase.md`** — in that case the record's whole job is to stop this question
being re-opened on the same evidence.

- [ ] **Step 4: Verify nothing leaked**

Run:
```bash
cd "D:/Claude Projects/Agro-Botany RAG & Product Linker System" && python -m pytest -q && git diff --stat main..HEAD
```
Expected: `180 passed`, and the only changed files are the spec, this plan, the frozen
paraphrase set, and the findings file. **No file under `src/` or `evals/` may appear.**

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/2026-07-21-fragility-findings.md
git commit -m "Record fragility probe result and the decision it produced"
```

---

## Definition of Done

- [ ] 54 paraphrases authored blind, committed before the harness existed, and approved by the user.
- [ ] Harness control run: 18/18 original eval queries classify HIT.
- [ ] All 54 frozen paraphrases run; three-class tally recorded.
- [ ] Failures characterised by floor-gap, control-drop, and category.
- [ ] The pre-registered rule applied as written, and the decision recorded.
- [ ] `pytest -q` reads 180; no `src/` or `evals/` file changed.
- [ ] Memory updated (`do-not-rechase` too, if the decision is CLOSE).
