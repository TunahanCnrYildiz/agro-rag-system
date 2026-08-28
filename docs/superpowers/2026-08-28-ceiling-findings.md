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

**Dut escapes both rules and remains the worst crop.** Median 330/da = 3,0 m² per tree —
implausible for a fruiting mulberry, but under the 444 bound, so the crop-level rule
cannot reach it without a new constant. It ships 14.950 kg/da in Diyarbakır. A reviewed
entry in `data/crop_area_review.json` is the honest instrument here, the way mushroom is
handled — a judgement recorded as a judgement, not a threshold pretending to be geometry.

**Caveat on this round's own numbers:** "more than 5× its crop's median" measures
suspicion, not proven error. Each flagged cell was not individually shown impossible. What
IS shown is that the density gate is not positioned to tell them apart.
