# Collapsed-Year Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Say so, on both surfaces that show it, when the newest published yield is far below its own five-year history — instead of prefilling a destroyed harvest as if it were an expectation.

**Architecture:** One predicate in `src/norms.py` decides, from the `NormValue` alone, whether a figure is far below its own printed range. The budget card appends a clause to the range line it already prints; the comparison adds a sentence directly under its range line. Nothing about which figure is SERVED changes.

**Tech Stack:** Python 3.14, pytest. No new dependencies, no data-file change, no client change.

**Spec:** `docs/superpowers/specs/2026-08-29-collapsed-year-warning-design.md`

## Global Constraints

- Run every command from the repo root. `src/config.py` reads a RELATIVE `env_file=".env"`; running elsewhere silently loads a wrong `EMBEDDING_MODEL`.
- **A cell that is NOT far below its own history must render byte-identically to today**, on both surfaces. Tests pin this rather than trusting it.
- **`cell.note` must not change.** `_verify` reads it and it becomes the answer's provenance sentence; a change there moves the answer text.
- **This round adds a sentence. It never changes which figure is served, and never invents one.** `norms._pick` keeps serving the most recent published value.
- The warning claims NO cause. It says the figure is far below its own history and nothing about why — the wording must stay true whether the harvest failed or the province left the crop.
- Turkish user-facing strings exactly as given in each task, matching the existing voice. Never claim to be a licensed Ziraat Mühendisi.
- Comments explain WHY, not what. Match the surrounding density and voice.
- Commit messages: short, natural, English, no `Co-Authored-By` trailer.
- `python -m pytest -q` must be green (**989 tests** at plan time) before every commit. There is no expected intermediate red state — if something is red, stop and report.
- Out of scope: `data/crop_norms.json`, `scripts/build_crop_norms.py`, the density rules, `norms._pick`, `src/router.py`, `budget.render`, and anything under `mobile-app/`.

---

### Task 1: `norms.far_below_recent`

**Files:**
- Modify: `src/norms.py` — one constant and one function, after the `NormValue` dataclass
- Test: `tests/test_norms.py`

**Interfaces:**
- Consumes: `norms.NormValue`, whose fields are `amount, year, scope, region, recent_min=None, recent_max=None`.
- Produces: `norms.far_below_recent(value: NormValue | None) -> bool`, and the module constant `norms._FAR_BELOW_RECENT`. Tasks 2 and 3 both call the function; nothing outside `norms.py` reads the constant except a mutation check.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_norms.py`, at the end of the file:

```python
def test_a_figure_far_below_its_own_five_year_range_is_flagged():
    """Bilecik/Erik 2025: 1 kg/ağaç against a prior 20-37. Production fell from
    2.954 tons to 27 while the recorded orchard area GREW - the trees are there
    and the harvest is not. The most recent published figure is not an
    expectation when there was almost nothing to measure."""
    value = norms.NormValue(1.0, 2025, "il", "Bilecik", 20.0, 37.0)
    assert norms.far_below_recent(value) is True


def test_an_ordinary_figure_is_not_flagged():
    value = norms.NormValue(31.0, 2025, "il", "Karabük", 27.0, 28.0)
    assert norms.far_below_recent(value) is False


def test_a_figure_with_no_range_is_never_flagged():
    """With nothing to compare against there is nothing to warn about. The
    range is the warning's own evidence."""
    assert norms.far_below_recent(
        norms.NormValue(1.0, 2025, "il", "Bilecik")) is False


def test_no_value_is_not_flagged():
    assert norms.far_below_recent(None) is False


def test_the_threshold_is_exercised_from_both_sides():
    """A midpoint of 100: 19 is below one fifth of it, 21 is not. Pins the
    constant itself, so it cannot drift without a test noticing."""
    below = norms.NormValue(19.0, 2025, "il", "Bilecik", 80.0, 120.0)
    above = norms.NormValue(21.0, 2025, "il", "Bilecik", 80.0, 120.0)
    assert norms.far_below_recent(below) is True
    assert norms.far_below_recent(above) is False


