# A country-level world layer from FAOSTAT, beside the province-level TÜİK layer

Design, 2026-09-23.

## What exists now, and what it cannot answer

`data/crop_norms.json` carries 246 crops × 81 provinces of Turkish yield and
price, built offline from hand-exported TÜİK MEDAS files by
`scripts/build_crop_norms.py`. It is the only numeric layer in the project, and
it stops at the Turkish border.

The client's recorded requirement is "whole world, all products"
(`docs/client-requirements.md` §6). The answer given there — and still the
answer — is that what exists to be had is **country level worldwide, district
level for Turkey**. Nobody publishes sub-national yield for the world. This
design builds the country-level half.

## What FAOSTAT actually is

Measured 2026-09-23 against the live bulk endpoints, not estimated.

| Dataset | URL | Compressed | Uncompressed | Last-Modified |
|---|---|---|---|---|
| Production, crops & livestock, normalised | `https://bulks-faostat.fao.org/production/Production_Crops_Livestock_E_All_Data_(Normalized).zip` | 33,9 MB | **545 MB** | 2025-12-31 |
| Producer prices, normalised | `https://bulks-faostat.fao.org/production/Prices_E_All_Data_(Normalized).zip` | 11,7 MB | **214 MB** | 2026-01-09 |

**This corrects the record.** `docs/client-requirements.md` §6 records "43 MB"
for the pair, measured 2026-08-11 by `HEAD`. That is the *compressed* size. The
same two files unpack to **759 MB**. The conclusion drawn from the old figure —
that this is a download, not a data-collection project — survives the
correction; the figure itself does not, and gets fixed as part of this work.

### Shape

Both files are one normalised row per observation:

```
Area Code, Area Code (M49), Area, Item Code, Item Code (CPC), Item,
Element Code, Element, Year Code, Year, Unit, Value, Flag, Note
```

The production file holds 4.209.110 rows across 14 elements, of which we want
one: **element 5412, `Yield`, unit `kg/ha`** — 823.058 rows, 1961–2024.
The prices file holds 1.319.563 rows across four elements, of which we want
**element 5532, `Producer Price (USD/tonne)`** — 167.589 rows, 1991–2024.
Element 5530 is `LCU/tonne`, each country in its own currency, which cannot be
compared across countries and is therefore not carried.

### What has to be thrown away, and why

| Dropped | Count | Because |
|---|---|---|
| Regional aggregates (`Area Code` ≥ 5000) | 34 of 244 areas | `Africa`, `European Union (27)`, `World` are not places a grower farms |
| Item-group totals (codes 1717…17530) | 11 items | `Cereals, primary`, `Fruit Primary` are sums, not crops |
| `n.e.c.` residual buckets | 14 items | `Other vegetables, fresh n.e.c.` covers 177 countries — more than any real crop — but nobody plants it. A number attached to an unnamed mixture is not an answer. |
| Livestock | 13 of 14 production elements, **and every price row for a non-crop item** | Out of scope — see the rule below |
| Years before 2016 | 1961–2015 | TÜİK's window is 2016–2025; the two layers line up or they cannot be read side by side |

**The crop rule: an item enters the file only if it has a yield row.** This is
not a tidiness preference, it is a correctness requirement. The production
file's element 5412 is crops by construction — livestock yield lives under
5413/5417/5424 — but **the prices file has no such separation**: it prices meat,
eggs and milk alongside wheat. Building the item list from the union of both
files admits `Meat of pigeons and other birds n.e.c.` and `Eggs from other birds
in shell` into a crop layer. Taking the item list from yield and then looking up
prices for exactly those items is what keeps them out. A first measurement of
this design made that mistake and counted 194 items where there are 143.

What survives: **143 crop items** (136 of which also have a price),
**199 countries** with crop yield — out of 210 non-aggregate areas —
**72.335 yield cells** and **33.209 price cells**. Both run 2016–2024.
Türkiye is area code 223.

