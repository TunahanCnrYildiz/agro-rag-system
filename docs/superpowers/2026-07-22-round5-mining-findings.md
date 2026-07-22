# Round-5 candidate mining — findings

**Date:** 2026-07-22. **Outcome: the vein is dry under the current caps.**
New-source mining produced **0 shippable candidates**. Round 5 closes at **+1**,
the one carried-forward row measured before mining (`quant_forage_irrigation_level`,
dp_257759, corpus-carried). The grape-graft carry-forward (dp_19426) was dropped
retrieval-broken — see `evals/eval_set.py`.

This file exists so round 6 does not repeat the scan. Read it (and
[[do-not-rechase]]) before mining again.

## Method

Two scans over the **393 dp_ sources NOT already used/banned/dropped/rejected**
(exclusion set = every `dp_` token in `eval_set.py` + the round-3 and round-4
slates = 226 sources). The scan was a throwaway script; the method below is the
record, not the code.

1. **Numeric own-voice conclusions** — a conclusion marker (`sonuç olarak`,
   `sonucuna varıl`, `önerilebilir`, `tavsiye edil`, `uygulanabileceği`, …) within
   ±180 chars of a number+unit. **24 hits.**
2. **Technique/implement/state-name recommendations** (non-cultivar, since the
   named-plant-material family is closed) — conclusion marker + a technique keyword
   (`sistemi`, `yöntemi`, `gömücü ayak`, `terbiye`, `aşı`, …), excluding
   `çeşit/anaç/genotip/hat/tescil`. **7 hits.**

All 31 reviewed by hand for answer-naturalness, own-voice (not cited literature),
in-scope, and crop/shape headroom.

## Why every hit failed

- **Off-scope** (largest class): concrete canal/cement engineering (dp_19587,
  dp_19592), remote sensing / spectroradiometry (dp_19411), mechanization forecast
  (dp_30500, dp_19526), tourism/land-use planning (dp_19553, dp_19599), germplasm
  inventory (dp_21739), human nutrition — milk, eggs (dp_30507, dp_30499),
  pesticide/insecticide (dp_30421, dp_19597 Abbott bioassay).
- **Results-table only** (not answer-natural): salt-germination % by crop
  (dp_1448114), genotype yield/oil ranges (dp_21727), cultivar registration &
  maturity days (dp_21695).
- **Cited literature, not own voice:** altitude→ripening (dp_30428, Karaçalı 1990),
  soil bulk density (dp_30459, Craul 1999), cotton irrigation verdict (dp_30523,
  Emiroğlu/Kochetkov), AMF inoculation (dp_1442118, Linderman & Davis 2001).
- **Capped crop:** grape at 2/2 (dp_19537 electromagnetic rooting, dp_19539 GA3);
  forage at 2/2 (dp_19456, dp_19603, dp_30443).
- **Soft/generic verdict:** chickpea weed control "elle kontrol" (dp_19447),
  saline-soil grasses+manure (dp_30443).
- **In-vitro + closed family:** cotton salt-tolerance cultivar Nazilli-84
  (dp_30462) — tissue-culture, and a cultivar recommendation = named-plant-material,
  which is closed.

## The one clean candidate — BLOCKED by a full cap, not by quality

- **dp_19602 — fasulye (bean) + boron, "1 kg/ha".** Own-voice conclusion: *"Sonuç
  olarak … borun ister topraktan ister yapraktan olsun 1 kg/ha dozu, fasulyenin
  verim ve tane kalitesine olumlu etki yaptığı …"*. New crop (bean, 0 slots),
  answer-natural. **claim_shape = input application rate, and that bucket is FULL
  at 3/3** (wheat N, mera N, rose pot fertilizer). Same wall as the two round-4
  reserves kept for round 5: **dp_19434 Ranunculus compost "8 ton/da"** and
  **dp_21704 lettuce zinc "20 ppm"**. Three clean dose candidates, one cap.
- **RISK if ever measured:** "1 kg/ha boron" is a fairly standard textbook rate, so
  a model-carried read is plausible — measure the ablated direction first.

## Decision (user, 2026-07-22): cap NOT raised

The input-application-rate cap stays at 3. Round 5 closes at +1. Rationale
([[do-not-rechase]]): the panel is a **drift guard**, the count is **not** coverage,
and its weakest guard (rose) is already a dose case. A 4th dose case skews the panel
toward one shape for low marginal drift value — the "count as coverage" trap. If a
future round revisits the cap, the three dose candidates above are the ready reserve.

## Standing conclusion for round 6

Under the current caps and the named-plant-material closure, **new DergiPark mining
is effectively exhausted.** The remaining headroom is in non-plant-material
name-recommendation shapes (training-system 1/3, sowing-implement 1/3 but maize is
capped, graft-material 0/3 but grape is capped) and brand-new shapes — none of which
surfaced a clean, in-scope, uncapped-crop candidate in this scan. Do not re-run the
same numeric/technique scan; it is recorded here as dry.
