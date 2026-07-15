# FAO Knowledge Repository Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `src/fetch_fao.py`, a fetcher that harvests plant-relevant, English, open-access PDFs from the FAO Knowledge Repository (openknowledge.fao.org) into `docs/books/` as `fao_<id>.pdf`.

**Architecture:** Harvest one OAI-PMH set ("Publications") page-by-page via `resumptionToken`, filter each `oai_dc` record client-side (English + plant-include keywords + off-topic exclude), extract the direct `.pdf` link from `dc:identifier`, and stream it to disk with the shared PDF validator. Mirrors the existing `fetch_dergipark.py` (OAI-PMH) and `fetch_openalex.py` (candidate filtering) patterns.

**Tech Stack:** Python 3.12+, `requests`, `xml.etree.ElementTree` (stdlib), `pytest`. Reuses `src/pdf_fetch_utils.py` and `src/config.py`. No new dependencies.

## Global Constraints

- **No new dependencies** — reuse `requests`, stdlib `xml.etree.ElementTree`, and `src/pdf_fetch_utils.py` (`pdf_session`, `stream_pdf_to_file`).
- **File naming** — downloaded PDFs are `fao_<id>.pdf` in `BOOKS_DIR` (`docs/books/`), where `<id>` is the handle tail (e.g. `x6751f`).
- **English only** — a record is a candidate only when `dc:language` is English.
- **Dual-import shim** — every `src/` module uses `try: from .config import ... except ImportError: from config import ...`; replicate it.
- **Politeness** — reuse the crawler `User-Agent` from `pdf_fetch_utils`; delay between OAI calls and between downloads.
- **OAI endpoint** — `https://openknowledge.fao.org/server/oai/request`; first call can be slow (cold start) → `OAI_TIMEOUT=90`, retry with backoff.
- **Publications set** — `col_20.500.14283_2` (FAO OAI sets are structural, not thematic; subject selection is client-side).
- **Quality gate** — after any harvest + `python -m src.ingest`, `python -m evals.run_eval` must still pass 12/12.

---

### Task 1: Module scaffold + record filtering (`_record_to_candidate`)

**Files:**
- Create: `src/fetch_fao.py`
- Test: `tests/test_fetch_fao.py`

**Interfaces:**
- Consumes: `pdf_session`, `stream_pdf_to_file`, `BOOKS_DIR` (from existing modules).
- Produces:
  - `_NS: dict[str, str]` — OAI + DC namespace map.
  - `OAI_URL: str`, `PUBLICATIONS_SET: str`, `OAI_DELAY: float`, `PDF_DELAY: float`, `OAI_TIMEOUT: int`, `OAI_RETRIES: int`, `MIN_BYTES: int`.
  - `_PLANT_INCLUDE: re.Pattern`, `_OFFTOPIC_FAO: re.Pattern`.
  - `_record_to_candidate(rec: xml.etree.ElementTree.Element) -> tuple[str, str, str] | None` — returns `(fao_id, pdf_url, title)` or `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fetch_fao.py`:

```python
import xml.etree.ElementTree as ET

from src import fetch_fao as ff
from src.fetch_fao import _record_to_candidate

_NS_DECL = (
    'xmlns="http://www.openarchives.org/OAI/2.0/" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"'
)


def _rec_xml(
    identifier="oai:openknowledge.fao.org:20.500.14283/x6751f",
    title="Cassava crop production guide",
    description="Improving cassava yield through better soil nutrition.",
    language="English",
    pdf="http://www.fao.org/3/a-x6751f.pdf",
    handle="https://openknowledge.fao.org/handle/20.500.14283/x6751f",
):
    """Build one OAI-PMH <record> XML string (namespaces on the record root)."""
    ids = ""
    if handle:
        ids += f"<dc:identifier>{handle}</dc:identifier>"
    if pdf:
        ids += f"<dc:identifier>{pdf}</dc:identifier>"
    return (
        f'<record {_NS_DECL}>'
        f'<header><identifier>{identifier}</identifier></header>'
        f'<metadata><oai_dc:dc>'
        f'<dc:title>{title}</dc:title>'
        f'<dc:description>{description}</dc:description>'
        f'{ids}'
        f'<dc:language>{language}</dc:language>'
        f'</oai_dc:dc></metadata>'
        f'</record>'
    )


def _rec(**kw):
    return ET.fromstring(_rec_xml(**kw))


def test_candidate_from_valid_record():
    assert _record_to_candidate(_rec()) == (
        "x6751f",
        "http://www.fao.org/3/a-x6751f.pdf",
        "Cassava crop production guide",
    )


def test_fao_id_parsed_from_header_handle_tail():
    cand = _record_to_candidate(
        _rec(identifier="oai:openknowledge.fao.org:20.500.14283/ab12cd")
    )
    assert cand[0] == "ab12cd"


def test_none_when_not_english():
    assert _record_to_candidate(_rec(language="French")) is None


def test_none_when_no_plant_term():
    # a policy/report doc with no plant keyword is dropped by the include filter
    assert _record_to_candidate(
        _rec(title="Annual report 2020", description="Overview of activities.")
    ) is None


def test_none_when_offtopic_even_with_plant_term():
    # has "crop" (include) but "forage"/"ruminant" (off-topic exclude) -> None
    assert _record_to_candidate(
        _rec(title="Crop residues as forage for ruminants",
             description="Feeding trial results.")
    ) is None


def test_none_for_fisheries_and_forestry():
    assert _record_to_candidate(
        _rec(title="Plant cover in coastal fisheries zones",
             description="Marine capture fisheries survey.")
    ) is None
    assert _record_to_candidate(
        _rec(title="Soil under forest plantations",
             description="Forestry and timber yield in the tropics.")
    ) is None


def test_keeps_manure_fertilizer_record():
    # poultry/cattle MANURE is an on-topic organic fertilizer -> kept
    cand = _record_to_candidate(
        _rec(title="Effect of poultry manure on cassava crop yield",
             description="Organic fertilization field trial.")
    )
    assert cand is not None


def test_none_when_no_pdf_identifier():
    assert _record_to_candidate(_rec(pdf=None)) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch_fao.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.fetch_fao'`.

- [ ] **Step 3: Create the module scaffold + filtering**

Create `src/fetch_fao.py`:

