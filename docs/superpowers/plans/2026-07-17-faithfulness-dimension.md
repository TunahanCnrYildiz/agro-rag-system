# Faithfulness Dimension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `run_eval.py --faithfulness`, which runs each `corpus_fact` case normal + ablated and classifies whether the corpus actually carries the answer, so the "corpus contributes to 2/33 cases" state becomes a guarded, tracked number.

**Architecture:** A pure classifier `_classify(normal_all_green, ablated_all_green)` maps the two-run outcome to one of four labels. A runner `run_faithfulness()` reuses the existing `_corpus_ablated()` primitive and `_answer_ok()` grounding check to run each opted-in case normal then ablated (with `--repeat` sampling), classify, report, and set the exit code. A `corpus_fact: true` field marks the opt-in cases.

**Tech Stack:** Python 3.14, pytest, existing `evals/run_eval.py` + `evals/eval_set.py`.

**Spec:** `docs/superpowers/specs/2026-07-17-faithfulness-dimension-design.md`

## Global Constraints

- **Contribution, not support:** measured by ablation-delta (corpus removed →
  answer degrades), NOT by an LLM-judge (the local model is an untrustworthy
  instrument — empty ~3%, mistranslates; handoff items 11, 20).
- **Scored over opt-in cases only** (`corpus_fact: true`). A generic assertion
  passing under ablation cannot distinguish "corpus did not help" from "assertion
  too weak", so only cases declaring a corpus-specific fact are counted.
- **No magic threshold.** Reuse the eval's existing sampled-dimension rule: `all()`
  ("every sample must pass") plus a visible hit fraction. A tuned threshold is the
  item-22(a) trap.
- **Exit 1 if any opt-in case is not corpus-carried.** Opting in is a claim the
  tool verifies, mirroring `--no-context`'s "every local case must lose grounding".
- **The score is a GUARD, not a coverage meter.** It does not answer "what
  fraction of user questions the corpus carries"; the denominator is small and
  self-selected. State this in the docstring.
- Commit style: short, English, no `Co-Authored-By` trailer.
- Repo root: `D:\Claude Projects\Agro-Botany RAG & Product Linker System`
- `answer()` returns `engine.ChatResult(answer: str, recommended_products: list)`.
- Live validation (Task 3) needs LM Studio serving bge-m3 + gemma; every unit test
  (Tasks 1-2) runs offline.

---

### Task 1: `_classify` — the four-quadrant pure function

**Files:**
- Modify: `evals/run_eval.py`
- Test: `tests/test_run_eval.py`

**Interfaces:**
- Produces: `_classify(normal_all_green: bool, ablated_all_green: bool) -> str`
  returning one of `"corpus-carried"`, `"model-carried"`, `"retrieval-broken"`,
  `"corpus-harmful"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_run_eval.py`:

```python
def test_classify_corpus_carried():
    # green normally, red ablated -> the corpus supplies the fact
    assert run_eval._classify(True, False) == "corpus-carried"


def test_classify_model_carried():
    # green both ways -> the model knew it; corpus adds nothing detectable
    assert run_eval._classify(True, True) == "model-carried"


def test_classify_retrieval_broken():
    # red both ways -> cannot answer even WITH the corpus
    assert run_eval._classify(False, False) == "retrieval-broken"


def test_classify_corpus_harmful():
    # red normally but green ablated -> the corpus BROKE a right answer
    assert run_eval._classify(False, True) == "corpus-harmful"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
python -m pytest tests/test_run_eval.py -k classify -v
```

Expected: FAIL — `AttributeError: module 'evals.run_eval' has no attribute '_classify'`.

- [ ] **Step 3: Implement**

In `evals/run_eval.py`, add after `_ablation_verdict` (line 119):

