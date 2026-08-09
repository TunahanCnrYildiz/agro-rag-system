# Routing Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add intent routing in front of the answer pipeline and measure it, while changing no user-visible behaviour.

**Architecture:** A new `src/router.py` classifies each query into one of six routes: a deterministic rule layer first, one classification call through the existing `ChatProfile` when the rules are undecided, and a fall back to today's behaviour on any failure. `engine.answer()` and `engine.stream_answer()` compute the route and record it, but every route still runs today's corpus path. Behaviour changes land in the two follow-up plans; this one makes routing exist, safe, and measurable.

**Tech Stack:** Python 3.14, pytest, existing `evals/` harness, OpenAI-compatible client already configured in `src/engine.py`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-09-routing-and-context-design.md`
- `src/engine.py` corpus path is **not** modified beyond adding the dispatch call. The `[OFFSCOPE]` / `[NOPRODUCT]` markers, the product-suppression backstop, the empty-answer guard and stream-truncation recovery all stay exactly as they are.
- The router **cannot break the system.** Any failure — rule miss, model error, malformed label — falls back to today's behaviour.
- Turkish matching uses the existing `engine._normalize_tr` fold and the existing left-boundary convention. Short stems that collide with unrelated words must be whole-word matched instead (see Task 3).
- The routing set is frozen **before** the router is implemented (Task 2 precedes Task 3).
- Exit gates from spec §9 apply: zero regression in the 55 eval cases, ≥90% routing accuracy, model layer firing on ≤30% of queries.
- Run every Python command with `PYTHONIOENCODING=utf-8` — the Windows console cannot encode Turkish and any script printing corpus or answer text dies without it.

---

### Task 1: Separate call failures from gate closures in the probe

The Faz 0 baseline recorded 25 samples as `no_advice`. All 25 were `Request timed out.` — the machine was generating at 8 tok/s against a 120 s timeout, so the product gate was never actually measured on those samples. The probe conflates "the model call raised" with "a gate closed", which is why the raw run had to be read by hand.

**Files:**
- Modify: `evals/probe_product_gate.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `GATE_ERROR = "error"`, a distinct gate value written into `evals/runs/<UTC>-probe.jsonl` alongside an `error` field carrying the exception type and message.

- [ ] **Step 1: Add the new gate constant**

In `evals/probe_product_gate.py`, below the existing gate constants:

```python
GATE_ERROR = "error"        # the model call raised - NOT a gate closure
```

- [ ] **Step 2: Record call failures as their own gate**

Replace the sample loop body inside `main()` (the `for i in range(args.repeat):` block) with:

```python
        for i in range(args.repeat):
            err = None
            try:
                text = engine._complete_text(messages)
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {str(exc)[:120]}"
                text = engine._llm_unavailable_message(exc)
            if err:
                gate, flags = GATE_ERROR, {"error": err}
            else:
                gate, flags = _attribute_gate(len(raw), text)
            gates.append(gate)
            totals[gate] = totals.get(gate, 0) + 1
            fh.write(json.dumps({
                "case": c["id"], "category": c["category"], "sample": i,
                "raw_products": len(raw), "top_score": top,
                "gate": gate, **flags,
                "answer": text,
            }, ensure_ascii=False) + "\n")
            fh.flush()
```

- [ ] **Step 3: Make the summary tell the truth about failures**

Replace the closing block (from `unstable = ...` to the final `print`) with:

```python
    errs = totals.get(GATE_ERROR, 0)
    if errs:
        print(f"\nUYARI: {errs} ornek model cagrisi hatasiyla dustu "
              f"(zaman asimi / baglanti).")
        print("Bu ornekler urun kapisini OLCMEZ. Uretim saglikli hale "
              "gelmeden kapi yorumlanamaz.")

    unstable = [r for r in rows if 0 < r[2] < r[3]]
    print(f"\nkararsiz vaka (ayni soru bazen acik bazen kapali): {len(unstable)}")
    for r in unstable:
        print(f"  {r[0]:<34} {r[2]}/{r[3]} acik")
    if errs:
        print("\nKararsizligin bir kismi cagri hatasindan olabilir - "
              "once UYARI satirina bak.")
    else:
        print("\nKararsizlik varsa sorun esik degil, model/marker kaynaklidir.")
```

