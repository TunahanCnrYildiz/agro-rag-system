# Product dose (P3): how much of this fertilizer for this field

Status: proposed
Date: 2026-08-22
Follows: P1 `2026-08-17-budget-form-design.md`, P2 `2026-08-17-numeric-data-layer-design.md`,
P2b `2026-08-22-budget-prefill-design.md`
Recon: `docs/superpowers/2026-08-22-product-dose-findings.md`

The stakeholder's pitch promises an answer to *"gübre ne kadar alacağım"*. Until 2026-08-22 that
was recorded as blocked by a catalog data gap. It is not: **40 of the 48 product pages publish a
per-dekar dose we can read**, and the only thing missing was a scraper that opened the tab. (The
recon measured 42; the whole-branch review refused two more whose figures turned out to be an
unreadable three-number chain — see the findings doc.)

This spec turns that into an answer, and — just as importantly — decides what it refuses.

---

## 1. What the recon established, and what it changed

All 48 `source_url`s were fetched. Every page carries three Elementor tabs, server-rendered in the
HTML: `Açıklama`, **`Uygulama (Yeri,Zamanı,Şekli,Dozu)`**, `Döküman`. A button
`#e-n-tab-title-N` pairs with a div `#e-n-tab-content-N` by the shared numeric suffix.

| | of 48 |
| --- | --- |
| Per-area dose (litres or grams per dekar / 1000 m²) | **42** |
| Dilution only (an amount per N litres of water) | 4 |
| No numeric dose at all | 2 |

The prior record — *"0 of 48 carry a numeric dose"* — was measured against `products.json`'s
`description` field and is exactly right about that: 0 of 48, averaging 143 characters, because
`scraper._fetch_description` reads the WooCommerce short description and stops. **A statement about
our data had been filed as a statement about the world.** That is the reusable lesson; the
correction is the smaller half.

## 2. Purpose & success criteria

1. A farmer who names a product, their crop group and their area gets the amount they need **for
   one application**, as a range, computed from the manufacturer's own published figure, with the
   application method the figure belongs to stated in the answer.
2. The answer says whose number it is. The figure is the manufacturer's; we quote it.
3. A range stays a range. `2–2,5 litre/da` over 5 dönüm is `10–12,5 litre`, never `11,25`.
4. **The season total is refused by name**, and the refusal says what it would need.
5. A product whose panel does not parse has no row, and the route says so rather than guessing.
6. The route makes no model call and no retrieval, so it is verified entirely by `pytest`.

## 3. What it answers, and what it refuses

| Question | Answer |
| --- | --- |
| "HİGRO BARF dekara ne kadar?" | The published dose for the chosen group and method |
| "5 dönümüm var, bir uygulamada ne kadar lazım?" | dose × area, as a range |
| "Sezon boyunca kaç litre alayım?" | **Refused**, with its reason |

**The refusal is a feature, not a shortfall.** A dose is per application, and a season's total needs
a count of applications. Only **8 of 48** panels state an interval or a number of applications, so
for the other 40 the season total is not in the source. Supplying one would mean authoring our own
programme and presenting it as the manufacturer's — the precise thing `src/fertplan.py`'s
`reviewed_by` gate exists to prevent.

Answering the narrow question while appearing to answer the broad one is a cost this project has
already paid once. So the refusal is explicit, names the missing datum, and is written by code.

## 4. Where the inputs come from

**From a card, never from the question.** P1 settled this for money: hand-curated Turkish token
matching plus proximity windows cannot survive Turkish inflection, and the review of that approach
found five demonstrated wrong money figures. *"5 dönümüm var, ne kadar alırım?"* has exactly the
same shape — a number in a sentence that must reach arithmetic — so it gets exactly the same
treatment.

| Field | Control | Why not inferred |
| --- | --- | --- |
| Ürün | searchable select over 48, the P2b crop-select control | 48 items, and a name matcher is a test surface for a convenience |
| Grup | three buttons: Sebze / Meyve / Tarla bitkisi | 45 of 48 panels segment this way; the farmer knows their own field better than a 246-row mapping table would |
| Alan | number + dönüm/hektar selector | P1's control, unchanged, including the unit-as-selection rule |