```python
def _classify(normal_all_green: bool, ablated_all_green: bool) -> str:
    """Label a case by how its grounding moves when the corpus is removed.

    corpus-carried : green normally, red ablated -> the corpus supplies the fact.
    model-carried  : green both ways -> the model knew it (or the mark is wrong).
    retrieval-broken: red both ways -> cannot answer even with the corpus.
    corpus-harmful : red normally, green ablated -> retrieval injected noise that
                     broke an answer the model would otherwise have gotten right.
    """
    if normal_all_green:
        return "corpus-carried" if not ablated_all_green else "model-carried"
    return "corpus-harmful" if ablated_all_green else "retrieval-broken"
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_run_eval.py -k classify -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add evals/run_eval.py tests/test_run_eval.py
git commit -m "Add _classify: label a case by how grounding moves under ablation"
```

---

### Task 2: `run_faithfulness` runner + `--faithfulness` CLI

**Files:**
- Modify: `evals/run_eval.py`
- Test: `tests/test_run_eval.py`

**Interfaces:**
- Consumes: Task 1's `_classify`; existing `_select` (line 70), `_corpus_ablated`
  (line 86), `_answer_ok` (line 60), `engine.answer`, `settings.request_timeout`.
- Produces: `run_faithfulness(repeat: int = 1, only: str | None = None,
  fast: bool = False) -> int`.

**Note on the offline tests:** they never call a real model. They monkeypatch
`engine.retrieve_context` (so `_corpus_ablated` still flips it to `""`) and
`engine.answer` with a fake that reads `retrieve_context` and branches on whether
context is present — so the test exercises the REAL ablation + classification path,
not a mock of it.

- [ ] **Step 1: Write the failing tests**

First add the two module-level imports these tests need, near the top of
`tests/test_run_eval.py` (it currently imports only `pytest` at line 3 and
`from evals import run_eval` at line 5; `engine` is imported locally inside one
test, `ChatResult` not at all):

```python
from src import engine
from src.engine import ChatResult
```

Then add the tests:

```python
def _optin_case(answer_any):
    return {"id": "probe", "category": "local", "corpus_fact": True,
            "query": "q", "answer_any": answer_any}


def test_faithfulness_corpus_carried_exits_0(monkeypatch):
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)  # respects _corpus_ablated
        return ChatResult("depo 2±0,5 derece" if ctx else "genel tavsiye", [])
    monkeypatch.setattr(engine, "answer", fake)

    assert run_eval.run_faithfulness() == 0


def test_faithfulness_model_carried_exits_1(monkeypatch):
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    # states the fact regardless of context -> the model carries it
    monkeypatch.setattr(engine, "answer",
                        lambda msg, history=None: ChatResult("hep 2±0,5 der", []))
    assert run_eval.run_faithfulness() == 1


def test_faithfulness_corpus_harmful_exits_1(monkeypatch):
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)
        # right ONLY when context is absent -> retrieval broke it
        return ChatResult("genel" if ctx else "2±0,5 dogru", [])
    monkeypatch.setattr(engine, "answer", fake)
    assert run_eval.run_faithfulness() == 1


def test_faithfulness_no_optin_case_exits_1(monkeypatch):
    plain = {"id": "z", "category": "nutrition", "query": "q", "answer_any": ["x"]}
    monkeypatch.setattr(run_eval, "_select", lambda only: [plain])
    assert run_eval.run_faithfulness() == 1


def test_faithfulness_fast_exits(monkeypatch):
    with pytest.raises(SystemExit):
        run_eval.run_faithfulness(fast=True)


def test_faithfulness_one_red_normal_sample_drops_corpus_carried(monkeypatch):
    monkeypatch.setattr(run_eval, "_select", lambda only: [_optin_case(["2±0,5"])])
    monkeypatch.setattr(engine, "retrieve_context", lambda q, k=None: "CTX")
    calls = {"n": 0}

    def fake(msg, history=None):
        ctx = engine.retrieve_context(msg)
        calls["n"] += 1
        if not ctx:
            return ChatResult("genel", [])           # ablated: always red
        text = "genel" if calls["n"] == 1 else "2±0,5 var"  # 1st normal red
        return ChatResult(text, [])
    monkeypatch.setattr(engine, "answer", fake)

    # repeat=2: normal samples red+green -> not unanimous -> not corpus-carried
    assert run_eval.run_faithfulness(repeat=2) == 1
```

- [ ] **Step 2: Run them to verify they fail**