```python
"""Harvest plant-relevant English open-access PDFs from the FAO Knowledge
Repository (openknowledge.fao.org, a DSpace 7 instance).

FAO's OAI-PMH sets are structural (Publications, Meeting docs, Posters...), not
thematic, and its REST search API is WAF-blocked, so we harvest one set via
OAI-PMH ``ListRecords`` (paging through ``resumptionToken``) and filter each
record client-side: English only, must mention a plant/agronomy term, must not
be off-topic (fisheries/forestry/livestock/economics). Each ``oai_dc`` record
exposes a direct ``.pdf`` link in ``dc:identifier``; we stream that to
docs/books/ as ``fao_<id>.pdf`` alongside the dp_/oa_/ia_ corpora.

    python -m src.fetch_fao --list-sets            # show the OAI sets and exit
    python -m src.fetch_fao --dry-run --max 100    # preview, download nothing
    python -m src.fetch_fao --max 100              # harvest PDFs
    python -m src.fetch_fao --set col_20.500.14283_3   # harvest a different set
"""

from __future__ import annotations

import argparse
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

try:
    from .config import BOOKS_DIR
    from .pdf_fetch_utils import pdf_session, stream_pdf_to_file
except ImportError:  # pragma: no cover
    from config import BOOKS_DIR  # type: ignore
    from pdf_fetch_utils import pdf_session, stream_pdf_to_file  # type: ignore

OAI_URL = "https://openknowledge.fao.org/server/oai/request"
# FAO "Publications" collection (books + technical publications). Structural set,
# not thematic - plant subject selection is done by the filters below.
PUBLICATIONS_SET = "col_20.500.14283_2"

OAI_DELAY = 0.5      # polite delay between OAI calls
PDF_DELAY = 1.5      # polite delay between PDF downloads
OAI_TIMEOUT = 90     # a ListRecords page is generated on demand and can be slow
OAI_RETRIES = 3
MIN_BYTES = 60_000   # skip tiny stubs / cover-only fragments

# OAI-PMH + Dublin Core namespaces.
_NS = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# A record must mention at least one plant/agronomy term in its title or
# description (FAO records rarely carry a usable dc:subject).
_PLANT_INCLUDE = re.compile(
    r"\bcrop|\bplant|\bsoil|nutrition|fertiliz|fertilis|horticultur|agronom|"
    r"irrigat|\bseed|prun|graft|greenhouse|compost|cultivat|\bpest|disease|"
    r"pollinat|propagat|orchard|vegetable|cereal|legume|\bfruit|nursery|"
    r"tillage|\bweed|harvest|germinat|rootstock",
    re.IGNORECASE,
)

# Even with a plant term present, drop clearly off-scope docs. Mirrors the
# OpenAlex fetcher's nuance: match "poultry/cattle FEED" but NOT bare
# "poultry"/"cattle", so poultry/cattle MANURE fertilizer papers survive.
_OFFTOPIC_FAO = re.compile(
    r"\bfisher|\baquacult|\bfish\b|\bshrimp|\bmollusc|\baquatic|\bmarine\b|"
    r"\bforest|\btimber|\blogging|silvicultur|"
    r"\blivestock|poultry feed|cattle feed|fish feed|feed ration|"
    r"\bruminant|\bsilage|\bfodder|\bforage|\bdairy\b|\bveterinar",
    re.IGNORECASE,
)


def _record_to_candidate(rec: ET.Element) -> tuple[str, str, str] | None:
    """Return (fao_id, pdf_url, title) for an English, plant-relevant, on-topic
    record that exposes a direct .pdf link, else None."""
    langs = [(e.text or "").strip().lower()
             for e in rec.findall(".//dc:language", _NS)]
    if not any(lang in ("en", "english") for lang in langs):
        return None

    titles = [e.text or "" for e in rec.findall(".//dc:title", _NS)]
    descs = [e.text or "" for e in rec.findall(".//dc:description", _NS)]
    blob = " ".join(titles + descs)
    if not _PLANT_INCLUDE.search(blob):
        return None
    if _OFFTOPIC_FAO.search(blob):
        return None

    ids = [(e.text or "") for e in rec.findall(".//dc:identifier", _NS)]
    pdf_url = next((u for u in ids if u.lower().endswith(".pdf")), "")
    if not pdf_url:
        return None

    header_id = rec.findtext(
        "oai:header/oai:identifier", default="", namespaces=_NS
    )
    fao_id = header_id.rsplit("/", 1)[-1].strip()
    if not fao_id:
        return None

    return fao_id, pdf_url, (titles[0] if titles else "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch_fao.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fetch_fao.py tests/test_fetch_fao.py
git commit -m "Add FAO fetcher record filtering"
```

---

### Task 2: OAI paging + candidate collection

**Files:**
- Modify: `src/fetch_fao.py` (append functions)
- Test: `tests/test_fetch_fao.py` (append tests)

**Interfaces:**
- Consumes: `_record_to_candidate`, `_NS`, `OAI_URL`, `OAI_DELAY`, `OAI_TIMEOUT`, `OAI_RETRIES` (Task 1).
- Produces:
  - `_oai(session, params: dict) -> xml.etree.ElementTree.Element | None`
  - `_collect_candidates(session, set_spec: str, max_books: int, max_scan: int) -> list[tuple[str, str, str]]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fetch_fao.py`:

