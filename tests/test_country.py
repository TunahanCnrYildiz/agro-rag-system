import pytest

from src.context.country import extract_country

# Verified against data/world_norms.json on 2026-09-25. Note 41, not 351:
# 351 is FAOSTAT's `China` AGGREGATE, which this project never resolves to.
TURKIYE, FRANCE, EGYPT = 223, 68, 59
CHINA, MOROCCO, INDIA = 41, 143, 100
KENYA, SPAIN, BRAZIL, NETHERLANDS, ITALY = 114, 203, 21, 150, 106


def test_a_turkish_locative_resolves():
    assert extract_country("Fransa'dayım, buğday ekiyorum") == FRANCE


def test_an_ordinary_turkish_case_suffix_resolves():
    assert extract_country("fransada yasiyorum") == FRANCE


def test_an_english_preposition_resolves():
    assert extract_country("I am in France and grow wheat") == FRANCE


def test_a_bare_name_as_the_whole_message_resolves():
    """The natural reply to "hangi ülkedesiniz?"."""
    assert extract_country("Mısır") == EGYPT
    assert extract_country("France") == FRANCE


def test_nothing_resolves_to_nothing():
    assert extract_country("buğdayıma ne zaman gübre atmalıyım") is None


@pytest.mark.parametrize("message", [
    "mısır ektim, ne kadar gübre atayım",
    "mısır silajı için doz nedir",
    "fasulye ektim",
    "hindistan cevizi yetiştirmek istiyorum",
    "bu gübre bakla için mi",
    "yenidünya (malta eriği) hakkında bilgi",
])
def test_a_crop_sentence_never_resolves_to_a_country(message):
    """Measured against our 246 crop labels: `Mısır` IS a crop label, `Fas`
    sits inside `Fasulye`, `Çin` inside `İçin`, `Hindistan` inside
    `Hindistan Cevizi`, `Malta` inside `Malta Eriği`. Substring matching
    would answer Morocco to "fasulye ektim"."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("Mısır'dayım", EGYPT),
    ("Fas'ta çiftçilik yapıyorum", MOROCCO),
    ("Çin'de yaşıyorum", CHINA),
    ("Hindistan'dayım", INDIA),
])
def test_the_same_words_resolve_when_stated_as_a_place(message, code):
    """The other half of the collision: refusing the crop sentence must not
    cost the genuine statement of location."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message", [
    "I use turkey manure on my field",
    "we buy litter from turkey farms",
])
def test_an_english_name_that_is_also_livestock_never_places_the_user(message):
    """`Turkey` is the English twin of `Mısır`. In an agriculture assistant
    "turkey manure", "turkey litter" and "turkey farms" are ordinary phrases,
    and `from turkey farms` satisfies a bare preposition rule. The country
    name must stay in the table, so the guard belongs here."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message", [
    "the protein in turkey for feed",
    "the oil in niger for biodiesel",
    "capsaicin in chile for sauce",
    "phosphorus in turkey and chicken manure",
    "we work at turkey farms near Konya",
    "at turkey manure today",
    "I am in turkey litter business",
])
def test_a_substance_in_an_ambiguous_name_is_not_a_location(message):
    """The shape a TAIL rule can never refuse, and the reason there is no longer
    a tail rule. "the protein in turkey for feed" and "my field is in Egypt near
    the delta" have the SAME tail, so every word admitted to close a noun phrase
    resolved the first sentence too: measured, `for`, `near`, `with`, `today`,
    `and`, the comma and the full stop all did, and `phosphorus in turkey and
    chicken manure` resolved to Türkiye under every version of that list.

    One of the two things that separates them is the capital letter, and it is
    the one these seven need. The first three resolved to Türkiye, Niger and
    Chile before it. The capitalised half of the class is a different rule
    entirely — see the compound-noun test below."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message", [
    "the protein in Sudan grass is high",
    "we compared yields in Guinea grass",
    "the oil in Brazil nuts",
    "kaolin in China clay",
    "capsaicin in Chile peppers",
    "the oil in Niger seed",
    "we work at Turkey farms",
    "I raise birds in Turkey houses",
    "in India ink",
    "in Panama hats",
    "the protein in sudan grass",
])
def test_a_capitalised_compound_noun_is_not_a_location(message):
    """The class the capital letter does NOT close, because in this domain the
    compound noun is capitalised too. `Sudan grass`, `Guinea grass`, `Brazil
    nut`, `China clay`, `Chile pepper` and `Niger seed` are the standard
    orthography for a plant named after a proper noun, not typos, and this is
    where an agriculture assistant's English traffic lives.

    Measured with the capitalisation gate alone and nothing else: 276, 90, 21,
    41, 40, 158, 223, 223, 100, 166, 276. The gate refuses none of them. What
    refuses them is the head noun — an open-class noun immediately after the
    name means the country is MODIFYING it, not stating where anyone is.

    The two rules fail on disjoint inputs, which is why this one was added
    beside the capital rather than in place of it: the lowercase test above
    needs the capital, these eleven need the head noun."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message", [
    "in Kenya seed is expensive",
    "in Turkey oil prices rose",
])
def test_the_head_noun_rule_costs_the_bare_noun_that_follows(message):
    """What the head-noun rule charges, pinned so it stays visible. A location
    sentence whose next word happens to be one of the listed nouns standing on
    its own is refused. Both of these are real shapes and both resolved before.
    Taken because the compound reading dominates each of those words in this
    assistant's traffic and the failure is in the safe direction — and it is why
    the list is short and nominal."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("My farm is in Spain with clay soil", SPAIN),
    ("I am in Brazil and we sell Brazil nuts", BRAZIL),
    ("we sell Brazil nuts, I am in Brazil", BRAZIL),
])
def test_the_head_noun_must_sit_immediately_after_the_name(message, code):
    """Adjacency is load-bearing, exactly as it is for the Turkish place nouns.
    `clay` and `nuts` are both on the list and all three of these still resolve:
    the first has a preposition between the name and the noun, and the other two
    mention the compound somewhere ELSE in a message that plainly says where the
    user is. Refusing per KEY rather than per MENTION would answer nothing to
    both of those."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message", [
    "i am in turkey",
    "i live in brazil",
    "my farm is in chile",
    "malide yasiyorum",
    "sudanda yasiyorum",
])
def test_the_capitalisation_rule_costs_the_lowercase_typist(message):
    """What the rule charges, pinned so it is visible rather than discovered. A
    user who types all-lowercase is refused where they used to be placed. It
    falls on ten names out of 199 - the ones that are also ordinary nouns -
    and the failure is in the safe direction: the assistant asks.

    The third sentence used to name `georgia` and would now pass for the WRONG
    REASON - `Georgia` is refused in both cases by _NOT_THIS_PLACE, whatever
    this gate does - so it names `chile` instead, which this gate alone holds.

    "malide yasiyorum" is there because `Mali` is spelled the same in both
    lists, so the requirement reaches its Turkish branches too. `mali` is also
    the Turkish adjective for fiscal, so that one is a gain as much as a cost."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message", [
    "Turkey is a big producer. The protein in turkey for feed is high.",
    "Chile is long. The capsaicin in chile for sauce is high.",
    "Turkey litter is cheap. The nitrogen in turkey litter is high.",
    "I use Turkey brand feed in turkey houses",
])
def test_one_capital_does_not_licence_every_lowercase_mention(message):
    """The capital is read AT THE MENTION, not anywhere in the message. English
    capitalises the first word of a sentence, so a message that opens by naming
    the country supplies its own licence for every lowercase mention after it.

    THE FIRST TWO ARE WHAT PIN THIS RULE: measured with the head noun already in
    place and the capital still tested whole-text, they resolved to 223 and 40,
    because `for feed` and `for sauce` put a preposition where the head noun
    would have been. The last two resolved to 223 on the same reading of the
    capital and are refused by the head noun as well, so they belong here for the
    shape rather than as the pin. "Turkey litter is cheap, how much should I
    spread" is an ordinary message for this assistant."""
    assert extract_country(message) is None