- [ ] **Step 4: Verify the self-test still passes and the probe starts**

Run: `PYTHONIOENCODING=utf-8 python -m evals.probe_product_gate --only tomato_nutrition --repeat 1 --tag "probe-fix-check"`
Expected: the header line prints, one case line prints, and the summary prints. If LM Studio is slow the line reads `error` rather than `no_advice` — that is the point of this task.

- [ ] **Step 5: Commit**

```bash
git add evals/probe_product_gate.py
git commit -m "Separate model-call failures from gate closures in the product probe"
```

---

### Task 2: Freeze the routing set

Authored **before** the router exists, so the set cannot be shaped by what the implementation happens to do. This mirrors the pre-registration used for the fragility probe on 2026-07-21.

**Files:**
- Create: `evals/routing_set.py`
- Test: `tests/test_routing_set.py`

**Interfaces:**
- Produces: `ROUTING_CASES: list[dict]`, each `{"query": str, "route": str}` where `route` is one of `plant_info`, `nutrition`, `fert_plan`, `budget`, `crop_choice`, `offscope`.

- [ ] **Step 1: Write the frozen set**

Create `evals/routing_set.py`:

```python
"""Frozen routing expectations. Authored 2026-08-10, BEFORE src/router.py existed.

Pre-registration matters here for the same reason it did for the fragility probe:
a set written after the implementation measures the implementation, not the
requirement. Do not edit a case to make the router pass - fix the router, or
record why the expectation was wrong.
"""

ROUTES = ("plant_info", "nutrition", "fert_plan", "budget", "crop_choice", "offscope")

ROUTING_CASES = [
    # --- plant_info: growing practice, plant health, physiology --------------
    {"query": "Asmada budama ne zaman ve nasıl yapılır?", "route": "plant_info"},
    {"query": "Meyve ağaçlarında aşılama nasıl yapılır?", "route": "plant_info"},
    {"query": "Domates yapraklarında kahverengi lekeler var, ne yapmalıyım?", "route": "plant_info"},
    {"query": "Serada domates yetiştirirken havalandırma neden önemlidir?", "route": "plant_info"},
    {"query": "Kabak çiçeklerinde tozlaşma olmuyor, ne yapabilirim?", "route": "plant_info"},
    {"query": "Çilek nasıl çoğaltılır?", "route": "plant_info"},
    {"query": "Hasat sonrası elmaları uzun süre nasıl saklarım?", "route": "plant_info"},
    {"query": "Damla sulama bitkiler için neden faydalıdır?", "route": "plant_info"},

    # --- nutrition: fertilization without a timing request -------------------
    {"query": "Domates yapraklarım sararıyor, ne önerirsiniz?", "route": "nutrition"},
    {"query": "Buğday tarlamda verimi artırmak için nasıl gübreleme yapmalıyım?", "route": "nutrition"},
    {"query": "Toprağımın pH değeri çok yüksek, nasıl düzeltebilirim?", "route": "nutrition"},
    {"query": "Evde kompost nasıl yapılır?", "route": "nutrition"},
    {"query": "Bitkilerde demir eksikliği nasıl giderilir?", "route": "nutrition"},
    {"query": "Zeytin ağaçlarımda meyve kalitesini artırmak için gübreleme?", "route": "nutrition"},
    {"query": "Manyok yetiştiriciliğinde gübreleme nasıl olmalı?", "route": "nutrition"},

    # --- fert_plan: nutrition AND timing ------------------------------------
    {"query": "Domatese ne zaman gübre vermeliyim?", "route": "fert_plan"},
    {"query": "Buğdayda azotu hangi dönemde uygulamalıyım?", "route": "fert_plan"},
    {"query": "Fındık için gübreleme takvimi çıkarır mısın?", "route": "fert_plan"},
    {"query": "Zeytinde gübreleme programı nasıl olmalı?", "route": "fert_plan"},
    {"query": "Asmaya hangi ayda besleme yapılır?", "route": "fert_plan"},
    {"query": "Domates fidesi diktim, ne zaman besleyeyim?", "route": "fert_plan"},
    {"query": "Gübreyi hangi dönemde vermem lazım?", "route": "fert_plan"},
    {"query": "Bu ay azotlu gübre atmalı mıyım?", "route": "fert_plan"},

    # --- budget: money ------------------------------------------------------
    {"query": "5 dönüm domates ektim 1 milyon masraf ettim, ne kadar kâr ederim?", "route": "budget"},
    {"query": "Buğday ekmenin dekara maliyeti nedir?", "route": "budget"},
    {"query": "Zeytinlikten yıllık ne kadar gelir beklerim?", "route": "budget"},
    {"query": "Fındık bahçesi kurmak kaç para tutar?", "route": "budget"},
    {"query": "Serada domates yetiştirmek kârlı mı?", "route": "budget"},
    {"query": "Girdi masraflarım ne kadar olur?", "route": "budget"},
    {"query": "Bu yatırımın geri dönüşü ne kadar sürer?", "route": "budget"},

    # --- crop_choice: what to plant -----------------------------------------
    {"query": "Bu yıl tarlama ne eksem iyi olur?", "route": "crop_choice"},
    {"query": "Hangi ürünü yetiştirmeliyim?", "route": "crop_choice"},
    {"query": "Bu sezon ne ekmek mantıklı?", "route": "crop_choice"},
    {"query": "Arazime hangi meyve ağacı uygun?", "route": "crop_choice"},
    {"query": "Bu yıl domates mi biber mi ekmeliyim?", "route": "crop_choice"},
    {"query": "Ne yetiştirsem daha iyi olur?", "route": "crop_choice"},

    # --- offscope: not about plants -----------------------------------------
    {"query": "İneklerimin sütü azaldı, ne yapmalıyım?", "route": "offscope"},
    {"query": "Traktörümün motoru çalışmıyor, ne yapmalıyım?", "route": "offscope"},
    {"query": "Bu akşam hangi filmi izleyeyim?", "route": "offscope"},
    {"query": "Balık yetiştiriciliği nasıl yapılır?", "route": "offscope"},
    {"query": "Kredi çekmek istiyorum, hangi banka uygun?", "route": "offscope"},
    {"query": "Yarın hangi takım maç yapıyor?", "route": "offscope"},
]
```

