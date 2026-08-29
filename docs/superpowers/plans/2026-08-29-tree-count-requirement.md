# Tree Count Requirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the budget form calling `Ağaç sayısı` optional when a per-tree yield prefill makes it mandatory — with a hint that works on the build people are running today, and the real label fix for the next one.

**Architecture:** `UnitOption`'s two booleans (`per_area`, `per_tree`) collapse into one `needs` field naming the FieldSpec a unit cannot be converted without, plus a per-unit `needs_error`. `_read` becomes one lookup. The wire's new `requires` list on a crop row is derived from that same fact, so the client's label and the server's refusal can never disagree. A temporary hint rides on the yield cell's `recent` string, the one line the deployed client renders that nothing on the server reads.

**Tech Stack:** Python 3.14, pytest. React Native / Expo client in `mobile-app/` (TypeScript, no test runner — verified with `npx tsc --noEmit`).

**Spec:** `docs/superpowers/specs/2026-08-29-tree-count-requirement-design.md`

## Global Constraints

- Run every Python command from the repo root. `src/config.py` reads a RELATIVE `env_file=".env"`; running elsewhere silently loads a wrong `EMBEDDING_MODEL`.
- **No user-facing Turkish string may change wording.** The two unit-refusal messages must render character for character as they do today. Tests pin both verbatim.
- **A field crop's `form_spec` output must be byte-identical to today**, crop rows included. Only a crop row whose yield cell is per-tree gains a key.
- A missing norm is never zero. Absence is `None`; a per-unit value with its dependency missing is REFUSED, never multiplied by a guess and never zeroed.
- Comments explain WHY, not what. Match the surrounding density and voice.
- Commit messages: short, natural, English, no `Co-Authored-By` trailer.
- `python -m pytest -q` must be green (**975 tests** at plan time) before every commit. There is no expected intermediate red state in this plan — if something is red, stop and report.
- Out of scope: `data/crop_norms.json`, the builder, the density rules, `src/norms.py`, `src/crop_compare.py`, `src/router.py`, and anything under `mobile-app/` other than `src/api.ts` and `src/BudgetCard.tsx`. Do not build or release an APK.

---

### Task 1: One `needs` field where there were two flags

**Files:**
- Modify: `src/budget.py` — `UnitOption`, `FIELDS`, `_read`, `validate`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `UnitOption(id, label, factor, needs=None, needs_error=None)` where `needs` is a `FieldSpec` id. `_read(spec, raw, provided=None)` takes a `dict[str, float | None]` keyed by field id instead of two positional floats. Task 3 reads `UnitOption.needs` to derive the wire's `requires`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`, immediately after `test_a_zero_area_and_a_zero_tree_count_report_the_same_shape`:

```python
def test_a_unit_names_the_field_it_cannot_be_converted_without():
    """One fact in one place. `_read` refuses on it and Task 3's wire `requires`
    is derived from it, so the client's label and the server's refusal cannot
    disagree."""
    units = {u.id: u for u in budget._FIELDS_BY_ID["yield_total"].units}
    assert units["kg_da"].needs == "area"
    assert units["kg_agac"].needs == "tree_count"
    assert units["kg"].needs is None
    assert units["ton"].needs is None


def test_the_per_area_refusal_reads_exactly_as_it_did():
    """A refactor may not move one character of user-facing Turkish."""
    _, errors = budget.validate(_payload(
        area={"value": "", "unit": "donum", "source": "user"},
        yield_total={"value": "400", "unit": "kg_da", "source": "user"}))
    messages = [e.message for e in errors]
    assert ("Ürün miktarı için dekar başına değer girdiniz; "
            "önce alanı doldurun.") in messages


def test_the_per_tree_refusal_reads_exactly_as_it_did():
    _, errors = budget.validate(_payload(
        yield_total={"value": "31", "unit": "kg_agac", "source": "user"}))
    assert [e.message for e in errors] == [
        "Ürün miktarı için ağaç başına değer girdiniz; "
        "önce ağaç sayısını doldurun."]


def test_a_unit_with_no_dependency_is_never_refused_for_one():
    """`kg` and `ton` state a total already. A lookup that fired on them would
    make every plain submission depend on a field it does not need."""
    inputs, errors = budget.validate(_payload(
        yield_total={"value": "4000", "unit": "kg", "source": "user"}))
    assert errors == [] and inputs.yield_kg.amount == 4000.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_budget.py -q -k "cannot_be_converted_without or reads_exactly_as_it_did or no_dependency_is_never_refused"`

