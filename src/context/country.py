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
        raw = json.loads(_TABLE.read_text(encoding="utf-8"))
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

# HAZARD: `from` marks where GOODS came from, not where the user is. A bare
# `from` used to be admitted here and it placed growers at their supplier -
# measured before this was fixed: "we bought seed from India" -> India, "I buy
# eggs from Turkey." -> Türkiye, "we import chicks from Turkey, mostly" ->
# Türkiye. The ambiguous-name rule below is no defence: it refuses `from turkey
# farms` only because the bird is lowercase there, and `from India`, `from
# Germany`, `from Kenya` are not ambiguous names at all - nothing in this module
# but this paragraph stops them. Seed, chicks, litter and fertiliser are bought
# across borders constantly in this assistant's traffic, so this is the common
# case, not the corner.
#
# `from` survives ONLY where it predicates the USER instead of a purchase:
# "I am from Kenya", "we're from Brazil". That is an enumerated copula, not a
# bare preposition, so no sentence about buying can reach it. It is also the
# English twin of `-lı` in _SUFFIX - "İzmirliyim" is already accepted as a
# statement of location by the same reasoning.
#
# REJECTED: demoting `from` so it fires only when nothing else in the message
# resolves. "we bought seed from India" has no other country in it, so it would
# still answer India - the harm itself, left standing.
#
# GIVEN UP: "I came from Kenya", "the seed came from Kenya and I am there now".
# The first is a travel statement that does not say where the user is now; the
# second does, and is lost. Asking costs a turn, misplacing costs every figure
# in the answer.
#
# ONLY THE `from` SHAPE IS HANDLED HERE. The supplier sentence stated with `in`
# is untouched and pre-existing: "our seed is grown in Turkey." resolves to
# Türkiye and "this fertiliser is made in Germany" to Germany, because `in`
# genuinely marks a location and nothing short of parsing says whose. Do not
# read the paragraphs above as closing the supplier class; they close the
# preposition that could never mean anything else.
_EN_ORIGIN = r"(?:i\s+am|i'm|we\s+are|we're)\s+from"

# HAZARD, and the reason the origin copula is its own branch rather than one
# more alternative beside `in`: a sentence can say both where the user is FROM
# and where the user farms, and only the second should carry the figures. The
# copula sits earlier in such a sentence than the `in`-clause, so earliest-
# match-wins (see _find) handed the answer to the origin - measured, "I'm from
# Turkey but I farm in Germany" -> Türkiye and "I am from Kenya but I live in
# France" -> Kenya, both of which answered the farm before `from` was admitted
# to this module at all.
#
# So origin is RANKED BELOW `in`/`at`: it is read only when no `in`/`at` branch
# matched ANYWHERE in the text. "I am from Kenya" standing alone keeps working,
# because there is nothing there to outrank it.
#
# REJECTED: one pattern for both, preferring the LATER match. It fixes these two
# sentences and breaks every sentence earliest-wins exists for - "I am in Turkey
# but I import seed from France" goes straight back to France.
_EN_IN = r"(?:in|at)\s+"

