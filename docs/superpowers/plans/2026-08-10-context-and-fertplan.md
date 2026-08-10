# Context and Fertilization Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fertilization-timing answer depend on where the user is, what month it is, and what the weather is about to do — and lay the mechanism for a reviewed fertilization calendar without shipping unreviewed agronomy.

**Architecture:** `stream_answer()` starts routing first, because it is the path both real clients use. Three small deterministic context modules (`season`, `location`, `weather`) are built and tested standalone. `fertplan.py` provides table lookup and plan assembly over a table that starts **empty**. The `fert_plan` route then enriches its answer with location, season and weather — always — and adds a calendar only for crops whose table rows have passed agronomic review.

**Tech Stack:** Python 3.14, pytest, `requests` (already a dependency), Open-Meteo (no key for non-commercial use), existing `evals/` harness.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-09-routing-and-context-design.md`. Plan 1: `docs/superpowers/plans/2026-08-10-routing-foundation.md`.
- **A route may dispatch different behaviour only when it has zero wrong entries in the frozen routing set.** `fert_plan` satisfies this today (8/8, zero). `budget` and `crop_choice` do NOT dispatch in this plan.
- The global routing gate stays at **0.90** and is still reported as FAILED. It was not relaxed.
- Zero regression in the 55 eval cases. The `[OFFSCOPE]`/`[NOPRODUCT]` markers, the product-suppression backstop, the empty-answer guard and stream-truncation recovery stay exactly as they are.
- **No crop ships in the fertilization table without agronomic review.** Neither the developer nor the plan's author is an agricultural engineer; correctness here cannot be established by testing. The table starts empty and rows are added only after review.
- **An empty table must never make the product worse.** With no reviewed rows, `fert_plan` still returns today's corpus answer plus context — it does not refuse.
- Plan and budget outputs carry a framing sentence stating assumptions and that the result is an estimate. **Appended by code, never requested in the prompt.**
- Turkish matching uses `engine._normalize_tr` and the existing left-boundary convention; stems short enough to collide are whole-word matched. Five collision rounds in Plan 1 established this is a property of the mechanism, not a bug — expect it.
- Run every Python command with `PYTHONIOENCODING=utf-8`.
- Never call a live weather API from a test. Stub it.

---

### Task 1: Route the streaming path

`stream_answer()` is the path both real clients use (`mobile-app/src/api.ts` and `web-widget/widget/agro-chat-widget.js` both send `stream: true`). It does not route, so the router currently runs on zero production traffic and the 55-case shield exercises a path users never hit. Everything later in this plan is worthless until this is closed.

Behaviour-neutral: the route is computed and made available to the function, and every route still runs today's path.

**Files:**
- Modify: `src/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `router.classify(message, history) -> (route, how)`.
- Produces: a local `route` / `route_how` inside `stream_answer()`, used by Task 7. The SSE wire format is **unchanged** — no new event, no new field.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
def test_stream_answer_computes_the_route(monkeypatch):
    seen = {}
    from src import router
    real = router.classify

    def spy(message, history=None):
        seen["route"] = real(message, history)
        return seen["route"]

    monkeypatch.setattr(router, "classify", spy)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    monkeypatch.setattr(engine, "_get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no stream")))
    list(engine.stream_answer("Domatese ne zaman gübre vermeliyim?"))
    assert seen["route"] == ("fert_plan", "rule")


def test_stream_answer_wire_format_has_no_route_field(monkeypatch):
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    monkeypatch.setattr(engine, "_get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no stream")))
    events = [json.loads(e[6:]) for e in engine.stream_answer("Merhaba") if e.startswith("data: ")]
    for e in events:
        assert "route" not in e, e
        assert e["type"] in ("token", "products", "done"), e


def test_stream_answer_survives_a_router_failure(monkeypatch):
    from src import router
    monkeypatch.setattr(router, "classify",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Kompost kullanabilirsiniz.")
    monkeypatch.setattr(engine, "_get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no stream")))
    # The router raises. What must hold is that streaming COMPLETES and closes
    # cleanly instead of propagating - what the reply says is the LLM path's
    # business, not the router's. (With _get_llm down, stream_answer takes its
    # own unavailable-message branch and never reaches _complete_text; asserting
    # on the mocked text here would test that branch, not the router.)
    events = [json.loads(e[6:]) for e in engine.stream_answer("Herhangi bir soru")
              if e.startswith("data: ")]
    assert events[-1]["type"] == "done"
    assert any(e["type"] == "token" for e in events)
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -k stream_answer_computes -v`
Expected: FAIL — `KeyError: 'route'`, because nothing calls `router.classify`.

- [ ] **Step 3: Compute the route in `stream_answer()`**

In `src/engine.py`, at the top of `stream_answer()`, before `context = retrieve_context(...)`:

```python
    # Same deferred import as answer(): src/router.py imports _normalize_tr from
    # THIS module at load time, so a top-level import here is a real cycle.
    # Behaviour-neutral in this task - Task 7 is what consumes the route.
    try:
        from src import router
        route, route_how = router.classify(message, history)
    except Exception:  # noqa: BLE001 - routing must never break answering
        route, route_how = "", ""
