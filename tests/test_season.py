"""The season calendar, on the shipped FAO-56 data (data/crop_stages.json)."""
from datetime import date

import pytest

from src import season

TOMATO = "domates (sofralik)"


@pytest.fixture(autouse=True)
def _fresh_cache():
    yield
    season._load.cache_clear()


def test_a_tomato_planted_mid_april_is_dated_from_the_mediterranean_row():
    """FAO-56 Table 11, Tomato, Mediterranean, April/May: 30 + 40 + 45 + 30
    days. The only arithmetic is adding those to the farmer's date."""
    cal = season.build(TOMATO, "Domates", date(2027, 4, 15))
    assert isinstance(cal, season.SeasonCalendar)
    assert [(s.start, s.end, s.days) for s in cal.stages] == [
        (date(2027, 4, 15), date(2027, 5, 14), 30),
        (date(2027, 5, 15), date(2027, 6, 23), 40),
        (date(2027, 6, 24), date(2027, 8, 7), 45),
        (date(2027, 8, 8), date(2027, 9, 6), 30),
    ]
    assert cal.row["region"] == "Mediterranean"


def test_the_water_lines_are_the_published_coefficients():
    """FAO-56 Table 12, Tomato: Kc ini 0.6 (from its group row), mid 1.15,
    end 0.70-0.90 - printed as published, decimal comma only."""
    cal = season.build(TOMATO, "Domates", date(2027, 4, 15))
    assert [s.water for s in cal.stages] == [
        "su ihtiyacı düşük (Kc 0,6)",
        "su ihtiyacı artıyor (Kc 0,6 → 1,15)",
        "su ihtiyacı en yüksek (Kc 1,15)",
        "su ihtiyacı azalıyor (Kc 1,15 → 0,70-0,90)",
    ]


def test_winter_wheat_planted_in_november_spans_the_winter():
    cal = season.build("bugday, durum bugdayi haric", "Buğday", date(2026, 11, 5))
    assert sum(s.days for s in cal.stages) == 240
    assert cal.stages[-1].end == date(2027, 7, 2)


def test_planting_out_of_the_published_season_gets_no_calendar():
    """FAO-56 publishes small grains for April in the Mediterranean; a
    November barley gets the reason, never April's durations stretched over
    another season."""
    result = season.build("arpa (diger)", "Arpa", date(2026, 11, 10))
    assert isinstance(result, season.NoCalendar)
    assert "Nisan" in result.reason and "Kasım" in result.reason


def test_a_month_away_is_still_the_published_season():
    assert isinstance(season.build(TOMATO, "Domates", date(2027, 6, 1)),
                      season.SeasonCalendar)        # row says April/May
    assert isinstance(season.build(TOMATO, "Domates", date(2027, 7, 1)),
                      season.NoCalendar)


def test_only_mediterranean_and_european_rows_are_read():
    """Tomato also has an "Arid Region, January" row; a January tomato is
    still refused, because that climate is not where these farmers are."""
    assert isinstance(season.build(TOMATO, "Domates", date(2027, 1, 15)),
                      season.NoCalendar)


def test_a_crop_with_no_published_stages_says_so():
    result = season.build("nohut, kuru", "Nohut", date(2027, 3, 1))
    assert isinstance(result, season.NoCalendar)
    assert "yayımlamıyor" in result.reason


def test_a_crop_the_map_does_not_name_says_so():
    assert isinstance(season.build("no-such-crop", "X", date(2027, 4, 1)),
                      season.NoCalendar)


@pytest.mark.parametrize("row, expected", [
    ({"init": "30", "dev": "40", "mid": "45", "late": "30", "total": "145"}, (30, 40, 45, 30)),
    # bell pepper: only 30 adds up to 125
    ({"init": "25/30", "dev": "35", "mid": "40", "late": "20", "total": "125"}, (30, 35, 40, 20)),
    # carrots: only 30 adds up to 100
    ({"init": "20", "dev": "30", "mid": "50/30", "late": "20", "total": "100"}, (20, 30, 30, 20)),
    # spinach: 60 and 70 both add up - which season is meant is not arithmetic
    ({"init": "20", "dev": "20", "mid": "15/25", "late": "5", "total": "60/70"}, None),
    # the page's typos never add up
    ({"init": "30", "dev": "90", "mid": "60", "late": "90", "total": "2705"}, None),
    ({"init": "30", "dev": "30", "mid": "30", "late": "103", "total": "110"}, None),
    ({"init": "10", "dev": "30", "mid": "var.", "late": "var.", "total": "var."}, None),
])
def test_stage_lengths_are_used_only_when_they_add_up(row, expected):
    assert season._days(row) == expected


@pytest.mark.parametrize("text, months", [
    ("April/May", {4, 5}),
    ("Mar-May", {3, 4, 5}),
    ("Apr; Sep/Oct", {4, 9, 10}),
    ("Nov/Jan", {11, 1}),
    ("May May/June", {5, 6}),
    ("Sept", {9}),
    ("Rainy seas.", set()),
    ("", set()),
])
def test_published_planting_dates_are_read_as_months(text, months):
    assert season.plant_months(text) == months


