# OpenAlex Global-Crop Fetcher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `src/fetch_openalex.py` that harvests English open-access PDFs for tropical/global gap crops from OpenAlex into `docs/books/` as `oa_*.pdf`.

**Architecture:** Mirror `fetch_dergipark.py`: a curated `CROP_TERMS` list drives per-crop OpenAlex `/works` searches (open-access + English), candidates are deduped (id+doi) and off-topic-filtered by title, then PDFs are streamed to disk and validated. Reuses `pdf_fetch_utils` (session + %PDF-validating writer) and `fetch_dergipark._OFFTOPIC_REC`.

**Tech Stack:** Python 3, requests, OpenAlex REST API (no key; polite pool via `mailto`), pytest.

## Global Constraints

- New file only: `src/fetch_openalex.py`; test file `tests/test_fetch_openalex.py`. Do NOT modify other modules.
- OpenAlex endpoint: `https://api.openalex.org/works`; add `mailto` param on every call (polite pool); no API key.
- Per-crop filter: `title_and_abstract.search:<crop>,open_access.is_oa:true,language:en`; sort `cited_by_count:desc`.
- File naming: `oa_<OpenAlexID>.pdf` (OpenAlex id is the trailing `W…` of `work["id"]`).
- PDF validation: reuse `stream_pdf_to_file(resp, dest, MIN_BYTES, "openalex")`; `MIN_BYTES = 60_000`.
- Off-topic: reject candidates whose title matches `fetch_dergipark._OFFTOPIC_REC`.
- Dedup within batch by oa_id AND doi; skip files already on disk or under `docs/books/_offtopic/`. No cross-source (dp_/ia_) dedup.
- Polite: `mailto`, delays, backoff on 429/5xx.
- Run tests from project root: `PYTHONIOENCODING=utf-8 python -m pytest`. Commit messages: English, concise, no AI-style body, no Co-Authored-By.

---

### Task 1: Module scaffold + constants + `_work_to_candidate`

**Files:**
- Create: `src/fetch_openalex.py`
- Create: `tests/test_fetch_openalex.py`

**Interfaces:**
- Consumes: `fetch_dergipark._OFFTOPIC_REC` (compiled regex).
- Produces: `CROP_TERMS: list[str]`, module constants, and
  `_work_to_candidate(work: dict) -> tuple[str, str, str, str] | None`
  returning `(oa_id, pdf_url, doi, title)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fetch_openalex.py`:

```python
from src.fetch_openalex import _work_to_candidate


def _work(**kw):
    base = {
        "id": "https://openalex.org/W123",
        "language": "en",
        "best_oa_location": {"pdf_url": "http://x/y.pdf"},
        "open_access": {"oa_url": "http://x/landing"},
        "doi": "https://doi.org/10.1/x",
        "title": "Cassava fertilization field trial",
    }
    base.update(kw)
    return base


def test_candidate_from_valid_oa_work():
    assert _work_to_candidate(_work()) == (
        "W123", "http://x/y.pdf", "https://doi.org/10.1/x",
        "Cassava fertilization field trial",
    )


def test_none_when_not_english():
    assert _work_to_candidate(_work(language="fr")) is None


def test_none_when_no_oa_pdf():
    assert _work_to_candidate(_work(best_oa_location={}, open_access={})) is None


def test_falls_back_to_oa_url_when_no_pdf_url():
    w = _work(best_oa_location={"pdf_url": None})
    assert _work_to_candidate(w)[1] == "http://x/landing"


def test_none_when_offtopic_title():
    # "cattle" is in _OFFTOPIC_REC -> livestock paper rejected
    assert _work_to_candidate(_work(title="Cattle feed value of cassava peels")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fetch_openalex.py -v`
Expected: FAIL (module `src.fetch_openalex` does not exist yet).

- [ ] **Step 3: Create the module with constants + helper**

Create `src/fetch_openalex.py`:

```python
"""Harvest English open-access PDFs for tropical/global gap crops from OpenAlex.

OpenAlex (openalex.org) is a free scholarly index. We query its /works endpoint
per curated gap crop (open-access + English), take well-cited candidates that
expose an OA PDF URL, drop off-topic (livestock/economics) ones by title, and
stream each PDF into docs/books/ as ``oa_<OpenAlexID>.pdf`` alongside the
DergiPark (dp_) and Internet Archive (ia_) corpora.

    python -m src.fetch_openalex --list-crops
    python -m src.fetch_openalex --dry-run --max 25 --per-crop 4
    python -m src.fetch_openalex --max 25 --per-crop 4
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

try:
    from .config import BOOKS_DIR
    from .pdf_fetch_utils import pdf_session, stream_pdf_to_file
    from .fetch_dergipark import _OFFTOPIC_REC
except ImportError:  # pragma: no cover
    from config import BOOKS_DIR  # type: ignore
    from pdf_fetch_utils import pdf_session, stream_pdf_to_file  # type: ignore
    from fetch_dergipark import _OFFTOPIC_REC  # type: ignore

OPENALEX_URL = "https://api.openalex.org/works"
POLITE_MAILTO = "agrobotanybot@ekolojiktarim.com.tr"  # OpenAlex polite pool

OA_DELAY = 0.3     # between API calls
OA_TIMEOUT = 30
OA_RETRIES = 3
PDF_DELAY = 1.5    # between PDF downloads
MIN_BYTES = 60_000  # skip tiny stubs

# Curated tropical/global gap crops under-covered by the TR/US corpus.
CROP_TERMS = [
    "cassava", "plantain", "sorghum", "pearl millet", "finger millet",
    "cowpea", "yam", "taro", "sweet potato", "rice", "teff",
    "pigeon pea", "groundnut", "banana",
]


def _work_to_candidate(work: dict) -> tuple[str, str, str, str] | None:
    """Return (oa_id, pdf_url, doi, title) for an English OA work with a PDF,
    or None (non-English, no OA PDF, bad id, or off-topic title)."""
    if (work.get("language") or "") != "en":
        return None
    loc = work.get("best_oa_location") or {}
    pdf_url = loc.get("pdf_url") or (work.get("open_access") or {}).get("oa_url")
    if not pdf_url:
        return None
    oa_id = (work.get("id") or "").rsplit("/", 1)[-1]
    if not oa_id.startswith("W"):
        return None
    title = work.get("title") or work.get("display_name") or ""
    if _OFFTOPIC_REC.search(title):
        return None
    return oa_id, pdf_url, work.get("doi") or "", title
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fetch_openalex.py -v`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fetch_openalex.py tests/test_fetch_openalex.py
git commit -m "Add OpenAlex fetcher scaffold + work-to-candidate parsing"
```

---

### Task 2: `_oa_get` (API call + backoff) and `search_crop`

**Files:**
- Modify: `src/fetch_openalex.py`
- Modify: `tests/test_fetch_openalex.py`

**Interfaces:**
- Consumes: `_work_to_candidate` (Task 1).
- Produces:
  - `_oa_get(session, params: dict) -> dict | None`
  - `search_crop(session, crop: str, max_per_crop: int) -> list[tuple]`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fetch_openalex.py`:

```python
from src import fetch_openalex as fo
from src.fetch_openalex import _oa_get, POLITE_MAILTO


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise fo.requests.RequestException(f"http {self.status_code}")


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return self._resp


def test_oa_get_adds_mailto_and_returns_json():
    session = _FakeSession(_FakeResp(200, {"results": [], "meta": {}}))
    out = _oa_get(session, {"filter": "x"})
    assert out == {"results": [], "meta": {}}
    assert session.calls[0]["mailto"] == POLITE_MAILTO


def test_search_crop_filters_and_pages(monkeypatch):
    page = {
        "results": [
            {"id": "https://openalex.org/W1", "language": "en",
             "best_oa_location": {"pdf_url": "u1.pdf"}, "doi": "d1",
             "title": "cassava yield"},
            {"id": "https://openalex.org/W2", "language": "fr",
             "best_oa_location": {"pdf_url": "u2.pdf"}, "doi": "d2",
             "title": "manioc rendement"},
        ],
        "meta": {"next_cursor": None},
    }
    monkeypatch.setattr(fo, "_oa_get", lambda s, p: page)
    monkeypatch.setattr(fo.time, "sleep", lambda *a: None)
    out = fo.search_crop(object(), "cassava", 10)
    assert [c[0] for c in out] == ["W1"]  # W2 dropped (not English)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fetch_openalex.py -k "oa_get or search_crop" -v`
