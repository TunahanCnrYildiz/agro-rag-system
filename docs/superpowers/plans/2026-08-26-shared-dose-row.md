# Shared Dose Row Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `HİGRO FERRY`'s field-crop growers the figure its page already publishes for them, by recording — as a reviewed data entry, not a wider regex — that one published sentence covers two crop groups.

**Architecture:** `data/dose_group_scope.json` gains a second reviewed section, `shared_rows`. `scripts/build_product_doses.py` copies the named source group's methods onto the named groups, guarded four ways so the copy can never silently widen. `src/doses.py`, the wire, the form and the client are untouched.

**Tech Stack:** Python 3.14 + pytest. No new dependencies, no network.

Spec: `docs/superpowers/specs/2026-08-26-shared-dose-row-design.md`
Branch point: `shared-dose-row` at `1f6d23e`, `pytest -q` = **896 passed**.

## Global Constraints

- **The copy is REVIEWED, never inferred.** No regex learns the coordination; a person read the panel and recorded what it covers, with the quote.
- **The guard against silent widening is the point.** `expect_methods` records what the reviewer saw; if the source group's method set ever differs, the converter RAISES so a human re-reads.
- **A stale review entry raises rather than sitting in the file looking like coverage** — the rule `dose_group_scope.json`'s existing `scope` section already follows.
- **An `also` group that already has its own row raises.** If the parser ever learns to read the coordination itself, this override must announce that it is now redundant rather than silently overwrite a published row.
- **`data/product_doses.json` is a GENERATED artifact**, reproducible by re-running the committed converter over the committed inputs. Hand-editing it is a defect.
- **The copied row is recorded in `meta`**, so a reader diffing the file can tell it was copied by review rather than published under its own heading.
- **No interface change:** `src/doses.py`'s functions and return types, the wire, the budget form and the mobile client are untouched, and **no new APK is needed**.
- Run everything from the repo root — `src/config.py` reads a relative `.env`.
- Commits: one per task, English, short and natural, **no `Co-Authored-By` trailer**.
- `pytest -q` green at the end of every task, starting from 896 passed.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `data/dose_group_scope.json` | **Modify.** Gains the `shared_rows` section with the one reviewed entry and its evidence. |
| `scripts/build_product_doses.py` | **Modify.** `build()` learns the `shared` argument, its four guards, and the copy; `main()` reads the new section and records it in `meta`. |
| `data/product_doses.json` | **Regenerate.** Gains `HİGRO FERRY`'s `tarla` row and a `meta.shared_rows` record. |
| `tests/test_build_product_doses.py` | **Modify.** The copy, the widening guard, the three staleness cases, inertness, and the real-data guards. |

---

## Task 1: The reviewed copy, and the four guards

**Files:**
- Modify: `data/dose_group_scope.json`, `scripts/build_product_doses.py`
- Test: `tests/test_build_product_doses.py`

**Interfaces:**
- Consumes: `src.dose_parse.GROUP_KEYS` (`("sebze", "meyve", "tarla")`), already imported by the converter.
- Produces: `build(panels, scope, shared=None)` — `shared` is `{product: {"from": str, "also": [str], "expect_methods": [str]}}`. **The return stays a 4-tuple**: `(table, unparsed, dropped, resolved_scope)`. Eleven existing call sites pass two arguments and must keep working.

- [ ] **Step 1: Read the panel before writing the review**

This step is the review. Run it and read the output:

```bash
PYTHONIOENCODING=utf-8 python -c "import json; from src.config import DATA_DIR; print(json.load(open(DATA_DIR/'raw'/'product_panels.json',encoding='utf-8'))['panels']['HİGRO FERRY'])"
```

Expected: a panel that says, twice, `Tek yıllık tarla ve endüstri bitkileri ile sebzelerde …`, once for `Yapraktan` (a dilution, `250-300 cc/100 Litre su`) and once for `To praktan` (`1000m² alana 1-2 litre`). Then check what ships today:

```bash
PYTHONIOENCODING=utf-8 python -c "from src import doses; [print(g, doses.lookup('HİGRO FERRY', g)) for g in ('sebze','meyve','tarla')]"
```