# HAZARD, the same rule in Turkish. `_SUFFIX` spells the ablative as well as
# the locative - `[dt][ae]n?`, where the optional `n` turns "-da" (in) into
# "-dan" (from) - and the apostrophe branch accepts ANYTHING after the
# apostrophe, so "Hollanda'dan tohum aldım" resolved to the Netherlands by
# exactly the shape `from` does in English.
#
# THIS MODULE DIVERGES FROM location.py HERE, deliberately. For a PROVINCE the
# ablative is fair evidence: "İzmir'den geldim" is usually said by someone in
# İzmir's orbit, and domestic sentences are rarely about importing. For a
# COUNTRY the ablative is overwhelmingly a purchase or an import. location.py's
# twin of this line is left exactly as it is.
#
# A BARE ablative is refused; an ablative carrying a personal ending is kept.
# "Hollanda'danım" ("I am from the Netherlands") states where the user belongs
# the way "Hollandalıyım" does. What tells them apart is the lookahead's own
# trailing `(?!\w)`: the bare ablative ENDS the word, while "Hollanda'danım"
# continues into `ım`, so the lookahead fails to match and lets it through.
#
# THE BUFFER `n` IS PART OF THE ABLATIVE, and omitting it let 22 aliases walk
# straight through this guard. Turkish inserts a buffer consonant between a
# 3rd-person possessive and a case ending, so the ablative of `Dominik
# Cumhuriyeti` is `Cumhuriyeti'nden`, never `Cumhuriyeti'den`. The first version
# of this lookahead spelled exactly four strings - `dan`, `den`, `tan`, `ten` -
# so it met the buffer `n` and failed, and the whole `… Adaları`,
# `… Cumhuriyeti`, `Rusya Federasyonu`, `Birleşik Arap Emirlikleri`, `Amerika
# Birleşik Devletleri`, `Fransız Polinezyası`, `Fildişi Sahili`, `Çin Anakarası`
# family placed the grower at their supplier: measured, "Dominik
# Cumhuriyeti'nden tohum aldım" -> 56, "Rusya Federasyonu'ndan tohum aldım" ->
# 185, "Solomon Adaları'ndan fide aldım" -> 25, "Birleşik Arap Emirlikleri'nden
# aldım" -> 225, while the single-word "Hollanda'dan tohum aldım" was refused
# correctly all along - which is why the gap hid.
#
# `[yn]?` is how _SUFFIX already spells its own optional buffer, kept the same
# shape here on purpose. `y` cannot precede `-dan` in any Turkish word, so
# admitting it costs nothing and the two lines stay readable side by side.
#
# ONLY THE APOSTROPHE BRANCH WAS AFFECTED. _SUFFIX cannot spell `nden` at all -
# `[dt][ae]n?` has no slot for a leading `n` - so the apostrophe-less
# "dominik cumhuriyetinden tohum aldim" never matched anything and still
# resolves to nothing. Confirmed, not assumed.
#
# COSTS, named rather than implied: "Hollanda'dan yazıyorum" ("writing from the
# Netherlands") is a genuine statement of location and is now refused, as is
# "Fransa'dan geldim, buradayım". Refusing a real location costs a question;
# accepting a supplier places the grower in the wrong country in silence.
_NOT_ABLATIVE = r"(?![yn]?[dt][ae]n(?!\w))"

