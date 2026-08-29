# The tree count field says "optional" and is not

Design, 2026-08-29. Cleans up a defect the per-tree budget round (`origin/main` `dab1836`)
left behind.

## The problem, as a farmer meets it

Karabük, crop `Ayva`. The form renders:

```
Ağaç sayısı (isteğe bağlı)              <- empty
Ürün miktarı   31   [kg/ağaç]           <- TÜİK 2025, Karabük
```

Submitting without the tree count is refused: *"Ürün miktarı için ağaç başına değer
girdiniz; önce ağaç sayısını doldurun."* So the field the form calls **optional** is
mandatory the moment a per-tree prefill lands — which is every one of the 61 tree crops.
The error text is correct and the refusal is right; the LABEL is the lie, and it costs a
guaranteed rejection round trip on every fruit-crop first submit.

The cause is structural, and the per-tree spec named it while choosing the mechanism:
`FieldSpec.required` is a property of the FIELD, not of the crop the farmer picked. The
client renders `{f.label}{f.required ? "" : " (isteğe bağlı)"}` from that one flag.

## Why the deployed client cannot be told the truth today

The levers the server has over an already-deployed build, all four checked:

| lever | verdict |
|---|---|
| `f.required = True` | drops the suffix, but the SERVER then rejects a wheat budget for a missing tree count |
| `f.label` | the client appends the suffix, so a conditional label renders *"Ağaç sayısı (meyvede zorunlu) (isteğe bağlı)"* |
| `cell.note` | **not free** — `_verify` reads it and it becomes the answer's provenance sentence, joined with `" · "` |
| `cell.recent` | **free** — written once in `_norm_cell`, never read anywhere on the server, rendered only by the client |

So the label cannot be made honest without a client change. This design does both halves:
a hint that works on the build people are running now, and the real fix for the next one.

## Part 1 — the hint, for the deployed build

When the yield cell is per-tree, its `recent` line carries the instruction:

```
Ürün miktarı   31   [kg/ağaç]
   TÜİK 2025, Karabük
   önceki 5 yıl: 27–31 kg/ağaç · ağaç sayısını da girin
```

When the five-year range is absent — fewer than two prior years carry a value — the line
is the hint alone: `ağaç sayısını da girin`. The hint must not depend on the range's
existence, or it would vanish on exactly the sparsest crops.

**This is a deliberate overload and is marked as temporary in the code.** The field is
named `recent` and means "the five years before this one"; an instruction is not that.
The comment must carry the removal condition: **delete it once a build carrying Part 2's
label fix is deployed.** Nothing in the code can detect that — it is a human call, so the
comment says who makes it rather than implying the code will notice.

**Known limit, stated rather than hidden:** the client renders `note` and `recent` only
while the field is marked `norm`. A farmer who types their own figure and picks the
`kg/ağaç` chip sees no hint. That is acceptable — choosing the unit by hand is a
deliberate act — and it is unreachable from the server anyway.

## Part 2 — `requires`, for the next build

Each crop row on the wire gains a list of the fields that crop makes mandatory:

```json
{"id": "ayva", "label": "Ayva", "yield": {...}, "price": {...},
 "requires": ["tree_count"]}
```

The client uses it for the suffix and nothing else:

```jsx
{f.label}
{f.required || (selected?.requires ?? []).includes(f.id) ? "" : " (isteğe bağlı)"}
```

Adding a key to the crop row is backwards-safe for the same reason the per-tree round's
new field was: the deployed client reads `.id`, `.label`, `.yield` and `.price` off that
object and ignores what it does not know.

**`requires` is DERIVED, never hand-listed.** The server's real rule lives in the unit: a
per-tree unit cannot be converted without the tree count, and `_read` refuses it. A
hand-written list would be a second source of truth for the same fact and would drift the
first time a unit changed. It is computed from the unit the row's yield cell actually
carries.

**Two rules make the derivation exact:**

- **Only fields that are OPTIONAL by default are listed.** A per-dekar cell needs `area`,
  but `area` is already `required=True`, so listing it would say nothing the client does
  not know and would put a `requires` key on every field crop. The list answers one
  question: *which normally-optional field does this crop make mandatory?*
