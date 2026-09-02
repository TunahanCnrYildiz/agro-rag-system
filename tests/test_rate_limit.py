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


def test_the_check_and_record_happens_under_the_lock():
    """A GUARD ON THE LOCK ITSELF, because its EFFECT cannot be demonstrated
    cheaply. Measured 2026-09-03: with the lock removed, 2.000 calls across 40
    threads at a 1-microsecond switch interval never admitted more than the
    ceiling, over eight runs at each of three configurations. The unguarded
    window is a few bytecodes wide and only matters at the one moment the
    window fills, so CPython's scheduler almost never lands in it.

    That is an argument about today's scheduler, not about correctness, which
    is why the lock stays and why this test pins what the race test cannot.

    It watches the WINDOW, not just the acquisition: the deque must grow
    between entering the lock and leaving it. Asserting only that `__enter__`
    ran would leave `with self._lock: pass` followed by an unguarded
    check-and-record passing, which is the very shape the lock exists to
    forbid.
    """
    limit = rate_limit.SlidingWindowLimit(2, _Clock())
    real = limit._lock
    depth = []

    class _Recording:
        def __enter__(self):
            depth.append(len(limit._calls))
            return real.__enter__()

        def __exit__(self, *exc):
            depth.append(len(limit._calls))
            return real.__exit__(*exc)

    limit._lock = _Recording()
    assert limit.allow() is True
    assert depth == [0, 1]
