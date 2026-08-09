"""Product-gate diagnostic probe.

The eval harness reports whether product gating PASSED, not WHY it failed. A
case that should show products can be closed by four different gates, and the
fix is different for each one. This probe re-runs the production pipeline and
records, per sample, which gate closed first.

    python -m evals.probe_product_gate                       # local, 19 'some' cases
    python -m evals.probe_product_gate --repeat 3
    python -m evals.probe_product_gate --provider openrouter --model <id>
    python -m evals.probe_product_gate --cases none          # the regression side
    python -m evals.probe_product_gate --only tomato_nutrition

Why sampling matters here: the complaint being diagnosed is "bazi durumlarda
takiliyor" - intermittent. A single pass cannot distinguish a deterministic
threshold problem from a stochastic marker problem; --repeat can.

Writes one JSON line per sample to evals/runs/<UTC>-probe.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The Windows console cannot encode Turkish; corpus and answer text both carry it.
# line_buffering so a 20-minute run shows progress instead of dumping at exit.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from evals.eval_set import CASES  # noqa: E402
from evals.run_eval import _apply_provider_override  # noqa: E402
from src import engine  # noqa: E402


# Gate names, in the order engine.answer() applies them. The FIRST one that
# closes is the attributed cause - later gates are not reached in production.
GATE_THRESHOLD = "threshold"    # match_products returned nothing (< MIN_PRODUCT_SIMILARITY)
GATE_NO_ADVICE = "no_advice"    # fallback reply, no advice for products to sit under
GATE_OFFSCOPE = "marker_offscope"
GATE_NOPRODUCT = "marker_noproduct"
GATE_BACKSTOP = "backstop"      # _looks_non_product fired on the answer text
GATE_OPEN = "open"              # nothing closed: products shown
GATE_ERROR = "error"        # the model call raised - NOT a gate closure


def _attribute_gate(raw_count: int, answer_text: str) -> tuple[str, dict]:
    """Mirror engine.answer()'s gating order and name the gate that closes.

    Kept as a faithful replay of engine.answer() lines 712-722 rather than a
    reimplementation of the rules: every predicate below is the engine's own
    function, so only the ORDER is restated here. _selftest() guards that.
    """
    if raw_count == 0:
        return GATE_THRESHOLD, {}

    has_advice = engine._has_advice(answer_text)
    clean, off_scope, no_product = engine._strip_markers(answer_text)
    backstop = engine._looks_non_product(clean)
    flags = {
        "has_advice": has_advice,
        "marker_offscope": off_scope,
        "marker_noproduct": no_product,
        "backstop": backstop,
    }

    if not has_advice:
        return GATE_NO_ADVICE, flags
    if off_scope:
        return GATE_OFFSCOPE, flags
    if no_product:
        return GATE_NOPRODUCT, flags
    if backstop:
        return GATE_BACKSTOP, flags
    return GATE_OPEN, flags


def _selftest() -> None:
    """Cheap guard that the replayed order still matches the engine, no LLM call."""
    # An ordinary nutrition answer with candidates: gate must be open.
    g, _ = _attribute_gate(3, "Domatesin azot ihtiyaci icin kompost ve solucan gubresi kullanabilirsiniz.")
    assert g == GATE_OPEN, g
    # No candidates: threshold wins even on a perfect answer.
    g, _ = _attribute_gate(0, "Kompost ve azotlu gubre onerilir.")
    assert g == GATE_THRESHOLD, g
    # Marker beats the backstop.
    g, _ = _attribute_gate(3, "[NOPRODUCT] Asmada budama kis sonunda yapilir.")
    assert g == GATE_NOPRODUCT, g
    # Backstop fires on a non-product activity with no nutrition term.
    g, _ = _attribute_gate(3, "Asmada budama kis sonunda, uyku doneminde yapilir.")
    assert g == GATE_BACKSTOP, g


def _top_score(query: str, ctx: str) -> float | None:
    """Highest product cosine for the query - shows how marginal the threshold is."""
    products = engine._load_products()
    if not products:
        return None
    embed_input = f"{query}\n{ctx[:1000]}" if ctx.strip() else query
    try:
        q = engine._get_embeddings_client().embed_query(embed_input)
    except Exception:  # noqa: BLE001
        return None
    return max(engine._cosine(q, p["_embedding"]) for p in products)


def _select(cases_arg: str, only: str | None) -> list[dict]:
    if only:
        picked = [c for c in CASES if c["id"] == only or c["category"] == only]
        if not picked:
            sys.exit(f"no case or category matching {only!r}")
        return picked
    if cases_arg == "all":
        return list(CASES)
    return [c for c in CASES if c.get("products", "any") == cases_arg]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repeat", type=int, default=3, metavar="N",
                   help="samples per case (default 3); the complaint is intermittent")
    p.add_argument("--cases", default="some", choices=["some", "none", "all"],
                   help="'some' = must show products (default), 'none' = must not")
    p.add_argument("--only", metavar="ID|CATEGORY")
    p.add_argument("--provider", choices=["local", "openrouter"])
    p.add_argument("--model", metavar="ID")
    p.add_argument("--tag", default="", help="label written into the run header")
    args = p.parse_args()

    _selftest()
    _apply_provider_override(args.provider, args.model)

    cases = _select(args.cases, args.only)
    profile = engine._chat_profile()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{stamp}-probe.jsonl")

    header = {
        "kind": "product-gate-probe",
        "utc": stamp,
        "tag": args.tag,
        "provider": args.provider or "(env default)",
        "model": profile.model,
        "cases": args.cases if not args.only else args.only,
        "n_cases": len(cases),
        "repeat": args.repeat,
        "expect": "products shown" if args.cases == "some" else "products hidden",
        "min_product_similarity": engine.MIN_PRODUCT_SIMILARITY,
    }
    print(json.dumps(header, ensure_ascii=False))
    print(f"-> {out_path}\n")

    fh = open(out_path, "w", encoding="utf-8")
    fh.write(json.dumps(header, ensure_ascii=False) + "\n")

    totals: dict[str, int] = {}
    rows = []
    t0 = time.time()

    for c in cases:
        # Retrieval and matching are deterministic (embedding + vector search,
        # no sampling), so they are measured once however high --repeat is.
        ctx = engine.retrieve_context(c["query"])
        raw = engine.match_products(c["query"], ctx)
        top = _top_score(c["query"], ctx)
        messages = engine._build_messages(c["query"], None, ctx, raw)

        gates: list[str] = []
        for i in range(args.repeat):
            err = None
            try:
                text = engine._complete_text(messages)
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {str(exc)[:120]}"
                text = engine._llm_unavailable_message(exc)
            if err:
                gate, flags = GATE_ERROR, {"error": err}
            else:
                gate, flags = _attribute_gate(len(raw), text)
            gates.append(gate)
            totals[gate] = totals.get(gate, 0) + 1
            fh.write(json.dumps({
                "case": c["id"], "category": c["category"], "sample": i,
                "raw_products": len(raw), "top_score": top,
                "gate": gate, **flags,
                "answer": text,
            }, ensure_ascii=False) + "\n")
            fh.flush()

        want_open = c.get("products", "any") == "some"
        n_open = gates.count(GATE_OPEN)
        ok = n_open == args.repeat if want_open else n_open == 0
        rows.append((c["id"], ok, n_open, args.repeat, top, len(raw), gates))
        mark = "OK  " if ok else "FAIL"
        score = f"{top:.3f}" if top is not None else "  -  "
        print(f"{mark} {c['id']:<34} open={n_open}/{args.repeat} "
              f"raw={len(raw)} top={score}  {','.join(gates)}")

    fh.close()

    print("\n" + "=" * 78)
    passed = sum(1 for r in rows if r[1])
    print(f"gecen vaka : {passed}/{len(rows)}   "
          f"(butun orneklerde beklendigi gibi davranan)")
    print(f"sure       : {time.time() - t0:.0f} s")
    print("\nkapi dagilimi (ornek basina):")
    for gate, n in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {gate:<18} {n:>4}  ({n / max(1, sum(totals.values())):.0%})")

    errs = totals.get(GATE_ERROR, 0)
    if errs:
        print(f"\nUYARI: {errs} ornek model cagrisi hatasiyla dustu "
              f"(zaman asimi / baglanti).")
        print("Bu ornekler urun kapisini OLCMEZ. Uretim saglikli hale "
              "gelmeden kapi yorumlanamaz.")

    unstable = [r for r in rows if 0 < r[2] < r[3]]
    print(f"\nkararsiz vaka (ayni soru bazen acik bazen kapali): {len(unstable)}")
    for r in unstable:
        print(f"  {r[0]:<34} {r[2]}/{r[3]} acik")
    if errs:
        print("\nKararsizligin bir kismi cagri hatasindan olabilir - "
              "once UYARI satirina bak.")
    else:
        print("\nKararsizlik varsa sorun esik degil, model/marker kaynaklidir.")


if __name__ == "__main__":
    main()
