# Budget and crop-choice routes — design

Supersedes nothing. Extends `docs/superpowers/specs/2026-08-09-routing-and-context-design.md`,
which designed six routes and left `budget` and `crop_choice` on the corpus path
deliberately. This spec makes those two diverge.

It does **not** build the numeric data layer. That was out of scope in the
routing spec ("each gets its own spec") and stays out of scope here.

---

## 1. Purpose & success criteria

**Purpose.** Answer the two question kinds the assistant currently handles by
falling through to a corpus search that cannot hold their answers: what something
costs or earns, and what to plant.

**Success criteria.**

1. A budget question with all four inputs present produces a revenue and margin
   figure **computed in Python**, not by the model.
2. A budget question with inputs missing names the cost items that decide the
   answer and asks for exactly the missing values. It never invents one.
3. A crop-choice question produces the factors that decide the choice and asks
   for the ones it does not know. It does not name a crop as a recommendation.
4. `budget` and `crop_choice` still have **zero wrong entries** in the frozen
   42-case routing set at the moment they are given divergent behaviour.
5. None of the 58 existing eval cases changes verdict.
6. Both new routes are covered by eval cases **in the same change that makes them
   diverge**, not in a later one.

Criterion 6 exists because the previous plan failed it: `fert_plan` diverged with
zero eval coverage of the route it changed, and only whole-branch review caught
it. The shield must exercise what the change changed.

---

## 2. Scope

**In scope**

- `budget` route: extract the numbers the user gave, compute in code, ask for the
  rest, explain the cost structure.
- `crop_choice` route: a context block carrying province and season, instructing
  the model to explain the deciding factors and ask.
- Eval coverage for both.

**Out of scope — deliberately**

- **The numeric data layer** (FAOSTAT, TÜİK, Pink Sheet). Its own spec. Until it
  lands there are **no default yields and no default prices**, anywhere.
- Establishment cost and multi-year return. See §7.
- Inflation, currency conversion, subsidy schemes.
- Recommending a crop.
- Membership, profiles, persistent memory.

**Deliberately unchanged**

`plant_info`, `nutrition` and `offscope` behave byte-for-byte as they do today.
The `[OFFSCOPE]` / `[NOPRODUCT]` markers, the product-suppression backstop, the
empty-answer guard and the stream-truncation recovery are not touched.

---

## 3. Architecture

Both routes follow the pattern `fert_plan` established: a route-specific context
block is prepended to the system prompt, and the answer is still produced by the
existing corpus path. No new answer path is created.

```
src/budget.py          NEW - extraction, arithmetic, framing
src/engine.py          _context_block gains two branches
src/context/           UNCHANGED - location and season reused as they are
data/                  nothing new
```

`crop_choice` adds **no module**. All new code lives in `src/budget.py`.

`src/budget.py` imports `_normalize_tr` from `src/engine.py`, so `engine.py` must
import it **inside the function body**, the same load-bearing deferred import
`router`, `fertplan` and `context.location` already require.

---

## 4. `budget.py`

### 4.1 Inputs

```python
@dataclass(frozen=True)
class BudgetInputs:
    area_da:     float | None    # dekar
    yield_kg_da: float | None    # kg per dekar
    price_tl_kg: float | None    # TL per kg
    cost_tl:     float | None    # total TL
    crop:        str   | None
```

Everything is normalised to canonical units **at extraction time**: dönüm → dekar
(they are the same, 1000 m²), hektar → 10 dekar, ton → 1000 kg. The model never
sees a conversion and never performs one.

### 4.2 Arithmetic

```
revenue = area_da * yield_kg_da * price_tl_kg
margin  = revenue - cost_tl
```

`compute(inputs) -> BudgetResult | None` returns `None` unless all four values
are present. **There is no partial calculation.** A result carries the figures
and the inputs they came from, so the answer can state what it used.

### 4.3 Extraction, and the rule that makes it safe

A number is assigned to a slot **only** when it carries an unambiguous unit or an
adjacent slot keyword. Anything else is ignored, which means the slot stays empty,
which means it gets asked for.

This deliberately chooses one failure mode over the other:

| The extractor… | Consequence |
| --- | --- |
| **misses** a number the user gave | asks for something already said — annoying, **visible**, harmless |
| **misreads** a number | states wrong money confidently — **silent**, and the user cannot detect it |

The second is unacceptable, so the extractor stays silent wherever it is unsure.

**"Adjacent" means within three words of the number, in either order.** Both
`1 milyon TL masraf ettim` and `masrafım 1 milyon TL` must extract; a cost
keyword at the other end of a long sentence must not.

**Accepted forms.**

| Slot | Accepted |
| --- | --- |
| Area | a number with `dönüm`, `dekar`, `da`, `hektar`, `ha`, `m²` |
| Cost | a number with an adjacent cost keyword — `masraf`, `gider`, `maliyet`, `harcadım`, `harcama`. **`TL` is optional**: the frozen case is *"1 milyon masraf ettim"*, with no currency written, and it must extract. |
| Price | an explicit per-weight form — `TL/kg`, `kilosu X TL`, `tonu X TL` (a per-ton figure is divided by 1000 into the canonical TL/kg) |
| Yield | **only** an explicit per-area form — see below |

**The trap that gets its own rule.** In Turkish, *"8 ton verim aldım"* means the
total; *"dekara 8 ton"* means per unit area. Reading one as the other inflates or
deflates the result fivefold on a five-dekar field. Therefore yield is accepted
only from an explicit per-area form — `dekara X kg`, `X kg/da`, `dönümde X ton`.
A bare `8 ton` is **ambiguous, so it is treated as missing and asked for.**

