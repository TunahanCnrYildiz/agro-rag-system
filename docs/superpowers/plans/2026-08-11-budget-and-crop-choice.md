# Budget and Crop-Choice Routes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `budget` and `crop_choice` routes answer their questions instead of falling through to a corpus search that cannot hold the answer — computing money in Python from numbers the user supplied, and never inventing one.

**Architecture:** Both routes follow the pattern `fert_plan` established in the previous plan: a route-specific context block is prepended to the system prompt and the answer is still produced by the existing corpus path. `crop_choice` adds no module at all. All new code is `src/budget.py`.

**Tech Stack:** Python 3.14, pytest, the existing `evals/` harness. No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-11-budget-and-crop-choice-design.md`.
- **A route may diverge only with zero wrong entries in the frozen 42-case routing set.** `budget` and `crop_choice` both satisfy this today; Task 6 re-measures before it matters.
- **No default yields and no default prices anywhere.** The numeric data layer is a separate spec. A missing number is asked for, never invented, never guessed by the model.
- **The model performs no arithmetic.** Every figure a user sees is computed in Python.
- Zero regression in the **58** existing eval cases. The `[OFFSCOPE]`/`[NOPRODUCT]` markers, the product-suppression backstop, the empty-answer guard and the stream-truncation recovery stay exactly as they are.
- Framing is **appended by code, never requested in the prompt**, and only when a calculation actually happened.
- `plant_info`, `nutrition` and `offscope` must be byte-for-byte unaffected.
- **`src/budget.py` imports `_normalize_tr` from `src/engine.py`.** Therefore `src/engine.py` must import `budget` **inside the function body** — the same load-bearing deferred import `router`, `fertplan` and `context.location` already require. A top-level import raises ImportError on every startup.
- Turkish matching uses enumerated suffixes, **never `\w*`**. Seven collision rounds in this project produced that rule; the most recent was `il\w*` swallowing `ile`, `ilgili` and `ilaç`.
- Run every Python command with `PYTHONIOENCODING=utf-8`.

---

### Task 1: The extractor

**This code was verified by the controller against every case in Step 1 before this plan was written — 15/15 pass, and the frozen budget set produces the table in spec §6.** Use it verbatim. If you find a case where it is wrong, that is genuinely valuable: stop and report BLOCKED with the input and output rather than adjusting the regexes yourself.

**Files:**
- Create: `src/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `engine._normalize_tr` (folds Turkish characters to ASCII and lowercases, so every pattern below is written against folded text).
- Produces: `BudgetInputs` (frozen dataclass, fields `area_da`, `yield_kg_da`, `price_tl_kg`, `cost_tl`, `crop`, all `| None`) and `extract(message: str) -> BudgetInputs`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_budget.py`:

```python
"""Budget input extraction.

The rule these tests encode: a number is assigned to a slot ONLY when it carries
an unambiguous unit or an adjacent slot keyword. Everything else is ignored,
which means it gets asked for. Missing a number the user gave is annoying and
visible; misreading one states wrong money silently. The tests below pin that
asymmetry, so do not loosen a must-not-extract case to make a match work.
"""

import pytest

from src.budget import extract


@pytest.mark.parametrize("text,field,expected", [
    ("5 dönüm", "area_da", 5),
    ("5 dekar mısır ektim", "area_da", 5),
    ("100 hektar", "area_da", 1000),
    ("1 milyon masraf ettim", "cost_tl", 1_000_000),
    ("masrafım 1 milyon TL", "cost_tl", 1_000_000),
    ("toplam 250.000 TL gider oldu", "cost_tl", 250_000),
    ("dekara 400 kg", "yield_kg_da", 400),
    ("dekara 1 ton", "yield_kg_da", 1000),
    ("400 kg/da aldım", "yield_kg_da", 400),
    ("kilosu 12,5 TL", "price_tl_kg", 12.5),
    ("tonu 12500 TL", "price_tl_kg", 12.5),
])
def test_unambiguous_values_are_extracted(text, field, expected):
    assert getattr(extract(text), field) == pytest.approx(expected)