```python
def _root_xml(record_xmls, token=None):
    tok = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    recs = "".join(record_xmls)
    return ET.fromstring(
        f'<OAI-PMH {_NS_DECL}><ListRecords>{recs}{tok}</ListRecords></OAI-PMH>'
    )


def test_collect_paginates_and_dedupes(monkeypatch):
    p1 = _root_xml(
        [_rec_xml(identifier="oai:x:20.500.14283/a", title="crop soil guide"),
         _rec_xml(identifier="oai:x:20.500.14283/b", title="plant nutrition")],
        token="t1",
    )
    p2 = _root_xml(
        [_rec_xml(identifier="oai:x:20.500.14283/a", title="crop soil guide"),
         _rec_xml(identifier="oai:x:20.500.14283/c", title="irrigation of maize")],
        token=None,
    )
    pages = iter([p1, p2])
    monkeypatch.setattr(ff, "_oai", lambda s, params: next(pages))
    monkeypatch.setattr(ff.time, "sleep", lambda *a: None)
    out = ff._collect_candidates(object(), "set", max_books=10, max_scan=100)
    assert [c[0] for c in out] == ["a", "b", "c"]  # dup "a" kept once


def test_collect_stops_at_max_books(monkeypatch):
    p1 = _root_xml(
        [_rec_xml(identifier="oai:x:20.500.14283/a", title="crop guide"),
         _rec_xml(identifier="oai:x:20.500.14283/b", title="plant soil")],
        token="t1",
    )
    monkeypatch.setattr(ff, "_oai", lambda s, params: p1)
    monkeypatch.setattr(ff.time, "sleep", lambda *a: None)
    out = ff._collect_candidates(object(), "set", max_books=1, max_scan=100)
    assert [c[0] for c in out] == ["a"]


def test_collect_respects_max_scan(monkeypatch):
    p1 = _root_xml(
        [_rec_xml(identifier="oai:x:20.500.14283/a", title="fisheries only")],
        token="t1",
    )
    calls = []

    def fake_oai(s, params):
        calls.append(params)
        return p1

    monkeypatch.setattr(ff, "_oai", fake_oai)
    monkeypatch.setattr(ff.time, "sleep", lambda *a: None)
    out = ff._collect_candidates(object(), "set", max_books=10, max_scan=1)
    assert out == []          # the one record is off-topic
    assert len(calls) == 1    # stopped after scanning 1 record (didn't page on)


def test_collect_stops_when_oai_returns_none(monkeypatch):
    monkeypatch.setattr(ff, "_oai", lambda s, params: None)
    monkeypatch.setattr(ff.time, "sleep", lambda *a: None)
    out = ff._collect_candidates(object(), "set", max_books=10, max_scan=100)
    assert out == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch_fao.py -k collect -v`
Expected: FAIL — `AttributeError: module 'src.fetch_fao' has no attribute '_collect_candidates'`.

- [ ] **Step 3: Implement OAI paging + collection**

Append to `src/fetch_fao.py`:

```python
def _oai(session: requests.Session, params: dict) -> ET.Element | None:
    """Call the OAI-PMH endpoint and return the parsed root element, retrying a
    few times with backoff since a full page can be slow to generate."""
    for attempt in range(1, OAI_RETRIES + 1):
        try:
            resp = session.get(OAI_URL, params=params, timeout=OAI_TIMEOUT)
            resp.raise_for_status()
            return ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as exc:
            if attempt == OAI_RETRIES:
                print(f"[fao] OAI failed after {OAI_RETRIES} tries ({params}): {exc}")
                return None
            time.sleep(2 * attempt)
    return None


def _collect_candidates(
    session: requests.Session, set_spec: str, max_books: int, max_scan: int
) -> list[tuple[str, str, str]]:
    """Page through a set's records, filtering to plant-relevant candidates.

    Stops when max_books candidates are found or max_scan records are scanned
    (the latter bounds walking a very large set). Dedupes by fao_id.
    """
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    scanned = 0
    params = {"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": set_spec}
    while len(out) < max_books and scanned < max_scan:
        root = _oai(session, params)
        if root is None:
            break
        for rec in root.findall(".//oai:record", _NS):
            scanned += 1
            cand = _record_to_candidate(rec)
            if cand and cand[0] not in seen:
                seen.add(cand[0])
                out.append(cand)
                if len(out) >= max_books:
                    break
        token = root.findtext(".//oai:resumptionToken", default="", namespaces=_NS)
        if not token:
            break
        params = {"verb": "ListRecords", "resumptionToken": token}
        time.sleep(OAI_DELAY)
    return out[:max_books]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch_fao.py -v`
