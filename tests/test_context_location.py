"""Province extraction. Pure: no network, no state - history is re-read per call."""

import pytest

from src.context.location import PROVINCES, extract_province


def test_all_81_provinces_present():
    assert len(PROVINCES) == 81
    assert len(set(PROVINCES)) == 81


@pytest.mark.parametrize("text,expected", [
    ("Manisa'dayım, domatese ne zaman gübre vermeliyim?", "Manisa"),
    ("manisada bağım var", "Manisa"),
    ("MANİSA", "Manisa"),
    ("Kahramanmaraş'ta zeytin yetiştiriyorum", "Kahramanmaraş"),
    ("Şanlıurfa'da buğday ektim", "Şanlıurfa"),
    ("Afyonkarahisar", "Afyonkarahisar"),
])
def test_extracts_inflected_and_folded_forms(text, expected):
    assert extract_province(text) == expected


@pytest.mark.parametrize("text", [
    "Domatese ne zaman gübre vermeliyim?",
    "Bafra'da fındık yetiştiriyorum",          # district, not a province
])
def test_returns_none_when_no_province(text):
    assert extract_province(text) is None


@pytest.mark.parametrize("text", [
    "Serada vantilatör kullanmalı mıyım?",     # 'Van' inside vantilatör
    "Karşı taraftaki tarlada ne var?",         # 'Kars' + folded ı inside karşı
    "Musluk suyuyla sulama yapılır mı?",       # 'Muş' inside musluk
    "Bu karar doğru mu?",                      # 'Kars' must not reach here either
])
def test_short_province_names_do_not_leak(text):
    # Four-letter provinces (Van, Kars, Muş, Rize, Bolu, Ordu, Uşak, Siirt) are
    # the same short-stem trap the router hit five times. These are the spec:
    # tighten the matcher until they pass, never delete the case.
    assert extract_province(text) is None


def test_history_is_used_when_the_message_has_none():
    history = [{"role": "user", "content": "Manisa'dayım"},
               {"role": "assistant", "content": "Anladım."}]
    assert extract_province("Peki ne zaman gübre vereyim?", history) == "Manisa"


def test_current_message_wins_over_history():
    history = [{"role": "user", "content": "Manisa'dayım"}]
    assert extract_province("Aslında Aydın'dayım", history) == "Aydın"


def test_most_recent_history_mention_wins():
    history = [{"role": "user", "content": "Manisa'dayım"},
               {"role": "user", "content": "Aydın'a taşındım"}]
    assert extract_province("Ne zaman gübre vereyim?", history) == "Aydın"


def test_does_not_match_inside_a_longer_word():
    # 'Van' must not fire inside 'vantilatör'.
    assert extract_province("Serada vantilatör kullanmalı mıyım?") is None


@pytest.mark.parametrize("text", [
    # Turkish produce is named after provinces, and in an agriculture assistant
    # the produce is the SUBJECT of the question, not the user's address. Matching
    # here sends the model another province's real weather forecast.
    "Trabzon hurmasına ne zaman gübre vermeliyim?",
    "Amasya elmasına ne zaman gübre atmalıyım?",
    "Malatya kayısısına ne zaman gübre verilir?",
    "Isparta gülüne ne zaman gübre verilir?",
    "Aydın incirine hangi dönemde gübre verilir?",
    "Ankara armuduna hangi ayda gübre verilir?",
    "Trabzon hurması yetiştirmek istiyorum",
    "Bu ağaç Amasya elması",
])
def test_produce_named_after_a_province_is_not_a_location(text):
    assert extract_province(text) is None


@pytest.mark.parametrize("text", [
    "Musa Bey ne zaman gübre versin?",      # 'Muş' + a
    "Sulama vanası arızalandı",             # 'Van' + a - a valve, in an irrigation answer
    "Vanayı kapatmayı unuttum",
    "Aydınlatma bitkiyi etkiler mi?",       # 'Aydın' + latma
])
def test_short_names_do_not_leak_into_ordinary_words(text):
    assert extract_province(text) is None


