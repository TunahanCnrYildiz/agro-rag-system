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
carried forward where the assertion is unchanged. They cost nothing to re-mine
and their round-3 rule checks still hold under round 4's rules.

---

## 0. Repair pass — 2026-07-21 (pre-run, no value measured yet)

This slate FAILED its review before any run. Nothing here had been validated, so
the frozen values were repaired in place; the freeze binds from the first run,
which has not happened. Repairs applied:

- **C-1 — ten of twenty anchors could not match.** `_matches` does no whitespace
  normalization, so any anchor spanning a line break in the STORED chunk text is
  dead. Rows 1, 2, 6 and 9 had ZERO working anchors; rows 3, 4 and 7 had one
  each. Every anchor on every row was re-verified against the store with the
  exact `_matches` semantics, corpus-wide and case-insensitively. All twenty
  anchors below are now **verified present, contiguous, and unique to their
  source**, with the locator recorded per row (§M-2).
- **C-2 — rows 1 and 2 admitted different values.** Row 1's bare `"8 ton"` also
  matched `8 ton/ha` and `8 tonluk`; row 2's bare `"60 g"` also matched `60 gün`
  and `60 g/ha` (the trailing guard is `(?!\d)` only, so a trailing letter or `/`
  passes). Both unit-less forms are REMOVED. Only fully denominated notations of
  the same value remain.
- **I-1 — shape re-labelling.** A claim shape is defined by the STRUCTURE of the
  assertion (a recommended value plus its unit), NOT by the application context
  or the unit's denominator. Rows 1, 2, 4 and 5 are therefore ONE shape —
  **input application rate** — the same bucket as the panel's existing
  `nitrogen dose`, which holds 2 against a cap of 3. **At most ONE of rows 1, 2,
  4, 5 may ship.** Row 6 is the same shape as `local_diyarbakir_safflower` (a
  region-adapted plant-material recommendation) and consumes that bucket's single
  remaining slot. The non-shipping dose rows are kept, marked
  **BLOCKED BY SHAPE CAP**, so round 5 can reconsider them.
- **I-5** — row 10 now asserts the COMBINATION, not its halves.
- **I-7** — row 1's framing corrected: it is NOT a clean unconditioned
  recommendation. See the row.
- **I-8** — row 7's query narrowed to the training system alone. The finding's
  factual premise was wrong; see the row's note.
- **M-1** — row 2's misleading `"60 g ha"` removed.
- **M-3** — row 3's low-discrimination `"oda sıcaklığ"` removed in favour of the
  25 °C notations.

### Repair pass 2 — 2026-07-21 (second review, still pre-run)

The slate failed a SECOND review before any run. Again nothing had been
validated, so the frozen values were repaired in place.

- **I-A — row 3 is a FALSE GUARD and is now UNSHIPPABLE.** Its `answer_any` is
  satisfied by an answer that prescribes the very outcome the paper rejects. No
  `answer_none` guardrail survives scrutiny. Full evidence in the row.
- **I-B — row 8 had an undisclosed retrieval collision.** `dp_19566` recorded in
  the row and in §3.
- **I-C / M-A — row 10's contiguous-only compound forms created a false
  negative.** Replaced with an ordered `answer_any` + `answer_none` pair that
  keeps the wrong half unsatisfiable. The M-A self-contradiction dissolves with
  the `+` form's removal.
- **M-B — row 1's `"8 ton da"` removed** as a strict prefix of `"8 ton da-1"`
  that also matches `8 ton daha`.

**Shippable count falls from 7 to 6** — row 3's loss also empties the storage
shape's last slot, which no other slate row can consume.

**Rank order for the four shape-capped dose rows (Task 2 tries ONE):**
**2 → 4 → 1 → 5.** Row 2 is strongest (the LOWEST tested dose won, so a
"more is better" prior gives the wrong answer). Row 4 is a clean own-voice
verdict with a supporting-not-competing risk. Row 1 drops below row 4 because
of I-7 (a competing in-document conclusion). Row 5 is last because its ÖZ states
the verdict in CODED form only.

---

## 1. The slate

### 1. dp_19434 (2011) — düğün çiçeği (*Ranunculus asiaticus* 'Orange'), Antalya plastik sera

- **claim_shape:** **input application rate** (I-1) — SAME bucket as the panel's
  `nitrogen dose` (panel 2, cap 3, **1 slot free**). Competes with rows 2, 4, 5.
- **STATUS: BLOCKED BY SHAPE CAP.** Rank 3 of the four dose rows. Do not ship
  unless row 2 and row 4 are both unusable. Kept for round 5.
- **Rule check:** R1 pass · R2 pass (Ranunculus new to panel, 0 → 1; no slate-mate
  on this crop) · **R3 FAIL as a slate-mate** — only one of rows 1/2/4/5 may ship.
- **proposed_query:** `Serada düğün çiçeği yetiştiriciliğinde dekara ne kadar kompost uygulamalıyım?`
- **frozen_answer_any:** `["8 ton da-1", "8 ton/da", "dekara 8 ton"]`
  (C-2: the bare `"8 ton"` is REMOVED — it also matched `8 ton/ha` and `8 tonluk`,
  which are different values. All three remaining forms are fully denominated
  notations of the same per-dekar rate; the paper writes it `8 ton da-1`.)
- **M-B applied — `"8 ton da"` REMOVED.** It added no legitimate coverage and was
  actively unsafe on both sides. It is a strict PREFIX of `"8 ton da-1"`, so every
  answer it could legitimately catch was already caught by the denominated form;
  and the right-hand guard is `(?!\d)` only, so a trailing LETTER passes:
  ```
  _matches("8 ton da", "8 ton daha fazla") = True     # false positive
  _matches("8 ton da", "8 ton da-1")       = True     # already covered
  ```
  This is the same defect class as C-2's bare `"8 ton"`, missed on the first pass.
