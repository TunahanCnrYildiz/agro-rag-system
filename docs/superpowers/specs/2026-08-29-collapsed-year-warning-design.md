# Saying so when the newest published yield is far below its own history

Design, 2026-08-29.

## The problem, as a farmer meets it

Bilecik, crop `Erik`. The budget form prefills **1 kg/ağaç**, noted `TÜİK 2025, Bilecik`.
The five years before it ran 20–37 kg/ağaç.

The raw data is internally consistent and there is no bug in it: production fell from
2.954 tons to **27 tons** while the recorded orchard area went UP, 3.192 → 3.810 dekar.
The trees are there; the harvest is not. Both measures agree.

What is wrong is the product. `norms._pick` serves *the most recent published figure*, and
the module's docstring justifies keeping a stale yield on the grounds that *a stale price
is not a meaningful physical quantity the way a stale yield still is.* That reasoning is
sound for STALENESS and does not cover a year in which the harvest was destroyed: the most
recent physical quantity is not an expectation when there was almost nothing to measure.

**Measured, on what a user can actually be served** (7.245 provincial yield cells that
print a prior range):

| the served figure is below | cells | of which 2025 |
|---|---|---|
| half its prior midpoint | 588 (8,1 %) | 575 |
| a third | 362 | 355 |
| a fifth | 240 (3,3 %) | 237 |
| a tenth | 95 | 95 |

The deepest are concentrated in **Niğde** — ceviz, nektarin, şeftali, vişne, armut, ayva,
erik, kiraz and zerdali all at 1–2 kg/ağaç — and in stone fruit generally (vişne 15,
kiraz 15, kayısı 15, şeftali 14, erik 12 across all provinces). That crop-and-province
profile is what a spring frost looks like. **This design does not depend on that being the
cause**, and says nothing about a cause: it only reacts to a figure being far below its own
published history.

## The threshold is TUNED, not argued — stated rather than hidden

The 444 trees/da ceiling in `scripts/build_crop_norms.py` was argued from geometry because
its distribution had no natural cut. **This distribution has no natural cut either**, and
the same honesty is owed here.

Histogram of `served ÷ prior five-year midpoint`, 0,05-wide bins below 0,6:

```
0.00-0.05  39   0.05-0.10  56   0.10-0.15  74
0.15-0.20  71   0.20-0.25  49   0.25-0.30  46
0.30-0.35  47   0.35-0.40  59   0.40-0.45  79
0.45-0.50  68   0.50-0.55 121   0.55-0.60 120
```

It decays smoothly from the mode at 0,9–1,2. There is no gap and no second peak: a
catastrophic year and a merely poor one lie on one continuum. An ordering rule does not
rescue it either — *"below the minimum of the prior five"* fires on **28,8 %** of cells and
**57 % of those are near misses** (0,8–1,0 of that minimum), an ordinary slightly-worse
year.

So the chosen value is **one fifth of the prior five-year midpoint**, and it is a TUNED
number. What can be said for it, and no more:

- the histogram's slope is shallowest across roughly 0,20–0,35 (about 47 cells per 0,05
  step, against about 120 near 0,5), so the choice is least consequential there;
- at one fifth it fires on **240 of 7.245 cells (3,3 %)**.

**Why a tuned number is acceptable HERE and was not acceptable for the density gates.** It
drives a SENTENCE, not a refusal. A wrong threshold that fires too often costs an
unnecessary sentence; one that fires too rarely leaves today's behaviour. **No outcome is
worse than shipping nothing.** The density rules delete data, which is why they were held
to a higher bar. This distinction is the design's whole justification and belongs in the
code comment, not only here.

## What was considered and dropped

**Refusing the prefill instead of warning.** Rejected on the asymmetry above: a false
positive would remove a legitimate prefill from a farmer, and the number driving it cannot
be argued.

**Substituting a typical figure** (a median of recent years). Refused outright: it would
serve a number nobody published, which is this project's binding rule.

**Requiring that the area did not fall**, to separate a failed harvest from a province
leaving the crop. Measured: of the 227 firing cells with an area series, **211 (93 %) had
area hold or grow** and only 16 fell. It would cost a new field in the data file and a
builder change to refine 7 % of a sentence. Dropped as YAGNI — and unnecessary, because
the wording claims no cause and is true either way.

## Design

### Detection — one function, both surfaces

`src/norms.py` gains a module-level helper. Everything it needs is already on `NormValue`:

```python
def far_below_recent(value: NormValue | None) -> bool
```

