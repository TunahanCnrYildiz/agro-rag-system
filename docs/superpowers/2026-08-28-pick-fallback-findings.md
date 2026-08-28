# The `_pick` fallback: what it actually was, and what fixed it

Measured 2026-08-28. Opened from the handoff lead *"`norms._pick` falling back to a
year whose density was never checked"*.

## The lead's phrasing was wrong, and the correction is the whole finding

The year **was** checked. `scripts/build_crop_norms.py`'s density gate runs at build
time over every derived cell, and Turunç/Adana 2017 **passed** it at 405 trees/da,
under the 444 ceiling. Nothing was unchecked.

The defect is a level higher: **the gate is a per-CELL test, but the thing it detects
is a per-(crop, province) PROPERTY.** `density_above_ceiling` says the province books
scattered trees' fruit against a compact orchard's dekars — that is how the province
keeps its books, not what the weather did, so it does not change from year to year.

`norms._pick` walked straight over four consecutive such verdicts. Turunç/Adana is
refused in 2022, 2023, 2024 **and** 2025; `_pick` served 2017 — the same broken
denominator, which merely squeaked under the ceiling — as **23.098 kg/da**, a citrus
yield roughly ten times any real one.

## The enrichment, measured

Over all 7.861 served provincial yield cells, split by why the served year is old:

| group | n | > 8 t/da | rate |
|---|---|---|---|
| fresh (2025) | 7.115 | 56 | 0,8 % |
| stale, plain data gap | 603 | 7 | 1,2 % |
| **stale, behind ≥1 gate refusal** | **143** | **16** | **11,2 %** |

~14× enriched, and not noise: 201 of the refusals those 143 cells hide behind are
`density_above_ceiling`.

## The documented compensating control does not operate there

`src/crop_compare.py:189` leaves yield out of the freshness gate that suppresses a
stale PRICE, on a stated argument: *"its five-year range is where an outlier shows"*.
Of the 16 refusal-shadowed cells above 8 t/da:

- **8 print no range at all** — walking back that far leaves fewer than two prior
  years, so `_recent_range` returns `None, None`;
- **0 of 16** have a range that excludes the figure.

Not one is flagged. The inverse correlation is structural, not bad luck: the further
`_pick` walks back, the less able the warning is to exist. The control is weakest
exactly where the risk is highest.

## The fix

`_ceiling_shadow()` in the builder: **a derived cell is refused when the ceiling
refuses a LATER year for the same (crop, province).** `norms.py` is untouched — it
stays file-in, values-out, and `_pick` needs no knowledge of refusals.

Three scoping decisions, each argued rather than tuned:

- **Only `density_above_ceiling` casts a shadow.** `no_per_tree_figure` is publication
  lag — half of those sit in 2025 because TÜİK's per-tree survey trails its production
  tables — and says nothing about the denominator. `density_below_floor` understates.
  Shadowing on either would delete sound figures across the freshest year.
- **A published `Kg/Dekar` figure is never shadowed.** The argument is about a
  denominator this script chose; a published yield does not use one.
- **The shadow falls backwards only.** `_pick` reads from the newest end, so shadowing
  forwards would delete the good cell it would otherwise serve.

## Result

| | before | after |
|---|---|---|
| stale cells behind a `density_above_ceiling` | 201 | **0** |
| stale tree cells > 8 t/da | 18 (9,23 %) | **2 (1,33 %)** |
| stale tree cells > 20 t/da | 1 | **0** |
| served provincial yield cells | 7.861 | 7.816 |

Coverage cost **45 cells, 0,57 %** — predicted exactly before writing any code. The
losses are the fat tail: their median is 4.954 kg/da against a served median of 986.
The 12 that look plausible were already condemned by the gate in a newer year.

Adana / Turunç now renders *"bu il için yayımlanmış verim rakamı yok"* instead of a
figure; Adana / Limon still renders 1.606 kg/da (TÜİK 2025) untouched.

## THE LESSON: `min` passed every test the fix was written with

The first implementation took `min(refused_years)` — shadow only what precedes the
FIRST refusal — and **all four tests written for the feature passed**, because in
Turunç/Adana the refusals happen to be one contiguous run at the recent end.

Refusals are not always contiguous. Dut/Muğla is refused in 2016-2018 **and** from
2020 on, because the recorded area lurches between 1, 46, 39 and 12 dekars. 2019 sits
in the hole between them at 403 trees/da — 12.500 kg/da of mulberry, and precisely the
cell `_pick` walks back to. It survived `min` untouched.

It was caught by **re-running the product measurement after the fix, not by the tests**:
the 12.500 figure was still sitting in the output. `test_a_passing_year_sandwiched_between_refusals_is_shadowed`
now pins it.

This is the same shape this project keeps re-earning — *the plan's tests do not verify
what the plan claims matters* — but one turn worse: the tests were correct about the
case they described and simply could not distinguish `min` from `max`. **A fixture built
from one real example encodes that example's accidents.** Re-measure the population
after the fix, every time.

## Still open, and deliberately NOT in this round

**The 444 ceiling is loose, and it is the larger defect.** 16 **fresh** 2025 tree cells
exceed 8 t/da, clustered at 380-433 trees/da — right under the ceiling (Dut/Diyarbakır
14.950 @ 427, Ayva/Karabük 13.419 @ 433). This round does not touch them, and could
not: they are not fallbacks. A ceiling round would have to argue a new bound from
geometry the way the current one does, and its cost would land on fresh cells.

**The `alan == 0` silent skip is untouched.** Zerdali/Afyonkarahisar records 0 dekars
in 2019-2024, so those years are skipped with no console line and no `meta` entry, and
`_pick` serves 2018 at 12.178 kg/da. No ceiling refusal exists to cast a shadow, so
this rule cannot reach it. Pre-existing, already recorded as a residual of the fruit
yield gate.
