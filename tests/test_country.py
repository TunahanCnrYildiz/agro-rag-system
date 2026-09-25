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
    """The other half, as always: the guard above must not cost the country."""
    assert extract_country("İtalya'dayım") == ITALY
    assert extract_country("italyada yasiyorum") == ITALY
    assert extract_country("I am in Italy") == ITALY


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
    any sentence about buying. This is the English twin of `-lı` in the Turkish
    suffix, which already accepts "Hollandalıyım" as a statement of location."""
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


def test_an_assistant_turn_is_never_evidence():
    history = [{"role": "assistant", "content": "Fransa'da buğday verimi yüksektir"}]
    assert extract_country("peki bizde?", history) is None
