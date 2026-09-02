# Refusal Naming and Cache Fixture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the province-level refusals whose median is unbounded a reason that names what the gate actually found, and make `tests/test_norms.py`'s cache hygiene structural instead of accidental.

**Architecture:** Two unrelated repairs in one round. (A) `_province_area_never_orchard` stops returning `bool` and returns the reason string or `None`, the way `_density_verdict` beside it already does, so the call site can record `province_median_year_records_no_orchard` where the median is unbounded and keep `province_median_density_above_ceiling` where it is a real density above 444. (B) `tests/test_norms.py` gains an autouse fixture that clears `norms._load` after every test, and the two manual clears that have been protecting the file by accident are removed. Then the data file is regenerated — no served figure changes, only `meta`.

**Tech Stack:** Python 3.14, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-02-refusal-naming-and-cache-fixture-design.md`

## Global Constraints

- The new reason string is exactly `province_median_year_records_no_orchard`. The existing `province_median_density_above_ceiling` keeps its exact spelling.
- The cut is on the MEDIAN, not on the members: a province takes the new reason when `statistics.median(densities)` is `_UNBOUNDED_DENSITY`, whether or not it also recorded real orchard years.
- **No served figure may change.** The `crops` block of `data/crop_norms.json` must come out byte-identical; only `meta.refused_yield_cells` differs. Expected after the rebuild: 66.610 served cells and 1.714 refusal entries, both unchanged, split 191 new / 84 old.
- No new horticultural constant. `_MAX_TREES_PER_DA = 444`, `_MIN_TREES_PER_DA = 5`, `_MIN_PROVINCES_TO_JUDGE_A_CROP = 10`, `_MIN_YEARS_TO_JUDGE_A_PROVINCE = 3` all untouched.
- Refusals keep the existing shape `{"crop": <label>, "province": <name>, "year": <int>, "reason": <str>}`, and a province-level refusal keeps `year: 0`.
- Comments and docstrings in English, matching the file's style: they state the ARGUMENT, not the mechanics. **This project treats a comment that describes something the code does not do as a defect** — three were found and fixed on the previous branch.
- Commit messages: short, natural, English, no body, and **no `Co-Authored-By` trailer**.
- Do not touch `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.github/workflows/`, `mobile-app/eas.json`, `mobile-app/app.json`.
- Run pytest as `python -m pytest ...` from the repo root. Prefix any command that runs the builder with `PYTHONIOENCODING=utf-8` — it prints Turkish crop names and the Windows console default raises `UnicodeEncodeError` on `İ`.

## Files

- Modify: `scripts/build_crop_norms.py` — `_province_area_never_orchard` and its one call site in `build()`.
- Modify: `tests/test_build_crop_norms.py` — three new fixture tests.
- Modify: `tests/test_norms.py` — one autouse fixture, two deletions.
- Regenerate: `data/crop_norms.json` (Task 3 only).

## Orientation for every implementer

`scripts/build_crop_norms.py` runs OFFLINE by hand, about once a year, turning hand-obtained TÜİK CSV exports into `data/crop_norms.json` — the crop-yield norms the budget form prefills for a farmer.

A fruit yield is usually DERIVED as production ÷ area. `Üretim Miktarı` counts fruit from every tree in a province; `Toplu Meyveliklerin Alanı` counts COMPACT ORCHARDS only. Where a province's fruit comes from scattered trees the denominator is nearly empty and the derived yield is absurd. The script judges this by implied planting density — `(tons × 1000 ÷ kg_per_tree) ÷ dekar` — against one bound, `_MAX_TREES_PER_DA = 444`, at three granularities: one cell, one province's median year, one crop's median province. Everything refused is appended to a list called `refused`, which becomes `meta.refused_yield_cells` in the output.

A previous round made a year of ZERO recorded area enter the province median as `_UNBOUNDED_DENSITY = float("inf")`, on the argument that a zero area implies a density no bound can hold. That is why a median can now be unbounded, and why a reason saying "median density above ceiling" can be describing no density at all.

---

### Task 1: Name the refusal after what the median actually showed

**Files:**
- Modify: `scripts/build_crop_norms.py` — `_province_area_never_orchard` (ends around line 365) and its call site in `build()` (around line 532)
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Consumes: `_UNBOUNDED_DENSITY` and `_MAX_TREES_PER_DA`, both already defined near the top of the file.
- Produces: `_province_area_never_orchard(...) -> str | None` — the reason the province is refused, or `None` to keep it. Task 3 relies on the two reason strings it can return.

Today the function returns `bool` and the call site hard-codes one reason:

```python
    if len(densities) < _MIN_YEARS_TO_JUDGE_A_PROVINCE:
        return False
    return statistics.median(densities) > _MAX_TREES_PER_DA
