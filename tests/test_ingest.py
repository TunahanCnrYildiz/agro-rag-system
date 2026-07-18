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


# --------------------------------------------------------------------------- #
# year / era metadata (2026-07-18)
# --------------------------------------------------------------------------- #
def test_year_to_era_buckets():
    assert ing._year_to_era(1908) == "pre-1950"
    assert ing._year_to_era(1975) == "1950-1989"
    assert ing._year_to_era(2001) == "1990-2009"
    assert ing._year_to_era(2018) == "2010+"
    assert ing._year_to_era(None) == "unknown"
    # boundaries land in the newer bucket
    assert ing._year_to_era(1950) == "1950-1989"
    assert ing._year_to_era(1990) == "1990-2009"
    assert ing._year_to_era(2010) == "2010+"


def test_derive_year_override_wins(monkeypatch):
    monkeypatch.setattr(ing, "_source_year_overrides", lambda: {"x.pdf": 1911})
    year, conf = ing.derive_source_year("x.pdf", "full of 2003 and 2007 text")
    assert (year, conf) == (1911, "override")


def test_derive_year_oa_constant():
    # a hand-checked OpenAlex year; no text needed
    year, conf = ing.derive_source_year("oa_W2115917750.pdf", "")
    assert (year, conf) == (2009, "api")


def test_derive_year_dp_from_text(monkeypatch):
    monkeypatch.setattr(ing, "_source_year_overrides", lambda: {})
    text = "Akd. Univ. Ziraat Fak. Derg. (2012) 25(1): 53-57 ... Polat 1999, Acar 2006"
    year, conf = ing.derive_source_year("dp_19411.pdf", text)
    # the header year that appears FIRST, not a later reference year
    assert (year, conf) == (2012, "text")


def test_derive_year_garbled_returns_none(monkeypatch):
    monkeypatch.setattr(ing, "_source_year_overrides", lambda: {})
    year, conf = ing.derive_source_year("ia_scan.pdf", "no plausible year here !!!")
    assert year is None


def test_build_backfill_metadata_merges_and_omits_none():
    records = [
        ("id1", "dp_a.pdf", {"source": "dp_a.pdf", "page": 0, "chunk_index": 0}),
        ("id2", "ia_b.pdf", {"source": "ia_b.pdf", "page": 3, "chunk_index": 1,
                             "year": 9999}),  # stale year must be cleared
    ]
    year_of = {"dp_a.pdf": (2015, "2010+"), "ia_b.pdf": (None, "unknown")}.get
    ids, metas = ing.build_backfill_metadata(records, year_of)
    assert ids == ["id1", "id2"]
    # existing fields preserved, era added, year set when known
    assert metas[0] == {"source": "dp_a.pdf", "page": 0, "chunk_index": 0,
                        "era": "2010+", "year": 2015}
    # unknown -> era set, year key removed (Chroma rejects None)
    assert metas[1]["era"] == "unknown" and "year" not in metas[1]


def test_iter_chunks_tags_era(monkeypatch):
    """Every emitted chunk carries era, and year when known."""
    fake = Path("dp_fake.pdf")
    monkeypatch.setattr(ing, "_iter_source_files", lambda: [fake])
    monkeypatch.setattr(ing, "_source_year_overrides", lambda: {})
    page = ("Ziraat Fak. Derg. (2015). Azotlu gübreleme bitki büyümesini artırır "
            "ve toprak besin dengesini korumak için oldukça önemlidir.",
            {"source": "dp_fake.pdf", "page": 0})
    monkeypatch.setattr(ing, "_load_file_text", lambda path: iter([page]))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""])
    docs = list(ing.iter_chunks(splitter))
    assert docs, "fixture should emit at least one chunk"
    for d in docs:
        assert d.metadata["era"] == "2010+"
        assert d.metadata["year"] == 2015


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


def _splitter():
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def test_iter_chunks_flags_zero_chunk_file(tmp_path, monkeypatch):
    p = tmp_path / "fao_scan.pdf"
    p.write_bytes(b"x")
    monkeypatch.setattr(ing, "_iter_source_files", lambda: [p])
    monkeypatch.setattr(ing, "_load_file_text", lambda path: iter([]))  # image-only: no text
    zero: list[str] = []
    chunks = list(ing.iter_chunks(_splitter(), store=None, zero_chunk_out=zero))
    assert chunks == []
    assert zero == ["fao_scan.pdf"]


def test_iter_chunks_not_flagged_when_text_present(tmp_path, monkeypatch):
    p = tmp_path / "dp_ok.pdf"
    p.write_bytes(b"x")
    monkeypatch.setattr(ing, "_iter_source_files", lambda: [p])
    monkeypatch.setattr(
        ing, "_load_file_text",
        lambda path: iter([(NORMAL_PROSE, {"source": path.name, "page": 0})]),
    )
    zero: list[str] = []
    chunks = list(ing.iter_chunks(_splitter(), store=None, zero_chunk_out=zero))
    assert len(chunks) >= 1
    assert zero == []


# --------------------------------------------------------------------------- #
# embedding-model guard (2026-07-18)
# --------------------------------------------------------------------------- #
import pytest


def test_check_embedding_model_match_silent():
    assert ing._check_embedding_model("bge-m3", "bge-m3") is None


def test_check_embedding_model_mismatch_raises():
    with pytest.raises(ing.EmbeddingModelMismatchError) as exc:
        ing._check_embedding_model("nomic-embed", "bge-m3")
    msg = str(exc.value)
    assert "nomic-embed" in msg and "bge-m3" in msg


def test_check_embedding_model_none_warns(capsys):
    assert ing._check_embedding_model(None, "bge-m3") is None
    out = capsys.readouterr().out
    assert "bge-m3" in out and "WARNING" in out


def test_check_embedding_model_error_names_reset():
    with pytest.raises(ing.EmbeddingModelMismatchError) as exc:
        ing._check_embedding_model("wrong", "bge-m3")
    assert "--reset" in str(exc.value)


class _FakeCollection:
    def __init__(self, metadata):
        self.metadata = metadata


class _FakeChroma:
    last_kwargs: dict = {}
    recorded_metadata = None  # what an existing collection reports back

    def __init__(self, **kwargs):
        _FakeChroma.last_kwargs = kwargs
        self._collection = _FakeCollection(_FakeChroma.recorded_metadata)


def _patch_chroma(monkeypatch, recorded):
    _FakeChroma.recorded_metadata = recorded
    _FakeChroma.last_kwargs = {}
    monkeypatch.setattr("langchain_chroma.Chroma", _FakeChroma)
    monkeypatch.setattr(ing, "get_embeddings", lambda: object())


def test_get_vector_store_passes_collection_metadata(monkeypatch):
    _patch_chroma(monkeypatch, {"embedding_model": settings.embedding_model})
    ing.get_vector_store()
    assert _FakeChroma.last_kwargs.get("collection_metadata") == {
        "embedding_model": settings.embedding_model
    }


def test_get_vector_store_verifies_by_default(monkeypatch):
    _patch_chroma(monkeypatch, {"embedding_model": "SOME-OTHER-MODEL"})
    with pytest.raises(ing.EmbeddingModelMismatchError):
        ing.get_vector_store()


def test_get_vector_store_verify_false_skips(monkeypatch):
    _patch_chroma(monkeypatch, {"embedding_model": "SOME-OTHER-MODEL"})
    store = ing.get_vector_store(verify_model=False)
    assert store is not None
