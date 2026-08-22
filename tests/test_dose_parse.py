"""Unit tests for src/dose_parse.py. Every input here is verbatim from a real
product page, fetched 2026-08-22 - not invented, because the shapes that break
a pattern are exactly the ones nobody invents."""

import pytest

from src.dose_parse import parse_dose


@pytest.mark.parametrize("text, expected", [
    # The common shape: amount, slash, 1000m2.
    ("Damlamadan 250 gr/ 1000m² alana uygulanılır.", (250.0, 250.0, "gr")),
    # A range, with the area written as 1000m2 and glossed as (da).
    ("Damlama sulama ile 2-2,5 litre / 1000m² (da)", (2.0, 2.5, "litre")),
    # The area FIRST, the amount 26 characters later. The recon's own pattern
    # used a 25-character window and lost this one.
    ("1000m² alan için damla sulama ile 2 – 2.5 litre uygulayın.", (2.0, 2.5, "litre")),
    # A Turkish thousands dot inside the area, and the amount after it.
    ("bir dekara (1.000 m²) 2 – 2,5 litre dozunda uygulama yapılabilir.", (2.0, 2.5, "litre")),
    # The word "dekara" with the amount after it.
    ("Damlama sulama sistemi ile bir dekara (1.000 m²) 3 (üç) litre tabandan uygulanılır.",
     (3.0, 3.0, "litre")),
    # "dekara" with the amount before it.
    ("Tahıllarda kıraç üretimde dekara 200 cc yapraktan 2 uygulama yapılır.",
     (200.0, 200.0, "cc")),
    # An en dash with spaces, and a decimal comma.
    ("dekara (1000m²) 1 – 1,5 litre", (1.0, 1.5, "litre")),
])
def test_a_per_area_dose_is_read(text, expected):
    assert parse_dose(text) == expected


@pytest.mark.parametrize("text", [
    # A DILUTION, not a dose. Per 100 litres of water, and turning it into a
    # per-dekar figure needs a spray volume the page never gives.
    "Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır",
    "5 gün ara ile 100 litre suya 250 gram dozunda 2 defa uygulama yapılmalıdır.",
    "100 litre suya 200 – 250 cc Higro 8 Mn ilave edilerek uygulama yapılabilir.",
    "gübrelerle 100 litre suya 100cc karıştılarak kullanılır.",
    # No numbers at all.
    "etikette önerilen uygulama dozajlarına dikkat edilmesi gerekmektedir.",
    # A number, but nothing tying it to an area.
    "Bekleme süresi 0 (sıfır) gündür.",
    # An interval, not a dose.
    "Sezon boyunca 3 hafta ara ile uygulamaya devam edilir.",
])
def test_text_with_no_per_area_dose_returns_none(text):
    """None, never a guess and never a zero: a wrong number here is a wrong
    purchase."""
    assert parse_dose(text) is None


def test_a_dose_survives_beside_a_dilution_in_the_same_sentence():
    """HİGRO BARF writes both halves as one unpunctuated sentence. Refusing the
    whole clause on sight of a dilution was measured and drops the catalog from
    42 products to 10."""
    text = ("Yapraktan uygulama ile 100 cc / 100 litre suya "
            "Damlama sulama ile 2-2,5 litre / 1000m² (da)")
    assert parse_dose(text) == (2.0, 2.5, "litre")


def test_the_dilutions_own_amount_is_still_refused():
    """The 100 cc belongs to the water, not to the dekar - and it is the figure
    that appears FIRST, so a matcher that stops at the first amount takes it."""
    assert parse_dose("Yapraktan uygulama ile 100 cc / 100 litre suya") is None


def test_the_low_bound_is_never_above_the_high_bound():
    low, high, _ = parse_dose("Damlama sulama ile 2,5-3 litre / 1000m²(da)")
    assert low <= high


def test_a_decimal_comma_is_turkish_not_a_thousands_separator():
    """2,5 is two and a half litres, not twenty-five."""
    assert parse_dose("Damlamadan 2,5 litre / 1000m²") == (2.5, 2.5, "litre")


def test_hectares_are_not_read_as_dekars():
    """A per-hectare figure is ten times a per-dekar one. Reading it as dekars
    would multiply every answer by ten, silently."""
    assert parse_dose("hektara 20 litre uygulanır") is None
