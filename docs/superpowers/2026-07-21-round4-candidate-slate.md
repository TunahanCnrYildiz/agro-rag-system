# Round-4 candidate slate — pre-registration

**Date:** 2026-07-21
**Branch:** `expand-corpus-fact-panel-round4`
**Spec:** `docs/superpowers/specs/2026-07-21-expand-corpus-fact-panel-round4-design.md`

This is the **round-4 pre-registration**. Every assertion below is FROZEN before
any run. Tasks 2–3 consume these rows in rank order and **may not invent
candidates outside this slate**. §2 records every source rejected at mining time
so round 5 does not re-mine the same dead ends.

**10 candidates**, below the budget of 15. That is the anticipated shortfall, not
a failure: the spec states up front that the easy vein is partly exhausted. The
binding constraint this round was again assertion QUALITY, not supply — 209
sources passed the conclusion-marker + value filter, 55 carried an own-voice
valued sentence, and almost all of those were results-table comparisons
("en yüksek X … uygulamasında belirlenmiştir") that fail the answer-naturalness
test. The slate was NOT padded to reach a number.

Legend: R1 = source not banned and not previously dropped · R2 = crop under the
absolute panel-wide cap of 2 · R3 = claim shape under its cap.

Rows 3, 4, 5 and 8 are the round-3 slate's **unmeasured** rows (7, 8, 9 and 10),
carried forward verbatim where the assertion is unchanged. They cost nothing to
re-mine and their round-3 rule checks still hold under round 4's rules.

---

## 1. The slate

### 1. dp_19434 (2011) — düğün çiçeği (*Ranunculus asiaticus* 'Orange'), Antalya plastik sera

- **claim_shape:** organic-amendment (compost) dose — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (Ranunculus new to panel, 0 → 1; no slate-mate
  on this crop) · R3 pass (new shape, only row on the slate in this bucket)
- **proposed_query:** `Serada düğün çiçeği yetiştiriciliğinde dekara ne kadar kompost uygulamalıyım?`
- **frozen_answer_any:** `["8 ton/da", "8 ton da", "dekara 8 ton", "8 ton"]`
  (all four are notations of the SAME value — the paper writes it `8 ton da-1`)
- **frozen_context_any:** `["toprağa zarar vermeden örtüaltı düğün çiçeği",
  "kentsel katı atık kompostunun zengin mineral bileşimi"]`
- **source_quote:** "Sonuç Araştırma sonuçlarına göre, söz konusu kompostun farklı
  dozlarının verim ve kalite özellikleri üzerinde kontrole göre artış gösterdiği
  ve **8 ton da-1** uygulama dozunun toprağa zarar vermeden örtüaltı düğün çiçeği
  yetiştiriciliğinde başarıyla kullanılabileceği saptanmıştır."
- **Answer-naturalness:** a grower asking how much compost to spread is answered
  with a per-dekar rate. It is the paper's own unconditioned recommendation
  sentence, not a results-table cell.
- **Recorded risk:** 8 ton da-1 was also the HIGHEST dose tested, so the
  *direction* ("more is better") is guessable; the number itself is not.

### 2. dp_19600 (2005) — ayçiçeği (*Helianthus annuus*), Ankara

