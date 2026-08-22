# Budget Prefill (P2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A farmer who picks their crop sees the budget form's yield and price fields already filled with TÜİK's figures for their province, each showing its year, its region, and the range of the five years before it — and every figure is theirs to overwrite.

**Architecture:** The server resolves the province from the conversation, builds the whole province's norm table in one pass, and ships it **with** the form in the same SSE event. The card fills fields client-side from that table, with no round trip and no new endpoint. On submit the client declares which fields it prefilled; the server verifies each claim against its own lookup before letting the answer attribute a figure to TÜİK.

**Tech Stack:** Python 3.14, FastAPI, pytest. React Native / Expo (TypeScript) for the card. No new dependencies on either side.

**Spec:** `docs/superpowers/specs/2026-08-22-budget-prefill-design.md`, which amends §7/§8/§9 of `docs/superpowers/specs/2026-08-17-numeric-data-layer-design.md`. Both bind.

**This is P2b.** P2a (`b7415a2`) shipped the data. Nothing here re-derives it.

## Global Constraints

- **Run every command from the repo root.** `src/config.py` reads a root-anchored `.env`; from anywhere else unrelated tests fail.
- **Windows console cannot encode Turkish.** Prefix any command whose output shows Turkish with `PYTHONIOENCODING=utf-8`, or keep stdout ASCII.
- Shell is PowerShell: `&&` does not work; use `;` or separate calls.
- **Branch:** work on `budget-prefill`, which already exists off `main` and carries the spec. Do not touch `demo`. `main` is shared — rebase, never force-push.
- **`src/norms.py` imports nothing from `src/engine.py` and nothing from `src/context/location.py`.** A test already pins this. The province arrives as a string the caller resolved.
- **`src/budget.py` imports nothing from `src/engine.py`.** Values in, text out.
- **A missing norm is never 0.** Absence is `None`, never a zero, because a zero flows into the arithmetic and comes out as a confident wrong answer.
- **The route makes no model call and no retrieval.** Every test here is `pytest`. **No eval case is added** — the route never reaches the model, so a case there would read green while asserting nothing.
- **All user-facing Turkish is written in `src/budget.py`** and travels the wire as finished text, with every number already formatted by `format_tr`/`_format_qty`. The client formats no numbers and composes no sentences.
- **`form_spec(errors)` with no `table` and no `submitted` must stay byte-identical to P1's output.** An old deployed client depends on it.
- All code, comments, docstrings and test names in English. User-facing strings in Turkish.
- **Commit messages:** short, natural, English, capitalised verb. No `Co-Authored-By` trailer.
- Run the full suite (`pytest -q`) before each commit; the baseline entering this plan is **616 passing**.

---

### Task 1: The recent range on a norm value

**Files:**
- Modify: `src/norms.py` (`NormValue`, `_pick`)
- Test: `tests/test_norms.py`

**Interfaces:**
- Consumes: nothing
- Produces: `NormValue.recent_min: float | None`, `NormValue.recent_max: float | None` — min and max over the non-null values of the **five years preceding** the year the value itself came from

**Background.** `lookup()` returns the most recent non-null year. Hazelnut in Ordu reads `[41.0, 94.0, 79.4, 95.6, 86.8, 73.7, 105.6, 87.5, 88.9, 28.4]`, so the prefill is **28.4** where a typical year is 74–106. The range is what makes that visible. It must **exclude** the prefilled year: including 2025 gives `28.4–105.6`, whose lower bound is the prefill itself and which therefore says nothing.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_norms.py`:

```python
ALTERNATE = {
    "meta": {"generated": "2026-08-22", "years": [2020, 2021, 2022, 2023, 2024, 2025]},
    "crops": {
        "findik": {
            "label": "Fındık",
            # The prefilled year (28.4) is atypical; the five before it are not.
            "yield_kg_da": {"scope": "il",
                            "Ordu": [86.8, 73.7, 105.6, 87.5, 88.9, 28.4],
                            "TR": [None, None, None, None, None, None]},
            "price_tl_kg": {"scope": "il",
                            "Ordu": [None, None, None, None, None, 202.26],
                            "TR": [None, None, None, None, None, None]},
        }
    },
}


def test_the_recent_range_excludes_the_prefilled_year(tmp_path, monkeypatch):
    """Including it would make the prefill its own lower bound, which says
    nothing about whether the prefill is typical."""
    _write(tmp_path, monkeypatch, ALTERNATE)
    norm = norms.lookup("findik", "Ordu").yield_kg_da
    assert norm.amount == 28.4
    assert (norm.recent_min, norm.recent_max) == (73.7, 105.6)


def test_a_single_prior_value_yields_no_range(tmp_path, monkeypatch):
    """One number is not a range, and rendering '202,26-202,26' would dress a
    single observation as a spread."""
    _write(tmp_path, monkeypatch, ALTERNATE)
    norm = norms.lookup("findik", "Ordu").price_tl_kg
    assert norm.amount == 202.26
    assert (norm.recent_min, norm.recent_max) == (None, None)


def test_the_range_window_is_the_five_years_before_the_hit(tmp_path, monkeypatch):
    """Not the last five of the series: when the walk-back skips null years the
    window moves with it."""
    payload = {
        "meta": {"years": [2019, 2020, 2021, 2022, 2023, 2024, 2025]},
        "crops": {"x": {
            "label": "X",
            # Latest non-null is 2022; the window is 2019-2021, and 2023-2025
            # must not leak into it.
            "yield_kg_da": {"scope": "il", "TR": [10.0, 20.0, 30.0, 44.0, None, None, None]},
            "price_tl_kg": {"scope": "il", "TR": [1.0, 1.0, 1.0, 1.0, None, None, None]},
        }},
    }
    _write(tmp_path, monkeypatch, payload)
    norm = norms.lookup("x", None).yield_kg_da
    assert norm.year == 2022 and norm.amount == 44.0
    assert (norm.recent_min, norm.recent_max) == (10.0, 30.0)


def test_a_range_never_replaces_the_prefill(tmp_path, monkeypatch):
    """The published figure is what prefills, however atypical it is."""
    _write(tmp_path, monkeypatch, ALTERNATE)
    norm = norms.lookup("findik", "Ordu").yield_kg_da
    assert norm.amount == 28.4
    assert norm.amount < norm.recent_min
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_norms.py -k "recent or range" -q
```

Expected: FAIL with `AttributeError: 'NormValue' object has no attribute 'recent_min'`.

- [ ] **Step 3: Implement it**

In `src/norms.py`, extend the dataclass. The new fields default to `None` so every existing construction site and test keeps working:

```python
@dataclass(frozen=True)
class NormValue:
    """One figure and where it came from. The provenance travels with the value
    because a provincial reading and a national one must never look alike."""
    amount: float
    year: int
    scope: str          # "il" | "tr"
    region: str         # "Manisa" | "Türkiye"
    # The spread of the five years BEFORE this one. Not the last five of the
    # series: this figure is the one being prefilled, and a range that contains
    # it cannot say whether it is typical. None when fewer than two of those
    # years carry a value - one number is not a range.
    recent_min: float | None = None
    recent_max: float | None = None
```

Add the window helper above `_pick`:

```python
_RECENT_YEARS = 5


def _recent_range(series: list, index: int) -> tuple[float | None, float | None]:
    """Min and max of the non-null values in the five years before `index`."""
    window = [v for v in series[max(0, index - _RECENT_YEARS):index] if v is not None]
    if len(window) < 2:
        return None, None
    return float(min(window)), float(max(window))