Expected: PASS (12 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/fetch_fao.py tests/test_fetch_fao.py
git commit -m "Add FAO OAI paging and candidate collection"
```

---

### Task 3: Download + orchestration + CLI

**Files:**
- Modify: `src/fetch_fao.py` (append functions)
- Test: `tests/test_fetch_fao.py` (append tests)

**Interfaces:**
- Consumes: `_collect_candidates`, `_oai`, `_NS`, `BOOKS_DIR`, `pdf_session`, `stream_pdf_to_file`, `MIN_BYTES`, `PDF_DELAY`, `PUBLICATIONS_SET` (Tasks 1-2).
- Produces:
  - `_is_pruned(fao_id: str) -> bool`
  - `list_sets(session) -> list[tuple[str, str]]`
  - `download(session, url: str, dest: pathlib.Path) -> bool`
  - `run(set_spec: str, max_books: int, max_scan: int, dry_run: bool) -> int`
  - `main() -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fetch_fao.py`:

```python
def test_is_pruned_detects_offtopic(tmp_path, monkeypatch):
    books = tmp_path / "books"
    (books / "_offtopic").mkdir(parents=True)
    (books / "_offtopic" / "fao_z9.pdf").write_bytes(b"x")
    monkeypatch.setattr(ff, "BOOKS_DIR", books)
    assert ff._is_pruned("z9") is True
    assert ff._is_pruned("z8") is False


def test_list_sets_parses_specs_and_names(monkeypatch):
    root = ET.fromstring(
        f'<OAI-PMH {_NS_DECL}><ListSets>'
        f'<set><setSpec>col_2</setSpec><setName>Publications</setName></set>'
        f'<set><setSpec>col_3</setSpec><setName>Technical documents</setName></set>'
        f'</ListSets></OAI-PMH>'
    )
    monkeypatch.setattr(ff, "_oai", lambda s, params: root)
    out = ff.list_sets(object())
    assert out == [("col_2", "Publications"), ("col_3", "Technical documents")]


def test_run_dry_run_downloads_nothing(tmp_path, monkeypatch):
    books = tmp_path / "books"
    monkeypatch.setattr(ff, "BOOKS_DIR", books)
    monkeypatch.setattr(ff, "pdf_session", lambda *a, **k: object())
    monkeypatch.setattr(
        ff, "_collect_candidates",
        lambda s, spec, mb, ms: [("x1", "u1.pdf", "crop production guide")],
    )
    monkeypatch.setattr(
        ff, "download",
        lambda *a: (_ for _ in ()).throw(AssertionError("no download in dry-run")),
    )
    n = ff.run(set_spec="set", max_books=100, max_scan=8000, dry_run=True)
    assert n == 0


def test_run_skips_existing_and_counts_saved(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir()
    (books / "fao_have.pdf").write_bytes(b"%PDF-old")  # already present -> skip
    monkeypatch.setattr(ff, "BOOKS_DIR", books)
    monkeypatch.setattr(ff, "pdf_session", lambda *a, **k: object())
    monkeypatch.setattr(ff.time, "sleep", lambda *a: None)
    monkeypatch.setattr(
        ff, "_collect_candidates",
        lambda s, spec, mb, ms: [
            ("have", "u_have.pdf", "already here"),
            ("new1", "u_new1.pdf", "new crop guide"),
        ],
    )
    saved_urls = []

    def fake_download(session, url, dest):
        saved_urls.append(url)
        dest.write_bytes(b"%PDF-new")
        return True

    monkeypatch.setattr(ff, "download", fake_download)
    n = ff.run(set_spec="set", max_books=100, max_scan=8000, dry_run=False)
    assert n == 1                       # only "new1" downloaded
    assert saved_urls == ["u_new1.pdf"]  # existing "have" skipped


def test_main_list_sets_prints(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["fetch_fao", "--list-sets"])
    monkeypatch.setattr(ff, "pdf_session", lambda *a, **k: object())
    monkeypatch.setattr(ff, "list_sets", lambda s: [("col_2", "Publications")])
    ff.main()
    printed = capsys.readouterr().out
    assert "col_2" in printed and "Publications" in printed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch_fao.py -k "pruned or list_sets or run or main" -v`
Expected: FAIL — `AttributeError: module 'src.fetch_fao' has no attribute '_is_pruned'`.

- [ ] **Step 3: Implement download + orchestration + CLI**

Append to `src/fetch_fao.py`:

```python
def _is_pruned(fao_id: str) -> bool:
    """True if this doc was already moved to docs/books/_offtopic/ (don't
    re-download)."""
    offtopic = BOOKS_DIR / "_offtopic"
    return offtopic.exists() and any(offtopic.rglob(f"fao_{fao_id}.pdf"))


def list_sets(session: requests.Session) -> list[tuple[str, str]]:
    """Return (setSpec, setName) for every OAI set (single page; FAO exposes ~17)."""
    root = _oai(session, {"verb": "ListSets"})
    if root is None:
        return []
    out: list[tuple[str, str]] = []
    for s in root.findall(".//oai:set", _NS):
        spec = (s.findtext("oai:setSpec", default="", namespaces=_NS) or "").strip()
        name = (s.findtext("oai:setName", default="", namespaces=_NS) or "").strip()
        if spec:
            out.append((spec, name))
    return out


def download(session: requests.Session, url: str, dest: Path) -> bool:
    """Stream a candidate PDF to disk, validating the %PDF header + size."""
    try:
        resp = session.get(url, stream=True, timeout=120)
    except requests.RequestException as exc:
        print(f"[fao]   ! download error: {exc}")
        return False
    if resp.status_code != 200:
        print(f"[fao]   ! http {resp.status_code}, skipping")
        resp.close()
        return False
    return stream_pdf_to_file(resp, dest, MIN_BYTES, "fao")


def run(set_spec: str, max_books: int, max_scan: int, dry_run: bool) -> int:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    session = pdf_session("en")
    candidates = _collect_candidates(session, set_spec, max_books, max_scan)
    print(f"[fao] {len(candidates)} candidate(s); target {max_books}\n")

    if dry_run:
        for i, (fao_id, _url, title) in enumerate(candidates, 1):
            print(f"{i:>3}  {fao_id:>10}  {title[:60]}")
        print("\n[fao] preview only. Re-run without --dry-run to download.")
        return 0

    saved = 0
    for fao_id, url, title in candidates:
        if saved >= max_books:
            break
        dest = BOOKS_DIR / f"fao_{fao_id}.pdf"
        if dest.exists():
            print(f"[fao]   = already have {dest.name}, skipping")
            continue
        if _is_pruned(fao_id):
            print(f"[fao]   = fao_{fao_id} previously pruned, skipping")
            continue
        print(f"[fao] {title[:55]}")
        if download(session, url, dest):
            saved += 1
        time.sleep(PDF_DELAY)

    print(f"\n[fao] DONE. downloaded {saved} paper(s) into {BOOKS_DIR}")
    if saved:
        print("[fao] next: python -m src.ingest")
    return saved


def main() -> None:
    p = argparse.ArgumentParser(
        description="Harvest plant-relevant open-access PDFs from the FAO "
                    "Knowledge Repository."
    )
    p.add_argument("--max", type=int, default=100, help="Max PDFs to download.")
    p.add_argument("--max-scan", type=int, default=8000,
                   help="Max OAI records to scan before stopping.")
    p.add_argument("--set", default=PUBLICATIONS_SET,
                   help="OAI setSpec to harvest (default: Publications).")
    p.add_argument("--dry-run", action="store_true",
                   help="Preview candidates without downloading.")
    p.add_argument("--list-sets", action="store_true",
                   help="List OAI sets and exit.")
    args = p.parse_args()

    if args.list_sets:
        for spec, name in list_sets(pdf_session("en")):
            print(f"  {spec}  {name}")
        return

    run(set_spec=args.set, max_books=args.max, max_scan=args.max_scan,
        dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full test file**

Run: `python -m pytest tests/test_fetch_fao.py -v`
Expected: PASS (17 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/fetch_fao.py tests/test_fetch_fao.py
git commit -m "Add FAO fetcher download, orchestration and CLI"
```

---

### Task 4: Live smoke test, docs, and quality gate

**Files:**
- Modify: `README.md` (fetcher list)
- Modify: `C:\Users\tunah\.claude\projects\D--Claude-Projects-Agro-Botany-RAG---Product-Linker-System\memory\handoff-next-steps.md` (mark FAO done)

**Interfaces:**
- Consumes: the finished `src/fetch_fao.py`.
- Produces: no new code symbols (docs + verification only).

- [ ] **Step 1: Live smoke test with `--list-sets`**

Run: `python -m src.fetch_fao --list-sets`
Expected: prints ~17 lines including `col_20.500.14283_2  Publications` (name may be localized). Confirms the live OAI endpoint and parsing work end-to-end.

- [ ] **Step 2: Live dry-run (small)**

Run: `python -m src.fetch_fao --dry-run --max 10 --max-scan 400`
Expected: a numbered preview table of plant-relevant English candidates (titles about crops/soil/plants), ending with "preview only". No files written. If the table is empty or off-topic, tune `_PLANT_INCLUDE` / `_OFFTOPIC_FAO` and re-run before proceeding.

- [ ] **Step 3: Real harvest (medium)**

Run: `python -m src.fetch_fao --max 100`
Expected: downloads `fao_<id>.pdf` files into `docs/books/`, ending with "DONE. downloaded N paper(s)" and "next: python -m src.ingest". N may be < 100 if the scan cap is hit first — raise `--max-scan` if more are wanted.

- [ ] **Step 4: Ingest the new PDFs**

Run: `python -m src.ingest`
Expected: the incremental ingest picks up only the new `fao_` PDFs (auto-skips already-ingested files) and adds their chunks to the vector store.

- [ ] **Step 5: Quality-gate eval**

Run: `python -m evals.run_eval`
Expected: baseline still passes 12/12 (retrieval, product-gating, grounding, guardrail). If it regressed, investigate before committing docs.

- [ ] **Step 6: Update README fetcher list**

In `README.md`, find the section that lists the corpus fetchers (`fetch_books.py`/`ia_`, `fetch_dergipark.py`/`dp_`, `fetch_openalex.py`/`oa_`) and add a matching entry:

```markdown
- `python -m src.fetch_fao` — FAO Knowledge Repository (openknowledge.fao.org,
  OAI-PMH); plant-relevant English open-access PDFs saved as `fao_<id>.pdf`.
```

Match the exact formatting of the surrounding fetcher bullets (verify by reading the section first).

- [ ] **Step 7: Update handoff memory**

In `handoff-next-steps.md`, move the FAO fetcher from "Next steps" to done (note the corpus grew), and set the next source/step. Keep it one edit; do not restructure the file.

- [ ] **Step 8: Commit docs**

```bash
git add README.md
git commit -m "Document FAO fetcher in README"
```

(The memory file lives outside the repo and is saved via the memory tool, not committed.)

---

## Notes for the implementer

- **Run tests from the project root** so the `src` package imports resolve:
  `python -m pytest tests/test_fetch_fao.py -v`.
- **The dual-import shim matters** — tests import `from src import fetch_fao`, but
  `python -m src.fetch_fao` runs it as part of the `src` package; both paths must work.
- **Filter tuning is expected** — `_PLANT_INCLUDE` / `_OFFTOPIC_FAO` are pragmatic
  keyword filters. Use the Task 4 dry-run to eyeball precision and adjust the
  regexes; the unit tests pin the important include/exclude behaviors so tuning
  won't silently break the nuances (e.g. keeping manure-fertilizer docs).
- **Do not exclude chemical-pesticide content at fetch time** — it is valid
  reference material; the assistant's answer-time guardrails govern its use.
```
