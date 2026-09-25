import csv
import io
import zipfile
from pathlib import Path

from scripts import build_world_norms as bwn

PRODUCTION_HEADER = [
    "Area Code", "Area Code (M49)", "Area", "Item Code", "Item Code (CPC)",
    "Item", "Element Code", "Element", "Year Code", "Year", "Unit", "Value",
    "Flag", "Note",
]
PRICE_HEADER = [
    "Area Code", "Area Code (M49)", "Area", "Item Code", "Item Code (CPC)",
    "Item", "Element Code", "Element", "Year Code", "Year", "Months Code",
    "Months", "Unit", "Value", "Flag",
]


def _production_row(area, item, label, element, year, value, flag="A", cpc="'0111"):
    return [str(area), "'792", f"Area {area}", str(item), cpc, label, element,
            "Yield", str(year), str(year), "kg/ha", f"{value:.6f}", flag, ""]


def _price_row(area, item, label, element, year, value, flag="A", months="7021"):
    return [str(area), "'792", f"Area {area}", str(item), "'0111", label,
            element, "Producer Price", str(year), str(year), months,
            "Annual value" if months == "7021" else "Month", "USD",
            f"{value:.6f}", flag]


def _archive(tmp_path: Path, name: str, header: list[str], rows: list[list[str]]) -> Path:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}.csv", buffer.getvalue())
    return path


def test_yield_is_converted_from_kg_per_hectare_to_kg_per_decare(tmp_path):
    path = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(223, 15, "Wheat", "5412", 2024, 3004.0),
    ])
    cells, items, countries, dropped = bwn.read_yields(path, "prod.csv")

    assert cells["15|223"]["2024"] == [300.4, "A"]
    assert items[15]["label"] == "Wheat"
    assert countries[223]["label"] == "Area 223"


def test_regional_aggregates_are_dropped(tmp_path):
    path = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(5000, 15, "Wheat", "5412", 2024, 3000.0),
        _production_row(223, 15, "Wheat", "5412", 2024, 3004.0),
    ])
    cells, _, countries, dropped = bwn.read_yields(path, "prod.csv")

    assert set(cells) == {"15|223"}
    assert set(countries) == {223}
    assert dropped["area_aggregates"] == 1


def test_item_group_totals_are_dropped(tmp_path):
    path = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(223, 1717, "Cereals, primary", "5412", 2024, 3000.0),
        _production_row(223, 15, "Wheat", "5412", 2024, 3004.0),
    ])
    cells, items, _, dropped = bwn.read_yields(path, "prod.csv")

    assert set(cells) == {"15|223"}
    assert set(items) == {15}
    assert dropped["item_groups"] == 1
    assert dropped["nec_items"] == 0


def test_nec_buckets_are_dropped(tmp_path):
    path = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(223, 463, "Other vegetables, fresh n.e.c.", "5412", 2024, 5000.0),
        _production_row(223, 15, "Wheat", "5412", 2024, 3004.0),
    ])
    cells, items, _, dropped = bwn.read_yields(path, "prod.csv")

    assert set(items) == {15}
    assert set(cells) == {"15|223"}
    assert dropped["nec_items"] == 1
    assert dropped["item_groups"] == 0


def test_years_before_the_window_are_dropped(tmp_path):
    path = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(223, 15, "Wheat", "5412", 2015, 2900.0),
        _production_row(223, 15, "Wheat", "5412", 2016, 3000.0),
    ])
    cells, _, _, _ = bwn.read_yields(path, "prod.csv")

    assert set(cells["15|223"]) == {"2016"}


def test_elements_other_than_yield_are_dropped(tmp_path):
    path = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(223, 15, "Wheat", "5312", 2024, 100.0),   # Area harvested
        _production_row(223, 15, "Wheat", "5510", 2024, 200.0),   # Production
        _production_row(223, 15, "Wheat", "5412", 2024, 3004.0),  # Yield
    ])
    cells, _, _, _ = bwn.read_yields(path, "prod.csv")

    assert cells["15|223"] == {"2024": [300.4, "A"]}


def test_the_flag_travels_with_the_value(tmp_path):
    path = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(223, 15, "Wheat", "5412", 2023, 2900.0, flag="A"),
        _production_row(223, 15, "Wheat", "5412", 2024, 3004.0, flag="E"),
    ])
    cells, _, _, _ = bwn.read_yields(path, "prod.csv")

    assert cells["15|223"]["2023"][1] == "A"
    assert cells["15|223"]["2024"][1] == "E"


def test_price_is_converted_from_usd_per_tonne_to_usd_per_kilogram(tmp_path):
    path = _archive(tmp_path, "prices", PRICE_HEADER, [
        _price_row(223, 15, "Wheat", "5532", 2024, 284.1),
    ])
    prices = bwn.read_prices(path, "prices.csv", {15: {"label": "Wheat"}})

    assert prices["15|223"]["2024"] == [0.2841, "A"]


