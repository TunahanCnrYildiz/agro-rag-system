# Shipped-Norms Smoke Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin, against the real `data/crop_norms.json`, the four invariants that three code reviews established by hand and left only in review transcripts.

**Architecture:** One new test file that walks the shipped table once through both surfaces — `budget._yield_cell` and `crop_compare._figures` + `_crop_block` — and asserts on what it collects. It must live in its own file: `tests/test_crop_compare.py`'s autouse fixture repoints `norms._PATH` at a temp table, so a "real data" test placed there would silently read the fixture.

**Tech Stack:** Python 3.14, pytest. Tests only — no `src/` change, no data-file change.

**Spec:** `docs/superpowers/specs/2026-08-29-shipped-norms-smoke-design.md`

## THE TDD SHAPE OF THIS ROUND IS UNUSUAL — READ THIS FIRST

There is no production code to write. **Every test in this plan PASSES the moment it is written**, because the properties already hold. "Write a failing test first" cannot apply.

The substitute, and it is not optional: **each assertion must be proven to bite by mutation.** For every test you add, you will break the production code it watches, confirm the test goes red for the right reason, then revert. A characterization test nobody has seen fail is a test nobody knows anything about — and this project has been bitten five times in the last week by tests that could not tell a right implementation from a wrong one, twice by tests that passed vacuously against the code they were written for.

Every task below therefore reads: write the test → run it and expect PASS → mutate → observe RED → revert → observe GREEN → commit.

## Global Constraints

- Run every command from the repo root. `src/config.py` reads a RELATIVE `env_file=".env"`; running elsewhere silently loads a wrong `EMBEDDING_MODEL`.
- **This round adds tests only.** No file under `src/`, `scripts/`, `data/` or `mobile-app/` may be modified. Mutations are temporary and must be reverted before every commit.
- **The invariants are exact — zero mismatches, zero violations.** A tolerance on them would admit exactly the drift they exist to catch.
- **The counts are FLOORS, not measured values**, following `tests/test_build_crop_norms.py::test_the_shipped_file_still_carries_most_of_its_yields`, which says why: *"45.000 is a deliberate floor, not the measured count… an order-of-magnitude collapse trips it, normal year-to-year drift in the TÜİK exports does not."* `data/crop_norms.json` is rebuilt by hand about once a year, and a pinned exact count teaches whoever regenerates it to edit the number rather than read it.
- The far-below COUNT is not asserted at all, not even as a floor: it depends on a threshold documented as tuned and on which year is most recent. Its invariant is asserted instead.
- Comments and docstrings explain WHY, not what. Match the surrounding density and voice.
- Commit messages: short, natural, English, no `Co-Authored-By` trailer.
- `python -m pytest -q` must be green (**1005 tests** at plan time) before every commit.

---

### Task 1: the file, the sweep, and proof it reads the shipped data

**Files:**
- Create: `tests/test_shipped_norms.py`

**Interfaces:**
- Consumes: `norms.province_table(province)`, `norms.available_crops()`, `norms._PATH`, `norms._load`, `src.context.location.PROVINCES`.
- Produces: a module-level helper `_sweep()` returning a list of `Row` namedtuples, used by Task 2. Its fields are `label, province, value, card, block` — see the code.

- [ ] **Step 1: Write the file with its instrument guard**

Create `tests/test_shipped_norms.py`:

```python
"""Smoke tests over the REAL data/crop_norms.json.

Three code reviews established these properties by sweeping the shipped file
by hand and then left the evidence in review transcripts nobody re-reads. Every
other test of these two surfaces runs on a fixture, so a regression in any of
them would keep the whole suite green.

THIS FILE MUST STAY SEPARATE. tests/test_crop_compare.py has an autouse fixture
that writes a fixture table to a temp file and points norms._PATH at it; a "real
data" test placed there would silently read the fixture and pass vacuously.
"""
from collections import namedtuple

from src import budget, crop_compare, norms
from src.context.location import PROVINCES


Row = namedtuple("Row", "label province value card block")


def _sweep():
    """Every (crop, province) the shipped table serves, through BOTH surfaces.

    The comparison side goes through `_figures` + `_crop_block` rather than
    `render`, because `render` takes a TWO-crop answer: covering every row
    through it would mean building ~10.000 pairings and would say nothing extra.
    `_crop_block` is the function that produces one crop's lines; `render` only
    joins them and appends the closing sentences, which this file does not
    assert about.

    Measured at 0,15 s for 19.926 rows, so one sweep serves every test here.
    """
    latest = norms.latest_year()
    rows = []
    for province in PROVINCES:
        for row in norms.province_table(province):
            value = (row.yield_kg_tree if row.yield_kg_tree is not None
                     else row.yield_kg_da)
            rows.append(Row(
                label=row.label,
                province=province,
                value=value,
                card=budget._yield_cell(row),
                block=crop_compare._crop_block(
                    crop_compare._figures(row, latest)),
            ))
    return rows


def test_the_sweep_really_reads_the_shipped_file():
    """PROVE THE INSTRUMENT BEFORE TRUSTING IT. norms._load is an
    lru_cache(maxsize=1) and several test modules repoint norms._PATH at a temp
    table. Measured today: after tests/test_norms.py and
    tests/test_crop_compare.py both run, a fresh read still sees the real file -
    so there is no leak. That is one teardown away from being false, and a smoke
    test silently reading a fixture would pass vacuously while claiming to guard
    the shipped data.
    """
    norms._load.cache_clear()
    assert norms._PATH.name == "crop_norms.json"
    assert norms._PATH.is_file(), norms._PATH
    assert len(norms.available_crops()) > 200, len(norms.available_crops())
    assert len(PROVINCES) == 81, len(PROVINCES)


def test_the_sweep_covers_the_whole_table():
    """A sweep that quietly collected nothing would make every assertion in this
    file vacuously true."""
    rows = _sweep()
    assert len(rows) > 15000, len(rows)
    assert sum(1 for r in rows if r.card is not None) > 5000
```

- [ ] **Step 2: Run the tests and expect them to PASS**

Run: `python -m pytest tests/test_shipped_norms.py -q`
Expected: **2 passed.** This is correct, not a mistake — see the note at the top of this plan.

- [ ] **Step 3: Prove the instrument guard bites**

Temporarily add this at the top of `test_the_sweep_really_reads_the_shipped_file`, before the existing asserts, to simulate a leaked fixture path:

```python
    import json, tempfile, pathlib
    p = pathlib.Path(tempfile.mkdtemp()) / "crop_norms.json"
    p.write_text(json.dumps({"meta": {"years": [2025]}, "crops": {}}),
                 encoding="utf-8")
    norms._PATH = p
```

Run: `python -m pytest tests/test_shipped_norms.py -q -k reads_the_shipped_file`
Expected: **FAIL** on the crop count (`assert 0 > 200`).

Remove those five lines, re-run, confirm PASS. Then confirm `git status --short` shows only your new untracked file — if `src/norms.py` shows as modified you have edited the module rather than the test, and must revert it.

- [ ] **Step 4: Prove the coverage guard bites**

Temporarily change `_sweep`'s loop to `for province in list(PROVINCES)[:2]:`.

Run: `python -m pytest tests/test_shipped_norms.py -q -k covers_the_whole_table`
Expected: **FAIL** on the row count.

Revert, re-run, confirm PASS.

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: **1007 passed, 0 failed** (1005 plus your two).

- [ ] **Step 6: Commit**

```bash
git add tests/test_shipped_norms.py
git commit -m "Sweep the shipped norms file, and prove the sweep reads it"
```

---

### Task 2: the four invariants and the two floors

**Files:**
- Modify: `tests/test_shipped_norms.py`

**Interfaces:**
- Consumes: `_sweep()` and `Row(label, province, value, card, block)` from Task 1; `norms.far_below_recent(value)`, `budget.FAR_BELOW_CLAUSE`, `crop_compare.FAR_BELOW_NOTE`.
- Produces: nothing later depends on this.

Useful facts about the values you will assert on:
- `budget._yield_cell(row)` returns `None` or a dict with `"value"`, `"unit"`, `"note"`, `"recent"`. `"unit"` is `"kg_agac"` for a per-tree row and `"kg_da"` otherwise.
- `budget.FAR_BELOW_CLAUSE` is `" — {year} bunun çok altında"`.
- `crop_compare.FAR_BELOW_NOTE` is `"{year} bu aralığın çok altında; olağan bir yılın beklentisi değil."`
- `crop_compare._crop_block(...)` returns a list of strings. A block that prints a range has a line containing `"önceki 5 yıl"`.
- `norms.latest_year()` is `2025` on the current file.

