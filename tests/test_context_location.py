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