Expected: `test_a_unit_names_the_field_it_cannot_be_converted_without` fails with `AttributeError: 'UnitOption' object has no attribute 'needs'`. The other three PASS — they pin behaviour that already works and exist to catch this refactor breaking it. Note exactly which fail before continuing.

- [ ] **Step 3: Write the implementation**

In `src/budget.py`, replace the two boolean fields on `UnitOption`:

```python
@dataclass(frozen=True)
class UnitOption:
    id: str
    label: str
    factor: float          # multiply by this to reach the canonical unit
    # The FIELD this unit cannot be converted without: a per-dekar value needs
    # the area, a per-tree value needs the tree count. Kept ON THE UNIT rather
    # than as a second field, so the conversion stays one lookup, a new
    # dependent unit needs no new branch, and the wire's `requires` is derived
    # from the same fact the validator enforces instead of restating it.
    needs: str | None = None            # a FieldSpec id
    # The refusal when `needs` is not filled. Carried per unit because the two
    # messages differ in more than the field's name - "dekar başına" against
    # "ağaç başına", "alanı" against "ağaç sayısını" - so one f-string over the
    # label cannot produce both, and generating them would change user-facing
    # Turkish.
    needs_error: str | None = None
```

In `FIELDS`, replace the `yield_total` spec's two dependent units:

```python
    FieldSpec("yield_total", "Ürün miktarı", True, 0.0, False,
              (UnitOption("kg", "kg", 1.0),
               UnitOption("ton", "ton", 1000.0),
               UnitOption("kg_da", "kg/dekar", 1.0, needs="area",
                          needs_error="için dekar başına değer girdiniz; "
                                      "önce alanı doldurun."),
               UnitOption("kg_agac", "kg/ağaç", 1.0, needs="tree_count",
                          needs_error="için ağaç başına değer girdiniz; "
                                      "önce ağaç sayısını doldurun."))),
```

Change `_read`'s signature and replace its two dependency branches with one:

```python
def _read(spec: FieldSpec, raw: dict,
          provided: dict[str, float | None] | None = None
          ) -> tuple[Value | None, FieldError | None]:
```

and, where the `if unit.per_area:` and `if unit.per_tree:` blocks were:

```python
    if unit.needs is not None:
        have = (provided or {}).get(unit.needs)
        if have is None:
            # Refused, never multiplied by a guessed value and never zeroed.
            return None, FieldError(spec.id, f"{spec.label} {unit.needs_error}")
        amount = amount * have
```

In `validate`, pass the dependencies by name. The two out-of-`FIELDS`-order reads stay exactly as they are — only what they hand down changes:

```python
    trees_spec = _FIELDS_BY_ID["tree_count"]
    trees_value, trees_error = _read(trees_spec, raw, {"area": area_da})
    values[trees_spec.id] = trees_value
    if trees_error is not None:
        errors.append(trees_error)
    trees = trees_value.amount if trees_value is not None else None

    provided = {"area": area_da, "tree_count": trees}
    for spec in FIELDS:
        if spec.id in (area_spec.id, trees_spec.id):
            continue
        value, error = _read(spec, raw, provided)
        values[spec.id] = value
        if error is not None:
            errors.append(error)
```

The `area` read above it keeps calling `_read(area_spec, raw)` with no third argument.