Expected: FAIL with `AttributeError` (`_oa_get` / `search_crop` not defined).

- [ ] **Step 3: Implement `_oa_get` and `search_crop`**

Append to `src/fetch_openalex.py` (after `_work_to_candidate`):

```python
def _oa_get(session: requests.Session, params: dict) -> dict | None:
    """Call the OpenAlex /works endpoint (with mailto) and return parsed JSON,
    retrying with backoff on 429 / 5xx."""
    query = {**params, "mailto": POLITE_MAILTO}
    for attempt in range(1, OA_RETRIES + 1):
        try:
            resp = session.get(OPENALEX_URL, params=query, timeout=OA_TIMEOUT)
            if resp.status_code in (429, 500, 502, 503):
                raise requests.RequestException(f"http {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == OA_RETRIES:
                print(f"[openalex] API failed ({params.get('filter', '')}): {exc}")
                return None
            time.sleep(2 * attempt)
    return None


def search_crop(
    session: requests.Session, crop: str, max_per_crop: int
) -> list[tuple[str, str, str, str]]:
    """Return up to max_per_crop (oa_id, pdf_url, doi, title) candidates for a
    crop: English, open-access, PDF-bearing, on-topic; well-cited first."""
    out: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    cursor = "*"
    flt = f"title_and_abstract.search:{crop},open_access.is_oa:true,language:en"
    while len(out) < max_per_crop and cursor:
        data = _oa_get(session, {
            "filter": flt,
            "sort": "cited_by_count:desc",
            "per-page": 50,
            "cursor": cursor,
        })
        if not data:
            break
        for work in data.get("results", []):
            cand = _work_to_candidate(work)
            if cand and cand[0] not in seen:
                seen.add(cand[0])
                out.append(cand)
        cursor = (data.get("meta") or {}).get("next_cursor")
        time.sleep(OA_DELAY)
    return out[:max_per_crop]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fetch_openalex.py -v`
Expected: all tests PASS (7 total).

- [ ] **Step 5: Commit**

```bash
git add src/fetch_openalex.py tests/test_fetch_openalex.py
git commit -m "Add OpenAlex API call + per-crop search"
```

---

### Task 3: `_collect_candidates` (dedup) + `_is_pruned`

**Files:**
- Modify: `src/fetch_openalex.py`
- Modify: `tests/test_fetch_openalex.py`

**Interfaces:**
- Consumes: `search_crop` (Task 2), `BOOKS_DIR`.
- Produces:
  - `_collect_candidates(session, crops: list[str], per_crop: int) -> list[tuple]`
  - `_is_pruned(oa_id: str) -> bool`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fetch_openalex.py`:

```python
def test_collect_dedups_by_id_and_doi(monkeypatch):
    data = {
        "cropA": [("W1", "u1", "d1", "t1"), ("W2", "u2", "d2", "t2")],
        "cropB": [("W1", "u1", "d1", "t1"), ("W3", "u3", "d2", "t3")],
    }
    monkeypatch.setattr(fo, "search_crop", lambda s, crop, n: data[crop])
    monkeypatch.setattr(fo.time, "sleep", lambda *a: None)
    out = fo._collect_candidates(object(), ["cropA", "cropB"], 10)
    # W1 kept once (dup id); W3 dropped (doi d2 already taken by W2)
    assert [c[0] for c in out] == ["W1", "W2"]


def test_is_pruned_detects_offtopic(tmp_path, monkeypatch):
    books = tmp_path / "books"
    (books / "_offtopic").mkdir(parents=True)
    (books / "_offtopic" / "oa_W9.pdf").write_bytes(b"x")
    monkeypatch.setattr(fo, "BOOKS_DIR", books)
    assert fo._is_pruned("W9") is True
    assert fo._is_pruned("W8") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fetch_openalex.py -k "collect or pruned" -v`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement the two helpers**

Append to `src/fetch_openalex.py`:

```python
def _collect_candidates(
    session: requests.Session, crops: list[str], per_crop: int
) -> list[tuple[str, str, str, str]]:
    """Gather candidates across crops, deduped by oa_id AND doi."""
    seen_ids: set[str] = set()
    seen_dois: set[str] = set()
    out: list[tuple[str, str, str, str]] = []
    for crop in crops:
        kept = 0
        for oa_id, pdf_url, doi, title in search_crop(session, crop, per_crop):
            if oa_id in seen_ids or (doi and doi in seen_dois):
                continue
            seen_ids.add(oa_id)
            if doi:
                seen_dois.add(doi)
            out.append((oa_id, pdf_url, doi, title))
            kept += 1
        print(f"[openalex] crop '{crop}': {kept} candidates")
        time.sleep(OA_DELAY)
    return out


