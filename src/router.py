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
                "crop_choice", "product_dose", "season", "offscope"]

# Stems match with a LEFT boundary and may run into their own suffixes, the same
# convention the crop lexicon and the product backstop use.
_BUDGET_STEMS = ("maliyet", "masraf", "butce", "kazanc",
                 "ciro", "yatirim", "fiyat")
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
_BUDGET_WORDS = ("kar", "karli", "karlilik", "karlimi",
                 # 'gelir' itself stays out (above), but its NOUN-only forms
                 # cannot be the verb: "geliri", "gelirimi", "gelirimiz",
                 # "gelirini" never mean "comes". "gelirim" is left out - it is
                 # also "I come".
                 "geliri", "gelirimi", "gelirimiz", "gelirini")
# The verb 'gelir' ("meyveye gelir", "kendine gelir", "denk gelir") never sits
# beside these words, so each phrase is income alone: "...ne kadar gelir elde
# ederim?" is a farmer's most natural way to ask the budget question, and it
# was answered as off-scope. Measured 2026-10-29 on 20 verb-'gelir' plant
# questions (0 routed to budget) and 9 income ones (9 routed), see
# tests/test_router.py.
_BUDGET_PHRASES = ("kac para", "ne kadar tutar", "ne kadar kazan",
                   "gelir elde", "gelir bekle", "gelir getir", "gelir sagla",
                   "ne kadar gelir", "yillik gelir")

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

# A season calendar named outright, or a calendar/programme asked to be drawn up.
_SEASON_PHRASES = ("sezon program", "sezon takvim", "ekim takvim", "ekim program",
                   "dikim takvim", "dikim program", "sulama takvim", "sulama program",
                   "yetistirme takvim", "yetistirme program", "uretim takvim",
                   "bakim takvim")
_SEASON_ASK = re.compile(r"(?<!\w)(?:takvim|program)\w*\s+"
                         r"(?:cikar|olustur|hazirla|yapar|yap\b|ver)")

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
# do with amount. 'ne miktar', 'miktari' and 'orani' were added 2026-08-25
# (post-fix review): natural Turkish amount words that real dose questions
# ("HİGRO BARF'ı dekara ne miktarda vermeliyim?", "...kullanım miktarı nedir?",
# "...oranı dekara nedir?") were falling through without.
_AMOUNT_PHRASES = ("ne kadar", "ne miktar", "miktari", "orani")
_AMOUNT_WORDS = ("kac",)

# The generic amount signal above ("ne kadar"/"kaç") also fires on questions
# that are not about quantity at all: a duration ("kaç günde bir uygulanır?"),
# a price ("kaç lira?", "ne kadar sürede" aside, "fiyatı ne kadar?" is caught
# separately by 'fiyat' in _BUDGET_STEMS, checked before this rule) or a count
# of kinds ("kaç çeşit var?"). Measured 2026-08-25 (post-fix review), all still
# routing product_dose on the strength of a named product plus a bare amount
# word: "HİGRO BARF kaç günde bir uygulanır?", "...ne kadar sürede etki eder?",
# "...raf ömrü kaç ay?", "...kaç lira?", "...kaç çeşit var?". None of these asks
# how much to apply, so the generic amount signal must not fire on them.
_NON_DOSE_AMOUNT_PHRASES = ("kac gun", "kac gunde", "gunde bir", "kac ay",
                            "kac hafta", "kac yil", "kac saat", "surede",
                            "kac lira", "kac tl", "kac cesit", "kac tur")

# Fertilizer as a PRODUCT, for the no-product-named half of the dose rule.
# Deliberately just this one stem, not the wider _PLANT_NUTRITION_STEMS: 'azot',
# 'fosfor', 'potasyum', 'npk' and 'kompost' are ELEMENTAL/generic terms, and a
# question like "Dekara kaç kilo azot gerekir?" asks about the element, not a
# branded product - converting an elemental amount into a product mass is out
# of scope (design spec, out-of-scope §10) and answering it with a card of 40
# products would be a guess wearing a helpful shape. See routing review
# (2026-08-25), finding 1.
_FERTILIZER_PRODUCT_STEM = ("gubre",)

