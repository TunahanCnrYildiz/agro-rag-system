# Client requirements and feasibility — living register

**Why this file exists.** Until 2026-08-11 the client's requirements lived only in
WhatsApp messages and in an assistant's working context. That context has already
been compacted once. A requirement nobody wrote down is a requirement that gets
re-derived, half-remembered, or quietly dropped — and the first sign of it here was
a design spec that deferred the client's central request without saying so.

**Status of this reconstruction.** Written on 2026-08-11 from the working record of
the session in which the WhatsApp screenshots were analysed, not from the screenshots
themselves. Items are marked:

- **[KAYIT]** — recorded in the session transcript, high confidence
- **[YENİDEN KURGU]** — reconstructed from a summary; **verify against the original
  messages before relying on it**
- **[ÖLÇÜLDÜ]** — independently measured in this repository, does not depend on memory

---

## 1. Who wants what

| Person | Role |
| --- | --- |
| **Hüseyin AĞAÇAYAK** | Assigned the project. Sets what it should do. |
| **Emirhan** | Deploys and operates it. Owns the deploy/Docker files. |

---

## 2. What Hüseyin asked for

**[KAYIT]** The central request, from his messages:

> Dünya geneli … veri topla dünya için … bölge bölge, ürün ürün … ondan bir RAG
> yap … son 5 yıl verisi

Broken into its parts:

| # | Request | Status |
| --- | --- | --- |
| R1 | Data covering the **whole world**, not only Turkey | **DATA BUILT 2026-09-25** (merge `25476be`) — `data/world_norms.json`, 143 crops × 199 countries. No answer surface reads it yet |
| R2 | Broken down **region by region** | **BUILT to the granularity that is published** — country level worldwide (199), province level for Turkey (81). Nobody publishes sub-national yield for the world |
| R3 | Broken down **product by product** | **BUILT, and smaller than asked** — FAOSTAT publishes yield for **143** crops worldwide, not "all products". Turkey keeps its 246. `data/crop_fao_map.json` ties the two |
| R4 | **Last 5 years** | **BUILT, exceeded** — world 2016–2024 (9 years), Turkey 2016–2025 (10). FAOSTAT always trails TÜİK by a year |
| R5 | "Make a RAG out of it" | **RESOLVED 2026-08-11** — a queryable table is accepted; see §4 and §6 |

**[KAYIT]** No deadline was given, but sooner is better.

**[KAYIT]** Membership and the KVKK/data-processing side will be handled by the
company, not by this project.

**[YENİDEN KURGU]** The request arrived after a screenshot of an earlier answer about
what the assistant could and could not do was sent to him. The exact prompting
context should be checked against the original thread.

---

## 3. What the data actually looks like

**[ÖLÇÜLDÜ]** during the feasibility pass:

| Source | Coverage | Granularity | Notes |
| --- | --- | --- | --- |
| **FAOSTAT** | Global | **Country level** | Production, area, yield. Roughly 50 MB for the whole set. Satisfies R1 and R4, but **not R2 below country level.** |
| **Tarım Bakanlığı / TÜİK** | Turkey only | **District level**, 1991→2025 | The only source found with real regional granularity. Satisfies R2 and R3 richly — for one country. |
| **World Bank Pink Sheet** | Global | Commodity level, monthly | Prices. |
| **Open-Meteo** | Global | Coordinates | Already integrated for the `fert_plan` route. Free for non-commercial use only; **a key must be budgeted before go-live.** |

**The tension this exposes, and it is not a technical detail.** R1 (whole world) and
R2 (region by region) pull in opposite directions given what exists publicly:
world-wide data is country-level; district-level data is Turkey-only. **No single
source satisfies both.** A decision is needed:

- **(a)** Turkey at district level, rest of the world at country level — honest, and
  the granularity difference has to be visible in the answers.
- **(b)** Country level everywhere — uniform, and much less useful for a Turkish
  grower, who is the actual user today.
- **(c)** Turkey first, world later — smallest, and defers R1.

**DECIDED 2026-08-11: option (a).** See §6. The granularity difference between
Turkey and the rest of the world must therefore be visible in any answer built on it.

---

## 4. Why "make a RAG out of it" is contested

**[KAYIT]** The developer's position, argued during the feasibility pass and not yet
put to Hüseyin in these terms:

RAG retrieves passages by semantic similarity and hands them to a model to read. That
is the right mechanism for **prose** — an agronomy paper explaining why potassium
matters at fruit set. It is the wrong mechanism for **numeric tables**:

- A number that is *retrieved* can be mis-transcribed by the model; a number that is
  *queried* cannot.
