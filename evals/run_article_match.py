"""Score Akademi article matching on the labelled set.

    python -m evals.run_article_match

Needs the embedding server (LM Studio's bge-m3 locally). For each set, prints
how many positives get a RIGHT post and how many questions get a WRONG one
(a positive whose top post is not among its labels, or any negative that
clears the bar) at the configured threshold and around it. The configured
threshold's bar is zero wrong on both sets.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from evals.article_set import (DEV_NEGATIVE, DEV_POSITIVE, HOLDOUT_NEGATIVE,  # noqa: E402
                               HOLDOUT_POSITIVE, slug)
from src import engine  # noqa: E402


def _top(query_vec, articles):
    return max(((engine._cosine(query_vec, a["_embedding"]), slug(a["source_url"]))
                for a in articles), key=lambda x: x[0])


def main() -> int:
    articles = engine._load_articles()
    if not articles:
        print("no articles loaded - is the embedding server up?")
        return 1
    emb = engine._get_embeddings_client()
    worst = 0
    for name, pos, neg in (("DEV", DEV_POSITIVE, DEV_NEGATIVE),
                           ("HOLDOUT", HOLDOUT_POSITIVE, HOLDOUT_NEGATIVE)):
        queries = [q for q, _ in pos] + neg
        vecs = dict(zip(queries, emb.embed_documents(queries)))
        top = {q: _top(vecs[q], articles) for q in queries}
        print(f"\n=== {name}: {len(pos)} positive, {len(neg)} negative")
        for t in sorted({engine.MIN_ARTICLE_SIMILARITY, 0.55, 0.60, 0.70}):
            right = sum(1 for q, ok in pos if top[q][0] >= t and top[q][1] in ok)
            wrong = sum(1 for q, ok in pos if top[q][0] >= t and top[q][1] not in ok) + \
                sum(1 for q in neg if top[q][0] >= t)
            mark = "  <- configured" if t == engine.MIN_ARTICLE_SIMILARITY else ""
            print(f"  t={t:.2f}: right {right}/{len(pos)}, WRONG {wrong}{mark}")
            if t == engine.MIN_ARTICLE_SIMILARITY:
                worst = max(worst, wrong)
    print(f"\nconfigured threshold {engine.MIN_ARTICLE_SIMILARITY}: "
          f"{'PASS' if worst == 0 else 'FAIL'} (wrong articles must be 0)")
    return 0 if worst == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