@pytest.mark.parametrize("text,expected", [
    # The context block tells the model to ASK which province. These are what a
    # Turkish speaker actually replies. Every one of them used to return None.
    ("Manisadayım", "Manisa"),
    ("İzmirdeyim", "İzmir"),
    ("Konyadayım", "Konya"),
    ("Rizedeyim", "Rize"),
    ("Manisalıyım", "Manisa"),
    ("Bursalıyım", "Bursa"),
    ("Vanlıyım", "Van"),
    ("Van", "Van"),
    ("Rize", "Rize"),
    ("Bolu", "Bolu"),
    ("Manisa.", "Manisa"),
    ("Manisa ilindeyim", "Manisa"),
    ("Trabzon ili", "Trabzon"),
])
def test_the_answers_the_assistant_asks_for_are_understood(text, expected):
    assert extract_province(text) == expected


def test_a_bare_province_reply_is_picked_up_from_history():
    # The assistant asked; the user answered with one word; the next turn must know.
    history = [{"role": "assistant", "content": "Hangi ildesiniz?"},
               {"role": "user", "content": "Van"}]
    assert extract_province("Peki ne zaman gübre vereyim?", history) == "Van"


@pytest.mark.parametrize("text,expected", [
    ("Vanda kayısı yetiştiriyorum", "Van"),
    ("Siirtte fıstık var", "Siirt"),
    ("Rizede çay bahçem var", "Rize"),
])
def test_locative_forms_of_short_provinces_still_work(text, expected):
    assert extract_province(text) == expected


@pytest.mark.parametrize("text,expected", [
    # MOBILE KEYBOARDS EMIT U+2019, not the ASCII apostrophe. Both real clients are
    # mobile/web and pass the text through unmodified, so a matcher that only knows
    # ' passes every desktop demo while failing the primary client.
    ("Manisa’dayım, domatese ne zaman gübre vermeliyim?", "Manisa"),
    ("Manisa’da bağım var", "Manisa"),
    ("Kahramanmaraş’ta zeytin yetiştiriyorum", "Kahramanmaraş"),
    ("Aydın’dayım", "Aydın"),
])
def test_the_smart_apostrophe_is_understood(text, expected):
    assert extract_province(text) == expected


@pytest.mark.parametrize("text,expected", [
    # Province + place noun is how growers actually say where they are. Requiring a
    # case suffix on the province alone missed every one of these.
    ("Diyarbakır koşullarında hangi aspir çeşidi önerilir?", "Diyarbakır"),
    ("Antalya koşullarında hangi anaç önerilir?", "Antalya"),
    ("Erzurum yöresinde hangi ahududu çeşidi iyi adapte olur?", "Erzurum"),
    ("Manisa civarında bağ var", "Manisa"),
    ("Antalya bölgesinde sera işletiyorum", "Antalya"),
    ("İzmir tarafında seram var", "İzmir"),
])
def test_a_place_noun_makes_a_bare_province_unambiguous(text, expected):
    assert extract_province(text) == expected


def test_the_place_noun_rule_does_not_rescue_a_produce_name():
    # The noun must follow the province IMMEDIATELY. Here the produce is in between,
    # so this stays a question ABOUT Trabzon persimmon, not a user in Trabzon.
    assert extract_province("Trabzon hurması bölgemizde yetişir mi?") is None


@pytest.mark.parametrize("text", [
    # `il\w*` swallows two of the commonest words in Turkish plus everyday
    # agriculture vocabulary. The "il" alternatives must stay ENUMERATED.
    "Trabzon ile Rize arasında hangi çeşit yetişir?",
    "Trabzon ilaçlama zamanı ne zaman gübre verilir?",
    "Ankara ilk defa gübre vereceğim",
    "Ordu ilgili bir soru soracağım",
    "Amasya ilave gübre ister mi?",
    "Manisa iletişim bilgileri",
    "Isparta gülü ilaçlaması ne zaman?",
    "Amasya elması ilkbaharda budanır mı?",
    "Ankara armudu ile Deveci armudu arası fark ne?",
])
def test_the_place_noun_rule_does_not_swallow_ordinary_words(text):
    assert extract_province(text) is None


