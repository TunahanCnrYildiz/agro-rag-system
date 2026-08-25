"""Rule-layer routing. Deterministic: no LLM, no network."""

import pytest

from src import router
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


@pytest.mark.parametrize("query", [
    "İnek gübresi nasıl kullanılır?",
    "Koyun gübresi hangi bitkilerde kullanılır?",
    "Tavuk gübresi bitkilere zarar verir mi?",
    "Traktörle gübre atarken nelere dikkat etmeliyim?",
])
def test_nutrition_stems_do_not_leak_to_offscope(query):
    # These carry a nutrition stem ('gubre') but no time stem, so fert_plan's
    # AND-gate does not fire. Without a carve-out they fell through to offscope,
    # where 'inek'/'koyun'/'tavuk'/'traktor' matched. Animal manure is ordinary
    # organic-fertilizer vocabulary; it must not be misrouted just because the
    # animal is also named. See routing review, finding 3.
    assert classify_by_rules(query) != "offscope"


@pytest.mark.parametrize("query", [
    "İnek gübresi nasıl kullanılır?",
    "Koyun gübresi hangi bitkilerde kullanılır?",
    "Tavuk gübresi bitkilere zarar verir mi?",
    "Traktörle gübre atarken nelere dikkat etmeliyim?",
])
def test_nutrition_stems_route_to_nutrition(query):
    assert classify_by_rules(query) == "nutrition"


def test_livestock_without_nutrition_stays_offscope():
    # No nutrition stem here, so the carve-out must not fire and the livestock
    # stem must still route this to offscope.
    assert classify_by_rules("İneklerimin sütü azaldı, ne yapmalıyım?") == "offscope"


@pytest.mark.parametrize("query", [
    "İneklerimi nasıl beslerim?",
    "Tavuklarımı ne ile beslemeliyim?",
    "Buzağıları nasıl beslerim?",
])
def test_generic_feeding_verb_does_not_leak_to_nutrition(query):
    # 'besle'/'besin' are generic Turkish for "feed"/"nutrient", not
    # plant-specific. Without a plant-specific stem alongside them, an
    # animal-feeding question must not route to nutrition.
    assert classify_by_rules(query) != "nutrition"


def test_recycling_does_not_leak_to_budget():
    # 'geri donus' is a left-boundary prefix of 'geri dönüşüm' (recycling).
    # Composting/organic-waste questions are in scope, not budget.
    assert classify_by_rules("Bitki atıklarının geri dönüşümü nasıl yapılır?") != "budget"


@pytest.mark.parametrize("query, route", [
    ("İnek gübresi nasıl kullanılır?", "nutrition"),
    ("Domates fidesi diktim, ne zaman besleyeyim?", "fert_plan"),
    ("Bu yatırımın geri dönüşü ne kadar sürer?", "budget"),
    ("İneklerimin sütü azaldı, ne yapmalıyım?", "offscope"),
])
def test_frozen_cases_still_hold(query, route):
    assert classify_by_rules(query) == route


def test_rule_hit_reports_rule():
    assert router.classify("Buğday ekmenin dekara maliyeti nedir?") == ("budget", "rule")


def test_silent_rules_take_the_default_without_a_model_call(monkeypatch):
    # This test guards the central routing decision: classify() must never call
    # the model when no rule fires. It patches OpenAI (not _get_llm itself) because
    # _get_llm() constructs OpenAI(...) by looking the name up in engine's module
    # globals at call time, so this intercepts the client construction no matter
    # how _get_llm itself is imported or referenced.
    from src import engine
    def explode(*a, **k):
        raise AssertionError("classify() must not call the model")
    monkeypatch.setattr(engine, "OpenAI", explode)
    assert router.classify("Asmada budama ne zaman yapılır?") == ("plant_info", "default")


def test_default_is_todays_corpus_path():
    # plant_info and nutrition both run the corpus path; the default must be one
    # of them, or a rule-silent question would change behaviour.
    assert router._DEFAULT_ROUTE in ("plant_info", "nutrition")


def test_history_argument_is_accepted_and_ignored_for_now():
    history = [{"role": "user", "content": "Manisa'dayım"}]
    assert router.classify("Asmada budama ne zaman yapılır?", history) == \
        router.classify("Asmada budama ne zaman yapılır?")


def test_a_named_product_with_a_how_much_question_is_a_dose_question():
    assert router.classify_by_rules("HİGRO BARF dekara ne kadar kullanmalıyım?") == "product_dose"


def test_a_dose_phrase_with_a_fertilizer_stem_is_a_dose_question():
    assert router.classify_by_rules("Gübreyi dekara kaç litre vermeliyim?") == "product_dose"


def test_money_still_wins_over_a_named_product():
    """'HİGRO BARF kaç para?' is a price question, not a dose question - budget
    is checked first and stays first."""
    assert router.classify_by_rules("HİGRO BARF kaç para tutar?") == "budget"


def test_a_timing_question_is_still_a_plan_not_a_dose():
    assert router.classify_by_rules("Domatese ne zaman gübre vermeliyim?") == "fert_plan"


def test_a_plain_nutrition_question_is_not_a_dose_question():
    assert router.classify_by_rules("Buğday tarlamda nasıl gübreleme yapmalıyım?") == "nutrition"