```

In `_pick`, at the point where a non-null value is found:

```python
    for i in range(len(series) - 1, -1, -1):
        if series[i] is not None:
            low, high = _recent_range(series, i)
            return NormValue(
                amount=float(series[i]),
                year=years[i],
                scope="il" if provincial else "tr",
                region=key if provincial else NATIONAL_LABEL,
                recent_min=low,
                recent_max=high,
            )
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_norms.py -q
```

Expected: PASS, and every pre-existing `test_norms.py` test still passing — the defaults keep old constructions valid.

- [ ] **Step 5: Run the full suite**

```bash
python -m pytest -q
```

Expected: 620 passed (616 + 4).

- [ ] **Step 6: Commit**

```bash
git add src/norms.py tests/test_norms.py
git commit -m "Carry the five years before a norm, so an odd year shows as odd"
```

---

### Task 2: The province table in one pass

**Files:**
- Modify: `src/norms.py`
- Test: `tests/test_norms.py`

**Interfaces:**
- Consumes: `NormValue` with the range fields from Task 1
- Produces: `norms.province_table(province: str | None) -> tuple[CropNorm, ...]` — every crop in the file resolved for one province, sorted by label, same element type `lookup` already returns

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_norms.py`:

```python
def test_the_province_table_matches_calling_lookup_for_every_crop(tmp_path, monkeypatch):
    """One pass, same answers. If these ever diverge, the form and the
    verification on submit would disagree about what the norm is."""
    _write(tmp_path, monkeypatch, GOOD)
    table = norms.province_table("Manisa")
    one_by_one = tuple(norms.lookup(cid, "Manisa")
                       for cid, _ in norms.available_crops())
    assert table == one_by_one


def test_the_province_table_is_sorted_by_label(tmp_path, monkeypatch):
    payload = {
        "meta": {"years": [2024, 2025]},
        "crops": {
            "zeytin": {"label": "Zeytin",
                       "yield_kg_da": {"scope": "il", "TR": [1.0, 2.0]},
                       "price_tl_kg": {"scope": "il", "TR": [1.0, 2.0]}},
            "arpa": {"label": "Arpa",
                     "yield_kg_da": {"scope": "il", "TR": [1.0, 2.0]},
                     "price_tl_kg": {"scope": "il", "TR": [1.0, 2.0]}},
        },
    }
    _write(tmp_path, monkeypatch, payload)
    assert [r.label for r in norms.province_table(None)] == ["Arpa", "Zeytin"]


def test_a_broken_file_gives_an_empty_table_not_an_exception(tmp_path, monkeypatch):
    """A broken data file must not break answering - fertplan._load's rule."""
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms.province_table("Manisa") == ()


def test_a_national_scope_measure_reports_itself_as_national(tmp_path, monkeypatch):
    """Pinned against a synthetic fixture on purpose: the shipped file carries no
    populated TR rows today, so testing this against real data would assert
    nothing. The path must stay covered for the day those rows land."""
    payload = {
        "meta": {"years": [2024, 2025]},
        "crops": {"x": {
            "label": "X",
            "yield_kg_da": {"scope": "tr", "TR": [10.0, 11.0]},
            "price_tl_kg": {"scope": "tr", "TR": [1.0, 2.0]},
        }},
    }
    _write(tmp_path, monkeypatch, payload)
    row = norms.province_table("Manisa")[0]
    assert row.yield_kg_da.scope == "tr"
    assert row.yield_kg_da.region == "Türkiye"


def test_the_shipped_file_still_carries_provincial_yields():
    """A guard on the real data, not a fixture. If a converter change or a bad
    refresh empties the file, every prefill silently disappears and every other
    test here keeps passing on its fixtures. Measured on 2026-08-22: Manisa 142,
    Konya 147, Ordu 75, Van 73 of 246 crops. The floor is deliberately far below
    those, so an honest yearly refresh does not trip it."""
    norms._load.cache_clear()
    table = norms.province_table("Manisa")
    provincial = [r for r in table
                  if r.yield_kg_da is not None and r.yield_kg_da.scope == "il"]
    assert len(table) > 200
    assert len(provincial) > 100


def test_the_shipped_file_keeps_the_two_tomatoes_apart():
    """There is no single 'domates' norm - TUIK publishes Sofralik and Salcalik
    separately, and they are different crops with different prices. The crop
    list must offer both rather than one of them standing in for the other."""
    norms._load.cache_clear()
    labels = [label for _, label in norms.available_crops()]
    assert "Domates (Sofralık)" in labels
    assert "Domates (Salçalık)" in labels
    assert "Domates" not in labels
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_norms.py -k province_table -q
```

Expected: FAIL with `AttributeError: module 'src.norms' has no attribute 'province_table'`.

- [ ] **Step 3: Implement it**

Add to `src/norms.py`, below `lookup`:

```python
def province_table(province: str | None) -> tuple[CropNorm, ...]:
    """Every crop the file carries, resolved for one province, sorted by label.

    Identical to calling lookup() for each id in available_crops(), and pinned
    that way by a test - the form is built from this and the verification on
    submit is built from lookup(), so the two must never drift.

    It exists because the whole table travels to the client with the form: the
    crop is chosen there, so the server cannot know in advance which row will
    be needed and sends all of them.
    """
    data = _load()
    years = data.get("years")
    if not years:
        return ()
    rows = tuple(
        CropNorm(
            crop=crop_id,
            label=entry["label"],
            yield_kg_da=_pick(entry["yield_kg_da"], years, province),
            price_tl_kg=_pick(entry["price_tl_kg"], years, province),
        )
        for crop_id, entry in data["crops"].items()
    )
    return tuple(sorted(rows, key=lambda row: row.label))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_norms.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest -q
git add src/norms.py tests/test_norms.py
git commit -m "Resolve a whole province's norms in one pass"
```

Expected: 625 passed.

---

### Task 3: The `kg/dekar` unit and the per-area conversion

**Files:**
- Modify: `src/budget.py` (`UnitOption`, `FIELDS`, `_read`, `validate`)
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 — this task is independent of the norm layer
- Produces: `UnitOption.per_area: bool`; a `kg_da` unit on the `yield_total` field; `validate` resolving area before any per-area field

**Background.** P1 asks for the **total** harvest on purpose: a farmer who took 2 tons off 5 dönüm holds "2 ton" in mind, not "400 kg/da". But TÜİK's norm is per dekar, so the field has to be able to hold one. The conversion is `value × factor × (area_da if per_area else 1)`.

**The label must change too.** Once the field can hold a per-dekar figure, `"Toplam ürün"` is wrong under two of its three units, and a label that contradicts the selected unit is exactly the mismatch the unit selector exists to prevent.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`:

```python
def test_a_per_dekar_yield_equals_the_same_total_entered_directly():
    per_area = {
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "100", "unit": "kg_da"},
        "price": {"value": "10", "unit": "tl_kg"},
    }
    total = {
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "500", "unit": "kg"},
        "price": {"value": "10", "unit": "tl_kg"},
    }
    a, errs_a = budget.validate(per_area)
    b, errs_b = budget.validate(total)
    assert errs_a == [] and errs_b == []
    assert a.yield_kg.amount == b.yield_kg.amount == 500.0
    assert budget.compute(a).revenue_tl == budget.compute(b).revenue_tl


def test_a_per_dekar_yield_without_an_area_is_a_field_error_not_a_zero():
    """The binding rule: a value we cannot convert is refused, never quietly
    turned into 0 - a zero flows into the arithmetic and comes out confident."""
    inputs, errors = budget.validate({
        "yield_total": {"value": "100", "unit": "kg_da"},
        "price": {"value": "10", "unit": "tl_kg"},
    })
    assert inputs is None
    assert "yield_total" in {e.field for e in errors}


