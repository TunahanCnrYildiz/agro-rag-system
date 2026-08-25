"""Unit tests for scripts/build_product_doses.py (no network)."""

import json

import pytest

from scripts.build_product_doses import build


PANELS = {
    "HİGRO FUBBY": ("Sebzelerde : Yapraktan 60-70 gr/ 100 Litre su ile uygulanılır, "
                    "Damlamadan 250 gr/ 1000m² alana uygulanılır."),
    "HİGRO ABS": ("HİGRO ABS, etikette önerilen uygulama dozajlarına dikkat "
                  "edilmesi gerekmektedir."),
    # Verbatim, HİGRO BARF. Carries a real RANGE, unlike the single figure
    # above - without one, an ordering check can only ever compare a number
    # with itself and passes whatever the code does.
    "HİGRO BARF": ("Sebzelerde : Yapraktan uygulama ile 100 cc / 100 litre suya "
                   "Damlama sulama ile 2-2,5 litre / 1000m² (da)"),
}


def test_a_parsable_panel_becomes_a_row():
    table, unparsed, dropped, scope = build(PANELS, {})
    assert table["HİGRO FUBBY"]["sebze"]["damlama"] == {
        "low": 250.0, "high": 250.0, "unit": "gr"}


def test_an_unparsable_panel_has_no_row_and_is_reported():
    """Absence, never a guessed figure - and never silent, because a silent
    skip is how a coverage collapse ships unnoticed."""
    table, unparsed, dropped, scope = build(PANELS, {})
    assert "HİGRO ABS" not in table
    assert "HİGRO ABS" in unparsed


def test_an_empty_input_yields_an_empty_table_not_an_error():
    table, unparsed, dropped, scope = build({}, {})
    assert table == {} and unparsed == [] and dropped == {}


def test_every_row_has_low_no_greater_than_high():
    """A reversed range would print '3 - 2 litre' and, worse, would mean the
    parser paired two unrelated numbers.

    The fixture has to contain a real range for this to check anything: with
    only single figures every row satisfies low <= high by construction, and
    the assertion passes whatever the code does."""
    table, _, _, _ = build(PANELS, {})
    spans = 0
    for groups in table.values():
        for methods in groups.values():
            for dose in methods.values():
                assert dose["low"] <= dose["high"]
                if dose["low"] < dose["high"]:
                    spans += 1
    assert spans, "no fixture row carries a range, so nothing was checked"


def test_the_shipped_file_is_what_the_converter_produces():
    """Re-run the committed converter over the committed raw panels and diff
    against the committed output. This is the check that proves the data file
    was generated, not hand-edited - the one P2a's final review ran by hand."""
    from src.config import DATA_DIR
    raw = json.loads((DATA_DIR / "raw" / "product_panels.json").read_text(encoding="utf-8"))
    review = json.loads((DATA_DIR / "dose_group_scope.json").read_text(encoding="utf-8"))
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    scope = {n: e["groups"] for n, e in review["scope"].items()}
    rebuilt, _, _, rebuilt_scope = build(raw["panels"], scope)
    assert rebuilt == shipped["products"]
    assert rebuilt_scope == shipped["all_groups_scope"]


def test_the_shipped_file_still_covers_most_of_the_catalog():
    """A guard on the real data. If a parser change or a site redesign empties
    the file, every other test here keeps passing on its fixtures. Measured
    2026-08-22: 40 of 48 products publish a per-area dose we can read, so the
    floor is set well below that and still catches a collapse."""
    from src.config import DATA_DIR
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    assert len(shipped["products"]) >= 35


def test_a_dropped_slot_is_returned_by_build_not_re_derived():
    """main() used to walk every panel a SECOND time to collect the dropped
    slots, so the report and the table came from two separate parses and could
    disagree about the same panel. One parse, both answers."""
    panels = {"X": ("Sebzelerde : Seralarda: 250 gr/ 1000m² uygulanılır. "
                    "Tarla sebzelerinde ve Tarla bitkilerinde 500 gr / 1000m² "
                    "uygulanılır.")}
    table, unparsed, dropped, scope = build(panels, {})
    assert dropped == {"X": [["sebze", "damlama"]]}
    assert "sebze" not in table["X"]
    assert "X" not in unparsed


def test_the_shipped_meta_records_both_kinds_of_failure():
    """Without these two keys there is no committed way to tell "this product
    publishes no drip figure" from "its drip figure was dropped as
    unresolvable" - and the answer path needs that difference."""
    from src.config import DATA_DIR
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    meta = shipped["meta"]
    assert "HİGRO MATEN" in meta["unparsed"]
    assert meta["dropped_slots"]["HIGRO FERFORCE"] == [["sebze", "damlama"]]
    assert meta["products_with_a_dose"] == len(shipped["products"])


def test_a_reversed_row_stops_the_converter_rather_than_shipping():
    """The parser refuses these upstream, so this can only fire if that refusal
    is loosened - which is precisely when a reversed row would otherwise go out
    with the other 102 looking perfectly normal."""
    import pytest

    from unittest.mock import patch
    with patch("scripts.build_product_doses.parse_panel",
               return_value={"sebze": {"damlama": (3.0, 1.0, "litre")}}):
        with pytest.raises(ValueError, match="do not belong together"):
            build({"X": "irrelevant"}, {})


def test_an_unreviewed_hepsi_row_stops_the_converter():
    """A `hepsi` row nobody read must not ship. Answering three groups off a
    missing heading is exactly the guess this file refuses to make."""
    panels = {"YENİ ÜRÜN": "Bir dekara (1.000 m²) 2 – 2,5 litre uygulanır."}
    with pytest.raises(ValueError, match="YENİ ÜRÜN"):
        build(panels, {})


def test_a_stale_scope_entry_stops_the_converter():
    """A review of a row that no longer exists is a review of nothing, and it
    would sit in the file looking like coverage."""
    panels = {"YENİ ÜRÜN": "Bir dekara (1.000 m²) 2 – 2,5 litre uygulanır."}
    scope = {"YENİ ÜRÜN": ["sebze", "meyve", "tarla"], "YOK ÜRÜN": ["sebze"]}
    with pytest.raises(ValueError, match="YOK ÜRÜN"):
        build(panels, scope)


def test_a_scope_naming_an_unknown_group_stops_the_converter():
    panels = {"YENİ ÜRÜN": "Bir dekara (1.000 m²) 2 – 2,5 litre uygulanır."}
    with pytest.raises(ValueError, match="hububat"):
        build(panels, {"YENİ ÜRÜN": ["hububat"]})


def test_a_reviewed_hepsi_row_ships_with_its_scope():
    panels = {"YENİ ÜRÜN": "Bir dekara (1.000 m²) 2 – 2,5 litre uygulanır."}
    table, unparsed, dropped, scope = build(panels, {"YENİ ÜRÜN": ["sebze", "tarla"]})
    assert "hepsi" in table["YENİ ÜRÜN"]
    assert scope == {"YENİ ÜRÜN": ["sebze", "tarla"]}


def test_the_shipped_scope_covers_every_shipped_hepsi_row():
    """The real data. If a parser change files a new product under `hepsi`,
    this fails until someone reads that product's panel."""
    from src.config import DATA_DIR
    shipped = json.loads((DATA_DIR / "product_doses.json").read_text(encoding="utf-8"))
    unqualified = {n for n, groups in shipped["products"].items() if "hepsi" in groups}
    assert unqualified == set(shipped["all_groups_scope"]), unqualified
    assert unqualified == {"FLY AZOT", "HIGRO 8 MN"}
