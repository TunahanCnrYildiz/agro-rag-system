# World Layer Readable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the user's country from the conversation, teach `norms.lookup` to serve FAOSTAT figures for it, and put those figures into the assistant's answer with their source and their FAOSTAT flag.

**Architecture:** A new `src/context/country.py` mirrors `src/context/location.py` — same folding, same suffix discipline, same "unresolved is an answer" stance — backed by a committed alias table. `src/norms.py` gains a `country` argument and a third scope; `NormValue` starts carrying its unit so a lira figure and a dollar figure can never look alike. The answer reaches the prompt through the context blocks the province and the weather already use.

**Tech Stack:** Python 3.14 standard library only (`re`, `json`, `dataclasses`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-world-layer-readable-design.md`

## Global Constraints

- **A Turkish user's figures come from TÜİK.** Province beats national beats nothing. FAOSTAT's Türkiye series (area 223) is a cross-check and never a source of answers — a user in Turkey must never receive a `"ulke"` figure.
- **No currency conversion**, and no exchange rate anywhere. The unit travels with the value; what a user is shown is a later round.
- **`None` is a real answer.** An unresolved country, a crop mapped to `null`, and a missing cell all produce `None`, and the assistant asks rather than guessing.
- **Unit strings are the ones that already exist** in `src/budget.py:359`: `"kg/da"`, `"TL/kg"`, `"kg/ağaç"`. The world price adds `"USD/kg"`. Do not invent new spellings.
- **`province_table()` is not touched.** `src/crop_compare.py:349` prints the literal word `TÜİK` beside figures it receives from that table; keeping the table Turkey-only is what keeps that label true. The comparison card is a later round.
- **The API contract does not change.** No new request or response field.
- **No network access in any test.** `data/crop_norms.json`, `data/world_norms.json` and `data/crop_fao_map.json` are all committed.
- **Deployment files are not touched:** `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.github/workflows/docker-publish.yml`, `web-widget/Dockerfile`, `web-widget/docker-entrypoint.d/`, `mobile-app/eas.json`, `mobile-app/app.json`.
- **Commit messages:** short, natural, English, no `Co-Authored-By` trailer.
- **Console output** goes through `scripts/_console.py` where a script prints at all; prefix any command printing Turkish with `PYTHONIOENCODING=utf-8`.

## File Structure

| File | Responsibility |
|---|---|
| `src/norms.py` (modify) | `NormValue.unit`; `CropNorm.price_tl_kg` → `price_per_kg`; `lookup(crop, province, country)`; the world-layer read |
| `data/country_aliases.json` (new) | 199 countries → Turkish and English names, keyed by FAO area code |
| `src/context/country.py` (new) | `extract_country(message, history) -> int | None` |
| `src/engine.py` (modify) | The context-block lines that carry a country figure into the prompt |
| `tests/test_country.py` (new) | Resolution, and the five crop-name collisions |
| `tests/test_country_aliases.py` (new) | The table's completeness and integrity |
| `tests/test_norms_world.py` (new) | The country scope and the resolution order |

---

### Task 1: `NormValue` carries its unit, and the price field is renamed

A contained refactor with **no behaviour change**. Every figure this project serves today is Turkish and stays exactly as it is; the only difference is that its unit is now written down. Doing it first means Task 4 has somewhere to put `"USD/kg"`.

**Files:**
- Modify: `src/norms.py`
- Modify: `src/budget.py`, `src/crop_compare.py`, `src/engine.py`
- Modify: `tests/test_norms.py`, `tests/test_budget.py`, `tests/test_budget_route.py`, `tests/test_crop_compare.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `NormValue(amount, year, scope, region, unit, recent_min, recent_max)` — `unit` is **required** and sits fifth, before the two defaulted fields.
  - `CropNorm(crop, label, yield_kg_da, price_per_kg, yield_kg_tree)` — `price_tl_kg` renamed.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_norms.py`:

```python
def test_every_served_value_names_its_unit():
    """A price and a yield must never be indistinguishable. `unit` has no
    default precisely so a new measure cannot quietly inherit the wrong one."""
    norm = norms.lookup("bugday, durum bugdayi haric", "Konya")
    assert norm is not None
    assert norm.yield_kg_da.unit == "kg/da"
    assert norm.price_per_kg.unit == "TL/kg"


def test_a_per_tree_yield_names_its_own_unit():
    norm = norms.lookup("findik", "Ordu")
    assert norm is not None
    assert norm.yield_kg_tree is not None
    assert norm.yield_kg_tree.unit == "kg/ağaç"
```

If `"findik"` is not a crop id or Ordu carries no per-tree figure, find one that does with:

```bash
PYTHONIOENCODING=utf-8 python -c "
import json
d=json.load(open('data/crop_norms.json',encoding='utf-8'))['crops']
for cid,v in d.items():
    m=v.get('yield_kg_tree')
    if isinstance(m,dict):
        for k in m:
            if k!='scope': print(cid,'|',k); break
        break
"
```

and use what it prints. Report which pair you used.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_norms.py -q`
Expected: FAIL — `AttributeError: 'NormValue' object has no attribute 'unit'`

- [ ] **Step 3: Add the field and thread it through**

In `src/norms.py`, add to `NormValue` after `recent_max`:

```python
    # WHICH unit, written down rather than inferred from the field name that
    # holds it. `CropNorm.price_per_kg` is lira for a Turkish figure and
    # dollars for a FAOSTAT one, and nothing else in the value says so.
    # No default: a default would let a price inherit "kg/da" in silence,
    # and a claim that is almost true is this project's recurring defect.
    unit: str
```

`recent_min` and `recent_max` already carry defaults, and a field without a default
cannot follow one that has it — so **declare the field order
`amount, year, scope, region, unit, recent_min, recent_max`**, with `unit` fifth.
The 29 positional call sites in the tests pass six arguments today
(`NormValue(28.4, 2025, "il", "Ordu", 73.7, 105.6)`) and each gains the unit in
fifth position (`NormValue(28.4, 2025, "il", "Ordu", "kg/da", 73.7, 105.6)`).
Read each site to see which measure it stands for; a price site takes `"TL/kg"`,
a per-tree site `"kg/ağaç"`.

Give `_pick` the unit:

```python
def _pick(measure: dict, years: list[int], province: str | None,
          unit: str) -> NormValue | None:
```

and pass `unit=unit` in the `NormValue(...)` construction.

In `_resolve`, pass the right unit per measure:

```python
    return CropNorm(
        crop=crop_id,
        label=entry["label"],
        yield_kg_da=_pick(entry["yield_kg_da"], years, province, "kg/da"),
        price_per_kg=_pick(entry["price_tl_kg"], years, province, "TL/kg"),
        yield_kg_tree=(_pick(entry["yield_kg_tree"], years, province, "kg/ağaç")
                       if "yield_kg_tree" in entry else None),
    )
```

Note the asymmetry and keep it: the **JSON key stays `price_tl_kg`** — that file is TÜİK only and its prices really are lira — while the **dataclass field becomes `price_per_kg`**.

- [ ] **Step 4: Rename the field everywhere it is read**

```bash
PYTHONIOENCODING=utf-8 grep -rn "price_tl_kg" --include="*.py" src tests evals
```

Rename **only `CropNorm`'s attribute** (`.price_tl_kg`, `price_tl_kg=` on a `CropNorm`).
Two things keep their name and both are easy to sweep up by mistake:

- **Every string literal `"price_tl_kg"`** indexes the JSON file. `data/crop_norms.json`
  is TÜİK only and its prices really are lira.
- **`BudgetInputs.price_tl_kg` in `src/budget.py:145` is a different field on a
  different type** — the price the user typed into the budget form, which
  `src/budget.py:739` prints with the word `TL` beside it. It is lira by
  construction, not by assumption. A foreign user's form will need a currency of
  its own, and that is the round that decides what a user sees.

`tests/test_build_crop_norms.py` contains **both kinds**: seven JSON-key reads that
stay, and **two genuine `CropNorm` attribute reads at lines 123 and 288**
(`n.price_tl_kg` where `n = norms.lookup(...)`) that must be renamed. Leaving those
two raises `AttributeError` inside a test whose own trailing lines clear
`norms._load`'s `lru_cache` — the cleanup is skipped, the cache stays poisoned with
that test's tiny table, and seven further tests in `tests/test_compare_route.py`
fail for a reason that has nothing to do with them.

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS, 1096 passed (the two new tests replace nothing; report the actual number)

- [ ] **Step 6: Commit**

```bash
git add src tests
git commit -m "Let a norm value say which unit it is in"
```

---

### Task 2: The country alias table

**Files:**
- Create: `data/country_aliases.json`
- Create: `tests/test_country_aliases.py`

**Interfaces:**
- Consumes: `data/world_norms.json`'s `countries` block.
- Produces: a JSON object keyed by FAO area code as a string, each value `{"fao": str, "tr": [str, ...], "en": [str, ...]}`. Both lists are non-empty.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_country_aliases.py`:

```python
import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def aliases() -> dict:
    return json.loads((DATA / "country_aliases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def world_countries() -> dict:
    document = json.loads((DATA / "world_norms.json").read_text(encoding="utf-8"))
    return document["countries"]


def test_every_country_in_the_world_file_has_an_entry(aliases, world_countries):
    """Not 'most of them'. A country with no entry is a user the assistant
    cannot place, and it fails silently as 'no figures for you'."""
    missing = [code for code in world_countries if code not in aliases]
    assert missing == []


def test_no_entry_invents_a_country(aliases, world_countries):
    assert set(aliases) <= set(world_countries)


def test_every_entry_carries_both_languages(aliases):
    for code, entry in aliases.items():
        if entry.get("aggregate"):
            continue
        assert entry["tr"], code
        assert entry["en"], code
        assert all(isinstance(name, str) and name.strip() for name in entry["tr"]), code
        assert all(isinstance(name, str) and name.strip() for name in entry["en"]), code


def test_the_fao_label_matches_the_world_file(aliases, world_countries):
    for code, entry in aliases.items():
        assert entry["fao"] == world_countries[code]["label"], code


def test_no_name_is_claimed_by_two_countries(aliases):
    """An ambiguous name resolves to whichever entry is tried first, which is
    an arbitrary answer dressed as a confident one.

    Two COUNTRIES may not share a name. One country repeating a name across its
    own `tr` and `en` is ordinary and must stay allowed: roughly 45 of these are
    spelled identically in both languages — Panama, Kenya, Malta, Belize, Yemen,
    Sudan. Forbidding that forces an invented variant into one of the lists and
    the name people actually type stops matching."""
    seen: dict[str, str] = {}
    for code, entry in aliases.items():
        for key in {name.strip().casefold() for name in entry["tr"] + entry["en"]}:
            assert seen.get(key, code) == code,                 f"{key!r} claimed by {seen.get(key)} and {code}"
            seen[key] = code


def test_the_china_aggregate_is_marked_and_unreachable():
    """Area 351 sums mainland, Hong Kong, Macao and Taiwan - an aggregate that
    survived the world layer's filter only because that filter dropped area
    codes >= 5000. Nothing may resolve to it, so it carries no names."""
    document = json.loads((DATA / "country_aliases.json").read_text(encoding="utf-8"))
    entry = document["351"]
    assert entry["aggregate"]
    assert entry["tr"] == []
    assert entry["en"] == []


def test_china_resolves_to_the_mainland_series(aliases):
    assert "Çin" in aliases["41"]["tr"]
    assert "China" in aliases["41"]["en"]


@pytest.mark.parametrize("code, tr, en", [
    ("223", "Türkiye", "Turkey"),
    ("68", "Fransa", "France"),
    ("235", "Özbekistan", "Uzbekistan"),
    ("59", "Mısır", "Egypt"),
])
def test_known_countries_carry_their_ordinary_names(aliases, code, tr, en):
    assert tr in aliases[code]["tr"], code
    assert en in aliases[code]["en"], code
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_country_aliases.py -q`
Expected: FAIL — `FileNotFoundError: .../data/country_aliases.json`

- [ ] **Step 3: List what you are naming**

```bash
PYTHONIOENCODING=utf-8 python -c "
import json,sys
sys.stdout.reconfigure(encoding='utf-8')
c=json.load(open('data/world_norms.json',encoding='utf-8'))['countries']
for k in sorted(c,key=int): print(f'{k:>4} {c[k][\"label\"]}')
"
```

- [ ] **Step 4: Write the table**

One entry per code, in the order that command prints. Four rules:

1. **`fao` is copied exactly** from the listing. A test compares them character for character.
2. **`tr` is what a Turkish speaker types.** `Fransa`, `Özbekistan`, `Mısır`, `Hollanda`, `Yunanistan`. Where the everyday name differs from the formal one, list both.

   **Where the two languages spell it the same, write the same spelling in both lists.** Panama, Kenya, Malta, Belize, Yemen, Sudan and about forty others are identical in Turkish and English. Put `Panama` in `tr` **and** in `en`. Never reach for an archaic or formal variant to make the lists differ — an earlier draft of this plan forbade the repetition by accident and it produced `British Honduras` for Belize, a name dropped in 1973, so an English speaker typing `Belize` would not have matched.
3. **`en` is what an English speaker types**, which is often not FAOSTAT's label: FAOSTAT writes `Iran (Islamic Republic of)`, `China, mainland`, `Bolivia (Plurinational State of)`, `Democratic People's Republic of Korea`. Put `Iran`, `China`, `Bolivia`, `North Korea` in `en`. Nobody types a parenthesis.
4. **A name belongs to exactly one country.** The `test_no_name_is_claimed_by_two_countries` gate is strict on purpose. FAOSTAT splits `China, mainland` (41), `China, Hong Kong SAR` (96), `China, Macao SAR` (128) and `China, Taiwan Province of` (214): give the bare `China` / `Çin` to **mainland, code 41**, and qualify the others (`Hong Kong`, `Makao`).

5. **Area 351 `China` is an AGGREGATE and gets no names at all.** Measured 2026-09-25: its 2024 series agrees with `China, mainland` within 1% on **94 of the 105 crops they share**, because it sums mainland, Hong Kong, Macao and Taiwan. It is the same class of thing as `Africa` or `European Union (27)`, which the world layer deliberately dropped — it survived only because that filter removed area codes **≥ 5000** and this one is 351. A sweep of all 199 areas found no second case.

   It still gets an entry, because "every country is decided" is the discipline this table holds, but the entry says what it is and carries no names:

```json
  "351": {"fao": "China", "tr": [], "en": [], "aggregate":
          "Sums 41 mainland, 96 Hong Kong, 128 Macao and 214 Taiwan; agrees with 41 within 1% on 94 of 105 shared crops, measured 2026-09-25"}
```

Do not invent a country that is not in the listing, and do not skip one because its name is awkward.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_country_aliases.py -q`
Expected: PASS, 11 passed

- [ ] **Step 6: Report what you wrote**

```bash
PYTHONIOENCODING=utf-8 python -c "
import json,sys
sys.stdout.reconfigure(encoding='utf-8')
a=json.load(open('data/country_aliases.json',encoding='utf-8'))
print('entries:',len(a))
print('tr names:',sum(len(v['tr']) for v in a.values()))
print('en names:',sum(len(v['en']) for v in a.values()))
print('entries where en differs from the FAO label:',
      sum(1 for v in a.values() if v['fao'] not in v['en']))
"
```

Put the output in your report, and list every entry where you were unsure which name a speaker would use.

- [ ] **Step 7: Commit**

```bash
git add data/country_aliases.json tests/test_country_aliases.py
git commit -m "Name all 199 countries in Turkish and English"
```

---

### Task 3: `extract_country`

**Files:**
- Create: `src/context/country.py`
- Create: `tests/test_country.py`

**Interfaces:**
- Consumes: `data/country_aliases.json` (Task 2), `src.engine._normalize_tr`.
- Produces: `extract_country(message: str, history: list[dict] | None = None) -> int | None` returning the FAO area code.

**Read `src/context/location.py` before you start.** This module is its twin and reuses its reasoning; the comments there explain why each guard exists and those reasons all apply here.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_country.py`:

```python
import pytest

from src.context.country import extract_country

# Verified against data/world_norms.json on 2026-09-25. Note 41, not 351:
# 351 is FAOSTAT's `China` AGGREGATE, which this project never resolves to.
TURKIYE, FRANCE, EGYPT = 223, 68, 59
CHINA, MOROCCO, INDIA = 41, 143, 100


def test_a_turkish_locative_resolves():
    assert extract_country("Fransa'dayım, buğday ekiyorum") == FRANCE


def test_an_ordinary_turkish_case_suffix_resolves():
    assert extract_country("fransada yasiyorum") == FRANCE


def test_an_english_preposition_resolves():
    assert extract_country("I am in France and grow wheat") == FRANCE


def test_a_bare_name_as_the_whole_message_resolves():
    """The natural reply to "hangi ülkedesiniz?"."""
    assert extract_country("Mısır") == EGYPT
    assert extract_country("France") == FRANCE


def test_nothing_resolves_to_nothing():
    assert extract_country("buğdayıma ne zaman gübre atmalıyım") is None


@pytest.mark.parametrize("message", [
    "mısır ektim, ne kadar gübre atayım",
    "mısır silajı için doz nedir",
    "fasulye ektim",
    "hindistan cevizi yetiştirmek istiyorum",
    "bu gübre bakla için mi",
    "yenidünya (malta eriği) hakkında bilgi",
])
def test_a_crop_sentence_never_resolves_to_a_country(message):
    """Measured against our 246 crop labels: `Mısır` IS a crop label, `Fas`
    sits inside `Fasulye`, `Çin` inside `İçin`, `Hindistan` inside
    `Hindistan Cevizi`, `Malta` inside `Malta Eriği`. Substring matching
    would answer Morocco to "fasulye ektim"."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("Mısır'dayım", EGYPT),
    ("Fas'ta çiftçilik yapıyorum", MOROCCO),
    ("Çin'de yaşıyorum", CHINA),
    ("Hindistan'dayım", INDIA),
])
def test_the_same_words_resolve_when_stated_as_a_place(message, code):
    """The other half of the collision: refusing the crop sentence must not
    cost the genuine statement of location."""
    assert extract_country(message) == code


def test_the_current_message_beats_history():
    history = [{"role": "user", "content": "Fransa'dayım"}]
    assert extract_country("Mısır'dayım", history) == EGYPT


def test_history_is_read_backwards_when_the_message_says_nothing():
    history = [
        {"role": "user", "content": "Fransa'dayım"},
        {"role": "assistant", "content": "Mısır'da durum farklı"},
    ]
    assert extract_country("peki gübre?", history) == FRANCE


def test_an_assistant_turn_is_never_evidence():
    history = [{"role": "assistant", "content": "Fransa'da buğday verimi yüksektir"}]
    assert extract_country("peki bizde?", history) is None
```

**These codes are verified, but check them again before you rely on them.** An
earlier draft of this plan had `MOROCCO = 136`, which is **Mauritania** — a test
pinning "Fas'ta" to the wrong country would have passed forever:

```bash
PYTHONIOENCODING=utf-8 python -c "
import json,sys
sys.stdout.reconfigure(encoding='utf-8')
c=json.load(open('data/world_norms.json',encoding='utf-8'))['countries']
for k,v in sorted(c.items(),key=lambda x:int(x[0])):
    if v['label'] in ('Morocco','China, mainland','India','Egypt','France','Türkiye'):
        print(f'{v[\"label\"]:<18} = {k}')
"
```

If a code differs, fix the constant and say so in your report. Do not change the test's intent.

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_country.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.context.country'`

- [ ] **Step 3: Write the module**

Create `src/context/country.py`. Mirror `src/context/location.py`'s structure exactly — load the table, fold every alias, order longest-first, and accept the same four forms it accepts, plus one English form:

```python
"""Which country the user is in, re-derived from the conversation every call.

The twin of location.py, and deliberately a separate module: the two tables
have different shapes and different failure modes, and merging them would make
both harder to read. Everything location.py says about storing nothing
server-side applies here unchanged.

Returns the FAO AREA CODE rather than a name. That is what indexes
data/world_norms.json, and FAOSTAT's labels are not what anyone types -
`Iran (Islamic Republic of)`, `China, mainland`, `Bolivia (Plurinational
State of)`.

THE COLLISION THIS MODULE EXISTS TO SURVIVE. Turkish country names sit inside
crop names. Measured against our 246 crop labels: `Mısır` IS the label for
maize, `Fas` sits inside `Fasulye`, `Çin` inside `İçin` - one of the commonest
words in the language - `Hindistan` inside `Hindistan Cevizi`, and `Malta`
inside `Malta Eriği`. A substring match answers Morocco to "fasulye ektim".
location.py already solved this shape of problem for provinces and its guards
are reused here rather than reinvented: a name resolves only with a case
suffix, as the whole message, or before a place noun, and a short name needs
the strict suffix.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from src.config import DATA_DIR
from src.engine import _normalize_tr

_TABLE = DATA_DIR / "country_aliases.json"
```

Then, following `location.py` line for line:

- `_load()` — read the table once; a broken file yields an empty mapping rather than raising, the way `norms._load` does.
- `_FOLDED: dict[str, int]` — every Turkish and English alias folded with `_normalize_tr`, mapped to its integer code.
- `_ORDERED` — `sorted(_FOLDED, key=len, reverse=True)`.
- Copy `_PERSON`, `_SUFFIX`, `_SHORT`, `_STRICT_SUFFIX`, `_PLACE` and `_TRIM` from `location.py` **verbatim**, with a comment saying they are copied and why they are not imported (importing would couple two tables that will drift apart as the country table gains alias languages).
- Add one form `location.py` does not need:

```python
# English states location with a preposition, not a suffix: "I am in France",
# "from Kenya". The Turkish branches never fire on these because an English
# name takes no case ending.
_EN_PLACE = r"(?:in|from|at)\s+"
```

- `_find(text)` — the same four branches as `location.py._find` (apostrophe, case suffix, whole message, place noun), plus `re.search(rf"(?<!\w){_EN_PLACE}{k}(?!\w)", folded)`.
- `extract_country(message, history)` — identical in shape to `extract_province`: the current message first, then user turns backwards. **Assistant turns are never evidence**, exactly as in `location.py`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_country.py -q`
Expected: PASS, 17 passed

If a collision test fails, **do not weaken it**. The guard it exercises is the reason this module is written the way it is; a failure means the regex is wrong, not the test.

- [ ] **Step 5: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: PASS

```bash
git add src/context/country.py tests/test_country.py
git commit -m "Resolve the user's country from the conversation"
```

---

### Task 4: `lookup` serves the country

**Files:**
- Modify: `src/norms.py`
- Create: `tests/test_norms_world.py`

**Interfaces:**
- Consumes: `NormValue.unit` (Task 1), `data/world_norms.json`, `data/crop_fao_map.json`.
- Produces: `lookup(crop: str, province: str | None, country: int | None = None) -> CropNorm | None`. `province_table` keeps its current signature and behaviour.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_norms_world.py`:

```python
import pytest

from src import norms

TURKIYE, FRANCE = 223, 68
WHEAT = "bugday, durum bugdayi haric"


def test_a_country_figure_is_served_when_no_province_resolves():
    norm = norms.lookup(WHEAT, None, country=FRANCE)
    assert norm is not None
    assert norm.yield_kg_da is not None
    assert norm.yield_kg_da.scope == "ulke"
    assert norm.yield_kg_da.region == "France"
    assert norm.yield_kg_da.unit == "kg/da"


def test_a_country_price_is_in_dollars_and_says_so():
    norm = norms.lookup(WHEAT, None, country=FRANCE)
    assert norm.price_per_kg is not None
    assert norm.price_per_kg.unit == "USD/kg"


def test_a_province_always_wins_over_a_country():
    """The world layer never overrides TÜİK. A province figure is provincial
    even when a country was also named."""
    norm = norms.lookup(WHEAT, "Konya", country=FRANCE)
    assert norm.yield_kg_da.scope == "il"
    assert norm.yield_kg_da.region == "Konya"
    assert norm.price_per_kg.unit == "TL/kg"


def test_turkiye_as_a_country_serves_tuik_not_faostat():
    """FAOSTAT carries Türkiye too. It is a cross-check, not a source."""
    norm = norms.lookup(WHEAT, None, country=TURKIYE)
    assert norm.yield_kg_da.scope == "tr"
    assert norm.yield_kg_da.region == "Türkiye"
    assert norm.price_per_kg.unit == "TL/kg"


def test_no_country_and_no_province_is_todays_behaviour():
    before = norms.lookup(WHEAT, None)
    after = norms.lookup(WHEAT, None, country=None)
    assert before == after


def test_a_crop_with_no_fao_counterpart_has_no_country_figure():
    """105 of our 246 crop ids map to null with a stated reason. `salep` is
    one; if it has gained a mapping, pick another null entry from
    data/crop_fao_map.json and say which in your report."""
    norm = norms.lookup("salep", None, country=FRANCE)
    assert norm is not None          # the crop exists
    assert norm.yield_kg_da is None  # the world layer has nothing for it


def test_a_country_that_does_not_grow_the_crop_yields_nothing():
    """A real code with no cell for this item. Find one with the command in
    Step 3 and name it in your report."""
    norm = norms.lookup("cay yapraklari", None, country=FRANCE)
    assert norm is None or norm.yield_kg_da is None


def test_an_unknown_crop_is_still_none():
    assert norms.lookup("bu bir urun degil", None, country=FRANCE) is None


def test_the_world_year_is_the_cells_own_year():
    """FAOSTAT ends at 2024 where TÜİK reaches 2025. A world figure must
    never borrow the Turkish file's latest year."""
    norm = norms.lookup(WHEAT, None, country=FRANCE)
    assert norm.yield_kg_da.year <= 2024
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_norms_world.py -q`
Expected: FAIL — `TypeError: lookup() got an unexpected keyword argument 'country'`

- [ ] **Step 3: Check the two crop ids the tests assume**

```bash
PYTHONIOENCODING=utf-8 python -c "
import json,sys
sys.stdout.reconfigure(encoding='utf-8')
m=json.load(open('data/crop_fao_map.json',encoding='utf-8'))['map']
w=json.load(open('data/world_norms.json',encoding='utf-8'))
print('salep ->', m.get('salep'))
print('cay yapraklari ->', m.get('cay yapraklari'))
code=(m.get('cay yapraklari') or {}).get('fao')
print('France has a cell for it:', f'{code}|68' in w['yield'] if code else 'n/a')
print()
print('a crop France DOES grow, for the positive tests:')
mm=m.get('bugday, durum bugdayi haric'); print('  wheat ->', mm, '| cell:', f\"{mm['fao']}|68\" in w['yield'])
"
```

If either assumption is wrong, substitute a crop id that satisfies it and **say which you used and why** in your report.

- [ ] **Step 4: Implement the country scope**

In `src/norms.py`:

```python
_WORLD = DATA_DIR / "world_norms.json"
_FAO_MAP = DATA_DIR / "crop_fao_map.json"
TURKIYE_AREA = 223   # FAOSTAT carries Türkiye; TÜİK is better and wins. See _resolve.


@lru_cache(maxsize=1)
def _load_world() -> dict:
    """The world layer, or an empty mapping. A broken file must not break
    answering, the same rule _load() follows for the Turkish one."""
```

Load both files behind `lru_cache` the way `_load()` already does, returning `{}` on any failure. **Add them to whatever fixture clears `_load`'s cache in `tests/conftest.py`** so a test cannot see another test's file.

Then a world picker beside `_pick`:

```python
def _pick_world(cells: dict, area: int, unit: str) -> NormValue | None:
    """The most recent year in one `"<item>|<area>"` series.

    No `recent_min`/`recent_max`: the five-year spread printed beside a Turkish
    figure comes from the same source as the figure. Mixing a FAOSTAT range
    into a surface built for TÜİK's would put two different things behind one
    label, so the range is left None until a surface asks for it.
    """
```

and the resolution order in `_resolve`, which gains a `country: int | None = None`
argument. `province_table` calls `_resolve` too and keeps passing nothing, so it
continues to serve Turkish figures only. `_resolve_world(crop_id, entry, country)`
is the sibling that builds a `CropNorm` from the world file using `_pick_world`:

```python
    # A province beats a country beats nothing. Türkiye as a country resolves
    # to the national TÜİK row, never to FAOSTAT's area 223 - that series is a
    # cross-check and the previous spec settled it.
    if province is None and country is not None and country != TURKIYE_AREA:
        return _resolve_world(crop_id, entry, country)
```

`lookup` gains `country: int | None = None` and passes it through. `province_table` does **not** — its signature and behaviour are unchanged.

For a world crop with no FAO mapping, or a mapping with no cell for that area, return a `CropNorm` whose measures are `None` rather than returning `None` for the whole crop — the crop exists, the figure does not, and the caller prefills what it can. That is the rule `lookup`'s own docstring already states.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_norms_world.py -q`
Expected: PASS, 9 passed

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: PASS — no existing test may change behaviour, because no caller passes `country` yet.

```bash
git add src/norms.py tests/test_norms_world.py tests/conftest.py
git commit -m "Serve a country's figures when no province resolves"
```

---

### Task 5: The figure reaches the answer

**Files:**
- Modify: `src/engine.py`
- Modify: `tests/test_engine.py`

**Interfaces:**
- Consumes: `country.extract_country` (Task 3), `norms.lookup(..., country=...)` (Task 4).
- Produces: no new public function — context-block lines only.

- [ ] **Step 1: Read the seam before changing it**

```bash
PYTHONIOENCODING=utf-8 sed -n '678,760p' src/engine.py
```

`_context_block(route, message, history, today)` builds the situational lines for `fert_plan`; `_crop_choice_block(message, history, today)` does the same for `crop_choice`. Both already resolve the province and both already state plainly when they could not. Follow that shape.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_engine.py`:

```python
def test_a_country_figure_reaches_the_prompt_with_its_source():
    block = engine._crop_choice_block("Fransa'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "France" in block
    assert "kg/da" in block


def test_a_world_figure_says_when_it_is_an_estimate():
    """41,3% of the shipped world yield cells carry FAOSTAT's `E` flag - the
    figure is FAO's estimate, not a country's report. This project prints a
    number with where it came from or does not print it."""
    block = engine._crop_choice_block("Nijerya'dayım, sorgum ekiyorum",
                                      None, date(2026, 9, 25))
    assert "tahmin" in block.lower() or block == ""


def test_a_turkish_user_still_gets_tuik():
    block = engine._crop_choice_block("Konya'dayım, buğday mı ekmeliyim",
                                      None, date(2026, 9, 25))
    assert "Konya" in block
    assert "France" not in block


def test_an_unresolved_country_asks_rather_than_guessing():
    block = engine._crop_choice_block("buğday mı ekmeliyim", None,
                                      date(2026, 9, 25))
    assert "BILINMIYOR" in block or "bilinmiyor" in block.lower()
```

Check `_crop_choice_block`'s exact current output before asserting on it — if it already contains an "unknown" line for the province, reuse that wording rather than inventing a second one. Adjust the assertions to what the function actually produces and **report what you changed and why**.

- [ ] **Step 3: Run them to verify they fail**

Run: `python -m pytest tests/test_engine.py -q -k "country or world or tuik"`
Expected: FAIL

- [ ] **Step 4: Add the lines**

In `_crop_choice_block` (and `_context_block` where the route already receives situational context), after the province is resolved:

- Resolve the country with `country.extract_country(message, history)`.
- Call `norms.lookup(crop, province, country=country)` for the crop the route already knows about, if any.
- When the figure's `scope` is `"ulke"`, state the country, the figure, its unit, and **its year** — never implying it shares TÜİK's latest.
- When the cell's FAOSTAT flag is `E`, say so in the line. The flag must be reachable from the value; if it is not, stop and report rather than dropping it — carrying it is why the previous round put it in the file.

Wrap the whole addition in the same `try/except` the surrounding code already uses: a context line is a convenience and must never break answering.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_engine.py -q`
Expected: PASS

- [ ] **Step 6: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: PASS

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Put the country's figures into the answer, flag and all"
```

---

## Out of scope

The budget and comparison cards, currency conversion, a country field in the profile, and alias languages beyond Turkish and English. `province_table()` and `src/crop_compare.py` are untouched: the comparison card prints the literal word `TÜİK` beside its figures, and keeping that path Turkey-only is what keeps the label true.