def test_a_refused_mention_does_not_eat_a_good_one_later():
    """Per-mention refusal has to keep WALKING, whichever rule did the refusing.
    `in turkey houses` fails both the head noun and the capital, and the branch
    must go on to the next occurrence rather than give the sentence up -
    stopping at the first match answered nothing here."""
    assert extract_country("I work in turkey houses but I am in Turkey") == TURKIYE


@pytest.mark.parametrize("message, code", [
    ("i am in peru", 170),
    ("perudayim", 170),
    ("Peru'dayım", 170),
    ("i am in cuba", 49),
])
def test_a_name_with_no_ambiguity_is_not_charged_for_one(message, code):
    """`peru` and `cuba` were gated on a capital with nothing to justify it -
    neither is an ordinary English noun. The first three resolved to nothing
    while they were listed, and `peru` is one key across both languages like
    `mali`, so the charge reached the Turkish branches too. The compound they do
    appear in, `Peru balsam`, is the head-noun rule's business."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message, code", [
    ("i am in india", INDIA),
    ("i am in panama", 166),
    ("i am in morocco", MOROCCO),
    ("i am in japan", 110),
])
def test_a_compound_only_hazard_is_closed_without_gating_the_name(message, code):
    """`India ink`, `Panama hats`, `Morocco leather` and `Japan wax` are all
    compound nouns of the hazardous shape, and the head-noun rule refuses all
    four (see the compound test above for the first two). None of these names is
    an ordinary English noun on its own, so none of them is gated on a capital -
    which is what adding them to the ambiguous list would have cost. Refusing at
    the right axis costs their lowercase typists nothing."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message, code", [
    ("Sudan'dayım", 276),
    ("I am in Sudan", 276),
])
def test_sudan_still_resolves_when_it_is_the_country(message, code):
    """`sudan` joined the ambiguous list because sudangrass is a standard forage
    and "the protein in sudan grass" resolved to 276 with the name lowercase and
    ungated. Like `Mali` it is one key across both languages, so the charge -
    pinned above as "sudanda yasiyorum" - reaches the Turkish branches too."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message, code", [
    ("I am in Turkey", TURKIYE),
    ("I live in Brazil", BRAZIL),
    ("my farm is in Guinea", 90),
    ("I am in Chile", 40),
    ("Mali'deyim", 133),
    ("Sudan'dayım", 276),
    ("TURKEY", TURKIYE),
])
def test_the_same_ambiguous_names_resolve_when_capitalised(message, code):
    """The other half, as always. All ten stay reachable - the rule asks for a
    capital letter, not for a different word. "TURKEY" counts: all-caps is a
    shout, not a common noun.

    `my farm is in Georgia` STOOD IN THIS LIST AND ASSERTED 73, and it is
    `Guinea` here now. The sentence shape is kept because it is the one this
    wave added to src/engine.py's `_SELF_EN`; the country is changed because
    `Georgia` is refused outright - see the test below."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message", [
    "my farm is in Georgia",
    "I farm in Georgia",
    "I am in Georgia",
    "we grow peanuts in Georgia",
    "the yield in Georgia peaches is high",
])
def test_the_english_georgia_is_refused_rather_than_placed(message):
    """`Georgia` is a top-ten US agricultural state and FAOSTAT has no US-state
    area, so an English-speaking grower who says his farm is in Georgia cannot
    be answered - and area 73 CAN be, which is the harm: he was handed Caucasian
    yields with nothing said. Same shape as the TRNC, same answer.

    The first of these was pinned the other way, as `("my farm is in Georgia",
    73)`, and it passed because src/engine.py's guard did not read `my farm is
    in` at all - so the wrong answer sat behind a branch that never fired. The
    wave that admitted that shape as a self-declaration had to decide this.

    The capital gate could never have helped: both readings are proper nouns and
    both are capitalised. The last sentence here resolved to 73 with the gate in
    place."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("Gürcistan'dayım", 73),
    ("Gürcistan'da yaşıyorum", 73),
    ("Gürcistan'da çiftçiyim", 73),
])
def test_the_turkish_georgia_still_resolves(message, code):
    """What makes the refusal above cheap: it is scoped to the ENGLISH spelling,
    so this product's primary user loses nothing. A Turkish speaker writes
    `Gürcistan`, and the US state has no Turkish name that collides with it."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message", [
    "I am in Indianapolis",
    "I am in Chadian territory",
    "we are in Guineafowl sheds",
])
def test_the_english_branch_still_ends_at_a_word_boundary(message):
    """Deleting the tail rule must not delete the word boundary with it. The
    tail rule's alternatives all required end-of-string, punctuation or a space,
    so the right-hand `(?!\\w)` was implicit; removing the rule outright would
    match `in India` inside "in Indianapolis" and `in Chad` inside "in Chadian".
    The lookbehind only guards the left edge."""
    assert extract_country(message) is None