Expected: `sebze` → one `toprak` 1.0–2.0 litre dose; `meyve` → one `yaprak` 2.0–3.0 litre dose; `tarla` → `()`.

If what you read disagrees with the entry below, write what you actually read and say so in your report.

- [ ] **Step 2: Add the reviewed section**

In `data/dose_group_scope.json`, add a `shared_rows` key as a sibling of `scope` (keep `meta` and `scope` exactly as they are). Replace `reviewed_by` with whoever ran Step 1 if that is not the name already in `meta`.

```json
 "shared_rows": {
  "HİGRO FERRY": {
   "from": "sebze",
   "also": ["tarla"],
   "expect_methods": ["toprak"],
   "evidence": "Panel iki kez 'Tek yıllık tarla ve endüstri bitkileri ile sebzelerde ... 1000m² alana 1-2 litre' diyor. Cümle iki grubu birlikte sayıyor; dose_parse._segments yalnızca 'sebzelerde' üzerinden segment açtığı için tarla figürsüz kalıyor. Ölçüldü 2026-08-26: 48 panelin yalnızca bu birinde bir grup bu şekilde kayboluyor."
  }
 }
```

- [ ] **Step 3: Write the failing tests**

Append to `tests/test_build_product_doses.py`:

```python
SHARED_PANEL = {
    "PAYLAŞAN ÜRÜN": "Topraktan : Tek yıllık tarla ve endüstri bitkileri ile "
                     "sebzelerde 1000m² alana 1-2 litre uygulanır.",
}


def _shared(**overrides):
    entry = {"from": "sebze", "also": ["tarla"], "expect_methods": ["toprak"]}
    entry.update(overrides)
    return {"PAYLAŞAN ÜRÜN": entry}


def test_a_reviewed_shared_row_reaches_the_other_group():
    """The page counts field crops and vegetables in one sentence, but only
    'sebzelerde' opens a segment. The reviewed copy is what gives a field
    grower the figure the manufacturer already published for them."""
    table, _unparsed, _dropped, _scope = build(SHARED_PANEL, {}, _shared())
    rows = table["PAYLAŞAN ÜRÜN"]
    assert rows["tarla"] == rows["sebze"]
    assert rows["tarla"]["toprak"] == {"low": 1.0, "high": 2.0, "unit": "litre"}


def test_the_copied_row_is_not_the_same_object_as_its_source():
    """Sharing one dict between two groups means a later edit to one silently
    edits the other."""
    table, _u, _d, _s = build(SHARED_PANEL, {}, _shared())
    rows = table["PAYLAŞAN ÜRÜN"]
    assert rows["tarla"] is not rows["sebze"]
    assert rows["tarla"]["toprak"] is not rows["sebze"]["toprak"]


def test_a_source_group_that_grew_a_method_stops_the_build():
    """THE GUARD THAT MAKES THE REVIEW MEAN SOMETHING. A person approved this
    copy on the strength of ONE published sentence. If the page later gives
    that group a second figure, the copy must not silently widen - the build
    stops and a human re-reads."""
    with pytest.raises(ValueError, match="expect_methods"):
        build(SHARED_PANEL, {}, _shared(expect_methods=["damlama"]))


def test_a_shared_entry_for_a_product_that_does_not_ship_stops_the_build():
    with pytest.raises(ValueError, match="YOK ÜRÜN"):
        build(SHARED_PANEL, {}, {"YOK ÜRÜN": {"from": "sebze", "also": ["tarla"],
                                              "expect_methods": ["toprak"]}})


def test_a_shared_entry_whose_source_group_is_missing_stops_the_build():
    with pytest.raises(ValueError, match="meyve"):
        build(SHARED_PANEL, {}, _shared(**{"from": "meyve"}))


def test_a_shared_entry_targeting_a_group_that_already_ships_stops_the_build():
    """If the parser ever learns to read the coordination itself, this override
    becomes redundant and must SAY SO rather than overwrite a row the page
    published under its own heading."""
    with pytest.raises(ValueError, match="sebze"):
        build(SHARED_PANEL, {}, _shared(also=["sebze"]))


def test_a_shared_entry_naming_an_unknown_group_stops_the_build():
    with pytest.raises(ValueError, match="hububat"):
        build(SHARED_PANEL, {}, _shared(also=["hububat"]))


def test_no_shared_section_changes_nothing():
    """The default must be inert: an omitted argument may not copy anything."""
    plain, _u, _d, _s = build(SHARED_PANEL, {})
    assert "tarla" not in plain["PAYLAŞAN ÜRÜN"]
```

