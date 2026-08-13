# `crop_choice` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `crop_choice` route answer "what should I plant this year" with the factors that decide it and the questions that are still open, instead of falling through to a corpus search that cannot hold the answer.

**Architecture:** `crop_choice` follows the pattern `fert_plan` established in plan 2: a route-specific context block is prepended to the system prompt and the answer is still produced by the existing corpus path. **This route adds no module and no arithmetic** — it reads province and season from modules that already exist and shipped green, and everything else it does is prompt text. That is the whole reason it was split out of the `budget` plan.

**Tech Stack:** Python 3.14, pytest, the existing `src/engine.py` / `src/context/*` modules. No new dependencies.

## Provenance

This plan is the `crop_choice` half of `docs/superpowers/plans/2026-08-11-budget-and-crop-choice.md`, extracted verbatim where the content carried over. The `budget` half of that plan is **superseded** — its extractor came out of review with five Criticals, every one a demonstrated wrong money figure, and the decision was to replace prose parsing with a form rather than patch it a fourth time. Task 3 of this plan records that in the old plan document so nobody executes it by accident.

The design this implements is `docs/superpowers/specs/2026-08-11-budget-and-crop-choice-design.md` §5 and §8. Read §5 before Task 1; it is fifteen lines and it is the contract.

## Global Constraints

- **A route may diverge only with zero wrong entries in the frozen 42-case routing set.** Measured on 2026-08-13 at the time of writing: `crop_choice` is in `sevke uygun rotalar (sifir yanlis giris)`, accuracy 37/42 (88%), gate FAILED at >= 90%. **The failing gate is about `plant_info` absorbing five cases and does not block this plan** — the binding rule from plan 1 is that a *diverging route* must have zero wrong entries of its own, and `crop_choice` does. Task 1 re-measures before touching code.
- **The routing rules are not touched by this plan.** A *changed* accuracy number is therefore itself a finding: stop and report it rather than explaining it.
- **Prompt text is ASCII-folded Turkish** (`Kullanicinin ili`, not `Kullanıcının ili`). Every existing context block is written this way; match it. Test assertions and eval anchors are the opposite — they are real Turkish, because they match what the model writes.
- **Windows console cannot encode Turkish.** Prefix every command that prints corpus or answer text with `PYTHONIOENCODING=utf-8`. Every command in this plan already carries it; do not drop it.
- **Run everything from the repo root.** `src/config.py` reads a root-anchored `.env`.
- **The prohibition on naming a crop is a PROMPT constraint, not something code can enforce** (spec §5). It is measured by the eval's `answer_none` dimension. **A red there is a finding to report, not an anchor to soften.**
- Baseline before this plan: **471 tests**, **58 eval cases**.
- Branch: `crop-choice`, cut from `main`. Do **not** build on `budget-and-crop-choice` — that branch carries `src/budget.py` and its five open Criticals, and nothing here needs it.

---

### Task 1: The context block

**Files:**
- Modify: `src/engine.py` (the `_context_block` function, currently at line 637)
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `src.context.location.extract_province(message, history) -> str | None`; `src.context.season.describe(d: date) -> str` (returns e.g. `"Ağustos ayı, yaz"`).
- Produces: a new branch inside the existing `_context_block(route, message, history, today)`. **Its signature does not change**, and a new module-level helper `_crop_choice_block(message, history, today) -> str`.

**Read `_context_block` before editing it.** It returns `""` for every route except `fert_plan`. You are adding one more branch; the `""` default for the remaining routes must survive, because `plant_info`, `nutrition`, `budget` and `offscope` all depend on it.

Note the deferred import already in that function: `src/context/location.py` imports `_normalize_tr` from `src/engine.py` at load time, so a top-level import of `src.context` in `engine.py` is a real cycle. Keep the import inside the function.

- [ ] **Step 1: Re-measure the dispatch condition FIRST**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_routing`

Expected: `crop_choice` appears in the `sevke uygun rotalar (sifir yanlis giris)` list, and accuracy reads `37/42 (88%)`.

**If `crop_choice` has gained a wrong entry, STOP and report BLOCKED.** The entire permission for this task rests on that number being zero. **If accuracy is no longer 37/42, STOP and report that too** — this plan does not touch the routing rules, so a changed number means something else moved.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_engine.py`. The file already imports `engine` and `date`; check the top of the file rather than adding duplicate imports.

