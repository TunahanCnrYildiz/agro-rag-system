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
maize, `Fas` sits inside `Fasulye`, and `Çin` inside `İçin` - one of the
commonest words in the language. `Hindistan` and `Malta` collide a step further
out: NEITHER `Hindistan Cevizi` NOR `Malta Eriği` is a crop label here, and an
earlier revision of this paragraph called them labels. Both are substrings of
one - `Diğer Sert Kabuklu Meyveler (… Hindistan Cevizi Hariç)`, where the name
appears in an EXCLUSION clause, and `Yenidünya (Malta Eriği)`, where it is a
parenthetical variant - and both sit in the part the family split throws away,
so the families are `Diğer Sert Kabuklu Meyveler` and `Yenidünya`. The country
names still have to be refused inside them, which is what this module does; the
distinction matters because a reader looking for a `Hindistan Cevizi` family
will not find one, and because the crop detector's own blind spot is the mirror
image of it (see `crop_compare._NOT_THIS_PLANT`: with no such family, nothing
covered `Ceviz` inside it and a coconut question was answered with walnut
figures). A substring match answers Morocco to "fasulye ektim".
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
# provinces: the table has 78 substring pairs (`Mali` in `Somali`, `Oman` in
# `Romanya`, `Dominik` in `Dominika`, `Nijer` in `Nijerya`), and the lenient
# suffix branch below would read the trailing letter of the longer name as a
# case ending. Trying the longer key first is what makes "Nijerya'dayım"
# Nigeria rather than Niger.
#
# 35 OF THE 78 POINT AT TWO DIFFERENT COUNTRIES, and only those can make the
# order decide an ANSWER rather than a spelling; the other 43 are one country's
# own aliases (`Antigua` inside `Antigua ve Barbuda`, both 8) and are harmless
# whichever key wins. Both figures are counted from _FOLDED by
# test_the_substring_pair_count_the_ordering_is_justified_by, so they cannot go
# stale again: this comment and the _matchers docstring both read 34 until
# 2026-10-02, and no counting basis of the shipped table gives 34 - the nearest
# is the 35 above. The table had not drifted either; it was already 78/35 when
# the figure was first written at c6d1c3a.
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

