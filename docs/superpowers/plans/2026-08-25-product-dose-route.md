# P3b — Product Dose Route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A farmer picks a product, their crop group and their area, and gets the manufacturer's own published per-dekar dose multiplied out for their field — as a range, with the application method named, and with the season total refused in writing.

**Architecture:** P3a already shipped the data (`data/product_doses.json`, 40 products / 103 slots) and its loader (`src/doses.py`). This plan adds (1) a reviewed scope for the two `hepsi` rows so an unqualified-looking figure can no longer answer a group its page never addressed, (2) a new route module `src/dose_answer.py` holding inputs, validation, arithmetic and Turkish text, (3) engine/router/API wiring on **both** transports, and (4) the mobile card. The route makes no model call and no retrieval, so it is verified entirely by `pytest`.

**Tech Stack:** Python 3.14 + FastAPI + pytest (server); Expo / React Native + TypeScript (client). No new dependencies.

Spec: `docs/superpowers/specs/2026-08-22-product-dose-design.md`
P3a findings: `docs/superpowers/2026-08-22-product-dose-findings.md`
Branch point: `origin/main` = `cafa526`, `pytest -q` = **752 passed**.

## Global Constraints

- **Every user-facing string is Turkish and is written by code.** No model call, no retrieval, no product matching on this route. A model never sees or authors a number here.
- **A missing dose is never 0, and never another group's figure.** Absence is stated, never filled in.
- **A range stays a range.** `2–2,5 litre/da` × 5 dönüm is `10–12,5 litre`, never `11,25`.
- **The unit is printed as published**, with one exception: a total of **1000 or more** of a sub-unit is promoted (`gr` → `kg`, `cc` → `litre`). No other conversion — a gram figure is never turned into a litre one.
- **Turkish numbers go through `src/budget.py`'s formatters only** (`format_tr`, `format_qty`, `parse_tr_number`, `coerce_number`). A second Turkish formatter is a second place for a decimal comma to go wrong.
- **The method is an attribute of the answer, not an input.** Every per-area figure that exists for the chosen product and group is printed, each labelled with its method.
- **Both transports or neither.** `engine.answer()` and `engine.stream_answer()` are mirror images; a route wired into one reaches no user while the tests stay green.
- **Wire changes are additive.** An already-deployed APK must keep working: new SSE event type, new response key, new request field. It shows the sentence and no card.
- **No eval case.** The route makes no model call, so an eval case there would read green while asserting nothing (the vacuity class).
- **Commits:** one per task, English, short and natural, **no `Co-Authored-By` trailer**.
- `pytest -q` must be green at the end of every task, starting from 752 passed.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `data/dose_group_scope.json` | **Create.** Hand-reviewed: which crop groups each unqualified (`hepsi`) row may answer, with the panel's own words as evidence. |
| `scripts/build_product_doses.py` | **Modify.** Read the scope, embed it in the output, and refuse to write an unreviewed `hepsi` row. |
| `src/doses.py` | **Modify.** `lookup` falls back to a `hepsi` row only for the groups the review allows. |
| `src/budget.py` | **Modify.** Two private helpers become public so the dose route can reuse them (`_coerce` → `coerce_number`, `_format_qty` → `format_qty`). |
| `src/dose_answer.py` | **Create.** The whole route: field specs, validation, arithmetic, unit promotion, Turkish render, refusals, framing. |
| `src/router.py` | **Modify.** New `product_dose` route and its rule. |
| `src/engine.py` | **Modify.** `_dose_result`, `ChatResult.dose_form`, the short-circuit in `answer()` and `stream_answer()`. |
| `src/main.py` | **Modify.** `DosePayload` request field, `dose_form` response key. |
| `evals/routing_set.py` | **Modify.** The new route and six pre-authored cases. |
| `mobile-app/src/api.ts` | **Modify.** Dose types, the `dose_form` SSE event, the `dose` request field. |
| `mobile-app/src/DoseCard.tsx` | **Create.** Product search + three group buttons + area with a unit selector. |
| `mobile-app/app/(tabs)/chat.tsx` | **Modify.** Render the card, consume it on submit, resend the question with the payload. |

---

## Task 1: The reviewed scope for unqualified rows

`FLY AZOT`'s figures sit under `hepsi`, and `doses.lookup` returns a `hepsi` row for **any** group asked — so today `lookup("FLY AZOT", "meyve")` hands a fruit grower a figure its page never wrote for fruit. `hepsi` is carrying two meanings, "the page named no crop" and "the page named crops we do not parse", and only the first justifies answering every group.

**The decision (user, 2026-08-25):** split those two meanings **in the data**. A reviewed file says which groups each `hepsi` row may answer; a row nobody reviewed answers nothing; the converter refuses to ship an unreviewed one. Same binding rule as `norms.py` and the `reviewed_by` gate on `data/fertplan_table.json`: absence, never a guess.

**Files:**
- Create: `data/dose_group_scope.json`
- Modify: `scripts/build_product_doses.py`, `src/doses.py`
- Regenerate: `data/product_doses.json`
- Test: `tests/test_doses.py`, `tests/test_build_product_doses.py`

**Interfaces:**
- Consumes: `src.dose_parse.ALL_GROUPS` (`"hepsi"`), `src.dose_parse.GROUP_KEYS` (`("sebze", "meyve", "tarla")`), `parse_panel`, `conflicting_slots`.
- Produces: `doses.lookup(product, group) -> tuple[Dose, ...]` (signature unchanged, behaviour narrowed); `doses.available_products() -> tuple[str, ...]`; `build(panels, scope) -> (table, unparsed, dropped, resolved_scope)`; `data/product_doses.json` gains a top-level `"all_groups_scope"` key.

- [ ] **Step 1: Read both panels before writing the review**

This step is the review. Do not skip it and do not take the values below on trust — the whole point of the file is that a person read the page.

Run:

```bash
PYTHONIOENCODING=utf-8 python -c "import json; raw=json.load(open('data/raw/product_panels.json',encoding='utf-8')); [print('=====',n,'\n',raw['panels'][n],'\n') for n in ('FLY AZOT','HIGRO 8 MN')]"
```

What the reading found on 2026-08-25, and what the scope file below records:

- **`HIGRO 8 MN`** names **no plant at all** (`"Mangan eksikliğinde bir dekara (1.000 m²) 2 – 2,5 litre"`). Genuinely unqualified → all three groups.
- **`FLY AZOT`** qualifies every figure by crop name: *Tahıllarda ve Hububatlarda*, *Mısır ve Ayçiçeği*, *Pancar, patates, soğan, havuç*, *Yeşil yapraklılar (marul, maydanoz, tere, roka)*. Those span field crops and vegetables; **no fruit species appears anywhere on the page.** So: `tarla` and `sebze`, not `meyve`. The two closing `NOT:` sentences do restate 200 cc / 250 cc without naming a crop, which is why this is a judgement call and not a parse — it is recorded as one, with the evidence beside it.

If your reading disagrees, change the file and say so in the commit message. Do not change it to make a test pass.

- [ ] **Step 2: Write the reviewed scope file**

Create `data/dose_group_scope.json`. Replace `reviewed_by` with the name of whoever actually did Step 1.

```json
{
 "meta": {
  "reviewed": "2026-08-25",
  "reviewed_by": "Tunahan Yıldız",
  "why": "A `hepsi` row means the parser found no group heading. That is two different facts: the page named no crop at all, or it named crops we do not map to groups. Only the first may answer every group, and no regex can tell them apart, so a person reads the panel and records the answer here."
 },
 "scope": {
  "FLY AZOT": {
   "groups": ["tarla", "sebze"],
   "evidence": "Panel her rakamı ürün adıyla niteliyor: 'Tahıllarda ve Hububatlarda kıraç üretimde dekara 200 cc yapraktan', 'Mısır ve Ayçiçeği', 'Pancar, patates, soğan, havuç gibi toprak altı yumrulu bitkilerde ... yapraktan 250 cc', 'Yeşil yapraklıların (marul, maydanoz, tere, roka, vb.)'. Sayfada tek bir meyve türü geçmiyor."
  },
  "HIGRO 8 MN": {
   "groups": ["sebze", "meyve", "tarla"],
   "evidence": "Panel hiçbir bitki adı vermiyor: 'DAMLAMA SULAMA: Mangan eksikliğinde bir dekara (1.000 m²) 2 – 2,5 litre dozunda'. Rakam bir gruba bağlı değil."
  }
 }
}
```

- [ ] **Step 3: Write the failing loader tests**

In `tests/test_doses.py`, add the scope key to the `GOOD` fixture and replace the old blanket-fallback test.

Change the `GOOD` constant to:

```python
GOOD = {
    "meta": {"generated": "2026-08-22"},
    "products": {
        "HİGRO FUBBY": {"sebze": {"damlama": {"low": 250.0, "high": 250.0, "unit": "gr"}},
                        "meyve": {"damlama": {"low": 250.0, "high": 250.0, "unit": "gr"}}},
        "HIGRO 8 MN": {"hepsi": {"damlama": {"low": 2.0, "high": 2.5, "unit": "litre"}}},
        "FLY AZOT": {"hepsi": {"yaprak": {"low": 200.0, "high": 250.0, "unit": "cc"}}},
    },
    "all_groups_scope": {"HIGRO 8 MN": ["sebze", "meyve", "tarla"],
                         "FLY AZOT": ["tarla", "sebze"]},
}
```

Delete `test_an_unqualified_dose_answers_every_group` and put these three in its place:

```python
def test_an_unqualified_dose_answers_every_group_it_was_reviewed_for(tmp_path, monkeypatch):
    """'hepsi' means the parser saw no group heading. When a reviewer confirmed
    the page names no crop either, the figure is the answer for any group."""
    _write(tmp_path, monkeypatch, GOOD)
    for group in ("sebze", "meyve", "tarla"):
        found = doses.lookup("HIGRO 8 MN", group)
        assert len(found) == 1 and found[0].high == 2.5


def test_a_reviewed_row_stays_out_of_the_groups_its_page_never_named(tmp_path, monkeypatch):
    """FLY AZOT's page qualifies every figure by crop and names no fruit. The
    fallback used to hand a fruit grower a cereal figure."""
    _write(tmp_path, monkeypatch, GOOD)
    assert doses.lookup("FLY AZOT", "meyve") == ()
    assert len(doses.lookup("FLY AZOT", "tarla")) == 1
    assert len(doses.lookup("FLY AZOT", "sebze")) == 1


def test_an_unreviewed_unqualified_row_answers_nothing(tmp_path, monkeypatch):
    """No review, no fallback. A row nobody read must not answer three groups
    on the strength of a missing heading."""
    payload = {"products": {"YENİ ÜRÜN": {"hepsi": {"damlama": {"low": 1.0, "high": 2.0, "unit": "litre"}}}},
               "all_groups_scope": {}}
    _write(tmp_path, monkeypatch, payload)
    for group in ("sebze", "meyve", "tarla"):
        assert doses.lookup("YENİ ÜRÜN", group) == ()
```

