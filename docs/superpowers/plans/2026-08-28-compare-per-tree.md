# Crop Comparison, Per-Tree Fruit Yield — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `src/crop_compare.py` printing the unsound derived `kg/da` for the 61 tree crops; print TÜİK's published `kg/ağaç` instead and compute no money figure for them.

**Architecture:** `_figures` picks the measure per row using the identical test `budget._yield_cell` uses (`row.yield_kg_tree is not None`). `CropFigures` gains a `per_tree` flag; `revenue_tl_da` is `None` whenever it is set. `_crop_block` grows a per-tree branch ahead of the missing-price branch, and `render` tightens the `NOT_PROFIT` gate from "either crop" to "both crops" while adding one sentence for the mixed case. No data file, no builder, no client, no router change.

**Tech Stack:** Python 3.14, pytest, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-28-compare-per-tree-design.md`

## Global Constraints

- Run every command from the repo root. `src/config.py` reads a RELATIVE `env_file=".env"`; running elsewhere silently loads a wrong `EMBEDDING_MODEL`.
- **The model performs no arithmetic and makes no appearance in this route.** Every number and every sentence a user sees here is written by Python.
- **A field-or-vegetable pair must render byte-identically to today.** A regression test pins this rather than trusting it.
- A missing norm is never zero. Absence is `None` throughout.
- **Never let a code-written sentence describe something the answer did not print.** This route has shipped two fixes for exactly that, both caught by reading the output out loud.
- Turkish user-facing strings only, matching the existing voice. Never claim to be a licensed Ziraat Mühendisi.
- Commit messages: short, natural, English, no `Co-Authored-By` trailer.
- `python -m pytest -q` must be green (954 tests at plan time) before every commit.
- Out of scope: `data/crop_norms.json`, `scripts/build_crop_norms.py`, the four density rules, `src/router.py`, `src/budget.py`, `mobile-app/`.

---

### Task 1: `_figures` reads the measure the row carries

**Files:**
- Modify: `src/crop_compare.py` — the `CropFigures` dataclass and `_figures`
- Test: `tests/test_crop_compare.py`

**Interfaces:**
- Consumes: `src.norms.CropNorm`, whose fields are, in order, `crop, label, yield_kg_da, price_tl_kg, yield_kg_tree` (the last defaulted to `None`).
- Produces: `CropFigures(label, yield_value, price_value, revenue_tl_da, missing, per_tree=False)`. Later tasks read `.per_tree` and rely on `.revenue_tl_da is None` whenever it is `True`.

- [ ] **Step 1: Add two tree crops to the test fixture**

In `tests/test_crop_compare.py`, inside the `TABLE["crops"]` dict, add these two entries after the existing `"kara bugday"` entry. Ayva's `yield_kg_da` is deliberately an implausible quince figure so later tests can assert it never reaches the page:

```python
        "ayva": {
            "label": "Ayva",
            "yield_kg_da": {"scope": "il", "Konya": [8000.0, 8500.0, 9000.0, 9500.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [11.0, 14.0, 16.0, 19.0],
                            "TR": [None, None, None, None]},
            "yield_kg_tree": {"scope": "il", "Konya": [25.0, 27.0, 28.0, 31.0],
                              "TR": [None, None, None, None]},
        },
        "ceviz": {
            "label": "Ceviz",
            "yield_kg_da": {"scope": "il", "Konya": [250.0, 255.0, 260.0, 263.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [80.0, 90.0, 100.0, 110.0],
                            "TR": [None, None, None, None]},
            "yield_kg_tree": {"scope": "il", "Konya": [18.0, 19.0, 20.0, 22.0],
                              "TR": [None, None, None, None]},
        },
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_crop_compare.py`, immediately before `def test_the_answer_prints_both_crops_with_their_figures():`

```python
def _figures_for(crop_id, latest_year=2025):
    row = next(r for r in _table() if r.crop == crop_id)
    return crop_compare._figures(row, latest_year)


def test_a_tree_crop_is_read_from_its_published_per_tree_measure():
    """TUIK publishes no per-dekar yield for 61 tree crops. The kg/da this
    project derives for them divides a province's whole production by the few
    dekars of COMPACT orchard it records, so Karabuk/Ayva ships 13.419 kg/da -
    about four times any real quince yield."""
    figures = _figures_for("ayva")
    assert figures.per_tree is True
    assert figures.yield_value.amount == 31.0


def test_a_tree_crop_gets_no_revenue_figure():
    """There is no honest money figure for it: converting per-tree to per-dekar
    needs a planting density nobody published, and revenue per TREE is not a
    fair comparison either - crop median densities run 11 to 79 trees/da."""
    assert _figures_for("ayva").revenue_tl_da is None


def test_a_field_crop_is_untouched_and_still_carries_its_revenue():
    figures = _figures_for("domates (sofralik)")
    assert figures.per_tree is False
    assert figures.yield_value.amount == 5492.1
    assert figures.revenue_tl_da == 5492.1 * 21.06


def test_a_tree_crop_never_blames_the_price_for_the_missing_revenue():
    """`missing == "fiyat"` renders "there is a yield but no price, so I am not
    computing revenue". On a per-tree row that states a false cause - the
    revenue was refused for the UNIT - and invites the reader to think a price
    would fix it."""
    figures = _figures_for("ayva", latest_year=2099)
    assert figures.price_value is None
    assert figures.missing is None
    assert figures.per_tree is True


def test_a_genuine_absence_still_reports_itself():
    """per_tree must not swallow a real gap. A row carrying neither measure is
    a missing yield, not a per-tree crop."""
    from dataclasses import replace
    row = next(r for r in _table() if r.crop == "ayva")
    figures = crop_compare._figures(
        replace(row, yield_kg_da=None, yield_kg_tree=None), 2025)
    assert figures.per_tree is False
    assert figures.missing == "verim"


def test_the_two_surfaces_choose_the_same_measure_for_the_same_row():
    """THE TEST THAT STOPS THEM DRIFTING AGAIN. src/budget.py and this module
    each decide which measure to serve; they disagreed on 1.568 cells for one
    round, and Karabuk/Ayva prefilled 31 kg/agac in the form while the
    comparison printed 13.419 kg/da."""
    from src import budget
    for row in _table():
        cell = budget._yield_cell(row)
        chose_per_tree = cell is not None and cell["unit"] == "kg_agac"
        assert crop_compare._figures(row, 2025).per_tree == chose_per_tree, row.label
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_crop_compare.py -q -k "per_tree_measure or no_revenue_figure or untouched_and_still or never_blames or genuine_absence or same_measure"`

Expected: FAIL. Most fail with `AttributeError: 'CropFigures' object has no attribute 'per_tree'`. `test_a_field_crop_is_untouched_and_still_carries_its_revenue` fails on the same attribute. Note which fail and why before continuing.

- [ ] **Step 4: Write the implementation**

In `src/crop_compare.py`, add the field to `CropFigures` (it goes last, with a default, so the existing constructions keep working):

```python
    label: str
    yield_value: object | None       # norms.NormValue
    price_value: object | None
    revenue_tl_da: float | None
    missing: str | None
    # TUIK publishes this crop's yield per TREE, so no per-dekar money figure
    # exists for it. NOT folded into `missing`: that field names the half we do
    # not HOLD, and here both halves are held and cannot be combined.
    per_tree: bool = False
```

Replace the body of `_figures`:

```python
def _figures(row, latest_year: int | None) -> CropFigures:
    # A row is served PER TREE exactly when its yield_kg_tree resolved - the
    # same test, character for character, that src/budget.py's _yield_cell
    # uses. The two surfaces decide this separately and disagreed on 1.568
    # cells for a round; a test pins them together.
    per_tree = row.yield_kg_tree is not None
    yield_value = row.yield_kg_tree if per_tree else row.yield_kg_da
    price = row.price_tl_kg
    # A price from an older year is not a smaller number, it is a different
    # currency: P2b measured Ordu's `Arpa (Diğer)` prefilling a 2018 price nine
    # times too low into a bold revenue figure. Yield is left alone - it does
    # not inflate, and its five-year range is where an outlier shows.
    if price is not None and (latest_year is None or price.year != latest_year):
        price = None
    missing = None
    if yield_value is None:
        missing = "verim"
    elif price is None and not per_tree:
        # A per-tree row never blames the PRICE for its missing revenue. That
        # branch's message is "there is a yield but no price, so I am not
        # computing revenue", which here names a false cause - the revenue was
        # refused for the unit - and suggests a price would fix it.
        missing = "fiyat"
    revenue = (None if (missing is not None or per_tree)
               else yield_value.amount * price.amount)
    return CropFigures(label=row.label, yield_value=yield_value,
                       price_value=price, revenue_tl_da=revenue,
                       missing=missing, per_tree=per_tree)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_crop_compare.py -q`

Expected: the six new tests pass and NOTHING ELSE MOVES.

This was measured before the plan was written: the two fixture crops were added to
`tests/test_crop_compare.py` on their own and `tests/test_crop_compare.py` plus
`tests/test_compare_route.py` ran **42 passed**. No existing test enumerates the crop
list, and neither `ayva` nor `ceviz` occurs inside any message those tests use.

Then run the whole suite: `python -m pytest -q` — expect **954 or more passed, 0 failed**.
A red test here is a real problem, not an expected intermediate state: your tests call
`_figures` directly and never render, so nothing reaches `_crop_block` with a per-tree
row yet. If something is red, STOP and report rather than pressing on to Task 2.

- [ ] **Step 6: Commit**

```bash
git add src/crop_compare.py tests/test_crop_compare.py
git commit -m "Read a tree crop's yield from the measure TUIK publishes"
```

---

### Task 2: `_crop_block` renders the per-tree crop

**Files:**
- Modify: `src/crop_compare.py` — a new module constant and `_crop_block`
- Test: `tests/test_crop_compare.py`

**Interfaces:**
- Consumes: `CropFigures.per_tree` from Task 1.
- Produces: `crop_compare.PER_TREE_NOTE`, a module-level string, referenced by Task 3's tests.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_crop_compare.py`, after the tests added in Task 1:

```python
def _render(first, second, latest_year=2025):
    inputs, errors = crop_compare.validate(_raw(first, second), _table())
    assert errors == []
    return crop_compare.render(
        inputs, crop_compare.compute(inputs, _table(), latest_year))


def test_a_tree_crop_prints_its_published_unit_and_never_the_derived_figure():
    text = _render("ayva", "domates (sofralik)")
    assert "31 kg/ağaç" in text
    assert "9.500" not in text and "kg/da" not in text.split("Domates")[0]


def test_a_tree_crop_carries_the_sentence_explaining_the_missing_revenue():
    text = _render("ayva", "domates (sofralik)")
    assert crop_compare.PER_TREE_NOTE in text


def test_a_tree_crops_price_is_joined_with_a_comma_not_a_times_sign():
    """`×` announces a product, and there is none - the revenue was refused."""
    text = _render("ayva", "domates (sofralik)")
    line = next(l for l in text.splitlines() if l.startswith("**Ayva**"))
    assert "fiyat 19,00 TL/kg" in line and "×" not in line


def test_a_tree_crops_five_year_range_reads_in_its_own_unit():
    text = _render("ayva", "domates (sofralik)")
    assert "verimde önceki 5 yıl: 25–28 kg/ağaç" in text


def test_a_tree_crop_with_no_current_price_drops_the_price_and_keeps_the_rest():
    """One absence, one reason. Naming the price too would suggest supplying
    one restores a revenue this route will not compute either way."""
    text = _render("ayva", "ceviz", latest_year=2099)
    line = next(l for l in text.splitlines() if l.startswith("**Ayva**"))
    assert "fiyat" not in line
    assert "31 kg/ağaç" in line
    assert crop_compare.PER_TREE_NOTE in text
    assert "gelir hesaplamıyorum." not in text.replace(
        crop_compare.PER_TREE_NOTE, "")


def test_a_field_crops_block_is_byte_identical_to_before():
    """The regression that matters: 185 of the 246 crops are not tree crops and
    their answer must not move by one character."""
    text = _render("domates (sofralik)", "biber (salcalik, kapya)")
    assert text.splitlines()[2] == (
        "**Domates (Sofralık)** · dekara brüt gelir **115.664 TL**")
    assert text.splitlines()[3] == (
        "   verim 5.492,1 kg/da (TÜİK 2025, Konya) × fiyat 21,06 TL/kg (TÜİK 2025)")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_crop_compare.py -q -k "published_unit_and_never or sentence_explaining or comma_not_a_times or own_unit or no_current_price_drops or byte_identical"`

Expected: FAIL — `AttributeError: module 'src.crop_compare' has no attribute 'PER_TREE_NOTE'` on several, and a `kg/da` yield line on the others.

- [ ] **Step 3: Write the implementation**

In `src/crop_compare.py`, add the constant next to `NOT_PROFIT` (keep it beside the other code-written sentences, not next to the function):

```python
# Written BY CODE and printed under the crop it explains, never at the foot of
# the answer - a reader must not have to work out which crop it refers to.
PER_TREE_NOTE = (
    "TÜİK bu ürünün verimini ağaç başına yayımlıyor; dekara çevirmek "
    "yayımlanmayan bir dikim sıklığı gerektirdiği için dekara gelir "
    "hesaplamıyorum."
)
```

Replace `_crop_block`:

```python
def _crop_block(figures: CropFigures) -> list[str]:
    """One crop's lines. Says what is missing rather than printing a blank.

    BRANCH ORDER IS LOAD-BEARING. A genuine absence outranks everything; then
    the per-tree case; only then a missing price. Testing the price first would
    tell a per-tree crop's reader that a price is what stands between them and
    a revenue figure, which is false.
    """
    if figures.missing == "verim":
        return [f"**{figures.label}**: bu il için yayımlanmış verim rakamı yok."]

    if figures.per_tree:
        y = figures.yield_value
        head = (f"**{figures.label}**: verim {format_qty(y.amount)} kg/ağaç "
                f"(TÜİK {y.year}, {y.region})")
        if figures.price_value is not None:
            # A comma, not the revenue line's `×`: that sign announces a
            # product, and this route computes none for a per-tree crop.
            head += (f", fiyat {format_tr(figures.price_value.amount, 2)} TL/kg "
                     f"(TÜİK {figures.price_value.year})")
        lines = [head]
        if y.recent_min is not None and y.recent_max is not None:
            lines.append(f"   verimde önceki 5 yıl: {format_qty(y.recent_min)}–"
                         f"{format_qty(y.recent_max)} kg/ağaç")
        lines.append(f"   {PER_TREE_NOTE}")
        return lines

    if figures.missing == "fiyat":
        return [f"**{figures.label}**: verim {format_qty(figures.yield_value.amount)} "
                f"kg/da (TÜİK {figures.yield_value.year}, {figures.yield_value.region}), "
                f"ancak güncel yıl için yayımlanmış fiyat yok, bu yüzden gelir "
                f"hesaplamıyorum."]

    y, p = figures.yield_value, figures.price_value
    lines = [
        # Whole lira: a gross revenue per dekar in the hundred-thousands does
        # not gain anything from kurus, and the extra digits read as precision
        # a provincial average does not have.
        f"**{figures.label}** · dekara brüt gelir "
        f"**{format_tr(figures.revenue_tl_da, 0)} TL**",
        f"   verim {format_qty(y.amount)} kg/da (TÜİK {y.year}, {y.region}) × "
        f"fiyat {format_tr(p.amount, 2)} TL/kg (TÜİK {p.year})",
    ]
    if y.recent_min is not None and y.recent_max is not None:
        lines.append(f"   verimde önceki 5 yıl: {format_qty(y.recent_min)}–"
                     f"{format_qty(y.recent_max)} kg/da")
    return lines
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_crop_compare.py -q`

Expected: all pass. Your tests here do not assert anything about the closing sentences,
so `render`'s gating — which Task 3 changes — cannot affect them.

Then run the whole suite: `python -m pytest -q` — expect **954 or more passed, 0 failed**.
If something is red, STOP and report.

- [ ] **Step 5: Commit**

```bash
git add src/crop_compare.py tests/test_crop_compare.py
git commit -m "Print a tree crop in the unit its yield is published in"
```

---

### Task 3: `render` gates the two closing sentences on what it actually printed

**Files:**
- Modify: `src/crop_compare.py` — a new module constant and `render`
- Test: `tests/test_crop_compare.py`

**Interfaces:**
- Consumes: `CropFigures.per_tree` (Task 1) and `PER_TREE_NOTE` (Task 2).
- Produces: `crop_compare.ONLY_ONE_REVENUE`, a module-level string.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_crop_compare.py`, after the tests added in Task 2:

```python
def test_not_profit_needs_both_crops_to_have_shown_a_revenue():
    """It refuses a RANKING - "kârlılık sıralamasını bu tablodan söyleyemem".
    With one figure there is no ranking to refuse and the sentence points at
    something the page does not contain. This route already shipped that fix
    once, for the case where NEITHER crop could show a revenue."""
    text = _render("ayva", "domates (sofralik)")
    assert crop_compare.NOT_PROFIT not in text


def test_not_profit_still_appears_for_two_field_crops():
    text = _render("domates (sofralik)", "biber (salcalik, kapya)")
    assert crop_compare.NOT_PROFIT in text


def test_a_lone_revenue_beside_a_tree_crop_says_it_is_not_a_comparison():
    """Otherwise the single money figure reads as a default winner."""
    text = _render("ayva", "domates (sofralik)")
    assert crop_compare.ONLY_ONE_REVENUE in text


def test_two_tree_crops_get_no_closing_sentence_at_all():
    """No revenue anywhere, so neither closing sentence has anything to
    describe. Both would name figures the answer never printed."""
    text = _render("ayva", "ceviz")
    assert crop_compare.NOT_PROFIT not in text
    assert crop_compare.ONLY_ONE_REVENUE not in text
    assert text.count(crop_compare.PER_TREE_NOTE) == 2


def test_a_lone_revenue_beside_a_plain_gap_says_nothing_extra():
    """THE CONDITION'S LOAD-BEARING HALF. A crop can lack a revenue because the
    province publishes nothing for it, and ONLY_ONE_REVENUE would then assert a
    per-tree reason that is simply untrue. Its own block already says what is
    missing."""
    from dataclasses import replace
    rows = {r.crop: r for r in _table()}
    blank = replace(rows["biber (salcalik, kapya)"],
                    yield_kg_da=None, yield_kg_tree=None)
    figures = (crop_compare._figures(rows["domates (sofralik)"], 2025),
               crop_compare._figures(blank, 2025))
    inputs, _ = crop_compare.validate(
        _raw("domates (sofralik)", "biber (salcalik, kapya)"), _table())
    text = crop_compare.render(inputs, figures)
    assert crop_compare.ONLY_ONE_REVENUE not in text
    assert crop_compare.NOT_PROFIT not in text
    assert "bu il için yayımlanmış verim rakamı yok" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_crop_compare.py -q -k "not_profit_needs_both or still_appears_for_two_field or lone_revenue_beside_a_tree or two_tree_crops_get_no or lone_revenue_beside_a_plain"`

Expected: FAIL — `AttributeError: module 'src.crop_compare' has no attribute 'ONLY_ONE_REVENUE'`, and `NOT_PROFIT` present where the tests say it must be absent.

- [ ] **Step 3: Write the implementation**

In `src/crop_compare.py`, add the constant immediately after `NOT_PROFIT`:

```python
# Only when one crop showed a revenue AND the other is per-tree. A crop can
# also lack a revenue because the province publishes nothing for it, and this
# sentence would then assert a per-tree reason that is untrue - the failure
# this route has already shipped two fixes for.
ONLY_ONE_REVENUE = (
    "Bu tabloda tek bir gelir rakamı var, dolayısıyla bir karşılaştırma değil: "
    "diğer ürünün verimi ağaç başına yayımlandığı için aynı birime "
    "getirilemiyor."
)
```

Replace the tail of `render` — everything from `lines.append(ATTRIBUTION)` to the `return`:

```python
    lines.append(ATTRIBUTION)
    revenues = [crop.revenue_tl_da is not None for crop in figures]
    if all(revenues):
        lines.extend(["", NOT_PROFIT])
    elif any(revenues) and any(crop.per_tree for crop in figures):
        lines.extend(["", ONLY_ONE_REVENUE])
    return "\n".join(lines)
```

Update `render`'s docstring — the paragraph beginning "NOT_PROFIT opens with" describes the old `any` gate. Replace that paragraph with:

```
    NOT_PROFIT opens with "these figures ARE gross revenue" and goes on to
    refuse a RANKING, so it needs BOTH crops to have printed one. With a single
    figure there is nothing to rank and the sentence describes a page that does
    not exist; with none it names figures that were never printed.

    ONLY_ONE_REVENUE covers the case NOT_PROFIT no longer does - one revenue
    beside a per-tree crop - and stops the lone money figure reading as a
    default winner.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_crop_compare.py -q`
Expected: all pass, including every test carried over from Tasks 1 and 2.

Run: `python -m pytest -q`
Expected: **954 or more passed, 0 failed.**

- [ ] **Step 5: Read the answers out loud**

Run:

```bash
PYTHONPATH=. python -c "
from scripts._console import use_utf8_console; use_utf8_console()
import json, tempfile, pathlib
from src import norms, crop_compare
import tests.test_crop_compare as t
p = pathlib.Path(tempfile.mkdtemp()) / 'crop_norms.json'
p.write_text(json.dumps(t.TABLE, ensure_ascii=False), encoding='utf-8')
norms._PATH = p; norms._load.cache_clear(); crop_compare._families.cache_clear()
table = norms.province_table('Konya')
for a, b in (('ayva','domates (sofralik)'), ('ayva','ceviz'),
             ('domates (sofralik)','biber (salcalik, kapya)')):
    i, e = crop_compare.validate({'first': a, 'second': b}, table)
    print('='*70); print(crop_compare.render(i, crop_compare.compute(i, table, 2025)))
"
```

Read each of the three answers sentence by sentence and check that **every closing sentence describes figures that actually appear above it**. This route has shipped two fixes for exactly that defect and both were caught here, not by a test. If a sentence describes something the answer did not print, stop and report it.

- [ ] **Step 6: Commit**

```bash
git add src/crop_compare.py tests/test_crop_compare.py
git commit -m "Gate both closing sentences on the revenues actually printed"
```

---

## Self-Review

**Spec coverage:**

| spec requirement | task |
|---|---|
| `_figures` reads per-tree exactly when `yield_kg_tree` resolved | 1 |
| `CropFigures.per_tree`, `missing` not overloaded | 1 |
| `revenue_tl_da` is `None` for every per-tree row | 1 |
| price freshness gate unchanged | 1 (kept verbatim in the rewritten `_figures`) |
| a per-tree row never reports `missing == "fiyat"` | 1 |
| cross-surface agreement with `budget._yield_cell` | 1 |
| per-tree block: unit, comma not `×`, range in `kg/ağaç`, explanation under the crop | 2 |
| branch order `verim` → `per_tree` → `fiyat` → revenue | 2 |
| stale price drops the clause and gives no second reason | 2 |
| field-crop block byte-identical | 2 |
| `NOT_PROFIT` requires both revenues | 3 |
| `ONLY_ONE_REVENUE`, gated on the other crop being per-tree | 3 |
| a plain gap gets no `ONLY_ONE_REVENUE` | 3 |
| every code-written sentence read out loud against the printed answer | 3, Step 5 |
| `named_crops`, `_families`, card, router, `compute`, `ATTRIBUTION` untouched | no task modifies them; the suite pins them |

No gaps.

**Placeholder scan:** every code step carries the actual code; every run step carries the actual command and its expected output. No TBD, no "handle edge cases", no "similar to Task N".

**Type consistency:** `CropFigures.per_tree` is named identically in Tasks 1, 2 and 3. `PER_TREE_NOTE` is defined in Task 2 and used in Task 2's implementation and Task 3's tests. `ONLY_ONE_REVENUE` is defined in Task 3 before its only use. `_render(first, second, latest_year=2025)` and `_figures_for(crop_id, latest_year=2025)` are defined once each (Tasks 2 and 1) and reused later.

**One risk, and it was measured away.** Task 1 adds two crops to a shared fixture, so
tests elsewhere in that file could have moved. Checked before writing this plan by applying
the fixture entries alone and running `tests/test_crop_compare.py tests/test_compare_route.py`:
**42 passed**, then reverted. No test enumerates the crop list, and neither name occurs
inside any message the existing tests use.

**Every task leaves the suite green**, and each Step tells the implementer to stop and
report if it does not. Task 1's tests call `_figures` directly and never render, so no
per-tree row reaches `_crop_block` before Task 2 teaches it the case; Task 2's tests assert
nothing about the closing sentences, so Task 3's gating change cannot reach back into them.
The green-before-every-commit constraint therefore holds at every commit, with no
deliberately-red intermediate state.