Then grep for any remaining reference: `grep -n "per_area\|per_tree" src/budget.py tests/test_budget.py`. A test pinning the old attribute names must be updated to the new one; a test pinning BEHAVIOUR must not be touched.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_budget.py -q`
Expected: all pass.

Run: `python -m pytest -q`
Expected: **975 passed, 0 failed.**

- [ ] **Step 5: Prove the refactor did not weaken the refusal**

Temporarily change `kg_agac`'s `needs` from `"tree_count"` to `None` and run:

Run: `python -m pytest tests/test_budget.py -q -k "per_tree_refusal or per_tree_value_without"`
Expected: **FAIL** — a per-tree value is silently accepted with no tree count.

Revert, re-run, confirm green and `git status --short` empty. A refactor that quietly removed a guard would otherwise look identical to one that kept it.

- [ ] **Step 6: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Put a unit's dependency on the unit itself"
```

---

### Task 2: The temporary hint under a per-tree prefill

**Files:**
- Modify: `src/budget.py` — a module constant and `_yield_cell`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: nothing from Task 1 (this touches only the cell builder).
- Produces: `budget._TREE_COUNT_HINT`, a module-level string. A per-tree yield cell's `recent` value ends with it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`, after `test_the_per_tree_cell_shows_its_own_five_year_range`:

```python
def test_a_per_tree_cell_tells_the_farmer_to_fill_the_tree_count():
    """The deployed client renders `{label}{required ? "" : " (isteğe bağlı)"}`,
    so `Ağaç sayısı` reads OPTIONAL while a per-tree prefill makes it
    mandatory. Until a build ships that can say otherwise, the instruction
    rides on the one line under this field that the client already renders and
    nothing on the server reads."""
    spec = budget.form_spec([], _tree_table())
    assert spec["crops"][0]["yield"]["recent"] == (
        "önceki 5 yıl: 27–28 kg/ağaç · ağaç sayısını da girin")


def test_the_hint_survives_a_cell_with_no_five_year_range():
    """It must not depend on the range's existence, or it would vanish on
    exactly the crops with the thinnest history."""
    table = (CropNorm("ayva", "Ayva", None,
                      NormValue(19.0, 2025, "il", "Karabük", None, None),
                      NormValue(31.0, 2025, "il", "Karabük", None, None)),)
    spec = budget.form_spec([], table)
    assert spec["crops"][0]["yield"]["recent"] == "ağaç sayısını da girin"


def test_a_field_crops_cell_carries_no_hint():
    spec = budget.form_spec([], _tree_table())
    cell = spec["crops"][1]["yield"]
    assert cell["recent"] == "önceki 5 yıl: 900–1.200 kg/da"
    assert "ağaç" not in cell["recent"]


def test_the_hint_does_not_touch_the_note_the_answer_prints():
    """`note` is not free: _verify reads it and it becomes the answer's
    provenance sentence. A hint there would leak into the answer."""
    spec = budget.form_spec([], _tree_table())
    assert spec["crops"][0]["yield"]["note"] == "TÜİK 2025, Karabük"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_budget.py -q -k "fill_the_tree_count or hint_survives or carries_no_hint or does_not_touch_the_note"`

Expected: the first two FAIL on the missing hint (`assert 'önceki 5 yıl: 27–28 kg/ağaç' == '...· ağaç sayısını da girin'`). The last two PASS — they are guards against the hint reaching a field crop or the note.

- [ ] **Step 3: Write the implementation**

In `src/budget.py`, add the constant immediately above `_yield_cell`:

```python
# TEMPORARY, added 2026-08-29. The deployed client renders a field's label as
# `{label}{required ? "" : " (isteğe bağlı)"}` from one flag, so `Ağaç sayısı`
# reads OPTIONAL even though a per-tree prefill makes it mandatory. Of the
# strings the server can put under that field, `note` is spoken for - _verify
# reads it and it becomes the answer's provenance line - so the instruction
# rides on `recent`, which nothing on the server reads.
#
# DELETE THIS, and the two lines below that use it, once a build carrying the
# `requires` label fix is deployed. Nothing here can detect that; it is a
# human call.
_TREE_COUNT_HINT = "ağaç sayısını da girin"
```

