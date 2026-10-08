import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def aliases() -> dict:
    return json.loads((DATA / "country_aliases.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def world_countries() -> dict:
    document = json.loads((DATA / "world_norms.json").read_text(encoding="utf-8"))
    return document["countries"]


def test_every_country_in_the_world_file_has_an_entry(aliases, world_countries):
    """Not 'most of them'. A country with no entry is a user the assistant
    cannot place, and it fails silently as 'no figures for you'."""
    missing = [code for code in world_countries if code not in aliases]
    assert missing == []


def test_no_entry_invents_a_country(aliases, world_countries):
    assert set(aliases) <= set(world_countries)


def test_every_entry_carries_both_languages(aliases):
    for code, entry in aliases.items():
        if entry.get("aggregate"):
            continue
        assert entry["tr"], code
        assert entry["en"], code
        assert all(isinstance(name, str) and name.strip() for name in entry["tr"]), code
        assert all(isinstance(name, str) and name.strip() for name in entry["en"]), code


def test_the_fao_label_matches_the_world_file(aliases, world_countries):
    for code, entry in aliases.items():
        assert entry["fao"] == world_countries[code]["label"], code


def test_no_name_is_claimed_by_two_countries(aliases):
    """An ambiguous name resolves to whichever entry is tried first, which is
    an arbitrary answer dressed as a confident one.

    Two COUNTRIES may not share a name. One country repeating a name across its
    own `tr` and `en` is ordinary and must stay allowed: roughly 45 of these are
    spelled identically in both languages — Panama, Kenya, Malta, Belize, Yemen,
    Sudan. Forbidding that forces an invented variant into one of the lists and
    the name people actually type stops matching."""
    seen: dict[str, str] = {}
    for code, entry in aliases.items():
        for key in {name.strip().casefold() for name in entry["tr"] + entry["en"]}:
            assert seen.get(key, code) == code, \
                f"{key!r} claimed by {seen.get(key)} and {code}"
            seen[key] = code


def test_the_china_aggregate_is_marked_and_unreachable():
    """Area 351 sums mainland, Hong Kong, Macao and Taiwan - an aggregate that
    survived the world layer's filter only because that filter dropped area
    codes >= 5000. Nothing may resolve to it, so it carries no names."""
    document = json.loads((DATA / "country_aliases.json").read_text(encoding="utf-8"))
    entry = document["351"]
    assert entry["aggregate"]
    assert entry["tr"] == []
    assert entry["en"] == []


def test_china_resolves_to_the_mainland_series(aliases):
    assert "Çin" in aliases["41"]["tr"]
    assert "China" in aliases["41"]["en"]


@pytest.mark.parametrize("code, tr, en", [
    ("223", "Türkiye", "Turkey"),
    ("68", "Fransa", "France"),
    ("235", "Özbekistan", "Uzbekistan"),
    ("59", "Mısır", "Egypt"),
])
def test_known_countries_carry_their_ordinary_names(aliases, code, tr, en):
    assert tr in aliases[code]["tr"], code
    assert en in aliases[code]["en"], code