def test_the_same_word_still_places_the_user_when_it_is_the_country():
    assert extract_country("I am in Turkey") == TURKIYE
    assert extract_country("Türkiye'deyim") == TURKIYE


@pytest.mark.parametrize("message", [
    "Kuzey Kıbrıs'tayım",
    "KKTC'deyim",
])
def test_northern_cyprus_is_refused_rather_than_placed(message):
    """FAOSTAT has no TRNC area, so the table cannot hold one. `Kıbrıs` fires
    inside `Kuzey Kıbrıs` under any boundary rule, which would hand a Turkish
    Cypriot grower — a likely user of this product — the Republic's yields
    while saying nothing. Refusing to place is the honest answer; the
    assistant then asks."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("Dominika'dayım", 55),
    ("Dominik Cumhuriyeti'ndeyim", 56),
    ("Nijer'deyim", 158),
    ("Nijerya'dayım", 159),
])
def test_a_longer_name_wins_over_the_shorter_one_inside_it(message, code):
    """`Dominik` sits inside `Dominika` and `Nijer` inside `Nijerya`, and the
    lenient suffix branch would accept the trailing letter as a case ending.
    `location.py` sorts its keys longest-first for exactly this and nothing
    pins that ordering; these four do."""
    assert extract_country(message) == code


def test_cyprus_itself_still_resolves():
    assert extract_country("Kıbrıs'tayım") == 50


def test_the_current_message_beats_history():
    history = [{"role": "user", "content": "Fransa'dayım"}]
    assert extract_country("Mısır'dayım", history) == EGYPT


def test_history_is_read_backwards_when_the_message_says_nothing():
    history = [
        {"role": "user", "content": "Fransa'dayım"},
        {"role": "assistant", "content": "Mısır'da durum farklı"},
    ]
    assert extract_country("peki gübre?", history) == FRANCE


def test_a_turkish_ending_on_an_english_spelling_is_not_a_location():
    """Found by sweeping all 246 crop labels through this module, and not in
    the plan's collision list: `İtalyan Çimi (Yemlik)` - Italian ryegrass - IS
    one of those labels, and the ENGLISH alias `Italy` plus the perfectly legal
    Turkish ending `-an` matched it, placing the grower in Italy. Turkish case
    endings only go on Turkish spellings, so the English ones no longer carry
    that branch."""
    assert extract_country("İtalyan çimi ektim, gübre önerir misiniz") is None


def test_italy_itself_still_resolves():
    """The other half, as always: the guard above must not cost the country.

    `Italy'deyim` is the case the guard actually endangered: the branch the fix
    touched is the Turkish suffix on an ENGLISH spelling, and the apostrophe is
    the one path that still carries it. The other three assertions test the
    Turkish spelling twice and an English preposition, none of which the fix
    goes near."""
    assert extract_country("İtalya'dayım") == ITALY
    assert extract_country("italyada yasiyorum") == ITALY
    assert extract_country("I am in Italy") == ITALY
    assert extract_country("Italy'deyim") == ITALY


@pytest.mark.parametrize("message", [
    "Franceda yasiyorum",
    "Germanyde yasiyorum",
    "Spaindeyim",
    "Cyprusta",
])
def test_the_italy_guard_costs_the_apostropheless_english_forms(message):
    """The guard is NOT free, and this pins what it charges. Gating the Turkish
    suffix branches on Turkish spellings killed the apostrophe-less Turkish
    ending on an English name; all four of these resolved before it. The trade
    is taken because a Turkish speaker writing without an apostrophe writes
    Fransa, Almanya, İspanya, Kıbrıs, while the crop collision the gate buys off
    was measured against real labels. Widening the `turkish` flag again would
    otherwise pass in silence."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("France'dayım", FRANCE),
    ("Italy'deyim", ITALY),
])
def test_the_apostrophe_path_is_not_gated(message, code):
    """The other direction of the same boundary: the apostrophe is an
    unambiguous proper-noun boundary, so it keeps the Turkish ending on an
    English spelling. Narrowing it would cost the commonest way a Turkish
    speaker writes a foreign country name."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message", [
    "we bought seed from India",
    "I buy eggs from Turkey.",
    "we import chicks from Turkey, mostly",
    "I came from Kenya",
])
def test_english_from_is_a_supplier_not_a_location(message):
    """`from X` marks where GOODS came from. All four resolved before this was
    fixed — India, Türkiye, Türkiye, Kenya — placing growers at their supplier.
    The compound-noun boundary is no defence: it stops `from turkey farms`, but
    a period, a comma or a closed-class word ends the phrase and the bare
    `from` match stands. Seed, chicks and litter cross borders constantly in
    this assistant's traffic, so this is the common case."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("I am from Kenya", KENYA),
    ("I'm from Brazil", BRAZIL),
    ("we are from Egypt", EGYPT),
    ("we're from France", FRANCE),
])
def test_from_still_places_the_user_when_it_predicates_the_user(message, code):
    """The boundary drawn around `from`: it is evidence only where it describes
    the USER rather than a purchase. An enumerated copula cannot be reached by
    any sentence about buying.

    `from` AND `-lı` HAVE SINCE PARTED COMPANY, and this docstring used to point
    at `-lı` as its twin. This function still RESOLVES "Hollandalıyım" - naming a
    country is what it is for - but engine's guard no longer places a speaker on
    it, because a nationality says where he is from. Whether `from` should follow
    it is open and recorded; see `_NATIONALITY_REFUSALS` in tests/test_engine.py."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message", [
    "Hollanda'dan tohum aldım",
    "Hollanda'dan gübre alıyoruz",
    "hollandadan tohum aldim",
])
def test_the_turkish_ablative_alone_is_a_supplier_not_a_location(message):
    """The Turkish twin of `from`, and the point where this module deliberately
    diverges from location.py. `-dan/-den` is the ablative, and for a COUNTRY it
    is overwhelmingly a purchase or an import. location.py keeps it because
    "İzmir'den geldim" usually is said by someone in İzmir's orbit and domestic
    sentences are rarely about importing; that twin is left alone."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message", [
    "Dominik Cumhuriyeti'nden tohum aldım",
    "Rusya Federasyonu'ndan tohum aldım",
    "Solomon Adaları'ndan fide aldım",
    "Birleşik Arap Emirlikleri'nden aldım",
    "Amerika Birleşik Devletleri'nden tohum aldım",
    "Fransız Polinezyası'ndan fide aldım",
    "Fildişi Sahili'nden kakao aldım",
    "Çin Anakarası'ndan gübre alıyoruz",
])
def test_the_ablative_with_a_buffer_n_is_also_a_supplier(message):
    """One per family shape, because the first version of the guard spelled
    exactly `dan|den|tan|ten` and every one of these walked straight through it:
    measured, 56, 185, 25 and 225 for the first four. Turkish puts a buffer `n`
    between a 3rd-person possessive and a case ending, so the ablative of
    `Dominik Cumhuriyeti` is `Cumhuriyeti'nden`, and 22 of the Turkish aliases
    are possessive-final compounds of exactly this kind. "Hollanda'dan tohum
    aldım" was refused correctly all along, which is why the gap hid."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("Dominik Cumhuriyeti'ndeyim", 56),
    ("Rusya Federasyonu'ndayım", 185),
    ("Solomon Adaları'ndayım", 25),
])
def test_the_buffer_n_locative_still_places_the_user(message, code):
    """The other side of the line: widening the lookahead to the buffer `n` must
    not swallow `-nda/-nde`, which is the locative on the same names and the
    ordinary way their growers say where they are."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message", [
    "Hollanda'danım",
    "Hollandalıyım",
    "Hollanda'dayım",
])
def test_the_ablative_still_places_the_user_when_it_predicates_the_user(message):
    """The other side of the line the test above draws. A bare ablative is
    refused; an ablative carrying a personal ending says where the user belongs,
    exactly as `-lı` and the locative do. The cost of drawing it here is real
    and named in country.py: "Hollanda'dan yazıyorum" is a genuine statement of
    location and is refused."""
    assert extract_country(message) == NETHERLANDS


