# P3 reconnaissance: the product pages DO carry a dose

Date: 2026-08-22
Answers the question the handoff left open: *"P3's first task is to check whether the product
pages carry a 'Kullanım Şekli / Dozu' section."*

**They do — 42 of 48 carry a dose per dekar.** The recorded blocker is wrong, and the reason it
was wrong is worth more than the correction.

## What was measured

All 48 `source_url`s in `docs/products/products.json` were fetched (48/48 succeeded, ~0.6 s apart).
Every page is a WooCommerce product rendered with Elementor **nested tabs**, and every one of the
48 carries exactly three:

| Tab | |
| --- | --- |
| `Açıklama` | the long description |
| `Uygulama (Yeri,Zamanı,Şekli,Dozu)` | **the dose** |
| `Döküman` | a registration certificate link |

The panels are **server-rendered in the HTML** — no JS, no AJAX. A button `#e-n-tab-title-N` pairs
with a div `#e-n-tab-content-N` by the shared numeric suffix. That pairing is the whole extraction.

## The result

| | of 48 |
| --- | --- |
| Per-area dose — litres or grams per dekar / per 1000 m² | **42** |
| Dilution only — an amount per N litres of water | 4 |
| No numeric dose at all | 2 |

Dilution-only: `HIGRO WETT`, `A.P.P® VIROXYN`, `HİGRO TRACO`, `ZİNCER`.
No dose: `HİGRO ABS` (defers to the label), `HİGRO® PİNK` (its Uygulama tab holds marketing prose).

38 of the 42 carry **both** a per-area dose and a dilution, because the same product is applied
two ways — from the leaf (diluted) and through drip irrigation (per dekar).

## Why the old measurement said zero, and why it was not wrong

The recorded figure — *"0 of 48 mention dekar/dönüm, 0 carry a numeric dose"* — was measured
against `products.json`'s **`description` field**, and re-measuring it confirms that exactly:

| Against the stored descriptions | |
| --- | --- |
| mention dekar / dönüm / 1000 m² | 2 |
| carry a per-area dose | **0** |
| average length | 143 chars |

The descriptions are marketing copy because `scraper._fetch_description` takes
`.woocommerce-product-details__short-description` and stops. It never opened the Uygulama tab —
nobody had asked it to.

**So the conclusion "not computable from what we hold at ANY level of review" was true of what we
held and false about what is obtainable.** The gap was in the scraper, not in the source. A
statement about our data got recorded as a statement about the world; that is the part to
remember.

## The unit the pages actually use, and the trap in it

The pages almost never write "dekar". They write **`/ 1000m²`**, and 1000 m² *is* one dekar. A
first pass searching for `dekar|dönüm` found **2** products; including `1000 m²` found 42.

Verbatim samples, all genuine:

```
HİGRO® FAST          100-200 cc/ 1000m²
HİGRO FUBBY          250 gr/ 1000m²
HİGRO BARF           2-2,5 litre / 1000m²
HIGRO 8 MN           1.000 m²) 2 – 2,5 litre
A.P.P – ORNE         3 Litre dekara
BİNGO                1000m² alan için damla sulama ile 2 – 2.5 litre
```

Note `1.000 m²` with a Turkish thousands dot, and the amount appearing on either side of the area.
Both cost a false negative on the first pass. The matcher has to accept `1000m²`, `1.000 m²`,
`1000 m2` and `da`, and it has to look both directions.

## What P3 still has to decide — the dose is not a single number

This is not "read a number and multiply". The shape of the data forces four decisions:

1. **Doses are per crop GROUP, not per crop.** 45 of 48 panels segment as *Sebzelerde / Meyvelerde
   / Tarla bitkilerinde*. There is no per-crop dose, so P2's crop selection does not key into this
   directly — something has to map a crop to its group, or the answer has to state the group.
2. **43 of 48 give a RANGE, not a figure** (`2 – 2,5 litre`). Multiplying a range by an area gives
   a range; collapsing it to one number invents precision the source does not have.
3. **A dose is per APPLICATION, and the season's total needs a count.** Only 8 of 48 panels state
   an interval or a number of applications. So "how much will I buy for the season" is *not*
   answerable for the other 40 — only "how much per application" is.
4. **The two application methods give different doses** (leaf vs drip) and the page does not
   choose for the farmer. Neither can we.

Also confirmed: **only 3 of 48 pages carry an NPK-looking triple and 7 any percentage.** So
converting an elemental recommendation (e.g. "16 kg of pure nitrogen per dekar") into a mass of
*this* product is still not possible from these pages. That half of the original blocker stands.

## What this means for P3's plan

The first task is no longer "find out whether the data exists". It is:

- extend `src/scraper.py` to capture the Uygulama panel alongside the description, keyed by the
  `e-n-tab-title-N` / `e-n-tab-content-N` pairing, and re-crawl;
- decide, with the user, what an honest answer looks like given constraints 1–4 above — most
  likely a per-application range for a named crop group, stating the group and the method, and
  refusing the season total rather than inventing an application count;
- keep the elemental→product conversion out of scope until a content analysis is obtainable.

The review gate from the earlier finding still binds and is unchanged by any of this: stating a
dose that the manufacturer published for their own product is quoting a source, not us authoring
an unconditioned recommendation for a farmer's field.

## Task 2: the panels are committed, and their grammars

