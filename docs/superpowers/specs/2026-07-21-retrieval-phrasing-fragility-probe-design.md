# Retrieval phrasing-fragility probe — design

**Date:** 2026-07-21
**Status:** design (approved in brainstorming)
**Scope:** MEASUREMENT ONLY. No fix is designed or built in this round.

## 1. The question

Retrieval is phrasing-sensitive. The recorded symptom: the `local_santamaria_pear`
question retrieves 4030 chars under the eval's wording, 2964 under a plainer one, and
**0 chars** under one natural rewording — nothing clears the 0.36 similarity floor.
Similar pairs are on record: `"Bağda kurşuni küf…"` → 0 but `"Üzümde kurşuni küf
hastalığı nasıl önlenir?"` → 3945; `"Kabakta elle tozlama…"` → 0 but `"Kabakta
tozlaşma nasıl olur?"` → 4049.

**Why this matters more than growing the eval panel.** The `corpus_fact` panel proves
the corpus *works*; it does not make the corpus *reach users*. When retrieval returns
nothing the system does not crash — the model answers from parametric knowledge and
(measured) produces a safe, sensible, but GENERIC answer. So the user-visible harm is
"generic instead of specific", silently, on some fraction of natural questions. That
fraction has never been measured on purpose.

**Existing numbers are by-products, not measurements.** A 48-question scan found 2
zero-chunk; an earlier 30-probe audit found 1 true zero + 4 near-empty; 9 of 10 short
natural questions were healthy. These came from three different sessions, different
probe sets, and straddle the corpus prune — they suggest roughly 2-7% but cannot
support a decision. Designing a fix against that range is the mistake this project
keeps catching (a proxy moving is a hypothesis, not a result).

**Closed doors, not to be re-opened by this work:** lowering the global 0.36 floor is
measured DEAD (at 0.34 an off-scope "bilgisayar…" query pulls 20 chunks at 0.4065);
LLM query rewriting/translation is DEAD (gemma returns empty on ~half); reranking is
DEAD when the candidate pool is empty. See `do-not-rechase`.

## 2. Design — a paraphrase set with a built-in control

The defect is **variance across phrasings**, not coverage. A flat list of natural
questions cannot measure it: when such a question returns 0, we cannot tell whether
the content was missing or merely unreachable, and each case needs manual chasing.

So: build the probe set on the **18 `corpus_fact` cases**, where the content is known
to exist (each was live-validated) and the eval phrasing is known to work. Each case
contributes **3 natural rewordings** → **54 probes**. Every probe has its own control:
if the eval wording retrieves the source and a natural rewording does not, that is a
pure ACCESS failure with content presence held constant.

**Stated limitation, up front:** those 18 queries were authored to work, so their
paraphrases may be friendlier than what a real user types. The result is therefore a
**lower bound** — "even when the content is definitely present, fragility is X%" —
not an estimate of real-user fragility. That is still a decision-grade number.

**Per probe, retrieval only (no chat model):** chunk count, context length, top
similarity score, and the retrieved source ids.

**Success is defined by SOURCE HIT, not context length.** 4000 chars from the wrong
paper is not better than 0 — a 3945-char retrieval was once read as healthy and its
chunks were mostly noise. Three outcome classes:

| Class | Meaning |
|---|---|
| **HIT** | the case's own source document is among the retrieved chunks |
| **MISS-EMPTY** | 0 chunks — nothing cleared the floor |
| **MISS-WRONG** | chunks returned, but the case's source is absent |

**Two definitional points, fixed now so they cannot be decided after seeing results:**
- A case may cite MORE THAN ONE source (`disease_rhizoctonia_biocontrol` cites
  `dp_21748` + `dp_1004550`). For such a case, retrieving **any one** of its cited
  sources counts as HIT. Its expected source set is written down with the frozen
  paraphrases, before running.
- `disease_rhizoctonia_biocontrol` is `model-carried`, not corpus-carried. It stays in
  the probe set anyway: this round measures RETRIEVAL, which is a separate question
  from whether the model needed the corpus to answer. Its result is reported but also
  flagged, so the count can be re-derived over the 17 corpus-carried cases alone.
