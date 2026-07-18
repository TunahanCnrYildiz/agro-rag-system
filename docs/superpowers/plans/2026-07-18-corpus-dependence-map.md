# Corpus-dependence Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the `corpus_fact` eval panel from 2 to ~10 cases across four topic zones and turn `--faithfulness` from a strict "all corpus-carried" gate into a corpus-dependence MAP (scoreboard) with a drift guard.

**Architecture:** The classification machinery already exists (`_classify`, `run_faithfulness`, `_corpus_ablated`). Task 1 changes only the exit condition — a new pure verdict helper gates on regression of cases *recorded* as corpus-carried, not on the whole panel being corpus-carried. Tasks 2–5 author + live-validate candidate cases (the bulk of the effort); each candidate ships with its measured `corpus_class` or is dropped. Task 6 captures the map.

**Tech Stack:** Python 3.14, pytest, chromadb (`data/vector_store/`, gitignored), LM Studio (bge-m3 + gemma at :1234). Spec: `docs/superpowers/specs/2026-07-18-corpus-dependence-map-design.md`.

## Global Constraints

- **Answer-natural assertion rule (item 25):** `answer_any` must be a value a good answer to the query would naturally state out loud, not a results-table cell. The pre-registration rule ("assertion comes from the source document") is necessary but NOT sufficient.
- **Keep/drop rule (cherry rule):** a candidate that fails GREEN-normal is DROPPED, never retuned. A case tuned until green asserts nothing.
- **Every shipped `corpus_fact` case carries a `corpus_class`** field equal to its live-measured quadrant at authoring time.
- **`corpus_class` values:** `"corpus-carried" | "model-carried" | "retrieval-broken" | "corpus-harmful"` (exact strings, matching `_classify` output).
- **Validation needs LM Studio** (bge-m3 + gemma at :1234). The eval is NOT in CI; only the pure unit tests are. Run unit tests with `python -m pytest -q`.
- **Run commands from the repo root** (`D:\Claude Projects\Agro-Botany RAG & Product Linker System`) with `PYTHONIOENCODING=utf-8` so Turkish output does not crash on cp1252.
- **Commits:** English, concise, no Claude co-author trailer. Batch a zone's cases into one commit.

---

### Task 1: Drift-guard verdict (`--faithfulness` becomes a map gate)

Replaces the whole-panel "all corpus-carried" exit condition with a regression gate over cases recorded as corpus-carried. Pure-function core + wiring + updated tests. CI-safe (no LM Studio).

**Files:**
- Modify: `evals/run_eval.py` (add `_faithfulness_verdict`; rewire `run_faithfulness` at ~243–289)
- Modify: `evals/eval_set.py` (add `corpus_class: "corpus-carried"` to the 2 existing pears at lines 258 and 265)
- Test: `tests/test_run_eval.py` (update the faithfulness block at 247–293)

**Interfaces:**
- Consumes: `_classify(normal_all_green, ablated_all_green) -> str` (run_eval.py:122, unchanged).
- Produces: `_faithfulness_verdict(cases: list[dict], live_labels: dict[str, str]) -> tuple[int, list[str]]` — returns `(exit_code, regressed_ids)`. `exit_code` is 1 iff any case with `corpus_class == "corpus-carried"` has `live_labels[id] != "corpus-carried"`; else 0. `regressed_ids` lists those case ids.

- [ ] **Step 1: Update the test helper to carry a recorded class**

In `tests/test_run_eval.py`, change `_optin_case` (line 247) to accept a class:

```python
def _optin_case(answer_any, corpus_class="corpus-carried"):
    return {"id": "probe", "category": "local", "corpus_fact": True,
            "corpus_class": corpus_class,
            "query": "q", "answer_any": answer_any}
```

- [ ] **Step 2: Write failing unit tests for the pure verdict**

Add to `tests/test_run_eval.py` (after the `_classify` tests, ~line 244):

