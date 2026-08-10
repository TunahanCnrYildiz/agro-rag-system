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