**The application method is NOT an input — it is an attribute of the answer.** An earlier draft made
it a third control, and measuring killed it: of the 42 products with a per-area dose, **37 attach it
to drip irrigation only**, 1 to foliar only (`FLY AZOT`), 1 to both, and 3 name no method. Foliar
figures are overwhelmingly dilutions (`60-70 gr / 100 litre su`), which are not per-area at all. A
selector that offers two options where 37 products have one is a choice in appearance only, and
pressing the wrong half would tell the farmer we have no figure for a method the product does not
publish one for.

So the card asks product, group and area; the answer reports **every** per-area figure that exists
for that product and group, each labelled with the method it belongs to. That is one line for
almost every product, two for the one that publishes both. The method is decided by the source, not
by the farmer, and the answer says which it is.

**The crop is deliberately not wired to the group.** P2 supplies 246 named crops, but mapping them
onto three groups needs an authored, reviewed table, and a misclassification yields a wrong dose
silently. `Kavun`, `Karpuz` and `Çilek` are genuine boundary cases. Out of scope; the farmer picks.

## 5. Arithmetic

Two multiplications, in Python, in one place:

```
low_total  = dose_low  × area_da
high_total = dose_high × area_da
```

No model call, no retrieval, no product matching. The route short-circuits the same way `budget`
does, and both transports must be wired — `answer()` and `stream_answer()` are mirror images, and
a route wired into only one reaches no user while the tests stay green.

Where the panel gives a single figure rather than a range, `low == high` and the answer prints one
number. Where it gives a range, both survive to the answer.

**The unit is stored as published and printed as published**, with one exception: a total of 1000
or more of a sub-unit is promoted (`1.250 gr` → `1,25 kg`, `2.500 cc` → `2,5 litre`). That is a
pure unit conversion and invents nothing, and a farmer buying fertilizer thinks in kilos and
litres. No other conversion happens — in particular a gram figure is never turned into a litre
one, because that needs a density the page does not give.

## 6. The data

`src/scraper.py` learns the Uygulama tab and a converter writes a **new committed file**,
`data/product_doses.json`:

```
product → { group → { method → {low, high, unit} } }
```

It is a separate file from `products.json` on purpose: a dose is structured, `description` is
prose, and the catalog is re-crawled on a different cadence than a dose table is reviewed. The
shape follows `data/crop_norms.json`: committed, diffable, with the source and the fetch date in
`meta`.

### The parse is the risky part, and the plan opens there

The panels are free Turkish. This spec's own reconnaissance produced **two false negatives from its
own regexes** before the number settled:

- the pages write **`/ 1000m²`**, not "dekar" — searching for `dekar|dönüm` finds 2 products, not
  42 — and they also write `1.000 m²` with a Turkish thousands dot;
- the amount appears on **either side** of the area (`250 gr/ 1000m²` but also
  `1000m² alan için … 2 – 2.5 litre`), and `gram` spelled out was missed by a pattern that had
  `gr` and `g`.

So the converter's contract is:

- **It reports every panel it could not parse, loudly, by name.** A silent skip is how a coverage
  collapse ships unnoticed.
- **A product whose panel does not parse has no row.** Absence, never a guessed figure — the same
  binding rule as `norms.py`, for the same reason: a wrong number here is a wrong purchase.
- The committed file must be a reproducible output of the committed converter over the committed
  fixtures, checkable by re-running it and diffing — the check that earned its keep in P2a.

## 7. Honesty

Two things are appended **by code**, never asked of a model:

- **Whose figure this is.** The dose is the manufacturer's published figure for their own product;
  the answer attributes it and does not present it as our recommendation. Quoting a manufacturer's
  own published dose is not the same act as authoring an unconditioned dose for a farmer's field —
  that distinction was established when `fert_plan` was specced and it is unchanged here. The
  `reviewed_by` gate on `data/fertplan_table.json` is **not** bypassed and not touched.
