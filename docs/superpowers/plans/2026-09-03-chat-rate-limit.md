# Chat Rate Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a ceiling on how often `/api/chat` can be called, so a publicly reachable endpoint with no auth cannot run up an unbounded bill.

**Architecture:** A new module `src/rate_limit.py` holds one class — a sliding window over request timestamps, taking its clock as a parameter so tests move time instead of sleeping, and holding a `threading.Lock` because FastAPI runs the synchronous `chat()` handler in a threadpool. `src/main.py` gains a config field, one module-level instance, a FastAPI dependency on the chat route only, and a startup line beside the existing CORS warning. The limit is GLOBAL, not per client, because the service sits behind a TLS-terminating proxy and cannot identify callers.

**Tech Stack:** Python 3.14, FastAPI, pytest. No new dependencies — `collections.deque` and `threading` are standard library.

**Spec:** `docs/superpowers/specs/2026-09-03-chat-rate-limit-design.md`

## Global Constraints

- The limit is **global**, never per-IP. Do not read `request.client.host` and do not read `X-Forwarded-For`. The spec explains why both are worse than useless here; a comment or name suggesting per-client behaviour is a defect, not a simplification.
- Default **60 requests per minute**, and `RATE_LIMIT_PER_MINUTE=0` disables the limit entirely. A running deployment that sets nothing must keep working.
- Only `/api/chat` is limited. `/api/products` and `/api/articles` are not.
- Refusal is HTTP **429** with a Turkish `detail`, consistent with the rest of the service's user-visible text.
- The window is a **trailing 60 seconds**, not a fixed bucket that resets on the minute.
- A **refused** call is not recorded in the window. Recording refusals would let a sustained flood push recovery out forever.
- The clock is `time.monotonic`, not `time.time` — a wall-clock adjustment must not open or extend the window.
- No new third-party dependency.
- Comments and docstrings in English, matching the surrounding style: they state the ARGUMENT, not the mechanics. **This project treats a comment that describes something the code does not do as a defect in its own right** — seven were found and fixed across the two previous rounds, so hold anything you write to that standard and measure any number before writing it.
- Commit messages: short, natural, English, no body, **no `Co-Authored-By` trailer**.
- Do not touch `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.github/workflows/`, `mobile-app/eas.json`, `mobile-app/app.json`. Deployment belongs to someone else; this change is application code only.
- Run pytest as `python -m pytest ...` from the repo root.

## Files

- Create: `src/rate_limit.py` — the counter. One class, no framework imports.
- Create: `tests/test_rate_limit.py` — its unit tests, with an injected clock.
- Modify: `src/config.py` — one field in the API/CORS section.
- Modify: `src/main.py` — the instance, the dependency, the route wiring, the startup line.
- Modify: `tests/test_main.py` — endpoint-level tests.
- Modify: `tests/conftest.py` — an autouse fixture so the suite cannot trip the live limiter.

## Orientation for every implementer

`src/main.py` is the FastAPI app. `/api/chat` is the expensive route: it calls a language model, which may be a paid hosted provider depending on an environment variable this repository does not control. The endpoint is deployed publicly with no authentication.

Two facts shape everything here:

1. **The service cannot tell its callers apart.** `docker-entrypoint.sh` runs uvicorn without `--proxy-headers`, and the app speaks plain HTTP behind an HTTPS host, so `request.client.host` is the proxy's address for every request. Keying a limit on it would throttle all users together while reading as if it isolated them; keying on `X-Forwarded-For` would let an attacker bypass the limit by setting a header. The limit is therefore global and says so.
2. **`chat()` is a synchronous `def`.** FastAPI runs synchronous handlers in a threadpool, so concurrent requests genuinely interleave and the counter needs a lock.

---

### Task 1: The counter

**Files:**
- Create: `src/rate_limit.py`
- Create: `tests/test_rate_limit.py`

**Interfaces:**
- Consumes: nothing.
- Produces, and Task 2 depends on all three:
  - `SlidingWindowLimit(per_minute: int, clock: Callable[[], float] = time.monotonic)`
  - `.allow() -> bool` — records the call and says whether it was within the ceiling
  - `.per_minute -> int` (read-only property) and `.reset() -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rate_limit.py`:

```python
"""Unit tests for the chat rate limit (no app, no network, no sleeping)."""

import threading

from src import rate_limit


class _Clock:
    """A clock the test moves by hand. Real sleeping would make these tests
    slow and flaky for no gain - the counter only ever asks what time it is."""

    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_a_call_under_the_ceiling_is_allowed():
    assert rate_limit.SlidingWindowLimit(2, _Clock()).allow() is True


def test_the_ceiling_is_exact_at_its_own_edge():
    """The Nth call passes and the N+1th does not, inside one window. An
    off-by-one here is invisible in production and obvious to a script."""
    limit = rate_limit.SlidingWindowLimit(3, _Clock())
    assert [limit.allow() for _ in range(3)] == [True, True, True]
    assert limit.allow() is False


def test_the_window_admits_again_once_the_oldest_call_falls_out():
    clock = _Clock()
    limit = rate_limit.SlidingWindowLimit(2, clock)
    assert limit.allow() is True          # t=0
    clock.now = 10.0
    assert limit.allow() is True          # t=10
    assert limit.allow() is False         # both still inside the window
    clock.now = 60.5                      # t=0 has left it, t=10 has not
    assert limit.allow() is True
    assert limit.allow() is False


def test_a_refused_call_does_not_extend_the_block():
    """THE FLOOD CASE. If a refusal were recorded, every rejected request would
    push recovery further out and a sustained flood would lock the endpoint
    shut forever - turning a ceiling into a permanent outage."""
    clock = _Clock()
    limit = rate_limit.SlidingWindowLimit(1, clock)
    assert limit.allow() is True          # t=0, the only recorded call
    for moment in (10.0, 20.0, 30.0, 40.0, 50.0):
        clock.now = moment
        assert limit.allow() is False
    clock.now = 60.5
    assert limit.allow() is True


def test_a_fixed_bucket_would_let_twice_the_ceiling_through():
    """WHY THE WINDOW TRAILS rather than resetting on the minute. A per-minute
    bucket admits the ceiling at 0:59 and the ceiling again at 1:01 - twice the
    limit in two seconds, which is exactly the burst the ceiling exists to
    stop."""
    clock = _Clock()
    limit = rate_limit.SlidingWindowLimit(2, clock)
    clock.now = 59.0
    assert limit.allow() is True
    assert limit.allow() is True
    clock.now = 61.0
    assert limit.allow() is False


def test_a_limit_of_zero_never_refuses():
    """The documented way to switch the ceiling off, so a deployment that wants
    no limit does not have to remove the dependency."""
    clock = _Clock()
    limit = rate_limit.SlidingWindowLimit(0, clock)
    assert all(limit.allow() for _ in range(500)) is True


def test_reset_empties_the_window():
    """Used by the test suite's own fixture: without it every test in the
    process would share one ceiling."""
    limit = rate_limit.SlidingWindowLimit(1, _Clock())
    assert limit.allow() is True
    assert limit.allow() is False
    limit.reset()
    assert limit.allow() is True


def test_the_ceiling_holds_when_threads_race():
    """`chat()` is a synchronous def, so FastAPI runs it in a threadpool and
    concurrent calls genuinely interleave between reading the window's length
    and appending to it. Uses the real clock: 200 calls finish far inside one
    60-second window."""
    limit = rate_limit.SlidingWindowLimit(50)
    admitted = []
    guard = threading.Lock()

    def worker():
        for _ in range(20):
            if limit.allow():
                with guard:
                    admitted.append(1)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(admitted) == 50
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_rate_limit.py -q`

Expected: a collection error — `ModuleNotFoundError: No module named 'src.rate_limit'`. Every test in the file fails for that one reason; that is the correct RED for a module that does not exist yet.

- [ ] **Step 3: Write the counter**

Create `src/rate_limit.py`:

```python
"""A ceiling on how often the expensive endpoint may be called.

THE CEILING IS GLOBAL, NOT PER CALLER, and that is a finding rather than a
simplification. This service runs behind a TLS-terminating proxy with uvicorn
started without `--proxy-headers`, so `request.client.host` is the proxy's
address on every request: a per-IP limit keyed on it would throttle all users
together while reading as though it isolated them. The other candidate key,
`X-Forwarded-For`, is set by the client, so an attacker rotates it and the
limit never fires. Counting everything is the only thing here that is true, and
it bounds the bill, which is what is at risk.

WHAT THIS BUYS AND WHAT IT COSTS. It converts an unbounded bill into a denial
of service an attacker can hold open. That is accepted deliberately: the
alternative on offer is the unbounded bill. The real fix is authentication,
which needs a client change and a redeploy this module exists to work around.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable


class SlidingWindowLimit:
    """At most `per_minute` calls in any trailing 60 seconds.

    THE WINDOW TRAILS rather than resetting on the minute: a fixed bucket
    admits the ceiling just before the boundary and the ceiling again just
    after, which is twice the limit in the span the limit exists to cover.

    THE CLOCK IS A PARAMETER so the tests move time instead of sleeping, and it
    defaults to `time.monotonic` rather than `time.time` - a wall-clock
    adjustment must not open the window or hold it shut.
    """

    WINDOW_SECONDS = 60.0

    def __init__(self, per_minute: int,
                 clock: Callable[[], float] = time.monotonic):
        self._per_minute = per_minute
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    @property
    def per_minute(self) -> int:
        return self._per_minute

    def allow(self) -> bool:
        """Record this call and say whether it was within the ceiling.

        A REFUSED CALL IS NOT RECORDED. Recording it would let every rejected
        request push recovery further out, so a sustained flood would hold the
        endpoint shut for as long as it continued - a ceiling that becomes a
        permanent outage under exactly the load it was built for.

        The lock is not decoration: `chat()` is a synchronous handler, so
        FastAPI runs it in a threadpool and two requests can otherwise read the
        window's length before either appends to it.
        """
        if self._per_minute <= 0:
            return True
        now = self._clock()
        with self._lock:
            cutoff = now - self.WINDOW_SECONDS
            while self._calls and self._calls[0] <= cutoff:
                self._calls.popleft()
            if len(self._calls) >= self._per_minute:
                return False
            self._calls.append(now)
            return True

    def reset(self) -> None:
        """Forget every recorded call. For the test suite, which would
        otherwise share one ceiling across every test in the process."""
        with self._lock:
            self._calls.clear()
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_rate_limit.py -q`

Expected: 8 passed.

- [ ] **Step 5: PIN THE LOCK BY MUTATION, and report honestly what you see**

`test_the_ceiling_holds_when_threads_race` passes whether or not the lock is there if the threads never happen to interleave at the wrong moment. Prove it can fail.

Temporarily replace `with self._lock:` in `allow()` with `if True:` — keeping the body and its indentation identical — and run:

`python -m pytest tests/test_rate_limit.py::test_the_ceiling_holds_when_threads_race -q`

Run it **at least five times**. Expected: it fails on at least one run, with more than 50 admitted.

**If it never fails across five runs, do not declare the lock pinned and do not tune the test to force a failure.** Report that the mutation did not bite, say how many runs you tried, and leave the test as it is. That result is a finding about the test — it would mean the lock's necessity rests on the argument in the docstring rather than on evidence — and reporting it is worth more than a green claim.

**Then restore `with self._lock:` by hand** — `git checkout` would destroy the rest of your uncommitted work — and confirm the file is back with `git diff` before committing.

- [ ] **Step 6: Commit**

```bash
git add src/rate_limit.py tests/test_rate_limit.py
git commit -m "Add a sliding-window call ceiling"
```

---

### Task 2: Wire it to the endpoint

