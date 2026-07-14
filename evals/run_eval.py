"""Repeatable quality eval for the RAG assistant.

    python -m evals.run_eval --fast   # retrieval + raw product gating (no chat LLM)
    python -m evals.run_eval          # full: also generate answers + keyword checks

Both modes need LM Studio serving the EMBEDDING model; full mode also needs the
CHAT model (slow). Prints a per-case table + aggregate metrics; exit code is
non-zero if any case fails (so it can gate CI later).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import engine  # noqa: E402
from src.config import settings  # noqa: E402
from evals.eval_set import CASES  # noqa: E402


def _retrieval_ok(case: dict, ctx: str) -> bool:
    exp = case.get("retrieval", "any")
    nonempty = bool(ctx.strip())
    if exp == "nonempty":
        return nonempty
    if exp == "empty":
        return not nonempty
    return True


def _products_ok(case: dict, n_products: int) -> bool:
    exp = case.get("products", "any")
    if exp == "some":
        return n_products > 0
    if exp == "none":
        return n_products == 0
    return True


def _answer_ok(case: dict, answer: str) -> tuple[bool, bool]:
    """(grounding_ok, guardrail_ok)."""
    a = answer.lower()
    any_terms = case.get("answer_any") or []
    none_terms = case.get("answer_none") or []
    grounding = (not any_terms) or any(t.lower() in a for t in any_terms)
    guardrail = all(t.lower() not in a for t in none_terms)
    return grounding, guardrail


def run(fast: bool) -> int:
    if not fast:
        settings.request_timeout = 400.0
    print(f"Running eval on {len(CASES)} cases ({'FAST' if fast else 'FULL'})\n")
    rows = []
    for c in CASES:
        t = time.time()
        ctx = engine.retrieve_context(c["query"])
        row = {"id": c["id"], "cat": c["category"],
               "retrieval": _retrieval_ok(c, ctx)}
        if fast:
            raw = engine.match_products(c["query"], ctx)
            row["raw_products"] = len(raw)
            row["ok"] = row["retrieval"]
        else:
            r = engine.answer(c["query"])
            row["products"] = _products_ok(c, len(r.recommended_products))
            g, gr = _answer_ok(c, r.answer)
            row["grounding"] = g
            row["guardrail"] = gr
            row["ok"] = all([row["retrieval"], row["products"], g, gr])
        row["secs"] = time.time() - t
        rows.append(row)
        mark = "PASS" if row["ok"] else "FAIL"
        print(f"  [{mark}] {c['id']:<24} ret={row['retrieval']} "
              + (f"rawprod={row.get('raw_products')}" if fast else
                 f"prod={row['products']} ground={row['grounding']} guard={row['guardrail']}")
              + f"  ({row['secs']:.0f}s)")

    passed = sum(1 for r in rows if r["ok"])
    print(f"\n=== {passed}/{len(rows)} cases passed ===")

    def rate(key):
        vals = [r[key] for r in rows if key in r]
        return f"{sum(vals)}/{len(vals)}" if vals else "n/a"

    print(f"  retrieval: {rate('retrieval')}", end="")
    if not fast:
        print(f" | product-gating: {rate('products')}"
              f" | grounding: {rate('grounding')}"
              f" | guardrail: {rate('guardrail')}")
    else:
        print()
    return 0 if passed == len(rows) else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Run the RAG quality eval.")
    p.add_argument("--fast", action="store_true",
                   help="Retrieval + raw product gating only (skip chat LLM).")
    args = p.parse_args()
    sys.exit(run(fast=args.fast))


if __name__ == "__main__":
    main()