```

Leave every `yield` exactly as it is. The route reaches no client in this task.

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -v`
Expected: all pass.

- [ ] **Step 5: Run the whole suite**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: all pass, count up by 3. Behaviour-neutral by construction — no existing test may change verdict.

- [ ] **Step 6: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Route the streaming path so the router reaches production traffic"
```

---

### Task 2: Make the dispatch condition machine-checkable

The amended binding condition is "a route may dispatch only with zero wrong entries in the frozen set." Right now that is prose. A condition nobody measures is a condition nobody follows.

**Files:**
- Modify: `evals/run_routing.py`
- Test: `tests/test_run_routing.py`

**Interfaces:**
- Consumes: `score(cases)` (existing).
- Produces: `wrong_entries(cases) -> dict[str, int]` mapping each route to the number of cases from *other* routes that landed on it, and a `dispatch-safe` line in `main()`'s output.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_routing.py`:

```python
def test_wrong_entries_counts_only_incoming_errors(monkeypatch):
    from evals import run_routing
    # 'a' is right; 'b' expected plant_info but landed on budget.
    routed = {"a": "budget", "b": "budget"}
    monkeypatch.setattr(run_routing, "classify",
                        lambda q, h=None: (routed[q], "rule"))
    cases = [
        {"query": "a", "route": "budget"},
        {"query": "b", "route": "plant_info"},
    ]
    out = run_routing.wrong_entries(cases)
    assert out["budget"] == 1        # one case wrongly ENTERED budget
    assert out["plant_info"] == 0    # nothing wrongly entered plant_info
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_run_routing.py -k wrong_entries -v`
Expected: FAIL — `AttributeError: module 'evals.run_routing' has no attribute 'wrong_entries'`

- [ ] **Step 3: Implement it**

In `evals/run_routing.py`, add after `score()`:

```python
def wrong_entries(cases: list[dict]) -> dict[str, int]:
    """Per route: how many cases from OTHER routes landed on it.

    This is the risk the dispatch condition cares about. A route that only ever
    LOSES cases to the default is harmless to dispatch on; a route that gains
    cases it should not have starts handling real questions with the wrong
    machinery the moment its behaviour diverges.
    """
    out = {r: 0 for r in ROUTES}
    for c in cases:
        got, _ = classify(c["query"])
        if got != c["route"] and got in out:
            out[got] += 1
    return out
```

and import `ROUTES` alongside `ROUTING_CASES`:

```python
from evals.routing_set import ROUTES, ROUTING_CASES  # noqa: E402
```

Then, in `main()`, after the existing gate lines:

```python
    we = wrong_entries(ROUTING_CASES)
    safe = [r for r, n in we.items() if n == 0]
    unsafe = {r: n for r, n in we.items() if n}
    print(f"\nsevke uygun rotalar (sifir yanlis giris): {', '.join(sorted(safe))}")
    if unsafe:
        print(f"yanlis giris alan rotalar: {unsafe}   <- bunlar davranis ayristiramaz")
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_run_routing.py -v`
Expected: all pass.

- [ ] **Step 5: Run the scorer and record the real numbers**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_routing`
Expected: the accuracy gate still fails at 37/42, and `fert_plan` appears in the dispatch-safe list. Report the full output. Do not change anything to make a number look better.

- [ ] **Step 6: Commit**

```bash
git add evals/run_routing.py tests/test_run_routing.py
git commit -m "Report which routes are safe to dispatch on"
```

---

### Task 3: Season from the date

**Files:**
- Create: `src/context/__init__.py` (empty), `src/context/season.py`
- Test: `tests/test_context_season.py`

**Interfaces:**
- Produces: `season_of(d: date) -> str` returning one of `"kış"`, `"ilkbahar"`, `"yaz"`, `"sonbahar"`; `describe(d: date) -> str` returning a short Turkish phrase like `"Ağustos ayı, yaz"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_context_season.py`:

```python
"""Season derivation. Pure: no clock, no network - the date is always passed in."""

from datetime import date

import pytest

from src.context.season import describe, season_of


@pytest.mark.parametrize("d,expected", [
    (date(2026, 1, 15), "kış"),
    (date(2026, 3, 1), "ilkbahar"),
    (date(2026, 5, 31), "ilkbahar"),
    (date(2026, 6, 1), "yaz"),
    (date(2026, 8, 31), "yaz"),
    (date(2026, 9, 1), "sonbahar"),
    (date(2026, 11, 30), "sonbahar"),
    (date(2026, 12, 1), "kış"),
    (date(2026, 2, 28), "kış"),
])
def test_season_boundaries(d, expected):
    assert season_of(d) == expected


def test_describe_names_the_month_and_the_season():
    assert describe(date(2026, 8, 10)) == "Ağustos ayı, yaz"


