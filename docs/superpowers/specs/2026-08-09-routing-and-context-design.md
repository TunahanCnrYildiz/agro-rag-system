# Query routing and context collection — design

Status: proposed
Date: 2026-08-09

Every query currently takes one path: embed → vector search → product match →
prompt → answer. A budget question ("5 dönüm domates ektim, ne kadar kâr
ederim?") pays for a corpus search that cannot hold its answer, then gets
refused because farm economics is out of scope. A fertilization-timing question
gets a generic answer because the system never learns where the user is or what
month it is.

This spec adds a routing step in front of the pipeline, three deterministic
context sources (location, season, weather), a reviewable fertilization rule
table, and a budget route. It does not change the corpus path.

---

## 1. Purpose & success criteria

**Purpose.** Make the assistant's answer depend on the question's *kind* and on
the user's *situation*, not only on the corpus.

**Success criteria.**

1. A fertilization-timing question, once the user has given a province, produces
   an answer that reflects that province, the current season, and the coming
   week's weather.
2. A budget question is answered rather than refused: the assistant asks for the
   numbers it lacks and computes with the numbers it is given.
3. A crop-choice question ("bu yıl ne ekeyim") gets an answer about the factors
   that decide it, not a generic fertilization passage.
4. For a supported crop, the assistant can produce a fertilization plan whose
   every line traces to a reviewed rule-table entry.
5. None of the 55 existing eval cases changes verdict.

Criterion 5 is the hard one. The corpus path works and is measured; this spec
adds paths beside it, never through it.

---

## 2. Scope

**In scope**

- Intent routing (hybrid: deterministic rules first, one small model call when
  the rules are undecided)
- Location extraction from conversation history (no session, no database)
- Season derivation from date
- Weather retrieval for the coming week
- Fertilization rule table + plan generation for a small, reviewed crop set
- Budget route: ask for missing inputs, compute from given inputs

**Out of scope — each gets its own spec**

- Numeric data layer (FAOSTAT, TÜİK) that would supply yield and price defaults
- Membership, user profiles, persistent memory
- Device GPS / IP geolocation
- Moving the vector store to object storage

**Deliberately unchanged**

- The `[OFFSCOPE]` / `[NOPRODUCT]` marker mechanism and the product-suppression
  backstop. Both are measured and working. Routing sits in front of them; it
  does not replace them.

---

## 3. Architecture

```
query + history
      │
 [1]  router.classify()        rules first; one small model call if undecided;
      │                        falls back to today's behaviour on any failure
      ▼  route
 [2]  route-specific context collection
      │
      ▼
 [3]  build prompt → model → answer
      │
      ▼
 [4]  EXISTING gates: marker stripping, product suppression, empty-answer
      guard, stream-truncation recovery — unchanged
```

New code lives outside `src/engine.py`, which is already 852 lines and carries
four responsibilities. Adding six more would make it unworkable.

```
src/router.py          intent decision
src/context/
    location.py        province extraction + static coordinate table
    season.py          date → season
    weather.py         Open-Meteo client, cache, timeout
src/fertplan.py        rule-table lookup + plan assembly
src/budget.py          arithmetic + assumption reporting
src/engine.py          existing corpus path (untouched) + route dispatch
```

---

## 4. Routes

| Route | Trigger | Context collected | Change |
| --- | --- | --- | --- |
| `plant_info` | pruning, disease, propagation, physiology | corpus | none |
| `nutrition` | general fertilization question | corpus + product match | none |
| `fert_plan` | timing or programme request | location, season, weather, corpus, rule table | new |
| `budget` | cost, profit, expense | user-supplied numbers | new |
| `crop_choice` | "what should I plant" | location, season | new |
| `offscope` | obviously non-plant | — | short-circuit only |

`plant_info` and `nutrition` reproduce today's behaviour exactly. Most traffic
lands there and sees no change beyond not paying for work it does not need.

`offscope` is a **short-circuit, not a replacement**. The router catches obvious
non-plant queries cheaply; the model's `[OFFSCOPE]` marker remains the backstop
for everything the rules miss. Deterministic rule plus model marker, the pattern
this project already uses for product suppression.

---

## 5. Components

### 5.1 `router.py`

```python
Route = Literal["plant_info","nutrition","fert_plan","budget","crop_choice","offscope"]
def classify(message: str, history: list[dict] | None) -> tuple[Route, str]
```

Returns the route and how it was decided (`"rule"`, `"model"`, `"default"`).

Rule layer, ordered specific-to-general:

- `budget` — kâr, maliyet, masraf, gelir, gider, bütçe, "kaç para", "ne kadar tutar"
- `fert_plan` — a nutrition stem (gübre, besle, azot, fosfor, potasyum) **and** a
  time stem (ne zaman, takvim, program, dönem, ay) in the same message
- `crop_choice` — "ne ek…", "hangi ürün", "ne yetiştir…" together with a
  this-season marker
- `offscope` — obvious non-plant stems

Stems are matched with the existing `_normalize_tr` fold and left-boundary rule,
so Turkish suffixes are handled the same way the crop lexicon handles them.

When no rule fires, one classification call runs. It uses the **configured chat
provider and model** — the same `ChatProfile` the answer path uses, not a second
model. Introducing a separate model would add a second provider-portability
surface to a system that already measured one such surface breaking.

The call asks for one label and nothing else, with a low token cap. If it fails,
times out, or returns anything outside the six labels, the route defaults to
today's behaviour. **The router cannot break the system; it can only switch
itself off.**

### 5.2 `context/location.py`

Extracts a Turkish province from the current message and the conversation
history, most recent mention winning. Backed by a static table of the 81
provinces and their coordinates — no geocoding call, so lookup is free,
instant, and works offline.

**Districts are out of scope for this version.** The table holds the 81
provinces only. A user who writes "Bafra" is not matched; the assistant asks for
the province. Province granularity is sufficient for both weather and
fertilization timing, and a district table is a data-entry job that can be added
later without changing any interface.

Nothing is stored server-side. Location is re-derived from `history` on every
request, which is why this spec needs no session, database, or user record. When
membership arrives, a profile value simply becomes the default before this
extraction runs.

### 5.3 `context/season.py`

Date → season and month, northern hemisphere. Deterministic.

Phenological stage is **not** derivable from the date: the same day can be
seedling stage or fruit set. The assistant asks for it. This is the "filiz mi
açtı diye sorar" step.

### 5.4 `context/weather.py`

Open-Meteo forecast for the province coordinates. Three agronomically useful
figures: precipitation in the coming days, frost risk, temperature range.

- 2-second timeout
- In-memory cache keyed by province and date
- Called only on `fert_plan` and `crop_choice`

Open-Meteo requires no key for non-commercial use but **does require one for
commercial use**. This is a live product, so a key must be budgeted before
go-live.

### 5.5 `fertplan.py`

The rule table is a **data file, not code**: crop × phenological stage →
nutrient emphasis, timing note, caution, corpus citation. Keeping it as data
makes it reviewable and diffable on its own.

Proposed starting crops, each chosen because the project already has evidence
for it: **tomato** (recurring example, in the eval set), **wheat** (eval set,
Turkey's largest crop), **olive** (eval set), **hazelnut** (lexicon work,
Black Sea region), **grapevine** (lexicon and pruning cases).

**Agronomic review gate.** Neither the author of this spec nor the developer is
an agricultural engineer. The table's correctness cannot be established by
testing — only by review. Therefore:

> A crop that has not passed agronomic review does not stay in the table. No
> plan is generated for it; the assistant says so plainly.

Shipping with three reviewed crops is correct. Shipping five unreviewed ones is
not.

### 5.6 `budget.py`

Inputs: area, crop, yield, sale price, total cost. Missing values are **asked
for, never invented**. With all values present it computes revenue and margin
and reports the values it used.

For "5 dönüm domates ektim 1M masraf ettim": area, crop and cost are given;
yield and price are missing, so it asks for those two.

When the numeric data layer lands, yield and price arrive as defaults from the
database instead of being asked for. The route does not change.

---

## 6. Degradation

Every new path degrades to today's behaviour, never to an error.

| Failure | Behaviour | What the user sees |
| --- | --- | --- |
| Router undecided and model call fails | today's path | today's answer |
| Weather unreachable or slow | continue without it | answer + "could not reach weather" |
| No location found | generic answer + question | answer + "which province?" |
| Phenological stage unknown | stage-free general guidance + question | answer + "what stage is it in?" |
| Crop absent from table | no plan generated | general nutrition answer + plain statement |
| Budget inputs missing | no calculation | the missing values are requested |
| Model unavailable | existing fallback | today's behaviour |

Latency: weather is the only new external call, it is capped and cached, and it
fires on two routes out of six. The router's model layer fires only when the
rules are undecided. Added latency on the majority of traffic is zero.

---

## 7. Safety and framing

The two absolute rules are unchanged: no definitive disease diagnosis, no
chemical recommendations. The identity rule is unchanged: the assistant never
presents itself as a licensed professional, including when it produces a plan.

Plan and budget outputs additionally carry a **framing sentence** stating the
assumptions they rest on and that the result is an estimate. This sentence is
**appended by code, not requested in the prompt**, so no model can omit it. It
is the line between advice and prescription, and it must not depend on model
compliance.

---

## 8. Testing and measurement

Almost all new code is deterministic and testable without an LLM or a network:

| Component | Test | Needs LLM |
| --- | --- | --- |
| `season.py` | date → season, boundary days | no |
| `location.py` | inflected forms; and forms that must NOT match | no |
| `weather.py` | stubbed HTTP; timeout and failure paths | no |
| `budget.py` | arithmetic, missing-value behaviour | no |
| `fertplan.py` | lookup, absent crop | no |
| `router.py` rules | labelled query set | no |
| `router.py` model layer | eval run | yes |

Two measurement sets:

1. **Routing set (new).** ~40 queries across the six routes, `query → expected
   route`. **Authored and frozen before implementation**, so the test cannot be
   shaped by what the code happens to do.
2. **The existing 55 cases,** unchanged, as the regression shield.

The routing set is added to the eval harness as a dimension. It scores in
`--fast` mode without an LLM, because the rule layer is deterministic.

---

## 9. Exit gates (pre-registered)

Written before measuring, so the outcome cannot be reinterpreted afterwards.

- **Any regression in the existing 55 cases → do not ship.** Hard gate.
- **Every existing nutrition and plant-information case must route to today's
  path.** If not, the router is too aggressive.
- **Routing accuracy ≥ 90% on the frozen set.** Below that the router does not
  ship and the rules are revised.
- **The model layer must fire on ≤ 30% of queries.** Above that the rules are
  too weak: the hybrid design's whole benefit rests on most queries being
  resolved for free, and that assumption must be measured rather than assumed.
- **No crop ships in the rule table without agronomic review.**

---

## 10. Follow-up specs

In the order they become useful:

1. **Numeric data layer** — FAOSTAT (country level, ~50 MB across production,
   producer prices and fertiliser datasets) and Tarım Bakanlığı / TÜİK
   (district level, 1991→2025) into a queryable table, exposed to the `budget`
   and `crop_choice` routes. Deliberately a database with exact lookup, not a
   vector store: the data is numeric, and semantic search over numbers returns
   approximate matches that cannot be verified.
2. **Membership, profile and memory** — makes location and crop persistent
   instead of re-derived per request.
3. **Calendar expansion** — more crops, as agronomic review capacity allows.