```python
def test_crop_choice_block_names_the_factors_and_forbids_a_recommendation():
    out = engine._context_block(
        "crop_choice", "Manisa'dayım, bu yıl ne eksem?", None, date(2026, 8, 11))
    assert "Manisa" in out
    assert "toprak" in out and "sulama" in out and "munavebe" in out
    assert "ONERME" in out


def test_crop_choice_block_asks_for_the_province_when_missing():
    out = engine._context_block(
        "crop_choice", "Bu yıl ne eksem?", None, date(2026, 8, 11))
    assert "BILINMIYOR" in out
    # The factors are still explained without a province - an unknown location
    # costs one line, not the answer.
    assert "toprak" in out and "ONERME" in out


def test_crop_choice_block_carries_the_season():
    """The month comes from `today`, not from the clock, so this is stable."""
    out = engine._context_block(
        "crop_choice", "Manisa'dayım, bu yıl ne eksem?", None, date(2026, 8, 11))
    assert "Ağustos" in out


def test_a_crop_choice_failure_degrades_to_an_empty_block(monkeypatch):
    """Spec §8: a context failure must cost the situation lines, not the answer."""
    monkeypatch.setattr("src.context.season.describe",
                        lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    assert engine._context_block(
        "crop_choice", "Bu yıl ne eksem?", None, date(2026, 8, 11)) == ""


def test_crop_choice_never_gets_a_framing_sentence():
    """`crop_choice` has no reviewed programme behind it, so it gets no framing
    suffix. This passes today by virtue of the `route != "fert_plan"` guard; it is
    here so that adding a second framing route later cannot silently give this one
    a sentence it has no basis for."""
    assert engine._framing_suffix("crop_choice", "Bu yıl ne eksem?") == ""


def test_other_routes_still_get_an_empty_context_block():
    """The regression that matters: adding a branch must not disturb the default."""
    for route in ("plant_info", "nutrition", "budget", "offscope"):
        assert engine._context_block(
            route, "Bu yıl ne eksem?", None, date(2026, 8, 11)) == "", route
```

- [ ] **Step 3: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -k "crop_choice or other_routes_still" -v`

Expected: the four `_context_block` crop_choice tests FAIL with an assertion error on an empty string. `test_crop_choice_never_gets_a_framing_sentence` and `test_other_routes_still_get_an_empty_context_block` **PASS already** — that is correct and expected; they are regression pins, not red-first tests. Do not "fix" them to fail.

- [ ] **Step 4: Implement**

First fix the docstring, which this change makes untrue. `_context_block` currently opens with *"Situation lines for the fert_plan route: where, when, and what the weather is about to do. Empty string for every other route, so nothing else pays for it and nothing else changes."* Replace that first paragraph with:

```python
    """Route-specific situation lines. Empty string for the routes that have
    none, so they pay nothing and nothing about them changes.

    `fert_plan` gets where, when and what the weather is about to do.
    `crop_choice` gets where and when, plus the factors that decide what to
    plant - no weather, because the question spans a season rather than the
    next few days.
    """
```

Keep the two paragraphs that follow it (the one about weather being best-effort and the province being asked for rather than guessed) — they are still true of `fert_plan`, which is the only route that reads them.

Then change the guard and add the helper. Replace:

```python
    if route != "fert_plan":
        return ""

    # Deferred: src/context/location.py imports _normalize_tr from THIS module at
    # load time, so a top-level import here is a real cycle.
    from src.context import location, season, weather
```

with:

```python
    # Deferred: src/context/location.py imports _normalize_tr from THIS module at
    # load time, so a top-level import here is a real cycle.
    if route == "crop_choice":
        try:
            return _crop_choice_block(message, history, today)
        except Exception as exc:                      # noqa: BLE001
            # Spec §8: the situation lines are an enhancement. Losing them must
            # cost those lines and nothing else, so the answer still gets built
            # from the corpus exactly as it did before this route diverged.
            print(f"[engine] crop_choice context failed, continuing without it: {exc}")
            return ""

    if route != "fert_plan":
        return ""

    from src.context import location, season, weather
```

and add this function immediately after `_context_block` ends (before `_framing_suffix`):

```python
def _crop_choice_block(message: str, history: list[dict] | None,
                       today: date) -> str:
    """Situation lines for the crop-choice route: where, when, and the factors
    that actually decide what to plant.

    No module and no arithmetic - province and season come from context modules
    that already shipped, and the rest is prompt text.

    The prohibition on naming a crop is a PROMPT constraint, not something this
    code can enforce; spec §5 says so and the eval measures whether it holds.
    Enforcing it here would mean detecting "recommended a crop" in Turkish free
    text, which is the same problem the product-suppression backstop already
    finds hard.
    """
    from src.context import location, season

    lines = [f"Tarih: {season.describe(today)}."]
    province = location.extract_province(message, history)
    if province:
        lines.append(f"Kullanicinin ili: {province}.")
    else:
        lines.append("Kullanicinin ili BILINMIYOR - cevabinda hangi ilde "
                     "oldugunu sor.")
    lines.append("Bu bir urun secimi sorusu. Karari belirleyen faktorleri anlat "
                 "ve eksik olanlari sor: toprak yapisi ve analiz, sulama imkani, "
                 "arazi buyuklugu, onceki urun ve munavebe, pazara mesafe, "
                 "isgucu ve makine.")
    lines.append("BELIRLI BIR URUN ONERME. Kullanicinin kosullarini bilmeden "
                 "urun onermek bir sezonluk gecim karari hakkinda temelsiz "
                 "tavsiye olur.")
    return "\n".join(lines)