```

```python
            no_orchard = bool(per_tree) and _province_area_never_orchard(
                province, published, uretim, alan, per_tree)
            if no_orchard:
                refused.append({"crop": labels[crop_id], "province": province,
                                "year": 0,
                                "reason": "province_median_density_above_ceiling"})
```

Measured on the shipped exports, those 275 entries split four ways: 63 all-finite with a median above 444, **132 where every member is unbounded**, **59 mixed where the median itself is unbounded**, and 21 mixed with a finite median above 444. The middle two — 191 entries — name a density that was never computed.

**A decision already taken, so you do not have to:** the function keeps its predicate-sounding name and returns `str | None`. `_density_verdict` in the same file has exactly this shape ("Why this derived cell must not be written, or None to write it"), and `if reason:` still reads as the predicate at the call site. Renaming would make several docstrings and two project memory files stale for a cosmetic gain.

- [ ] **Step 1: Write the failing tests**

Append these three to `tests/test_build_crop_norms.py`, directly after `test_the_province_refusal_is_recorded_once_under_its_own_reason`:

```python
def test_a_province_with_no_orchard_area_at_all_says_so():
    """Its judged years record no compact orchard in ANY of them, so no density
    was ever computed and the median is unbounded. Calling that "median density
    above ceiling" names a measurement that did not happen - 132 of the shipped
    file's 275 province entries are this shape, İncir (Yaş)/Düzce among them
    with ten zero-area years."""
    rows = []
    for year in (2016, 2017, 2018):
        rows += [R("Düzce", "İncir (Yaş)", year, "uretim", 100.0),
                 R("Düzce", "İncir (Yaş)", year, "alan", 0.0),
                 R("Düzce", "İncir (Yaş)", year, "verim_agac", 25.0)]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert [c["reason"] for c in record["cells"]] == [
        "province_median_year_records_no_orchard"]


def test_real_densities_do_not_save_a_province_whose_middle_year_has_none():
    """THE SHAPE A MEMBER-COUNTING RULE WOULD MISS, and the reason the cut is
    the MEDIAN. This province recorded a real orchard in two years - 200
    trees/da, well under the 444 ceiling, so those cells would have been served
    - and no orchard at all in three. Five members, the middle one unbounded.

    The verdict does not rest on the two real densities, so the reason must not
    claim it does. 59 of the shipped file's 275 entries are this shape."""
    rows = _years("İncir (Yaş)", "Kırklareli", [200, 200])
    for year in (2018, 2019, 2020):
        rows += [R("Kırklareli", "İncir (Yaş)", year, "uretim", 100.0),
                 R("Kırklareli", "İncir (Yaş)", year, "alan", 0.0),
                 R("Kırklareli", "İncir (Yaş)", year, "verim_agac", 25.0)]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert {c["reason"] for c in record["cells"]} == {
        "province_median_year_records_no_orchard"}