def test_a_zero_range_cannot_divide_by_zero():
    """recent_min == recent_max == 0 cannot occur through _recent_range, which
    refuses a range whose ends are equal - but this function is public and must
    not raise on a value someone constructs."""
    assert norms.far_below_recent(
        norms.NormValue(1.0, 2025, "il", "Bilecik", 0.0, 0.0)) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_norms.py -q -k "far_below or ordinary_figure or no_range_is_never or no_value_is_not or threshold_is_exercised or zero_range"`

Expected: all six FAIL with `AttributeError: module 'src.norms' has no attribute 'far_below_recent'`.

- [ ] **Step 3: Write the implementation**

In `src/norms.py`, immediately after the `NormValue` dataclass, add:

```python
# ONE FIFTH, AND THIS NUMBER IS TUNED RATHER THAN ARGUED. Measured over the
# 7.245 provincial yield cells that print a prior range: the distribution of
# `served / prior midpoint` decays smoothly from its mode at 0,9-1,2 with NO gap
# and no second peak, so a catastrophic year and a merely poor one lie on one
# continuum. An ordering rule does not rescue it either - "below the minimum of
# the prior five" fires on 28,8% of cells and 57% of those are near misses. All
# that can be said for one fifth is that the histogram's slope is shallowest
# across roughly 0,20-0,35, so the choice is least consequential there, and that
# it fires on 240 cells (3,3%).
#
# WHY A TUNED NUMBER IS ACCEPTABLE HERE and was not for the density gates in
# scripts/build_crop_norms.py: this one drives a SENTENCE, not a refusal. Firing
# too often costs an unnecessary sentence; firing too rarely leaves today's
# behaviour. No outcome is worse than shipping nothing. The density rules delete
# data, which is why they were held to the higher "argued from geometry" bar.
_FAR_BELOW_RECENT = 0.2


def far_below_recent(value: NormValue | None) -> bool:
    """Whether this figure sits far below the five years printed beside it.

    A statement about the VALUE, not about presentation, so it lives here and
    both surfaces reach the same verdict for the same cell. The budget form and
    the comparison decided a measure separately once before and disagreed on
    1.568 cells for a round; a test pins them together.

    False without a range: the range is this warning's own evidence, and with
    nothing to compare against there is nothing to warn about.
    """
    if value is None or value.recent_min is None or value.recent_max is None:
        return False
    midpoint = (value.recent_min + value.recent_max) / 2
    if midpoint <= 0:
        return False
    return value.amount < _FAR_BELOW_RECENT * midpoint
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_norms.py -q`
Expected: all pass.

Run: `python -m pytest -q`
Expected: **989 or more passed, 0 failed.**

- [ ] **Step 5: Prove the threshold test bites**

Temporarily change `_FAR_BELOW_RECENT` to `0.02` and run:

Run: `python -m pytest tests/test_norms.py -q -k "threshold_is_exercised or far_below_its_own"`
Expected: **FAIL** — the boundary case at 19 (0,19 of the midpoint) is no longer flagged.

Revert, re-run, confirm green. A threshold no test pins is a threshold that can drift silently.

- [ ] **Step 6: Commit**

```bash
git add src/norms.py tests/test_norms.py
git commit -m "Recognise a yield that sits far below its own five-year history"
```

---

### Task 2: the budget card says so on the range line

**Files:**
- Modify: `src/budget.py` — a new import, a module constant, and `_yield_cell`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `norms.far_below_recent(value) -> bool` from Task 1.
- Produces: a yield cell whose `recent` ends with the warning clause when the figure is far below. Nothing later depends on it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`, after `test_a_field_crops_cell_carries_no_hint`:

```python
def _collapsed_table():
    """Erik's 2025 figure collapsed; Mısır's did not. Erik is per-tree so its
    cell also carries the temporary tree-count hint - the worst-case line."""
    return (
        CropNorm("erik", "Erik",
                 NormValue(7.1, 2025, "il", "Bilecik", 449.9, 925.4),
                 NormValue(30.0, 2025, "il", "Bilecik", None, None),
                 NormValue(1.0, 2025, "il", "Bilecik", 20.0, 37.0)),
        CropNorm("misir", "Mısır",
                 NormValue(1100.0, 2024, "tr", "Türkiye", 900.0, 1200.0),
                 NormValue(8.0, 2025, "tr", "Türkiye", None, None)),
    )


def test_a_collapsed_yield_says_so_on_its_range_line():
    """The range is the warning's evidence, so one line does both jobs."""
    spec = budget.form_spec([], _collapsed_table())
    assert spec["crops"][0]["yield"]["recent"] == (
        "önceki 5 yıl: 20–37 kg/ağaç — 2025 bunun çok altında "
        "· ağaç sayısını da girin")


def test_an_ordinary_yield_line_is_untouched():
    spec = budget.form_spec([], _collapsed_table())
    assert spec["crops"][1]["yield"]["recent"] == "önceki 5 yıl: 900–1.200 kg/da"


def test_a_collapsed_per_dekar_yield_says_so_too():
    """The test is the VALUE, not the measure - a field crop collapses the same
    way. Erik here carries no per-tree figure, so its kg/da cell is served."""
    from dataclasses import replace
    row = replace(_collapsed_table()[0], yield_kg_tree=None)
    spec = budget.form_spec([], (row,))
    assert spec["crops"][0]["yield"]["recent"] == (
        "önceki 5 yıl: 449,9–925,4 kg/da — 2025 bunun çok altında")


def test_the_warning_does_not_touch_the_note():
    """`note` is not free: _verify reads it and it becomes the answer's
    provenance sentence. A warning there would move the answer text."""
    spec = budget.form_spec([], _collapsed_table())
    assert spec["crops"][0]["yield"]["note"] == "TÜİK 2025, Bilecik"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_budget.py -q -k "collapsed_yield_says_so or ordinary_yield_line or collapsed_per_dekar or warning_does_not_touch"`