def test_describe_uses_turkish_month_names():
    assert describe(date(2026, 1, 5)).startswith("Ocak")
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_context_season.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.context'`

- [ ] **Step 3: Implement**

Create `src/context/__init__.py` as an empty file.

Create `src/context/season.py`:

```python
"""Season from a date, northern hemisphere.

Meteorological seasons (three whole months each), not astronomical ones: the
consumer is agronomic advice, where "Haziran = yaz" is the useful statement and
a solstice date two weeks either way is not.

The date is always a parameter, never read from the clock here. That keeps the
module pure and its tests free of a frozen-time fixture.
"""
from __future__ import annotations

from datetime import date

_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
           "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def season_of(d: date) -> str:
    m = d.month
    if m in (12, 1, 2):
        return "kış"
    if m in (3, 4, 5):
        return "ilkbahar"
    if m in (6, 7, 8):
        return "yaz"
    return "sonbahar"


def describe(d: date) -> str:
    """A short Turkish phrase for the prompt: 'Ağustos ayı, yaz'."""
    return f"{_MONTHS[d.month - 1]} ayı, {season_of(d)}"
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_context_season.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/context/__init__.py src/context/season.py tests/test_context_season.py
git commit -m "Derive the season from the date"
```

---

### Task 4: Province from the conversation

**SPEC DEVIATION, recorded deliberately.** Spec §5.2 says this module carries a static table of the 81 provinces *and their coordinates*, so no geocoding call is needed. This plan keeps the province **names** and drops the coordinates: hand-writing 81 coordinate pairs invites silent errors, and a wrong coordinate produces confidently wrong weather with nothing to catch it. Coordinates are resolved in Task 5 by geocoding and cached. The names are the part that must be exact for matching, and they are.

**Files:**
- Create: `src/context/location.py`
- Test: `tests/test_context_location.py`

**Interfaces:**
- Produces: `PROVINCES: tuple[str, ...]` (81 names, title-case Turkish) and `extract_province(message: str, history: list[dict] | None = None) -> str | None`, returning the most recently mentioned province, current message first.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_context_location.py`:

```python
"""Province extraction. Pure: no network, no state - history is re-read per call."""

import pytest

from src.context.location import PROVINCES, extract_province


def test_all_81_provinces_present():
    assert len(PROVINCES) == 81
    assert len(set(PROVINCES)) == 81


@pytest.mark.parametrize("text,expected", [
    ("Manisa'dayım, domatese ne zaman gübre vermeliyim?", "Manisa"),
    ("manisada bağım var", "Manisa"),
    ("MANİSA", "Manisa"),
    ("Kahramanmaraş'ta zeytin yetiştiriyorum", "Kahramanmaraş"),
    ("Şanlıurfa'da buğday ektim", "Şanlıurfa"),
    ("Afyonkarahisar", "Afyonkarahisar"),
])
def test_extracts_inflected_and_folded_forms(text, expected):
    assert extract_province(text) == expected


@pytest.mark.parametrize("text", [
    "Domatese ne zaman gübre vermeliyim?",
    "Bafra'da fındık yetiştiriyorum",          # district, not a province
])
def test_returns_none_when_no_province(text):
    assert extract_province(text) is None


@pytest.mark.parametrize("text", [
    "Serada vantilatör kullanmalı mıyım?",     # 'Van' inside vantilatör
    "Karşı taraftaki tarlada ne var?",         # 'Kars' + folded ı inside karşı
    "Musluk suyuyla sulama yapılır mı?",       # 'Muş' inside musluk
    "Bu karar doğru mu?",                      # 'Kars' must not reach here either
])
def test_short_province_names_do_not_leak(text):
    # Four-letter provinces (Van, Kars, Muş, Rize, Bolu, Ordu, Uşak, Siirt) are
    # the same short-stem trap the router hit five times. These are the spec:
    # tighten the matcher until they pass, never delete the case.
    assert extract_province(text) is None


def test_history_is_used_when_the_message_has_none():
    history = [{"role": "user", "content": "Manisa'dayım"},
               {"role": "assistant", "content": "Anladım."}]
    assert extract_province("Peki ne zaman gübre vereyim?", history) == "Manisa"


def test_current_message_wins_over_history():
    history = [{"role": "user", "content": "Manisa'dayım"}]
    assert extract_province("Aslında Aydın'dayım", history) == "Aydın"


def test_most_recent_history_mention_wins():
    history = [{"role": "user", "content": "Manisa'dayım"},
               {"role": "user", "content": "Aydın'a taşındım"}]
    assert extract_province("Ne zaman gübre vereyim?", history) == "Aydın"


def test_does_not_match_inside_a_longer_word():
    # 'Van' must not fire inside 'vantilatör'.
    assert extract_province("Serada vantilatör kullanmalı mıyım?") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_context_location.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.context.location'`

- [ ] **Step 3: Implement**

Create `src/context/location.py`:

```python
"""Which province the user is in, re-derived from the conversation every call.

Nothing is stored server-side: no session, no database, no user record. That is
what lets context work land before membership does. When membership arrives, a
profile value becomes the default and this function stays exactly as it is.

Districts are out of scope. The table holds the 81 provinces; a user who writes
"Bafra" is not matched and the assistant asks for the province. Province
granularity is enough for both weather and fertilization timing, and a district
table can be added later without changing this interface.
"""
from __future__ import annotations

import re

from src.engine import _normalize_tr

PROVINCES: tuple[str, ...] = (
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya",
    "Ankara", "Antalya", "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın",
    "Batman", "Bayburt", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur",
    "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Düzce",
    "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep",
    "Giresun", "Gümüşhane", "Hakkâri", "Hatay", "Iğdır", "Isparta", "İstanbul",
    "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu",
    "Kayseri", "Kırıkkale", "Kırklareli", "Kırşehir", "Kilis", "Kocaeli",
    "Konya", "Kütahya", "Malatya", "Manisa", "Mardin", "Mersin", "Muğla",
    "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya",
    "Samsun", "Siirt", "Sinop", "Sivas", "Şanlıurfa", "Şırnak", "Tekirdağ",
    "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat",
    "Zonguldak",
)

# Folded name -> canonical name. Built once; the fold is the same one the crop
# lexicon and the router use, so "manisada", "Manisa'dayım" and "MANİSA" all
# reduce to the same key.
_FOLDED = {_normalize_tr(p): p for p in PROVINCES}

# Longest first, so "Kahramanmaraş" is tried before "Maraş"-like substrings and
# multi-word names are not shadowed by a shorter sibling.
_ORDERED = sorted(_FOLDED, key=len, reverse=True)


def _find(text: str) -> str | None:
    """Left-boundary match, so a province may carry Turkish case suffixes
    ("Manisa'dayım", "manisada") but never fires inside a longer word
    ("Van" must not match "vantilatör")."""
    folded = _normalize_tr(text)
    for key in _ORDERED:
        if re.search(rf"(?<!\w){re.escape(key)}(?!\w|')", folded):
            return _FOLDED[key]
        if re.search(rf"(?<!\w){re.escape(key)}(?=[a-z']*\b)", folded):
            return _FOLDED[key]
    return None


def extract_province(message: str, history: list[dict] | None = None) -> str | None:
    """Most recent province mentioned: the current message wins, then history
    read backwards. Returns None when nobody has said where they are."""
    found = _find(message)
    if found:
        return found
    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        found = _find(turn.get("content", ""))
        if found:
            return found
    return None
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_context_location.py -v`
Expected: all pass. If any `_do_not_leak` or `longer_word` case fails, the matcher is too permissive — **tighten it, never delete or weaken the case.** Those tests encode the same short-stem trap that cost Plan 1 five rounds, and a bare four-letter province name folded into ordinary Turkish is exactly where it recurs. If you find a collision the tests do not cover, add it.

- [ ] **Step 5: Commit**

```bash
git add src/context/location.py tests/test_context_location.py
git commit -m "Extract the user's province from the conversation"
```

---

### Task 5: Weather for a province

**Files:**
- Create: `src/context/weather.py`
- Test: `tests/test_context_weather.py`

**Interfaces:**
- Produces: `forecast(province: str) -> str | None` — a short Turkish phrase for the prompt, or `None` when unavailable. Never raises.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_context_weather.py`:

```python
"""Weather lookup. The network is ALWAYS stubbed - a test that reaches Open-Meteo
would be slow, flaky, and would fail in CI."""

import src.context.weather as weather


def _stub(monkeypatch, geo=None, fc=None, boom=None):
    def fake_get(url, params=None, timeout=None):
        if boom:
            raise boom
        class R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self_inner): return geo if "geocoding" in url else fc
        return R()
    monkeypatch.setattr(weather.requests, "get", fake_get)
    weather.forecast.cache_clear()
    weather._geocode.cache_clear()


GEO = {"results": [{"latitude": 38.6, "longitude": 27.4}]}
FC = {"daily": {"precipitation_sum": [0.0, 12.4, 0.0],
                "temperature_2m_min": [11.0, 10.2, 9.4],
                "temperature_2m_max": [30.1, 24.0, 26.5]}}


def test_returns_a_phrase_naming_rain_and_temperature(monkeypatch):
    _stub(monkeypatch, geo=GEO, fc=FC)
    out = weather.forecast("Manisa")
    assert out is not None
    assert "12" in out          # the rain figure reaches the phrase
    assert "30" in out or "9" in out


def test_network_failure_returns_none_and_does_not_raise(monkeypatch):
    _stub(monkeypatch, boom=TimeoutError("timed out"))
    assert weather.forecast("Manisa") is None


def test_unknown_province_returns_none(monkeypatch):
    _stub(monkeypatch, geo={"results": []}, fc=FC)
    assert weather.forecast("Atlantis") is None


