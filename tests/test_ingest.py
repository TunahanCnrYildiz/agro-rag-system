from pathlib import Path

from src.ingest import _is_junk_chunk
from src import ingest as ing

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
