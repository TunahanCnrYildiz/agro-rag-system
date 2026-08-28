# The 444 trees/da ceiling: it bounds the wrong quantity

Measured 2026-08-28, straight after the `_pick` fallback round left it as the larger
open lead. **The conclusion is do NOT tune it.**

## The identity that settles it

```
kg/da  =  trees/da  ×  kg/tree
```

Not an approximation — it is how `build()` derives the cell. `_density_verdict` bounds
the FIRST factor at 444. The number we ship is the product. So the gate's real ceiling
on a shipped yield is **444 × the crop's per-tree figure**, and that figure is TÜİK's,
varying from 2 kg (hazelnut) to 127 kg (grapefruit):

| crop | med kg/tree | yield the gate permits | crop's own median yield |
|---|---|---|---|
| Fındık | 2 | 888 kg/da | 117 |
| Şam Fıstığı | 4 | 1.776 | 125 |
| Ceviz | 20 | 8.880 | 234 (**38×**) |
| Elma (Golden) | 36 | 15.984 | 1.443 |
| Greyfurt | 127 | **56.388** | 3.939 |

The implicit cap spans **888 → 141.414 kg/da, a factor of 159**, and what sets it is the
per-tree figure — which has nothing to do with whether a dekar can hold the trees.

**So the gate is blind for large-canopy crops.** Walnut needs only 235 trees/da to reach
an absurd 2.580 kg/da; the ceiling never fires. Rize records 69-115 dekar of walnut
against 178 tons. Denizli records **15 dekar** of hazelnut against 25 tons — 333 trees/da,
1.667 kg/da, and it passes. And it is loose for medium-canopy crops: Edirne's Golden
apple sits at 383 trees/da and ships 11.873 kg/da.

## A per-crop bound was tried and does not separate

First, a real validation: **each crop's own median implied density reproduces its known
planting distance**, five for five — ceviz 11/da = 9,6 m; fındık 50 = 4,5 m; elma
(golden) 34 = 5,4 m; kayısı 38 = 5,1 m; kiraz 30 = 5,8 m. The median is a sound anchor,
so a per-crop bound `K × crop median` is a fair thing to test.

Simulated end to end (each variant includes the shipped ceiling shadow), counting served
cells more than 5× their own crop's provincial median yield:

| rule | served | lost | outliers left |
|---|---|---|---|
| today (global 444) | 1.639 | 0 | 79 |
| + per-crop K=10 | 1.625 | 14 | 68 |
| + per-crop K=8 | 1.611 | 28 | 61 |
| + per-crop K=6 | 1.584 | 55 | 45 |

The most aggressive variant still leaves 45 of 79 while costing 55 cells. **And it cannot
separate:** `Elma (Granny Smith)/Tekirdağ` sits at 6,0× its crop median density and
yields 3.904-6.667 kg/da — a genuine modern high-density orchard (≈3,5 m² per tree, which
is a real super-spindle system). `Fındık/Denizli` sits at 6,7× and is entirely broken.
They overlap.

That is the original spec's own verdict on 444 — *"raises the floor on wrongness, it does
not remove it"* — reappearing one level up. Tuning moves the metric, not the defect.

## What DID ship: the same argument, one level up

`_area_never_orchard()`. The cell gate asks whether THIS province's area can hold its
trees. When the **median** province cannot, the question was never about a province:
`Toplu Meyveliklerin Alanı` is not recording that crop's ground anywhere, and the cells
that fall under the bound are the same bookkeeping, less extreme.

**No new constant.** It reuses `_MAX_TREES_PER_DA`. Two crops qualify:

| crop | median density | m²/tree | its served yield median |
|---|---|---|---|
| Kızılcık | 837/da | 1,2 | 12.312 kg/da |
| İğde | 727/da | 1,4 | 11.571 kg/da |

Those yields are independent confirmation: no cornelian cherry or oleaster grows 12 t/da.

Scoping, each argued:

- **The MEDIAN**, so a handful of scattered-tree provinces costs those cells and never the
  crop. Apple is recorded properly nearly everywhere and survives whole; a test pins it.
- **At least 10 provinces** before a crop is judged as a crop — a median over one or two
  provincial administrations describes them, not the crop. **The cut is insensitive, not
  tuned:** the above-ceiling crops rest on 29, 18 and 2 provinces, so every minimum from
  3 to 18 selects the same two. Turunç (median 2.480/da, 2 provinces) is the case just
  outside; its bad cells were already removed by the cell gate and the ceiling shadow.
- **Only the derived half is dropped.** A published Kg/Dekar figure uses no denominator,
  so the finding does not touch it — the same rule `_ceiling_shadow` follows.
- **Prices are untouched.** Kızılcık keeps 34 price cells, İğde 26. Same split the
  reviewed `not_field_area` crops get.

**Cost: 20 of 7.816 served cells (0,26 %).** pytest 920.

## THE LESSON: four of the five tests did not bite

Written first, as the process requires — and then **four of the five passed against the
unpatched builder.** The fixture repeated ONE density across twelve provinces, so every
cell was above 444 and the CELL gate already removed them all; the crop rule was
invisible. The fixture proved the premise, not the feature.

Fixed by spreading the densities so four of twelve fall UNDER the cell gate and only a
crop-level rule can reach them, plus a test that pins exactly that
(`test_the_cell_gate_alone_leaves_the_sound_looking_cells_standing`).