def test_second_call_for_the_same_province_does_not_hit_the_network(monkeypatch):
    calls = {"n": 0}
    def counting_get(url, params=None, timeout=None):
        calls["n"] += 1
        class R:
            def raise_for_status(self): pass
            def json(self_inner): return GEO if "geocoding" in url else FC
        return R()
    monkeypatch.setattr(weather.requests, "get", counting_get)
    weather.forecast.cache_clear()
    weather._geocode.cache_clear()
    weather.forecast("Manisa")
    first = calls["n"]
    weather.forecast("Manisa")
    assert calls["n"] == first
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_context_weather.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.context.weather'`

- [ ] **Step 3: Implement**

Create `src/context/weather.py`:

```python
"""Coming-week weather for a province, as a short phrase for the prompt.

Three figures are agronomically useful and the rest is noise: rain in the next
few days (fertiliser applied before heavy rain washes off), the low (frost), and
the high.

Open-Meteo needs no key for non-commercial use. IT DOES REQUIRE ONE FOR
COMMERCIAL USE, and this is a commercial product - budget a key before go-live.

Never raises. A weather lookup that can break an answer is worse than no weather.
"""
from __future__ import annotations

from functools import lru_cache

import requests

_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FC_URL = "https://api.open-meteo.com/v1/forecast"

# Short: this sits in the request path. Exceeding it costs the weather sentence,
# not the answer.
_TIMEOUT = 2.0


@lru_cache(maxsize=128)
def _geocode(province: str) -> tuple[float, float] | None:
    """Province name -> coordinates. Cached for the process lifetime; the 81
    provinces do not move, so one lookup each is the whole cost."""
    try:
        r = requests.get(_GEO_URL, timeout=_TIMEOUT, params={
            "name": province, "count": 1, "language": "tr", "country": "TR",
        })
        r.raise_for_status()
        results = (r.json() or {}).get("results") or []
        if not results:
            return None
        return float(results[0]["latitude"]), float(results[0]["longitude"])
    except Exception:  # noqa: BLE001 - see module docstring
        return None


@lru_cache(maxsize=128)
def forecast(province: str) -> str | None:
    """A Turkish phrase, or None when unavailable for any reason.

    Cached per province. The cache is deliberately NOT keyed by date: it lives
    only as long as the process, and a forecast that is a few hours stale changes
    no fertilisation advice.
    """
    coords = _geocode(province)
    if coords is None:
        return None
    lat, lon = coords
    try:
        r = requests.get(_FC_URL, timeout=_TIMEOUT, params={
            "latitude": lat, "longitude": lon, "timezone": "Europe/Istanbul",
            "forecast_days": 7,
            "daily": "precipitation_sum,temperature_2m_min,temperature_2m_max",
        })
        r.raise_for_status()
        daily = (r.json() or {}).get("daily") or {}
        rain = [x for x in (daily.get("precipitation_sum") or []) if x is not None]
        tmin = [x for x in (daily.get("temperature_2m_min") or []) if x is not None]
        tmax = [x for x in (daily.get("temperature_2m_max") or []) if x is not None]
        if not (rain and tmin and tmax):
            return None
    except Exception:  # noqa: BLE001
        return None

    total_rain = round(sum(rain), 1)
    return (f"önümüzdeki hafta toplam {total_rain} mm yağış bekleniyor, "
            f"sıcaklık {round(min(tmin))}-{round(max(tmax))} °C aralığında")
```

- [ ] **Step 4: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_context_weather.py -v`
Expected: all pass.

- [ ] **Step 5: One live smoke check, by hand**

Run: `PYTHONIOENCODING=utf-8 python -c "from src.context.weather import forecast; print(forecast('Manisa'))"`
Expected: a Turkish phrase with plausible numbers for the season. This is the only place a live call is allowed — record the output in your report. If it returns `None`, report that rather than working around it.

- [ ] **Step 6: Commit**

```bash
git add src/context/weather.py tests/test_context_weather.py
git commit -m "Add a coming-week weather phrase per province"
```

---

### Task 6: Fertilization table and lookup, with an empty table

The mechanism ships now; the agronomy does not. The table starts **empty** and stays empty until a qualified reviewer approves rows.

**Files:**
- Create: `src/fertplan.py`, `data/fertplan_table.json`
- Test: `tests/test_fertplan.py`

**Interfaces:**
- Produces: `lookup(crop: str, stage: str | None) -> list[dict]` returning reviewed rows for a crop (empty list when none), `available_crops() -> tuple[str, ...]`, `detect_crop(message: str) -> str | None`, and `FRAMING` — the fixed sentence Task 7 appends.

**`detect_crop` matches against the table's OWN keys**, not a separate crop list. Two consequences worth having: with an empty table it always returns `None`, so nothing downstream can produce a plan; and when a reviewed crop is added, detection starts working with no code change. There is no second list to keep in sync.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fertplan.py`:

```python
"""Fertilization table lookup. The TABLE'S CONTENT is not tested here - correctness
of agronomy cannot be established by unit test, only by review. What is tested is
that the mechanism handles an empty table, an unknown crop, and a reviewed row."""

import json

import pytest

from src import fertplan


def test_table_ships_empty_until_reviewed():
    # Guards the constraint directly: no unreviewed agronomy reaches a user.
    assert fertplan.available_crops() == ()


def test_unknown_crop_returns_no_rows():
    assert fertplan.lookup("domates", None) == []


def test_lookup_reads_reviewed_rows(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "Fide döneminde ..."},
        {"stage": "çiçeklenme", "reviewed_by": "Z. Müh.", "note": "Çiçeklenmede ..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    fertplan._load.cache_clear()
    rows = fertplan.lookup("domates", None)
    assert len(rows) == 2
    assert fertplan.lookup("domates", "fide")[0]["stage"] == "fide"


def test_rows_without_a_reviewer_are_dropped(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "note": "onaysız"},
        {"stage": "çiçeklenme", "reviewed_by": "Z. Müh.", "note": "onaylı"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    fertplan._load.cache_clear()
    rows = fertplan.lookup("domates", None)
    assert [r["stage"] for r in rows] == ["çiçeklenme"]


def test_a_missing_table_file_is_not_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(fertplan, "_TABLE_PATH", tmp_path / "nope.json")
    fertplan._load.cache_clear()
    assert fertplan.lookup("domates", None) == []


def test_framing_sentence_exists_and_says_it_is_an_estimate():
    assert "tahmin" in fertplan.FRAMING.lower()


def test_detect_crop_finds_nothing_while_the_table_is_empty():
    assert fertplan.detect_crop("Domatese ne zaman gübre vermeliyim?") is None


def test_detect_crop_matches_a_reviewed_crop_with_turkish_suffixes(monkeypatch, tmp_path):
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    fertplan._load.cache_clear()
    assert fertplan.detect_crop("Domatese ne zaman gübre vermeliyim?") == "domates"
    assert fertplan.detect_crop("domatesin gübrelemesi") == "domates"
    assert fertplan.detect_crop("Buğdaya ne zaman gübre vereyim?") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fertplan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.fertplan'`

- [ ] **Step 3: Create the empty table**

Create `data/fertplan_table.json` containing exactly:

```json
{}
```

- [ ] **Step 4: Implement**

Create `src/fertplan.py`:

```python
"""Fertilization plan rows, and the framing that keeps a plan advice.

THE TABLE IS DATA, NOT CODE, and it ships EMPTY. Its correctness cannot be
established by testing - only by review - and neither the author of this module
nor the developer is an agricultural engineer. A row without a `reviewed_by` is
dropped at load time, so an unreviewed line cannot reach a user even if someone
adds one to the file.

Adding a crop is therefore a review task, not a programming task: append rows
with `reviewed_by` filled in by the person who checked them. No code changes.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from src.config import DATA_DIR
from src.engine import _normalize_tr

_TABLE_PATH = DATA_DIR / "fertplan_table.json"

# Appended BY CODE, never asked of the model, so no model can omit it. This
# sentence is the line between advice and prescription.
FRAMING = (
    "Bu program bir tahmindir ve yukarıda belirtilen bilgilere dayanmaktadır; "
    "kesin doz için toprak analizi yaptırmanız ve bir ziraat mühendisine "
    "danışmanız önerilir."
)


@lru_cache(maxsize=1)
def _load() -> dict[str, list[dict]]:
    """Reviewed rows only. A missing or malformed file yields an empty table -
    never an exception, because a broken table must not break answering."""
    try:
        raw = json.loads(Path(_TABLE_PATH).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, list[dict]] = {}
    for crop, rows in (raw or {}).items():
        kept = [r for r in rows if r.get("reviewed_by")]
        if kept:
            out[crop.lower()] = kept
    return out


def available_crops() -> tuple[str, ...]:
    """Crops with at least one reviewed row."""
    return tuple(sorted(_load()))


def detect_crop(message: str) -> str | None:
    """Which reviewed crop the message is about, or None.

    Matched against the TABLE'S OWN KEYS so there is no second list to drift.
    While the table is empty this can only return None, which is exactly the
    behaviour we want before review has happened.

    Left-boundary match, so a crop may carry Turkish suffixes ("domatese",
    "domatesin") - the same convention the crop lexicon and the router use.
    """
    folded = _normalize_tr(message)
    for crop in sorted(_load(), key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(_normalize_tr(crop))}", folded):
            return crop
    return None


def lookup(crop: str, stage: str | None) -> list[dict]:
    """Reviewed rows for a crop, optionally narrowed to one phenological stage.
    Empty list when the crop has no reviewed rows - the caller must then say so
    plainly rather than inventing a plan."""
    rows = _load().get((crop or "").lower(), [])
    if stage:
        rows = [r for r in rows if r.get("stage") == stage]
    return list(rows)
```