@pytest.mark.parametrize("text", [
    # "8 ton" is TOTAL in Turkish; "dekara 8 ton" is per area. Reading one as the
    # other is a fivefold error on a five-dekar field, so an unmarked figure is
    # ambiguous and must be asked for instead.
    "8 ton verim aldım",
    "geçen yıl 40 ton aldım",
    # A bare number with no slot keyword nearby.
    "1 milyon",
    "5 dönüm ektim, 12 yaşında bir bahçe",
    # 'da' is a clitic meaning "also" and sits next to numbers constantly. It is
    # accepted only inside the compound "kg/da", where the slash disambiguates.
    "2024 da ekim yaptım",
    "tarlada çalıştım",
])
def test_ambiguous_or_absent_values_are_not_extracted(text):
    got = extract(text)
    assert (got.area_da, got.yield_kg_da, got.price_tl_kg, got.cost_tl) == (
        None, None, None, None), got


def test_the_canonical_frozen_case():
    got = extract("5 dönüm domates ektim 1 milyon masraf ettim, ne kadar kâr ederim?")
    assert got.area_da == 5
    assert got.cost_tl == 1_000_000
    assert got.yield_kg_da is None      # not given, so it must be asked for
    assert got.price_tl_kg is None


def test_a_price_next_to_a_cost_keyword_is_not_read_as_the_cost():
    """The regression that made the cost-pattern order load-bearing.

    In "kilosu 12,5 TL, masrafım 20000 TL" the word "masrafım" sits within three
    words of the PRICE. Matching number-then-keyword first read 12,5 as the cost
    and produced a margin of 25000-12.5 instead of 25000-20000 — wrong money,
    stated confidently, with nothing in the answer to reveal it.
    """
    got = extract("5 dekar, dekara 400 kg, kilosu 12,5 TL, masrafım 20000 TL")
    assert got.area_da == 5
    assert got.yield_kg_da == 400
    assert got.price_tl_kg == 12.5
    assert got.cost_tl == 20_000        # NOT 12.5


def test_extraction_never_raises_on_junk():
    for text in ("", "?????", "12,,5 TL", "1.2.3 dönüm", "milyon milyon"):
        extract(text)          # must not raise
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.budget'`. Record the exact text.

- [ ] **Step 3: Implement**

Create `src/budget.py`:

```python
"""Budget inputs, arithmetic, and the framing that keeps a figure an estimate.

THE MODEL PERFORMS NO ARITHMETIC. Every number a user sees from this route is
computed here, in Python, from values the user supplied. There are no default
yields and no default prices: until the numeric data layer lands (its own spec),
a value that was not given is asked for, never invented.

EXTRACTION IS DELIBERATELY TIMID. A number reaches a slot only when it carries an
unambiguous unit or an adjacent slot keyword. Anything else is ignored, so the
slot stays empty and gets asked for. That chooses one failure mode over the
other: missing a number the user gave is annoying and VISIBLE, while misreading
one states wrong money SILENTLY, and the user cannot detect it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.engine import _normalize_tr

_MULT = {"bin": 1_000, "milyon": 1_000_000, "milyar": 1_000_000_000}

# 1.000.000 | 12,5 | 400 - Turkish thousands separator and decimal comma.
_NUM = r"\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?"

# Area. NOTE the absence of bare "da": it is one of the commonest words in
# Turkish (a clitic meaning "also") and sits next to numbers constantly, so
# "2024 da ekim yaptim" would extract 2024 dekar. It survives only inside the
# compound "kg/da" below, where the slash disambiguates it.
_AREA_FACTOR = {"donum": 1.0, "dekar": 1.0, "hektar": 10.0, "ha": 10.0}
_AREA_RE = re.compile(
    rf"(?<!\d)({_NUM})(?:\s*(bin|milyon|milyar))?\s*(donum|dekar|hektar|ha)(?!\w)")

# Yield, ONLY from an explicit per-area form. See the module docstring.
_YIELD_PREFIX_RE = re.compile(
    rf"(?:dekara|dekarda|donume|donumde)\s*({_NUM})(?:\s*(bin|milyon))?\s*(kg|ton)(?!\w)")
_YIELD_SLASH_RE = re.compile(
    rf"(?<!\d)({_NUM})(?:\s*(bin|milyon))?\s*(kg|ton)\s*/\s*(?:da|dekar|donum)(?!\w)")

# Price, only from an explicit per-weight form.
_PRICE_RES = (
    (re.compile(rf"(?<!\d)({_NUM})(?:\s*(bin|milyon))?\s*(?:tl|lira)\s*/\s*kg(?!\w)"), 1),
    (re.compile(rf"kilosu\s*({_NUM})(?:\s*(bin|milyon))?\s*(?:tl|lira)(?!\w)"), 1),
    (re.compile(rf"(?<!\d)({_NUM})(?:\s*(bin|milyon))?\s*(?:tl|lira)\s*/\s*ton(?!\w)"), 1000),
    (re.compile(rf"tonu\s*({_NUM})(?:\s*(bin|milyon))?\s*(?:tl|lira)(?!\w)"), 1000),
)

# Cost: a number with a cost keyword WITHIN THREE WORDS, in either order, so both
# "1 milyon TL masraf ettim" and "masrafim 1 milyon TL" work while a keyword at
# the far end of a long sentence does not. TL is optional - the canonical frozen
# case is "1 milyon masraf ettim", with no currency written.
_COST_WORDS = r"(?:masraf|gider|maliyet|harcadim|harcadik|harcama)"
_GAP = r"(?:\s+\S+){0,3}\s*"
# ORDER IS LOAD-BEARING: keyword-then-number is tried FIRST.
# With the other order, "kilosu 12,5 TL, masrafim 20000 TL" matched the PRICE as
# the cost, because "masrafim" sits within three words of it - producing a margin
# of 25000-12.5 instead of 25000-20000, silently. Keyword-first reads the number
# the keyword actually introduces. (Found by running this extractor against the
# plan's own example before the plan was finished; the case is now a test.)
_COST_RES = (
    re.compile(rf"{_COST_WORDS}\w*{_GAP}(?<!\d)({_NUM})(?:\s*(bin|milyon|milyar))?(?:\s*(?:tl|lira))?"),
    re.compile(rf"(?<!\d)({_NUM})(?:\s*(bin|milyon|milyar))?(?:\s*(?:tl|lira))?{_GAP}{_COST_WORDS}"),
)


@dataclass(frozen=True)
class BudgetInputs:
    """Canonical units throughout: dekar, kg/dekar, TL/kg, TL."""
    area_da: float | None = None
    yield_kg_da: float | None = None
    price_tl_kg: float | None = None
    cost_tl: float | None = None
    crop: str | None = None


def _value(raw: str, multiplier: str | None) -> float | None:
    """'1.000.000' -> 1000000.0, '12,5' -> 12.5, ('1','milyon') -> 1000000.0."""
    try:
        n = float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return n * _MULT[multiplier] if multiplier else n


def extract(message: str) -> BudgetInputs:
    """Pull only what is unambiguous out of the message. Never raises."""
    try:
        text = _normalize_tr(message)
    except Exception:  # noqa: BLE001 - a budget answer must not break answering
        return BudgetInputs()

    area = yield_ = price = cost = None

    m = _AREA_RE.search(text)
    if m:
        v = _value(m.group(1), m.group(2))
        if v is not None:
            area = v * _AREA_FACTOR[m.group(3)]

    for rx in (_YIELD_PREFIX_RE, _YIELD_SLASH_RE):
        m = rx.search(text)
        if m:
            v = _value(m.group(1), m.group(2))
            if v is not None:
                yield_ = v * (1000 if m.group(3) == "ton" else 1)
            break

    for rx, divisor in _PRICE_RES:
        m = rx.search(text)
        if m:
            v = _value(m.group(1), m.group(2))
            if v is not None:
                price = v / divisor
            break

    for rx in _COST_RES:
        m = rx.search(text)
        if m:
            cost = _value(m.group(1), m.group(2))
            break

    return BudgetInputs(area_da=area, yield_kg_da=yield_,
                        price_tl_kg=price, cost_tl=cost)
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -v`
Expected: all pass.

- [ ] **Step 5: Record what the frozen budget set yields**

Run:

```bash
PYTHONIOENCODING=utf-8 python -c "
from src.budget import extract
from evals.routing_set import ROUTING_CASES
for c in ROUTING_CASES:
    if c['route'] == 'budget':
        g = extract(c['query'])
        f = {k: v for k, v in vars(g).items() if v is not None}
        print(f'  {str(f) if f else chr(40)+chr(41)}  <- ' + c['query'])
"
```

Expected: the first case yields `area_da=5.0, cost_tl=1000000.0`; the other six yield nothing, because they contain no numbers. **Paste the output into your report.** Six of seven extracting nothing is the correct result, not a shortfall.

- [ ] **Step 6: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Extract budget inputs only where they are unambiguous"
```

---

### Task 2: The arithmetic

**Files:**
- Modify: `src/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `BudgetInputs` from Task 1.
- Produces: `BudgetResult` (frozen dataclass, fields `revenue_tl: float`, `margin_tl: float`, `inputs: BudgetInputs`), `compute(inputs: BudgetInputs) -> BudgetResult | None`, `missing(inputs: BudgetInputs) -> tuple[str, ...]`, and `COST_ITEMS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_budget.py`:

```python
from src.budget import COST_ITEMS, BudgetInputs, compute, missing


def test_all_four_present_computes_revenue_and_margin():
    r = compute(BudgetInputs(area_da=5, yield_kg_da=400,
                             price_tl_kg=12.5, cost_tl=1_000_000))
    assert r is not None
    assert r.revenue_tl == pytest.approx(5 * 400 * 12.5)       # 25 000
    assert r.margin_tl == pytest.approx(25_000 - 1_000_000)    # negative, and that is fine


@pytest.mark.parametrize("kwargs", [
    {"area_da": 5, "yield_kg_da": 400, "price_tl_kg": 12.5},          # no cost
    {"area_da": 5, "yield_kg_da": 400, "cost_tl": 1000},              # no price
    {"area_da": 5, "price_tl_kg": 12.5, "cost_tl": 1000},             # no yield
    {"yield_kg_da": 400, "price_tl_kg": 12.5, "cost_tl": 1000},       # no area
    {},                                                               # nothing
])
def test_a_missing_value_means_no_calculation_at_all(kwargs):
    # There is no partial calculation. A revenue figure without a cost figure
    # would read as a profit figure to anyone skimming it.
    assert compute(BudgetInputs(**kwargs)) is None


def test_missing_names_exactly_what_is_absent():
    got = missing(BudgetInputs(area_da=5, cost_tl=1_000_000))
    assert set(got) == {"yield_kg_da", "price_tl_kg"}
    assert missing(BudgetInputs(area_da=5, yield_kg_da=400,
                                price_tl_kg=12.5, cost_tl=1)) == ()


def test_cost_items_are_the_things_a_grower_actually_pays_for():
    assert "tohum" in COST_ITEMS and "gübre" in COST_ITEMS and "hasat" in COST_ITEMS
    assert len(COST_ITEMS) >= 5


def test_a_zero_price_is_a_real_value_not_a_missing_one():
    # 0.0 is falsy. A slot must be tested for None, never for truthiness, or a
    # legitimately free input silently becomes a question.
    r = compute(BudgetInputs(area_da=5, yield_kg_da=400,
                             price_tl_kg=0.0, cost_tl=100))
    assert r is not None
    assert r.revenue_tl == 0
    assert missing(BudgetInputs(area_da=5, yield_kg_da=400,
                                price_tl_kg=0.0, cost_tl=0.0)) == ()
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -k "compute or missing or COST or zero" -v`
Expected: FAIL — `ImportError: cannot import name 'compute' from 'src.budget'`.

- [ ] **Step 3: Implement**

Append to `src/budget.py`:

```python
# What a grower actually pays for. Used when no numbers were given: naming the
# items turns "I cannot answer" into "here is what decides it, and here is what I
# need from you". No figures are attached to them - there are none to attach.
COST_ITEMS: tuple[str, ...] = (
    "tohum/fide", "gübre", "toprak işleme", "sulama", "ilaçlama",
    "hasat", "nakliye", "işçilik",
)

_REQUIRED = ("area_da", "yield_kg_da", "price_tl_kg", "cost_tl")


@dataclass(frozen=True)
class BudgetResult:
    revenue_tl: float
    margin_tl: float
    inputs: BudgetInputs


def missing(inputs: BudgetInputs) -> tuple[str, ...]:
    """The required slots that are empty, in a fixed order."""
    return tuple(f for f in _REQUIRED if getattr(inputs, f) is None)


def compute(inputs: BudgetInputs) -> BudgetResult | None:
    """Revenue and margin, or None when anything required is absent.

    There is NO partial calculation: a revenue figure presented without a cost
    figure reads as a profit figure to anyone skimming it.

    Note the `is None` tests in `missing` rather than truthiness - 0.0 is a
    legitimate price or cost, and a falsy check would turn it into a question.
    """
    if missing(inputs):
        return None
    revenue = inputs.area_da * inputs.yield_kg_da * inputs.price_tl_kg
    return BudgetResult(revenue_tl=revenue,
                        margin_tl=revenue - inputs.cost_tl,
                        inputs=inputs)
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Compute revenue and margin in code, never partially"
```

---

### Task 3: The framing sentence

**Files:**
- Modify: `src/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Produces: `FRAMING: str`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_budget.py`:

```python
def test_framing_says_it_is_an_estimate_and_names_its_basis():
    from src.budget import FRAMING
    low = FRAMING.lower()
    assert "tahmin" in low
    # It must say the figure rests on the user's own numbers, because it does.
    assert "verdiğiniz" in low or "girdiğiniz" in low
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -k framing -v`
Expected: FAIL — `ImportError: cannot import name 'FRAMING'`.