Expected: the two `collapsed_*` tests FAIL on the missing clause. `test_an_ordinary_yield_line_is_untouched` and `test_the_warning_does_not_touch_the_note` PASS — they are guards against the warning reaching a normal cell or the note.

- [ ] **Step 3: Write the implementation**

In `src/budget.py`, add the import beside the existing ones (this module has not imported `norms` before — it takes its table as a parameter. The edge is acyclic: `norms` imports only `src.config`, and it reads no file until `_load()` is called, so importing it here has no side effect):

```python
from src import norms
```

Add the constant immediately above `_yield_cell`, beside `_TREE_COUNT_HINT`:

```python
# Appended to the range line, which is this warning's own evidence, so one line
# does both jobs. It names no CAUSE: a harvest can fail or a province can leave
# the crop, and the sentence must stay true either way.
def _far_below_clause(value) -> str:
    return f" — {value.year} bunun çok altında"
```

Rewrite `_yield_cell` so both measures pass through the same warning step:

```python
def _yield_cell(row) -> dict | None:
    """This row's yield cell.

    A row is served PER TREE exactly when its `yield_kg_tree` resolved - no
    list of crops, no flag, no name matching. TUIK publishes no per-dekar yield
    for 61 tree crops, and the kg/da this project derives for them divides a
    province's whole production by the few dekars of COMPACT orchard it
    records; the published per-tree figure has no such denominator. So per-tree
    wins wherever it exists, which is the same precedence the builder already
    applies in the other direction.

    Both measures then pass through the same two additions to `recent`, in this
    order: the far-below clause, which belongs to the figure, and only then the
    temporary "fill the tree count" hint, which belongs to the form - see
    `_TREE_COUNT_HINT` above for why and when that one goes.
    """
    if row.yield_kg_tree is not None:
        value = row.yield_kg_tree
        cell = _norm_cell(value, *_NORM_UNITS["yield_tree"], None,
                          show_range=True)
    else:
        value = row.yield_kg_da
        cell = _norm_cell(value, *_NORM_UNITS["yield"], None, show_range=True)
    if cell is None:
        return None
    if norms.far_below_recent(value):
        # far_below_recent is False without a range, so `recent` is never None
        # here and the clause always has something to attach to.
        cell["recent"] = f"{cell['recent']}{_far_below_clause(value)}"
    if row.yield_kg_tree is not None:
        cell["recent"] = (f"{cell['recent']} · {_TREE_COUNT_HINT}"
                          if cell["recent"] else _TREE_COUNT_HINT)
    return cell
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_budget.py -q`
Expected: all pass.

Run: `python -m pytest -q`
Expected: **989 or more passed, 0 failed.**

