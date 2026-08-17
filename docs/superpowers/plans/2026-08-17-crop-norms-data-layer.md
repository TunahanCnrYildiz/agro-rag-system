# Crop Norms Data Layer (P2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `norms.lookup(crop, province)` return a yield and a price with the year and region they came from, backed by a committed TÜİK-derived data file.

**Architecture:** A hand-obtained TÜİK export is converted offline by `scripts/build_crop_norms.py` into `data/crop_norms.json`, a committed file with a shared year axis. `src/norms.py` reads it, falls back from province to national explicitly, walks back to the most recent non-null year, and reports the provenance of every figure. Nothing is fetched at runtime and nothing is invented.

**Tech Stack:** Python 3.14, pytest. No new dependencies at runtime; the converter may use a spreadsheet reader.

**Spec:** `docs/superpowers/specs/2026-08-17-numeric-data-layer-design.md`

**This is P2a.** It ships nothing user-visible. P2b consumes `norms.lookup` to prefill the budget form; it is a separate plan and depends only on the interface this plan produces, not on the TÜİK file shape.

## Global Constraints

- **Run every command from the repo root.** `src/config.py` reads a root-anchored `.env`; from anywhere else unrelated tests fail.
- **Windows console cannot encode Turkish.** Prefix any command whose output shows Turkish with `PYTHONIOENCODING=utf-8`, or keep stdout ASCII.
- Shell is PowerShell: `&&` does not work; use `;` or separate calls.
- **`src/norms.py` imports nothing from `src/engine.py`.** Validating province spellings against `location.PROVINCES` happens in the TEST, because `location` imports `engine._normalize_tr` and a data lookup has no business dragging the engine in.
- **A missing norm is never 0.** Missing data yields "no norm", never a zero, because a zero flows into the budget arithmetic and produces a confident wrong answer.
- **No interpolation, no neighbouring-province average, no carrying a national figure forward as provincial.** Each would produce a number nobody published.
- **`_load` never raises.** A missing, malformed or wrong-shaped file yields an empty table, exactly as `src/fertplan.py:_load` does.
- All code, comments, docstrings and test names in English. User-facing strings in Turkish.
- **Commit messages:** short, natural, English, capitalised verb. No `Co-Authored-By` trailer.
- **Branch:** create `crop-norms` off `main` before Task 1. Do not touch `demo`.
- **No eval run.** Nothing here reaches the model.

---

### Task 1: Obtain the TÜİK export and record its shape

**This task writes no code and it is the only task with an external dependency.** Everything else in this plan works against a fixture the tests author, so if this task stalls, Tasks 2 and 3 are unblocked and may proceed; only Task 4 needs its output.

**Files:**
- Create: `docs/superpowers/2026-08-17-tuik-export-findings.md`
- Create: `data/raw/` containing the exported file(s), committed as obtained

**Interfaces:**
- Consumes: nothing
- Produces: the real column names, units and dimensions that Task 4's converter is written against

**Background.** Reconnaissance on 2026-08-17 established that TÜİK's download endpoint `veriportali.tuik.gov.tr/api/tr/data/downloads` returns a legacy `.xls` **only with a browser session** (plain HTTP gives 403), and that MEDAS at `biruni.tuik.gov.tr/medas/?kn=92&locale=tr` is the queryable database — it has a `Düzey` (geographic level) selector and carries both `Bitkisel Üretim İstatistikleri` and `Tarımsal Ürün Fiyatları ve Üretim Değerleri`. MEDAS is a ZK application and does not respond to scripted DOM events; it needs a real browser session driven by hand.

- [ ] **Step 1: Export crop production from MEDAS**

Open `https://biruni.tuik.gov.tr/medas/?kn=92&locale=tr`. Select the topic `Bitkisel Üretim İstatistikleri`. In `Göstergeler` choose the production and yield indicators; in `Zaman` choose the last ten years; in `Düzey` choose **İl** if it is offered. Generate the report and export it.

- [ ] **Step 2: Export producer prices from MEDAS**

Repeat for the topic `Tarımsal Ürün Fiyatları ve Üretim Değerleri`. This is the actual-price dataset; do **not** use `Tarım Ürünleri Üretici Fiyat Endeksi`, which is an index and cannot be multiplied by a yield.