def test_a_per_dekar_yield_with_an_unparseable_area_is_also_refused():
    inputs, errors = budget.validate({
        "area": {"value": "beş", "unit": "donum"},
        "yield_total": {"value": "100", "unit": "kg_da"},
        "price": {"value": "10", "unit": "tl_kg"},
    })
    assert inputs is None
    assert {"area", "yield_total"} <= {e.field for e in errors}


def test_the_yield_label_reads_correctly_under_every_unit_it_offers():
    """'Toplam' is wrong for kg/dekar, and a label that contradicts the selected
    unit is the mismatch the selector exists to prevent."""
    spec = next(f for f in budget.FIELDS if f.id == "yield_total")
    assert "toplam" not in spec.label.lower()
    assert [u.id for u in spec.units] == ["kg", "ton", "kg_da"]
    assert [u.per_area for u in spec.units] == [False, False, True]


def test_the_original_units_are_untouched():
    """P1 regression: 2 ton off 5 donum is still 2000 kg."""
    inputs, errors = budget.validate({
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": "2", "unit": "ton"},
        "price": {"value": "10", "unit": "tl_kg"},
        "cost": {"value": "5000", "unit": "tl"},
    })
    assert errors == []
    assert inputs.yield_kg.amount == 2000.0
    assert budget.compute(inputs).margin_tl == 15000.0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -k "per_dekar or label or original_units" -q
```

Expected: FAIL — `kg_da` is not a known unit, so `validate` reports "birimi seçin".

- [ ] **Step 3: Implement it**

In `src/budget.py`, add the flag to `UnitOption`:

```python
@dataclass(frozen=True)
class UnitOption:
    id: str
    label: str
    factor: float          # multiply by this to reach the canonical unit
    # A per-area unit needs the area before it means anything. Kept a property
    # of the UNIT rather than a second field, so the conversion stays one line
    # and a new per-area unit needs no new branch.
    per_area: bool = False
```

Replace the `yield_total` entry in `FIELDS`:

```python
    # "Toplam" would be wrong under kg/dekar, so the label is neutral across all
    # three units. The per-dekar unit exists because TUIK publishes yields that
    # way and P2b prefills them; a farmer stating their own harvest still picks
    # kg or ton and states a total, exactly as in P1.
    FieldSpec("yield_total", "Ürün miktarı", True, 0.0, False,
              (UnitOption("kg", "kg", 1.0),
               UnitOption("ton", "ton", 1000.0),
               UnitOption("kg_da", "kg/dekar", 1.0, per_area=True))),
```

Give `_read` the area and the conversion. Change its signature and its tail:

```python
def _read(spec: FieldSpec, raw: dict, area_da: float | None
          ) -> tuple[Value | None, FieldError | None]:
```

and, after the min-value checks, replace the single `return`:

```python
    if unit.per_area:
        if area_da is None:
            # Refused, never multiplied by a guessed area and never zeroed.
            return None, FieldError(
                spec.id,
                f"{spec.label} için dekar başına değer girdiniz; "
                f"önce alanı doldurun.")
        amount = amount * area_da

    return Value(amount * unit.factor, "user"), None
```

Rewrite the loop in `validate` so the area is resolved first:

```python
    raw = raw if isinstance(raw, dict) else {}
    values: dict[str, Value | None] = {}
    errors: list[FieldError] = []

    # The area is read before everything else because a per-area unit cannot be
    # converted without it. Reading it out of FIELDS order rather than relying
    # on the tuple happening to list it first: that order is a layout decision,
    # not a contract, and a reorder would silently break every per-area field.
    area_spec = _FIELDS_BY_ID["area"]
    area_value, area_error = _read(area_spec, raw, None)
    values[area_spec.id] = area_value
    if area_error is not None:
        errors.append(area_error)
    area_da = area_value.amount if area_value is not None else None

    for spec in FIELDS:
        if spec.id == area_spec.id:
            continue
        value, error = _read(spec, raw, area_da)
        values[spec.id] = value
        if error is not None:
            errors.append(error)
```

Leave the rest of `validate` exactly as it is.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -q
```

Expected: PASS, including every P1 test.

- [ ] **Step 5: Check the errors are still reported all at once**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -k error -q
```

Expected: PASS. `validate` still collects every error rather than the first, so a user fixing a form is not walked through them one round trip at a time.

- [ ] **Step 6: Run the full suite and commit**

```bash
python -m pytest -q
git add src/budget.py tests/test_budget.py
git commit -m "Let the yield field hold a per-dekar figure"
```

Expected: 630 passed.

---

### Task 4: The norm table on the wire

**Files:**
- Modify: `src/budget.py` (`form_spec` and two new private helpers)
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `norms.province_table` (Task 2) → `tuple[CropNorm, ...]`; the `kg_da` unit (Task 3)
- Produces: `budget.form_spec(errors, table=None) -> dict` with an added `"crops"` key when a table is given. Each crop row is
  `{"id": str, "label": str, "yield": cell | None, "price": cell | None}` and each cell is
  `{"value": str, "unit": str, "note": str, "recent": str | None}`

**Background.** The crop is selected on the client, so the server cannot prefill one field — it sends every crop's figures and the card fills the fields when a crop is picked. Every number is **already formatted in Turkish** here; the client must never format one, because a second Turkish number formatter is a second place for a decimal comma to go wrong.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`:

```python
from src.norms import CropNorm, NormValue


def _table():
    return (
        CropNorm("findik", "Fındık",
                 NormValue(28.4, 2025, "il", "Ordu", 73.7, 105.6),
                 NormValue(202.26, 2025, "il", "Ordu", None, None)),
        CropNorm("misir", "Mısır",
                 NormValue(1100.0, 2024, "tr", "Türkiye", 900.0, 1200.0),
                 None),
    )


def test_a_form_with_no_table_is_byte_identical_to_p1():
    """An old deployed client reads this dict. Adding a key it does not expect
    is a wire change dressed as an addition."""
    assert budget.form_spec([]) == {
        "fields": [
            {"id": f.id, "label": f.label, "required": f.required,
             "units": [{"id": u.id, "label": u.label} for u in f.units],
             "value": "", "source": "empty", "error": None}
            for f in budget.FIELDS
        ]
    }
    assert "crops" not in budget.form_spec([])


def test_a_table_ships_every_crop_with_its_figures():
    spec = budget.form_spec([], _table())
    assert [c["id"] for c in spec["crops"]] == ["findik", "misir"]
    cell = spec["crops"][0]["yield"]
    assert cell["value"] == "28,4"
    assert cell["unit"] == "kg_da"
    assert cell["note"] == "TÜİK 2025, Ordu"
    assert cell["recent"] == "önceki 5 yıl: 73,7–105,6 kg/da"


def test_a_price_cell_carries_two_decimals_and_its_own_unit():
    spec = budget.form_spec([], _table())
    cell = spec["crops"][0]["price"]
    assert cell["value"] == "202,26"
    assert cell["unit"] == "tl_kg"
    assert cell["recent"] is None


def test_a_measure_with_no_norm_is_none_not_zero():
    """The binding rule, on the wire this time: absence is absence."""
    spec = budget.form_spec([], _table())
    assert spec["crops"][1]["price"] is None


def test_a_national_figure_names_turkiye_rather_than_looking_provincial():
    spec = budget.form_spec([], _table())
    assert spec["crops"][1]["yield"]["note"] == "TÜİK 2024, Türkiye"


def test_no_raw_float_reaches_the_wire():
    """Every figure is Turkish-formatted text. A float would arrive with a DOT
    decimal and parse_tr_number refuses those, so 28.4 would come back as a
    field error - or worse, as 284."""
    spec = budget.form_spec([], _table())
    for crop in spec["crops"]:
        for key in ("yield", "price"):
            if crop[key] is not None:
                assert isinstance(crop[key]["value"], str)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -k "table or wire or crops or byte_identical" -q
```

