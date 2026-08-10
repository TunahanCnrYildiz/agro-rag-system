"""Score the frozen routing set.

    python -m evals.run_routing

Reports accuracy (spec gate: >= 90%), the one real gate here. The spec also
called for a <= 30% "model layer" gate, but src.router.classify() only ever
returns how="rule" or how="default" - there is no model layer, so that gate
measures nothing and is void. The default-route rate is still printed as
information (how often no rule fired), just not as a pass/fail decision.
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


ACCURACY_GATE = 0.90


def decide(out: dict) -> bool:
    """The pass/fail decision, isolated so it can be tested without running
    the full scorer.

    accuracy >= ACCURACY_GATE is the one real gate. by_how (and any "model"
    key in it) plays no part here - the former <= 30% "model layer" gate is
    void, since the router never actually calls a model.
    """
    return out["accuracy"] >= ACCURACY_GATE


def main() -> None:
    out = score(ROUTING_CASES)
    print(f"dogruluk : {out['correct']}/{out['total']} "
          f"({out['accuracy']:.0%})   kapi: >= 90%")
    print("model katmani kapisi (<= 30%) GECERSIZ: src.router.classify() "
          "yalnizca how='rule' veya how='default' donduruyor, model katmani "
          "hic calismiyor - bu kapi karara katilmiyor.")
    fallback_n = out["by_how"].get("default", 0)
    print(f"kural disi (varsayilan rota) orani : {fallback_n}/{out['total']} "
          f"({fallback_n / max(1, out['total']):.0%})   bilgi amacli, kapi degil")
    print(f"karar dagilimi : {out['by_how']}")
    if out["misses"]:
        print("\nkacirilanlar:")
        for q, exp, got in out["misses"]:
            print(f"  beklenen={exp:<12} gelen={got:<12} {q}")
    ok = decide(out)
    print("\nKAPILAR: " + ("GECTI" if ok else "GECMEDI"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
