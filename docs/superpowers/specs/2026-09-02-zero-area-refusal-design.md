# A zero area is refused silently, so the audit covers less than half of what is thrown out

Design, 2026-09-02.

## The defect, in the file's own words

`build()` writes its refusal record with this comment:

> The finding travels WITH the file. Without this record there is no committed way to tell
> a province that grows none of a crop from one whose figure we threw out.

Measured on the committed exports, the record holds 1.058 entries. A further **1.978 cells
are dropped with no entry at all** — no `meta` record, no stderr line, no console count.
More of what the builder throws out is invisible than visible.

Four drops are silent. Three of them are refusals; the fourth is not.

| shape | cells | where it is dropped |
|---|---|---|
| production present, **area 0** | 1.674 | `if tons is not None and dekar:` — the truthiness of `dekar` |
| TÜİK published a `Verim` of exactly **0** | 268 | `if value:` |
| area present, **production 0** (derived yield is 0,0) | 36 | `if value:` |
| both 0 | 77 | `if value:` — **nothing was thrown out here** |

## The zero area is not a fourth kind of bad cell

All 1.674 zero-area cells sit on tree crops. The zeroed column is therefore always
`Toplu Meyveliklerin Alanı`, never `Ekilen Alan` — and the density gate already has a name
for what that means: the province books fruit from scattered trees against a compact
orchard's dekars. **A zero area is that same finding at its limit.** The implied planting
density is unbounded, which is past any ceiling by any argument.

It escapes the gate for a mechanical reason, not a principled one. `_density_verdict`
computes `(tons * 1000 / per_tree) / dekar`, so a zero denominator would raise; the
truthiness guard at the call site keeps it out. But the guard sits **before** any verdict
is formed, so the cell never enters `refused` and — the load-bearing consequence —
**never casts a shadow**.

Worked example, Zerdali in Afyonkarahisar, from the committed exports:

```
 yıl       ton    dekar  kg/ağaç    ağaç/da      kg/da
2016     312.0     68.0     35.0        131       4588
2017     337.0     28.0     39.0        309      12036
2018     341.0     28.0     41.0        297      12179
2019     322.0      0.0     42.0          -          -   <- dropped in silence
2020     313.0      0.0     40.0          -          -
2021     311.0      0.0     41.0          -          -
2022     312.0      0.0     41.0          -          -
2023     226.0      0.0     35.0          -          -
2024     226.0      0.0     43.0          -          -
2025         -        -        -          -          -
```

Every density in the served years is under `_MAX_TREES_PER_DA` (444), so the cell gate has
nothing to say about them; it is the six zero years that carry the finding, and they are
exactly the ones that never reach it.

`src/norms.py` walks back to the most recent surviving year and serves **12.179 kg/da**.
Six consecutive years say the province records no compact orchard for this crop at all,
and not one of them reaches the file to say so.

## Design

### 1. `area_is_zero` — record it

A cell with production present and area exactly 0 is appended to `refused` under the reason
`area_is_zero`, then skipped as it is today.

The record is written **regardless of `per_tree`**. Today every such cell is a tree crop, so
the distinction changes no output; the reason it is written unconditionally is that the
refusal is about a division that cannot be performed, which is true of a vegetable too. A
future export that carries a zero `Ekilen Alan` must not fall back into silence.

### 2. `area_is_zero` casts a shadow

`_ceiling_shadow` collects the years a province is refused above the ceiling and condemns
every EARLIER derived cell there. A zero-area year joins that collection.

The docstring's own argument carries over without weakening: the refusal does not say
"this year's figure is odd", it says the recorded area is not the ground the production came
off. A year of zero recorded orchard says exactly that, in the strongest available terms.
The exclusions the docstring lists still hold and still exclude: `no_per_tree_figure` means
TÜİK has not published that survey yet, `density_below_floor` understates rather than
inflates, and a **published** Kg/Dekar figure is never shadowed because the argument is
about a denominator this script chose.

Shadowed cells keep the existing reason `shadowed_by_ceiling_refusal`. A zero area is
treated as a ceiling refusal throughout, so a second shadow reason would name a second
concept that does not exist.

Only a zero area with **production above zero** shadows. A year with both figures at zero
makes no claim about the denominator — see section 5.

### 3. Zero years enter the province median, not the crop median

`_province_area_never_orchard` asks whether THIS province's area column fails to record THIS
crop's ground. A year of zero recorded orchard is the most extreme possible answer to that
question, so it enters the median as an unbounded density. The median ranks rather than
averages, so an unbounded member needs no arithmetic.

`_area_never_orchard` — the crop-level median — does **not** take them. Its own docstring
states the intent: *"a handful of scattered-tree provinces costs those cells and never the
crop — apple is recorded properly nearly everywhere and must survive whole."* Measured: with
zero years in both medians, 338 served cells fall and among them is the whole of
Muşmula/Bursa —

```
 yıl       ton    dekar  kg/ağaç    ağaç/da      kg/da
2016     216.0    127.0     27.0         63       1701
2020     781.0   1156.0     25.0         27        676
2025     874.0   1389.0     17.0         37        629
```

— 24 to 63 trees per dekar, an area that grows smoothly from 127 to 1.389 dekars, and not
one zero year of its own. It would be destroyed by other provinces' zeros, which is the
failure its rule was written to prevent. With the zeros in the province median only, the
further loss over the shadow alone is 74 cells and Bursa survives whole.

