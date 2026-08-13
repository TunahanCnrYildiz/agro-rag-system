# crop_choice — gate results and the prohibition that could not be measured

Plan: `docs/superpowers/plans/2026-08-13-crop-choice.md`
Spec: `docs/superpowers/specs/2026-08-11-budget-and-crop-choice-design.md` §5, §8
Branch: `crop-choice`, through Tasks 1-2 and four post-review fix rounds on the
eval case (`0b1aff2`, `70b66c6`, `f10fb08`, `dc38b48`)

`crop_choice` now diverges the same way `fert_plan` did: a route-specific
context block is prepended to the system prompt, and the answer is still
produced by the existing corpus path. This is the second route to diverge,
and the first one where the divergence is entirely a prompt constraint —
"explain the factors, do not name a crop" — with no module and no arithmetic
behind it.

---

## 1. What shipped

`src/engine.py::_context_block` gained a `route == "crop_choice"` branch that
delegates to a new `_crop_choice_block(message, history, today)` helper. For
every other route the function's behaviour is unchanged — `""` by default,
the `fert_plan` branch untouched.

The block, when a province is given, reads:

```
Tarih: Ağustos ayı, yaz.
Kullanicinin ili: Manisa.
Bu bir urun secimi sorusu. Karari belirleyen faktorleri anlat ve eksik
olanlari sor: toprak yapisi ve analiz, sulama imkani, arazi buyuklugu,
onceki urun ve munavebe, pazara mesafe, isgucu ve makine.
BELIRLI BIR URUN ONERME. Kullanicinin kosullarini bilmeden urun onermek bir
sezonluk gecim karari hakkinda temelsiz tavsiye olur.
```

With no province it substitutes a `BILINMIYOR` line asking which province,
same as `fert_plan`. There is no weather line — the question spans a season,
not the next few days, so the weather module is not consulted at all. Like
`fert_plan`, a context-build failure (season or location module raising)
degrades to `""` and costs only the situation lines, never the answer
(spec §8; pinned by
`test_a_crop_choice_failure_degrades_to_an_empty_block`).

**The one thing this route deliberately does not do: name a crop.** The
`BELIRLI BIR URUN ONERME` line is unconditional prompt text. It is not
enforced by code — spec §5 says explicitly that detecting "recommended a
crop" in Turkish free text is the same problem the product-suppression
backstop already finds hard, and this plan does not reopen that.

---

## 2. Numbers

| Metric | Before this plan | After |
| --- | --- | --- |
| pytest | 471 | **477** (+6, all in `tests/test_engine.py`) |
| eval cases | 58 | **59** (+1, `crop_choice_gives_factors_not_a_recommendation`) |
| Routing accuracy | 37/42 (88%) | **37/42 (88%)**, unchanged |

Two warnings in the pytest run are third-party and pre-date this branch:
starlette's testclient httpx deprecation, and chromadb's
`asyncio.iscoroutinefunction` deprecation.

Routing was re-measured twice — once by the Task 1 implementer before
touching any code, once by the controller after — and both reads agree:
`crop_choice` sits in `sevke uygun rotalar (sifir yanlis giris)` (zero wrong
entries), which is the only condition this plan needed to be permitted to
diverge. The overall gate still reads `KAPILAR: GECMEDI` because `plant_info`
absorbs five cases that belong to other routes; that is a pre-existing,
expected failure this plan does not touch and is not responsible for fixing.

**The full 59-case shield has NOT been run.** LM Studio was down for the
entire session — every attempt to reach it is recorded in the Task 2 report
as deferred. This is the plan's own exit gate 2 (`evals.run_eval` at 59/59)
and it is **open**. Nothing in this document should be read as implying that
gate passed; it has simply not been attempted yet.

---

## 3. Did the prohibition hold? — UNMEASURED, and that is the headline finding

Spec §5 states the crop-naming prohibition "is measured by the eval's
`answer_none` guardrail dimension." **With this harness, it is not.** Four
review rounds on the single `crop_choice` eval case established why, each
exposing a distinct defect class in trying to write a substring guardrail
for it:

1. **Round 1 — the anchors were the wrong shape of violation.** The first
   `answer_none` list (`["şunu ekin", "bunu ekmenizi öneririm"]`) banned
   demonstrative-pronoun *templates* a real violation never contains. A model
   that actually breaks the prohibition writes the crop's name — "pamuk
   ekmenizi öneririm" — not a pronoun, so neither banned phrase would ever
   fire on a genuine violation.
2. **Round 2 — the bare modal fired on compliant answers.** Narrowing to
   "ban the act, not the pronoun" added `"ekebilirsiniz"` as an anchor. It
   also matches compliant sentences that use the same modal without naming a
   crop — "en uygun türü seçip ekebilirsiniz" — a false positive on exactly
   the "explain and let the grower decide" style the case exists to reward.
   Dropped, with the resulting gap ("buğday ekebilirsiniz" now escapes)
   documented rather than silently reintroduced.
