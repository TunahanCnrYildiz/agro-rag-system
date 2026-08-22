# Budget prefill (P2b): the norms reach the form

Status: proposed
Date: 2026-08-22
Amends: `2026-08-17-numeric-data-layer-design.md` (P2) — §7, §8, §9
Follows: P2a, merged as `b7415a2` (`data/crop_norms.json`, `src/norms.py`)

P2's design covers both halves of the work. P2a built the data half; this spec is
the **delta** for the form half — the four decisions P2 left open, the two facts
P2a's real data established, and one internal contradiction in P2 that has to be
resolved before either sentence in §8 can be written.

It does not restate P2. Everything in P2 §1–§6 and §10–§12 still binds. Where a
section here carries the same number as one in P2, it **replaces** it.

---

## 1. What P2 left unresolved

P2 was written before any export had been seen, so four things could not be
settled then and one was not noticed:

1. **When the prefill happens.** P2 says the crop field "becomes a real selection,
   populated from `available_crops()`". But the form is emitted in ONE shot, from
   `_budget_result` → `form_spec`, *before* the user has selected anything. How a
   value reaches the field after the selection is not described.
2. **Which year.** P2 §9 says a null latest year walks back. It does not address a
   latest year that is present and atypical — the case P2a's data produced.
3. **Where the province comes from.** P2 §9 says "the province is never guessed",
   but nothing passes a province to the budget route at all: it short-circuits
   before `_context_block`, and `_budget_result` receives only the payload.
4. **How 246 crops are selected on a phone.**
5. **(Not noticed then.)** §7 and §8 contradict each other — see §5 below.

`src/router.py` carries no crop lexicon; one was measured and deliberately not
built. So the crop cannot be read out of the question, and a selection is the
only mechanism available. That is the same conclusion P1 reached about money.

## 2. Flow

**Turn 1 — the question arrives.**

```
router -> "budget"
_budget_result(payload, message, history)          <- gains message/history
  location.extract_province(message, history)      -> "Ordu" | None
  norms.province_table(province)                   -> 246 rows for that province
  budget.form_spec(errors, table)                  -> fields + crops
```

The table ships **with the form**, in the same SSE `form` event. The mobile client
already sends the province as the first user turn (`"Ordu'dayım."`, written by
`profileTurns` in the chat screen), so `extract_province` resolves it from history
without a new wire field. This is the same mechanism weather and `fert_plan`
already use, with the same measured collision list; it is not a new inference
surface. When it resolves nothing, the province is `None` and no norm is invented.

**In the card.** A search box over the 246 labels. Selecting a crop fills the
yield and price fields **immediately, client-side, with no round trip** — the
numbers are already on the device. Each filled field shows its provenance
(`TÜİK 2025, Ordu`) and its recent range (`son 5 yıl: 73,7–105,6 kg/da`). Editing a
field makes it the user's.

**A prefill also sets the unit**, because a figure without its unit is the defect
P1 exists to prevent: yield prefills as `kg/dekar` (the form TÜİK states it in) and
price as `TL/kg`. Dropping `28,4` into a field still reading `kg` would be a total
harvest of 28 kg off the whole orchard.

**Selecting a second crop overwrites only untouched fields.** A field the user has
typed into keeps its value; only fields still marked `norm` are replaced. Wiping a
figure the farmer entered because they browsed the crop list is data loss, and
silent.

**A crop change also clears what the new crop cannot refill.** The wire carries
exactly one `crop`, so a field's norm can only belong to the selected crop — a yield
from one crop beside a price from another is not representable, and the server would
downgrade the orphaned claim to the farmer's own. So when the crop changes, or the
farmer answers "not in the list", any field still marked `norm` that the new crop
cannot refill loses its value, its marking and its unit. Found by review after the
card had already been driven in a browser: every golden path passed, and the failing
state was reachable only by deselecting a crop after a prefill.

**Turn 2 — submit.** The server validates, computes, and chooses the framing. No
model call, no retrieval. The route is still verified entirely by `pytest`.

### Why the table travels with the form

The alternatives were a `GET /api/crop-norms` endpoint and a two-turn card. The
endpoint adds a public, unauthenticated surface to a service that already has no
auth and no rate limit, and makes filling a form network-dependent. The two-turn
card spends two chat bubbles on one question and roughly doubles the card's state
machine. Shipping the table costs one measured **20,948 bytes** (Manisa; 24,811
with the recent ranges), and nothing at all in storage: the chat screen strips
`form` from every message before persisting it
(`messages.map(({ form, ...rest }) => rest)`), so the table never enters
`chatStore`.