@pytest.mark.parametrize("text,expected", [
    # _ORDERED is longest-first, so a spurious hit on a LONG province name would be
    # returned before a genuine apostrophe statement of a shorter one is ever tried.
    # The user says explicitly that the other province is not what they mean.
    ("Kahramanmaraş ile ilgili değil, Van'dayım, ne zaman gübre vermeliyim?", "Van"),
    ("Afyonkarahisar ilk sorum değildi; Manisa'dayım", "Manisa"),
    ("Diyarbakır ilgisi yok, Rize'deyim", "Rize"),
])
def test_a_spurious_long_name_does_not_shadow_a_real_statement(text, expected):
    assert extract_province(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Konya ovasında buğday ekiyorum", "Konya"),
    ("Konya ovalarında buğday ekiyorum", "Konya"),   # plural was missed before
    ("Manisa ilçesinde bağ var", "Manisa"),
])
def test_place_noun_inflections_are_covered(text, expected):
    assert extract_province(text) == expected


@pytest.mark.parametrize("text,expected", [
    # The sentence recorded in the bug note, measured 2026-09-25.
    ("Van'dayım ama Ankara'dan aldım", "Van"),
    # The one that costs money: the budget card prefills from this.
    ("Konya'dayım ama Adana'dan fide aldım", "Konya"),
    ("İzmir'deyim ama Afyonkarahisar'dan aldım", "İzmir"),
    ("Manisa'dayım, Kahramanmaraş'ta fiyatlar nasıl", "Manisa"),
    # The second province is named with a place noun rather than a suffix.
    ("Rize'deyim, Diyarbakır bölgesinde ne ekilir", "Rize"),
])
def test_the_province_the_user_states_beats_the_longer_name(text, expected):
    """THE EARLIEST MENTION WINS, NOT THE LONGEST NAME.

    `_find` used to return on the first key in `_ORDERED` that matched anywhere,
    and `_ORDERED` is length descending with ties broken by the order of
    `PROVINCES` - so a sentence naming two provinces was decided by which name
    had more letters, or, when they had the same number, by which one the table
    lists first. Measured 2026-09-25:
    `extract_province("Van'dayım ama Ankara'dan aldım")` answered **Ankara**.

    Over 25 920 two-province sentences the old code answered the strictly longer
    name 21 760 times, the strictly shorter one 0 times, and in 4 160 the two
    names fold to equal length and table order decided. `Konya` and `Adana` are
    one of those 4 160 - both fold to five characters, and Adana is
    `PROVINCES[0]` - so the second sentence here is NOT an instance of "the
    longer name won"; it is an instance of the table deciding.

    WHY IT IS WORTH A TEST OF ITS OWN: `extract_province` feeds the budget card's
    prefill and the comparison card, so a Konya grower writing the second sentence
    got Adana's yields and prices filled into a form, with nothing in the answer
    saying which province the numbers came from.

    THE HEADLINE IS IN `test_both_word_orders_answer_the_stated_province`, not
    here: these five sentences all state the location FIRST, which is the half of
    the population that position alone fixes."""
    assert extract_province(text) == expected


