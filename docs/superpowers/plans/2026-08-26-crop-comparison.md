# Crop Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a farmer has narrowed to two crops, put the published figures for both — for their own province — side by side, and refuse to say which one to plant.

**Architecture:** A new route module `src/crop_compare.py` holds crop-name detection, validation, the one multiplication per crop, and the Turkish. The engine's existing `crop_choice` branch gains a fork: a message naming **two or more distinct crops** gets the comparison card; every other `crop_choice` message keeps today's factors answer, untouched. **`src/router.py` is not modified at all**, so the pre-registered routing set cannot move.

**Tech Stack:** Python 3.14 + FastAPI + pytest (server); Expo / React Native + TypeScript (client). No new dependencies.

Spec: `docs/superpowers/specs/2026-08-26-crop-comparison-design.md`
Branch point: `crop-comparison` at `bfe6c26`, `pytest -q` = **852 passed**.

## Global Constraints

- **Every user-facing string is Turkish and is written by code.** No model call, no retrieval, no product matching on this route.
- **Nothing that reaches arithmetic is read from the question.** The two crops arrive as explicit card selections. Crop-name detection decides only WHICH ANSWER to show; a wrong detection costs a card the farmer can ignore, never a wrong figure.
- **The answer never names a winner.** It prints both crops' figures and a code-written sentence saying gross revenue is not profit.
- **Price comes only from the dataset's most recent year**; a crop whose price is older shows no revenue figure. **Yield may be older** and shows its five-year range. (P2b's measured rule: lira is nominal, a yield is a physical quantity.)
- **A missing half means no revenue for that crop, and the answer names which half was missing.** Never zero.
- **Every figure prints its year and region.**
- **No area input.** Area applies the same multiplier to both crops; everything stays per dekar.
- **The open "ne eksem?" question keeps today's answer** — the factors context block, pinned by `evals/eval_set.py::crop_choice_gives_factors_not_a_recommendation`.
- **`src/router.py` and `evals/routing_set.py` are NOT touched by this plan.**
- **Both transports or neither.** `engine.answer()` and `engine.stream_answer()` are mirror images.
- **Wire changes are additive**: a new response key, a new SSE event type, a new request field. An already-deployed APK ignores all three and keeps working.
- **No eval case** — the route makes no model call, so a case there would read green while asserting nothing.
- **Turkish numbers go through `src/budget.py`'s formatters only** (`format_tr`, `format_qty`, `parse_tr_number`, `coerce_number`).
- Run everything from the repo root — `src/config.py` reads a relative `.env`.
- Commits: one per task, English, short and natural, **no `Co-Authored-By` trailer**.
- `pytest -q` green at the end of every task, starting from 852 passed.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/crop_compare.py` | **Create.** Crop-name detection, validation, the card spec, the arithmetic, the Turkish. |
| `src/engine.py` | **Modify.** `_compare_result`, `ChatResult.compare_form`, the fork inside the `crop_choice` branch, both transports. |
| `src/main.py` | **Modify.** `ComparePayload` request field, `compare_form` response key. |
| `mobile-app/src/api.ts` | **Modify.** Compare types, the `compare_form` SSE event, the `compare` request field. |
| `mobile-app/src/CompareCard.tsx` | **Create.** Two crop selects and a submit button. |
| `mobile-app/app/(tabs)/chat.tsx` | **Modify.** Render the card, consume it on submit. |
| `tests/test_crop_compare.py` | **Create.** Detection, validation, arithmetic, Turkish. |
| `tests/test_compare_route.py` | **Create.** The engine fork and both transports. |

---

## Task 1: Which crops did the farmer name?

The fork needs one question answered: does this message name two different crops the table carries? This is the only part of the route that reads the question at all, and it decides nothing but which answer to show.

**Files:**
- Create: `src/crop_compare.py`
- Test: `tests/test_crop_compare.py`

**Interfaces:**
- Consumes: `norms.available_crops() -> tuple[tuple[str, str], ...]` (crop id, display label), `engine._normalize_tr`, `engine._TR_SUFFIXES`.
- Produces: `crop_compare.named_crops(message: str) -> tuple[str, ...]` returning the display FAMILY names found, in the order they were found.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_crop_compare.py`:

```python
"""Unit tests for src/crop_compare.py (no network, no store, no model)."""

import json

import pytest

from src import crop_compare, norms


TABLE = {
    # FOUR years, not two, and that is load-bearing: norms._recent_range needs at
    # least TWO values before the picked year or it returns (None, None), and the
    # five-year range would silently never reach the answer.
    "meta": {"generated": "2026-08-26", "years": [2022, 2023, 2024, 2025]},
    "crops": {
        "domates (sofralik)": {
            "label": "Domates (Sofralık)",
            "yield_kg_da": {"scope": "il", "Konya": [4930.6, 5100.0, 6473.1, 5492.1],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [12.0, 15.0, 18.0, 21.06],
                            "TR": [None, None, None, None]},
        },
        "biber (salcalik, kapya)": {
            "label": "Biber (Salçalık, Kapya)",
            "yield_kg_da": {"scope": "il", "Konya": [2997.5, 3100.0, 3732.6, 3154.7],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [20.0, 25.0, 30.0, 39.89],
                            "TR": [None, None, None, None]},
        },
        "tatli patates": {
            "label": "Tatlı Patates",
            "yield_kg_da": {"scope": "il", "Konya": [1900.0, 2000.0, 2050.0, 2100.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [8.0, 9.0, 10.0, 12.0],
                            "TR": [None, None, None, None]},
        },
        "arpa (biralik)": {
            "label": "Arpa (Biralık)",
            "yield_kg_da": {"scope": "il", "Konya": [380.0, 395.0, 410.0, 420.0],
                            "TR": [None, None, None, None]},
            "price_tl_kg": {"scope": "il", "Konya": [6.0, 7.0, 8.0, 9.5],
                            "TR": [None, None, None, None]},
        },
    },
}


@pytest.fixture(autouse=True)
def table(tmp_path, monkeypatch):
    """Every test here runs against a fixture table, never the shipped file:
    a real crop's figures changing must not turn these red."""
    path = tmp_path / "crop_norms.json"
    path.write_text(json.dumps(TABLE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    crop_compare._families.cache_clear()
    yield
    norms._load.cache_clear()
    crop_compare._families.cache_clear()


def test_two_crops_are_found_in_a_comparison_question():
    assert crop_compare.named_crops(
        "Bu yıl domates mi biber mi ekmeliyim?") == ("Domates", "Biber")


def test_a_crop_is_found_through_a_turkish_suffix():
    """'domatesi', 'bibere' - the matcher must see the name through a case
    ending, the same way the retrieval lexicon's matcher does."""
    assert crop_compare.named_crops("Domatesi mi bibere mi yatırım yapsam?") == (
        "Domates", "Biber")


def test_a_name_inside_a_longer_word_is_not_a_crop():
    """The bounded-suffix matcher exists so 'arpa' does not fire inside
    'arpacık' - a stye, not a barley field."""
    assert crop_compare.named_crops("Gözümde arpacık çıktı, ne yapmalıyım?") == ()


def test_a_two_word_crop_is_one_crop_not_two():
    """'Tatlı Patates' contains 'Patates'. Counting both would turn one crop
    into a comparison the farmer never asked for."""
    assert crop_compare.named_crops("Tatlı patates ekmeyi düşünüyorum") == (
        "Tatlı Patates",)


def test_an_open_question_names_no_crop():
    assert crop_compare.named_crops("Bu yıl tarlama ne eksem iyi olur?") == ()


def test_the_same_crop_twice_is_one_crop():
    assert crop_compare.named_crops("Domates mi domates mi?") == ("Domates",)


def test_a_crop_the_table_does_not_carry_is_not_found():
    assert crop_compare.named_crops("Kahve mi kakao mu yetiştirsem?") == ()


def test_detection_never_raises_on_junk():
    for junk in ("", None, "?!.", "12345"):
        assert crop_compare.named_crops(junk) == ()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_crop_compare.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.crop_compare'`.

