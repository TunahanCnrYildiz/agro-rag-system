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
