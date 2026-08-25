# Fruit yield: refuse the cells whose denominator is not the orchard

Status: proposed
Date: 2026-08-25
Follows: P2a `2026-08-17-numeric-data-layer-design.md`, P2b `2026-08-22-budget-prefill-design.md`
Blocks: P4 (`crop_choice` naming a crop)

`data/crop_norms.json` serves a per-dekar yield for every fruit. For a large minority of
province × crop × year cells that figure is not a yield at all — it is a province's whole fruit
production divided by the few dekars of *compact orchard* the province happens to record. The
budget form prefills it. This spec makes the builder refuse those cells instead of writing them.

---

## 1. What the recon established

**The builder's own premise is false.** `scripts/build_crop_norms.py` opens with:

> Tahıllar and Meyveler publish `Verim` directly, in Kg/Dekar.

Measured 2026-08-25: **not one fruit publishes a per-dekar yield.** All 61 of them publish
`Verim … - Kg/Meyve Veren Ağaç` — kilograms per fruit-bearing **tree**. The unit gate
(`_UNITS = {"verim": {"kg/dekar"}, …}`) correctly refuses every one of those rows, prints them as
`skipped unusable measure/unit`, and then the code silently falls through to the derivation path
built for vegetables:

```
yield_kg_da = üretim (ton) × 1000 ÷ toplu meyveliklerin alanı (dekar)
```

**The two halves do not describe the same trees.** TÜİK's production counts fruit from every tree
in the province, scattered roadside and garden trees included. `Toplu meyveliklerin alanı` counts
only compact orchards. Where a fruit is grown mostly as scattered trees, the numerator is whole and
the denominator is nearly empty:

| | production | compact orchard area | derived "yield" |
| --- | --- | --- | --- |
| Turunç, Adana, 2025 | 2.439 t | **2 da** | **1.219.500 kg/da** |
| Dut, Samsun, 2025 | 1.735 t | **4 da** | 433.750 kg/da |
| Ayva, Ordu, 2025 | 267 t | **3 da** | 89.000 kg/da |
| Ayva, Tokat, 2025 | 182 t | 155 da | 1.174 kg/da ✓ |

The last row is the control: the same crop, in a province that records a real orchard area, lands
where quince should.

**This reaches a user.** P2b prefills the yield into the budget form, and the form multiplies it by
a price. An Adana grower selecting `Turunç` is handed 1.219.500 kg/da and a revenue in the millions
per dekar — the confident-wrong-money class the entire budget rewrite exists to remove. A crude
sweep (yield above 20 t/da) finds **106 such cells across 54 provinces**, and that sweep is a floor:
it only catches cells whose per-tree yield happened to be high as well.

**The lesson is the file's oldest one, in a new place.** P3a recorded *"a statement about our data
had been filed as a statement about the world."* Here a statement about ONE crop group (cereals
publish kg/da) was filed as a statement about two, and the fallback it enabled has been shipping
ever since.

## 2. Purpose & success criteria

1. A fruit yield cell whose denominator cannot be the area the production came from is **not
   written**, and is reported by name.
2. Every refusal is visible: named on the console during the build, and recorded in the committed
   file's `meta`.
3. The published per-tree figure is **read as evidence and never written as a yield**. It is a
   different measure in a different unit; converting it would need a planting density this project
   does not have.
4. No interface changes. `src/norms.py`'s functions and return types, the wire, the budget form and
   the mobile client are untouched, and **no new APK is needed**. The only change a consumer can
   observe is that some cells are now absent — which every consumer already handles, because a
   missing cell was always possible.
5. The committed data file stays a reproducible output of the committed builder over the committed
   exports.

## 3. The test

For every cell the builder is about to derive, compute the tree density the three published numbers
imply:

```
implied trees/da = (üretim_kg ÷ ağaç başına kg) ÷ toplu alan_da
```

All three numbers come from TÜİK. Nothing is assumed about the crop.

**The data validates the test before the test judges the data.** Across 16.392 derived cells the
median implied density is **40 trees/da** — exactly a 5 m × 5 m orchard grid. The distribution's
peak sits in the 20–80 band. Where the source records a real orchard, this arithmetic returns a real
orchard.

## 4. The band, and why it is argued rather than discovered

| percentile | 5 | 25 | 50 | 75 | 90 | 95 | 99 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| implied trees/da | 9 | 25 | **40** | 84 | 343 | 956 | 6.613 |

**There is no valley.** The distribution is unimodal with a long, smoothly decaying right tail, so a
threshold cannot be read off a gap in the data. This spec does not pretend otherwise: the bound is
**argued**, and the argument is geometric, not agronomic — this project has recorded that neither
the user nor the assistant is an agricultural engineer, so no claim here rests on horticultural
judgement.

- **Ceiling: 444 trees/da.** That is a 1,5 m × 1,5 m grid — 2,25 m² of ground per tree. A
  fruit-bearing tree does not stand at 1,5 m spacing. Above this, the recorded area cannot be the
  ground the trees are standing on, so it cannot be the ground the production came from.
- **Floor: 5 trees/da.** The mirror error: an area is recorded and almost no production comes off
  it — a young orchard not yet in bearing, or an area recorded before a crop failure. It understates
  the yield rather than inflating it, which is the safer direction and still a wrong figure in a
  revenue line.

