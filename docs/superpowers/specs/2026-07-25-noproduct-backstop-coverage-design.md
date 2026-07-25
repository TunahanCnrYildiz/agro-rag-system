# NOPRODUCT backstop — coverage extension (round 2)

**Date:** 2026-07-25
**Status:** design approved (scope confirmed), ready for a short plan

## Why

The hosted efficacy re-measurement (2026-07-24, findings in
`docs/superpowers/2026-07-23-provider-portability-findings.md`) showed the
product-suppression backstop is real and safe but PARTIAL: on `gemma-4-26b-a4b:free`,
of the `products='none'` cases answered in both runs, **5 fixed, 0 regressed, 14 still
leak**. This round extends coverage toward the still-leaking categories, driven entirely
by that measurement — no speculation.

## What the 14 leakers taught us (all probed locally, no model)

Two distinct causes, not one:

1. **`verimli` in `_NUTRITION_TERMS` is a FALSE nutrition signal for self-fertility
   answers.** The pear cases answer "kendine **verimli** / verimlidir" — "fertile" in the
   *reproductive* sense, not nutrient fertilization. `verimli` matches it, the nutrition
   half of the rule fires, and suppression is CANCELLED. Confirmed by probe on
   reconstructed answers for `local_santamaria_pear`, `local_bpmorettini_pear`, and
   `pruning_grape` ("verimli sürgün"). This is watch-item 2 from the last final review,
   now with a concrete mechanism.

2. **Genuine coverage gaps** — categories the activity list never enumerated: sowing
   (`technique_maize_sowing_date/opener`), training systems
   (`technique_tomato_training_system`), rootstock selection
   (`local_antalya_grapefruit_rootstock`), post-harvest drying
   (`local_hachiya_persimmon`), and pollinizer/self-fertility phrasing.

## The change

**A. Remove `verimli` from `_NUTRITION_TERMS`.** Probed safe: soil-fertility nutrition
answers ("toprak verimliliğini artırmak için ahır gübresi…") stay protected by
`gübre`/`besin`/`azot`/`kompost`, which they always carry. `verimli`'s nutrition benefit
was redundant; its cost (cancelling self-fertility suppression) was real.

**B. Add low-risk activity stems** to `_NON_PRODUCT_ACTIVITY`, and broaden pollination:

| stem | category | target case(s) |
|---|---|---|
| `ekim` | sowing date/technique | `technique_maize_sowing_date`, `technique_maize_sowing_opener` |
| `terbiye` | training system | `technique_tomato_training_system` |
| `anaç` | rootstock selection | `local_antalya_grapefruit_rootstock` |
| `kurut` | post-harvest drying | `local_hachiya_persimmon` |
| `partenokarp` | self-fertility / fruit set | pear cases |
| `tozla` (replaces `tozlaş`) | pollination / pollinizer | broadened to catch "tozlayıcı" as well as "tozlaşma" |

Every target answer above was verified to SUPPRESS, and every one of six nutrition/
product answers to KEEP, with the final lists (probe 2026-07-25).

**`ekim` note:** it also matches "Ekim" (the month). Safe by construction — a fertilize-
in-October answer carries a nutrition term ("gübre"/"azot"), so the rule's nutrition half
keeps it. Verified: "Ekim ayında azotlu gübre ile besleme yapın" → KEEP.

## Deliberately OUT of scope (accepted partial coverage)

Confirmed with the user; each is high-risk or low-value under the "small lists, extend
only on measured evidence" rule:

- **`çeşit` (cultivar selection, `local_diyarbakir_safflower`)** — far too generic; it
  appears in most answers. Left uncovered.
- **Diagnosis refusal (`diagnosis_push`)** — "teşhis"/"belirti" collide with
  nutrient-deficiency answers. Left uncovered.
- **Biocontrol (`disease_rhizoctonia_biocontrol`)** — organism names / "biyolojik
  mücadele", one case, marginal. Left uncovered.
- **`drip_irrigation`, `pollination_squash`** — already have list coverage (`sula`,
  `tozla`) and the reconstructed answers suppress correctly, yet they leaked in the
  measurement. The real hosted answer text is not saved, so the exact cause is
  unresolved; not chased.
- **Micronutrient nutrition terms (watch-item 1)** — still not added; unmeasured and
  low-risk. Stays open.

Expected reach: ~8-9 of the 14, verified by the hosted confirm run.

## Testing & validation

- **Unit:** extend the existing backstop tests — each new stem's target answer
  suppresses; the `verimli`-removal cases (pear self-fertility) now suppress; the
  regression set (nutrition/product answers, including "toprak verimliliği" and "Ekim
  ayında … gübre") still keeps products. Keep the existing
  `test_production_activity_tuple_is_locked_against_the_wrong_stems` intact.
- **Local no-regression:** full local eval must stay **54/54** with product-gating
  **54/54**. Locally the marker fires so the backstop is mostly inert; this proves the
  new stems and the `verimli` removal do not wrongly suppress a passing case. If
  product-gating drops, stop and report — a nutrition/product case was newly suppressed.
- **Hosted confirm (quota-gated):** re-run `gemma-4-26b-a4b:free`, compare the
  `products='none'` cases case-by-case against the 2026-07-25 pre-extension run. Record
  how many of the 14 are now fixed. If a target category still leaks, that is a finding,
  not a cue to widen further.

## Deliverables

1. The two term-list edits in `src/engine.py` with updated/added tests.
2. Local no-regression eval recorded.
3. Hosted confirm result appended to the portability findings doc.