- [ ] **Step 4: Run them and watch them fail**

Run: `python -m pytest tests/test_doses.py -q`
Expected: FAIL — `test_a_reviewed_row_stays_out_of_the_groups_its_page_never_named` and `test_an_unreviewed_unqualified_row_answers_nothing` both fail, because today's `lookup` falls through to `hepsi` for every group.

- [ ] **Step 5: Narrow the fallback in `src/doses.py`**

Replace `_load`, `available_products` and `lookup` with:

```python
@lru_cache(maxsize=1)
def _load() -> tuple[dict, dict]:
    """(validated products, reviewed all-groups scope). Never raises.

    A product is dropped WHOLE when any of its groups is malformed rather than
    half-loaded: a product answering for one group and silently not for another
    is indistinguishable from one that simply has no figure there.

    The scope says which groups each `hepsi` row may answer. A scope entry
    naming a group nobody publishes is dropped rather than trusted, and a
    product with no entry gets no fallback at all - see lookup().
    """
    try:
        raw = json.loads(Path(_PATH).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}, {}
        products = raw.get("products")
        if not isinstance(products, dict):
            return {}, {}
        kept = {name: groups for name, groups in products.items()
                if isinstance(name, str) and _valid_product(groups)}
        scope_raw = raw.get("all_groups_scope")
        scope_raw = scope_raw if isinstance(scope_raw, dict) else {}
        scope = {name: frozenset(g for g in groups if g in GROUP_KEYS)
                 for name, groups in scope_raw.items()
                 if isinstance(name, str) and isinstance(groups, list)}
        return kept, scope
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}, {}


def available_products() -> tuple[str, ...]:
    """Every product carrying at least one per-area dose, sorted."""
    return tuple(sorted(_load()[0]))


def lookup(product: str, group: str) -> tuple[Dose, ...]:
    """Every per-area figure this product publishes for this crop group.

    Usually one - 37 of the 42 products with a per-area dose publish it for drip
    irrigation only. The caller prints each with its method rather than choosing
    between them, because the source decides the method, not the farmer.

    THE `hepsi` FALLBACK IS REVIEWED, NOT AUTOMATIC. `hepsi` only says the
    parser found no group heading, which happens both when the page names no
    crop AND when it names crops we do not map to groups. FLY AZOT is the
    second kind: every figure on its page is qualified by crop name, and none
    of those crops is a fruit. So the fallback fires only for the groups a
    person confirmed - and for a product nobody reviewed, not at all.
    """
    products, scope = _load()
    groups = products.get(product)
    if not groups:
        return ()
    if group not in KNOWN_GROUPS:
        # A group we do not publish is not a question we can answer. Without
        # this a typo falls straight through to the unqualified `hepsi` row for
        # any product that has one, and the caller gets a real figure back for
        # a group it never asked about.
        return ()
    methods = groups.get(group)
    if methods is None and group in scope.get(product, frozenset()):
        methods = groups.get(ALL_GROUPS)
    methods = methods or {}
    return tuple(
        Dose(low=float(d["low"]), high=float(d["high"]), unit=d["unit"], method=method)
        for method in _METHODS
        if (d := methods.get(method)) is not None
    )
```

- [ ] **Step 6: Run the loader tests**

Run: `python -m pytest tests/test_doses.py -q`
Expected: PASS, all of them.

- [ ] **Step 7: Write the failing converter tests**

In `tests/test_build_product_doses.py`, add:

```python
def test_an_unreviewed_hepsi_row_stops_the_converter():
    """A `hepsi` row nobody read must not ship. Answering three groups off a
    missing heading is exactly the guess this file refuses to make."""
    panels = {"YENİ ÜRÜN": "Bir dekara (1.000 m²) 2 – 2,5 litre uygulanır."}
    with pytest.raises(ValueError, match="YENİ ÜRÜN"):
        build(panels, {})


def test_a_stale_scope_entry_stops_the_converter():
    """A review of a row that no longer exists is a review of nothing, and it
    would sit in the file looking like coverage."""
    panels = {"YENİ ÜRÜN": "Bir dekara (1.000 m²) 2 – 2,5 litre uygulanır."}
    scope = {"YENİ ÜRÜN": ["sebze", "meyve", "tarla"], "YOK ÜRÜN": ["sebze"]}
    with pytest.raises(ValueError, match="YOK ÜRÜN"):
        build(panels, scope)


def test_a_scope_naming_an_unknown_group_stops_the_converter():
    panels = {"YENİ ÜRÜN": "Bir dekara (1.000 m²) 2 – 2,5 litre uygulanır."}
    with pytest.raises(ValueError, match="hububat"):
        build(panels, {"YENİ ÜRÜN": ["hububat"]})


def test_a_reviewed_hepsi_row_ships_with_its_scope():
    panels = {"YENİ ÜRÜN": "Bir dekara (1.000 m²) 2 – 2,5 litre uygulanır."}
    table, unparsed, dropped, scope = build(panels, {"YENİ ÜRÜN": ["sebze", "tarla"]})
    assert "hepsi" in table["YENİ ÜRÜN"]
    assert scope == {"YENİ ÜRÜN": ["sebze", "tarla"]}


def test_the_shipped_scope_covers_every_shipped_hepsi_row():
    """The real data. If a parser change files a new product under `hepsi`,
    this fails until someone reads that product's panel."""
    from src.config import DATA_DIR
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    unqualified = {n for n, groups in shipped["products"].items() if "hepsi" in groups}
    assert unqualified == set(shipped["all_groups_scope"]), unqualified
    assert unqualified == {"FLY AZOT", "HIGRO 8 MN"}
```

Update every existing `build(...)` call in this file — **lines 22, 30, 36, 47, 65, 86 and 114** as the file stands at `cafa526`. Each gets a second argument (`{}` where its fixture panels carry a group heading, the right scope where they do not) and the six that unpack three values now unpack four. Check the fixtures first: run `python -c "from tests.test_build_product_doses import PANELS; from src.dose_parse import parse_panel; print({n: list(parse_panel(t)) for n, t in PANELS.items()})"` — any fixture that parses to `hepsi` needs a scope entry or the new gate will raise inside a test that is about something else. And update the reproducibility test to cover the new key:

```python
def test_the_shipped_file_is_what_the_converter_produces():
    """Re-run the committed converter over the committed raw panels and diff
    against the committed output. This is the check that proves the data file
    was generated, not hand-edited - the one P2a's final review ran by hand."""
    from src.config import DATA_DIR
    raw = json.loads((DATA_DIR / "raw" / "product_panels.json").read_text(encoding="utf-8"))
    review = json.loads((DATA_DIR / "dose_group_scope.json").read_text(encoding="utf-8"))
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    scope = {n: e["groups"] for n, e in review["scope"].items()}
    rebuilt, _, _, rebuilt_scope = build(raw["panels"], scope)
    assert rebuilt == shipped["products"]
    assert rebuilt_scope == shipped["all_groups_scope"]
```

- [ ] **Step 8: Run them and watch them fail**

Run: `python -m pytest tests/test_build_product_doses.py -q`
Expected: FAIL — `TypeError: build() takes 1 positional argument but 2 were given`.

- [ ] **Step 9: Teach the converter the review gate**

In `scripts/build_product_doses.py`, change the import line to:

```python
from src.dose_parse import ALL_GROUPS, GROUP_KEYS, conflicting_slots, parse_panel
```

Add next to `RAW`/`OUT`:

```python
REVIEW = DATA_DIR / "dose_group_scope.json"
```

Change `build`'s signature and add the gate just before `return`:

```python
def build(panels: dict[str, str], scope: dict[str, list[str]]
          ) -> tuple[dict, list[str], dict, dict]:
    """(table, unparsed names, dropped slots by product, resolved scope). Pure -
    no file access, so it is testable.

    The dropped slots come back from here rather than being re-derived by the
    caller: main() used to walk all 48 panels a second time to collect them,
    which meant the report and the table were built from two separate parses
    and could in principle disagree about the same panel.

    `scope` is the REVIEWED answer to a question no regex can settle: a `hepsi`
    row only tells us the parser saw no group heading, which is true both when
    the page names no crop and when it names crops we do not map to groups.
    An unreviewed `hepsi` row RAISES rather than shipping, because the shipped
    behaviour of an unscoped row would be "answers every group" - a guess, in
    the one place this project has decided never to guess.
    """
```

(keep the existing body up to the `table[name] = rows` loop, then:)

```python
    unreviewed = sorted(n for n, rows in table.items()
                        if ALL_GROUPS in rows and n not in scope)
    if unreviewed:
        raise ValueError(
            f"no reviewed group scope for {unreviewed} - their panels parsed to "
            f"an unqualified '{ALL_GROUPS}' row. Read each panel in "
            f"data/raw/product_panels.json and add an entry to "
            f"data/dose_group_scope.json saying which groups it may answer")
    stale = sorted(n for n in scope
                   if n not in table or ALL_GROUPS not in table[n])
    if stale:
        raise ValueError(
            f"data/dose_group_scope.json reviews {stale}, which ship no "
            f"'{ALL_GROUPS}' row - a review of nothing, sitting in the file "
            f"looking like coverage")
    for name, groups in scope.items():
        unknown = sorted(g for g in groups if g not in GROUP_KEYS)
        if unknown:
            raise ValueError(f"{name}: reviewed for {unknown}, which is not a "
                             f"group we publish (known: {list(GROUP_KEYS)})")
    return table, unparsed, dropped, {n: list(g) for n, g in scope.items()}
```

Change `main()` to read the review and write the key:

```python
def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    scope = {name: entry["groups"] for name, entry in review["scope"].items()}
    table, unparsed, conflicts, resolved = build(raw["panels"], scope)

    OUT.write_text(json.dumps(
        {"meta": {"generated": date.today().isoformat(),
                  "source": raw["meta"],
                  "reviewed_scope": review["meta"],
                  "products_with_a_dose": len(table),
                  "products_read": len(raw["panels"]),
                  "unparsed": unparsed,
                  "dropped_slots": conflicts},
         "products": table,
         "all_groups_scope": resolved},
        ensure_ascii=False, indent=1), encoding="utf-8")
```

