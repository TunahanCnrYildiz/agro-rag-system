# P4 — crop comparison: the two crops the farmer already narrowed to

Status: done, `177f907`
Date: 2026-08-26
Follows: P2a `2026-08-17-numeric-data-layer-design.md`, P2b `2026-08-22-budget-prefill-design.md`,
P3 `2026-08-22-product-dose-design.md`, the fruit yield gate `2026-08-25-fruit-yield-gate-design.md`
Reverses nothing: the shipped `crop_choice` refusal stays exactly where it is (§6).

The stakeholder's pitch promises an answer to *"ne ekeyim"*. The shipped `crop_choice` route
deliberately refuses to name a crop, and that refusal was a measured decision, not an oversight.
This spec does not overturn it. It adds the narrower thing the data can actually support: when the
farmer has **already narrowed to specific crops**, we put the published figures for those crops side
by side and refuse the verdict.

---

## 1. What changed, and what did not

**What changed:** the numbers became worth reading. Until 2026-08-25 the yield series carried fruit
"yields" derived from a compact-orchard area that did not hold the trees behind the production —
Turunç in Adana shipped as 1.219.500 kg/da. Ranking anything on that produced nonsense. Post-gate the
figures are sane: Manisa's top crop by gross revenue is Enginar at 332.250 TL/da, Ordu's is Çilek at
521.278, and every one of them rests on a yield between 2,5 and 5,5 t/da.

**What did not change: there is still no cost data anywhere in this project.** `CropNorm` carries
`yield_kg_da` and `price_tl_kg` and nothing else; the budget form asks the farmer for their own cost
because we have none to offer. So the only money figure we can compute per crop is **gross revenue**,
and the gap between gross revenue and profit varies by crop more than the crops differ from each
other. That single fact shapes every decision below.

## 2. Purpose & success criteria

1. A farmer who has narrowed to two crops sees, for their own province, what the published record
   says about each: yield with its year and region, the five-year yield range, the price, and gross
   revenue per dekar.
2. **The answer refuses to say which one to plant**, and says why in a sentence written by code.
3. Every figure is attributed. A farmer can tell our arithmetic from TÜİK's publication.
4. Where half a crop's figures are missing, that crop shows no revenue — absence, never zero.
5. The route makes no model call and no retrieval, so it is verified entirely by `pytest`.
6. The open *"ne eksem?"* question keeps today's answer, unchanged (§6).

## 3. What it answers, and what it refuses

| Question | Answer |
| --- | --- |
| "Konya'da domates mi biber mi ekmeliyim?" | Both crops' published figures, side by side, no verdict |
| "Hangisi daha çok kazandırır?" | Gross revenue for each, plus the sentence saying that is not profit |
| "Bu yıl tarlama ne eksem iyi olur?" | **Unchanged**: today's factors answer (§6) |
| "Hangisi daha kârlı?" | Never reaches this route — `kâr` is a budget stem, so the router sends it to the budget form, which asks for the farmer's own costs. That is the right destination, and it is why the profit refusal here is a **sentence inside the answer** rather than a fourth answer path |

**Why the refusal is the feature, in one worked example.** Konya, 2025:

| | verim | fiyat | dekara brüt gelir |
| --- | --- | --- | --- |
| Domates (Sofralık) | 5.492,1 kg/da (2025) | 21,06 TL/kg | **115.664 TL** |
| Biber (Salçalık, Kapya) | 3.154,7 kg/da (2025) | 39,89 TL/kg | **125.841 TL** |

Nine percent apart. A nine percent gross gap says nothing about which crop pays better, because
pepper and tomato do not cost the same to grow, and we have no figure for either cost. Printing these
two numbers and stopping is honest; printing them and implying a winner is the confident-wrong-answer
class this project has removed twice already.

## 4. Where the inputs come from

**From a card, and the data forces it.** `Biber` is not one row: the table carries `Biber
(Dolmalık)`, `Biber (Salçalık, Kapya)`, `Biber (Sivri)`, `Biber (Çarliston)` and `Biber, Kuru,
İşlenmemiş`, each with its own yield and price. `Domates` is two rows, `Elma` four. A farmer who
types "biber" has not told us which figure to read, and no matcher can guess it — a guess here
produces a wrong number silently, which is the defect class P1 was rewritten to remove.

| Field | Control | Why not inferred |
| --- | --- | --- |
| Ürün 1, Ürün 2 | the P2b searchable crop select, twice | 246 rows, and the variants above make disambiguation the farmer's call |
| İl | resolved from the conversation, as `budget` and `fert_plan` already do | asked in chat rather than guessed; a wrong province produces confidently wrong figures |

**There is deliberately no area field.** Area applies the same multiplier to both crops, so it cannot
change the comparison. Everything stays per dekar, and the farmer supplies no number at all.

## 5. Arithmetic and provenance

One multiplication per crop, in Python, in one place:

```
brüt gelir (TL/da) = verim (kg/da) × fiyat (TL/kg)
```

- **Price comes only from the dataset's most recent year.** P2b measured this: lira is nominal, and
  29 of Ordu's 61 price norms were older than 2023, with `Arpa (Diğer)` prefilling a 2018 price nine
  times too low. A crop with no latest-year price shows no revenue figure.