# HAZARD: a bare preposition is NOT evidence either, because twelve English
# country names are also ordinary English nouns - and in an agriculture
# assistant they are ordinary WORKING nouns. `from turkey farms` satisfied
# `(?:in|from|at)\s+turkey(?!\w)` because a space is not a word character, and
# `turkey manure`, `turkey litter`, `niger seed` (Guizotia abyssinica, a real
# oilseed), `chile peppers`, `brazil nuts` and `china clay` are all the same
# shape.
#
# WHAT WAS TRIED AND MEASURED DEAD: a TAIL rule - requiring the name to close
# its noun phrase by enumerating the closed-class words allowed to follow it.
# The axis is wrong, not the list. Every candidate tail word was measured
# against a matched pair, a real location and a substance-containment, and every
# single one is damaging - including `and`, the comma and the full stop, which
# were in the list before it was ever widened:
#
#   tail      "my field is in Egypt <tail> the delta"  "the protein in turkey <tail> feed"
#   today     Egypt                                    Türkiye
#   near      Egypt                                    Türkiye
#   for       Egypt                                    Türkiye
#   with      Egypt                                    Türkiye
#   and       Egypt                                    Türkiye
#   , or .    Egypt                                    Türkiye
#
# The tail is IDENTICAL in both sentences, so nothing that reads the tail can
# separate them: a wide list resolves the bird, a narrow list kills ordinary
# English sentences, and `phosphorus in turkey and chicken manure` resolved to
# Türkiye under every version of the list. The class was never closed.
#
# THE RULE THAT DOES SEPARATE THEM is the one English itself uses: proper nouns
# are CAPITALISED. `Turkey` is the country and `turkey` is the bird, and the same
# line divides `Chile`/`chile`, `China`/`china`, `Brazil`/`brazil`,
# `Niger`/`niger`. So for these twelve names ONLY, the name must also appear
# Capitalised in the ORIGINAL text; the other 187 keep their old behaviour
# unchanged, because `Egypt`, `France` and `Kenya` are not words.
#
# WHAT IT COSTS, and it is not nothing:
#  * A user who types all-lowercase now gets a refusal where they used to get a
#    placement: "i am in turkey" resolves to nothing. That is the safe direction
#    - the assistant asks - and it falls on twelve names out of 199, not on the
#    table. It is the price this rule was chosen knowing about.
#  * The tail rule also refused a CAPITALISED compound noun after a preposition
#    ("at Turkey farms", "in Turkey manure"), and nothing refuses those now.
#    Taken knowingly: it needs someone writing the bird with a capital letter
#    mid-sentence, weighed against every ordinary English sentence the tail rule
#    was killing.
#  * The gerund refusal goes with it. "We are based in Brazil growing soy"
#    resolves to Brazil now, and `in turkey growing` is refused by the
#    capitalisation instead. A strict improvement - the old rule refused both,
#    and also refused "I am in Brazil growing soy" and "I work in Kenya growing
#    maize", which were never ambiguous at all.
#
# `Mali` and `Peru` are spelled the same in Turkish, so they are ONE key and the
# requirement reaches their Turkish branches too: "malide yasiyorum" is refused
# where "Mali'deyim" is not. For `mali`, which is also the Turkish adjective for
# fiscal, that direction is a gain rather than a cost.
#
# HAND-KEPT, and it has to be: this is a claim about English vocabulary, and no
# property of the alias table can derive it. A new alias that is also an English
# noun stays unguarded until it is added here.
#
# TESTED ON THE ORIGINAL TEXT, not the folded text: _normalize_tr lowercases, so
# the signal is gone by the time the branches run. _find therefore takes both.
_AMBIGUOUS_EN = frozenset({
    "brazil", "chad", "chile", "china", "cuba", "georgia",
    "guinea", "jordan", "mali", "niger", "peru", "turkey",
})

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
# THE REFUSAL IS MESSAGE-WIDE, not location-scoped. Any mention of the TRNC
# anywhere in a text kills that text's whole result, whether or not the TRNC is
# the place the user says they are in: "KKTC'de fiyatlar nasıl, ben
# Fransa'dayım" resolves to nothing, though the user plainly said France. That
# is a measured cost, accepted because the mention cannot be told apart from a
# statement of location without parsing the sentence, the failure is in the
# safe direction, and a message that names the TRNC in passing while stating a
# different country is rare. Narrowing it means deciding WHICH mention is the
# location, which is the problem this refusal exists to avoid.
#
# Matched on the FOLDED text: "Kuzey Kıbrıs" -> "kuzey kibris", "KKTC" -> "kktc".
_NO_AREA = re.compile(
    r"(?<!\w)(?:kuzey\s+kibris|k\.?k\.?t\.?c\.?|trnc|northern\s+cyprus)(?!\w)"
)


