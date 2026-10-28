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


@pytest.mark.parametrize("query", [
    "HİGRO BARF nedir?",
    "HİGRO BARF ne zaman uygulanır?",
    "BİNGO ürününü domateste kullanabilir miyim?",
])
def test_naming_a_product_is_not_asking_its_amount(query):
    # Naming a product used to hijack the route for any question that
    # mentions one, including ones with no amount ask at all - a dead end for
    # a deployed client that cannot draw the card. See routing review
    # (2026-08-25), finding 1.
    assert router.classify_by_rules(query) != "product_dose"


def test_an_elemental_amount_question_is_not_a_dose_question():
    # "azot" is an element, not a branded product; converting an elemental
    # amount into a product mass is out of scope (design spec §10), and
    # answering it with a card of 40 products is a guess wearing a helpful
    # shape.
    assert router.classify_by_rules("Dekara kaç kilo azot gerekir?") != "product_dose"


def test_a_named_product_with_a_bare_ne_kadar_is_still_a_dose_question():
    # No _DOSE_PHRASES hit here - the generic "ne kadar" alongside a named
    # product must still carry the route.
    assert router.classify_by_rules(
        "5 dönümlük tarlama FLY AZOT'tan ne kadar lazım?") == "product_dose"


@pytest.mark.parametrize("query", [
    "HİGRO BARF kaç günde bir uygulanır?",
    "HİGRO BARF ne kadar sürede etki eder?",
    "HİGRO BARF'ın raf ömrü kaç ay?",
    "HİGRO BARF kaç lira?",
    "HİGRO BARF kaç çeşit var?",
])
def test_a_named_product_with_a_duration_question_is_not_a_dose_question(query):
    # A product name plus a bare "kaç" used to be enough on its own - but
    # "kaç günde", "kaç ay" and "kaç çeşit" ask about timing, shelf life or
    # variety, never a quantity. Measured 2026-08-25 (post-fix review).
    assert router.classify_by_rules(query) != "product_dose"


def test_a_named_product_with_a_price_question_is_budget_not_dose():
    # 'fiyat' was missing from _BUDGET_STEMS, so this fell through the money
    # rule and reached the dose rule on its bare "ne kadar" instead.
    assert router.classify_by_rules("HİGRO BARF fiyatı ne kadar?") == "budget"


@pytest.mark.parametrize("query", [
    "HİGRO BARF'ı dekara ne miktarda vermeliyim?",
    "Buğdayda HİGRO BARF kullanım miktarı nedir?",
    "HİGRO BARF oranı dekara nedir?",
])
def test_ne_miktarda_and_orani_are_dose_questions(query):
    # "ne miktar", "miktarı" and "oranı" are natural Turkish amount words that
    # were missing from the amount signal, so real dose questions fell through
    # to the default corpus route. Measured 2026-08-25 (post-fix review).
    assert router.classify_by_rules(query) == "product_dose"


# A nutrient-qualified "gübre" with a rate - the class the dose route hijacked.
_FERTILIZER_CLASS_QUESTIONS = [
    "Meranın otlatma kapasitesini artırmak için dekara kaç kilogram azotlu gübre uygulanmalıdır?",
    "Buğdaya dekara kaç kg azotlu gübre verilir?",
    "Dekara ne kadar fosforlu gübre atılmalı?",
    "Mısıra dekara kaç kilo potasyumlu gübre gerekir?",
    "Potaslı gübre dekara ne kadar verilmeli?",
    "Dekara kaç kg kükürtlü gübre uygulanır?",
    "Kalsiyumlu gübre dekara ne kadar atılır?",
    "Magnezyumlu gübre dekara kaç kilo verilmeli?",
    "Dekara ne kadar çinkolu gübre gerekir?",
    "Borlu gübre dekara kaç kilo atılır?",
    "Demirli gübre dekara ne kadar uygulanmalı?",
    "Azotlu gübreler dekara ne kadar verilir?",
]

# The user's OWN fertilizer - possessed, definite or named. The first four carry
# the same nutrient qualifier as the class above, so they are the inputs that
# can break the bare-"gübre" sub-decision.
_FERTILIZER_IN_HAND_QUESTIONS = [
    "Azotlu gübremi dekara ne kadar atmalıyım?",
    "Aldığım azotlu gübreyi dekara kaç kilo vereyim?",
    "Bu azotlu gübreden dekara ne kadar atmalıyım?",
    "Elimdeki fosforlu gübreyi dekara ne kadar vereyim?",
    "Gübreyi dekara kaç litre vermeliyim?",
    "Domates için gübreden dekara ne kadar atmalıyım?",
    "HİGRO BARF dekara ne kadar kullanmalıyım?",
    "HİGRO FUBBY'nin dekara dozu nedir?",
]


@pytest.mark.parametrize("query", _FERTILIZER_CLASS_QUESTIONS)
def test_a_nutrient_qualified_fertilizer_is_a_class_not_a_dose(query):
    """A REGRESSION THAT STOOD TWO MONTHS. quant_mera_nitrogen_dose passed 8/8 on
    the 2026-08-13 answer-eval baseline; the dose route landed 2026-08-25 and
    from then on the first sentence above got the dose card's fixed intro in 0 s
    instead of an answer. The no-product half of the dose rule reads "gübre" as
    a product, and "azotlu gübre" is a fertilizer CLASS - the same thing
    "Dekara kaç kilo azot gerekir?" asks, which already routes to nutrition."""
    assert router.classify_by_rules(query) == "nutrition"


@pytest.mark.parametrize("query", _FERTILIZER_IN_HAND_QUESTIONS)
def test_a_fertilizer_in_hand_keeps_the_dose_card(query):
    """THE SUB-DECISION IS WHETHER "gübre" IS BARE. The qualifier alone does not
    make a class: "Azotlu gübremi" is the user's own nitrogen fertilizer, and the
    dose card is the right answer to it."""
    assert router.classify_by_rules(query) == "product_dose"


def test_the_class_questions_reach_the_rule_they_test():
    """WITHOUT THIS, THE TWO TESTS ABOVE COULD PASS ON NOTHING. This branch has
    met the vacuous zero more than once: a refusal set that cannot reach the
    rule under test proves nothing about it, and the routing set's own
    "product_dose: zero wrong entries" was one, with no nutrient-class question
    in it. So every class question is asserted to satisfy BOTH conditions of the
    no-product dose clause - a dose phrase and the "gübre" stem - which is to
    say each one would route product_dose but for the carve-out. And the
    carve-out is asserted to be the reason, by the class pattern matching it.

    The sub-decision gets the same treatment: the in-hand questions that carry a
    nutrient qualifier are asserted NOT to match the class pattern, so the
    bare-"gübre" gate is what keeps them a dose."""
    from src.engine import _normalize_tr
    for query in _FERTILIZER_CLASS_QUESTIONS:
        folded = _normalize_tr(query)
        assert router._has_stem(folded, router._DOSE_PHRASES), query
        assert router._has_stem(folded, router._FERTILIZER_PRODUCT_STEM), query
        assert router._FERTILIZER_CLASS.search(folded), query
    qualified_in_hand = [q for q in _FERTILIZER_IN_HAND_QUESTIONS
                         if any(e + "l" in _normalize_tr(q)
                                for e in router._NUTRIENT_ELEMENTS)]
    assert len(qualified_in_hand) == 4
    for query in qualified_in_hand:
        assert not router._FERTILIZER_CLASS.search(_normalize_tr(query)), query