**Measured output size: 4,38 MB**, written with `indent=1` the way
`build_crop_norms.py` writes its own output. Compact separators give 2,28 MB,
but this file is committed and refreshed about once a year, and a 2 MB single
line makes that annual diff unreadable; 450.000 short lines diff properly.
Against `crop_norms.json`'s 2,7 MB, and the 1,3 GB vector store this project
already ships, the world layer is not a size problem either way.

### The one-year lag

TÜİK yield runs to **2025**. FAOSTAT yield and USD prices run to **2024**.
The newest world figure will always be at least one year behind the newest
Turkish figure. This is a property of the sources, and any surface that shows
both must show each one's year rather than implying a shared "latest".

### Half the world's yield figures are estimates

Every FAOSTAT row carries a flag:

| Flag | Meaning | Share of the 823.058 yield rows |
|---|---|---|
| `A` | Official figure | 393.637 (47,8%) |
| `E` | Estimated value | **416.182 (50,6%)** |
| `X` | Figure from external organization | 13.239 (1,6%) |

More than half of world yield is FAO's estimate, not a country's report. This
project does not print a number without being able to say where it came from —
the TÜİK builder refuses cells it cannot defend and records why. The world
layer cannot be the exception: **the flag travels with the value**, cell by
cell, into the output file. What a surface does with it is P2/P3's problem;
losing it here would make that decision impossible to make later.

## Keying: FAO item code

`data/world_norms.json` is keyed by **FAO item code**, not by our crop ids, and
a separate mapping file ties the two.

The decision was forced by the shape of the data. Our crop list is finer than
FAOSTAT's:

| Our crop ids | FAO item |
|---|---|
| `Durum Buğdayı`, `Buğday, Durum Buğdayı Hariç` | 15 `Wheat` |
| `Arpa (Biralık)`, `Arpa (Diğer)` | 44 `Barley` |
| `Lahana (Beyaz)`, `Lahana (Kırmızı)`, `Lahana (Kara Yaprak)` | 358 `Cabbages` |
| `Mercimek, Kuru (Kırmızı)`, `Mercimek, Kuru (Yeşil)` | 201 `Lentils, dry` |
| `Ayçiçeği Tohumu (Yağlık)`, `Ayçiçeği Tohumu (Çerezlik)` | 267 `Sunflower seed` |

The relation is **many-to-one**. Keying the world file by our crop ids would
have to either duplicate one FAO series under several keys — inviting a reader
to believe Turkey's beer barley has a distinct world yield when FAOSTAT knows
only "Barley" — or pick one key and silently drop the others. Keying by FAO
code stores each series once, under the identity its publisher gave it, and
makes the collapse explicit in a file a person can read.

It also means the file stays a faithful mirror of its source: re-downloading
and diffing is one step, and the 143 items include crops we do not grow, so
extending our crop list later adds a line to the mapping rather than requiring
a rebuild.

## Files

| File | Responsibility |
|---|---|
| `scripts/fetch_faostat.py` (new) | Download the two zips to a git-ignored cache. Record URL, `Last-Modified` and byte count for the output's `meta`. |
| `scripts/build_world_norms.py` (new) | Stream the two archives, apply the drops above, emit `data/world_norms.json`. |
| `data/crop_fao_map.json` (new) | Our 246 crop ids → FAO item code, or an explicit reason there is none. |
| `data/world_norms.json` (new, ~4,38 MB) | The output. Committed. |
| `tests/test_build_world_norms.py` (new) | The converter, against fixtures. |
| `tests/test_crop_fao_map.py` (new) | The mapping's completeness and referential integrity. |
| `docs/client-requirements.md` (modify) | Correct the 43 MB figure to compressed/uncompressed. |