@pytest.mark.parametrize("message, code", [
    ("I am in Turkey but I import seed from France", TURKIYE),
    ("Mısır'dayım ama Fransa'dan gübre alıyorum", EGYPT),
    ("Fransa'dan gübre alıyorum, ben Mısır'dayım", EGYPT),
])
def test_a_two_country_sentence_answers_the_user_not_the_supplier(message, code):
    """All three answered France before this was fixed. Two faults met here:
    `from`/`-dan` matched a supplier at all, and `_find` returned on the first
    key that matched ANYWHERE, so among the survivors the LONGER NAME won
    regardless of where in the sentence it sat."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message, code", [
    ("I am in Egypt and my brother is in France", EGYPT),
    ("I am in Chad but I sell in Kenya", 39),
    ("Fransa'dayım ama Mısır'da da tarlam var", FRANCE),
    ("Mısır'dayım, Fransa'da da tarlam var", EGYPT),
])
def test_the_earliest_country_wins_not_the_longest_named_one(message, code):
    """Position alone, with two countries that BOTH match by the same branch, so
    nothing but the ordering rule can decide. `Fransa` is longer than `Mısır`
    and `Kenya` longer than `Chad`, and under the old longest-first return each
    pair answered the same way whichever order the user wrote them in."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message, code", [
    ("I farm in Kenya today", KENYA),
    ("my field is in Egypt near the delta", EGYPT),
    ("I am in Egypt for farming", EGYPT),
    ("My farm is in Spain with clay soil", SPAIN),
    ("I am in Kenya, near Nakuru", KENYA),
])
def test_an_ordinary_english_sentence_still_resolves(message, code):
    """The recall half of the English branch. A tail rule enumerating the words
    allowed to follow a country name killed all five of these at one width and
    resolved `in turkey for feed` at the other; reading the capital letter
    instead costs neither.

    The old docstring here claimed Kenya, Brazil and Chad are held "only in
    English" and so have no second branch. Measured from `_FOLDED`, all three
    have a Turkish alias — `kenya`, `cad`, `brezilya` — and exactly ONE of the
    199 entries has an empty `tr` list: FAOSTAT's `China` aggregate, 351, whose
    `en` list is empty too. The claim was true of a spelling and false of a
    country."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message, code", [
    ("We are based in Brazil growing soy", BRAZIL),
    ("I am in Brazil growing soy", BRAZIL),
    ("I work in Kenya growing maize", KENYA),
])
def test_a_gerund_after_the_country_no_longer_costs_the_sentence(message, code):
    """The gerund refusal is GONE, and this pins that it went. The tail rule
    refused a present participle to keep out `turkey growing` and `turkey
    farming`, and charged every innocent sentence of the same shape for it —
    all three of these resolved to nothing. Capitalisation separates the two
    classes directly, so `in turkey growing` is still refused (see the lowercase
    test above) while these are not.

    A TRADE, not the "strict improvement" an earlier version of this docstring
    claimed. The same relaxation admitted "we work at Turkey farms" -> 223 and
    "I raise birds in Turkey houses" -> 223, which the tail rule had been
    refusing. The head-noun rule takes that half back and deliberately does not
    re-refuse the gerund: `growing` and `farming` are the same words as "I am in
    Turkey farming wheat", which is exactly the class being defended here."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message, code", [
    ("I'm from Turkey but I farm in Germany", 79),
    ("I am from Kenya but I live in France", FRANCE),
])
def test_a_stated_current_location_outranks_where_the_user_is_from(message, code):
    """`I am from X` is the weakest of the five branches and is read only when no
    `in`/`at` branch matched anywhere in the text. Both of these answered the
    ORIGIN once `from` was admitted — Türkiye and Kenya — because the copula sits
    earlier in the sentence than the `in`-clause and the earliest match wins.
    Preferring the later match instead would have sent "I am in Turkey but I
    import seed from France" back to France."""
    assert extract_country(message) == code