- [ ] **Step 3: Implement**

Append to `src/budget.py`:

```python
# Appended BY CODE in engine.answer/stream_answer, never asked of the model, so
# no model can omit it. Gated on a calculation having actually happened - putting
# "this is an estimate" under a reply that only asked questions is the defect the
# previous plan's review found and fixed.
FRAMING = (
    "Bu hesap yalnızca sizin verdiğiniz sayılara dayanan bir tahmindir. "
    "Verim ve fiyat bölgeye, yıla ve pazara göre değişir; kesin bir gelir "
    "taahhüdü değildir."
)
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/budget.py tests/test_budget.py
git commit -m "Add the budget framing sentence"
```

---

### Task 4: The context blocks

**Files:**
- Modify: `src/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `budget.extract`, `budget.compute`, `budget.missing`, `budget.COST_ITEMS`; `context.location.extract_province`, `context.season.describe`.
- Produces: two new branches inside the existing `_context_block(route, message, history, today)`. Its signature does not change.

**Read `_context_block` before editing it.** It currently returns `""` for every route except `fert_plan`. You are adding two more branches; the `""` default for the remaining routes must survive, because `plant_info`, `nutrition` and `offscope` depend on it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
def test_budget_block_names_given_values_and_asks_for_the_rest():
    out = engine._context_block(
        "budget", "5 dönüm domates ektim 1 milyon masraf ettim, ne kadar kâr ederim?",
        None, date(2026, 8, 11))
    assert "5" in out and "dekar" in out          # what was given
    assert "verim" in out and "fiyat" in out      # what is missing
    assert "UYDURMA" in out                       # and the instruction not to invent
    assert "tohum" in out                         # cost items explained


def test_budget_block_with_nothing_given_still_explains_the_cost_items():
    out = engine._context_block(
        "budget", "Buğday ekmenin dekara maliyeti nedir?", None, date(2026, 8, 11))
    assert "tohum" in out and "sulama" in out
    assert "alan" in out and "verim" in out       # all four asked for


def test_budget_block_carries_the_computed_figures_when_all_four_are_present():
    out = engine._context_block(
        "budget",
        "5 dekar, dekara 400 kg, kilosu 12,5 TL, masrafım 20000 TL",
        None, date(2026, 8, 11))
    assert "25000" in out.replace(".", "").replace(",", "")   # 5*400*12.5 revenue
    assert "HESAPLANMIS" in out
    assert "yeniden hesaplama" in out.lower()


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


def test_a_budget_failure_degrades_to_an_empty_block(monkeypatch):
    """Spec §8: a budget failure must cost the situation lines, not the answer."""
    from src import budget
    monkeypatch.setattr(budget, "extract",
                        lambda m: (_ for _ in ()).throw(RuntimeError("boom")))
    assert engine._context_block(
        "budget", "5 dönüm ektim", None, date(2026, 8, 11)) == ""


def test_a_crop_choice_failure_degrades_to_an_empty_block(monkeypatch):
    monkeypatch.setattr("src.context.season.describe",
                        lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    assert engine._context_block(
        "crop_choice", "Bu yıl ne eksem?", None, date(2026, 8, 11)) == ""


@pytest.mark.parametrize("route", ["plant_info", "nutrition", "offscope", ""])
def test_every_other_route_still_gets_an_empty_block(route):
    assert engine._context_block(
        route, "5 dönüm domates ektim 1 milyon masraf ettim", None,
        date(2026, 8, 11)) == ""
```

`tests/test_engine.py` already imports `json` and `date` and `engine`. Add `import pytest` at the top if it is not already there.

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -k "budget_block or crop_choice_block" -v`
Expected: FAIL — the blocks come back `""`, so the substring assertions fail.

- [ ] **Step 3: Implement**

In `src/engine.py`, inside `_context_block`, replace the final `return ""` with the
two branches below, then add the two helper functions immediately after
`_context_block`. Splitting the bodies out is what lets one `try` wrap the whole of
each block rather than a single call inside it — spec §8 requires a budget failure to
degrade to today's corpus answer, not to a broken reply.

```python
    if route == "budget":
        # Deferred: src/budget.py imports _normalize_tr from THIS module, so a
        # top-level import here is a real cycle.
        from src import budget
        try:
            return _budget_block(budget, message)
        except Exception:  # noqa: BLE001 - spec §8
            return ""

    if route == "crop_choice":
        try:
            return _crop_choice_block(message, history, today)
        except Exception:  # noqa: BLE001 - spec §8
            return ""

    return ""


