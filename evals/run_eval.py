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


def _context_ok(case: dict, ctx: str) -> bool:
    """The retrieved context must actually be ABOUT the query's topic.

    'nonempty' only proves chunks cleared the score floor, not that they are
    relevant - the pre-cross-lingual bug looked exactly like that (full context,
    mostly unrelated chunks). Terms are listed in BOTH languages where relevant,
    so this asserts the topic was found, not the language it was found in.
    """
    terms = case.get("context_any") or []
    if not terms:
        return True
    c = ctx.lower()
    return any(t.lower() in c for t in terms)


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


def _select(only: str | None) -> list[dict]:
    """Pick the cases to run: everything, or one id / one category.

    A whole-set --repeat run costs N x ~20 min, so without this the sampling is
    too expensive to actually use.
    """
    if not only:
        return list(CASES)
    picked = [c for c in CASES if c["id"] == only or c["category"] == only]
    if not picked:
        cats = sorted({c["category"] for c in CASES})
        sys.exit(f"--only {only!r} matched no case. Pass a case id, or one of: "
                 f"{', '.join(cats)}")
    return picked


def run(fast: bool, repeat: int = 1, only: str | None = None) -> int:
    if fast and repeat > 1:
        sys.exit("--repeat needs the chat model; it does nothing with --fast.")
    cases = _select(only)
    if not fast:
        settings.request_timeout = 400.0
    suffix = f", {repeat}x each" if repeat > 1 else ""
    print(f"Running eval on {len(cases)} cases "
          f"({'FAST' if fast else 'FULL'}{suffix})\n")
    rows = []
    for c in cases:
        t = time.time()
        # retrieval/context are deterministic (embedding + vector search, no
        # sampling), so they are measured once however high `repeat` is.
        ctx = engine.retrieve_context(c["query"])
        row = {"id": c["id"], "cat": c["category"],
               "retrieval": _retrieval_ok(c, ctx),
               "context": _context_ok(c, ctx)}
        if fast:
            raw = engine.match_products(c["query"], ctx)
            row["raw_products"] = len(raw)
            row["ok"] = all([row["retrieval"], row["context"]])
        else:
            samples = []
            for _ in range(repeat):
                r = engine.answer(c["query"])
                g, gr = _answer_ok(c, r.answer)
                samples.append({
                    "products": _products_ok(c, len(r.recommended_products)),
                    "grounding": g,
                    "guardrail": gr,
                })
            for dim in ("products", "grounding", "guardrail"):
                vals = [s[dim] for s in samples]
                # every sample must pass: "leaks 1 time in 8" is a failure
                row[dim] = all(vals)
                row[dim + "_hits"] = (sum(vals), len(vals))
            row["ok"] = all([row["retrieval"], row["context"],
                             row["products"], row["grounding"],
                             row["guardrail"]])
        row["secs"] = time.time() - t
        rows.append(row)
        mark = "PASS" if row["ok"] else "FAIL"
        if fast:
            detail = f"rawprod={row.get('raw_products')}"
        elif repeat > 1:
            detail = " ".join(
                f"{name}={row[dim + '_hits'][0]}/{row[dim + '_hits'][1]}"
                for name, dim in (("prod", "products"), ("ground", "grounding"),
                                  ("guard", "guardrail")))
        else:
            detail = (f"prod={row['products']} ground={row['grounding']} "
                      f"guard={row['guardrail']}")
        print(f"  [{mark}] {c['id']:<24} ret={row['retrieval']} "
              f"ctx={row['context']} " + detail + f"  ({row['secs']:.0f}s)")

    passed = sum(1 for r in rows if r["ok"])
    print(f"\n=== {passed}/{len(rows)} cases passed ===")

    def rate(key):
        vals = [r[key] for r in rows if key in r]
        return f"{sum(vals)}/{len(vals)}" if vals else "n/a"

    def sample_rate(dim):
        """Rate over SAMPLES, not cases: 'guardrail: 23/24' reads very
        differently from 'guardrail: 30/31', and that difference is the point."""
        hits = [r[dim + "_hits"] for r in rows if dim + "_hits" in r]
        if not hits:
            return "n/a"
        return f"{sum(h for h, _ in hits)}/{sum(n for _, n in hits)}"

    print(f"  retrieval: {rate('retrieval')} | context: {rate('context')}", end="")
    if not fast:
        print(f" | product-gating: {sample_rate('products')}"
              f" | grounding: {sample_rate('grounding')}"
              f" | guardrail: {sample_rate('guardrail')}")
    else:
        print()
    return 0 if passed == len(rows) else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Run the RAG quality eval.")
    p.add_argument("--fast", action="store_true",
                   help="Retrieval + raw product gating only (skip chat LLM).")
    p.add_argument("--repeat", type=int, default=1, metavar="N",
                   help="Sample each case N times (full mode only). A case "
                        "passes only if EVERY sample passes. Generation is "
                        "sampled, so a single run hides intermittent failures; "
                        "N>1 costs N x ~20 min.")
    p.add_argument("--only", metavar="ID|CATEGORY",
                   help="Run just one case id, or one category (nutrition, "
                        "horticulture, disease, chemical, offscope). Pair with "
                        "--repeat: sampling all 31 cases N times costs N x ~20 "
                        "min, one category is minutes.")
    args = p.parse_args()
    sys.exit(run(fast=args.fast, repeat=args.repeat, only=args.only))


if __name__ == "__main__":
    main()