(Both figures are design-time measurements taken one variant at a time. On the finished
branch, where all four changes are in place, adding the zeros to the crop median as well
would remove 264 more served cells — see "As built" below.)

The cell this split is for is Elma (Amasya)/Karaman: 2016-2020 recorded at zero area, then
2021-2024 carrying 11.615 to 12.769 kg/da off 11-13 dekars at 155-223 trees/da. The cell gate
passes all of it — that spacing is geometrically legal — and the shadow cannot reach it,
because every zero year precedes it. Only the province median refuses it.

### 4. The other two silent refusals are recorded

- `published_yield_is_zero` — TÜİK published a `Verim` of exactly 0 (268 cells).
- `production_is_zero` — an area is recorded and the production against it is 0, so the
  derived yield is 0,0 (36 cells).

Both are already refused, with the reasoning already written in the comment at `if value:`:
there is no way to tell a true zero from a missing marker, and neither reading is a norm.
Neither changes any served figure. They are recorded because a refusal the file does not
mention is indistinguishable from a province that grows nothing — the exact confusion the
record exists to prevent.

### 5. Both-zero stays silent

77 cells carry production 0 against area 0. No figure was discarded: the province grew none
of the crop that year. The record is a record of what was thrown out; an entry here would
say the opposite of the truth.

## What this costs

Served cells: **66.836 → 66.610**, a fall of 0,34 %. No crop is emptied. Thirty
(crop, province) pairs of 7.745 go empty, and there the budget form asks the farmer instead
of prefilling — the project's standing answer to a missing norm.

The refusal record roughly triples, from 1.058 entries to about 3.100, and
`data/crop_norms.json` grows from 2,7 MB to roughly 2,9 MB. Those figures are estimates from
the counts above; the rebuilt file states the real ones. The builder prints one stderr line
per refused cell, as it does today; the console summary stays one line per reason.

### As built — what the rebuilt file actually says

Written after implementation, because two of the estimates above were wrong and the design
should carry the correction rather than the guess.

**Served cells: 66.610, exactly as predicted.** The four changes together reproduce the
design measurement to the cell.

**The refusal record holds 1.714 entries, not ~3.100, and `area_is_zero` appears 110 times,
not ~1.674.** The estimate ignored an interaction between two of the changes. Counting zero
years in the province median takes that gate from 95 refused (crop, province) pairs to 275,
and a province-wide refusal is recorded ONCE, for the province, and skips the year loop
before the per-cell block runs. So 1.564 of the zero-area cells are folded into a
province-level entry instead of getting their own. That is the file's existing convention,
stated in its own comment — *"Recorded once for the province, not once per cell - the finding
is about the column, and a per-cell line would say the wrong thing"* — and the finding stays
visible at the granularity the rule works at. The file is 2,8 MB.

**One naming question this leaves open.** 132 of those 275 province entries cover pairs where
every member of the median was unbounded — no density was ever computed for them — yet they
are recorded under `province_median_density_above_ceiling`. The name is defensible on this
design's own premise, since a zero-area year IS an unbounded implied density and a median of
those is above any bound. But a reader mining the record for zero-area bookkeeping finds 110
cells while 132 wholly zero-area pairs sit under a density reason. Left as it is; recorded
here so it is a decision rather than an oversight.

**`counting them here removes 338 served cells` in `_area_never_orchard`'s docstring is now
264.** The 338 was measured during design, on a standalone reimplementation, before the other
three changes existed. The docstring carries the corrected figure; the qualitative half of
that sentence — Muşmula/Bursa destroyed, 24-63 trees/da, area growing smoothly from 127 to
1.389 dekars, not one zero year of its own — was re-verified against the raw exports and
holds.

## Known survivor, stated rather than fixed

**Zerdali/Malatya is not closed by this round.** Its zero years are 2019-2022 and its median
is 228 trees/da, under the ceiling, so the province gate does not reach it. `src/norms.py`
serves 2025 at 441 kg/da with a prior-five-year range carrying 12.077-12.255, and
`far_below_recent` fires on it.

This is the Ayva/Karabük shape: the implied spacing is geometrically legal and the absurdity
enters through the **per-tree** figure — 51 to 77 kg from a wild apricot. Judging that needs a
horticultural bound nobody here can defend, which is the per-crop-bound path measured and
closed on 2026-08-28 (`docs/superpowers/2026-08-28-ceiling-findings.md`). No new constant is
invented here.

## Testing

Fixture tests in `tests/test_build_crop_norms.py`, following the shape already there:

- a zero-area cell with production is refused as `area_is_zero`
- a zero-area cell condemns the earlier derived cells in its province
- a zero-area cell with production 0 records nothing and shadows nothing
- a published `Verim` of 0 is recorded as `published_yield_is_zero`
- a zero production against a recorded area is recorded as `production_is_zero`
- zero years push a province's median past the ceiling
- zero years do NOT push a crop's median past it — a properly recorded province survives
  the zeros of other provinces

`data/crop_norms.json` is regenerated by `python -m scripts.build_crop_norms`. This is not
optional bookkeeping: `test_the_shipped_file_is_what_the_builder_produces` rebuilds from the
committed exports and compares, so the file cannot lag the code or be edited by hand.
`test_the_shipped_file_still_carries_most_of_its_yields` holds a floor of 45.000 cells, which
66.610 clears.