# HAZARD: a bare preposition is NOT evidence either, because ten English
# country names are also ordinary English nouns - and in an agriculture
# assistant they are ordinary WORKING nouns. `from turkey farms` satisfied
# `(?:in|from|at)\s+turkey(?!\w)` because a space is not a word character, and
# `turkey manure`, `turkey litter`, `niger seed` (Guizotia abyssinica, a real
# oilseed), `chile peppers`, `brazil nuts` and `china clay` are all the same
# shape.
#
# WHAT WAS TRIED AND MEASURED DEAD: a TAIL WHITELIST - requiring the name to
# close its noun phrase by enumerating the closed-class words allowed to follow
# it. Every candidate tail word was measured against a matched pair, a real
# location and a substance-containment, and every single one is damaging -
# including `and`, the comma and the full stop, which were in the list before it
# was ever widened:
#
#   tail      "my field is in Egypt <tail> the delta"  "the protein in turkey <tail> feed"
#   today     Egypt                                    Türkiye
#   near      Egypt                                    Türkiye
#   for       Egypt                                    Türkiye
#   with      Egypt                                    Türkiye
#   and       Egypt                                    Türkiye
#   , or .    Egypt                                    Türkiye
#
# The tail is IDENTICAL in both sentences, so nothing that WHITELISTS the tail
# can separate them: a wide list resolves the bird, a narrow list kills ordinary
# English sentences, and `phosphorus in turkey and chicken manure` resolved to
# Türkiye under every version of the list. That is a verdict on the whitelist,
# not on reading the word after the name - see _EN_HEAD, which blacklists the
# HEAD NOUN instead and is measured below.
#
# ONE RULE THAT SEPARATES THEM is the one English itself uses: proper nouns are
# CAPITALISED. `Turkey` is the country and `turkey` is the bird, and the same
# line divides `Chile`/`chile`, `China`/`china`, `Brazil`/`brazil`,
# `Niger`/`niger`. So for these ten names ONLY, the name must also appear
# Capitalised in the ORIGINAL text; the other 188 keep their old behaviour
# unchanged, because `Egypt`, `France` and `Kenya` are not words.
#
# IT IS ONLY ONE OF TWO RULES, and that is the correction this revision exists
# to make. The capital letter does NOT separate the country from the compound
# noun, because in this domain the compound noun is capitalised too: `Sudan
# grass`, `Guinea grass`, `Brazil nut`, `China clay`, `Chile pepper` and `Niger
# seed` are the standard orthography for a plant named after a proper noun, not
# typos. Measured on the previous revision, all capitalised: "the protein in
# Sudan grass is high" -> 276, "we compared yields in Guinea grass" -> 90, "the
# oil in Brazil nuts" -> 21, "kaolin in China clay" -> 41, "capsaicin in Chile
# peppers" -> 40, "the oil in Niger seed" -> 158, "we work at Turkey farms" ->
# 223, "I raise birds in Turkey houses" -> 223, "in India ink" -> 100, "in
# Panama hats" -> 166. This gate refuses none of them; _EN_HEAD refuses all ten.
# The two rules fail on DISJOINT inputs - the capital catches lowercase "in
# turkey for feed", the head noun catches capitalised "in Sudan grass" - which is
# why this revision ADDS the second rather than swapping the first out again.
#
# WHAT THE CAPITAL LETTER COSTS, measured:
#  * A user who types all-lowercase gets a refusal where they used to get a
#    placement: "i am in turkey" resolves to nothing. That is the safe direction
#    - the assistant asks - and it falls on ten names out of 199, not on the
#    table. It is the price this rule was chosen knowing about.
#  * It buys NOTHING against the capitalised compound noun, per the ten measured
#    figures above. Everything refused there is refused by _EN_HEAD, and if
#    _EN_HEAD is ever deleted this gate will not notice.
#  * The gerund refusal that went with the tail whitelist is a TRADE, not the
#    strict improvement an earlier revision of this comment claimed. Dropping it
#    resolves "We are based in Brazil growing soy" -> 21, "I am in Brazil growing
#    soy" -> 21 and "I work in Kenya growing maize" -> 114, all of which were
#    refused before; it also admitted "we work at Turkey farms" -> 223 and "I
#    raise birds in Turkey houses" -> 223, which the whitelist had been refusing.
#    _EN_HEAD takes the second half back and deliberately does NOT re-refuse the
#    gerund - see the REJECTED note there.
#
# `Mali` is spelled the same in Turkish, so it is ONE key and the requirement
# reaches its Turkish branches too: "malide yasiyorum" is refused where
# "Mali'deyim" is not. `mali` is also the Turkish adjective for fiscal, so that
# direction is a gain rather than a cost. `Sudan` is the same shape and is here
# for the same reason: sudangrass is a standard forage, measured "the protein in
# sudan grass" -> 276 before this revision, with the name lowercase and ungated.
#
# `peru` AND `cuba` WERE REMOVED, having been listed with no ambiguity to justify
# the charge. Neither is an ordinary English noun, and the gate was costing their
# lowercase forms for nothing: measured before the removal, "i am in peru",
# "perudayim" and "i am in cuba" all resolved to nothing, and they resolve to
# 170, 170 and 49 now. `peru` is one key across both languages like `mali`, so
# the charge had reached the Turkish branches as well. The compound nouns they do
# appear in - `Peru balsam` - are _EN_HEAD's business, not this gate's.
#
# `georgia` WAS REMOVED THIS WAVE, for the opposite reason: not too little
# ambiguity but too much for a capital letter to settle. See _NOT_THIS_PLACE,
# which refuses the English spelling outright.
#
# `chad` AND `jordan` ARE KEPT ON A WEAKER CLAIM THAN THE OTHER EIGHT, and that
# is said here rather than left implied. They are not ordinary English nouns -
# they are proper nouns of OTHER referents, a given name and a surname - so the
# capital cannot separate them from the country, and measured, it does not try:
# "Jordan said the yield in Jordan is low" -> 112 and "we counted the hanging
# chad in Chad" -> 39 with the gate in place. What the gate does for these two
# is refuse "i am in jordan" and "i am in chad", which is pure cost by the
# `peru`/`cuba` argument. They are kept anyway, for one reason: removing them
# WIDENS this module's recall, and widening a resolver in the same wave that
# narrows the guard reading it is exactly what three earlier waves on this
# branch got wrong. A person's name never stands after `in`, so the removal is
# cheap and it should be its own change with its own measurement.
#
# RE-MEASURED 2026-10-06, after the guard was cut to two patterns, and the lead
# is SHARPER now rather than weaker - the decision is still to keep, and this is
# what it costs and buys at today's tip:
#   * what it costs: `extract_country("i am in jordan")` and `("i am in chad")`
#     are None, so a lowercase English self-declaration naming either country
#     gets no figures at all. Capitalised, both resolve.
#   * what it buys: NOTHING reachable. "Jordan said the yield in Jordan is low"
#     resolves 112, and `extract_country` has exactly ONE caller - inside
#     `_country_lines`, behind `engine._states_location`, which refuses that
#     sentence because no person suffix sits on the name. So the misreading the
#     gate exists to prevent cannot reach a user today.
# It is kept all the same, on the same argument and not a new one: removing it
# widens recall, and this wave DELETED rules from the guard that reads this
# module. Widening the resolver in the wave that strips its reader is the exact
# shape of the mistake three earlier waves made. Pinned as a cost by
# `test_the_capital_gate_on_chad_and_jordan_costs_their_lowercase_typists`.
#
# HAND-KEPT, and it has to be: this is a claim about English vocabulary, and no
# property of the alias table can derive it. A new alias that is also an English
# noun stays unguarded until it is added here.
#
# TESTED ON THE ORIGINAL TEXT, not the folded text: _normalize_tr lowercases, so
# the signal is gone by the time the branches run. _find therefore takes both.
_AMBIGUOUS_EN = frozenset({
    "brazil", "chad", "chile", "china",
    "guinea", "jordan", "mali", "niger", "sudan", "turkey",
})