- [ ] **Step 5: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fertplan.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/fertplan.py data/fertplan_table.json tests/test_fertplan.py
git commit -m "Add fertilization table lookup; table ships empty pending review"
```

---

### Task 7: The `fert_plan` route enriches its answer

The first task in this project where a route changes what a user receives. Permitted because `fert_plan` has zero wrong entries in the frozen set (Task 2 reports it).

**What diverges:** on `fert_plan`, the prompt gains a context block naming the province, the season and the coming week's weather, and the model is told to use them. If the crop has reviewed table rows, they are supplied too and the framing sentence is appended by code.

**What does not:** with an empty table this route still produces today's corpus answer, now aware of where and when. **It must never refuse for lack of a table row** — that would make the product worse than before this plan.

**Files:**
- Modify: `src/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: `season.describe`, `location.extract_province`, `weather.forecast`, `fertplan.lookup`, `fertplan.FRAMING`.
- Produces: `_context_block(route, message, history, today) -> str` in `src/engine.py`, returning "" for every route except `fert_plan`.

**The route is passed in, not recomputed.** `answer()` and `stream_answer()` already hold it. Classifying a second time inside this function would duplicate work and, worse, create two places that could disagree about which route a message is on.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine.py`:

```python
from datetime import date


def test_context_block_is_empty_off_the_fert_plan_route():
    assert engine._context_block("plant_info", "Asmada budama ne zaman yapılır?", None, date(2026, 8, 10)) == ""


def test_context_block_names_season_and_province(monkeypatch):
    monkeypatch.setattr("src.context.weather.forecast", lambda p: "yağış yok")
    out = engine._context_block("fert_plan", "Manisa'dayım, domatese ne zaman gübre vermeliyim?",
                                None, date(2026, 8, 10))
    assert "Manisa" in out
    assert "Ağustos" in out
    assert "yağış yok" in out


def test_context_block_asks_for_the_province_when_missing(monkeypatch):
    monkeypatch.setattr("src.context.weather.forecast", lambda p: "yağış yok")
    out = engine._context_block("fert_plan", "Domatese ne zaman gübre vermeliyim?",
                                None, date(2026, 8, 10))
    assert "Ağustos" in out          # season still known
    assert "il" in out.lower()       # and it says to ask which province


def test_context_block_survives_a_weather_outage(monkeypatch):
    monkeypatch.setattr("src.context.weather.forecast", lambda p: None)
    out = engine._context_block("fert_plan", "Manisa'dayım, domatese ne zaman gübre vermeliyim?",
                                None, date(2026, 8, 10))
    assert "Manisa" in out
    assert out != ""