- [ ] **Step 2: Write the test that guards the set's shape**

Create `tests/test_routing_set.py`:

```python
"""The frozen routing set must stay well-formed; a malformed case would silently
weaken the gate it exists to enforce."""

import collections

from evals.routing_set import ROUTES, ROUTING_CASES


def test_every_route_label_is_known():
    for c in ROUTING_CASES:
        assert c["route"] in ROUTES, c


def test_queries_are_unique():
    seen = collections.Counter(c["query"] for c in ROUTING_CASES)
    assert [q for q, n in seen.items() if n > 1] == []


def test_every_route_is_represented():
    covered = {c["route"] for c in ROUTING_CASES}
    assert covered == set(ROUTES)


def test_set_is_large_enough_to_measure_a_90_percent_gate():
    # Below ~30 cases a single miss moves the rate by more than 3 points and the
    # 90% gate stops discriminating.
    assert len(ROUTING_CASES) >= 30
```

- [ ] **Step 3: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_routing_set.py -v`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add evals/routing_set.py tests/test_routing_set.py
git commit -m "Freeze the routing expectation set before the router is written"
```

---

### Task 3: Rule layer

**Files:**
- Create: `src/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `engine._normalize_tr(text) -> str` (existing).
- Produces: `Route` (type alias), `ROUTES` (tuple), `classify_by_rules(message: str) -> Route | None` — returns `None` when no rule fires.

**The short-stem trap.** Folding turns `kâr` into `kar`, which is a left-boundary prefix of `karar`, `karnabahar`, `karışım`, `kardeş`. The existing convention (left boundary only) is wrong for stems this short. `kar` is therefore matched as a **whole word**, and the test below locks that in — the same class of mistake the codebase already documents for `buda`/`budala` and `prun`/`Prunus`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_router.py`:

```python
"""Rule-layer routing. Deterministic: no LLM, no network."""

import pytest

from src.router import classify_by_rules


@pytest.mark.parametrize("query", [
    "5 dönüm domates ektim 1 milyon masraf ettim, ne kadar kâr ederim?",
    "Buğday ekmenin dekara maliyeti nedir?",
    "Serada domates yetiştirmek kârlı mı?",
    "Girdi masraflarım ne kadar olur?",
])
def test_budget_queries(query):
    assert classify_by_rules(query) == "budget"


@pytest.mark.parametrize("query", [
    "Bu karar doğru mu?",
    "Karnabahar nasıl yetiştirilir?",
    "Toprak karışımı nasıl hazırlanır?",
])
def test_short_stem_kar_does_not_leak(query):
    # 'kâr' folds to 'kar', which prefixes karar/karnabahar/karışım. Matching it
    # as a stem would route all three to budget.
    assert classify_by_rules(query) != "budget"


@pytest.mark.parametrize("query", [
    "Domatese ne zaman gübre vermeliyim?",
    "Buğdayda azotu hangi dönemde uygulamalıyım?",
    "Fındık için gübreleme takvimi çıkarır mısın?",
])
def test_fert_plan_needs_both_nutrition_and_time(query):
    assert classify_by_rules(query) == "fert_plan"


@pytest.mark.parametrize("query", [
    "Domates yapraklarım sararıyor, ne önerirsiniz?",
    "Evde kompost nasıl yapılır?",
])
def test_nutrition_without_time_is_not_fert_plan(query):
    assert classify_by_rules(query) != "fert_plan"


@pytest.mark.parametrize("query", [
    "Bu yıl tarlama ne eksem iyi olur?",
    "Bu sezon ne ekmek mantıklı?",
])
def test_crop_choice(query):
    assert classify_by_rules(query) == "crop_choice"


@pytest.mark.parametrize("query", [
    "İneklerimin sütü azaldı, ne yapmalıyım?",
    "Traktörümün motoru çalışmıyor, ne yapmalıyım?",
    "Yarın hangi takım maç yapıyor?",
])
def test_obvious_offscope(query):
    assert classify_by_rules(query) == "offscope"


def test_short_stem_mac_does_not_leak():
    # 'maç' folds to 'mac', which prefixes 'macar'. Macar fiği is a forage legume,
    # a perfectly in-scope plant topic.
    assert classify_by_rules("Macar fiği ekimi nasıl yapılır?") != "offscope"


def test_unknown_returns_none():
    assert classify_by_rules("Asmada budama ne zaman yapılır?") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.router'`

- [ ] **Step 3: Implement the rule layer**

Create `src/router.py`:

```python
"""Intent routing.

The pipeline used to run one path for every question: embed, search the corpus,
match products, answer. A budget question paid for a corpus search that cannot
hold its answer; a timing question never learned what month it was. This module
decides, before any of that work happens, which path a question takes.

Rules first, deliberately. Routing decided by the model would add a second
provider-portability surface, and this project has already measured one such
surface breaking: the [NOPRODUCT] marker stopped transferring when the chat
provider changed (2026-07-24). A deterministic rule costs nothing, never drifts,
and can be unit-tested without a network.
"""
from __future__ import annotations

import re
from typing import Literal

from src.engine import _normalize_tr

Route = Literal["plant_info", "nutrition", "fert_plan", "budget",
                "crop_choice", "offscope"]

ROUTES: tuple[str, ...] = ("plant_info", "nutrition", "fert_plan", "budget",
                           "crop_choice", "offscope")

# Stems match with a LEFT boundary and may run into their own suffixes, the same
# convention the crop lexicon and the product backstop use.
_BUDGET_STEMS = ("maliyet", "masraf", "gelir", "gider", "butce", "kazanc",
                 "ciro", "zarar", "yatirim", "geri donus")
# Whole-word only: folding 'kâr' gives 'kar', which is a left prefix of karar,
# karnabahar, karisim, kardes. A stem match here would be a silent false positive.
_BUDGET_WORDS = ("kar", "karli", "karlilik", "karlimi")
_BUDGET_PHRASES = ("kac para", "ne kadar tutar", "ne kadar kazan")

_NUTRITION_STEMS = ("gubre", "besle", "besleme", "azot", "fosfor", "potasyum",
                    "npk", "kompost", "besin")
_TIME_STEMS = ("ne zaman", "hangi ay", "hangi donem", "takvim", "program",
               "donemde", "bu ay", "zamanla")

_CROP_CHOICE_PHRASES = ("ne eksem", "ne ekmek", "ne ekmeli", "ne ekeyim",
                        "hangi urun", "ne yetistir", "hangi meyve",
                        "mi ekmeliyim", "hangi bitkiyi")

_OFFSCOPE_STEMS = ("inek", "buzagi", "koyun", "tavuk", "hayvancilik",
                   "balik yetistir", "su urun", "traktor", "bicerdover",
                   "banka", "kredi", "dolar", "borsa", "film", "takim")
# Whole-word only: folded 'mac' is a left prefix of 'macar', and 'Macar fiği' is
# a real forage legume. Same trap as 'kar'/'karar' above.
_OFFSCOPE_WORDS = ("mac", "maci", "maclar")


def _has_stem(folded: str, stems: tuple[str, ...]) -> bool:
    """Left-boundary match, so a stem may run into its own suffix."""
    return any(re.search(rf"(?<!\w){re.escape(s)}", folded) for s in stems)


def _has_word(folded: str, words: tuple[str, ...]) -> bool:
    """Both boundaries - for stems too short to be safe on the left alone."""
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", folded) for w in words)


def classify_by_rules(message: str) -> Route | None:
    """Return a route, or None when no rule fires and the model layer is needed.

    Ordered specific-to-general: a message that is both about money and about
    fertilizer ("gubre maliyeti") is a budget question first.
    """
    folded = _normalize_tr(message)

    if (_has_stem(folded, _BUDGET_STEMS)
            or _has_word(folded, _BUDGET_WORDS)
            or _has_stem(folded, _BUDGET_PHRASES)):
        return "budget"

    if _has_stem(folded, _CROP_CHOICE_PHRASES):
        return "crop_choice"

    if _has_stem(folded, _NUTRITION_STEMS) and _has_stem(folded, _TIME_STEMS):
        return "fert_plan"

    if _has_stem(folded, _OFFSCOPE_STEMS) or _has_word(folded, _OFFSCOPE_WORDS):
        return "offscope"

    return None
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_router.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/router.py tests/test_router.py
git commit -m "Add deterministic rule layer for intent routing"
```

---

### Task 4: Public entry point and safe default

**REVISED 2026-08-10, after measuring Task 3.** This task originally added a
model classification call for messages the rules could not decide. Measurement
killed it before it was written.

Against the frozen set the rule layer leaves 17 of 42 cases undecided, and 15 of
those 17 expect `plant_info` or `nutrition`. That is structural, not a gap in the
rule list: neither route has — or can have — a positive rule, because between
them they *are* the default. Widening the rules does not help; adding a nutrition
rule only moves 17 to 13.

The decisive point is that **`plant_info` and `nutrition` run the same corpus
path.** Paying for a model call to tell them apart buys nothing. So the model
layer is not built: when no rule fires, the default is taken directly.

This is the same trade this project already made once, when LLM query
translation was replaced by a deterministic lexicon: a model call that a fixed
rule can replace costs latency, money and reproducibility, and buys none of them
back.

The cost is real and worth stating: a special-route question phrased in a way no
rule catches now goes to the corpus path instead of its own route. Plans 2 and 3
will show whether that happens often enough to justify reviving the model layer,
and the routing set measures it every run.

**Files:**
- Modify: `src/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `classify_by_rules` (Task 3).
- Produces: `classify(message: str, history: list[dict] | None = None) -> tuple[Route, str]` where the second element is `"rule"` or `"default"`. No model call, no network, no `history` use yet — the parameter exists so Task 5 and later plans need no signature change.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_router.py`:

```python
from src import router


def test_rule_hit_reports_rule():
    assert router.classify("Buğday ekmenin dekara maliyeti nedir?") == ("budget", "rule")


def test_silent_rules_take_the_default_without_a_model_call(monkeypatch):
    # No network, no client, no chat profile. If classify() ever reaches for the
    # LLM, _get_llm is the first thing it would touch - so make touching it fatal.
    from src import engine
    def explode(*a, **k):
        raise AssertionError("classify() must not call the model")
    monkeypatch.setattr(engine, "_get_llm", explode)
    assert router.classify("Asmada budama ne zaman yapılır?") == ("plant_info", "default")


def test_default_is_todays_corpus_path():
    # plant_info and nutrition both run the corpus path; the default must be one
    # of them, or a rule-silent question would change behaviour.
    assert router._DEFAULT_ROUTE in ("plant_info", "nutrition")


def test_history_argument_is_accepted_and_ignored_for_now():
    history = [{"role": "user", "content": "Manisa'dayım"}]
    assert router.classify("Asmada budama ne zaman yapılır?", history) == \
        router.classify("Asmada budama ne zaman yapılır?")
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_router.py -k "classify or default or history" -v`
Expected: FAIL — `AttributeError: module 'src.router' has no attribute 'classify'`

- [ ] **Step 3: Implement the entry point**

Append to `src/router.py`:

```python
# The route taken whenever no rule fires. plant_info is today's corpus path, so
# an undecided question behaves exactly as it does now.
#
# There is deliberately NO model fallback here. Measured against the frozen set,
# the rules leave 17 of 42 cases undecided and 15 of those expect plant_info or
# nutrition - which is structural, since between them those two ARE the default
# and cannot have a positive rule. And they run the SAME corpus path, so a model
# call to tell them apart would change nothing while costing latency, money and
# reproducibility. Same trade this codebase already made when it replaced LLM
# query translation with the deterministic crop lexicon.
_DEFAULT_ROUTE: Route = "plant_info"


def classify(message: str, history: list[dict] | None = None) -> tuple[Route, str]:
    """Return (route, how) where how is 'rule' or 'default'.

    `history` is accepted but unused: Task 5 and the follow-up plans pass it, and
    taking it now means no signature change later.
    """
    ruled = classify_by_rules(message)
    if ruled is not None:
        return ruled, "rule"
    return _DEFAULT_ROUTE, "default"
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_router.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/router.py tests/test_router.py
git commit -m "Add the router entry point; no model fallback, by measurement"
```

---

### Task 5: Dispatch the route without changing behaviour

Every route still runs today's corpus path. The route is computed and carried on the result so it can be measured. This is the walking skeleton: it proves routing is wired in and harmless before any route changes what a user sees.

**Files:**
- Modify: `src/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `router.classify` (Task 4).
- Produces: `ChatResult.route: str` and `ChatResult.route_how: str`, both defaulting to `""`. `as_api()` is **not** changed, so the HTTP contract is untouched.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_engine.py`:

```python
def test_answer_records_the_route(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    r = engine.answer("Buğday ekmenin dekara maliyeti nedir?")
    assert r.route == "budget"
    assert r.route_how == "rule"


def test_route_is_not_exposed_over_the_api(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    r = engine.answer("Buğday ekmenin dekara maliyeti nedir?")
    assert set(r.as_api()) == {"answer", "recommended_products"}


def test_router_failure_does_not_break_answering(monkeypatch):
    from src import router
    monkeypatch.setattr(router, "classify",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    r = engine.answer("Herhangi bir soru")
    assert r.answer == "Kompost kullanabilirsiniz."
    assert r.route == ""
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -k route -v`
Expected: FAIL — `AttributeError: 'ChatResult' object has no attribute 'route'`

- [ ] **Step 3: Add the fields to `ChatResult`**

In `src/engine.py`, in the `ChatResult` dataclass, add two fields **after** the existing ones so positional construction elsewhere keeps working:

```python
    route: str = ""
    route_how: str = ""
```

Leave `as_api()` exactly as it is: the route is diagnostic, not part of the HTTP contract, and adding it would change a response shape that two clients already parse.

- [ ] **Step 4: Compute the route in `answer()`**

