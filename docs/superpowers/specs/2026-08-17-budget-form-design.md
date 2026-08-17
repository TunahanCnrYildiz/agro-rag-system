# Budget route, option C: numbers come from a form

Status: proposed
Date: 2026-08-17
Supersedes: the budget half of `2026-08-11-budget-and-crop-choice-design.md`

The first budget attempt read the numbers out of Turkish prose. Its review found
**five Criticals, every one a demonstrated wrong money figure** — `"5 dönümde 2 ton
aldım, kilosu 10 TL, masrafım 5000 TL"` produced a margin of 95,000 instead of
15,000, and `"Kilosunu 12,5 TL, masrafım 20000 TL"` read the cost as 12.5. Three
rounds of patching hand-curated Turkish token sets each opened new holes, because
the approach — inferring which number in a sentence belongs to which slot — cannot
survive Turkish inflection. The work was stopped by decision, not by a failing test.

This spec replaces the approach. The numbers come from a small form, so nothing is
inferred. `src/budget.py` is written fresh from `main`; the extraction module on
`budget-and-crop-choice` stays on that branch as a record and is not merged.

---

## 1. Purpose & success criteria

Answer a farmer's money question with arithmetic that is correct by construction,
and never show a figure the system computed from a guess.

1. A budget question opens a form; a submitted form produces revenue, cost and
   margin computed in Python from the user's own values.
2. No wrong money figure is possible from misreading the question, because the
   question is not read for numbers at all.
3. A unit is never inferred. Where two units are plausible the form makes it a
   selection.
4. The route makes no model call and no corpus retrieval, so its correctness is
   established entirely by `pytest`.
5. An already-deployed client that does not know about forms does not break.

## 2. Scope

**In scope**

- A four-input form (area, total harvest, price, cost) surfaced as a card inside
  the chat
- Revenue / cost / margin / margin-percent arithmetic in Python
- Code-written Turkish rendering, including a framing sentence
- API contract additions on request, response, and the SSE stream
- The mobile client card

**Out of scope — each has its own place in the sequence**

- P2 — the numeric data layer (TÜİK/FAOSTAT yield and price norms). This spec is
  built so P2 prefills the same form rather than replacing it; see §12.
- P3 — computing a fertilizer quantity for the user's field
- P4 — `crop_choice` naming a crop from historical series
- Payback period / establishment investment. Decided out: it needs a fifth input
  and a different question shape. `"Bu yatırımın geri dönüşü ne kadar sürer?"`
  takes the ordinary path and gets the ordinary result. It is **not** given a
  special sentence: detecting that one question would be a branch, and §4 keeps
  the route branch-free on purpose. The framing sentence already states what the
  figure is — revenue, cost and margin from the user's own numbers — so a payback
  question visibly does not receive a payback answer.

**Deliberately unchanged**

- The router. `budget` already has **zero false entries** in the frozen 42-case
  routing set (all five current misses land in `plant_info`), which is the
  property that makes it safe for this route to diverge. No rule is added.
  In particular the `gelir` stem stays OUT: it was removed because it means
  "comes into fruit" in Turkish and pulled plant questions into `budget`. The
  cost is that `"Zeytinlikten yıllık ne kadar gelir beklerim?"` does not reach
  this route and gets an ordinary corpus answer. That is a paid trade, not a bug.
- The `[OFFSCOPE]` / `[NOPRODUCT]` markers, product suppression, the corpus path.

## 3. Why a form, and what a form does not fix

Two arguments, and the second is the one that is easy to miss.

**It removes the guess.** Parsing asks "which number in this sentence is the
cost?". A form does not ask that question, so it cannot answer it wrongly. Two of
the five Criticals become structurally impossible rather than guarded.

**It makes the unit a selection instead of an inference — but only if it is
designed to.** A form that asks for "yield per dekar" relocates the defect rather
than removing it. A farmer who harvested 2 tons from 5 dönüm holds *"2 ton"* in
mind, not *"400 kg/da"*. Given a field labelled "dekara verim (kg)" they will type
2000, and the result is 100,000 TL instead of 20,000 — five times too high, and
silent, because the number is sitting in a field they filled themselves.

