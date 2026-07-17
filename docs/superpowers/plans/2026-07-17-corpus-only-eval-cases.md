# Corpus-Only Eval Cases Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the eval cases that go RED when the corpus is removed, and a committed `--no-context` flag that proves they do.

**Architecture:** A new `local` category holds natural Turkish questions about Turkey-specific cultivars, asserting a specific finding from the source DergiPark paper. `run_eval.py --no-context` forces `engine.retrieve_context` to `""` for the whole run; its exit code answers one question only — did every `local` case lose grounding? Cases that stay green under ablation are decorative and are dropped, never re-tuned.

**Tech Stack:** Python 3.14, pytest, existing `evals/run_eval.py` + `evals/eval_set.py`.

**Spec:** `docs/superpowers/specs/2026-07-17-corpus-only-eval-cases-design.md`

## Global Constraints

- **The assertions below are PRE-REGISTERED by this committed plan.** Each is a
  finding quoted from its source paper. Do NOT edit an assertion after seeing a
  result. A case that fails to discriminate is **dropped and recorded**, never
  tuned until green (spec: "the assertion comes from the DOCUMENT, not from the
  output"; handoff item 22(a)).
- **A `local` case ships only if it is RED under `--no-context` AND GREEN in a
  normal run.** Anything else is decoration.
- **Under `--no-context` the exit code ignores ordinary cases.** They fail by
  construction (product-gating drops to 27/31 — measured), so an exit code driven
  by them would be 1 on every run and carry no information.
- Fewer than 3 cases may survive. That is an accepted outcome: the eval guards
  retrieval in **zero** places today, so one survivor is a gain.
- `--no-context --fast` must exit 1: `--fast` never calls `answer()`, so there is
  nothing to ablate (mirrors the existing `--fast --repeat N>1` rule).
- Commit style: short, English, no `Co-Authored-By` trailer.
- Repo root: `D:\Claude Projects\Agro-Botany RAG & Product Linker System`
- Needs LM Studio serving bge-m3 + gemma at :1234 for the validation steps only;
  every unit test runs offline.

---

### Task 1: `--no-context` — the validator

**Files:**
- Modify: `evals/run_eval.py`
- Test: `tests/test_run_eval.py`

**Interfaces:**
- Produces: `_ablation_verdict(rows: list[dict]) -> tuple[int, list[str]]` returning `(exit_code, decorative_case_ids)`; `_corpus_ablated()` context manager; `run(fast, repeat=1, only=None, no_context=False) -> int`.
- Consumes: `engine.retrieve_context` (`src/engine.py:324`), which `answer()` looks up on the module at call time — patching it therefore covers the call inside `answer()`, which is the one that matters.

**Why a pure verdict function:** it is the part with the logic, and it must be
testable without a model. The ablation itself is one line; the trap it guards
against ("0 of 0 local cases discriminate" exiting 0) is pure list logic.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_run_eval.py`:

```python
def test_ablation_verdict_all_local_cases_lost_grounding():
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "local_b", "cat": "local", "grounding": False}]
    assert run_eval._ablation_verdict(rows) == (0, [])


def test_ablation_verdict_flags_a_local_case_that_survives_ablation():
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "local_b", "cat": "local", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (1, ["local_b"])