(the print block below it is unchanged, plus one line after the `unparsed` block:)

```python
    if resolved:
        print(f"[doses] {len(resolved)} unqualified row(s) answer only their reviewed groups:")
        for name, groups in resolved.items():
            print(f"          {name}: {', '.join(groups)}")
```

- [ ] **Step 10: Regenerate the data file and check the diff**

Run:

```bash
python -m scripts.build_product_doses
```

Expected: `40 of 48 products carry a per-area dose`, and the new line naming `FLY AZOT: tarla, sebze` and `HIGRO 8 MN: sebze, meyve, tarla`.

Then confirm the only content change is the new key and the meta:

```bash
git diff --stat data/product_doses.json
```

Expected: `data/product_doses.json` changed. Verify with `git diff data/product_doses.json | head -40` that no `low`/`high`/`unit` value moved — only `meta` and the appended `all_groups_scope`.

- [ ] **Step 11: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS — 752 + the new tests, no failures.

- [ ] **Step 12: Commit**

```bash
git add data/dose_group_scope.json data/product_doses.json scripts/build_product_doses.py src/doses.py tests/test_doses.py tests/test_build_product_doses.py && git commit -m "Answer an unqualified dose only where a reviewer read the page"
```

---

## Task 2: The route module — inputs, validation, form

**Files:**
- Modify: `src/budget.py` (two renames)
- Create: `src/dose_answer.py`
- Test: `tests/test_dose_answer.py` (create), `tests/test_budget.py` (rename in three assertions)

**Interfaces:**
- Consumes: `doses.available_products()`, `doses.lookup`, `dose_parse.GROUP_KEYS`, `budget.UnitOption`, `budget.FieldError`.
- Produces: `dose_answer.GROUPS: tuple[tuple[str, str], ...]`, `dose_answer.AREA_UNITS: tuple[UnitOption, ...]`, `dose_answer.DoseInputs(product: str, group: str, area_da: float)`, `dose_answer.validate(raw: dict) -> tuple[DoseInputs | None, list[FieldError]]`, `dose_answer.form_spec(errors: list[FieldError], submitted: dict | None = None) -> dict`.

- [ ] **Step 1: Make the two budget helpers public**

`src/budget.py` already owns the reviewed Turkish number handling, including the `bool`-is-an-`int` trap that once turned a JSON `true` into 1 dekar. Reuse it; do not restate it.

Rename `_coerce` → `coerce_number` and `_format_qty` → `format_qty` in `src/budget.py`, updating every call site inside that file, and prepend one line to each docstring:

```python
def coerce_number(value: object) -> float | None:
    """Accept a JSON number as readily as the string a text input produces.

    Public because src/dose_answer.py reads the same kind of field from the
    same kind of client. A second copy of this is a second place for the bool
    guard below to be forgotten.

    bool is checked first because it is a subclass of int in Python: without
    the guard, True would silently become 1 dekar.
    """
```

```python
def format_qty(value: float) -> str:
    """Format a quantity for the restated line without rounding it away.

    Public for the same reason as coerce_number: the dose route prints the same
    kind of quantity and must not grow a second Turkish formatter.
    ...
    """
```

Run: `grep -rn "_format_qty\|_coerce" src/ tests/ evals/ --include=*.py`
Expected: no hits outside `src/budget.py`'s own definitions once the rename is done, except the three assertions in `tests/test_budget.py::test_format_qty_does_not_leave_a_half_formatted_decimal` — update those to `budget.format_qty`.

Run: `python -m pytest -q`
Expected: PASS, unchanged count.

- [ ] **Step 2: Write the failing validation tests**

Create `tests/test_dose_answer.py`:

```python
"""Unit tests for src/dose_answer.py (no network, no store, no model)."""

import json

import pytest

from src import dose_answer, doses


TABLE = {
    "meta": {"generated": "2026-08-25"},
    "products": {
        "HİGRO FUBBY": {"sebze": {"damlama": {"low": 250.0, "high": 250.0, "unit": "gr"}},
                        "meyve": {"damlama": {"low": 1.0, "high": 1.5, "unit": "litre"}}},
        "FLY AZOT": {"hepsi": {"yaprak": {"low": 200.0, "high": 250.0, "unit": "cc"}}},
    },
    "all_groups_scope": {"FLY AZOT": ["tarla", "sebze"]},
}


@pytest.fixture(autouse=True)
def table(tmp_path, monkeypatch):
    """Every test here runs against a fixture table, never the shipped file:
    a real product's figures changing must not turn these red."""
    path = tmp_path / "product_doses.json"
    path.write_text(json.dumps(TABLE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(doses, "_PATH", path)
    doses._load.cache_clear()
    yield
    doses._load.cache_clear()


def _raw(product="HİGRO FUBBY", group="sebze", value="5", unit="donum"):
    return {"product": product, "group": group,
            "area": {"value": value, "unit": unit}}


def test_a_complete_payload_validates():
    inputs, errors = dose_answer.validate(_raw())
    assert errors == []
    assert (inputs.product, inputs.group, inputs.area_da) == ("HİGRO FUBBY", "sebze", 5.0)


def test_hectares_become_dekars():
    inputs, _ = dose_answer.validate(_raw(value="2", unit="hektar"))
    assert inputs.area_da == 20.0


def test_every_error_is_reported_at_once():
    """A user fixing a form should not be walked through one round trip at a
    time - budget.validate's rule."""
    inputs, errors = dose_answer.validate({})
    assert inputs is None
    assert {e.field for e in errors} == {"product", "group", "area"}


def test_a_product_we_hold_no_dose_for_is_a_field_error():
    inputs, errors = dose_answer.validate(_raw(product="YOK BÖYLE BİR ÜRÜN"))
    assert inputs is None
    assert [e.field for e in errors] == ["product"]


def test_an_unknown_group_is_a_field_error():
    inputs, errors = dose_answer.validate(_raw(group="hububat"))
    assert inputs is None
    assert [e.field for e in errors] == ["group"]


def test_a_zero_area_is_refused():
    """Never multiplied out as 0 - that answers 'you need 0 litres' about a
    purchase."""
    inputs, errors = dose_answer.validate(_raw(value="0"))
    assert inputs is None and [e.field for e in errors] == ["area"]


def test_a_true_area_is_refused_not_read_as_one_donum():
    """bool is an int subclass in Python; the budget form paid for this once."""
    raw = _raw()
    raw["area"]["value"] = True
    inputs, errors = dose_answer.validate(raw)
    assert inputs is None and [e.field for e in errors] == ["area"]


def test_a_turkish_decimal_comma_is_read():
    inputs, _ = dose_answer.validate(_raw(value="2,5"))
    assert inputs.area_da == 2.5


def test_validate_never_raises_on_junk():
    for junk in (None, [], "5 dönüm", {"area": "5"}, {"product": 7, "group": None}):
        inputs, errors = dose_answer.validate(junk)
        assert inputs is None and errors


def test_a_fresh_form_lists_every_product_and_group():
    spec = dose_answer.form_spec([])
    assert spec["kind"] == "product_dose"
    assert spec["products"] == list(doses.available_products())
    assert [g["id"] for g in spec["groups"]] == ["sebze", "meyve", "tarla"]
    assert spec["area"]["value"] == ""
    assert all(v is None for v in spec["errors"].values())


def test_a_rejected_form_echoes_what_was_entered():
    """The card seeds its state from the spec, so without the echo one bad
    field wipes the product, the group and the area together."""
    raw = _raw(value="0")
    _, errors = dose_answer.validate(raw)
    spec = dose_answer.form_spec(errors, raw)
    assert spec["product"] == "HİGRO FUBBY"
    assert spec["group"] == "sebze"
    assert spec["area"]["value"] == "0"
    assert spec["errors"]["area"]


def test_an_unrecognised_unit_falls_back_to_the_first():
    """Otherwise the card renders with no chip selected and no way to tell why."""
    spec = dose_answer.form_spec([], _raw(unit="fersah"))
    assert spec["area"]["unit"] == "donum"
```

- [ ] **Step 3: Run them and watch them fail**

Run: `python -m pytest tests/test_dose_answer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.dose_answer'`.

- [ ] **Step 4: Write `src/dose_answer.py`**

