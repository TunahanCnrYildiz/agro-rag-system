# The crop comparison, once fruit yield is published per tree

Design, 2026-08-28. Follows the per-tree budget round (`origin/main` `dab1836`), which
left this surface knowingly untouched.

## The problem

`src/budget.py` now serves TÜİK's published `kg/ağaç` figure for the 61 tree crops.
`src/crop_compare.py` still serves the DERIVED `yield_kg_da`, so the two surfaces
contradict each other on **1.568 (crop, province) cells**. Karabük/Ayva is the sharpest:
the budget form prefills 31 kg/ağaç, the comparison prints 13.419 kg/da — roughly four
times any real quince yield, because the derivation divides a province's whole production
by the few dekars of compact orchard it records.

## Why the fix is not "use the per-tree figure and carry on"

The comparison's output is **dekara brüt gelir** — `kg/da × TL/kg`. Two routes to keep a
money figure for a tree crop, and both are closed:

- **Convert per-tree to per-dekar.** Needs a planting density nobody published. That is
  exactly the denominator the per-tree round removed; reintroducing it here would undo
  the round on the other surface.
- **Print revenue per TREE instead.** Measured, and it is not a fair comparison: crop
  median densities run ceviz 11, zeytin 18, kiraz 30, elma 34, fındık 50, armut 57, ayva
  79 trees/da — a **7× span**. Cevizin per-tree revenue beside ayva's is skewed sevenfold
  in ayva's favour. This route already carries `NOT_PROFIT` because two gross figures side
  by side read as a ranking; a per-tree pair is the same trap with a hidden multiplier.

So for a tree crop this route prints what TÜİK published and computes no money at all.

## Scale

| | |
|---|---|
| crops in the picker | 246 |
| of those, ever resolving a per-tree figure | 61 |
| crop FAMILIES the card offers | 187 |
| of those, tree families | **54 (29 %)** |
| cells where the two surfaces disagree today | 1.568 |

## Design

### Which measure — the same rule as the budget form

`_figures` reads per-tree **exactly when the row's `yield_kg_tree` resolved** — no crop
list, no flag, no name matching. This is character-for-character the test
`budget._yield_cell` uses. A test asserts both surfaces answer the same for the same row,
so they cannot drift apart again.

`CropFigures` gains `per_tree: bool`.

**`missing` is not reused for this.** It means "the half we do not hold" (`"verim"` /
`"fiyat"`); the per-tree case is a different statement — *both halves are held and cannot
be combined*. Overloading it would file one finding as another, the failure class that has
blocked this project twice.

`revenue_tl_da` is `None` for every `per_tree` row. The price freshness gate is unchanged:
a price older than the dataset's latest year is still suppressed, because lira is nominal
and a stale price misleads whether or not a revenue is computed from it.

**`missing` on a per-tree row is only ever `"verim"` or `None`, never `"fiyat"`.** Today
`_figures` sets `"fiyat"` whenever the price resolved to nothing, and that branch's whole
message is *"there is a yield but no price, so I am not computing revenue"* — which on a
per-tree row states a false cause. The revenue was refused for the unit, not the price.

`_crop_block` therefore tests in this order: `missing == "verim"` first (a genuine absence
outranks everything), then `per_tree`, then `missing == "fiyat"`, then the revenue block.

### What it prints

A tree crop with a current price:

```
**Ayva**: verim 31 kg/ağaç (TÜİK 2025, Karabük), fiyat 19,00 TL/kg (TÜİK 2025)
   verimde önceki 5 yıl: 27–28 kg/ağaç
   TÜİK bu ürünün verimini ağaç başına yayımlıyor; dekara çevirmek yayımlanmayan
   bir dikim sıklığı gerektirdiği için dekara gelir hesaplamıyorum.
```

A comma, not the `×` the revenue line uses: `×` announces a product, and there is none.
The explanation sits **under the crop it explains**, not at the foot of the answer, so a
reader never has to work out which crop it refers to.

A tree crop whose price is absent or stale drops the price clause and keeps the rest —
the same yield line, range and explanation. It does NOT also say "fiyat yok, bu yüzden
gelir hesaplamıyorum": the revenue was already refused for a different and more
fundamental reason, and giving two reasons for one absence invites the reader to think
supplying a price would fix it.