```bash
python -m pytest tests/test_run_eval.py -k faithfulness -v
```

Expected: FAIL — `AttributeError: module 'evals.run_eval' has no attribute 'run_faithfulness'`.

- [ ] **Step 3: Implement the runner**

In `evals/run_eval.py`, add after `run()` (line 226, before `main`):

```python
def run_faithfulness(repeat: int = 1, only: str | None = None,
                     fast: bool = False) -> int:
    """Corpus-contribution check over `corpus_fact` cases only.

    For each opted-in case: run answer() normal and ablated, and classify by how
    its grounding moves (see _classify). Exit 0 only if every such case is
    corpus-carried - opting in is a claim ("this case needs the corpus") that this
    verifies, exactly as --no-context requires every local case to lose grounding.

    NOT a coverage meter: the score sees only cases we deliberately built to need
    the corpus, so "2/2" means "both of the two we bothered to make corpus-specific
    work", not "the corpus carries 100% of user questions". The denominator is
    small and self-selected - do not read it as corpus coverage.
    """
    if fast:
        sys.exit("--faithfulness needs the chat model; --fast never calls answer().")
    cases = [c for c in _select(only) if c.get("corpus_fact")]
    if not cases:
        print("[faithfulness] no `corpus_fact` case in this selection - "
              "nothing to measure")
        return 1
    settings.request_timeout = 400.0

    def grounded_hits(case: dict) -> int:
        return sum(_answer_ok(case, engine.answer(case["query"]).answer)[0]
                   for _ in range(repeat))

    suffix = f", {repeat}x each" if repeat > 1 else ""
    print(f"=== faithfulness (corpus contribution), "
          f"{len(cases)} corpus_fact case(s){suffix} ===\n")
    counts = {"corpus-carried": 0, "model-carried": 0,
              "retrieval-broken": 0, "corpus-harmful": 0}
    for c in cases:
        normal_hits = grounded_hits(c)
        with _corpus_ablated():
            ablated_hits = grounded_hits(c)
        label = _classify(normal_hits == repeat, ablated_hits == repeat)
        counts[label] += 1
        print(f"  {c['id']:<24} {label:<16} "
              f"normal {normal_hits}/{repeat}  ablated {ablated_hits}/{repeat}")

    total = len(cases)
    print(f"\n  corpus-carried: {counts['corpus-carried']}/{total}  |  "
          f"harmful: {counts['corpus-harmful']}  |  "
          f"retrieval-broken: {counts['retrieval-broken']}  |  "
          f"model-carried: {counts['model-carried']}")
    return 0 if counts["corpus-carried"] == total else 1
```

- [ ] **Step 4: Wire the CLI flag**

In `main()`, add the argument after `--no-context` (line 246):

```python
    p.add_argument("--faithfulness", action="store_true",
                   help="Corpus-contribution check: for each corpus_fact case, "
                        "run normal + ablated and classify. Exit 0 only if every "
                        "such case is corpus-carried. Pair with --repeat to expose "
                        "flaky wins.")
```

and replace the final dispatch (lines 247-249):

```python
    args = p.parse_args()
    if args.faithfulness:
        sys.exit(run_faithfulness(repeat=args.repeat, only=args.only,
                                  fast=args.fast))
    sys.exit(run(fast=args.fast, repeat=args.repeat, only=args.only,
                 no_context=args.no_context))
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_run_eval.py -k faithfulness -v
```

Expected: 6 passed.

- [ ] **Step 6: Run the whole suite and commit**

```bash
python -m pytest -q
git add evals/run_eval.py tests/test_run_eval.py
git commit -m "Add run_faithfulness + --faithfulness: guard corpus_fact cases"
```

Expected: suite green (do not assert a count — `f2881bd` removed the hardcoded ones).

---

### Task 3: Mark the opt-in cases, document, validate live

**Files:**
- Modify: `evals/eval_set.py`

**Interfaces:**
- Consumes: Task 2's `--faithfulness`.

- [ ] **Step 1: Add `corpus_fact: true` to the two local cases**

In `evals/eval_set.py`, add the field to `local_deveci_pear` and
`local_santamaria_pear` (they already carry corpus-specific `answer_any`):

