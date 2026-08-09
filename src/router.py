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
from typing import Literal

from src.engine import _normalize_tr

Route = Literal["plant_info", "nutrition", "fert_plan", "budget",
                "crop_choice", "offscope"]

ROUTES: tuple[str, ...] = ("plant_info", "nutrition", "fert_plan", "budget",
                           "crop_choice", "offscope")

# Stems match with a LEFT boundary and may run into their own suffixes, the same
# convention the crop lexicon and the product backstop use.
_BUDGET_STEMS = ("maliyet", "masraf", "gelir", "gider", "butce", "kazanc",
                 "ciro", "zarar", "yatirim", "geri donus")
# Whole-word only: folding 'kâr' gives 'kar', which is a left prefix of karar,
# karnabahar, karisim, kardes. A stem match here would be a silent false positive.
_BUDGET_WORDS = ("kar", "karli", "karlilik", "karlimi")
_BUDGET_PHRASES = ("kac para", "ne kadar tutar", "ne kadar kazan")

_NUTRITION_STEMS = ("gubre", "besle", "besleme", "azot", "fosfor", "potasyum",
                    "npk", "kompost", "besin")
_TIME_STEMS = ("ne zaman", "hangi ay", "hangi donem", "takvim", "program",
               "donemde", "bu ay", "zamanla")

_CROP_CHOICE_PHRASES = ("ne eksem", "ne ekmek", "ne ekmeli", "ne ekeyim",
                        "hangi urun", "ne yetistir", "hangi meyve",
                        "mi ekmeliyim", "hangi bitkiyi")

_OFFSCOPE_STEMS = ("inek", "buzagi", "koyun", "tavuk", "hayvancilik",
                   "balik yetistir", "su urun", "traktor", "bicerdover",
                   "banka", "kredi", "dolar", "borsa", "film", "takim")
# Whole-word only: folded 'mac' is a left prefix of 'macar', and 'Macar fiği' is
# a real forage legume. Same trap as 'kar'/'karar' above.
_OFFSCOPE_WORDS = ("mac", "maci", "maclar")


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

    if _has_stem(folded, _CROP_CHOICE_PHRASES):
        return "crop_choice"

    if _has_stem(folded, _NUTRITION_STEMS) and _has_stem(folded, _TIME_STEMS):
        return "fert_plan"

    if _has_stem(folded, _OFFSCOPE_STEMS) or _has_word(folded, _OFFSCOPE_WORDS):
        return "offscope"

    return None