- **Corpus-attestation of the remaining forms (stated, not a defect).** Only
  `8 ton da-1` occurs in the store (dp_19434.pdf, pages 0, 2, 3, 4 — unique
  corpus-wide). `"8 ton/da"` and `"dekara 8 ton"` return **ZERO corpus chunks**:
  they are ANSWER-SIDE notations only. That is legitimate — `answer_any` is
  matched against the model's answer, not against chunk text, and a model may
  well denominate the rate in a notation the paper does not use. It is recorded
  here so a later reader does not mistake the zero counts for dead anchors of the
  kind C-1 removed. (The `context_any` anchors, which DO have to exist in the
  store, are verified separately below.)
- **frozen_context_any:** `["uygulama dozunun toprağa zarar",
  "Artan kompost seviyeleri, kontrol"]`
- **Anchor locators (verified 2026-07-21):**
  - `uygulama dozunun toprağa zarar` — dp_19434.pdf, **1 chunk, page 4**, unique
    corpus-wide. Sits in the SAME chunk as `8 ton da-1`.
  - `Artan kompost seviyeleri, kontrol` — dp_19434.pdf, **1 chunk, page 4**,
    unique corpus-wide. Same chunk as the value.
  - REPLACED: `toprağa zarar vermeden örtüaltı düğün çiçeği` (0 chunks — the
    store holds `toprağa zarar \nvermeden`) and `kentsel katı atık kompostunun
    zengin mineral bileşimi` (0 chunks — the store holds `kentsel \nkatı atık`).
- **source_quote:** "4. Sonuç Araştırma sonuçlarına göre, söz konusu kompostun
  farklı dozlarının verim ve kalite özellikleri üzerinde kontrole göre artış
  gösterdiği ve **8 ton da-1** uygulama dozunun toprağa zarar vermeden örtüaltı
  düğün çiçeği yetiştiriciliğinde başarıyla kullanılabileceği saptanmıştır."
- **Answer-naturalness:** a grower asking how much compost to spread is answered
  with a per-dekar rate, not a results-table cell.
- **FRAMING CORRECTION (I-7) — this is NOT a clean unconditioned recommendation.**
  The 8 t/da sentence sits in an `Araştırma sonuçlarına göre` paragraph. The
  paper's actual `Sonuç olarak` paragraph, two paragraphs later, **names no dose
  at all** and carries a caution: "…aynı kompostun yüksek tuz düzeyi içermesi
  nedeniyle tarımda artan dozlarda kullanımı öncesi mutlaka analiz edilmesi
  gerekmektedir." The results section likewise reports soil salt, Mn, Zn and Fe
  RISING with dose (355 → 421 → 478 → 560 micromhos). So the document contains a
  competing conclusion that argues AGAINST simply raising the dose. Task 2 must
  weigh this as a risk flag: retrieval landing on the `Sonuç olarak` chunk yields
  a caution, not a number.
- **Recorded risk:** 8 ton da-1 was also the HIGHEST dose tested, so the
  *direction* ("more is better") is guessable; the number itself is not.

### 2. dp_19600 (2005) — ayçiçeği (*Helianthus annuus*), Ankara

- **claim_shape:** **input application rate** (I-1) — SAME bucket as the panel's
  `nitrogen dose` (panel 2, cap 3, **1 slot free**). Competes with rows 1, 4, 5.
- **STATUS: RANK 1 of the four dose rows — this is the ONE Task 2 tries first.**
  Shipping it consumes the bucket's last slot and blocks rows 1, 4 and 5.
- **Rule check:** R1 pass · R2 pass (sunflower new to panel, 0 → 1) · R3 pass as
  the single row taking the input-application-rate bucket's remaining slot.
- **proposed_query:** `Ayçiçeğinde ekim öncesi tohuma humik asit uygulaması hangi dozda yapılmalı?`
- **frozen_answer_any:** `["60 g/100 kg", "100 kg tohuma 60 g", "60 g HA/100 kg"]`
  (C-2: bare `"60 g"` and `"60 gram"` REMOVED — `"60 g"` also matched `60 gün` and
  `60 g/ha`, which are different values. M-1: `"60 g ha"` REMOVED — it reads as a
  per-hectare rate but actually meant `60 g HA` (humik asit), which is exactly the
  ambiguity the rule forbids. All three remaining forms carry the `/100 kg tohum`
  denominator explicitly.)
- **frozen_context_any:** `["Sanbro çeşidinin fide özellikleri",
  "yüksek verimin ön koşuludur"]`
- **Anchor locators (verified 2026-07-21):**
  - `Sanbro çeşidinin fide özellikleri` — dp_19600.pdf, **1 chunk, page 4**,
    unique corpus-wide. Same chunk as the verdict.
  - `yüksek verimin ön koşuludur` — dp_19600.pdf, **1 chunk, page 4**, unique
    corpus-wide. Same chunk as the verdict.
  - Both were chosen over the value-bearing run because they carry no query echo.
    For reference, the value's own contiguous run `100 kg tohuma 60 g` is also
    dp_19600-unique (1 chunk, page 4) and is used in `answer_any`.
  - REPLACED: `ekimden önce ayçiçeği tohumlarına uygulanabileceği` (0 chunks — the
    store holds `ekimden önce \nayçiçeği`) and `60 g HA/100 kg tohum ile muamele
    edilmesinin` (0 chunks — the store holds `60 g HA/100 kg tohum ile \nmuamele`).
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
- **STATUS: UNSHIPPABLE (I-A). Do NOT run this row.** The assertion does not test
  what the case claims, and no guardrail repairs it. Evidence below. The row is
  kept, not deleted, so round 5 does not re-mine dp_1338811 expecting it to work.
- **Rule check:** R1 pass · R2 pass (tulip new, 0 → 1) · R3 pass at the cap; this
  is the ONE storage row rule 3 allows, so no other storage candidate may ship.
  **Because this row is unshippable, the storage slot goes UNUSED this round** —
  no other slate row is a storage claim, so it cannot be reallocated.
- **proposed_query:** `Muş lalesi soğanlarını söküm sonrası yaz boyunca nasıl saklamalıyım?`
- **frozen_answer_any:** `["25 °c", "25°c", "25 0c"]`
  (M-3: `"oda sıcaklığ"` REMOVED — the paper's own Methods call the control
  "room temperature", so the phrase is low-discrimination and a model can emit it
  without the corpus. The discriminating content is the 25 °C notation. The paper
  writes it `oda sıcaklığında (yaklaşık 25 0C'de)`; all three forms are notations
  of the same value.)