def test_a_finite_median_above_the_ceiling_keeps_the_density_reason():
    """THE BOUNDARY, in the direction that is easy to get wrong. Zero years are
    present, but four real densities of 1.500 trees/da outnumber the single
    zero, so the middle member IS a density and it IS above the ceiling. The
    old reason is the true one here and must survive. 21 of the shipped file's
    275 entries are this shape."""
    rows = _years("Ayva", "Karabük", [1500, 1500, 1500, 1500])
    rows += [R("Karabük", "Ayva", 2020, "uretim", 100.0),
             R("Karabük", "Ayva", 2020, "alan", 0.0),
             R("Karabük", "Ayva", 2020, "verim_agac", 25.0)]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    reasons = {c["reason"] for c in record["cells"]}
    assert "province_median_density_above_ceiling" in reasons
    assert "province_median_year_records_no_orchard" not in reasons
```

`_years(crop, province, densities, tons=100.0, per_tree=25.0, start=2016)` is an existing helper in that file: it emits one cell per year for one province at each chosen implied density, starting at 2016. Note its argument order is `(crop, province, ...)` while `R(...)` takes the province first — that is the file's existing convention, not a mistake.

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_build_crop_norms.py -q -k "no_orchard_area_at_all or middle_year_has_none or finite_median_above"`

Expected: the first two FAIL, the third PASSES.
- `test_a_province_with_no_orchard_area_at_all_says_so` — AssertionError comparing `['province_median_density_above_ceiling']` to `['province_median_year_records_no_orchard']`.
- `test_real_densities_do_not_save_a_province_whose_middle_year_has_none` — AssertionError on the set comparison, for the same reason. It may also carry `area_is_zero` entries; if the actual set differs from what you expect in any way other than the reason name, report exactly what you saw.
- `test_a_finite_median_above_the_ceiling_keeps_the_density_reason` — PASSES already. It is a guard on the name that must NOT move, not a TDD RED. Do not delete it and do not treat its passing as an error.

- [ ] **Step 3: Return the reason instead of a bool**

Replace the last three lines of `_province_area_never_orchard`:

```python
    if len(densities) < _MIN_YEARS_TO_JUDGE_A_PROVINCE:
        return False
    return statistics.median(densities) > _MAX_TREES_PER_DA
```

with:

```python
    if len(densities) < _MIN_YEARS_TO_JUDGE_A_PROVINCE:
        return None
    median = statistics.median(densities)
    if not median > _MAX_TREES_PER_DA:
        return None
    # WHICH REASON IS A QUESTION ABOUT THE MIDDLE, NOT ABOUT THE MEMBERS. An
    # unbounded median means no density sits where the verdict was read, so
    # calling it a density above the ceiling would name a measurement that did
    # not happen - true of a province with no orchard area in any judged year,
    # and equally of one whose real years are outnumbered by its zero ones.
    return ("province_median_year_records_no_orchard"
            if median == _UNBOUNDED_DENSITY
            else "province_median_density_above_ceiling")
```

Then change the signature line and the first line of the docstring:

```python
def _province_area_never_orchard(province: str, published: dict, uretim: dict,
                                 alan: dict, per_tree: dict) -> str | None:
    """Why THIS province's area column fails to record THIS crop's ground, or
    None when it does not fail.

    A reason rather than a flag, the same shape as `_density_verdict` above:
    the caller records what the median found, and the two answers are not the
    same finding.
```

Leave the rest of the docstring exactly as it is — its middle-granularity argument, the Erik/Tunceli and İncir/Karaman measurements, the Ayva/Karabük note and the `_MIN_YEARS_TO_JUDGE_A_PROVINCE` paragraph are all still true.

- [ ] **Step 4: Record whichever reason came back**

At the call site in `build()`, replace:

```python
            no_orchard = bool(per_tree) and _province_area_never_orchard(
                province, published, uretim, alan, per_tree)
            if no_orchard:
                refused.append({"crop": labels[crop_id], "province": province,
                                "year": 0,
                                "reason": "province_median_density_above_ceiling"})
```

