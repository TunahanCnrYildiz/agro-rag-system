# Fruit Yield Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `data/crop_norms.json` from serving a fruit "yield" that is a province's whole production divided by a few dekars of compact orchard — refuse those cells at build time and report every one by name.

**Architecture:** All of it lands in `scripts/build_crop_norms.py`, the offline converter. It learns to read TÜİK's per-tree yield (which it currently throws away at the unit gate) and uses it **only as evidence**: for every fruit cell it is about to derive, it computes the tree density the three published numbers imply and refuses the cell when that density is impossible. A small committed review file carries the crops whose recorded area is not field area at all. `src/norms.py`, the wire, the budget form and the mobile client are untouched.

**Tech Stack:** Python 3.14 + pytest. No new dependencies, no network.

Spec: `docs/superpowers/specs/2026-08-25-fruit-yield-gate-design.md`
Branch point: `fruit-yield-gate` at `d985c4a`, `pytest -q` = **830 passed**.

## Global Constraints

- **A refused cell is ABSENT — never zero, never a neighbour's figure.** A zero reaches a farmer as "this crop earns nothing"; another province's figure is a different claim entirely.
- **The per-tree figure is read as evidence and NEVER written as a yield.** Converting it to per-dekar needs a planting density TÜİK does not publish here, and authoring one would invent the very number this work removes.
- **A published figure always beats a derived one.** Unchanged: the 20 fruit crops that publish `Kg/Dekar` never reach the derivation path and must not be touched.
- **The gate applies ONLY to tree crops.** Vegetables derive from `ekilen alan`, which genuinely is the whole crop's sown area. A gate that touched them would delete every vegetable yield in the file. This is the single most dangerous mistake available in this plan.
- **Every refusal is visible**: printed to the console during the build, and recorded in the committed file's `meta`.
- **The band is 444 and 5 implied trees/dekar**, and it is argued, not discovered — the distribution is unimodal with no natural cut. 444 trees/da is a 1,5 m × 1,5 m grid; a fruit tree does not stand at that spacing.
- `data/crop_norms.json` is a GENERATED artifact: reproducible by re-running the committed builder over the committed exports. Hand-editing it is a defect.
- **Run everything from the repo root** — `src/config.py` reads a relative `.env`.
- Commits: one per task, English, short and natural, **no `Co-Authored-By` trailer**.
- `pytest -q` green at the end of every task, starting from 830 passed.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `scripts/build_crop_norms.py` | **Modify.** Read the per-tree measure; gate derived tree-crop cells; honour the review file; report refusals. |
| `data/crop_area_review.json` | **Create.** Hand-reviewed: crops whose recorded area is not field area, with the evidence. |
| `data/crop_norms.json` | **Regenerate.** Loses ~10% of derived fruit cells; gains a refusal record in `meta`. |
| `tests/test_build_crop_norms.py` | **Modify.** The gate's both ends, the vegetable guard, the review file, the real-data guards. |

---

## Task 1: Read the per-tree yield instead of discarding it

Today `parse_label` returns `None` for every `Kg/Meyve Veren Ağaç` row, so those figures never enter the builder. The gate needs them. They come in under **their own measure name**, so no code path can mistake one for a per-dekar yield.

**Files:**
- Modify: `scripts/build_crop_norms.py` (module docstring, `_UNITS`, `parse_label`)
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Produces: `parse_label(label, olcum="")` returns `("verim_agac", name, unit)` for a per-tree yield row; `Row(province, crop, year, "verim_agac", value)` reaches `build()`. `build()`'s output is unchanged by this task.

- [ ] **Step 1: Check what the folded unit string actually is**

The routing below keys on the folded unit. Confirm it rather than assuming:

```bash
PYTHONIOENCODING=utf-8 python -c "from src.engine import _normalize_tr; print(repr(_normalize_tr('Kg/Meyve Veren Ağaç')))"
```

Expected: `'kg/meyve veren agac'`. If it differs, use what it prints — verbatim — as the `_UNITS["verim_agac"]` entry, and say so in your report.

- [ ] **Step 2: Write the failing tests**

In `tests/test_build_crop_norms.py`, **replace** `test_a_per_tree_yield_is_refused` with the two tests below. Its binding claim — a per-tree figure never becomes a per-dekar yield — is not dropped; it moves to `build()`, where the damage would actually happen:

```python
def test_a_per_tree_yield_is_read_under_its_own_measure():
    """TÜİK publishes orchard fruit yield ONLY as Kg/Meyve Veren Ağaç. It is
    read - the density gate needs it as evidence - but under a measure name of
    its own, so no code path can mistake it for a per-dekar figure."""
    assert bcn.parse_label(
        "Verim ve 01.24.10.00.00. (Elma) - Kg/Meyve Veren Ağaç") == (
        "verim_agac", "Elma", "Kg/Meyve Veren Ağaç")


def test_a_per_tree_yield_never_becomes_a_yield():
    """Written into a per-dekar field an apple would read 80 instead of ~2500 -
    silently wrong by more than an order of magnitude. Evidence only."""
    rows = [R("Manisa", "Elma", 2025, "verim_agac", 80.0)]
    out = bcn.build(rows)
    assert out["crops"]["elma"]["yield_kg_da"] == {"scope": "tr", "TR": [None]}


def test_a_per_dekar_verim_is_still_read_as_a_yield():
    """The routing must not swallow the unit it was always meant to accept."""
    assert bcn.parse_label(
        "Verim ve 01.11.11.00.00. (Durum Buğdayı) - Kg/Dekar") == (
        "verim", "Durum Buğdayı", "Kg/Dekar")
```

- [ ] **Step 3: Run them and watch them fail**

Run: `python -m pytest tests/test_build_crop_norms.py -q`
Expected: FAIL — `parse_label` returns `None` where the first test expects a tuple.

- [ ] **Step 4: Route the per-tree unit to its own measure**

In `scripts/build_crop_norms.py`, replace the `_UNITS` block and its comment with:

```python
# The unit each measure must carry to be usable. Fruit `Verim` comes in TWO
# units: Kg/Dekar for vines, berries and herbs, and Kg/Meyve Veren Agac for
# every orchard tree - TUIK publishes NO per-dekar yield for apple, walnut,
# citrus, quince and the rest. The per-tree figure is read under `verim_agac`,
# a measure of its own: build() uses it as EVIDENCE for the density gate and
# never writes it as a yield, because scaling it to a dekar needs a planting
# density nobody published.
_UNITS = {"verim": {"kg/dekar"}, "verim_agac": {"kg/meyve veren agac"},
          "alan": {"dekar"}, "uretim": {"ton"},
          "fiyat": {"kilogram"}}
```

Then, in `parse_label`, replace the unit check at the end of the function:

```python
    unit = (m.group("unit") or "").strip()
    folded = _normalize_tr(unit)
    # A `Verim` row in the per-tree unit is not an unusable row - it is a
    # different measure wearing the same label, and the gate in build() cannot
    # run without it.
    if measure == "verim" and folded in _UNITS["verim_agac"]:
        measure = "verim_agac"
    if folded not in _UNITS[measure]:
        return None
    return measure, m.group("name").strip(), unit
```

- [ ] **Step 5: Correct the module docstring's false premise**

The premise at the top of the file is what allowed the silent fallback. In the module docstring, replace:

```
  - Tahıllar and Meyveler publish `Verim` directly, in Kg/Dekar.
  - Sebzeler publish no Verim at all: only `Üretim Miktarı` (Ton) and
    `Ekilen Alan` (Dekar), so the yield is DERIVED from the pair.
```

with:

```
  - Tahıllar publish `Verim` directly, in Kg/Dekar.
  - Meyveler publish `Verim` too, but almost all of it is Kg/Meyve Veren AGAC -
    per TREE, not per dekar. Measured 2026-08-25: 61 of the 81 fruit crops in
    these exports publish only the per-tree figure, and 20 (vines, berries,
    herbs) publish Kg/Dekar. So most fruit yield is DERIVED, like a vegetable's.
  - Sebzeler publish no Verim at all: only `Üretim Miktarı` (Ton) and
    `Ekilen Alan` (Dekar), so the yield is DERIVED from the pair.
THE TWO DERIVATIONS ARE NOT EQUALLY SAFE, which is why build() gates one of
them. A vegetable's denominator is `Ekilen Alan` - the whole crop's sown area.
A fruit's is `Toplu Meyveliklerin Alani` - COMPACT ORCHARDS ONLY - while its
numerator counts fruit from every tree in the province, scattered ones
included. Where a fruit is grown as scattered trees the denominator is nearly
empty: Turunc in Adana 2025 is 2.439 tons over 2 dekars, which divides out to
1.219.500 kg/da.
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_build_crop_norms.py -q`
Expected: PASS.

Then the whole suite: `python -m pytest -q`
Expected: 830 passed + the two net-new tests. Nothing else may change — this task alters no output.

- [ ] **Step 7: Prove the output really is unchanged**

Run:

```bash
python -m scripts.build_crop_norms && git status --short data/crop_norms.json
```

