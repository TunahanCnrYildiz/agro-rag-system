from src import fetch_openalex as fo
from src.fetch_openalex import _work_to_candidate
from src.fetch_openalex import _oa_get, POLITE_MAILTO


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
