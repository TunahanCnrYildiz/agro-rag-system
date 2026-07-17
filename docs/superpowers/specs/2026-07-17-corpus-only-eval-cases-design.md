# Corpus-only eval cases: make the eval able to see the corpus

**Date:** 2026-07-17
**Status:** design, approved
**Files touched:** `evals/eval_set.py`, `evals/run_eval.py`, `tests/test_run_eval.py`

## The problem, measured

The eval cannot tell whether retrieval contributes anything. Ablation run
2026-07-17 — `engine.retrieve_context` forced to `""`, full eval:

```
dimension        normal   EMPTY CORPUS
grounding         31/31      31/31     <- ZERO change
guardrail         31/31      31/31     <- ZERO change
product-gating    31/31      27/31     <- the only signal
retrieval/context 31/31       7/31     <- tautological; the ablation emptied them
```

91,891 chunks from 1,004 PDFs, and the eval detects their value in 4 cases out of
31 — `tomato_nutrition`, `cassava_nutrition_tr`, `cassava_fert_en`, `compost`, all
`products:"some"` nutrition cases where an empty context starves
`match_products`. **The corpus's only measurable job today is feeding the product
matcher, not the answer.**

So every "eval 31/31" claim to date is a claim about **gemma + the prompt**, not
about retrieval. The eval stayed green from 65,500 to 91,891 chunks because the
corpus was never what made it green.

Why the existing dimensions miss it: `answer_any` is an any-of keyword check, and
a confident bluff passes it exactly like a grounded answer. The persona
(`config.py:148-150`) *deliberately* authorises bluffing — "if the context does
not cover the question, say so honestly and give general, safe guidance". The
system is hybrid by design; nothing was ever built to tell the halves apart.

## The corpus is NOT decorative — also measured

