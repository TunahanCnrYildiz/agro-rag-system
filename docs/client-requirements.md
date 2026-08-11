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
| R1 | Data covering the **whole world**, not only Turkey | **Not started** — scoped 2026-08-11, see §6 |
| R2 | Broken down **region by region** | **Not started** — country level worldwide, district level for Turkey |
| R3 | Broken down **product by product** | **Not started** — all products, no subset |
| R4 | **Last 5 years** | **Not started** — the bulk sets carry the full series |
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
| *(not written)* | **The numeric data layer itself. R1, R2, R3, R4 and the R5 mechanism all live here, and none of it is designed yet.** |

**Read that last row as the headline.** Two specs have now been written around the
client's central request without addressing it. Each deferral was individually
defensible — the routing work had to come first, and the budget route genuinely does
not need the data to be useful — but the cumulative effect is that R1–R4 have not
moved since they were asked for.

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
Measured 2026-08-11 by `HEAD` against the FAOSTAT bulk endpoints: **[ÖLÇÜLDÜ]**

| Dataset | Size |
| --- | --- |
| Production — crops & livestock, normalised, all countries, all years | **32 MB** |
| Producer prices, normalised | **11 MB** |
| **Total** | **43 MB** |

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