```

Note why the `try` wraps the whole helper rather than sitting inside it: `season.describe` and `extract_province` are the two things that can raise, and both are needed before the first line is built. Wrapping at the call site keeps the helper readable and gives one place where the degrade decision lives.

- [ ] **Step 5: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -v`

Expected: all pass, including every pre-existing test. **If a pre-existing test changes verdict, stop and report which** — do not adjust it.

- [ ] **Step 6: Run the whole suite**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`

Expected: all pass. The count was **471** before this task; report the new number (six tests added, so 477).

- [ ] **Step 7: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Give crop_choice the factors that decide what to plant"
```

---

### Task 2: Eval coverage, in the same change that makes the route diverge

**Files:**
- Modify: `evals/eval_set.py`
- Test: the eval harness itself is the test.

**Interfaces:**
- Consumes: nothing from Task 1's Python API; it exercises the whole answer path end to end, which is the point.
- Produces: one new case in `CASES`, taking the set from 58 to 59.

**Why this is not optional and not deferrable.** Plan 2 added a diverging route without adding cases, and the shield passed 55/55 while exercising the changed route **zero times**. A green shield that never touches the change is worse than no shield, because it reads as evidence.

- [ ] **Step 1: Add the case**

Append to the `CASES` list in `evals/eval_set.py`, before the closing `]`:

```python
    # ----------------------------------------------------------------- #
    # crop_choice - the route this plan makes diverge
    # ----------------------------------------------------------------- #
    # Anchors avoid month and season names: those come from date.today(), so an
    # anchor like "Ağustos" would be green today and red in December with nothing
    # about the product having changed. The province is safe - it comes from the
    # question.
    {"id": "crop_choice_gives_factors_not_a_recommendation",
     "category": "crop_choice",
     "query": "Manisa'dayım, bu yıl tarlama ne eksem iyi olur?",
     "retrieval": "any",
     "products": "any",
     "answer_any": ["toprak", "sulama", "münavebe", "pazar"],
     # The prohibition is a PROMPT constraint, not something code can enforce, so
     # it is measured here. A red on this case is a finding to report, not an
     # anchor to soften.
     "answer_none": ["şunu ekin", "bunu ekmenizi öneririm"]},
]
```

- [ ] **Step 2: Check the anchors cannot match inside longer words**

`_matches(term, text)` applies a LEFT word boundary and a trailing-digit guard, but no right boundary. Verify the new anchors behave:

```bash
PYTHONIOENCODING=utf-8 python -c "
from evals.run_eval import _matches
for term, text, want in [
    ('toprak', 'toprak analizi yaptirin', True),
    ('toprak', 'topraksiz tarim', True),
    ('sulama', 'sulama imkaniniz var mi', True),
    ('münavebe', 'münavebe planiniz', True),
    ('pazar', 'pazara mesafe', True),
    ('pazar', 'Pazartesi gunu', True),
]:
    got = _matches(term, text)
    print(('OK   ' if got == want else 'DIKKAT'), got, repr(term), '<-', text)
"
```

Expected: every line `OK`. Two of these are deliberately weak and expected `True`: `pazar` matches inside `Pazartesi`, and `toprak` inside `topraksiz`. **Report them, do not silently drop them** — `answer_any` is an *any* match over four terms, so a weak anchor lowers the case's power rather than making it wrong. If any line prints `DIKKAT`, the matcher's behaviour has changed since plan 2 and that is a finding.

- [ ] **Step 3: Confirm the case is wired**

Run: `PYTHONIOENCODING=utf-8 python -c "from evals.eval_set import CASES; print(len(CASES)); print([c['id'] for c in CASES if c['category'] == 'crop_choice'])"`

Expected: `59` and `['crop_choice_gives_factors_not_a_recommendation']`.

- [ ] **Step 4: Run the new case against a live model**