with:

```python
            province_reason = (_province_area_never_orchard(
                province, published, uretim, alan, per_tree)
                if per_tree else None)
            no_orchard = province_reason is not None
            if no_orchard:
                refused.append({"crop": labels[crop_id], "province": province,
                                "year": 0, "reason": province_reason})
```

`no_orchard` is read further down the year loop, so it must stay a plain bool.

- [ ] **Step 5: Run the whole builder suite**

Run: `python -m pytest tests/test_build_crop_norms.py -q`

Expected: all pass except `test_the_shipped_file_is_what_the_builder_produces`, which goes red because the committed `data/crop_norms.json` still carries the old reason on 191 entries. That is planned and is fixed in Task 3. Do NOT regenerate the data file here.

Also confirm `test_the_province_refusal_is_recorded_once_under_its_own_reason` — an existing test asserting the OLD reason on an all-finite fixture — still passes. If it went red, the cut is wrong: it means a finite median is being given the new name. Report that rather than editing the test.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py
git commit -m "Name a province refusal after what its median actually showed"
```

---

### Task 2: Make the norms cache hygiene structural

**Files:**
- Modify: `tests/test_norms.py` — one new fixture, two deletions

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: nothing Task 3 relies on. This task is independent of the other two and can be reviewed on its own.

`norms._load` is `@lru_cache(maxsize=1)` — the only cache in `src/norms.py`. The `_write` helper at the top of `tests/test_norms.py` repoints `norms._PATH` at a temp file and clears the cache **on the way in and not on the way out**. `monkeypatch` restores `_PATH` at teardown; nothing restores the cache, so a one- or two-crop fixture table survives into whatever runs next.

**It does not leak today, and the reason is the finding.** Measured: after `tests/test_norms.py` the cache holds the real 246 crops. What keeps it clean is that the last `_write` test is followed by two real-data tests that call `norms._load.cache_clear()` **for their own purposes**. Reorder the file, or add one `_write` test below them, and the protection is gone. `tests/test_shipped_norms.py` exists as a separate file precisely because a real-data test among fixture tests *"would silently read the fixture and pass vacuously"* — its own words — and the same trap is live here, defused by an accident of ordering.

- [ ] **Step 1: Add the autouse fixture**

In `tests/test_norms.py`, directly after the `from src import norms` import and before the `_write` helper, add:

```python
@pytest.fixture(autouse=True)
def _clear_the_norms_cache():
    """`norms._load` is an lru_cache and `_write` below repoints `norms._PATH`
    at a temp file. monkeypatch puts the path back at teardown; it cannot put
    the cache back, so a two-crop fixture table would answer every later test
    in the process - in this file and in any file that runs after it.

    Until this fixture existed the file stayed clean by ACCIDENT: the last
    `_write` test happened to be followed by real-data tests that cleared the
    cache for their own reasons. Reordering the file was enough to break it.
    The shape here is `tests/test_crop_compare.py`'s, which has always cleared
    on both sides.
    """
    yield
    norms._load.cache_clear()