- **The key is ABSENT, not an empty list, when nothing qualifies.** That keeps a field
  crop's row byte-identical to today, which is what the wire-literal test pins.

## Part 3 — one field where there were two flags

`UnitOption` carries `per_area: bool` and `per_tree: bool`, and which FIELD each one needs
is encoded separately, inside `_read`'s two branches. Part 2 would be a third place
holding the same fact.

Replace both flags with the dependency itself:

```python
    # The field this unit cannot be converted without. A per-area unit needs the
    # area; a per-tree unit needs the tree count. Kept ON THE UNIT so the
    # conversion stays one lookup, and so `requires` on the wire is derived from
    # the same fact the validator enforces rather than restating it.
    needs: str | None = None        # a FieldSpec id
```

`_read` collapses its two branches into one lookup keyed by `needs`. `FIELDS` becomes
`UnitOption("kg_da", "kg/dekar", 1.0, needs="area")` and
`UnitOption("kg_agac", "kg/ağaç", 1.0, needs="tree_count")`.

The refusal message is built from the needed field's own label, so the two messages that
exist today keep their exact wording:

- `kg/dekar` → *"Ürün miktarı için dekar başına değer girdiniz; önce alanı doldurun."*
- `kg/ağaç` → *"Ürün miktarı için ağaç başına değer girdiniz; önce ağaç sayısını doldurun."*

Those two strings differ in more than the field name (*"dekar başına"* / *"ağaç başına"*,
*"alanı"* / *"ağaç sayısını"*), so they cannot be produced by one f-string over the label.
`UnitOption` therefore gains a second field beside `needs`:

```python
    needs: str | None = None        # a FieldSpec id
    # The refusal shown when `needs` is not filled in. Carried per unit because
    # the two messages differ in more than the field's name, and generating
    # them from the label would change user-facing Turkish.
    needs_error: str | None = None
```

`_read` formats it with the field's own label, exactly as today: `f"{spec.label} {unit.needs_error}"`,
where `needs_error` holds the part after the label — *"için dekar başına değer girdiniz;
önce alanı doldurun."* and *"için ağaç başına değer girdiniz; önce ağaç sayısını
doldurun."* The rendered strings are unchanged character for character, and a test pins
both verbatim.

## What does not change

`compute()`, `render()`, the framing sentences, the price path, `cell.note`, the answer's
provenance line, `src/crop_compare.py`, the data file, the builder, the router.

**A field-crop form must be byte-identical to today**, `form_spec` output included except
for the added `requires` key on crop rows that earn one. A test pins the wire literal, as
it already does.

## Testing

- A per-tree cell's `recent` carries the hint, with the range and without it.
- A per-dekar cell's `recent` is unchanged — no hint anywhere on a field crop.
- `cell.note` is unchanged for both, so the answer's provenance sentence cannot move.
- `requires` is `["tree_count"]` for a row whose yield cell is per-tree, and the KEY IS
  ABSENT otherwise — including for a per-dekar row, whose `area` dependency is already
  `required`. **Proven by mutation**: hand-fixing the list to a constant must make a test
  go red.
- A crop with no yield cell at all gets no `requires` — the derivation must not assume a
  cell exists.
- `_read` refuses a per-area value with no area, and a per-tree value with no tree count,
  with today's two messages **verbatim**. This is a regression on the refactor.
- The two out-of-`FIELDS`-order reads in `validate` still behave as mirrors — the test
  that pins that already exists and must stay green.
- Client: with a fruit crop selected the label carries no `(isteğe bağlı)`; with a field
  crop it does; with no crop selected it does.

## Out of scope

- Prefilling or guessing a tree count. There is no published planting density, and
  inventing one is the defect this whole line of work removed.
- `FieldSpec.required` becoming crop-conditional on the server. The server's enforcement
  is already correct through the unit; only the label was wrong.
- Building the APK. That is Emirhan's, and Part 1 exists precisely because it has not
  shipped yet.
