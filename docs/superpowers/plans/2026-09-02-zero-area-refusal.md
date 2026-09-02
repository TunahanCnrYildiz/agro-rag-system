# Zero-Area Refusal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the crop-norms builder record the cells it drops in silence, and treat a zero recorded orchard area as the ceiling refusal it already is.

**Architecture:** Everything happens in `scripts/build_crop_norms.py`, an offline script that turns hand-obtained TÜİK CSV exports into `data/crop_norms.json`. Four changes: the derived-yield call site inside `build()` records three refusals it currently drops silently; `_ceiling_shadow` counts a zero-area year among the years that condemn earlier cells; `_province_area_never_orchard` counts zero-area years in its median while `_area_never_orchard` deliberately does not. Then the data file is regenerated.

**Tech Stack:** Python 3.14, pytest. No new dependencies. The whole change is pure functions over in-memory rows plus one regenerated JSON file.

**Spec:** `docs/superpowers/specs/2026-09-02-zero-area-refusal-design.md`

## Global Constraints

- Reason strings are exactly `area_is_zero`, `published_yield_is_zero`, `production_is_zero`. Cells condemned by a zero-area year keep the **existing** reason `shadowed_by_ceiling_refusal` — no second shadow reason is introduced.
- A cell with production 0 against area 0 records **nothing** and casts **no shadow**. No figure was discarded there.
- `area_is_zero` is recorded regardless of whether the crop publishes a per-tree yield. The shadow, which lives inside the existing `if per_tree` branch, stays tree-crop-only.
- `_area_never_orchard` (the CROP median) must **not** take zero-area years. `_province_area_never_orchard` (the PROVINCE median) must.
- No new horticultural constant. `_MAX_TREES_PER_DA = 444` and `_MIN_TREES_PER_DA = 5` are unchanged, and nothing new is tuned against the data.
- Every refusal appended to `refused` uses the existing shape: `{"crop": <label>, "province": <name>, "year": <int>, "reason": <str>}`.
- Comments and docstrings are in English and match the surrounding file's style: they state the ARGUMENT, not the mechanics.
- Commit messages: short, natural, English, no body unless it earns one, and **no `Co-Authored-By` trailer**.
- Do not touch `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.github/workflows/`, `mobile-app/eas.json` or `mobile-app/app.json`.

## Files

- Modify: `scripts/build_crop_norms.py` — the builder. All logic changes.
- Modify: `tests/test_build_crop_norms.py` — fixture tests, appended near the tests they belong beside.
- Regenerate: `data/crop_norms.json` — the shipped data file (Task 5 only).

## Orientation for every implementer

`build()` walks each crop, then each province, then each year. A yield is either PUBLISHED by TÜİK (`verim`, Kg/Dekar) or DERIVED from a production/area pair (`uretim` tons ÷ `alan` dekars). Fruit crops also publish a per-tree yield (`verim_agac`), which is used only as EVIDENCE for the density gates and never written as a yield.

The gates, from narrow to wide:
- `_density_verdict(tons, dekar, per_tree)` — one cell. Refuses above 444 trees/dekar or below 5.
- `_ceiling_shadow(...)` — the latest year a province is refused above the ceiling; every EARLIER derived cell there is refused too.
- `_province_area_never_orchard(...)` — this province's median year is past the ceiling.
- `_area_never_orchard(...)` — this crop's median province is past the ceiling.

Everything refused is appended to a list called `refused`, which becomes `meta.refused_yield_cells` in the output: `{"counts": {reason: n}, "cells": [...]}`. That record is the file's only way to distinguish "this province grows none of this crop" from "we threw the figure out".

Run the tests with:

```bash
python -m pytest tests/test_build_crop_norms.py -q
```

---

### Task 1: Record `area_is_zero`

**Files:**
- Modify: `scripts/build_crop_norms.py:486-494` (inside `build()`, the derived-yield branch)
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the reason string `"area_is_zero"`, used by Task 3's tests and Task 4's behaviour.

Today the derived branch reads:

```python
                    tons = uretim.get(province, {}).get(year)
                    dekar = alan.get(province, {}).get(year)
                    if no_orchard:
                        continue          # already refused, once, above
                    if tons is not None and dekar:
```