Expected: FAIL with `TypeError: form_spec() takes 1 positional argument but 2 were given`.

- [ ] **Step 3: Implement it**

Add above `form_spec` in `src/budget.py`:

```python
# The unit each measure is published in, and how it is written when it appears
# inside a sentence rather than on a chip.
_NORM_UNITS = {"yield": ("kg_da", "kg/da"), "price": ("tl_kg", "TL/kg")}


def _norm_cell(norm, unit_id: str, unit_text: str, decimals: int | None) -> dict | None:
    """One prefillable figure, finished for display.

    Everything the card shows for this figure is written HERE: the value in
    Turkish notation, the unit to select alongside it, where it came from, and
    the range of the years before it. The client renders strings and formats
    nothing - a second Turkish number formatter over there is a second place
    for a decimal comma to go wrong.
    """
    if norm is None:
        return None
    value = (_format_qty(norm.amount) if decimals is None
             else format_tr(norm.amount, decimals))
    recent = None
    if norm.recent_min is not None and norm.recent_max is not None:
        recent = (f"önceki 5 yıl: {_format_qty(norm.recent_min)}–"
                  f"{_format_qty(norm.recent_max)} {unit_text}")
    return {
        "value": value,
        # The unit travels WITH the value. Dropping 28,4 into a field still
        # reading "kg" would claim a whole orchard yielded 28 kilos.
        "unit": unit_id,
        "note": f"TÜİK {norm.year}, {norm.region}",
        "recent": recent,
    }


def _crop_rows(table) -> list[dict]:
    """Every crop's figures, for a card that picks one of them client-side."""
    rows = []
    for row in table:
        rows.append({
            "id": row.crop,
            "label": row.label,
            "yield": _norm_cell(row.yield_kg_da, *_NORM_UNITS["yield"], None),
            "price": _norm_cell(row.price_tl_kg, *_NORM_UNITS["price"], 2),
        })
    return rows
```

Change `form_spec`:

```python
def form_spec(errors: list[FieldError], table=None) -> dict:
    """Serialise FIELDS for the client, attaching each error to its own field.

    `table` is a province's worth of norms, from norms.province_table. When it
    is absent - no province resolved, or a broken data file - the output is
    byte-identical to P1's, because an already-deployed client reads this dict
    and an unexpected key is a wire change wearing an addition's clothes.
    """
    by_field = {e.field: e.message for e in errors}
    spec = {
        "fields": [
            {
                "id": f.id,
                "label": f.label,
                "required": f.required,
                "units": [{"id": u.id, "label": u.label} for u in f.units],
                "value": "",
                "source": "empty",
                "error": by_field.get(f.id),
            }
            for f in FIELDS
        ]
    }
    if table:
        spec["crops"] = _crop_rows(table)
    return spec
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest -q
git add src/budget.py tests/test_budget.py
git commit -m "Ship a province's norms alongside the form"
```

Expected: 636 passed.

---

### Task 5: A rejected form comes back with what was typed

**Files:**
- Modify: `src/budget.py` (`form_spec`)
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `form_spec(errors, table)` from Task 4
- Produces: `form_spec(errors, table=None, submitted=None) -> dict`; when `submitted` is a payload dict, each field carries the raw `value` and the selected `unit` back, and the dict carries `"crop"`

**Background.** The card seeds its state from the server's `value`, so a form re-served after a validation error currently arrives empty and the user re-types everything. Four fields made that survivable in P1. This plan makes it worse twice over: Task 3 adds a brand-new error (`kg/dekar` with no area), and a wipe now also discards the crop selection and its prefill. Ten lines remove a defect this work would otherwise introduce.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`:

```python
def test_a_rejected_form_carries_back_what_was_typed():
    """Without this, the error Task 3 introduces - a per-dekar yield with no
    area - throws away the crop and every other field the user filled."""
    submitted = {
        "crop": "findik",
        "area": {"value": "", "unit": "donum"},
        "yield_total": {"value": "100", "unit": "kg_da"},
        "price": {"value": "202,26", "unit": "tl_kg"},
    }
    _, errors = budget.validate(submitted)
    spec = budget.form_spec(errors, _table(), submitted)
    fields = {f["id"]: f for f in spec["fields"]}
    assert fields["yield_total"]["value"] == "100"
    assert fields["yield_total"]["unit"] == "kg_da"
    assert fields["price"]["value"] == "202,26"
    assert spec["crop"] == "findik"
    assert fields["area"]["error"]


def test_an_unsubmitted_form_carries_no_values_and_no_unit_key():
    """Nothing was submitted, so there is nothing to echo and P1's shape holds."""
    spec = budget.form_spec([], _table())
    for field in spec["fields"]:
        assert field["value"] == ""
        assert "unit" not in field
    assert "crop" not in spec


def test_an_unknown_unit_is_not_echoed_back():
    """A unit the field does not offer would render as no chip selected at all."""
    submitted = {"yield_total": {"value": "100", "unit": "furlong"}}
    spec = budget.form_spec([], _table(), submitted)
    fields = {f["id"]: f for f in spec["fields"]}
    assert fields["yield_total"]["unit"] == "kg"


def test_a_non_string_submitted_value_is_echoed_as_text():
    """A JSON number is a legal submission; echoing it as a float would put a
    dot decimal into a field parse_tr_number refuses."""
    spec = budget.form_spec([], None, {"area": {"value": 5, "unit": "donum"}})
    fields = {f["id"]: f for f in spec["fields"]}
    assert fields["area"]["value"] == "5"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -k "rejected or unsubmitted or unknown_unit or non_string" -q
```

Expected: FAIL with `TypeError: form_spec() takes 2 positional arguments but 3 were given`.

- [ ] **Step 3: Implement it**

Add above `form_spec`:

```python
def _echo(spec: FieldSpec, submitted: dict | None) -> dict:
    """What the user typed, given back verbatim.

    Verbatim matters: this is the value the error message is ABOUT, so
    reformatting it would show the user something other than what was rejected.
    A number that arrived as JSON becomes text, because that is what a text
    input holds and what parse_tr_number reads.
    """
    entry = (submitted or {}).get(spec.id)
    if not isinstance(entry, dict):
        return {"value": "", "unit": spec.units[0].id}
    value = entry.get("value")
    unit = entry.get("unit")
    return {
        "value": "" if value is None else str(value),
        # An unrecognised unit falls back to the first, or the card would render
        # with no chip selected and no way to tell why.
        "unit": unit if any(u.id == unit for u in spec.units) else spec.units[0].id,
    }
```

Extend `form_spec`:

```python
def form_spec(errors: list[FieldError], table=None, submitted=None) -> dict:
```

and inside, after building `spec["fields"]`:

```python
    if submitted:
        for field in spec["fields"]:
            field.update(_echo(_FIELDS_BY_ID[field["id"]], submitted))
        crop = submitted.get("crop")
        if isinstance(crop, str) and crop.strip():
            spec["crop"] = crop
    if table:
        spec["crops"] = _crop_rows(table)
    return spec
```

Update the docstring to name the third argument:

