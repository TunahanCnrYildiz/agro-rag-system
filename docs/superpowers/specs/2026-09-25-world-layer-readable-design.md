# Making the world layer readable: country scope for `norms.lookup`

Design, 2026-09-25. Follows `docs/superpowers/specs/2026-09-23-faostat-world-layer-design.md`.

## Where this starts

`data/world_norms.json` shipped on 2026-09-25 (merge `25476be`): 143 crops across
199 countries, 2016–2024, with a producer price for 136 of them.
`data/crop_fao_map.json` decides all 246 of our Turkish crop ids — 141 onto FAO item
codes, 105 nulled with a stated reason.

**Nothing reads either file.** `norms.lookup(crop, province)` opens
`data/crop_norms.json` and stops at the Turkish border, exactly as it did before that
round. The presentation now tells the client the assistant works abroad; this design
is what makes that sentence true.

## What exists to build on

| | |
|---|---|
| `src/context/location.py` | `extract_province(message, history)` — re-derived from the conversation each call, nothing stored server-side. 81 provinces, folded names, longest match first, Turkish suffix tolerance. Districts deliberately out of scope. |
| `src/norms.py` | `lookup(crop, province)`, `available_crops()`, `latest_year()`, `province_table(province)`. `NormValue` already carries `amount, year, scope ("il"\|"tr"), region, recent_min, recent_max`. |
| `src/engine.py` | `_context_block(route, message, history, today)` at line 678 builds the situational lines that reach the prompt; `_crop_choice_block` at 726 does the same for `crop_choice`. The province and the weather already arrive this way. |

`location.py`'s own docstring anticipates this round: *"When membership arrives, a
profile value becomes the default and this function stays exactly as it is."* Country
resolution is built the same way and inherits the same future.

## 1. Country resolution — `src/context/country.py`

A twin of `location.py`, not a generalisation of it. The two tables have different
shapes and different failure modes, and merging them would make both harder to read.

```python
def extract_country(message: str, history: list[dict] | None = None) -> int | None:
    """The FAO area code for the country the user names, or None."""
```

It returns the **FAO area code** (223 for Türkiye), not a label, because that is what
indexes `world_norms.json` and because the labels are unstable — FAOSTAT writes
`Iran (Islamic Republic of)` and `China, mainland`, which nobody types.

**Unresolved is a first-class answer.** `None` means the assistant asks, exactly as it
does today for a user who writes "Bafra" instead of a province. No guessing, no
defaulting to Türkiye.

### `data/country_aliases.json`

199 entries, one per country in `world_norms.json`, keyed by FAO area code:

```json
{
  "223": {"fao": "Türkiye",    "tr": ["Türkiye", "Turkiye"], "en": ["Turkey", "Türkiye"]},
  "68":  {"fao": "France",     "tr": ["Fransa"],             "en": ["France"]},
  "235": {"fao": "Uzbekistan", "tr": ["Özbekistan"],         "en": ["Uzbekistan"]},
  "59":  {"fao": "Egypt",      "tr": ["Mısır"],              "en": ["Egypt"]}
}
```

Turkish and English only, because the corpus is Turkish and English only — an Uzbek
question is already answered in Uzbek from TR/EN sources, and adding a third alias
language later is a data change, not a code change. **Every one of the 199 gets an
entry**, the same completeness discipline `crop_fao_map.json` holds; a test asserts it.

### Country names collide with crop names, and `location.py` already knows how

Measured against our 246 crop labels on 2026-09-25:

| Turkish country name | Collides with |
|---|---|
| **Mısır** (Egypt) | the crop label `Mısır` **exactly**, plus `Mısır (Hasıl)`, `Mısır (Slaj)` |
| **Hindistan** (India) | inside `Hindistan Cevizi` |
| **Fas** (Morocco) | inside `Fasulye` |
| **Çin** (China) | inside `İçin` — one of the commonest words in Turkish |
| **Malta** | inside `Malta Eriği` |

Substring matching would resolve "fasulye ektim" to Morocco. `location.py` already
carries the discipline that prevents this and it is reused rather than reinvented:

- A name matches only as a **whole token carrying a locative suffix** — `Mısır'dayım`,
  `Fas'ta`, `Çin'de` — the `_SUFFIX` / `_PLACE` patterns that file already defines.
  A bare `mısır` in a sentence never resolves to a country.
- A name of **four characters or fewer** (`Çin`, `Fas`, `Çad`, `Mali`, `Peru`, `Küba`)
  requires the strict suffix form, exactly `location.py`'s `_SHORT` / `_STRICT_SUFFIX`
  rule.

The plan pins one test per row of that table, in both directions: the crop sentence
must not resolve to a country, and the locative sentence must.

### One of the 199 "countries" is an aggregate

**[Found while writing this design, 2026-09-25.]** FAOSTAT area **351 `China`** sums
areas 41 `China, mainland`, 96 `Hong Kong SAR`, 128 `Macao SAR` and 214
`Taiwan Province of`. Its 2024 series agrees with mainland's within 1% on **94 of the
105 crops they share**.

It is the same class of thing as `Africa` and `European Union (27)`, which the world
layer deliberately dropped — it survived because that filter removed area codes
**≥ 5000** and this one is 351. A sweep comparing every pair of the 199 areas found
no second case.