`dekar` is tested for TRUTH, so a recorded area of exactly 0 falls through with no verdict formed and no trace left. Measured on the committed exports: 1.674 cells.

- [ ] **Step 1: Write the failing tests**

Append these three to `tests/test_build_crop_norms.py`, directly after `test_a_tree_crop_cell_with_no_per_tree_figure_is_refused`:

```python
def test_a_zero_area_cell_is_refused_under_its_own_reason():
    """Zerdali in Afyonkarahisar 2019-2024: the province books 322 tons of fruit
    against ZERO dekars of compact orchard. No division can be performed, so no
    yield was ever written - but nothing said so, and the file could not tell
    this from a province that grows no wild apricot at all."""
    rows = [
        R("Afyonkarahisar", "Zerdali", 2024, "uretim", 322.0),
        R("Afyonkarahisar", "Zerdali", 2024, "alan", 0.0),
        R("Afyonkarahisar", "Zerdali", 2024, "verim_agac", 42.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert {"crop": "Zerdali", "province": "Afyonkarahisar", "year": 2024,
            "reason": "area_is_zero"} in record["cells"]


def test_a_zero_area_is_refused_on_a_crop_with_no_per_tree_figure_too():
    """Every zero-area cell in today's exports belongs to a tree crop, so this
    is the case the data does not currently carry. It is pinned anyway: the
    refusal is that nothing can be divided by zero, which is as true of a
    vegetable's `Ekilen Alan` as of an orchard's `Toplu Meyveliklerin Alani`.
    A future export must not fall back into silence."""
    rows = [
        R("Sivas", "Marul (Göbekli)", 2025, "uretim", 12.0),
        R("Sivas", "Marul (Göbekli)", 2025, "alan", 0.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert [c["reason"] for c in record["cells"]] == ["area_is_zero"]


def test_a_zero_area_with_nothing_grown_against_it_records_nothing():
    """A GUARD, NOT A NEW BEHAVIOUR - it passes before this change and must keep
    passing after it. Production 0 over area 0 is not a refusal: no figure was
    discarded, the province simply grew none of the crop that year. The record
    is a record of what was thrown out, and an entry here would say the
    opposite of the truth."""
    rows = [
        R("Kastamonu", "Limon Ve Misket Limonu", 2024, "uretim", 0.0),
        R("Kastamonu", "Limon Ve Misket Limonu", 2024, "alan", 0.0),
        R("Kastamonu", "Limon Ve Misket Limonu", 2024, "verim_agac", 30.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert record["cells"] == []
```

- [ ] **Step 2: Run them to see which fail**

Run: `python -m pytest tests/test_build_crop_norms.py -q -k "zero_area"`

Expected: the first two FAIL, the third PASSES.
- `test_a_zero_area_cell_is_refused_under_its_own_reason` — AssertionError; `record["cells"]` is `[]`, so the dict is not in it.
- `test_a_zero_area_is_refused_on_a_crop_with_no_per_tree_figure_too` — AssertionError comparing `[]` to `['area_is_zero']`.
- `test_a_zero_area_with_nothing_grown_against_it_records_nothing` — PASSES. It is deliberately a guard on behaviour that must not change. Do NOT "fix" it, and do not delete it.

If the third one fails, stop and report — the fixture is wrong, not the code.

- [ ] **Step 3: Record the refusal**

In `scripts/build_crop_norms.py`, inside `build()`, insert the new block between the `if no_orchard: continue` line and the `if tons is not None and dekar:` line:

```python
                    if no_orchard:
                        continue          # already refused, once, above
                    if tons and dekar == 0:
                        # THE CEILING'S OWN FINDING AT ITS LIMIT. The province
                        # books fruit from scattered trees against a compact
                        # orchard's dekars, and here those dekars reached zero:
                        # the implied density is past every bound rather than
                        # merely past 444. The cell was already dropped - by the
                        # truthiness of `dekar` on the next line, which forms no
                        # verdict and leaves no trace.
                        #
                        # Recorded whether or not the crop publishes a per-tree
                        # figure: the refusal is that nothing can be divided by
                        # zero, which is as true of a vegetable's `Ekilen Alan`.
                        # Today every such cell is a tree crop, so this costs
                        # nothing and closes the hole a future export would fall
                        # into.
                        refused.append({"crop": labels[crop_id],
                                        "province": province,
                                        "year": year,
                                        "reason": "area_is_zero"})
                        continue
                    if tons is not None and dekar:
```

