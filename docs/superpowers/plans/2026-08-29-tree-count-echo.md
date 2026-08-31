# Tree Count Echo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the budget answer restate the tree count — an input it uses and never names — so a farmer who types 4000 for 400 can see it.

**Architecture:** `validate` already reads the tree count and throws it away after converting a per-tree yield. It will carry it on `BudgetInputs`, but only when the yield's chosen unit actually needed it, and `render` will echo it beside the area. Deciding "did it take part" needs the submitted unit, which only `_read` knows today, so that lookup is extracted first.

**Tech Stack:** Python 3.14, pytest. One source file, one test file. No data-file, builder or client change.

**Spec:** `docs/superpowers/specs/2026-08-29-tree-count-echo-design.md`

## Global Constraints

- Run every command from the repo root. `src/config.py` reads a RELATIVE `env_file=".env"`; running elsewhere silently loads a wrong `EMBEDDING_MODEL`.
- **A field-crop answer must be byte-identical to today.** 185 of the 246 crops are not tree crops.
- **The tree count is echoed ONLY when it took part** — when the yield's unit has `needs == "tree_count"`. A farmer can fill it and then state their harvest in `kg`; listing it under *"Şu değerlere göre"* would name a figure that entered no arithmetic, the defect class this route has shipped three fixes for.
- That condition is read from `UnitOption.needs`, the single source of truth the `requires` round established. Not a second copy.
- `compute()` and every figure it produces are untouched. This round adds an echo, changes no arithmetic.
- A missing norm is never zero. Absence is `None`.
- Turkish user-facing strings exactly as given. `format_qty` formats the count, so 4000 renders `4.000`.
- Comments explain WHY, not what. Match the surrounding density and voice.
- Commit messages: short, natural, English, no `Co-Authored-By` trailer.
- `python -m pytest -q` must be green (**1012 tests** at plan time) before every commit.
- Out of scope: `src/crop_compare.py`, `src/norms.py`, the card, the builder, `data/`, `mobile-app/`.

---

### Task 1: extract the unit lookup

**Files:**
- Modify: `src/budget.py` — a new module-level helper, and `_read`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `budget._chosen_unit(spec: FieldSpec, raw: dict) -> UnitOption | None`. Task 2 calls it from `validate`.

**This is a pure refactor: no behaviour may change.** `_read` currently resolves the submitted unit inline at `src/budget.py:204`:

```python
    unit = next((u for u in spec.units if u.id == entry.get("unit")), None)
```

Task 2 needs the same answer in `validate`, so the lookup moves into one named place rather than being written twice.

**Do NOT touch the similar-looking lookup in `_requires` (around `src/budget.py:450`).** It resolves a unit from a CELL dict the server itself built (`cell["unit"]`), not from an untrusted payload — a different question with a different input. Forcing one helper over both would merge two things that only look alike.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`, immediately after `test_a_unit_names_the_field_it_cannot_be_converted_without`:

```python
def test_the_chosen_unit_is_the_one_the_payload_names():
    spec = budget._FIELDS_BY_ID["yield_total"]
    unit = budget._chosen_unit(spec, {"yield_total": {"value": "31",
                                                      "unit": "kg_agac"}})
    assert unit is not None and unit.id == "kg_agac"


def test_no_unit_is_chosen_when_the_payload_names_none():
    """`_read` refuses such a submission with "birimi seçin"; the lookup must
    report the absence rather than guessing a default."""
    spec = budget._FIELDS_BY_ID["yield_total"]
    assert budget._chosen_unit(spec, {"yield_total": {"value": "31"}}) is None


def test_no_unit_is_chosen_when_the_payload_names_one_the_field_lacks():
    """A client is untrusted: a unit id this field does not offer is not a
    unit, and must not resolve to a neighbouring field's."""
    spec = budget._FIELDS_BY_ID["yield_total"]
    assert budget._chosen_unit(
        spec, {"yield_total": {"value": "31", "unit": "tl_kg"}}) is None