- [ ] **Step 3: Write the module**

Create `src/crop_compare.py`:

```python
"""Two crops the farmer picked, side by side, and no verdict.

THE MODEL PERFORMS NO ARITHMETIC AND MAKES NO APPEARANCE. Every number a user
sees from this route is computed here, in Python, from figures TUIK published.

WHAT THIS ROUTE REFUSES IS THE POINT. It prints gross revenue per dekar for
each crop and says, in a sentence written by code, that gross revenue is not
profit - because this project holds NO cost data at all, and two crops' costs
can differ by more than the difference the farmer is looking at. Measured on
Konya 2025: domates 115.664 TL/da against biber 125.841 TL/da, nine percent
apart, which says nothing at all about which one pays better.

NOTHING THAT REACHES ARITHMETIC IS READ FROM THE QUESTION. named_crops() below
reads the message, but only to decide WHICH ANSWER to show; the figures come
from two explicit card selections. A wrong detection costs a card the farmer
can ignore. `Biber` alone is five different rows in the table, with five
different yields - which row is meant is the card's question, never ours.

This module imports `_normalize_tr` and `_TR_SUFFIXES` from src/engine.py the
same way src/router.py does, and for the same reason: the engine imports THIS
module lazily, inside the function that uses it, so the cycle is never real.
"""
from __future__ import annotations

import re
from functools import lru_cache

from src import norms
from src.engine import _TR_SUFFIXES, _normalize_tr


@lru_cache(maxsize=1)
def _families() -> tuple[tuple[str, str], ...]:
    """(folded family name, display family) for every crop the table carries.

    A crop FAMILY is the label with its variant stripped: `Domates (Sofralık)`
    and `Domates (Salçalık)` are both `Domates`, `Buğday, Durum Buğdayı Hariç`
    is `Buğday`. The farmer types the family; the card asks which row.

    Sorted longest first so a two-word family is tested before the one-word
    family inside it.
    """
    out: dict[str, str] = {}
    for _crop_id, label in norms.available_crops():
        family = re.split(r"\s*[(,]", label)[0].strip()
        if family:
            out.setdefault(_normalize_tr(family), family)
    return tuple(sorted(out.items(), key=lambda item: -len(item[0])))


def named_crops(message: str) -> tuple[str, ...]:
    """Every crop family this message names, in the order they appear.

    The matcher is the bounded-suffix one the crop lexicon already uses: a name
    may run into a Turkish case ending ("domatesi") but not into a different
    word ("arpacık" is a stye, not barley).

    A family contained inside a longer matched family is dropped: "tatlı
    patates" names ONE crop, and counting "patates" as a second would invent a
    comparison the farmer never asked for.
    """
    folded = _normalize_tr(message or "")
    if not folded:
        return ()

    hits: list[tuple[int, str, str]] = []
    for folded_family, display in _families():
        match = re.search(
            rf"(?<!\w){re.escape(folded_family)}(?:{_TR_SUFFIXES})?(?!\w)", folded)
        if match:
            hits.append((match.start(), folded_family, display))

    kept = [hit for hit in hits
            if not any(hit[1] != other[1] and hit[1] in other[1] for other in hits)]
    kept.sort(key=lambda hit: hit[0])
    return tuple(display for _start, _folded, display in kept)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_crop_compare.py -q`
Expected: PASS.

- [ ] **Step 5: Check the detector against the real table before trusting it**

The fixture has four crops; the shipped table has 187 families, and short ones (`Nar`, `Tere`, `Dut`, `Gül`) are where a matcher earns its keep or embarrasses itself. Run:

```bash
PYTHONIOENCODING=utf-8 python -c "
from src import crop_compare as cc
for m in ('Bu yıl domates mi biber mi ekmeliyim?',
          'Narenciye bahçesi kurmak istiyorum',
          'Tereyağı nasıl saklanır?',
          'Gülmekten karnım ağrıdı',
          'Nar mı dut mu daha kârlı?',
          'Bu yıl tarlama ne eksem iyi olur?'):
    print(f'{str(cc.named_crops(m)):40s} <- {m}')"
```

Expected: the first names Domates+Biber, the last names none. `Narenciye`, `Tereyağı` and `Gülmekten` must name NOTHING — if any of them fires, the bounded-suffix matcher is not doing its job and that is a finding to report. `Nar mı dut mu` naming two crops is correct.

Record the actual output in your report, whatever it is.

- [ ] **Step 6: Commit**

```bash
git add src/crop_compare.py tests/test_crop_compare.py && git commit -m "Read which crops a question names, and nothing else from it"
```

---

## Task 2: The card, and what the farmer must choose

**Files:**
- Modify: `src/crop_compare.py`
- Test: `tests/test_crop_compare.py`

**Interfaces:**
- Consumes: `norms.province_table(province) -> tuple[CropNorm, ...]` where `CropNorm(crop, label, yield_kg_da, price_tl_kg)`; `budget.FieldError(field, message)`.
- Produces: `crop_compare.CompareInputs(first: str, second: str, province: str | None)`, `crop_compare.validate(raw: object, table) -> tuple[CompareInputs | None, list[FieldError]]`, `crop_compare.form_spec(errors, table, submitted=None, province=None) -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_crop_compare.py`:

```python
def _table():
    return norms.province_table("Konya")


def _raw(first="domates (sofralik)", second="biber (salcalik, kapya)"):
    return {"first": first, "second": second}


def test_two_chosen_crops_validate():
    inputs, errors = crop_compare.validate(_raw(), _table())
    assert errors == []
    assert (inputs.first, inputs.second) == (
        "domates (sofralik)", "biber (salcalik, kapya)")


def test_both_crops_are_required():
    inputs, errors = crop_compare.validate({}, _table())
    assert inputs is None
    assert {e.field for e in errors} == {"first", "second"}


def test_the_same_crop_twice_is_refused():
    """A comparison needs two different crops; the same row twice is a form
    the user filled wrong, not a question we can answer."""
    inputs, errors = crop_compare.validate(
        _raw(second="domates (sofralik)"), _table())
    assert inputs is None
    assert [e.field for e in errors] == ["second"]


def test_a_crop_the_province_does_not_carry_is_a_field_error():
    inputs, errors = crop_compare.validate(_raw(first="yok bir urun"), _table())
    assert inputs is None
    assert [e.field for e in errors] == ["first"]


def test_validate_never_raises_on_junk():
    for junk in (None, [], "domates", {"first": 7, "second": None}):
        inputs, errors = crop_compare.validate(junk, _table())
        assert inputs is None and errors


def test_a_fresh_card_lists_every_crop_the_province_carries():
    spec = crop_compare.form_spec([], _table())
    assert spec["kind"] == "crop_compare"
    labels = [c["label"] for c in spec["crops"]]
    assert "Domates (Sofralık)" in labels and "Biber (Salçalık, Kapya)" in labels
    assert spec["first"] == "" and spec["second"] == ""
    assert all(v is None for v in spec["errors"].values())


def test_the_card_carries_only_ids_and_labels():
    """The budget card ships a whole province of prefill cells because it
    prefills; this one only fills two selects, and 246 rows of figures on the
    wire would be dead weight."""
    spec = crop_compare.form_spec([], _table())
    assert all(set(c) == {"id", "label"} for c in spec["crops"])


def test_a_rejected_card_echoes_what_was_chosen():
    raw = _raw(second="domates (sofralik)")
    _inputs, errors = crop_compare.validate(raw, _table())
    spec = crop_compare.form_spec(errors, _table(), raw)
    assert spec["first"] == "domates (sofralik)"
    assert spec["errors"]["second"]


def test_the_card_names_the_province_it_was_built_for():
    """The farmer has to be able to see which province's figures they are
    about to be shown - a wrong province is a wrong answer that reads right."""
    spec = crop_compare.form_spec([], _table(), None, "Konya")
    assert spec["province"] == "Konya"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_crop_compare.py -q`
Expected: FAIL — `AttributeError: module 'src.crop_compare' has no attribute 'validate'`.

- [ ] **Step 3: Implement**

Append to `src/crop_compare.py` (and add `from dataclasses import dataclass` plus `from src.budget import FieldError` to the imports at the top):

```python
@dataclass(frozen=True)
class CompareInputs:
    """Two crop ids the farmer chose, and the province their figures come from."""
    first: str
    second: str
    province: str | None = None


def _known(table) -> dict[str, str]:
    """crop id -> label, for the crops this province actually carries."""
    return {row.crop: row.label for row in (table or ())}


def validate(raw: object, table) -> tuple[CompareInputs | None, list[FieldError]]:
    """Read both selections, collect every error. Never raises.

    The ids are checked against the table rather than believed: they arrive
    from a client, and a crop we hold no row for must become a field error
    rather than an empty answer with no explanation.
    """
    raw = raw if isinstance(raw, dict) else {}
    known = _known(table)
    errors: list[FieldError] = []
    chosen: list[str] = []

    for field, label in (("first", "Birinci ürün"), ("second", "İkinci ürün")):
        value = raw.get(field)
        value = value.strip() if isinstance(value, str) else ""
        if not value:
            errors.append(FieldError(field, f"{label} seçin."))
        elif value not in known:
            errors.append(FieldError(
                field, f"{label} için bu ilde yayımlanmış bir rakam yok."))
        else:
            chosen.append(value)

    if len(chosen) == 2 and chosen[0] == chosen[1]:
        errors.append(FieldError(
            "second", "Karşılaştırma için iki farklı ürün seçin."))

    if errors:
        return None, errors
    return CompareInputs(first=chosen[0], second=chosen[1]), []


def form_spec(errors: list[FieldError], table, submitted: object = None,
              province: str | None = None) -> dict:
    """Serialise the card for the client, attaching each error to its field.

    Only ids and labels travel. The budget card ships a province of prefill
    cells because it prefills two fields from them; this card fills two selects
    and nothing else, and 246 rows of figures would be dead weight on the wire.
    """
    submitted = submitted if isinstance(submitted, dict) else {}
    by_field = {e.field: e.message for e in errors}
    first = submitted.get("first")
    second = submitted.get("second")
    return {
        "kind": "crop_compare",
        "province": province,
        "crops": [{"id": row.crop, "label": row.label} for row in (table or ())],
        "first": first if isinstance(first, str) else "",
        "second": second if isinstance(second, str) else "",
        "errors": {"first": by_field.get("first"),
                   "second": by_field.get("second")},
    }
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_crop_compare.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/crop_compare.py tests/test_crop_compare.py && git commit -m "Take the two crops from the card, and refuse what it garbles"
```

---

## Task 3: One multiplication per crop, and the Turkish that surrounds it

**Files:**
- Modify: `src/crop_compare.py`
- Test: `tests/test_crop_compare.py`

**Interfaces:**
- Consumes: `norms.latest_year() -> int | None`; `NormValue(amount, year, scope, region, recent_min, recent_max)`; `budget.format_tr`, `budget.format_qty`.
- Produces: `crop_compare.CropFigures(label, yield_value, price_value, revenue_tl_da, missing)`, `crop_compare.compute(inputs, table, latest_year) -> tuple[CropFigures, CropFigures]`, `crop_compare.render(inputs, figures) -> str`, and the constants `ATTRIBUTION`, `NOT_PROFIT`, `ASK_FOR_CROPS`, `COMPUTE_FAILED`, `NO_PROVINCE`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_crop_compare.py`:

```python
def test_gross_revenue_is_yield_times_price():
    inputs, _ = crop_compare.validate(_raw(), _table())
    first, second = crop_compare.compute(inputs, _table(), 2025)
    assert round(first.revenue_tl_da) == 115664      # 5492,1 x 21,06
    assert round(second.revenue_tl_da) == 125841     # 3154,7 x 39,89


def test_a_price_older_than_the_latest_year_yields_no_revenue():
    """Lira is nominal: P2b measured a 2018 price prefilling nine times too
    low. An older price is not a smaller figure, it is a different currency."""
    inputs, _ = crop_compare.validate(_raw(), _table())
    first, _second = crop_compare.compute(inputs, _table(), 2026)
    assert first.revenue_tl_da is None
    assert first.missing == "fiyat"


