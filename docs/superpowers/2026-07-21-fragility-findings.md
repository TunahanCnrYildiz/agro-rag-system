# Retrieval phrasing-fragility probe — findings

**Date:** 2026-07-21
**Spec:** `docs/superpowers/specs/2026-07-21-retrieval-phrasing-fragility-probe-design.md`
**Frozen paraphrases:** `docs/superpowers/2026-07-21-fragility-paraphrase-set.md` (commit `4d47862`, authored blind before the harness existed)

## Instrument control

Before any paraphrase ran, the harness was gated on the 18 ORIGINAL eval queries:
**18/18 HIT.** The instrument reaches every case's source under the wording the eval
uses, so a paraphrase miss is a property of the paraphrase, not of the harness.
Control `max_raw_score` range: 0.4151 – 0.7091.

## Result

| Class | n (of 54) |
|---|---|
| HIT | 47 |
| MISS-EMPTY | 3 |
| MISS-WRONG | 4 |
| **Failures (EMPTY + WRONG)** | **7** |

Over the 17 corpus-carried cases only (excluding the model-carried
`disease_rhizoctonia_biocontrol`, n=51): **6 failures**.

### By paraphrase category

| Category | HIT | MISS-EMPTY | MISS-WRONG | Failures |
|---|---|---|---|---|
| colloquial | 13 | 3 | 2 | **5** |
| inflected | 16 | 0 | 2 | **2** |
| synonym | 18 | 0 | 0 | **0** |

**The synonym axis is clean — 18/18.** Every alternative domain term tested reached
its source (`muhafaza`/`derim`/`omca`/`tomurcuk`/`antraknoz`/`cennet hurması`/
`tohumlama`/`asgari`). Turkish inflection is nearly clean too (2 failures, both in the
one affected family below). The damage is concentrated in SHORTENING.

### By source — the dominant finding

| Source | probes | failures |
|---|---|---|
| `dp_19393` (4 pear self-fertility cases) | 12 | **6** |
| the other 15 documents | 42 | **1** |

**Six of the seven failures come from ONE document**, and the seventh is the
model-carried rhizoctonia case. Excluding `dp_19393`, the failure rate is **1/42**.

## The decision the pre-registered rule produces

The rule, fixed before any probe ran: ≤2 → CLOSE; ≥6 → PROCEED; 3-5 → undecidable.

**Failures = 7 ≥ 6 → PROCEED.** The rule is applied as written. The spec also fixed in
advance that the SHAPE of failures does not affect go/no-go, only which mechanism to
design — and the shape here is unusually clear, so that clause is doing real work
rather than being a formality.

**Recorded discomfort, per the plan's instruction to write it down rather than
override the rule:** the headline 7 is inflated by a design property of the probe set
that I chose. Four of the 18 cases draw on `dp_19393`, and three of those four ask
substantially the SAME question ("is cultivar X self-fertile, does it need a
pollinizer?"). So the 54 probes are not 54 independent questions — they are roughly 15
distinct question shapes, one of which is repeated four times. Under a stricter
reading that de-duplicates by document, the count is 1 and the rule would say CLOSE.
The spec anticipated the concentration and required reporting it both ways; it did not
anticipate that the concentration would decide the outcome. **This is a genuine
limitation of the measurement, not a reason to retro-fit the threshold.**

## What actually fails, and why it is diagnosable

All six `dp_19393` failures are the same question family: *is this pear cultivar
self-fertile / does it need a pollinizer?*

| Probe | max_raw | vs floor | vs its control |
|---|---|---|---|
| santamaria colloquial | 0.3034 | −0.057 | −0.143 |
| ankara colloquial | 0.3007 | −0.059 | −0.201 |
| bpmorettini colloquial | 0.2941 | −0.066 | −0.178 |
| santamaria inflected | 0.3718 | +0.012 | −0.075 |
| beurrehardy colloquial | 0.4088 | +0.049 | −0.006 |
| beurrehardy inflected | 0.4133 | +0.053 | −0.002 |

Two distinct failure modes, and they are not the same defect:

1. **MISS-EMPTY (3 probes, scores 0.294–0.303).** These are **nowhere near** the 0.36
   floor — a 0.06 shortfall, not a rounding miss. The eval wording scores 0.44–0.50 on
   the same cases. What the short form drops is the domain phrase **"kendine
   verimli"**: `"Ankara armuduna dölleyici lazım mı?"` (0.3007) versus
   `"Ankara armudu kendine verimli mi, bahçeye tozlayıcı çeşit dikmek gerekir mi?"`
   (0.5016). The corpus states this finding as *kendine verimli / kendine kısır /
   partenokarp*; a query carrying only *tozlayıcı / dölleyici* does not reach it.
   **Lowering the floor would not fix this** — 0.30 is below any floor that keeps
   off-scope queries empty (an off-scope query already reaches ~0.34–0.41).
2. **MISS-WRONG (3 probes, scores 0.372–0.413).** These clear the floor but retrieve
   **`dp_1399494`** — the pear-breeding review — instead of `dp_19393`. A topically
   adjacent pear document out-competes the right one. This is a RANKING failure, a
   different defect from the cliff above, and it is the one case where the corpus
   returning "something plausible about pears" is arguably worse than returning
   nothing, because the answer will be grounded in the wrong study.

**Shortening is the damaging axis; synonyms and inflection are not.** That is the
opposite of what the pre-registered categories were hedging against — the inflection
axis was included because the lexicon matcher's historical bug lived there, and it
came back nearly clean.

## What this does NOT establish

- **It is a lower bound, by design.** These paraphrases derive from queries authored to
  work, so real-user fragility is at least this bad and probably worse.
- **It says nothing about coverage.** Content presence was held constant on purpose.
- **The failure is not "the corpus is fragile" in general.** 15 of 16 documents were
  reached by every paraphrase tried. One question family, on one document, accounts for
  the entire signal.

## Raw data

Scratch, not committed: `<scratchpad>/probe_fragility.py`,
`<scratchpad>/run_paraphrases.py`, `<scratchpad>/fragility_results.txt`.
Re-runnable — retrieval only, no chat model, minutes not hours.
