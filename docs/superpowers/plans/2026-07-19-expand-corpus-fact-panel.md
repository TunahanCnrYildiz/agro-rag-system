# Expand the corpus_fact panel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author +4–6 new *validated* `corpus-carried` eval cases so the corpus-dependence map guards retrieval in ~12–14 of 39 cases instead of 8.

**Architecture:** Pure DATA authoring on the already-shipped map machinery (item 31). No code path changes. For each candidate: read a real `dp_` chunk via `engine.retrieve_context`, pre-register an answer-natural assertion, append the case to `evals/eval_set.py`, and classify it live with `python -m evals.run_eval --faithfulness --only <id> --repeat 4`. Ship only cases the classifier labels `corpus-carried`; drop the rest with a `# DROPPED` provenance comment.

**Tech Stack:** Python 3.14, the existing `evals/` harness, LM Studio (bge-m3 embeddings + gemma-4-12b-qat chat at :1234), the gitignored `data/vector_store/` Chroma store.

## Global Constraints

Copied verbatim from the spec (`docs/superpowers/specs/2026-07-19-expand-corpus-fact-panel-design.md`). Every task implicitly includes these:

- **NO code change** to `src/`, `evals/run_eval.py`, `evals/inspect_retrieval.py`, the prompt, or retrieval. The ONLY source edit is APPENDING dict entries to `evals/eval_set.py`. If a candidate only validates by changing code, it is out of scope — drop it.
- **Validate at the eval's own config with `--repeat 4`.** The live label decides the quadrant.
- **Classifier rule** (`run_eval._classify`, repeat=4), in order: `ablated > normal` → **corpus-harmful**; `normal < 2` → **retrieval-broken**; `ablated >= 2` → **model-carried**; else → **corpus-carried**. Ship ONLY `corpus-carried`.
- **Answer-natural assertion:** `answer_any` must be a value a good answer to THAT question would say out loud, not a results-table cell. Governing test from item 25 (cherry drop): "would a good answer say this number out loud?"
- **Discriminating `context_any`:** source-unique phrase, verified not to appear verbatim across many corpus sources (item 31 vetch drop).
- **`answer_any` broadening is legitimate ONLY for alternate NOTATIONS of the SAME value** (`2±0,5` / `2 ± 0.5`), never a looser or different noun ("P2O5" → "fosfor" is forbidden).
- **A candidate that fails GREEN-normal is DROPPED, not retuned** (cherry rule). Record every drop as a `# DROPPED` comment.
- **Local cultivar cases** set `category: "local"` and MUST also pass `python -m evals.run_eval --no-context --only local` (exit 0 = every local case lost grounding).
- **Target:** ~10 candidates mined → +4–6 shipped `corpus-carried`. Model-carried is a valid map finding, not a failure, but is NOT shipped as a carried guard this round (goal is raising the carried count).
- **Commits:** concise, English, human-style, NO `Co-Authored-By` trailer.
- LM Studio must be reachable at `http://localhost:1234` (verify: `curl -s http://localhost:1234/v1/models`).

---

## File Structure

- `evals/eval_set.py` — MODIFY (append case dicts + `# DROPPED` comments only). The one source file this plan touches.
- `<scratchpad>/mine.py` — CREATE (scratch, NOT committed) — the mining harness.
- `docs/superpowers/plans/` + handoff memory — the map artifact (Task 5).

Scratchpad dir for this session:
`C:\Users\tunah\AppData\Local\Temp\claude\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\0e391496-aa1f-47a8-a012-e393b7fe4a27\scratchpad`

---

## Task 1: Mining + validation harness (scratch, no commit)

Stand up the two tools the authoring tasks reuse: a corpus-reader that shows exactly what the eval will retrieve for a candidate question, and a confirmed per-candidate validation command.

**Files:**
- Create: `<scratchpad>/mine.py` (scratch, not committed)
- Reference: `src/engine.py:346` (`retrieve_context`), `evals/run_eval.py:273` (`run_faithfulness`)

**Interfaces:**
- Consumes: `engine.retrieve_context(query: str) -> str` (returns chunks with `[Kaynak: <source_id>, s.<page>]` headers — the source id is how we identify the `dp_` paper).
- Produces: the reusable command `python <scratchpad>/mine.py "<TR question>"` and the validation command `python -m evals.run_eval --faithfulness --only <id> --repeat 4`.

- [ ] **Step 1: Write the mining harness**