- [ ] **Step 3: Commit the raw exports unchanged**

```bash
git add data/raw
git commit -m "Add the raw TUIK exports the converter is written against"
```

Commit them as obtained. A converter whose input is not in the repo cannot be re-run or reviewed.

- [ ] **Step 4: Write the findings document**

Create `docs/superpowers/2026-08-17-tuik-export-findings.md` answering each of these explicitly. Where the answer is "no", say so — a "no" here is a finding, not a failure, and §11 of the spec already says the design survives a missing price dimension.

1. Does `Düzey` offer **İl** for crop production? For producer prices?
2. Exact column headers of each export, quoted.
3. The unit of the yield column — is it kg/da, kg/ha, or a total production figure from which yield must be derived? If it is a total, is the area column present so yield can be computed?
4. The unit of the price column, and its currency and time basis.
5. Which years each export covers.
6. How province names are spelled, and whether they match `src/context/location.py:PROVINCES` exactly. List every mismatch.
7. Which crops appear, and their exact names.
8. The file format actually delivered (`.xls`, `.xlsx`, `.csv`) and its encoding.

- [ ] **Step 5: Commit the findings**

```bash
git add docs/superpowers/2026-08-17-tuik-export-findings.md
git commit -m "Record what the TUIK exports actually contain"
```

---

### Task 2: Load and validate the norms file

**Files:**
- Create: `src/norms.py`
- Test: `tests/test_norms.py`

**Interfaces:**
- Consumes: `DATA_DIR` from `src/config.py`
- Produces: `NATIONAL_KEY = "TR"`, `NATIONAL_LABEL = "Türkiye"`, `_load() -> dict` returning `{"years": list[int], "crops": dict}` or `{}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_norms.py`:

```python
"""Unit tests for src/norms.py (no network, no store, no model)."""

import json

import pytest

from src import norms


def _write(tmp_path, monkeypatch, payload):
    """Point norms at a temporary file and clear its cache."""
    path = tmp_path / "crop_norms.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    return path


GOOD = {
    "meta": {
        "generated": "2026-08-17",
        "years": [2023, 2024, 2025],
        "sources": {"yield": {"name": "TUIK"}, "price": {"name": "TUIK"}},
    },
    "crops": {
        "domates": {
            "label": "Domates",
            "yield_kg_da": {"scope": "il", "Manisa": [5900, None, 6500],
                            "TR": [5500, 5600, 5700]},
            "price_tl_kg": {"scope": "tr", "TR": [6.05, 9.40, 12.40]},
        }
    },
}


def test_a_valid_file_loads(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    data = norms._load()
    assert data["years"] == [2023, 2024, 2025]
    assert "domates" in data["crops"]


def test_a_missing_file_is_an_empty_table(tmp_path, monkeypatch):
    """A broken data file must never break answering - fertplan._load's rule."""
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms._load() == {}


def test_malformed_json_is_an_empty_table(tmp_path, monkeypatch):
    path = tmp_path / "crop_norms.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    assert norms._load() == {}


def test_a_top_level_list_is_an_empty_table(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, [1, 2, 3])
    assert norms._load() == {}


def test_missing_years_is_an_empty_table(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    del payload["meta"]["years"]
    _write(tmp_path, monkeypatch, payload)
    assert norms._load() == {}


def test_a_series_of_the_wrong_length_drops_its_crop(tmp_path, monkeypatch):
    """The year axis is shared, so a mismatched series has no meaning - every
    value in it would be attributed to the wrong year."""
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["yield_kg_da"]["Manisa"] = [1, 2]
    _write(tmp_path, monkeypatch, payload)
    assert norms._load().get("crops", {}) == {}


def test_a_measure_without_a_national_row_drops_its_crop(tmp_path, monkeypatch):
    """TR is the fallback row; without it a province miss has nowhere to go."""
    payload = json.loads(json.dumps(GOOD))
    del payload["crops"]["domates"]["price_tl_kg"]["TR"]
    _write(tmp_path, monkeypatch, payload)
    assert norms._load().get("crops", {}) == {}


def test_an_unknown_scope_drops_its_crop(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["yield_kg_da"]["scope"] = "ilce"
    _write(tmp_path, monkeypatch, payload)
    assert norms._load().get("crops", {}) == {}


def test_a_bad_crop_does_not_take_the_good_ones_with_it(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["bugday"] = {"label": "Buğday", "yield_kg_da": "nonsense"}
    _write(tmp_path, monkeypatch, payload)
    assert list(norms._load()["crops"]) == ["domates"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_norms.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'src.norms'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/norms.py`:

```python
"""Yield and price norms, and the provenance that keeps a norm an average.

THE DATA IS A FILE, NOT A FETCH, and that was measured rather than assumed:
TUIK's download endpoint answers 403 without a browser session, MEDAS does not
respond to scripted interaction, and the figures are published once a year. A
runtime fetcher would carry real fragility for almost no freshness, and this
project has already paid once for a silent bootstrap failure. A committed file
also puts each norm's year and region in a diff.

NOTHING IS INVENTED. A province with no row falls back to the national row and
SAYS SO. A missing year walks back to the most recent one that exists and
carries THAT year, so an answer reads "TUIK 2023" rather than implying 2025.
There is no interpolation, no neighbouring-province average, and no carrying a
national figure forward as if it were provincial - each would produce a number
nobody published.

A MISSING NORM IS NEVER ZERO. Absence returns None, because a zero flows into
the budget arithmetic and comes out as a confident wrong answer.

This module imports nothing from src/engine.py, the same boundary src/budget.py
keeps: it is a file in, values out.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.config import DATA_DIR

_PATH = DATA_DIR / "crop_norms.json"

NATIONAL_KEY = "TR"
NATIONAL_LABEL = "Türkiye"

_MEASURES = ("yield_kg_da", "price_tl_kg")
_SCOPES = ("il", "tr")


def _valid_series(series: object, n_years: int) -> bool:
    """A series must be aligned to the shared year axis, or every value in it
    would be attributed to the wrong year."""
    if not isinstance(series, list) or len(series) != n_years:
        return False
    return all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))
               for v in series)


def _valid_measure(measure: object, n_years: int) -> bool:
    if not isinstance(measure, dict):
        return False
    if measure.get("scope") not in _SCOPES:
        return False
    if NATIONAL_KEY not in measure:
        return False
    return all(_valid_series(s, n_years)
               for k, s in measure.items() if k != "scope")


@lru_cache(maxsize=1)
def _load() -> dict:
    """Validated norms, or an empty table. Never raises.

    A crop is dropped whole when any of its measures is malformed, rather than
    half-loaded: a crop carrying a yield but a silently missing price would
    prefill one field and leave the other blank with no explanation.
    """
    try:
        raw = json.loads(Path(_PATH).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        years = raw.get("meta", {}).get("years")
        if not isinstance(years, list) or not years:
            return {}
        if not all(isinstance(y, int) and not isinstance(y, bool) for y in years):
            return {}

        crops: dict[str, dict] = {}
        for crop_id, crop in (raw.get("crops") or {}).items():
            if not isinstance(crop, dict) or not isinstance(crop.get("label"), str):
                continue
            if all(_valid_measure(crop.get(m), len(years)) for m in _MEASURES):
                crops[crop_id] = crop
        return {"years": years, "crops": crops}
    except Exception:  # noqa: BLE001 - a broken data file must not break answering
        return {}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_norms.py -q
```