```

- [ ] **Step 2: Delete the two manual clears the fixture replaces**

In `test_the_shipped_file_still_carries_provincial_yields`, delete the line `norms._load.cache_clear()` — it is the first statement in the body.

In `test_the_shipped_file_keeps_the_two_tomatoes_apart`, delete the line `norms._load.cache_clear()` — likewise the first statement in the body.

Delete nothing else. `_write` keeps its clear on the way in, and `tests/test_shipped_norms.py` keeps its own clear — that file documents it as an instrument check, *"PROVE THE INSTRUMENT BEFORE TRUSTING IT"*, which is a different job.

- [ ] **Step 3: Run the file and then the whole suite**

Run: `python -m pytest tests/test_norms.py -q`

Expected: all pass.

Run: `python -m pytest -q`

Expected: everything passes except `test_the_shipped_file_is_what_the_builder_produces` if Task 1 has already landed on this branch. Report the counts.

- [ ] **Step 4: PIN THE FIXTURE BY MUTATION — this step is the point of the task**

A fixture that is merely present proves nothing. Temporarily delete the `norms._load.cache_clear()` line **after** the `yield` in `_clear_the_norms_cache`, leaving the fixture otherwise intact.

Run: `python -m pytest tests/test_norms.py -q`

Expected: FAIL. With both manual clears now gone, the two real-data tests read the one-crop fixture table left behind by the `_write` test above them. `test_the_shipped_file_still_carries_provincial_yields` should fail on `assert len(table) > 200`.

**Then restore the deleted line by hand** — `git checkout` would destroy the rest of your uncommitted work — and re-run to confirm the file is green again. Report both outputs verbatim.

**If nothing goes red, STOP and report it.** That result would mean the fixture pins nothing and the task has bought a comment instead of a guarantee. Do not adjust the fixture or the tests to manufacture a failure; report what you saw and what you think protects the file instead.

- [ ] **Step 5: Commit**

```bash
git add tests/test_norms.py
git commit -m "Clear the norms cache in a fixture instead of by accident"
```

---

### Task 3: Regenerate the shipped data file

**Files:**
- Regenerate: `data/crop_norms.json`

**Interfaces:**
- Consumes: the reason strings from Task 1.
- Produces: nothing further.

`test_the_shipped_file_is_what_the_builder_produces` rebuilds from the committed CSV exports and compares against the shipped file, so the file cannot lag the code. It has been red since Task 1.

**The binding claim of this whole round is that no served figure changes.** Task 1 renames a label; it must not move a single yield. Steps 2 and 3 are what turn that claim into evidence.

- [ ] **Step 1: Regenerate**

```bash
PYTHONIOENCODING=utf-8 python -m scripts.build_crop_norms
```

It prints one stderr line per refused cell — several thousand, which is normal — and finishes with a per-reason summary on stdout. **Record that summary verbatim in your report.**

- [ ] **Step 2: Check the reason counts**

Expected in the summary: `province_median_year_records_no_orchard` = **191** and `province_median_density_above_ceiling` = **84**. Every other reason unchanged from the committed file: `no_per_tree_figure` 328, `density_below_floor` 331, `shadowed_by_ceiling_refusal` 225, `density_above_ceiling` 137, `published_yield_is_zero` 268, `production_is_zero` 36, `area_is_zero` 110, `area_excludes_the_trees` 1, `crop_median_density_above_ceiling` 2, `area_is_not_field` 1. Total entries **1714**.

191 + 84 = 275, which is what the single old reason held. If the split differs, report both numbers and stop — a different split means the cut is not the one the spec describes.

- [ ] **Step 3: Prove no served figure moved**

This compares the rebuilt `crops` block against the one committed before this branch:

```bash
PYTHONIOENCODING=utf-8 python -c "import json, io, subprocess; new = json.load(io.open('data/crop_norms.json', encoding='utf-8')); old = json.loads(subprocess.run(['git','show','main:data/crop_norms.json'], capture_output=True, text=True, encoding='utf-8').stdout); print('crops identical:', new['crops'] == old['crops']); print('served:', sum(1 for c in new['crops'].values() for p, s in c['yield_kg_da'].items() if p not in ('scope','TR') for v in s if v is not None))"
```

Expected: `crops identical: True` and `served: 66610`.

If `crops identical` is False, STOP and report. It would mean the return-type change altered which provinces are refused, not merely what they are called — the one outcome this round must not have.

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest -q`

Expected: everything passes, 1033 or more depending on how many tests the earlier tasks added. Report the exact count.

- [ ] **Step 5: Commit**

```bash
git add data/crop_norms.json
git commit -m "Rebuild the norms file with the split province reason"
```
