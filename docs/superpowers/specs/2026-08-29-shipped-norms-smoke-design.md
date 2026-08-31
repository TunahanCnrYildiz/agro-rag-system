# A smoke test over the shipped norms file

Design, 2026-08-29.

## Why

Three rounds in a row established invariants about the shipped `data/crop_norms.json` by
sweeping it inside a code review, and then let the evidence evaporate:

- the budget form and the comparison choose the **same measure** for every row — they
  disagreed on 1.568 cells for a whole round before that was fixed;
- **no per-tree cell prints `kg/da`** — 1.665 rendered cells were checked once, by hand;
- both surfaces reach the **same far-below verdict**;
- **no warned cell sits at or above its own range minimum** — this one is a fix for a
  Critical, verified on real data twice and pinned by no test.

Every test in `tests/test_crop_compare.py` and `tests/test_budget.py` runs on a fixture.
A regression in any of the above would keep the whole suite green, and the only record
that the property ever held is a review transcript nobody re-reads.

## Why a separate file, and it is not a preference

`tests/test_crop_compare.py:97` has an autouse fixture that writes a fixture table to a
temp file and points `norms._PATH` at it. A "real data" test placed in that file would
silently read the fixture. A new file avoids the trap by construction.

`tests/conftest.py`'s autouse fixture only isolates the answer log and does not touch
`norms` — checked.

## Prove the instrument before asserting anything

`norms._load` is an `lru_cache(maxsize=1)`, and several test modules repoint `norms._PATH`
at a temp table. Measured: after `tests/test_norms.py` and `tests/test_crop_compare.py`
both run, a fresh read still sees the real file — 246 crops, the real `_PATH`, a cache
miss rather than a stale hit. **So there is no leak today.** That is one teardown away from
being false, and a smoke test that silently read a fixture would pass vacuously — the
failure class this project has hit five times.

So the test clears `norms._load` and asserts it is reading the shipped file **before**
asserting anything about it: the crop count and the resolved `_PATH`. This is the same
discipline as *"before believing a red result, prove the measurement can go green"*, applied
to a green one.

## One sweep, several assertions

**The comparison side is exercised through `crop_compare._figures(row, latest_year)` and
`crop_compare._crop_block(figures)`, not through `render`.** `render` takes a TWO-CROP
answer, so covering every row through it would mean building ~10.000 pairings and would
say nothing extra: `_crop_block` is the function that produces one crop's lines, and
`render` only joins them and appends the closing sentences, which this round does not
assert about.

Measured: 19.926 rows through BOTH surfaces — `budget._yield_cell` and
`_figures` + `_crop_block` — takes **0,15 s**. The test walks the file once and collects
everything, rather than sweeping once per assertion.

| assertion | kind |
|---|---|
| the two surfaces choose the same MEASURE for every row | exact — zero mismatches |
| the two surfaces reach the same FAR-BELOW verdict wherever the comparison prints a range | exact — zero mismatches |
| no per-tree cell renders a `kg/da` unit ON EITHER SURFACE — the card's cell carries `unit == "kg_agac"`, and the comparison's block says `kg/ağaç` and never `kg/da` | exact — zero violations |
| no far-below cell has an amount at or above its `recent_min` | exact — zero violations |
| per-tree cells served, derived `kg/da` cells served | **floor**, not the measured count |

## Counts are floors, and that follows this project's own precedent

`tests/test_build_crop_norms.py::test_the_shipped_file_still_carries_most_of_its_yields`
already does exactly this, and says why:

> 45.000 is a deliberate floor, not the measured count. Measured 67.535 cells when this
> test was written; the floor sits at roughly two thirds of that: an order-of-magnitude
> collapse trips it, normal year-to-year drift in the TÜİK exports does not.

`data/crop_norms.json` is rebuilt by hand about once a year from new TÜİK exports, so a
pinned `2.097` or `234` would go red on every regeneration and teach whoever regenerates it
to edit the number rather than read it.

Measured today, for the floors: of 19.926 rows the card serves **8.274** yield cells —
**2.097** per tree and **6.177** per dekar. (7.745 rows carry a provincial `yield_kg_da`
value, but per-tree takes precedence where both exist, so that is not what the card
serves; the test counts what is served.) 246 crops, 81 provinces. The floors sit at
roughly two thirds: **1.400** and **4.000**.

**The invariants are NOT floors.** "Zero mismatches" is the whole point of them, and a
tolerance there would let exactly the drift they exist to catch slip through.

The far-below count is deliberately **not** asserted at all, not even as a floor: it depends
on a threshold documented as tuned, and on which year happens to be most recent. Its
invariant — no warned cell at or above its range minimum — is what matters and is asserted
exactly.

## Out of scope

- The price freshness gate, the builder's refusal counters against the file, and anything
  in `scripts/build_crop_norms.py` — that file already has its own shipped-data tests.
- Any change to `src/`. This round adds tests only.
- Turning the review transcripts' other measurements into tests. Only the four exact
  invariants above are pinned — measure agreement, far-below agreement, no `kg/da` on a
  per-tree cell, and no warned cell at or above its range minimum. The rest were one-off
  sizings, not properties, and the two counts are floors rather than invariants.
