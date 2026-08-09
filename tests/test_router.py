"""Rule-layer routing. Deterministic: no LLM, no network."""

import pytest

from src.router import classify_by_rules


@pytest.mark.parametrize("query", [
    "5 dönüm domates ektim 1 milyon masraf ettim, ne kadar kâr ederim?",
    "Buğday ekmenin dekara maliyeti nedir?",
    "Serada domates yetiştirmek kârlı mı?",
    "Girdi masraflarım ne kadar olur?",
])
def test_budget_queries(query):
    assert classify_by_rules(query) == "budget"


@pytest.mark.parametrize("query", [
    "Bu karar doğru mu?",
    "Karnabahar nasıl yetiştirilir?",
    "Toprak karışımı nasıl hazırlanır?",
])
def test_short_stem_kar_does_not_leak(query):
    # 'kâr' folds to 'kar', which prefixes karar/karnabahar/karışım. Matching it
    # as a stem would route all three to budget.
    assert classify_by_rules(query) != "budget"


@pytest.mark.parametrize("query", [
    "Domatese ne zaman gübre vermeliyim?",
    "Buğdayda azotu hangi dönemde uygulamalıyım?",
    "Fındık için gübreleme takvimi çıkarır mısın?",
])
def test_fert_plan_needs_both_nutrition_and_time(query):
    assert classify_by_rules(query) == "fert_plan"


@pytest.mark.parametrize("query", [
    "Domates yapraklarım sararıyor, ne önerirsiniz?",
    "Evde kompost nasıl yapılır?",
])
def test_nutrition_without_time_is_not_fert_plan(query):
    assert classify_by_rules(query) != "fert_plan"


@pytest.mark.parametrize("query", [
    "Bu yıl tarlama ne eksem iyi olur?",
    "Bu sezon ne ekmek mantıklı?",
])
def test_crop_choice(query):
    assert classify_by_rules(query) == "crop_choice"


@pytest.mark.parametrize("query", [
    "İneklerimin sütü azaldı, ne yapmalıyım?",
    "Traktörümün motoru çalışmıyor, ne yapmalıyım?",
    "Yarın hangi takım maç yapıyor?",
])
def test_obvious_offscope(query):
    assert classify_by_rules(query) == "offscope"


def test_short_stem_mac_does_not_leak():
    # 'maç' folds to 'mac', which prefixes 'macar'. Macar fiği is a forage legume,
    # a perfectly in-scope plant topic.
    assert classify_by_rules("Macar fiği ekimi nasıl yapılır?") != "offscope"


def test_unknown_returns_none():
    assert classify_by_rules("Asmada budama ne zaman yapılır?") is None


@pytest.mark.parametrize("query", [
    "Bitkilerde demir eksikliği nasıl giderilir?",
    "Yaprak bitleri buğdaya zarar verir mi?",
    "Don zararı gören fidanlar kurtarılır mı?",
    "Elma ağacım ne zaman meyveye gelir?",
    "Bu hastalık kendiliğinden geçip gider mi?",
])
def test_budget_stems_do_not_leak_plant_questions(query):
    # 'gider'/'zarar'/'gelir' are high-frequency non-financial agriculture
    # words. Matching them as budget stems misrouted plant questions.
    assert classify_by_rules(query) != "budget"


@pytest.mark.parametrize("query", [
    "Malç filmi serada nasıl kullanılır?",
    "Fide takımı nasıl hazırlanır?",
])
def test_offscope_stems_do_not_leak_horticulture(query):
    # 'film' prefixes plastic mulch film and 'takim' means set/kit as often
    # as sports team; both are ordinary horticulture vocabulary.
    assert classify_by_rules(query) != "offscope"