```python
# <scratchpad>/mine.py — scratch, not committed
import sys
from src import engine

query = sys.argv[1]
ctx = engine.retrieve_context(query)
print(f"=== {query} ===")
print(f"[chars: {len(ctx)}]")
print(ctx if ctx else "(EMPTY — nothing cleared the 0.36 floor)")
```

- [ ] **Step 2: Run it on a known-good question to confirm it shows source ids + text**

Run (from repo root):
```bash
python <scratchpad>/mine.py "Deveci armudu ne zaman hasat edilmeli ve soğukta ne kadar depolanabilir?"
```
Expected: non-empty output containing `[Kaynak: dp_21747, ...]` and the `2±0,5` storage detail. If EMPTY, LM Studio / the store is misconfigured — STOP and fix before authoring (item 1 instrument-bug lesson: wrong `EMBEDDING_MODEL` silently empties retrieval).

- [ ] **Step 3: Smoke-test the validation command on an existing carried case**

Run:
```bash
python -m evals.run_eval --faithfulness --only local_deveci_pear --repeat 4
```
Expected: a line `local_deveci_pear   corpus-carried   normal N/4  ablated M/4` with `N>=2, M<2`, tally `corpus-carried: 1/1`, exit 0. (deveci is flaky ~1/3 — if it prints `retrieval-broken` at 1/4 normal, re-run once; a persistent minority-normal means the store/model is off.) This confirms the exact command + expected output shape every authoring task depends on.

- [ ] **Step 4: No commit** (scratch tooling only). Task deliverable = both commands demonstrably working.

---

## Task 2: Zone-1 — local Turkish cultivar candidates (PRIMARY)

Mine ~4 cultivar-specific findings, ship the ones that validate corpus-carried. This is the highest-hit-rate zone (all 3 existing local pears + the deveci anchor are here).

**Files:**
- Modify: `evals/eval_set.py` (append to `CASES`, in the `# --- local:` block near line 290)
- Uses: `<scratchpad>/mine.py`

**Interfaces:**
- Consumes: Task 1's mining + validation commands.
- Produces: 2–4 new `local` + `corpus_fact: True` cases with `corpus_class: "corpus-carried"`.

**Mining seeds** (topics known to be in the store as `dp_` cultivar studies; read, do NOT assert from the title — item 31 lesson 22e). Run `mine.py` on natural TR questions such as:
- other pear cultivars in the Eğirdir self-fertility paper `dp_19393` (e.g. "Mustafabey", "Akça", "Kaiser" — a self-fertile/self-sterile verdict, the ankara/santamaria shape);
- a quince, plum, or fig cultivar's regional harvest window or a named standard;
- a table-grape or apricot cultivar's cultivar-specific trait (AVOID Hacıhaliloğlu "kurutmalık" — measured corpus-harmful, item 31; AVOID 0900 Ziraat cherry 8.91 g — dropped, item 25);
- a strawberry / chestnut / walnut cultivar trait that a natural answer states (AVOID Şebin protandry — dropped as not answer-natural, item 31).

The winning shape: a **self-fertility verdict**, **harvest window**, or **storage/regional standard** — things a natural "should I..." / "when..." answer says out loud.

- [ ] **Step 1: Mine candidates**

For each seed, run:
```bash
python <scratchpad>/mine.py "<natural TR question about the cultivar>"
```
Read the output. Keep a candidate ONLY if the retrieved context contains a specific, cultivar-bound fact a natural answer would state. Note the `dp_` source id and the paper's exact wording.

- [ ] **Step 2: Pre-register and append each candidate**

Append to `CASES` using this exact template (fill the discovered values; keep the provenance comment):

```python
    {"id": "local_<cultivar>_<crop>", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",   # provisional; confirm/replace in Step 3
     "query": "<natural TR question a real user would ask>",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["<source-unique phrase from the chunk>"],
     # dp_<id> (<paper short name>): <the paper's own finding, quoted>. A natural
     # answer to this question states <fact>, not a results-table cell.
     "answer_any": ["<answer-natural value>", "<same-value alternate notation>"]},
```

- [ ] **Step 3: Validate each candidate BOTH directions**

