from pathlib import Path

from src import fetch_dergipark as fd
from src.fetch_dergipark import _OFFTOPIC_REC, is_offtopic_text

# --------------------------------------------------------------------------- #
# Fetcher filter (_OFFTOPIC_REC) — applied to clean OAI title+subject text.
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Cleanup filter (_OFFTOPIC_CLEANUP_REC / is_offtopic_text) — applied to noisy
# full-page PDF text, so it must be high-precision and avoid false positives.
# --------------------------------------------------------------------------- #

# Full-page snippets that MUST be flagged (unambiguous livestock/aquaculture).
CLEANUP_OFFTOPIC = [
    "Ziraat Fakültesi Zootekni Bölümü, Antalya. Koyun besleme çalışması",
    "Isotonic Regression Analysis İvesi Koyunlarının Awassi Sheep growth",
    "Atatürk Üniversitesi Su Ürünleri Fakültesi, Erzurum",
    "Broyler tavuklarda artan rasyon düzeyinin karkas verimine etkisi",
    "Veteriner Fakültesi buzağı büyüme performansı",
]

# Full-page snippets that MUST NOT be flagged. These are the exact false-positive
# classes the audit found: the surname 'Koyuncu', the substring inside
# 'konsantrasyon', goat/cattle manure (an on-topic organic fertilizer), dairy
# products from a plant, the surname 'Balık', and a 'Tarım Ekonomisi' dept.
CLEANUP_INSCOPE = [
    "Bir çalışmada Erbaş & Koyuncu (2022) tozlanmayı incelemiştir",
    "Artan NaCl konsantrasyonlarının çimlenme üzerine etkisi",
    "Effects of Goat Manure, Biochar, and NPK Application on yield",
    "The leaves are traditionally used in the production of dairy products",
    "Balık et al. (2016) reported new cultivars of the plant",
    "Ondokuz Mayıs Üniversitesi Ziraat Fakültesi Tarım Ekonomisi Bölümü",
]


def test_cleanup_flags_livestock_fulltext():
    for text in CLEANUP_OFFTOPIC:
        assert is_offtopic_text(text), f"should flag: {text}"


def test_cleanup_ignores_plant_fulltext_false_positives():
    for text in CLEANUP_INSCOPE:
        assert not is_offtopic_text(text), f"should NOT flag: {text}"


# --------------------------------------------------------------------------- #
# clean_offtopic — report-only by default, moves only with apply=True.
# --------------------------------------------------------------------------- #

class _FakeStore:
    """Minimal Chroma stand-in recording deletes by source name."""
    def __init__(self):
        self.deleted = []

    def get(self, where, limit=None):
        return {"ids": [f"{where['source']}:0"]}

    def delete(self, ids):
        self.deleted.extend(ids)


def _make_books(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir()
    off = books / "dp_1.pdf"
    keep = books / "dp_2.pdf"
    off.write_bytes(b"x")
    keep.write_bytes(b"x")
    monkeypatch.setattr(fd, "BOOKS_DIR", books)
    texts = {
        off: "Zootekni Bölümü koyun besleme ve rasyon çalışması",
        keep: "Bitki besleme ve toprak besin maddeleri",
    }
    return books, off, keep, texts


def test_clean_offtopic_report_only_moves_nothing(tmp_path, monkeypatch):
    books, off, keep, texts = _make_books(tmp_path, monkeypatch)

    n = fd.clean_offtopic(store=_FakeStore(), apply=False,
                          text_fn=lambda p: texts[p])

    assert n == 1
    assert off.exists()  # nothing moved in report-only mode
    assert keep.exists()
    report = books.parent / "offtopic_candidates.txt"
    assert report.exists()
    assert "dp_1.pdf" in report.read_text(encoding="utf-8")
    assert "dp_2.pdf" not in report.read_text(encoding="utf-8")


def test_clean_offtopic_apply_moves_and_deletes(tmp_path, monkeypatch):
    books, off, keep, texts = _make_books(tmp_path, monkeypatch)

    store = _FakeStore()
    n = fd.clean_offtopic(store=store, apply=True, text_fn=lambda p: texts[p])

    assert n == 1
    assert not off.exists()
    assert (books / "_offtopic" / "dp_1.pdf").exists()
    assert keep.exists()
    assert store.deleted == ["dp_1.pdf:0"]


# --------------------------------------------------------------------------- #
# _is_pruned — a fetch must not re-download a paper already moved to _offtopic.
# --------------------------------------------------------------------------- #

def test_is_pruned_detects_offtopic_papers(tmp_path, monkeypatch):
    books = tmp_path / "books"
    (books / "_offtopic").mkdir(parents=True)
    (books / "_offtopic" / "dp_123.pdf").write_bytes(b"x")
    # nested (e.g. lowrelevance/) must also count as pruned
    (books / "_offtopic" / "lowrelevance").mkdir()
    (books / "_offtopic" / "lowrelevance" / "dp_456.pdf").write_bytes(b"x")
    monkeypatch.setattr(fd, "BOOKS_DIR", books)

    assert fd._is_pruned("123") is True
    assert fd._is_pruned("456") is True
    assert fd._is_pruned("999") is False


def test_is_pruned_false_when_no_offtopic_dir(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir()
    monkeypatch.setattr(fd, "BOOKS_DIR", books)
    assert fd._is_pruned("123") is False
