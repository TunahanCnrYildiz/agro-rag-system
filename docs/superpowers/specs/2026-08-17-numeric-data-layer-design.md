# Numeric data layer (P2): yield and price norms that prefill the budget form

Status: proposed
Date: 2026-08-17
Follows: `2026-08-17-budget-form-design.md` (P1, merged as `26fa006`)

P1 answers a money question from four numbers the user types. Three of the seven
frozen budget questions ask instead for a market norm — *"Buğday ekmenin dekara
maliyeti nedir?"*, *"Fındık bahçesi kurmak kaç para tutar?"*, *"Girdi masraflarım
ne kadar olur?"* — and the sales pitch promises an **average** profit and a
history of what performed well. None of that is answerable from the user's own
figures alone.

This spec adds the data. Province × crop × year yield and producer price, held in
a committed file, used to **prefill the same form** P1 already built. The wire
format, the card and the arithmetic do not change shape: P1 reserved `value` and
`source` on every field for exactly this.

---

## 1. Purpose & success criteria

1. A farmer who selects a crop and has a province sees the form's yield and price
   fields already filled, each showing which year and which region it came from.
2. Every prefilled figure is overwritable, and the moment the user edits it the
   figure becomes theirs.
3. No missing datum is ever silently rendered as zero.
4. The answer never presents a regional average as a prediction about this
   farmer's field.
5. The route still makes no model call and no corpus retrieval, so P2 is verified
   entirely by `pytest`.

## 2. Scope

**In scope**

- `data/crop_norms.json` — province × crop × year yield (kg/da) and producer price
  (TL/kg), with provenance
- `scripts/build_crop_norms.py` — converts a TÜİK export into that file
- `src/norms.py` — lookup with an explicit fallback and provenance
- Prefill wiring into `budget.form_spec`, a `kg/dekar` unit on the yield field,
  and a second framing sentence
- The crop field becoming a real, explicit selection

**Out of scope — separate work**

- P4, `crop_choice` naming a crop from history. The same file will feed it, which
  is why the schema stores a multi-year series rather than one year, but the
  decision mechanism is its own spec and it reverses a shipped decision.
- P3, fertilizer quantity. Unrelated, and blocked on a catalog data gap.
- An input-cost norm. TÜİK's `Tarımsal Girdi Fiyat Endeksi` is an **index**, not a
  cost in lira; the cost field stays the user's.
- Any automated fetch at runtime. See §4.

## 3. What P2 breaks in P1, and must fix

P1 appends this sentence by code:

> "Bu hesap bir tahmindir ve **tamamen sizin girdiğiniz rakamlara dayanır**;
> fiyat veya verim öngörüsü değildir."

The moment a norm prefills a field, that sentence is **false**. It is the kind of
error that survives review because it still reads plausibly: the sentence is
present, well-formed, and wrong.

So the framing branches on whether any figure came from a norm — see §8. This is
not a nicety; it is the difference between "here is your arithmetic" and "here is
a regional average dressed as your arithmetic".

## 4. Architecture

```
scripts/build_crop_norms.py   TÜİK export  ->  data/crop_norms.json     (offline, manual)
data/crop_norms.json          committed, reviewable, diffable
src/norms.py                  lookup(crop, province) -> values + provenance
src/budget.py                 form_spec(errors, prefill=None); a per-area unit; two framings
```

**The data is a file, not a fetch, and that was measured rather than assumed.**
Reconnaissance on 2026-08-17 established:

- TÜİK's download endpoint works — `veriportali.tuik.gov.tr/api/tr/data/downloads`
  returned a 53 KB legacy `.xls` (OLE2, magic `d0cf11e0`) for the 2025 crop
  production bulletin — **but only with a browser session**. The same URL over
  plain HTTP returns **403**.
- MEDAS (`biruni.tuik.gov.tr/medas/`) is the queryable database, with a `Düzey`
  (geographic level) selector, and it carries both `Bitkisel Üretim İstatistikleri`
  and `Tarımsal Ürün Fiyatları ve Üretim Değerleri`. That second dataset is actual
  prices, not the `Tarım Ürünleri Üretici Fiyat Endeksi`, which is an index and is
  the wrong instrument for us. MEDAS is a ZK application and did not respond to
  scripted interaction.
- The portal names SDMX but no working endpoint was found (`/sdmx`, `/api/sdmx/*`
  → 404).

Both routes therefore resist automation, and the data is published **once a year**
(the 2025 bulletin is dated 26 December 2025). A fetcher would carry real
fragility for almost no freshness. This project has already paid for a silent
bootstrap failure once — a store that could not be downloaded became a corpus a
tenth the size, and the fix was to make the exit code a contract.