- "Manisa'da 2024 domates verimi" is a lookup with one correct answer, not a
  similarity search over documents.
- Aggregations — averages, trends, "last 5 years" — are arithmetic over rows. A
  retriever cannot do arithmetic, and this project has already decided (in the budget
  design) that **the model must never do arithmetic either**.

**The proposed answer to R5:** keep the RAG for the prose corpus that exists today,
and put the numbers in a **queryable table** that the assistant reads deterministically
— the same shape as the fertilization rule table and the weather lookup, both of which
already work this way. The user-visible result is what Hüseyin asked for ("the system
knows regional product data"); the mechanism underneath is a query, not a retrieval.

**AGREED 2026-08-11.** A queryable table is accepted as the answer to "bir RAG yap".
See §6.

---

## 5. Which spec covers which request

| Spec | Covers |
| --- | --- |
| `specs/2026-08-09-routing-and-context-design.md` | Intent routing; location, season, weather context; fertilization rule table. **Explicitly defers the numeric data layer.** |
| `specs/2026-08-11-budget-and-crop-choice-design.md` | The `budget` and `crop_choice` routes — the **consumers** of the numeric data. Computes only from numbers the user supplies. **Defers R1–R4 again.** |
| `specs/2026-08-17-numeric-data-layer-design.md` | The Turkish half of the numeric layer — TÜİK, 246 crops × 81 provinces. |
| `specs/2026-09-23-faostat-world-layer-design.md` | **The world half. R1–R4 land here.** Shipped 2026-09-25. |

**That headline is now spent.** It read, until 2026-09-25, as a warning that two
specs had been written around the client's central request without addressing it and
that R1–R4 had not moved since they were asked for. They have moved: the Turkish half
shipped on 2026-08-19 and the world half on 2026-09-25. What is still deferred is
narrower and should be named as such — **no answer surface reads the world layer
yet.** Country resolution, `norms.lookup`'s country scope, and the currency decision
for the budget and comparison surfaces are the remaining work.

---

## 6. Answers, 2026-08-11

Given by the developer on the client's behalf. **[KAYIT]**

| # | Question | Answer |
| --- | --- | --- |
| 1 | Granularity | **Whole world, all products.** Read from "tüm dünya". In practice this means option (a) of §3, because that is what exists: **country level worldwide, district level for Turkey.** |
| 2 | Mechanism | **A queryable table is accepted** as the answer to "bir RAG yap". |
| 3 | Which products | **All of them.** No priority subset. |
| 4 | What the number is for | **All three** — deciding what to plant, estimating income, and comparing regions. |

### The scale question, measured rather than estimated

The request sounds like a data-collection project. It is not; it is a download.

| Dataset | Compressed | Uncompressed |
| --- | --- | --- |
| Production — crops & livestock, normalised, all countries, all years | 33,9 MB | 545 MB |
| Producer prices, normalised | 11,7 MB | 214 MB |
| **Total** | **45,6 MB** | **759 MB** |

Re-measured 2026-09-23. The 2026-08-11 figures (32 MB / 11 MB / 43 MB) were the
**compressed** sizes, recorded without that word. The conclusion they supported —
that this is a download rather than a data-collection project — survives; the
figures did not, and only the download is 43 MB.

For comparison, this project already carries a **1.3 GB** vector store. The client's
"whole world, all products" dataset is roughly **one thirtieth** of what is already
being shipped to every deployment.

### Three expectations that need correcting, not three obstacles

1. **"Region by region" worldwide means COUNTRY level.** District granularity exists
   only for Turkey. This is a limit of what is published, not of effort.
2. **Statistics say what IS grown, not what CAN be grown.** They are a reasonable
   proxy, but soil, water and market access on the user's own field decide the
   answer. The data **informs** a planting decision; it does not make one. This is
   consistent with the `crop_choice` design already agreed, which explains factors
   and asks rather than recommending — the data will put numbers behind the factors,
   it will not change the shape of the answer.
3. **Producer prices are national annual averages.** A useful anchor; not a forecast
   of what a grower will be paid at market next month. Any income figure built on
   them must say so.

### Consequences for the table shape

Serving all three use cases from one table is workable **because they are the same
three columns read three ways**: (country|district, product, year) → (area, yield,
production, producer price). Crop choice reads it as "what does well here", income
reads it as "yield × price", region comparison reads it as "the same product across
places". The risk flagged when the question was asked — a schema that serves none of
them — is avoided by not adding a fourth reading later without revisiting the shape.

---

## 7. Standing constraints (not from Hüseyin, but binding)

- **[KAYIT]** The product acts **like** a ziraat mühendisi. It must never claim to
  **be** one. This binds README and About text as well as answers.
- Diagnosis and chemical prescription are out of scope.
- **[ÖLÇÜLDÜ]** `/api/chat` has no authentication and no rate limit, and
  `CORS_ALLOW_ORIGINS` is `*`. With any paid API key behind it, that is an open
  wallet. Not covered by `docs/deploy-runbook.md`. **Go-live blocker.**
- No agronomy reaches a user without review by a qualified agricultural engineer.
  The fertilization table ships empty for this reason.

---

## 8. Hüseyin's edited deck, accepted as the target — 2026-09-25

**[KAYIT]** On 2026-09-25 Hüseyin returned the project deck as a **16-page PDF he had
edited himself**, saying the project must match it exactly. The client side accepted
it as the target on the same day. **That PDF, not the 12-slide deck this project
generated, is now the requirement document.**

**[ÖLÇÜLDÜ]** Ten of its sixteen pages are this project's own slides, several
verbatim — the three-step flow, the three calculation cards, the dose and comparison
examples, the knowledge base counts, the catalogue, the four design rules, the
TÜRKİYE/DÜNYA numeric layer, the verification figures and the limits page. Six pages
are his: the commercial-benefit page, memory, the mobile season flow, language and
market, data protection, and a rewritten cover.

Every claim on the six new pages was checked against the code on 2026-09-25:

| Page | Claim | State |
| --- | --- | --- |
| 4 | Profile holds where the farmer is and what they grow, and the assistant recalls it each session | **Built.** `mobile-app/src/auth.tsx` carries `province` and `crops`; `app/(tabs)/chat.tsx` prepends them to every conversation |
| 12 | The profile can be viewed, corrected and deleted, and deletion clears it from the assistant | **Built.** `deleteProfile` plus a "Profili sil" confirmation in `app/profile.tsx`; the profile lives in device storage |
| 2, 10 | Commercial benefits; answers in the asker's language | **Built** as architecture. The corpus behind those answers is Turkish and English only — an Uzbek question is answered in Uzbek from TR/EN sources |
| 4 | *"kaç dönüm diye sormaz"* — field size is remembered | **NOT built.** The profile has no area field; each card asks for area again |
| 4 | *"Her sohbet profili biraz daha netleştirir"* | **NOT built.** The profile is user-edited; nothing refines it from conversation |
| 5 | **Fertilization and irrigation calendar, generated from the crop's phenological stages and shifted by the weather** | **NOT built — see below** |
| 15 | "1.050 otomatik test" | Stale; 1.096 as of 2026-09-25 |

### The season calendar is a data-review task, not a programming task

**[ÖLÇÜLDÜ]** The scaffolding exists and the data does not:

- `src/router.py` already routes calendar questions — `_TIME_STEMS` contains
  `"takvim"` and `"program"` — to the `fert_plan` route.
- `src/engine.py` already gives that route the province, the season and the
  coming week's weather.
- `data/fertplan_table.json` **contains no rows.** `fertplan.available_crops()`
  returns an empty tuple today.
- The table's own README states the position: *"The assembly step that would turn
  rows into a fertilization calendar is not written,"* and *"A row without
  `reviewed_by` is dropped at load time, so unreviewed agronomy cannot reach a
  user even if someone adds it here."*

**This is deliberate and it is the binding constraint.** Per §7, the product must
never present unreviewed agronomy. A per-crop, per-stage fertilization and
irrigation programme is exactly the kind of advice this project refuses to invent.
Filling that table requires a **named agricultural engineer** to review each row and
sign it in `reviewed_by` — the schema drops anything unsigned.

So page 5 cannot be delivered by writing code. It needs, from the client:

1. a fertilization and irrigation table per crop and per phenological stage, and
2. an agricultural engineer who will put their name and title to it.

Until both arrive, the assembly step is the smaller half of the work and is blocked
behind them.

### Decision taken

**[KAYIT]** The client side chose to accept the PDF as it stands rather than correct
it or build page 5 first. Page 5 is **not** labelled as a future step on any
customer-facing slide — an earlier instruction was explicit that "sıradaki adım"
notes confuse the reader and do not belong in the deck. It is recorded here instead.

### Two documents have now diverged

**[ÖLÇÜLDÜ]** The generated deck artifact still holds 12 slides and does not contain
Hüseyin's six pages. Anyone regenerating the PDF from it would silently drop them.
Whoever next touches the presentation must start from Hüseyin's file, not from the
artifact, or reconcile the two first.
