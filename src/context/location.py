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


# Personal endings Turkish speakers actually use when saying where they are:
# "Manisadayim", "Izmirdeyim", "Manisaliyim".
_PERSON = r"(?:y[iu]m|y[iu]z|s[iu]n|d[iu]r)?"

# Case suffix. MANDATORY - a bare name is handled separately below.
_SUFFIX = r"(?:[dt][ae]n?|[yn]?[aeiu]n?|l[iu])" + _PERSON

# Short provinces collide with ordinary words once folded: "mus"+a is "musa",
# "van"+a is "vana" (an irrigation valve - this is an agriculture assistant),
# "kars"+i is "karsi". A bare vowel suffix is not evidence for these; require an
# explicit locative/ablative or -li.
_SHORT = 4
_STRICT_SUFFIX = r"(?:[dt][ae]n?|l[iu])" + _PERSON

# A place noun immediately after a bare name makes it unambiguous. "Diyarbakir
# kosullarinda", "Antalya bolgesinde", "Manisa civarinda", "Izmir tarafinda" are how
# growers actually state where they are, and requiring a case suffix alone missed all
# of them. It must follow IMMEDIATELY: "Trabzon hurmasi bolgemizde yetisir mi" has
# the produce in between, so it still does not match.
_PLACE = r"(?:il|bolge|yore|civar|kosul|taraf|ilce|ovas|havzas)\w*"

_TRIM = " \t\n\r.,!?;:()\"'-…"


def _find(text: str) -> str | None:
    """Match a province, tolerating Turkish case suffixes but never firing inside
    a longer word and never firing on a produce name.

    Three forms are accepted. An apostrophe is an unambiguous proper-noun boundary
    in Turkish, so anything may follow it ("Manisa'dayim", "Kars'ta"). A known case
    suffix, optionally with a personal ending, carries the ordinary statements of
    location ("manisada", "Manisadayim", "Manisaliyim").

    A BARE name is deliberately NOT evidence of location. Turkish names produce by
    province - "Trabzon hurmasi", "Amasya elmasi", "Isparta gulu" - and in an
    agriculture assistant those are the SUBJECT of the question, not the user's
    address. A bare name is accepted only where it cannot be a modifier: when it is
    the whole message (the natural reply to "hangi ildesiniz?"), or when a place noun
    follows it immediately ("Diyarbakir kosullarinda", "Antalya bolgesinde").

    WHAT THIS DOES NOT CLOSE: the other branch of the regex still resolves ordinary
    Turkish words that happen to be a province plus a legal case suffix - "kilise"
    (church) -> Kilis, "hataya" (mistake) -> Hatay, "mersini" (myrtle, a PLANT) ->
    Mersin, "tokati" -> Tokat, "sivasi" -> Sivas. Same harm shape as the produce
    names, lower frequency, and pre-existing. Do not read this function as having
    solved the collision problem; it solved one branch of it.
    """
    folded = _normalize_tr(text)
    whole = folded.strip(_TRIM)
    for key in _ORDERED:
        k = re.escape(key)
        if re.search(rf"(?<!\w){k}'", folded):
            return _FOLDED[key]
        suffix = _STRICT_SUFFIX if len(key) <= _SHORT else _SUFFIX
        if re.search(rf"(?<!\w){k}{suffix}(?!\w)", folded):
            return _FOLDED[key]
        if whole == key:
            return _FOLDED[key]
        if re.search(rf"(?<!\w){k}\s+{_PLACE}(?!\w)", folded):
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
