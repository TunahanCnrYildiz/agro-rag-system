"""Intent routing.

The pipeline used to run one path for every question: embed, search the corpus,
match products, answer. A budget question paid for a corpus search that cannot
hold its answer; a timing question never learned what month it was. This module
decides, before any of that work happens, which path a question takes.

Rules first, deliberately. Routing decided by the model would add a second
provider-portability surface, and this project has already measured one such
surface breaking: the [NOPRODUCT] marker stopped transferring when the chat
provider changed (2026-07-24). A deterministic rule costs nothing, never drifts,
and can be unit-tested without a network.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from src.engine import _normalize_tr

Route = Literal["plant_info", "nutrition", "fert_plan", "budget",
                "crop_choice", "product_dose", "offscope"]

# Stems match with a LEFT boundary and may run into their own suffixes, the same
# convention the crop lexicon and the product backstop use.
_BUDGET_STEMS = ("maliyet", "masraf", "butce", "kazanc",
                 "ciro", "yatirim")
# 'geri donus' was dropped: it is a left-boundary prefix of 'geri dönüşüm'
# (recycling), and misrouted plant-waste/composting questions to budget. The
# one frozen case that used it ("Bu yatırımın geri dönüşü ne kadar sürer?")
# already carries 'yatirim', so nothing is lost. See routing review, finding 4.2.
# 'gelir', 'gider' and 'zarar' were dropped: all three are high-frequency
# non-financial agriculture words ('giderilir' = remedied, 'zarar' = pest/frost
# damage, 'gelir' = comes into fruit) and misrouted plant questions to budget.
# See routing review, finding 1.
# Whole-word only: folding 'kâr' gives 'kar', which is a left prefix of karar,
# karnabahar, karisim, kardes. A stem match here would be a silent false positive.
_BUDGET_WORDS = ("kar", "karli", "karlilik", "karlimi")
_BUDGET_PHRASES = ("kac para", "ne kadar tutar", "ne kadar kazan")

_NUTRITION_STEMS = ("gubre", "besle", "azot", "fosfor", "potasyum",
                    "npk", "kompost", "besin")
# 'besle'/'besin' are generic Turkish for "feed"/"nutrient", not plant-specific,
# and matched animal-feeding questions ("İneklerimi nasıl beslerim?"). The
# nutrition rule (no time stem to add specificity) needs a narrower set, so it
# uses _PLANT_NUTRITION_STEMS below instead. See routing review, finding 4.1.
# The fert_plan rule still uses the full tuple above. The time stem does NOT
# fix the collision, though: "İneklerimi ne zaman beslerim?", "Tavuklarımı
# hangi ayda beslemeliyim?" and "Buzağıları ne zaman beslerim?" all measure
# fert_plan. fert_plan is checked before the nutrition carve-out, so the same
# collision just moves one precedence level up instead of being closed.
# Fixing it is deferred to the next plan (see
# docs/superpowers/2026-08-10-routing-foundation-findings.md).
_PLANT_NUTRITION_STEMS = ("gubre", "azot", "fosfor", "potasyum", "npk",
                          "kompost")
_TIME_STEMS = ("ne zaman", "hangi ay", "hangi donem", "takvim", "program",
               "donemde", "bu ay", "zamanla")

_CROP_CHOICE_PHRASES = ("ne eksem", "ne ekmek", "ne ekmeli", "ne ekeyim",
                        "hangi urun", "ne yetistir", "hangi meyve",
                        "mi ekmeliyim", "hangi bitkiyi")

_OFFSCOPE_STEMS = ("inek", "buzagi", "koyun", "tavuk", "hayvancilik",
                   "balik yetistir", "su urun", "traktor", "bicerdover",
                   "banka", "kredi", "dolar", "borsa")
# 'film' and 'takim' were dropped: 'film' prefixes plastic mulch film (a real
# protected-cropping practice) and 'takim' means set/kit as often as sports
# team ('fide takimi' = seedling kit). See routing review, finding 2.
# Whole-word only: folded 'mac' is a left prefix of 'macar', and 'Macar fiği' is
# a real forage legume. Same trap as 'kar'/'karar' above.
_OFFSCOPE_WORDS = ("mac", "maci", "maclar")

# "How much per dekar" phrasings. Deliberately narrow: every one of these names
# an AMOUNT PER AREA or asks for a dose outright, so none of them fires on a
# timing question ("ne zaman", "hangi ay") or on a price one - and budget is
# checked first anyway, which keeps "dekara maliyeti nedir" money.
_DOSE_PHRASES = ("dekara ne kadar", "dekara kac", "donume ne kadar",
                 "donume kac", "ne kadar atmali", "ne kadar atarim",
                 "kac litre", "kac kilo", "kac kg", "dozu nedir",
                 "dozu ne kadar", "dozu ne")

# A bare amount ask, generic enough to fire even when none of the phrases above
# does - but only alongside a named product (see classify_by_rules), never on
# its own: "ne kadar" and "kaç" are far too common in Turkish to gate a route
# by themselves. 'kac' is matched by WORD, not stem: folded 'kac' is a
# left-boundary prefix of 'kaçınmak', 'kaçak' and others that have nothing to
# do with amount.
_AMOUNT_PHRASES = ("ne kadar",)
_AMOUNT_WORDS = ("kac",)

# Fertilizer as a PRODUCT, for the no-product-named half of the dose rule.
# Deliberately just this one stem, not the wider _PLANT_NUTRITION_STEMS: 'azot',
# 'fosfor', 'potasyum', 'npk' and 'kompost' are ELEMENTAL/generic terms, and a
# question like "Dekara kaç kilo azot gerekir?" asks about the element, not a
# branded product - converting an elemental amount into a product mass is out
# of scope (design spec, out-of-scope §10) and answering it with a card of 40
# products would be a guess wearing a helpful shape. See routing review
# (2026-08-25), finding 1.
_FERTILIZER_PRODUCT_STEM = ("gubre",)


@lru_cache(maxsize=1)
def _product_pattern():
    """One regex over every product carrying a published dose, folded.

    Data-driven rather than a hand-kept list: a product that leaves the dose
    table stops triggering the route on the same day, and a new one starts.
    Both boundaries are anchored - 'FLY AZOT' must not fire on 'azotlu gubre'.
    """
    from src import doses
    names = [_normalize_tr(name) for name in doses.available_products()]
    if not names:
        return None
    names.sort(key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in names) + r")(?!\w)")


def _names_a_dose_product(folded: str) -> bool:
    try:
        pattern = _product_pattern()
    except Exception:  # noqa: BLE001 - routing must never break answering
        return False
    return bool(pattern and pattern.search(folded))


def _has_stem(folded: str, stems: tuple[str, ...]) -> bool:
    """Left-boundary match, so a stem may run into its own suffix."""
    return any(re.search(rf"(?<!\w){re.escape(s)}", folded) for s in stems)


def _has_word(folded: str, words: tuple[str, ...]) -> bool:
    """Both boundaries - for stems too short to be safe on the left alone."""
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", folded) for w in words)


def classify_by_rules(message: str) -> Route | None:
    """Return a route, or None when no rule fires and the model layer is needed.

    Ordered specific-to-general: a message that is both about money and about
    fertilizer ("gubre maliyeti") is a budget question first.
    """
    folded = _normalize_tr(message)

    if (_has_stem(folded, _BUDGET_STEMS)
            or _has_word(folded, _BUDGET_WORDS)
            or _has_stem(folded, _BUDGET_PHRASES)):
        return "budget"

    # A named product asking an amount, or a fertilizer-as-product amount
    # question with no product named. Checked after budget (a price question
    # about a product is still money) and before fert_plan/nutrition, which
    # would otherwise swallow every "gubre" in it.
    #
    # Naming a product is not asking how much of it - "HİGRO BARF nedir?" and
    # "BİNGO ürününü domateste kullanabilir miyim?" both name a product without
    # asking an amount, and used to hijack the route for every question that
    # merely mentions one. So clause A requires an amount signal alongside the
    # name; because the name is already present, that signal may be generic
    # (_DOSE_PHRASES, or a bare "ne kadar"/"kaç"), not just the narrow phrases
    # clause B needs to earn the route on its own. See routing review
    # (2026-08-25), finding 1.
    product_named = _names_a_dose_product(folded)
    if product_named and (
            _has_stem(folded, _DOSE_PHRASES)
            or _has_stem(folded, _AMOUNT_PHRASES)
            or _has_word(folded, _AMOUNT_WORDS)):
        return "product_dose"
    if not product_named and (
            _has_stem(folded, _DOSE_PHRASES)
            and _has_stem(folded, _FERTILIZER_PRODUCT_STEM)):
        return "product_dose"

    if _has_stem(folded, _CROP_CHOICE_PHRASES):
        return "crop_choice"

    if _has_stem(folded, _NUTRITION_STEMS) and _has_stem(folded, _TIME_STEMS):
        return "fert_plan"

    # A nutrition stem without a time stem is still a plant-nutrition question,
    # whatever animal or machine it happens to name ("inek gubresi", "traktorle
    # gubre atmak"). Checking this before offscope keeps those in scope instead
    # of letting the livestock/machinery stems below catch them. See routing
    # review, finding 3.
    if _has_stem(folded, _PLANT_NUTRITION_STEMS):
        return "nutrition"

    if _has_stem(folded, _OFFSCOPE_STEMS) or _has_word(folded, _OFFSCOPE_WORDS):
        return "offscope"

    return None


# The route taken whenever no rule fires. plant_info is today's corpus path, so
# an undecided question behaves exactly as it does now.
#
# There is deliberately NO model fallback here. Measured against the frozen set,
# the rules leave 17 of 42 cases undecided and 15 of those expect plant_info or
# nutrition - which is structural, since between them those two ARE the default
# and cannot have a positive rule. And they run the SAME corpus path, so a model
# call to tell them apart would change nothing while costing latency, money and
# reproducibility. Same trade this codebase already made when it replaced LLM
# query translation with the deterministic crop lexicon.
_DEFAULT_ROUTE: Route = "plant_info"


def classify(message: str, history: list[dict] | None = None) -> tuple[Route, str]:
    """Return (route, how) where how is 'rule' or 'default'.

    `history` is accepted but unused: Task 5 and the follow-up plans pass it, and
    taking it now means no signature change later.
    """
    ruled = classify_by_rules(message)
    if ruled is not None:
        return ruled, "rule"
    return _DEFAULT_ROUTE, "default"