# HAZARD, and the one the capitalisation gate above does not touch: a country
# name immediately followed by an open-class noun is a COMPOUND NOUN naming a
# plant, a product or a building, not a statement of location. `Sudan grass` is
# Sorghum x drummondii, `Niger seed` is Guizotia abyssinica, `Brazil nut` is
# Bertholletia excelsa, `China clay` is kaolin, `Chile pepper` is Capsicum, and
# `turkey litter`, `Turkey farms` and `Turkey houses` are where the bird lives.
# All ten measured figures in the paragraph above are this shape.
#
# THE AXIS, and why this is not the dead tail whitelist in new clothes: the
# whitelist asked which words are ALLOWED to follow the name and failed because
# the answer is identical in both sentences ("in Egypt near the delta" / "in
# turkey near the feeder"). This asks the opposite question - which words the
# name is MODIFYING - and the answer is not identical: an open-class noun head
# is never what follows a country that states where the user is.
#
# ADJACENCY IS LOAD-BEARING, exactly as it is for _PLACE. `clay` is in this list
# and "My farm is in Spain with clay soil" still resolves to 203, because the
# preposition sits between the name and the noun. Relaxing the `\s+` to allow an
# intervening word brings that sentence straight back down.
#
# WHAT IT COSTS, measured rather than implied: a location sentence whose next
# word happens to be one of these bare nouns is refused. "in Kenya seed is
# expensive" and "in Turkey oil prices rose" resolve to nothing now. Both are
# real shapes and the refusal is real; it is taken because the compound reading
# dominates each of these words in this assistant's traffic and the failure is in
# the safe direction. This is a cost of the rule, not an argument against it, and
# it is why the list is kept short and every entry has to earn its place.
#
# REJECTED: adding gerunds (`growing`, `farming`) to close `in Turkey farming`.
# They are the same words as "I am in Turkey farming wheat" and "We are based in
# Brazil growing soy" (21, measured), which is the class the tail whitelist was
# already charged with killing. The head-noun list stays nominal.
#
# APPLIED TO EVERY KEY, not just the ten above. `India`, `Panama`, `Morocco`
# and `Japan` are not ordinary English nouns and are NOT gated on a capital, but
# `India ink`, `Panama hats`, `Morocco leather` and `Japan wax` are all compound
# nouns of exactly this shape - measured, "in India ink" -> 100 and "in Panama
# hats" -> 166 before this rule. Refusing the compound at the right axis costs
# their lowercase typists nothing, which adding them to _AMBIGUOUS_EN would not.
#
# MATCHED ON THE FOLDED TEXT, so no re.I is needed and the position is the same
# position the branches report: the fold lowercases and these words are ASCII.
#
# BEYOND THE MEASURED PROTOTYPE this list adds four poultry nouns - `hen`,
# `chick`, `poult` - which sit beside the `breast|meat|fowl` already here and are
# how a turkey flock is talked about, and `balsam`, for `Peru balsam`
# (Myroxylon balsamum), a real botanical extract and the compound `Peru` turns up
# in. Each of the four was measured against the prototype list: "we work at
# Turkey hens" -> 223, "the vaccine in Turkey chicks" -> 223, "the feed in Turkey
# poults" -> 223 and "the oil in Peru balsam" -> 170 without them, nothing with.
# The rest is plural inflection of words the prototype already carried: `grasses`, `oils`, `breasts`, `fowls` and above all
# `pigs`, because "guinea pigs" is far commoner than "guinea pig".
_EN_HEAD = (r"(?:grass(?:es)?|seeds?|nuts?|clay|peppers?|manure|litter|farms?"
            r"|houses?|meal|oils?|wax|leather|ink|hats?|feed|breasts?|meat"
            r"|fowls?|pigs?|hens?|chicks?|poults?|balsam)")

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