def test_local_currency_prices_are_dropped(tmp_path):
    path = _archive(tmp_path, "prices", PRICE_HEADER, [
        _price_row(223, 15, "Wheat", "5530", 2024, 9000.0),   # LCU/tonne
        _price_row(223, 15, "Wheat", "5532", 2024, 284.1),    # USD/tonne
    ])
    prices = bwn.read_prices(path, "prices.csv", {15: {"label": "Wheat"}})

    assert prices["15|223"] == {"2024": [0.2841, "A"]}


def test_monthly_prices_are_dropped(tmp_path):
    """The archive carries a row per month beside the annual one. Today only
    the local-currency element has them, so the element filter hides this — but
    a monthly USD row would otherwise become the year's price, last row wins."""
    path = _archive(tmp_path, "prices", PRICE_HEADER, [
        _price_row(223, 15, "Wheat", "5532", 2024, 284.1),
        _price_row(223, 15, "Wheat", "5532", 2024, 9999.0, months="7012"),  # December
    ])
    prices = bwn.read_prices(path, "prices.csv", {15: {"label": "Wheat"}})

    assert prices["15|223"] == {"2024": [0.2841, "A"]}


def test_a_priced_item_with_no_yield_never_enters_the_file(tmp_path):
    """The prices file also prices meat, eggs and milk. Taking the item list
    from the union of both files admits livestock into a crop layer."""
    path = _archive(tmp_path, "prices", PRICE_HEADER, [
        _price_row(223, 1089, "Meat of pigeons and other birds", "5532", 2024, 4000.0),
        _price_row(223, 15, "Wheat", "5532", 2024, 284.1),
    ])
    prices = bwn.read_prices(path, "prices.csv", {15: {"label": "Wheat"}})

    assert set(prices) == {"15|223"}


def test_build_carries_units_sources_and_flag_definitions(tmp_path, monkeypatch):
    prod = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(223, 15, "Wheat", "5412", 2024, 3004.0),
    ])
    prices = _archive(tmp_path, "prices", PRICE_HEADER, [
        _price_row(223, 15, "Wheat", "5532", 2024, 284.1),
    ])
    monkeypatch.setattr(bwn, "_archive_for", lambda key, *, force=False: (
        prod if key == "production" else prices,
        "prod.csv" if key == "production" else "prices.csv",
        {"dataset": key, "url": f"{key}.zip", "last_modified": "z", "bytes": 1},
    ))

    document = bwn.build()

    assert document["meta"]["units"] == {"yield": "kg/da", "price": "USD/kg"}
    # The provenance describes the archives that were actually read, because it
    # came back from the same call that produced them.
    assert [source["dataset"] for source in document["meta"]["sources"]] == [
        "production", "prices"
    ]
    assert document["meta"]["flags"]["E"] == "Estimated value"
    assert document["yield"]["15|223"]["2024"] == [300.4, "A"]
    assert document["price"]["15|223"]["2024"] == [0.2841, "A"]
    assert document["items"]["15"]["label"] == "Wheat"
    assert document["countries"]["223"]["label"] == "Area 223"
    assert document["meta"]["dropped"] == {
        "area_aggregates": 0, "item_groups": 0, "nec_items": 0
    }
    assert document["meta"]["generated"]


def test_cells_are_ordered_numerically_by_item_then_area(tmp_path, monkeypatch):
    """`yield` and `price` are most of the file, and this file is committed and
    refreshed once a year. In archive-row order, FAO reordering its own export
    moves every line; string order would file `15|223` before `5|9`."""
    prod = _archive(tmp_path, "prod", PRODUCTION_HEADER, [
        _production_row(223, 15, "Wheat", "5412", 2024, 3004.0),
        _production_row(9, 5, "Oats", "5412", 2024, 2000.0),
        _production_row(9, 15, "Wheat", "5412", 2024, 2500.0),
        _production_row(223, 5, "Oats", "5412", 2024, 2100.0),
    ])
    prices = _archive(tmp_path, "prices", PRICE_HEADER, [
        _price_row(223, 15, "Wheat", "5532", 2024, 284.1),
        _price_row(9, 5, "Oats", "5532", 2024, 200.0),
    ])
    monkeypatch.setattr(bwn, "_archive_for", lambda key, *, force=False: (
        prod if key == "production" else prices,
        "prod.csv" if key == "production" else "prices.csv",
        {"dataset": key, "url": f"{key}.zip", "last_modified": "z", "bytes": 1},
    ))

    document = bwn.build()

    assert list(document["yield"]) == ["5|9", "5|223", "15|9", "15|223"]
    assert list(document["price"]) == ["5|9", "15|223"]