The ablation says the eval is blind; it does not say the corpus is useless. Direct
evidence, same day, on `dp_21747.pdf` (Şen, Ünal & Arda, *"Bursa yöresinde
yetiştirilen 'Deveci' armut çeşidinin yöresel olgunluk standartlarının ve
depolama durumlarının saptanması"*, ANADOLU J. of AARI 19(2) 2009):

Question: *"Deveci armudu ne zaman hasat edilmeli ve soğukta ne kadar
depolanabilir?"*

- **With the corpus:** "Bursa yöresinde... Ekim ayının ortası veya sonu... Kasım
  ortasına geciktirilirse çözünür kuru maddede olumsuzluklar... **2±0,5°C**'de
  yaklaşık 6 ay" — the paper's findings, reproduced.
- **Ablated:** "Eylül sonundan Kasım başına... **0-2°C**... **3 ila 6 ay**" —
  generic, hedged, wrong harvest window, no region.

The corpus contributes specific, local, correct detail. The eval simply never
asked for it. That is what this spec fixes.

## Design

### The case shape

A new category, `local`: a **natural Turkish question a grower would actually
ask** about a Turkey-specific cultivar, asserting **a specific finding from the
source paper**.

```python
{"id": "local_deveci_pear", "category": "local",
 "query": "Deveci armudu ne zaman hasat edilmeli ve soğukta ne kadar depolanabilir?",
 "retrieval": "nonempty", "products": "none",
 "context_any": ["deveci"],
 "answer_any": ["2±0,5", "2±0.5", "2 ± 0,5", "2 ± 0.5"]}
```

`answer_any` needs no new mechanism: listing only the spelling variants of ONE
value makes an any-of behave as "this fact must be present".

`products: "none"` follows eval_set's standing stance — the catalog is 48
fertilizers and none of them answers a harvest-timing question.

### The discipline: the assertion comes from the DOCUMENT, not from the output

The easiest way to ruin this. In the Deveci probe, `2±0,5°C` is **the paper's
value** — legitimate. "Bursa" also discriminated, but picking it *because the
ablated answer lacked it* would be tuning the assertion to the result — exactly
what item 22(a) warns about.

**Rule: derive each assertion from the source document before running anything.**
The ablation then answers one question only: does this assertion discriminate? If
it does not, **the case is dropped, never re-tuned.** A case tuned until green
asserts nothing — the vacuity bug wearing a new hat.

This rule has already earned its place: the first assertion drafted for Deveci was
`answer_any: ["6 ay"]`, which does **not** discriminate — the ablated answer also
says "3 ila 6 ay". A plausible-looking case that measured nothing.

### Validation: a case must be RED ablated and GREEN normally

Same move item 12 used for the cross-lingual cases (flip the toggle, watch five go
red). A `local` case that stays green under ablation is decorative and does not
ship.

### `run_eval.py --no-context`

The validator, committed rather than performed once, because a case's
discrimination can silently rot when someone edits it later. Unlike `--repeat`
(item 21 — insurance, catches nothing today) this has a concrete recurring
trigger: **run it whenever a `local` case is added or edited.**

Behaviour:

- Forces `engine.retrieve_context` to return `""` for the whole run.
- **Does not score `retrieval`/`context`** — the flag emptied them by
  construction, so counting them would print 24 tautological FAILs (measured) and
  bury the signal. They report `n/a`.
- Prints the ablation verdict for the cases that exist to be ablated:
  ```
  [ablation] local cases that lost grounding: 3/3 - they discriminate
  ```
- **The exit code answers the ablation's question, not the eval's.** Under
  `--no-context` the normal pass/fail rule would exit 1 on every run regardless —
  product-gating alone drops to 27/31 by construction (measured) — so an exit code
  driven by it carries no information. With this flag the exit code is **0 when
  every `local` case lost grounding** (they all discriminate) and **1 when any
  `local` case still passes grounding** (that case is decorative). Ordinary cases
  failing is expected here and must not affect it.
- **Exit 1 if there are no `local` cases in the selection at all** — otherwise
  "0 of 0 discriminate" would exit 0 and report success for a run that validated
  nothing. Same vacuity trap as `all([])`, which this project has already shipped
  once (item 4's `answer_none`).
- Composes with `--only` and `--fast` is rejected: `--fast` never calls
  `answer()`, so `--no-context --fast` has nothing to ablate. Exit 1, as
  `--fast --repeat N>1` already does.

### Scope: 3 candidates, survivors only

**Amended after mining (2026-07-17).** This section first named five cultivars
picked by chunk count — `deveci` 84, `amasya` 33, `gemlik` 27, `santa maria` 27,
`0900 ziraat` 23. Reading the sources killed two of them, and the reason matters:
**a chunk count measures a WORD, not what the document is about.**

- **Amasya apple — the cultivar is not in the corpus.** `"amasya elma"` and
  `"amasya kırmızısı"` both scan to **0 chunks**. The 33 `amasya` hits are the
  PROVINCE name in the distribution lists of a Scarabaeidae fauna survey
  (`dp_1052881.pdf`).
- **Gemlik olive — wrong topic.** `"gemlik zeytin"` scans to 2 chunks, both in
  `dp_1869487.pdf`, a metabolomics study of the geographic origin of Gemlik olive
  OIL (food authenticity, adulteration). No natural grower question lands there.

That is the same error this project measured and closed hours earlier: FAO breadth
was chased on chunk share, and chunk share turned out to be a vanity metric
(handoff item 1). It was repeated here within the same day, at a smaller scale.

The surviving candidates are **`deveci`, `santa maria`, `0900 ziraat`**. For each:
read the source chunks, extract a specific finding, write a natural question, then
ablation-validate.

**Fewer than three may survive, and that is an accepted outcome.** A cultivar
whose corpus content is not specific enough, or whose facts gemma already knows,
yields a case that does not discriminate — and it does not ship. One survivor
would mean the eval guards retrieval in one more place than it does today, which
is one more than zero. Deveci is already validated.

## Out of scope

- `answer_min` (n-of-m on the answer). Try single-concept `answer_any` first; only
  if cases die of brittleness does an n-of-m field have a measured user. Same
  reasoning that kept `context_min` out on 2026-07-17.
- Fixing the corpus, the retrieval, or `retrieval_k` (item 24 — closed, dead).
- The product-matcher's correctness (a real gap, blocked by catalog data).
- Backfilling `local` cases for the non-Turkish corpus (ia_/fao_/oa_).

## Testing

TDD. `tests/test_run_eval.py`:

- `--no-context` makes `retrieve_context` return `""` on the path `answer()` uses
- `retrieval`/`context` are reported `n/a`, not scored, under `--no-context`
- a `local` case that loses grounding under ablation → counted as discriminating
- a `local` case that keeps grounding under ablation → exit 1
- ordinary (non-`local`) cases failing under ablation → does NOT affect the exit
  code (the guard against the "always exits 1, so the code says nothing" trap)
- `--no-context` with no `local` case in the selection → exit 1, not 0
- `--no-context --fast` exits 1

Existing fakes and `monkeypatch` stay the idiom; no test calls a real model.

## Verification

- Each shipped `local` case demonstrated RED under `--no-context` and GREEN in a
  normal run.
- The full eval stays green on every dimension with the new cases included.
- Any candidate that failed to discriminate is recorded in the handoff with what
  it asserted, so nobody rewrites it later on the same hunch.
