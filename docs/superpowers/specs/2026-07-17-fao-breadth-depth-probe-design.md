# FAO breadth: measure the thin topics before harvesting anything

**Date:** 2026-07-17
**Status:** design, approved
**Supersedes nothing.** Resolves handoff item 1 ("more FAO breadth (optional)").

## The request, and why it is not a harvesting task

Handoff item 1 offers two ways to grow the FAO corpus: harvest another OAI set
(`col_20.500.14283_3`, Technical documents) or strengthen the thin topics found
by the item-3 store audit — pollination (0.5% of chunks), pruning/grafting
(1.9%), greenhouse (2.3%), post-harvest.

Neither is blocked by code. `fetch_fao.py` already takes `--set`, so "add another
set" is one command, not a feature.

What is missing is a reason. The eval is 31/31 on every dimension and the four
thin topics **already have eval cases that pass** (`pruning_grape`, `grafting`,
`greenhouse_ventilation`, `pollination_squash`, `postharvest_storage` —
`eval_set.py:151-184`). The only number calling them "thin" is chunk share, which
measures corpus volume, not answer quality. Harvesting ~90 more PDFs on that
signal would grow the store ~10% and prove nothing.

This is the item-5 shape exactly: "the corpus lacks bordeaux/sigatoka content"
felt obvious, and measurement said the content was there (281 chunks) while
Turkish queries scored it below the 0.36 floor. The hypothesis was wrong and the
fix was elsewhere.

So this spec builds **a measurement, not a harvest**. The harvest is downstream of
what it says, and may not happen at all.

## Why the existing green cases do not settle it

`context_any` is an `any`-of substring check (`run_eval.py:43-47`).
`pollination_squash` passes if the retrieved context contains any of
"tozla/polen/pollinat/arı/bee" — one passing mention inside a general
horticulture book clears that bar. A 0.5% corpus share can be simultaneously
green here and genuinely too thin to answer a real question well.

So the existing cases are not vacuous (they do assert the topic was retrieved,
which is what they were built for in item 12), but they are **shallow**: they
guard topic presence, not topic depth. That gap is what the probes measure.

## Depth cannot be asserted at the answer layer

**The load-bearing constraint of this design.**

An `answer_any` depth probe would be vacuous, because the model answers from
parametric knowledge without the corpus. gemma knows how squash hand-pollination
works; ask it and "erkek çiçek / dişi çiçek / sabah" appear in the answer whether
or not a single corpus chunk supports them. Green probe, zero information about
the corpus. Same class as the `answer_none` bug (item 4) and the `retrieval:"any"`
bug (item 12): a check that looks like an assertion and asserts nothing.

Depth is therefore asserted on the **retrieved context**, which the model's
knowledge cannot contaminate — it holds what the corpus holds. A side benefit:
context checks are deterministic (embedding + vector search, no sampling), so
they need no `--repeat` and fit the harness's existing "retrieval/context are
single-sample BY DESIGN" stance (item 21).

## The depth claim: n-of-m specific terms

The observation the probe rests on: **a source that actually teaches a topic
contains several specific terms together; a source that merely mentions it in
passing contains one.**

Mechanism: **n-of-m**, `n=3` of `m=6` terms per topic, checked against the
retrieved context.

Rejected alternatives:
- **all-of** — brittle. One missing synonym ("tozlaşma" vs "tozlama") turns it red,
  which reports on the term list's wording, not on the corpus.
- **LLM-judge over the context** — costly, stochastic, and this project has
  already measured this model returning empty (item 20, ~3%) and mistranslating
  (item 11). An unreliable instrument produces unreliable measurements.

n-of-m also keeps eval_set's stated philosophy — "keywords are chosen to be
robust (several alternatives) rather than brittle" — while adding teeth.

### Pre-registration

The term lists and `n=3` are written **before the first run** and are not tuned
afterwards. Per item 22(a): tuning a threshold against the result turns the
instrument into a device for confirming the hypothesis you already hold. Whatever
the pre-registered probes say is the finding.

**Known weakness, recorded up front:** the terms are authored, so a red probe may
mean "the corpus lacks this content" *or* "the corpus lacks the words I chose".
The disambiguation step below catches this case too — if the corpus scan finds
the content the probe missed, the term list was the problem.

## A red probe is not a harvest signal

A red probe has two possible causes, and they call for opposite actions:
content absent (harvest) vs content present but unretrieved (a retrieval matter,
where harvesting is the wrong treatment). Item 5 is the standing proof that
guessing here goes wrong.

So every red probe gets a **disambiguation step**: a direct corpus scan for the
topic — the paginated `store.get` technique from item 19 (93k chunks at once
errors with "too many SQL variables"), or `evals/inspect_retrieval.py`.

### Decision procedure (fixed in advance)

| Probe | Corpus scan | Action |
|---|---|---|
| green | — | Topic is thin but costs us nothing. **No harvest.** |
| red | content absent | **Harvest** it, re-run the probe, promote to eval if green. |
| red | content present | Retrieval matter, not a corpus gap. **No harvest**; record in handoff. |

**All four green ends this work item**, and that is an accepted, good outcome —
agreed with the user before the first run so the result cannot be re-litigated
afterwards.

## Where the probes live

Probes run from a **throwaway script in the scratch directory**, calling
`retrieve_context()` and counting terms. They do not touch the harness.

This is the same measure-first discipline applied one level up: adding
`context_min` to `run_eval.py` now would commit a field that no case uses if the
probes come back green — dead code, shipped on a guess. The harness gains
`context_min` (TDD, unit tests, beside `_context_ok`) only if a probe earns a
permanent place in the eval.

Rejected: putting the probes straight into `eval_set.py` as failing cases. A red
probe that harvesting cannot fix would leave the eval permanently broken, and
"31/31" is the project's gate — a gate nobody can get green is a gate nobody
reads. That is the sibling of the vacuity bug: instead of an eval that is green
while asserting nothing, an eval that is red and therefore ignored.

## Scope

**In:** a scratch probe script; four pre-registered probes; the disambiguation
scan for any red; harvesting only what a red-plus-absent verdict justifies;
promoting rescued probes into `eval_set.py` (with `context_min` in the harness,
TDD) only then.

**Out:** harvesting `col_20.500.14283_3` speculatively; tuning the FAO filter
regexes; product-linker geography (handoff item 2, deferred); the EN→TR lexicon
(item 19, gated on the same audience decision).

## Verification

- The probe script's finding is the deliverable, whatever it says.
- If nothing is harvested: eval stays 31/31, suite stays green, and the handoff
  records the measurement so item 1 is closed rather than re-opened on the same
  hunch.
- If something is harvested: probe red → green on the same pre-registered terms,
  full eval still 31/31 (no regressions), promoted cases proven to guard by
  showing them red against the pre-harvest store.