@pytest.mark.parametrize("message, code", [
    ("I am from Kenya", KENYA),
    ("I am from Morocco originally", MOROCCO),
])
def test_origin_alone_still_places_the_user(message, code):
    """Ranking origin below `in`/`at` must not demote it out of existence: with
    no other branch matching, there is nothing to outrank it. The second
    sentence was dead under the tail rule, whose adverb list had `already`,
    `still` and `mostly` but not `originally` — one of the six ordinary
    sentences that rule was costing, where the fix report counted five."""
    assert extract_country(message) == code


def test_naming_the_trnc_refuses_the_whole_message():
    """The refusal is message-wide, not location-scoped: the user plainly said
    France, and still gets nothing. Accepted because the mention cannot be told
    apart from a statement of location without parsing the sentence, the failure
    is in the safe direction, and such messages are rare. Pinned so the cost is
    visible rather than discovered."""
    assert extract_country("KKTC'de fiyatlar nasıl, ben Fransa'dayım") is None


def test_an_assistant_turn_is_never_evidence():
    history = [{"role": "assistant", "content": "Fransa'da buğday verimi yüksektir"}]
    assert extract_country("peki bizde?", history) is None


@pytest.mark.parametrize("message", [
    "Dominika'dan tohum aldım",
    "Dominika'den tohum aldım",
    "Nijerya'dan tohum aldım",
    "Nijerya'den tohum aldım",
])
def test_a_shorter_key_cannot_eat_a_longer_name_and_miss_its_ablative(message):
    """The worst shape this module can produce: a purchase read as a location
    AND as the wrong country.

    `dominik` matched inside `Dominika` by eating the trailing `a` as a case
    suffix and stopping at the apostrophe, so it never reached the `'dan` that
    the ablative guard refuses — answering 56 Dominican Republic for a sentence
    about buying seed from 55 Dominica. Same shape for `nijer` inside `Nijerya`.
    Measured across every alias in an ablative purchase frame: 452 refused
    correctly, these four were the whole of the damage."""
    assert extract_country(message) is None