@pytest.mark.parametrize("text,expected", [
    # The longest names, each standing alone - they must not be displaced by a
    # shorter key, and nothing else in these sentences can match.
    ("Kahramanmaraş'ta zeytin yetiştiriyorum", "Kahramanmaraş"),
    ("Afyonkarahisar'dayım", "Afyonkarahisar"),
    # The bare-name branch reports offset 0 whatever the message opens with.
    ("  Manisa", "Manisa"),
    ('"Manisa"', "Manisa"),
])
def test_a_long_name_is_not_displaced_by_a_shorter_key(text, expected):
    """THE TIE-BREAK THESE CASES LOOK LIKE IS DEAD CODE HERE, and this test is
    named for what it actually covers.

    An earlier docstring claimed `Kars` would answer for `Kahramanmaraş` because
    "both begin at offset 0 once folded". Measured: `_normalize_tr` gives
    `'kahramanmaras'` and `'kars'`, and `'kahramanmaras'.startswith('kars')` is
    False. Exactly one key matches at offset 0 of that sentence. Two keys can
    only tie on position if one is a PREFIX of the other, and no folded province
    name is a prefix of another (0 pairs; `mus` is inside `gumushane` but not at
    its start). Relaxing `start < best_start` to `<=` leaves the whole suite
    green and changes 0 of 53 140 answers.

    The strict comparison stays because `country.py` shares this code shape and
    there it IS live (`Dominik`/`Dominika`, `Nijer`/`Nijerya`). What is pinned
    here is only that these four messages answer these four provinces."""
    assert extract_province(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Konya ovasındayım, Adana'ya göre geç oluyor, Konya'da kar var", "Konya"),
    ("Rize yöresindeyim, Diyarbakır'a göre çok yağış var, Rize'de ne ekilir?",
     "Rize"),
    ("Antalya bölgesindeyim, Mersin'e göre nasıl, Antalya'da sera var",
     "Antalya"),
])
def test_the_earliest_of_a_key_s_own_branches_is_the_one_that_counts(text, expected):
    """THE LIVE COMPARISON INSIDE `_find`, which nothing else pins.

    One key can match several of the three branches at different offsets, and
    `found < start` keeps the earliest of them. In the first sentence `konya`
    matches the place-noun branch at offset 0 and the apostrophe branch near the
    end, while `adana` matches once in between: taking the per-branch MAXIMUM
    instead answers Adana, and mutating `found < start` to `found > start`
    changes 6 480 answers in the sweep while leaving every other test green.

    Each of the three answers a DIFFERENT province under that mutation - Adana,
    Diyarbakır, Mersin - so none of them passes by accident, and all three are
    sentences a grower could write: the second province is named with `-a göre`
    ("compared to"), which is not an ablative and so is not what `_NOT_ABLATIVE`
    refuses."""
    assert extract_province(text) == expected


def test_both_word_orders_answer_the_stated_province():
    """THE HEADLINE, and it is a NET number over both halves of the population.

    Position alone answers the stated province when the user states it first and
    the SUPPLIER, every time, when the user states the purchase first - which is
    equally ordinary Turkish. Measured over every ordered pair of the 81
    provinces in four frames, 6 480 pairs each, 25 920 sentences:

        {loc}'dayım ama {sup}'dan aldım     old 3240 -> 6480
        {loc}'dayım, {sup}'dan fide aldım   old 3240 -> 6480
        {sup}'dan aldım ama {loc}'dayım     old 3240 -> 6480
        {sup}'dan fide aldım, {loc}'dayım   old 3240 -> 6480

    Net 12 960/25 920 before, 25 920/25 920 after. With earliest-wins but no
    `_NOT_ABLATIVE` the two bottom frames go to 0/6 480 and the net stays
    12 960 - which is why both rules ship together.

    Four frames x one counterpart rather than the full sweep, because the sweep
    takes about fifteen seconds and this suite runs on every commit; the
    counterpart is derived from `PROVINCES`, so adding a province cannot leave a
    hole. It covers 160 of the 6 480 ordered pairs. `Kahramanmaraş` is the second
    longest folded name, so for 79 of the 81 provinces both directions put the
    longer name in the same place - this test pins the class cheaply, and the
    numbers above are where the coverage claim lives."""
    for province in PROVINCES:
        other = "Kahramanmaraş" if province != "Kahramanmaraş" else "Van"
        for loc, sup in ((province, other), (other, province)):
            assert extract_province(f"{loc}'dayım ama {sup}'dan aldım") == loc
            assert extract_province(f"{sup}'dan fide aldım, {loc}'dayım") == loc