and change `_yield_cell`'s per-tree branch:

```python
    if row.yield_kg_tree is not None:
        cell = _norm_cell(row.yield_kg_tree, *_NORM_UNITS["yield_tree"], None,
                          show_range=True)
        if cell is not None:
            cell["recent"] = (f"{cell['recent']} · {_TREE_COUNT_HINT}"
                              if cell["recent"] else _TREE_COUNT_HINT)
        return cell
    return _norm_cell(row.yield_kg_da, *_NORM_UNITS["yield"], None,
                      show_range=True)
```

Extend `_yield_cell`'s docstring with one sentence saying the per-tree cell also carries the temporary hint and pointing at the constant's comment for why and when it goes.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_budget.py -q`
Expected: all pass.

Run: `python -m pytest -q`
Expected: **975 or more passed, 0 failed.**

- [ ] **Step 5: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Tell the farmer to fill the tree count, until the client can"
```

---

### Task 3: `requires` on the wire, derived from the unit

**Files:**
- Modify: `src/budget.py` — a new `_requires` helper and `_crop_rows`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `UnitOption.needs` from Task 1; `_yield_cell(row) -> dict | None`.
- Produces: a crop row may carry `"requires": ["tree_count"]`. Task 4's client reads it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`, after the tests from Task 2:

```python
def test_a_per_tree_crop_row_names_the_field_it_makes_mandatory():
    spec = budget.form_spec([], _tree_table())
    assert spec["crops"][0]["requires"] == ["tree_count"]


def test_a_field_crop_row_carries_no_requires_key_at_all():
    """Not an empty list: the row must stay byte-identical to what an already
    deployed client has been reading."""
    spec = budget.form_spec([], _tree_table())
    assert "requires" not in spec["crops"][1]


def test_an_already_required_dependency_is_not_listed():
    """A per-dekar cell needs the AREA, and the area is required for every
    crop. Listing it would tell the client nothing it does not know and would
    put the key on every field crop."""
    spec = budget.form_spec([], _table())
    assert all("requires" not in crop for crop in spec["crops"])


def test_a_crop_with_no_yield_cell_gets_no_requires():
    """The derivation must not assume a cell exists."""
    table = (CropNorm("bos", "Boş", None, None, None),)
    spec = budget.form_spec([], table)
    assert "requires" not in spec["crops"][0]


def test_requires_is_derived_from_the_unit_not_hand_listed():
    """THE POINT. The server's real rule lives in the unit - a per-tree value
    is refused without the tree count. A hand-written list would be a second
    source of truth for one fact and would drift the first time a unit changed.
    Blank the unit's dependency and the wire must stop claiming it."""
    from dataclasses import replace
    spec = budget._FIELDS_BY_ID["yield_total"]
    stripped = tuple(replace(u, needs=None) if u.id == "kg_agac" else u
                     for u in spec.units)
    original = budget._FIELDS_BY_ID["yield_total"]
    try:
        budget._FIELDS_BY_ID["yield_total"] = replace(spec, units=stripped)
        assert "requires" not in budget.form_spec([], _tree_table())["crops"][0]
    finally:
        budget._FIELDS_BY_ID["yield_total"] = original
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_budget.py -q -k "names_the_field_it_makes_mandatory or carries_no_requires_key or already_required_dependency or no_yield_cell_gets_no_requires or derived_from_the_unit"`

Expected: `test_a_per_tree_crop_row_names_the_field_it_makes_mandatory` fails with `KeyError: 'requires'`. The other four PASS — they are guards, and `test_requires_is_derived_from_the_unit_not_hand_listed` passes vacuously while no key exists at all. Note which fail; the derivation test only becomes load-bearing after Step 3, and Step 5 proves it.

