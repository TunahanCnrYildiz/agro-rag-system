# FAOSTAT World Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `data/world_norms.json` — country-level yield and producer price for 143 crops across 199 countries, from FAOSTAT — plus the map that ties our 246 Turkish crop ids to FAO item codes.

**Architecture:** A fetcher downloads two public bulk archives to a git-ignored cache and records their provenance. A converter streams them, drops everything that is not a crop in a country in our year window, converts units, and emits one JSON file keyed by FAO item code. A hand-built map file records, for every one of our 246 crop ids, either its FAO item code or the reason it has none. No surface reads any of it yet.

**Tech Stack:** Python 3.14 standard library only (`zipfile`, `csv`, `urllib.request`, `json`, `pathlib`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-23-faostat-world-layer-design.md`

## Global Constraints

- **The crop rule:** an item enters `world_norms.json` only if it has a yield row. The prices file also prices meat, eggs and milk; taking the item list from the union of both files admits livestock into a crop layer.
- **Units are converted in the builder:** `kg/ha ÷ 10 = kg/da`, `USD/tonne ÷ 1000 = USD/kg`. Nothing downstream re-converts.
- **Every cell is `[value, flag]`.** The FAOSTAT flag travels with the value. Absent years are simply absent — no null placeholders.
- **Dropped from the source:** areas with `Area Code >= 5000` (34 regional aggregates), item codes `{1717, 1720, 1723, 1726, 1729, 1732, 1735, 1738, 1804, 1841, 17530}` (11 group totals), any item whose label contains `n.e.c.` (14 residual buckets), years before 2016.
- **Expected output, measured 2026-09-23:** 143 items, 199 countries, 72.335 yield cells, 33.209 price cells, years 2016–2024, about 4,38 MB (written with `indent=1`, like `crop_norms.json`).
- **The archives are never committed.** `data/faostat_cache/` is git-ignored.
- **No network access in any test.** The fetcher is tested with a stubbed opener; the converter with fixtures built in `tmp_path`.
- **Deployment files are not touched:** `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.github/workflows/docker-publish.yml`, `web-widget/Dockerfile`, `web-widget/docker-entrypoint.d/`, `mobile-app/eas.json`, `mobile-app/app.json`.
- **Commit messages:** short, natural, English, no `Co-Authored-By` trailer.
- **Console output** goes through `scripts/_console.py` like the other scripts in this project, so Turkish labels survive a Windows console.

---

### Task 1: The fetcher

**Files:**
- Create: `scripts/fetch_faostat.py`
- Create: `tests/test_fetch_faostat.py`
- Modify: `.gitignore`
- Modify: `docs/client-requirements.md:142-150`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `DATASETS: dict[str, Dataset]` with keys `"production"` and `"prices"`; `Dataset` is a frozen dataclass with fields `key: str`, `url: str`, `member: str`.
  - `CACHE_DIR: Path`
  - `fetch(key: str, *, force: bool = False, opener=urllib.request.urlopen) -> Path` — returns the path of the cached `.zip`.
  - `describe(key: str) -> dict` — returns `{"dataset": str, "url": str, "last_modified": str, "bytes": int}` read from the sidecar written at download time; raises `FileNotFoundError` if the dataset was never fetched.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetch_faostat.py`:

```python
import io
import json
import zipfile

import pytest

from scripts import fetch_faostat as ff


class _FakeResponse(io.BytesIO):
    def __init__(self, payload: bytes, last_modified: str) -> None:
        super().__init__(payload)
        self._headers = {"Last-Modified": last_modified}

    @property
    def headers(self):
        return self._headers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _zip_bytes(member: str = None) -> bytes:
    """A zip carrying the member `fetch` expects, unless told otherwise.

    `fetch` validates the member name, so a helper writing some other name
    would make every download test fail for a reason it is not about.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member or ff.DATASETS["production"].member, "Area Code,Value\n2,1\n")
    return buffer.getvalue()


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ff, "CACHE_DIR", tmp_path)
    return tmp_path


def test_fetch_writes_the_archive_and_its_provenance(cache):
    payload = _zip_bytes()
    calls = []

    def opener(url, timeout=None):
        calls.append(url)
        return _FakeResponse(payload, "Wed, 31 Dec 2025 11:33:28 GMT")

    path = ff.fetch("production", opener=opener)

    assert path.read_bytes() == payload
    assert calls == [ff.DATASETS["production"].url]
    assert ff.describe("production") == {
        "dataset": ff.DATASETS["production"].key,
        "url": ff.DATASETS["production"].url,
        "last_modified": "Wed, 31 Dec 2025 11:33:28 GMT",
        "bytes": len(payload),
    }


def test_a_second_fetch_does_not_download_again(cache):
    calls = []

    def opener(url, timeout=None):
        calls.append(url)
        return _FakeResponse(_zip_bytes(), "Wed, 31 Dec 2025 11:33:28 GMT")

    ff.fetch("production", opener=opener)
    ff.fetch("production", opener=opener)

    assert len(calls) == 1


def test_force_downloads_again(cache):
    calls = []

    def opener(url, timeout=None):
        calls.append(url)
        return _FakeResponse(_zip_bytes(), "Wed, 31 Dec 2025 11:33:28 GMT")

    ff.fetch("production", opener=opener)
    ff.fetch("production", force=True, opener=opener)

    assert len(calls) == 2


def test_an_archive_without_the_expected_member_is_rejected(cache):
    """A valid zip that is not the archive we asked for — FAOSTAT renaming
    a file, a proxy zipping an error page — must not be adopted as cached.
    Task 2 opens `Dataset.member` by name and would fail far from here."""
    def opener(url, timeout=None):
        return _FakeResponse(_zip_bytes("something_else.csv"),
                             "Wed, 31 Dec 2025 11:33:28 GMT")

    with pytest.raises(zipfile.BadZipFile):
        ff.fetch("production", opener=opener)

    assert list(cache.glob("*.zip")) == []


def test_a_truncated_download_leaves_no_cached_archive(cache):
    def opener(url, timeout=None):
        return _FakeResponse(b"not a zip at all", "Wed, 31 Dec 2025 11:33:28 GMT")

    with pytest.raises(zipfile.BadZipFile):
        ff.fetch("production", opener=opener)

    assert list(cache.glob("*.zip")) == []
    with pytest.raises(FileNotFoundError):
        ff.describe("production")


def test_describe_before_any_fetch_raises(cache):
    with pytest.raises(FileNotFoundError):
        ff.describe("prices")


def test_an_unknown_dataset_is_rejected(cache):
    with pytest.raises(KeyError):
        ff.fetch("livestock")


def test_both_datasets_are_declared_with_matching_members():
    assert set(ff.DATASETS) == {"production", "prices"}
    for dataset in ff.DATASETS.values():
        assert dataset.url.endswith(".zip")
        assert dataset.url.endswith(dataset.member.replace(".csv", ".zip"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_fetch_faostat.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.fetch_faostat'`

- [ ] **Step 3: Write the fetcher**

Create `scripts/fetch_faostat.py`:

```python
"""Download the two FAOSTAT bulk archives this project converts.

TÜİK's inputs are committed under `data/raw/` because they are hand-driven
MEDAS exports that nobody can reproduce from a URL — a converter whose input is
missing can neither be re-run nor inspected. FAOSTAT's inputs are a fixed public
URL, so they stay out of git and this script fetches them instead. What keeps
the conversion auditable is the provenance recorded beside each archive and
copied into `data/world_norms.json`'s meta block: the URL, the server's
Last-Modified, and the byte count.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from scripts._console import use_utf8_console
from src.config import DATA_DIR

_BASE = "https://bulks-faostat.fao.org/production/"
TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class Dataset:
    key: str
    url: str
    member: str


DATASETS: dict[str, Dataset] = {
    "production": Dataset(
        key="Production_Crops_Livestock_E_All_Data_(Normalized)",
        url=_BASE + "Production_Crops_Livestock_E_All_Data_(Normalized).zip",
        member="Production_Crops_Livestock_E_All_Data_(Normalized).csv",
    ),
    "prices": Dataset(
        key="Prices_E_All_Data_(Normalized)",
        url=_BASE + "Prices_E_All_Data_(Normalized).zip",
        member="Prices_E_All_Data_(Normalized).csv",
    ),
}

CACHE_DIR = DATA_DIR / "faostat_cache"


def _archive_path(dataset: Dataset) -> Path:
    return CACHE_DIR / f"{dataset.key}.zip"


def _sidecar_path(dataset: Dataset) -> Path:
    return CACHE_DIR / f"{dataset.key}.provenance.json"


def fetch(key: str, *, force: bool = False, opener=urllib.request.urlopen) -> Path:
    """Return the cached archive for `key`, downloading it when needed."""
    dataset = DATASETS[key]
    archive = _archive_path(dataset)
    if archive.exists() and not force:
        return archive

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with opener(dataset.url, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read()
        last_modified = response.headers.get("Last-Modified", "")

    # Write to a temporary name and validate before adopting it, so an
    # interrupted download never leaves a half archive that later runs
    # would treat as cached.
    staged = archive.with_suffix(".zip.part")
    staged.write_bytes(payload)
    try:
        with zipfile.ZipFile(staged) as archive_file:
            if dataset.member not in archive_file.namelist():
                raise zipfile.BadZipFile(
                    f"{dataset.key}: expected member {dataset.member!r}"
                )
    except zipfile.BadZipFile:
        staged.unlink(missing_ok=True)
        raise

    staged.replace(archive)
    _sidecar_path(dataset).write_text(
        json.dumps(
            {
                "dataset": dataset.key,
                "url": dataset.url,
                "last_modified": last_modified,
                "bytes": len(payload),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return archive


def describe(key: str) -> dict:
    """Return the provenance recorded when `key` was last downloaded."""
    sidecar = _sidecar_path(DATASETS[key])
    if not sidecar.exists():
        raise FileNotFoundError(f"{key} has not been fetched; run this script first")
    return json.loads(sidecar.read_text(encoding="utf-8"))


def main() -> None:
    use_utf8_console()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if cached")
    args = parser.parse_args()

    for key in DATASETS:
        path = fetch(key, force=args.force)
        meta = describe(key)
        print(f"{key}: {path} ({meta['bytes'] / 1e6:.1f} MB, {meta['last_modified']})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_fetch_faostat.py -q`
Expected: PASS, 8 passed

If `from scripts import fetch_faostat` fails because `scripts/` has no `__init__.py`, check how `tests/test_build_crop_norms.py` imports `scripts/build_crop_norms.py` and follow that existing pattern exactly rather than inventing a new one.

- [ ] **Step 5: Ignore the cache**

Append to `.gitignore`:

```
# FAOSTAT bulk archives (45,6 MB, re-downloadable from a fixed URL —
# see scripts/fetch_faostat.py for why these are not committed the way
# TÜİK's hand-exported inputs under data/raw/ are)
data/faostat_cache/
```

- [ ] **Step 6: Correct the size figure in the requirements register**

`docs/client-requirements.md` currently records 32 MB / 11 MB / 43 MB under
"The scale question, measured rather than estimated". Those are compressed
sizes presented without saying so. Replace that table with:

```markdown
| Dataset | Compressed | Uncompressed |
| --- | --- | --- |
| Production — crops & livestock, normalised, all countries, all years | 33,9 MB | 545 MB |
| Producer prices, normalised | 11,7 MB | 214 MB |
| **Total** | **45,6 MB** | **759 MB** |

Re-measured 2026-09-23. The 2026-08-11 figures (32 MB / 11 MB / 43 MB) were the
**compressed** sizes, recorded without that word. The conclusion they supported —
that this is a download rather than a data-collection project — survives; the
figures did not, and only the download is 43 MB.
```

Leave the surrounding prose, including the 1.3 GB vector-store comparison, as it is.

- [ ] **Step 7: Run the full suite and commit**

Run: `python -m pytest -q`
Expected: PASS, 1058 passed

```bash
git add scripts/fetch_faostat.py tests/test_fetch_faostat.py .gitignore docs/client-requirements.md
git commit -m "Fetch the FAOSTAT bulk archives, and record where they came from"
```

---

### Task 2: The converter, and the file it ships

**Files:**
- Create: `scripts/build_world_norms.py`
- Create: `tests/test_build_world_norms.py`
- Create: `data/world_norms.json` (generated, ~4,38 MB, committed)

**Interfaces:**
- Consumes: `scripts.fetch_faostat.DATASETS`, `fetch`, `describe`.
- Produces:
  - `YIELD_ELEMENT = "5412"`, `PRICE_ELEMENT = "5532"`, `FIRST_YEAR = 2016`, `AGGREGATE_AREA_FLOOR = 5000`, `ITEM_GROUPS: frozenset[int]`, `HA_PER_DA = 10`, `KG_PER_TONNE = 1000`
  - `is_crop_item(item_code: int, label: str) -> bool`
  - `read_yields(archive: Path, member: str)` returning `(cells, items, countries, dropped)`; `cells` is keyed `"<item>|<area>"` mapping `"<year>"` to `[value_kg_da, flag]`; `dropped` is `{"area_aggregates": int, "item_groups": int, "nec_items": int}`, counting the distinct areas and items each filter removed.
  - `read_prices(archive: Path, member: str, items: dict[int, dict]) -> dict[str, dict[str, list]]`
  - `build(sources: list[dict]) -> dict` — the whole output document.
  - `main()`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_build_world_norms.py`:

```python
import csv
import io
import zipfile
from pathlib import Path

import pytest

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


def _price_row(area, item, label, element, year, value, flag="A"):
    return [str(area), "'792", f"Area {area}", str(item), "'0111", label,
            element, "Producer Price", str(year), str(year), "7021", "Annual value",
            "USD", f"{value:.6f}", flag]


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
    monkeypatch.setattr(bwn, "_archive_for", lambda key: (
        prod if key == "production" else prices,
        "prod.csv" if key == "production" else "prices.csv",
    ))

    document = bwn.build(sources=[{"dataset": "x", "url": "y", "last_modified": "z", "bytes": 1}])

    assert document["meta"]["units"] == {"yield": "kg/da", "price": "USD/kg"}
    assert document["meta"]["sources"][0]["dataset"] == "x"
    assert document["meta"]["flags"]["E"] == "Estimated value"
    assert document["yield"]["15|223"]["2024"] == [300.4, "A"]
    assert document["price"]["15|223"]["2024"] == [0.2841, "A"]
    assert document["items"]["15"]["label"] == "Wheat"
    assert document["countries"]["223"]["label"] == "Area 223"
    assert document["meta"]["dropped"] == {
        "area_aggregates": 0, "item_groups": 0, "nec_items": 0
    }
    assert document["meta"]["generated"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_build_world_norms.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.build_world_norms'`

- [ ] **Step 3: Write the converter**

Create `scripts/build_world_norms.py`:

```python
"""Convert the FAOSTAT bulk archives into `data/world_norms.json`.

The output is keyed by FAO item code rather than by our own crop ids because
our crop list is finer than FAOSTAT's: `Durum Buğdayı` and
`Buğday, Durum Buğdayı Hariç` are both FAO item 15 `Wheat`, and three of our
cabbages are all item 358. Keying by FAO code stores each series once, under
the identity its publisher gave it; `data/crop_fao_map.json` records the
collapse where a person can read it.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date
from pathlib import Path

from scripts import fetch_faostat
from scripts._console import use_utf8_console
from src.config import DATA_DIR

YIELD_ELEMENT = "5412"   # Yield, kg/ha — crops only; livestock yield is 5413/5417/5424
PRICE_ELEMENT = "5532"   # Producer Price, USD/tonne — 5530 is LCU, not comparable
FIRST_YEAR = 2016        # TÜİK's window starts here; earlier years cannot be read beside it
AGGREGATE_AREA_FLOOR = 5000   # `Africa`, `European Union (27)`, `World` …
ITEM_GROUPS = frozenset({1717, 1720, 1723, 1726, 1729, 1732, 1735, 1738,
                         1804, 1841, 17530})  # `Cereals, primary` and friends: sums, not crops
HA_PER_DA = 10           # FAOSTAT publishes per hectare; every surface here uses dekar
KG_PER_TONNE = 1000      # FAOSTAT prices per tonne; TÜİK prices per kilogram

FLAG_MEANINGS = {
    "A": "Official figure",
    "B": "Time series break",
    "E": "Estimated value",
    "I": "Value imputed by a receiving agency",
    "X": "Figure from external organization",
}

OUTPUT = DATA_DIR / "world_norms.json"


def is_crop_item(item_code: int, label: str) -> bool:
    """Reject the group totals and the `n.e.c.` residual buckets.

    `Other vegetables, fresh n.e.c.` is reported by more countries than any
    real crop, but nobody plants it; a number attached to an unnamed mixture
    is not an answer.
    """
    return item_code not in ITEM_GROUPS and "n.e.c" not in label.lower()


def _rows(archive: Path, member: str):
    with zipfile.ZipFile(archive) as bundle:
        with bundle.open(member) as raw:
            stream = io.TextIOWrapper(raw, encoding="utf-8-sig",
                                      errors="replace", newline="")
            reader = csv.reader(stream)
            header = next(reader)
            index = {name: position for position, name in enumerate(header)}
            for row in reader:
                yield row, index


def _clean(code: str) -> str:
    return code.strip().lstrip("'")


def read_yields(archive: Path, member: str):
    """Return `(cells, items, countries, dropped)` from the production archive.

    `dropped` counts the DISTINCT areas and items each filter removed, so the
    output can say what this vintage of the source actually contained rather
    than repeating the rule back at the reader.
    """
    cells: dict[str, dict[str, list]] = {}
    items: dict[int, dict] = {}
    countries: dict[int, dict] = {}
    aggregates: set[int] = set()
    groups: set[int] = set()
    residual: set[int] = set()

    for row, index in _rows(archive, member):
        if row[index["Element Code"]] != YIELD_ELEMENT:
            continue
        area_code = int(row[index["Area Code"]])
        if area_code >= AGGREGATE_AREA_FLOOR:
            aggregates.add(area_code)
            continue
        year = int(row[index["Year"]])
        if year < FIRST_YEAR:
            continue
        item_code = int(row[index["Item Code"]])
        label = row[index["Item"]]
        if not is_crop_item(item_code, label):
            (groups if item_code in ITEM_GROUPS else residual).add(item_code)
            continue

        items.setdefault(item_code, {"label": label,
                                     "cpc": _clean(row[index["Item Code (CPC)"]])})
        countries.setdefault(area_code, {"label": row[index["Area"]],
                                         "m49": _clean(row[index["Area Code (M49)"]])})
        value = float(row[index["Value"]]) / HA_PER_DA
        cells.setdefault(f"{item_code}|{area_code}", {})[str(year)] = [
            round(value, 2), row[index["Flag"]]
        ]
    dropped = {"area_aggregates": len(aggregates),
               "item_groups": len(groups),
               "nec_items": len(residual)}
    return cells, items, countries, dropped


def read_prices(archive: Path, member: str, items: dict[int, dict]):
    """Return price cells for exactly the items that already have a yield.

    The prices archive is not restricted to crops — it prices meat, eggs and
    milk too — so the item list must come from yield and prices must be looked
    up for those items, never the other way round.
    """
    cells: dict[str, dict[str, list]] = {}
    for row, index in _rows(archive, member):
        if row[index["Element Code"]] != PRICE_ELEMENT:
            continue
        item_code = int(row[index["Item Code"]])
        if item_code not in items:
            continue
        area_code = int(row[index["Area Code"]])
        if area_code >= AGGREGATE_AREA_FLOOR:
            continue
        year = int(row[index["Year"]])
        if year < FIRST_YEAR:
            continue
        value = float(row[index["Value"]]) / KG_PER_TONNE
        cells.setdefault(f"{item_code}|{area_code}", {})[str(year)] = [
            round(value, 4), row[index["Flag"]]
        ]
    return cells


def _archive_for(key: str) -> tuple[Path, str]:
    dataset = fetch_faostat.DATASETS[key]
    return fetch_faostat.fetch(key), dataset.member


def build(sources: list[dict]) -> dict:
    prod_archive, prod_member = _archive_for("production")
    price_archive, price_member = _archive_for("prices")

    yields, items, countries, dropped = read_yields(prod_archive, prod_member)
    prices = read_prices(price_archive, price_member, items)

    years = sorted({int(year) for cell in yields.values() for year in cell}
                   | {int(year) for cell in prices.values() for year in cell})
    return {
        "meta": {
            "generated": date.today().isoformat(),
            "years": [years[0], years[-1]] if years else [],
            "units": {"yield": "kg/da", "price": "USD/kg"},
            "sources": sources,
            "flags": FLAG_MEANINGS,
            "dropped": dropped,
        },
        "items": {str(code): items[code] for code in sorted(items)},
        "countries": {str(code): countries[code] for code in sorted(countries)},
        "yield": yields,
        "price": prices,
    }


def main() -> None:
    use_utf8_console()
    sources = []
    for key in fetch_faostat.DATASETS:
        fetch_faostat.fetch(key)
        sources.append(fetch_faostat.describe(key))

    document = build(sources)
    # indent=1 like build_crop_norms.py: this file is committed and refreshed
    # about once a year, and a 2 MB single line makes that diff unreadable.
    OUTPUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"items: {len(document['items'])}")
    print(f"countries: {len(document['countries'])}")
    print(f"yield cells: {sum(len(c) for c in document['yield'].values())}")
    print(f"price cells: {sum(len(c) for c in document['price'].values())}")
    print(f"dropped: {document['meta']['dropped']}")
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_build_world_norms.py -q`
Expected: PASS, 11 passed

- [ ] **Step 5: Generate the real file**

Run: `python -m scripts.build_world_norms`

Expected output — **these numbers are the acceptance criterion for this step.**
They were measured against the archives dated 2025-12-31 and 2026-01-09:

```
items: 143
countries: 199
yield cells: 72335
price cells: 33209
dropped: {'area_aggregates': 34, 'item_groups': 11, 'nec_items': 14}
wrote .../data/world_norms.json (4.38 MB)
```

If FAOSTAT has published a newer archive since, the counts will differ slightly.
That is acceptable **only** if `items` stays in the 140s and `countries` in the
190s; a count outside that means a filter is wrong, not that the source moved.
Report the numbers you actually saw in your report file either way.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_world_norms.py tests/test_build_world_norms.py data/world_norms.json
git commit -m "Convert the FAOSTAT archives into a country-level crop layer"
```

---

### Task 3: The map's shape, and the field crops (crop ids 0–99)

**Files:**
- Create: `data/crop_fao_map.json`
- Create: `tests/test_crop_fao_map.py`

**Interfaces:**
- Consumes: `data/world_norms.json`'s `items` block (Task 2), `data/crop_norms.json`'s `crops` block.
- Produces: `data/crop_fao_map.json` with the shape below. Tasks 4 and 5 extend the same `"map"` object and add nothing new to its shape.

**File shape:**

```json
{
  "generated": "2026-09-23",
  "map": {
    "durum bugdayi": {"fao": 15, "note": "FAOSTAT does not split durum from other wheat"},
    "kaplica": {"fao": null, "reason": "FAOSTAT has no emmer item"}
  }
}
```

Every entry has a `"fao"` key. An entry with an integer `"fao"` carries a
`"note"` only when the mapping is not word-for-word — a collapse, a narrowing,
or a judgement someone might otherwise re-litigate. An entry with `"fao": null`
always carries a `"reason"`.

**What this task covers:** the first 100 crop ids in `data/crop_norms.json`'s
`crops` object, in file order — index 0 (`Durum Buğdayı`) through index 99
(`Fiğ Tohumu`). These are the cereals, pulses, oilseeds, vegetables, industrial
crops and fodder crops.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_crop_fao_map.py`:

```python
import json
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def crop_ids() -> list[str]:
    document = json.loads((DATA / "crop_norms.json").read_text(encoding="utf-8"))
    return list(document["crops"])


@pytest.fixture(scope="module")
def world_items() -> set[int]:
    document = json.loads((DATA / "world_norms.json").read_text(encoding="utf-8"))
    return {int(code) for code in document["items"]}


@pytest.fixture(scope="module")
def crop_map() -> dict:
    return json.loads((DATA / "crop_fao_map.json").read_text(encoding="utf-8"))["map"]


def test_every_mapped_id_is_a_real_crop(crop_map, crop_ids):
    assert set(crop_map) <= set(crop_ids)


def test_every_entry_decides_something(crop_map):
    for crop_id, entry in crop_map.items():
        assert "fao" in entry, crop_id
        assert entry["fao"] is None or isinstance(entry["fao"], int), crop_id


def test_an_unmapped_crop_says_why(crop_map):
    for crop_id, entry in crop_map.items():
        if entry["fao"] is None:
            assert entry.get("reason"), crop_id


def test_a_mapped_crop_never_carries_a_reason(crop_map):
    """`reason` means 'there is no FAO item'. A mapped crop explaining itself
    uses `note`, so the two can never be confused by a reader or a filter."""
    for crop_id, entry in crop_map.items():
        if entry["fao"] is not None:
            assert "reason" not in entry, crop_id


def test_every_mapped_code_exists_in_the_world_file(crop_map, world_items):
    for crop_id, entry in crop_map.items():
        if entry["fao"] is not None:
            assert entry["fao"] in world_items, f"{crop_id} -> {entry['fao']}"


def test_the_field_crops_are_all_decided(crop_map, crop_ids):
    for crop_id in crop_ids[:100]:
        assert crop_id in crop_map, crop_id


@pytest.mark.parametrize("ids, code", [
    (["durum bugdayi", "bugday, durum bugdayi haric"], 15),
    (["arpa (biralik)", "arpa (diger)"], 44),
    (["lahana (beyaz)", "lahana (kirmizi)", "lahana (kara yaprak)"], 358),
    (["mercimek, kuru (kirmizi)", "mercimek, kuru (yesil)"], 201),
    (["aycicegi tohumu (yaglik)", "aycicegi tohumu (cerezlik)"], 267),
])
def test_known_many_to_one_collapses_hold(crop_map, ids, code):
    """FAOSTAT is coarser than TÜİK. These collapses are deliberate; an edit
    that splits one of them is a mistake, not a refinement."""
    for crop_id in ids:
        assert crop_map[crop_id]["fao"] == code, crop_id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_crop_fao_map.py -q`
Expected: FAIL — `FileNotFoundError: .../data/crop_fao_map.json`

- [ ] **Step 3: List the two sides**

Run this to print what you are mapping from and to. Read both lists fully
before writing a single entry.

```bash
python -c "
import json,sys
sys.stdout.reconfigure(encoding='utf-8')
c=json.load(open('data/crop_norms.json',encoding='utf-8'))['crops']
for i,(k,v) in enumerate(list(c.items())[:100]): print(f'{i:>3} {k:<44} {v[\"label\"]}')
print('---- FAO items ----')
w=json.load(open('data/world_norms.json',encoding='utf-8'))['items']
for code in sorted(w,key=int): print(f'{code:>6} {w[code][\"label\"]}')
"
```

- [ ] **Step 4: Write the map**

Create `data/crop_fao_map.json` with `"generated": "2026-09-23"` and one entry
for each of the first 100 crop ids.

**How to decide each one.** The mapping is a translation claim about two
labels, not an agronomic judgement — `Nohut` is `Chick peas`, and that is
checkable with a dictionary. Three rules:

1. **Map to the FAO item that names the same plant and the same product.**
   `Ayçiçeği Tohumu (Yağlık)` is FAO 267 `Sunflower seed`; both are the seed.
2. **When our list is finer than FAOSTAT's, collapse and say so in `note`.**
   Several of our ids legitimately share one FAO code. Do not invent a
   distinction FAOSTAT does not publish.
3. **When no FAO item names that plant, write `"fao": null` with a `reason`.**
   This is a fact about FAOSTAT's item list, not a gap in your work. Do not
   reach for a neighbouring item to avoid a null, and never map to an
   `n.e.c.` bucket — those are not in `world_norms.json` at all.

Do not map a crop to an item merely because it is in the same family. A green
fodder crop (`Fiğ (Yeşilot)`) is not the seed crop (`Fiğ Tohumu`), and FAOSTAT
publishes fodder under almost none of these names.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_crop_fao_map.py -q`
Expected: PASS, 11 passed

- [ ] **Step 6: Report the shape of what you decided**

Run and put the output in your report file:

```bash
python -c "
import json,sys,collections
sys.stdout.reconfigure(encoding='utf-8')
m=json.load(open('data/crop_fao_map.json',encoding='utf-8'))['map']
print('entries:',len(m))
print('mapped:',sum(1 for e in m.values() if e['fao'] is not None))
print('null:',sum(1 for e in m.values() if e['fao'] is None))
d=collections.Counter(e['fao'] for e in m.values() if e['fao'] is not None)
print('FAO codes used by more than one crop id:')
for code,n in d.most_common():
    if n>1: print(' ',code,n,[k for k,e in m.items() if e['fao']==code])
"
```

- [ ] **Step 7: Commit**

```bash
git add data/crop_fao_map.json tests/test_crop_fao_map.py
git commit -m "Map the field, vegetable and fodder crops to FAO item codes"
```

---

### Task 4: The fruits, nuts and spices (crop ids 100–195)

**Files:**
- Modify: `data/crop_fao_map.json`
- Modify: `tests/test_crop_fao_map.py`

**Interfaces:**
- Consumes: the file shape and decision rules established in Task 3. Read
  `data/crop_fao_map.json` and the existing entries before adding to them;
  the shape is fixed and this task adds no new keys.
- Produces: entries for crop ids at index 100–195.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_crop_fao_map.py`, directly after
`test_the_field_crops_are_all_decided`:

```python
def test_the_fruits_and_spices_are_all_decided(crop_map, crop_ids):
    for crop_id in crop_ids[100:196]:
        assert crop_id in crop_map, crop_id
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_crop_fao_map.py -q`
Expected: FAIL on `test_the_fruits_and_spices_are_all_decided`, with the first
missing crop id named in the assertion message.

- [ ] **Step 3: List this slice**

```bash
python -c "
import json,sys
sys.stdout.reconfigure(encoding='utf-8')
c=json.load(open('data/crop_norms.json',encoding='utf-8'))['crops']
for i,(k,v) in enumerate(list(c.items())[100:196],100): print(f'{i:>3} {k:<52} {v[\"label\"]}')
print('---- FAO items ----')
w=json.load(open('data/world_norms.json',encoding='utf-8'))['items']
for code in sorted(w,key=int): print(f'{code:>6} {w[code][\"label\"]}')
"
```

- [ ] **Step 4: Extend the map**

Add one entry per crop id in this slice, following the three rules written in
Task 3, Step 4. This slice is where our list is at its finest: five grape ids,
five apple ids and four mandarin ids all collapse onto single FAO items, and
`Portakal (Washington)`, `Portakal (Yafa)` and `Diğer Portakallar` are all
FAO 490 `Oranges`. Record each collapse in `note`.

Two traps in this slice specifically:

- **`Sofralık Zeytinler` and `Yağlık Zeytinler`** are both FAO 260 `Olives`;
  FAOSTAT does not split table from oil olives at the item level.
- **`İncir (Yaş)` and `İncir (Kuru)`** — FAO 569 `Figs` is the fresh crop.
  Dried figs are a processed product and FAOSTAT's crop yield does not cover
  them; decide deliberately and write down which way you went.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_crop_fao_map.py -q`
Expected: PASS, 12 passed

- [ ] **Step 6: Commit**

```bash
git add data/crop_fao_map.json tests/test_crop_fao_map.py
git commit -m "Map the fruit, nut and spice crops to FAO item codes"
```

---

### Task 5: The tail, and the completeness gate (crop ids 196–245)

**Files:**
- Modify: `data/crop_fao_map.json`
- Modify: `tests/test_crop_fao_map.py`

**Interfaces:**
- Consumes: the file shape and decision rules from Task 3.
- Produces: entries for crop ids at index 196–245, and the assertion that all
  246 are decided.

- [ ] **Step 1: Write the failing test**

In `tests/test_crop_fao_map.py`, replace the two slice tests
(`test_the_field_crops_are_all_decided` and
`test_the_fruits_and_spices_are_all_decided`) with one:

```python
def test_every_crop_we_carry_is_decided(crop_map, crop_ids):
    """Not 'most of them'. A crop id missing from this file is a crop nobody
    made a decision about, which reads exactly like a crop with no FAO item."""
    missing = [crop_id for crop_id in crop_ids if crop_id not in crop_map]
    assert missing == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_crop_fao_map.py -q`
Expected: FAIL on `test_every_crop_we_carry_is_decided`, listing the ~50
undecided crop ids.

- [ ] **Step 3: List this slice**

```bash
python -c "
import json,sys
sys.stdout.reconfigure(encoding='utf-8')
c=json.load(open('data/crop_norms.json',encoding='utf-8'))['crops']
for i,(k,v) in enumerate(list(c.items())[196:],196): print(f'{i:>3} {k:<52} {v[\"label\"]}')
print('---- FAO items ----')
w=json.load(open('data/world_norms.json',encoding='utf-8'))['items']
for code in sorted(w,key=int): print(f'{code:>6} {w[code][\"label\"]}')
"
```

- [ ] **Step 4: Extend the map**

Add one entry per remaining crop id, following the three rules from Task 3,
Step 4.

**Expect many nulls here, and do not fight them.** This slice is mostly green
fodder variants (`Fiğ (Macar) (Yeşil Ot)`, `Mısır (Slaj)`, `Çayır Otu
(Yeşilot)`, `İtalyan Çimi (Yemlik)`) and medicinal or aromatic plants
(`Salep`, `Kantaron`, `Civanperçemi`, `Ekinezya`, `Oğul Otu`). FAOSTAT
publishes yield for none of these. A null with an honest reason is the correct
answer; a strained mapping to a neighbouring item is worse than no mapping,
because it will be believed.

A handful in this slice do map cleanly — `Sorgum`, `Tatlı Patates`,
`Şeker Kamışı`, `Kara Buğday`, `Keten Tohumu`, `Fasulye, Kuru`,
`Kenevir Tohumu`, `Kuşkonmaz`. Check each against the FAO item list rather
than assuming this whole slice is empty.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_crop_fao_map.py -q`
Expected: PASS, 11 passed (the two slice tests were replaced by one)

- [ ] **Step 6: Report the final shape**

Run the reporting command from Task 3, Step 6 again and put its output in your
report file. `entries` must be 246.

- [ ] **Step 7: Commit**

```bash
git add data/crop_fao_map.json tests/test_crop_fao_map.py
git commit -m "Map the remaining crops, and require a decision for all 246"
```

---

### Task 6: The magnitude screen

**Files:**
- Create: `tests/test_crop_fao_map_scale.py`
- Modify: `data/crop_fao_map.json` (only if the screen finds a real error)

**Interfaces:**
- Consumes: `data/crop_fao_map.json`, `data/crop_norms.json`, `data/world_norms.json`.
- Produces: no importable surface — this task adds one test and, if it fails
  honestly, corrections to the map.

**What this is and what it is not.** FAOSTAT carries Türkiye (area code 223),
and so do we. A crop mapped to the wrong FAO item will usually disagree with
our own Turkish figure by an order of magnitude. Measured on known-good pairs:

| Crop | FAO Türkiye 2024 | Our province median | Ratio |
|---|---|---|---|
| Wheat (15) | 300,4 | 257 / 283 | 0,86 – 0,94 |
| Barley (44) | 253,6 | 238 | 0,94 |
| Lentils (201) | 167,2 | 141 | 0,84 |
| Chick peas (191) | 125,2 | 131 | 1,05 |
| Sunflower (267) | 226,1 | 234 | 1,03 |
| Tomatoes (388) | 8.017 | 4.278 | 1,87 |

The tomato ratio is real and legitimate: FAOSTAT's `Tomatoes` includes
processing tomatoes, which we split into `Domates (Sofralık)` and
`Domates (Salçalık)`, and a province median is not a production-weighted
national average.

**So this is a screen, not a proof.** It catches a crop mapped into the wrong
family — a cereal pointed at a vegetable is 250 against 8.000. It does **not**
catch a confusion within a family: chick peas at 125 and lentils at 167 would
pass while swapped. Nothing in this task may be described as verifying the
mapping. What verifies the mapping is a second person reading the two labels.

Only the 87 FAO items that have Türkiye data can be screened at all; a mapping
to any of the other 56 is silently skipped.

- [ ] **Step 1: Write the test**

Create `tests/test_crop_fao_map_scale.py`:

```python
import json
import statistics
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "data"
TURKIYE = "223"
LOWER, UPPER = 0.2, 5.0

# Ratios outside the band that are correct anyway. Each needs a reason that
# explains the divergence, not a note that it was observed.
ALLOWED = {
    # "crop id": "why FAOSTAT and TÜİK legitimately disagree by this much",
}


@pytest.fixture(scope="module")
def world():
    return json.loads((DATA / "world_norms.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def norms():
    return json.loads((DATA / "crop_norms.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def crop_map():
    return json.loads((DATA / "crop_fao_map.json").read_text(encoding="utf-8"))["map"]


def _turkish_median(entry: dict, years: list[int], year: int) -> float | None:
    measure = entry.get("yield_kg_da") or {}
    if not isinstance(measure, dict) or year not in years:
        return None
    position = years.index(year)
    values = [
        series[position]
        for name, series in measure.items()
        if name != "scope" and isinstance(series, list)
        and len(series) > position and series[position] is not None
    ]
    return statistics.median(values) if values else None


def _ratios(world, norms, crop_map):
    years = norms["meta"]["years"]
    for crop_id, mapping in crop_map.items():
        code = mapping["fao"]
        if code is None:
            continue
        cell = world["yield"].get(f"{code}|{TURKIYE}")
        entry = norms["crops"].get(crop_id)
        if not cell or entry is None:
            continue
        shared = sorted(set(cell) & {str(year) for year in years}, reverse=True)
        if not shared:
            continue
        year = int(shared[0])
        ours = _turkish_median(entry, years, year)
        theirs = cell[str(year)][0]
        if not ours or not theirs:
            continue
        yield crop_id, code, year, theirs, ours, theirs / ours


def test_the_screen_actually_covers_something(world, norms, crop_map):
    """A screen that silently compares nothing would pass forever."""
    assert sum(1 for _ in _ratios(world, norms, crop_map)) >= 40


def test_no_mapping_disagrees_with_our_own_turkish_figure_by_an_order_of_magnitude(
    world, norms, crop_map
):
    offenders = [
        f"{crop_id} -> FAO {code} ({year}): FAOSTAT {theirs:.1f} vs ours {ours:.1f}"
        f" = {ratio:.2f}x"
        for crop_id, code, year, theirs, ours, ratio in _ratios(world, norms, crop_map)
        if not (LOWER <= ratio <= UPPER) and crop_id not in ALLOWED
    ]
    assert offenders == [], "\n".join(offenders)
```

- [ ] **Step 2: Run it and read what it says**

Run: `python -m pytest tests/test_crop_fao_map_scale.py -q`

- [ ] **Step 3: Adjudicate every offender, one at a time**

For each crop the screen names, decide which of two things is true, and act:

- **The mapping is wrong.** Fix `data/crop_fao_map.json`. This is the outcome
  the screen exists for.
- **The mapping is right and the divergence is real** — a processing/table
  split like tomatoes, an irrigated-versus-dry split, a crop where our median
  covers three provinces. Add the crop id to `ALLOWED` with a reason that
  explains the divergence.

Do not widen `LOWER`/`UPPER` to make the test pass. The band is calibrated
against the six known-good pairs in the table above; moving it discards the
only signal this test carries.

Record in your report file, for every offender: the ratio, which of the two
outcomes you chose, and why.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_crop_fao_map_scale.py data/crop_fao_map.json
git commit -m "Screen the FAO map against our own Turkish yields"
```

---

## Out of scope

No surface reads `data/world_norms.json` or `data/crop_fao_map.json` in this
plan. Country resolution and `norms.lookup`'s country scope are P2; the budget
and comparison surfaces and the currency decision are P3.