Therefore: **the form asks for the TOTAL harvest with a kg/ton selector**, and
derives the per-dekar figure itself. The farmer's own words are the input. This
single decision closes the ton/kg confusion and the total/per-area confusion at
once. Area and price get the same treatment.

## 4. Architecture & flow

```
Turn 1  message ──► router ──► "budget"
                                 │
                                 ├─ no retrieval, no product match, no LLM
                                 └─► answer: one code-written sentence
                                     form:   FIELDS, serialised

Turn 2  message (unchanged) + budget{…} ──► validate ──► compute ──► render
                                                │
                                                └─ errors ──► form + field errors
```

The budget route short-circuits **before** retrieval. This is the spec that
opened the routing work restating its own opening line: a budget question was
paying for a corpus search that cannot hold its answer.

**Turn 2 does not depend on the router.** If a complete `budget` payload arrives,
the server computes, whatever the route says. The second turn does not bet on the
router a second time.

`message` on turn 2 carries the **original question**, so history stays coherent
and readable. The client renders the submitted values as the user's bubble, not a
duplicate of the question.

**One behaviour, no branches.** All seven frozen budget questions take this path —
the four the calculator answers and the three that want a market norm. The three
norm questions are not a separate refusal path; the sentence that opens the form
is the same sentence. When P2 lands, the only change is that fields arrive filled.

## 5. API contract

Three additions, all optional, all backward compatible:

```
ChatRequest    + budget: BudgetPayload | None
ChatResponse   + form:   FormSpec | None
SSE            + {"type": "form", "form": {…}}
```

The SSE protocol is already typed (`token` / `products` / `done`), so a client
that switches on `type` ignores an unknown one. **This is a binding constraint,
not a nicety:** the APK currently deployed does not know about forms. It must
still receive the `token` sentence and `done` and behave sanely. The sentence is
therefore written to stand on its own — an honest answer, not a caption for a
widget the old client cannot draw.

**Field-level source.** Every field carries a value *and* where it came from:
`user` / `norm` / `empty`. Nothing sets `norm` in P1. It exists so P2 prefills
without changing the wire format, the card, or the arithmetic.

## 6. Components

```
src/budget.py     FIELDS, parsing, validation, arithmetic, rendering, FRAMING
src/engine.py     one short-circuit on route == "budget", in BOTH entry points
src/main.py       request/response models, SSE form event
mobile-app/src/BudgetCard.tsx    the card
```

`src/budget.py` public surface:

```python
FIELDS: tuple[FieldSpec, ...]
parse_tr_number(text: str) -> float | None
validate(raw: dict) -> tuple[BudgetInputs | None, list[FieldError]]
compute(inputs: BudgetInputs) -> BudgetResult
render(inputs: BudgetInputs, result: BudgetResult) -> str
FRAMING: str
```

**`FIELDS` is the single source of truth.** The form the client draws and the
validation the server runs are serialised from the same tuple. Without this they
drift: the client stops marking a field required, the server keeps rejecting it,
and the user sees an error with no cause.

**`budget.py` imports nothing from `engine.py`.** The branch version imported
`_normalize_tr` to tokenise; with no text parsing that dependency is gone. The
module is values in, text out, and is testable with no store and no model.

**`engine.py` stays thin.** It is already past 1,000 lines with four
responsibilities. It gets a branch, not logic.

**Client persistence.** The chat is persisted across restarts. A *submitted* form
renders in history as a static summary of the values and the result. An
unsubmitted card is not persisted as an interactive form — reopening the app must
not present a live form attached to a stale turn.

## 7. Arithmetic & units

```
area_da     = area  × (1 | 10)          # dönüm|dekar → 1, hektar → 10
yield_kg    = total × (1 | 1000)        # kg → 1, ton → 1000
price_tl_kg = price × (1 | 0.001)       # TL/kg → 1, TL/ton → 0.001
revenue     = yield_kg × price_tl_kg
margin      = revenue − cost_tl
margin_pct  = margin / revenue × 100    # only when revenue > 0
```

Three of the four inputs carry a unit selector, for the reason in §3. Cost does
not: it is a plain TL total and has no second plausible unit.