- [ ] **Step 5: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Say on the card when a yield is far below its own history"
```

---

### Task 3: the comparison says so under its range line

**Files:**
- Modify: `src/crop_compare.py` — a module constant and both range-printing branches of `_crop_block`
- Test: `tests/test_crop_compare.py`

**Interfaces:**
- Consumes: `norms.far_below_recent(value) -> bool` from Task 1. `crop_compare` already imports `norms`.
- Produces: `crop_compare.FAR_BELOW_NOTE`, a module-level format string.

- [ ] **Step 1: Add two collapsed crops to the test fixture**

In `tests/test_crop_compare.py`, inside the `TABLE["crops"]` dict, add these two entries after the existing `"ceviz"` entry. `visne` collapses on its per-tree measure, `kayisi` on its per-dekar one, so both branches of `_crop_block` are exercised:

```python
        "visne": {
            "label": "Vişne",
            "yield_kg_da": {"scope": "il", "Konya": [900.0, 950.0, 1000.0, 30.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [20.0, 24.0, 28.0, 33.0],
                            "TR": [None, None, None, None]},
            "yield_kg_tree": {"scope": "il", "Konya": [30.0, 32.0, 34.0, 1.0],
                              "TR": [None, None, None, None]},
        },
        "kayisi": {
            "label": "Kayısı",
            "yield_kg_da": {"scope": "il", "Konya": [900.0, 950.0, 1000.0, 40.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [18.0, 22.0, 26.0, 31.0],
                            "TR": [None, None, None, None]},
        },
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_crop_compare.py`, after the tests added for the closing sentences:

```python
def test_a_collapsed_per_tree_yield_is_called_out_under_its_range():
    """The sentence sits directly under the range it refers to, so a reader
    never has to work out which figure it is about."""
    text = _render("visne", "domates (sofralik)")
    lines = _crop_block_lines(text, "Vişne")
    assert lines[1] == "   verimde önceki 5 yıl: 30–34 kg/ağaç"
    assert lines[2] == (
        "   2025 bu aralığın çok altında; olağan bir yılın beklentisi değil.")


def test_a_collapsed_per_dekar_yield_is_called_out_too():
    """The test is the VALUE, not the measure. Kayısı here has no per-tree
    figure, so it renders through the revenue branch."""
    text = _render("kayisi", "domates (sofralik)")
    lines = _crop_block_lines(text, "Kayısı")
    assert lines[2] == "   verimde önceki 5 yıl: 900–1.000 kg/da"
    assert lines[3] == (
        "   2025 bu aralığın çok altında; olağan bir yılın beklentisi değil.")


def test_an_ordinary_crop_gets_no_such_sentence():
    text = _render("domates (sofralik)", "biber (salcalik, kapya)")
    assert crop_compare.FAR_BELOW_NOTE.format(year=2025) not in text


def test_a_block_that_prints_no_range_never_carries_the_sentence():
    """`missing == "fiyat"` prints ONE line and no range at all. Kayısı is
    chosen deliberately: its 2025 figure IS far below its history, so this test
    fails if the sentence is emitted from the value alone rather than from the
    range line it belongs under. With any ordinary crop it would pass
    vacuously."""
    text = _render("kayisi", "domates (sofralik)", latest_year=2099)
    assert "yayımlanmış fiyat yok" in text
    assert crop_compare.FAR_BELOW_NOTE.format(year=2025) not in text


def test_the_two_surfaces_agree_on_which_figures_are_far_below():
    """The pair to the measure-agreement test above. These surfaces drifted
    once already; both now ask norms the same question."""
    from src import budget
    for row in _table():
        value = (row.yield_kg_tree if row.yield_kg_tree is not None
                 else row.yield_kg_da)
        cell = budget._yield_cell(row)
        if cell is None or cell["recent"] is None:
            continue
        on_card = "çok altında" in cell["recent"]
        assert on_card == norms.far_below_recent(value), row.label
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_crop_compare.py -q -k "collapsed_per_tree_yield or collapsed_per_dekar_yield or ordinary_crop_gets_no or prints_no_range_never or surfaces_agree_on_which"`

Expected: the two `collapsed_*` tests FAIL, and the three others fail with `AttributeError: module 'src.crop_compare' has no attribute 'FAR_BELOW_NOTE'`.

All five expected strings were checked against the real formatter before this plan was written: `format_qty` renders `449.9` as `449,9`, `925.4` as `925,4`, `1100.0` as `1.100`, `1000.0` as `1.000` and `34.0` as `34`. The fixture's existing crops are `domates (sofralik)`, `biber (salcalik, kapya)`, `tatli patates`, `arpa (biralik)`, `bugday, durum bugdayi haric`, `kara bugday`, `ayva` and `ceviz` — there is no `misir` in this file, unlike in `tests/test_budget.py`.

- [ ] **Step 4: Write the implementation**

In `src/crop_compare.py`, add the constant beside `PER_TREE_NOTE`:

```python
# Written BY CODE and printed directly under the range it refers to. It names
# no CAUSE - a harvest can fail or a province can leave the crop - so it stays
# true either way, and it says nothing about what next season will bring.
FAR_BELOW_NOTE = ("{year} bu aralığın çok altında; olağan bir yılın "
                  "beklentisi değil.")
```

In `_crop_block`, in the `per_tree` branch, replace the range block:

```python
        if y.recent_min is not None and y.recent_max is not None:
            lines.append(f"   verimde önceki 5 yıl: {format_qty(y.recent_min)}–"
                         f"{format_qty(y.recent_max)} kg/ağaç")
            if norms.far_below_recent(y):
                lines.append(f"   {FAR_BELOW_NOTE.format(year=y.year)}")
```

and in the revenue branch at the end of the function, replace the range block:

```python
    if y.recent_min is not None and y.recent_max is not None:
        lines.append(f"   verimde önceki 5 yıl: {format_qty(y.recent_min)}–"
                     f"{format_qty(y.recent_max)} kg/da")
        if norms.far_below_recent(y):
            lines.append(f"   {FAR_BELOW_NOTE.format(year=y.year)}")
    return lines
```

Extend `_crop_block`'s docstring with one sentence: the far-below sentence follows the range line in both branches because the range is its evidence, and the `missing` branches print no range so they cannot carry it.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_crop_compare.py -q`
Expected: all pass. If a pre-existing test moved because two crops joined the fixture, report it rather than adjusting it silently.

Run: `python -m pytest -q`
Expected: **989 or more passed, 0 failed.**

- [ ] **Step 6: Read the answers out loud**

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
for a, b in (('visne','domates (sofralik)'), ('kayisi','ayva'),
             ('domates (sofralik)','biber (salcalik, kapya)')):
    i, e = crop_compare.validate({'first': a, 'second': b}, table)
    print('='*70); print(crop_compare.render(i, crop_compare.compute(i, table, 2025)))
"
```

Read each answer sentence by sentence. Every sentence must be true of the figures printed above it, and the far-below sentence must sit under the range it refers to. This route has shipped three fixes for sentences describing things the answer did not print, and each was caught here rather than by a test. If anything reads wrong, stop and report.

- [ ] **Step 7: Commit**

```bash
git add src/crop_compare.py tests/test_crop_compare.py
git commit -m "Say in the comparison when a yield is far below its own history"
```

---

## Self-Review

**Spec coverage:**

| spec requirement | task |
|---|---|
| `far_below_recent`, one function, both surfaces | 1 |
| threshold one fifth of the prior midpoint | 1 |
| the constant's comment records it as TUNED, with the evidence and why that is acceptable here | 1 |
| False without a range | 1 (test) |
| card: clause appended to the range line, exact text | 2 |
| card: warning before the tree hint | 2 |
| card: applies to per-dekar as well as per-tree | 2 (test) |
| card: `note` untouched | 2 (test) |
| card: price cell unaffected | 2 — the price cell is built `show_range=False` and `_yield_cell` is the only caller changed |
| comparison: own line, exact text, directly under the range | 3 |
| comparison: both branches, per-tree and per-dekar | 3 (two tests) |
| comparison: no-range blocks cannot carry it | 3 (test) |
| both surfaces reach the same verdict | 3 (cross-surface test — norms, the card's cell and the comparison's rendered block, all three checked) |
| ordinary cells byte-identical | 2 and 3 (guards) |
| threshold proven by mutation | 1 (Step 5) |
| every sentence read against the printed answer | 3 (Step 6) |

No gaps. The spec's out-of-scope list — `budget.render`, the area condition, the builder, the data file, `_pick` — is touched by no task.

**Placeholder scan:** every code step carries the actual code; every run step carries the actual command and its expected output. No TBD, no "handle edge cases", no "similar to Task N".

**Type consistency:** `far_below_recent(value) -> bool` is named identically in Tasks 1, 2 and 3. `_FAR_BELOW_RECENT` is defined and mutated only in Task 1. `_far_below_clause(value) -> str` is defined and used only in Task 2. `FAR_BELOW_NOTE` is defined in Task 3 and used there and in its tests, always via `.format(year=...)`.

**Three risks worth naming:**

1. **Task 2 adds an import `src/budget.py` has never had.** It takes its table as a parameter precisely so it need not load norms. The edge is acyclic (`norms` imports only `src.config`) and side-effect-free (`_load` is lazy), but a reviewer should see it as a deliberate choice rather than an accident, which is why the task says so in the step itself.
2. **Task 3 adds two crops to a shared fixture.** The same move was measured safe once before in this file, but not for these names — Step 5 tells the implementer to report a moved pre-existing test rather than adjust it.
3. **Every expected string in this plan was verified against the real formatter before it was written**, not recalled: `_norm_cell` renders a range as `önceki 5 yıl: {min}–{max} {unit}` with `format_qty`, so `449.9` renders `449,9` and `1100.0` renders `1.100`. This plan's predicted failure messages have been wrong three times in recent rounds; the expected VALUES here follow the formatter's actual rules.