**This needs LM Studio running with the model loaded.** Healthy throughput is ~65 tok/s; a single case is ~20 s. If it takes minutes, the machine has the VRAM-spill fault — reboot rather than tuning anything (see the ops notes in memory), then re-run.

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --only crop_choice`

Expected: the case passes on all four dimensions. **If `answer_none` goes red, the model named a crop despite the prohibition. That is the finding spec §5 predicted — report it with the exact sentence it produced. Do not soften the anchor and do not add more prompt text to fight it in this task;** it is a measurement about prompt constraints, and changing the instrument to make it green is the failure mode this project has already recorded five times.

- [ ] **Step 5: Run the full shield**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval`

Expected: **59/59**, i.e. the 58 that passed before plus the new one. Budget 20-25 minutes.

**Any case that was green before and is red now is a regression caused by this plan** — the context block is the only thing that changed, and it only fires on one route. Report which case, do not adjust it.

- [ ] **Step 6: Commit**

```bash
git add evals/eval_set.py
git commit -m "Measure the crop_choice route the same change makes diverge"
```

---

### Task 3: Findings, and retire the superseded budget plan

**Files:**
- Create: `docs/superpowers/2026-08-13-crop-choice-findings.md`
- Modify: `docs/superpowers/plans/2026-08-11-budget-and-crop-choice.md`

**Interfaces:** none. This task is documentation, and it is the task that stops a future session from executing dead work.

- [ ] **Step 1: Write the findings document**

Create `docs/superpowers/2026-08-13-crop-choice-findings.md` with these sections, filled from what was actually measured — not from what this plan predicted:

- **What shipped** — the context block, the route it fires on, and the one thing it deliberately does not do (name a crop).
- **Numbers** — test count before and after; eval count before and after; the full-shield result; the routing accuracy re-measured in Task 1 Step 1.
- **Did the prohibition hold?** — the `answer_none` verdict from Task 2 Step 4, with the model's actual sentence quoted. If it held, say so and say that one green case is weak evidence for a prompt constraint, not proof. If it did not hold, this is the headline finding.
- **Weak anchors** — the `pazar`/`Pazartesi` and `toprak`/`topraksiz` matches from Task 2 Step 2, so the next person does not rediscover them.
- **What this route still cannot do** — it explains factors and asks questions; it has no soil, market-price or rotation data behind it, so it cannot rank options even when the user answers everything it asks. Say this plainly; it is the honest boundary of the feature.

- [ ] **Step 2: Mark the budget half superseded**

At the top of `docs/superpowers/plans/2026-08-11-budget-and-crop-choice.md`, immediately after the `# ...Implementation Plan` heading line, insert:

```markdown
> **SUPERSEDED — DO NOT EXECUTE TASKS 1, 2, 3 AND 5 (the `budget` half).**
> The extractor built in Tasks 1-2 came out of review with five Criticals, every
> one a demonstrated wrong money figure (e.g. `"5 dönümde 2 ton aldım, kilosu
> 10 TL, masrafım 5000 TL"` produced a 95,000 TL margin instead of 15,000). The
> root cause is the approach, not the patches: hand-curated Turkish token sets
> with ±2 windows cannot survive Turkish inflection, and each fix opened new
> holes across three rounds. The deciding number is that **six of the seven
> frozen budget questions contain no numbers at all**, so the extractor served
> one question in seven while carrying five silent wrong-money defects.
>
> `budget` waits for a new spec in which the numbers come from a **form**, not
> from parsing prose. That changes the interaction model, so it needs
> brainstorming → spec → plan, not an amendment to this document.
>
> **The `crop_choice` half was split out and executed** as
> `docs/superpowers/plans/2026-08-13-crop-choice.md`. Tasks 4 and 6 here are
> superseded by it; the code they describe lives there.
>
> `src/budget.py` and its tests remain on the `budget-and-crop-choice` branch,
> wired to nothing.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/2026-08-13-crop-choice-findings.md docs/superpowers/plans/2026-08-11-budget-and-crop-choice.md
git commit -m "Record what crop_choice measured and retire the budget plan"
```

---

## Exit gates

All three must be true before this branch merges:

1. `PYTHONIOENCODING=utf-8 python -m pytest -q` — all pass, count reported.
2. `PYTHONIOENCODING=utf-8 python -m evals.run_eval` — **59/59**, with any red reported as a finding rather than tuned away.
3. `PYTHONIOENCODING=utf-8 python -m evals.run_routing` — `crop_choice` still has zero wrong entries and accuracy still reads 37/42.

The routing gate itself (>= 90%) is **expected to stay FAILED** and does not block this plan. It fails because `plant_info` absorbs five cases, four of which produce identical output today. Reporting it as failed is the requirement; making it pass is not this plan's job.