- Four cases (`santamaria`, `ankara`, `beurrehardy`, `bpmorettini`) share the source
  `dp_19393`. The probe set therefore covers 16 distinct documents, not 18. This does
  not bias the measurement — each probe asks whether ITS question reaches ITS source —
  but it means the result speaks about 16 documents' reachability, and a systematic
  problem with `dp_19393` would show up 4 times.

## 3. Pre-registered decision rule

Fixed BEFORE any probe runs. The failure count is MISS-EMPTY + MISS-WRONG.

| Result | Decision |
|---|---|
| **≤ 2 / 54** | Fragility is not a practical problem. CLOSE it, record the finding, build nothing. |
| **≥ 6 / 54** | Worth fixing. Proceed to a separate mechanism-design spec. |
| **3-5 / 54** | Genuinely undecidable at this n. Extend the set by +54 paraphrases, then re-apply this rule. |

**Why the bands are coarse.** At n=54, 3 failures is ~5.6% with a confidence interval
of roughly [1%, 15%]. A single percentage cannot be trusted here. The blank-answer
investigation is the cautionary precedent: its rate walked 20% → 7% → 5% → 3% as n
went 10 → 100, and every figure before the last was over-confident. The middle band is
named "undecidable" deliberately, so that an ambiguous result is resolved by more data
rather than by argument after the fact.

**The SHAPE of failures does not affect go/no-go** — only which mechanism to design if
the threshold is met. "The rate is low but the pattern is so clear, let's build anyway"
is explicitly ruled out here, in advance.

**MISS-WRONG is counted as a failure**, which makes the threshold easier to reach than
a zero-chunk-only rule would. This is deliberate: from the user's side, retrieving the
wrong document contributes nothing. Both classes are reported SEPARATELY so the
decision stays auditable and can be re-derived under a stricter rule.

## 4. Paraphrase authoring discipline

Three paraphrases per case, each targeting a distinct plausible failure mode, so the
set is systematic rather than hand-picked:

1. **Colloquial / short** — how a grower would actually type it
   ("Deveci armudu kaç ay dayanır?").
2. **Inflected / suffixed** — Turkish morphology variation. The lexicon matcher's
   suffix bug came from exactly this axis.
3. **Alternative term** — a different word for the same concept
   ("muhafaza" ↔ "depolama", "tozlayıcı" ↔ "dölleyici").

**Validity rule:** a paraphrase must carry the SAME information need. Narrowing it,
broadening it, or hinting at the answer or the source is forbidden — that produces a
leading query and inflates the result. The dropped `local_sebin_walnut` case is the
precedent: its term only entered the context when the query itself supplied it.

**Freeze:** all 54 paraphrases are written and saved BEFORE a single probe runs. After
the first run none may be edited, added, or removed.

## 5. Recording & deliverable

Recorded per probe: case id, paraphrase category, outcome class, chunk count, top
score, retrieved sources. For failures, also the **gap between the top score and the
0.36 floor** — "just missed" and "nowhere close" are different defects and point at
different mechanisms.

- The spec (this file) is committed; it holds the pre-registration.
- The probe script and raw output are scratch and NOT committed (round-3 precedent:
  pre-registration lives in the committed spec, so the terms stay auditable without
  carrying a script).
- The result is written to `handoff-next-steps`, and to `do-not-rechase` **especially
  if the answer is ≤2** — in that case the record's whole job is to stop this question
  being re-opened.

**Cost:** this measurement needs only the embedding model, not the chat model, so 54
probes take minutes rather than the hours round 3's validations took. That is what
makes extending the set a real option if the undecidable band comes up.

## 6. Explicit non-goals

- **No fix in this round.** Mechanism design is gated on the result and gets its own
  spec only if the count reaches 6.
- No corpus data added — three independent measurements found no genuine data gap.
- No change to the 0.36 floor (measured dead), the prompt (measured harmful), or any
  retrieval code.
- No new eval cases. This is not a panel round.