# HAZARD, THE SAME SHAPE ONE STEP ALONG: a country name whose dominant reading
# in THIS assistant is a different place, and one FAOSTAT holds no figures for.
# `Georgia` is a top-ten US agricultural state - peanuts, pecans, peaches,
# poultry - and "my farm is in Georgia" from an English-speaking grower is far
# likelier to be the state than the Republic. FAOSTAT has no US-state area, so
# the state cannot be answered; area 73 can, and answering it hands a Georgia
# grower Caucasian yields with nothing said. That is the TRNC harm exactly, and
# it is treated the same way: refuse, and let the assistant ask.
#
# IT WAS THE OTHER WAY ROUND UNTIL THIS WAVE, and pinned: tests/test_country.py
# asserted `("my farm is in Georgia", 73)` as the correct answer. The guard in
# src/engine.py did not read `my farm is in` at all, so the wrong answer stayed
# behind a branch that never fired; the same wave that admitted that shape as a
# self-declaration had to decide this, and decided against the country.
#
# THE ENGLISH SPELLING ONLY, which is what makes the trade cheap. `Gürcistan`
# and `gurcistan` are untouched and still resolve to 73, so this product's
# primary user - a Turkish speaker - loses nothing whatever. What is given up is
# an English-speaking grower in the Republic of Georgia, who is asked instead of
# placed. Measured: "Gürcistan'dayım" -> 73, "Gürcistan'da yaşıyorum" -> 73,
# "my farm is in Georgia" -> None, "I farm in Georgia" -> None, "the yield in
# Georgia peaches is high" -> None (73 before, and the capital gate bought
# nothing against it).
#
# MESSAGE-WIDE, for the reason _NO_AREA is: the user HAS said where they are,
# and falling through to another country in the same sentence or to an older
# turn is the same silent misplacement in a different costume.
#
# NOT A CAPITALISATION MATTER. `georgia` was in _AMBIGUOUS_EN and the gate could
# never have helped: both readings are proper nouns and both are capitalised.
# That is the module's own argument for why the capital "buys NOTHING against
# the capitalised compound noun", applied to a capitalised PLACE noun.
_NOT_THIS_PLACE = re.compile(r"(?<!\w)georgia(?!\w)")


