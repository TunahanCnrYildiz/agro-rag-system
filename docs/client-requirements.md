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
| R1 | Data covering the **whole world**, not only Turkey | **Not started** |
| R2 | Broken down **region by region** | **Not started** |
| R3 | Broken down **product by product** | **Not started** |
| R4 | **Last 5 years** | **Not started** |
| R5 | "Make a RAG out of it" | **Contested — see §4** |

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

**This decision has not been made.** It belongs to Hüseyin, not to the developer.

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

**This has not been agreed with him.** It should be, before the data layer is built,
because it changes what "yap bir RAG" means in the delivery.

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

## 6. Open questions for Hüseyin

1. **Granularity:** option (a), (b) or (c) from §3?
2. **Mechanism:** is a queryable numeric table acceptable as the answer to "bir RAG
   yap", given §4?
3. **Which products?** "Ürün ürün" over FAOSTAT's full list is hundreds of crops.
   Is there a priority set — what the company actually sells into?
4. **What is the number for?** Deciding what to plant, estimating income, or
   comparing regions? Each implies a different table shape, and building for all
   three at once is how the schema ends up serving none of them.

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