Conversion happens once, at the boundary. Inside the module there is one unit
system: dekar, kg, TL/kg, TL.

Worked example, the Critical that named this spec: 5 dönüm, 2 ton total, 10 TL/kg,
5,000 TL cost → 2,000 kg × 10 = 20,000 revenue → **margin 15,000 TL** (the old
extractor said 95,000). The per-dekar figure, 400 kg/da, is derived and shown back.

## 8. Validation

| Field | Required | Unit | Rule |
| --- | --- | --- | --- |
| Area | yes | dönüm / hektar | `> 0`. Zero dönüm is an error, not a calculation |
| Total harvest | yes | kg / ton | `>= 0`. Zero is valid — a total crop loss is a real answer: revenue 0, margin = −cost |
| Price | yes | TL/kg / TL/ton | `>= 0` |
| Cost | **no** | TL | `>= 0` when given. Omitted → revenue reported, margin not computed |
| Crop | no | — | Selected, offered from the stored profile. **Never extracted from the message** |

A unit selector always has a default, and the default is the common case
(dönüm, kg, TL/kg). An absent or unrecognised unit is a field error, never a
silent fallback — silently assuming a unit is the inference this design exists to
remove.

**Cost is optional on purpose.** It makes `"Zeytinlikten yıllık ne kadar gelir
beklerim?"` answerable without demanding a number the question did not ask about.

**No upper bound.** A cap would be arbitrary and would reject a legitimate large
holding. The protection that replaces it is in §9.

**`parse_tr_number` is the only parsing that survives**, and it reads one field's
contents, never a sentence. `"12,5"` → 12.5, `"1.250"` → 1250, `"1.250,75"` →
1250.75. `"1.5"` is **refused**: it is ambiguous between 1,5 and a malformed
thousands group, and a visible field error is the right direction to fail. The
message says to use a comma for decimals.

## 9. Rendering & framing

The template restates its inputs before it states its result:

> Girdiğiniz değerlere göre: **5 dönüm**, toplam **2 ton** (dekara 400 kg),
> kilogram fiyatı **10,00 TL**, masraf **5.000,00 TL**.
> Gelir **20.000,00 TL** · Masraf **5.000,00 TL** · **Marj 15.000,00 TL** (kâr marjı %75)

This is what replaces an upper bound. A user who meant 5 and typed 5000 reads
"5.000 dönüm" in the first line, and a wrong unit selection shows up in the
derived per-dekar figure.

`FRAMING` is appended **by code and never asked of the model**, the same pattern
as `fertplan.FRAMING`: this is an estimate, it rests entirely on the figures you
supplied, and it is not a price or yield forecast.

Numbers are formatted Turkish — thousands dot, decimal comma. A small formatter
is written and tested rather than trusting a locale library.

## 10. Error handling

- **Field errors belong to fields.** Non-numeric, negative, zero area, missing
  required → the form comes back carrying per-field errors. There is no "hatalı
  giriş" chat sentence.
- **The server validates independently of the client.** Client-side checks are a
  convenience; the server's are the contract.
- **Loose types at the wire, strict validation inside.** The payload accepts
  strings, because a text input produces strings, and `validate()` does the real
  work. A bad value becomes a field error, not a 422 mid-conversation. Only a
  structurally wrong body (not an object) is a 422 — that is a genuine client bug
  and must stay loud.
- **If `compute` raises, the route goes silent, it does not guess.** There is no
  fallback to the model path: an LLM answer about money is precisely what this
  spec removes. A code-written sentence is returned with no figures.
- **Revenue 0 omits the percentage line** rather than printing `%0` or infinity.
- **An old client** ignores the `form` event and still receives `token` + `done`.

## 11. Testing

Everything is `pytest`. No LM Studio, no vector store, no eval run.