- **The season caveat.** Every answer states that the figure is per application, so that a farmer
  reading a purchase quantity out of it is corrected in the same breath.

A range is never collapsed to a midpoint. Collapsing invents a precision the source does not have,
and the resulting single number reads more authoritative than the range it came from — the
plausible-looking-wrong-number class again.

## 8. Error handling

| Situation | Behaviour |
| --- | --- |
| Product has no per-area dose (the 4 dilution-only, the 2 with none) | The route says it holds no per-dekar figure for that product and stops. It does not fall back to the dilution, which needs a spray volume the page does not give |
| Selected group absent for that product | No figure for that combination, named as such |
| Product has a per-area figure under a method the farmer did not expect | Not an error: the method is reported, not chosen. Every figure that exists for the product and group is printed, each labelled |
| Area missing or unparseable | A field error, never a silent zero |
| `data/product_doses.json` missing or malformed | Empty table; the route explains it has no dose data. Never an exception |
| A panel that parsed to `low > high` | Rejected at load, and the converter fails loudly on it |

**The binding rule, inherited: a missing dose is never 0.** A zero flows into the multiplication and
returns "you need 0 litres", which is a confident wrong answer about a purchase.

## 9. Testing

Everything is `pytest`. No network, no LM Studio, no vector store, **no eval case** — the route
makes no model call, so a case there would read green while asserting nothing.

| Group | What it pins |
| --- | --- |
| Converter | committed fixture panels produce the expected rows; a panel with no per-area figure produces NO row and is reported; `low ≤ high` on every row |
| Parse breadth | the four shapes that broke the recon's own regexes: `250 gr/ 1000m²`, `1.000 m²) 2 – 2,5 litre`, `1000m² alan için … 2 – 2.5 litre`, `100 litre suya 250 gram` (a dilution, which must NOT be read as per-area) |
| Coverage guard | the shipped file carries a per-area dose for a floor number of products, so a converter regression that empties it fails loudly rather than silently removing the feature |
| Arithmetic | a range times an area gives a range; a single figure gives one number; the range is never collapsed |
| Refusals | no per-area dose → said, not guessed; missing group or method → named; missing area → a field error |
| Framing | the manufacturer attribution and the per-application caveat are appended by code and present on every computed answer |
| Route | no model call, no retrieval, and **both** `answer()` and `stream_answer()` serve it identically |

## 10. Out of scope

- **Elemental → product mass.** Converting "16 kg of pure nitrogen per dekar" into a mass of this
  product needs a guaranteed-content analysis; only **3 of 48** pages carry an NPK-looking triple
  and 7 any percentage. Unchanged from the original P3 blocker, and the half of it that stands.
- **Season totals** (§3).
- **A crop → group mapping table** (§4).
- **Dilution-based amounts.** Turning `100 cc / 100 litre su` into a per-area quantity needs the
  spray volume per dekar, which is not on the page and varies by equipment.
- Any change to `data/fertplan_table.json` or its review gate.

## 11. Sequencing: this is two plans, not one

P2 was split for a reason that applies again here — the data half carries an unknown, and the
consumer half carries none. Keeping them together locks the certain work behind the uncertain
work.

- **P3a — the dose data.** Teach `src/scraper.py` the Uygulama tab, write the converter, ship
  `data/product_doses.json` and its loader. The unknown is the parse (§6): free Turkish that has
  already defeated two of this spec's own patterns. Its first task is a fixture set captured from
  the real panels, chosen to include the four shapes in §9's parse-breadth row.
- **P3b — the route and the card.** Depends only on the loader's interface, not on the parse. The
  card is the P2b card with different fields; the arithmetic is two multiplications.

P3a ships nothing user-visible, exactly as P2a did. P3b is where the answer appears.

## 12. Where this sits

| | | Status |
| --- | --- | --- |
| P1 | budget calculator | done, `26fa006` |
| P2a | crop norms data layer | done, `b7415a2` |
| P2b | budget prefill | done, `6b5d831` |
| **P3** | **this spec** | **proposed** |
| P4 | `crop_choice` naming a crop | needs P2's series; reverses a shipped decision |