- [ ] **Step 3: Write the implementation**

In `src/budget.py`, add the helper immediately after `_yield_cell`:

```python
def _requires(cell: dict | None) -> list[str] | None:
    """Which normally-optional field this crop makes mandatory, or None.

    DERIVED, never hand-listed. The server's rule lives in the unit: a per-tree
    value cannot be converted without the tree count and `_read` refuses it. A
    separate list would be a second source of truth for one fact, and the
    client's label would drift from the server's refusal the first time a unit
    changed.

    Only fields that are OPTIONAL by default appear. A per-dekar cell needs the
    AREA, which is required for every crop, so saying so would tell the client
    nothing and would put this key on every field crop.
    """
    if cell is None:
        return None
    unit = next((u for u in _FIELDS_BY_ID["yield_total"].units
                 if u.id == cell["unit"]), None)
    if unit is None or unit.needs is None:
        return None
    needed = _FIELDS_BY_ID.get(unit.needs)
    if needed is None or needed.required:
        return None
    return [needed.id]
```

and rewrite `_crop_rows`'s loop body so the cell is built once and the key is added only when it is earned:

```python
    rows = []
    for row in table:
        price = row.price_tl_kg
        if price is not None and (latest_year is None or price.year != latest_year):
            price = None
        cell = _yield_cell(row)
        entry = {
            "id": row.crop,
            "label": row.label,
            "yield": cell,
            "price": _norm_cell(price, *_NORM_UNITS["price"], 2, show_range=False),
        }
        # Absent, not an empty list: a field crop's row must stay exactly what
        # an already-deployed client has been reading.
        requires = _requires(cell)
        if requires:
            entry["requires"] = requires
        rows.append(entry)
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_budget.py -q`
Expected: all pass.

Run: `python -m pytest -q`
Expected: **975 or more passed, 0 failed.**

- [ ] **Step 5: Prove the derivation test bites**

Replace `_requires`'s body with a hand-written constant — `return ["tree_count"] if cell and cell["unit"] == "kg_agac" else None` — and run:

Run: `python -m pytest tests/test_budget.py -q -k "derived_from_the_unit"`
Expected: **FAIL** — the wire still claims `tree_count` after the unit's dependency was blanked.

Revert, re-run, confirm green and `git status --short` empty. Without this step the test would pass against a hand-listed implementation, which is exactly what it exists to forbid.

- [ ] **Step 6: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Publish which field a crop makes mandatory, derived from its unit"
```

---

### Task 4: The client stops calling it optional

**Files:**
- Modify: `mobile-app/src/api.ts` — the `CropOption` interface
- Modify: `mobile-app/src/BudgetCard.tsx` — the label line
- Verify: `npx tsc --noEmit`

**Interfaces:**
- Consumes: the `requires` key from Task 3.
- Produces: nothing later depends on this.

- [ ] **Step 1: Read the two files and the existing shape**

Run: `cat mobile-app/src/api.ts | sed -n '55,75p'` and `sed -n '178,190p' mobile-app/src/BudgetCard.tsx`

There is no JavaScript test runner in this project (`package.json` has only `expo` scripts), so this task is verified by the type checker and by reading. Do not add a test framework.

- [ ] **Step 2: Add the field to the type**

In `mobile-app/src/api.ts`, add to the `CropOption` interface, after `price`:

```typescript
  // Fields this crop makes mandatory even though the form marks them
  // optional. Absent for most crops; the server sends it only when a crop
  // earns one, so an older build simply never sees it.
  requires?: string[];
```

- [ ] **Step 3: Use it for the label**

In `mobile-app/src/BudgetCard.tsx`, replace the label block:

```tsx
          <Text style={styles.label}>
            {f.label}
            {f.required || (selected?.requires ?? []).includes(f.id)
              ? ""
              : " (isteğe bağlı)"}
          </Text>