Note the guard is `tons and dekar == 0`, not `tons is not None and dekar == 0`: a production of zero against a zero area discarded nothing, and the third test above pins that.

- [ ] **Step 4: Run the full builder suite**

Run: `python -m pytest tests/test_build_crop_norms.py -q`

Expected: all pass, including the three above. `test_the_shipped_file_is_what_the_builder_produces` will FAIL — that is expected and is fixed in Task 5, which regenerates the file. Report it in your report as a known, planned failure; do not regenerate the data file in this task.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py
git commit -m "Record the cells whose area is zero"
```

---

### Task 2: Record the two zero-value refusals

**Files:**
- Modify: `scripts/build_crop_norms.py:485-520` (the same year loop inside `build()`)
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Consumes: the `refused.append({...})` shape and the `area_is_zero` guard added in Task 1 — leave that guard where it is.
- Produces: the reason strings `"published_yield_is_zero"` and `"production_is_zero"`.

Two more drops leave no trace. A published `Verim` of exactly 0 (268 cells) and a derived yield of exactly 0,0 from a zero production against a recorded area (36 cells) both fall through `if value:` at the bottom of the loop. The comment there already argues WHY they are refused; neither ever reaches the record.

A tree crop's zero production is already caught upstream as `density_below_floor` (0 trees/dekar is under the floor of 5), so `production_is_zero` reaches only crops with no per-tree figure.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build_crop_norms.py`, after the tests added in Task 1:

```python
def test_a_published_yield_of_zero_is_refused_and_recorded():
    """TUIK publishes a Verim of exactly 0 in 268 cells. It has always been
    refused - prefilling 0 would tell a farmer to expect no harvest and compute
    an income of zero - but the refusal left no trace, so the committed file
    could not tell it from a province that grows none of the crop."""
    rows = [
        R("Ordu", "Bakla, Kuru (İnsan Tüketimi İçin)", 2016, "verim", 0.0),
        R("Ordu", "Bakla, Kuru (İnsan Tüketimi İçin)", 2017, "verim", 145.0),
    ]
    out = bcn.build(rows)
    record = out["meta"]["refused_yield_cells"]
    assert {"crop": "Bakla, Kuru (İnsan Tüketimi İçin)", "province": "Ordu",
            "year": 2016,
            "reason": "published_yield_is_zero"} in record["cells"]
    assert out["crops"]["bakla, kuru (insan tuketimi icin)"] \
              ["yield_kg_da"]["Ordu"] == [None, 145.0]


def test_a_zero_production_against_a_recorded_area_is_refused_and_recorded():
    """Two dekars sown, nothing off them: the derived yield is 0,0 and has
    always been dropped. A TREE crop's zero production is already caught one
    step earlier as `density_below_floor` - 0 trees/dekar is under the floor of
    5 - so this reason reaches only the crops with no per-tree figure to judge
    with, which is where the 36 measured cells sit."""
    rows = [
        R("Sivas", "Marul (Göbekli)", 2025, "uretim", 0.0),
        R("Sivas", "Marul (Göbekli)", 2025, "alan", 2.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert [c["reason"] for c in record["cells"]] == ["production_is_zero"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_build_crop_norms.py -q -k "zero_and_recorded or published_yield_of_zero"`

Expected: both FAIL with AssertionError — `record["cells"]` is `[]` in each, so neither the membership check nor the `== ['production_is_zero']` comparison holds.

- [ ] **Step 3: Record the published zero**

In `build()`, the year loop currently opens:

```python
            for year, i in index.items():
                value = published.get(province, {}).get(year)
                if value is None:
```

Insert the new branch between those last two lines:

```python
            for year, i in index.items():
                value = published.get(province, {}).get(year)
                if value == 0:
                    # TUIK published a yield of exactly zero. Refused for the
                    # reason argued at `if value` below - a true zero and a
                    # missing marker are indistinguishable here, and neither
                    # reading is a norm - and recorded, so the file does not
                    # present a discarded figure as a crop nobody grows.
                    refused.append({"crop": labels[crop_id],
                                    "province": province, "year": year,
                                    "reason": "published_yield_is_zero"})
                    continue
                if value is None:
```

- [ ] **Step 4: Record the derived zero**

At the bottom of the same loop, the code reads:

```python
                if value:
                    # `if value` and not `is not None`: a yield of exactly 0 is
                    # refused. The exports carry zeros in 0.4-12% of cells and
```

Change the first comment line and add the `elif`. The block becomes:

```python
                if value:
                    # `if value` and not `is not None`: a yield of exactly 0 is
                    # refused, and the `elif` below records it. The exports
                    # carry zeros in 0.4-12% of cells and there is no way to
                    # tell a true zero from a missing marker - but neither
                    # reading is a norm. Prefilling 0 would tell a farmer to
                    # expect no harvest and compute an income of zero, which is
                    # the confident-wrong-answer this whole route exists to
                    # prevent. No norm is the honest outcome.
                    #
                    # One decimal: a derived yield is tonnes over dekars, both
                    # already rounded at the source, so thirteen significant
                    # digits would advertise a precision nobody has.
                    series[i] = round(value, _DECIMALS["verim"])
                elif value is not None:
                    # A derived 0,0: an area is recorded and nothing came off
                    # it. A tree crop never arrives here - `density_below_floor`
                    # takes it one step earlier - so this is the field and
                    # vegetable case, where no per-tree figure exists to judge
                    # with. `value is not None` keeps the genuinely absent cell
                    # silent: nothing was thrown out there.
                    refused.append({"crop": labels[crop_id],
                                    "province": province, "year": year,
                                    "reason": "production_is_zero"})
```

- [ ] **Step 5: Run the full builder suite**

Run: `python -m pytest tests/test_build_crop_norms.py -q`

Expected: all pass except `test_the_shipped_file_is_what_the_builder_produces`, which stays red until Task 5. Report it as the known planned failure.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py
git commit -m "Record the two zero-valued yield refusals"
```

---

### Task 3: A zero area casts a shadow

**Files:**
- Modify: `scripts/build_crop_norms.py` — the whole of `_ceiling_shadow`, including its docstring
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Consumes: `area_is_zero` from Task 1 — the counts assertion in the second test below expects that reason to be present.
- Produces: no new names. Shadowed cells keep `shadowed_by_ceiling_refusal`.

`_ceiling_shadow` returns the LATEST year a province is refused above the ceiling; every earlier derived cell there is then refused as `shadowed_by_ceiling_refusal`. A zero-area year currently cannot enter that collection, because the comprehension filters on `and alan.get(province, {}).get(year)` — truthiness again — and because `_density_verdict` would divide by zero.

This is what leaves Zerdali/Afyonkarahisar serving 12.179 kg/da: 2017 and 2018 sit at 309 and 297 trees/dekar, under the 444 ceiling, so the cell gate passes them, and the six zero years that follow cannot reach back.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build_crop_norms.py`, directly after `test_a_passing_year_sandwiched_between_refusals_is_shadowed`:

```python
def test_a_cell_older_than_a_zero_area_year_is_shadowed_too():
    """A zero recorded orchard makes the ceiling's own statement in the
    strongest terms available: the recorded area is not the ground the
    production came off. That is how the province keeps its books, not what the
    weather did, so it condemns the earlier derived cells exactly as a ceiling
    refusal does.

    Zerdali in Afyonkarahisar, from the real exports: 2018 is 341 tons over 28
    dekars at 41 kg per tree - 297 trees/da, under the 444 ceiling, so the cell
    gate passes it and norms._pick serves it as 12.179 kg/da. 2019 books 322
    tons against zero dekars."""
    rows = [
        R("Afyonkarahisar", "Zerdali", 2018, "uretim", 341.0),
        R("Afyonkarahisar", "Zerdali", 2018, "alan", 28.0),
        R("Afyonkarahisar", "Zerdali", 2018, "verim_agac", 41.0),
        R("Afyonkarahisar", "Zerdali", 2019, "uretim", 322.0),
        R("Afyonkarahisar", "Zerdali", 2019, "alan", 0.0),
        R("Afyonkarahisar", "Zerdali", 2019, "verim_agac", 42.0),
    ]
    out = bcn.build(rows)
    assert "Afyonkarahisar" not in out["crops"]["zerdali"]["yield_kg_da"]


def test_the_zero_area_shadow_carries_the_reason_that_already_exists():
    """A zero area is treated as a ceiling refusal throughout, so the cells it
    condemns carry the existing reason. A second shadow reason would name a
    second concept, and there is only one."""
    rows = [
        R("Afyonkarahisar", "Zerdali", 2018, "uretim", 341.0),
        R("Afyonkarahisar", "Zerdali", 2018, "alan", 28.0),
        R("Afyonkarahisar", "Zerdali", 2018, "verim_agac", 41.0),
        R("Afyonkarahisar", "Zerdali", 2019, "uretim", 322.0),
        R("Afyonkarahisar", "Zerdali", 2019, "alan", 0.0),
        R("Afyonkarahisar", "Zerdali", 2019, "verim_agac", 42.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert record["counts"] == {"area_is_zero": 1,
                                "shadowed_by_ceiling_refusal": 1}


def test_a_zero_area_with_no_production_casts_no_shadow():
    """A GUARD - it passes before this change and must keep passing after it.
    Both figures at zero make no claim about the denominator: the province grew
    none of the crop that year. Only a zero area that production was booked
    against says the area column is wrong, so only that one reaches backwards."""
    rows = [
        R("Tokat", "Ayva", 2024, "uretim", 182.0),
        R("Tokat", "Ayva", 2024, "alan", 155.0),
        R("Tokat", "Ayva", 2024, "verim_agac", 31.0),
        R("Tokat", "Ayva", 2025, "uretim", 0.0),
        R("Tokat", "Ayva", 2025, "alan", 0.0),
        R("Tokat", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_da"]["Tokat"] == [1174.2, None]
```

- [ ] **Step 2: Run them to see which fail**

Run: `python -m pytest tests/test_build_crop_norms.py -q -k "zero_area_year or zero_area_shadow or no_production_casts"`

Expected: the first two FAIL, the third PASSES.
- `test_a_cell_older_than_a_zero_area_year_is_shadowed_too` — AssertionError: `"Afyonkarahisar"` IS in the yields, because 2018 is still served at 12178.6.
- `test_the_zero_area_shadow_carries_the_reason_that_already_exists` — AssertionError: counts are `{'area_is_zero': 1}` with no shadow entry.
- `test_a_zero_area_with_no_production_casts_no_shadow` — PASSES, and must keep passing.

- [ ] **Step 3: Let a zero-area year cast the shadow**

Replace the body of `_ceiling_shadow` (the list comprehension and the `return`) with:

```python
    refused = []
    for year in years:
        if published.get(province, {}).get(year) is not None:
            continue
        tons = uretim.get(province, {}).get(year)
        dekar = alan.get(province, {}).get(year)
        if tons is None:
            continue
        if dekar == 0:
            # A zero recorded area cannot be divided into, so no verdict is
            # computed - but the statement it makes is the ceiling's, at its
            # limit. Only when production was booked AGAINST it: production and
            # area both at zero say the province grew none that year, which is
            # a claim about the crop and not about the area column.
            if tons:
                refused.append(year)
        elif dekar and _density_verdict(
                tons, dekar, per_tree.get(province, {}).get(year)
        ) == "density_above_ceiling":
            refused.append(year)
    return max(refused, default=None)
```

- [ ] **Step 4: Update the docstring's own account of itself**

`_ceiling_shadow`'s docstring contains this paragraph, which is now wrong as written:

```
    Only `density_above_ceiling` casts a shadow. `no_per_tree_figure` means
    TUIK has not published that year's per-tree survey yet - half of those sit
    in the freshest year for exactly that reason - and says nothing about the
    denominator. `density_below_floor` understates rather than inflates.
```

Replace that paragraph with:

```
    `density_above_ceiling` casts a shadow, and so does a zero recorded area -
    the same statement with the denominator gone entirely. The others do not:
    `no_per_tree_figure` means TUIK has not published that year's per-tree
    survey yet - half of those sit in the freshest year for exactly that reason
    - and says nothing about the denominator. `density_below_floor` understates
    rather than inflates. An area of zero with no production booked against it
    says the province grew none of the crop, which is not a claim about the
    area column either.
```

Leave the rest of the docstring alone; the Turunç and Dut examples in it are still true.

- [ ] **Step 5: Run the full builder suite**

Run: `python -m pytest tests/test_build_crop_norms.py -q`

Expected: all pass except `test_the_shipped_file_is_what_the_builder_produces`.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py
git commit -m "A zero recorded area condemns the earlier cells too"
```

---

### Task 4: Zero years in the province median, never in the crop median

**Files:**
- Modify: `scripts/build_crop_norms.py` — a new module constant beside `_MIN_TREES_PER_DA`, the body of `_province_area_never_orchard`, and a note in `_area_never_orchard`'s docstring
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: the module constant `_UNBOUNDED_DENSITY`.

`_province_area_never_orchard` asks whether THIS province's area column fails to record THIS crop's ground; a year of zero recorded orchard is the most extreme possible answer, so it belongs in that median. `_area_never_orchard` asks whether the column fails the crop ANYWHERE, and its own docstring states the intent that forbids the zeros there: *"a handful of scattered-tree provinces costs those cells and never the crop - apple is recorded properly nearly everywhere and must survive whole."*

Measured: with the zeros in both medians, 338 served cells fall and among them is the whole of Muşmula/Bursa — 24 to 63 trees per dekar, an area growing smoothly from 127 to 1.389 dekars, not one zero year of its own. With the zeros in the province median only, 74 cells fall and Bursa survives whole.

- [ ] **Step 1: Write the tests**

Append to `tests/test_build_crop_norms.py`, after `test_a_province_recorded_in_too_few_years_is_not_judged_as_a_province`:

```python
def test_zero_years_push_a_province_past_the_ceiling():
    """A year of zero recorded orchard is the most extreme answer there is to
    the question this rule asks, so it enters the median as an unbounded
    density. The median RANKS rather than averages, so an unbounded member
    needs no arithmetic performed on it.

    Elma (Amasya) in Karaman is the cell this is for: 2016-2020 recorded at zero
    area, then 2021-2024 carrying 11.615 to 12.769 kg/da off 11 to 13 dekars at
    155-223 trees/da. The cell gate passes that spacing, and the shadow cannot
    reach those years because every zero year precedes them. Only this rule
    can."""
    rows = []
    for year in (2016, 2017, 2018):
        rows += [R("Karaman", "Elma (Amasya)", year, "uretim", 100.0),
                 R("Karaman", "Elma (Amasya)", year, "alan", 0.0),
                 R("Karaman", "Elma (Amasya)", year, "verim_agac", 25.0)]
    # 100 t at 25 kg/tree is 4.000 trees; over 20 dekars that is 200 trees/da,
    # under the 444 ceiling, and these years are LATER than every zero year.
    for year in (2019, 2020, 2021):
        rows += [R("Karaman", "Elma (Amasya)", year, "uretim", 100.0),
                 R("Karaman", "Elma (Amasya)", year, "alan", 20.0),
                 R("Karaman", "Elma (Amasya)", year, "verim_agac", 25.0)]
    out = bcn.build(rows)
    assert _provinces_served(out, "elma (amasya)") == []