`True` when the value exists, carries a five-year range, and its amount is below one fifth
of that range's midpoint. `False` when there is no range — with nothing to compare against
there is nothing to warn about.

It lives in `norms.py` because it is a statement about the VALUE, not about presentation,
and because both surfaces must reach the same verdict for the same cell. The two surfaces
decided a measure separately once before and disagreed on 1.568 cells for a round; a test
pins them together here from the start.

### The budget card — the warning extends the range line

The range is the warning's evidence, so one line does both jobs:

```
önceki 5 yıl: 20–37 kg/ağaç                             <- unchanged
önceki 5 yıl: 20–37 kg/ağaç — 2025 bunun çok altında    <- far below
```

The appended text is exactly `" — {year} bunun çok altında"`, where `{year}` is the
served value's own year. It rides on `recent` because that is the only line the deployed
client renders under a prefilled field that nothing on the server reads. `note` is spoken
for: `_verify` reads it and it becomes the answer's provenance sentence.

**Only the YIELD cell can carry this.** The price cell is built with `show_range=False`
and so has no `recent` line at all, and prices are already gated on freshness — only the
dataset's latest year is served. A collapsed price is out of scope by construction.

**Known cost, stated rather than hidden:** on a per-tree cell the line also carries the
temporary tree-count hint, so the worst case reads *"önceki 5 yıl: 20–37 kg/ağaç — 2025
bunun çok altında · ağaç sayısını da girin"*. It may wrap. The hint is already marked for
deletion once the label fix ships, and the line shortens then.

### The comparison — its own line

`src/crop_compare.py` has room in the text answer, so the sentence is not crammed:

```
   verimde önceki 5 yıl: 20–37 kg/ağaç
   2025 bu aralığın çok altında; olağan bir yılın beklentisi değil.
```

The sentence is exactly `"{year} bu aralığın çok altında; olağan bir yılın beklentisi
değil."`, indented like the lines around it and placed IMMEDIATELY AFTER the range line it
refers to — a reader must not have to work out which figure it is about.

**It applies to any far-below cell, per-tree or per-dekar alike.** The test is the value,
not the measure.

**It cannot appear on a block that prints no range.** The `missing == "verim"` and
`missing == "fiyat"` blocks carry no five-year line, and `far_below_recent` returns False
without a range, so the two rules agree without a special case.

**Including this surface is not optional.** Leaving it out would reopen exactly the
divergence closed the day before: the same crop and province telling two different stories
on two surfaces. The comparison is also where a money figure is printed for a field crop,
so a collapsed yield there becomes a gross-revenue figure.

## What does not change

`norms._pick`, `compute()`, `cell.note`, the answer's provenance sentence, the price
freshness gate, the data file, the builder, the density rules, the router, the client.

**A cell that is not far below its own history renders byte-identically to today**, on both
surfaces. Tests pin this rather than trusting it.

## Testing

- A far-below cell carries the warning on the card; a normal cell's `recent` is unchanged.
- A far-below cell carries the sentence in the comparison, directly under its range line;
  a normal one does not. A block that prints no range never carries it.
- `cell.note` is unchanged in both cases, so the answer's provenance line cannot move.
- A cell with NO five-year range gets no warning — there is nothing to compare against.
- **Both surfaces reach the same verdict for the same row**, asserted by walking a table.
- The threshold is exercised from both sides: a cell just above it warns not at all, a cell
  just below it warns.
- **Proven by mutation:** changing the constant from one fifth to one fiftieth must turn a
  test red. A threshold no test pins is a threshold that can drift silently.

## Out of scope, with reasons

- **The budget ANSWER (`render`).** The warning's value is before the farmer commits; the
  answer comes after. It would also need `Value` to carry the norm's verdict, which is new
  plumbing for a surface that arrives too late to change a decision.
- The area-did-not-fall refinement, the builder, and the data file — see above.
- Anything that changes which figure is SERVED. This round adds a sentence; `_pick` keeps
  serving the most recent published value.

## The lead this closes, and the one it does not

It closes *"the printed range can exclude the figure it sits under"* only for the extreme
tail. The broader observation stands: **64,9 % of range-printing cells sit outside their own
range**, mostly by a little, because the ranges are narrow. That is a presentation question
about `_recent_range`'s definition and is untouched here.

**This defect is also transient.** When TÜİK publishes 2026, 2025 stops being the most
recent year and the range widens to include it. But the data file is rebuilt by hand about
once a year and those figures do not exist before late 2026, so the defect is live for
roughly a year — too long to leave, too short to build a refusal mechanism for.