A committed file also matches how this repo already treats reviewable data
(`data/fertplan_table.json`) and makes each norm's year and region visible in a
diff.

## 5. The data file

Illustrative shape, abbreviated to five years and one crop. Every value below is
made up except the yield bulletin number, which was observed; the real years,
crops and figures come from the export obtained in the plan's first task (§11).

```json
{
  "meta": {
    "generated": "2026-08-17",
    "years": [2021, 2022, 2023, 2024, 2025],
    "sources": {
      "yield": {"name": "TÜİK Bitkisel Üretim İstatistikleri",
                "bulletin": "53939", "published": "2025-12-26"},
      "price": {"name": "TÜİK Tarımsal Ürün Fiyatları ve Üretim Değerleri",
                "published": null}
    }
  },
  "crops": {
    "domates": {
      "label": "Domates",
      "yield_kg_da": {"scope": "il", "Manisa": [5900, 6000, null, 6300, 6500],
                      "TR": [5500, 5600, 5700, 5800, 5900]},
      "price_tl_kg": {"scope": "tr", "TR": [3.10, 4.20, 6.05, 9.40, 12.40]}
    }
  }
}
```

**Which crops the file covers is decided by the export, not chosen here.** Task 1
records what the source actually carries; the set is then narrowed to crops this
product serves. Committing to a crop list before seeing the data would be the same
mistake as committing to the schema.

- **One shared year axis** in `meta`; every series is an array aligned to it, with
  `null` for a missing year. This keeps the file small and makes P4's "last five
  or ten years" a slice rather than a query.
- **`scope` is per measure, not per value.** Yield may have province rows while
  price has only a national one; the data states which, rather than the code
  guessing.
- **`TR` is always present** on both measures — it is the fallback row.
- **Province keys use the canonical spelling in `location.PROVINCES`.** A test
  pins this: `"Afyon"` instead of `"Afyonkarahisar"` would not raise, it would
  silently never match, which is the failure mode this project keeps meeting.

Rough size at 20 crops × 81 provinces × 10 years: under 200 KB. Committable.

## 6. Lookup and fallback

```python
@dataclass(frozen=True)
class NormValue:
    amount: float
    year: int
    scope: str      # "il" | "tr"
    region: str     # "Manisa" | "Türkiye"

@dataclass(frozen=True)
class CropNorm:
    crop: str
    yield_kg_da: NormValue | None
    price_tl_kg: NormValue | None

available_crops() -> tuple[tuple[str, str], ...]        # (id, label) for the select
lookup(crop: str, province: str | None) -> CropNorm | None
```

Resolution order, and nothing beyond it:

1. The named province's row, if the measure's `scope` is `il` and the row exists.
2. Otherwise the `TR` row, reported as `scope="tr"`, `region="Türkiye"`.
3. Within the chosen row, the most recent **non-null** year, and that year is
   carried on the value. A series whose latest entry is null reports the older
   year it actually used — "TÜİK 2023", not "TÜİK 2025".
4. A series that is entirely null yields no norm for that measure.

**No interpolation, no neighbouring-province average, no carrying a national
figure forward as if it were provincial.** Each of those would produce a number
nobody published.

`src/norms.py` imports nothing from `src/engine.py`, the same boundary
`src/budget.py` keeps. Validating province spellings against `location.PROVINCES`
is left to the test, because `location` imports `engine._normalize_tr` and a data
lookup has no business dragging the engine in.

`_load` is cached for the process and swallows everything: a missing file, invalid
JSON, a wrong top-level type, or a series of the wrong length yields an empty
table. A broken data file must not break answering.

## 7. Prefill, and the per-area unit

P1's form asks for the **total** harvest, deliberately: a farmer who took 2 tons
off 5 dönüm holds "2 ton" in mind, not "400 kg/da". But TÜİK's norm is per dekar,
and the total cannot be derived until the area is known.

Resolved by giving the yield field a third unit rather than new machinery:

```
Ürün miktarı:  [ 650 ]  [ kg | ton | kg/dekar ]
```

**The field's label changes from P1's "Toplam ürün" to a neutral one.** Once the
field can hold a per-dekar figure, "toplam" is wrong for two of its three units,
and a label that contradicts the selected unit is exactly the kind of mismatch the
unit selector exists to prevent. The placeholder and helper text follow the same
rule: they must read correctly under every unit the field offers.

`UnitOption` gains `per_area: bool`, and the conversion generalises to one line:

```
yield_kg = value × factor × (area_da if unit.per_area else 1)
```