@lru_cache(maxsize=1)
def _matchers() -> tuple[
    tuple[int, str, re.Pattern[str] | None, re.Pattern[str],
          tuple[re.Pattern[str], ...], re.Pattern[str]],
    ...,
]:
    """Per key, longest first: (code, key, capitalisation test or None, the
    head-noun refusal, the four branches that place the user, the origin
    branch). PRE-COMPILED, built once on first use, the way norms._load is.

    location.py builds its patterns inside the loop, which is fine at 81
    provinces: ~320 distinct patterns fit in `re`'s internal cache, so the
    second call is free. At 199 countries it is well past that, the cache (512
    entries) thrashes, and EVERY pattern is recompiled on EVERY call - measured
    2026-09-25, before this cache existed, at 272 ms per call against 1.4 ms for
    the province twin. That is the historical figure that bought the cache, not a
    current one: nothing in this module recompiles now, and the cache is no
    longer where the time goes.

    WHERE THE TIME GOES NOW, and it is no longer the cache. Measured on one
    machine over four runs of 400 calls, so these figures are comparable with
    each other and with nothing else: 1.24-1.34 ms for a message that matches
    nothing, 1.29-1.37 ms for a two-country sentence, 0.21-0.22 ms when the
    message opens with the country and _find can break at position 0. The cost is
    the five scans of the text per key in _find, not the six patterns built here;
    the head-noun and capitalisation tests add no scan at all, because they are
    anchored at a position a branch has already found.

    THE 1.4 ms QUOTED ABOVE FOR THE PROVINCE TWIN IS HISTORICAL, from the same
    2026-09-25 run as the 272 ms, and it is not this machine. Measured here
    alongside the figures above, location.extract_province costs 0.28 ms on the
    same no-match message, so this module is ~4.5x its twin rather than under it.
    That is the honest shape: 199 keys and five branches against 81 keys and
    four, on a module consulted once per answer. Nothing here is a regression to
    chase - the two revisions of guards before this one moved it from 1.22 to
    ~1.3 ms, and this one did not move it - but do not read the old 1.4 ms as
    headroom this still fits inside.

    Keys stay longest-first and that IS still load-bearing, for the 78 substring
    pairs - see _find, where longest-first decides ties. The order WITHIN the
    branch tuple is not: _find takes the earliest match across all of them, so
    the old "apostrophe before the lenient suffix" ordering no longer decides
    anything.

    THE ORIGIN BRANCH IS SEPARATE from the other four because it is ranked below
    them, not because it matches differently; see _EN_IN and _find.

    THE CAPITALISATION TEST IS None FOR ALL BUT ELEVEN KEYS, and the head-noun
    test is built for every key. Both are preconditions on a matched OCCURRENCE
    rather than part of a branch: the branches read folded text, where the case
    is already gone, and neither test belongs inside a pattern that four branches
    share. First letter upper, the rest any case, so "TURKEY" counts as
    capitalised - all-caps is a shout, not a common noun.

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
        # Only the ten ambiguous names carry the test; the rest get None and
        # are never asked. `key` is ASCII for all ten, so the capital can be
        # taken straight off it - no Turkish letter needs unfolding.
        #
        # The lookbehind is kept although _find only ever anchors this pattern at
        # a position a branch already cleared one for: the whole-text fallback
        # below uses .search, and that one needs it.
        cap = (re.compile(rf"(?<!\w){key[0].upper()}(?i:{re.escape(key[1:])})(?!\w)")
               if key in _AMBIGUOUS_EN else None)
        # Anchored at the name, never searched: _find matches it at the position
        # a branch reported, so "Brazil nuts" mentioned elsewhere in the message
        # cannot refuse an "I am in Brazil" that stands on its own. That is the
        # same per-occurrence rule the capitalisation test now follows, and for
        # the same reason - see _find.
        head = re.compile(rf"(?<!\w){k}\s+{_EN_HEAD}(?!\w)")
        # The country name is captured so _find can compare WHERE each branch
        # matched. Without it the English branch would report the position of
        # its preposition and beat a Turkish match on the same word by three
        # characters.
        built.append((code, key, cap, head, (
            re.compile(rf"(?<!\w)(?P<name>{k})'{_NOT_ABLATIVE}"),
            # `(?!['\w])` and not `(?!\w)`: an apostrophe here means the real
            # proper noun runs on and a SHORTER key has eaten its trailing vowel
            # as a case suffix. "Dominika'dan tohum aldim" matched key `dominik`
            # + `a` and stopped at the apostrophe, never reaching the `'dan` that
            # _NOT_ABLATIVE refuses - so a purchase read as a location AND as the
            # wrong country (56 Dominican Republic for 55 Dominica; 158 Niger for
            # 159 Nigeria). Turkish attaches the apostrophe BEFORE the suffix on a
            # proper noun ("Ankara'da"), never after, so nothing legitimate is lost.
            re.compile(rf"(?<!\w)(?P<name>{k}){_NOT_ABLATIVE}{suffix}(?!['\w])"
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
    """True when the ALREADY-FOLDED text names a place this table cannot answer
    for - either one FAOSTAT has no area for at all (_NO_AREA) or one whose
    dominant reading here is a place it has no area for (_NOT_THIS_PLACE).

    Separate from _find because it is not a failure to match - it is a decision
    not to answer, and the caller must stop rather than look elsewhere.

    Takes folded text, not raw: every caller needs the fold anyway and doing it
    here as well folded each message twice on a path that runs on every answer.
    """
    return bool(_NO_AREA.search(folded) or _NOT_THIS_PLACE.search(folded))


def _admits(cap: re.Pattern[str] | None, head: re.Pattern[str],
            folded: str, original: str, aligned: bool, pos: int) -> bool:
    """True when the country name AT `pos` may place the user.

    Both tests are asked HERE, of one occurrence, rather than of the whole text
    per key. Whole-text was measured wrong in both directions:

      * it let one capital licence every lowercase mention, and English
        capitalises the first word of a sentence, so a message that opens by
        naming the country supplies its own licence for every mention after it.
        Measured with the head noun already in place and the capital still tested
        whole-text: "Turkey is a big producer. The protein in turkey for feed is
        high." -> 223 and "Chile is long. The capsaicin in chile for sauce is
        high." -> 40, both refused now. The head noun cannot reach these - `for
        feed` and `for sauce` put a preposition where its noun would be - and
        "Turkey litter is cheap, how much should I spread" is an ordinary message
        for this assistant, not a corner case.
      * the mirror image for the head noun: "I am in Brazil and we sell Brazil
        nuts" says plainly where the user is, and a whole-text head refusal would
        drop the key and answer nothing.

    POSITIONS ARE ONLY COMPARABLE WHEN THE FOLD IS LENGTH-PRESERVING, which is
    what `aligned` carries. _TR_FOLD is 1:1 by construction and maps U+0130
    (`İ`) to ASCII `I` BEFORE .lower() runs, which is the one character whose
    lowercase would otherwise be two - "İstanbul" -> "istanbul", 8 to 8. So the
    fallback below is not expected to fire; it is here because that is a property
    of another module's table, and if it ever stops holding this must degrade to
    the old whole-text test rather than read the wrong character. The head noun
    needs no fallback: it is matched on `folded`, against its own position.
    """
    if head.match(folded, pos) is not None:
        return False
    if cap is None:
        return True
    if aligned:
        return cap.match(original, pos) is not None
    return cap.search(original) is not None


def _find(folded: str, original: str) -> int | None:
    """Match a country in ALREADY-FOLDED text, tolerating Turkish case suffixes
    and English prepositions, but never firing inside a longer word and never
    firing on a crop name.

    TAKES THE TEXT TWICE, folded and as the user wrote it. The branches need the
    fold; the ten names that are also ordinary English nouns need the capital
    letter, which the fold destroys. Folding stayed where it is - in
    extract_country, done once per text - and the original is passed alongside it
    rather than re-derived, because these two strings must describe the same text
    and a second fold here would be a second chance for them not to. See
    _AMBIGUOUS_EN.

    TWO PRECONDITIONS SIT ON EVERY MATCH, not on every key: the capital letter
    for those ten names, and the head-noun refusal for all 199. Both are
    asked of the OCCURRENCE a branch found, so a later mention cannot licence an
    earlier one and an earlier one cannot condemn a later one. See _admits, which
    names what whole-text testing was measured to cost in each direction.

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
    # Where `whole` actually begins, so a message that opens with whitespace or a
    # quote mark still hands _admits the position of its first letter.
    lead = len(folded) - len(folded.lstrip(_TRIM))
    aligned = len(folded) == len(original)
    best_start: int | None = None
    best_code: int | None = None
    origin_start: int | None = None
    origin_code: int | None = None
    for code, key, cap, head, patterns, origin in _matchers():
        start = None
        if whole == key and _admits(cap, head, folded, original, aligned, lead):
            start = lead
        for pattern in patterns:
            # EVERY occurrence, not just the first: _admits can refuse one and
            # clear the next, and a single `search` threw the sentence away on
            # the refused one - "I work in turkey houses but I am in Turkey"
            # answered nothing and answers 223 now.
            #
            # A RESUMED search, not finditer. finditer allocates a scanner per
            # call whether or not anything matches, and this runs 4x199 times
            # per message: measured, it put the no-match message at 1.66 ms and
            # a message opening with the country at 0.49 ms, against 1.22 and
            # 0.21 before this revision. Resuming from `pos` pays only where
            # there IS a match, which is 1 key in 199. Same walk, same result.
            pos = 0
            while (match := pattern.search(folded, pos)) is not None:
                # `name` is the country itself, so branches with different
                # preambles - the English preposition - stay comparable.
                found = match.start("name")
                if _admits(cap, head, folded, original, aligned, found):
                    # Left to right, so the first ADMITTED match is the earliest
                    # this branch can offer.
                    if start is None or found < start:
                        start = found
                    break
                pos = match.end()
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
        pos = 0
        while (match := origin.search(folded, pos)) is not None:
            found = match.start("name")
            if _admits(cap, head, folded, original, aligned, found):
                if origin_start is None or found < origin_start:
                    origin_start, origin_code = found, code
                break
            pos = match.end()
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
    # `is not None`, not truthiness: _find returns an FAO AREA CODE, and 0 is a
    # code like any other as far as this function's contract goes. No shipped
    # table holds area 0, so this changes nothing today - which is the reason to
    # write it correctly rather than to leave the code saying something false.
    found = _find(folded, message)
    if found is not None:
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
        # `is not None` for the reason given above.
        found = _find(content, raw)
        if found is not None:
            return found
    return None