```python
"""The product-dose route: the manufacturer's own per-dekar figure, times the
farmer's area, and nothing else.

THE MODEL PERFORMS NO ARITHMETIC AND MAKES NO APPEARANCE. Every number a user
sees from this route is computed here, in Python, from a figure the
manufacturer published and an area the user selected. The route does not call
the LLM at all.

NOTHING IS READ OUT OF THE QUESTION. "5 donumum var, ne kadar alirim?" has
exactly the shape P1 removed from the budget route - a number in a sentence
that must reach arithmetic - so it gets exactly the same treatment: labelled
fields, a unit that is a SELECTION, no inference.

THE METHOD IS AN ATTRIBUTE OF THE ANSWER, NOT AN INPUT. 37 of the 42 products
with a per-area dose publish it for drip irrigation only, so a method selector
would offer a choice in appearance only. Every figure that exists for the
product and group is printed, each labelled with the method the source
attached to it.

This module imports nothing from src/engine.py - the boundary src/norms.py,
src/budget.py and src/doses.py all keep.
"""
from __future__ import annotations

from dataclasses import dataclass

from src import doses
from src.budget import FieldError, UnitOption, coerce_number
from src.dose_parse import GROUP_KEYS

# The three groups the panels segment by, with the label the card prints. The
# ids come from the parser rather than being restated, so a group the data can
# carry and a button the farmer can press cannot drift apart.
_GROUP_LABELS = {"sebze": "Sebze", "meyve": "Meyve", "tarla": "Tarla bitkisi"}
GROUPS: tuple[tuple[str, str], ...] = tuple((key, _GROUP_LABELS[key])
                                            for key in GROUP_KEYS)
_GROUP_IDS = frozenset(GROUP_KEYS)

# P1's area control, unchanged, including the unit-as-selection rule.
AREA_UNITS: tuple[UnitOption, ...] = (UnitOption("donum", "dönüm", 1.0),
                                      UnitOption("hektar", "hektar", 10.0))

AREA_LABEL = "Alan"


@dataclass(frozen=True)
class DoseInputs:
    """Canonical throughout: dekar."""
    product: str
    group: str
    area_da: float


def _read_area(raw: dict) -> tuple[float | None, FieldError | None]:
    entry = raw.get("area")
    if not isinstance(entry, dict) or entry.get("value") in (None, ""):
        return None, FieldError("area", f"{AREA_LABEL} alanını doldurun.")
    amount = coerce_number(entry.get("value"))
    if amount is None:
        return None, FieldError(
            "area", f"{AREA_LABEL} bir sayı olmalı. Ondalık için virgül kullanın.")
    unit = next((u for u in AREA_UNITS if u.id == entry.get("unit")), None)
    if unit is None:
        return None, FieldError("area", f"{AREA_LABEL} için birimi seçin.")
    if amount <= 0:
        return None, FieldError("area", f"{AREA_LABEL} sıfırdan büyük olmalı.")
    return amount * unit.factor, None


def validate(raw: object) -> tuple[DoseInputs | None, list[FieldError]]:
    """Read every field, collect every error. Never raises.

    The product is checked against the table rather than believed, for the same
    reason budget._verify looks the crop up: it arrives from a client, and a
    name we hold no figure for must become a field error rather than an empty
    answer with no explanation.
    """
    raw = raw if isinstance(raw, dict) else {}
    errors: list[FieldError] = []

    product = raw.get("product")
    product = product.strip() if isinstance(product, str) else ""
    if not product:
        errors.append(FieldError("product", "Ürünü seçin."))
    elif product not in doses.available_products():
        errors.append(FieldError(
            "product",
            "Bu ürünün sayfasında dekara doz yayımlanmamış; elimde bir rakam yok."))

    group = raw.get("group")
    if not isinstance(group, str) or group not in _GROUP_IDS:
        errors.append(FieldError(
            "group", "Tarlanızın grubunu seçin: sebze, meyve veya tarla bitkisi."))

    area_da, area_error = _read_area(raw)
    if area_error is not None:
        errors.append(area_error)

    if errors:
        return None, errors
    return DoseInputs(product=product, group=group, area_da=area_da), []


def form_spec(errors: list[FieldError], submitted: object = None) -> dict:
    """Serialise the card for the client, attaching each error to its field.

    `submitted` is the payload that failed validation. Echoing it back is not a
    nicety: the card seeds its state from this dict, so without it a single bad
    field wipes the product and the group along with the area.

    `kind` is here so a client that grows a second card type can tell them
    apart. The dose form travels on its own SSE event and its own response key,
    so an already-deployed build never receives one at all - see src/engine.py.
    """
    submitted = submitted if isinstance(submitted, dict) else {}
    by_field = {e.field: e.message for e in errors}

    entry = submitted.get("area")
    entry = entry if isinstance(entry, dict) else {}
    value = entry.get("value")
    unit = entry.get("unit")

    product = submitted.get("product")
    group = submitted.get("group")
    return {
        "kind": "product_dose",
        "products": list(doses.available_products()),
        "groups": [{"id": key, "label": label} for key, label in GROUPS],
        "product": product if isinstance(product, str) else "",
        "group": group if isinstance(group, str) else "",
        "area": {
            "label": AREA_LABEL,
            # A number that arrived as JSON becomes text, because that is what
            # a text input holds and what the parser reads.
            "value": "" if value is None else str(value),
            # An unrecognised unit falls back to the first, or the card renders
            # with no chip selected and no way to tell why.
            "unit": unit if any(u.id == unit for u in AREA_UNITS) else AREA_UNITS[0].id,
            "units": [{"id": u.id, "label": u.label} for u in AREA_UNITS],
        },
        "errors": {"product": by_field.get("product"),
                   "group": by_field.get("group"),
                   "area": by_field.get("area")},
    }
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_dose_answer.py -q`
Expected: PASS.

- [ ] **Step 6: Pin the module boundary**

Add to `tests/test_dose_answer.py` (the same guard `tests/test_doses.py` runs on `src/doses.py`):

```python
def test_dose_answer_does_not_import_the_engine():
    """A file in, values out. The engine imports this module, not the reverse -
    and a cycle here raises ImportError on every startup."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("src/dose_answer.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("engine" in name for name in imported), imported
```

Run: `python -m pytest tests/test_dose_answer.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/budget.py src/dose_answer.py tests/test_dose_answer.py tests/test_budget.py && git commit -m "Read the dose card's three fields, and refuse what they garble"
```

---

## Task 3: The arithmetic, and the one unit promotion

**Files:**
- Modify: `src/dose_answer.py`
- Test: `tests/test_dose_answer.py`

**Interfaces:**
- Produces: `dose_answer.DoseTotal(method, dose_low, dose_high, dose_unit, total_low, total_high, total_unit)` and `dose_answer.compute(inputs: DoseInputs) -> tuple[DoseTotal, ...]`.

- [ ] **Step 1: Write the failing arithmetic tests**

Append to `tests/test_dose_answer.py`:

```python
def test_a_single_figure_times_an_area():
    inputs, _ = dose_answer.validate(_raw(group="meyve", value="5"))
    totals = dose_answer.compute(inputs)
    assert len(totals) == 1
    assert (totals[0].total_low, totals[0].total_high, totals[0].total_unit) == (
        5.0, 7.5, "litre")


def test_a_range_stays_a_range():
    """Never a midpoint: collapsing invents a precision the source does not
    have, and the single number reads more authoritative than the range."""
    inputs, _ = dose_answer.validate(_raw(product="FLY AZOT", group="tarla", value="2"))
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_high) == (400.0, 500.0)


def test_a_thousand_grams_is_promoted_to_kilos():
    """A farmer buying fertilizer thinks in kilos. This is a pure unit
    conversion and invents nothing."""
    inputs, _ = dose_answer.validate(_raw(value="5"))     # 250 gr/da x 5 da
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_unit) == (1.25, "kg")


def test_under_a_thousand_stays_in_the_published_unit():
    inputs, _ = dose_answer.validate(_raw(value="2"))     # 250 gr/da x 2 da
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_unit) == (500.0, "gr")


def test_a_range_is_promoted_as_one_unit():
    """Printing '1000 cc – 1,25 litre' would read as two different figures."""
    inputs, _ = dose_answer.validate(_raw(product="FLY AZOT", group="sebze", value="5"))
    totals = dose_answer.compute(inputs)
    assert (totals[0].total_low, totals[0].total_high, totals[0].total_unit) == (
        1.0, 1.25, "litre")


def test_the_published_dose_survives_the_promotion():
    """The answer quotes the maker's own per-dekar figure alongside the total,
    so it must stay in the unit the page used."""
    inputs, _ = dose_answer.validate(_raw(value="5"))
    totals = dose_answer.compute(inputs)
    assert (totals[0].dose_low, totals[0].dose_unit) == (250.0, "gr")


def test_a_group_the_product_does_not_publish_computes_nothing():
    """Never another group's figure, and never zero."""
    inputs, _ = dose_answer.validate(_raw(group="tarla"))
    assert dose_answer.compute(inputs) == ()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_dose_answer.py -q`
Expected: FAIL — `AttributeError: module 'src.dose_answer' has no attribute 'compute'`.

- [ ] **Step 3: Implement**

Append to `src/dose_answer.py`:

```python
@dataclass(frozen=True)
class DoseTotal:
    """One published figure and what it comes to over the farmer's area.

    The published figure travels alongside the total because the answer quotes
    it: "dekara 250 gr" is the manufacturer's sentence, "1,25 kg" is ours.
    """
    method: str
    dose_low: float
    dose_high: float
    dose_unit: str
    total_low: float
    total_high: float
    total_unit: str


# The only conversion this route performs, and it is a pure one: 1000 of a
# sub-unit is the unit above it, on any page, with no density involved. A gram
# figure is NEVER turned into a litre one - that needs a density the pages do
# not give.
_PROMOTE = {"gr": ("kg", 1000.0), "cc": ("litre", 1000.0)}


def _promote(low: float, high: float, unit: str) -> tuple[float, float, str]:
    """Promote BOTH ends or neither, decided by the larger one.

    Deciding per end would print "1000 cc - 1,25 litre" for a single range,
    which reads as two different figures rather than one span.
    """
    target = _PROMOTE.get(unit)
    if target is None:
        return low, high, unit
    name, factor = target
    if max(low, high) < factor:
        return low, high, unit
    return low / factor, high / factor, name


def compute(inputs: DoseInputs) -> tuple[DoseTotal, ...]:
    """All arithmetic for this route lives here: two multiplications per figure.

    Empty when the product publishes nothing for that group - which is an
    answer ("we hold no figure"), not a zero. A zero would flow into a purchase
    quantity and say "you need 0 litres".
    """
    out = []
    for dose in doses.lookup(inputs.product, inputs.group):
        low, high, unit = _promote(dose.low * inputs.area_da,
                                   dose.high * inputs.area_da, dose.unit)
        out.append(DoseTotal(method=dose.method,
                             dose_low=dose.low, dose_high=dose.high,
                             dose_unit=dose.unit,
                             total_low=low, total_high=high, total_unit=unit))
    return tuple(out)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_dose_answer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dose_answer.py tests/test_dose_answer.py && git commit -m "Multiply the published dose out, and keep the range a range"
```

---

## Task 4: The Turkish the route writes

**Files:**
- Modify: `src/dose_answer.py`
- Test: `tests/test_dose_answer.py`

**Interfaces:**
- Produces: `dose_answer.ASK_FOR_INPUTS`, `dose_answer.COMPUTE_FAILED`, `dose_answer.ATTRIBUTION`, `dose_answer.SEASON_REFUSAL`, `dose_answer.no_dose_for_group(inputs) -> str`, `dose_answer.render(inputs, totals) -> str`.

- [ ] **Step 1: Write the failing render tests**

Append to `tests/test_dose_answer.py`:

```python
def test_the_answer_restates_what_it_computed_from():
    inputs, _ = dose_answer.validate(_raw(group="meyve", value="5"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert "HİGRO FUBBY" in text
    assert "5 dönüm" in text
    assert "meyve" in text


def test_the_answer_names_the_method_the_figure_belongs_to():
    """The source decides the method, not the farmer - so the answer says which
    one it is showing."""
    inputs, _ = dose_answer.validate(_raw(group="meyve", value="5"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert "Damlamadan" in text


def test_the_answer_prints_the_published_dose_and_the_total():
    inputs, _ = dose_answer.validate(_raw(group="meyve", value="5"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert "1–1,5 litre" in text     # the maker's per-dekar figure
    assert "5–7,5 litre" in text     # over 5 donum


def test_a_single_figure_prints_one_number_not_a_range():
    inputs, _ = dose_answer.validate(_raw(value="2"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert "500 gr" in text
    assert "500–500" not in text


def test_every_answer_says_whose_figure_it_is():
    inputs, _ = dose_answer.validate(_raw(value="2"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert dose_answer.ATTRIBUTION in text


def test_every_answer_refuses_the_season_total_by_name():
    """A dose is per application, and only 8 of 48 panels state an interval or
    a count. Supplying one would mean authoring our own programme and
    presenting it as the manufacturer's."""
    inputs, _ = dose_answer.validate(_raw(value="2"))
    text = dose_answer.render(inputs, dose_answer.compute(inputs))
    assert dose_answer.SEASON_REFUSAL in text
    assert "sezon" in text.lower()


def test_a_missing_figure_is_named_not_guessed():
    inputs, _ = dose_answer.validate(_raw(group="tarla"))
    text = dose_answer.no_dose_for_group(inputs)
    assert "HİGRO FUBBY" in text
    assert "tarla bitki" in text
    assert "250" not in text and "1,5" not in text


def test_every_method_the_parser_can_emit_has_a_turkish_label():
    """A method with no label is a KeyError inside a rendered answer - and it
    reaches a user, not a test, because the shipped data has one of them once."""
    from src import dose_parse
    for method, _pattern in dose_parse._METHODS:
        assert method in dose_answer.METHOD_LABELS


def test_every_group_has_a_sentence_form():
    for key, _label in dose_answer.GROUPS:
        assert key in dose_answer.GROUP_IN_SENTENCE
```

- [ ] **Step 2: Run them and watch them fail**

Run: `python -m pytest tests/test_dose_answer.py -q`
Expected: FAIL — `AttributeError: module 'src.dose_answer' has no attribute 'render'`.

- [ ] **Step 3: Implement**

Add `format_qty` to the budget import line at the top of `src/dose_answer.py`:

```python
from src.budget import FieldError, UnitOption, coerce_number, format_qty
```

Append to `src/dose_answer.py`:

```python
# Written out rather than derived by .capitalize()/.lower() at runtime: Turkish
# casing has a dotted/dotless I trap, and these strings appear inside sentences
# where the right form is not the one a case function would produce.
METHOD_LABELS = {"damlama": "Damlamadan",
                 "yaprak": "Yapraktan",
                 "toprak": "Topraktan"}

GROUP_IN_SENTENCE = {"sebze": "sebzede",
                     "meyve": "meyvede",
                     "tarla": "tarla bitkisinde"}

# Appended BY CODE, never asked of the model - the fertplan.FRAMING pattern.
# This sentence is the line between quoting a maker's dose and authoring one.
ATTRIBUTION = (
    "Bu rakam ürünün kendi sayfasında üreticinin yayımladığı dozdur; bizim "
    "önerimiz değildir."
)

# The refusal is a feature, not a shortfall. Only 8 of 48 panels state an
# interval or a number of applications, so for the other 40 the season total is
# simply not in the source; supplying one would mean authoring a programme and
# presenting it as the manufacturer's. It is unconditional rather than triggered
# by the question, because deciding "did they ask for a season total?" would put
# a Turkish text matcher back on the path this route exists to keep clear of one.
SEASON_REFUSAL = (
    "Doz TEK bir uygulama içindir. Sayfa kaç uygulama yapılacağını yazmadığı "
    "için sezon boyunca gereken toplam miktarı hesaplayamıyorum; onu söylemek "
    "üreticinin yazmadığı bir programı ona mal etmek olurdu."
)

# Written to stand alone: a deployed client that cannot draw the card shows only
# this, so it names what it needs instead of pointing at a widget.
ASK_FOR_INPUTS = (
    "Hangi üründen ne kadar almanız gerektiğini hesaplayabilirim. Üç şeye "
    "ihtiyacım var: ürün, tarlanızın grubu (sebze, meyve veya tarla bitkisi) ve "
    "alanı. Bunları verirseniz üreticinin dekara yayımladığı dozu alanınızla "
    "çarpar, bir uygulamada gereken miktarı söylerim."
)

# The failure mode of this route is silence, never a guess: there is no fallback
# to the model path, because an invented purchase quantity is what it removes.
COMPUTE_FAILED = (
    "Hesaplamayı tamamlayamadım. Lütfen seçimlerinizi kontrol edip tekrar deneyin."
)


def _amount(low: float, high: float, unit: str) -> str:
    """A range as a range; a single figure as one number."""
    if low == high:
        return f"{format_qty(low)} {unit}"
    return f"{format_qty(low)}–{format_qty(high)} {unit}"


def no_dose_for_group(inputs: DoseInputs) -> str:
    """Said, not guessed - and it names both halves of the combination.

    Deliberately prints no figure at all: the temptation this message exists to
    refuse is showing the group next door's number "for reference".
    """
    return (
        f"**{inputs.product}** için {GROUP_IN_SENTENCE[inputs.group]} dekara bir "
        f"doz yayımlanmamış. Bu ürünün sayfasında bu gruba ait bir rakam yok, "
        f"başka bir grubun rakamını da buraya taşımıyorum.\n\n{ATTRIBUTION}"
    )


def render(inputs: DoseInputs, totals: tuple[DoseTotal, ...]) -> str:
    """Code-written Turkish. Restates its inputs before stating its result."""
    lines = [
        f"**{inputs.product}** · {GROUP_IN_SENTENCE[inputs.group]} · "
        f"**{format_qty(inputs.area_da)} dönüm**",
        "",
    ]
    for total in totals:
        dose = _amount(total.dose_low, total.dose_high, total.dose_unit)
        whole = _amount(total.total_low, total.total_high, total.total_unit)
        lines.append(
            f"{METHOD_LABELS[total.method]} dekara **{dose}**: "
            f"{format_qty(inputs.area_da)} dönüm için bir uygulamada "
            f"**{whole}**."
        )
    lines.extend(["", ATTRIBUTION, "", SEASON_REFUSAL])
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_dose_answer.py -q`
Expected: PASS.

- [ ] **Step 5: Read the rendered answer out loud**

Reading the rendered output found four defects no assertion caught on P2b. Do it here too.

Run:

```bash
PYTHONIOENCODING=utf-8 python -c "from src import dose_answer as d; i,_ = d.validate({'product':'HİGRO FUBBY','group':'meyve','area':{'value':'5','unit':'donum'}}); print(d.render(i, d.compute(i))); print('---'); i2,_ = d.validate({'product':'FLY AZOT','group':'sebze','area':{'value':'2,5','unit':'donum'}}); print(d.render(i2, d.compute(i2)))"
```

Check, by reading: the product name is the catalog's own; the group reads naturally inside the sentence; the dash between range ends is an en dash, not a hyphen-minus mixed with one; `2,5 dönüm` echoes as `2,5` and not `2` or `2,50`; no sentence claims we recommend anything; the season sentence does not contradict the line above it. Fix what reads wrong before moving on.

- [ ] **Step 6: Commit**

```bash
git add src/dose_answer.py tests/test_dose_answer.py && git commit -m "Say whose dose it is, and refuse the season total in writing"
```

---

## Task 5: Wiring — router, engine, API

**Files:**
- Modify: `src/router.py`, `evals/routing_set.py`, `src/engine.py`, `src/main.py`
- Test: `tests/test_router.py`, `tests/test_dose_route.py` (create), `tests/test_main.py`

**Interfaces:**
- Consumes: `dose_answer.validate/compute/render/form_spec/no_dose_for_group/ASK_FOR_INPUTS/COMPUTE_FAILED`, `doses.available_products()`.
- Produces: `engine.ChatResult.dose_form: dict | None`; `engine.answer(message, history=None, budget_payload=None, dose_payload=None)`; `engine.stream_answer(message, history=None, budget_payload=None, dose_payload=None)` emitting `{"type": "dose_form", "form": {...}}`; `/api/chat` accepting `dose` and returning `dose_form`.

- [ ] **Step 1: Author the routing cases BEFORE the rule**

The frozen set is pre-registered: a case written to fit an existing rule measures the rule, not the requirement. Write these first, run the gate, and only then write the rule.

In `evals/routing_set.py`, change `ROUTES` to:

```python
ROUTES = ("plant_info", "nutrition", "fert_plan", "budget", "crop_choice",
          "product_dose", "offscope")
```

and add this block after the `budget` block:

```python
    # --- product_dose: how much of a fertilizer for this field ---------------
    # Authored 2026-08-25, BEFORE src/router.py knew this route existed.
    {"query": "HİGRO BARF dekara ne kadar kullanmalıyım?", "route": "product_dose"},
    {"query": "5 dönümlük tarlama FLY AZOT'tan ne kadar lazım?", "route": "product_dose"},
    {"query": "HİGRO FUBBY'nin dekara dozu nedir?", "route": "product_dose"},
    {"query": "Gübreyi dekara kaç litre vermeliyim?", "route": "product_dose"},
    {"query": "Domates için gübreden dekara ne kadar atmalıyım?", "route": "product_dose"},
    {"query": "Bir dönüme kaç kilo gübre gider?", "route": "product_dose"},
```

- [ ] **Step 2: Write the failing router tests**

Append to `tests/test_router.py`:

```python
def test_a_named_product_with_a_how_much_question_is_a_dose_question():
    assert router.classify_by_rules("HİGRO BARF dekara ne kadar kullanmalıyım?") == "product_dose"


def test_a_dose_phrase_with_a_fertilizer_stem_is_a_dose_question():
    assert router.classify_by_rules("Gübreyi dekara kaç litre vermeliyim?") == "product_dose"


def test_money_still_wins_over_a_named_product():
    """'HİGRO BARF kaç para?' is a price question, not a dose question - budget
    is checked first and stays first."""
    assert router.classify_by_rules("HİGRO BARF kaç para tutar?") == "budget"


def test_a_timing_question_is_still_a_plan_not_a_dose():
    assert router.classify_by_rules("Domatese ne zaman gübre vermeliyim?") == "fert_plan"


def test_a_plain_nutrition_question_is_not_a_dose_question():
    assert router.classify_by_rules("Buğday tarlamda nasıl gübreleme yapmalıyım?") == "nutrition"
```

Run: `python -m pytest tests/test_router.py tests/test_routing_set.py -q`
Expected: FAIL — the new route has no rule, and `test_every_route_is_represented` now sees a route the router cannot produce.

- [ ] **Step 3: Write the rule**