- [ ] **Step 1: Write the tests**

Append to `tests/test_shipped_norms.py`:

```python
def test_both_surfaces_choose_the_same_measure_for_every_row():
    """They disagreed on 1.568 cells for a whole round: the form prefilled
    Karabük/Ayva at 31 kg/ağaç while the comparison printed 13.419 kg/da."""
    mismatched = [
        r.label for r in _sweep()
        if r.card is not None
        and (r.card["unit"] == "kg_agac") != ("kg/ağaç" in r.block[0])
    ]
    assert mismatched == [], mismatched[:10]


def test_no_per_tree_row_prints_a_per_dekar_unit_anywhere():
    """The derived kg/da for a tree crop divides a province's whole production
    by the few dekars of COMPACT orchard it records. It still exists in the data
    file; no surface may show it."""
    leaked = [
        (r.label, r.province) for r in _sweep()
        if r.card is not None and r.card["unit"] == "kg_agac"
        and ("kg/da" in " ".join(r.block) or "kg/da" in (r.card["recent"] or ""))
    ]
    assert leaked == [], leaked[:10]


def test_both_surfaces_reach_the_same_far_below_verdict():
    """One predicate, two callers. Checked only where the comparison prints a
    range at all - its `missing` branches print none, and by the design's own
    rule they carry no warning either."""
    disagreed = []
    for r in _sweep():
        if r.card is None or not any("önceki 5 yıl" in ln for ln in r.block):
            continue
        on_card = "çok altında" in (r.card["recent"] or "")
        in_block = any(
            crop_compare.FAR_BELOW_NOTE.format(year=r.value.year) in ln
            for ln in r.block)
        if on_card != in_block:
            disagreed.append((r.label, r.province))
    assert disagreed == [], disagreed[:10]


def test_no_warned_cell_sits_at_or_above_its_own_range_minimum():
    """The sentence says the figure is far below the range printed beside it.
    Before this was fixed, six cells were warned while sitting ON their range's
    minimum - K.Maraş/Fındık served 1 under a printed range of 1-12."""
    violations = [
        (r.label, r.province, r.value.amount, r.value.recent_min)
        for r in _sweep()
        if norms.far_below_recent(r.value)
        and (r.value.recent_min is None or r.value.amount >= r.value.recent_min)
    ]
    assert violations == [], violations[:10]


def test_the_file_still_serves_most_of_its_yields():
    """FLOORS, not the measured counts. Measured today: 2.097 cells served
    per tree and 6.177 served per dekar. The floors sit at roughly two thirds, the same
    reasoning tests/test_build_crop_norms.py already uses: an order-of-magnitude
    collapse trips them, normal year-to-year drift in the TÜİK exports does not.
    A pinned exact count would go red on every yearly regeneration and teach
    whoever regenerates it to edit the number rather than read it.
    """
    rows = _sweep()
    per_tree = sum(1 for r in rows
                   if r.card is not None and r.card["unit"] == "kg_agac")
    per_dekar = sum(1 for r in rows
                    if r.card is not None and r.card["unit"] == "kg_da")
    assert per_tree > 1400, per_tree
    assert per_dekar > 4000, per_dekar
```

- [ ] **Step 2: Run them and expect them to PASS**

Run: `python -m pytest tests/test_shipped_norms.py -q`
Expected: **7 passed.** Correct, not a mistake.

- [ ] **Step 3: Prove each invariant bites — one mutation at a time**

Apply each mutation, run the named test, confirm it goes RED, then revert and confirm GREEN before the next. Record all four observations in your report.

**(a) Measure agreement.** In `src/crop_compare.py`'s `_figures`, change `per_tree = row.yield_kg_tree is not None` to `per_tree = False`.
Run: `python -m pytest tests/test_shipped_norms.py -q -k same_measure`
Expected: FAIL, listing tree crops.