- **Yield may come from an older year, and shows its five-year range.** Also P2b's rule, for the
  opposite reason: a yield is a physical quantity that does not inflate, so a stale one still means
  something, and the range is where an outlier is visible. After the fruit yield gate, an older yield
  is now common for tree crops — TÜİK's 2025 per-tree survey lags its production tables.
- **Each figure prints its year and region**, exactly as the budget prefill does.
- **A missing half means no revenue for that crop**, and the answer says which half was missing. Never
  zero: a zero reads as "this crop earns nothing".

## 6. The route, and the refusal that stays

`crop_choice` already exists, already routes, and already receives a context block instructing the
model to explain the deciding factors and **not** name a crop. Five of the six frozen `crop_choice`
cases are open questions (*"Bu yıl tarlama ne eksem iyi olur?"*), and the eval case
`crop_choice_gives_factors_not_a_recommendation` pins that behaviour.

**Those keep today's answer.** The comparison card is served only when the farmer has actually
narrowed — when the message names **two or more distinct crops the table carries**. The frozen set
already contains exactly one such case: *"Bu yıl domates mi biber mi ekmeliyim?"*

"Names a crop" here means a crop NAME, not a table row. `domates` matches two rows and `biber` five;
for routing they count as one crop each, and the message above names two. Which row is meant is the
card's question, never the router's — the router only decides that a comparison was asked for.

**The crop matching is for ROUTING ONLY and never reaches arithmetic.** It decides which of two
answers to show; the figures are read from the card's explicit selections. A misroute costs a card
the farmer can ignore. This is the same shape as the product-dose route's product-name rule — and
that rule's history is the warning: as first written it fired on any message merely *naming* a
product, which cost the corpus answer and the product recommendations for questions that were not
about quantity at all. So this rule requires **two** crop names, not one, and the frozen 42 must be
re-measured before and after.

## 7. Honesty

Two sentences are appended **by code**, never asked of a model — the `fertplan.FRAMING` pattern:

- **Whose figures these are.** TÜİK's published provincial averages, with year and region, not a
  forecast for one parcel.
- **That gross revenue is not profit**, that two crops' costs can differ by more than the difference
  shown, and that the budget form with the farmer's own costs is where a real comparison happens.

A provincial mean is a central tendency across every holding in the province. Printed beside a second
crop's mean it invites being read as a ranking, which is precisely why the second sentence exists.

## 8. Error handling

| Situation | Behaviour |
| --- | --- |
| Fewer than two crops selected | A field error naming which select is empty |
| The same crop selected twice | A field error: a comparison needs two different crops |
| No province resolved | **No card at all** — the route asks which province and stops. Corrected 2026-08-26 against the implementation, which is the safer of the two: a card served without a province lets the farmer pick two crops, submit, fail province resolution again on the same resent message, and lose both picks with nothing to retry |
| A crop has no yield for that province | That crop's row shows the missing half by name, and no revenue |
| A crop has no latest-year price | Same, naming the price as the missing half |
| `crop_norms.json` missing or malformed | Empty table; the route says it has no figures. Never an exception |

## 9. Testing

Everything is `pytest`. No network, no LM Studio, no vector store, **no eval case** — the route makes
no model call, so a case there would read green while asserting nothing.

| Group | What it pins |
| --- | --- |
| Inputs | two crops required; the same crop twice is refused; an unknown crop id is a field error |
| Arithmetic | `verim × fiyat` per crop; a missing half yields no revenue and never zero |
| Provenance | each figure's year and region reach the answer; price is latest-year only |
| Framing | both code-written sentences appear on every computed answer |
| Refusal | no sentence in the rendered answer names a winner |
| Routing | a two-crop message routes to the comparison; a one-crop message and an open *"ne eksem"* message do **not**; the 42 pre-existing frozen cases are unmoved |
| The shipped refusal | the open-question path still produces today's factors answer |
| Route | no model call, no retrieval, and **both** `answer()` and `stream_answer()` serve it identically |

## 10. Out of scope

- **Ranking a province's crops.** The pitch's broadest reading, and the one the missing cost data
  cannot support: a gross-revenue ranking tells every farmer to plant strawberries.
- **Profit, margin, or any cost figure.** We hold none. The budget form is where the farmer's own
  costs enter.
- **More than two crops.** Two is what the question shape *"X mi Y mi"* asks and what a chat answer
  can hold; a third column is a table nobody reads on a phone.
- **Prefilling the card from the question's crop names.** A convenience that needs a Turkish matcher
  whose wrong guesses land on figures. If the two searches prove annoying in use, it can be its own
  round, with the variants problem solved first.
- **Reversing the `crop_choice` refusal for open questions** (§6).

## 11. Where this sits

| | | Status |
| --- | --- | --- |
| P1 | budget calculator | done, `26fa006` |
| P2a | crop norms data layer | done, `b7415a2` |
| P2b | budget prefill | done, `6b5d831` |
| P3 | product dose | done, `14d93fb` |
| — | fruit yield gate | done, `16445fc` |
| **P4** | **this spec** | **done, `177f907`** |