```python
    `submitted` is the payload that failed validation. Echoing it back is not a
    nicety: the card seeds its state from `value`, so without it a single bad
    field wipes the whole form, the crop selection and its prefill included.
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -q
```

Expected: PASS, including `test_a_form_with_no_table_is_byte_identical_to_p1` from Task 4 — no `submitted`, no new keys.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest -q
git add src/budget.py tests/test_budget.py
git commit -m "Give a rejected form back with its values, not empty"
```

Expected: 640 passed.

---

### Task 6: Provenance on submit, and the server's check of it

**Files:**
- Modify: `src/main.py` (`BudgetField`)
- Modify: `src/budget.py` (`Value`, `_read`, `validate`)
- Test: `tests/test_budget.py`, `tests/test_api_budget.py`

**Interfaces:**
- Consumes: `_norm_cell` and `_crop_rows` from Task 4; `norms.province_table` output as `table`
- Produces: `budget.validate(raw, table=None)`; `Value.source` is `"norm"` only for a claim the server confirmed, and `Value.note` carries that norm's provenance text for Task 7's framing

**Background.** The spec this amends contains a contradiction: P2 §7 says every submitted value is `"user"`, P2 §8 says the framing branches on whether a norm was used. Both cannot hold, or the norm sentence never renders and P1's now-false sentence is never replaced. The resolution separates **precedence** (the arithmetic always uses the submitted value — unchanged) from **provenance** (the client declares it, the server verifies it).

The verification compares the submitted **text and unit** to the cell the server would have served — not the parsed floats. Exact string comparison answers the real question, "is this the figure we sent?", with no floating-point tolerance to argue about.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`:

```python
def _submitted(value="28,4", unit="kg_da", source="norm"):
    return {
        "crop": "findik",
        "area": {"value": "5", "unit": "donum"},
        "yield_total": {"value": value, "unit": unit, "source": source},
        "price": {"value": "202,26", "unit": "tl_kg", "source": "norm"},
    }


def test_a_confirmed_claim_is_marked_as_a_norm():
    inputs, errors = budget.validate(_submitted(), _table())
    assert errors == []
    assert inputs.yield_kg.source == "norm"
    assert inputs.yield_kg.note == "TÜİK 2025, Ordu"


def test_an_edited_value_claiming_to_be_a_norm_is_downgraded():
    """The farmer's own figure must never be attributed to TUIK."""
    inputs, _ = budget.validate(_submitted(value="90"), _table())
    assert inputs.yield_kg.source == "user"
    assert inputs.yield_kg.note is None


def test_a_claim_under_a_different_unit_is_downgraded():
    """28,4 kg is not 28,4 kg/dekar, and only one of them is what we served."""
    inputs, _ = budget.validate(_submitted(unit="kg"), _table())
    assert inputs.yield_kg.source == "user"


def test_a_claim_with_no_table_is_downgraded():
    """Nothing to check it against is not the same as checking and agreeing."""
    inputs, _ = budget.validate(_submitted())
    assert inputs.yield_kg.source == "user"


def test_a_claim_for_a_crop_the_table_does_not_carry_is_downgraded():
    raw = _submitted()
    raw["crop"] = "yokolan"
    inputs, _ = budget.validate(raw, _table())
    assert inputs.yield_kg.source == "user"


def test_an_old_client_sending_no_source_gets_user():
    """Defaulting to 'user' keeps a deployed build on P1's exact framing rather
    than claiming a provenance it never asserted."""
    raw = _submitted()
    del raw["yield_total"]["source"]
    inputs, _ = budget.validate(raw, _table())
    assert inputs.yield_kg.source == "user"


def test_a_user_claim_is_never_upgraded():
    """Even when the number happens to equal the norm: the user typed it."""
    inputs, _ = budget.validate(_submitted(source="user"), _table())
    assert inputs.yield_kg.source == "user"


def test_the_arithmetic_always_uses_the_submitted_value():
    """Precedence is unchanged by any of this. A prefill is a default, never a
    lock, and a downgrade changes only the label."""
    inputs, _ = budget.validate(_submitted(value="90", unit="kg_da"), _table())
    assert inputs.yield_kg.amount == 450.0    # 90 kg/da over 5 donum
```

Add to `tests/test_api_budget.py`:

```python
def test_a_payload_carrying_a_source_is_accepted(client):
    payload = dict(PAYLOAD)
    payload["yield_total"] = {"value": "2", "unit": "ton", "source": "norm"}
    response = client.post("/api/chat",
                           json={"message": BUDGET_Q, "budget": payload})
    assert response.status_code == 200


def test_a_payload_with_no_source_is_still_accepted(client):
    """An already-deployed build sends none. It must not 422 mid-conversation."""
    response = client.post("/api/chat",
                           json={"message": BUDGET_Q, "budget": PAYLOAD})
    assert response.status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -k "claim or norm or submitted_value or old_client" tests/test_api_budget.py -q
```

Expected: FAIL with `TypeError: validate() takes 1 positional argument but 2 were given`.

- [ ] **Step 3: Add the wire field**

In `src/main.py`, extend `BudgetField`:

```python
class BudgetField(BaseModel):
    value: str | int | float | bool = ""
    unit: str = ""
    # Which figures the client prefilled from the norm table and the user left
    # alone. The server does not take this on trust - see budget._verify - but
    # it cannot ask the client after the fact either. Defaulting to "user" keeps
    # an already-deployed build, which sends nothing here, on P1's framing.
    source: str = "user"
```

- [ ] **Step 4: Carry the claim and the note through `budget.py`**

Extend `Value`:

```python
@dataclass(frozen=True)
class Value:
    amount: float
    source: str            # "user" | "norm" | "empty"
    # Where the norm came from, for the framing sentence. Only ever set on a
    # value the server itself confirmed against its own lookup.
    note: str | None = None
```

In `_read`, carry the claim through unverified — verification needs the crop and the table, which `_read` has no business knowing:

```python
    claimed = "norm" if entry.get("source") == "norm" else "user"
    return Value(amount * unit.factor, claimed), None
```

Add the verifier above `validate`:

```python
# Which submitted field each norm measure prefills, and how that cell is built.
_VERIFIED = (("yield_total", "yield_kg_da", "yield", None),
             ("price", "price_tl_kg", "price", 2))


def _verify(values: dict, raw: dict, crop: str | None, table) -> dict:
    """Confirm or downgrade every "this came from a norm" claim.

    A field claiming a norm whose submitted text does not match what we served
    is the user's own figure wearing TUIK's name, and the framing would then
    attribute a farmer's number to a statistical agency. Comparison is on the
    served TEXT and unit rather than the parsed floats: it answers exactly the
    question being asked - is this the figure we sent? - and has no rounding
    tolerance to get wrong.

    "user" is never second-guessed in the other direction. A value the user
    typed is theirs even when it happens to equal the norm.
    """
    row = None
    if crop is not None:
        row = next((r for r in (table or ()) if r.crop == crop), None)

    for field_id, measure, unit_key, decimals in _VERIFIED:
        value = values.get(field_id)
        if value is None or value.source != "norm":
            continue
        cell = (None if row is None
                else _norm_cell(getattr(row, measure), *_NORM_UNITS[unit_key], decimals))
        entry = raw.get(field_id) or {}
        if (cell is not None
                and entry.get("value") == cell["value"]
                and entry.get("unit") == cell["unit"]):
            values[field_id] = Value(value.amount, "norm", cell["note"])
        else:
            values[field_id] = Value(value.amount, "user")
    return values
```

Change `validate`'s signature and call the verifier just before it builds `BudgetInputs`:

```python
def validate(raw: dict, table=None) -> tuple[BudgetInputs | None, list[FieldError]]:
```

```python
    crop = raw.get("crop")
    crop = crop if isinstance(crop, str) and crop.strip() else None
    values = _verify(values, raw, crop, table)

    return BudgetInputs(
        area_da=values["area"],
        ...
        crop=crop,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py tests/test_api_budget.py -q
```

Expected: PASS.

- [ ] **Step 6: Run the full suite and commit**

```bash
python -m pytest -q
git add src/budget.py src/main.py tests/test_budget.py tests/test_api_budget.py
git commit -m "Let the client say which figures it prefilled, and check it"
```

Expected: 650 passed.

---

### Task 7: The second framing sentence

**Files:**
- Modify: `src/budget.py` (`render`, one new function)
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: `Value.source` and `Value.note` from Task 6
- Produces: `budget.framing(inputs: BudgetInputs) -> str`; `render` appends it instead of the bare `FRAMING` constant

**Background.** P1 appends, by code: *"Bu hesap bir tahmindir ve **tamamen sizin girdiğiniz rakamlara dayanır**; fiyat veya verim öngörüsü değildir."* The moment a norm figure survives to submit, that sentence is false — and it is the kind of error that survives review because it still reads plausibly. `FRAMING` itself does not change: it stays the sentence for the case it was written for.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget.py`:

```python
def _all_typed():
    """Every figure the user's own. Note that overriding the YIELD alone is not
    enough - _submitted() claims the price is a norm too, and the price claim
    would still be confirmed."""
    raw = _submitted(value="90")
    raw["price"] = {"value": "15", "unit": "tl_kg", "source": "user"}
    return raw


def test_a_form_of_the_users_own_figures_keeps_p1s_sentence_exactly():
    inputs, _ = budget.validate(_all_typed(), _table())
    text = budget.render(inputs, budget.compute(inputs))
    assert text.rstrip().endswith(budget.FRAMING)


def test_a_norm_figure_replaces_that_sentence():
    """Leaving it would state that the calculation rests entirely on the user's
    own numbers while one of them came from TUIK."""
    inputs, _ = budget.validate(_submitted(), _table())
    text = budget.render(inputs, budget.compute(inputs))
    assert budget.FRAMING not in text
    assert "verim ve fiyat" in text
    assert "TÜİK 2025, Ordu" in text
    assert "öngörü değildir" in text


def test_the_framing_names_only_the_figures_that_are_not_the_users():
    """A sentence that says 'verim ve fiyat' while the farmer typed the price
    tells them their own number came from TUIK."""
    raw = _submitted()
    raw["price"] = {"value": "15", "unit": "tl_kg", "source": "user"}
    inputs, _ = budget.validate(raw, _table())
    text = budget.framing(inputs)
    assert text.startswith("Bu hesaptaki verim rakamı")
    assert "verim ve fiyat" not in text


def test_the_framing_is_always_the_last_line():
    """It is appended by code and never asked of a model; a figure after it
    would read as a correction to it."""
    inputs, _ = budget.validate(_submitted(), _table())
    lines = [l for l in budget.render(inputs, budget.compute(inputs)).split("\n") if l]
    assert lines[-1] == budget.framing(inputs)


