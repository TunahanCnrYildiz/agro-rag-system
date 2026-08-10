"""Which province the user is in, re-derived from the conversation every call.

Nothing is stored server-side: no session, no database, no user record. That is
what lets context work land before membership does. When membership arrives, a
profile value becomes the default and this function stays exactly as it is.

Districts are out of scope. The table holds the 81 provinces; a user who writes
"Bafra" is not matched and the assistant asks for the province. Province
granularity is enough for both weather and fertilization timing, and a district
table can be added later without changing this interface.
"""
from __future__ import annotations

import re

from src.engine import _normalize_tr

PROVINCES: tuple[str, ...] = (
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Aksaray", "Amasya",
    "Ankara", "Antalya", "Ardahan", "Artvin", "Aydın", "Balıkesir", "Bartın",
    "Batman", "Bayburt", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur",
    "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Düzce",
    "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep",
    "Giresun", "Gümüşhane", "Hakkâri", "Hatay", "Iğdır", "Isparta", "İstanbul",
    "İzmir", "Kahramanmaraş", "Karabük", "Karaman", "Kars", "Kastamonu",
    "Kayseri", "Kırıkkale", "Kırklareli", "Kırşehir", "Kilis", "Kocaeli",
    "Konya", "Kütahya", "Malatya", "Manisa", "Mardin", "Mersin", "Muğla",
    "Muş", "Nevşehir", "Niğde", "Ordu", "Osmaniye", "Rize", "Sakarya",
    "Samsun", "Siirt", "Sinop", "Sivas", "Şanlıurfa", "Şırnak", "Tekirdağ",
    "Tokat", "Trabzon", "Tunceli", "Uşak", "Van", "Yalova", "Yozgat",
    "Zonguldak",
)

# Folded name -> canonical name. Built once; the fold is the same one the crop
# lexicon and the router use, so "manisada", "Manisa'dayım" and "MANİSA" all
# reduce to the same key.
_FOLDED = {_normalize_tr(p): p for p in PROVINCES}

# Longest first, so "Kahramanmaraş" is tried before "Maraş"-like substrings and
# multi-word names are not shadowed by a shorter sibling.
_ORDERED = sorted(_FOLDED, key=len, reverse=True)


# Case suffixes that may follow a bare province name. ENUMERATED on purpose:
# allowing "any letters" makes "Van" match inside "vantilator". Text reaching
# here is already ASCII-folded, so the suffixes appear folded too.
_SUFFIX = r"(?:[dt][ae]n?|[yn]?[aeiu]n?|l[iu])?"

# Provinces this short collide with ordinary words once folded: "kars"+i is
# "karsi" (karsi), "mus"+a is "musa". For these a bare vowel suffix is not
# evidence enough - require an apostrophe or an explicit locative/ablative.
_SHORT = 4
_STRICT_SUFFIX = r"(?:[dt][ae]n?|[yn]?[ae])"


def _find(text: str) -> str | None:
    """Match a province, tolerating Turkish case suffixes but never firing
    inside a longer word.

    Two forms are accepted. An apostrophe is an unambiguous proper-noun
    boundary in Turkish, so anything may follow it ("Manisa'dayim",
    "Kars'ta"). Without one, only a known case suffix may follow and the word
    must then END - which is what keeps "Van" out of "vantilator".
    """
    folded = _normalize_tr(text)
    for key in _ORDERED:
        k = re.escape(key)
        if re.search(rf"(?<!\w){k}'", folded):
            return _FOLDED[key]
        suffix = _STRICT_SUFFIX if len(key) <= _SHORT else _SUFFIX
        if re.search(rf"(?<!\w){k}{suffix}(?!\w)", folded):
            return _FOLDED[key]
    return None


def extract_province(message: str, history: list[dict] | None = None) -> str | None:
    """Most recent province mentioned: the current message wins, then history
    read backwards. Returns None when nobody has said where they are."""
    found = _find(message)
    if found:
        return found
    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        found = _find(turn.get("content", ""))
        if found:
            return found
    return None