**Files:**
- Modify: `src/config.py` — the API/CORS section, around line 184
- Modify: `src/main.py` — imports, the instance, the dependency, the route decorator, the startup line
- Modify: `tests/test_main.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes from Task 1: `rate_limit.SlidingWindowLimit(per_minute, clock=...)`, `.allow() -> bool`, `.per_minute`, `.reset()`.
- Produces: `main._chat_limit`, the module-level instance the tests and the conftest fixture reach for by name.

The existing `_warn_if_open_cors` in `src/main.py` is the pattern to follow for the startup line: a module-level function, called once at import, printing to stdout, with a test that captures it through `capsys`.

- [ ] **Step 1: Add the setting**

In `src/config.py`, in the `# --- API / CORS --- #` section, directly after the `cors_origins_list` property and before the `@model_validator`, add:

```python
    # --- Rate limit --- #
    # A GLOBAL ceiling on /api/chat, not a per-caller one: behind a
    # TLS-terminating proxy this service cannot tell its callers apart, and a
    # limit keyed on a client-settable header would be protection in name only.
    # 60/minute is invisible to a demo - three people cannot produce sixty chat
    # turns in a minute - and immediate for a script. 0 disables it.
    rate_limit_per_minute: int = Field(default=60)
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_main.py`:

```python
def test_the_chat_endpoint_refuses_once_the_ceiling_is_crossed(monkeypatch):
    """The endpoint is public and unauthenticated, so the ceiling is the only
    thing standing between a script and the model bill."""
    from src import rate_limit
    monkeypatch.setattr(main, "_chat_limit", rate_limit.SlidingWindowLimit(2))
    fake = ChatResult(answer="cevap", recommended_products=[])
    monkeypatch.setattr(main.engine, "answer",
                        lambda msg, hist, budget=None, dose=None, compare=None: fake)
    body = {"message": "soru", "stream": False}
    assert client.post("/api/chat", json=body).status_code == 200
    assert client.post("/api/chat", json=body).status_code == 200
    refused = client.post("/api/chat", json=body)
    assert refused.status_code == 429
    assert "istek" in refused.json()["detail"].lower()


def test_the_catalog_routes_are_not_rate_limited(monkeypatch):
    """The ceiling guards the expensive path. These read a JSON file: no model
    call, no money, and throttling them would only break the app's browsing."""
    from src import rate_limit
    monkeypatch.setattr(main, "_chat_limit", rate_limit.SlidingWindowLimit(1))
    for _ in range(5):
        assert client.get("/api/products").status_code in (200, 503)
        assert client.get("/api/articles").status_code in (200, 503)


def test_the_active_ceiling_is_announced_at_startup(capsys):
    from src import rate_limit
    main._announce_rate_limit(rate_limit.SlidingWindowLimit(60))
    out = capsys.readouterr().out
    assert "60" in out and "/api/chat" in out


def test_a_disabled_ceiling_is_announced_as_a_warning(capsys):
    """Silence would make an unlimited public endpoint the quiet option."""
    from src import rate_limit
    main._announce_rate_limit(rate_limit.SlidingWindowLimit(0))
    out = capsys.readouterr().out
    assert "WARNING" in out
```

The `200 or 503` in the catalog test is deliberate: those routes return 503 when the data file is absent, and this test is about the limit, not about the file.

- [ ] **Step 3: Run them to verify they fail**

Run: `python -m pytest tests/test_main.py -q -k "ceiling or not_rate_limited"`

Expected: all four FAIL.
- the two `_announce_rate_limit` tests with `AttributeError: module 'src.main' has no attribute '_announce_rate_limit'`
- `test_the_chat_endpoint_refuses_once_the_ceiling_is_crossed` with `AttributeError` on `_chat_limit` from `monkeypatch.setattr` (it refuses to patch a name that does not exist)
- `test_the_catalog_routes_are_not_rate_limited` for the same reason

- [ ] **Step 4: Wire the limit into the app**

In `src/main.py`, add `Depends` to the FastAPI import:

```python
from fastapi import Depends, FastAPI, HTTPException
```

and add `rate_limit` to both branches of the try/except import block:

```python
try:
    from .config import settings, PRODUCTS_JSON
    from .articles_scraper import ARTICLES_JSON
    from . import engine
    from . import rate_limit
except ImportError:  # pragma: no cover
    from config import settings, PRODUCTS_JSON  # type: ignore
    from articles_scraper import ARTICLES_JSON  # type: ignore
    import engine  # type: ignore
    import rate_limit  # type: ignore
```