def test_a_missing_half_is_never_zero():
    """Absence, not 0: a zero flows into a revenue line as "this crop earns
    nothing", which is a claim we never measured."""
    inputs, _ = crop_compare.validate(_raw(), _table())
    first, _second = crop_compare.compute(inputs, _table(), 2026)
    assert first.revenue_tl_da is None


def test_each_figure_keeps_its_year_and_region():
    inputs, _ = crop_compare.validate(_raw(), _table())
    first, _second = crop_compare.compute(inputs, _table(), 2025)
    assert (first.yield_value.year, first.yield_value.region) == (2025, "Konya")


def test_the_answer_prints_both_crops_with_their_figures():
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    assert "Domates (Sofralık)" in text and "Biber (Salçalık, Kapya)" in text
    assert "115.664 TL" in text and "125.841 TL" in text


def test_the_answer_says_whose_figures_these_are():
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    assert crop_compare.ATTRIBUTION in text
    assert "TÜİK" in text and "2025" in text


def test_every_answer_refuses_the_profit_comparison():
    """The binding one. Two gross figures side by side read as a ranking, and
    the cost that would decide it is not in this project at all."""
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    assert crop_compare.NOT_PROFIT in text
    assert "masraf" in text


def test_the_answer_never_names_a_winner():
    """No sentence may recommend one of the two. The figures are the answer."""
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    for verdict in ("öneririm", "tercih edin", "daha kârlı", "daha iyi",
                    "tavsiye ederim", "seçin"):
        assert verdict not in text.lower(), verdict


def test_a_crop_with_a_missing_half_says_which_half():
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2026))
    assert "fiyat" in text
    assert "115.663" not in text and "115.664" not in text


def test_the_five_year_range_reaches_the_answer():
    inputs, _ = crop_compare.validate(_raw(), _table())
    text = crop_compare.render(inputs, crop_compare.compute(inputs, _table(), 2025))
    assert "önceki" in text
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_crop_compare.py -q`
Expected: FAIL — `AttributeError: module 'src.crop_compare' has no attribute 'compute'`.

- [ ] **Step 3: Implement the arithmetic**

Append to `src/crop_compare.py` (and add `format_qty, format_tr` to the `src.budget` import at the top):

```python
@dataclass(frozen=True)
class CropFigures:
    """One crop's published figures, and what they come to per dekar.

    `missing` names the half we do not hold - "verim" or "fiyat" - so the
    answer can say which one rather than printing a blank.
    """
    label: str
    yield_value: object | None       # norms.NormValue
    price_value: object | None       # norms.NormValue
    revenue_tl_da: float | None
    missing: str | None


def _figures(row, latest_year: int | None) -> CropFigures:
    yield_value = row.yield_kg_da
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
    elif price is None:
        missing = "fiyat"
    revenue = (None if missing is not None
               else yield_value.amount * price.amount)
    return CropFigures(label=row.label, yield_value=yield_value,
                       price_value=price, revenue_tl_da=revenue,
                       missing=missing)


def compute(inputs: CompareInputs, table,
            latest_year: int | None) -> tuple[CropFigures, CropFigures]:
    """All arithmetic for this route: one multiplication per crop.

    Never a comparison, a ratio or a difference. The two figures sit beside
    each other and the reader draws their own conclusion - which is the whole
    design, because the cost that would decide it is not in this project.
    """
    rows = {row.crop: row for row in (table or ())}
    return tuple(_figures(rows[crop_id], latest_year)
                 for crop_id in (inputs.first, inputs.second))
```

- [ ] **Step 4: Implement the Turkish**

Append to `src/crop_compare.py`:

```python
# Appended BY CODE on every computed answer, never asked of a model - the
# fertplan.FRAMING pattern.
ATTRIBUTION = (
    "Rakamlar TÜİK'in yayımladığı il ortalamalarıdır; tek bir tarlanın verimi "
    "veya sizin alacağınız fiyat için öngörü değildir."
)

# THE SENTENCE THIS ROUTE EXISTS FOR. Two gross figures side by side read as a
# ranking, and the number that would decide it - what each crop COSTS to grow -
# is not in this project at all. Measured on Konya 2025: domates 115.664 TL/da
# against biber 125.841 TL/da, nine percent apart, which tells a farmer nothing
# about which one pays better.
NOT_PROFIT = (
    "Bu rakamlar dekara BRÜT gelirdir, masraf içermez. İki ürünün girdi ve "
    "işçilik masrafı aradaki farktan çok daha fazla ayrışabilir, bu yüzden "
    "hangisinin daha kârlı olduğunu bu tablodan söyleyemem. Kendi masrafınızı "
    "girerek bütçe hesabı yaptırırsanız kâr karşılaştırmasını yapabilirsiniz."
)

ASK_FOR_CROPS = (
    "Karşılaştırayım: hangi iki ürünü düşünüyorsunuz? İkisini seçerseniz "
    "ilinizde yayımlanmış verim ve fiyat rakamlarını yan yana koyarım."
)

# Written to stand alone: without a province there is no provincial figure to
# print, and guessing one produces confidently wrong numbers.
NO_PROVINCE = (
    "Karşılaştırma yapabilmem için hangi ilde olduğunuzu bilmem gerekiyor; "
    "verim ve fiyat rakamları ilden ile değişiyor. İlinizi yazarsanız o ilin "
    "yayımlanmış rakamlarını yan yana koyarım."
)

# The failure mode of this route is silence, never a guess.
COMPUTE_FAILED = (
    "Karşılaştırmayı tamamlayamadım. Lütfen seçimlerinizi kontrol edip tekrar "
    "deneyin."
)


def _crop_block(figures: CropFigures) -> list[str]:
    """One crop's lines. Says what is missing rather than printing a blank."""
    if figures.missing == "verim":
        return [f"**{figures.label}**: bu il için yayımlanmış verim rakamı yok."]
    if figures.missing == "fiyat":
        return [f"**{figures.label}**: verim {format_qty(figures.yield_value.amount)} "
                f"kg/da ({figures.yield_value.year}), ancak güncel yıl için "
                f"yayımlanmış fiyat yok, bu yüzden gelir hesaplamıyorum."]

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


