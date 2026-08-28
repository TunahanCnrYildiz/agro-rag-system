# Serve fruit yield in TÜİK's published unit (kg/ağaç) — budget form

Design, 2026-08-28. Scope decided with the user: **the budget form only.**

## The problem, and why a bound cannot fix it

For 61 tree crops TÜİK publishes no per-dekar yield. `scripts/build_crop_norms.py`
derives one from `Üretim Miktarı ÷ Toplu Meyveliklerin Alanı`, and those two count
different populations: the numerator counts fruit from every tree in the province,
scattered and garden trees included; the denominator counts compact orchards only.

Four rules now defend that derivation — `_density_verdict` (cell),
`_province_area_never_orchard` (crop×province), `_area_never_orchard` (crop), and
`_ceiling_shadow` — and `docs/superpowers/2026-08-28-ceiling-findings.md` measured why
none of them can finish the job: `kg/da = ağaç/da × kg/ağaç` is an identity, so bounding
the density leaves the shipped yield bounded only by `444 × the crop's per-tree figure`,
which ranges 888 → 141.414 kg/da across crops. Ayva/Karabük still ships 13.419 kg/da.

**The published per-tree figure has no denominator we chose, so it needs no bound at all.**

## Measured before designing

| | |
|---|---|
| tree crops publishing kg/ağaç | 61 |
| currently served derived kg/da tree cells | 1.568 |
| **of those, a kg/ağaç figure exists** | **1.568 (100 %)** |
| would lose their prefill | **0** |
| (crop, province) pairs carrying kg/ağaç | 2.097 |
| **of those, serving no kg/da today — new coverage** | **+529** |
| pairs whose kg/ağaç figure is from 2025 | 1.958 of 2.097 |
| value distribution | median 19, p10 3, p90 58 kg/ağaç |

Zero coverage cost and a 34 % coverage gain. This is the rare change that is strictly
better on both axes.

## Design

### Data layer

The builder already reads `verim_agac` — it is the density gate's evidence — and throws
it away. It will now also write it, as `yield_kg_tree`, in the same shape as
`yield_kg_da`: aligned to the shared year axis, a zero refused the way every other
measure refuses one, `scope` and national row present.

**No gate runs on it.** Every existing gate defends a denominator this script chose; a
published figure has none. This follows the module's standing rule — *a published figure
always wins over a derivable one; never recompute what the source already states.*

`src/norms.py`:

- `CropNorm` gains `yield_kg_tree: NormValue | None`, resolved by the existing `_pick`.
  The year walk-back needs no change: a stale per-tree yield is a physical quantity, the
  same argument that already leaves `yield_kg_da` out of the price freshness gate.
- **`yield_kg_tree` must be validated as OPTIONAL, and this is the trap in this design.**
  `_load` currently drops a crop whole unless `all(_valid_measure(crop.get(m)) ...)` holds
  for every name in `_MEASURES`. Adding `yield_kg_tree` to `_MEASURES` would make
  `crop.get("yield_kg_tree")` return `None` for every field crop, `_valid_measure(None)`
  return False, and **all 246 crops would silently vanish from the table.** The measure
  must be validated only when present. A test pins this by loading a table whose field
  crops carry no per-tree measure and asserting they survive.

### One definition the rest of the design rests on

**A crop is served per-tree exactly when its resolved `yield_kg_tree` is not None** — no
separate list, no flag, no name matching. The rule is decided per (crop, province) by what
the table actually holds, so a province with no per-tree figure for a tree crop keeps
whatever `yield_kg_da` survives the gates rather than losing its prefill.

**Per-tree wins whenever both exist.** That is the whole point of the change, and it is
the same precedence the builder already applies in the other direction (a published
per-dekar figure beats a derivable one). Measured: all 1.568 served tree cells have a
per-tree figure, so in practice the derived cell loses for every one of them.

### Form

`src/budget.py`:

| change | where |
|---|---|
| `UnitOption("kg_agac", "kg/ağaç", 1.0, per_tree=True)` added to `yield_total` | `FIELDS` |
| `FieldSpec("tree_count", "Ağaç sayısı", required=False, min_value=0.0, min_exclusive=True, ...)` with one unit (`adet`), the way `cost` carries one option rather than a selector | `FIELDS` |
| `UnitOption` gains `per_tree: bool = False` | dataclass |
| `_read` grows the symmetric branch: a per-tree unit with no tree count is REFUSED, never multiplied by a guessed count | `_read` |
| `validate` reads `tree_count` before the field loop, out of `FIELDS` order, for the reason the comment already gives for area: that order is a layout decision, not a contract | `validate` |
| a row whose `yield_kg_tree` resolved is built from it with unit id `kg_agac`; every other row keeps `yield_kg_da` / `kg_da` | `_crop_rows` |
| `_VERIFIED` names the measure per ROW (the same `yield_kg_tree`-or-`yield_kg_da` test `_crop_rows` uses) rather than naming `yield_kg_da` outright, so a claim is compared against the very cell that was served | `_verify` |

`per_tree` is the exact mirror of `per_area`, whose comment already anticipated it: *"Kept
a property of the UNIT rather than a second field, so the conversion stays one line and a
new per-area unit needs no new branch."* The error text follows the existing one:
*"Ürün miktarı için ağaç başına değer girdiniz; önce ağaç sayısını doldurun."*

`tree_count` is **optional, enforced by the unit** rather than by a `required` flag.
`FieldSpec.required` is a property of the field, not of the selected crop, so making it
conditionally required would need a new mechanism; the per-area precedent shows the unit
is the right place for the dependency.

### What does not change

- **`compute()` is untouched.** The canonical unit is still total kg, so
  `yield_kg_da = total / area` still holds. The farmer's OWN tree count × TÜİK's published
  kg/ağaç gives the total harvest, and dividing by the farmer's OWN area gives a per-dekar
  figure that belongs to them. TÜİK's broken denominator never enters the arithmetic.
- `render()`, the framing sentences, the price path, `_norm_cell`'s range line.
- **`src/crop_compare.py` keeps serving derived `yield_kg_da`.** Accepted knowingly: for a
  fruit crop the two surfaces will disagree (Ayva/Karabük: the form prefills 31 kg/ağaç,
  the comparison prints 13.419 kg/da) until the comparison round lands. Recorded here so
  the next round inherits it as a decision, not a discovery.
- The four density rules and their refusal record stay, because `crop_compare` still
  depends on the derived measure.
- **The client.** `mobile-app/src/BudgetCard.tsx` renders `form.fields.map(...)`, the unit
  chips from `f.units.map(...)`, and builds its payload from `form.fields`; the unit travels
  with the prefill cell (`setUnits(cell.unit)`). A new field and a new unit therefore
  render and submit on an already-deployed build. **This was verified in the repo source,
  not in a shipped APK** — the deployed build is two cards behind — but the addition is
  backwards-safe for the same reason: an older client also maps over whatever
  `form.fields` contains.

## Testing

- `yield_kg_tree` is written aligned to the year axis, and a zero is refused.
- **No gate touches it:** a crop whose density gate refuses every derived cell still gets
  its per-tree series in full.
- **The optional-measure trap:** a table whose field crops carry no `yield_kg_tree` loads
  with all its crops intact. Proven by mutation — make the measure mandatory and this test
  must go red.
- A per-tree unit with no tree count is refused with its own message, and the value is
  neither zeroed nor multiplied by a guessed count.
- A tree crop's form row prefills the per-tree cell with unit `kg_agac`; a field crop's
  still prefills `kg_da`.
- `_verify` confirms a per-tree norm claim against the per-tree cell, and downgrades to
  "user" when the submitted text does not match what was served.
- End to end: tree count × per-tree norm → total kg → the answer's `dekara N kg` line.
- Regression: a field-crop budget submission is byte-identical to today's.

## Known oddity, recorded rather than hidden

The largest published per-tree figures come from catch-all and non-tree items: *Diğer
tropikal ve subtropikal meyveler* 5.000 kg/ağaç (Kütahya), *Fesleğen (Reyhan)* 2.000,
*Kuşdili (Biberiye)* 1.342. Basil and rosemary are not trees — TÜİK's "meyve veren ağaç"
means a plant or clump for them. 40 of 18.740 published per-tree cells exceed 500 kg/ağaç
(0,2 %). These are TÜİK's own figures with no denominator of ours, so they are served as
published. Excluding them was offered and declined; if it is ever wanted, the instrument
is a reviewed list like `data/crop_area_review.json`, not a threshold.

## Out of scope

`crop_compare`, the derived-yield retirement, and any change to the density rules.