@lru_cache(maxsize=1)
def _matchers() -> tuple[
    tuple[int, str, re.Pattern[str] | None, tuple[re.Pattern[str], ...], re.Pattern[str]],
    ...,
]:
    """Per key, longest first: (code, key, capitalisation test or None, the four
    branches that place the user, the origin branch). PRE-COMPILED, built once on
    first use, the way norms._load is.

    location.py builds its patterns inside the loop, which is fine at 81
    provinces: ~320 distinct patterns fit in `re`'s internal cache, so the
    second call is free. At 199 countries and five branches it is ~1000, the
    cache (512 entries) thrashes, and EVERY pattern is recompiled on EVERY
    call - measured 2026-09-25, before this cache existed, at 272 ms per call
    against 1.4 ms for the province twin. That is the historical figure that
    bought the cache, not a current one: nothing in this module recompiles now.
    Keys stay longest-first and that IS still load-bearing, for the 34 substring
    pairs - see _find, where longest-first decides ties. The order WITHIN the
    branch tuple is not: _find takes the earliest match across all of them, so
    the old "apostrophe before the lenient suffix" ordering no longer decides
    anything.

    THE ORIGIN BRANCH IS SEPARATE from the other four because it is ranked below
    them, not because it matches differently; see _EN_IN and _find.

    THE CAPITALISATION TEST IS None FOR ALL BUT TWELVE KEYS. It is a whole-text
    precondition rather than part of a branch: the branches read folded text and
    the case is already gone there. First letter upper, the rest any case, so
    "TURKEY" counts as capitalised - all-caps is a shout, not a common noun.

    A name spelled in ENGLISH gets neither the Turkish case suffix nor the
    Turkish place noun. Nobody writes "Germanyde" or "France bolgesinde" - the
    Turkish table already holds "Almanya" and "Fransa" for that - so those two
    branches can only fire by accident on an English spelling, and one of them
    did: `Italy` + `-an` -> "Italyan cimi", Italian ryegrass. The apostrophe
    ("France'dayim" is how a Turkish speaker writes a foreign name), the whole
    message ("France") and the English preposition stay for every spelling.

    WHAT THAT GATE COSTS, measured and not free: the apostrophe-less Turkish
    suffix on an ENGLISH spelling is gone. "Franceda yasiyorum", "Germanyde
    yasiyorum", "Spaindeyim" and "Cyprusta" all resolved before it and resolve
    to nothing now. The trade is taken because a Turkish speaker writing
    without an apostrophe writes the Turkish name - Fransa, Almanya, İspanya,
    Kıbrıs - so these forms are a mixture of two conventions, while the crop
    collision they bought off was measured against real labels. The apostrophe
    path is deliberately NOT gated and keeps "France'dayım" and "Italy'deyim"
    working; tests/test_country.py pins both directions, because widening
    `turkish` back would otherwise pass in silence.

    CACHE: the result is keyed on nothing, so it cannot go stale in production -
    _FOLDED is built once at import. A test that monkeypatches _FOLDED or
    _ORDERED must call `_matchers.cache_clear()`, or it will match against the
    table this ran on first.
    """
    built = []
    for key in _ORDERED:
        k = re.escape(key)
        code, turkish = _FOLDED[key]
        suffix = _STRICT_SUFFIX if len(key) <= _SHORT else _SUFFIX
        # An empty negative lookahead always fails, so a branch switched off
        # this way keeps the tuple one shape and _find free of language tests.
        # It still carries the `name` group every branch is read through.
        never = r"(?P<name>(?!))"
        # Only the twelve ambiguous names carry the test; the rest get None and
        # are never asked. `key` is ASCII for all twelve, so the capital can be
        # taken straight off it - no Turkish letter needs unfolding.
        cap = (re.compile(rf"(?<!\w){key[0].upper()}(?i:{re.escape(key[1:])})(?!\w)")
               if key in _AMBIGUOUS_EN else None)
        # The country name is captured so _find can compare WHERE each branch
        # matched. Without it the English branch would report the position of
        # its preposition and beat a Turkish match on the same word by three
        # characters.
        built.append((code, key, cap, (
            re.compile(rf"(?<!\w)(?P<name>{k})'{_NOT_ABLATIVE}"),
            re.compile(rf"(?<!\w)(?P<name>{k}){_NOT_ABLATIVE}{suffix}(?!\w)"
                       if turkish else never),
            re.compile(rf"(?<!\w)(?P<name>{k})\s+{_PLACE}(?!\w)"
                       if turkish else never),
            # `(?!\w)` is all that is left of the old tail rule, and it is not
            # optional: without it `in India` matches inside "in Indianapolis"
            # and `in Chad` inside "in Chadian territory". The lookbehind only
            # guards the left edge.
            re.compile(rf"(?<!\w){_EN_IN}(?P<name>{k})(?!\w)"),
        ), re.compile(rf"(?<!\w){_EN_ORIGIN}\s+(?P<name>{k})(?!\w)")))
    return tuple(built)


def _refuses(folded: str) -> bool:
    """True when the ALREADY-FOLDED text names a place FAOSTAT has no area for.

    Separate from _find because it is not a failure to match - it is a decision
    not to answer, and the caller must stop rather than look elsewhere.

    Takes folded text, not raw: every caller needs the fold anyway and doing it
    here as well folded each message twice on a path that runs on every answer.
    """
    return bool(_NO_AREA.search(folded))