For each new id:
```bash
python -m evals.run_eval --faithfulness --only <id> --repeat 4
```
Read the label:
- `corpus-carried` (normal ≥2/4, ablated <2/4) → KEEP. Leave `corpus_class: "corpus-carried"`.
- `model-carried` (ablated ≥2/4) → the model already knows it → DROP for this round.
- `retrieval-broken` (normal <2/4) → the answer doesn't carry the fact → DROP (do NOT retune to green — cherry rule).
- `corpus-harmful` (ablated > normal) → DROP.

- [ ] **Step 4: Replace dropped candidates with a `# DROPPED` comment**

For every candidate that did not ship, delete its dict and leave a provenance comment in its place, matching the existing style (see `eval_set.py:318-334`):
```python
    # DROPPED 2026-07-19: local_<x>_<crop>, "<query>" asserting dp_<id>'s
    # <fact>. <quadrant> (normal N/4, ablated M/4): <one-line why>. Not retuned.
```

- [ ] **Step 5: Confirm the local ablation gate still holds**

```bash
python -m evals.run_eval --no-context --only local
```
Expected: `[ablation] local cases that lost grounding: K/K - they discriminate`, exit 0 (K = old 3 + newly shipped local cases). If any new local case still grounds with an empty corpus, it guards nothing → DROP it (should not happen if Step 3 labelled it corpus-carried, but this is the local-specific gate the spec requires).

- [ ] **Step 6: Commit the survivors**

```bash
git add evals/eval_set.py
git commit -m "Add Zone-1 local cultivar corpus_fact cases (<N> corpus-carried)"
```

---

## Task 3: Zone-3 — horticulture technique threshold candidates (SECONDARY)

Mine ~3 technique parameters a practical answer states (spacing, depth, dose, count, diameter). Both existing technique cases (carob ≥10 mm, grape 18 göz) are corpus-carried, so this zone has a good track record.

**Files:**
- Modify: `evals/eval_set.py` (append near the Zone-3 block, line ~336)
- Uses: `<scratchpad>/mine.py`

**Interfaces:**
- Consumes: Task 1's commands.
- Produces: 1–2 new `horticulture` + `corpus_fact: True` cases, `corpus_class: "corpus-carried"`.

**Mining seeds** (natural TR technique questions; read the chunk):
- a planting spacing / density for a specific crop from a `dp_` field trial ("… dikim sıklığı / sıra arası kaç cm olmalı");
- a cutting length / rooting parameter for propagation of a named plant;
- a pruning parameter (bud count, branch number) for a crop other than the grape already covered;
- a graft-timing or budding-height threshold.

CAUTION: a value the model already knows generically (e.g. "sıra arası ~70 cm for maize") will validate model-carried — that is fine to discover, just don't ship it. Prefer crop-specific, less-generic parameters.

- [ ] **Step 1: Mine candidates** — run `mine.py` on each seed question; keep only those whose retrieved context states a specific technique parameter.

- [ ] **Step 2: Append each candidate** using the template (note `category: "horticulture"`, NO `local`):

```python
    {"id": "technique_<param>_<crop>", "category": "horticulture", "corpus_fact": True,
     "corpus_class": "corpus-carried",   # provisional; confirm in Step 3
     "query": "<natural TR technique question>",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["<source-unique phrase>"],
     # dp_<id> (<paper>): <the parameter, quoted from prose (not a table cell)>.
     "answer_any": ["<value>", "<same-value alternate notation>"]},
```

- [ ] **Step 3: Validate BOTH directions** — `python -m evals.run_eval --faithfulness --only <id> --repeat 4`; apply the same KEEP/DROP rule as Task 2 Step 3.

- [ ] **Step 4: `# DROPPED` comments** for non-survivors (same format as Task 2 Step 4).

- [ ] **Step 5: Commit**

```bash
git add evals/eval_set.py
git commit -m "Add Zone-3 technique corpus_fact cases (<N> corpus-carried)"
```

---

## Task 4: Zone-4 — quantitative candidates (CAUTION, optional)

Mine ~2–3 specific rates/ratios/figures. This is the HARDEST zone (item 31: the model often knows rough rates; most Zone-4 drops clustered here). Only attempt if Tasks 2–3 did not already reach the +4–6 target; ship only clean corpus-carried wins.

**Files:**
- Modify: `evals/eval_set.py` (append near the Zone-4 block, line ~361)

**Interfaces:**
- Consumes: Task 1's commands.
- Produces: 0–2 new `corpus_fact: True` cases (category `nutrition`/`horticulture`), `corpus_class: "corpus-carried"`.