def _is_pruned(oa_id: str) -> bool:
    """True if this work was already moved to docs/books/_offtopic/ (don't
    re-download)."""
    offtopic = BOOKS_DIR / "_offtopic"
    return offtopic.exists() and any(offtopic.rglob(f"oa_{oa_id}.pdf"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fetch_openalex.py -v`
Expected: all PASS (9 total).

- [ ] **Step 5: Commit**

```bash
git add src/fetch_openalex.py tests/test_fetch_openalex.py
git commit -m "Add OpenAlex candidate collection (dedup) + prune skip"
```

---

### Task 4: `download`, `run`, `main` (CLI) + validation harvest

**Files:**
- Modify: `src/fetch_openalex.py`
- Modify: `tests/test_fetch_openalex.py`

**Interfaces:**
- Consumes: `_collect_candidates`, `_is_pruned`, `pdf_session`, `stream_pdf_to_file`.
- Produces:
  - `download(session, url: str, dest: Path) -> bool`
  - `run(crop: str | None, max_books: int, per_crop: int, dry_run: bool) -> int`
  - `main() -> None`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fetch_openalex.py`:

```python
def test_list_crops_prints_all(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["fetch_openalex", "--list-crops"])
    fo.main()
    printed = capsys.readouterr().out
    assert "cassava" in printed and "sorghum" in printed


def test_run_dry_run_downloads_nothing(tmp_path, monkeypatch):
    books = tmp_path / "books"
    monkeypatch.setattr(fo, "BOOKS_DIR", books)
    monkeypatch.setattr(fo, "pdf_session", lambda *a, **k: object())
    monkeypatch.setattr(
        fo, "_collect_candidates",
        lambda s, crops, per: [("W1", "u1.pdf", "d1", "cassava trial")],
    )
    # download must never be called in dry-run
    monkeypatch.setattr(fo, "download",
                        lambda *a: (_ for _ in ()).throw(AssertionError("no download")))
    n = fo.run(crop=None, max_books=25, per_crop=4, dry_run=True)
    assert n == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fetch_openalex.py -k "list_crops or dry_run" -v`
Expected: FAIL (`main` / `run` not defined).

- [ ] **Step 3: Implement download, run, main**

Append to `src/fetch_openalex.py`:

```python
def download(session: requests.Session, url: str, dest: Path) -> bool:
    """Stream a candidate PDF to disk, validating the %PDF header + size."""
    try:
        resp = session.get(url, stream=True, timeout=120)
    except requests.RequestException as exc:
        print(f"[openalex]   ! download error: {exc}")
        return False
    if resp.status_code != 200:
        print(f"[openalex]   ! http {resp.status_code}, skipping")
        resp.close()
        return False
    return stream_pdf_to_file(resp, dest, MIN_BYTES, "openalex")


def run(crop: str | None, max_books: int, per_crop: int, dry_run: bool) -> int:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    session = pdf_session()
    crops = [crop] if crop else CROP_TERMS
    candidates = _collect_candidates(session, crops, per_crop)
    print(f"[openalex] {len(candidates)} candidate(s); target {max_books}\n")

    if dry_run:
        for i, (oa_id, _url, _doi, title) in enumerate(candidates[:max_books], 1):
            print(f"{i:>3}  {oa_id:>12}  {title[:60]}")
        print("\n[openalex] preview only. Re-run without --dry-run to download.")
        return 0

    saved = 0
    for oa_id, url, _doi, title in candidates:
        if saved >= max_books:
            break
        dest = BOOKS_DIR / f"oa_{oa_id}.pdf"
        if dest.exists():
            print(f"[openalex]   = already have {dest.name}, skipping")
            continue
        if _is_pruned(oa_id):
            print(f"[openalex]   = oa_{oa_id} previously pruned, skipping")
            continue
        print(f"[openalex] {title[:55]}")
        if download(session, url, dest):
            saved += 1
        time.sleep(PDF_DELAY)

    print(f"\n[openalex] DONE. downloaded {saved} paper(s) into {BOOKS_DIR}")
    if saved:
        print("[openalex] next: python -m src.ingest")
    return saved


def main() -> None:
    p = argparse.ArgumentParser(
        description="Harvest open-access global-crop papers from OpenAlex."
    )
    p.add_argument("--max", type=int, default=25, help="Max PDFs to download.")
    p.add_argument("--per-crop", type=int, default=4,
                   help="Max candidates pulled per crop.")
    p.add_argument("--crop", default=None,
                   help="Limit to one crop term (e.g. cassava).")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview candidates without downloading.")
    p.add_argument("--list-crops", action="store_true",
                   help="List curated crop terms and exit.")
    args = p.parse_args()

    if args.list_crops:
        for c in CROP_TERMS:
            print(f"  {c}")
        return

    run(crop=args.crop, max_books=args.max, per_crop=args.per_crop,
        dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONIOENCODING=utf-8 python -m pytest tests/test_fetch_openalex.py -v`
Expected: all PASS (11 total).

- [ ] **Step 5: Commit**

```bash
git add src/fetch_openalex.py tests/test_fetch_openalex.py
git commit -m "Add OpenAlex download + run + CLI"
```

- [ ] **Step 6: Validation harvest (manual; needs network + LM Studio)**

Preview, then harvest a small batch:

Run: `PYTHONIOENCODING=utf-8 python -m src.fetch_openalex --dry-run --max 25 --per-crop 4`
Expected: a list of ~25 candidate titles across gap crops (cassava, sorghum, …).

Run: `PYTHONIOENCODING=utf-8 python -m src.fetch_openalex --max 25 --per-crop 4`
Expected: `[openalex] DONE. downloaded N paper(s)` with `oa_*.pdf` in `docs/books/`
(N may be < 25 if some OA URLs are landing pages that fail the %PDF check — that
is expected; note the success rate).

Then ingest and probe retrieval:

Run: `PYTHONIOENCODING=utf-8 python -m src.ingest`
Run: `PYTHONIOENCODING=utf-8 python -m src.engine "cassava fertilization"`
Expected: a grounded answer; retrieval should include an `oa_*` source. If the
PDF success rate is very low, revisit landing-page → PDF resolution (out of scope
for v1, but note it for a follow-up).

---

## Self-Review

**Spec coverage:**
- File `src/fetch_openalex.py` reusing pdf_fetch_utils + `_OFFTOPIC_REC` → Tasks 1-4. ✓
- Constants incl. `CROP_TERMS`, `OPENALEX_URL`, `POLITE_MAILTO`, `MIN_BYTES` → Task 1. ✓
- `_work_to_candidate` (OA pdf fallback, language, off-topic title) → Task 1. ✓
- `_oa_get` (mailto + backoff), `search_crop` (filter+sort+paging) → Task 2. ✓
- `_collect_candidates` dedup id+doi, `_is_pruned` → Task 3. ✓
- `download` (stream_pdf_to_file), `run`, `main` CLI (--max/--per-crop/--crop/--dry-run/--list-crops), naming `oa_<id>.pdf` → Task 4. ✓
- Testing (unit for parse/dedup/prune; manual dry-run + harvest) → Task 1-4 tests + Task 4 Step 6. ✓
- Success criteria (25 PDFs, grounded cassava answer, no off-topic) → Task 4 Step 6. ✓
- Out-of-scope items (cross-source dedup, landing→PDF, clean-offtopic, multilingual) → not planned. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows full code. ✓

**Type consistency:** `_work_to_candidate -> (oa_id, pdf_url, doi, title)` used consistently by `search_crop`, `_collect_candidates`, `run`. `_oa_get(session, params)`, `search_crop(session, crop, max_per_crop)`, `_collect_candidates(session, crops, per_crop)`, `_is_pruned(oa_id)`, `download(session, url, dest)`, `run(crop, max_books, per_crop, dry_run)` — names/signatures match across tasks and tests. ✓