def test_zero_years_do_not_push_a_crop_past_the_ceiling():
    """THE MISTAKE THIS SPLIT EXISTS TO PREVENT, and it is a guard: it passes
    before the change above and must keep passing after it.

    `_area_never_orchard` states its own intent - a handful of scattered-tree
    provinces costs those cells and never the crop. Measured with the zeros in
    the crop median too, 338 served cells fell and among them was the whole of
    Musmula/Bursa: 24 to 63 trees per dekar, an area growing smoothly from 127
    to 1.389 dekars, not one zero year of its own, destroyed by OTHER provinces'
    zeros. That is precisely the failure the median was chosen to avoid.

    Ten zero-area provinces is deliberate: it is the number
    `_MIN_PROVINCES_TO_JUDGE_A_CROP` needs before the crop rule will judge at
    all, so if the zeros ever enter this median they arrive with enough weight
    to act."""
    sound = "Bursa"
    rows = []
    for province in [p for p in bcn.PROVINCES if p != sound][:10]:
        rows += [R(province, "Muşmula", 2025, "uretim", 100.0),
                 R(province, "Muşmula", 2025, "alan", 0.0),
                 R(province, "Muşmula", 2025, "verim_agac", 25.0)]
    # 4.000 trees over 100 dekars is 40 trees/da - a 5m x 5m orchard, exactly
    # what the denominator claims to be.
    rows += [R(sound, "Muşmula", 2025, "uretim", 100.0),
             R(sound, "Muşmula", 2025, "alan", 100.0),
             R(sound, "Muşmula", 2025, "verim_agac", 25.0)]
    out = bcn.build(rows)
    assert _provinces_served(out, "musmula") == [sound]
```

- [ ] **Step 2: Run them to see which fails**

Run: `python -m pytest tests/test_build_crop_norms.py -q -k "push_a_province or push_a_crop"`

Expected: the first FAILS, the second PASSES.
- `test_zero_years_push_a_province_past_the_ceiling` — AssertionError comparing `['Karaman']` to `[]`. Today only the three sound years enter the median, so it is 200 trees/da and the province is not refused.
- `test_zero_years_do_not_push_a_crop_past_the_ceiling` — PASSES. It is a guard on a mistake the next step must not make; Step 5 proves it can fail.

- [ ] **Step 3: Name the density a zero area implies**

In `scripts/build_crop_norms.py`, directly below the `_MIN_TREES_PER_DA = 5` line, add:

```python
# A zero recorded area implies a density no bound can hold. It enters the
# PROVINCE median as this and never the CROP median - see both docstrings for
# why the same figure belongs in one and not the other. A median ranks rather
# than averages, so an unbounded member is a legitimate one: nothing is
# computed with it, it is only placed.
_UNBOUNDED_DENSITY = float("inf")
```

- [ ] **Step 4: Take zero years into the province median**

`_province_area_never_orchard` currently collects its densities like this:

```python
    densities = []
    for year, tons in uretim.get(province, {}).items():
        dekar = alan.get(province, {}).get(year)
        tree = per_tree.get(province, {}).get(year)
        if (tons and dekar and tree
                and published.get(province, {}).get(year) is None):
            densities.append((tons * 1000.0 / tree) / dekar)
```

Replace that loop with:

```python
    densities = []
    for year, tons in uretim.get(province, {}).items():
        dekar = alan.get(province, {}).get(year)
        tree = per_tree.get(province, {}).get(year)
        if not (tons and tree
                and published.get(province, {}).get(year) is None):
            continue
        if dekar == 0:
            densities.append(_UNBOUNDED_DENSITY)
        elif dekar:
            densities.append((tons * 1000.0 / tree) / dekar)
```

`dekar` may be None as well as 0; `dekar == 0` is False for None and `elif dekar` skips it, so a missing area still contributes nothing.

Then add this paragraph to the end of `_province_area_never_orchard`'s docstring, before the closing `"""`:

```
    A YEAR OF ZERO RECORDED AREA COUNTS, as an unbounded density. It is the
    most extreme possible answer to the question this rule asks, and leaving it
    out let a province book six consecutive years of fruit against no orchard
    at all and still be judged sound on the three years that carried an area.
```

- [ ] **Step 5: Prove the crop-median guard can fail**

The second test in Step 1 passes both before and after this change, so pin it by mutation rather than by trusting it.

Temporarily edit `_area_never_orchard`'s collection loop so a zero area contributes `_UNBOUNDED_DENSITY` there too — the same shape you just wrote into `_province_area_never_orchard`.

Run: `python -m pytest tests/test_build_crop_norms.py -q -k "push_a_crop"`

Expected: it now FAILS, comparing `[]` to `['Bursa']` — the zeros of ten other provinces have destroyed a province that records its orchards properly.

**Now revert that temporary edit** (`git checkout` is not safe here — you have uncommitted work; undo it by hand) and re-run the same command to confirm it passes again. Report both outputs.

- [ ] **Step 6: Write down why the crop median refuses the zeros**

Add this paragraph to the end of `_area_never_orchard`'s docstring, before the closing `"""`:

```
    A YEAR OF ZERO RECORDED AREA DOES NOT COUNT HERE, though it does in
    `_province_area_never_orchard`. The two rules ask different questions. That
    one asks whether a province records this crop's ground, and a zero answers
    it. This one asks whether the COLUMN describes the crop anywhere, and
    zeros concentrated in scattered-tree provinces answer a question about those
    provinces. Measured: counting them here removes 338 served cells including
    the whole of Musmula/Bursa - 24 to 63 trees/da, an area growing smoothly
    from 127 to 1.389 dekars, not one zero year of its own - which is exactly
    the "apple must survive whole" failure the median was chosen to prevent.
