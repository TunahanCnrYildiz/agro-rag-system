# Round-6 candidate mining (FAO + OpenAlex) — findings

**Date:** 2026-07-22. **Outcome: the FAO/OpenAlex vein is DRY too, for a STRUCTURAL
reason.** New-source mining over the English corpus produced **0 shippable
corpus_fact candidates**. Round 6 closes with **no additions**.

This is the sanctioned round-6 path from the round-5 findings ("a round 6 needs a
new source prefix, FAO/OpenAlex, or a rule change"). It was taken and measured. Read
this (and [[do-not-rechase]]) before proposing FAO/OpenAlex mining again.

## Method

Two scans over the **93 fao_ (25,757 chunks) + 27 oa_ (2,388 chunks) sources**,
using English own-voice recommendation markers (`it is recommended`, `we/it is
concluded`, `should be applied`, `optimum … was`, `gave/produced the highest`, …):

1. Recommendation marker + a specific numeric value (kg/ha, t/ha, %, °C, cm, days …).
   **11 hits (oa_ 3, fao_ 8).**
2. Broader conclusion scan over all 27 oa_ files with gap-crop name hints, no numeric
   requirement, to catch name/technique recommendations the numeric filter misses.

All reviewed by hand.

## Why every hit failed — and why it is structural, not bad luck

The single most important project finding ([[do-not-rechase]]) is that **the corpus
carries local / specific / citable; the model carries general.** FAO/OpenAlex are
neither local nor obscure, so they fall on the wrong side of that line:

- **General / textbook → high model-carried risk** (the model already knows it):
  Rhizobium inoculation 25–30 °C / pH 6–7 (fao_a0443e), potato pH 5–5.5 / avoid lime
  (fao_ai592e), use nitrate not ammonium N source (oa_W2895907234), compost mulch
  rate 2–6 m³/100 m² (fao_k1455e — also the dose cap is full).
- **Cited literature, not the paper's own voice:** climate-change land projections
  IPCC 2007 (fao_ak542e), grapevine rootstock Ramsey / Southey & Jooste 1991
  (oa_W1979210892), millet "5 t/ha under optimum" / Dida & Devos 2006 (oa_W2047116407),
  EMS mutagenesis doses / Desta et al. (oa_W3038546650).
- **Off-scope or lab / not a plant-care action:** grapevine/banana/teff GENOME
  assemblies (oa_W1994145712, W2061918046, W2175948239, W3006638720 — bioinformatics),
  vineyard remote sensing / EM38 / kriging (oa_W2167719861, W2170232199, W3020289656),
  coconut pollen cryopreservation (fao_t0824e), aflatoxin/food safety (oa_W2118755534),
  human dietary adequacy (oa_W2001465005).
- **Results-figure / soft feasibility (not answer-natural):** Purslane 64 % K decrease
  under salinity (fao_cb9565en), Sida hermaphrodita digestate 9 t/ha biomass
  (fao_cb7374en — also a grower-unnatural bioenergy species).
- **Capped crop:** grape (2/2) and maize (2/2) dominate the agronomic oa_ files
  (viticulture salinity/rootstock/pruning; zinc-in-maize oa_W2791140682).

The gap crops these oa_ files nominally cover (cacao, sweet potato, oil palm, millet,
taro) appear mostly in GENOME and REVIEW papers, not agronomic trials with an
actionable own-voice recommendation. That is exactly why the existing gap-crop eval
cases test cross-lingual RETRIEVAL reachability, not a specific corpus_fact value.

## Standing conclusion — corpus_fact growth is exhausted across ALL current prefixes

- Round 5: DergiPark (dp_) measured dry under the caps.
- Round 6: FAO + OpenAlex (fao_ / oa_) measured dry for a structural reason.

There is no cheap next round. Growing the panel further would require a genuinely new
source of **obscure-yet-answer-natural local specifics** — the property that made the
Turkish local-cultivar papers work. The productive move, if the user wants it, is
**re-harvesting more Turkish DergiPark local-cultivar / regional-trial papers**
(the reliable Zone-1 vein), NOT another pass over the corpus as it stands. Do not
re-run the round-5 or round-6 scans; both are recorded dry.