def _budget_block(budget, message: str) -> str:
    """Situation lines for the budget route.

    The model is never asked to compute. When every value is present it receives
    finished arithmetic and is told to present it; when one is missing it receives
    the list of what to ask for and an instruction not to invent anything.
    """
    inputs = budget.extract(message)
    result = budget.compute(inputs)

    given = []
    if inputs.area_da is not None:
        given.append(f"alan {inputs.area_da:g} dekar")
    if inputs.yield_kg_da is not None:
        given.append(f"verim {inputs.yield_kg_da:g} kg/dekar")
    if inputs.price_tl_kg is not None:
        given.append(f"fiyat {inputs.price_tl_kg:g} TL/kg")
    if inputs.cost_tl is not None:
        given.append(f"masraf {inputs.cost_tl:g} TL")

    lines = ["Kullanicinin verdigi degerler: "
             + (", ".join(given) if given else "(hicbiri)") + "."]

    if result is not None:
        lines.append(f"HESAPLANMIS gelir: {result.revenue_tl:g} TL. "
                     f"HESAPLANMIS kar: {result.margin_tl:g} TL.")
        lines.append("Bu rakamlari oldugu gibi sun, yeniden hesaplama.")
    else:
        names = {"area_da": "alan (dekar)",
                 "yield_kg_da": "verim (dekara kg)",
                 "price_tl_kg": "satis fiyati (TL/kg)",
                 "cost_tl": "toplam masraf (TL)"}
        lines.append("EKSIK: "
                     + ", ".join(names[f] for f in budget.missing(inputs)) + ".")
        lines.append("Cevabinda tam olarak bu eksikleri sor, deger UYDURMA.")
        lines.append("Maliyeti belirleyen kalemleri say: "
                     + ", ".join(budget.COST_ITEMS) + ".")

    return "
".join(lines)


