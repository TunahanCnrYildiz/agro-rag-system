"""Unit tests for src/budget.py (no store, no model, no network)."""

from src import budget


def test_parse_accepts_a_turkish_decimal():
    assert budget.parse_tr_number("12,5") == 12.5


def test_parse_accepts_a_thousands_group():
    assert budget.parse_tr_number("1.250") == 1250.0
    assert budget.parse_tr_number("1.250,75") == 1250.75


def test_parse_accepts_a_plain_integer():
    assert budget.parse_tr_number("5") == 5.0


def test_parse_refuses_an_english_decimal():
    """'1.5' is ambiguous between 1,5 and a malformed thousands group. A visible
    field error is the right direction to fail - guessing is what this whole
    module exists to remove."""
    assert budget.parse_tr_number("1.5") is None


def test_parse_refuses_junk():
    assert budget.parse_tr_number("abc") is None
    assert budget.parse_tr_number("") is None
    assert budget.parse_tr_number("12,5,3") is None
    assert budget.parse_tr_number("-5") is None


def test_parse_tolerates_surrounding_space():
    assert budget.parse_tr_number("  5  ") == 5.0


def test_format_groups_thousands_and_uses_a_decimal_comma():
    assert budget.format_tr(20000, 2) == "20.000,00"
    assert budget.format_tr(1234567.891, 2) == "1.234.567,89"


def test_format_with_no_decimals_omits_the_comma():
    assert budget.format_tr(400, 0) == "400"
    assert budget.format_tr(5000, 0) == "5.000"


def test_format_keeps_the_sign_outside_the_grouping():
    assert budget.format_tr(-5000, 2) == "-5.000,00"


def test_format_does_not_print_a_negative_zero():
    """A value that rounds away to zero should format as zero, not -0."""
    assert budget.format_tr(-0.001, 2) == "0,00"
    assert budget.format_tr(-0.001, 0) == "0"