@pytest.mark.parametrize("message, code", [
    ("Dominika'dayım", 55),
    ("Nijerya'dayım", 159),
])
def test_the_apostrophe_guard_does_not_cost_the_genuine_locative(message, code):
    """The other half. Turkish attaches the apostrophe BEFORE the suffix on a
    proper noun, so refusing a suffix match that runs into one loses nothing."""
    assert extract_country(message) == code


@pytest.mark.parametrize("apostrophe", ["'", "\u2019", "\u2018", "\u02bc"])
def test_the_ablative_guard_holds_on_a_typographic_apostrophe(apostrophe):
    r"""The guard is spelled with an ASCII apostrophe — `(?!['\w])` — and only
    reaches a phone's apostrophe because `_TR_FOLD` in src/engine.py folds
    U+2019, U+2018 and U+02BC to ASCII before any branch runs.

    That coupling crosses a module boundary and nothing pinned it: the guard
    lives here, the fold that feeds it lives in the engine, and the engine's
    comment justifies the mapping by the PROVINCE matcher's apostrophe rule,
    which predates this guard. Drop a mapping there, or respell the guard with a
    literal `'`, and the two-fault bug returns on the delivery surface only —
    iOS and Android Turkish layouts emit U+2019, so the desktop demo would keep
    passing while every phone read a purchase as a location and named the wrong
    country. Measured: all four spellings refuse the supplier and keep the
    locative."""
    for name, code in (("Dominika", 55), ("Nijerya", 159)):
        assert extract_country(f"{name}{apostrophe}dan tohum aldım") is None
        assert extract_country(f"{name}{apostrophe}dayım") == code