A norm prefills as `650 kg/dekar` — the form the source states it in — and the
farmer sees their own total derived in the restated line. Switching the chip back
to `ton` and typing a total reproduces P1's behaviour exactly.

`form_spec` grows an optional prefill argument and one additive wire field:

```
form_spec(errors, prefill=None)
field: { …, "value": "650", "source": "norm", "source_note": "TÜİK 2025, Manisa" }
```

`source_note` is new; `value` and `source` were already on the wire in P1 and
shipped empty. **A prefill is a default, never a lock:** a submitted value is
always `source: "user"`, even where a norm existed.

The crop field becomes a real selection, populated from `available_crops()`, plus
a "diğer" option that prefills nothing. P1 left `crop` deliberately unwired
because the mobile profile stores `crops` as free text naming several crops, and
dropping that into a single-crop slot would be guesswork. A selection is not a
guess.

## 8. Framing

Two sentences, both appended by code and never asked of a model:

- **No norm used** — P1's sentence, unchanged, byte for byte.
- **A norm used** — names which figures are not the user's, gives the source and
  year, and states plainly that a regional average is not a prediction about this
  field. A provincial mean yield is a central tendency across every holding in the
  province; presenting it without that sentence invites it to be read as a
  forecast for one parcel.

## 9. Error handling

| Situation | Behaviour |
| --- | --- |
| File missing or malformed | Empty table; no prefill; the form behaves exactly as P1 |
| Crop absent from the table | No prefill. The select is built from `available_crops()`, but the server validates independently |
| Province row absent | `TR` fallback, reported as such |
| No province known at all | `TR` fallback. The province is never guessed |
| Latest year null | Walk back to the most recent non-null year and carry that year |
| Whole series null | No norm for that measure |
| `kg/dekar` selected without an area | A field error, not a silent zero |

**The binding rule: a missing norm never becomes 0.** A zero flows into the
arithmetic and produces a confident wrong answer, which is the P2 form of the
defect class P1 exists to prevent.

## 10. Testing

Everything is `pytest`. No network, no LM Studio, no vector store, no eval run.

| Group | What it pins |
| --- | --- |
| Schema validity | every province key is in `location.PROVINCES`; every crop has a `TR` row on both measures; every series length equals `len(meta.years)` |
| Label consistency | the yield field's label and helper text contain no word that is wrong under one of its units — no "toplam" while `kg/dekar` is offered |
| `_load` robustness | missing file, malformed JSON, wrong top-level type, wrong-length series → empty or skipped, never raised |
| Fallback | province present → `il`; absent → `tr`/"Türkiye"; province unknown → `tr` |
| Year walk-back | latest year null → the most recent non-null value **and its year** |
| No invention | an all-null series returns no norm, **not** 0 |
| Prefill wire | with a prefill: value, `source: "norm"`, `source_note`; **without a prefill the output is byte-identical to P1's** |
| User wins | a submitted value is `source: "user"` even where a norm existed |
| Per-area unit | `kg/dekar` × area equals the equivalent total entered directly; the unit without an area is a field error |
| Framing branch | norm used → the norm sentence; none used → P1's exact sentence; both code-appended |
| Converter | a small fixture export produces the expected JSON; a row with an unparseable number is skipped loudly, never zeroed |

No eval case is added. The route makes no model call, so a case here would read
green while asserting nothing — the vacuity class this project has shipped before.

## 11. Sequencing: the converter cannot be written first

The schema in §5 is a **proposal**, not a finding. Reconnaissance reached MEDAS's
topic list and the download endpoint, but not inside the query builder: whether
`Düzey` offers İl for these two datasets, and whether price carries province rows
at all, was **not** observed.

Therefore the implementation plan's first task is to **obtain a real export and
record its shape** — column names, units, whether province rows exist, which years
are covered, and the same for price. The converter is written against that file.
Any other order invents a schema and rewrites it when the data arrives.

If price turns out to have no province dimension, nothing in this design breaks:
`scope: "tr"` is already the declared way to say so, and the user already reads
which region each figure came from.

## 12. Where this sits

| | | Status |
| --- | --- | --- |
| P1 | budget calculator | done, merged `26fa006` |
| **P2** | **this spec** | **proposed** |
| P3 | fertilizer quantity for the user's field | blocked on a catalog data gap: 0 of 48 products carry a dose or an NPK analysis |
| P4 | `crop_choice` naming a crop from history | needs P2's series; reverses a shipped decision |

P2 answers the pitch's "ortalama kâr" and supplies the series the pitch's "geçmiş
5-10 yıl, şu tutmuş" needs, which is why it is the highest-value remaining piece.