```python
def test_verdict_recorded_carried_still_carried_passes():
    cases = [{"id": "a", "corpus_class": "corpus-carried"}]
    assert run_eval._faithfulness_verdict(cases, {"a": "corpus-carried"}) == (0, [])


def test_verdict_recorded_carried_regressed_fails_and_names_it():
    cases = [{"id": "a", "corpus_class": "corpus-carried"}]
    assert run_eval._faithfulness_verdict(cases, {"a": "model-carried"}) == (1, ["a"])


def test_verdict_recorded_carried_now_retrieval_broken_fails():
    cases = [{"id": "a", "corpus_class": "corpus-carried"}]
    assert run_eval._faithfulness_verdict(cases, {"a": "retrieval-broken"}) == (1, ["a"])


def test_verdict_model_carried_case_never_gates():
    cases = [{"id": "b", "corpus_class": "model-carried"}]
    assert run_eval._faithfulness_verdict(cases, {"b": "retrieval-broken"}) == (0, [])


def test_verdict_missing_class_never_gates():
    cases = [{"id": "c"}]
    assert run_eval._faithfulness_verdict(cases, {"c": "corpus-harmful"}) == (0, [])


def test_verdict_mixed_reports_only_the_regressed():
    cases = [{"id": "a", "corpus_class": "corpus-carried"},
             {"id": "b", "corpus_class": "model-carried"}]
    assert run_eval._faithfulness_verdict(
        cases, {"a": "model-carried", "b": "model-carried"}) == (1, ["a"])
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `python -m pytest tests/test_run_eval.py -k verdict -q`
Expected: FAIL with `AttributeError: module 'evals.run_eval' has no attribute '_faithfulness_verdict'`

- [ ] **Step 4: Implement the pure verdict helper**

In `evals/run_eval.py`, add directly after `_classify` (after line 133):

```python
def _faithfulness_verdict(
    cases: list[dict], live_labels: dict[str, str]
) -> tuple[int, list[str]]:
    """(exit_code, regressed_ids) for the corpus-dependence map.

    The map is DATA: model-carried cases are a legitimate finding, not a
    failure. The only regression worth failing on is a case we RECORDED as
    corpus-carried that no longer is - the corpus or retrieval stopped
    carrying a fact it used to. Cases with any other (or no) recorded
    corpus_class never touch the exit code.
    """
    regressed = [
        c["id"] for c in cases
        if c.get("corpus_class") == "corpus-carried"
        and live_labels.get(c["id"]) != "corpus-carried"
    ]
    return (1 if regressed else 0), regressed
```

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python -m pytest tests/test_run_eval.py -k verdict -q`
Expected: PASS (6 passed)

- [ ] **Step 6: Rewire `run_faithfulness` to build `live_labels` and use the verdict**

In `evals/run_eval.py`, in `run_faithfulness` (the loop at ~275–289), collect labels and replace the return. The loop body already computes `label`; capture it:

```python
    counts = {"corpus-carried": 0, "model-carried": 0,
              "retrieval-broken": 0, "corpus-harmful": 0}
    live_labels: dict[str, str] = {}
    for c in cases:
        normal_hits = grounded_hits(c)
        with _corpus_ablated():
            ablated_hits = grounded_hits(c)
        label = _classify(normal_hits == repeat, ablated_hits == repeat)
        live_labels[c["id"]] = label
        counts[label] += 1
        print(f"  {c['id']:<24} {label:<16} "
              f"normal {normal_hits}/{repeat}  ablated {ablated_hits}/{repeat}")

    total = len(cases)
    print(f"\n  corpus-carried: {counts['corpus-carried']}/{total}  |  "
          f"harmful: {counts['corpus-harmful']}  |  "
          f"retrieval-broken: {counts['retrieval-broken']}  |  "
          f"model-carried: {counts['model-carried']}")

    code, regressed = _faithfulness_verdict(cases, live_labels)
    if regressed:
        print(f"\n  [drift] corpus-carried cases that REGRESSED: "
              f"{', '.join(regressed)}")
    return code
```

Also update the `run_faithfulness` docstring (lines 245–255): it no longer requires every case to be corpus-carried; it now reports the map and fails only on regression of a recorded corpus-carried case.

- [ ] **Step 7: Update the existing live-semantics faithfulness tests**

In `tests/test_run_eval.py`, replace the three behavioural tests (252–282) so they encode the drift semantics. Keep `test_faithfulness_no_optin_case_exits_1` (285) and `test_faithfulness_fast_exits` (291) unchanged.

