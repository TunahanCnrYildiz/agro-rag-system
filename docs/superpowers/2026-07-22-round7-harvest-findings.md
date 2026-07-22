# Round-7 DergiPark harvest — findings

**Date:** 2026-07-22. **Outcome: the harvest ran cleanly and DRY for `corpus_fact`.**
120 new DergiPark agronomy PDFs were harvested, 17 pruned as off-topic, 103 ingested
(+4,628 chunks, store 76,798 → 81,426). The existing panel did NOT regress. A targeted
mining pass over the 103 new files yielded **0 shippable corpus_fact candidates.** No
case was added; the new papers stay in the corpus (freshness, no regression).

Read this and [[do-not-rechase]] before proposing another harvest.

## What ran (all steps of the round-7 plan)

- **Harvest:** `fetch_dergipark --max 120 --per-journal 150` — 120 new PDFs (dp_ count
  619 → 739), pushing through 72 retry/429 events. NOTE: the default `--per-journal 25`
  gives a shallow pool that is mostly already downloaded; raising it to 150 was needed
  to reach un-downloaded articles. The DergiPark curated list is NOT exhausted — a deep
  dry-run showed **3,079 candidate articles, 2,465 of them un-downloaded.** Paper supply
  is abundant; that is not the constraint (see below).
- **Off-topic cleanup:** `--clean-offtopic --apply` moved 17 livestock/aquaculture leaks
  to `_offtopic/` (0 chunks each — caught before ingest). 103 files remained.
- **Ingest:** incremental, +4,628 chunks (~45/file).
- **Regression gate — ALL THREE LAYERS PASSED, no rollback:**
  - `--fast` ctx diff vs the pre-harvest baseline: **clean** — no existing corpus_fact
    case flipped `ctx=True → False`, i.e. no new paper displaced a verdict chunk (the
    dp_19448→dp_19426 collision class did not recur).
  - `--faithfulness --repeat 4` whole panel: **exit 0, 22/23 corpus-carried** (the one
    model-carried, disease_rhizoctonia_biocontrol, is its recorded class). rose read
    2/4 and bpmorettini 3/4 — both known flaky, not harvest-caused, not drop triggers.
  - `pytest -q`: **187**.
- **Mining:** two passes over the 103 new files (own-voice conclusion + value; then a
  focused pass for under-cap non-cultivar shapes). 26 + 2 hits, all reviewed by hand.

## Why every candidate failed — the SAME structural wall as rounds 5-6

The 28 reviewed hits failed on exactly the grounds the caps and the core finding predict:

- **Cultivar recommendations → named-plant-material family is CLOSED:** apricot cultivars
  (dp_21754 "Precoce de Tyrinthe/Feriana/Beliana/Priana"), walnut micropropagation
  cultivar (dp_1409004 "Kozdere"), wheat stable-cultivar list (dp_21757 "Ziyabey 98…").
  This is the single largest class among the fresh papers — and it is the closed vein.
- **Lab / in-vitro / microbiology / genomics:** tissue-culture ABA/sucrose protocol
  (dp_21761), antimicrobial zone assay (dp_1181413), HCN bacterial method (dp_1269854),
  nematode race ID (dp_1334551), grape genetic map (dp_21758).
- **Cited literature, not own voice:** sweet-sorghum bioethanol yields (dp_1127371),
  drip-irrigation interval (dp_21755, Giorgessi 1984).
- **Results-range / null-finding (not answer-natural):** root wet/dry weight
  (dp_1311407), sugar-beet chloride "no effect" (dp_1079341), soilless cress EC
  (dp_1150723).
- **Off-scope:** recycling awareness (dp_1172745), ice-cream science (dp_335399), olive-
  leaf hematology (dp_341465), market value (dp_348459), climate description (dp_360031),
  pesticide-purchasing behaviour (dp_1387405).
- **Chemical (guardrail):** turf Rhizoctonia fungicide dose (dp_1341341).
- **Generic/textbook → model-carried:** soybean Rhizobium/Azotobacter inoculation
  (dp_405065); lentil salt biopriming by obscure strain code (dp_1406770, not
  answer-natural).
- **Capped crop:** grape drip irrigation (dp_21755), grape genetic map (dp_21758).
- **Dose-shape → cap full:** sugar-beet chloride 8 kg/da (dp_1079341).

## The decisive conclusion — `corpus_fact` growth is over, and NOT for lack of papers

Three consecutive rounds now measured dry: round 5 (DergiPark existing pool), round 6
(FAO/OpenAlex), round 7 (a FRESH 103-paper DergiPark harvest). Round 7 is the important
one because it removes the "maybe we just need new material" hypothesis: **new material
is abundant (2,465 un-downloaded), and harvesting 103 of it shipped nothing.**

The binding constraint is **not paper supply — it is the rule structure**: the
input-application-rate (dose) cap is full at 3/3, and the named-plant-material family
(cultivar/rootstock/variety recommendations — the single most common answer-natural
fact in Turkish agronomy papers) is closed at 5. What remains addable (under-cap
technique/quantitative/storage/irrigation shapes on new, uncapped crops) is genuinely
rare in the corpus and did not appear in a clean, own-voice, answer-natural form here.

**Harvesting cannot unlock more corpus_fact cases while those caps hold.** The only
lever that could is a RULE change — which the user already declined for the dose cap
(the "count as coverage" trap), and which [[do-not-rechase]] argues against on the
merits (the panel is a drift guard; a higher count is not coverage).

**Do not harvest again for corpus_fact growth.** The panel stays at 54 cases / 23
corpus_fact. Harvesting for genuine retrieval COVERAGE remains available as a separate
motivation, but that was measured to have no data gap and is not corpus_fact work.
