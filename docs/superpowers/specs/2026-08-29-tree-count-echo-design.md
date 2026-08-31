# The budget answer omits an input it promised to restate

Design, 2026-08-29.

## The defect, in the function's own words

`budget.render`'s docstring: *"Code-written Turkish. Restates its inputs before stating its
result."* It restates the area and the price. It does not restate the tree count.

A farmer in Karabük comparing quince, who types **4000** trees where they meant 400:

```
Şu değerlere göre Ayva için: **10 dönüm**, toplam **124.000 kg**
(dekara 12.400 kg), kilogram fiyatı **19,00 TL**.

Gelir **2.356.000,00 TL**.
```

The area is echoed. The price is echoed. The number that multiplied their yield by ten
appears nowhere — its only trace is inside `124.000 kg`, which they would have to divide
by 31 to check. The answer even prints `dekara 12.400 kg`, a figure this project spent
several rounds establishing is impossible for quince, without naming the input that
produced it.

This is not a feature request. The function states a contract in its own docstring and
omits one of its inputs from it.

## Why it is missing

`validate` reads `tree_count`, uses it to convert a per-tree yield to a total, and
discards it. `BudgetInputs` carries `area_da`, `yield_kg`, `price_tl_kg` and `cost_tl` —
there is nowhere for the count to survive to `render`.

## Design

### Carry it, but only when it took part

`BudgetInputs` gains `trees: Value | None = None`.

`validate` sets it **only when the yield's chosen unit has `needs == "tree_count"`** — that
is, only when the count actually multiplied the yield.

**That condition is load-bearing, not a nicety.** A farmer can fill the tree count and then
state their harvest in `kg`; the count then plays no part in any arithmetic. Listing it
under *"Şu değerlere göre"* would be a code-written sentence describing something that did
not happen — the defect class this route has already shipped three separate fixes for.

The condition is read from `UnitOption.needs`, the single source of truth the `requires`
round established for "which field does this unit depend on". It is not a second copy of
that fact, and a test proves the link by mutation: blank `kg_agac`'s `needs` and the echo
must disappear.

**One detail this needs, and it removes an existing duplication rather than adding one.**
`validate` must know which unit the yield was submitted in, and today only `_read` knows —
it resolves the unit internally and returns just a `Value`. Rather than repeat that lookup
in `validate`, extract it: a module-level

```python
def _chosen_unit(spec: FieldSpec, raw: dict) -> UnitOption | None
```

returning the `UnitOption` the payload names for that field, or `None` when the payload
names none or names one the field does not offer. `_read` calls it in place of its inline
`next(...)`, and `validate` calls it to ask whether the yield's unit `needs` the tree count.
The lookup then exists once.

### Echo it beside the area

```
Şu değerlere göre Ayva için: **10 dönüm**, **4.000 ağaç**, toplam **124.000 kg**
(dekara 12.400 kg), kilogram fiyatı **19,00 TL**.
```

**Immediately after the area item and before the yield clause**, because both are the
farmer's own measurement of their own orchard, and because it mirrors exactly how the area
is already treated. It is deliberately NOT folded
into the yield clause — that clause already carries two figures (`toplam … kg` and
`dekara … kg`), and a third would bury the one the reader needs to check.

The wording is `**{count} ağaç**`, formatted with `format_qty` like every other quantity in
that sentence, so 4000 renders as `4.000`.

## What does not change

`compute()`, the framing sentence, `_verify`, the card, `crop_compare`, the data file, the
client.

**A field-crop answer is byte-identical to today.** No per-tree unit means no `trees` on the
inputs, which means no extra item in the list. A test pins this rather than trusting it.

## Testing

- A fruit budget's answer contains the tree count, formatted and in position.
- **A field-crop budget's answer is byte-identical to today** — the regression that matters,
  since 185 of the 246 crops are not tree crops.
- **The discriminating case:** a tree count supplied while the harvest is stated in `kg` is
  NOT echoed, because it took no part. This is the test that separates "carry it when it
  matters" from "carry it whenever present".
- `BudgetInputs.trees` is `None` for a field crop and set for a per-tree one.
- `_chosen_unit` returns `None` for a payload naming no unit and for one naming a unit the
  field does not offer — the two cases `_read`'s inline lookup already handled, so the
  extraction must not change either. `_read`'s existing refusal tests cover this and must
  stay green untouched.
- **Proven by mutation:** blanking `kg_agac`'s `needs` must make the echo disappear, showing
  the condition is derived from the unit rather than restated.
- The existing render tests use substring assertions rather than whole-string pins, so none
  should move; if one does, that is a real finding, not something to adjust.

## Out of scope

- The card. This is about the ANSWER, after submission; the card's own labelling was settled
  in the `requires` round.
- Warning that a tree count looks implausible. This round restates an input so the farmer can
  check it; judging the number would need a plausible-density claim, and this project has
  measured and refused exactly that (`docs/superpowers/2026-08-28-ceiling-findings.md`).
- `compute()` and every figure it produces.
