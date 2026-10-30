"""Which place answers, when the profile and the conversation disagree.

The rule, decided by the user 2026-10-30: the profile's province holds until
the conversation names a place; a place the farmer names - their own, or one
they ask about - then answers, province or country alike. The mobile client
sends the profile as the OLDEST turn, so "most recent place wins" across
provinces AND countries is exactly that rule. Until now provinces and countries
were each searched on their own and a province always won, so a profile saying
Konya beat "Fransa'dayım" typed a moment ago.
"""
import pytest

from src import engine
from src.context import country as country_ctx
from src.context import location

PROFILE_KONYA = [{"role": "user", "content": (
    "Adım Ahmet. Konya'dayım. domates yetiştiriyorum. "
    "Bunu aklında tut, her cevapta tekrar etme.")}]


def _turns(*user_lines):
    out = list(PROFILE_KONYA)
    for line in user_lines:
        out += [{"role": "user", "content": line}, {"role": "assistant", "content": "..."}]
    return out


def test_with_no_place_in_the_conversation_the_profile_province_holds():
    assert location.extract_province("Buğdaydan ne kadar gelir elde ederim?",
                                     PROFILE_KONYA) == "Konya"


@pytest.mark.parametrize("message", [
    "Fransa'dayım, buğdaydan ne kadar gelir elde ederim?",
    "Fransa'da buğday verimi nasıl?",
])
def test_a_country_named_now_beats_the_profile_province(message):
    assert location.extract_province(message, PROFILE_KONYA) is None
    assert country_ctx.extract_country(message, PROFILE_KONYA) == 68


def test_a_province_named_now_beats_the_profile_province():
    assert location.extract_province("Antalya'da domates ne zaman ekilir?",
                                     PROFILE_KONYA) == "Antalya"


def test_the_most_recent_place_wins_either_way():
    history = _turns("Fransa'dayım, buğday nasıl?")
    assert location.extract_province("Peki arpa?", history) is None
    history = _turns("Fransa'dayım, buğday nasıl?", "Şimdi Antalya'dayım.")
    assert location.extract_province("Peki arpa?", history) == "Antalya"


def test_turkiye_is_not_abroad():
    assert location.extract_province("Türkiye'de buğday verimi ne kadar?",
                                     PROFILE_KONYA) == "Konya"


def test_maize_is_not_egypt():
    """Mısır is maize and Egypt; the country matcher's own guard decides, and a
    maize question must not cancel the profile's province."""
    assert location.extract_province("Mısır ekmeli miyim?", PROFILE_KONYA) == "Konya"


def test_a_province_and_a_country_in_one_turn_keep_the_province():
    """Within one sentence the province is where they are; TÜİK wins there,
    as it always has."""
    assert location.extract_province(
        "Konya'dayım ama Fransa'ya da ihracat yapıyorum.", []) == "Konya"


def test_the_budget_card_follows_the_conversation_over_the_profile(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the budget route must not reach this")

    monkeypatch.setattr(engine, "retrieve_context", boom)
    monkeypatch.setattr(engine, "match_products", boom)
    monkeypatch.setattr(engine, "_complete_text", boom)
    abroad = engine.answer("Fransa'dayım, buğdaydan ne kadar gelir elde ederim?",
                           PROFILE_KONYA).form
    home = engine.answer("Buğdaydan ne kadar gelir elde ederim?", PROFILE_KONYA).form
    cost = lambda form: [u["id"] for f in form["fields"] if f["id"] == "cost"
                         for u in f["units"]]
    assert cost(abroad) == ["usd"]
    assert cost(home) == ["tl"]


def test_maize_said_earlier_is_not_egypt_either():
    """The maize guard holds for history turns as well as the current message:
    a follow-up after a maize question keeps the profile's province."""
    history = _turns("Mısırda çinko eksikliği var, ne yapmalıyım?")
    assert country_ctx.extract_country("Peki ne zaman uygulayayım?", history) is None
    assert location.extract_province("Peki ne zaman uygulayayım?", history) == "Konya"
