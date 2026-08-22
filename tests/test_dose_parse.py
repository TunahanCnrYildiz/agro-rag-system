"""Unit tests for src/dose_parse.py. Every input here is verbatim from a real
product page, fetched 2026-08-22 - not invented, because the shapes that break
a pattern are exactly the ones nobody invents."""

import pytest

from src.dose_parse import parse_dose
from src.dose_parse import parse_panel


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


def test_a_comma_free_dilution_followed_by_an_area_word_is_still_refused():
    """No comma separates the dilution's amount from "dekara", so _GAP's
    comma boundary cannot be what refuses this - only the skip check that
    disqualifies an amount bound to water can."""
    assert parse_dose("100 litre suya 250 gram dekara uygulanir") is None


def test_a_glossed_dilution_amount_is_still_refused():
    """Same shape as above, but the amount carries the parenthetical numeral
    gloss ("250 (iki yuz elli) gram"). _DILUTION must be able to see the
    gloss too, or this amount is invisible to the skip check and gets read
    as a per-dekar dose instead of the water volume it actually is."""
    assert parse_dose("100 litre suya 250 (iki yuz elli) gram dekara uygulanir") is None


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


# Verbatim, HİGRO FUBBY, fetched 2026-08-22.
FUBBY = ("Sebzelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
         "Damlamadan 250 gr/ 1000m² alana uygulanılır. "
         "Meyvelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
         "Damlamadan 250 gr/ 1000m² alana uygulanılır. "
         "Tarla bitkilerinde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
         "Damlamadan 250 gr/ 1000m² alana uygulanılır.")

# Verbatim, HİGRO BARF. Different figures per group - the case that makes
# group segmentation load-bearing rather than decorative.
BARF = ("Çiçek öncesi ve sonrası dönemlerde uygulama dozları : "
        "Sebzelerde : Yapraktan uygulama ile 100 cc / 100 litre suya "
        "Damlama sulama ile 2-2,5 litre / 1000m² (da) "
        "Meyve Ağaçlarında: Yapraktan uygulama ile 200-250 cc / 100 litre suya "
        "Damlama sulama ile 2,5-3 litre / 1000m²(da)")

# Verbatim, BİNGO. Area first, and no method word at all.
BINGO = ("Sebzeler İçin: 1000m² alan için damla sulama ile 2 – 2.5 litre uygulayın. "
         "Meyve Ağaçları İçin: 1000m² alan için damla sulama ile 2 – 3 litre uygulayın. "
         "Tarla Bitkileri İçin: 1000m² alan için damla sulama ile 2 – 2.5 litre uygulayın.")

# Verbatim, HIGRO 8 MN, with the page furniture already cut by Task 1.
MN = ("YAPRAKTAN: Mangan eksikliği görüldüğü her dönemde; 100 litre suya 200 – 250 cc "
      "Higro 8 Mn ilave edilerek uygulama yapılabilir. DAMLAMA SULAMA: Mangan "
      "eksikliğinde bir dekara (1.000 m²) 2 – 2,5 litre dozunda Higro 8 Mn "
      "uygulaması yapılabilir.")

# Verbatim, HİGRO ABS. No dose anywhere.
ABS = ("HİGRO ABS, Kullanılacak çeşitlerde, etikette önerilen uygulama dozajlarına "
       "dikkat edilmesi gerekmektedir. Sadece Topraktan uygulama yapılmalıdır, bu "
       "uyarıya dikkat edilmelidir.")


def test_each_group_gets_its_own_dose():
    parsed = parse_panel(FUBBY)
    assert set(parsed) == {"sebze", "meyve", "tarla"}
    for group in parsed:
        assert parsed[group]["damlama"] == (250.0, 250.0, "gr")


def test_groups_with_different_figures_stay_different():
    """If segmentation silently merged them, a fruit grower would be given the
    vegetable dose - a wrong number that looks entirely plausible."""
    parsed = parse_panel(BARF)
    assert parsed["sebze"]["damlama"] == (2.0, 2.5, "litre")
    assert parsed["meyve"]["damlama"] == (2.5, 3.0, "litre")


def test_the_foliar_dilution_is_not_stored_as_a_dose():
    """Both panels put a 100-litre dilution in the same sentence as the
    per-dekar figure. Only the per-dekar one is a dose."""
    parsed = parse_panel(FUBBY)
    assert "yaprak" not in parsed["sebze"]


def test_a_group_heading_without_a_colon_is_still_a_heading():
    """HİGRO CUFİT and ZİNCER write 'Sebzelerde Yapraktan ...' with no colon;
    a pattern that requires one loses both products."""
    text = ("Sebzelerde Damlamadan 1 litre / 1000m² uygulanır. "
            "Meyvelerde Damlamadan 2 litre / 1000m² uygulanır.")
    parsed = parse_panel(text)
    assert parsed["sebze"]["damlama"] == (1.0, 1.0, "litre")
    assert parsed["meyve"]["damlama"] == (2.0, 2.0, "litre")


def test_an_area_first_clause_is_read():
    parsed = parse_panel(BINGO)
    assert parsed["sebze"]["damlama"] == (2.0, 2.5, "litre")
    assert parsed["meyve"]["damlama"] == (2.0, 3.0, "litre")


def test_a_panel_with_no_group_headings_applies_to_all():
    """HIGRO 8 MN names methods, not groups. With no group stated we must not
    invent one, so the dose is recorded as applying to all of them."""
    parsed = parse_panel(MN)
    assert set(parsed) == {"hepsi"}
    assert parsed["hepsi"]["damlama"] == (2.0, 2.5, "litre")
    assert "yaprak" not in parsed["hepsi"]


def test_a_comma_separates_the_foliar_clause_from_the_drip_one():
    """One sentence, two halves, a comma between them. Without splitting on the
    comma the drip figure is credited to 'yaprak', because that word comes
    first in the sentence."""
    parsed = parse_panel(FUBBY)
    assert parsed["sebze"]["damlama"] == (250.0, 250.0, "gr")
    assert "yaprak" not in parsed["sebze"]


def test_two_figures_for_one_method_become_the_span_they_cover():
    """FLY AZOT publishes 200 cc for dry farming and 250 cc for irrigated in one
    unqualified block. Keeping the first would silently choose between two
    published figures."""
    text = ("kıraç üretimde dekara 200 cc yapraktan uygulanır. "
            "Sulu üretimde dekara 250 cc yapraktan uygulanır.")
    assert parse_panel(text)["hepsi"]["yaprak"] == (200.0, 250.0, "cc")


def test_a_panel_with_no_dose_yields_nothing():
    assert parse_panel(ABS) == {}


def test_an_empty_panel_yields_nothing():
    assert parse_panel("") == {}
