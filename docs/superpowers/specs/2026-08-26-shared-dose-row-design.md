# One published figure, two crop groups: the reviewed shared row

Status: proposed
Date: 2026-08-26
Follows: P3a `2026-08-22-product-dose-design.md`, and the reviewed-scope pattern it established
Scope: **one product, one group, one figure.** Measured, not assumed — see §1.

`HİGRO FERRY`'s panel publishes one figure for field crops **and** vegetables in a single sentence.
Our parser opens a segment on `sebzelerde` only, so a field grower asking about that product is told
we hold no readable figure — while the manufacturer published one. This spec closes that, with a
reviewed data override rather than a wider regex.

---

## 1. What the measurement says

Across all 48 panels, exactly **one** loses a crop group this way.

A scan compared, for every panel, the group words that appear in the text against the segments
`dose_parse._segments` actually opens. Two products came back:

- **`FLY AZOT` — a false positive.** Its only `tarla` occurrence is *"Eğer Holder **ile tarlaya**
  girilmeyecek…"* — the field itself, not the crop group. Nothing is lost.
- **`HİGRO FERRY` — the real one.** Its panel says, twice:

  > Tek yıllık **tarla ve endüstri bitkileri ile sebzelerde** 1000m² alana **1-2 litre**

What ships today:

| group | figure | correct? |
| --- | --- | --- |
| `sebze` | topraktan 1–2 litre | ✓ |
| `meyve` | yapraktan 2–3 litre | ✓ |
| `tarla` | — | ✗ the page publishes 1–2 litre for it |

**Today's answer is not a lie**, and that matters for how urgent this is: since the P3b review,
`no_dose_for_group` says *"elimde okunabilir bir dekar dozu yok"* — a claim about our data, not about
what the manufacturer published. So this is a coverage gap, not a false statement.

## 2. Why not teach the parser

P3a recorded the trap: widening the `tarla` pattern to span intervening words also swallows
`Tarla sebzelerinde` in `HİGRO FERFORCE`, which is a **vegetable** sub-case, not a field-crop
heading. A general "A ve B ile C'de" reader is a permanent maintenance surface and a regression risk
across all 48 panels — bought for one figure on one page.

The converter already reports every panel it cannot parse, loudly and by name, so a second product
carrying this construction announces itself rather than disappearing. If that ever happens more than
once or twice, the parser becomes the right answer; today it is not.

## 3. Where the review lives

`data/dose_group_scope.json` gains a second section. It is not a new file, because it answers the
same question the existing `scope` section answers — **which crop groups does this published figure
cover?** — for a case no regex can settle. One review surface, one review date, one reviewer.

```json
"shared_rows": {
  "HİGRO FERRY": {
    "from": "sebze",
    "also": ["tarla"],
    "expect_methods": ["toprak"],
    "evidence": "Panel iki kez 'Tek yıllık tarla ve endüstri bitkileri ile sebzelerde ... 1000m² alana 1-2 litre' diyor. Cümle iki grubu birlikte sayıyor; _segments yalnızca 'sebzelerde' üzerinden segment açtığı için tarla figürsüz kalıyor."
  }
}
```

## 4. What gets copied, and the guard against silent widening

The source group's methods are copied to each named group.

**`expect_methods` is the reviewer's own record of what they saw**, and the converter **raises** when
the source group's method set no longer matches it. That is the whole point: a panel edit that gives
`HİGRO FERRY`'s `sebze` block a second figure must not silently widen a row a person approved on the
strength of one sentence. A human re-reads instead.

Today `sebze` carries exactly one method (`toprak`), so `expect_methods` is `["toprak"]`.

## 5. Staleness, three ways

The converter raises when a `shared_rows` entry names:

1. a product that no longer ships,
2. a `from` group that product no longer carries,
3. an `also` group that **already has its own row** — which also disposes of the degenerate entry
   where `also` names the `from` group itself, since that group has a row by definition.

The third is the one worth stating plainly: if the parser ever learns to read the coordination
itself, this override becomes redundant, and it must announce that rather than silently overwrite a
row the page published under its own heading.

## 6. Where it is applied

In the converter, beside the existing `hepsi` scope gate — so `src/doses.py` and `lookup()` need no
new logic at all, and every consumer sees an ordinary row.

`data/product_doses.json`'s `meta` records the copy under `shared_rows`, so a reader diffing the file
can tell that `HİGRO FERRY`'s `tarla` row was **copied by review** rather than published under its
own heading. Precedent: the same file already records `unparsed`, `dropped_slots` and
`all_groups_scope` for exactly this reason — the finding travels with the data.

## 7. What the answer does NOT say

Considered and declined: a sentence telling the farmer this figure is one the page states for
vegetables and field crops together. The dose answer already attributes the figure to the
manufacturer's own page, and the figure genuinely *is* what that page says for field crops. An extra
clause adds words without adding anything the farmer can act on. The evidence lives in the review
file, where a maintainer will look for it.

## 8. Testing

Everything is `pytest`, no network.

| Group | What it pins |
| --- | --- |
| The copy | a reviewed entry gives the `also` group the `from` group's methods, values unchanged |
| The guard | a source group whose methods differ from `expect_methods` RAISES |
| Staleness | each of §5's three cases RAISES, distinguishably |
| Inertness | with no `shared_rows` section, the converter's output is unchanged |
| Real data | `lookup("HİGRO FERRY", "tarla")` returns the 1–2 litre `toprak` figure, and `sebze` and `meyve` are byte-identical to what they are today |
| Reproducibility | re-running the converter over the committed inputs reproduces the committed file |

## 9. Out of scope

- **Teaching `dose_parse` the coordination** (§2).
- **Any change to `src/doses.py`, the wire, the form or the client.** No new APK is needed.
- **`FLY AZOT`'s merged `200–250 cc` span**, decided 2026-08-25 to stay as it is: both ends are on
  the page, and the sentence qualifying 200 names no crop.

## 10. Where this sits

| | | Status |
| --- | --- | --- |
| P3a | product dose data | done, `cafa526` |
| P3b | the dose route and card | done, `14d93fb` |
| **this** | **the reviewed shared row** | **proposed** |
