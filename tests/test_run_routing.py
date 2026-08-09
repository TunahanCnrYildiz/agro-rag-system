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