All 48 `Uygulama` panels were fetched with `scripts/fetch_dose_panels.py` and committed unchanged
to `data/raw/product_panels.json`. 48/48 succeeded, no `FETCH FAILED`, and every panel came back
non-empty, 173-1523 chars.

The earlier measurement said 173-**1793**, and the difference is not site drift: the 1793-character
panel was `HIGRO 8 MN`, measured before the extractor learned to cut page furniture. Through
`extract_tab_panels` the same panel is **241 characters** — the other 1552 were the related-products
rail. The cut is working, and this is what it looks like from the outside.

Reading the panels shows at least three grammars, and the converter in Task 4 is written against
exactly this:

| Grammar | Example | Count |
| --- | --- | --- |
| Group-first, method inline | `Sebzelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, Damlamadan 250 gr/ 1000m² alana uygulanılır.` | ~42 |
| Method-first, uppercase, no group | `YAPRAKTAN: … DAMLAMA SULAMA: bir dekara (1.000 m²) 2 – 2,5 litre` | `HIGRO 8 MN` |
| Crop-named prose, no group heading | `Tahıllarda ve Hububatlarda kıraç üretimde dekara 200 cc yapraktan 2 uygulama yapılır.` | `FLY AZOT` |

**The colon after the group word is optional** — `HİGRO CUFİT` and `ZİNCER` write `Sebzelerde Yapraktan …` with no colon, and a pattern that requires one loses them.

Three panels fit none of the three rows cleanly, and each names a trap the converter has to survive:

- **`HİGRO FERRY`** puts the group word mid-sentence (`… ile sebzelerde 1000m² alana 1-2 litre`)
  rather than as a heading, and carries a typo — `To praktan` for `Topraktan`.
- **`HIGRO FERFORCE`** gives its fruit doses **per tree** (`ağaç başına 25-50 gr`), which is not a
  per-area figure and must not be read as one; and it splits its vegetable dose into greenhouse
  (`250 gr/ 1000m²`) and open field (`500 gr / 1000m²`).
- **`HİGRO ZİMOBOR`** opens with a CMS placeholder the firm left in the page: `Buraya uygulama`.

## Measured against the committed panels, before the converter was written

Running the plan's intended patterns over `data/raw/product_panels.json` established three things
that changed the plan:

1. **The comma is a clause boundary.** The panels write `Yapraktan … , Damlamadan …` as one
   sentence. Splitting on `.` and `;` alone leaves both halves in one clause and credits the drip
   figure to foliar.
2. **A dilution must disqualify its own figure, not the clause it sits in.** `HİGRO BARF` writes
   `Yapraktan uygulama ile 100 cc / 100 litre suya Damlama sulama ile 2-2,5 litre / 1000m² (da)`
   with no punctuation at all between the halves. Refusing the whole clause drops the catalog from
   **42 products to 10**.
3. **One product publishes two figures for one group and method** — `FLY AZOT`, 200 cc for dry
   farming and 250 cc for irrigated. Keeping the first silently chooses between two published
   numbers; the span they cover states both.

With all three applied, the per-area count over the committed panels is **42 of 48**, and the six
left out are exactly the four dilution-only products and the two with no dose.


## What the whole-branch review changed, 2026-08-22

The recon's headline figure was **42 of 48**. After the final review it is **40**, and every step
of the difference is a correction rather than a loss. The review compared shipped rows against the
pages they came from — something no test did — and found three wrong numbers in the committed file:

| Product | Page | Was shipped |
| --- | --- | --- |
| `HİGRO MATEN`, `HİGRO MATEN PLUS` | `Damlamadan 2 – 2,5 – 1 Litre// 1000m²` | `1,0 – 2,5 litre` (meyve: `1,0 – 4,0`) |
| `HİGRO ZİNCBOR` | `0,5kg – 1kg/ 1000m²` | `0,5 – 0,5 kg` |
| `HIGRO FERFORCE` sebze | greenhouse `250 gr` **and** open field `500 gr` | `250 gr` alone |

And two products were silently losing a whole crop group: `HİGRO ZİMOBOR` and `HİGRO EQUAJE` write
their `tarla` clause with no comma, and the dilution match spans the real dose, so stepping past the
match swallowed it. They still had rows for their other groups, so nothing reported it.

Four mechanisms came out of that:

1. **An unreadable number chain is refused, never salvaged.** `2 – 2,5 – 1 Litre` cost a wrong
   number **twice** — first by reordering a reversed pair into a range the page never states, then,
   after the reorder became a refusal, by the scan resuming and rescuing the trailing `1 Litre` as
   a single figure. Rescuing a fragment of an unreadable sequence is the same act as inventing one.
   MATEN and MATEN PLUS are now refused outright: **42 → 40**.
2. **A range may spell its unit on both sides.** Requiring it only after the second number
   collapsed `0,5kg – 1kg` to `0,5 – 0,5`, and `low == high` is indistinguishable from a genuine
   single figure.
3. **A rejected match resumes the scan after the amount, not after the match.** A dilution match
   routinely *contains* the real dose.
4. **A sub-qualified group is dropped and surfaced**, not silently reduced to one of its figures.
   `Sebzelerde : Seralarda: 250 gr … Tarla sebzelerinde … 500 gr` publishes two answers for one
   slot; picking either is a guess.

**The lesson under all of it:** the "42 of 48" invariant was used to prove every earlier fix safe,
and it was blind to all five defects. It counted PRODUCTS, not slots, and compared nothing to the
pages. A per-slot diff against the panels is the check that finds this class; a per-product count
is not.
