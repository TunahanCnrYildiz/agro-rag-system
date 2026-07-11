# DergiPark Ingest Quality & Performance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop off-topic (livestock) papers and fertilizer NPK tables from being mis-handled during DergiPark ingestion, and make re-ingestion incremental.

**Architecture:** Three independent fixes across two modules. `fetch_dergipark.py` gains livestock terms in its off-topic regex plus a local `--clean-offtopic` cleanup command; `ingest.py`'s junk filter is restructured to rescue digit-heavy agronomy tables, and its file loop skips already-ingested files by querying the Chroma store.

**Tech Stack:** Python 3, pytest (new), pypdf, langchain-chroma / Chroma, regex.

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-07-11-dergipark-ingest-quality-design.md`.
- Off-topic PDFs are **moved** to `docs/books/_offtopic/`, never deleted.
- Fix #2 rescue threshold: agronomy numeric signal **AND** ≥ 5 real words (tokens with ≥ 3 alphabetic chars).
- Off-topic short roots must be `\b`-anchored; `et`/`süt` are omitted; `büyüme eğrisi`/`growth curve` are NOT added.
- Commit messages: English, short, no AI-style body, no Co-Authored-By trailer.
- Run tests from the project root so `src` imports as a package: `python -m pytest`.

---

### Task 1: Test scaffolding + strengthened off-topic regex

**Files:**
- Modify: `requirements.txt` (add pytest)
- Create: `tests/__init__.py`
- Create: `tests/test_fetch_dergipark.py`
- Modify: `src/fetch_dergipark.py:83-87` (`_OFFTOPIC_REC`)

**Interfaces:**
- Consumes: nothing.
- Produces: `_OFFTOPIC_REC` (compiled regex) now matches livestock/animal-science terms.

- [ ] **Step 1: Add pytest to requirements**

Append to `requirements.txt`:

```
pytest>=8.0
```

Install it:

Run: `python -m pip install "pytest>=8.0"`
Expected: pytest installs successfully.

- [ ] **Step 2: Create the test package marker**

Create `tests/__init__.py` (empty file):

```python
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_fetch_dergipark.py`:

```python
from src.fetch_dergipark import _OFFTOPIC_REC

# Titles that MUST be flagged as off-topic (livestock / animal science).
OFFTOPIC_TITLES = [
    "Estimation of Growth Curves of Awassi Sheep by Isotonic Regression",
    "İvesi Koyunlarının Büyüme Eğrilerinin Tahmin Edilmesi",
    "Süt sığırlarında karkas verimi ve besi performansı",
    "Broyler tavuklarda rasyon etkisi",
    "Arıcılıkta koloni yönetimi",
]

# In-scope titles that MUST NOT be flagged (plant nutrition vocabulary that
# contains dangerous substrings like 'besin', 'besleme', 'etki').
INSCOPE_TITLES = [
    "Bitki besleme ve toprak besin maddeleri dinamiği",
    "Azotlu gübrelemenin bitki büyümesine etkisi",
    "Mikrobiyal metabolizma ve toprak sağlığı",
    "Buğdayda verim ve besin içeriği",
]


def test_offtopic_titles_flagged():
    for title in OFFTOPIC_TITLES:
        assert _OFFTOPIC_REC.search(title), f"should flag: {title}"


def test_inscope_titles_not_flagged():
    for title in INSCOPE_TITLES:
        assert not _OFFTOPIC_REC.search(title), f"should NOT flag: {title}"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch_dergipark.py -v`
Expected: `test_offtopic_titles_flagged` FAILS (Awassi/sheep/koyun not yet matched).

- [ ] **Step 5: Extend the off-topic regex**

In `src/fetch_dergipark.py`, replace the `_OFFTOPIC_REC` definition (lines 83-87):

```python
_OFFTOPIC_REC = re.compile(
    r"hayvan|veteriner|zootekni|bal[ıi]k|su [üu]r[üu]nleri|fisher|aquacult|"
    r"ekonomi|pazarlama|market|dairy|poultry|meat",
    re.IGNORECASE,
)
```

with (livestock terms added; short roots leading-`\b` anchored, `besi` fully
anchored so it never matches `besin`/`besleme`):

```python
_OFFTOPIC_REC = re.compile(
    r"hayvan|veteriner|zootekni|bal[ıi]k|su [üu]r[üu]nleri|fisher|aquacult|"
    r"ekonomi|pazarlama|market|dairy|poultry|meat|"
    r"\bkoyun|\bsheep|\bkuzu|\blamb|\bke[çc]i|\bgoat|\bs[ıi][ğg][ıi]r|\bcattle|"
    r"\binek|\bbuza[ğg][ıi]|\bivesi|\bawassi|\bbroyler|\bbroiler|\bkanatl[ıi]|"
    r"\brasyon|\bbesi\b|\bkarkas|\bcarcass|\bar[ıi]c[ıi]l[ıi]k|\bipekb[öo]ce[ğg]i",
    re.IGNORECASE,
)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch_dergipark.py -v`
Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt tests/__init__.py tests/test_fetch_dergipark.py src/fetch_dergipark.py
git commit -m "Add livestock terms to DergiPark off-topic filter"
```