## 3. Which figure prefills

**The latest published year, with its recent range shown beside it.**

`norms.lookup()` returns the most recent non-null year. For an alternate-bearing,
frost-prone crop that year can be an outlier. Hazelnut in Ordu reads

```
2016..2025:  41.0  94.0  79.4  95.6  86.8  73.7  105.6  87.5  88.9  28.4
```

A typical year is 74–106 kg/da; 2025 is **28.4**. Prefilling 28.4 is defensible as
"the latest published figure" and misleading as an expectation.

A multi-year median would read better and would be **a number TÜİK never
published**, which is the line `src/norms.py` exists to hold ("NOTHING IS
INVENTED"). So the prefill stays the published figure and the card shows the
recent range next to it. The outlier becomes visible rather than silent, and the
farmer overrides it knowing what they are overriding. That is the same trade the
whole budget route makes: the defect class here is a plausible-looking wrong
number, and the fix is to make the figure legible, not to smooth it.

`NormValue` gains `recent_min` and `recent_max`, taken over the non-null values of
**the five years preceding the prefilled one** — not the last five years of the
series. The distinction decides the whole feature: including 2025, hazelnut in
Ordu reads `28,4–105,6`, whose lower bound is the prefill itself and which
therefore says nothing; excluding it reads `73,7–105,6` against a prefill of
`28,4`, and the farmer sees the contrast at a glance. For an ordinary crop the
prefill simply sits inside the range and reads as confirmation.

Fewer than two non-null values in that window yields no range rather than a
degenerate one, and neither does a window whose values are all equal — a range
of `63–63` dresses one observation as a spread.

### What this reasoning got wrong about price, found by the final review

Everything above reasons about **yield**, and it does not transfer. Two things
break for a producer price:

- **Lira is nominal.** A stale yield is a physical quantity that does not inflate;
  a stale price is simply wrong money. Measured on the shipped file: in Ordu only
  **25 of 61** price norms are from 2025 and **29 predate 2023**. `Arpa (Diğer)`
  prefilled **1,10 TL/kg from 2018**, rendering `Gelir 423,50 TL` — roughly nine
  times low, in bold, from a form whose entire reason for existing is that the
  previous approach shipped plausible-looking wrong money figures.
- **The range stops being a warning and becomes noise.** The prefill sits *above*
  its own five-year band for 95 of 103 Manisa price cells and 45 of 48 in Ordu.
  That is currency drift, not an anomaly, so a line designed to make an outlier
  visible instead flags almost every crop.

So the rule splits by measure:

| | Prefill | Recent range |
| --- | --- | --- |
| Yield | the latest published year, however atypical | shown |
| Price | **only when its year is the dataset's most recent**; otherwise no cell at all | **never shown** |

Absence, not zero, and not a cell carrying an empty value: the field simply stays
empty exactly as it did before this feature. When the dataset's latest year cannot
be determined, no price is prefilled either — not knowing the cutoff is not a
reason to serve a stale figure. Yield is untouched: 71 of 75 Ordu yield norms are
already 2025.

`norms.latest_year()` supplies the cutoff explicitly. It is threaded through
`form_spec` as an argument rather than inferred from the cells, because inferring
"the latest year" from whichever figures happen to be present is the kind of guess
this route exists to remove.

## 4. The crop selection

A **search box** over the labels, plus an explicit "diğer" that prefills nothing
and leaves the form behaving exactly as P1. 246 options is past what a picker can
carry on a phone, and matching needs the Turkish fold (ı/i, ş, ğ, ç, ö, ü) so that
typing `findik` finds `Fındık`.

Ordering by the mobile profile's free-text `crops` was considered and rejected for
now: it adds a matcher, and therefore a test surface, for a convenience. The
selection itself would still be the user's, so it can be added later without
changing anything in this design.

**Tomato is two crops** — `Domates (Sofralık)` and `Domates (Salçalık)`. There is
no single "domates" norm. Both appear in the list; nothing merges them.

## 5. The contradiction in P2, and how it is resolved

P2 §7 ends: "**a submitted value is always `source: "user"`**, even where a norm
existed", and P2 §10 pins that as a test. P2 §8 says the framing "branches on
whether any figure came from a norm".

Both cannot hold. If every submitted value is `user`, no figure ever "came from a
norm" at submit time, the norm framing never renders, and P2 §3 — *the moment a
norm prefills a field, P1's sentence is false* — is left unfixed. This is the
error class P2 §3 itself names: present, well-formed, and wrong.

**Resolution.** The two claims are about different things and are separated:

- **Precedence** (P2's actual intent): the arithmetic always uses the submitted
  value. A prefill is a default, never a lock. Unchanged.
- **Provenance** (what the framing needs): the client sends a per-field `source` —
  `"norm"` when the field was prefilled and left untouched, `"user"` when typed.
  A form re-served after a validation error **echoes that claim back** on the
  field's existing `source` key. The card must not re-derive it by comparing the
  echoed value to the norm: a farmer who typed a figure that happens to equal the
  average would have it upgraded to `"norm"`, and the answer would then attribute
  their own number to TÜİK — the honesty invariant broken from outside the
  server's reach, since a `"user"` claim is never second-guessed.

The server does not take the client's word for it. A field claiming `"norm"` whose
submitted value does not match the norm the server itself resolves is **downgraded
to `"user"`**. So a client that lies, or one working from a stale table, cannot
make the answer attribute the farmer's own figure to TÜİK. The reverse is never
second-guessed: a field claiming `"user"` is the user's, even if the number
happens to equal the norm.

`BudgetField` in `src/main.py` gains `source: str = "user"`. Defaulting to `"user"`
keeps an already-deployed client — which sends no `source` at all — on P1's exact
framing rather than silently claiming a provenance it never asserted.

## 6. `src/norms.py`

| Addition | |
| --- | --- |
| `province_table(province)` | every crop resolved in one pass, rather than 246 `lookup` calls |
| `NormValue.recent_min` / `.recent_max` | non-null values of the last five years; `None` when fewer than two exist |

The module boundary holds: `norms` imports neither `engine` nor `location`, and
P2a's import test already pins that. The province arrives as a string the caller
resolved.

## 7. `src/budget.py`

Implements P2 §7, unchanged in intent:

- `UnitOption` gains `per_area: bool`; the yield field gains a **`kg/dekar`** unit.
- The label changes from `"Toplam ürün"` to `"Ürün miktarı"`. Once the field can
  hold a per-dekar figure, "toplam" is wrong under two of its three units, and a
  label that contradicts the selected unit is the exact mismatch the unit selector
  exists to prevent. Placeholder and helper text follow the same rule.
- One conversion line: `yield_kg = value × factor × (area_da if per_area else 1)`.
- `kg/dekar` selected with no area is a **field error**, never a silent zero.
- `form_spec(errors, table=None)` attaches `source_note` and `recent` to a field it
  prefills, and emits the crop list. **With no table the output is byte-identical
  to P1's.** (P2 §7 called this argument `prefill` and typed it as one crop's
  figures; it becomes the whole province table, because §2 moved the crop selection
  to the client. The wire fields it produces are P2's, unchanged.)
- Two framings, both appended by code, never asked of a model: P1's sentence
  verbatim when no norm figure survived to submit; otherwise a sentence naming
  which figures are not the user's, their source and year, and stating that a
  provincial average is not a prediction for one parcel.
- **A form re-served with validation errors echoes what was submitted** — each
  field's raw value and unit, and the selected crop. In P1 an error returned an
  empty form and the card, which seeds its state from the server's `value`, threw
  away everything the user had typed. Four fields made that survivable. This spec
  makes it worse in two ways: it adds a brand-new error (`kg/dekar` with no area),
  and a wipe now also discards the crop selection and its prefill. Echoing is ten
  lines and removes a defect this work would otherwise introduce.

All Turkish shown in the card is written here, in `src/budget.py`, and travels the
wire as finished text — the provenance note (`TÜİK 2025, Ordu`), the range line
(`önceki 5 yıl: 73,7–105,6 kg/da`), and every prefilled figure, already formatted
with `format_tr`. The client formats no numbers and composes no sentences: a
second Turkish number formatter on the client is a second place for a decimal
comma to go wrong.

## 8. Coverage, measured

The TR fallback **does not fire today.** Across Manisa, Ordu, Konya and Van, zero
crops resolve at `scope: "tr"`. P2a's exports were IBBS3-only: the `TR` key exists
on every measure (`_valid_measure` requires it) but its series is entirely null.
P2 §9's row "Province row absent → `TR` fallback, reported as such" is therefore
**dead code in practice**, not wrong.

Yield norms available, of 246 crops:

| Manisa | Konya | Ordu | Van |
| --- | --- | --- | --- |
| 142 | 147 | 75 | 73 |

The remainder prefill nothing and the form behaves exactly as P1. This is correct
behaviour, not a gap to paper over: a crop that is not grown in Van should not
carry a Van norm, and a national average for it would answer a question nobody
asked. **Populating the `TR` rows is one manual MEDAS export per crop group and is
out of scope here** — recorded in `data/raw/README.md` alongside the rest of the
refresh recipe.

The fallback's tests are **not** deleted for reading green vacuously. They are
pinned against a synthetic `scope: "tr"` fixture, so the path stays covered for the
day the national rows land.

## 9. Error handling

P2 §9's table binds, with these rows amended or added:

| Situation | Behaviour |
| --- | --- |
| No province resolved from the conversation | No provincial norm; the `TR` row is consulted and today carries nothing. Never guessed, never a neighbouring province |
| Crop has no row for this province | No prefill for that measure. The other measure still prefills if it has one |
| Latest year present but atypical | Prefilled as published, with the recent range beside it (§3) |
| Fewer than two non-null values in five years | No range shown; the prefill is unaffected |
| Client sends `source: "norm"`, value ≠ the server's norm | Downgraded to `"user"`; P1's framing |
| Client sends no `source` (old build) | `"user"`; P1's framing, byte for byte |
| A submitted form fails validation | The re-served form echoes every submitted value, unit and the crop, alongside the errors |

**The binding rule is P2's and is unchanged: a missing norm never becomes 0.**

## 10. Testing

P2 §10's table binds in full. Added:

| Group | What it pins |
| --- | --- |
| `province_table` | identical to calling `lookup` for all 246 crops; one file read |
| `recent` range | taken over the five years BEFORE the prefilled one, never including it; nulls dropped; fewer than two values yields no range; the range never replaces the prefill |
| Error echo | a form re-served with errors carries back every submitted value, its unit and the crop; a form never submitted still carries empty values and no errors |
| Provenance downgrade | `"norm"` with a mismatched value → `"user"`; a missing `source` → `"user"`; `"user"` never upgraded |
| Framing branch, end to end | a submitted form with an untouched prefill renders the norm sentence; the same form with that field edited renders P1's sentence verbatim |
| Province wiring | `_budget_result` resolves the province from history; an unresolvable one prefills nothing and does not raise |
| `tr` fallback | pinned against a synthetic national fixture, independent of what `data/crop_norms.json` currently carries |
| Prefilled unit | a prefilled yield carries `kg/dekar` and a prefilled price `TL/kg`; the served field never carries a norm figure under a unit it was not published in |
| Coverage guard | the shipped file yields a non-zero number of provincial yield norms for a named province, so a converter regression that empties the file fails loudly |

The card's own two rules — a second crop selection replaces only fields still
marked `norm`, and a prefill sets the field's unit — are client behaviour and are
verified by driving the app in Expo web, the way P1's card was. The traps that
cost time last round (React state needs the native value setter plus an `input`
event; `computer` clicks time out, so dispatch the pointer sequence) are recorded
in the handoff notes.

No eval case is added. The route makes no model call, so a case here would read
green while asserting nothing — the vacuity class this project has shipped before.

## 11. Client

`mobile-app/src/BudgetCard.tsx` gains the crop search and the provenance line;
`api.ts`'s `FormSpec` gains `crops`, and `BudgetFieldValue` gains `source`. The
card already seeds its state from the server's `value`, which was written for
exactly this and needs no change.

**A new build is required** for the card to draw the crop select — and one is
already required for P1's card. An older build keeps working: it ignores the extra
wire fields, sends no `source`, and gets P1's behaviour and P1's framing.

## 12. Out of scope

P3 (fertilizer quantity, blocked on a catalog data gap) · P4 (`crop_choice`) ·
the national-level MEDAS export · an input-cost norm (TÜİK publishes an index, not
lira) · ordering the crop list from the profile's free-text `crops`.