- **claim_shape:** seed pre-treatment dose — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (sunflower new to panel, 0 → 1) · R3 pass
- **proposed_query:** `Ayçiçeğinde ekim öncesi tohuma humik asit uygulaması hangi dozda yapılmalı?`
- **frozen_answer_any:** `["60 g", "60 gram", "60 g/100 kg", "60 g ha"]`
  (notations of the same dose; `_matches`'s digit-guard keeps "60 g" out of "160 g")
- **frozen_context_any:** `["ekimden önce ayçiçeği tohumlarına uygulanabileceği",
  "60 g HA/100 kg tohum ile muamele edilmesinin"]`
- **source_quote:** "Ayrıca, HA uygulamalarının hem kök hem de fide gelişimini
  olumlu yönde etkilediği ve **100 kg tohuma 60 g humik asit** dozunun ise ekimden
  önce ayçiçeği tohumlarına uygulanabileceği sonucuna varılmıştır."
- **Answer-naturalness:** a seed-treatment rate is exactly what a "hangi dozda"
  answer states. **Strongest row on the slate:** the doses tested were 60/120/180
  and the LOWEST won, so "more is better" gives the wrong answer — the corpus has
  to carry it.

### 3. dp_1338811 (2023) — Muş lalesi (*Tulipa sintenisii*)

*(round-3 slate row 7, unmeasured — carried forward verbatim)*

- **claim_shape:** storage condition (panel 2 → 3 — **SHAPE NOW AT CAP**)
- **Rule check:** R1 pass · R2 pass (tulip new, 0 → 1) · R3 pass at the cap; this
  is the ONE storage row rule 3 allows, so no other storage candidate may ship.
- **proposed_query:** `Muş lalesi soğanlarını söküm sonrası yaz boyunca nasıl saklamalıyım?`
- **frozen_answer_any:** `["oda sıcaklığ", "25 °c", "25 0c", "25°c"]`
  (the paper writes "oda sıcaklığında (yaklaşık 25 0C'de)" — one claim, two notations)
- **frozen_context_any:** `["kar örtüsü altında", "çıkış oranı kontrol uygulamasında"]`
- **source_quote:** "Muş lalesi'nin soğan gelişimleri ve bazı bitkisel
  özelliklerinin incelendiği çalışmada incelenen bütün özelikler bakımından en iyi
  sonuçlar soğanların yaz döneminde **oda sıcaklığında (yaklaşık 25 0C'de)**
  bekletildiği kontrol uygulamasından elde edilmiştir."
- **Why it should discriminate:** general knowledge says tulip bulbs need
  chilling; this paper found the OPPOSITE for *T. sintenisii* (emergence 93.3 % at
  room temperature vs 56.6 % / 46.6 % after 1–2 months cold). An ablated model is
  likely to recommend chilling.

### 4. dp_21749 (2009) — gül (rose), saksıda fidan

*(round-3 slate row 8, unmeasured — carried forward verbatim)*

- **claim_shape:** pot fertilizer dose (non-nitrogen) — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (rose new, 0 → 1) · R3 pass. Not a "nitrogen
  dose" row: the assertion is a per-pot rate of a humic compound fertilizer, so it
  does not consume that shape's single remaining slot.
- **proposed_query:** `Saksıda gül fidanı yetiştirirken hümik asitli kompoze gübreden saksı başına ne kadar vermeliyim?`
- **frozen_answer_any:** `["6 g/saksı", "6 g saksı", "6 g/bitki", "saksı başına 6 g"]`
  (the paper itself states the dose both as g/saksı and g/bitki — same value)
- **frozen_context_any:** `["gonca-çiçek sayısı", "yaprak kuru madde oranı"]`
- **source_quote:** "…özellikle **6 g/saksı**'lık gübre dozunda en olumlu sonuç elde
  edilmiştir." and "**6 g/bitki** gübre dozunun sağlıklı gül yetiştirmek ve en fazla
  sayıda çiçek elde etmek açısından en uygun doz olacağı sonucuna varılmıştır."
- **Recorded risk:** the paper also reports that 12 g/saksı DEPRESSED plant height.
  That is a supporting finding, not a competing recommendation.

### 5. dp_21704 (2012) — marul (lettuce)

*(round-3 slate row 9, unmeasured — carried forward verbatim, including its risk)*

- **claim_shape:** micronutrient dose — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (lettuce new, 0 → 1) · R3 pass
- **proposed_query:** `Marulda çinko eksikliği için topraktan kaç ppm çinko uygulanmalı?`
- **frozen_answer_any:** `["20 ppm"]`
- **frozen_context_any:** `["çinko sülfat", "baş boyu"]`
- **source_quote:** "Her iki uygulamada da marul bitkisinin gelişimi ve beslenmesi
  topraktan **20 ppm** (ZnT2) ve yapraktan % 0.20 (ZnY2) dozlarının önerilebileceği
  sonucuna varılmıştır." Corroborated by the paper's own results section:
  "…en etkili çinko dozunun topraktan 20 ppm çinkonun uygulandığı ZnT2 uygulaması
  olduğu belirlenmiştir."
- **RISK, recorded before running:** the ÖZ states the same verdict in CODED form
  ("ZnT2, ZnY2 seviyeleri … önerilebilir"); only the conclusions spell out
  "20 ppm". If retrieval lands on the abstract chunk the number never enters
  context. This is why it is ranked 5 and not higher.

### 6. dp_19511 (2008) — Marsh Seedless altıntop (grapefruit), Antalya

- **claim_shape:** rootstock recommendation — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (grapefruit/citrus new to panel, 0 → 1) · R3 pass
- **proposed_query:** `Antalya koşullarında Marsh Seedless altıntop için hangi anaç önerilir?`
- **frozen_answer_any:** `["carrizo", "carrizo sitranj", "carrizo citrange"]`
  (three notations of the SAME rootstock name — not a broadening)
- **frozen_context_any:** `["Marsh Seedless altıntopu için Carrizo sitranjı anacı",
  "en iyi ağaç gelişimi ise turunç anacı"]`
- **source_quote:** "Sonuç olarak incelenen tüm faktörler göz önüne alındığında
  bölgemiz koşullarında yetiştirilen Marsh Seedless altıntopu için **Carrizo
  sitranjı** anacı, en iyi sonucu vermiştir."
- **RISK, recorded before running:** Carrizo citrange is an internationally famous
  citrus rootstock a model may name with an EMPTY corpus — the
  `local_avocado_antalya` failure mode. Ranked below the dose rows for exactly
  this reason. Do NOT retune it green if it reads model-carried; record and drop.
- **Anchor note for Task 2:** the paper's literature review cites Carrizo
  repeatedly, so both anchors above were chosen from the paper's OWN verdict and
  results sentences. Verify uniqueness case-insensitively before running.

### 7. dp_19468 (2009) — M19 salkım domates (tomato), Antalya sera

- **claim_shape:** training-system choice — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (tomato at 0 corpus_fact cases → 1; the
  existing `tomato_disease_organic` is NOT a corpus_fact case and consumes no
  slot) · R3 pass
- **proposed_query:** `Serada salkım domateste hangi terbiye sistemi ve dikim sıklığı önerilir?`
- **frozen_answer_any:** `["atlatma", "atlatma sık"]`
- **frozen_context_any:** `["atlatma sık dikim uygulamasının üreticiye tavsiye",
  "karşı telin üzerinden atlatarak"]`
- **source_quote:** "Sonuç olarak salkım domates yetiştiriciliğinde **atlatma sık
  dikim** uygulamasının üreticiye tavsiye edilebilecek bir terbiye sistemi olduğu
  tespit edilmiştir."
- **Answer-naturalness:** "atlatma" is a Turkish-specific greenhouse training term
  a model has little reason to emit unaided — good discrimination.
- **Recorded risk:** the results section names "kontrol sık dikim" as the
  highest-YIELD treatment while the conclusion recommends "atlatma sık". This is
  the `technique_grape_bud_load` structure (a table-conditioned figure vs an
  unconditioned conclusion), which SHIPPED — not the guar-bean either/or. Flagged
  so Task 2 does not mistake it for a contradiction.

### 8. dp_19517 (2007) — mısır (maize), ikinci ürün doğrudan ekim

*(round-3 slate row 10, excluded that round as a same-crop alternate — now eligible)*

- **claim_shape:** sowing-implement choice — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (maize 1 → 2, AT the absolute cap; no further
  maize case may ever be added) · R3 pass
- **proposed_query:** `İkinci ürün mısırın doğrudan ekiminde hangi gömücü ayak tipi daha iyi çıkış sağlar?`
- **frozen_answer_any:** `["çift disk", "çift diskli"]`
- **frozen_context_any:** `["çıkış oranı indeksi", "yan tekerlek"]`
- **source_quote:** "Sonuç olarak, bu araştırmanın yürütüldüğü iklim ve toprak
  koşulları için, ikinci ürün mısırın doğrudan ekiminde, daha yüksek tarla filiz
  çıkış oranı ve çıkış oranı indeksi ve daha düşük ortalama çıkış süresi için
  **çift diskli gömücü ayak** ve yan tekerlek olarak adlandırılan derinlik ayar ve
  kontrol sistemi kullanılması önerilmektedir."
- **RISK, carried from round 3:** double-disc openers are standard no-till
  practice; a plausible model-carried outcome. Kept as map data, ranked low.

### 9. dp_257759 (2016) — Macar fiği + yem bezelyesi (forage legumes)

- **claim_shape:** irrigation level — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass (distinct from the dropped `dp_257760` guar-bean and
  `dp_30458` vetch-phosphorus sources — different documents, different claims) ·
  R2 pass (rangeland/forage 1 → 2, AT the absolute cap) · R3 pass
- **proposed_query:** `Macar fiği ve yem bezelyesinde kurak dönemde hangi toprak nem seviyesinde sulama yapmalıyım?`
- **frozen_answer_any:** `["%75 tarla kapasitesi", "% 75 tarla kapasitesi",
  "tarla kapasitesinin %75"]`
- **frozen_context_any:** `["en yüksek ot verimleri için",
  "tarla kapasitesinin %25'ine düşmesine sebep olan kuraklıklar"]`
- **source_quote:** "Kurak dönemlerde sulama gerektiğinde ise en yüksek ot
  verimleri için **%75 tarla kapasitesi** seviyesinde sulama yapıldığında elde
  edildiği sonucuna varılmıştır."
- **RISK, recorded before running:** "75 % of field capacity" is a fairly generic
  irrigation-scheduling figure; model-carried is plausible. Ranked low.

### 10. dp_19426 (2011) — asma (grape), aşı kaynaşması, Tekirdağ

- **claim_shape:** graft-material state — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (grape 1 → 2, AT the absolute cap) · R3 pass
- **proposed_query:** `Asma aşısında anaç çeliği ve kalem hangi sürme durumunda olmalı?`
- **frozen_answer_any:** `["sürmüş çelik", "sürmemiş kalem"]`
- **frozen_context_any:** `["sürmüş çelik X sürmemiş kalem",
  "aşı kaynaşma özellikleri üzerine"]`
- **source_quote:** "Sonuç olarak **sürmüş çelik X sürmemiş kalem** durumunun aşıda
  kullanılması önerilebilir."
- **RISK, recorded before running:** dp_19448 and dp_19471 are the same research
  group on the same graft combination (with UV-C). Retrieval may land on either,
  so **anchor uniqueness must be checked hard** before running — this is the
  round-3 lesson that put anchor uniqueness first in the validation order.
  Ranked last for this reason.

---

## 2. Slate-wide self-check (Step 4 — counted, not glanced)

**Crop distribution (10 rows, 10 distinct crops):**

| Crop | Panel now | Slate rows | Panel after | Verdict |
|---|---|---|---|---|
| düğün çiçeği (Ranunculus) | 0 | 1 | 1 | OK |
| ayçiçeği (sunflower) | 0 | 1 | 1 | OK |
| Muş lalesi (tulip) | 0 | 1 | 1 | OK |
| gül (rose) | 0 | 1 | 1 | OK |
| marul (lettuce) | 0 | 1 | 1 | OK |
| altıntop (grapefruit/citrus) | 0 | 1 | 1 | OK |
| domates (tomato) | 0 | 1 | 1 | OK |
| mısır (maize) | 1 | 1 | 2 | OK, AT CAP |
| yem bitkisi / rangeland-forage | 1 | 1 | 2 | OK, AT CAP |
| asma (grape) | 1 | 1 | 2 | OK, AT CAP |

- **Pear appears ZERO times.** ✔
- **No crop reaches 3 panel-wide.** ✔ Three rows sit exactly at the cap of 2
  (maize, forage, grape); the other seven take a crop from 0 to 1.
- **No crop appears twice on the slate**, so no slate-mate can breach a cap even
  if every row ships. ✔

**Claim-shape distribution:**

| Shape | Panel now | New allowed | Slate rows | Verdict |
|---|---|---|---|---|
| self-fertility verdict | 4 | 0 | **0** | ✔ |
| storage duration / condition | 2 | 1 | **1** (row 3) | ✔ at cap |
| nitrogen dose | 2 | 1 | **0** | ✔ |
| resistant-cultivar list | 2 | 1 | **0** | ✔ |
| region-adapted cultivar rec. | 2 | 1 | **0** | ✔ |
| harvest timing / drying pretreatment / biocontrol list / min-diameter / bud load / sowing date | 1 each | 2 each | **0** | ✔ |
| organic-amendment (compost) dose | 0 | 3 | 1 (row 1) | ✔ |
| seed pre-treatment dose | 0 | 3 | 1 (row 2) | ✔ |
| pot fertilizer dose | 0 | 3 | 1 (row 4) | ✔ |
| micronutrient dose | 0 | 3 | 1 (row 5) | ✔ |
| rootstock recommendation | 0 | 3 | 1 (row 6) | ✔ |
| training-system choice | 0 | 3 | 1 (row 7) | ✔ |
| sowing-implement choice | 0 | 3 | 1 (row 8) | ✔ |
| irrigation level | 0 | 3 | 1 (row 9) | ✔ |
| graft-material state | 0 | 3 | 1 (row 10) | ✔ |

Nine of ten rows open a brand-new shape bucket. That is a direct consequence of
rule 3: every shape the panel already uses is at or near its cap, so the only
headroom left is in new shapes. Worth naming, because it means round 5 will have
these nine buckets partly filled and even less headroom.

**Source check:** none of the ten sources appears in the 16 banned panel sources,
the 9 measured-and-dropped sources, or round 3's mine-time rejection list. ✔

---

## 3. Rejected at mining time — do NOT re-mine

These were read and rejected BEFORE any candidate line was written.

**Recommendation sentence is CITED literature, not the paper's own voice:**

- `dp_19378` karnabahar/vermikompost — its "en uygun gübre miktarı … 20 kg N da-1,
  10 kg P2O5 da-1, 20 kg K2O da-1" sentence is **Eser ve ark. (1987)**, quoted in
  Materials to justify the base fertilization. The paper's own conclusion names no
  single actionable dose.
- `dp_21736`, `dp_21717` (partly), `dp_293435`, `dp_19598`, `dp_21705`,
  `dp_19391`, `dp_1053693`, `dp_30457`, `dp_19433` — key sentence is another
  author's finding.

**Fails the answer-naturalness test (value lives only in a results table):**

- `dp_1010297`, `dp_1066386`, `dp_1134317`, `dp_1185441`, `dp_1404009`,
  `dp_1419633`, `dp_1419657`, `dp_1420178`, `dp_1453157`, `dp_1869487`,
  `dp_19409`, `dp_19478`, `dp_19482`, `dp_19501`, `dp_19519`, `dp_19540`,
  `dp_19541`, `dp_19543`, `dp_19546`, `dp_19549`, `dp_19557`, `dp_19582`,
  `dp_19588`, `dp_19589`, `dp_19591`, `dp_19594`, `dp_21701`, `dp_21706`,
  `dp_21707`, `dp_21718`, `dp_21722`, `dp_21726`, `dp_21729`, `dp_21730`,
  `dp_238214`, `dp_297798`, `dp_30456`, `dp_1584091` — all are
  "en yüksek/en düşük X … Y uygulamasında belirlenmiştir" range reports. This is
  the single largest rejection class, and the reason the slate is 10 and not 15.

**Ambiguous / multi-valued assertion (the guar-bean class — greening it needs a
DIFFERENT claim):**

- `dp_19431` aspir + humik asit — genuinely multi-valued by timing: 18 g/da to the
  soil at sowing, 12 g/da at the 4–5 leaf stage, 6 g/da later. No single value is
  *the* answer.
- `dp_19415` çilek tüplü vs frigo fide — an explicit either/or: tüplü wins on
  earliness, frigo on total yield per plant.
- `dp_21717`/`dp_21736`/`dp_21737` fiğ+buğday "%70-30 karışım oranı" — the same
  value recurs in three sources, one of them citing another, so retrieval cannot
  be pinned to a single document; it also puts two capped crops (forage and wheat)
  at risk on one row.

**Known-dead structure or generic-knowledge value (would be measured only to
re-learn a recorded lesson):**

- `dp_19596` Biga ekmeklik buğday (Flamura, Dropia, Gelibolu) and `dp_19508`
  (Tosunbey, Flamura, Dropia) — **exactly the dropped `local_ege_durum_wheat`
  shape**: a 34-genotype roster in Materials plus a three-cultivar recommendation
  in the conclusion, so a green grounding would most likely be list-echo. The two
  sources also recommend overlapping trios, so retrieval collides between them.
  Not worth the ~10 minutes of local-model time to re-learn this.
- `dp_19493` Santa Rosa erik, damla sulama — the paper's own Introduction states
  that irrigation "generally commences as 30 or 40 % of available water is
  depleted", i.e. its own 40 % verdict IS the textbook value. Model-carried by
  construction.
- `dp_19404` örtüaltı muz derlemesi — a review; "15–16 °C" and "damla sulama en
  uygun sistemdir" are generic knowledge.

**Soft comparative verdict — no crisp assertable value:**

- `dp_1027549` topraksız marul, domates atığı ortamı — "iyi bir alternatif olduğu
  belirlenmiştir"; would also have been a second lettuce row.
- `dp_1714624` mor şeker mısır — conclusion resolves to "toprak analizine göre
  uzmana danışın"; the 15/12/0 kg da-1 figures are cited.
- `dp_1067105`, `dp_19425`, `dp_19469`, `dp_19492`, `dp_19562`, `dp_19379`,
  `dp_1625815` — "organik materyal toprağı iyileştirdi" class, no dose verdict.
- `dp_19477` nohut kurak çimlenme, `dp_19483` papaya, `dp_19605` safran,
  `dp_21744`, `dp_19560`, `dp_19534` — feasibility/observation verdicts only.

**Laboratory or in-vitro protocol, not a plant-care action:**

- `dp_1065707` (µM melatonin), `dp_1852107` (aspir mikroçoğaltım), `dp_1393380`,
  `dp_1081099`, `dp_19441`, `dp_19475`, `dp_19512`, `dp_19513`, `dp_19523`,
  `dp_21703`, `dp_21715`, `dp_21724`, `dp_1683423`, `dp_1428236`, `dp_1393986`.

**Out of project scope (chemicals) or not plant care at all:**

- `dp_1456609`, `dp_19568`, `dp_1159095`, `dp_1246295`, `dp_1799224` — insecticide
  / fungicide dose and mortality work.
- `dp_1419641` (koruyucu gaz karışımı), `dp_1419634` (kök kereviz MAP depolama),
  `dp_257762`, `dp_384605`, `dp_1031945` — food packaging / human nutrition.
- `dp_19535` (pamuk uydu görüntüsü), `dp_19397` (GPS alıcı), `dp_19384` (briket
  yakıt), `dp_19416` (biyogaz), `dp_21714`, `dp_30498`, `dp_1766147` — engineering
  / remote sensing.
- `dp_19385`, `dp_19387`, `dp_19417`, `dp_19418`, `dp_19428`, `dp_19453`,
  `dp_19462`, `dp_19463`, `dp_19496`, `dp_19498`, `dp_19529`, `dp_19536`,
  `dp_19569`, `dp_19571`, `dp_238140`, `dp_285028`, `dp_285638`, `dp_293243`,
  `dp_30455`, `dp_30466`, `dp_30477`, `dp_30484`, `dp_30538`, `dp_30539`,
  `dp_1000641`, `dp_1053386`, `dp_1451161`, `dp_1465646`, `dp_1514390`,
  `dp_1561509`, `dp_257756` — agricultural economics, policy, tourism, herbaria,
  gene-bank curation.
- `dp_19538`, `dp_19580`, `dp_19464`, `dp_19473`, `dp_19530`, `dp_1223378`,
  `dp_19389`, `dp_19457`, `dp_19572`, `dp_30464` — soil / greenhouse inventory
  surveys; they report ranges, never a recommendation.
- `dp_1010178`, `dp_1022541`, `dp_1052881`, `dp_285103`, `dp_285164`,
  `dp_1900979`, `dp_1018772`, `dp_1068346`, `dp_1464905`, `dp_1244455`,
  `dp_21700`, `dp_21711`, `dp_21723`, `dp_1494763`, `dp_1570912`, `dp_1485702`,
  `dp_19387` — faunistic/floristic surveys, characterisation studies, method
  papers.

**Grower-unnatural species:**

- `dp_19565` *Vitex madiensis*, Cameroon agroforestry shrub — same class as round
  3's `dp_19522` *Dalbergia sissoo* rejection.

**Held OUT deliberately (not a defect — a collision risk):**

- `dp_19448` and `dp_19471` — the same Tekirdağ group as slate row 10 (dp_19426),
  on the same graft combination with UV-C. Shipping one of these AND dp_19426
  would put two cases on one retrieval path. They are recorded here as dp_19426's
  anchor-uniqueness hazard, not as independent candidates.