**Turkish surface detail.** Decimal comma (`12,5 TL`), thousands separator
(`1.000.000`), word multipliers (`1 milyon`, `500 bin`), and inflected units
(`dönümde`, `dekara`, `TL'ye`). Unit suffixes are **enumerated, never `\w*`** —
the convention `src/context/location.py` arrived at after seven collision rounds,
most recently when `il\w*` swallowed `ile`, `ilgili` and `ilaç`.

The collision surface here is genuinely narrower than in province matching,
because the anchor is the **unit word** (`dönüm`, `dekar`, `ton`, `TL`), not the
number. That is a reason to expect fewer rounds, not a reason to skip the
must-extract / must-not-extract table in §6.

### 4.4 What the model receives

With values missing:

```
Kullanicinin verdigi degerler: alan 5 dekar, masraf 1.000.000 TL.
EKSIK: verim (dekara kg), satis fiyati (TL/kg).
Cevabinda tam olarak bu eksikleri sor, deger UYDURMA.
Maliyet kalemlerini say: tohum, gubre, toprak isleme, sulama, ilaclama,
hasat, nakliye.
```

With all four present, the block instead carries the **computed** revenue and
margin and instructs the model to present them without recalculating. **The model
performs no arithmetic in either case.**

### 4.5 Framing

A fixed sentence appended **by code**, never requested in the prompt, so no model
can drop it — the same mechanism as `fertplan.FRAMING`, and for the same reason.

It is gated on a calculation having actually happened. Appending "this is an
estimate" to an answer that only asked questions would repeat the defect found in
the previous plan's review, where the disclaimer landed under a reply containing
no programme.

---

## 5. `crop_choice`

No module. A context block only:

```
Tarih: <month>, <season>.
Kullanicinin ili: <province>.        (omitted when unknown, with a line saying so)
Bu bir urun secimi sorusu. Karari belirleyen faktorleri anlat ve eksik olanlari
sor: toprak yapisi ve analiz, sulama imkani, arazi buyuklugu, onceki urun ve
munavebe, pazara mesafe, isgucu ve makine.
BELIRLI BIR URUN ONERME. Kullanicinin kosullarini bilmeden urun onermek bir
sezonluk gecim karari hakkinda temelsiz tavsiye olur.
```

**The prohibition is a prompt constraint, not a guarantee, and this spec does not
pretend otherwise.** A sentence appended by code cannot be dropped by a model; a
sentence forbidden by a prompt can still be produced. Enforcing it in code would
mean detecting "recommended a crop" in Turkish free text — the same class of
problem the product-suppression backstop already finds hard.

So it is **measured, not enforced**: the eval's `answer_none` guardrail dimension
carries banned phrasings, and a failure there is a finding to report, not a
number to soften.

---

## 6. Testing and gates

**Controller-verified extractor before dispatch.** The must-extract /
must-not-extract table is written first, run against the candidate implementation,
and only handed to an implementer once every case passes. Handing an implementer
code that fails its own tests blocked a task earlier in this project.

The table must include, at minimum:

| Input | Expected |
| --- | --- |
| `5 dönüm` | area 5 |
| `100 hektar` | area 1000 |
| `1 milyon masraf ettim` | cost 1 000 000 (no `TL` written — the frozen case) |
| `masrafım 1 milyon TL` | cost 1 000 000 (keyword before the number) |
| `dekara 400 kg` | yield 400 |
| `kilosu 12,5 TL` | price 12,5 |
| `tonu 12500 TL` | price 12,5 |
| `8 ton verim aldım` | **yield stays None** — total vs per-area is ambiguous |
| `1 milyon` with no keyword nearby | **cost stays None** |
| `geçen yıl 40 ton aldım` | **nothing extracted** |

The whole frozen `budget` set must also be run through the extractor and the
result recorded, so what each of the seven real questions yields is on the record
before any behaviour depends on it.

**Eval coverage in the same change.** Cases for both routes, taking the set from
58 to about 63. At minimum: a budget question with all inputs (must produce the
computed figure), a budget question with none (must name cost items and ask), and
a crop-choice question (`answer_none` on recommendation phrasings).

**Anchors must not be time-dependent.** The season line is derived from
`date.today()`, so an anchor like `Ağustos` would be green today and red in
December with nothing about the product having changed. This is recorded in the
existing eval set and applies here too.

**Routing gate re-measured before dispatch.** `budget` and `crop_choice` must
still show zero wrong entries in `evals.run_routing`. If either has gained one,
that route does not diverge.

**No regression** in the 58 existing cases, and the unit suite stays green.

---

## 7. Known limits, stated rather than discovered later

**Two questions in the frozen budget set fall outside the four-slot model.**

| Question | Why |
| --- | --- |
| *"Fındık bahçesi kurmak kaç para tutar?"* | **Establishment cost** — saplings, land preparation, and several years before first yield. Not annual operating economics. |
| *"Bu yatırımın geri dönüşü ne kadar sürer?"* | **Multi-year payback** — needs a cash-flow series, not a single year. |

Both still route to `budget` and both still get the cost-structure answer and the
questions, so neither returns empty. **Neither produces a calculation**, and that
is by design in this version.

**No defaults exist.** Until the numeric data layer lands, a user who supplies
nothing gets questions. That is the honest state and it should not be papered over
with model-invented "typical" figures.

**The crop-choice prohibition is measured, not enforced.** See §5.

---

## 8. Degradation

Every path degrades to today's behaviour, never to an error.

| Failure | Behaviour |
| --- | --- |
| Extraction finds nothing | all four asked for; cost items still explained |
| Extraction finds some | the rest asked for; no partial calculation |
| A number is ambiguous | treated as missing and asked for |
| `budget.py` raises for any reason | route falls back to today's corpus answer |
| Province unknown on `crop_choice` | factors explained, province asked for |