def _find(folded: str, original: str) -> int | None:
    """Match a country in ALREADY-FOLDED text, tolerating Turkish case suffixes
    and English prepositions, but never firing inside a longer word and never
    firing on a crop name.

    TAKES THE TEXT TWICE, folded and as the user wrote it. The branches need the
    fold; the twelve names that are also ordinary English nouns need the capital
    letter, which the fold destroys. Folding stayed where it is - in
    extract_country, done once per text - and the original is passed alongside it
    rather than re-derived, because these two strings must describe the same text
    and a second fold here would be a second chance for them not to. See
    _AMBIGUOUS_EN.

    Five forms are accepted, the first four as location.py accepts them except
    for the ablative. An apostrophe is an unambiguous proper-noun boundary in
    Turkish, so almost anything may follow it ("Mısır'dayım", "Fas'ta") - the
    one exception is the bare ablative, which marks a supplier rather than a
    location and is refused in both branches it can reach; see _NOT_ABLATIVE. A
    known case suffix, optionally with a personal ending, carries the ordinary
    statements ("fransada", "Fransadayim"). A BARE name is accepted only where
    it cannot be a modifier: as the whole message (the natural reply to "hangi
    ulkedesiniz?"), or with a place noun immediately after it. The fifth is
    English, which has no case ending and states location with a preposition
    instead - `in` and `at`, and `from` only after a copula.

    `from` AFTER A COPULA IS THE WEAKEST OF THE FIVE and is read only when none
    of the others matched anywhere in the text, so "I'm from Turkey but I farm in
    Germany" answers Germany. See _EN_IN for why earliest-wins cannot do this on
    its own.

    THE EARLIEST MATCH WINS, not the longest name. A sentence may name two
    countries and only one of them is where the user is - "I am in Turkey but I
    import seed from France", "Mısır'dayım ama Fransa'dan gübre alıyorum" - and
    returning on the first key that matched ANYWHERE handed those to whichever
    country had the longer name, which is unrelated to what the user said. So
    every key is tried and the candidate with the smallest match position is
    returned. It is the weakest defensible reading of a two-country sentence:
    people state where they are before they qualify it.

    LONGEST-FIRST STILL DECIDES TIES, and that is the whole reason _ORDERED
    exists: `Dominik` and `Dominika` both match "Dominika'dayım" at position 0,
    as do `Nijer` and `Nijerya` on "Nijerya'dayım", because the lenient suffix
    branch reads the longer name's trailing letter as a case ending. Candidates
    arrive longest-first and a later one has to be STRICTLY earlier to win, so
    the longer name keeps the position it shares. Four tests pin this.

    WHAT THIS DOES NOT CLOSE, inherited unchanged from location.py: the lenient
    suffix branch still resolves ordinary Turkish words that happen to be a
    country plus a legal case ending. Same harm shape as the crop names, lower
    frequency. Do not read this function as having solved the collision problem;
    it solved the branches it names.
    """
    if _refuses(folded):
        return None
    whole = folded.strip(_TRIM)
    best_start: int | None = None
    best_code: int | None = None
    origin_start: int | None = None
    origin_code: int | None = None
    for code, key, cap, patterns, origin in _matchers():
        # An ambiguous name that never appears capitalised is not this country
        # in this text, by ANY branch - the whole key drops out here rather than
        # each branch testing it.
        if cap is not None and not cap.search(original):
            continue
        # The whole message being the name is position 0 by construction.
        start = 0 if whole == key else None
        for pattern in patterns:
            match = pattern.search(folded)
            # `name` is the country itself, so branches with different
            # preambles - the English preposition - stay comparable.
            if match is not None and (start is None or match.start("name") < start):
                start = match.start("name")
        if start is not None and (best_start is None or start < best_start):
            best_start, best_code = start, code
        if best_start == 0:
            # Nothing can beat position 0, and any later key that ties it is
            # shorter and would lose the tie anyway. This keeps the common case
            # - the message opens with the country - at its old cost instead of
            # paying for all 199 keys. Leaving origin uncomputed is safe: a
            # primary match outranks every origin match by construction.
            break
        # Origin is collected in the same pass but compared separately, and it
        # never breaks the loop early: position 0 is unreachable for it, since
        # the copula always precedes the name.
        match = origin.search(folded)
        if match is not None and (origin_start is None
                                  or match.start("name") < origin_start):
            origin_start, origin_code = match.start("name"), code
    # Ranked, not merged: origin answers only for texts where nothing said where
    # the user IS.
    return best_code if best_code is not None else origin_code


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
    folded = _normalize_tr(message)
    if _refuses(folded):
        return None
    found = _find(folded, message)
    if found:
        return found
    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        raw = turn.get("content", "")
        content = _normalize_tr(raw)
        # The walk stops here, it does not skip past: this turn IS the most
        # recent statement of location, and continuing would answer with a
        # country the user has since moved on from.
        if _refuses(content):
            return None
        # Both forms of the SAME turn, for the reason _find's docstring gives.
        found = _find(content, raw)
        if found:
            return found
    return None
