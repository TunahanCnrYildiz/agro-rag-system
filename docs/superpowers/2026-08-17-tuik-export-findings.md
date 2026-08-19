# What the TÜİK exports actually contain

Date: 2026-08-18
Task 1 of `docs/superpowers/plans/2026-08-17-crop-norms-data-layer.md`.
Answers the eight questions that task asks. The converter is written against
THIS, not against the illustrative schema in the spec.

Files obtained so far, both in `data/raw/`:

| file | rows | crops | years |
| --- | --- | --- | --- |
| `2016-2020.csv` |  397 | 80 | 2016-2020 |
| `2021-2025.csv` |  440 | 95 | 2021-2025 |

Both are the **`Tahıllar ve diğer bitkisel ürünler`** group only. See "Still
missing" at the end.

## 1. Does `Düzey` offer İl?

**Yes** — the option is named **`İBBS3 (İl Düzeyi)`**, not "İl". The full list is
Türkiye · İBBS1 · İBBS2 (26 Bölge) · İBBS3 (İl Düzeyi) · İlçe Düzeyi.
So `scope: "il"` is real for yield. Not yet established for price.

## 2. Column headers

Pipe-delimited, UTF-8 **with BOM**. Two header rows before the data:

```
|||Sütunlar|||…
Satırlar|||Adana-1|Adıyaman-2|Afyonkarahisar-3|Aksaray-68|…
```

Columns 0-2 are the row labels (group, crop, year); columns 3.. are the 81
provinces. **81 province columns present in both files** - verified by count.

## 3. The yield unit

`Kg/Dekar`, directly. **No derivation needed** - there is no need to divide a
production total by an area, because `Verim` is its own measure in MEDAS.

The crop label carries the measure, the code, the Turkish name and the unit:

```
Verim ve 01.11.11.00.00. (Durum Buğdayı) - Kg/Dekar
```

## 4. Price

**Not yet exported.** The `Tarımsal Ürün Fiyatları ve Üretim Değerleri` topic is
still outstanding, so nothing is known about its columns, its unit, or whether it
offers İBBS3.

## 5. Years covered

2016-2020 and 2021-2025, exactly. Split by year on purpose: the MEDAS report
limit is `gösterge × düzey × zaman ≤ 50000`, and 100 crops × 81 provinces × 10
years = 81.000. Five years fits at 40.500.

## 6. Province spelling

Every column matches `src/context/location.py:PROVINCES` after stripping the
`-<plaka>` suffix, **with one exception**:

| in the export | in PROVINCES |
| --- | --- |
| `Hakkari` | `Hakkâri` |

The converter needs a rename map with that single entry. Task 5's test exists to
catch exactly this class - a misspelled province does not raise, it silently
never matches.

## 7. Crops

96 distinct crops across the two files: 95 in 2021-2025, 80 in 2016-2020.
16 appear only in the later file (Kara Buğday, Keten Tohumu, Salep, Sudan Otu …)
and 1 only in the earlier one (Mahlut). The shared year axis with `null` gaps
handles this; the converter must UNION the crop sets, not intersect them.

## 8. Format

CSV, UTF-8 with BOM, delimiter `|`.

**Numbers use a DOT as the decimal separator: `176.0`, `1220.0`.** This is not
Turkish formatting. The plan's `_number()` assumed Turkish (`.` thousands, `,`
decimal) and would have turned `176.0` into `1760` - every yield ten times too
big, silently. The converter must parse these as plain floats.

64% of the data cells are blank (22.634 of 35.235 in the 2021-2025 file). That is
ordinary - not every crop is grown in every province - and each blank becomes
`null`, never 0.

## Still missing

- `Sebzeler` — 2 files (2016-2020, 2021-2025)
- `Meyveler içecek ve baharat bitkileri` — 2 files
- `Tarımsal Ürün Fiyatları ve Üretim Değerleri` — the whole price side

Without vegetables the budget form cannot prefill for tomato, which is the
crop most likely to be asked about.