def render(inputs: CompareInputs, figures: tuple[CropFigures, CropFigures]) -> str:
    """Code-written Turkish. Both crops, no verdict."""
    where = f" ({inputs.province})" if inputs.province else ""
    lines = [f"İki ürünün yayımlanmış rakamları{where}:", ""]
    for crop in figures:
        lines.extend(_crop_block(crop))
        lines.append("")
    lines.extend([ATTRIBUTION, "", NOT_PROFIT])
    return "\n".join(lines)
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_crop_compare.py -q`
Expected: PASS.

- [ ] **Step 6: Read the rendered answer out loud**

Reading the rendered output found four defects no assertion caught on P2b, and a self-contradicting sentence on P3b. Do it here too.

```bash
PYTHONIOENCODING=utf-8 python -c "
from src import crop_compare as cc, norms
t = norms.province_table('Konya')
i, _ = cc.validate({'first': 'domates (sofralik)', 'second': 'biber (salcalik, kapya)'}, t)
i = cc.CompareInputs(i.first, i.second, 'Konya')
print(cc.render(i, cc.compute(i, t, norms.latest_year())))"
```

Read every line against the one next to it: does any sentence claim something the answer as a whole does not support? Does the layout survive on a phone-width bubble? Does anything read as a recommendation? Fix what reads wrong before moving on, and paste the output into your report.

- [ ] **Step 7: Commit**

```bash
git add src/crop_compare.py tests/test_crop_compare.py && git commit -m "Put both crops' figures side by side, and refuse to pick one"
```

---

## Task 4: Wiring — the fork inside `crop_choice`, and both transports

**Files:**
- Modify: `src/engine.py`, `src/main.py`
- Test: `tests/test_compare_route.py` (create), `tests/test_main.py`

**Interfaces:**
- Consumes: everything Tasks 1-3 produced; `norms.province_table`, `norms.latest_year`; `src.context.location.extract_province`.
- Produces: `engine.ChatResult.compare_form: dict | None`; `engine.answer(message, history=None, budget_payload=None, dose_payload=None, compare_payload=None)`; the same for `stream_answer`, emitting `{"type": "compare_form", "form": {...}}`; `/api/chat` accepting `compare` and returning `compare_form`.

- [ ] **Step 1: Write the failing route tests**

Create `tests/test_compare_route.py`:

```python
"""The crop-comparison route inside the engine: it must compute, and it must
not retrieve, match products, or call the model. The open 'ne eksem?' question
must keep the answer it has today."""

import json

import pytest

from src import crop_compare, engine


COMPARE_Q = "Konya'dayım, bu yıl domates mi biber mi ekmeliyim?"
OPEN_Q = "Konya'dayım, bu yıl tarlama ne eksem iyi olur?"


@pytest.fixture
def no_llm(monkeypatch):
    """Make every expensive path explode, so a test passes only if the route
    genuinely avoided it."""
    def boom(*args, **kwargs):
        raise AssertionError("the comparison route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return monkeypatch


def _payload(first="domates (sofralik)", second="biber (salcalik, kapya)"):
    return {"first": first, "second": second}


def test_a_two_crop_question_returns_the_card(no_llm):
    result = engine.answer(COMPARE_Q)
    assert result.route == "crop_choice"
    assert result.answer == crop_compare.ASK_FOR_CROPS
    assert result.compare_form["kind"] == "crop_compare"
    assert result.form is None and result.dose_form is None


def test_the_card_is_built_for_the_province_in_the_conversation(no_llm):
    assert engine.answer(COMPARE_Q).compare_form["province"] == "Konya"


def test_an_open_question_keeps_todays_answer(monkeypatch):
    """THE SHIPPED REFUSAL. 'Ne eksem?' still goes down the corpus path with
    the factors context block - this route does not take it over."""
    seen = {}

    def fake_context(message, history=None):
        seen["retrieved"] = True
        return ""

    monkeypatch.setattr(engine, "retrieve_context", fake_context)
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda *a, **k: "faktörler...")
    result = engine.answer(OPEN_Q)
    assert result.compare_form is None
    assert seen.get("retrieved") is True


def test_a_one_crop_question_keeps_todays_answer(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda *a, **k: "faktörler...")
    result = engine.answer("Konya'dayım, domates ekmeli miyim?")
    assert result.compare_form is None


def test_a_complete_payload_is_computed(no_llm):
    result = engine.answer(COMPARE_Q, None, None, None, _payload())
    assert result.compare_form is None
    assert crop_compare.NOT_PROFIT in result.answer


def test_a_rejected_payload_comes_back_as_a_card_with_errors(no_llm):
    result = engine.answer(COMPARE_Q, None, None, None,
                           _payload(second="domates (sofralik)"))
    assert result.compare_form["errors"]["second"]


def test_a_submitted_payload_is_computed_whatever_the_router_says(no_llm):
    """Turn 2 does not bet on the classifier a second time."""
    result = engine.answer("teşekkürler", None, None, None, _payload())
    assert result.compare_form is None
    assert crop_compare.NOT_PROFIT in result.answer


def test_no_province_asks_for_one_rather_than_guessing(no_llm):
    result = engine.answer("Domates mi biber mi ekmeliyim?")
    assert result.answer == crop_compare.NO_PROVINCE
    assert result.compare_form is None


def test_a_broken_computation_never_becomes_a_guess(no_llm, monkeypatch):
    monkeypatch.setattr(crop_compare, "compute", lambda *a: 1 / 0)
    result = engine.answer(COMPARE_Q, None, None, None, _payload())
    assert result.answer == crop_compare.COMPUTE_FAILED
    assert result.compare_form is None


def _events(chunks):
    return [json.loads(c.split("data: ", 1)[1]) for c in chunks if "data: " in c]


def test_the_stream_serves_the_same_card(no_llm):
    events = _events(list(engine.stream_answer(COMPARE_Q)))
    assert [e["type"] for e in events] == ["token", "compare_form", "done"]


def test_both_transports_answer_identically(no_llm):
    direct = engine.answer(COMPARE_Q, None, None, None, _payload()).answer
    streamed = "".join(e["content"] for e in
                       _events(list(engine.stream_answer(
                           COMPARE_Q, None, None, None, _payload())))
                       if e["type"] == "token")
    assert direct == streamed
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_compare_route.py -q`
Expected: FAIL — `TypeError: answer() takes from 1 to 4 positional arguments but 5 were given`.

- [ ] **Step 3: Add the result field**

In `src/engine.py`, extend `ChatResult` and `as_api`:

```python
    dose_form: dict | None = None
    # The comparison card travels on its own key for the same reason the dose
    # card does: an already-deployed APK reads `form` and draws a BUDGET card
    # from whatever arrives there.
    compare_form: dict | None = None

    def as_api(self) -> dict:
        return {
            "answer": self.answer,
            "recommended_products": [p.as_api() for p in self.recommended_products],
            "form": self.form,
            "dose_form": self.dose_form,
            "compare_form": self.compare_form,
        }
