# Round-3 candidate slate — durable record

**Date:** 2026-07-20
**Branch:** `expand-corpus-fact-panel-round3`

This is the committed, durable copy of the round-3 mining slate. The live slate
was authored as uncommitted scratch (per the plan's item-1 precedent) and would
not survive the branch; the mine-time rejection list from Task 1 §6 lived only in
`.superpowers/sdd/task-1-report.md`, which is gitignored. Both are preserved here
so a later round does not re-chase the same dead ends or re-mine the same veins.

## Outcome of each slate row (from task-2-report.md and task-3-report.md)

The 10-row slate was consumed in rank order. Final disposition:

| # | source | crop | outcome |
|---|---|---|---|
| 1 | dp_21741 | durum wheat | **DROPPED after measurement** — `--faithfulness` read a textbook `corpus-carried` (normal 4/4, ablated 0/4), but the mandatory normal run read **`ctx=False`**: retrieval never lands on the conclusion chunk, only the methods roster, so grounding fired on a twelve-cultivar list-echo. This is the artifact class that forced the normal-run ctx check. NOT shipped. (Its wheat crop slot was therefore freed again.) |
| 2 | dp_1514564 | safflower | **SHIPPED** as `local_diyarbakir_safflower` — corpus-carried, normal 4/4 ablated 0/4, normal run ret=True ctx=True. |
| 3 | dp_30474 | raspberry | **SHIPPED** as `local_oltu_raspberry` — corpus-carried, normal 4/4 ablated 0/4, normal run ret=True ctx=True. |
| 4 | dp_1559843 | chickpea | **SHIPPED** as `local_chickpea_blight_cultivars` — corpus-carried, normal 4/4 ablated 0/4, normal run ret=True ctx=True after a context-anchor realignment (yield-trait anchors repointed to the disease-scale verdict). |
| 5 | dp_21712 | pea | **DROPPED after measurement** — `_classify` **retrieval-broken** (normal 0/4, ablated 0/4). Not a plumbing failure: "22 Kasım" is in context, but the same document cites a competing point date (Soya ve ark. 1989, "25 Ekim") and the model recites the citation instead of the paper's own verdict. Guarbean rule; not retuned. |
| 6 | dp_21713 | maize | **SHIPPED** as `technique_maize_sowing_date` — corpus-carried, normal 4/4 ablated 0/4, normal run ret=True ctx=True. Its frozen `context_any` `["maverick", "c-955"]` was found non-unique (maverick also in fao_bt155e, c-955 also in dp_21696) and replaced BEFORE the first run with three source-unique phrases. |
| 7 | dp_1338811 | tulip (Muş lalesi) | **UNMEASURED** — the stopping rule fired at 4 shipped (rows 2, 3, 4, 6). Slate entry intact and re-usable. Storage-condition shape was at cap of 3 either way. |
| 8 | dp_21749 | rose | **UNMEASURED** — stopping rule. Slate entry intact and re-usable. |
| 9 | dp_21704 | lettuce | **UNMEASURED** — stopping rule. Carries a pre-registered risk: the verdict is stated in coded form (ZnT2/ZnY2) in the abstract and spelled out as "20 ppm" only in the conclusions, so it may be retrieval-broken if untested. |
| 10 | dp_19517 | maize | **EXCLUDED, not measured** — an alternate to row 6, not a peer. Both are maize; shipping both would rebuild the same-crop concentration this round exists to break. Row 6 shipped, so row 10 is excluded by its own slate condition. |

**Net: 4 shipped (rows 2, 3, 4, 6), 2 dropped after measurement (rows 1, 5),
3 left unmeasured by the stopping rule (rows 7–9), 1 excluded as a same-crop
alternate (row 10).** Round-3 corpus-carried total: 4 of 4 — stopping rule met.

---

## The slate (verbatim from the scratch `slate.md`)

# Round-3 candidate slate — corpus_fact panel

10 candidates, ranked. Tasks 2–4 consume in order and may not invent candidates
outside this slate. Every assertion below is FROZEN before any run.

Legend: R1 = source not banned · R2 = crop new or ≤1 · R3 = claim shape under cap.

---

## 1. dp_21741 (2009) — makarnalık buğday (durum wheat)

- **claim_shape:** region-adapted cultivar recommendation (NEW shape; 0 → 1)
- **Rule check:** R1 pass (not in banned list) · R2 pass (wheat panel-count 1
  → 2; rule 2 permits exactly one further wheat case, and this consumes it —
  note the panel case is *ekmeklik*, this is *makarnalık*) · R3 pass (new shape,
  1 of 3 on slate)
- **proposed_query:** `Ege Bölgesi koşullarında makarnalık buğday ekeceğim, verimi istikrarlı hangi çeşitler önerilir?`
- **frozen_answer_any:** `["sarıçanak 98", "sarıçanak", "salihli 92"]`
  - "ege 88" deliberately EXCLUDED: "ege" echoes the query wording, a weak anchor.
- **frozen_context_any:** `["stabil çeşitler", "verim performanslarını ve stabilitelerini"]`
- **source_quote:** "Araştırma sonucunda, saptanan bütün parametreler ele
  alındığında bölgede tavsiye edilebilecek stabil çeşitler; Sarıçanak 98, Ege 88
  ve Salihli 92 çeşitleridir."
- **Answer-naturalness:** a grower asking which durum cultivar to sow is answered
  with cultivar names — the same shape that carried `disease_fireblight_resistant`.
  Not a results-table cell.

## 2. dp_1514564 (2025) — aspir (safflower)

- **claim_shape:** region-adapted cultivar recommendation (2 of 3)
- **Rule check:** R1 pass · R2 pass (safflower new to panel, count 1) · R3 pass
- **proposed_query:** `Diyarbakır koşullarında hangi aspir çeşidi önerilir?`
- **frozen_answer_any:** `["remzibey-05", "remzibey 05", "remzibey"]`
  (all three are notations of the same cultivar name — no broadening)
- **frozen_context_any:** `["bitkide tabla sayısı", "ham yağ oranı"]`
- **source_quote:** "Sonuç olarak, üç yıllık bu çalışmanın sonuçlarına dayanarak,
  Remzibey-05 çeşidi Diyarbakır ekolojik koşulları için önerilebilir."
- **Answer-naturalness:** the paper's own single-cultivar verdict, stated twice
  (TR abstract + English conclusion). A cultivar name is what a recommendation
  answer says out loud.

## 3. dp_30474 (2010) — ahududu (raspberry)

- **claim_shape:** region-adapted cultivar recommendation (3 of 3 — SHAPE NOW FULL)
- **Rule check:** R1 pass · R2 pass (raspberry new, count 1) · R3 pass at the cap
- **proposed_query:** `Erzurum Oltu yöresinde hangi ahududu çeşitleri iyi adapte olur?`
- **frozen_answer_any:** `["hollanda boduru", "newburg"]`
  - "heritage" and "summit" deliberately EXCLUDED even though the paper names
    them: both are internationally famous raspberry cultivars a model can emit
    with an empty corpus. This is the `local_avocado_antalya` lesson applied at
    slate time — narrowing to the corpus-specific names TIGHTENS the assertion,
    it does not loosen it.
- **frozen_context_any:** `["g meyve/sürgün", "yılda iki ürün veren"]`
- **source_quote:** "Sonuç olarak yılda iki ürün veren Heritage, Hollanda Boduru
  ve Summit çeşitleri ile yılda tek ürün veren Newburg çeşidinin diğer çeşitlere
  göre yörede daha iyi adapte oldukları belirlenmiştir."

## 4. dp_1559843 (2024) — nohut (chickpea)

- **claim_shape:** resistant-cultivar list (panel 1 → 2; cap 3)
- **Rule check:** R1 pass · R2 pass (chickpea new, count 1) · R3 pass
- **proposed_query:** `Nohutta yanıklık hastalığına dayanıklılık bakımından hangi çeşitler öne çıkıyor?`
- **frozen_answer_any:** `["göktürk", "azkan"]`
  - "arda" EXCLUDED: too short/common a token to anchor on safely.
- **frozen_context_any:** `["ilk bakla yüksekliği", "yüz tane ağırlığı"]`
- **source_quote:** "Bu çalışma sonuçları doğrultusunda Göktürk, Azkan ve Arda
  çeşitlerinin yanıklığa dayanıklılık bakımından bölge için daha uygun olduğu
  belirlenmiştir."

## 5. dp_21712 (2005) — bezelye (pea)

- **claim_shape:** sowing date (NEW shape; 0 → 1)
- **Rule check:** R1 pass · R2 pass (pea new, count 1) · R3 pass (1 of 2 on slate)
- **proposed_query:** `Ot amaçlı bezelyede en yüksek hasıl verimi için ekim ne zaman yapılmalı?`
- **frozen_answer_any:** `["22 kasım"]`
- **frozen_context_any:** `["durango", "hasıl ve kuru madde verimi"]`
- **source_quote:** "...en yüksek hasıl ve kuru madde veriminin 22 Kasım'da
  yapılan ekimlerden sağlandığını göstermiştir."
- **Answer-naturalness:** a specific calendar date is exactly what a sowing-time
  answer states, and it is not guessable — the model has no prior for
  "22 November" over any other late-autumn date.

## 6. dp_21713 (2003) — mısır (maize)

- **claim_shape:** sowing date (2 of 2 on slate; panel cap 3)
- **Rule check:** R1 pass · R2 pass (maize new, count 1 — see #10 caveat) · R3 pass
- **proposed_query:** `Alaşehir koşullarında ana ürün mısırda en uygun ekim zamanı nedir?`
- **frozen_answer_any:** `["20 mayıs"]`
- **frozen_context_any:** `["maverick", "c-955"]`
- **source_quote:** "20 Mayıs ekimi, en uygun ekim zamanı olarak tespit
  edilmiştir (Çizelge 9)." — corroborated by the paper's own
  "Alaşehir bölgesi için en uygun ekim zamanı Mayıs ortası ile sonu arasındaki
  dönemdir." The two are consistent (no guarbean-style either/or).

## 7. dp_1338811 (2023) — Muş lalesi (Tulipa sintenisii)

- **claim_shape:** storage condition (panel 2 → 3 — SHAPE NOW AT CAP)
- **Rule check:** R1 pass · R2 pass (tulip new, count 1) · R3 pass at the cap;
  this is the ONE storage case rule 3 allows, so no other storage candidate ships.
- **proposed_query:** `Muş lalesi soğanlarını söküm sonrası yaz boyunca nasıl saklamalıyım?`
- **frozen_answer_any:** `["oda sıcaklığ", "25 °c", "25 0c", "25°c"]`
  (the paper writes "oda sıcaklığında (yaklaşık 25 0C'de)" — one claim, two notations)
- **frozen_context_any:** `["kar örtüsü altında", "çıkış oranı kontrol uygulamasında"]`
- **source_quote:** "Muş lalesi'nin soğan gelişimleri ve bazı bitkisel
  özelliklerinin incelendiği çalışmada incelenen bütün özelikler bakımından en
  iyi sonuçlar soğanların yaz döneminde oda sıcaklığında (yaklaşık 25 0C'de)
  bekletildiği kontrol uygulamasından elde edilmiştir."
- **Why it should discriminate:** general knowledge says tulip bulbs need
  chilling; this paper found the opposite for *T. sintenisii* (emergence 93.3 %
  at room temperature vs 56.6 % / 46.6 % after 1–2 months cold). An ablated model
  is likely to recommend chilling.

## 8. dp_21749 (2009) — gül (rose)

- **claim_shape:** non-nitrogen fertilizer dose (NEW shape; 0 → 1)
- **Rule check:** R1 pass · R2 pass (rose new, count 1) · R3 pass
- **proposed_query:** `Saksıda gül fidanı yetiştirirken hümik asitli kompoze gübreden saksı başına ne kadar vermeliyim?`
- **frozen_answer_any:** `["6 g/saksı", "6 g saksı", "6 g/bitki", "saksı başına 6 g"]`
  (the paper itself states the dose both as g/saksı and g/bitki — same value)
- **frozen_context_any:** `["gonca-çiçek sayısı", "yaprak kuru madde oranı"]`
- **source_quote:** "...özellikle 6 g/saksı'lık gübre dozunda en olumlu sonuç
  elde edilmiştir." and "6 g/bitki gübre dozunun sağlıklı gül yetiştirmek ve en
  fazla sayıda çiçek elde etmek açısından en uygun doz olacağı sonucuna
  varılmıştır."

## 9. dp_21704 (2012) — marul (lettuce)

- **claim_shape:** micronutrient dose (NEW shape; 0 → 1)
- **Rule check:** R1 pass · R2 pass (lettuce new, count 1) · R3 pass
- **proposed_query:** `Marulda çinko eksikliği için topraktan kaç ppm çinko uygulanmalı?`
- **frozen_answer_any:** `["20 ppm"]`
- **frozen_context_any:** `["çinko sülfat", "baş boyu"]`
- **source_quote:** "Her iki uygulamada da marul bitkisinin gelişimi ve
  beslenmesi topraktan 20 ppm (ZnT2) ve yapraktan % 0.20 (ZnY2) dozlarının
  önerilebileceği sonucuna varılmıştır."
- **RISK, recorded before running:** the paper's ÖZ states the same verdict in
  CODED form ("ZnT2, ZnY2 seviyeleri ... önerilebilir"); only the conclusions
  section spells out "20 ppm". If retrieval lands on the abstract chunk the
  number never enters context. Rank 9 for that reason.

## 10. dp_19517 (2007) — mısır (maize) — ALTERNATE ONLY

- **claim_shape:** sowing-implement choice (NEW shape; 0 → 1)
- **Rule check:** R1 pass · R2 **conditional** — this would be the SECOND maize
  candidate (with #6). Maize is not on rule 2's capped list, so two maize cases
  are not a rule breach, but shipping both would rebuild exactly the crop
  concentration this round exists to break. **Ship this only if #6 did not ship.**
- **proposed_query:** `İkinci ürün mısırın doğrudan ekiminde hangi gömücü ayak tipi daha iyi çıkış sağlar?`
- **frozen_answer_any:** `["çift disk"]`
- **frozen_context_any:** `["çıkış oranı indeksi", "yan tekerlek"]`
- **source_quote:** "Araştırma sonuçlarına göre ikinci ürün mısırın doğrudan
  ekiminde, daha yüksek tarla filiz çıkış oranı ve daha düşük filiz çıkış süresi
  için çift diskli gömücü ayak ve yan tekerlek kullanılması önerilmektedir."
- **RISK:** double-disc openers are standard no-till practice; a plausible
  model-carried outcome. Kept as map data, ranked last.

---

## Mine-time rejections (copied from Task 1 report §6)

These sources were rejected BEFORE any candidate line was written — they never
entered the slate. Recorded so a future round does not re-chase them as data gaps.
(Source: `.superpowers/sdd/task-1-report.md` §6, which is gitignored and would
otherwise not survive.)

**Failed the answer-naturalness test (value lives only in a table, or is not
what an answer says out loud):**

- `dp_1035375` tritikale — conclusion recommends genotypes by NUMBER
  ("10 adet genotip (8, 9, 11, 13...)"). No answer states a genotype number.
- `dp_19500` asma (grape) rootstock — "5BB en yüksek randıman" is a results
  comparison, not a recommendation; grape is also at its crop cap.
- `dp_1419654` antepfıstığı (pistachio) harvest "1 hafta içerisinde" — vague
  value, and the source text is OCR-degraded.
- `dp_19522` *Dalbergia sissoo* germination 25 ºC — a generic germination
  temperature a model guesses without any corpus; grower-unnatural species.

**Ambiguous or multi-valued assertion (the guarbean class — the only way to green
is a DIFFERENT claim):**

- `dp_1532562` 'Zambesi' zambak, humic acid — genuinely multi-valued: 150 ppm
  best for vase life, 300 ppm for stem length, 600 ppm for bud count, ">600 ppm
  wasteful". No single value is *the* answer.
- `dp_19578` papaya germination — a range (250–1000 ppm GA3) that differs per
  cultivar, plus an alternate hot-water treatment.
- `dp_19437` *Anemone coronaria* — a REVIEW summarising Gill (2010), and it
  gives 100 ppm N in one place and 100–200 ppm in another.
- `dp_1362458` buğday N — a regression/modelling review mixing its own 12 kg/da
  with cited 5, 13 and 7–13 kg/da figures; wheat slot also consumed by #1.

**Coded treatment labels (the value never reaches the answer as stated):**

- `dp_21697` Karaburun nergisi — the recommendation is "U4 uygulaması"; the real
  content (GTS + 8-HQC + sakkaroz, dry storage) is a biocide mixture. The
  storage slot is also consumed by #7.

**Not the paper's own voice (cited literature, caught by the citation filter or
by reading):**

- `dp_1521566` nohut patotip tolerance list — a literature-review paragraph
  citing Samsun/Adana studies; would also have been a second chickpea.
- `dp_19455` (sowing time / row spacing) and `dp_21746` (kolza) — key sentences
  are "…belirlemişlerdir / bildirmektedir", i.e. other authors' findings.
- `dp_19521` buğday çeşitleri (Gerek-79, Kutluk-94) — cultivar-catalogue prose.
- `dp_21708` tritikale Menemen — hedged ("…yorumlanabilmektedir").

**OCR-degraded source (assertion tokens unreliable for retrieval and matching):**

- `dp_30424` turp (radish) — the whole abstract is mojibake
  ("Araflt›rma", "çeflitleri"). The finding is real but unmatchable.
- `dp_30454` patates (potato), Erzurum, "Lady Rosetta, Desire, Hermes" — a good
  finding, but diacritic-stripped OCR AND the region-cultivar shape is already
  at its cap of 3 with cleaner-text candidates. **Worth re-mining in a LATER
  round if a region-cultivar slot reopens.**
- `dp_384565` patates, Erzurum, "Cycloon, Van Gogh" — same crop, same region,
  same question, DIFFERENT recommended cultivars from `dp_30454`. Retrieval
  would surface both and neither assertion would reliably appear. Do not ship
  either without disambiguating the query first.

**Out of project scope (chemicals) or not grower advice:**

- `dp_1567278` — recommendation is bound to methoxyfenozide/spinetoram doses.
- `dp_1224482` — "Fungisit 1" at 2500 ppm; the fungicide is anonymised.
- `dp_19505` in-vitro FA 0.3 mM, `dp_1582874` EMS/SA mutagen doses,
  `dp_19377` EDTA phytoextraction, `dp_30498` chromium adsorption on walnut
  sawdust — laboratory protocols, not plant-care questions.
- `dp_1091137` armut (pear) anaç — **crop banned outright by rule 2.**