In `src/router.py`, extend the `Route` literal:

```python
Route = Literal["plant_info", "nutrition", "fert_plan", "budget",
                "crop_choice", "product_dose", "offscope"]
```

Add above `classify_by_rules`:

```python
# "How much per dekar" phrasings. Deliberately narrow: every one of these names
# an AMOUNT PER AREA or asks for a dose outright, so none of them fires on a
# timing question ("ne zaman", "hangi ay") or on a price one - and budget is
# checked first anyway, which keeps "dekara maliyeti nedir" money.
_DOSE_PHRASES = ("dekara ne kadar", "dekara kac", "donume ne kadar",
                 "donume kac", "ne kadar atmali", "ne kadar atarim",
                 "kac litre", "kac kilo", "kac kg", "dozu nedir",
                 "dozu ne kadar", "dozu ne")


@lru_cache(maxsize=1)
def _product_pattern():
    """One regex over every product carrying a published dose, folded.

    Data-driven rather than a hand-kept list: a product that leaves the dose
    table stops triggering the route on the same day, and a new one starts.
    Both boundaries are anchored - 'FLY AZOT' must not fire on 'azotlu gubre'.
    """
    from src import doses
    names = [_normalize_tr(name) for name in doses.available_products()]
    if not names:
        return None
    names.sort(key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in names) + r")(?!\w)")


def _names_a_dose_product(folded: str) -> bool:
    try:
        pattern = _product_pattern()
    except Exception:  # noqa: BLE001 - routing must never break answering
        return False
    return bool(pattern and pattern.search(folded))
```

Add `from functools import lru_cache` to the imports at the top of the module.

Then, inside `classify_by_rules`, insert this block **after** the budget block and **before** the `crop_choice` block:

```python
    # A named product, or an explicit per-area amount question. Checked after
    # budget (a price question about a product is still money) and before
    # fert_plan/nutrition, which would otherwise swallow every "gubre" in it.
    if _names_a_dose_product(folded) or (
            _has_stem(folded, _DOSE_PHRASES)
            and _has_stem(folded, _PLANT_NUTRITION_STEMS)):
        return "product_dose"
```

- [ ] **Step 4: Run the router tests and the frozen gate**

Run: `python -m pytest tests/test_router.py tests/test_routing_set.py tests/test_run_routing.py -q`
Expected: PASS.

Run: `python -m evals.run_routing`
Expected: the 42 pre-existing cases must land exactly where they did before — **37/42, with the same five misses**. The six new cases bring the set to 48. If any of the original 42 changed route, the rule is too wide: narrow `_DOSE_PHRASES` or the precedence, do not edit the frozen case.

This was pre-measured on 2026-08-25, before the rule was written: simulating exactly the two clauses above over all 42 frozen cases (product-name regex, or a `_DOSE_PHRASES` hit plus a `_PLANT_NUTRITION_STEMS` hit, with budget keeping precedence) steals **zero** of them. So a miss here means the implementation drifted from the rule as specified, not that the rule needs loosening.

Record the before/after numbers in the commit message.

- [ ] **Step 5: Write the failing route tests**

Create `tests/test_dose_route.py`:

```python
"""The product-dose route inside the engine: it must compute, and it must not
retrieve, match products, or call the model."""

import json

import pytest

from src import dose_answer, doses, engine


DOSE_Q = "HİGRO FUBBY dekara ne kadar kullanmalıyım?"


@pytest.fixture
def no_llm(monkeypatch):
    """Make every expensive path explode, so a test passes only if the route
    genuinely avoided it."""
    def boom(*args, **kwargs):
        raise AssertionError("the dose route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    return monkeypatch


def _payload(product="HİGRO FUBBY", group="sebze", value="5"):
    return {"product": product, "group": group,
            "area": {"value": value, "unit": "donum"}}


def test_a_dose_question_without_inputs_returns_the_card(no_llm):
    result = engine.answer(DOSE_Q)
    assert result.route == "product_dose"
    assert result.answer == dose_answer.ASK_FOR_INPUTS
    assert result.dose_form["kind"] == "product_dose"
    assert result.form is None, "the budget card must not be served here"


def test_a_fresh_card_carries_no_errors(no_llm):
    result = engine.answer(DOSE_Q)
    assert all(v is None for v in result.dose_form["errors"].values())


def test_a_dose_question_recommends_no_products(no_llm):
    assert engine.answer(DOSE_Q).recommended_products == []


def test_a_complete_payload_is_computed(no_llm):
    result = engine.answer(DOSE_Q, None, None, _payload())
    assert result.dose_form is None
    assert "dekara" in result.answer
    assert dose_answer.SEASON_REFUSAL in result.answer


def test_a_rejected_payload_comes_back_as_a_card_with_errors(no_llm):
    result = engine.answer(DOSE_Q, None, None, _payload(value="0"))
    assert result.dose_form["errors"]["area"]
    assert result.dose_form["area"]["value"] == "0"


def test_a_group_with_no_figure_is_said_not_guessed(no_llm):
    result = engine.answer(DOSE_Q, None, None, _payload(product="FLY AZOT", group="meyve"))
    assert result.dose_form is None
    assert "yayımlanmamış" in result.answer


def test_a_submitted_payload_is_computed_whatever_the_router_says(no_llm):
    """Turn 2 does not bet on the classifier a second time - the budget route's
    rule, for the same reason: the card is attached to the first question."""
    result = engine.answer("teşekkürler", None, None, _payload())
    assert result.route == "product_dose"
    assert result.dose_form is None


def test_a_broken_computation_never_becomes_a_guess(no_llm, monkeypatch):
    monkeypatch.setattr(dose_answer, "compute", lambda *a: 1 / 0)
    result = engine.answer(DOSE_Q, None, None, _payload())
    assert result.answer == dose_answer.COMPUTE_FAILED
    assert result.dose_form is None


def _events(chunks):
    return [json.loads(c.split("data: ", 1)[1]) for c in chunks if "data: " in c]


def test_the_stream_serves_the_same_card(no_llm):
    events = _events(list(engine.stream_answer(DOSE_Q)))
    assert [e["type"] for e in events] == ["token", "dose_form", "done"]
    assert events[1]["form"]["kind"] == "product_dose"


def test_the_stream_computes_a_submitted_payload(no_llm):
    events = _events(list(engine.stream_answer(DOSE_Q, None, None, _payload())))
    assert [e["type"] for e in events] == ["token", "done"]
    assert "dekara" in events[0]["content"]


def test_both_transports_answer_identically(no_llm):
    """answer() and stream_answer() are mirror images; a route wired into one
    reaches no user while the tests stay green."""
    direct = engine.answer(DOSE_Q, None, None, _payload()).answer
    streamed = "".join(e["content"] for e in
                       _events(list(engine.stream_answer(DOSE_Q, None, None, _payload())))
                       if e["type"] == "token")
    assert direct == streamed
```

Run: `python -m pytest tests/test_dose_route.py -q`
Expected: FAIL — `TypeError: answer() takes from 1 to 3 positional arguments but 4 were given`.

- [ ] **Step 6: Wire the engine**

In `src/engine.py`, add the field to `ChatResult` and its serialisation:

```python
@dataclass
class ChatResult:
    answer: str
    recommended_products: list[RecommendedProduct]
    route: str = ""
    route_how: str = ""
    form: dict | None = None
    # The dose card travels on its own key, never inside `form`. An
    # already-deployed APK reads `form` and draws a BUDGET card from it; handing
    # it dose fields would render a money form over a dose question and submit
    # the answer back under the wrong payload.
    dose_form: dict | None = None

    def as_api(self) -> dict:
        return {
            "answer": self.answer,
            "recommended_products": [p.as_api() for p in self.recommended_products],
            "form": self.form,
            "dose_form": self.dose_form,
        }
```

Add `_dose_result` next to `_budget_result`:

```python
def _dose_result(payload: dict | None) -> ChatResult:
    """The dose route: no retrieval, no product match, no model call.

    Two multiplications in src/dose_answer.py over a figure the manufacturer
    published and an area the user selected. When the payload is absent or
    incomplete we return the card instead of an answer; a payload that was
    never submitted gets a clean card rather than a list of "required" errors.

    validate()/compute()/render() share one guard: any of them raising returns
    COMPUTE_FAILED with no card and no figures. They are documented never to
    raise, but on the streaming path the 200 and headers are already sent by
    the time this runs, so a raise here would break the connection mid-stream.
    """
    # Deferred like the router import: keeping engine's module-level imports
    # free of route modules is what stops the cycles the rest of this file
    # documents.
    from src import dose_answer

    submitted = bool(payload)
    try:
        inputs, errors = dose_answer.validate(payload or {})
        if inputs is not None:
            totals = dose_answer.compute(inputs)
            text = (dose_answer.render(inputs, totals) if totals
                    else dose_answer.no_dose_for_group(inputs))
            return ChatResult(answer=text, recommended_products=[],
                              route="product_dose")
    except Exception:  # noqa: BLE001 - a broken validation or sum must not become a guess
        return ChatResult(answer=dose_answer.COMPUTE_FAILED,
                          recommended_products=[], route="product_dose")

    return ChatResult(answer=dose_answer.ASK_FOR_INPUTS, recommended_products=[],
                      route="product_dose",
                      dose_form=dose_answer.form_spec(
                          errors if submitted else [],
                          payload if submitted else None))
```

Change `answer`'s signature and add the short-circuit **above** the budget one:

```python
def answer(message: str, history: list[dict] | None = None,
           budget_payload: dict | None = None,
           dose_payload: dict | None = None) -> ChatResult:
```

```python
    # Checked before budget: a submitted dose card is answered as a dose
    # question whatever the message it rode in on classifies as. The two
    # payloads are mutually exclusive in both clients; if one ever sends both,
    # the dose card is the one the user just pressed.
    if dose_payload or route == "product_dose":
        result = _dose_result(dose_payload)
        result.route_how = route_how
        return result

    if route == "budget" or budget_payload:
        ...
```

Mirror both in `stream_answer`:

```python
def stream_answer(
    message: str, history: list[dict] | None = None,
    budget_payload: dict | None = None,
    dose_payload: dict | None = None
) -> Iterator[str]:
```

