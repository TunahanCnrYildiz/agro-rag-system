"""Season derivation. Pure: no clock, no network - the date is always passed in."""

from datetime import date

import pytest

from src.context.season import describe, season_of


@pytest.mark.parametrize("d,expected", [
    (date(2026, 1, 15), "kış"),
    (date(2026, 3, 1), "ilkbahar"),
    (date(2026, 5, 31), "ilkbahar"),
    (date(2026, 6, 1), "yaz"),
    (date(2026, 8, 31), "yaz"),
    (date(2026, 9, 1), "sonbahar"),
    (date(2026, 11, 30), "sonbahar"),
    (date(2026, 12, 1), "kış"),
    (date(2026, 2, 28), "kış"),
])
def test_season_boundaries(d, expected):
    assert season_of(d) == expected


def test_describe_names_the_month_and_the_season():
    assert describe(date(2026, 8, 10)) == "Ağustos ayı, yaz"


def test_describe_uses_turkish_month_names():
    assert describe(date(2026, 1, 5)).startswith("Ocak")
