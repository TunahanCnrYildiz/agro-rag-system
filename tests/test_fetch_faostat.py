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


def _zip_bytes(member: str | None = None) -> bytes:
    """A zip carrying the member `fetch` expects, unless told otherwise.

    `fetch` validates the member name, so a helper writing some other name
    would make every download test fail for a reason it is not about.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(member or ff.DATASETS["production"].member,
                         "Area Code,Value\n2,1\n")
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


def test_a_cached_archive_without_its_provenance_is_fetched_again(cache):
    """The sidecar is half the cache entry. Returning the zip without it makes
    `fetch` report success and `describe` then raise, telling the operator to
    run the script they just ran."""
    calls = []

    def opener(url, timeout=None):
        calls.append(url)
        return _FakeResponse(_zip_bytes(), "Wed, 31 Dec 2025 11:33:28 GMT")

    ff.fetch("production", opener=opener)
    ff._sidecar_path(ff.DATASETS["production"]).unlink()

    ff.fetch("production", opener=opener)

    assert len(calls) == 2
    assert ff.describe("production")["bytes"] == len(_zip_bytes())


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