The zips themselves are **not** committed. `data/raw/README.md` requires TÜİK's
inputs in the repo because they are hand-driven MEDAS exports that cannot be
reproduced from a URL — re-running that converter without them is impossible.
FAOSTAT's inputs are a fixed public URL, so the fetcher plus the recorded
`Last-Modified` and byte count in `meta` give the same auditability for 45,6 MB
less repository. That distinction is the reason, and it is written down here so
the next person does not read the omission as an oversight.

## Output shape

```json
{
  "meta": {
    "generated": "2026-09-23",
    "years": [2016, 2024],
    "units": {"yield": "kg/da", "price": "USD/kg"},
    "sources": [
      {"dataset": "Production_Crops_Livestock_E_All_Data_(Normalized)",
       "url": "https://bulks-faostat.fao.org/production/...",
       "last_modified": "Wed, 31 Dec 2025 11:33:28 GMT", "bytes": 33921825}
    ],
    "flags": {"A": "Official figure", "E": "Estimated value",
              "X": "Figure from external organization",
              "I": "Value imputed by a receiving agency",
              "B": "Time series break"},
    "dropped": {"area_aggregates": 34, "item_groups": 11, "nec_items": 14}
  },
  "items":     {"15": {"label": "Wheat", "cpc": "0111"}},
  "countries": {"223": {"label": "Türkiye", "m49": "792"}},
  "yield":     {"15|223": {"2024": [289.1, "A"]}},
  "price":     {"15|223": {"2024": [0.2841, "A"]}}
}
```

Two conversions, both applied in the builder so no reader has to remember them:

- **`kg/ha ÷ 10 = kg/da`** — FAOSTAT publishes per hectare, TÜİK and every
  surface in this project use dekar.
- **`USD/tonne ÷ 1000 = USD/kg`** — TÜİK prices are per kilogram.

Each cell is `[value, flag]`. A missing year is simply absent; there are no
null placeholders.

## The mapping, and how it is kept honest

`data/crop_fao_map.json` records a decision for **every one of our 246 crop
ids** — never a missing key:

```json
{
  "durum bugdayi":  {"fao": 15,   "note": "FAOSTAT does not split durum"},
  "kaplica":        {"fao": null, "reason": "no FAO item for emmer"},
  "tahillarin saman ve kabuklari": {"fao": null, "reason": "not a crop"}
}
```

A crop with no FAO counterpart is a fact about FAOSTAT, not a gap in our work,
and writing it as an explicit `reason` is the same discipline the TÜİK builder
already applies to the cells it refuses. Tests assert:

1. Every one of the 246 crop ids in `crop_norms.json` appears in the map.
2. Every non-null `fao` value exists in `world_norms.json`'s `items`.
3. Where several crop ids share one FAO code, that is allowed and asserted for
   the known cases above — so a later edit that accidentally splits them fails.

## Global constraints

- **The world layer never overrides TÜİK for Turkey.** Where province data
  exists it wins; the world figure for area 223 is a cross-check, not a source
  of answers. P2 decides how `norms.lookup` expresses that; this round must not
  make it impossible.
- **The granularity difference stays visible.** Country-level and
  province-level numbers are never presented as the same kind of thing.
- **Flags survive into the file.** Dropping them here would silently discard
  the fact that half the world's yield is estimated.
- **Deployment files are not touched** — `Dockerfile`, `docker-compose.yml`,
  `docker-entrypoint.sh`, `.github/workflows/docker-publish.yml`,
  `web-widget/Dockerfile`, `web-widget/docker-entrypoint.d/`,
  `mobile-app/eas.json`, `mobile-app/app.json`.
- **No network access in tests.** The converter is tested against small
  fixtures; the fetcher's download path is tested with a stubbed transport.

## Out of scope for this round

- **P2** — country resolution (how a user's country is determined) and
  `norms.lookup`'s country scope.
- **P3** — the budget and comparison surfaces, and the currency decision
  (USD/kg is what the file stores; what a user is shown is P3's problem).
- Anything that changes what an answer says. This round builds a file and the
  map that indexes it; no surface reads it yet.