```

- [ ] **Step 4: Add the route helper**

Add next to `_dose_result` in `src/engine.py`:

```python
def _compare_result(payload: dict | None, message: str = "",
                    history: list[dict] | None = None) -> ChatResult:
    """The crop-comparison route: no retrieval, no product match, no model call.

    One multiplication per crop in src/crop_compare.py, over figures TUIK
    published. The province is resolved from the conversation the same way
    weather, fert_plan and the budget prefill resolve it - and when it cannot
    be resolved the route ASKS, because a provincial figure from the wrong
    province is a wrong answer that reads perfectly right.

    Deferred imports for the cycle src/router.py documents: crop_compare
    imports _normalize_tr from THIS module at load time.
    """
    from src import crop_compare, norms
    from src.context import location

    province = location.extract_province(message, history)
    if not province:
        return ChatResult(answer=crop_compare.NO_PROVINCE,
                          recommended_products=[], route="crop_choice")

    table = norms.province_table(province)
    submitted = bool(payload)
    try:
        inputs, errors = crop_compare.validate(payload or {}, table)
        if inputs is not None:
            inputs = crop_compare.CompareInputs(inputs.first, inputs.second, province)
            figures = crop_compare.compute(inputs, table, norms.latest_year())
            return ChatResult(answer=crop_compare.render(inputs, figures),
                              recommended_products=[], route="crop_choice")
    except Exception:  # noqa: BLE001 - a broken validation or sum must not become a guess
        return ChatResult(answer=crop_compare.COMPUTE_FAILED,
                          recommended_products=[], route="crop_choice")

    return ChatResult(answer=crop_compare.ASK_FOR_CROPS, recommended_products=[],
                      route="crop_choice",
                      compare_form=crop_compare.form_spec(
                          errors if submitted else [], table,
                          payload if submitted else None, province))
```

- [ ] **Step 5: Fork inside `crop_choice`, on both transports**

Change `answer`'s signature:

```python
def answer(message: str, history: list[dict] | None = None,
           budget_payload: dict | None = None,
           dose_payload: dict | None = None,
           compare_payload: dict | None = None) -> ChatResult:
```

Add this block immediately after the dose short-circuit and before the budget one:

```python
    # The comparison fork lives INSIDE crop_choice rather than in the router:
    # `crop_choice` already routes these questions correctly, and a new routing
    # rule would put the pre-registered frozen set at risk for nothing. An open
    # "ne eksem?" question names no crop, falls through this branch, and keeps
    # the factors answer it has today - which is a measured decision, not an
    # oversight.
    if compare_payload or (route == "crop_choice"
                           and len(_named_crops(message)) >= 2):
        result = _compare_result(compare_payload, message, history)
        result.route_how = route_how
        return result
```

Add the small helper above `_compare_result`, so both transports call one thing:

```python
def _named_crops(message: str) -> tuple[str, ...]:
    """Which crops this message names. Never raises: a detector failure must
    cost the card, not the answer."""
    try:
        from src import crop_compare
        return crop_compare.named_crops(message)
    except Exception as exc:  # noqa: BLE001
        print(f"[engine] crop detection failed, no comparison this turn: {exc}")
        return ()
```

Mirror both in `stream_answer` — the same signature addition, and:

```python
    if compare_payload or (route == "crop_choice"
                           and len(_named_crops(message)) >= 2):
        result = _compare_result(compare_payload, message, history)
        yield _sse({"type": "token", "content": result.answer})
        if result.compare_form is not None:
            yield _sse({"type": "compare_form", "form": result.compare_form})
        yield _sse({"type": "done"})
        return
```

- [ ] **Step 6: Run the route tests**

Run: `python -m pytest tests/test_compare_route.py -q`
Expected: PASS.

- [ ] **Step 7: Wire the API**

In `src/main.py`, add after `DosePayload`:

```python
class ComparePayload(BaseModel):
    first: str | None = None
    second: str | None = None
```

Add to `ChatRequest`:

```python
    compare: ComparePayload | None = Field(
        default=None, description="Filled crop-comparison card, when the user submitted one."
    )
```

Add to `ChatResponse`:

```python
    # Optional so an already-deployed client, which never reads it, is unaffected.
    compare_form: dict | None = None