def test_no_unit_is_chosen_when_the_field_is_absent_or_malformed():
    """validate() coerces a non-dict payload before use; this helper is called
    with the raw one and must not raise on either shape."""
    spec = budget._FIELDS_BY_ID["yield_total"]
    assert budget._chosen_unit(spec, {}) is None
    assert budget._chosen_unit(spec, {"yield_total": "31 kg_agac"}) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_budget.py -q -k "chosen_unit or names_none or field_lacks or absent_or_malformed"`
Expected: all four FAIL with `AttributeError: module 'src.budget' has no attribute '_chosen_unit'`.

- [ ] **Step 3: Write the implementation**

In `src/budget.py`, add the helper immediately above `_read`:

```python
def _chosen_unit(spec: FieldSpec, raw: dict) -> UnitOption | None:
    """The unit this payload names for that field, or None.

    Named rather than inlined because `validate` has to ask the same question
    `_read` answers internally - was the yield submitted in a unit that needs
    the tree count? - and a second copy of the lookup would be a second place
    to get "which unit did they pick" wrong.

    None both for a payload naming no unit and for one naming a unit this field
    does not offer: the client is untrusted, and a stray id must not resolve to
    some other field's unit.
    """
    entry = raw.get(spec.id)
    if not isinstance(entry, dict):
        return None
    return next((u for u in spec.units if u.id == entry.get("unit")), None)
```

Then, in `_read`, replace the inline lookup with a call:

```python
    unit = _chosen_unit(spec, raw)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_budget.py -q`
Expected: all pass. `_read`'s existing refusal tests — the "birimi seçin" ones — must be green and untouched; if any needed editing, the extraction changed behaviour and you should stop and report.

Run: `python -m pytest -q`
Expected: **1012 or more passed, 0 failed.**

- [ ] **Step 5: Prove the refactor did not stop the lookup working**

Temporarily make `_chosen_unit` return the field's first unit regardless:

```python
    return spec.units[0]
```

Run: `python -m pytest tests/test_budget.py -q`
Expected: **FAIL** — a per-tree submission would be read as plain `kg`, and the unit-refusal tests would stop refusing.

Revert, re-run, confirm green. A refactor that silently stopped resolving the unit would otherwise look identical to one that kept working.

- [ ] **Step 6: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Name the lookup that resolves a submitted unit"
```

---

### Task 2: carry the count when it took part, and echo it

**Files:**
- Modify: `src/budget.py` — `BudgetInputs`, the `return BudgetInputs(...)` in `validate`, and `render`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `budget._chosen_unit(spec, raw) -> UnitOption | None` from Task 1; `UnitOption.needs` is a `FieldSpec` id or `None`.
- Produces: `BudgetInputs.trees: Value | None = None`. Nothing later depends on it.

Facts you will need:
- `BudgetInputs` is constructed in exactly ONE place, `src/budget.py:317`, with keyword arguments — so a new defaulted field is safe. Its current fields are `area_da, yield_kg, price_tl_kg, cost_tl` then `crop=None, crop_label=None`.
- `validate` already stores the tree count's `Value` as `values["tree_count"]`.
- `render` builds a list named `given` and joins it with `", "`.
- `format_qty(4000.0)` renders `'4.000'`; `format_qty(400.0)` renders `'400'`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`, after the tests from Task 1:

```python
def _fruit_payload(**over):
    """A per-tree submission: the yield is stated per tree, so the count is
    what turns it into a total."""
    base = {
        "area": {"value": "10", "unit": "donum", "source": "user"},
        "tree_count": {"value": "4000", "unit": "adet", "source": "user"},
        "yield_total": {"value": "31", "unit": "kg_agac", "source": "user"},
        "price": {"value": "19,00", "unit": "tl_kg", "source": "user"},
    }
    base.update(over)
    return base


def test_the_answer_restates_the_tree_count_it_used():
    """render's own docstring promises it "restates its inputs". A farmer who
    types 4000 where they meant 400 currently sees that mistake only inside a
    total they would have to divide by 31 to check."""
    inputs, errors = budget.validate(_fruit_payload())
    assert errors == []
    text = budget.render(inputs, budget.compute(inputs))
    assert "**4.000 ağaç**" in text
    assert text.startswith("Girdiğiniz değerlere göre: **10 dönüm**, "
                           "**4.000 ağaç**, toplam **124.000 kg**")