```python
    # Must mirror answer() exactly, including the payload clause and its order.
    # Both clients stream, so a card wired only into answer() would reach no
    # user at all - and the tests would still pass.
    if dose_payload or route == "product_dose":
        result = _dose_result(dose_payload)
        yield _sse({"type": "token", "content": result.answer})
        if result.dose_form is not None:
            # A NEW event type: an already-deployed client ignores an unknown
            # `type` (see mobile-app/src/api.ts), so it shows the sentence and
            # no card rather than drawing a budget form out of dose fields.
            yield _sse({"type": "dose_form", "form": result.dose_form})
        yield _sse({"type": "done"})
        return
```

- [ ] **Step 7: Run the route tests**

Run: `python -m pytest tests/test_dose_route.py -q`
Expected: PASS.

- [ ] **Step 8: Wire the API**

In `src/main.py`, add after `BudgetPayload`:

```python
class DoseField(BaseModel):
    # Loose at the wire for the same reason BudgetField is, bool included: it
    # must reach src/dose_answer.py as a bool so the guard there can reject it,
    # rather than being smart-unioned into the int 1 on the way.
    value: str | int | float | bool = ""
    unit: str = ""


class DosePayload(BaseModel):
    product: str | None = None
    group: str | None = None
    area: DoseField | None = None
```

Add the request field to `ChatRequest`:

```python
    dose: DosePayload | None = Field(
        default=None, description="Filled product-dose card, when the user submitted one."
    )
```

Add the response key to `ChatResponse`:

```python
    # Optional so an already-deployed client, which never reads it, is unaffected.
    dose_form: dict | None = None
```

And pass it through in `chat()`:

```python
    history = [t.model_dump() for t in req.history]
    budget_payload = req.budget.model_dump() if req.budget else None
    dose_payload = req.dose.model_dump() if req.dose else None

    if req.stream:
        return StreamingResponse(
            engine.stream_answer(req.message, history, budget_payload, dose_payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result = engine.answer(req.message, history, budget_payload, dose_payload)
    return ChatResponse(**result.as_api())
```

- [ ] **Step 9: Pin the API surface**

**First, fix the two stubs that this signature change breaks.** `tests/test_main.py` monkeypatches `engine.answer` and `engine.stream_answer` with lambdas typed `(msg, hist, budget=None)` — lines 24 and 39. A fourth positional argument turns both into a `TypeError` that reads like a routing bug; the file's own comment above line 22 warns about exactly this. Change both to `(msg, hist, budget=None, dose=None)`.

Then append (note: `client` in this file is a module-level `TestClient`, not a fixture — do not add it as a parameter):

```python
def test_a_dose_card_reaches_the_json_transport(monkeypatch):
    monkeypatch.setattr(
        main.engine, "answer",
        lambda msg, hist, budget=None, dose=None:
            ChatResult(answer="x", recommended_products=[],
                       dose_form={"kind": "product_dose"}))
    body = client.post("/api/chat", json={"message": "doz"}).json()
    assert body["dose_form"] == {"kind": "product_dose"}


def test_a_submitted_dose_payload_reaches_the_engine(monkeypatch):
    seen = {}

    def fake(msg, hist, budget=None, dose=None):
        seen["dose"] = dose
        return ChatResult(answer="x", recommended_products=[])

    monkeypatch.setattr(main.engine, "answer", fake)
    client.post("/api/chat", json={
        "message": "doz",
        "dose": {"product": "HİGRO FUBBY", "group": "sebze",
                 "area": {"value": "5", "unit": "donum"}}})
    assert seen["dose"]["product"] == "HİGRO FUBBY"
    assert seen["dose"]["area"]["value"] == "5"


def test_a_boolean_area_survives_the_wire_as_a_boolean(monkeypatch):
    """The budget form's own lesson: a guard is worthless if a layer above it
    launders the value first. Pydantic's smart union would turn a JSON `true`
    into the int 1 before src/dose_answer.py ever saw it."""
    seen = {}

    def fake(msg, hist, budget=None, dose=None):
        seen["dose"] = dose
        return ChatResult(answer="x", recommended_products=[])

    monkeypatch.setattr(main.engine, "answer", fake)
    client.post("/api/chat", json={
        "message": "doz",
        "dose": {"product": "X", "group": "sebze",
                 "area": {"value": True, "unit": "donum"}}})
    assert seen["dose"]["area"]["value"] is True
```

Run: `python -m pytest tests/test_main.py -q`
Expected: PASS.

- [ ] **Step 10: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS, no failures.

- [ ] **Step 11: Drive it against a live server, both transports**

Start the API (no LM Studio needed — this route makes no model call):

```bash
python -m uvicorn src.main:app --port 8000
```

In a second shell:

```bash
curl -s -X POST localhost:8000/api/chat -H "Content-Type: application/json" -d "{\"message\":\"HİGRO FUBBY dekara ne kadar?\"}" | python -m json.tool
```

Expected: `dose_form.kind == "product_dose"`, `form` null, 40 entries in `products`.

```bash
curl -s -X POST localhost:8000/api/chat -H "Content-Type: application/json" -d "{\"message\":\"doz\",\"dose\":{\"product\":\"HİGRO FUBBY\",\"group\":\"sebze\",\"area\":{\"value\":\"5\",\"unit\":\"donum\"}}}" | python -m json.tool
```

Expected: an answer naming the method, the published per-dekar figure and the total, plus both closing sentences; `dose_form` null.

```bash
curl -s -N -X POST localhost:8000/api/chat -H "Content-Type: application/json" -d "{\"message\":\"HİGRO FUBBY dekara ne kadar?\",\"stream\":true}"
```

Expected: `token`, then `dose_form`, then `done`.

- [ ] **Step 12: Commit**

```bash
git add src/router.py src/engine.py src/main.py evals/routing_set.py tests/ && git commit -m "Route a dose question to its own card, on both transports"
```

---

## Task 6: The card

**Files:**
- Modify: `mobile-app/src/api.ts`, `mobile-app/app/(tabs)/chat.tsx`, `mobile-app/src/BudgetCard.tsx`
- Create: `mobile-app/src/DoseCard.tsx`, `mobile-app/src/turkish.ts`

**Interfaces:**
- Consumes: the `dose_form` SSE event and the `dose` request field from Task 5.
- Produces: `DosePayload`, `DoseFormSpec`, `sendChatMessageStream(message, history, handlers, budget?, dose?)`, and `<DoseCard form onSubmit disabled />` where `onSubmit(payload: DosePayload, summary: string)`.

- [ ] **Step 1: Add the wire types**

In `mobile-app/src/api.ts`, after the budget types:

```ts
export interface DoseFieldValue {
  value: string;
  unit: string;
}

export interface DosePayload {
  product?: string;
  group?: string;
  area?: DoseFieldValue;
}

export interface DoseGroup {
  id: string;
  label: string;
}

export interface DoseFormSpec {
  kind: "product_dose";
  products: string[];
  groups: DoseGroup[];
  // Echoed back on a rejected card, so one bad field does not wipe the rest.
  product: string;
  group: string;
  area: {
    label: string;
    value: string;
    unit: string;
    units: FormUnit[];
  };
  errors: { product: string | null; group: string | null; area: string | null };
}
```

Add the handler and the event branch:

```ts
export interface ChatStreamHandlers {
  onToken: (content: string) => void;
  onProducts: (products: RecommendedProduct[]) => void;
  onForm?: (form: FormSpec) => void;
  onDoseForm?: (form: DoseFormSpec) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}
```

```ts
      } else if (evt.type === "form") {
        handlers.onForm?.(evt.form);
      } else if (evt.type === "dose_form") {
        handlers.onDoseForm?.(evt.form);
      }
```

And the request field:

```ts
export function sendChatMessageStream(
  message: string,
  history: ChatTurn[],
  handlers: ChatStreamHandlers,
  budget?: BudgetPayload,
  dose?: DosePayload
): void {
```

```ts
  xhr.send(JSON.stringify({ message, history, stream: true, budget, dose }));
```

- [ ] **Step 2: Move the Turkish folding helper somewhere both cards can use it**

`BudgetCard.tsx` already owns a `fold()` that handles the dotted/dotless I; the dose card needs exactly the same one, and every product name here starts with `HİGRO`. Two copies is one copy too many.

Create `mobile-app/src/turkish.ts` holding the function verbatim as it stands in `BudgetCard.tsx:13-20`, exported:

```ts
// Turkish lowercasing for search boxes. toLowerCase() alone maps I to i but
// leaves I undotted, and the things users search for here - crop names, product
// names - are overwhelmingly the ones with dotted capitals.
export function fold(text: string): string {
  return text
    .replace(/I/g, "ı")
    .replace(/İ/g, "i")
    .toLowerCase()
    .replace(/[ışğüöç]/g, (c) => ({ ı: "i", ş: "s", ğ: "g", ü: "u", ö: "o", ç: "c" }[c] ?? c));
}
```

Delete the local copy from `BudgetCard.tsx` and import it there instead: `import { fold } from "./turkish";`. Nothing else in that file changes.

- [ ] **Step 3: Write the card**

Create `mobile-app/src/DoseCard.tsx` (import `fold` from `./turkish` rather than restating it — the copy shown inside this file below is the one you just moved, do not re-add it):

