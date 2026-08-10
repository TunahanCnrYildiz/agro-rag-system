# Routing foundation — gate results

Plan: `docs/superpowers/plans/2026-08-10-routing-foundation.md`
Spec: `docs/superpowers/specs/2026-08-09-routing-and-context-design.md`
Branch: `routing-foundation`, base `fd40d06`

Routing now runs in front of the answer pipeline and is measured. No route
changes what a user receives — that was the point of doing this first.

---

## 1. Environment

The Faz 0 baseline was measured on a chat model that had fallen back to CPU:
**8.2 tok/s** against a 120 s client timeout, so 25 of 57 probe samples timed out
and measured nothing. Restarting LM Studio did not fix it; the machine has an
**AMD Radeon RX 9070 XT** and no NVIDIA GPU, and LM Studio silently uses the CPU
unless a suitable runtime is selected.

After the GPU was engaged: **61.3 tok/s**, a 7.5× recovery. Every number below
was measured after that.

A second observation from the same check, unrelated to this branch but worth
recording: with the production settings, a typical answer spends **~2,028
characters on internal reasoning and ~759 on the visible reply** — roughly three
quarters of the generated tokens are never shown. Locally that costs only time.
On a hosted provider it is a direct cost multiplier, so `max_tokens`,
`request_timeout` and the reasoning setting should be reviewed together at the
provider switch.

## 2. Unit suite

`pytest`: **276 → 334 passing**, no test changed verdict at any task boundary.

## 3. Routing gate — FAILED

```
dogruluk : 37/42 (88%)   kapi: >= 90%   -> GECMEDI
kural disi (varsayilan rota) orani : 13/42 (31%)   bilgi amacli, kapi degil
karar dagilimi : {'rule': 29, 'default': 13}
```

The five misses, all falling to the `plant_info` default:

| Expected | Query | Effect on the user |
| --- | --- | --- |
| nutrition | Domates yapraklarım sararıyor, ne önerirsiniz? | none — same corpus path |
| nutrition | Toprağımın pH değeri çok yüksek, nasıl düzeltebilirim? | none — same corpus path |
| nutrition | Bitkilerde demir eksikliği nasıl giderilir? | none — same corpus path |
| budget | Zeytinlikten yıllık ne kadar gelir beklerim? | **real gap** |
| offscope | Bu akşam hangi filmi izleyeyim? | none — the `[OFFSCOPE]` marker still refuses it |

Four of the five have no user-visible consequence in this release, because
`plant_info` and `nutrition` run the same path and the off-scope refusal is
still handled by the existing marker. Behaviourally distinct accuracy is
**40/42 = 95%**.

**The gate is reported as failed anyway.** The 90% threshold was pre-registered
before measuring, and changing a metric after seeing the result is exactly what
pre-registration exists to prevent. Both numbers are recorded; the ruling is the
human's.

### Why the rules leave 13 undecided

Not a gap in the stem lists. `plant_info` and `nutrition` between them *are* the
default, so neither can have a positive rule, and 15 of the 17 originally
undecided cases expect one of those two. Adding a nutrition rule moved 17 → 13
and no further widening helps.

## 4. Model-layer gate — VOID, not failed