---

### Task 2: `--clean-offtopic` cleanup pass

**Files:**
- Modify: `src/fetch_dergipark.py` (add helpers + CLI flag)
- Modify: `tests/test_fetch_dergipark.py` (add cleanup tests)

**Interfaces:**
- Consumes: `_OFFTOPIC_REC` from Task 1.
- Produces:
  - `is_offtopic_text(text: str) -> bool`
  - `_first_page_text(path: Path) -> str`
  - `clean_offtopic(store=None, dry_run: bool = False, text_fn=_first_page_text) -> int`
    — returns count of flagged files; moves each flagged `dp_*.pdf` into
    `BOOKS_DIR/_offtopic/` and deletes its chunks from `store` (unless `dry_run`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fetch_dergipark.py`:

```python
from pathlib import Path
from src import fetch_dergipark as fd


class _FakeStore:
    """Minimal Chroma stand-in recording deletes by source name."""
    def __init__(self):
        self.deleted = []

    def get(self, where, limit=None):
        return {"ids": [f"{where['source']}:0"]}

    def delete(self, ids):
        self.deleted.extend(ids)


def test_clean_offtopic_moves_only_offtopic(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir()
    off = books / "dp_1.pdf"
    keep = books / "dp_2.pdf"
    off.write_bytes(b"x")
    keep.write_bytes(b"x")

    monkeypatch.setattr(fd, "BOOKS_DIR", books)
    texts = {off: "Awassi sheep growth curve", keep: "Bitki besleme ve toprak"}

    store = _FakeStore()
    moved = fd.clean_offtopic(store=store, dry_run=False,
                              text_fn=lambda p: texts[p])

    assert moved == 1
    assert not off.exists()
    assert (books / "_offtopic" / "dp_1.pdf").exists()
    assert keep.exists()
    assert store.deleted == ["dp_1.pdf:0"]


def test_clean_offtopic_dry_run_moves_nothing(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir()
    off = books / "dp_1.pdf"
    off.write_bytes(b"x")
    monkeypatch.setattr(fd, "BOOKS_DIR", books)

    moved = fd.clean_offtopic(store=_FakeStore(), dry_run=True,
                              text_fn=lambda p: "koyun besi rasyonu")
    assert moved == 1
    assert off.exists()  # untouched in dry-run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch_dergipark.py -k clean_offtopic -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'clean_offtopic'`.

- [ ] **Step 3: Implement the cleanup helpers**

In `src/fetch_dergipark.py`, add these functions above the `# Drivers` section
(after the `download` function, ~line 250):

```python
def _first_page_text(path: Path) -> str:
    """Extract first-page text for local off-topic classification."""
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(path))
    except Exception:  # noqa: BLE001
        return ""
    if not reader.pages:
        return ""
    try:
        return reader.pages[0].extract_text() or ""
    except Exception:  # noqa: BLE001
        return ""


def is_offtopic_text(text: str) -> bool:
    """True when first-page text matches the off-topic (livestock) filter."""
    return bool(_OFFTOPIC_REC.search(text))


def clean_offtopic(store=None, dry_run: bool = False,
                   text_fn=_first_page_text) -> int:
    """Move already-downloaded off-topic dp_*.pdf out of the corpus and delete
    their chunks from the vector store. Local only; no network. Returns the
    number of flagged files."""
    pdfs = sorted(BOOKS_DIR.glob("dp_*.pdf"))
    flagged = [p for p in pdfs if is_offtopic_text(text_fn(p))]
    print(f"[clean] scanned {len(pdfs)} dp PDFs, {len(flagged)} off-topic")
    if dry_run:
        for p in flagged:
            print(f"[clean]   would move {p.name}")
        return len(flagged)
    if not flagged:
        return 0
    if store is None:
        from .ingest import get_vector_store
        store = get_vector_store()
    offtopic_dir = BOOKS_DIR / "_offtopic"
    offtopic_dir.mkdir(exist_ok=True)
    for p in flagged:
        got = store.get(where={"source": p.name})
        if got.get("ids"):
            store.delete(ids=got["ids"])
        p.replace(offtopic_dir / p.name)
        print(f"[clean]   moved {p.name} ({len(got.get('ids', []))} chunks removed)")
    return len(flagged)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch_dergipark.py -k clean_offtopic -v`
Expected: both cleanup tests PASS.

- [ ] **Step 5: Wire up the CLI flag**

In `src/fetch_dergipark.py` `main()`, add the argument (after the `--list-sets`
argument, ~line 338):

```python
    p.add_argument("--clean-offtopic", action="store_true",
                   help="Move already-downloaded off-topic PDFs out and delete "
                        "their chunks from the store (respects --dry-run).")
```

And add this handler right after `args = p.parse_args()` (before the
`if args.list_sets:` block, ~line 340):

```python
    if args.clean_offtopic:
        clean_offtopic(dry_run=args.dry_run)
        return
```

- [ ] **Step 6: Verify the command runs (dry-run, no changes)**

Run: `python -m src.fetch_dergipark --clean-offtopic --dry-run`
Expected: prints `[clean] scanned N dp PDFs, M off-topic` and lists files it
`would move`; no files are moved.

- [ ] **Step 7: Commit**

```bash
git add src/fetch_dergipark.py tests/test_fetch_dergipark.py
git commit -m "Add --clean-offtopic pass to prune livestock papers from store"
```

---

### Task 3: Rescue NPK / agronomy tables in the junk filter

**Files:**
- Modify: `src/ingest.py:14-17` (imports — add `re`)
- Modify: `src/ingest.py:107-137` (constants + `_is_junk_chunk`)
- Create: `tests/test_ingest.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `_real_word_count(text: str) -> int`
  - `_has_agronomy_signal(text: str) -> bool`
  - `_is_junk_chunk(text: str) -> bool` (restructured; same signature)

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingest.py`:

```python
from src.ingest import _is_junk_chunk

# The exact fertilizer table chunk that is wrongly dropped today.
NPK_CHUNK = (
    "Material Analysis N (%) P2O5 (%) K2O (%) "
    "Complete 14-14-14 14 14 14 Urea [CO(NH2)2] 46-0-0 46 0 0 Solophos"
)
GLYPH_GARBAGE = "Table 1 Schnute y e ei xi /g32 /g14 /g11 /g12 /g69 model"
PURE_NUMBERS = "12 34 56 78 90 12 34 56 78 90 12 34 56 78 90 12 34 56"
NORMAL_PROSE = (
    "Azotlu gübreleme bitki büyümesini artırır ve toprak besin dengesini "
    "korumak için önemlidir."
)


def test_npk_table_is_kept():
    assert _is_junk_chunk(NPK_CHUNK) is False


def test_glyph_garbage_is_dropped():
    assert _is_junk_chunk(GLYPH_GARBAGE) is True


def test_pure_numbers_dropped():
    assert _is_junk_chunk(PURE_NUMBERS) is True


def test_normal_prose_is_kept():
    assert _is_junk_chunk(NORMAL_PROSE) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: `test_npk_table_is_kept` FAILS (chunk currently dropped), and
`test_glyph_garbage_is_dropped` may pass incidentally.

- [ ] **Step 3: Add the `re` import**

In `src/ingest.py`, add to the imports block (after `import hashlib`, line 15):

```python
import re
```

- [ ] **Step 4: Add rescue constants and helpers, restructure the filter**

In `src/ingest.py`, replace the block from `MIN_CHUNK_CHARS = 40` through the end
of `_is_junk_chunk` (lines 107-137) with:

```python
MIN_CHUNK_CHARS = 40
MIN_ALPHA_RATIO = 0.6
MIN_SPACE_RATIO = 0.08
MAX_AVG_WORD_LEN = 20
MIN_RESCUE_WORDS = 5  # real words needed to rescue a digit-heavy table

# Recurring USDA scan boilerplate - real text, but metadata about the scan
# itself, not agricultural content. Filtered by substring, case-insensitive.
_BOILERPLATE_MARKERS = (
    "do not assume content reflects current scientific knowledge",
)

# pypdf glyph-mapping failures surface as "/g32" etc. - always garbage.
_GLYPH_ARTIFACT = re.compile(r"/g\d+")
# NPK ratios (14-14-14, 46-0-0) and fertilizer/agronomy unit tokens mark
# digit-heavy chunks worth keeping despite a low letter ratio.
_NPK_RATIO = re.compile(r"\b\d{1,3}-\d{1,3}-\d{1,3}\b")
_UNIT_TOKEN = re.compile(r"kg/ha|mg/kg|g/kg|ppm|p2o5|k2o|%", re.IGNORECASE)


def _real_word_count(text: str) -> int:
    """Count tokens with at least 3 alphabetic characters."""
    return sum(1 for tok in text.split() if sum(c.isalpha() for c in tok) >= 3)


def _has_agronomy_signal(text: str) -> bool:
    """True when the chunk shows fertilizer/agronomy numeric structure."""
    return bool(_NPK_RATIO.search(text) or _UNIT_TOKEN.search(text))


def _is_junk_chunk(text: str) -> bool:
    """Reject OCR-garbage chunks while preserving valuable agronomy tables.

    Stage 1 (hard junk): too short, glyph artifacts, or run-together words.
    Stage 2 (rescue): keep digit-heavy chunks that carry an agronomy numeric
    signal plus enough real words. Stage 3: the original quality heuristics.
    """
    # Stage 1: always reject, regardless of numeric content.
    if len(text) < MIN_CHUNK_CHARS:
        return True
    if _GLYPH_ARTIFACT.search(text):
        return True
    if (text.count(" ") / len(text)) < MIN_SPACE_RATIO:
        return True
    # Stage 2: rescue digit-heavy fertilizer/agronomy tables.
    if _has_agronomy_signal(text) and _real_word_count(text) >= MIN_RESCUE_WORDS:
        return False
    # Stage 3: original quality heuristics.
    letters = sum(c.isalpha() for c in text)
    if (letters / len(text)) < MIN_ALPHA_RATIO:
        return True
    words = text.split()
    if words and (len(text) / len(words)) > MAX_AVG_WORD_LEN:
        return True
    lowered = text.lower()
    if any(marker in lowered for marker in _BOILERPLATE_MARKERS):
        return True
    return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: all four tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ingest.py tests/test_ingest.py
git commit -m "Rescue NPK/agronomy tables from ingest junk filter"
```

---

### Task 4: Incremental ingest (skip already-ingested files)

**Files:**
- Modify: `src/ingest.py:64-72` (`_iter_source_files` — exclude `_offtopic/`)
- Modify: `src/ingest.py:140-157` (`iter_chunks` — accept store/force, skip)
- Modify: `src/ingest.py:163-224` (`ingest()` + `main()` — `--force` flag)
- Modify: `tests/test_ingest.py` (add tests)

**Interfaces:**
- Consumes: `get_vector_store()` (existing).
- Produces:
  - `_already_ingested(store, source_name: str) -> bool`
  - `iter_chunks(splitter, store=None, force=False)` (new params)
  - `ingest(reset: bool = False, force: bool = False) -> int`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_ingest.py`:

```python
from pathlib import Path
from src import ingest as ing


class _FakeStore:
    def __init__(self, existing):
        self._existing = existing  # set of source names already ingested

    def get(self, where, limit=None):
        name = where["source"]
        return {"ids": [f"{name}:0"] if name in self._existing else []}


def test_already_ingested_true_when_present():
    store = _FakeStore({"dp_1.pdf"})
    assert ing._already_ingested(store, "dp_1.pdf") is True


def test_already_ingested_false_when_absent():
    store = _FakeStore({"dp_1.pdf"})
    assert ing._already_ingested(store, "dp_2.pdf") is False


def test_iter_source_files_excludes_offtopic(tmp_path, monkeypatch):
    books = tmp_path / "books"
    (books / "_offtopic").mkdir(parents=True)
    (books / "dp_1.pdf").write_bytes(b"x")
    (books / "_offtopic" / "dp_2.pdf").write_bytes(b"x")
    monkeypatch.setattr(ing, "BOOKS_DIR", books)

    names = [p.name for p in ing._iter_source_files()]
    assert names == ["dp_1.pdf"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -k "already_ingested or excludes_offtopic" -v`
Expected: FAIL with `AttributeError: ... has no attribute '_already_ingested'`.

- [ ] **Step 3: Exclude `_offtopic/` from source files**

In `src/ingest.py`, replace `_iter_source_files` (lines 64-72):

```python
def _iter_source_files() -> list[Path]:
    if not BOOKS_DIR.exists():
        return []
    files = sorted(
        p
        for p in BOOKS_DIR.rglob("*")
        if p.suffix.lower() in {".pdf", ".txt"} and p.is_file()
    )
    return files
```

with:

```python
def _iter_source_files() -> list[Path]:
    if not BOOKS_DIR.exists():
        return []
    files = sorted(
        p
        for p in BOOKS_DIR.rglob("*")
        if p.suffix.lower() in {".pdf", ".txt"}
        and p.is_file()
        and "_offtopic" not in p.parts
    )
    return files
```

- [ ] **Step 4: Add the `_already_ingested` helper**

In `src/ingest.py`, add above `iter_chunks` (before line 140):

```python
def _already_ingested(store, source_name: str) -> bool:
    """True when the store already holds at least one chunk for this file."""
    got = store.get(where={"source": source_name}, limit=1)
    return bool(got.get("ids"))
```

- [ ] **Step 5: Teach `iter_chunks` to skip ingested files**

In `src/ingest.py`, replace the `iter_chunks` signature and file loop
(lines 140-149) — change the `def` line and the start of the `for path` loop:

```python
def iter_chunks(splitter: RecursiveCharacterTextSplitter) -> Iterator[Document]:
    """Lazily yield chunked Documents across all source files."""
    files = _iter_source_files()
    if not files:
        print(f"[ingest] no .pdf/.txt files found under {BOOKS_DIR}")
        return
    print(f"[ingest] found {len(files)} source file(s)")

    for path in files:
        print(f"[ingest] processing {path.name}")
```

with:

```python
def iter_chunks(
    splitter: RecursiveCharacterTextSplitter, store=None, force: bool = False
) -> Iterator[Document]:
    """Lazily yield chunked Documents across all source files. When ``store`` is
    given and ``force`` is False, files already present in the store are skipped
    so re-ingestion does not re-embed the whole corpus."""
    files = _iter_source_files()
    if not files:
        print(f"[ingest] no .pdf/.txt files found under {BOOKS_DIR}")
        return
    print(f"[ingest] found {len(files)} source file(s)")

    for path in files:
        if store is not None and not force and _already_ingested(store, path.name):
            print(f"[ingest]   = {path.name} already ingested, skipping")
            continue
        print(f"[ingest] processing {path.name}")
```

- [ ] **Step 6: Pass store/force from `ingest()` and add the `--force` flag**

In `src/ingest.py` `ingest()`, change the signature (line 163):

```python
def ingest(reset: bool = False) -> int:
```

to:

```python
def ingest(reset: bool = False, force: bool = False) -> int:
```

Then change the `iter_chunks` call (line 194) from:

```python
    for doc in iter_chunks(splitter):
```

to:

```python
    for doc in iter_chunks(splitter, store=store, force=force):
```

In `main()`, add the flag (after the `--reset` argument, ~line 222):

```python
    parser.add_argument(
        "--force", action="store_true",
        help="Re-ingest every file even if already in the store.",
    )
```

and update the call (line 224) from `ingest(reset=args.reset)` to:

```python
    ingest(reset=args.reset, force=args.force)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: all tests PASS (Task 3 tests + the three new ones).

- [ ] **Step 8: Verify incremental skip end-to-end**

With LM Studio serving the embedding model, run ingest twice:

Run: `python -m src.ingest`
Expected (second run): every file prints `= <name> already ingested, skipping`
and it finishes in seconds with `total chunks so far` not increasing.

Run: `python -m src.ingest --force`
Expected: files are processed again (no skip messages).

- [ ] **Step 9: Commit**

```bash
git add src/ingest.py tests/test_ingest.py
git commit -m "Skip already-ingested files unless --force"
```

---

## Self-Review

**Spec coverage:**
- Fix #1 regex → Task 1. Fix #1 cleanup pass (move + delete chunks, dry-run) → Task 2. ✓
- Fix #2 three-stage junk filter with NPK rescue + ≥5 real words → Task 3. ✓
- Fix #3 incremental skip via store, `--force`, `_offtopic/` excluded → Task 4. ✓
- Testing section of spec (regex positives/negatives, junk cases, incremental) → Tasks 1-4 tests. ✓
- Out-of-scope items (embedding model, two-column, extra header filtering) → not planned. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows full code. ✓

**Type consistency:** `clean_offtopic(store, dry_run, text_fn)`, `is_offtopic_text(text)`, `_first_page_text(path)`, `_already_ingested(store, source_name)`, `_has_agronomy_signal(text)`, `_real_word_count(text)`, `iter_chunks(splitter, store, force)`, `ingest(reset, force)` — names and signatures match across tasks and tests. Fake stores implement the exact `get`/`delete` shapes the code calls. ✓