# "Gübre" QUALIFIED BY A NUTRIENT is a fertilizer CLASS, not a product the user
# holds, and the comment above already draws that line for the bare element:
# "Dekara kaç kilo azot gerekir?" asks about the element. "Dekara kaç kilogram
# azotlu gübre uygulanmalıdır?" asks the same thing with the word "gübre" in it,
# and the stem test above could not tell them apart. Measured 2026-10-28: the
# eval case quant_mera_nitrogen_dose passed 8/8 on the 2026-08-13 baseline and
# failed after the dose route landed (2026-08-25), answered in 0 s by the dose
# card's fixed intro instead of the corpus - a regression nothing caught for two
# months, because the routing set held no nutrient-class question carrying
# "gübre", so run_routing's "product_dose: zero wrong entries" had zero eligible
# inputs.
#
# THE SUB-DECISION IS WHETHER "gübre" IS BARE. The qualifier alone is not enough:
# "Azotlu gübremi dekara ne kadar atmalıyım?" carries it too, and that is the
# user's OWN fertilizer - possessed, so a dose question. So the class reading
# needs the qualifier immediately before a BARE "gübre" (or its plural); a case
# or possessive ending on it (-yi, -mi, -den) marks a fertilizer in hand and
# keeps the dose card.
#
# THE ELEMENTS ARE THE PLANT NUTRIENTS, A CLOSED CHEMICAL SET, not phrasings
# collected from sentences: macro (N, P, K), secondary (S, Ca, Mg) and the
# micronutrients Turkish names fertilizers after. Closing only "azotlu" would
# have left "kükürtlü gübre" hijacked by the same rule. Kept LOCAL to this rule
# rather than added to _NUTRITION_STEMS, which feeds two other routes. The
# adjacency to "gübre" is the gate, so an element word elsewhere in a sentence
# cannot fire it.
_NUTRIENT_ELEMENTS = ("azot", "fosfor", "potasyum", "potas", "kukurt",
                      "kalsiyum", "magnezyum", "demir", "cinko", "bor",
                      "mangan", "bakir")
_FERTILIZER_CLASS = re.compile(
    r"(?<!\w)(?:" + "|".join(_NUTRIENT_ELEMENTS) + r")l[iu]\s+gubre(?:ler)?(?!\w)")


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
    # The exclusion is checked before the generic amount words count, so a
    # duration/price/count-of-kinds question loses the generic signal outright
    # rather than being decided by a later, harder-to-audit clause. It does
    # NOT gate _DOSE_PHRASES: "kaç litre", "dozu nedir" and the like already
    # name a quantity unambiguously and need no such guard.
    generic_amount = not _has_stem(folded, _NON_DOSE_AMOUNT_PHRASES) and (
        _has_stem(folded, _AMOUNT_PHRASES) or _has_word(folded, _AMOUNT_WORDS))
    if product_named and (_has_stem(folded, _DOSE_PHRASES) or generic_amount):
        return "product_dose"
    # A NAMED product never reaches this: clause A above already returned. So
    # the class carve-out only ever decides the no-product half, which is the
    # half that reads "gübre" as a product - see _FERTILIZER_CLASS.
    if not product_named and (
            _has_stem(folded, _DOSE_PHRASES)
            and _has_stem(folded, _FERTILIZER_PRODUCT_STEM)
            and not _FERTILIZER_CLASS.search(folded)):
        return "product_dose"

    if _has_stem(folded, _CROP_CHOICE_PHRASES):
        return "crop_choice"

    # A season calendar (PDF p5) - asked for by name, and only without a
    # nutrition word: "gübreleme takvimi" stays fert_plan below, because the
    # season card carries the stages and their water use and no fertilization
    # rows yet. Checked before fert_plan for that reason alone.
    if (not _has_stem(folded, _NUTRITION_STEMS)
            and (_has_stem(folded, _SEASON_PHRASES) or _SEASON_ASK.search(folded))):
        return "season"

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