```tsx
// The product-dose card. Three inputs and nothing else: the product, the crop
// group, and the area with a unit selector - the same unit-as-SELECTION rule
// the budget card follows.
//
// There is deliberately NO application-method control. Of the 42 products with
// a per-area dose, 37 publish it for drip irrigation only, so a method selector
// would offer a choice in appearance only - and pressing the wrong half would
// say we hold no figure for a method the maker never published one for. The
// method is reported in the answer instead.
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { DoseFormSpec, DosePayload } from "./api";
import { colors } from "./theme";
// Shared with BudgetCard: typing "higro" has to find "HİGRO", and the dotted
// I is exactly what a plain toLowerCase() gets wrong.
import { fold } from "./turkish";

interface Props {
  form: DoseFormSpec;
  // `summary` is what the chat shows as the user's bubble for this turn. The
  // request still carries the original question, but echoing it again would
  // read as the user asking twice.
  onSubmit: (payload: DosePayload, summary: string) => void;
  // A stale card from an earlier turn stays rendered and tappable, so it needs
  // the same submit gate as the text input.
  disabled: boolean;
}

export default function DoseCard({ form, onSubmit, disabled }: Props) {
  const [product, setProduct] = useState(form.product);
  const [query, setQuery] = useState(form.product);
  const [group, setGroup] = useState(form.group);
  const [area, setArea] = useState(form.area.value);
  const [unit, setUnit] = useState(form.area.unit);

  // The list closes when the box already reads as the chosen product and
  // reopens the moment the text differs - the budget card's rule.
  const searchOpen = Boolean(query.trim() && query !== product);
  const matches = searchOpen
    ? form.products.filter((p) => fold(p).includes(fold(query))).slice(0, 8)
    : [];

  function submit() {
    if (disabled) return;
    const payload: DosePayload = {
      product,
      group,
      area: { value: area.trim(), unit },
    };
    const groupLabel = form.groups.find((g) => g.id === group)?.label ?? "";
    const unitLabel = form.area.units.find((u) => u.id === unit)?.label ?? "";
    const summary = [product, groupLabel, `${area.trim()} ${unitLabel}`.trim()]
      .filter(Boolean)
      .join(" · ");
    onSubmit(payload, summary);
  }

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Text style={styles.label}>Ürün</Text>
        <TextInput
          style={styles.input}
          value={query}
          onChangeText={setQuery}
          placeholder="Ürün arayın (örn. higro)"
          placeholderTextColor="#9aa"
        />
        {matches.map((name) => (
          <Pressable
            key={name}
            style={styles.match}
            onPress={() => {
              setProduct(name);
              setQuery(name);
            }}
          >
            <Text style={styles.matchText}>{name}</Text>
          </Pressable>
        ))}
        {form.errors.product ? (
          <Text style={styles.error}>{form.errors.product}</Text>
        ) : null}
      </View>

      <View style={styles.row}>
        <Text style={styles.label}>Grup</Text>
        <View style={styles.units}>
          {form.groups.map((g) => (
            <Pressable
              key={g.id}
              onPress={() => setGroup(g.id)}
              style={[styles.unit, group === g.id && styles.unitActive]}
            >
              <Text style={[styles.unitText, group === g.id && styles.unitTextActive]}>
                {g.label}
              </Text>
            </Pressable>
          ))}
        </View>
        {form.errors.group ? (
          <Text style={styles.error}>{form.errors.group}</Text>
        ) : null}
      </View>

      <View style={styles.row}>
        <Text style={styles.label}>{form.area.label}</Text>
        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            keyboardType="numeric"
            value={area}
            onChangeText={setArea}
            placeholder="0"
            placeholderTextColor="#9aa"
          />
          <View style={styles.units}>
            {form.area.units.map((u) => (
              <Pressable
                key={u.id}
                onPress={() => setUnit(u.id)}
                style={[styles.unit, unit === u.id && styles.unitActive]}
              >
                <Text style={[styles.unitText, unit === u.id && styles.unitTextActive]}>
                  {u.label}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
        {form.errors.area ? <Text style={styles.error}>{form.errors.area}</Text> : null}
      </View>

      <Pressable
        style={[styles.submit, disabled && styles.submitDisabled]}
        onPress={submit}
        disabled={disabled}
      >
        <Text style={styles.submitText}>Hesapla</Text>
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
  inputRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: "#e2e8e2",
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    color: colors.dark,
  },
  units: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  unit: {
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#e2e8e2",
  },
  unitActive: { backgroundColor: colors.green, borderColor: colors.green },
  unitText: { fontSize: 12, color: colors.dark },
  unitTextActive: { color: "#fff", fontWeight: "600" },
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

- [ ] **Step 4: Render it in the chat**

In `mobile-app/app/(tabs)/chat.tsx`:

Import it and its types:

```tsx
import DoseCard from "../../src/DoseCard";
```

```tsx
  DosePayload,
  DoseFormSpec,
```

Extend the `Message` type:

```tsx
  form?: FormSpec;
  doseForm?: DoseFormSpec;
```

Extend `sendTurn` and pass the payload through:

```tsx
  function sendTurn(text: string, budget?: BudgetPayload, dose?: DosePayload) {
```

```tsx
      onDoseForm: (doseForm) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === botId ? { ...m, doseForm, question: text } : m))
        );
      },
```

```tsx
    }, budget, dose);
```

And render the card beside the budget one, inside the same `messages.map`:

```tsx
              {m.doseForm && (
                <DoseCard
                  form={m.doseForm}
                  disabled={loading}
                  onSubmit={(payload, summary) => {
                    if (loading) return;
                    setMessages((prev) => [
                      // The card is consumed: replace it, so a stale card
                      // cannot be submitted twice.
                      ...prev.map((x) =>
                        x.id === m.id ? { ...x, doseForm: undefined } : x
                      ),
                      { id: newId(), role: "user", text: summary },
                    ]);
                    sendTurn(m.question ?? summary, undefined, payload);
                  }}
                />
              )}
```

Finally, the persistence strip: `chat.tsx` already drops `form` before saving (`messages.map(({ form, ...rest }) => rest)`). Drop the dose card the same way, or a reloaded conversation restores a card whose server-side state is gone:

```tsx
      messages: messages.map(({ form, doseForm, ...rest }) => rest) as never,
```

- [ ] **Step 5: Typecheck**

Run:

```bash
cd mobile-app && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add mobile-app/src/api.ts mobile-app/src/turkish.ts mobile-app/src/DoseCard.tsx mobile-app/src/BudgetCard.tsx "mobile-app/app/(tabs)/chat.tsx" && git commit -m "Draw the dose card, and consume it on submit"
```

---

## Task 7: Drive it for real, then write it down

Nothing here is optional. P1 and P2b both shipped defects that only a person driving the app found, and both times every test was green.

**Files:**
- Modify: `docs/superpowers/specs/2026-08-22-product-dose-design.md` (status), `.superpowers/sdd/progress.md`, `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md`
- Create: `docs/superpowers/2026-08-25-product-dose-route-findings.md`

- [ ] **Step 1: Run the app in a browser and press the card**

Two traps, both already paid for: run `expo start --web` from `mobile-app/`, and point the client at the local API (`EXPO_PUBLIC_API_BASE=http://127.0.0.1:8000`). This route needs **no LM Studio**.

```bash
cd mobile-app && npx expo start --web
```

With uvicorn running from Task 5 Step 11, drive the full flow at http://localhost:8081 and confirm each of these by looking at the screen:

1. Ask `HİGRO FUBBY dekara ne kadar kullanmalıyım?` → the sentence appears with the card under it.
2. The product search finds `HİGRO FUBBY` when you type `fubby`, and `HİGRO BARF` when you type `barf`.
3. Three group buttons; the pressed one is filled green.
4. `dönüm`/`hektar` switch, and hektar genuinely multiplies the answer by ten.
5. Submit → the user bubble shows the **entered values**, not the question repeated.
6. The answer names the method, the published dose and the total, and closes with both sentences.
7. The card is gone after submit (0 inputs, 0 buttons) and cannot be submitted twice.
8. Reload → the conversation restores with **no interactive card**.
9. Submit with the area empty → the card comes back with the error on the area and the product and group still selected.
10. Pick `FLY AZOT` + `Meyve` → the answer says no figure is published for that group, and prints **no number at all**.

Fix what is wrong in the source (never in the browser), then re-check from step 1.

- [ ] **Step 2: Screenshot the working flow**

Take a screenshot of the card and of a computed answer, and attach them to the findings doc below.

- [ ] **Step 3: Write the findings**

Create `docs/superpowers/2026-08-25-product-dose-route-findings.md` recording, at minimum:
- the routing gate before and after (the original 42 cases must be unchanged);
- the reviewed scope decision for `FLY AZOT` and `HIGRO 8 MN`, with the panel quotes;
- anything Step 1 found that no test caught — and, for each, whether a test now catches it;
- what is still open: `HİGRO FERRY`'s one figure for two groups (`lookup(FERRY, "tarla")` is `()`, and it appears in neither `unparsed` nor `dropped_slots`), and elemental → product mass (only 3 of 48 pages carry an NPK triple).

- [ ] **Step 4: Update the spec's status table**

In `docs/superpowers/specs/2026-08-22-product-dose-design.md` §12, mark P3 done with the merge commit.

- [ ] **Step 5: Update the record and the handoff memory**

Append the round to `.superpowers/sdd/progress.md` in the same voice as the P3a block.

Then rewrite the P3b block in `handoff-next-steps.md`: what shipped, the new pytest count, that **Emirhan needs a new APK** for the card to draw at all (the client reads a new SSE event and sends a new request field; an older build shows the sentence and no card), and that P4 (`crop_choice`) is next.

- [ ] **Step 6: Full suite, one last time**

Run: `python -m pytest -q`
Expected: PASS.

Run: `python -m evals.run_routing`
Expected: the original 42 unchanged.

- [ ] **Step 7: Commit and merge**

```bash
git add docs .superpowers && git commit -m "Record what the dose route ships and what it still refuses"
```

Then merge to `main` with `--no-ff`, verify **on the merged result** (`pytest -q` and a converter re-run that reproduces `data/product_doses.json` with no diff), and push. `main` is shared: rebase, never force-push. Do not touch `demo`.

---

## Self-Review

**Spec coverage** (`docs/superpowers/specs/2026-08-22-product-dose-design.md`):

| Spec section | Where |
| --- | --- |
| §2.1 amount for one application, as a range, method stated | Tasks 3, 4 |
| §2.2 the answer says whose number it is | Task 4 (`ATTRIBUTION`) |
| §2.3 a range stays a range | Task 3 (`test_a_range_stays_a_range`) |
| §2.4 season total refused by name | Task 4 (`SEASON_REFUSAL`) |
| §2.5 an unparsed product has no row and the route says so | Task 2 (product field error), Task 4 (`no_dose_for_group`) |
| §2.6 no model call, no retrieval, pytest only | Task 5 (`no_llm` fixture on every route test) |
| §3 the three questions and the refusal | Tasks 3–4 |
| §4 inputs from a card; method is not an input; crop not mapped to group | Tasks 2, 6 |
| §5 two multiplications; both transports | Tasks 3, 5 |
| §5 unit promotion at 1000 | Task 3 (`_promote`) |
| §7 attribution + per-application caveat by code | Task 4 |
| §8 every error row | Task 2 (field errors), Task 5 (`COMPUTE_FAILED`, empty table) |
| §9 the whole testing table | Tasks 1–5 |
| §10 out of scope: elemental→mass, season totals, crop→group table, dilutions | Not built; named in Task 7's findings |
| P3a's deferred `FLY AZOT` decision | Task 1 |

**Not covered by this plan, on purpose:** `HİGRO FERRY`'s single figure published for two groups. It needs a design decision (widening the `tarla` pattern swallows `Tarla sebzelerinde` in `HİGRO FERFORCE`), it is one figure on one page, and it does not block the route. Task 7 Step 3 records it as still open.
