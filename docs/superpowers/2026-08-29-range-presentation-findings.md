# The five-year range: measured, and the definition is sound

Investigated 2026-08-29. **No code changed. The lead is closed.**

## The lead, and how it was overstated

The handoff carried this as the largest open lead:

> 64,9 % of range-printing cells sit outside their own printed range.

That number was wrong, and wrong in my own favour: **it counted price cells**, which are
built with `show_range=False` and print no range at all. Measured on cells that actually
print one — yield cells only:

| | cells | share |
|---|---|---|
| print a five-year range | 7.245 | |
| the served figure is INSIDE it | 3.729 | 51,5 % |
| below the minimum | 2.084 | 28,8 % |
| above the maximum | 1.432 | 19,8 % |

So 48,5 %, not 64,9 %. And when a figure is outside, it is usually not marginal: the
median distance is 0,44–0,78 of the range's own width, and only 30 % of the outside cases
sit within a quarter of a range-width.

## The first hypothesis: a min–max of five points is a narrow band

For independent draws, the chance that a new value falls outside the min–max of `n`
previous ones is exactly `2/(n+1)` — 33,3 % at n=5, 50 % at n=3, 66,7 % at n=2. So *some*
of the outside rate is the estimator, not the data.

Split by how many prior years each range rests on:

| prior years | cells | observed outside | `2/(n+1)` |
|---|---|---|---|
| 2 | 113 | 55,8 % | 66,7 % |
| 3 | 200 | 42,5 % | 50,0 % |
| 4 | 252 | 38,9 % | 40,0 % |
| **5** | **6.680** | **49,0 %** | **33,3 %** |

At 2, 3 and 4 prior years the observed rate is at or BELOW the independent-draw
prediction — the range behaves exactly as a narrow estimator should, slightly better in
fact, which is what mild year-to-year autocorrelation looks like.

But 92 % of cells rest on five prior years, and there the observed rate is half again the
prediction. That is not sampling noise. Something systematic.

## What the excess actually is

Split the five-prior-year cells by which year is being served:

| served year | cells | below | above | outside |
|---|---|---|---|---|
| 2021 | 24 | 16,7 % | 29,2 % | 45,8 % |
| 2022 | 29 | 20,7 % | 3,4 % | 24,1 % |
| 2023 | 18 | 11,1 % | 33,3 % | 44,4 % |
| **2024** | **111** | **8,1 %** | **25,2 %** | **33,3 %** |
| **2025** | **6.498** | **29,7 %** | 19,7 % | **49,4 %** |

**2024 lands on 33,3 % — the independent-draw prediction, exactly.** 2021–2023 carry 18–29
cells each and are noise.

The entire excess is 2025's BELOW side: 8,1 % → 29,7 %. That is the bad-year effect the
collapsed-year round already measured and already warns about on both surfaces.

## Conclusion

**`_recent_range`'s definition is sound, and this is the evidence.** Its docstring justifies
excluding the served year — *"a range that contains it cannot say whether it is typical"* —
and the measurement bears that out: on a normal year the estimator is well calibrated to
within a rounding error of theory.

Two things follow, and both are reasons NOT to change it:

- **Including the served year would destroy the signal.** The range would then contain the
  figure by construction and could no longer answer the question it exists to answer. The
  33,3 % is the price of the signal, not a defect in it.
- **A third of figures falling outside is inherent**, not evidence of anything. Anyone
  re-opening this on the raw outside-rate is re-deriving `2/(n+1)`.

## What is left, and why it was not worth acting on

A line reading *"önceki 5 yıl: 20–37 kg/ağaç"* invites a reader to treat it as "the normal
range", when it is the min and max of five observations that a new one falls outside a
third of the time by construction. That is a reader-expectation gap, not a defect: the
label is literally accurate, and the only honest additions — a note that one year in three
lands outside — would lengthen a one-line hint to say something no farmer needs.

Considered and dropped.

## For anyone who re-opens this

Bring a NEW question, not the outside-rate. The rate is explained. Something that would
justify re-opening:

- evidence that readers actually misinterpret the line — this investigation had none, only
  my own reading of it;
- a year other than 2025 showing the same below-side excess on a sample larger than a
  hundred cells, which would mean the 2025 explanation is wrong.
