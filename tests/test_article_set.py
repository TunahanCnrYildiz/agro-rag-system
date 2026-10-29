"""The labelled article set must stay well-formed: a label naming a post that
no longer exists, or one the eligibility filter drops, can never be matched -
and every miss it records is then a miss of nothing."""

import json

from evals.article_set import (DEV_NEGATIVE, DEV_POSITIVE, HOLDOUT_NEGATIVE,
                               HOLDOUT_POSITIVE, slug)
from src import engine
from src.config import ARTICLES_JSON


def _eligible_slugs():
    data = json.loads(ARTICLES_JSON.read_text(encoding="utf-8"))
    return {slug(a["source_url"]) for a in engine._eligible_articles(data)}


def test_every_label_names_an_eligible_post():
    eligible = _eligible_slugs()
    for query, labels in DEV_POSITIVE + HOLDOUT_POSITIVE:
        assert labels, query
        assert labels <= eligible, (query, labels - eligible)


def test_no_query_is_in_two_places():
    queries = ([q for q, _ in DEV_POSITIVE + HOLDOUT_POSITIVE]
               + DEV_NEGATIVE + HOLDOUT_NEGATIVE)
    assert len(queries) == len(set(queries))


def test_the_holdout_has_both_kinds():
    assert len(HOLDOUT_POSITIVE) >= 10 and len(HOLDOUT_NEGATIVE) >= 10