def _crop_choice_block(message: str, history: list[dict] | None, today) -> str:
    """Situation lines for the crop-choice route.

    The prohibition on naming a crop is a PROMPT constraint, not something this
    code can enforce; spec §5 says so and the eval measures whether it holds.
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
    return "
".join(lines)
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -v`
Expected: all pass, including every pre-existing test. If a pre-existing one changes verdict, **stop and report which** — do not adjust it.

- [ ] **Step 5: Run the whole suite**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: all pass. The count was 471 before this plan; report the new number.

- [ ] **Step 6: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Give budget and crop_choice their context blocks"
```

---

### Task 5: Append the budget framing on both answer paths

**Files:**
- Modify: `src/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Modifies the existing `_framing_suffix(route, message) -> str`.

**Both real clients stream** (`mobile-app/src/api.ts` and `web-widget/widget/agro-chat-widget.js` send `stream: true`). `_framing_suffix` is already consumed by BOTH `answer()` and `stream_answer()`, so extending that one function covers both paths and no new wiring is needed. Do not add a second append site.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
def test_budget_framing_is_appended_only_when_a_figure_was_computed():
    from src import budget
    complete = "5 dekar, dekara 400 kg, kilosu 12,5 TL, masrafım 20000 TL"
    assert engine._framing_suffix("budget", complete) == budget.FRAMING


def test_budget_framing_is_absent_when_the_answer_only_asked_questions():
    # "This is an estimate" under a reply containing no estimate is the defect the
    # previous plan's review caught. It must not be reintroduced here.
    assert engine._framing_suffix("budget", "Buğday ekmenin maliyeti nedir?") == ""
    assert engine._framing_suffix(
        "budget", "5 dönüm domates ektim 1 milyon masraf ettim") == ""


def test_crop_choice_never_gets_a_framing_sentence():
    assert engine._framing_suffix("crop_choice", "Bu yıl ne eksem?") == ""
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -k budget_framing -v`
Expected: FAIL — `_framing_suffix` returns `""` for `budget` today.

- [ ] **Step 3: Implement**

In `src/engine.py`, in `_framing_suffix`, before the existing `fert_plan` handling (or beside it — the function returns `""` for unknown routes and that must stay):

```python
    if route == "budget":
        # Deferred, same cycle as above.
        from src import budget
        # Gated on a figure ACTUALLY being produced, not on the route. A reply
        # that only asked for the missing numbers contains no estimate to frame.
        if budget.compute(budget.extract(message)) is not None:
            return budget.FRAMING
        return ""
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -v`
Expected: all pass.

- [ ] **Step 5: Prove the streaming path carries it too**

The unit tests above exercise `_framing_suffix` directly. Confirm the streamed answer really contains the sentence:

```bash
PYTHONIOENCODING=utf-8 python -c "
import json
from src import engine, budget
q = '5 dekar mısır ektim, dekara 400 kg aldım, kilosu 12,5 TL, masrafım 20000 TL. Kârım ne?'
ev = [json.loads(e[6:]) for e in engine.stream_answer(q) if e.startswith('data: ')]
text = ''.join(e['content'] for e in ev if e['type'] == 'token')
print('FRAMING present:', budget.FRAMING in text)
print('event types:', [e['type'] for e in ev][-3:])
print()
print(text)
"
```

Expected: `FRAMING present: True`, event types ending `['token', 'products', 'done']`, and an answer that states the computed profit. **Paste the output into your report.** This needs LM Studio running.

- [ ] **Step 6: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Frame a budget answer only when a figure was computed"
```

---

### Task 6: Eval coverage, in the same change that makes the routes diverge

The previous plan shipped a diverging route with **zero** eval coverage of it and only whole-branch review noticed. This task exists so that cannot repeat.

**Files:**
- Modify: `evals/eval_set.py`
- Test: the eval harness itself is the test.

- [ ] **Step 1: Re-measure the dispatch condition FIRST**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_routing`

Expected: `budget` and `crop_choice` both appear in the `sevke uygun rotalar (sifir yanlis giris)` list. Accuracy should still read 37/42 with the gate FAILED — this plan does not touch the routing rules, so a *changed* accuracy is itself something to investigate and report.

**If either route has gained a wrong entry, STOP and report BLOCKED.** The entire permission for Tasks 4 and 5 rests on that number being zero.

- [ ] **Step 2: Add the cases**

Append to the `CASES` list in `evals/eval_set.py`, before the closing `]`:

```python
    # ----------------------------------------------------------------- #
    # budget and crop_choice - the two routes this plan makes diverge
    # ----------------------------------------------------------------- #
    # Added in the SAME change that makes them diverge. The previous plan did
    # not, and the shield passed 55/55 while exercising the changed route zero
    # times.
    #
    # Anchors avoid month and season names: those come from date.today(), so an
    # anchor like "Ağustos" would be green today and red in December with nothing
    # about the product having changed.
    {"id": "budget_computes_from_given_numbers",
     "category": "budget",
     "query": ("5 dekar mısır ektim, dekara 400 kg aldım, kilosu 12,5 TL, "
               "masrafım 20000 TL. Kârım ne kadar?"),
     "retrieval": "any",
     "products": "any",
     # 5 * 400 * 12.5 = 25 000 TL revenue, 5 000 TL margin. The figures are
     # computed in Python and handed to the model, so they must survive into the
     # answer verbatim.
     "answer_any": ["25000", "25.000", "25 000"]},

    {"id": "budget_asks_instead_of_inventing",
     "category": "budget",
     "query": "Buğday ekmenin dekara maliyeti nedir?",
     "retrieval": "any",
     "products": "any",
     # No numbers were given, so no numbers may be produced. What the answer must
     # do is name the cost items and ask.
     "answer_any": ["tohum", "gübre", "sulama", "işçilik"],
     # The guardrail: it must not answer with a confident per-dekar figure it has
     # no basis for. "TL" alone is too common to ban, so ban the shapes that a
     # fabricated cost would take.
     "answer_none": ["yaklaşık 5000", "ortalama 5000", "5000 TL/da"]},

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

- [ ] **Step 3: Check the anchors cannot match inside longer words**

`_matches(term, text)` applies a LEFT word boundary and a trailing-digit guard, no right boundary. Verify the new anchors behave:

```bash
PYTHONIOENCODING=utf-8 python -c "
from evals.run_eval import _matches
for term, text, want in [
    ('tohum', 'tohumluk secimi onemlidir', True),
    ('pazar', 'pazara mesafe', True),
    ('pazar', 'Pazartesi gunu', True),
    ('25000', 'geliriniz 25000 TL olur', True),
    ('25000', 'geliriniz 125000 TL olur', False),
]:
    got = _matches(term, text)
    print(('OK   ' if got == want else 'DIKKAT'), got, repr(term), '<-', text)
"
```

Expected: every line `OK`. Note `pazar` legitimately matches inside `Pazartesi` — the anchor list is an *any* match, so that is a weak anchor rather than a wrong one; report it, do not silently drop it.

- [ ] **Step 4: Run the fast shield**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --fast`
Expected: 61/61 (58 + 3).

- [ ] **Step 5: Run the full shield**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval`
Expected: 61/61.

For any red: read the logged answer in `evals/runs/*.jsonl` **before** concluding anything, then escalate that case once with `--repeat 8` and treat that verdict as final in both directions. Do not re-run until green, and do not widen an anchor to make a red disappear — read the answer and report whether the anchor was narrow or the product was wrong.

- [ ] **Step 6: Commit**

```bash
git add evals/eval_set.py
git commit -m "Cover the budget and crop_choice routes in the eval set"
```

---

### Task 7: Run the gates and record what came back

**Files:**
- Create: `docs/superpowers/2026-08-11-budget-and-crop-choice-findings.md`

- [ ] **Step 1: Confirm generation speed before measuring**

```bash
PYTHONIOENCODING=utf-8 python -c "
import time, statistics
from src import engine
c = engine._get_llm(); p = engine._chat_profile()
r = []
for _ in range(3):
    t0 = time.time()
    x = c.chat.completions.create(model=p.model, max_tokens=400, temperature=0.4,
        messages=[{'role':'user','content':'Domateste azotun rolunu 150 kelimeyle anlat.'}])
    r.append(x.usage.completion_tokens/(time.time()-t0))
print(f'{statistics.median(r[1:]):.1f} tok/s')
"
```

If this reads in single digits or the low teens, **run `Get-Counter '\GPU Process Memory(*)\Shared Usage'` first.** A large shared figure for `llama-server` means the documented VRAM spill — eject and reload the model. A small one means the other fault, and the only fix measured to work is a full machine reboot. Do not spend time on runtimes or background apps; that was measured on 2026-08-10 and neither helped.

- [ ] **Step 2: Unit suite**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q` — record the count.

- [ ] **Step 3: Routing gates**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_routing` — record the full output, including that the 0.90 accuracy gate is still red at 37/42 and was not relaxed.

- [ ] **Step 4: Regression shield**

Run `--fast` and then the full run. Record both, and any red with the analysis from Task 6 Step 5.

- [ ] **Step 5: Look at real answers**

A green suite is not evidence that the output reads well. Run all three by hand and read them:

```bash
PYTHONIOENCODING=utf-8 python -c "
from src import engine
for q in ['5 dekar mısır ektim, dekara 400 kg aldım, kilosu 12,5 TL, masrafım 20000 TL. Kârım ne?',
          'Buğday ekmenin dekara maliyeti nedir?',
          \"Manisa'dayım, bu yıl tarlama ne eksem iyi olur?\"]:
    r = engine.answer(q)
    print('='*70); print(r.route, '|', q); print('-'*70); print(r.answer); print()
"
```

What they must do: the first states 25 000 TL revenue and 5 000 TL margin and carries the framing sentence; the second names cost items and asks for the four values without inventing any; the third explains the factors and does not name a crop to plant. **Paste all three verbatim, including if one reads badly.**

- [ ] **Step 6: Write the findings**

Create `docs/superpowers/2026-08-11-budget-and-crop-choice-findings.md` recording: measured tok/s, unit count, routing gates and the dispatch-safe list, the eval result with any red analysed, the extractor's output over the frozen budget set, the three real answers, and what remains blocked on the numeric data layer.

State plainly that **six of the seven frozen budget questions extract no numbers and therefore never reach the arithmetic**, and that two of them — orchard establishment cost and multi-year payback — are outside the four-slot model by design (spec §7).

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/2026-08-11-budget-and-crop-choice-findings.md
git commit -m "Record budget and crop-choice gate results"
```

---

## What this plan deliberately leaves undone

- **The numeric data layer.** R1–R4 of `docs/client-requirements.md` are not addressed here. Until it lands there are no default yields or prices, and a user who supplies nothing gets questions. That is the honest state.
- **Establishment cost and multi-year payback.** Two questions in the frozen budget set need them; both get the cost-structure answer and no calculation. Spec §7.
- **Crop recommendation.** `crop_choice` explains and asks; it does not name a crop. The prohibition is measured through `answer_none`, not enforced in code, and the spec says so.
- **`crop` is extracted by nothing.** `BudgetInputs.crop` exists in the dataclass but is always `None`; no arithmetic uses it. It is there because the numeric data layer will key on it, and adding the field now costs nothing while changing the dataclass later would touch every caller.