- **frozen_context_any:** `["çıkış oranı kontrol uygulamasında",
  "soğanlarının kışın kar örtüsü"]`
- **Anchor locators (verified 2026-07-21):**
  - `çıkış oranı kontrol uygulamasında` — dp_1338811.pdf, **1 chunk, page 4**,
    unique corpus-wide. Same chunk as the `25 0C` verdict. (Carried unchanged —
    verified working.)
  - `soğanlarının kışın kar örtüsü` — dp_1338811.pdf, **1 chunk, page 4**, unique
    corpus-wide. Same chunk as the verdict.
  - REPLACED: `kar örtüsü altında` (0 chunks — the store holds
    `kışın kar örtüsü \naltında`).
- **source_quote:** "Muş lalesi'nin soğan gelişimleri ve bazı bitkisel
  özelliklerinin incelendiği çalışmada incelenen bütün özelikler bakımından en iyi
  sonuçlar soğanların yaz döneminde **oda sıcaklığında (yaklaşık 25 0C'de)**
  bekletildiği kontrol uygulamasından elde edilmiştir."
- **Why it was thought to discriminate:** general knowledge says tulip bulbs need
  chilling; this paper found the OPPOSITE for *T. sintenisii* (emergence 93.3 % at
  room temperature vs 56.6 % / 46.6 % after 1–2 months cold). An ablated model is
  likely to recommend chilling.

#### I-A — why this row is a FALSE GUARD, and why no guardrail fixes it

**The defect.** The row's stated discrimination is "an ablated model will
recommend chilling; this paper found the opposite." But `answer_any` is a set of
25 °C NOTATIONS, and 25 °C also appears inside answers that PRESCRIBE chilling —
as a drying or curing step before the cold period. Verified:

```
_matches("25 °c", "soğanları 20-25 °c de kurutup sonra 4 °c de soğuklamaya alın")
  = True
```

That answer is wrong in exactly the way the case exists to catch, and it grounds
GREEN. So a green normal run would NOT establish that the model gave the paper's
verdict, and the case would ship as a false guard.

**Every candidate guardrail fails.** `answer_none` uses PLAIN substring matching,
not `_matches` (`run_eval.py:88-90` — "guardrail stays PLAIN substring on
purpose"), so it has no word boundary and no negation awareness. Tested against
the wrong answer above and against four phrasings a CORRECT, corpus-grounded
answer could plausibly take:

| candidate | blocks the wrong answer? | also fires on a CORRECT answer? | verdict |
|---|---|---|---|
| `soğuklama` | yes | **YES** | rejected |
| `soğuklamaya` | yes | **YES** | rejected |
| `soğukta bekletme` | **no** | **YES** | rejected |
| `ay soğukta` | **no** | **YES** | rejected |
| `4 °c` | yes | no (in sample) | rejected — see below |
| `+4 °c` | **no** | no | rejected |
| `+6 °c` | **no** | no | rejected |
| `buzdolab` | **no** | no | rejected |

- `soğuklama` / `soğuklamaya` are **disqualified by the paper's own conclusion**,
  which uses the word to state the CORRECT mechanism: "…kışın kar örtüsü altında
  **soğuklama** ihtiyaçlarını karşıladığını…". The better an answer is grounded in
  this source, the more likely it reproduces the guard term. Blocking it would
  penalise precisely the answers the case wants.
- `soğukta bekletme` / `ay soğukta` fire on a correct answer citing the paper's
  own numbers ("1 ay soğukta bekletmede çıkış %56,6'ya düştü") while NOT blocking
  the wrong answer, which says `soğuklamaya`. Wrong on both sides.
- `4 °c` and `+4 °c` rest on a **false premise in the finding itself.** The paper's
  cold treatment was **+6 °C in a buzdolabı** (Materyal ve Metot, p2: "…+6 0C'de
  buzdolabında 1 ay süre ile bekletilmiş"), not 4 °C. So 4 °C is not "the outcome
  the paper rejects" — it is a guess at one temperature a wrong model might name.
  A model prescribing tulip chilling is at least as likely to say 5 °C or 9 °C
  (the standard forcing range), neither of which `4 °c` blocks. And as a plain
  substring with no boundary, `4 °c` fires inside `24 °c` and `14 °c`
  (both verified True), so a correct answer giving a range like "20-24 °C" is
  falsely blocked.

**The general reason no guardrail exists.** The paper's verdict is a NEGATIVE
claim — *do not chill*. A correct answer must therefore talk about chilling in
order to reject it. Any lexical guard specific enough to catch a chilling
PRESCRIPTION also catches a chilling REFUTATION, because plain substring matching
cannot see the negation. The two answers differ in syntax, not vocabulary, and
`answer_none` only sees vocabulary.

**Why not repair it on the `answer_any` side instead.** Tying 25 °C to a storage
verb would need a regex or a multi-term conjunction; `answer_any` is a flat
ANY-list of `re.escape`d terms, so neither is expressible. Requiring a single
long contiguous run (e.g. `yaz boyunca oda sıcaklığında`) reintroduces exactly
the false-negative defect I-C removes from row 10.

**Verdict: UNSHIPPABLE, recorded as slate-time map data.** Under this project's
rule that a red case is DROPPED and never tuned green, shipping this row would
have been worse than losing it: it could only have gone green for the wrong
reason. Losing it costs the storage-shape slot, which no other row can use.

### 4. dp_21749 (2009) — gül (rose), saksıda fidan

*(round-3 slate row 8, unmeasured — carried forward verbatim)*

- **claim_shape:** **input application rate** (I-1) — SAME bucket as the panel's
  `nitrogen dose` (panel 2, cap 3, **1 slot free**). Competes with rows 1, 2, 5.
- **STATUS: BLOCKED BY SHAPE CAP.** Rank 2 of the four dose rows — Task 2's
  fallback if row 2 is unusable. Kept for round 5.
- **Rule check:** R1 pass · R2 pass (rose new, 0 → 1) · **R3 FAIL as a slate-mate**
  — only one of rows 1/2/4/5 may ship. The round-3 argument that a per-pot rate of
  a humic compound fertilizer is a DIFFERENT shape from a nitrogen dose is
  **overruled by I-1**: shape is the structure of the assertion (value + unit),
  not the application context or the unit's denominator.
- **proposed_query:** `Saksıda gül fidanı yetiştirirken hümik asitli kompoze gübreden saksı başına ne kadar vermeliyim?`
- **frozen_answer_any:** `["6 g/saksı", "6 g saksı", "6 g/bitki", "saksı başına 6 g"]`
  (the paper itself states the dose both as g/saksı and g/bitki — same value. No
  bare `"6 g"` form is present, so C-2 does not bite here.)
- **frozen_context_any:** `["yaprak kuru madde oranı",
  "18 kg harç için en olumlu sonucu"]`
- **Anchor locators (verified 2026-07-21):**
  - `yaprak kuru madde oranı` — dp_21749.pdf, **6 chunks, pages 0, 4, 7, 8, 10**,
    unique corpus-wide (no other source). One of those chunks is the page-10
    verdict chunk. (Carried unchanged — verified working.)
  - `18 kg harç için en olumlu sonucu` — dp_21749.pdf, **1 chunk, page 10**,
    unique corpus-wide. Sits in the SAME chunk as `6 g/saksı` and `6 g/bitki`.
  - REPLACED (I-3): `gonca-çiçek sayısı` (0 chunks — the store holds
    `gonca�çiçek sayısı`, with U+FFFD where the hyphen should be; same defect
    class as round 3's dead `bitkide tabla sayısı` anchor). The page-10 verdict
    chunk writes the character correctly as `gonca (çiçek) sayısına`, which IS
    matchable (dp_21749, 2 chunks, page 10) and is held in reserve.
- **source_quote:** "…özellikle **6 g/saksı**'lık gübre dozunda en olumlu sonuç elde
  edilmiştir." and "**6 g/bitki** gübre dozunun sağlıklı gül yetiştirmek ve en fazla
  sayıda çiçek elde etmek açısından en uygun doz olacağı sonucuna varılmıştır."
- **Recorded risk:** the paper also reports that 12 g/saksı DEPRESSED plant height.
  That is a supporting finding, not a competing recommendation.

### 5. dp_21704 (2012) — marul (lettuce)

*(round-3 slate row 9, unmeasured — carried forward verbatim, including its risk)*

- **claim_shape:** **input application rate** (I-1) — SAME bucket as the panel's
  `nitrogen dose` (panel 2, cap 3, **1 slot free**). Competes with rows 1, 2, 4.
- **STATUS: BLOCKED BY SHAPE CAP.** Rank 4 (last) of the four dose rows — its
  coded-abstract risk below keeps it bottom. Kept for round 5.
- **Rule check:** R1 pass · R2 pass (lettuce new, 0 → 1) · **R3 FAIL as a
  slate-mate** — only one of rows 1/2/4/5 may ship.
- **proposed_query:** `Marulda çinko eksikliği için topraktan kaç ppm çinko uygulanmalı?`
- **frozen_answer_any:** `["20 ppm"]`
- **frozen_context_any:** `["çinko sülfat (ZnSO4.7H2O)",
  "denemeleriyle de kalibre edilerek uygulanması"]`
- **Anchor locators (verified 2026-07-21):**
  - `çinko sülfat (ZnSO4.7H2O)` — dp_21704.pdf, **3 chunks, pages 0, 2, 6**,
    unique corpus-wide. The page-6 chunk is the verdict chunk holding `20 ppm`.
  - `denemeleriyle de kalibre edilerek uygulanması` — dp_21704.pdf, **1 chunk,
    page 6**, unique corpus-wide. Same chunk as `20 ppm`.
  - REPLACED (I-4): `çinko sülfat` — matchable but **NOT source-specific**:
    10 chunks across 3 sources (dp_21704 ×8, dp_1082347 ×1 page 12,
    dp_1225168 ×1 page 11). Under ANY-semantics it could carry ctx=True without
    dp_21704 being retrieved at all. The parenthesised formula makes it unique.
  - Also DROPPED: `baş boyu` — it verifies clean (dp_21704, 6 chunks,
    pages 0, 2, 4, 5, unique corpus-wide) but never co-occurs with the `20 ppm`
    verdict chunk, so a green ctx on it would prove only that an adjacent chunk
    was retrieved. Held in reserve if a third anchor is ever wanted.
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

- **claim_shape:** **region-adapted plant-material recommendation** (I-1) — the
  SAME bucket as the panel's `local_diyarbakir_safflower` (panel 2, cap 3,
  **1 slot free**). This row CONSUMES that last slot: 2 → 3, bucket then AT CAP.
  It is not a brand-new "rootstock recommendation" shape; the assertion structure
  is "for region X, plant material Y is recommended", which is the safflower case.
- **Rule check:** R1 pass · R2 pass (grapefruit/citrus new to panel, 0 → 1) ·
  R3 pass, **at the cap**, and no other slate row competes for this bucket.
- **proposed_query:** `Antalya koşullarında Marsh Seedless altıntop için hangi anaç önerilir?`
- **frozen_answer_any:** `["carrizo", "carrizo sitranj", "carrizo citrange"]`
  (three notations of the SAME rootstock name — not a broadening)
- **frozen_context_any:** `["Sonuç olarak incelenen tüm faktörler",
  "açısından en iyi sonuçlar Carrizo sitranjı"]`
- **Anchor locators (verified 2026-07-21):**
  - `Sonuç olarak incelenen tüm faktörler` — dp_19511.pdf, **1 chunk, page 10**,
    unique corpus-wide. The verdict chunk; own voice; no query echo.
  - `açısından en iyi sonuçlar Carrizo sitranjı` — dp_19511.pdf, **2 chunks,
    pages 0 and 10**, unique corpus-wide. Page 10 is the verdict chunk. Own voice:
    "Araştırma sonucunda, verim ve kalite açısından en iyi sonuçlar Carrizo
    sitranjı anacı üzerindeki ağaçlarda … saptanmıştır."
  - REPLACED: `Marsh Seedless altıntopu için Carrizo sitranjı anacı` (0 chunks —
    the store holds `Marsh Seedless \naltıntopu`) and `en iyi ağaç gelişimi ise
    turunç anacı` (0 chunks — the store holds `en iyi ağaç \ngelişimi`).
- **Correction to the round-4 anchor note (I-2, partially amended).** The finding
  states the second anchor was cited literature rather than the paper's own voice.
  **The evidence does not fully support that.** The exact string
  `en iyi ağaç gelişimi ise turunç anacı` occurs ONLY in the paper's own
  conclusion (page 10, chunk 51: "…en iyi ağaç gelişimi ise turunç anacı
  üzerindeki ağaçlarda saptanmıştır"), so the slate's own-voice claim for THAT
  anchor was correct; the anchor was dead for the line-break reason (C-1), not
  for provenance. The sentence the finding quotes —
  "…altıntopunda en iyi ağaç gelişiminin turunç anacı üzerinde olduğunu saptayarak
  sonuçlarımızı desteklemiştir" — is a DIFFERENT sentence, on page 9, attributed
  to **Ecomides ve Gregoriou (1993)**. It is genuinely cited literature, and it is
  a real hazard: a near-identical claim in another author's voice sits one page
  from the verdict. Both replacement anchors above are drawn from the page-10
  verdict chunk, so neither can be satisfied by the page-9 citation.
- **Anchor note for Task 2 (corrected):** the paper's literature review cites
  Carrizo repeatedly, including a same-direction finding by another author on
  page 9. Anchor uniqueness has now been verified corpus-wide and
  case-insensitively; both anchors are confined to the verdict chunk.
- **source_quote:** "Sonuç olarak incelenen tüm faktörler göz önüne alındığında
  bölgemiz koşullarında yetiştirilen Marsh Seedless altıntopu için **Carrizo
  sitranjı** anacı, en iyi sonucu vermiştir."
- **RISK, recorded before running:** Carrizo citrange is an internationally famous
  citrus rootstock a model may name with an EMPTY corpus — the
  `local_avocado_antalya` failure mode. Ranked below the dose rows for exactly
  this reason. Do NOT retune it green if it reads model-carried; record and drop.

### 7. dp_19468 (2009) — M19 salkım domates (tomato), Antalya sera

- **claim_shape:** training-system choice — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (tomato at 0 corpus_fact cases → 1; the
  existing `tomato_disease_organic` is NOT a corpus_fact case and consumes no
  slot) · R3 pass
- **proposed_query (NARROWED per I-8):** `Serada salkım domateste hangi terbiye sistemi önerilir?`
  (was: `…hangi terbiye sistemi ve dikim sıklığı önerilir?`)
- **frozen_answer_any:** `["atlatma", "atlatma sık"]`
- **frozen_context_any:** `["karşı telin üzerinden atlatarak",
  "uygulamasının üreticiye tavsiye edilebilecek"]`
- **Anchor locators (verified 2026-07-21):**
  - `karşı telin üzerinden atlatarak` — dp_19468.pdf, **1 chunk, page 2**, unique
    corpus-wide. (Carried unchanged — verified working.) NOTE: this is the Methods
    chunk (Çizelge 1), not the verdict chunk, so it proves the source but not the
    verdict chunk.
  - `uygulamasının üreticiye tavsiye edilebilecek` — dp_19468.pdf, **1 chunk,
    page 4**, unique corpus-wide. This IS the verdict chunk. Held alongside the
    Methods anchor deliberately: a green on both means the retrieval covered the
    verdict.
  - REPLACED: `atlatma sık dikim uygulamasının üreticiye tavsiye` (0 chunks — the
    store holds `atlatma sık dikim \nuygulamasının`). The alternative
    `yetiştiriciliğinde atlatma sık dikim` also verifies (dp_19468, 1 chunk,
    page 4) and is held in reserve; it was not chosen because it carries answer
    echo without adding retrieval evidence beyond the anchor already selected.
- **source_quote:** "Sonuç olarak salkım domates yetiştiriciliğinde **atlatma sık
  dikim** uygulamasının üreticiye tavsiye edilebilecek bir terbiye sistemi olduğu
  tespit edilmiştir."
- **Answer-naturalness:** "atlatma" is a Turkish-specific greenhouse training term
  a model has little reason to emit unaided — good discrimination.
- **I-8, applied with a correction to its premise.** The finding says the query
  asks two things while the assertion covers one, and that "the paper's yield
  winner is `seyrek dikim` (density)". **The second half is wrong on the
  evidence.** The paper explicitly REJECTS seyrek dikim — its own ÖZ and its
  `4. Sonuç` both open with "seyrek dikim uygulaması kesinlikle önerilmezken sık
  dikim ve uç almadan yapılan yetiştiriciliğin ciddi verim artışı sağladığı…" —
  and its per-m² yield winner is `kontrol sık dikim` (32,5 kg/m²). `Seyrek dikim`
  wins only on per-truss yield (894,34 g/salkım), which the paper immediately
  discounts because plants per dekar fall. So the paper's recommendation,
  `atlatma sık dikim`, answers BOTH halves of the original query, and no wrong
  answer could have grounded green on the original assertion.
  **The narrowing is applied anyway**, because the residual defect the finding
  points at is real: the query invited a two-part answer while `answer_any`
  required only the training-system half, so a correct answer that led with
  density and never said "atlatma" would have been scored red. Narrowing removes
  that false-negative path. `answer_any` was NOT widened — that would be a
  different claim.
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
- **frozen_context_any:** `["yan tekerlek",
  "yürütüldüğü iklim ve toprak koşulları için"]`
- **Anchor locators (verified 2026-07-21):**
  - `yan tekerlek` — dp_19517.pdf, **10 chunks, pages 0, 2, 3, 4, 6, 7, 8**,
    unique corpus-wide. The page-8 chunk is the verdict chunk. (Carried unchanged
    — verified working.)
  - `yürütüldüğü iklim ve toprak koşulları için` — dp_19517.pdf, **1 chunk,
    page 8**, unique corpus-wide. The verdict chunk; own voice.
  - REPLACED: `çıkış oranı indeksi` — it verifies clean (dp_19517, 5 chunks,
    pages 0, 5, 6, 7, unique corpus-wide) but is **dead inside the verdict chunk
    itself**, where the store holds `çıkış oranı\nindeksi`. A green on it would
    prove only that an adjacent chunk was retrieved. Held in reserve.
- **source_quote:** "Sonuç olarak, bu araştırmanın yürütüldüğü iklim ve toprak
  koşulları için, ikinci ürün mısırın doğrudan ekiminde, daha yüksek tarla filiz
  çıkış oranı ve çıkış oranı indeksi ve daha düşük ortalama çıkış süresi için
  **çift diskli gömücü ayak** ve yan tekerlek olarak adlandırılan derinlik ayar ve
  kontrol sistemi kullanılması önerilmektedir."
- **RISK, carried from round 3:** double-disc openers are standard no-till
  practice; a plausible model-carried outcome. Kept as map data, ranked low.
- **RISK — RETRIEVAL COLLISION with `dp_19566` (I-B, added on the second review).**
  `dp_19566.pdf` (Karayel & Özmerzi — the SAME authors, same journal, same
  research programme as dp_19517) also compares furrow openers, `çift diskli`
  among them, and it **recommends a DIFFERENT opener**. Both `answer_any` terms hit
  it hard:

  | term | dp_19517 (the source) | dp_19566 (the collider) |
  |---|---|---|
  | `çift disk` | pages 0, 2, 3, 4, 5, 6, 7, 8 | **pages 0, 1, 2, 3, 4, 6, 7** |
  | `çift diskli` | pages 0, 2, 3, 4, 5, 6, 7, 8 | **pages 0, 1, 2, 3, 4, 6, 7** |

  dp_19566's own `4. Sonuç` (p7–8) reads: "…gömücü ayaklar arasında en düşük çizi
  kesit alanı ve toprak kabarması **balta** gömücü ayak, en yüksek … ise çapa
  gömücü ayak…". It judges openers on furrow cross-section and soil disturbance;
  dp_19517 judges them on field emergence rate. Same vocabulary, different
  criterion, **opposite winner.**

  **Why the row still stands, unlike row 3.** Both `context_any` anchors are
  dp_19517-unique corpus-wide (verified above), so `ctx=True` still pins the right
  document — the collision cannot forge a green ctx. The hazard is to the
  INTERPRETATION of a green run, not to its validity.

  **What Task 2 must watch for.** If this row reads green, check that the retrieved
  context is dp_19517 and not dp_19566 before recording it corpus-carried. A green
  `answer_any` off a dp_19566 chunk would be grounding on a paper that recommends
  balta — the answer would be right by accident. Conversely, if the row reads RED
  with dp_19566 in context, that is a retrieval-collision finding, not a
  model-carried one; record it as such and do not re-mine either paper in round 5.
  This mirrors how row 10 already records dp_19448/dp_19471.

### 9. dp_257759 (2016) — Macar fiği + yem bezelyesi (forage legumes)

- **claim_shape:** irrigation level — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass (distinct from the dropped `dp_257760` guar-bean and
  `dp_30458` vetch-phosphorus sources — different documents, different claims) ·
  R2 pass (rangeland/forage 1 → 2, AT the absolute cap) · R3 pass
- **proposed_query:** `Macar fiği ve yem bezelyesinde kurak dönemde hangi toprak nem seviyesinde sulama yapmalıyım?`
- **frozen_answer_any:** `["%75 tarla kapasitesi", "% 75 tarla kapasitesi",
  "tarla kapasitesinin %75"]`
- **frozen_context_any:** `["kapasitesinin %25’ine düşmesine sebep olan kuraklıklar",
  "her iki yem bitkisine ne ciddi zarar vererek"]`
- **Anchor locators (verified 2026-07-21):**
  - `kapasitesinin %25’ine düşmesine sebep olan kuraklıklar` — dp_257759.pdf,
    **2 chunks, page 4**, unique corpus-wide. The verdict chunk holding
    `%75 tarla kapasitesi`. **Note the apostrophe: the store uses U+2019 (’), not
    ASCII `'`.** The old anchor's ASCII apostrophe was one of its two defects.
  - `her iki yem bitkisine ne ciddi zarar vererek` — dp_257759.pdf, **1 chunk,
    page 4**, unique corpus-wide. Same chunk as the value. (The "bitkisine ne"
    spacing is a typo in the source; it is reproduced verbatim on purpose.)
  - REPLACED: `en yüksek ot verimleri için` (0 chunks — the store holds
    `en yüksek ot verimleri \niçin`; the truncated `en yüksek ot verimleri` does
    verify, dp_257759 1 chunk page 4, and is held in reserve) and
    `tarla kapasitesinin %25'ine düşmesine sebep olan kuraklıklar` (0 chunks —
    ASCII apostrophe, plus the store holds `tarla \nkapasitesinin`).
- **source_quote:** "Kurak dönemlerde sulama gerektiğinde ise en yüksek ot
  verimleri için **%75 tarla kapasitesi** seviyesinde sulama yapıldığında elde
  edildiği sonucuna varılmıştır."
- **RISK, recorded before running:** "75 % of field capacity" is a fairly generic
  irrigation-scheduling figure; model-carried is plausible. Ranked low.

### 10. dp_19426 (2011) — asma (grape), aşı kaynaşması, Tekirdağ

- **claim_shape:** graft-material state — **NEW shape** (0 → 1; cap 3)
- **Rule check:** R1 pass · R2 pass (grape 1 → 2, AT the absolute cap) · R3 pass
- **proposed_query:** `Asma aşısında anaç çeliği ve kalem hangi sürme durumunda olmalı?`
- **frozen_answer_any (I-C — the ORDERED claim, no contiguity demanded):**
  `["sürmüş çelik", "sürmüş anaç", "çeliği sürmüş", "çeliğin sürmüş",
  "çeliğinin sürmüş"]`
- **frozen_answer_none (I-C — blocks the wrong half):** `["sürmüş kalem"]`

#### I-C — why the four contiguous forms were replaced

**The defect.** All four previously frozen forms (`A x B`, `A × B`, `A + B`,
`A ile B`) required the answer to reproduce the compound notation as ONE
CONTIGUOUS STRING. A perfectly correct, natural Turkish answer —
"anaç çeliği sürmüş, kalem ise sürmemiş olmalıdır" — matches **none** of them,
because the two halves are separated by a comma and an inflected clause. Under
this project's rule that a red case is DROPPED as map data and never tuned green,
that false negative would have been permanently recorded as a real finding about
the corpus.

**Two of the four were not even corpus-attested.** Verified against the store:

| frozen form | corpus chunks |
|---|---|
| `sürmüş çelik x sürmemiş kalem` | dp_19426 pages 0, 7 |
| `sürmüş çelik + sürmemiş kalem` | dp_19426 pages 3, 5 · **dp_19448 page 0** |
| `sürmüş çelik × sürmemiş kalem` (U+00D7) | **ZERO** |
| `sürmüş çelik ile sürmemiş kalem` | **ZERO** |

**The replacement, and how it preserves the ordered claim.** The claim is a
CONJUNCTION — *rootstock cutting sprouted* **AND** *scion unsprouted*. `answer_any`
is an ANY-list and cannot express a conjunction. But the case does not need to;
it needs the conjunction's TRUTH CONDITIONS, and those decompose:

- `answer_any` asserts the **rootstock half** — the discriminating half. General
  viticultural knowledge says graft material should be dormant, so the ablated
  failure mode is `sürmemiş çelik × sürmemiş kalem`: right on the scion, **wrong on
  the rootstock**. Requiring the rootstock half is what the old fix was reaching
  for, and it is what actually carries the paper's surprise.
- `answer_none` blocks the **wrong scion half**, `sürmüş kalem`. This closes the
  only gap the `answer_any` list leaves open: an answer saying
  `sürmüş çelik × sürmüş kalem` satisfies the rootstock half but is wrong on the
  scion. With the guardrail it fails.

Together the two fields are satisfied exactly when the answer asserts the
rootstock cutting sprouted and does NOT assert the scion sprouted — the paper's
pairing, with no contiguity required. Case analysis:

| answer | `answer_any` | `answer_none` | result | correct? |
|---|---|---|---|---|
| `sürmüş çelik X sürmemiş kalem` | hit | clear | **green** | ✔ the verdict |
| `anaç çeliği sürmüş, kalem ise sürmemiş olmalıdır` | hit (`çeliği sürmüş`) | clear | **green** | ✔ **false negative fixed** |
| `sürmüş anaç çeliği ile sürmemiş kalem` | hit (`sürmüş anaç`) | clear | **green** | ✔ |
| `sürmemiş çelik × sürmemiş kalem` | **no hit** | — | **red** | ✔ wrong rootstock half blocked |
| `sürmüş çelik × sürmüş kalem` | hit | **tripped** | **red** | ✔ wrong scion half blocked |
| `sürmemiş çelik × sürmüş kalem` | **no hit** | — | **red** | ✔ both halves wrong |

Note the guardrail is safe against the CORRECT pairing: `answer_none` is plain
substring, and `sürmemiş kalem` does **not** contain `sürmüş kalem`
(`sürm-emiş` ≠ `sürm-üş`), so the right answer never trips its own guard.

**Corpus attestation of the new forms (stated, per row 1's note).**
`sürmüş çelik` → dp_19426 pages 0, 2, 3, 4, 5, 7 and dp_19448 pages 0, 2, 3, 4, 5.
`sürmüş anaç` → dp_19448 page 2 only. `çeliği sürmüş`, `çeliğin sürmüş` and
`çeliğinin sürmüş` → **ZERO corpus chunks** — answer-side inflections only, which
is legitimate and is the whole point of the fix: the natural ANSWER phrasing is
not the paper's phrasing.

**Broadening test — same claim, or a different one?** All five `answer_any` forms
assert one thing: the rootstock cutting had sprouted. They differ only by Turkish
suffix (`çeliği` / `çeliğin` / `çeliğinin`) and word order. The bare form
`anaç sürmüş` was CONSIDERED AND EXCLUDED: it drops the `çelik` noun, so it would
also be satisfied by a claim about the rootstock VARIETY rather than the rootstock
CUTTING — a different claim.

**Residual limitation, recorded not hidden.** Neither field sees negation, so
"sürmüş çelik kullanılmamalıdır" grounds green. This is inherent to substring
matching and is NOT introduced by this fix — the four contiguous forms were
equally negation-blind. It is recorded so a green run is not over-read.

#### M-A — the self-contradiction is resolved

The row previously argued that "dp_19448 writes the pairing with `+`, so no
sibling can satisfy the anchors" while simultaneously listing
`sürmüş çelik + sürmemiş kalem` in `answer_any` — a form that does match dp_19448
page 0 (verified above). **The contradiction dissolves because the `+` form is now
gone entirely.**

The underlying confusion is worth naming, since it caused the error: the sibling
argument is about **`context_any`**, which is matched against retrieved CHUNK TEXT
and therefore must be source-unique. `answer_any` is matched against the MODEL'S
ANSWER, where corpus uniqueness is not the relevant property at all. Mixing the
two is what let a sibling-matching string sit inside a paragraph arguing that no
sibling could match. Both `context_any` anchors remain dp_19426-unique and confined
to the page-7 verdict chunk, so the sibling argument stands where it actually
applies.

One consequence must still be flagged for Task 2: `sürmüş çelik` occurs in
dp_19448 as well as dp_19426, so if retrieval lands on dp_19448 the model could
ground green off the SIBLING. That is why `ctx` must be checked, not just
grounding — and it is the same discipline the row's existing risk note demands.
- **frozen_context_any:** `["sürmüş çelik X sürmemiş kalem durumunun aşıda kullanılması",
  "Filizi kesilmemiş kalem durumunun en düşük değerleri"]`
- **Anchor locators (verified 2026-07-21):**
  - `sürmüş çelik X sürmemiş kalem durumunun aşıda kullanılması` — dp_19426.pdf,
    **1 chunk, page 7**, unique corpus-wide. The verdict chunk. The shorter
    `sürmüş çelik X sürmemiş kalem` also verifies unique to dp_19426 (4 chunks,
    pages 0 and 7) but spans the abstract too; the longer run pins the verdict
    chunk specifically, which is what defeats the dp_19448 / dp_19471 hazard.
  - `Filizi kesilmemiş kalem durumunun en düşük değerleri` — dp_19426.pdf,
    **1 chunk, page 7**, unique corpus-wide. Same verdict chunk.
  - DROPPED: `aşı kaynaşma özellikleri üzerine` — it verifies clean (dp_19426,
    1 chunk, page 0, unique corpus-wide) but sits in the ABSTRACT, one of the two
    places the sibling papers are most likely to collide topically. Replaced by a
    verdict-chunk anchor for the reason recorded in the row's risk note.
  - Sibling check: dp_19448 writes the combination with `+` rather than `X`, so
    neither anchor above can be satisfied by a sibling chunk.
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
| storage duration / condition | 2 | 1 | **1** (row 3) | ✘ **row 3 UNSHIPPABLE (I-A) — slot goes unused** |
| nitrogen dose | 2 | 1 | **0** | ✔ |
| resistant-cultivar list | 2 | 1 | **0** | ✔ |
| region-adapted cultivar rec. | 2 | 1 | **0** | ✔ |
| harvest timing / drying pretreatment / biocontrol list / min-diameter / bud load / sowing date | 1 each | 2 each | **0** | ✔ |
| **input application rate** (was: nitrogen dose) | **2** | **1** | **4** (rows 1, 2, 4, 5) | ✘ **OVER CAP — only ONE may ship** |
| **region-adapted plant-material rec.** (`local_diyarbakir_safflower`) | **2** | **1** | **1** (row 6) | ✔ at cap, slot consumed |
| training-system choice | 0 | 3 | 1 (row 7) | ✔ |
| sowing-implement choice | 0 | 3 | 1 (row 8) | ✔ |
| irrigation level | 0 | 3 | 1 (row 9) | ✔ |
| graft-material state | 0 | 3 | 1 (row 10) | ✔ |

**Table rewritten by the I-1 repair pass.** As originally counted, rows 1, 2, 4
and 5 each opened a brand-new bucket ("organic-amendment dose", "seed
pre-treatment dose", "pot fertilizer dose", "micronutrient dose") and row 6
opened a "rootstock recommendation" bucket. Under the spec's rule that a claim
shape is the STRUCTURE of the assertion (a recommended value plus its unit), not
the application context or the unit's denominator, those four dose rows are ONE
shape and row 6 is not new at all.

**Per-row bucket accounting after the repair:**

| Row | Bucket it consumes | Slots free before | After if it ships | Status |
|---|---|---|---|---|
| 1 | input application rate | 1 | 0 | **BLOCKED BY SHAPE CAP** (rank 3) |
| 2 | input application rate | 1 | 0 | **ELIGIBLE — try first** (rank 1) |
| 3 | storage duration / condition | 1 | 1 | **UNSHIPPABLE (I-A)** — false guard, no guardrail repairs it |
| 4 | input application rate | 1 | 0 | **BLOCKED BY SHAPE CAP** (rank 2) |
| 5 | input application rate | 1 | 0 | **BLOCKED BY SHAPE CAP** (rank 4) |
| 6 | region-adapted plant-material rec. | 1 | 0 | ELIGIBLE, consumes last slot |
| 7 | training-system choice (new) | 3 | 2 | ELIGIBLE |
| 8 | sowing-implement choice (new) | 3 | 2 | ELIGIBLE |
| 9 | irrigation level (new) | 3 | 2 | ELIGIBLE |
| 10 | graft-material state (new) | 3 | 2 | ELIGIBLE |

**Maximum shippable this round is therefore 6, not 10** (one of rows 1/2/4/5,
plus rows 6, 7, 8, 9, 10). Rows 1, 4 and 5 are kept, not deleted, so round 5
can reconsider them once the input-application-rate bucket's cap is revisited.

**Was 7 before the second review; row 3 is now UNSHIPPABLE (I-A).** Row 3 was the
slate's only storage-shape row, so its slot cannot be reallocated and the storage
bucket stays at 2 of 3. The shortfall against the spec's +4 target is therefore
NOT driven by the shape caps alone — one row was lost to assertion quality, found
at slate time rather than after a run. That is the cheap place to find it.

Four of ten rows open a brand-new shape bucket (was: nine). Every shape the panel
already uses is at or near its cap, so the headroom left is in those four new
buckets and nowhere else. Round 5 will be tighter still.

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
  **Second-review addendum:** dp_19448 also matches row 10's new `answer_any` term
  `sürmüş çelik` (pages 0, 2, 3, 4, 5) and `sürmüş anaç` (page 2). Row 10's
  `context_any` anchors remain dp_19426-unique, so `ctx` still discriminates — but
  a green grounding with dp_19448 in context is grounding off the SIBLING and must
  not be recorded as corpus-carried for dp_19426.

- `dp_19566` — **added on the second review (I-B) as slate row 8's collision
  hazard.** Karayel & Özmerzi, the same authors and journal as row 8's source
  `dp_19517`, comparing the same furrow openers. `çift disk` / `çift diskli` — both
  of row 8's `answer_any` terms — hit it on **7 pages (0, 1, 2, 3, 4, 6, 7)**. Its
  conclusion recommends **balta**, a DIFFERENT opener, because it judges openers on
  furrow cross-section and soil disturbance rather than on emergence rate.
  Recorded here, not as a candidate: it is not being mined, it is being watched.
  Row 8's ctx anchors are dp_19517-unique so ctx still pins the right document, but
  Task 2 must confirm the retrieved context is dp_19517 before recording a green as
  corpus-carried. Do not mine dp_19566 in round 5 either — as a candidate in its own
  right it would collide with row 8 the same way in reverse.