When one crop printed a revenue **and the other is per-tree**, one further code-written
sentence:

```
Bu tabloda tek bir gelir rakamı var, dolayısıyla bir karşılaştırma değil:
diğer ürünün verimi ağaç başına yayımlandığı için aynı birime getirilemiyor.
```

Its job is to stop the single money figure reading as a default winner.

**The `per_tree` half of that condition is load-bearing.** One crop can also lack a revenue
because this province publishes nothing for it at all, and the sentence would then assert a
per-tree reason that is simply untrue — the failure this route has twice shipped a fix for:
a code-written sentence describing something the page does not contain. Where the other
crop's revenue is missing for any other reason, its own block already says so and no extra
sentence is added.

### `NOT_PROFIT` tightens

It is appended today when `any(crop.revenue_tl_da is not None ...)`. It becomes **both**.

The sentence refuses a RANKING — *"kârlılık sıralamasını bu tablodan söyleyemem"*. With
one figure there is no ranking to refuse and the sentence points at something the page
does not contain. This route already learned that lesson once, in review, for the case
where NEITHER crop could show revenue; a per-tree crop creates the new case where exactly
one can.

### What does not change

`named_crops`, `_families`, the card, `src/router.py`, the two-crop selection, `compute`'s
one multiplication per crop, `ATTRIBUTION`, `NO_PROVINCE`, `ASK_FOR_CROPS`,
`COMPUTE_FAILED`.

**Each field-or-vegetable pair's per-crop BLOCK must render byte-identically to today.**
A regression test pins this rather than trusting it. The CLOSING SENTENCE does not carry
the same guarantee: where exactly one crop prints a revenue, `NOT_PROFIT` is replaced by
the shorter `GROSS_ONLY` (see "`NOT_PROFIT` tightens" above) — a later, deliberate change.
Measured on 2.520 real field/vegetable pairs: every block matched, but 667 pairs' closing
sentence changed this way (e.g. Aksaray's `marul (kıvırcık)` + `dereotu`, where the lettuce
has no current price so only one revenue prints). `NOT_PROFIT` bundles a gross-revenue
caveat with a refusal to rank; a single revenue has nothing to rank against, so only the
caveat half still applies.

The client is untouched: this route returns plain text, not a card.

## Testing

- A tree crop prints no revenue, prints the `kg/ağaç` unit, and carries its explanation.
- A field crop's block is byte-identical to today (regression).
- Mixed pair: the field crop's revenue shows, the tree crop's does not, `GROSS_ONLY` and
  the single-revenue sentence both appear, `NOT_PROFIT` does NOT.
- Two tree crops: no revenue anywhere, no `NOT_PROFIT`, no single-revenue sentence, two
  explanations.
- Two field crops: two revenues, `NOT_PROFIT` present, no single-revenue sentence.
- **One field crop with a revenue beside a crop this province publishes NOTHING for:** the
  single-revenue sentence is absent, because its stated reason would be false — but the one
  revenue that did print is still gross, so `GROSS_ONLY` appears alone. `NOT_PROFIT` is
  absent.
- A tree crop with a stale price: no price clause, no second reason for the missing
  revenue, yield still per-tree.
- A tree crop with no yield at all still reports `missing == "verim"` — `per_tree` must not
  swallow a genuine absence.
- A per-tree row never reports `missing == "fiyat"`, so the answer never gives the price as
  the reason a per-tree revenue is absent.
- **Cross-surface:** for the same `CropNorm` row, `crop_compare._figures(...).per_tree`
  agrees with whether `budget._yield_cell(...)` chose the per-tree measure. This is the
  test that stops the two surfaces drifting again.
- Every code-written sentence is read out loud against what the answer actually printed
  before it ships — the check that has twice caught this route claiming figures that were
  not on the page.

## Out of scope, deliberately

- **The derived `yield_kg_da` stays in `data/crop_norms.json` and the four density rules
  stay with it.** This round stops any surface from PRINTING it for a tree crop; it does
  not delete it. Retiring the measure is a separate decision with its own blast radius —
  `norms.CropNorm`, the builder, and every gate would move at once.
- Ayva/Karabük's derived 13.419 kg/da therefore still exists in the data file. After this
  round nothing shows it to a user.
- The budget form. It shipped in the previous round and is not touched here.
