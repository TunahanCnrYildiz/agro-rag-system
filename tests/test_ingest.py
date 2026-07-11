from pathlib import Path

from src.ingest import (
    _extract_pdf_pages,
    _is_junk_chunk,
    _normalize_text,
    MIN_SPACE_RATIO,
)
from src import ingest as ing
from src.config import settings
from langchain_text_splitters import RecursiveCharacterTextSplitter

FIXTURE = Path(__file__).parent / "fixtures" / "ia_301ento00unit.pdf"

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


def test_normalize_text_collapses_crlf():
    assert _normalize_text("a\r\nb\rc\nd") == "a\nb\nc\nd"


def test_extract_pdf_pages_yields_page_metadata():
    pages = list(_extract_pdf_pages(FIXTURE))
    assert pages, "fixture should yield at least one page"
    text, meta = pages[0]
    assert meta["source"] == "ia_301ento00unit.pdf"
    assert meta["page"] == 0
    assert text.strip()


def test_extract_pdf_pages_restores_word_spacing():
    pages = list(_extract_pdf_pages(FIXTURE))
    full = " ".join(text for text, _ in pages)
    assert full, "fixture should produce text"
    # pypdf gave ~0.001 here (words run together); pypdfium2 restores spacing.
    assert full.count(" ") / len(full) >= MIN_SPACE_RATIO


def test_extract_pdf_pages_survives_junk_filter():
    # Under pypdf this file yielded 0 kept chunks; pypdfium2 must yield >= 1.
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    kept = 0
    for text, _ in _extract_pdf_pages(FIXTURE):
        for chunk in splitter.split_text(text):
            chunk = chunk.strip()
            if chunk and not _is_junk_chunk(chunk):
                kept += 1
    assert kept >= 1


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
