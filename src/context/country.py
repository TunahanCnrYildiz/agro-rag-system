"""Which country the user is in, re-derived from the conversation every call.

The twin of location.py, and deliberately a separate module: the two tables
have different shapes and different failure modes, and merging them would make
both harder to read. Everything location.py says about storing nothing
server-side applies here unchanged.

Returns the FAO AREA CODE rather than a name. That is what indexes
data/world_norms.json, and FAOSTAT's labels are not what anyone types -
`Iran (Islamic Republic of)`, `China, mainland`, `Bolivia (Plurinational
State of)`.

THE COLLISION THIS MODULE EXISTS TO SURVIVE. Turkish country names sit inside
crop names. Measured against our 246 crop labels: `Mısır` IS the label for
maize, `Fas` sits inside `Fasulye`, `Çin` inside `İçin` - one of the commonest
words in the language - `Hindistan` inside `Hindistan Cevizi`, and `Malta`
inside `Malta Eriği`. A substring match answers Morocco to "fasulye ektim".
location.py already solved this shape of problem for provinces and its guards
are reused here rather than reinvented: a name resolves only with a case
suffix, as the whole message, or before a place noun, and a short name needs
the strict suffix.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from src.config import DATA_DIR
from src.engine import _normalize_tr

_TABLE = DATA_DIR / "country_aliases.json"


def _load() -> dict[str, tuple[int, bool]]:
    """Folded alias -> (FAO area code, spelled in Turkish), or an empty mapping.
    Never raises.

    A broken table costs the country line and nothing else, the way norms._load
    treats a broken norms file: this module is consulted while answering, so it
    must degrade to "we do not know where you are" rather than to a traceback.

    Entries are skipped one at a time rather than dropping the table whole - an
    alias list that is not a list of strings says nothing about the other 198
    countries, and losing them all would be a far larger regression than losing
    one.

    WHICH LIST A NAME CAME FROM IS KEPT, and it is not bookkeeping. Turkish case
    endings are only legal on a Turkish spelling, and running them over the
    English ones costs real answers: `Italy` plus the perfectly legal ending
    `-an` matches "Italyan cimi" - Italian ryegrass, one of our 246 crop labels -
    and placed the grower in Italy. See _matchers. `tr` is read first so a name
    that appears in BOTH lists (`Türkiye` is in both) keeps the Turkish branches.
    """
    try:
        raw = json.loads(Path(_TABLE).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        folded: dict[str, tuple[int, bool]] = {}
        for code, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            try:
                area = int(code)
            except (TypeError, ValueError):
                continue
            for lang in ("tr", "en"):
                for name in entry.get(lang) or ():
                    if not isinstance(name, str) or not name.strip():
                        continue
                    key = _normalize_tr(name.strip())
                    turkish = lang == "tr" or folded.get(key, (0, False))[1]
                    folded[key] = (area, turkish)
        return folded
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}


# Folded alias -> (FAO area code, spelled in Turkish). Both languages land in
# ONE table on purpose: a message may mix them ("I am in Türkiye") and the
# branches, not the caller, decide what each spelling may carry. Uniqueness
# under _normalize_tr was measured when the table was built - no two countries
# share a folded name - so a later language cannot silently overwrite an
# earlier one without that check failing.
_FOLDED = _load()

# Longest first. This is load-bearing here in a way it only nearly was for
# provinces: the table has 34 substring pairs (`Mali` in `Somali`, `Oman` in
# `Romanya`, `Dominik` in `Dominika`, `Nijer` in `Nijerya`), and the lenient
# suffix branch below would read the trailing letter of the longer name as a
# case ending. Trying the longer key first is what makes "Nijerya'dayım"
# Nigeria rather than Niger.
_ORDERED = sorted(_FOLDED, key=len, reverse=True)


# --------------------------------------------------------------------------
# Copied VERBATIM from src/context/location.py. Not imported: the two tables
# will drift apart - this one is already gaining alias languages, and any
# tightening made for 199 country names would silently change how the 81
# provinces are matched, which is the coupling that makes shared regex
# constants dangerous. The comments come with them because the collisions they
# describe are the same collisions here.
# --------------------------------------------------------------------------

# Personal endings Turkish speakers actually use when saying where they are:
# "Manisadayim", "Izmirdeyim", "Manisaliyim".
_PERSON = r"(?:y[iu]m|y[iu]z|s[iu]n|d[iu]r)?"

# Case suffix. MANDATORY - a bare name is handled separately below.
_SUFFIX = r"(?:[dt][ae]n?|[yn]?[aeiu]n?|l[iu])" + _PERSON

# Short names collide with ordinary words once folded. For provinces it was
# "van"+a -> "vana"; for countries it is `fas` inside "burkina fasoda" and `uk`
# inside "arnavutlukta" - both verified to be blocked by this rule plus the
# lookbehind. A bare vowel suffix is not evidence for these; require an
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
# so a spurious hit on a long name was RETURNED BEFORE a genuine apostrophe
# statement of a shorter one was ever tried: "Kahramanmaras ile ilgili degil,
# Van'dayim" answered Kahramanmaras. The other nouns have no common short prefixes,
# so \w* is safe for them - and it is what lets "ovalarinda" work as well as
# "ovasinda".
_PLACE = (r"(?:il|ili|ilin|ilinde|ilindeyim|ilinden|iline|ilimde|ilimdeyim|ilimizde"
          r"|ilce\w*|bolge\w*|yore\w*|civar\w*|kosul\w*|taraf\w*|ova\w*|havza\w*)")

_TRIM = " \t\n\r.,!?;:()\"'-…"

# --------------------------------------------------------------------------
# End of the verbatim copy. Everything below is specific to countries.
# --------------------------------------------------------------------------

# English states location with a preposition, not a suffix: "I am in France",
# "from Kenya". The Turkish branches never fire on these because an English
# name takes no case ending.
_EN_PLACE = r"(?:in|from|at)\s+"

# HAZARD: a bare preposition is NOT evidence. `from turkey farms` satisfies
# `(?:in|from|at)\s+turkey(?!\w)`, because a space is not a word character, and
# `turkey manure`, `turkey litter` and `turkey farms` are ordinary phrases in an
# agriculture assistant. `Turkey` is not alone: `from niger seed` (Guizotia
# abyssinica, a real oilseed) and `chile peppers` are the same shape, and
# "we bought seed from India" is not a statement of where the user is either.
#
# The rule: an English name places the user only when it CLOSES its noun phrase.
# "in France", "in France, growing wheat", "in France and I grow wheat" all end
# the phrase at the country; a compound noun continues it with a second noun,
# and that second noun is what this refuses. It is the English counterpart of
# the Turkish rule one screen up - there the evidence is the case ending on the
# name, here it is that nothing is glued to the end of it - and it costs nothing
# for the other 198 countries, which is why it is applied to all of them rather
# than to a hand-kept list of ambiguous names.
#
# ENUMERATED, not `\w*`, for the reason _PLACE carries above: these are closed-
# class English words that cannot head a compound noun, so admitting them cannot
# re-open the collision. Anything open-class after the name ends the match, and
# `\s*$` alone is what makes "I am in Turkey" work.
_EN_TAIL = (r"(?:and|but|or|so|then|now|too|also|where|which|while|when|because"
            r"|since|if|i|we|my|our|you|your|they|it|this|that|these|those|the"
            r"|is|are|was|were|do|does|did|can|could|will|would|have|has|had"
            r"|right|currently)")
_EN_BOUNDARY = rf"(?:\s*$|\s*[.,;:!?)\]]|\s+{_EN_TAIL}(?!\w))"

# HAZARD: FAOSTAT has no area for the TRNC, so the table cannot hold one, and
# `Kıbrıs` fires inside `Kuzey Kıbrıs` under every boundary rule there is - the
# lookbehind sees a space. Left alone, a Turkish Cypriot grower - a likely user
# of this product - is handed the Republic of Cyprus's yields with nothing said.
#
# So this is an explicit REFUSAL rather than a match: naming a place we have no
# figures for resolves to nothing, and the assistant asks. The alternative
# considered was deleting the `Kıbrıs` alias, which would have cost the Republic
# its name for everyone; and the narrower "suppress only Cyprus for this text",
# which loses the point - the user HAS said where they are, and quietly falling
# through to some other country in the same sentence, or to an older turn, is
# the same silent misplacement in a different costume. See extract_country,
# where this also stops the walk back through history.
#
# Matched on the FOLDED text: "Kuzey Kıbrıs" -> "kuzey kibris", "KKTC" -> "kktc".
_NO_AREA = re.compile(
    r"(?<!\w)(?:kuzey\s+kibris|k\.?k\.?t\.?c\.?|trnc|northern\s+cyprus)(?!\w)"
)


@lru_cache(maxsize=1)
def _matchers() -> tuple[tuple[int, str, tuple[re.Pattern[str], ...]], ...]:
    """The four Turkish forms and the English one, PRE-COMPILED, longest key
    first. Built once on first use, the way norms._load is.

    location.py builds its patterns inside the loop, which is fine at 81
    provinces: ~320 distinct patterns fit in `re`'s internal cache, so the
    second call is free. At 199 countries and five branches it is ~1000, the
    cache (512 entries) thrashes, and EVERY pattern is recompiled on EVERY
    call - measured at 272 ms per call against 1.4 ms for the province twin.
    This module runs on every answer, so that is not a copy worth keeping
    faithful. The order of the tuple is the order location.py tries the
    branches in, and both orders are load-bearing: longest key first for the
    34 substring pairs, apostrophe before the lenient suffix.

    A name spelled in ENGLISH gets neither the Turkish case suffix nor the
    Turkish place noun. Nobody writes "Germanyde" or "France bolgesinde" - the
    Turkish table already holds "Almanya" and "Fransa" for that - so those two
    branches can only fire by accident on an English spelling, and one of them
    did: `Italy` + `-an` -> "Italyan cimi", Italian ryegrass. The apostrophe
    ("France'dayim" is how a Turkish speaker writes a foreign name), the whole
    message ("France") and the English preposition stay for every spelling.
    """
    built = []
    for key in _ORDERED:
        k = re.escape(key)
        code, turkish = _FOLDED[key]
        suffix = _STRICT_SUFFIX if len(key) <= _SHORT else _SUFFIX
        # An empty negative lookahead always fails, so a branch switched off
        # this way keeps the tuple one shape and _find free of language tests.
        never = r"(?!)"
        built.append((code, key, (
            re.compile(rf"(?<!\w){k}'"),
            re.compile(rf"(?<!\w){k}{suffix}(?!\w)" if turkish else never),
            re.compile(rf"(?<!\w){k}\s+{_PLACE}(?!\w)" if turkish else never),
            re.compile(rf"(?<!\w){_EN_PLACE}{k}{_EN_BOUNDARY}"),
        )))
    return tuple(built)


def _refuses(text: str) -> bool:
    """True when the text names a place FAOSTAT has no area for.

    Separate from _find because it is not a failure to match - it is a decision
    not to answer, and the caller must stop rather than look elsewhere.
    """
    return bool(_NO_AREA.search(_normalize_tr(text)))


def _find(text: str) -> int | None:
    """Match a country, tolerating Turkish case suffixes and English
    prepositions, but never firing inside a longer word and never firing on a
    crop name.

    Five forms are accepted, the first four exactly as location.py accepts them.
    An apostrophe is an unambiguous proper-noun boundary in Turkish, so anything
    may follow it ("Mısır'dayım", "Fas'ta"). A known case suffix, optionally with
    a personal ending, carries the ordinary statements ("fransada",
    "Fransadayim"). A BARE name is accepted only where it cannot be a modifier:
    as the whole message (the natural reply to "hangi ulkedesiniz?"), or with a
    place noun immediately after it. The fifth is English, which has no case
    ending and states location with a preposition instead.

    WHAT THIS DOES NOT CLOSE, inherited unchanged from location.py: the lenient
    suffix branch still resolves ordinary Turkish words that happen to be a
    country plus a legal case ending. Same harm shape as the crop names, lower
    frequency. Do not read this function as having solved the collision problem;
    it solved the branches it names.
    """
    if _refuses(text):
        return None
    folded = _normalize_tr(text)
    whole = folded.strip(_TRIM)
    for code, key, (apostrophe, suffixed, before_place, english) in _matchers():
        if apostrophe.search(folded):
            return code
        if suffixed.search(folded):
            return code
        if whole == key:
            return code
        if before_place.search(folded):
            return code
        if english.search(folded):
            return code
    return None


def extract_country(message: str, history: list[dict] | None = None) -> int | None:
    """Most recent country mentioned, as an FAO area code: the current message
    wins, then history read backwards. Returns None when nobody has said where
    they are - and also when the most recent thing they said was a place we
    have no figures for.

    ASSISTANT TURNS ARE NEVER EVIDENCE, exactly as in location.py: the
    assistant names countries constantly while answering ("Fransa'da bugday
    verimi yuksektir"), and reading its own words back as the user's location
    would place growers wherever the last example happened to be set.
    """
    if _refuses(message):
        return None
    found = _find(message)
    if found:
        return found
    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        content = turn.get("content", "")
        # The walk stops here, it does not skip past: this turn IS the most
        # recent statement of location, and continuing would answer with a
        # country the user has since moved on from.
        if _refuses(content):
            return None
        found = _find(content)
        if found:
            return found
    return None
