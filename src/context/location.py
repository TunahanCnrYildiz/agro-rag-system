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

# THE ABLATIVE IS NOT A LOCATION. `_SUFFIX` spells it as well as the locative -
# `[dt][ae]n?`, where the optional `n` turns "-da" (in) into "-dan" (from) - and
# the apostrophe branch accepted anything after the apostrophe, so "Ankara'dan
# aldım" ("I bought from Ankara") placed the grower in Ankara. That sentence
# says where the SEED came from.
#
# COPIED VERBATIM FROM src/context/country.py, where it is `_NOT_ABLATIVE` and
# has carried the same shape since ee43c18. Read it there for the reasoning that
# earned each piece: why the buffer `n` is in it (22 country aliases walked
# through a version that spelled only `dan|den|tan|ten`), why `[yn]?` is spelled
# the way `_SUFFIX` spells its own buffer, and why a bare ablative is refused
# while one carrying a personal ending is kept - "Ankara'danım" ("I am from
# Ankara") states where the user belongs the way "Ankaralıyım" does, and the
# trailing `(?!\w)` is what tells them apart: the bare ablative ENDS the word,
# "Ankara'danım" runs on into `ım`.
#
# SHIPPED IN THE SAME COMMIT AS EARLIEST-WINS, because apart it is not a fix.
# Earliest-wins alone answers the stated province when the user states it first
# and the SUPPLIER, every time, when the user states the purchase first:
# measured over all 6 480 ordered pairs of the 81 provinces, "{sup}'dan fide
# aldım, {loc}'dayım" went 3 240/6 480 right (a coin flip on name length) to
# 0/6 480. The twin shipped both halves together for exactly this reason -
# `ee43c18` is titled after the ablative and contains both - and the round
# ledger records the fixer's note that narrowing the suffix alone "would have
# fixed nothing while looking like a fix". The reverse half alone is the same
# trade: net zero, and wrong in a predictable direction instead of half the time.
#
# COST, named rather than implied: an ablative that really does state a location
# is now refused. Measured over the 81 provinces, "{p}'dan yazıyorum" and
# "{p}'den geldim" went 81/81 placed to 0/81. The province case is weaker than
# the country one - "İzmir'den geldim" is more often said near İzmir than
# "Hollanda'dan yazıyorum" is said near the Netherlands - so this is a real loss,
# and it buys off a systematic one. Refusing a location costs a question:
# `extract_province` returns None, `src/engine.py` finds no national row in
# data/crop_norms.json for a Turkish user, and the assistant asks which province.
# Accepting a supplier prefills the budget card with the wrong province's yields
# and prices and says nothing.
#
# STALE SENTENCE IN THE TWIN, left alone on purpose: country.py's comment above
# its own `_NOT_ABLATIVE` says this module "diverges … deliberately" and that
# "location.py's twin of this line is left exactly as it is". That stopped being
# true here. country.py is out of scope for this change and is not touched, so
# the correction lives on this side.
_NOT_ABLATIVE = r"(?![yn]?[dt][ae]n(?!\w))"

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

    TWO RULES DECIDE A TWO-PROVINCE SENTENCE, and they were built together
    because apart neither one is a fix. THE EARLIEST MATCH WINS, NOT THE LONGEST
    NAME, and AN ABLATIVE IS NOT A LOCATION (`_NOT_ABLATIVE` above).

    WHAT THE OLD RULE ACTUALLY WAS, measured rather than named: `_find` returned
    the first key in `_ORDERED` that matched anywhere, and `_ORDERED` is length
    descending with ties broken by the order of `PROVINCES`. Over every ordered
    pair of the 81 provinces in four frames, 25 920 two-province sentences, the
    old code answered the strictly LONGER name 21 760 times (84 %), the strictly
    shorter one 0 times, a third province 0 times, and in the remaining 4 160 the
    two names fold to the SAME length - every one of those decided by table
    order. So: length in 84 % of them, table order in the rest, and what the user
    said in neither.

    THE EXAMPLE THIS BUG IS USUALLY TOLD WITH IS ONE OF THE 4 160.
    "Konya'dayım ama Adana'dan fide aldım" answered Adana - correctly reported,
    wrongly explained: `konya` and `adana` both fold to five characters, so what
    chose Adana is `PROVINCES[0]`, not "whichever name was longer". The length
    reading is right about the class and wrong about that sentence.

    SO EVERY KEY IS TRIED and the candidate with the smallest match position is
    returned. It is the weakest defensible reading of a two-province sentence:
    people state where they are before they qualify it.

    AND POSITION ALONE WOULD HAVE BEEN HALF A FIX. Earliest-wins answers the
    stated province when the user states it first, and the SUPPLIER every time
    when the user states the purchase first - "Adana'dan fide aldım, Konya'dayım"
    is as ordinary as the other order. Measured across the same four frames, two
    with the location first and two with the origin first: old 12 960 of 25 920
    right (a coin flip), position alone 12 960 of 25 920, position with
    `_NOT_ABLATIVE` 25 920 of 25 920. The net of position alone is ZERO, which is
    why the two ship together and why `country.py`'s `ee43c18` shipped its pair
    together too.

    IT ALSO OPENS THE WORLD LAYER WHERE IT WAS SHUT. `src/engine.py` reads
    `_country_lines` only when this function comes back empty, so a Turkish
    province name in a sentence about a FOREIGN grower's supplier used to swallow
    the whole decision: "Hollanda'dayım ama Ankara'dan fide aldım" answered Ankara
    and the FAOSTAT figures were never reached - and earliest-wins could not help,
    because Ankara is the only province in that sentence. Measured over the 81
    provinces against five countries in both word orders: 81/81 placed in a
    Turkish province before, 81/81 reaching the country's figures now.

    THE `il` ENUMERATION BELOW CLOSED ONE INSTANCE OF THIS, not the class, and
    the comment on `_PLACE` says so in its own words: "Kahramanmaras ile ilgili
    degil, Van'dayim" answered Kahramanmaras because a spurious long-name hit was
    returned before a genuine short-name statement was tried. Narrowing `il\\w*`
    stopped that sentence. Position stops the shape.

    THE TIE-BREAK IS DEAD HERE AND IS KEPT FOR SYMMETRY WITH THE TWIN. Candidates
    arrive longest first and a later one must be STRICTLY earlier to win. In this
    table that comparison can never fire: two keys can only match at the same
    offset if one is a prefix of the other, and NO folded province name is a
    prefix of another (measured: 0; `mus` sits inside `gumushane` but not at its
    start). Relaxing it to `<=` leaves the suite green and changes 0 of 53 140
    answers. In `country.py` it is live - `Dominik`/`Dominika` and
    `Nijer`/`Nijerya` genuinely tie - so the line stays, described for what it is.

    THE PER-BRANCH MINIMUM IS THE LIVE ONE. A key can match more than one branch
    and the branches report different positions, so `found < start` keeps the
    earliest of them: "Konya ovasındayım, Adana'ya göre geç oluyor, Konya'da kar
    var" is Konya by the place-noun branch at offset 0, and taking the maximum
    instead answers Adana. That mutation changes 6 480 answers in the sweep, so
    this is the comparison a test has to pin.

    PORTED FROM src/context/country.py's `_find`, which was built as this
    function's twin and inherited both bugs on the day it was written. The country
    side was fixed on 2026-09-25 and this side was left alone because that round's
    plan forbade touching a shipped module mid-round. ON POSITION AND ON THE
    ABLATIVE THE TWO NOW AGREE; two differences remain and both are deliberate.
    The twin tests capitalisation for the ten country names that are also ordinary
    English nouns (`_admits`), which has no province equivalent. And its suffix
    branch ends `(?!['\\w])` where this one ends `(?!\\w)`, because there the
    shorter of a prefix pair would eat a longer name's vowel as a case suffix and
    stop before the `'dan` this guard refuses. Measured here: porting it changes
    answers only for strings built as province + vowel + "'dan" - "Adıyamana'dan"
    - which no prefix pair in this table can produce and nobody writes.

    WHAT THIS DOES NOT CLOSE, first: the other branch of the regex still resolves
    ordinary Turkish words that happen to be a province plus a legal case suffix -
    "kilise" (church) -> Kilis, "hataya" (mistake) -> Hatay, "mersini" (myrtle, a
    PLANT) -> Mersin, "tokati" -> Tokat, "sivasi" -> Sivas. Same harm shape as the
    produce names, lower frequency, and pre-existing. Do not read this function as
    having solved the collision problem; it solved the branches it names.

    WHAT THIS DOES NOT CLOSE, second: a province name in SINGLE quotes now beats
    a genuine statement after it. "'Van' Kahramanmaraş'tayım" -> Van, measured
    0/6 480 over the ordered pairs where it used to be 3 240/6 480. The apostrophe
    branch cannot tell a closing quote from a Turkish case-suffix apostrophe, and
    earliest-wins amplifies that. DOUBLE quotes are unaffected (6 480/6 480), the
    twin has the same branch, and closing it here alone would be the divergence
    this change exists to remove - so it is sized and left open, not deferred with
    a reason.

    COST IN TIME, both halves: a match anywhere but offset 0 no longer returns
    early, so it pays for all 81 keys. Best of 5 x 400 calls, old against new:
    two provinces 0,099 -> 0,219 ms, no match 0,191 -> 0,185, opens with the
    province 0,164 -> 0,171, province at the end 0,295 -> 0,298, long no-match
    0,579 -> 0,578. One call per answer, against generation at ~65 tok/s.
    """
    folded = _normalize_tr(text)
    whole = folded.strip(_TRIM)
    best_start: int | None = None
    best_name: str | None = None
    for key in _ORDERED:
        k = re.escape(key)
        suffix = _STRICT_SUFFIX if len(key) <= _SHORT else _SUFFIX
        # 0, not the offset of the first letter. `whole == key` means the
        # trimmed message IS this one province name, so no second key can be
        # present to compare against - measured, 0 of the 81 bare messages have
        # a second candidate - and the only thing this number can still do is
        # decide whether the `break` below fires. An earlier version computed
        # the real offset and commented that a message opening with whitespace
        # or a quote mark "still reports the position of its first letter";
        # setting it to 0 and to 10**6 both leave the suite green and change no
        # answer, so that comment described a consumer that does not exist here.
        # The twin has one - country.py passes its `lead` to `_admits`, which
        # indexes into the unfolded text for the capitalisation test on the ten
        # English-noun country names. This module has no `_admits`.
        start = 0 if whole == key else None
        for pattern in (rf"(?<!\w)(?P<name>{k})'{_NOT_ABLATIVE}",
                        rf"(?<!\w)(?P<name>{k}){_NOT_ABLATIVE}{suffix}(?!\w)",
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
            # PURELY THE PERFORMANCE OPTIMISATION IT LOOKS LIKE: nothing can beat
            # offset 0, and no later key can even tie it, since a tie needs a
            # prefix pair and this table has none. Disabling it leaves the suite
            # green and changes 0 of 53 140 answers - it only keeps the common
            # case, a message that opens with the province, from paying for all
            # 81 keys.
            break
    return best_name


def extract_province(message: str, history: list[dict] | None = None) -> str | None:
    """Most recent province mentioned: the current message wins, then history
    read backwards. Returns None when nobody has said where they are.

    THE MOST RECENT PLACE WINS, NOT THE MOST RECENT PROVINCE (decided by the
    user 2026-10-30). A turn that names a country outside Türkiye, and no
    province, ends the search with None, so the caller's country fallback
    answers. Without this a profile saying "Konya'dayım" - the mobile client
    sends it as the OLDEST turn - beat "Fransa'dayım" typed a moment ago,
    because provinces were searched on their own and a province always won.
    The profile still holds whenever the conversation names no place.

    Within one turn a province still wins: "Konya'dayım ama Fransa'ya da ihracat
    yapıyorum" is in Konya. Assistant turns are never evidence, as before.
    """
    texts = [message] + [turn.get("content", "") for turn in reversed(history or [])
                         if turn.get("role") == "user"]
    for text in texts:
        found = _find(text)
        if found:
            return found
        if _abroad(text):
            return None
    return None


def _abroad(text: str) -> bool:
    """Whether this one turn places the farmer outside Türkiye - by the country
    matcher's own rules, guards included, so "Mısır ekmeli miyim?" is maize and
    "Türkiye'de" is home. A place it declines to answer for ("Kaliforniya'dayım")
    is abroad too: the province is no longer where they are.

    Deferred import: src/context/country.py imports from src/engine.py, which
    imports this module's callers at answer time, not at load time."""
    # NEVER RAISES. A broken country layer costs the country decision, never
    # the province: on failure this says "not abroad" and the province search
    # behaves exactly as it did before countries could outrank it.
    try:
        from src import norms
        from src.context import country as country_ctx

        folded = _normalize_tr(text or "")
        if not folded:
            return False
        if country_ctx._refuses(folded):
            return True
        # extract_country on this one turn alone: the same matcher and the same
        # guards the answer uses, maize-is-not-Egypt included.
        code = country_ctx.extract_country(text, [])
        return code is not None and code != norms.TURKIYE_AREA
    except Exception:  # noqa: BLE001
        return False