- [ ] **Step 4: Run them and watch them fail**

Run: `python -m pytest tests/test_build_product_doses.py -q`
Expected: FAIL — `TypeError: build() takes 2 positional arguments but 3 were given`.

- [ ] **Step 5: Teach the converter the shared row**

In `scripts/build_product_doses.py`, change `build`'s signature and extend its docstring:

```python
def build(panels: dict[str, str], scope: dict[str, list[str]],
          shared: dict | None = None
          ) -> tuple[dict, list[str], dict, dict]:
```

Add to the docstring, after the `scope` paragraph:

```
    `shared` is the second REVIEWED answer to the same kind of question: a
    page that publishes ONE figure for TWO groups in one sentence. HIGRO
    FERRY writes "Tek yillik tarla ve endustri bitkileri ILE sebzelerde ...
    1-2 litre", and _segments opens a segment on "sebzelerde" only, so field
    growers get nothing for a figure the maker published for them. Widening
    the `tarla` pattern to span intervening words was measured and refused -
    it swallows FERFORCE's "Tarla sebzelerinde", a VEGETABLE sub-case - so
    the coverage is recorded by a person instead, with the sentence quoted.
    Measured 2026-08-26: exactly one of the 48 panels loses a group this way.
```

Then insert this block immediately before the final `return` (after the existing `scope` gates, so an unreviewed `hepsi` row is still reported first):

```python
    for name, entry in (shared or {}).items():
        rows = table.get(name)
        if rows is None:
            raise ValueError(
                f"data/dose_group_scope.json shares a row for {name!r}, which "
                f"ships no dose at all - a review of nothing, sitting in the "
                f"file looking like coverage")
        source = entry["from"]
        if source not in rows:
            raise ValueError(
                f"{name}: reviewed to share its {source!r} row, but it ships no "
                f"{source!r} row - the panel changed under the review")
        # THE GUARD THAT MAKES THE REVIEW MEAN SOMETHING. A person approved this
        # copy on the strength of one published sentence, and recorded which
        # methods that sentence produced. If the page later gives the source
        # group another figure, copying it too would widen a row nobody
        # approved - so the build stops and a human re-reads the panel.
        found, expected = sorted(rows[source]), sorted(entry["expect_methods"])
        if found != expected:
            raise ValueError(
                f"{name}: its {source!r} row now carries {found}, but the review "
                f"in data/dose_group_scope.json recorded expect_methods "
                f"{expected}. Re-read the panel and update the entry rather "
                f"than shipping a copy nobody approved")
        for group in entry["also"]:
            if group not in GROUP_KEYS:
                raise ValueError(
                    f"{name}: shared to {group!r}, which is not a group we "
                    f"publish (known: {list(GROUP_KEYS)})")
            if group in rows:
                raise ValueError(
                    f"{name}: shared to {group!r}, which already ships its own "
                    f"row. If the parser learned to read this page itself, the "
                    f"entry is redundant - delete it rather than overwrite a "
                    f"published row")
            # A fresh dict per method: two groups sharing one mapping means a
            # later edit to either silently edits both.
            rows[group] = {method: dict(dose)
                           for method, dose in rows[source].items()}
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_build_product_doses.py -q`
Expected: PASS, including every pre-existing test in the file — the eleven two-argument `build(...)` call sites must be untouched.

- [ ] **Step 7: Wire `main()` and record the copy in `meta`**

In `main()`, read the new section next to the existing one:

```python
    scope = {name: entry["groups"] for name, entry in review["scope"].items()}
    shared = review.get("shared_rows", {})
    table, unparsed, conflicts, resolved = build(raw["panels"], scope, shared)
```

Add the record to `meta`, beside `unparsed` and `dropped_slots` — the finding travels with the file:

```python
                  "unparsed": unparsed,
                  "dropped_slots": conflicts,
                  # Which rows were COPIED by review rather than published
                  # under their own heading. Without this a reader diffing the
                  # file cannot tell the two apart.
                  "shared_rows": {name: {"from": e["from"], "also": list(e["also"])}
                                  for name, e in shared.items()},
```

And print it, in the loud style the rest of `main()` uses, after the `resolved` block:

```python
    if shared:
        print(f"[doses] {len(shared)} reviewed shared row(s):")
        for name, entry in shared.items():
            print(f"          {name}: {entry['from']} -> {', '.join(entry['also'])}")
```

- [ ] **Step 8: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS. `tests/test_build_product_doses.py::test_the_shipped_file_is_what_the_converter_produces` will FAIL at this point — it rebuilds with two arguments while `main()` now passes three, so the rebuilt table lacks the shared row. **That is expected and Task 2 fixes it**; if any OTHER test fails, stop and report.

- [ ] **Step 9: Commit**

```bash
git add data/dose_group_scope.json scripts/build_product_doses.py tests/test_build_product_doses.py && git commit -m "Share a reviewed dose row with the group its page names alongside"
```

---

## Task 2: Regenerate, and guard the real data

**Files:**
- Regenerate: `data/product_doses.json`
- Test: `tests/test_build_product_doses.py`

- [ ] **Step 1: Regenerate**

Run:

```bash
python -m scripts.build_product_doses
```

Expected: the existing report, plus a new line reading `1 reviewed shared row(s):` and `HİGRO FERRY: sebze -> tarla`. The product count stays **40 of 48** — this copies a row onto an existing product, it does not add one.

- [ ] **Step 2: Read the diff before trusting it**

Run:

```bash
git diff --stat data/product_doses.json
```

Then check by hand that exactly one product gained exactly one group:

```bash
PYTHONIOENCODING=utf-8 python -c "
import json
from src.config import DATA_DIR
import subprocess
new = json.loads((DATA_DIR/'product_doses.json').read_text(encoding='utf-8'))
old = json.loads(subprocess.run(['git','show','HEAD:data/product_doses.json'],
                                capture_output=True, text=True, encoding='utf-8').stdout)
for name in sorted(set(new['products']) | set(old['products'])):
    a, b = old['products'].get(name, {}), new['products'].get(name, {})
    if a != b:
        print(name, 'BEFORE', sorted(a), '-> AFTER', sorted(b))
print('meta.shared_rows =', new['meta'].get('shared_rows'))
"
```

Expected: exactly one line — `HİGRO FERRY BEFORE ['meyve', 'sebze'] -> AFTER ['meyve', 'sebze', 'tarla']` — and the `meta.shared_rows` record. If any other product changed, stop and report.

- [ ] **Step 3: Fix the reproducibility test and add the real-data guards**

`test_the_shipped_file_is_what_the_converter_produces` currently rebuilds with two arguments. It must rebuild the way `main()` builds, or it proves the file was generated by a different code path than the one that ships. Update its body to read the new section too:

```python
def test_the_shipped_file_is_what_the_converter_produces():
    """Re-run the committed converter over the committed raw panels and diff
    against the committed output. This is the check that proves the data file
    was generated, not hand-edited - the one P2a's final review ran by hand.

    It must build the way main() builds, INCLUDING the reviewed shared rows:
    rebuilding without them would compare the shipped file against a table the
    shipping code never produces, and pass only by accident."""
    from src.config import DATA_DIR
    raw = json.loads((DATA_DIR / "raw" / "product_panels.json").read_text(encoding="utf-8"))
    review = json.loads((DATA_DIR / "dose_group_scope.json").read_text(encoding="utf-8"))
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    scope = {n: e["groups"] for n, e in review["scope"].items()}
    rebuilt, _, _, rebuilt_scope = build(raw["panels"], scope,
                                         review.get("shared_rows", {}))
    assert rebuilt == shipped["products"]
    assert rebuilt_scope == shipped["all_groups_scope"]
```

Then append the real-data guards:

```python
def test_the_shipped_file_gives_ferry_its_field_crop_figure():
    """The whole point, on the real data: the page publishes 1-2 litre for
    field crops and vegetables in one sentence, and a field grower now gets it."""
    from src import doses
    found = doses.lookup("HİGRO FERRY", "tarla")
    assert len(found) == 1
    assert (found[0].low, found[0].high, found[0].unit, found[0].method) == (
        1.0, 2.0, "litre", "toprak")


def test_ferrys_other_groups_did_not_move():
    """A copy onto one group must not disturb the two that were already right."""
    from src import doses
    sebze = doses.lookup("HİGRO FERRY", "sebze")
    meyve = doses.lookup("HİGRO FERRY", "meyve")
    assert len(sebze) == 1 and (sebze[0].low, sebze[0].high, sebze[0].unit,
                                sebze[0].method) == (1.0, 2.0, "litre", "toprak")
    assert len(meyve) == 1 and (meyve[0].low, meyve[0].high, meyve[0].unit,
                                meyve[0].method) == (2.0, 3.0, "litre", "yaprak")


def test_the_shipped_file_records_which_rows_were_copied():
    """A reader diffing the file must be able to tell a copied row from one the
    page published under its own heading."""
    from src.config import DATA_DIR
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    assert shipped["meta"]["shared_rows"] == {
        "HİGRO FERRY": {"from": "sebze", "also": ["tarla"]}}
```

- [ ] **Step 4: Run everything**

Run: `python -m pytest -q`
Expected: PASS — 896 plus the tests added in Task 1 and this one, no failures.

- [ ] **Step 5: Check what the dose route now answers**

The route is the reason this work exists; look at it rather than assuming.

```bash
PYTHONIOENCODING=utf-8 python -c "
from src import dose_answer as d
i, errs = d.validate({'product': 'HİGRO FERRY', 'group': 'tarla',
                      'area': {'value': '5', 'unit': 'donum'}})
print('errors:', errs)
print(d.render(i, d.compute(i)))"
```

Expected: no errors, and an answer stating the published `1–2 litre` per dekar, `5–10 litre` for five dönüm, with the manufacturer attribution and the per-application sentence. Read it as a farmer would and paste it into your report; before this change the same call produced the "elimde okunabilir bir dekar dozu yok" refusal.

- [ ] **Step 6: Commit**

```bash
git add data/product_doses.json tests/test_build_product_doses.py && git commit -m "Regenerate the dose table with Ferry's shared field-crop row"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Where |
| --- | --- |
| §1 the measurement, and that today's answer is not a lie | Task 1 Step 1 re-reads the panel; the evidence string records the measurement |
| §2 why not the parser | Task 1 Step 5's docstring addition |
| §3 the review lives in `dose_group_scope.json` | Task 1 Step 2 |
| §4 the copy and the `expect_methods` guard | Task 1 Steps 3, 5 |
| §5 staleness, three ways | Task 1 Step 3 (three tests) + Step 5 (three raises), plus the unknown-group raise |
| §6 applied in the converter, recorded in `meta` | Task 1 Steps 5, 7 |
| §7 the answer says nothing extra | Nothing in this plan touches `src/dose_answer.py`; Task 2 Step 5 reads the unchanged wording |
| §8 the whole testing table | Tasks 1-2 |
| §9 out of scope | Not built |

**Placeholder scan:** none — every step carries its code, its command and its expected output.

**Type consistency:** `build(panels, scope, shared=None)` is called with two arguments by eleven pre-existing tests and with three by `main()` and the new tests; the entry keys `from` / `also` / `expect_methods` / `evidence` are written in Step 2 and read in Steps 5 and 7 and in Task 2's meta test; the return stays a 4-tuple throughout.

**One risk this plan does not remove:** `meta.shared_rows` is written by `main()` from the review file rather than returned by `build()`, so in principle the record could describe a copy that `build` refused to make. In practice it cannot — every refusal is a `raise`, so `main()` never reaches the write — and it matches the existing precedent, where `resolved` is likewise an echo of `build`'s own input. Task 2 Step 3's `test_the_shipped_file_records_which_rows_were_copied` pins the record against the shipped file, and the reproducibility test pins the file against the converter.