3. **Round 3 — multi-word stems collided with Turkish agglutination.**
   `evals/run_eval.py`'s `_answer_ok` matches `answer_none` terms with a
   plain `in` and no word boundary, on the comment's own stated assumption
   that "every answer_none term is one word." This case's anchors were the
   first multi-word terms in the file, and agglutination broke the
   assumption immediately: `"çekmenizi öneririm"` (asking to draw water) ends
   in the substring `"ekmenizi öneririm"`, so a compliant irrigation answer
   naming no crop would have tripped the guardrail. A leading space on each
   anchor restored the boundary the plain `in` test lacks.
4. **Round 4 — the ruling.** Even boundary-corrected, the guardrail runs
   **backwards** on realistic Turkish:

   | Sentence | Should be | Actual |
   | --- | --- | --- |
   | `"Buğday ekmenizi kesinlikle öneririm."` | caught | **escaped** — an adverb between object and verb splits the phrase |
   | `"Buğday ekmenizi şiddetle tavsiye ederim."` | caught | **escaped**, same cause |
   | `"Size ne ekmenizi önereceğimi söyleyebilmem için toprak analizi gerekli."` | quiet | **flagged** — and this is the compliant answer |
   | `"Hangi ürünü ekmenizi önerebileceğimi ancak sulama imkanınızı bilirsem söylerim."` | quiet | **flagged** |

   The root cause is that the two classes differ by the verb's **object** — a
   crop name versus an interrogative — which no substring or regex can see.
   Separating them needs a crop lexicon, a route this project has already
   measured and rejected elsewhere.

**The user ruled: remove the dimension rather than ship a guardrail whose
green reads as evidence.** Commit `dc38b48` deleted `answer_none` from the
case entirely — not emptied to `[]`, removed as a key — and replaced it with
a comment recording the omission as a measured finding, pointing here. The
case's key set is now exactly `answer_any, category, id, products, query,
retrieval`.

**The case still measures something real.** It keeps `answer_any` (`toprak`,
`sulama`, `münavebe`, `pazar`) — the requirement that the factors actually
get explained — and a reviewer verified this dimension can go red for a
plausible bad answer, so it is not a guardrail that only ever passes. The
verification the ruling itself demanded shows the surviving signal directly:
against `guardrail=True` on all three test sentences above (nothing left to
measure the prohibition), `grounding` split `False` / `True` / `True` in the
same order — the factors-explained requirement discriminates even though the
crop-naming prohibition no longer does.

**A process finding worth recording on its own.** Twice during these four
rounds, a verification probe used `_matches` directly rather than going
through the real `_answer_ok` path. `_matches` applies a left word boundary;
`answer_none` matching in `_answer_ok` uses a plain `in` with no boundary at
all. A probe exercising the wrong function reads as evidence while checking
nothing — the same lesson this project has already recorded elsewhere about
instruments being wrong more often than the systems they check.

---

## 4. Weak anchors, recorded so they are not rediscovered

In the surviving `answer_any` list, two of the four terms match inside
longer, unrelated words through the real (lowercasing) path:

- `pazar` matches inside `Pazartesi` ("Monday").
- `toprak` matches inside `topraksiz` ("soil-less").

`answer_any` is an *any* match over four terms, so these lower the case's
power rather than making it wrong — a case could pass on a weak match alone
without ever hitting `sulama` or `münavebe`. Not fixed here; recorded so the
next person does not treat rediscovering them as a new bug.

(A related false alarm during Task 2: probing `_matches('pazar',
'Pazartesi gunu')` directly prints `False`, because `_matches` does not
lowercase its own arguments and the probe passed capital `P`. Every real
caller — `_answer_ok`, `_context_ok` — lowercases both sides first, so this
is a probe-harness artifact, not a behaviour change. Listed here because it
looks like the same class of finding at a glance and is not.)

---

## 5. An open spec question this plan deliberately did not settle

The block's `BELIRLI BIR URUN ONERME` line is unconditional — it always
tells the model not to name a crop, regardless of what the user has already
answered. The stakeholder (Hüseyin) does want the product to help with crop
choice, and `docs/client-requirements.md` §6 records the agreed position:
statistics say what crops **are** grown, not what **can** be grown, so the
data informs a planting decision rather than making one. That is consistent
with today's unconditional design.

But once the numeric data layer lands **and** the user has answered the
factor questions this route asks (soil, irrigation, plot size, previous
crop/rotation, market distance, labour/machinery), the prohibition may need
to become conditional — "if you know the conditions, rank the candidates
with reasons; if not, ask." That is a spec-level change, not a defect in
what shipped here, and it is recorded as a follow-up rather than acted on:
this plan's job was to make the route explain factors and ask questions, not
to design the ranking behaviour a future data layer would enable.

---

## 6. What this route still cannot do

Say this plainly, because it is the honest boundary of the feature: the
route explains the factors that decide a crop-choice question and asks for
whichever of them the user has not supplied. It has **no soil data, no
market-price data, and no rotation data behind it** — nothing that could
turn an answered set of factors into a ranked list of candidates. Even a
user who answers every question this route asks gets, today, a well-informed
explanation and nothing that could be called a recommendation. That is by
design (§1), not an oversight, but it means the route's ceiling is "explain
and ask," not "advise," until a numeric data layer exists to rank against.