```python
def test_faithfulness_recorded_carried_still_carried_exits_0(monkeypatch):
    monkeypatch.setattr(run_eval, "_select",
                        lambda only: [_optin_case(["2±0,5"], "corpus-carried")])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)  # respects _corpus_ablated
        return ChatResult("depo 2±0,5 derece" if ctx else "genel tavsiye", [])
    monkeypatch.setattr(engine, "answer", fake)
    assert run_eval.run_faithfulness() == 0


def test_faithfulness_recorded_carried_regressed_to_model_exits_1(monkeypatch):
    monkeypatch.setattr(run_eval, "_select",
                        lambda only: [_optin_case(["2±0,5"], "corpus-carried")])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    # states the fact regardless of context -> now model-carried = REGRESSION
    monkeypatch.setattr(engine, "answer",
                        lambda msg, history=None: ChatResult("hep 2±0,5 der", []))
    assert run_eval.run_faithfulness() == 1


def test_faithfulness_recorded_model_carried_never_gates(monkeypatch):
    # a case we recorded as model-carried is DATA - it must not fail the run
    monkeypatch.setattr(run_eval, "_select",
                        lambda only: [_optin_case(["2±0,5"], "model-carried")])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    monkeypatch.setattr(engine, "answer",
                        lambda msg, history=None: ChatResult("hep 2±0,5 der", []))
    assert run_eval.run_faithfulness() == 0
```

- [ ] **Step 8: Add `corpus_class` to the two existing pears**

In `evals/eval_set.py`, add the field to both `local` cases (lines 258 and 265). For `local_deveci_pear`:

```python
    {"id": "local_deveci_pear", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
```

For `local_santamaria_pear`:

```python
    {"id": "local_santamaria_pear", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
```

- [ ] **Step 9: Run the full unit suite**

Run: `python -m pytest -q`
Expected: PASS (all tests green; the 6 new verdict tests + 3 rewritten faithfulness tests included).

- [ ] **Step 10: Live sanity — the 2 pears still map clean**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 8`
Expected: both pears labelled `corpus-carried` (deveci may flake — `--repeat 8` averages it), tally `corpus-carried: 2/2`, no `[drift]` line, exit 0. If deveci shows a `[drift]` regression, re-run `--repeat 8 --only local_deveci_pear` to confirm it is the known flake (item 25), not a real regression.

- [ ] **Step 11: Commit**

```bash
git add evals/run_eval.py evals/eval_set.py tests/test_run_eval.py
git commit -m "Faithfulness becomes a drift guard: gate only on corpus-carried regressions"
```

---

### Task 2: Zone 1 candidates — local Turkish cultivar facts

Author 2 candidates asserting a Turkey-specific cultivar finding only the corpus carries (highest expected hit-rate). This and Tasks 3–5 are INVESTIGATIVE: mine a real source, draft the case, measure its quadrant live, keep-or-drop.

**Files:**
- Modify: `evals/eval_set.py` (append cases to `CASES`, after the `local` block ~line 271)

**Interfaces:**
- Consumes: `corpus_class` field convention + keep/drop rule (Task 1, Global Constraints).
- Produces: 0–2 new `corpus_fact` cases with ids `local_<slug>` and a recorded `corpus_class`.

- [ ] **Step 1: Mine a source fact.** Pick a Turkish cultivar term and read its `dp_` chunks. Seed terms to try (each is a distinct cultivar with likely corpus coverage): `"Sarılop"` (fig), `"Tombul"` (hazelnut), `"Öküzgözü"` (grape), `"Ohadi"` / `"Kırmızı"` (pistachio). Run, reading the printed dp_ text for a specific, answer-natural finding (a harvest window, a self-fertility verdict, a specific ratio):

```bash
PYTHONIOENCODING=utf-8 PYTHONPATH="$PWD" python -c "
from src import engine
col = engine._get_retriever_store()._collection
term='Sarılop'
r=col.get(where_document={'\$contains':term}, include=['documents','metadatas'], limit=40)
for d,m in zip(r['documents'],r['metadatas']):
    if m.get('source','').startswith('dp_'):
        print('---',m['source'],m.get('era'),'---'); print(' '.join(d.split())[:500]); print()
"
```

- [ ] **Step 2: Draft the case.** Append to `CASES` in `evals/eval_set.py`, mirroring the pear template. Replace the bracketed parts with the mined fact; `corpus_class` starts as `"corpus-carried"` (a hypothesis, confirmed in Step 3):

```python
    {"id": "local_<slug>", "category": "local", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "<natural TR question a grower would ask>",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["<cultivar name, lowercased>"],
     # <dp_source>: <one-line why this fact is the source's own finding>
     "answer_any": ["<answer-natural value the fact yields>"]},
```

- [ ] **Step 3: Measure the quadrant live.**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --only local_<slug> --repeat 4`
Read the printed label:
- `corpus-carried` → KEEP; leave `corpus_class: "corpus-carried"`.
- `model-carried` → KEEP as map data; change `corpus_class` to `"model-carried"`.
- `retrieval-broken` or `corpus-harmful` (i.e. red normally) → **DROP** the case (delete it from `CASES`); record the drop for the Task 6 artifact (id, query, why it failed green-normal). Do NOT retune.