def test_ablation_verdict_ignores_non_local_cases():
    """Ordinary cases fail under ablation by construction - if they moved the
    exit code it would be 1 on every run and mean nothing."""
    rows = [{"id": "local_a", "cat": "local", "grounding": False},
            {"id": "tomato_nutrition", "cat": "nutrition", "grounding": True},
            {"id": "compost", "cat": "nutrition", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (0, [])


def test_ablation_verdict_with_no_local_case_fails_rather_than_passing_vacuously():
    """'0 of 0 discriminate' must not read as success - same shape as the
    all([]) bug this project already shipped once."""
    rows = [{"id": "compost", "cat": "nutrition", "grounding": True}]
    assert run_eval._ablation_verdict(rows) == (1, [])


def test_corpus_ablated_empties_the_path_answer_uses(monkeypatch):
    from src import engine
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "REAL")
    assert engine.retrieve_context("x") == "REAL"
    with run_eval._corpus_ablated():
        assert engine.retrieve_context("x") == ""
    assert engine.retrieve_context("x") == "REAL"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
python -m pytest tests/test_run_eval.py -k "ablation or corpus_ablated" -v
```

Expected: FAIL — `AttributeError: module 'evals.run_eval' has no attribute '_ablation_verdict'`.

- [ ] **Step 3: Implement**

In `evals/run_eval.py`, add the import at the top (beside the existing ones):

```python
from contextlib import contextmanager
```

Add beside `_select` (line 69):

```python
@contextmanager
def _corpus_ablated():
    """Force retrieve_context to "" for the whole run.

    Patches the module attribute, not a local: answer() looks the name up on
    `engine` at call time, so this covers the retrieval INSIDE answer() - which
    is the one under test. A version that only blanked run()'s own `ctx` would
    ablate nothing and quietly "prove" the corpus load-bearing.
    """
    original = engine.retrieve_context
    engine.retrieve_context = lambda query, k=None: ""
    try:
        yield
    finally:
        engine.retrieve_context = original


def _ablation_verdict(rows: list[dict]) -> tuple[int, list[str]]:
    """(exit_code, decorative_case_ids) for a --no-context run.

    A `local` case exists to prove the corpus is load-bearing, so with an empty
    corpus it MUST lose grounding. One that still passes is asserting something
    the model knows anyway - decoration, and exactly the blind spot this flag
    exists to expose.

    Ordinary cases are ignored on purpose: they fail under ablation by
    construction (measured 2026-07-17: product-gating 31/31 -> 27/31), so letting
    them touch the exit code would make it 1 on every run and worthless.
    """
    local_rows = [r for r in rows if r.get("cat") == "local"]
    if not local_rows:
        return 1, []
    decorative = [r["id"] for r in local_rows if r.get("grounding")]
    return (1 if decorative else 0), decorative
```

Change `run`'s signature (line 85) and its guards:

```python
def run(fast: bool, repeat: int = 1, only: str | None = None,
        no_context: bool = False) -> int:
    if fast and repeat > 1:
        sys.exit("--repeat needs the chat model; it does nothing with --fast.")
    if fast and no_context:
        sys.exit("--no-context needs the chat model; --fast never calls answer().")
```

Now make four surgical edits inside `run`. The `fast` / full sampling branches
(lines 103-124) keep their existing bodies except where stated.

**Edit A** — import `nullcontext` too, so the loop reads the same in both modes:

```python
from contextlib import contextmanager, nullcontext
```

**Edit B** — wrap the loop. Replace line 94-95:

```python
    rows = []
    for c in cases:
```

with:

```python
    rows = []
    # The ablation must be in force around answer(), not just around run()'s own
    # retrieve_context call - blanking only the local `ctx` would ablate nothing.
    with (_corpus_ablated() if no_context else nullcontext()):
      for c in cases:
```

Re-indent the existing loop body (through line 139) by two spaces to sit under
`for`. Nothing else in it changes except Edits C and D.

**Edit C** — stop scoring the two dimensions this flag empties. Replace lines
100-102:

```python
        row = {"id": c["id"], "cat": c["category"],
               "retrieval": _retrieval_ok(c, ctx),
               "context": _context_ok(c, ctx)}
```

with:

```python
        row = {"id": c["id"], "cat": c["category"]}
        # retrieval/context are emptied BY this flag; scoring them would print a
        # wall of tautological FAILs (24 of them, measured) and bury the signal.
        if not no_context:
            row["retrieval"] = _retrieval_ok(c, ctx)
            row["context"] = _context_ok(c, ctx)
```

**Edit D** — `row["ok"]` and the per-case print must tolerate the two missing
keys. Replace the `row["ok"] = all([...])` in the `fast` branch (line 106):

```python
            row["ok"] = all([row["retrieval"], row["context"]])
```

with:

```python
            row["ok"] = all(row[d] for d in ("retrieval", "context"))
```

(`--fast --no-context` exits earlier, so `fast` always has both keys.)

Replace the `row["ok"] = all([...])` in the full branch (lines 122-124):

```python
            row["ok"] = all([row["retrieval"], row["context"],
                             row["products"], row["grounding"],
                             row["guardrail"]])
```

with:

```python
            dims = ["products", "grounding", "guardrail"]
            if not no_context:
                dims += ["retrieval", "context"]
            row["ok"] = all(row[d] for d in dims)
```

And replace the print (lines 138-139):

```python
        print(f"  [{mark}] {c['id']:<24} ret={row['retrieval']} "
              f"ctx={row['context']} " + detail + f"  ({row['secs']:.0f}s)")
```

with:

```python
        ret_ctx = ("ret=n/a ctx=n/a " if no_context
                   else f"ret={row['retrieval']} ctx={row['context']} ")
        print(f"  [{mark}] {c['id']:<24} " + ret_ctx + detail
              + f"  ({row['secs']:.0f}s)")
```

The `rate('retrieval')` / `rate('context')` summary lines (line 156) need no
change: `rate` already skips rows lacking the key and returns `"n/a"`.

Finally, replace the return (line 163):

```python
    if no_context:
        code, decorative = _ablation_verdict(rows)
        n_local = sum(1 for r in rows if r["cat"] == "local")
        if not n_local:
            print("\n[ablation] no `local` case in this selection - "
                  "nothing was validated")
            return code
        print(f"\n[ablation] local cases that lost grounding: "
              f"{n_local - len(decorative)}/{n_local}"
              + (" - they discriminate" if not decorative else ""))
        for case_id in decorative:
            print(f"[ablation] ! {case_id} still passes grounding with an EMPTY "
                  f"corpus - it guards nothing")
        return code
    return 0 if passed == len(rows) else 1
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_run_eval.py -k "ablation or corpus_ablated" -v
```

Expected: 5 passed.

- [ ] **Step 5: Wire up the CLI flag**

In `main()` (line 166), beside the existing arguments:

```python
    p.add_argument("--no-context", action="store_true",
                   help="Ablation: run with an EMPTY corpus to prove the `local` "
                        "cases actually depend on retrieval. Exit 0 only if every "
                        "local case loses grounding.")
```

and pass it through:

```python
    sys.exit(run(fast=args.fast, repeat=args.repeat, only=args.only,
                 no_context=args.no_context))
```

- [ ] **Step 6: Verify the guard rejects `--fast`**

```bash
python -m evals.run_eval --no-context --fast; echo "exit=$?"
```

Expected: `--no-context needs the chat model; --fast never calls answer().` and `exit=1`.

- [ ] **Step 7: Run the full suite and commit**

```bash
python -m pytest -q
git add evals/run_eval.py tests/test_run_eval.py
git commit -m "Add eval --no-context: prove a case fails without the corpus"
```

Expected: suite green (do not assert a count — `f2881bd` removed the hardcoded ones because they go stale).

---

### Task 2: The three pre-registered `local` cases

**Files:**
- Modify: `evals/eval_set.py`

**Interfaces:**
- Consumes: Task 1's `--no-context`.
- Produces: up to three cases with `category: "local"`.

**Sources (read 2026-07-17; each assertion is the paper's own finding):**

| Case | Source | The paper's finding |
|---|---|---|
| `local_deveci_pear` | `dp_21747.pdf` — Şen, Ünal & Arda, ANADOLU J. of AARI 19(2) 2009, *"Bursa yöresinde yetiştirilen 'Deveci' armut çeşidinin yöresel olgunluk standartlarının ve depolama durumlarının saptanması"* | Fruit stored at **2±0.5 °C**; keeps ~6 months if harvested mid/late October; November harvest degrades soluble solids + sensory quality. |
| `local_santamaria_pear` | `dp_19393.pdf` — self-fertility trial, Eğirdir (Isparta), 2008-2009, QA rootstock, 12-year-old trees | Ankara, Deveci, Williams, Beurre Hardy are **completely self-sterile**; Santa Maria, Akça, B.P.Morettini set some fruit on selfing but with very low seed count, judged **parthenocarpic**. |
| `local_0900ziraat_cherry` | `dp_1154776.pdf` — Güçlü, Demir, Koyuncu & Özüsoy, 2023, *"Farklı şekillerde yapılan kalsiyum uygulamalarının 0900 Ziraat kiraz çeşidinde meyve kalitesine etkileri"* | Foliar-only and foliar+soil calcium gave the highest fruit weight (**8.91 g** and 8.80 g); foliar gave the largest fruit width (26.73 mm); effects on SÇKM/pH/titratable acidity were **not** statistically significant. |

**Prior validation:** `local_deveci_pear` is already measured RED-ablated /
GREEN-normal (2026-07-17). With the corpus it answers "Bursa... Ekim ortası veya
sonu... 2±0,5°C'de yaklaşık 6 ay"; ablated it answers "Eylül sonundan Kasım
başına... 0-2°C... 3 ila 6 ay". The other two are untested.

**Rejected during mining, do NOT revive without new evidence:**
- **Amasya apple** — `"amasya elma"` and `"amasya kırmızısı"` both scan to **0
  chunks**. The 33 `amasya` hits are the PROVINCE name inside a
  Scarabaeidae fauna survey (`dp_1052881.pdf`) — the cultivar is not in the corpus.
- **Gemlik olive** — `"gemlik zeytin"` scans to 2 chunks, both in
  `dp_1869487.pdf`, a metabolomics paper on the geographic origin of Gemlik olive
  OIL (food authenticity), not growing. No natural grower question lands there.
- The first Deveci assertion drafted was `answer_any: ["6 ay"]`. It does **not**
  discriminate — the ablated answer also says "3 ila 6 ay".

- [ ] **Step 1: Add the cases**

In `evals/eval_set.py`, append to `CASES`:

```python
    # --- local: Turkey-specific cultivar facts that only the corpus carries ---
    # Each answer_any is the SOURCE PAPER's own finding (see the plan's table),
    # chosen before any run. These are the only cases that go red when the corpus
    # is removed - verify with: python -m evals.run_eval --no-context --only local
    {"id": "local_deveci_pear", "category": "local",
     "query": "Deveci armudu ne zaman hasat edilmeli ve soğukta ne kadar depolanabilir?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["deveci"],
     # dp_21747: stored at 2±0.5 °C. Ablated, the model says "0-2°C" and
     # "3 ila 6 ay" - so "6 ay" would NOT discriminate, but this does.
     "answer_any": ["2±0,5", "2±0.5", "2 ± 0,5", "2 ± 0.5"]},
    {"id": "local_santamaria_pear", "category": "local",
     "query": "Santa Maria armudu kendine verimli mi, bahçeye dölleyici çeşit dikmek gerekir mi?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["santa maria"],
     # dp_19393 (Eğirdir): selfed fruit had very low seed set and was judged
     # parthenocarpic - the study's own conclusion term.
     "answer_any": ["partenokarp"]},
    {"id": "local_0900ziraat_cherry", "category": "local",
     "query": "0900 Ziraat kirazında kalsiyumu yapraktan mı topraktan mı uygulamalı?",
     "retrieval": "nonempty", "products": "any",
     "context_any": ["0900 ziraat"],
     # dp_1154776: foliar application gave the highest mean fruit weight, 8.91 g.
     "answer_any": ["8.91", "8,91"]},
```

`products: "any"` on the cherry case only, and deliberately: it is a nutrition
question, so a calcium product WOULD be a legitimate recommendation — "none" would
be wrong — but the catalog cannot be shown to rank the right one, so "some" would
pass vacuously. Same documented gap as `propagation_cutting` (`eval_set.py:39-42`).
The other two ask about harvest timing and pollination, where the 48-fertilizer
catalog answers nothing: "none" per eval_set's standing stance.

- [ ] **Step 2: Document the category**

In the `eval_set.py` docstring, extend the category line:

```
- category: nutrition | horticulture | disease | chemical | offscope | local
```

and add, after the `answer_none` entry:

```
`local` cases are different in kind from the rest: they exist to prove RETRIEVAL
contributes, not that the answer is nice. Measured 2026-07-17 by ablation
(retrieve_context forced to ""): grounding stayed 31/31 and guardrail stayed
31/31 with an EMPTY corpus - i.e. every other case is passing on gemma's own
knowledge plus the prompt, and the corpus's only measurable job was feeding
match_products (product-gating 31/31 -> 27/31). A `local` case asserts a specific
finding from ONE source paper, so the model cannot bluff it. Validate with
`--no-context`: a local case MUST go red there, or it guards nothing.
```

- [ ] **Step 3: Commit before validating**

The assertions are pre-registered by the plan; committing them before the run
keeps that auditable.

```bash
git add evals/eval_set.py
git commit -m "Add local eval cases: corpus-only cultivar facts"
```

---

### Task 3: Validate, then drop what does not discriminate

**Files:**
- Modify: `evals/eval_set.py` (only to DELETE a non-discriminating case)

**Interfaces:**
- Consumes: Tasks 1 and 2.

- [ ] **Step 1: Confirm the cases pass normally**

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
python -m evals.run_eval --only local
```

Expected: 3/3, each with `ground=True`. A case failing HERE means the corpus does
not actually supply its fact through retrieval — record it and drop it in Step 3;
do not soften the assertion.

- [ ] **Step 2: Run the ablation**

```bash
python -m evals.run_eval --no-context --only local; echo "exit=$?"
```

Expected on full success:

```
[ablation] local cases that lost grounding: 3/3 - they discriminate
exit=0
```

Any line reading `! <id> still passes grounding with an EMPTY corpus` marks a
decorative case, and the exit code is 1.

- [ ] **Step 3: Drop every case that failed either direction**

A case ships only if Step 1 was GREEN and Step 2 was RED for it. Delete the
others from `eval_set.py` — do not retune them (Global Constraints).

For each dropped case record, in the handoff: its query, its assertion, and which
direction failed. Without that, the next session re-derives the same dead case
from the same chunk counts.

```bash
git add evals/eval_set.py
git commit -m "Drop the local cases that do not depend on the corpus"
```

(Skip this commit if all three survived.)

- [ ] **Step 4: Prove the whole eval is still green**

```bash
python -m evals.run_eval
python -m pytest -q
```

Expected: every dimension green including the surviving `local` cases; suite
green. If a `local` case is red here but green in Step 1, it is flaky — that is a
`--repeat` question (`python -m evals.run_eval --repeat 5 --only local`), not a
reason to weaken the assertion.

---

### Task 4: Record the outcome

**Files:**
- Modify: `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md`

- [ ] **Step 1: Update item 25 with what shipped**

Item 25 currently ends with "NEXT: fix the EVAL, not the corpus". Replace that
with the result: how many `local` cases survived, their ids, and the verdict line
from the ablation run. State plainly how many places the eval now guards
retrieval (it was **zero**).

Record the mining dead-ends so nobody repeats them: Amasya apple (0 chunks — the
33 hits were the province in a beetle survey), Gemlik olive (2 chunks, food
authenticity not growing), and `"6 ay"` as a non-discriminating assertion.

- [ ] **Step 2: Note the tool and its trigger**

Add one line to the Ops section:

```
`python -m evals.run_eval --no-context --only local` - ablation: run it whenever
a `local` case is added or edited. Exit 0 only if every local case loses
grounding with an empty corpus. Needs the chat model; ~1 min for 3 cases.
```

- [ ] **Step 3: Confirm the repo is clean**

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
git status --short
```

Expected: clean, or only the pre-existing untracked `docs/books/_offtopic/`.
