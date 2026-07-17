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
from contextlib import contextmanager, nullcontext
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


@contextmanager
def _corpus_ablated():
    """Force retrieve_context to "" for the whole run.

    Patches the module attribute, not a local: answer() looks the name up on
    `engine` at call time, so this covers the retrieval INSIDE answer() - which
    is the one under test. A version that only blanked run()'s own `ctx` would
    ablate nothing and quietly "prove" the corpus load-bearing.
    """
    original = engine.retrieve_context
    engine.retrieve_context = lambda query, k=None: ""
    try:
        yield
    finally:
        engine.retrieve_context = original


def _ablation_verdict(rows: list[dict]) -> tuple[int, list[str]]:
    """(exit_code, decorative_case_ids) for a --no-context run.

    A `local` case exists to prove the corpus is load-bearing, so with an empty
    corpus it MUST lose grounding. One that still passes is asserting something
    the model knows anyway - decoration, and exactly the blind spot this flag
    exists to expose.

    Ordinary cases are ignored on purpose: they fail under ablation by
    construction (measured 2026-07-17: product-gating 31/31 -> 27/31), so letting
    them touch the exit code would make it 1 on every run and worthless.
    """
    local_rows = [r for r in rows if r.get("cat") == "local"]
    if not local_rows:
        return 1, []
    decorative = [r["id"] for r in local_rows if r.get("grounding")]
    return (1 if decorative else 0), decorative


def _classify(normal_all_green: bool, ablated_all_green: bool) -> str:
    """Label a case by how its grounding moves when the corpus is removed.

    corpus-carried : green normally, red ablated -> the corpus supplies the fact.
    model-carried  : green both ways -> the model knew it (or the mark is wrong).
    retrieval-broken: red both ways -> cannot answer even with the corpus.
    corpus-harmful : red normally, green ablated -> retrieval injected noise that
                     broke an answer the model would otherwise have gotten right.
    """
    if normal_all_green:
        return "corpus-carried" if not ablated_all_green else "model-carried"
    return "corpus-harmful" if ablated_all_green else "retrieval-broken"


def run(fast: bool, repeat: int = 1, only: str | None = None,
        no_context: bool = False) -> int:
    if fast and repeat > 1:
        sys.exit("--repeat needs the chat model; it does nothing with --fast.")
    if fast and no_context:
        sys.exit("--no-context needs the chat model; --fast never calls answer().")
    cases = _select(only)
    if not fast:
        settings.request_timeout = 400.0
    suffix = f", {repeat}x each" if repeat > 1 else ""
    print(f"Running eval on {len(cases)} cases "
          f"({'FAST' if fast else 'FULL'}{suffix})\n")
    rows = []
    # The ablation must be in force around answer(), not just around run()'s own
    # retrieve_context call - blanking only the local `ctx` would ablate nothing.
    with (_corpus_ablated() if no_context else nullcontext()):
      for c in cases:
        t = time.time()
        # retrieval/context are deterministic (embedding + vector search, no
        # sampling), so they are measured once however high `repeat` is.
        ctx = engine.retrieve_context(c["query"])
        row = {"id": c["id"], "cat": c["category"]}
        # retrieval/context are emptied BY this flag; scoring them would print a
        # wall of tautological FAILs (24 of them, measured) and bury the signal.
        if not no_context:
            row["retrieval"] = _retrieval_ok(c, ctx)
            row["context"] = _context_ok(c, ctx)
        if fast:
            raw = engine.match_products(c["query"], ctx)
            row["raw_products"] = len(raw)
            row["ok"] = all(row[d] for d in ("retrieval", "context"))
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
            dims = ["products", "grounding", "guardrail"]
            if not no_context:
                dims += ["retrieval", "context"]
            row["ok"] = all(row[d] for d in dims)
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
        ret_ctx = ("ret=n/a ctx=n/a " if no_context
                   else f"ret={row['retrieval']} ctx={row['context']} ")
        print(f"  [{mark}] {c['id']:<24} " + ret_ctx + detail
              + f"  ({row['secs']:.0f}s)")

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
    if no_context:
        code, decorative = _ablation_verdict(rows)
        n_local = sum(1 for r in rows if r["cat"] == "local")
        if not n_local:
            print("\n[ablation] no `local` case in this selection - "
                  "nothing was validated")
            return code
        print(f"\n[ablation] local cases that lost grounding: "
              f"{n_local - len(decorative)}/{n_local}"
              + (" - they discriminate" if not decorative else ""))
        for case_id in decorative:
            print(f"[ablation] ! {case_id} still passes grounding with an EMPTY "
                  f"corpus - it guards nothing")
        return code
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
    p.add_argument("--no-context", action="store_true",
                   help="Ablation: run with an EMPTY corpus to prove the `local` "
                        "cases actually depend on retrieval. Exit 0 only if every "
                        "local case loses grounding.")
    args = p.parse_args()
    sys.exit(run(fast=args.fast, repeat=args.repeat, only=args.only,
                 no_context=args.no_context))


if __name__ == "__main__":
    main()