def test_the_substring_pair_count_the_ordering_is_justified_by():
    """Pins the two figures the longest-first comment rests on, so they cannot
    go stale the way they already did once.

    Both read 34 until 2026-10-02, and no counting basis of the shipped table
    gives 34: there are 78 substring pairs, 35 of which name two DIFFERENT
    countries - and only those 35 let the ordering decide an answer rather than
    a spelling. The table had not drifted, so 34 was never right.

    If a new alias moves either number, update the comment above `_ORDERED` and
    the `_matchers` docstring in the same commit. Keeping those two prose claims
    honest is what this test is for, not the particular integers."""
    from src.context.country import _FOLDED

    keys = list(_FOLDED)
    pairs = [(lo, sh) for lo in keys for sh in keys if sh != lo and sh in lo]
    differ = [p for p in pairs if _FOLDED[p[0]][0] != _FOLDED[p[1]][0]]
    assert len(pairs) == 78
    assert len(differ) == 35


def test_area_zero_would_be_an_answer_not_a_miss(monkeypatch):
    """`extract_country` returned an FAO area code through a truthiness test, so
    area 0 would have been read as "nobody said where they are" and fallen
    through to the history walk - and then to None.

    No shipped table holds area 0, so this is a pin on the CONTRACT rather than
    on a live defect: the function returns a code or None, and 0 is a code. Both
    call sites are covered - the current message and a history turn."""
    import src.context.country as country_ctx

    monkeypatch.setattr(country_ctx, "_find", lambda folded, original: 0)
    assert extract_country("Fransa'dayım") == 0

    calls = []

    def only_history(folded, original):
        calls.append(folded)
        return 0 if len(calls) > 1 else None

    monkeypatch.setattr(country_ctx, "_find", only_history)
    assert extract_country("buğday mı ekmeliyim",
                           [{"role": "user", "content": "Fransa'dayım"}]) == 0