```python
    {"id": "local_deveci_pear", "category": "local", "corpus_fact": True,
     "query": "Deveci armudu ne zaman hasat edilmeli ve soğukta ne kadar depolanabilir?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["deveci"],
     "answer_any": ["2±0,5", "2±0.5", "2 ± 0,5", "2 ± 0.5"]},
    {"id": "local_santamaria_pear", "category": "local", "corpus_fact": True,
     "query": "Santa Maria armudu kendine verimli mi, bahçeye dölleyici çeşit dikmek gerekir mi?",
     "retrieval": "nonempty", "products": "none",
     "context_any": ["santa maria"],
     "answer_any": ["partenokarp"]},
```

- [ ] **Step 2: Document the field in the docstring**

In the `eval_set.py` docstring, after the `context_min` / `local` notes, add:

```
- corpus_fact: True marks a case whose `answer_any` is a fact ONLY the corpus
             would supply (a cultivar-specific value, not a generic keyword).
             `--faithfulness` runs ONLY these cases, normal + ablated, and
             requires each to be corpus-carried (green normal, red ablated). It is
             a GUARD that each claimed corpus-carried case really is one - NOT a
             measure of what fraction of user questions the corpus carries (the
             denominator is small and self-selected). A field, not a category, so
             a future nutrition case asserting a corpus-specific value can opt in.
```

- [ ] **Step 3: Validate that unit tests still pass**

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
python -m pytest -q
```

Expected: suite green.

- [ ] **Step 4: Live-validate against the real store (needs LM Studio)**

```bash
python -m evals.run_eval --faithfulness
```

Expected: both cases classified `corpus-carried`, summary `corpus-carried: 2/2`,
exit 0. Confirm with `echo $?` written to a file, NOT `| tail` (handoff item 22(b):
`cmd | tail; echo $?` reports tail's exit code):

```bash
python -m evals.run_eval --faithfulness > /tmp/f.txt 2>&1; echo "exit=$?"; cat /tmp/f.txt
```

If a case comes back `model-carried`, the deveci flake may have struck (it is
2-in-15 red normally); re-run, and use `--repeat 5 --faithfulness` to see the
fraction. A persistent non-`corpus-carried` result is a real finding — record it,
do not weaken the assertion to force green.

- [ ] **Step 5: Prove the guard has teeth**

Temporarily weaken one assertion to a generic keyword the model always says, and
confirm the tool flips it to `model-carried` and exits 1:

```bash
# in eval_set.py, TEMPORARILY change local_deveci_pear answer_any to ["armut"]
python -m evals.run_eval --faithfulness --only local_deveci_pear > /tmp/f.txt 2>&1; echo "exit=$?"; cat /tmp/f.txt
# expect: model-carried, exit=1. Then REVERT the change.
```

- [ ] **Step 6: Commit**

```bash
git add evals/eval_set.py
git commit -m "Mark the two local cases corpus_fact; --faithfulness guards them"
```

---

### Task 4: Record the outcome

**Files:**
- Modify: `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md`

- [ ] **Step 1: Update item 26 with what shipped**

Note that the faithfulness guard now exists: `--faithfulness` classifies
`corpus_fact` cases into the four quadrants, exit 0 only if all corpus-carried;
today 2/2. State plainly it is a GUARD, not the coverage meter — the "grow 2/33"
work is still authoring more `corpus_fact` cases (item 25 extension), which this
now protects. Record the Step 4 live result (both corpus-carried, or any flake
seen) and the Step 5 teeth-check outcome.

- [ ] **Step 2: Add the tool to the Ops section**

```
`python -m evals.run_eval --faithfulness` - corpus-contribution guard over
`corpus_fact` cases: normal + ablated, exit 0 only if all corpus-carried. Pair
with `--repeat N` to expose flaky wins (deveci). Needs the chat model.
```

- [ ] **Step 3: Confirm the repo is clean**

```bash
cd "D:\Claude Projects\Agro-Botany RAG & Product Linker System"
git status --short
```

Expected: clean, or only the pre-existing untracked `docs/books/_offtopic/`.