def test_a_tree_count_that_took_no_part_is_not_restated():
    """THE DISCRIMINATING CASE. The harvest is stated in kg, so the count
    multiplied nothing. Listing it under "Girdiğiniz değerlere göre" would name
    a figure that entered no arithmetic."""
    inputs, errors = budget.validate(_fruit_payload(
        yield_total={"value": "4000", "unit": "kg", "source": "user"}))
    assert errors == []
    assert inputs.trees is None
    assert "ağaç" not in budget.render(inputs, budget.compute(inputs))


def test_a_field_crop_answer_is_byte_identical_to_before():
    """185 of the 246 crops are not tree crops; their answer must not move by
    one character."""
    inputs, errors = budget.validate(_payload())
    assert errors == []
    text = budget.render(inputs, budget.compute(inputs))
    assert text.startswith(
        "Girdiğiniz değerlere göre: **10 dönüm**, toplam **4.000 kg** "
        "(dekara 400 kg), kilogram fiyatı **12,50 TL**.")
    assert "ağaç" not in text


def test_the_count_is_carried_only_for_a_per_tree_yield():
    """The flag on BudgetInputs, not just the rendered text."""
    assert budget.validate(_fruit_payload())[0].trees.amount == 4000.0
    assert budget.validate(_payload())[0].trees is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_budget.py -q -k "restates_the_tree_count or took_no_part or byte_identical_to_before or carried_only_for_a_per_tree"`

Expected: `test_the_answer_restates_the_tree_count_it_used` FAILS on the missing text, and `test_the_count_is_carried_only_for_a_per_tree_yield` FAILS with `AttributeError: 'BudgetInputs' object has no attribute 'trees'`. The other two PASS — they are guards, and their passing before the change is what makes them worth having after it.

- [ ] **Step 3: Write the implementation**

In `src/budget.py`, add the field to `BudgetInputs` immediately after `cost_tl`:

```python
    cost_tl: Value | None
    # The tree count, and ONLY when it actually multiplied the yield - that is,
    # when the harvest was submitted in a per-tree unit. A farmer can fill it in
    # and then state their harvest in kg, and naming it under "Şu değerlere
    # göre" would list a figure that entered no arithmetic.
    trees: Value | None = None
```

In `validate`, replace the `return BudgetInputs(...)`:

```python
    # Whether the count took part is a property of the UNIT the yield was
    # submitted in - the same `needs` the validator refuses on - so it is read
    # from there rather than restated.
    yield_unit = _chosen_unit(_FIELDS_BY_ID["yield_total"], raw)
    took_part = yield_unit is not None and yield_unit.needs == "tree_count"

    return BudgetInputs(
        area_da=values["area"],
        yield_kg=values["yield_total"],
        price_tl_kg=values["price"],
        cost_tl=values["cost"],
        trees=values["tree_count"] if took_part else None,
        crop=crop,
        crop_label=row.label if row is not None else None,
    ), []
```

In `render`, replace the `given` list's construction:

```python
    given = [f"**{format_qty(inputs.area_da.amount)} dönüm**"]
    if inputs.trees is not None:
        # Beside the area, because both are the farmer's own measurement of
        # their own orchard. Not inside the yield clause, which already carries
        # two figures - a third would bury the one they need to check.
        given.append(f"**{format_qty(inputs.trees.amount)} ağaç**")
    given.extend([
        f"toplam **{format_qty(inputs.yield_kg.amount)} kg** "
        f"(dekara {format_qty(result.yield_kg_da)} kg)",
        f"kilogram fiyatı **{format_tr(inputs.price_tl_kg.amount, 2)} TL**",
    ])
```

The `if result.cost_tl is not None: given.append(...)` that follows stays exactly where it is.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_budget.py -q`
Expected: all pass.

Run: `python -m pytest -q`
Expected: **1016 or more passed, 0 failed.**

The existing render tests use substring assertions rather than whole-string pins, so none should move. If one does, that is a real finding — stop and report it rather than adjusting it.

- [ ] **Step 5: Prove the "took part" condition is derived, not restated**

Temporarily blank `kg_agac`'s dependency in `FIELDS`: change `needs="tree_count"` to `needs=None` on that unit.