This is the second instance in one day, after `min`/`max` in the fallback round. Both
times the check that caught it was the same: **run the tests and look at WHICH ones fail,
not just whether the suite is red.** A test that passes before the fix is not evidence.

## Still open — and the real fix is NOT a better ceiling

**Serve fruit yield in its published unit (kg/ağaç).** TÜİK publishes a per-tree yield
for all 61 tree crops. It needs no denominator, so it needs no gate, no shadow and no
crop-level rule — the entire class of defect disappears. This round's evidence promotes
that lead from a nicety to **the** fix: the derivation is unsound because its numerator
counts every tree in the province and its denominator counts only compact orchards, and
no bound on the ratio repairs that. Cost: a tree-count form field and a new APK.

**~~Dut escapes both rules~~ — CLOSED the same day by a reviewed entry.** Median 330/da =
3,0 m² per tree, under the 444 bound, so neither gate could reach it without a new
constant pretending to be geometry. Recorded as a judgement instead, in
`data/crop_area_review.json`.

The evidence that justified it: across 559 derived cells in 66 provinces the implied
density runs p25 = 78/da (12,9 m²/tree), median 330 (3,0 m², 1,7 m spacing), p75 = 1.167
(0,9 m²), p90 = 4.139 (0,2 m²). **Only 11 of 559 cells fall under 20 trees/da** — a real
mulberry spacing — so the breakage is the whole column, not a tail. Its 37 served cells had
a median of 2.319 kg/da against TÜİK's own median of 24 kg per tree, which at any real
spacing is 400-600 kg/da.

**It needed a SECOND reviewed category, not mushroom's.** Mushroom's area is the wrong KIND
of surface — a building's footprint — and nothing about it survives. Dut's area is the right
kind and INCOMPLETE: `Toplu Meyveliklerin Alanı` counts compact orchards while `Üretim
Miktarı` counts fruit from every mulberry in the province. Different finding, so
`area_excludes_the_trees` with its own reason string, and only the DERIVED half is dropped —
a published Kg/Dekar figure uses no denominator. Filing it under `area_is_not_field` would
have put a false statement about mulberry into the committed audit record, which is the
same "a statement about one thing filed as a statement about another" that blocked both the
fruit yield gate and P3a. Cost: 37 served cells; 69 mulberry price cells untouched.

## Addendum, same day: Ayva/Karabük and the MIDDLE granularity

Looked at because it became the highest served fruit figure. **Ayva as a crop is sound** —
median 79 trees/da = 12,7 m² per tree = 3,6 m spacing, right for quince — so the crop-level
rule would have been a large over-reach. The defect is per-PROVINCE: 15 of ayva's 71
provinces have a median implying under 4 m² per tree (Kayseri 0,1; Ordu 0,2; Trabzon 0,2).
Karabük itself records 7, 7, 10, 10 dekar of compact quince orchard in 2016-2019 — against
231-280 tons — then steps to 31-38 dekar, and still implies 433 trees/da.

**Shipped: `_province_area_never_orchard`, the same bound at the granularity between the
two that already existed.** Cell → PROVINCE → crop, one geometric argument, no new
constant. 165 of 1.917 (crop, province) pairs have a median year past the bound; because
the cell gate and the shadow already take most of them, it removes **14 served cells** —
Erik/Tunceli at 0,8 m² per tree, İncir/Karaman at 0,4, Ayva/Hatay at 0,9. Median not mean,
so one wild year costs that year and never the province; at least 3 years before a province
is judged as a province.

**It does NOT close Karabük, and that was decided rather than missed.** Karabük's median
implies 2,4 m² per tree — past what a quince stands at, but not past the 2,25 m² this bound
already permits. Closing it means a bound somewhere in 2,25-4 m², and that band holds **44
served cells** including `Elma (Golden)/Edirne` at 3,3 m² — a spacing that is real for
super-spindle apple (0,9 m in-row × 3,5 m between rows ≈ 3,15 m²). Geometry cannot condemn
3,3 m²; what condemns Edirne is its 11.873 kg/da, which is a different argument. That is
exactly the per-crop-bound path measured and closed above, so it was not reopened on the
same evidence.

The band structure, which is the clearest thing this round produced:

| province-median implies | served cells | their median yield |
|---|---|---|
| < 2,25 m² (past the bound) | 14 | 2.139 kg/da |
| **2,25 - 4 m² ← Karabük** | **44** | **3.722** |
| 4 - 6 m² | 66 | 2.940 |
| 6 - 9 m² | 70 | 1.924 |
| > 9 m² | 1.388 | **602** |

Monotone: the less ground each tree implies, the more inflated the served yield. The sound
population sits at 602 kg/da and Karabük's band is six times it. **Ayva/Karabük stays open
knowingly, at 13.419 kg/da**, and `kg/ağaç` dissolves it along with the rest.

**A test caught the test, again.** The province rule's guard case — "one wild year must cost
that year, not the province" — went red against correct code: the wild year was in the
MIDDLE, and the ceiling shadow shipped that morning had already blanked everything before
it, so the expectation was wrong, not the builder. Moving the wild year to the front made
the fixture test only the rule under test. Third instance in one day of the same class.

**Caveat on this round's own numbers:** "more than 5× its crop's median" measures
suspicion, not proven error. Each flagged cell was not individually shown impossible. What
IS shown is that the density gate is not positioned to tell them apart.