**(b) No per-dekar unit on a per-tree row.** In `src/budget.py`'s `_yield_cell`, change the per-tree branch to build its cell with `*_NORM_UNITS["yield"]` instead of `*_NORM_UNITS["yield_tree"]`.
Run: `python -m pytest tests/test_shipped_norms.py -q -k per_dekar_unit`
Expected: FAIL.

**(c) Far-below agreement.** In `src/budget.py`'s `_yield_cell`, delete the two lines that append `FAR_BELOW_CLAUSE`.
Run: `python -m pytest tests/test_shipped_norms.py -q -k same_far_below_verdict`
Expected: FAIL.

**(d) The range-minimum invariant.** In `src/norms.py`'s `far_below_recent`, drop the `value.amount < value.recent_min` conjunct, leaving the midpoint test alone.
Run: `python -m pytest tests/test_shipped_norms.py -q -k range_minimum`
Expected: FAIL, listing about six cells.

**If any mutation leaves its test green, stop and report it** — that assertion is not watching what its name claims.

The two FLOORS are not mutation-tested: they are collapse guards, and the only way to trip one is to break the data file, which is out of scope for this round. Say so in your report rather than inventing a mutation for them.

- [ ] **Step 4: Confirm the tree is clean and the suite is green**

Run: `git status --short`
Expected: only `tests/test_shipped_norms.py`. If any file under `src/` shows as modified, a mutation was not reverted — revert it before continuing.

Run: `python -m pytest -q`
Expected: **1012 passed, 0 failed** (1005 plus seven).

- [ ] **Step 5: Commit**

```bash
git add tests/test_shipped_norms.py
git commit -m "Pin the shipped file's cross-surface invariants"
```

---

## Self-Review

**Spec coverage:**

| spec requirement | task |
|---|---|
| separate file, because of the autouse fixture trap | 1 (module docstring records why) |
| prove the instrument reads the shipped file before asserting | 1 |
| one sweep, not one per assertion | 1 (`_sweep`) |
| comparison exercised via `_figures` + `_crop_block`, not `render` | 1 (`_sweep`, with the reason) |
| both surfaces choose the same measure | 2 |
| both surfaces reach the same far-below verdict, where a range is printed | 2 |
| no per-tree cell renders `kg/da` on either surface | 2 |
| no warned cell at or above its `recent_min` | 2 |
| counts as floors with the precedent's reasoning | 2 |
| the far-below count is not asserted at all | 2 — no test references it |
| tests only, no `src/` change | Global Constraints, and Task 2 Step 4 checks it |

No gaps.

**Placeholder scan:** every code step carries the actual code; every run step carries the actual command and its expected result. No TBD, no "add appropriate assertions", no "similar to Task N".

**Type consistency:** `Row(label, province, value, card, block)` is defined in Task 1 and every field is used in Task 2 exactly as named. `_sweep()` is defined once and called in both tasks. `budget.FAR_BELOW_CLAUSE` and `crop_compare.FAR_BELOW_NOTE` are quoted from the current source, not recalled.

**Every assertion in this plan was RUN against the real data before the plan was
committed**, not reasoned about: 19.926 rows, 8.274 cards, **zero** measure mismatches,
**zero** per-tree rows leaking `kg/da`, **zero** far-below disagreements, **zero** cells
warned at or above their range minimum, no empty `_crop_block` result. That run also
corrected a number in this plan's own first draft — the per-dekar floor was based on 7.745,
the count of rows CARRYING a provincial `kg/da` value, where the card actually serves 6.177
because per-tree takes precedence. This plan's predicted values have been wrong four times
in recent rounds; these were measured.

**Three risks worth naming:**

1. **Every test here passes on arrival**, so the usual RED gate is absent. The mutation steps ARE the gate; a task whose mutations were skipped has proven nothing. Both tasks make this explicit rather than leaving it to judgement.
2. **The mutations edit `src/`, which the Global Constraints forbid changing.** They are temporary by construction, and Task 2 Step 4 checks `git status` before the commit for exactly this reason.
3. **`test_both_surfaces_choose_the_same_measure_for_every_row` reads `r.block[0]`.** That is the crop's first line, which every `_crop_block` branch emits; a block is never empty. If a future branch returned `[]` the test would raise `IndexError` rather than fail cleanly — noted so a reviewer can judge whether that matters.