Then, directly below the existing `_warn_if_open_cors(settings.cors_origins_list)` call, add:

```python
# GLOBAL, not per caller. uvicorn runs without `--proxy-headers` behind a
# TLS-terminating proxy, so every request arrives wearing the proxy's address;
# a per-IP limit keyed on it would throttle everyone together while reading as
# if it isolated them, and one keyed on `X-Forwarded-For` would be bypassed by
# setting a header. See src/rate_limit.py.
_chat_limit = rate_limit.SlidingWindowLimit(settings.rate_limit_per_minute)


def _announce_rate_limit(limit: rate_limit.SlidingWindowLimit) -> None:
    """One-time startup line, the same job `_warn_if_open_cors` does above:
    a dangerous configuration should not be the silent one."""
    if limit.per_minute <= 0:
        print(
            "[main] WARNING: RATE_LIMIT_PER_MINUTE=0 - /api/chat accepts "
            "unlimited requests. It is public and unauthenticated."
        )
    else:
        print(
            f"[main] rate limit: {limit.per_minute} requests/minute on "
            f"/api/chat, counted globally rather than per caller. "
            f"Set RATE_LIMIT_PER_MINUTE=0 to disable."
        )


_announce_rate_limit(_chat_limit)


def _enforce_chat_limit() -> None:
    """Reads `_chat_limit` at call time rather than closing over it, so a test
    can swap the instance."""
    if not _chat_limit.allow():
        raise HTTPException(
            status_code=429,
            detail=("Şu anda çok fazla istek alıyorum. Lütfen biraz bekleyip "
                    "tekrar deneyin."),
        )
```

Finally, change the chat route decorator from:

```python
@app.post("/api/chat", response_model=ChatResponse)
```

to:

```python
@app.post("/api/chat", response_model=ChatResponse,
          dependencies=[Depends(_enforce_chat_limit)])
```

Leave the `chat()` function body and signature untouched — the dependency keeps the handler free of the concern.

- [ ] **Step 5: Stop the test suite from sharing one live ceiling**

The instance in `main.py` is module-level, so every test in the process shares it. The suite makes 20 chat POSTs today against a ceiling of 60, so it passes — by accident of the current test count, which is exactly the kind of accidental green this project has already paid to remove once.

In `tests/conftest.py`, add:

```python
@pytest.fixture(autouse=True)
def _fresh_chat_rate_limit():
    """`src/main.py` holds ONE rate limiter for the process, so without this
    every test in the suite spends from the same ceiling and the suite passes
    only while it stays under it. It makes 20 chat requests today against 60 -
    green by accident of the current test count, not by construction.

    Reached through `sys.modules` so this fixture does not import the app for
    the many tests that never touch it.
    """
    module = sys.modules.get("src.main")
    if module is not None:
        module._chat_limit.reset()
    yield
```

and add `import sys` to that file's imports.

- [ ] **Step 6: Run the suite**

Run: `python -m pytest -q`

Expected: 1036 passed before this branch, plus 8 from Task 1 and 4 from Step 2 — **1048 passed, 0 failed**. Report the real number.

- [ ] **Step 7: PIN THE CONFTEST FIXTURE BY MUTATION**

The fixture protects against a condition the suite does not currently meet, so prove it does something.

Temporarily change the default in `src/config.py` from `Field(default=60)` to `Field(default=1)` and run the full suite:

`python -m pytest -q`

Expected: still **all green**. With a ceiling of one request per minute for the whole process, every chat test after the first would 429 without the fixture.

Then temporarily comment out the `module._chat_limit.reset()` line in the fixture, leaving the default at 1, and run again. Expected: **failures** in `tests/test_main.py` and `tests/test_api_budget.py`, from unexpected 429s.

Restore both edits by hand and re-run to confirm green. Report all three outputs.

- [ ] **Step 8: Commit**

```bash
git add src/config.py src/main.py tests/test_main.py tests/conftest.py
git commit -m "Cap how often the public chat endpoint can be called"
```
