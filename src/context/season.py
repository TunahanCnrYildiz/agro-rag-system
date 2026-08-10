"""Season from a date, northern hemisphere.

Meteorological seasons (three whole months each), not astronomical ones: the
consumer is agronomic advice, where "Haziran = yaz" is the useful statement and
a solstice date two weeks either way is not.

The date is always a parameter, never read from the clock here. That keeps the
module pure and its tests free of a frozen-time fixture.
"""
from __future__ import annotations

from datetime import date

_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
           "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def season_of(d: date) -> str:
    m = d.month
    if m in (12, 1, 2):
        return "kış"
    if m in (3, 4, 5):
        return "ilkbahar"
    if m in (6, 7, 8):
        return "yaz"
    return "sonbahar"


def describe(d: date) -> str:
    """A short Turkish phrase for the prompt: 'Ağustos ayı, yaz'."""
    return f"{_MONTHS[d.month - 1]} ayı, {season_of(d)}"
