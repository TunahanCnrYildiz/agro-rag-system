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
    and `_ORDERED` is sorted by length - so a sentence naming two provinces was
    decided by which name had more letters. Measured 2026-09-25:
    `extract_province("Van'dayım ama Ankara'dan aldım")` answered **Ankara**.

    WHY IT IS WORTH A TEST OF ITS OWN: `extract_province` feeds the budget card's
    prefill and the comparison card, so a Konya grower writing the second sentence
    got Adana's yields and prices filled into a form, with nothing in the answer
    saying which province the numbers came from.

    Measured over every ordered pair of the 81 provinces in three frames, 19 440
    sentences: before this fix 9 720 of them answered the province the user
    stated - exactly half, which is what "the longer name wins" predicts on
    ordered pairs - and after it, all 19 440 do."""
    assert extract_province(text) == expected


@pytest.mark.parametrize("text,expected", [
    # Position ties: both names start at the same offset and the longer one must
    # keep it. `Van` is inside no other province, but `Kars` opens
    # `Karsiyaka`-shaped folds and `Afyonkarahisar` opens nothing - the real ties
    # are names that are prefixes of other names.
    ("Kahramanmaraş'ta zeytin yetiştiriyorum", "Kahramanmaraş"),
    ("Afyonkarahisar'dayım", "Afyonkarahisar"),
    # Leading whitespace and a quote mark: the bare-name branch reports the
    # position of the first LETTER, not of the string.
    ("  Manisa", "Manisa"),
    ('"Manisa"', "Manisa"),
])
def test_a_tie_on_position_keeps_the_longer_name(text, expected):
    """Candidates are tried longest-first and a later one has to be STRICTLY
    earlier to win, so a short name sharing a position with a long one cannot
    displace it. Without that, `Kars` would answer for `Kahramanmaraş` - both
    begin at offset 0 once folded."""
    assert extract_province(text) == expected


def test_every_province_wins_against_every_other_when_stated_first():
    """The class, derived from `PROVINCES` rather than enumerated, so adding a
    province cannot leave a hole here. Each province is paired with a fixed
    counterpart in both directions: whichever is stated first is the answer,
    regardless of which name is longer.

    One counterpart rather than all 80, because the full 19 440-sentence sweep
    that measured this fix takes about fifteen seconds and this suite runs on
    every commit. The sweep's result is quoted in
    `test_the_province_the_user_states_beats_the_longer_name`."""
    for province in PROVINCES:
        other = "Kahramanmaraş" if province != "Kahramanmaraş" else "Van"
        assert extract_province(f"{province}'dayım ama {other}'dan aldım") == province
        assert extract_province(f"{other}'dayım ama {province}'dan aldım") == other


@pytest.mark.parametrize("text", [
    "Ankara'dan aldım",
    "Adana'dan fide getirdim",
])
def test_the_bare_ablative_still_places_the_user_and_that_is_open(text):
    """PINNED AS A KNOWN GAP, NOT AS CORRECT BEHAVIOUR. `_SUFFIX` admits the
    ablative, so a sentence that says where the SEED came from places the user
    there. The country twin refuses this shape - `_NOT_ABLATIVE` in
    src/context/country.py - and this side deliberately still does not.

    It was left out of the commit that fixed the position bug because position
    and suffix are two different decisions: narrowing a shipped surface in the
    same breath as reordering it is how the country guard earned seven review
    rounds. This test exists so the next reader finds the gap measured rather
    than discovering it."""
    assert extract_province(text) is not None