def test_the_p1_constant_is_untouched():
    assert budget.FRAMING == (
        "Bu hesap bir tahmindir ve tamamen sizin girdiğiniz rakamlara dayanır; "
        "fiyat veya verim öngörüsü değildir."
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -k framing -q
```

Expected: FAIL with `AttributeError: module 'src.budget' has no attribute 'framing'`.

- [ ] **Step 3: Implement it**

Add below `FRAMING` in `src/budget.py`:

```python
# The second framing, for a calculation that used a published average. Both
# sentences are appended BY CODE and neither is ever asked of a model - the
# fertplan.FRAMING pattern. A provincial mean yield is a central tendency across
# every holding in the province; printed without this it invites being read as a
# forecast for one parcel.
def framing(inputs: BudgetInputs) -> str:
    """P1's sentence, or the one that names whose figures these are."""
    used = [(label, value)
            for label, value in (("verim", inputs.yield_kg),
                                 ("fiyat", inputs.price_tl_kg))
            if value.source == "norm"]
    if not used:
        return FRAMING

    which = " ve ".join(label for label, _ in used)
    notes: list[str] = []
    for _, value in used:
        # Both measures normally share one note; printing it twice would read
        # as two different sources.
        if value.note and value.note not in notes:
            notes.append(value.note)
    source = " · ".join(notes)
    return (
        f"Bu hesaptaki {which} rakamı sizin değil, TÜİK'in yayımladığı bölge "
        f"ortalamasıdır ({source}). Bölge ortalaması tek bir tarlanın verimi "
        f"veya sizin alacağınız fiyat için bir öngörü değildir; kendi "
        f"rakamınızı girerseniz hesap ona göre yapılır."
    )
```

In `render`, replace the final line:

```python
    lines.extend(["", framing(inputs)])
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget.py -q
```

Expected: PASS, including every P1 render test — with no norm figures, `framing` returns `FRAMING` unchanged.

- [ ] **Step 5: Read one rendered answer of each kind**

```bash
PYTHONIOENCODING=utf-8 python -c "
import sys; sys.path.insert(0, '.')
from src import budget, norms
table = norms.province_table('Ordu')
raw = {'crop': 'findik',
       'area': {'value': '5', 'unit': 'donum'},
       'yield_total': {'value': '28,4', 'unit': 'kg_da', 'source': 'norm'},
       'price': {'value': '202,26', 'unit': 'tl_kg', 'source': 'norm'},
       'cost': {'value': '5000', 'unit': 'tl'}}
inputs, errors = budget.validate(raw, table)
print(errors)
print(budget.render(inputs, budget.compute(inputs)))
"
```

Expected: no errors, and an answer whose last line is the norm framing naming `TÜİK 2025, Ordu`. **Read it as a sentence** — this is the only step in the plan where a human judges the Turkish rather than an assertion.

- [ ] **Step 6: Run the full suite and commit**

```bash
python -m pytest -q
git add src/budget.py tests/test_budget.py
git commit -m "Say plainly when a figure is TUIK's average and not the user's"
```

Expected: 655 passed.

---

### Task 8: Wire the province and the table into the route

**Files:**
- Modify: `src/engine.py` (`_budget_result` and its two call sites, around lines 848–879, 904, 962)
- Test: `tests/test_budget_route.py`, `tests/test_api_budget.py`

**Interfaces:**
- Consumes: `norms.province_table` (Task 2), `budget.form_spec(errors, table, submitted)` (Tasks 4–5), `budget.validate(raw, table)` (Task 6)
- Produces: `_budget_result(payload, message="", history=None) -> ChatResult` — the last server-side piece; nothing later depends on its signature

**Background.** `stream_answer()` and `answer()` must stay mirror images. **Both clients stream**, so a table wired only into `answer()` would reach no user at all — and the route tests would still pass. This project has shipped exactly that mistake before.

`src/context/location.py` imports `engine._normalize_tr` at module load, so the import stays deferred inside the function, the way `_context_block` already does it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_budget_route.py`:

```python
ORDU_HISTORY = [{"role": "user", "content": "Adım Ayşe. Ordu'dayım. Fındık yetiştiriyorum."}]


def test_the_form_carries_the_provinces_norms(no_llm):
    result = engine.answer(BUDGET_Q, ORDU_HISTORY)
    crops = {c["id"]: c for c in result.form["crops"]}
    assert "findik" in crops
    assert crops["findik"]["yield"]["note"].endswith("Ordu")


def test_a_conversation_with_no_province_prefills_nothing(no_llm):
    """The province is never guessed: no province means no provincial norm, not
    a default one and not a neighbouring one.

    Asserted by CONTRAST rather than by looping over cells that are all None
    today - a loop like that passes whatever the data does, which is the vacuity
    class. Measured 2026-08-22: with no province, 0 of 246 crops resolve either
    measure, because P2a's exports were IBBS3-only and every TR row is null. If
    the national rows are ever populated this test fails loudly and is the right
    place to decide what a national prefill should say."""
    with_province = engine.answer(BUDGET_Q, ORDU_HISTORY)
    without = engine.answer(BUDGET_Q)
    assert without.form is not None

    def cell(result, crop_id, key):
        crops = {c["id"]: c for c in result.form.get("crops", [])}
        return crops[crop_id][key]

    assert cell(with_province, "findik", "yield")["note"] == "TÜİK 2025, Ordu"
    assert cell(without, "findik", "yield") is None
    assert cell(without, "findik", "price") is None


def test_a_broken_norm_layer_does_not_break_the_route(no_llm, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("norms exploded")

    monkeypatch.setattr("src.norms.province_table", boom)
    result = engine.answer(BUDGET_Q, ORDU_HISTORY)
    assert result.answer == budget.ASK_FOR_NUMBERS
    assert "crops" not in result.form


def test_a_rejected_submission_comes_back_with_its_values(no_llm):
    raw = {"crop": "findik",
           "yield_total": {"value": "100", "unit": "kg_da"},
           "price": {"value": "10", "unit": "tl_kg"}}
    result = engine.answer(BUDGET_Q, ORDU_HISTORY, raw)
    fields = {f["id"]: f for f in result.form["fields"]}
    assert fields["yield_total"]["value"] == "100"
    assert result.form["crop"] == "findik"
```

Add to `tests/test_api_budget.py`:

```python
def test_the_streamed_form_event_carries_the_crops(client):
    """Both clients stream. A table wired only into answer() reaches no user."""
    response = client.post("/api/chat", json={
        "message": BUDGET_Q, "stream": True,
        "history": [{"role": "user", "content": "Ordu'dayım."}],
    })
    events = [json.loads(line[len("data: "):])
              for line in response.text.splitlines()
              if line.startswith("data: ")]
    form = next(e["form"] for e in events if e["type"] == "form")
    assert any(c["id"] == "findik" for c in form["crops"])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget_route.py tests/test_api_budget.py -q
```

Expected: FAIL with `KeyError: 'crops'` — the form is served without a table.

- [ ] **Step 3: Implement it**

Replace `_budget_result` in `src/engine.py`:

```python
def _budget_result(payload: dict | None, message: str = "",
                   history: list[dict] | None = None) -> ChatResult:
    """The budget route: no retrieval, no product match, no model call.

    Every figure is computed in src/budget.py from values the user typed into
    labelled fields, or from a norm they accepted. When the payload is absent or
    incomplete we return the form instead of an answer; a payload that was never
    submitted gets a clean form rather than a list of "required" errors.

    The province is resolved from the conversation the same way weather and
    fert_plan resolve it, and the whole province's norm table travels with the
    form because the crop is selected on the client. A failure anywhere in that
    lookup costs the prefill and nothing else: the form still serves, exactly as
    it did in P1.

    validate() and compute() share one guard: either raising returns
    COMPUTE_FAILED with no form and no figures. validate() is documented never
    to raise, but on the streaming path the 200 and headers are already sent by
    the time this runs, so a raise here would break the connection mid-stream.
    """
    # Deferred like the router import below: src/context/location.py imports
    # _normalize_tr from THIS module at load time, so hoisting it makes the
    # cycle real. Same reason _context_block imports it locally.
    from src import budget

    table = ()
    try:
        from src import norms
        from src.context import location
        table = norms.province_table(location.extract_province(message, history))
    except Exception:  # noqa: BLE001 - a prefill is a convenience, not the route
        table = ()

    submitted = bool(payload)
    try:
        inputs, errors = budget.validate(payload or {}, table)
        if inputs is not None:
            result = budget.compute(inputs)
            return ChatResult(answer=budget.render(inputs, result),
                              recommended_products=[], route="budget")
    except Exception:  # noqa: BLE001 - a broken validation or sum must not become a guess
        return ChatResult(answer=budget.COMPUTE_FAILED,
                          recommended_products=[], route="budget")

    return ChatResult(answer=budget.ASK_FOR_NUMBERS, recommended_products=[],
                      route="budget",
                      form=budget.form_spec(errors if submitted else [],
                                            table,
                                            payload if submitted else None))
```

Update **both** call sites. In `answer()` (around line 904):

```python
    if route == "budget" or budget_payload:
        result = _budget_result(budget_payload, message, history)
        result.route_how = route_how
        return result
```

In `stream_answer()` (around line 962):

```python
    if route == "budget" or budget_payload:
        result = _budget_result(budget_payload, message, history)
        yield _sse({"type": "token", "content": result.answer})
```

- [ ] **Step 4: Verify both transports really differ from each other in no way**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/test_budget_route.py tests/test_api_budget.py -q
```

Expected: PASS, including the streaming test. If the streaming one fails while the others pass, the call site at line 962 was missed.

- [ ] **Step 5: Confirm the route still avoids the model and the store**

```bash
python -m pytest tests/test_budget_route.py -q
```

Expected: PASS. The `no_llm` fixture makes `retrieve_context`, `match_products` and `_complete_text` raise, so these tests pass only if the route genuinely reached none of them.

- [ ] **Step 6: Run the full suite and commit**

```bash
python -m pytest -q
git add src/engine.py tests/test_budget_route.py tests/test_api_budget.py
git commit -m "Resolve the province and send its norms with the form"
```

Expected: 660 passed.

---

### Task 9: The card

**Files:**
- Modify: `mobile-app/src/api.ts` (`FormSpec`, `BudgetFieldValue`)
- Modify: `mobile-app/src/BudgetCard.tsx`

**Interfaces:**
- Consumes: the wire from Tasks 4–6 — `form.crops[]`, `form.crop`, each field's `value`/`unit`, and `source` on submit
- Produces: nothing any later task depends on

**Background.** The card already seeds its state from the server's `value`, which P1 wrote for exactly this. What it does not have is a crop, a provenance line, or the two rules that keep a prefill honest.

**Three traps, all met before on this screen:**
1. `computer` clicks time out on this page. Drive it by dispatching `pointerdown`/`mousedown`/`pointerup`/`mouseup`/`click` on the element with `tabindex="0"` — that is React-Native-Web's pressable.
2. Setting an input's `.value` directly does not reach React state. Use the native value setter plus an `input` event, or the form submits empty.
3. A full page reload **signs you out** by design. Move between tabs by clicking `a[href="/chat"]`, never by navigating the URL.

- [ ] **Step 1: Extend the wire types**

In `mobile-app/src/api.ts`:

```ts
export interface BudgetFieldValue {
  value: string;
  unit: string;
  // Which figures came from the norm table and were left alone. The server
  // verifies this against its own lookup before believing it.
  source?: "norm" | "user";
}

export interface NormCell {
  value: string;
  unit: string;
  note: string;
  recent: string | null;
}

export interface CropOption {
  id: string;
  label: string;
  yield: NormCell | null;
  price: NormCell | null;
}
```

and add to `FormSpec`:

```ts
  crops?: CropOption[];
  crop?: string;
```

with `unit?: string` on the field type, for the echo of a rejected form.

- [ ] **Step 2: Fold the crop search into the card**

In `BudgetCard.tsx`, add state and the Turkish fold:

```tsx
// Turkish lowercasing, so typing "findik" finds "Fındık". toLowerCase() alone
// maps I to i but leaves I undotted, and the crops the user searches for most
// are the ones with dotted capitals.
function fold(text: string): string {
  return text
    .replace(/I/g, "ı")
    .replace(/İ/g, "i")
    .toLowerCase()
    .replace(/[ışğüöç]/g, (c) => ({ ı: "i", ş: "s", ğ: "g", ü: "u", ö: "o", ç: "c" }[c] ?? c));
}
```

Add the state:

```tsx
const [query, setQuery] = useState("");
const [crop, setCrop] = useState<string | undefined>(form.crop);
const [sources, setSources] = useState<Record<string, "norm" | "user">>({});
```

Compute the matches. Cap them at 8: 246 rows inside a chat bubble is a scroll trap, and a farmer who types three letters is not browsing.

```tsx
const selected = (form.crops ?? []).find((c) => c.id === crop);
// The list closes when the box already reads as the chosen crop, and reopens
// the moment the text differs. Clearing `crop` on every keystroke instead would
// blank the provenance lines under fields that are still showing its figures.
const matches =
  query.trim() && query !== selected?.label
    ? (form.crops ?? []).filter((c) => fold(c.label).includes(fold(query))).slice(0, 8)
    : [];
```

Render the search above the fields, only when the server actually sent a table — an old server, or one that resolved no province, sends none and the card must look exactly like P1's:

```tsx
{form.crops && form.crops.length > 0 && (
  <View style={styles.row}>
    <Text style={styles.label}>Ürün</Text>
    <TextInput
      style={styles.input}
      value={query}
      onChangeText={setQuery}
      placeholder="Ürün arayın (örn. fındık)"
      placeholderTextColor="#9aa"
    />
    {matches.map((option) => (
      <Pressable
        key={option.id}
        style={styles.match}
        onPress={() => selectCrop(option)}
      >
        <Text style={styles.matchText}>{option.label}</Text>
      </Pressable>
    ))}
    {matches.length > 0 && (
      // The explicit way out: a crop we do not carry, or one the farmer would
      // rather fill in themselves. It selects nothing and prefills nothing.
      <Pressable style={styles.match} onPress={() => { setCrop(undefined); setQuery(""); }}>
        <Text style={styles.matchText}>Diğer (listede yok)</Text>
      </Pressable>
    )}
  </View>
)}
```

Add the two styles alongside the existing ones:

```tsx
  match: {
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e2e8e2",
  },
  matchText: { fontSize: 13, color: colors.dark },
```

- [ ] **Step 3: Fill the fields on selection, honouring both rules**

```tsx
function selectCrop(option: CropOption) {
  setCrop(option.id);
  setQuery(option.label);
  const cells: [string, NormCell | null][] = [
    ["yield_total", option.yield],
    ["price", option.price],
  ];
  for (const [id, cell] of cells) {
    if (!cell) continue;
    // Only fields still marked as a norm are replaced. A figure the farmer
    // typed is not thrown away because they browsed the crop list.
    if (sources[id] === "user") continue;
    setValues((p) => ({ ...p, [id]: cell.value }));
    // The unit travels with the value: 28,4 under a "kg" chip would claim a
    // whole orchard yielded 28 kilos.
    setUnits((p) => ({ ...p, [id]: cell.unit }));
    setSources((p) => ({ ...p, [id]: "norm" }));
  }
}
```

In the existing `onChangeText` for every field, mark it the user's:

```tsx
onChangeText={(t) => {
  setValues((p) => ({ ...p, [f.id]: t }));
  setSources((p) => ({ ...p, [f.id]: "user" }));
}}
```

Do the same in the unit `onPress`: choosing a different unit for a prefilled figure makes it the user's.

- [ ] **Step 4: Show the provenance, and send it**

Under each field, when `sources[f.id] === "norm"`, render the selected crop's `note` and `recent`. Both are finished Turkish from the server — render them, never compose or reformat them. Place them where the error line already goes, so a field never shows both at once:

```tsx
{sources[f.id] === "norm" && (() => {
  const cell = f.id === "yield_total" ? selected?.yield : selected?.price;
  if (!cell) return null;
  return (
    <View>
      <Text style={styles.note}>{cell.note}</Text>
      {cell.recent ? <Text style={styles.note}>{cell.recent}</Text> : null}
    </View>
  );
})()}
```

```tsx
  note: { fontSize: 11, color: "#6b7a6b" },
```

In `submit()`, add the crop and the per-field source:

```tsx
    payload[f.id] = { value: v, unit: units[f.id], source: sources[f.id] ?? "user" };
```

```tsx
  if (crop) (payload as Record<string, unknown>).crop = crop;
```

- [ ] **Step 5: Type-check**

```bash
npx tsc --noEmit -p mobile-app
```

Expected: no errors.

- [ ] **Step 6: Drive the real card in a browser**

```bash
npx expo start --web
```

`react-native-web` and `react-dom` are installed, so the app runs at `http://localhost:8081`. **The budget route needs no LM Studio** — it makes no model call. Sign in, open the chat, and ask `5 dönüm fındık ektim, ne kadar kâr ederim?`.

Confirm, in order:

1. The card renders with a crop search box and four fields.
2. Typing `findik` lists **Fındık**; selecting it fills the yield with `28,4` and moves the chip to **kg/dekar**, and fills the price with `202,26` under **TL/kg**.
3. Under the yield: `TÜİK 2025, Ordu` and `önceki 5 yıl: 73,7–105,6 kg/da`.
4. Typing over the yield clears its provenance lines. Then searching `mısır` and selecting it leaves that typed yield alone and still refills the price — the rule that a browse never eats a figure the farmer entered.
5. Selecting `Diğer (listede yok)` clears the crop and leaves every field exactly as it stands.
6. Entering an area of `5` and submitting gives an answer whose last line is the **norm framing**, naming TÜİK and Ordu — not P1's sentence.
7. Submitting with the yield in **kg/dekar** and the area left **empty** returns the form with a field error **and every other value still in place**, crop included.
8. After a reload the conversation restores with **no interactive form**.

- [ ] **Step 7: Capture the evidence and commit**

Take a screenshot of step 3 and one of step 6.

```bash
git add mobile-app/src/api.ts mobile-app/src/BudgetCard.tsx
git commit -m "Pick a crop in the card and prefill from its norms"
```

- [ ] **Step 8: Record the state**

Append to `.superpowers/sdd/progress.md`: the suite count, what was driven in the browser and what it showed, and the one fact Emirhan needs — **a new APK is required** for the card to draw the crop select. An older build keeps working: it ignores the extra wire fields, sends no `source`, and gets P1's behaviour and P1's framing.

```bash
git add .superpowers/sdd/progress.md
git commit -m "Record what P2b shipped and what still needs a build"
```

---

## Verification before calling this done

- [ ] `python -m pytest -q` — expected 660+, no failures, no skips that were not skipping before.
- [ ] `form_spec([])` with no table and no submitted payload is byte-identical to P1's dict (Task 4's test pins it; confirm it still passes at the end).
- [ ] The streamed `form` event carries `crops` (Task 8's test) — **both clients stream**, so this is the one that proves a user would see it.
- [ ] One rendered answer of each framing, read as Turkish by a person (Task 7, Step 5).
- [ ] The eight browser checks in Task 9, Step 6.
- [ ] No eval run was needed and none was added.