```

And in `chat()`:

```python
    compare_payload = req.compare.model_dump() if req.compare else None

    if req.stream:
        return StreamingResponse(
            engine.stream_answer(req.message, history, budget_payload,
                                 dose_payload, compare_payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result = engine.answer(req.message, history, budget_payload, dose_payload,
                           compare_payload)
```

**Then fix the stubs this breaks.** `tests/test_main.py` monkeypatches `engine.answer`/`engine.stream_answer` with lambdas typed `(msg, hist, budget=None, dose=None)`. A fifth argument turns both into a `TypeError` that reads like a routing bug. Update every such stub in that file to `(msg, hist, budget=None, dose=None, compare=None)`.

Append to `tests/test_main.py` (note: `client` there is a module-level `TestClient`, not a fixture):

```python
def test_a_comparison_card_reaches_the_json_transport(monkeypatch):
    monkeypatch.setattr(
        main.engine, "answer",
        lambda msg, hist, budget=None, dose=None, compare=None:
            ChatResult(answer="x", recommended_products=[],
                       compare_form={"kind": "crop_compare"}))
    body = client.post("/api/chat", json={"message": "karşılaştır"}).json()
    assert body["compare_form"] == {"kind": "crop_compare"}


def test_a_submitted_comparison_payload_reaches_the_engine(monkeypatch):
    seen = {}

    def fake(msg, hist, budget=None, dose=None, compare=None):
        seen["compare"] = compare
        return ChatResult(answer="x", recommended_products=[])

    monkeypatch.setattr(main.engine, "answer", fake)
    client.post("/api/chat", json={
        "message": "karşılaştır",
        "compare": {"first": "domates (sofralik)", "second": "arpa (biralik)"}})
    assert seen["compare"]["first"] == "domates (sofralik)"
```

- [ ] **Step 8: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS, 852 + the new tests.

Then confirm the frozen routing set really is untouched:

Run: `python -m evals.run_routing`
Expected: **46/51, KAPILAR: GECTI** — byte-identical to before this branch, because `src/router.py` was not modified.

- [ ] **Step 9: Drive it against a live server, both transports**

This route makes no model call, so no LM Studio is needed.

```bash
python -m uvicorn src.main:app --port 8000
```

In a second shell, using a UTF-8 payload FILE rather than an inline `-d` (Git Bash mangles a dotted İ on the wire):

```bash
printf '{"message":"Konya%%27day%%C4%%B1m, bu y%%C4%%B1l domates mi biber mi ekmeliyim?"}' > /tmp/q.json
curl -s -X POST localhost:8000/api/chat -H "Content-Type: application/json" --data-binary @/tmp/q.json | python -m json.tool
```

Expected: `compare_form.kind == "crop_compare"`, `province` = `Konya`, `form` and `dose_form` null. Then submit a payload the same way and confirm the answer carries both crops and both closing sentences. Paste both responses into your report.

- [ ] **Step 10: Commit**

```bash
git add src/engine.py src/main.py tests/ && git commit -m "Serve the comparison inside crop_choice, on both transports"
```

---

## Task 5: The card

**Files:**
- Modify: `mobile-app/src/api.ts`, `mobile-app/app/(tabs)/chat.tsx`
- Create: `mobile-app/src/CompareCard.tsx`

**Interfaces:**
- Consumes: the `compare_form` SSE event and the `compare` request field from Task 4; `fold` from `mobile-app/src/turkish.ts`.
- Produces: `ComparePayload`, `CompareFormSpec`, `sendChatMessageStream(message, history, handlers, budget?, dose?, compare?)`, `<CompareCard form onSubmit disabled />`.

- [ ] **Step 1: Add the wire types**

In `mobile-app/src/api.ts`, after the dose types:

```ts
export interface ComparePayload {
  first?: string;
  second?: string;
}

export interface CompareCrop {
  id: string;
  label: string;
}

export interface CompareFormSpec {
  kind: "crop_compare";
  province: string | null;
  crops: CompareCrop[];
  first: string;
  second: string;
  errors: { first: string | null; second: string | null };
}
```

Add the handler and the event branch:

```ts
  onCompareForm?: (form: CompareFormSpec) => void;
```

```ts
      } else if (evt.type === "compare_form") {
        handlers.onCompareForm?.(evt.form);
      }
```

And the request field:

```ts
export function sendChatMessageStream(
  message: string,
  history: ChatTurn[],
  handlers: ChatStreamHandlers,
  budget?: BudgetPayload,
  dose?: DosePayload,
  compare?: ComparePayload
): void {
```

```ts
  xhr.send(JSON.stringify({ message, history, stream: true, budget, dose, compare }));
```

- [ ] **Step 2: Write the card**

Create `mobile-app/src/CompareCard.tsx`:

```tsx
// The crop-comparison card: two searchable selects and nothing else.
//
// There is no area field on purpose - area applies the same multiplier to both
// crops, so it cannot change the comparison, and every figure stays per dekar.
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { CompareCrop, CompareFormSpec, ComparePayload } from "./api";
import { colors } from "./theme";
import { fold } from "./turkish";

interface Props {
  form: CompareFormSpec;
  // `summary` is what the chat shows as the user's bubble for this turn.
  onSubmit: (payload: ComparePayload, summary: string) => void;
  disabled: boolean;
}

function labelOf(form: CompareFormSpec, id: string): string {
  return form.crops.find((c) => c.id === id)?.label ?? "";
}

export default function CompareCard({ form, onSubmit, disabled }: Props) {
  const [first, setFirst] = useState(form.first);
  const [second, setSecond] = useState(form.second);
  const [queryOne, setQueryOne] = useState(labelOf(form, form.first));
  const [queryTwo, setQueryTwo] = useState(labelOf(form, form.second));

  function matches(query: string, chosen: string): CompareCrop[] {
    const open = Boolean(query.trim() && query !== labelOf(form, chosen));
    if (!open) return [];
    return form.crops
      .filter((c) => fold(c.label).includes(fold(query)))
      .slice(0, 8);
  }

  function submit() {
    if (disabled) return;
    const summary = [labelOf(form, first), labelOf(form, second)]
      .filter(Boolean)
      .join(" ↔ ");
    onSubmit({ first, second }, summary || "karşılaştır");
  }

  function select(
    slot: "first" | "second",
    option: CompareCrop,
  ) {
    if (slot === "first") {
      setFirst(option.id);
      setQueryOne(option.label);
    } else {
      setSecond(option.id);
      setQueryTwo(option.label);
    }
  }

  const rows: {
    slot: "first" | "second";
    label: string;
    query: string;
    setQuery: (t: string) => void;
    chosen: string;
    error: string | null;
  }[] = [
    { slot: "first", label: "Birinci ürün", query: queryOne, setQuery: setQueryOne, chosen: first, error: form.errors.first },
    { slot: "second", label: "İkinci ürün", query: queryTwo, setQuery: setQueryTwo, chosen: second, error: form.errors.second },
  ];

  return (
    <View style={styles.card}>
      {form.province ? (
        <Text style={styles.note}>{form.province} için yayımlanmış rakamlar</Text>
      ) : null}
      {rows.map((row) => (
        <View key={row.slot} style={styles.row}>
          <Text style={styles.label}>{row.label}</Text>
          <TextInput
            style={styles.input}
            value={row.query}
            onChangeText={row.setQuery}
            placeholder="Ürün arayın (örn. domates)"
            placeholderTextColor="#9aa"
          />
          {matches(row.query, row.chosen).map((option) => (
            <Pressable
              key={option.id}
              style={styles.match}
              onPress={() => select(row.slot, option)}
            >
              <Text style={styles.matchText}>{option.label}</Text>
            </Pressable>
          ))}
          {row.error ? <Text style={styles.error}>{row.error}</Text> : null}
        </View>
      ))}
      <Pressable
        style={[styles.submit, disabled && styles.submitDisabled]}
        onPress={submit}
        disabled={disabled}
      >
        <Text style={styles.submitText}>Karşılaştır</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e2e8e2",
    padding: 14,
    marginTop: 8,
    gap: 12,
  },
  row: { gap: 6 },
  label: { fontSize: 13, fontWeight: "600", color: colors.dark },
  note: { fontSize: 11, color: "#6b7a6b" },
  input: {
    borderWidth: 1,
    borderColor: "#e2e8e2",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    color: colors.dark,
  },
  error: { fontSize: 12, color: "#c0392b" },
  match: {
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e2e8e2",
  },
  matchText: { fontSize: 13, color: colors.dark },
  submit: {
    backgroundColor: colors.green,
    borderRadius: 8,
    paddingVertical: 11,
    alignItems: "center",
  },
  submitDisabled: { opacity: 0.5 },
  submitText: { color: "#fff", fontWeight: "700" },
});
```

- [ ] **Step 3: Render it in the chat**

In `mobile-app/app/(tabs)/chat.tsx`:

```tsx
import CompareCard from "../../src/CompareCard";
```

Add `ComparePayload` and `CompareFormSpec` to the `./api` import list, extend the `Message` type with `compareForm?: CompareFormSpec;`, extend `sendTurn`:

```tsx
  function sendTurn(text: string, budget?: BudgetPayload, dose?: DosePayload,
                    compare?: ComparePayload) {
```

```tsx
      onCompareForm: (compareForm) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, compareForm, question: text } : m))
        );
      },
