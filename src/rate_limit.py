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