In `src/engine.py`, at the top of `answer()`, before `context = retrieve_context(...)`:

```python
    # Routing is diagnostic in this release: every route still runs the corpus
    # path below. Wiring it now, with behaviour unchanged, is what lets the 55
    # eval cases prove the router is harmless before any route diverges.
    try:
        from src import router
        route, route_how = router.classify(message, history)
    except Exception:  # noqa: BLE001 - routing must never break answering
        route, route_how = "", ""
```

and change the final `return` of `answer()` to carry them:

```python
    return ChatResult(answer=answer_text.strip(), recommended_products=products,
                      route=route, route_how=route_how)
```

- [ ] **Step 5: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -v`
Expected: all pass, including the pre-existing tests.

- [ ] **Step 6: Run the whole unit suite**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: all pass. No test may change verdict — this task is behaviour-neutral by construction.

- [ ] **Step 7: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Compute and record the route without changing answer behaviour"
```

---

### Task 6: Routing dimension in the eval harness

**Files:**
- Create: `evals/run_routing.py`
- Test: `tests/test_run_routing.py`

**Interfaces:**
- Consumes: `ROUTING_CASES` (Task 2), `router.classify` (Task 4).
- Produces: `score(cases) -> dict` with keys `total`, `correct`, `accuracy`, `by_how` (counts of `rule`/`model`/`default`), and `misses` (list of `(query, expected, actual)`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_routing.py`:

```python
"""The routing scorer must report both accuracy and how each decision was made -
the 30% model-layer gate is unmeasurable without the second number."""

from evals.run_routing import score


def test_score_counts_hits_and_how(monkeypatch):
    from evals import run_routing
    monkeypatch.setattr(run_routing, "classify",
                        lambda q, h=None: ("budget", "rule"))
    cases = [
        {"query": "a", "route": "budget"},
        {"query": "b", "route": "plant_info"},
    ]
    out = score(cases)
    assert out["total"] == 2
    assert out["correct"] == 1
    assert out["accuracy"] == 0.5
    assert out["by_how"]["rule"] == 2
    assert out["misses"] == [("b", "plant_info", "budget")]
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_run_routing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.run_routing'`

- [ ] **Step 3: Implement the scorer**

Create `evals/run_routing.py`:

```python
"""Score the frozen routing set.

    python -m evals.run_routing

Reports accuracy (spec gate: >= 90%) and how often the model layer was needed
(spec gate: <= 30%). The second number matters as much as the first: the hybrid
design's whole benefit is that most queries resolve for free, and an assumption
nobody measures is an assumption that quietly stops holding.
"""
from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from evals.routing_set import ROUTING_CASES  # noqa: E402
from src.router import classify  # noqa: E402


def score(cases: list[dict]) -> dict:
    correct = 0
    by_how: collections.Counter = collections.Counter()
    misses: list[tuple[str, str, str]] = []
    for c in cases:
        route, how = classify(c["query"])
        by_how[how] += 1
        if route == c["route"]:
            correct += 1
        else:
            misses.append((c["query"], c["route"], route))
    total = len(cases)
    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "by_how": dict(by_how),
        "misses": misses,
    }


def main() -> None:
    out = score(ROUTING_CASES)
    print(f"dogruluk : {out['correct']}/{out['total']} "
          f"({out['accuracy']:.0%})   kapi: >= 90%")
    model_n = out["by_how"].get("model", 0) + out["by_how"].get("default", 0)
    print(f"model katmani tetiklenme : {model_n}/{out['total']} "
          f"({model_n / max(1, out['total']):.0%})   kapi: <= 30%")
    print(f"karar dagilimi : {out['by_how']}")
    if out["misses"]:
        print("\nkacirilanlar:")
        for q, exp, got in out["misses"]:
            print(f"  beklenen={exp:<12} gelen={got:<12} {q}")
    ok = out["accuracy"] >= 0.90 and model_n / max(1, out["total"]) <= 0.30
    print("\nKAPILAR: " + ("GECTI" if ok else "GECMEDI"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_run_routing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/run_routing.py tests/test_run_routing.py
git commit -m "Score the frozen routing set against the spec's two gates"
```

---

### Task 7: Run the exit gates

Nothing is implemented here. This task exists because the spec's gates are only meaningful if someone actually runs them and writes down what came back.

**Files:**
- Create: `docs/superpowers/2026-08-10-routing-foundation-findings.md`

**Interfaces:**
- Consumes: everything above.
- Produces: a findings document; no code.

- [ ] **Step 1: Get the chat model onto the GPU and confirm generation speed**

The Faz 0 baseline was invalid: the model generated at 8.2 tok/s against a 120 s timeout, so 25 of 57 samples timed out and measured nothing. Restarting LM Studio did **not** fix it — measured again at 8.2 tok/s afterwards.

Diagnosis: this machine has an **AMD Radeon RX 9070 XT** and no NVIDIA GPU. LM Studio does not use an AMD card unless a suitable runtime is selected; with none, it falls back to CPU silently and only gets slow. 8 tok/s for a 12B model is CPU-inference speed, not spilled-VRAM speed.

Check both, in LM Studio:
1. **GPU Offload** layer slider on the model — at 0 everything runs on CPU.
2. **Runtime / Engine** — ROCm or Vulkan for AMD. "CPU llama.cpp" is the failure mode.

Verify with:

```bash
PYTHONIOENCODING=utf-8 python -c "
import time
from src import engine
c = engine._get_llm(); p = engine._chat_profile()
t0 = time.time()
r = c.chat.completions.create(model=p.model, max_tokens=400, temperature=0.4,
    messages=[{'role':'user','content':'Domateste azotun rolunu 150 kelimeyle anlat.'}])
el = time.time() - t0
print(f'{r.usage.completion_tokens/el:.1f} tok/s')
print('bos icerik!' if not (r.choices[0].message.content or '').strip() else 'icerik var')
"
```

Expected: comfortably above 40 tok/s, and non-empty content. Do not run the measurements below until both hold — every generation-dependent number in this task is meaningless on a CPU-bound model.

Note for the hosted migration: `max_tokens=2048` and `request_timeout=120` are calibrated for a fast local model. At 8 tok/s a full budget needs 251 s. Review the pair together when the chat provider changes.

- [ ] **Step 2: Run the unit suite**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: all pass.

- [ ] **Step 3: Run the routing gates**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_routing`
Expected: `KAPILAR: GECTI`. If accuracy is below 90%, fix the rules — **do not edit a frozen case to make it pass.** If a case turns out to be genuinely wrong, record why in the findings document.

- [ ] **Step 4: Run the regression shield**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --fast`
Expected: retrieval and context dimensions unchanged from the last recorded run.

Then the full run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval`
Expected: no case changes verdict. Spec §9 hard gate — any regression blocks the release.

- [ ] **Step 5: Re-run the product-gate probe on a healthy model**

Run: `PYTHONIOENCODING=utf-8 python -m evals.probe_product_gate --cases some --repeat 3 --tag "faz0-yeniden"`
Expected: `error` count zero. This closes the Faz 0 question the first run could not answer: whether the product gate is stable once generation is healthy.

- [ ] **Step 6: Write the findings**

Create `docs/superpowers/2026-08-10-routing-foundation-findings.md` recording: measured tok/s, routing accuracy, model-layer trigger rate, the eval verdict, the re-run probe gate distribution, and every routing miss with a one-line judgement of whether the rule or the expectation was wrong.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/2026-08-10-routing-foundation-findings.md
git commit -m "Record routing foundation gate results"
```

---

## What this plan deliberately does not do

No route changes what a user sees. That is the point: the router lands, is measured, and is proven harmless against the 55-case shield before any behaviour diverges.

Two follow-up plans complete the spec:

- **Plan 2 — context and fertilization planning:** `src/context/{season,location,weather}.py`, `src/fertplan.py`, and the `fert_plan` route consuming them. Carries the agronomic review gate from spec §5.5 and the code-appended framing sentence from §7.
- **Plan 3 — budget and crop choice:** `src/budget.py` and the `budget` / `crop_choice` routes. Asks for missing numbers, never invents them.
