"""Retrieval diagnostic: dump what the vector search returns for probe queries,
so a human can judge retrieval quality BEFORE deciding on any hybrid/rerank/MMR
change (measure first, optimise second).

    python -m evals.inspect_retrieval                 # eval + hard probes, k=10
    python -m evals.inspect_retrieval --k 8           # show top-8 per query
    python -m evals.inspect_retrieval --queries hard  # only the hard probes

Needs LM Studio serving the EMBEDDING model. Writes a markdown report to
docs/retrieval_report.md and prints a compact per-query summary. No new deps.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import engine  # noqa: E402
from src.config import settings, DOCS_DIR  # noqa: E402
from evals.eval_set import CASES  # noqa: E402

# Curated hard probes that stress retrieval differently from the eval set:
# exact terms / NPK ratios / Latin binomials (dense embeddings blur these),
# cross-lingual queries (corpus is TR+EN), and an off-scope query (the relevance
# floor must reject it - nothing should clear it).
HARD_PROBES = [
    ("npk_exact", "14-14-14 kompoze gübre hangi bitkilerde ve ne zaman kullanılır?"),
    ("bordeaux_mix", "Bağda bordo bulamacı nasıl hazırlanır ve uygulanır?"),
    ("tuta_latin", "Tuta absoluta zararlısına karşı organik mücadele yöntemleri"),
    ("fr_cassava", "Comment fertiliser le manioc pour un meilleur rendement?"),
    ("es_compost", "¿Cómo hago compost en casa para mi jardín?"),
    ("offscope_crypto", "Bitcoin fiyatı bu yıl ne olur?"),
]


def probe_queries(which: str) -> list[tuple[str, str]]:
    """Return (id, query) pairs for the chosen probe set."""
    eval_qs = [(c["id"], c["query"]) for c in CASES]
    if which == "eval":
        return eval_qs
    if which == "hard":
        return HARD_PROBES
    return eval_qs + HARD_PROBES


def _snippet(text: str, n: int = 160) -> str:
    """Whitespace-collapsed, length-capped, pipe-escaped chunk preview (the pipe
    escape keeps a chunk that contains '|' from breaking the markdown table)."""
    flat = re.sub(r"\s+", " ", text).strip()[:n]
    return flat.replace("|", "\\|")


def build_report(rows, k: int, which: str, floor: float, prod_k: int) -> str:
    """Render the markdown report from gathered rows.

    ``rows`` is a list of ``(qid, query, results, error)`` where ``results`` is a
    list of ``(Document, score)`` (or None when ``error`` is set). Pure function
    of its inputs so it can be unit-tested without a live store.
    """
    out = [
        "# Retrieval diagnostic report",
        "",
        f"- probes: **{which}** ({len(rows)})  |  top-k shown: **{k}**  "
        f"|  production k={prod_k}, relevance floor={floor}",
        "- ✓ = clears the floor (would reach the LLM);  ✗ = dropped as noise",
        "",
    ]
    for qid, query, results, error in rows:
        out.append(f"## {qid}")
        out.append(f"\n> {query}\n")
        if error is not None:
            out.append(f"_retrieval failed: {error}_\n")
            continue
        kept = sum(1 for _d, s in results if s >= floor)
        top = results[0][1] if results else 0.0
        cut = results[prod_k - 1][1] if len(results) >= prod_k else 0.0
        out.append(
            f"_cleared floor: **{kept}/{len(results)}**  |  #1 score {top:.3f}  |  "
            f"#{prod_k} (prod cutoff) score {cut:.3f}_\n"
        )
        out.append("| # | score | ✓ | source | p. | snippet |")
        out.append("|--:|------:|:-:|--------|---:|---------|")
        for i, (d, score) in enumerate(results, 1):
            mark = "✓" if score >= floor else "✗"
            src = d.metadata.get("source", "?")
            page = d.metadata.get("page", "?")
            out.append(f"| {i} | {score:.3f} | {mark} | {src} | {page} | {_snippet(d.page_content)} |")
        out.append("")
    return "\n".join(out)


def _gather(store, queries, k):
    """Run each query against the store, capturing results or the error."""
    rows = []
    for qid, query in queries:
        try:
            results = store.similarity_search_with_relevance_scores(query, k=k)
            rows.append((qid, query, results, None))
        except Exception as exc:  # noqa: BLE001
            rows.append((qid, query, None, str(exc)))
    return rows


def run(k: int, which: str) -> int:
    store = engine._get_retriever_store()
    if store is None:
        print("[inspect] vector store unavailable (nothing ingested / langchain missing).")
        return 1
    floor = engine.MIN_RETRIEVAL_RELEVANCE
    prod_k = settings.retrieval_k

    rows = _gather(store, probe_queries(which), k)
    report = build_report(rows, k, which, floor, prod_k)

    out = DOCS_DIR / "retrieval_report.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(f"[inspect] wrote {out}\n")

    # Compact console summary: one line per query.
    for qid, _query, results, error in rows:
        if error is not None:
            print(f"  {qid:<22} ERROR: {error}")
            continue
        kept = sum(1 for _d, s in results if s >= floor)
        top = results[0][1] if results else 0.0
        print(f"  {qid:<22} cleared {kept}/{len(results)}  top={top:.3f}")
    return 0


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass

    p = argparse.ArgumentParser(
        description="Diagnostic dump of retrieval results for probe queries."
    )
    p.add_argument("--k", type=int, default=10, help="Top-k results to show per query.")
    p.add_argument("--queries", choices=["eval", "hard", "all"], default="all",
                   help="Which probe set to run (default: all).")
    args = p.parse_args()
    sys.exit(run(k=args.k, which=args.queries))


if __name__ == "__main__":
    main()