```

- [ ] **Step 7: Run the full builder suite**

Run: `python -m pytest tests/test_build_crop_norms.py -q`

Expected: all pass except `test_the_shipped_file_is_what_the_builder_produces`.

- [ ] **Step 8: Commit**

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py
git commit -m "Count zero-area years in the province median, not the crop one"
```

---

### Task 5: Regenerate the shipped data file

**Files:**
- Regenerate: `data/crop_norms.json`
- Test: the whole suite

**Interfaces:**
- Consumes: every change from Tasks 1-4.
- Produces: nothing further tasks rely on.

`test_the_shipped_file_is_what_the_builder_produces` rebuilds from the committed CSV exports and compares against the shipped file, so the data file cannot lag the code. It has been red since Task 1; this task is what makes it green.

- [ ] **Step 1: Regenerate**

Run:

```bash
PYTHONIOENCODING=utf-8 python -m scripts.build_crop_norms
```

The `PYTHONIOENCODING` is not optional on this machine: the script prints Turkish crop names and the Windows console default raises `UnicodeEncodeError` on `İ`.

It prints one stderr line per refused cell (now several thousand) and finishes with a summary of counts per reason on stdout. **Record that summary in your report** — the per-reason counts are the deliverable of this task as much as the file is.

- [ ] **Step 2: Check the counts against what the spec predicted**

The spec predicts, from the measured exports:

- `area_is_zero` around 1.674, reduced by the cells that a province-wide refusal now swallows instead
- `published_yield_is_zero` = 268
- `production_is_zero` = 36

Report the real numbers. If `published_yield_is_zero` or `production_is_zero` differ from 268 and 36 at all, stop and report — those two touch no gate and their counts are arithmetic, so a difference means something else changed. `area_is_zero` differing is expected and fine.

- [ ] **Step 3: Verify the served-cell count**

Run:

```bash
PYTHONIOENCODING=utf-8 python -c "import json, io; d = json.load(io.open('data/crop_norms.json', encoding='utf-8')); print(sum(1 for c in d['crops'].values() for p, s in c['yield_kg_da'].items() if p not in ('scope', 'TR') for v in s if v is not None))"
```

Expected: **66610**. The spec measured 66.836 before the change and 66.610 after.

That prediction comes from a standalone reimplementation of `build()`'s loop written during design, not from the real function, so treat it as a strong expectation rather than an assertion. Report the number you get. A difference of a few dozen is information worth reporting and no reason to stop; a difference in the hundreds means one of the four changes does not do what the spec describes — stop and report rather than adjusting anything to reach the number.

- [ ] **Step 4: Run the whole suite, not just this file**

Run: `python -m pytest -q`

Expected: everything passes, including `test_the_shipped_file_is_what_the_builder_produces`, `test_the_shipped_file_still_carries_most_of_its_yields` (floor 45.000, and 66.610 clears it), `test_the_shipped_file_carries_no_cell_the_gate_should_have_refused`, and the `tests/test_norms.py` suite that reads the same file. Report the total count.

- [ ] **Step 5: Commit**

```bash
git add data/crop_norms.json
git commit -m "Rebuild the norms file with the zero-area refusals"
```