**Mining seeds:** a fertilizer dose, seeding rate, or ratio stated as an UNCONDITIONED recommendation in a `dp_` study's Sonuç (conclusion), like the wheat 16 kg/da N case — NOT a single results-table cell, and NOT a round number the model already volunteers.

- [ ] **Step 1: Mine** — run `mine.py`; verify the figure appears in a conclusion-style statement, and that `context_any` phrase is source-unique (grep the store output for the phrase across a couple of other queries to be sure).

- [ ] **Step 2: Append** using the Task 3 template (adjust `category` + `products` — a nutrition case uses `"products": "some"`, matching `quant_wheat_nitrogen_dose`).

- [ ] **Step 3: Validate BOTH directions** — same command + KEEP/DROP rule. Expect a higher drop rate here.

- [ ] **Step 4: `# DROPPED` comments** for non-survivors.

- [ ] **Step 5: Commit** (skip if nothing shipped)

```bash
git add evals/eval_set.py
git commit -m "Add Zone-4 quantitative corpus_fact cases (<N> corpus-carried)"
```

---

## Task 5: Whole-panel verification + map artifact

Prove the full panel is coherent (no drift, no broken dimensions, suite green) and record the map.

**Files:**
- Reference: `evals/eval_set.py` (final state)
- Update: the handoff memory (`C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md`) — a new dated item recording the per-zone result.

- [ ] **Step 1: Run the full map over ALL corpus_fact cases**

```bash
python -m evals.run_eval --faithfulness --repeat 4
```
Expected: every case recorded `corpus_class: "corpus-carried"` classifies `corpus-carried` live; tally shows `corpus-carried: <old 7 + new>/<total>`; NO `[drift]` line; exit 0. If a NEW case flips, fix its `corpus_class` to the honest live label or drop it. If an OLD case (deveci) shows a one-run flake, re-run `--only <id> --repeat 8` to disambiguate (item 25 — deveci is intermittently red ~1/3, this is expected, not a regression).

- [ ] **Step 2: Confirm the local ablation gate over the whole local set**

```bash
python -m evals.run_eval --no-context --only local
```
Expected: exit 0, all local cases lose grounding.

- [ ] **Step 3: Run the unit suite (no code changed → must be untouched)**

```bash
python -m pytest -q
```
Expected: same green count as before this plan (170 passed). A new dict in a list touches no tested function; a RED here means something other than data changed — investigate before proceeding.

- [ ] **Step 4: Record the map artifact in the handoff memory**

Add a new item (next number) to `handoff-next-steps.md` summarizing: per-zone which candidates shipped corpus-carried, which fell model-carried, which dropped and why; the new panel size and carried count (8/39 → <new>/39); and the reminder that this is a guard scoreboard, NOT a coverage meter. Add the one-line pointer isn't needed (handoff is already indexed in MEMORY.md).

- [ ] **Step 5: Final state**

No repo commit in this task: `evals/eval_set.py` was committed per-zone in Tasks 2–4, this plan + spec are already committed, and the handoff memory lives OUTSIDE the repo (saved by the Write tool). Confirm `git status` is clean and `git log --oneline -5` shows the per-zone commits. Optionally push if the user asks (item 31 pushed to origin; not required).

---

## Self-Review (completed by plan author)

**Spec coverage:** §1 target (+4–6 carried, panel→~12–14) → Tasks 2–4 + Task 5 Step 1 tally. §2 zone bias → Tasks 2 (primary), 3 (secondary), 4 (caution). §3 protocol (read source / answer-natural / discriminating context / both-direction validate / record quadrant / drop-not-retune) → every authoring task's Steps 1–4 + Global Constraints. §4 deliverable + testing → Task 5 (map + pytest + live validation). §5 out-of-scope (no code change) → Global Constraints line 1. All covered.

**Placeholder scan:** The `<...>` tokens in case templates are RUNTIME DATA (the mined facts), not plan placeholders — they cannot be known before execution reads the corpus, and the process to fill them is fully specified. All commands, file paths, the case skeleton, and the classifier decision rule are concrete.

**Type consistency:** Field names (`corpus_fact`, `corpus_class`, `context_any`, `answer_any`, `category`, `products`, `retrieval`) match `eval_set.py` exactly. Validation command (`--faithfulness --only <id> --repeat 4`) matches `run_eval.py:342,351`. Classifier thresholds match `_classify` (verified against `run_eval.py:122`). `retrieve_context` signature matches `engine.py:346`.
