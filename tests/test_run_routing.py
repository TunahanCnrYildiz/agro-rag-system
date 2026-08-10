"""The routing scorer must report both accuracy and how each decision was made -
the 30% model-layer gate is unmeasurable without the second number."""

from evals.run_routing import decide, score


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


def test_decide_passes_above_the_accuracy_threshold():
    assert decide({"accuracy": 0.90, "by_how": {}}) is True
    assert decide({"accuracy": 0.95, "by_how": {}}) is True


def test_decide_fails_below_the_accuracy_threshold():
    assert decide({"accuracy": 0.89, "by_how": {}}) is False
    assert decide({"accuracy": 0.0, "by_how": {}}) is False


def test_decide_ignores_by_how_entirely():
    """The void model-layer gate must not sneak back in through by_how - a
    "model" key (which classify() never actually produces) must not affect
    the verdict either way."""
    passing = {"accuracy": 0.95}
    failing = {"accuracy": 0.5}

    assert decide({**passing, "by_how": {"model": 999, "default": 999}}) is True
    assert decide({**passing, "by_how": {}}) is True
    assert decide({**failing, "by_how": {"model": 0, "default": 0}}) is False
    assert decide({**failing, "by_how": {"rule": 100}}) is False


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