```

```tsx
    }, budget, dose, compare);
```

Render it beside the other two cards inside the same `messages.map`:

```tsx
              {m.compareForm && (
                <CompareCard
                  form={m.compareForm}
                  disabled={loading}
                  onSubmit={(payload, summary) => {
                    if (loading) return;
                    setMessages((prev) => [
                      ...prev.map((x) =>
                        x.id === m.id ? { ...x, compareForm: undefined } : x
                      ),
                      { id: newId(), role: "user", text: summary },
                    ]);
                    sendTurn(m.question ?? summary, undefined, undefined, payload);
                  }}
                />
              )}
```

And strip it before persisting, beside `form` and `doseForm`:

```tsx
      messages: messages.map(({ form, doseForm, compareForm, ...rest }) => rest) as never,
```

- [ ] **Step 4: Typecheck**

`npx tsc` is broken in this repo because of the `&` in the folder path. Run:

```bash
cd mobile-app && node "node_modules/typescript/bin/tsc" --noEmit
```

Expected: no output, exit 0.

- [ ] **Step 5: Commit**

```bash
git add mobile-app/src/api.ts mobile-app/src/CompareCard.tsx "mobile-app/app/(tabs)/chat.tsx" && git commit -m "Draw the comparison card, and consume it on submit"
```

---

## Task 6: Drive it for real, then write it down

**Files:**
- Create: `docs/superpowers/2026-08-26-crop-comparison-findings.md`
- Modify: `docs/superpowers/specs/2026-08-26-crop-comparison-design.md` (status), `.superpowers/sdd/progress.md`

- [ ] **Step 1: Run the app and press the card**

Two traps this project has already paid for: pass the API base as SHELL ENV ONLY (there is no `mobile-app/.env`, and creating one would bake `127.0.0.1` into the next APK), and never sleep a fixed number of seconds — wait for content.

```bash
python -m uvicorn src.main:app --port 8000
```

```bash
cd mobile-app && EXPO_PUBLIC_API_BASE=http://127.0.0.1:8000 node node_modules/expo/bin/cli start --web --clear
```

Every screen sits behind a local sign-up; create a throwaway profile to reach the chat. Then confirm each of these by looking at the screen:

1. Ask `Konya'dayım, bu yıl domates mi biber mi ekmeliyim?` → the sentence appears with the card under it, and the card says which province it is for.
2. Typing `domates` in the first select finds `Domates (Sofralık)` and `Domates (Salçalık)`; picking one fills the box.
3. Submitting with only one crop chosen returns the card with the error on the empty select and the first choice still there.
4. Picking the same crop twice returns the "iki farklı ürün" error.
5. A full submit shows the user's bubble as the two crop names, then an answer carrying both crops' yield, price, gross revenue, the five-year range, and BOTH closing sentences.
6. The card is gone after submit and cannot be submitted twice.
7. After a reload the conversation restores with no interactive card.
8. Ask `Konya'dayım, bu yıl tarlama ne eksem iyi olur?` → **no card**, and the old factors answer (this one needs LM Studio; if it is not running, the fallback message is fine — what matters is that no card appears).

Fix what is wrong in the source, never in the browser, then re-check from step 1.

- [ ] **Step 2: Screenshot the card and a computed answer**

Put them in `docs/screenshots/`, following that directory's naming style.

- [ ] **Step 3: Write the findings**

Create `docs/superpowers/2026-08-26-crop-comparison-findings.md` recording: the detector's output on the real 187-family table (Task 1 Step 5); what the rendered answer looks like; anything Step 1 found that no test caught, and whether a test now catches it; the routing numbers before and after (they must be identical — `src/router.py` was not touched); and what is still open, naming the two the spec scopes out: ranking a province's crops, and any profit figure.

- [ ] **Step 4: Update the spec's status and the records**

Mark P4 done with its merge commit in the spec's §11 table. Append the round to `.superpowers/sdd/progress.md`, and rewrite the handoff memory's top block: what shipped, the new pytest count, and that **Emirhan needs a new APK** for this card too (the client reads a new SSE event and sends a new request field; an older build shows the sentence and no card).

- [ ] **Step 5: Full suite one last time**

Run: `python -m pytest -q` — PASS.
Run: `python -m evals.run_routing` — **46/51, unchanged**.

- [ ] **Step 6: Commit**

```bash
git add docs .superpowers && git commit -m "Record what the comparison ships and what it refuses"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Where |
| --- | --- |
| §2.1 both crops' figures for the farmer's province | Tasks 2-3 |
| §2.2 refuses to say which to plant, and says why | Task 3 (`NOT_PROFIT`, `test_the_answer_never_names_a_winner`) |
| §2.3 every figure attributed | Task 3 (`test_each_figure_keeps_its_year_and_region`) |
| §2.4 a missing half means no revenue, never zero | Task 3 (`test_a_missing_half_is_never_zero`) |
| §2.5 no model call, no retrieval, pytest only | Task 4 (`no_llm` on every route test) |
| §2.6 the open question keeps today's answer | Task 4 (`test_an_open_question_keeps_todays_answer`) |
| §3 the answer/refusal table | Tasks 3-4 |
| §4 inputs from a card; no area field; province from the conversation | Tasks 2, 4, 5 |
| §5 arithmetic, price latest-year only, yield range, provenance | Task 3 |
| §6 the fork, and the routing matcher never reaching arithmetic | Tasks 1, 4 |
| §7 both code-written sentences | Task 3 |
| §8 every error row | Tasks 2 (field errors), 4 (`NO_PROVINCE`, `COMPUTE_FAILED`, empty table) |
| §9 the whole testing table | Tasks 1-5 |
| §10 out of scope | Not built; named in Task 6's findings |

**Placeholder scan:** none — every step carries its code, its command and its expected output.

**Type consistency:** `CompareInputs(first, second, province=None)` is constructed in Tasks 2 and 4 with those names; `CropFigures(label, yield_value, price_value, revenue_tl_da, missing)` is built in Task 3 and read by `_crop_block` and the tests; `form_spec(errors, table, submitted=None, province=None)` is called with four arguments in Task 4; `compare_form` is the response key, the SSE type and the `ChatResult` field in Tasks 4 and 5 alike.

**One risk the plan cannot test away:** the detector runs over 187 crop families, and short ones (`Nar`, `Dut`, `Tere`, `Gül`) sit inside ordinary Turkish words. The bounded-suffix matcher is what keeps them out, and Task 1 Step 5 is where a reader checks it against real sentences rather than fixtures. A false positive needs TWO of them in one message to produce a card, which is what makes the risk tolerable — but if Step 5 shows any of those firing, say so rather than moving on.