Run: `python -m pytest tests/test_budget.py -q -k "restates_the_tree_count or carried_only_for_a_per_tree"`
Expected: **FAIL** — with the unit no longer declaring the dependency, the count is not carried and the echo disappears.

Revert, re-run, confirm green. Without this the condition could have been written as `yield_unit.id == "kg_agac"` and no test would tell the difference.

- [ ] **Step 6: Read the answer out loud**

Run:

```bash
PYTHONPATH=. python -c "
from scripts._console import use_utf8_console; use_utf8_console()
from src import budget, norms
table = norms.province_table('Karabük')
for count in ('400', '4000'):
    p = {'area': {'value': '10', 'unit': 'donum', 'source': 'user'},
         'tree_count': {'value': count, 'unit': 'adet', 'source': 'user'},
         'yield_total': {'value': '31', 'unit': 'kg_agac', 'source': 'norm'},
         'price': {'value': '19,00', 'unit': 'tl_kg', 'source': 'user'},
         'crop': 'ayva'}
    i, e = budget.validate(p, table)
    print('='*70); print(budget.render(i, budget.compute(i)))
"
```

Read both answers. The count must appear, formatted, in the position the spec describes, and the sentence must still read as Turkish rather than a list of tokens. If the 4.000 version does not make the mistake visible at a glance, say so — that is the whole point of the round.

- [ ] **Step 7: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Restate the tree count the answer was already using"
```

---

## Self-Review

**Spec coverage:**

| spec requirement | task |
|---|---|
| `_chosen_unit` extracted, lookup exists once | 1 |
| `_chosen_unit` keeps both `None` cases `_read` already handled | 1 (two tests) |
| `_requires`'s lookup deliberately NOT merged | 1 (stated in the task's preamble) |
| `BudgetInputs.trees: Value | None = None` | 2 |
| carried only when the yield's unit `needs` the count | 2 |
| the condition derived from `needs`, not restated | 2 (Step 5 mutation) |
| echoed immediately after the area, before the yield clause | 2 (the `given` list's order, pinned by a `startswith`) |
| formatted with `format_qty` | 2 (`**4.000 ağaç**` in the expected text) |
| a tree count that took no part is not echoed | 2 (the discriminating test) |
| field-crop answer byte-identical | 2 |
| `compute()` untouched | no task modifies it |
| every sentence read against the printed answer | 2, Step 6 |

No gaps. The spec's out-of-scope list — the card, judging plausibility, `compute()` — is touched by no task.

**Placeholder scan:** every code step carries the actual code; every run step carries the actual command and its expected result. No TBD, no "handle edge cases", no "similar to Task N".

**Type consistency:** `_chosen_unit(spec, raw) -> UnitOption | None` is defined in Task 1 and called in Task 2 with the same argument shape. `BudgetInputs.trees` is named identically in Task 2's implementation and all four of its tests. `_payload` (field crop) and `_fruit_payload` (per-tree) are distinct helpers; `_payload` already exists in the test file.

**Every expected string was verified against the running code before this plan was committed**, not recalled: `format_qty` renders `4000.0` as `4.000`, `400.0` as `400`, `124000.0` as `124.000`; the current field-crop answer begins `Girdiğiniz değerlere göre: **10 dönüm**, toplam **4.000 kg** (dekara 400 kg), kilogram fiyatı **12,50 TL**.`; and `BudgetInputs` is constructed in exactly one place, with keywords. The fruit prediction was derived from today's real output rather than imagined — the same payload currently renders `Girdiğiniz değerlere göre: **10 dönüm**, toplam **124.000 kg** (dekara 12.400 kg), kilogram fiyatı **19,00 TL**.`, so inserting one item after the area gives exactly the string Task 2 pins. This plan's predicted values were wrong four times in recent rounds; these were measured.

**Two risks worth naming:**

1. **Task 1 is a refactor of a live code path**, and one that silently stopped resolving units would look identical to one that kept working — which is why Step 5 forces the lookup to misbehave and requires the suite to go red.
2. **Task 2's `startswith` assertions pin word order**, which is stricter than the rest of this file's substring style. That is deliberate: the spec places the count in a specific position, and a substring check would pass with it anywhere in the sentence.