| Group | What it pins |
| --- | --- |
| Arithmetic | Each of the five review Criticals as a regression case with the corrected expectation; the 5 dönüm / 2 ton case; hektar→dekar; ton→kg; TL/ton→TL/kg; zero yield; cost omitted → revenue only; revenue 0 → no percentage |
| Units | Each selector converts in both settings; an absent or unrecognised unit is a field error, never a silent default |
| `parse_tr_number` | `12,5`, `1.250`, `1.250,75` accepted; `1.5`, `abc`, empty, `12,5,3` refused |
| Validation | Every rule in both directions; the error names its field |
| `FIELDS` is single-source | The serialised form spec covers exactly the fields `validate()` knows |
| Rendering | Turkish number format; the restated-inputs line; `FRAMING` always present and code-appended |
| API contract | No inputs → `form`, no products, non-empty sentence · complete inputs → result, no `form` · invalid inputs → `form` + field errors |
| **Stream parity** | The same question through `stream=True` and `stream=False` yields the same text and the same `form` payload |
| Short-circuit | On route `budget`, `retrieve_context` and the chat client are **never called** |
| Old client | A consumer that skips unknown SSE types still receives `token` + `done` |
| Routing property | `budget` still takes **zero false entries** in the frozen routing set |

**Stream parity is the load-bearing test.** This project has already paid for
exactly this mistake once: `stream_answer()` did not route while **both clients
streamed**, so the router ran on zero production traffic and the eval shield
exercised `answer()` — the path users never hit. Wiring the form into `answer()`
and forgetting `stream_answer()` is the same defect waiting in the same place.

**The routing-property test converts a measurement into a guard.** The whole
design rests on no unrelated question reaching `budget`. If a future router rule
breaks that, this fails loudly instead of a form card appearing under a question
about leaf spot.

### The eval is untouched, deliberately

The 59-case shield does not cover this route: there are no budget cases and the
route makes no model call. **No eval run is required for this work** and the
shield's meaning is unchanged.

No eval case is added either. An eval measures the model; this route has no
model, so any case added here would read green while asserting nothing — the
**vacuity class** this project has already shipped once (`retrieval:"any"` made
`_retrieval_ok` unconditionally true; an unused `answer_none` passed through
`all([])`). The question for every new check stays: *what fails if this claim is
false?*

## 12. Forward compatibility with P2

P2 supplies yield and price norms per province and crop. It does **not** replace
this form; it prefills it.

- The `source` field on each input flips from `empty` to `norm`.
- The card shows the prefilled value as an assumption the user can overwrite.
- The arithmetic, the rendering, the validation and the wire format do not change.
- The three norm questions stop needing the user to supply anything, without any
  new path — which is why §4 gives the route a single behaviour and why the
  opening sentence is worded "give me the figure and I will compute it" rather
  than "I have no market data".

## 13. Sequence this belongs to

| | | Depends on | Blocked by |
| --- | --- | --- | --- |
| **P1** | This spec — the calculator | — | — |
| P2 | Numeric data layer (yield/price norms, historical series) | — | confirming the source is actually obtainable |
| P3 | Fertilizer quantity for the user's field | P1 | see below |
| P4 | `crop_choice` naming a crop from history | P2 | reverses a shipped, deliberate decision |

**On P3, recorded here so it is not re-derived.** Stating a dose is *not* blocked —
the system already answers "dekara kaç kg saf azot?" with `16 kg/da` grounded in
dp_21735, and that is a green eval case. Arithmetic on top of a dose that came
from somewhere else (dose × area; elemental N → product mass via the label
percentage) is multiplication, and the judgement lives in the dose, not the
multiplication. What stays gated is **us authoring an unconditioned dose for this
user's field** as our own assertion — which is what the `fert_plan` table is, and
why a row without `reviewed_by` is dropped at load.

A separate and more concrete obstacle was measured on 2026-08-17: the product
catalog carries **no application rate and no guaranteed analysis** — 0 of 48
products mention dekar/dönüm, 0 carry a numeric dose, 0 carry an NPK triple, and
descriptions average 143 characters of marketing copy. The catalog is liquid
foliar and micronutrient products, not bulk urea sold by the dekar. So "how many
litres of this product for 5 dönüm" cannot be computed from what we hold at any
level of review. That is a catalog data gap, not a review problem; all 48
`source_url`s are on hand and `src/scraper.py` exists. Whether the product pages
carry a "Kullanım Şekli / Dozu" section is the first thing P3 must check.