@pytest.mark.parametrize("text", [
    "Ankara'dan aldım",
    "Adana'dan fide getirdim",
    "Antalya'dan tohum aldım",
    # No apostrophe: `_SUFFIX` spells the ablative there too.
    "Ankaradan aldım",
    # The ablative with nothing else in the sentence to go on.
    "Kahramanmaraş'dan fide aldım ama nerede ekeceğimi bilmiyorum",
])
def test_the_bare_ablative_does_not_place_the_user(text):
    """A SENTENCE ABOUT WHERE THE SEED CAME FROM IS NOT A LOCATION. This is the
    `_NOT_ABLATIVE` half of the change; the position half is above.

    Returning None here is the point: `src/engine.py` finds no national row for a
    Turkish user in data/crop_norms.json, so the assistant ASKS which province
    instead of prefilling the budget card from the supplier's."""
    assert extract_province(text) is None


@pytest.mark.parametrize("text,expected", [
    # An ablative carrying a personal ending says where the user BELONGS, and the
    # trailing `(?!\w)` inside _NOT_ABLATIVE is what tells the two apart.
    ("Ankara'danım", "Ankara"),
    ("Manisa'danım, serada domates yetiştiriyorum", "Manisa"),
    # And the locative, which shares the first two letters with the ablative.
    ("Ankara'dayım", "Ankara"),
    ("Ankara'da bağım var", "Ankara"),
    ("Ankarada bağım var", "Ankara"),
    ("Ankaralıyım", "Ankara"),
])
def test_the_ablative_guard_keeps_the_forms_that_do_state_a_location(text, expected):
    assert extract_province(text) == expected


@pytest.mark.parametrize("text", [
    "İzmir'den geldim",
    "Manisa'dan yazıyorum",
])
def test_the_price_of_the_ablative_guard_is_a_refused_location(text):
    """THE COST, PINNED SO IT CANNOT BE FORGOTTEN. These two really do state a
    location and are now refused. Measured over the 81 provinces: "{p}'dan
    yazıyorum" and "{p}'den geldim" went 81/81 placed to 0/81.

    The twin writes the same cost for "Hollanda'dan yazıyorum", and the province
    case is the weaker of the two - "İzmir'den geldim" is more often said near
    İzmir than its country equivalent. It buys off a systematic error in the
    other direction, and a refusal costs a question while a supplier silently
    fills the budget card with the wrong province's figures."""
    assert extract_province(text) is None


def test_a_province_ablative_no_longer_swallows_a_stated_country():
    """THE WORLD LAYER THIS OPENS. `src/engine.py` reads `_country_lines` only
    when `extract_province` comes back empty, so a Turkish province name in a
    foreign grower's sentence used to decide the whole turn - and earliest-wins
    could not help, because there is only one province in it.

    Measured over the 81 provinces against five countries in both word orders:
    81/81 placed in a Turkish province before, 81/81 reaching the country's
    FAOSTAT figures now."""
    for province in PROVINCES:
        assert extract_province(f"Hollanda'dayım ama {province}'dan fide aldım") is None
        assert extract_province(f"{province}'dan fide aldım, Hollanda'dayım") is None


@pytest.mark.parametrize("text,expected", [
    ("'Van' Kahramanmaraş'tayım", "Van"),
    ('"Van" Kahramanmaraş\'tayım', "Kahramanmaraş"),
])
def test_a_single_quoted_name_beats_a_later_statement_and_that_is_open(text, expected):
    """PINNED AS A MEASURED DEFECT, NOT AS CORRECT BEHAVIOUR - and pinned on the
    shape that actually moved, which the gap test this replaces did not.

    The apostrophe branch cannot tell a closing single quote from a Turkish
    case-suffix apostrophe, so a quoted name matches as if it were a statement,
    and earliest-wins hands it the sentence. Measured over the ordered pairs:
    "'{q}' {loc}'dayım" went 3 240/6 480 to 0/6 480. Double quotes are
    unaffected, 6 480/6 480 in both revisions, because `"` is not what the branch
    reads.

    NOT CLOSED HERE because `country.py`'s apostrophe branch is identical, and
    narrowing one side only would reopen the divergence this change exists to
    remove. Sized and left open: a grower quoting a province name is rare, and
    the cost is one turn's wrong province."""
    assert extract_province(text) == expected