The spec's "model layer must fire on ≤ 30% of queries" no longer measures
anything: the model layer was measured and **deliberately not built** (see the
plan's revised Task 4). `classify()` returns only `rule` or `default`, and
`default` costs no model call.

The scorer originally printed `by_how["model"] + by_how["default"]` under the
label "model katmani tetiklenme", announcing that a model fired on 31% of
queries when the true count was **zero**. That line was corrected: the gate no
longer participates in the verdict, the output states why, and the number is
reported as the rule-fallback rate, labelled informational.

## 5. Regression shield — 54/55, and it is not a regression

```
retrieval 55/55 | context 55/55 | product-gating 55/55 | grounding 54/55 | guardrail 55/55
```

`--fast` (retrieval + context only, no LLM): **55/55**. That alone clears the
`_TR_FOLD` change — the only paths `_normalize_tr` feeds are query expansion and
the product backstop, and both are green.

The single failure, `quant_wheat_nitrogen_dose`, failed **only** on grounding.
Escalated to `--repeat 8` per the project's two-stage drift gate:

```
prod=8/8  ground=6/8  guard=8/8
```

Reading the eight logged answers settles it. **All eight contain the correct
figure.** The two that scored red wrote it in scientific unit notation:

- sample 4 — `16 kg da⁻¹ azot dozunun ekonomik olarak yeterli olduğu`
- sample 5 — `16 kg da-1 azot dozunun daha ekonomik olduğu`

The case's anchors are `16 kg/da`, `16 kg saf azot`, `16 kg n`. None of them
sees `kg da-1` or `kg da⁻¹` — which is the notation agronomy papers use, i.e.
the corpus's own. The model echoing its source is being scored as a miss.

Three pre-branch runs of this case all passed, but each with a *different*
phrasing (`16 kg saf azot` once, `16 kg/da` twice). They passed on phrasing
luck, not because the anchor set was adequate.

**Conclusion: the hard gate is not violated.** This branch cannot have caused it
— the route is computed and discarded, and the answer path is untouched. This is
a pre-existing narrowness in the eval's anchor set for one case.

### It is the third instance of a known class

The project has fixed this twice already, both times by **normalising the
searched text, never the anchor**: LaTeX notation (`$2\pm0,5^\circ$`) and
markdown emphasis (`**6 gram**`). Unit notation (`kg da-1`, `kg da⁻¹` → `kg/da`)
is the same shape and deserves the same fix — in its own small change, not here.
The lesson this project already wrote down applies again: *a measurement
instrument's blind spots look exactly like findings about the thing being
measured.*

## 6. Product-gate probe — superseded, not run again

The plan called for re-running `evals/probe_product_gate` on a healthy model to
close the question the CPU-bound baseline could not answer. The full eval
already answers it more broadly: **product-gating 55/55**, across all 55 cases
(19 that must show products and 35 that must not), against a healthy model.

The probe's value is attributing a *closed* gate to one of four causes. With
nothing closed, there is nothing to attribute. Recorded rather than spent.

This also resolves the original complaint that started Faz 0: **the product gate
is not defective locally.** The remaining hypothesis for the reported behaviour
is the deployment, which was rebuilt from a fresh, much smaller corpus (a few
hundred documents against 1,050 here) — different context, different similarity
scores, different threshold behaviour.

## 7. Carried forward

**To Plan 2, as its first task.** `stream_answer()` does not route. It is the
production path for both the mobile app and the web widget (`stream: true`), so
when routes diverge, divergent behaviour would reach no real user. Harmless
today because every route runs the same path.

**To Plan 2 or before it.** `fert_plan`'s AND-gate still uses the broad
`_NUTRITION_STEMS`, so `besle`/`besin` plus any time stem misroutes animal
feeding — `İneklerimi ne zaman beslerim?` → `fert_plan`. Inert while nothing
dispatches on the route. The comment at `src/router.py` claiming the time stem
supplies the missing specificity is wrong and should be corrected with the fix.

**Known stem collisions, deliberately unfixed.** `hangi urun` (generic "which
product"), `ne ekmek` (collides with *ekmek* = bread), and `program` in
`_TIME_STEMS`. None breaks the frozen set; none is user-visible while all routes
share a path.

**The underlying property, not a bug to patch away.** Four rounds of collisions
were found and fixed in the rule lists — `gider`/`giderilir`, `zararlı` = pest,
`İnek gübresi` → offscope, `besle` → animal feeding, `geri dönüş` → recycling.
Each fix surfaced the next. Substring matching over short Turkish roots has an
unbounded false-positive surface; `evals/run_routing.py` now measures it every
run, which is the right place for it.

**Router failures are silent.** The `except Exception` around the routing call
swallows everything by design, but nothing logs it, so a real router regression
would be invisible in production.
