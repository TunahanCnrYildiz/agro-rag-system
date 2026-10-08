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
# the produce in between, so it still does not match - that adjacency is load-bearing,
# and relaxing it brings the produce-name collision straight back.
#
# "il" IS ENUMERATED, the rest take \w*. An earlier version wrote `il\w*` and it
# swallowed `ile`, `ilgili`, `ilac`, `ilave`, `ilk` - two of the commonest words in
# the language plus everyday agriculture vocabulary. Worse, _ORDERED is longest-first,
# so a spurious hit on a long province name was RETURNED BEFORE a genuine apostrophe
# statement of a shorter one was ever tried: "Kahramanmaras ile ilgili degil,
# Van'dayim" answered Kahramanmaras. The other nouns have no common short prefixes,
# so \w* is safe for them - and it is what lets "ovalarinda" work as well as
# "ovasinda".
_PLACE = (r"(?:il|ili|ilin|ilinde|ilindeyim|ilinden|iline|ilimde|ilimdeyim|ilimizde"
          r"|ilce\w*|bolge\w*|yore\w*|civar\w*|kosul\w*|taraf\w*|ova\w*|havza\w*)")

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

    THE EARLIEST MATCH WINS, NOT THE LONGEST NAME. A sentence may name two
    provinces and only one of them is where the user is - "Van'dayım ama
    Ankara'dan aldım", "Konya'dayım ama Adana'dan fide aldım" - and returning on
    the first key that matched ANYWHERE handed those to whichever name was longer,
    which is unrelated to what the user said. Measured 2026-09-25, before this
    revision: both of those answered the second province, so a Konya grower's
    budget card was prefilled with Adana's yields and prices and nothing said so.
    So every key is tried and the candidate with the smallest match position is
    returned. It is the weakest defensible reading of a two-province sentence:
    people state where they are before they qualify it.

    THE `il` ENUMERATION BELOW CLOSED ONE INSTANCE OF THIS, not the class, and
    the comment on `_PLACE` says so in its own words: "Kahramanmaras ile ilgili
    degil, Van'dayim" answered Kahramanmaras because a spurious long-name hit was
    returned before a genuine short-name statement was tried. Narrowing `il\\w*`
    stopped that sentence. Position stops the shape.

    LONGEST-FIRST STILL DECIDES TIES, and that is what `_ORDERED` is for.
    Candidates arrive longest first and a later one must be STRICTLY earlier to
    win, so a short name sharing a position with a long one does not displace it.

    PORTED FROM src/context/country.py's `_find`, which was built as this
    function's twin and inherited this bug on the day it was written. The country
    side was fixed on 2026-09-25 and this side was left alone because that round's
    plan forbade touching a shipped module mid-round. The two now agree.

    WHAT THIS DOES NOT CLOSE, first: the other branch of the regex still resolves
    ordinary Turkish words that happen to be a province plus a legal case suffix -
    "kilise" (church) -> Kilis, "hataya" (mistake) -> Hatay, "mersini" (myrtle, a
    PLANT) -> Mersin, "tokati" -> Tokat, "sivasi" -> Sivas. Same harm shape as the
    produce names, lower frequency, and pre-existing. Do not read this function as
    having solved the collision problem; it solved the branches it names.

    WHAT THIS DOES NOT CLOSE, second - AND IT IS THE ONE A READER WILL REACH FOR:
    `_SUFFIX` admits the bare ablative, so "Ankara'dan aldım" alone still answers
    Ankara, and that sentence says where the SEED came from. The country twin
    refuses it (`_NOT_ABLATIVE` there). It is deliberately NOT fixed here, in this
    change: position and suffix are two decisions, this commit makes one of them,
    and narrowing a shipped surface in the same breath as reordering it is how the
    country guard earned seven review rounds. Measured and left open.
    """
    folded = _normalize_tr(text)
    whole = folded.strip(_TRIM)
    # Where `whole` actually begins, so a message opening with whitespace or a
    # quote mark still reports the position of its first letter.
    lead = len(folded) - len(folded.lstrip(_TRIM))
    best_start: int | None = None
    best_name: str | None = None
    for key in _ORDERED:
        k = re.escape(key)
        suffix = _STRICT_SUFFIX if len(key) <= _SHORT else _SUFFIX
        start = lead if whole == key else None
        for pattern in (rf"(?<!\w)(?P<name>{k})'",
                        rf"(?<!\w)(?P<name>{k}){suffix}(?!\w)",
                        rf"(?<!\w)(?P<name>{k})\s+{_PLACE}(?!\w)"):
            match = re.search(pattern, folded)
            # `name` is the province itself, so the three branches stay
            # comparable even though two of them match trailing text.
            if match is not None:
                found = match.start("name")
                if start is None or found < start:
                    start = found
        if start is not None and (best_start is None or start < best_start):
            best_start, best_name = start, _FOLDED[key]
        if best_start == 0:
            # Nothing can beat position 0, and any later key that ties it is
            # shorter and would lose the tie anyway. This keeps the common case -
            # the message opens with the province - from paying for all 81 keys.
            break
    return best_name


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