Expected: the only difference is `meta.generated` (today's date). Confirm with `git diff --stat data/crop_norms.json` that no crop's series moved; if anything else changed, stop — the routing leaked a per-tree figure into a yield.

Then restore the file so the next task starts clean: `git checkout data/crop_norms.json`

- [ ] **Step 8: Commit**

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py && git commit -m "Read the per-tree yield as evidence, not as a yield"
```

---

## Task 2: Refuse the derived cells whose implied tree density is impossible

**Files:**
- Modify: `scripts/build_crop_norms.py` (`build`, plus two module constants and one helper)
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Consumes: `Row(..., "verim_agac", ...)` from Task 1.
- Produces: `_density_verdict(tons: float, dekar: float, per_tree: float | None) -> str | None` returning `None` (write the cell) or one of `"no_per_tree_figure"`, `"density_above_ceiling"`, `"density_below_floor"`. `build()` collects refusals into a list of `{"crop": str, "province": str, "year": int, "reason": str}` — Task 4 puts that list in `meta`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build_crop_norms.py`:

```python
def test_a_tree_crop_cell_inside_the_band_is_written_unchanged():
    """Ayva in Tokat 2025: 182 tons over 155 dekars, 31 kg per tree. That is
    (182000/31)/155 = 38 trees/da - a 5m x 5m orchard, exactly what the
    denominator claims to be. The gate must not touch a figure it accepts."""
    rows = [
        R("Tokat", "Ayva", 2025, "uretim", 182.0),
        R("Tokat", "Ayva", 2025, "alan", 155.0),
        R("Tokat", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_da"]["Tokat"] == [1174.2]


def test_a_cell_whose_area_cannot_hold_its_trees_is_refused():
    """Ayva in Ordu 2025: 267 tons over 3 dekars, 31 kg per tree. That implies
    (267000/31)/3 = 2871 trees on one dekar - 0,35 m2 each. The area is not the
    ground the production came from, so 89.000 kg/da is not a yield."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert "Ordu" not in out["crops"]["ayva"]["yield_kg_da"]


def test_a_cell_with_an_area_but_almost_no_production_is_refused():
    """The mirror error: 6 tons over 766 dekars at 27 kg per tree is 0,3
    trees/da - an orchard planted but not yet bearing. It understates the yield
    instead of inflating it, which is safer and still wrong in a revenue line."""
    rows = [
        R("Adana", "Avokado", 2021, "uretim", 6.0),
        R("Adana", "Avokado", 2021, "alan", 766.0),
        R("Adana", "Avokado", 2021, "verim_agac", 27.0),
    ]
    out = bcn.build(rows)
    assert "Adana" not in out["crops"]["avokado"]["yield_kg_da"]


def test_a_tree_crop_cell_with_no_per_tree_figure_is_refused():
    """The crop publishes per-tree yields elsewhere, so it IS a tree crop and
    this cell should have been judged - but this province-year carries no
    figure to judge it with. An unjudged cell and a judged one must not be
    indistinguishable in the output."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Tokat", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert "Ordu" not in out["crops"]["ayva"]["yield_kg_da"]


def test_a_vegetable_is_never_gated():
    """THE MOST DANGEROUS MISTAKE THIS GATE CAN MAKE. Vegetables publish no
    per-tree yield anywhere, and their denominator - Ekilen Alan - really is the
    whole crop's sown area. A gate that judged them would find no evidence and
    delete every vegetable yield in the file. 300 tons over 1 dekar is a strange
    tomato figure, and it still ships, because nothing here can judge it."""
    rows = [
        R("Manisa", "Domates", 2025, "uretim", 300.0),
        R("Manisa", "Domates", 2025, "alan", 1.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["domates"]["yield_kg_da"]["Manisa"] == [300000.0]


def test_a_published_per_dekar_yield_is_never_gated():
    """A published figure beats a derived one, so the gate never runs on it -
    even for a crop that also publishes a per-tree figure."""
    rows = [
        R("Ordu", "Ayva", 2025, "verim", 1200.0),
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    out = bcn.build(rows)
    assert out["crops"]["ayva"]["yield_kg_da"]["Ordu"] == [1200.0]


def test_the_verdict_names_which_bound_was_crossed():
    """The report has to say WHY, and the three reasons are not interchangeable:
    two are impossible figures, one is an unjudgeable one."""
    assert bcn._density_verdict(267.0, 3.0, 31.0) == "density_above_ceiling"
    assert bcn._density_verdict(6.0, 766.0, 27.0) == "density_below_floor"
    assert bcn._density_verdict(267.0, 3.0, None) == "no_per_tree_figure"
    assert bcn._density_verdict(182.0, 155.0, 31.0) is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_build_crop_norms.py -q`
Expected: FAIL — `AttributeError: module 'scripts.build_crop_norms' has no attribute '_density_verdict'`, and the refusal tests fail because every cell is still written.

- [ ] **Step 3: Add the constants and the verdict helper**

In `scripts/build_crop_norms.py`, add above `def build(`:

```python
# THE BAND IS ARGUED, NOT DISCOVERED. Measured over the 16.392 derived fruit
# cells, the implied density is unimodal - median 40 trees/da, which is a
# 5m x 5m orchard grid - with a long, smoothly decaying tail and NO natural cut
# to read a threshold off. So the bounds rest on geometry, not on horticultural
# judgement nobody here has:
#   444 trees/da is a 1,5m x 1,5m grid, 2,25 m2 of ground per tree. A
#   fruit-bearing tree does not stand at that spacing, so the recorded area
#   cannot be the ground the production came from.
#   Below 5 trees/da the area is recorded and almost nothing comes off it - an
#   orchard not yet in bearing. That understates the yield rather than inflating
#   it: safer, still wrong in a revenue line.
# THIS RAISES THE FLOOR ON WRONGNESS, IT DOES NOT REMOVE IT. A mulberry cell
# implying 200 trees/da is still mostly scattered trees and still passes.
_MAX_TREES_PER_DA = 444
_MIN_TREES_PER_DA = 5


def _density_verdict(tons: float, dekar: float,
                     per_tree: float | None) -> str | None:
    """Why this derived cell must not be written, or None to write it.

    All three numbers are TUIK's own. Nothing is assumed about the crop.
    """
    if not per_tree:
        # This crop publishes per-tree yields, so the cell SHOULD have been
        # judged - this province-year simply carries nothing to judge it with.
        # Refused rather than written unchecked: an unjudged figure and a judged
        # one must not look the same in the output.
        return "no_per_tree_figure"
    trees_per_da = (tons * 1000.0 / per_tree) / dekar
    if trees_per_da > _MAX_TREES_PER_DA:
        return "density_above_ceiling"
    if trees_per_da < _MIN_TREES_PER_DA:
        return "density_below_floor"
    return None
```

- [ ] **Step 4: Run the gate inside `build`**

In `build()`, immediately after `rows = list(rows)` near the top, add:

```python
    refused: list[dict] = []
```

Inside the `for crop_id, by_measure in seen.items():` loop, after the three existing `published` / `uretim` / `alan` lines, add:

```python
        # A tree crop is one TUIK publishes a per-tree yield for ANYWHERE. That
        # is a property of the CROP, not of the cell, and it is what says "this
        # crop's area column is Toplu Meyveliklerin Alani". Vegetables never
        # publish one, so the gate below cannot touch them - and must not:
        # their denominator really is the whole crop's sown area.
        per_tree = by_measure.get("verim_agac", {})
```

Then replace the derivation block inside the year loop with:

```python
                if value is None:
                    # Vegetables publish no Verim, and most fruits publish only
                    # a per-tree one; derive from the pair, and only where BOTH
                    # halves exist. Ton -> kg is the 1000.
                    tons = uretim.get(province, {}).get(year)
                    dekar = alan.get(province, {}).get(year)
                    if tons is not None and dekar:
                        reason = (_density_verdict(
                                      tons, dekar,
                                      per_tree.get(province, {}).get(year))
                                  if per_tree else None)
                        if reason is not None:
                            refused.append({"crop": labels[crop_id],
                                            "province": province,
                                            "year": year,
                                            "reason": reason})
                            continue
                        value = tons * 1000.0 / dekar
```

Finally, so the list is stable across runs (the committed file must be reproducible byte for byte), sort it just before `build` returns — put this immediately above the `return {"meta": ...}` statement:

```python
    refused.sort(key=lambda r: (r["crop"], r["province"], r["year"]))
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_build_crop_norms.py -q`
Expected: PASS, including every pre-existing test in the file. If `test_vegetable_yield_is_derived_from_production_and_area` or `test_a_published_verim_wins_over_a_derivable_one` broke, the gate is running where it must not.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py && git commit -m "Refuse a fruit cell whose area cannot hold the trees behind its production"
```

---

## Task 3: The reviewed list of crops whose area is not field area

Mushroom reaches no gate: it comes through the vegetable path, has no tree data, and its `ekilen alan` is the footprint of a building whose beds are stacked in tiers — Ordu 2025 is 179 t ÷ **1 da** = 179.000 kg/da, and it tops the yield × price ranking of every province measured. No arithmetic over the published numbers can see this; it is knowledge about what the area MEANS. So it is reviewed by a person and committed, exactly as `data/dose_group_scope.json` was.

**Files:**
- Create: `data/crop_area_review.json`
- Modify: `scripts/build_crop_norms.py` (`build` signature, `main`)
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Produces: `build(rows, not_field_area=())` — `not_field_area` is an iterable of crop **display labels**; `build` folds them with `_normalize_tr` itself. Existing callers that pass one argument keep working. `REVIEW = DATA_DIR / "crop_area_review.json"`.

- [ ] **Step 1: Confirm the numbers before writing the review**

This step is the review. Run it and read the output:

```bash
PYTHONIOENCODING=utf-8 python -c "import sys; sys.path.insert(0,'.'); import scripts.build_crop_norms as b; from src.config import DATA_DIR; [print(r.province, r.measure, r.value) for f in ('sebze-uretim-2016-2025.csv','sebze-alan-2016-2025.csv') for r in b.read_export(DATA_DIR/'raw'/f) if r.crop.strip().startswith('Mantar') and r.province in ('Ordu','Manisa') and r.year==2025]" 2>&1 | grep -v skipped
```

Expected: Ordu 179 t / 1 da, Manisa 100 t / 4 da. If what you read disagrees with the file below, write what you actually read and say so in your report.

- [ ] **Step 2: Write the review file**

Create `data/crop_area_review.json`. Replace `reviewed_by` with the name of whoever ran Step 1.

```json
{
 "meta": {
  "reviewed": "2026-08-25",
  "reviewed_by": "Tunahan Yıldız",
  "why": "The density gate in scripts/build_crop_norms.py judges a derived yield by the tree density its own numbers imply. That test cannot see a crop whose recorded area is not field area at all - there is nothing in the published numbers that says so. A person reads the crop and records it here; the builder then writes no yield for it."
 },
 "not_field_area": {
  "Mantar (Kültür)": {
   "evidence": "Ordu 2025: 179 ton üretim / 1 dekar ekilen alan = 179.000 kg/da. Manisa 2025: 100 ton / 4 dekar = 25.000 kg/da. Mantar çok katlı yastıklarda yetişiyor, yani 'ekilen alan' binanın taban alanı - üretimin geldiği yüzey değil. Türetilen rakam her ilin verim x fiyat sıralamasının tepesine çıkıyor.",
   "note": "The price series is untouched: a mushroom price is a price."
  }
 }
}
```

- [ ] **Step 3: Write the failing tests**

Append to `tests/test_build_crop_norms.py`:

```python
def test_a_reviewed_crop_gets_no_yield_at_all():
    """Mushroom's `ekilen alan` is a building's footprint and its beds are
    stacked in tiers, so production over area is not a yield in any unit. No
    published number says so - a person did."""
    rows = [
        R("Ordu", "Mantar (Kültür)", 2025, "uretim", 179.0),
        R("Ordu", "Mantar (Kültür)", 2025, "alan", 1.0),
    ]
    out = bcn.build(rows, not_field_area=["Mantar (Kültür)"])
    assert "Ordu" not in out["crops"]["mantar (kultur)"]["yield_kg_da"]


def test_a_reviewed_crop_keeps_its_price():
    """A mushroom price is a price. Only the area-based figure is unusable."""
    rows = [
        R("Ordu", "Mantar (Kültür)", 2025, "uretim", 179.0),
        R("Ordu", "Mantar (Kültür)", 2025, "alan", 1.0),
        R("Ordu", "Mantar (Kültür)", 2025, "fiyat", 132.18),
    ]
    out = bcn.build(rows, not_field_area=["Mantar (Kültür)"])
    assert out["crops"]["mantar (kultur)"]["price_tl_kg"]["Ordu"] == [132.18]


def test_a_stale_review_entry_stops_the_build():
    """A review of a crop that is no longer in the exports is a review of
    nothing, sitting in the file looking like coverage."""
    rows = [R("Ordu", "Ayva", 2025, "verim", 1200.0)]
    with pytest.raises(ValueError, match="Mantar"):
        bcn.build(rows, not_field_area=["Mantar (Kültür)"])


def test_no_review_means_no_exclusions():
    """The default must be inert: an omitted argument may not silently gate."""
    rows = [
        R("Ordu", "Mantar (Kültür)", 2025, "uretim", 179.0),
        R("Ordu", "Mantar (Kültür)", 2025, "alan", 1.0),
    ]
    assert bcn.build(rows)["crops"]["mantar (kultur)"]["yield_kg_da"]["Ordu"] == [179000.0]
```

Add `import pytest` at the top of the file if it is not already imported.

- [ ] **Step 4: Run them and watch them fail**

Run: `python -m pytest tests/test_build_crop_norms.py -q`
Expected: FAIL — `build() got an unexpected keyword argument 'not_field_area'`.

- [ ] **Step 5: Implement**

In `scripts/build_crop_norms.py`, add next to the other path constants (near `SOURCES`):

```python
REVIEW = DATA_DIR / "crop_area_review.json"
```

Change `build`'s signature and docstring:

```python
def build(rows, not_field_area=()) -> dict:
    """Group Row(...) into the schema src/norms.py validates.

    Format-independent on purpose: read_export does the parsing, this does the
    shaping, and only this half can be tested without a real export.

    `not_field_area` is the REVIEWED answer to a question no published number
    can settle: whether a crop's recorded area is the ground its production came
    off. Mushroom's is a building's footprint. Those crops get no yield at all;
    their prices are untouched. A reviewed crop that no longer appears in the
    exports RAISES rather than sitting in the file looking like coverage.
    """
```

At the top of `build`, after `refused: list[dict] = []`, add:

```python
    excluded = {_normalize_tr(name): name for name in not_field_area}
```

After the row-grouping loop (immediately before `crops: dict[str, dict] = {}`), add the staleness gate:

```python
    stale = sorted(name for crop_id, name in excluded.items() if crop_id not in seen)
    if stale:
        raise ValueError(
            f"data/crop_area_review.json reviews {stale}, which the exports do "
            f"not carry - a review of nothing, sitting in the file looking like "
            f"coverage")
```

Inside the crop loop, immediately after the `per_tree = ...` line from Task 2, add:

```python
        # A reviewed crop yields nothing at all: not a gated figure, not a
        # figure with a caveat. Its price survives - a mushroom price is a price.
        if crop_id in excluded:
            published, uretim, alan = {}, {}, {}
            refused.append({"crop": labels[crop_id], "province": "*",
                            "year": 0, "reason": "area_is_not_field"})
```

Then wire `main()` to read the file — replace its `data = build(rows)` line with:

```python
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    data = build(rows, not_field_area=review["not_field_area"])
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_build_crop_norms.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add data/crop_area_review.json scripts/build_crop_norms.py tests/test_build_crop_norms.py && git commit -m "Write no yield for a crop whose recorded area is not field area"
```

---

## Task 4: Report every refusal, in the file and on the console

A silent skip is how a coverage collapse ships unnoticed. `product_doses.json`'s `unparsed` and `dropped_slots` set the precedent: the finding travels **with** the file.

**Files:**
- Modify: `scripts/build_crop_norms.py` (`build` return value, `main` printing)
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Produces: `data["meta"]["refused_yield_cells"] = {"counts": {reason: int, ...}, "cells": [{"crop", "province", "year", "reason"}, ...]}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build_crop_norms.py`:

```python
def test_a_refusal_is_recorded_in_the_file_with_its_reason():
    """The finding travels WITH the data: without this there is no committed
    way to tell "this province grows no quince" from "we threw its figure out"."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    record = bcn.build(rows)["meta"]["refused_yield_cells"]
    assert record["counts"] == {"density_above_ceiling": 1}
    assert record["cells"] == [{"crop": "Ayva", "province": "Ordu",
                                "year": 2025, "reason": "density_above_ceiling"}]


def test_the_refusal_record_is_empty_when_nothing_was_refused():
    record = bcn.build(_rows())["meta"]["refused_yield_cells"]
    assert record == {"counts": {}, "cells": []}


def test_refusals_are_sorted_so_the_committed_file_is_stable():
    """The file must be a reproducible output of the builder; a set-ordered list
    would diff differently on every run for no reason."""
    rows = [
        R("Tokat", "Erik", 2025, "uretim", 500.0),
        R("Tokat", "Erik", 2025, "alan", 1.0),
        R("Tokat", "Erik", 2025, "verim_agac", 16.0),
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    cells = bcn.build(rows)["meta"]["refused_yield_cells"]["cells"]
    assert [c["crop"] for c in cells] == ["Ayva", "Erik"]


def test_the_build_names_every_refusal_on_the_console(capsys):
    """It runs by hand once a year; its job is to fail loudly."""
    rows = [
        R("Ordu", "Ayva", 2025, "uretim", 267.0),
        R("Ordu", "Ayva", 2025, "alan", 3.0),
        R("Ordu", "Ayva", 2025, "verim_agac", 31.0),
    ]
    bcn.build(rows)
    printed = capsys.readouterr()
    assert "Ayva" in printed.err and "Ordu" in printed.err
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_build_crop_norms.py -q`
Expected: FAIL — `KeyError: 'refused_yield_cells'`.

- [ ] **Step 3: Implement**

In `build()`, replace the sort line added in Task 2 and the `return` statement with:

```python
    refused.sort(key=lambda r: (r["crop"], r["province"], r["year"]))
    counts: dict[str, int] = {}
    for cell in refused:
        counts[cell["reason"]] = counts.get(cell["reason"], 0) + 1
    for cell in refused:
        print(f"refused yield cell: {cell['crop']} / {cell['province']} / "
              f"{cell['year']}: {cell['reason']}", file=sys.stderr)

    return {"meta": {"generated": date.today().isoformat(),
                     "years": years, "sources": SOURCES,
                     # The finding travels WITH the file. Without this record
                     # there is no committed way to tell a province that grows
                     # none of a crop from one whose figure we threw out.
                     "refused_yield_cells": {"counts": counts,
                                             "cells": refused}},
            "crops": crops}
```

In `main()`, replace the final `print(...)` line with:

```python
    record = data["meta"]["refused_yield_cells"]
    print(f"wrote {out}: {len(data['crops'])} crops, years {data['meta']['years']}")
    if record["counts"]:
        total = sum(record["counts"].values())
        print(f"refused {total} yield cell(s), reported here rather than silently:")
        for reason, n in sorted(record["counts"].items()):
            print(f"          {reason}: {n}")
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_build_crop_norms.py -q`
Expected: PASS.

Then: `python -m pytest -q`
Expected: green. `tests/test_norms.py` reads the shipped file — if anything there fails, the new `meta` key broke the loader's validation, which it must not.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py && git commit -m "Record every refused yield cell in the file and on the console"
```

---

## Task 5: Regenerate, and guard the real data

**Files:**
- Regenerate: `data/crop_norms.json`
- Test: `tests/test_build_crop_norms.py`

- [ ] **Step 1: Regenerate**

Run:

```bash
python -m scripts.build_crop_norms
```

Expected: `refused N yield cell(s)` with `density_above_ceiling` ≈ 1.314, `density_below_floor` ≈ 259, `no_per_tree_figure` ≈ 102, `area_is_not_field` 1. The counts may differ slightly from the spec's if your Task 1 Step 1 folding differed; record what you actually get.

- [ ] **Step 2: Read the diff before trusting it**

Run:

```bash
git diff --stat data/crop_norms.json
```

Then check the three cells the spec names by hand:

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0,'.')
from src import norms
for crop, prov in (('Ayva','Ordu'), ('Ayva','Tokat'), ('Turunç','Adana'), ('Mantar (Kültür)','Ordu'), ('Domates (Sofralık)','Konya')):
    row = next((r for r in norms.province_table(prov) if r.label == crop), None)
    y = row.yield_kg_da if row else None
    print(f'{crop} / {prov}: {y.amount if y else None}')
"
```

Expected: `Ayva / Ordu` → `None`; `Ayva / Tokat` → a figure near 1.174; `Turunç / Adana` → `None`; `Mantar (Kültür) / Ordu` → `None`; `Domates (Sofralık) / Konya` → unchanged near 5.492 (the vegetable guard).

- [ ] **Step 3: Write the real-data guards**

Append to `tests/test_build_crop_norms.py`:

```python
def test_the_shipped_file_is_what_the_builder_produces():
    """Proves the data file was generated, not hand-edited."""
    import json as _json
    from src.config import DATA_DIR
    rows = []
    for path in sorted((DATA_DIR / "raw").glob("*.csv")):
        rows.extend(bcn.read_export(path))
    review = _json.loads((DATA_DIR / "crop_area_review.json").read_text(encoding="utf-8"))
    rebuilt = bcn.build(rows, not_field_area=review["not_field_area"])
    shipped = _json.loads((DATA_DIR / "crop_norms.json").read_text(encoding="utf-8"))
    assert rebuilt["crops"] == shipped["crops"]
    assert rebuilt["meta"]["refused_yield_cells"] == shipped["meta"]["refused_yield_cells"]


def test_the_shipped_file_still_carries_most_of_its_yields():
    """A guard on the real data: if the gate ever starts refusing everything,
    every fixture test above keeps passing while the feature quietly empties."""
    import json as _json
    from src.config import DATA_DIR
    shipped = _json.loads((DATA_DIR / "crop_norms.json").read_text(encoding="utf-8"))
    cells = sum(1 for crop in shipped["crops"].values()
                for province, series in crop["yield_kg_da"].items()
                if province not in ("scope", "TR")
                for v in series if v is not None)
    assert cells >= 20000, cells
    # 20.000 is a deliberate floor, not the measured count. Print `cells` once
    # when you write this test and RAISE the floor to roughly two thirds of what
    # you actually get: a floor an order of magnitude below the truth catches a
    # total collapse and nothing else. Record the real number in your report.


def test_the_shipped_file_carries_no_cell_the_gate_should_have_refused():
    """The file stores a yield, not a density, so this check runs the density
    test again over the committed exports rather than reading the file alone."""
    import json as _json
    from src.config import DATA_DIR
    rows = []
    for path in sorted((DATA_DIR / "raw").glob("*.csv")):
        rows.extend(bcn.read_export(path))
    per_tree, uretim, alan = {}, {}, {}
    for r in rows:
        key = (bcn._normalize_tr(r.crop), r.province, r.year)
        if r.measure == "verim_agac":
            per_tree[key] = r.value
        elif r.measure == "uretim":
            uretim[key] = r.value
        elif r.measure == "alan":
            alan[key] = r.value
    shipped = _json.loads((DATA_DIR / "crop_norms.json").read_text(encoding="utf-8"))
    years = shipped["meta"]["years"]
    bad = []
    for crop_id, crop in shipped["crops"].items():
        for province, series in crop["yield_kg_da"].items():
            if province in ("scope", "TR"):
                continue
            for i, value in enumerate(series):
                if value is None:
                    continue
                key = (crop_id, province, years[i])
                if key not in per_tree or key not in uretim or key not in alan:
                    continue
                if bcn._density_verdict(uretim[key], alan[key], per_tree[key]):
                    bad.append(key)
    assert bad == [], bad[:5]


def test_the_shipped_file_refused_the_cells_the_spec_names():
    """The three worked examples from the design doc, on the real data."""
    import json as _json
    from src.config import DATA_DIR
    shipped = _json.loads((DATA_DIR / "crop_norms.json").read_text(encoding="utf-8"))
    refused = {(c["crop"], c["province"]) for c in
               shipped["meta"]["refused_yield_cells"]["cells"]}
    assert ("Ayva", "Ordu") in refused
    assert ("Turunç", "Adana") in refused
    assert ("Mantar (Kültür)", "*") in refused
    assert ("Ayva", "Tokat") not in refused
```

`bcn._normalize_tr` is imported into the builder's namespace from `src.engine`, so the test can reach it there; if it is not exposed, import it in the test with `from src.engine import _normalize_tr` and use that instead.

- [ ] **Step 4: Run everything**

Run: `python -m pytest -q`
Expected: PASS. `tests/test_norms.py` and `tests/test_budget.py` both read the real norms — a failure there means a consumer depended on a cell this gate removed, which is a finding to report, not a number to soften.

- [ ] **Step 5: Check what the budget form now does with a refused crop**

The prefill is the reason this work exists; look at it rather than assuming.

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0,'.')
from src import budget, norms
spec = budget.form_spec([], norms.province_table('Adana'), None, norms.latest_year())
rows = {c['label']: c for c in spec['crops']}
for name in ('Turunç', 'Mantar (Kültür)', 'Domates (Sofralık)'):
    row = rows.get(name)
    print(name, '-> yield cell:', row['yield'] if row else 'crop absent')
"
```

Expected: `Turunç` and `Mantar (Kültür)` now serve `None` for yield (the card shows no prefill and the farmer types their own), while `Domates (Sofralık)` still carries its figure. Neither may crash.

- [ ] **Step 6: Commit**

```bash
git add data/crop_norms.json tests/test_build_crop_norms.py && git commit -m "Regenerate the norms without the cells the gate refuses"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Where |
| --- | --- |
| §2.1 refuse the cell, report by name | Tasks 2, 4 |
| §2.2 refusals visible on console and in `meta` | Task 4 |
| §2.3 per-tree read as evidence, never written | Task 1 (`test_a_per_tree_yield_never_becomes_a_yield`) |
| §2.4 no interface change, no new APK | Nothing outside `scripts/` and `data/` is touched; Task 5 Step 5 checks the consumer |
| §2.5 reproducible output | Task 5 (`test_the_shipped_file_is_what_the_builder_produces`) |
| §3 the density test | Task 2 (`_density_verdict`) |
| §4 the band and its argument | Task 2 Step 3, in the constant's own comment |
| §5 the cost | Task 5 Step 1 records the actual counts |
| §6 unjudgeable cells refused; mushroom reviewed | Tasks 2, 3 |
| §7 output and reporting | Task 4 |
| §8 absent never zero; published beats derived; no conversion | Task 2 (`test_a_published_per_dekar_yield_is_never_gated`), Task 1 |
| §9 the whole testing table | Tasks 1–5 |
| §10 out of scope | Not built |

**Placeholder scan:** none — every step carries its code, its command and its expected output.

**Type consistency:** `_density_verdict(tons, dekar, per_tree)` returns `str | None` and is called with exactly those three in Task 2; the refusal dict keys `crop`/`province`/`year`/`reason` are written in Tasks 2 and 3 and read in Task 4 and Task 5's tests; `build(rows, not_field_area=())` is called with one argument by every pre-existing test and with the keyword by `main()` and the new tests.

**One risk this plan cannot test away:** the gate's `per_tree` lookup is keyed on the crop label as TÜİK spells it in each export. If the production file and the fruit-yield file ever spell a crop differently, that crop's cells all become `no_per_tree_figure` and vanish. Task 5's coverage floor (`>= 20000` cells) is what catches that, and Task 5 Step 1's counts are what makes it visible — if `no_per_tree_figure` comes back in the thousands rather than near 102, stop and investigate the spelling before committing.