- [ ] **Step 4: Repeat Steps 1–3 for the second Zone-1 candidate** (a different cultivar).

- [ ] **Step 5: Confirm the suite still parses and passes.**

Run: `python -m pytest -q`
Expected: PASS (new cases are data; no unit test asserts their count).

- [ ] **Step 6: Commit the surviving Zone-1 cases.**

```bash
git add evals/eval_set.py
git commit -m "Add Zone-1 corpus_fact cases (local Turkish cultivar) to the dependence map"
```

---

### Task 3: Zone 2 candidates — disease/pest organic management

Author 2 candidates asserting a corpus-specific disease detail — a named biocontrol agent or a resistant-cultivar list a natural organic answer would state.

**Files:**
- Modify: `evals/eval_set.py` (append to `CASES`)

**Interfaces:**
- Consumes: same conventions as Task 2.
- Produces: 0–2 `corpus_fact` cases (ids like `disease_<slug>`) with recorded `corpus_class`.

- [ ] **Step 1: Mine a source fact.** Seed terms: `"Trichoderma"`, `"Bacillus subtilis"` (biocontrol agents named in `dp_`), or a resistant-cultivar list — e.g. pear fire-blight resistance (`dp_1399494` names Potomac / Blake's Pride / Shenandoah / Sunrise per handoff item 30). Use the Step-1 mining command from Task 2 with the chosen term; read for a specific, answer-natural detail.

- [ ] **Step 2: Draft the case** in `evals/eval_set.py`, `category: "disease"`, mirroring the template in Task 2 Step 2. Example shape for the fire-blight candidate (confirm the cultivars against the mined chunk before committing):

```python
    {"id": "disease_fireblight_resistant", "category": "disease", "corpus_fact": True,
     "corpus_class": "corpus-carried",
     "query": "Ateş yanıklığına dayanıklı armut çeşitleri hangileridir?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["ateş yanıklığı", "erwinia", "fire blight"],
     # dp_1399494 names specific resistant cultivars - a natural answer lists them
     "answer_any": ["potomac", "blake", "shenandoah", "sunrise"]},
```

Note: this zone is also where the guardrail matters — do NOT author a case whose natural answer would name a chemical (that collides with the disease guardrail). Keep assertions on organic/biological/resistant facts.

- [ ] **Step 3: Measure the quadrant live** (same command + keep/drop rule as Task 2 Step 3, with `--only disease_<slug>`).

- [ ] **Step 4: Repeat Steps 1–3 for the second Zone-2 candidate.**

- [ ] **Step 5: Run the unit suite.**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit the surviving Zone-2 cases.**

```bash
git add evals/eval_set.py
git commit -m "Add Zone-2 corpus_fact cases (disease organic) to the dependence map"
```

---

### Task 4: Zone 3 candidates — horticulture technique parameter

Author 2 candidates asserting a corpus-specific technique parameter (a grafting success rate, a specific bud/shoot count, a drip rate) — lower expected hit-rate, so expect some drops.

**Files:**
- Modify: `evals/eval_set.py` (append to `CASES`)

**Interfaces:**
- Consumes: same conventions as Task 2.
- Produces: 0–2 `corpus_fact` cases (ids like `technique_<slug>`) with recorded `corpus_class`.

- [ ] **Step 1: Mine a source fact.** Seed terms: `"aşı tutma"` / `"% tutum"` (grafting take-rate), `"göz aşısı"`, `"sürgün sayısı"`, a specific drip rate like `"litre/saat"`. Use Task 2's mining command. Reject table-only values (a rate quoted only in a results table) — apply the answer-natural rule strictly here; this zone is where the cherry-drop shape recurs.

- [ ] **Step 2: Draft the case** in `evals/eval_set.py`, `category: "horticulture"`, mirroring the template in Task 2 Step 2 (`retrieval: "nonempty"`, `products: "none"`).

- [ ] **Step 3: Measure the quadrant live** (Task 2 Step 3 rule, `--only technique_<slug>`).

- [ ] **Step 4: Repeat Steps 1–3 for the second Zone-3 candidate.**

- [ ] **Step 5: Run the unit suite.**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit the surviving Zone-3 cases.**

```bash
git add evals/eval_set.py
git commit -m "Add Zone-3 corpus_fact cases (horticulture technique) to the dependence map"
```

---

### Task 5: Zone 4 candidates — gap-crop / quantitative finding

Author 2 candidates asserting a specific quantitative finding (a yield figure, a fertilizer rate) for a crop — a value the model is less likely to state precisely.

**Files:**
- Modify: `evals/eval_set.py` (append to `CASES`)

**Interfaces:**
- Consumes: same conventions as Task 2.
- Produces: 0–2 `corpus_fact` cases (ids like `quant_<slug>`) with recorded `corpus_class`.

- [ ] **Step 1: Mine a source fact.** Seed terms: `"t/ha"`, `"kg/da"`, `"verim"` combined with a crop, or a C/N ratio (`"C/N"`). Prefer a figure a grower would ask about and an answer would state (an expected yield, a recommended rate), not an experimental-plot artifact.

- [ ] **Step 2: Draft the case** in `evals/eval_set.py`. Category: `"nutrition"` if it is a fertilizer rate, else `"horticulture"`. Mirror the Task 2 template.

- [ ] **Step 3: Measure the quadrant live** (Task 2 Step 3 rule, `--only quant_<slug>`). Note: quantitative facts often come back `model-carried` (gemma knows rough yields) — that is a valid map finding, keep it with `corpus_class: "model-carried"`.

- [ ] **Step 4: Repeat Steps 1–3 for the second Zone-4 candidate.**

- [ ] **Step 5: Run the unit suite.**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit the surviving Zone-4 cases.**

```bash
git add evals/eval_set.py
git commit -m "Add Zone-4 corpus_fact cases (gap-crop quantitative) to the dependence map"
```

---

### Task 6: Run the full map + write the artifact

Produce the deliverable: the scoreboard across all `corpus_fact` cases and a written per-zone map, including dropped candidates.

**Files:**
- Modify: `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md` (new item; the handoff is the project's convention for measured findings — outside git)

**Interfaces:**
- Consumes: all `corpus_fact` cases shipped in Tasks 1–5 + the dropped-candidate notes.
- Produces: the map artifact (handoff item) — no code.

- [ ] **Step 1: Run the full map.**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --faithfulness --repeat 4`
Capture the per-case labels + the tally line + exit code. (Expect a mix of corpus-carried and model-carried; exit 0 unless a recorded corpus-carried case regressed.)

- [ ] **Step 2: Write the map artifact.** Add a new numbered item to `handoff-next-steps.md` recording: the scoreboard (tally), the per-zone result (which zones came back corpus-carried vs model-carried), the DROPPED candidates (id, query, why green-normal failed) as findings, and the one-line takeaway (where the corpus is load-bearing). Reference the spec and this plan by path.

- [ ] **Step 3: Confirm the drift guard is live and green.**

Run: `python -m pytest -q` (unit suite green) and confirm Step 1's run exited 0 (no unflagged regression). If deveci flaked, note it per item 25.

- [ ] **Step 4: Commit any final eval_set docstring touch-ups** (if the `corpus_fact` field comment in `eval_set.py:57-64` needs updating to mention `corpus_class` and the map framing):

```bash
git add evals/eval_set.py
git commit -m "Document corpus_class and the dependence-map framing in eval_set"
```

---

## Self-Review

**Spec coverage:**
- §1 purpose (panel 2→~10, map framing) → Tasks 2–5 (cases) + Task 1 (map gate) + Task 6 (artifact). ✓
- §2 authoring + validation protocol (read source, answer-natural, both-direction, keep/drop) → Tasks 2–5 Steps 1–3 + Global Constraints. ✓
- §3 drift-guard (`corpus_class` field, scoreboard, gate only on corpus-carried regression, flakiness via `--repeat`) → Task 1 (helper + wiring + tests) + Step 10 flakiness note. ✓
- §4 deliverable (map artifact) + unit tests → Task 6 + Task 1 Steps 2/4/9. ✓
- §5 out-of-scope → nothing in the plan touches freshness/prompt/retrieval-fix/harvesting. ✓

**Placeholder scan:** Investigative tasks (2–5) leave the mined fact to execution BY DESIGN — but each gives exact mining commands, a concrete case template, a live validation command, and a deterministic keep/drop rule, so the METHOD has no placeholders. The bracketed `<...>` in case templates are the discovered values, not hand-waving.

**Type consistency:** `_faithfulness_verdict(cases, live_labels) -> (int, list[str])` defined in Task 1, used only there. `corpus_class` string values are fixed in Global Constraints and match `_classify` output. `_optin_case(answer_any, corpus_class=...)` signature consistent across Task 1 steps 1/7.
