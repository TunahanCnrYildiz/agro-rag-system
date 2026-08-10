"""Bootstrap download of a prebuilt vector store.

Every test stubs the network. The interesting cases here are not the happy path
but the ways a download SILENTLY produces a broken store: an error page served
with status 200, a truncated body, or the wrong archive entirely. Each of those
must stop the run loudly instead of leaving a half-store behind.
"""

import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from src import fetch_vector_store as fvs


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _make_store_zip(path: Path, chunks: int = 3) -> bytes:
    """A minimal but structurally real store archive: chroma.sqlite3 carrying a
    collections row and `chunks` embeddings, plus a segment directory."""
    db = path.parent / "chroma.sqlite3"
    con = sqlite3.connect(db)
    con.execute("create table collections (id text, name text)")
    con.execute("insert into collections values ('cid', 'botany_knowledge')")
    con.execute("create table embeddings (id integer)")
    con.executemany("insert into embeddings values (?)", [(i,) for i in range(chunks)])
    con.commit()
    con.close()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db, "chroma.sqlite3")
        z.writestr("seg-1/data_level0.bin", b"\x00" * 64)
    db.unlink()
    return buf.getvalue()


class _Resp:
    """Enough of requests.Response for _download / _open_stream."""

    def __init__(self, body: bytes, content_type="application/zip", status=200):
        self._body = body
        self.headers = {"Content-Type": content_type,
                        "Content-Length": str(len(body))}
        self.status_code = status

    def iter_content(self, n):
        for i in range(0, len(self._body), n):
            yield self._body[i:i + n]

    @property
    def text(self):
        return self._body.decode("utf-8", "replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def serve(monkeypatch):
    """Make every GET return one prepared response."""
    def _serve(resp):
        monkeypatch.setattr(fvs.requests.Session, "get",
                            lambda self, *a, **k: resp)
    return _serve


@pytest.fixture
def store_dir(monkeypatch, tmp_path):
    d = tmp_path / "vector_store"
    monkeypatch.setattr(fvs, "VECTOR_STORE_DIR", d)
    return d


# --------------------------------------------------------------------------- #
# Drive link recognition
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url,expected", [
    ("https://drive.google.com/file/d/1AbC_dEfGh12345/view?usp=sharing", "1AbC_dEfGh12345"),
    ("https://drive.google.com/uc?id=1AbC_dEfGh12345&export=download", "1AbC_dEfGh12345"),
    ("https://github.com/x/y/releases/download/v1/vector_store.zip", None),
    ("https://pub-abc.r2.dev/vector_store.zip", None),
])
def test_drive_id_only_fires_on_drive_links(url, expected):
    assert fvs._drive_id(url) == expected


# --------------------------------------------------------------------------- #
# the failure modes that would otherwise ship a broken store
# --------------------------------------------------------------------------- #
def test_an_html_error_page_is_rejected_not_written(tmp_path, store_dir, serve):
    # Drive serves its quota notice with HTTP 200. Without the magic-byte check
    # we would save HTML into a file named .zip and only find out much later.
    serve(_Resp(b"<html><body>Sorry, you have exceeded your download quota"
                b"</body></html>", content_type="text/html"))
    with pytest.raises(SystemExit) as e:
        fvs.run("https://example.com/vector_store.zip")
    assert "zip degil" in str(e.value)
    assert not store_dir.exists()


def test_a_truncated_archive_is_rejected(tmp_path, store_dir, serve):
    good = _make_store_zip(tmp_path)
    serve(_Resp(good[:len(good) // 2]))          # starts with PK, still broken
    with pytest.raises(SystemExit) as e:
        fvs.run("https://example.com/vector_store.zip")
    assert "bozuk" in str(e.value)
    assert not store_dir.exists()


def test_a_checksum_mismatch_aborts(tmp_path, store_dir, serve):
    serve(_Resp(_make_store_zip(tmp_path)))
    with pytest.raises(SystemExit) as e:
        fvs.run("https://example.com/vector_store.zip", expected_sha="0" * 64)
    assert "UYUSMUYOR" in str(e.value)
    assert not store_dir.exists()


def test_an_archive_without_chroma_sqlite_is_rejected(tmp_path, store_dir, serve):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "wrong archive")
    serve(_Resp(buf.getvalue()))
    with pytest.raises(SystemExit) as e:
        fvs.run("https://example.com/vector_store.zip")
    assert "chroma.sqlite3 yok" in str(e.value)
    assert not store_dir.exists()


def test_an_empty_store_is_rejected(tmp_path, store_dir, serve):
    serve(_Resp(_make_store_zip(tmp_path, chunks=0)))
    with pytest.raises(SystemExit) as e:
        fvs.run("https://example.com/vector_store.zip")
    assert "bos gorunuyor" in str(e.value)


# --------------------------------------------------------------------------- #
# the happy path, and not clobbering an existing store
# --------------------------------------------------------------------------- #
def test_a_good_archive_lands_and_verifies(tmp_path, store_dir, serve, capsys):
    body = _make_store_zip(tmp_path)
    serve(_Resp(body))
    fvs.run("https://example.com/vector_store.zip",
            expected_sha=hashlib.sha256(body).hexdigest())
    assert (store_dir / "chroma.sqlite3").exists()
    assert (store_dir / "seg-1" / "data_level0.bin").exists()
    out = capsys.readouterr().out
    assert "botany_knowledge" in out
    assert "parca      : 3" in out


def test_a_populated_store_is_left_alone(monkeypatch, tmp_path, store_dir):
    store_dir.mkdir(parents=True)
    (store_dir / "chroma.sqlite3").write_bytes(b"existing")

    def explode(*a, **k):
        raise AssertionError("must not download over a populated store")

    # monkeypatch, not a bare assignment: deleting Session.get afterwards would
    # strip the method from the class for the rest of the process and break
    # every later test in the run.
    monkeypatch.setattr(fvs.requests.Session, "get", explode)
    fvs.run("https://example.com/vector_store.zip")
    assert (store_dir / "chroma.sqlite3").read_bytes() == b"existing"


def test_force_replaces_but_keeps_the_old_store(tmp_path, store_dir, serve):
    store_dir.mkdir(parents=True)
    (store_dir / "chroma.sqlite3").write_bytes(b"existing")
    serve(_Resp(_make_store_zip(tmp_path)))
    fvs.run("https://example.com/vector_store.zip", force=True)

    # The replaced store is expensive and, once rebuilt elsewhere, gone for
    # good - it must be moved aside, never deleted.
    backup = store_dir.with_name(store_dir.name + "_replaced")
    assert backup.exists()
    assert (backup / "chroma.sqlite3").read_bytes() == b"existing"
    assert (store_dir / "chroma.sqlite3").read_bytes() != b"existing"


def test_a_gitkeep_alone_does_not_count_as_populated(tmp_path, store_dir, serve):
    # A fresh clone ships data/vector_store/.gitkeep; that must not be mistaken
    # for a real store, or the bootstrap would skip and the system run blind.
    store_dir.mkdir(parents=True)
    (store_dir / ".gitkeep").write_text("")
    serve(_Resp(_make_store_zip(tmp_path)))
    fvs.run("https://example.com/vector_store.zip")
    assert (store_dir / "chroma.sqlite3").exists()