Expected: `9 passed`.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest -q
git add src/norms.py tests/test_norms.py
git commit -m "Load and validate the crop norms file"
```

The full suite was 564 before this task; expect 573.

---

### Task 3: Lookup, fallback and provenance

**Files:**
- Modify: `src/norms.py`
- Test: `tests/test_norms.py`

**Interfaces:**
- Consumes: `_load`, `NATIONAL_KEY`, `NATIONAL_LABEL` from Task 2
- Produces:
  - `NormValue(amount: float, year: int, scope: str, region: str)`
  - `CropNorm(crop: str, label: str, yield_kg_da: NormValue | None, price_tl_kg: NormValue | None)`
  - `available_crops() -> tuple[tuple[str, str], ...]` — `(id, label)` pairs sorted by label
  - `lookup(crop: str, province: str | None) -> CropNorm | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_norms.py`:

```python
def test_available_crops_returns_id_label_pairs(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["armut"] = {
        "label": "Armut",
        "yield_kg_da": {"scope": "tr", "TR": [1, 2, 3]},
        "price_tl_kg": {"scope": "tr", "TR": [4, 5, 6]},
    }
    _write(tmp_path, monkeypatch, payload)
    assert norms.available_crops() == (("armut", "Armut"), ("domates", "Domates"))


def test_available_crops_is_empty_without_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms.available_crops() == ()


def test_a_province_row_is_used_and_reported_as_provincial(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    n = norms.lookup("domates", "Manisa")
    assert n.yield_kg_da.amount == 6500.0
    assert n.yield_kg_da.year == 2025
    assert n.yield_kg_da.scope == "il"
    assert n.yield_kg_da.region == "Manisa"


def test_a_province_without_a_row_falls_back_to_the_nation(tmp_path, monkeypatch):
    """And says so - the user must be able to read which one they got."""
    _write(tmp_path, monkeypatch, GOOD)
    n = norms.lookup("domates", "Rize")
    assert n.yield_kg_da.amount == 5700.0
    assert n.yield_kg_da.scope == "tr"
    assert n.yield_kg_da.region == "Türkiye"


def test_no_province_at_all_falls_back_to_the_nation(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    n = norms.lookup("domates", None)
    assert n.yield_kg_da.scope == "tr"


def test_a_national_scope_measure_ignores_the_province(tmp_path, monkeypatch):
    """price_tl_kg has scope 'tr': naming a province must not invent a
    provincial reading of a national figure."""
    _write(tmp_path, monkeypatch, GOOD)
    n = norms.lookup("domates", "Manisa")
    assert n.price_tl_kg.amount == 12.40
    assert n.price_tl_kg.scope == "tr"
    assert n.price_tl_kg.region == "Türkiye"


def test_a_null_latest_year_walks_back_and_carries_that_year(tmp_path, monkeypatch):
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["yield_kg_da"]["Manisa"] = [5900, 6300, None]
    _write(tmp_path, monkeypatch, payload)
    n = norms.lookup("domates", "Manisa")
    assert n.yield_kg_da.amount == 6300.0
    assert n.yield_kg_da.year == 2024


def test_an_all_null_series_yields_no_norm_rather_than_zero(tmp_path, monkeypatch):
    """The binding rule: a zero would flow into the budget arithmetic and come
    out as a confident wrong answer."""
    payload = json.loads(json.dumps(GOOD))
    payload["crops"]["domates"]["price_tl_kg"]["TR"] = [None, None, None]
    _write(tmp_path, monkeypatch, payload)
    n = norms.lookup("domates", "Manisa")
    assert n.price_tl_kg is None
    assert n.yield_kg_da is not None


def test_an_unknown_crop_has_no_norm(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert norms.lookup("kivi", "Manisa") is None


def test_lookup_without_a_file_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(norms, "_PATH", tmp_path / "nope.json")
    norms._load.cache_clear()
    assert norms.lookup("domates", "Manisa") is None


def test_the_crop_label_is_carried(tmp_path, monkeypatch):
    _write(tmp_path, monkeypatch, GOOD)
    assert norms.lookup("domates", "Manisa").label == "Domates"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_norms.py -q
```

Expected: FAIL, `AttributeError: module 'src.norms' has no attribute 'available_crops'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/norms.py`:

```python
@dataclass(frozen=True)
class NormValue:
    """One figure and where it came from. The provenance travels with the value
    because a provincial reading and a national one must never look alike."""
    amount: float
    year: int
    scope: str          # "il" | "tr"
    region: str         # "Manisa" | "Türkiye"


@dataclass(frozen=True)
class CropNorm:
    crop: str
    label: str
    yield_kg_da: NormValue | None
    price_tl_kg: NormValue | None


def available_crops() -> tuple[tuple[str, str], ...]:
    """(id, label) for every crop the file carries, sorted by label."""
    crops = _load().get("crops", {})
    return tuple(sorted(((cid, c["label"]) for cid, c in crops.items()),
                        key=lambda pair: pair[1]))


def _pick(measure: dict, years: list[int], province: str | None) -> NormValue | None:
    """The province's row when the measure has one, otherwise the national row,
    then the most recent non-null year in it."""
    provincial = (measure.get("scope") == "il"
                  and province is not None
                  and province in measure)
    key = province if provincial else NATIONAL_KEY
    series = measure.get(key)
    if not isinstance(series, list):
        return None
    for i in range(len(series) - 1, -1, -1):
        if series[i] is not None:
            return NormValue(
                amount=float(series[i]),
                year=years[i],
                scope="il" if provincial else "tr",
                region=key if provincial else NATIONAL_LABEL,
            )
    return None


def lookup(crop: str, province: str | None) -> CropNorm | None:
    """Norms for a crop, or None when the file does not carry it.

    A measure that resolves to nothing is None on the result rather than absent,
    so the caller prefills the fields it can and leaves the rest to the user.
    """
    data = _load()
    entry = data.get("crops", {}).get(crop)
    if entry is None:
        return None
    years = data["years"]
    return CropNorm(
        crop=crop,
        label=entry["label"],
        yield_kg_da=_pick(entry["yield_kg_da"], years, province),
        price_tl_kg=_pick(entry["price_tl_kg"], years, province),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_norms.py -q
```

Expected: `20 passed`.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest -q
git add src/norms.py tests/test_norms.py
git commit -m "Resolve a norm to a province or the nation, and say which"
```

Expect 584 in the full suite.

---

### Task 4: The converter and the real data file

**Depends on Task 1.** Write the converter against the column names recorded in `docs/superpowers/2026-08-17-tuik-export-findings.md`, not against the illustrative schema in the spec.

**Files:**
- Create: `scripts/build_crop_norms.py`
- Create: `data/crop_norms.json` (generated, committed)
- Test: `tests/test_build_crop_norms.py`

**Interfaces:**
- Consumes: the raw exports in `data/raw/`, and the schema `src/norms.py` validates
- Produces: `data/crop_norms.json`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_build_crop_norms.py`. These tests exercise `build`, which takes already-parsed tuples and is therefore independent of the export's format — they can be written and run before the export exists. `read_export` is the format-dependent half and is covered by the manual inspection in Step 5.

```python
"""Tests for the offline converter. It runs by hand, once a year, so its job is
to fail loudly rather than to be convenient."""

import json

import pytest

from scripts import build_crop_norms as bcn


ROWS = [
    # (province, crop, year, yield_kg_da, price_tl_kg)
    ("Manisa", "Domates", 2024, 6300.0, None),
    ("Manisa", "Domates", 2025, 6500.0, None),
    ("Türkiye", "Domates", 2024, 5600.0, 9.40),
    ("Türkiye", "Domates", 2025, 5700.0, 12.40),
]


def test_the_year_axis_is_shared_and_sorted():
    out = bcn.build(ROWS)
    assert out["meta"]["years"] == [2024, 2025]


def test_series_are_aligned_to_the_year_axis():
    out = bcn.build(ROWS)
    assert out["crops"]["domates"]["yield_kg_da"]["Manisa"] == [6300.0, 6500.0]


def test_a_missing_year_becomes_null_not_zero():
    """A gap must survive as a gap. Zero would flow into the arithmetic."""
    rows = [r for r in ROWS if not (r[0] == "Manisa" and r[2] == 2024)]
    out = bcn.build(rows)
    assert out["crops"]["domates"]["yield_kg_da"]["Manisa"] == [None, 6500.0]


def test_the_national_row_is_keyed_TR():
    out = bcn.build(ROWS)
    assert "TR" in out["crops"]["domates"]["yield_kg_da"]


def test_scope_is_il_when_any_province_row_exists():
    out = bcn.build(ROWS)
    assert out["crops"]["domates"]["yield_kg_da"]["scope"] == "il"


def test_scope_is_tr_when_only_the_nation_has_rows():
    rows = [r for r in ROWS if r[0] == "Türkiye"]
    out = bcn.build(rows)
    assert out["crops"]["domates"]["yield_kg_da"]["scope"] == "tr"


def test_an_unparseable_number_is_skipped_loudly(capsys):
    """Silently zeroing a bad cell is how a wrong figure reaches a user."""
    rows = ROWS + [("Manisa", "Domates", 2025, "yok", None)]
    bcn.build(rows)
    assert "yok" in capsys.readouterr().err


def test_an_unknown_province_is_skipped_loudly(capsys):
    rows = ROWS + [("Kudüs", "Domates", 2025, 1.0, None)]
    out = bcn.build(rows)
    assert "Kudüs" in capsys.readouterr().err
    assert "Kudüs" not in out["crops"]["domates"]["yield_kg_da"]


def test_the_output_passes_the_loader_that_will_read_it(tmp_path, monkeypatch):
    """The converter and the loader must agree, or the file is dead on arrival."""
    from src import norms
    path = tmp_path / "crop_norms.json"
    path.write_text(json.dumps(bcn.build(ROWS), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(norms, "_PATH", path)
    norms._load.cache_clear()
    assert norms.lookup("domates", "Manisa").yield_kg_da.amount == 6500.0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_build_crop_norms.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'scripts.build_crop_norms'`.

- [ ] **Step 3: Write the converter**

The converter splits in two on purpose. `build` does the shaping and is fully specified below because it does not depend on the export's format. `read_export` does the parsing and is the only part that needs Task 1's findings — writing it before the file is in hand would be inventing a format.

Create `scripts/build_crop_norms.py`:

```python
"""Turn the hand-obtained TUIK exports into data/crop_norms.json.

Runs OFFLINE, by hand, about once a year - the figures are published annually
and TUIK's endpoints resist automation (403 without a browser session; MEDAS
does not answer scripted interaction). So this is a script, not a service.

It fails LOUDLY. Every row it cannot use is printed to stderr and skipped,
because the alternative - a quietly zeroed cell - reaches a user as a confident
wrong figure, which is the defect class the whole budget route was rewritten to
remove.

Importing src.context.location here is fine even though src/norms.py refuses to:
this never runs in a request, so pulling the engine in costs nothing.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from src.config import DATA_DIR
from src.context.location import PROVINCES
from src.engine import _normalize_tr

NATIONAL = "TR"
# Whatever the export calls the country-wide row folds onto NATIONAL.
_NATIONAL_NAMES = {"tr", "turkiye", "turkiye toplam", "toplam", "genel toplam"}

# Filled in from docs/superpowers/2026-08-17-tuik-export-findings.md.
SOURCES = {
    "yield": {"name": "TÜİK Bitkisel Üretim İstatistikleri",
              "bulletin": "53939", "published": "2025-12-26"},
    "price": {"name": "TÜİK Tarımsal Ürün Fiyatları ve Üretim Değerleri",
              "published": None},
}


def _number(raw) -> float | None:
    """Turkish-formatted cell to float, or None. Never guesses."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def build(rows) -> dict:
    """Group (province, crop, year, yield_kg_da, price_tl_kg) tuples into the
    schema src/norms.py validates.

    Format-independent on purpose: read_export does the parsing, this does the
    shaping, and only this half can be tested before the export exists.
    """
    known = set(PROVINCES)
    years = sorted({r[2] for r in rows if isinstance(r[2], int)})
    index = {y: i for i, y in enumerate(years)}
    crops: dict[str, dict] = {}

    for province, crop, year, yield_raw, price_raw in rows:
        folded = _normalize_tr(str(province))
        region = NATIONAL if folded in _NATIONAL_NAMES else str(province).strip()
        if region != NATIONAL and region not in known:
            print(f"skipped unknown province: {province!r}", file=sys.stderr)
            continue
        if year not in index:
            print(f"skipped unknown year: {year!r}", file=sys.stderr)
            continue

        crop_id = _normalize_tr(str(crop))
        entry = crops.setdefault(
            crop_id, {"label": str(crop).strip(), "yield_kg_da": {}, "price_tl_kg": {}})

        for measure, raw in (("yield_kg_da", yield_raw), ("price_tl_kg", price_raw)):
            if raw is None:
                continue
            value = _number(raw)
            if value is None:
                print(f"skipped unparseable {measure} for "
                      f"{crop} / {province} / {year}: {raw!r}", file=sys.stderr)
                continue
            series = entry[measure].setdefault(region, [None] * len(years))
            series[index[year]] = value

    for entry in crops.values():
        for measure in ("yield_kg_da", "price_tl_kg"):
            series_by_region = entry[measure]
            # The national row must exist even when empty: it is the fallback,
            # and src/norms.py drops a crop that has no TR row.
            series_by_region.setdefault(NATIONAL, [None] * len(years))
            entry[measure] = {
                "scope": "il" if any(k != NATIONAL for k in series_by_region) else "tr",
                **series_by_region,
            }

    return {"meta": {"generated": date.today().isoformat(),
                     "years": years, "sources": SOURCES},
            "crops": crops}


def read_export(path: Path):
    """Yield (province, crop, year, yield_kg_da, price_tl_kg) from one export.

    THIS is the format-dependent half. Write it against the column names,
    units and layout recorded in
    docs/superpowers/2026-08-17-tuik-export-findings.md - not against a guess.
    Three things the findings must settle before this is written:
      - whether the yield column is kg/da, kg/ha, or a total that must be
        divided by an area column;
      - the price column's currency and time basis;
      - how the export spells province names, and the rename table for any
        that do not match src/context/location.PROVINCES.
    Emit None for a measure the export does not carry; do not emit 0.
    """
    raise NotImplementedError("write against the findings document")


def main() -> None:
    rows = []
    for path in sorted((DATA_DIR / "raw").glob("*")):
        rows.extend(read_export(path))
    out = DATA_DIR / "crop_norms.json"
    out.write_text(json.dumps(build(rows), ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_build_crop_norms.py -q
```

Expected: `9 passed`.

- [ ] **Step 5: Generate and commit the real file**

```bash
python -m scripts.build_crop_norms
python -m pytest -q
```

Inspect `data/crop_norms.json` before committing: check the crop count, the year range, and that a province you know (Manisa) carries a plausible yield. Read the stderr output — every skipped row is a data question, not noise.

```bash
git add scripts/build_crop_norms.py tests/test_build_crop_norms.py data/crop_norms.json
git commit -m "Convert the TUIK exports into the committed norms file"
```

---

### Task 5: Pin the real file against the province table

**Files:**
- Test: `tests/test_norms.py`

**Interfaces:**
- Consumes: `data/crop_norms.json` from Task 4, `src/context/location.PROVINCES`

This is the guard the spec calls for: a province spelled `"Afyon"` instead of `"Afyonkarahisar"` does not raise, it silently never matches, which is the failure mode this project keeps meeting.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_norms.py`:

```python
def test_the_shipped_file_uses_canonical_province_names():
    """A misspelled province does not raise - it silently never matches. The
    test is the only thing that can see it."""
    from src.context.location import PROVINCES
    norms._load.cache_clear()
    data = norms._load()
    assert data, "data/crop_norms.json did not load - the shipped file is broken"
    allowed = set(PROVINCES) | {norms.NATIONAL_KEY}
    unknown = set()
    for crop in data["crops"].values():
        for measure in ("yield_kg_da", "price_tl_kg"):
            unknown |= {k for k in crop[measure] if k != "scope"} - allowed
    assert unknown == set(), f"unknown province keys: {sorted(unknown)}"


def test_the_shipped_file_carries_at_least_one_crop():
    norms._load.cache_clear()
    assert norms.available_crops(), "the shipped norms file carries no crops"
```

- [ ] **Step 2: Run the tests**

```bash
python -m pytest tests/test_norms.py -q
```

If either fails, the converter's rename table is incomplete — fix `scripts/build_crop_norms.py`, regenerate `data/crop_norms.json`, and run again. Do not relax the test.

- [ ] **Step 3: Run the full suite and commit**

```bash
python -m pytest -q
git add tests/test_norms.py
git commit -m "Pin the shipped norms file against the province table"
```

---

## Finishing

- [ ] Run the whole suite from the repo root: `python -m pytest -q`. Every test green, and the 2 pre-existing warnings unchanged.
- [ ] **Do not run the 59-case eval.** Nothing in this plan reaches the model.
- [ ] Confirm `src/norms.py` still imports nothing from `src/engine.py`: `python -c "import ast,sys; print([n for n in ast.walk(ast.parse(open('src/norms.py',encoding='utf-8').read())) if isinstance(n,(ast.Import,ast.ImportFrom)) and 'engine' in ast.dump(n)])"` — expect `[]`.
- [ ] Merge to `main` with `--no-ff`. **Do not touch `demo`.**
- [ ] P2b (the prefill) is now unblocked: it depends on `norms.lookup`, `norms.available_crops` and the `NormValue` fields, all of which this plan fixes.