```

`selected` is already computed in this component as the crop row matching the chosen crop; do not introduce a second lookup.

- [ ] **Step 4: Type-check**

Run: `cd mobile-app && npx tsc --noEmit`
Expected: no output, exit code 0. If `tsc` reports an error in a file you did not touch, report it rather than fixing it — this project's client has not been type-clean-gated before and a pre-existing error is not yours.

- [ ] **Step 5: Read the three states out loud**

There is no runner, so reason through the rendered label for each case and write what you conclude in your report:
- a fruit crop selected (`requires: ["tree_count"]`) → `Ağaç sayısı` with NO suffix, `Masraf` still `(isteğe bağlı)`
- a field crop selected (no `requires`) → `Ağaç sayısı (isteğe bağlı)`
- no crop selected (`selected` is `undefined`) → `Ağaç sayısı (isteğe bağlı)`

If any of the three does not follow from the code you wrote, stop and report.

- [ ] **Step 6: Commit**

```bash
git add mobile-app/src/api.ts mobile-app/src/BudgetCard.tsx
git commit -m "Stop calling the tree count optional when the crop needs it"
```

---

## Self-Review

**Spec coverage:**

| spec requirement | task |
|---|---|
| hint on a per-tree cell's `recent`, with and without a range | 2 |
| hint marked temporary, with its removal condition and who decides | 2 (the constant's comment) |
| `note` untouched, so the answer's provenance cannot move | 2 (test) |
| `requires` on the crop row | 3 |
| derived from the unit, never hand-listed | 3 (Steps 3 and 5) |
| only default-optional fields listed | 3 (`needed.required` check + test) |
| key ABSENT, not an empty list | 3 (`if requires:` + test) |
| no yield cell → no `requires` | 3 (test) |
| `needs` replaces the two booleans | 1 |
| `needs_error` per unit, both messages verbatim | 1 (Steps 1 and 3) |
| `_read` collapses to one lookup | 1 |
| the two out-of-order reads stay mirrors | 1 (the existing test stays green) |
| client label reads the truth in all three states | 4 |
| field-crop `form_spec` byte-identical | 3 (test) and the existing pinned wire literal |

No gaps. The spec's "out of scope" items are touched by no task.

**Placeholder scan:** every code step carries the actual code; every run step carries the actual command and its expected output. No TBD, no "handle edge cases", no "similar to Task N".

**Type consistency:** `UnitOption.needs` / `needs_error` are named identically in Tasks 1 and 3. `_read(spec, raw, provided)` is defined and called with the same third-argument shape in Task 1. `_requires(cell) -> list[str] | None` is defined in Task 3 and used only there. `_TREE_COUNT_HINT` is defined in Task 2 and used only there. The client's `requires?: string[]` (Task 4) matches the `list[str]` Task 3 emits.

**Every string this plan pins was checked against the real fixture before the plan was
committed** — `_tree_table()`'s Ayva cell renders `note` `TÜİK 2025, Karabük` and `recent`
`önceki 5 yıl: 27–28 kg/ağaç`; its Mısır cell renders `önceki 5 yıl: 900–1.200 kg/da`;
`_table()`'s two crops are `findik` and `misir`, neither per-tree. This plan's predicted
failure messages have been wrong three times in this project's recent rounds, so the
expected VALUES were verified rather than recalled.

**Two risks worth naming:**

1. **Task 1 is a refactor of a shipped guard.** A refactor that silently dropped the refusal would look identical to one that kept it, so Step 5 blanks a unit's dependency and requires the tests to go red. Do not skip it.
2. **Task 3's derivation test passes vacuously before the feature exists** (no `requires` key at all means "not in" holds). Step 2 says so plainly and Step 5 proves the test bites against a hand-listed implementation — the failure mode this project has hit four times is a test that cannot tell a right implementation from a wrong one.
