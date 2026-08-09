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