def test_empty_table_does_not_refuse(monkeypatch):
    from src import fertplan
    monkeypatch.setattr("src.context.weather.forecast", lambda p: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Domatese azot verebilirsiniz.")
    r = engine.answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
    assert r.route == "fert_plan"
    assert "Domatese azot verebilirsiniz." in r.answer
    assert fertplan.FRAMING not in r.answer   # no reviewed rows, so no framing


def test_reviewed_rows_add_the_framing_sentence(monkeypatch, tmp_path):
    import json as _json
    from src import fertplan
    table = tmp_path / "t.json"
    table.write_text(_json.dumps({"domates": [
        {"stage": "fide", "reviewed_by": "Z. Müh.", "note": "Fide döneminde ..."},
    ]}), encoding="utf-8")
    monkeypatch.setattr(fertplan, "_TABLE_PATH", table)
    fertplan._load.cache_clear()
    monkeypatch.setattr("src.context.weather.forecast", lambda p: None)
    monkeypatch.setattr(engine, "retrieve_context", lambda *a, **k: "ctx")
    monkeypatch.setattr(engine, "match_products", lambda *a, **k: [])
    monkeypatch.setattr(engine, "_complete_text", lambda m: "Program: ...")
    r = engine.answer("Manisa'dayım, domatese ne zaman gübre vermeliyim?")
    assert fertplan.FRAMING in r.answer
    fertplan._load.cache_clear()
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -k context_block -v`
Expected: FAIL — `AttributeError: module 'src.engine' has no attribute '_context_block'`

- [ ] **Step 3: Implement the context block**

In `src/engine.py`, add near `_build_messages`:

```python
def _context_block(route: str, message: str, history: list[dict] | None, today) -> str:
    """Situation lines for the fert_plan route: where, when, and what the weather
    is about to do. Empty string for every other route, so nothing else pays for
    it and nothing else changes.

    Weather is best-effort by design (see src/context/weather.py) - its absence
    removes one line and never blocks the answer.
    """
    if route != "fert_plan":
        return ""

    from src.context import location, season, weather

    lines = [f"Tarih: {season.describe(today)}."]
    province = location.extract_province(message, history)
    if province:
        lines.append(f"Kullanicinin ili: {province}.")
        fc = weather.forecast(province)
        if fc:
            lines.append(f"Hava durumu: {fc}.")
    else:
        lines.append("Kullanicinin ili BILINMIYOR - cevabinda hangi ilde "
                     "oldugunu sor, tavsiyeni genel tut.")
    lines.append("Bitkinin fenolojik donemi bilinmiyorsa cevabinda sor "
                 "(fide, cicek, meyve tutumu gibi).")
    return "\n".join(lines)
```

Wire it into `_build_messages` so the block is prepended to the system message when non-empty. Do not change the message list's shape.

- [ ] **Step 4: Append the framing sentence in `answer()`**

In `src/engine.py`, in `answer()`, after the marker stripping and before the return:

```python
    # Framing is appended by CODE, never asked of the model, so no model can drop
    # it. Gated on rows ACTUALLY FOUND for this question, not on the table being
    # non-empty: a general answer is advice already and needs no disclaimer.
    if route == "fert_plan":
        # Deferred import, same reason as router: fertplan reads _normalize_tr
        # from this module, so a top-level import here is a real cycle.
        from src import fertplan
        crop = fertplan.detect_crop(message)
        if crop and fertplan.lookup(crop, None):
            answer_text = f"{answer_text.rstrip()}\n\n{fertplan.FRAMING}"
```

- [ ] **Step 5: Run the tests**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_engine.py -v`
Expected: all pass.

- [ ] **Step 6: Run the whole suite**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: all pass. This task DOES change behaviour on one route — if an existing test changes verdict, stop and report which, rather than adjusting the test.

- [ ] **Step 7: Commit**

```bash
git add src/engine.py tests/test_engine.py
git commit -m "Enrich fert_plan answers with province, season and weather"
```

---

### Task 8: Run the gates and record what came back

**Files:**
- Create: `docs/superpowers/2026-08-10-context-and-fertplan-findings.md`

- [ ] **Step 1: Confirm generation speed before measuring**

If throughput is ~8 tok/s the model has spilled out of VRAM; eject and reload it in LM Studio (this does not self-correct). Verify above 40 tok/s:

```bash
PYTHONIOENCODING=utf-8 python -c "
import time
from src import engine
c = engine._get_llm(); p = engine._chat_profile()
t0 = time.time()
r = c.chat.completions.create(model=p.model, max_tokens=400, temperature=0.4,
    messages=[{'role':'user','content':'Domateste azotun rolunu 150 kelimeyle anlat.'}])
print(f'{r.usage.completion_tokens/(time.time()-t0):.1f} tok/s')
"
```

- [ ] **Step 2: Unit suite**

Run: `PYTHONIOENCODING=utf-8 python -m pytest -q`
Expected: all pass.

- [ ] **Step 3: Routing gates**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_routing`
Expected: accuracy still 37/42 (this plan does not touch the rules), and `fert_plan` still listed dispatch-safe. **If `fert_plan` has gained a wrong entry, stop — Task 7 must not ship.**

- [ ] **Step 4: Regression shield**

Run: `PYTHONIOENCODING=utf-8 python -m evals.run_eval --fast` — expected 55/55.
Then: `PYTHONIOENCODING=utf-8 python -m evals.run_eval` — expected 55/55.

One route now diverges, so a red here is not automatically a flake. For any red: read the logged answer in `evals/runs/*.jsonl` before concluding anything, then escalate with `--repeat 8`. Grounding reds have twice turned out to be anchor narrowness rather than defects.

- [ ] **Step 5: Look at a real answer**

Ask the running system a fert_plan question with a province and read the reply:

```bash
PYTHONIOENCODING=utf-8 python -c "
from src import engine
r = engine.answer(\"Manisa'dayim, domatese ne zaman gubre vermeliyim?\")
print('ROUTE:', r.route, r.route_how); print(); print(r.answer)
"
```

Expected: an answer that names Manisa and the season, asks for the phenological stage, and does **not** claim a fertilization programme. Paste it into the findings. A green test suite is not evidence that the output reads well.

- [ ] **Step 6: Write the findings**

Create `docs/superpowers/2026-08-10-context-and-fertplan-findings.md` recording: measured tok/s, unit count, routing gates and the dispatch-safe list, the eval result with any red analysed, the live weather smoke output, the real answer from Step 5, and what is still blocked on agronomic review.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/2026-08-10-context-and-fertplan-findings.md
git commit -m "Record context and fertplan gate results"
```

---

## What this plan deliberately leaves undone

- **The fertilization table is empty.** Rows require a qualified reviewer. The mechanism, the review gate, and the framing sentence all ship; the agronomy waits. Adding a crop is a review task, not a code change.
- **`budget` and `crop_choice` do not dispatch.** They stay on the corpus path. Plan 3 covers them, and the numeric data layer (FAOSTAT country-level, Tarım Bakanlığı district-level) is a separate spec that feeds them.
- **The global routing gate is still red at 88%.** Unchanged and still reported. The `nutrition` → `plant_info` confusion behind it changes nothing while both run the corpus path.