**This raises the floor on wrongness; it does not remove it.** A mulberry cell implying 200 trees/da
is still mostly scattered trees and still passes. The gate catches the cells that are impossible,
not the cells that are merely wrong, and §7's committed report is what lets a later reader see how
much was let through.

## 5. What the gate costs

Measured over the 16.392 cells the builder genuinely derives (the 20 fruit crops that publish
Kg/Dekar — vines, berries, herbs — never reach the derivation path, because a published figure wins):

| | cells | share |
| --- | --- | --- |
| Kept | 14.717 | **89,8%** |
| Refused — implied density above 444/da | 1.314 | 8,0% |
| Refused — implied density below 5/da | 259 | 1,6% |
| Refused — no per-tree figure for that province-year | 102 | 0,6% |
| **Total refused** | **1.675** | **10,2%** |

Four crops lose every cell they had: `Frenk Üzümü`, `Fesleğen (Reyhan)`, `Kuşdili Bitkisi
(Biberiye)`, `Tarhun`. The crops that lose the most cells are exactly the scattered-tree ones —
`Dut`, `Kızılcık`, `Ayva`, `Erik`, `İncir (Yaş)`, `Vişne`, `Zerdali`, `İğde`.

## 6. Cells the gate cannot judge, and the crops it cannot see

**No per-tree figure for that province-year → refuse.** 102 cells, 0,6%. An unjudged figure and a
judged one must not be indistinguishable in the output; absence is the answer this project has
already settled on twice (`norms.py`, `doses.py`).

**Mushroom is outside every gate and needs its own answer.** `Mantar (Kültür)` arrives through the
vegetable path, has no tree data, and its `ekilen alan` is the footprint of a building whose beds
are stacked in tiers: Ordu is 179 t ÷ **1 da** = 179.000 kg/da. It tops the yield × price ranking of
every province measured. No arithmetic over the published numbers can detect this — it is knowledge
about what the area MEANS.

So it follows the pattern P3a established and this project has already approved once: a small,
hand-written, committed review file naming the crops whose recorded area is not field area, with the
evidence beside each. One entry today (`Mantar (Kültür)`). The builder reads it, writes no yield for
those crops, and reports them. A crop in the file that no longer appears in the exports **raises**,
the same staleness gate `dose_group_scope.json` carries.

## 7. Output and reporting

`data/crop_norms.json` gains, under `meta`, a record of what was refused and why — counts per
reason, plus the refused cells themselves so a reader can audit any one of them without re-running
anything. Precedent: `product_doses.json`'s `unparsed` and `dropped_slots`.

The build also prints every refusal to the console, grouped by reason, in the loud style the file
already uses. A silent skip is how a coverage collapse ships unnoticed.

## 8. Binding rules inherited

- **A refused cell is absent, never zero and never a neighbour's figure.** A zero flows into a
  revenue line as "this crop earns nothing"; a neighbouring province's figure is a different claim
  entirely.
- **A published figure always beats a derived one.** Unchanged, and it is why the 20 kg/dekar fruit
  crops are untouched by this spec.
- **The per-tree figure is never converted to a per-dekar one.** That needs a planting density per
  crop per province that TÜİK does not publish here, and authoring one would be inventing the very
  number this spec removes.

## 9. Testing

Everything is `pytest`, no network.

| Group | What it pins |
| --- | --- |
| The test | fixture rows with a known production, area and per-tree yield produce the expected implied density |
| Ceiling | a cell above 444/da produces NO row and is reported |
| Floor | a cell below 5/da produces NO row and is reported |
| Unjudgeable | a cell with no per-tree figure produces NO row and is reported, distinctly from the two above |
| Kept | a cell inside the band is written unchanged — the gate must not alter a figure it accepts |
| Per-tree isolation | a per-tree row never becomes a yield, at any density |
| Published wins | a crop publishing Kg/Dekar is unaffected by the gate |
| Excluded crops | a crop named in the review file gets no yield row; a stale entry raises |
| Real data | the shipped file carries a yield for a floor number of cells, so a regression that empties it fails loudly; and re-running the density check over the committed exports finds no *kept* cell outside the band (the file stores a yield, not a density, so this check goes through the builder rather than reading the file alone) |
| Reproducibility | re-running the builder over the committed exports reproduces the committed file with no diff |

## 10. Out of scope

- **Serving fruit yield in its published unit (kg/ağaç).** It is the more faithful answer and the one
  the project's own "published beats derived" rule points at, but it needs a second unit in the norms
  layer, a tree-count path in the budget form, a wire change and a new APK. Recorded as the open
  lead this spec does not close.
- **Correcting a refused cell.** We refuse; we do not reconstruct. A corrected figure would need
  scattered-tree counts TÜİK does not publish in these exports.
- **The scattered-tree distortion below the ceiling** (§4).
- **P4 itself.** This spec exists so P4 has numbers worth ranking; it makes no decision about what
  P4 does with them.

## 11. Where this sits

| | | Status |
| --- | --- | --- |
| P2a | crop norms data layer | done, `b7415a2` |
| P2b | budget prefill | done, `6b5d831` |
| P3 | product dose | done, `14d93fb` |
| **this** | **fruit yield gate** | **proposed** |
| P4 | `crop_choice` naming a crop | blocked on this |
