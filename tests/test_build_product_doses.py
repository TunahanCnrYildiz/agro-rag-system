"""Unit tests for scripts/build_product_doses.py (no network)."""

import json

from scripts.build_product_doses import build


PANELS = {
    "HİGRO FUBBY": ("Sebzelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
                    "Damlamadan 250 gr/ 1000m² alana uygulanılır."),
    "HİGRO ABS": ("HİGRO ABS, etikette önerilen uygulama dozajlarına dikkat "
                  "edilmesi gerekmektedir."),
}


def test_a_parsable_panel_becomes_a_row():
    table, unparsed = build(PANELS)
    assert table["HİGRO FUBBY"]["sebze"]["damlama"] == {
        "low": 250.0, "high": 250.0, "unit": "gr"}


def test_an_unparsable_panel_has_no_row_and_is_reported():
    """Absence, never a guessed figure - and never silent, because a silent
    skip is how a coverage collapse ships unnoticed."""
    table, unparsed = build(PANELS)
    assert "HİGRO ABS" not in table
    assert "HİGRO ABS" in unparsed


def test_an_empty_input_yields_an_empty_table_not_an_error():
    table, unparsed = build({})
    assert table == {} and unparsed == []


def test_every_row_has_low_no_greater_than_high():
    """A reversed range would print '3 - 2 litre' and, worse, would mean the
    parser paired two unrelated numbers."""
    table, _ = build(PANELS)
    for groups in table.values():
        for methods in groups.values():
            for dose in methods.values():
                assert dose["low"] <= dose["high"]


def test_the_shipped_file_is_what_the_converter_produces():
    """Re-run the committed converter over the committed raw panels and diff
    against the committed output. This is the check that proves the data file
    was generated, not hand-edited - the one P2a's final review ran by hand."""
    from src.config import DATA_DIR
    raw = json.loads((DATA_DIR / "raw" / "product_panels.json").read_text(encoding="utf-8"))
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    rebuilt, _ = build(raw["panels"])
    assert rebuilt == shipped["products"]


def test_the_shipped_file_still_covers_most_of_the_catalog():
    """A guard on the real data. If a parser change or a site redesign empties
    the file, every other test here keeps passing on its fixtures. Measured
    2026-08-22: 42 of 48 products publish a per-area dose, so the floor is set
    well below that and still catches a collapse."""
    from src.config import DATA_DIR
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    assert len(shipped["products"]) >= 35