**This round does not regenerate the data file for it.** An aggregate nothing resolves
to does no harm, and rebuilding a 4,38 MB artifact to remove one row would drag the
previous round's gates back open. Instead the alias table gives `Çin` and `China` to
**41**, gives 351 no names at all, and records what it is — so `extract_country` can
never return it. A test pins that. If a later round regenerates the world file for
another reason, dropping 351 belongs in it.

## 2. `NormValue` carries its unit, and `price_tl_kg` is renamed

**The field name is currently a lie waiting to happen.** `CropNorm.price_tl_kg` would
carry USD/kg the moment a French user asks. Renaming it is part of this work:

- `CropNorm.price_tl_kg` → **`CropNorm.price_per_kg`**. 54 references, all Python —
  **it does not cross the wire**, neither `src/main.py` nor `mobile-app/src/api.ts`
  mentions it, so no client or API contract changes.
- The JSON key `price_tl_kg` inside `data/crop_norms.json` **keeps its name.** That
  file is TÜİK only and its prices really are lira. Renaming it would be false in the
  other direction.

`NormValue` gains one field:

```python
unit: str        # "kg/da" | "TL/kg" | "USD/kg"
```

**Required, with no default.** A default of `"kg/da"` would let a price silently claim
to be a yield, and the failure this project keeps rediscovering is the statement that
is almost true. Thirty construction sites exist — one in `src/norms.py:207` and 29
positional ones across `tests/test_budget.py`, `tests/test_norms.py` and
`tests/test_budget_route.py` — and all are updated.

**No conversion.** USD is not turned into TL. Picking a rate is a product decision with
a date attached, and it belongs to the round that decides what a user sees.

## 3. Resolution order

```
lookup(crop, province, country=None) -> CropNorm | None
```

| Situation | Source | `scope` |
|---|---|---|
| A province resolved | TÜİK, that province | `"il"` |
| No province, country is Türkiye | TÜİK, national | `"tr"` |
| Country is not Türkiye | FAOSTAT, that country | `"ulke"` |
| Neither resolves | `None` | — |

**The national row is empty by construction, so the second line of that table serves nothing today.** Measured 2026-09-25: 553 measures in `data/crop_norms.json` carry a `"TR"` key and not one holds a value. `scripts/build_crop_norms.py` ships it that way deliberately — *"a mean of the provinces is a number nobody published"*. A Turkish user who has not named a province therefore receives nothing and the assistant asks them, which is what `location.py` already does for the same reason and yields better data than an average would. The row stays in the table because that is where a national figure would go if TÜİK ever published one; nobody should close the gap by averaging.

**The world layer never overrides TÜİK for Turkey.** FAOSTAT's Türkiye series is a
cross-check, not a source of answers — settled in the previous spec and unchanged here.
A Turkish user never receives a `"ulke"` figure.

The join runs through `crop_fao_map.json`: our crop id → FAO item code → the
`"<item>|<area>"` cell. A crop whose map entry is `null` has no world figure and
`lookup` returns `None` for that measure, with the reason already recorded in the map.

`province_table(province)` is untouched. It feeds the budget card's prefill, which is
the next round's problem.

## 4. The figure reaches the answer, and so does its flag

Country figures arrive in the prompt the way the province and the weather already do —
through `_context_block` and `_crop_choice_block`. Nothing new is invented for the
transport.

**The FAOSTAT flag travels into the sentence.** Measured on the shipped file, not the
raw archive: **29.842 of its 72.335 yield cells — 41,3% — are flagged `E`**, FAO's own
estimate rather than a country's report (57,1% are `A`, official, and 1,6% `X`). The
previous spec's 50,6% describes all 823.058 rows from 1961 on; the 2016+ window we
ship is cleaner than that, and quoting the wider figure here would overstate the
problem. A line that prints an `E` figure says so. The previous spec carried the flag into the file precisely so this decision could
be made here, and the project's standing rule — a number is printed with where it came
from, or not printed — leaves only one answer.

The one-year lag is stated the same way: FAOSTAT ends at 2024 where TÜİK reaches 2025,
so a world figure names its own year rather than implying a shared "latest".

## Global constraints

- **No conversion between currencies**, and no rate hard-coded anywhere.
- **A Turkish user's figures come from TÜİK.** Province beats national beats nothing;
  FAOSTAT never enters that chain.
- **`None` is a real answer.** An unresolved country, an unmapped crop and a missing
  cell all produce `None`, and the assistant asks rather than guessing.
- **No network access in any test.** Both data files are committed.
- **Deployment files are not touched:** `Dockerfile`, `docker-compose.yml`,
  `docker-entrypoint.sh`, `.github/workflows/docker-publish.yml`,
  `web-widget/Dockerfile`, `web-widget/docker-entrypoint.d/`, `mobile-app/eas.json`,
  `mobile-app/app.json`.
- **The API contract does not change.** No new request or response field; the country
  is read from the conversation.
- Commit messages: short, natural, English, no `Co-Authored-By` trailer.

## Out of scope

- **The budget and comparison cards.** They travel to the client through
  `province_table`, they need a client change to show a country figure, and the client
  is blocked behind a redeploy this project does not own.
- **Currency display and conversion.** We carry the unit; what a user sees is next.
- **A country field in the profile.** `location.py`'s docstring describes how it will
  slot in when membership work reaches it; nothing here forecloses it.
- **Alias languages beyond Turkish and English.** A data change when wanted.