def test_the_capital_gate_on_chad_and_jordan_costs_their_lowercase_typists():
    """A LEAD PINNED AS A COST, so the next wave to pick it up starts from a
    measurement rather than from prose. `chad` and `jordan` sit in
    `_AMBIGUOUS_EN` on a weaker claim than the other eight: they are proper
    nouns of OTHER referents - a given name, a surname - so a capital letter
    cannot separate them from the country, and measured, it does not try.

    What the gate costs is here: the lowercase English self-declaration. What it
    buys is nothing reachable - "Jordan said the yield in Jordan is low"
    resolves, but `extract_country`'s one caller sits behind
    `engine._states_location`, which refuses that sentence outright.

    KEPT ANYWAY, and the reason is process rather than measurement: removing
    these two WIDENS this module's recall, and the wave that wrote this test
    deleted five rules from the guard that reads it. Three earlier waves on this
    branch widened and narrowed in the same commit and each one reopened a class
    it had just closed."""
    assert extract_country("I am in Jordan") == 112
    assert extract_country("I am in Chad") == 39
    assert extract_country("i am in jordan") is None
    assert extract_country("i am in chad") is None
    # And the misreading the gate exists for is held by the guard, not here.
    from src import engine
    assert extract_country("Jordan said the yield in Jordan is low") == 112
    assert not engine._states_location("Jordan said the yield in Jordan is low",
                                       engine._code_aliases(112))