def test_every_answer_carries_the_source_and_the_warning():
    text = season.render(season.build(TOMATO, "Domates", date(2027, 4, 15)))
    assert "FAO-56 (Allen vd., 1998), Tablo 11 - Mediterranean, April/May ekimi ve Tablo 12." in text
    assert season.DISCLAIMER in text
    assert season.FERTILIZATION_HEAD in text
    refused = season.render(season.build("nohut, kuru", "Nohut", date(2027, 3, 1)))
    assert season.DISCLAIMER in refused


def test_an_approximate_mapping_says_what_was_published():
    text = season.render(season.build("biber (sivri)", "Biber (Sivri)", date(2027, 5, 1)))
    assert "FAO-56 bu süreleri dolmalık (bell) biber için yayımlıyor." in text


def test_a_broken_data_file_costs_the_calendar_not_the_answer(monkeypatch, tmp_path):
    bad = tmp_path / "crop_stages.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(season, "_STAGES_JSON", bad)
    season._load.cache_clear()
    assert isinstance(season.build(TOMATO, "Domates", date(2027, 4, 15)), season.NoCalendar)


def test_every_mapped_crop_names_rows_that_exist():
    """A typo in the map would silently become "no calendar" for that crop."""
    stages, mapping = season._load()
    t11 = {r["crop"] for r in stages["stages"]}
    t12 = {(r["crop"], r["variant"]) for r in stages["kc"]}
    for cid, entry in mapping.items():
        if cid.startswith("_"):
            continue
        assert entry["t11"] is None or entry["t11"] in t11, cid
        assert tuple(entry["t12"]) in t12, cid


# --------------------------------------------------------------------------- #
# Fertilization rows: the company's own product pages (data/product_timing.json)
# --------------------------------------------------------------------------- #
import json  # noqa: E402
import re  # noqa: E402

from src.config import DATA_DIR, PRODUCTS_JSON  # noqa: E402

TIMING = json.loads((DATA_DIR / "product_timing.json").read_text(encoding="utf-8"))
PANELS = json.loads((DATA_DIR / "raw" / "product_panels.json").read_text(encoding="utf-8"))


def _ws(text):
    return " ".join(str(text).split())


@pytest.mark.parametrize("row", TIMING["rows"], ids=lambda r: f"{r['product']}:{r['quote'][:20]}")
def test_every_row_quotes_its_product_page_verbatim(row):
    """A row is the page's own words or it is nothing: the quote must appear in
    the raw panel the page published, whitespace aside."""
    panel = PANELS.get("panels", PANELS).get(row["product"])
    assert panel is not None, row["product"]
    assert _ws(row["quote"]) in _ws(panel if isinstance(panel, str) else json.dumps(panel, ensure_ascii=False))


def test_every_row_names_a_catalog_product_and_calendar_crops():
    names = {p["product_name"] for p in json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))}
    crops = set(season.available_crops())
    for row in TIMING["rows"]:
        assert row["product"] in names, row["product"]
        named = row.get("crops") or TIMING["tuik_groups"][row["tuik_group"]]
        assert set(named) <= crops, row["product"]


def test_no_row_recommends_a_pesticide():
    """FLY AZOT's page times two applications "ot ilacı ile birlikte"; the
    assistant never recommends chemicals (PDF p16), so a summary may not."""
    for row in TIMING["rows"]:
        assert not re.search(r"ila[cç]", row["when"], re.I), row["when"]


def test_the_vegetable_group_is_tuiks_own():
    """Re-derived from the raw TÜİK export: a crop is in "Sebzeler" because
    TÜİK lists it there, never because we judged it a vegetable."""
    from src.engine import _normalize_tr
    raw = _normalize_tr((DATA_DIR / "raw" / "sebze-uretim-2016-2025.csv")
                        .read_text(encoding="utf-8-sig"))
    veg = {m.group(1).strip() for m in re.finditer(
        r"\d{2}\.\d{2}\.\d{2}\.\d{2}\.\d{2}\.\s*\((.*?)\)\s*-\s*\w", raw)}
    assert TIMING["tuik_groups"]["sebzeler"] == [c for c in season.available_crops() if c in veg]


def test_a_planting_relative_row_is_dated_from_the_farmers_date():
    """ZİNCER: "Dikimden 3 hafta sonra" - 15 April + 21 days."""
    apps = {a.product: a for a in season.applications(TOMATO, date(2027, 4, 15))}
    assert apps["ZİNCER"].first == date(2027, 5, 6)
    assert apps["HİGRO ROOT LEGEND"].first == date(2027, 4, 15)
    assert apps["HİGRO BARF"].first is None          # "çiçek öncesi" is not a date


def test_a_stage_worded_row_is_never_dated():
    apps = season.applications("bugday, durum bugdayi haric", date(2026, 11, 5))
    assert {a.product for a in apps} == {"ZİNCER", "FLY AZOT"}
    assert all(a.first is None for a in apps)


def test_the_calendar_prints_the_programme_or_says_there_is_none():
    text = season.render(season.build(TOMATO, "Domates", date(2027, 4, 15)))
    assert season.FERTILIZATION_HEAD in text
    assert "- **ZİNCER** · dikimden 3 hafta sonra başlayarak, 2-3 hafta arayla · ilk uygulama: 6 Mayıs 2027" in text
    assert season.NO_FERTILIZATION_YET not in text
    flax = season.render(season.build("keten tohumu", "Keten", date(2027, 4, 15)))
    assert season.NO_FERTILIZATION_YET in flax
