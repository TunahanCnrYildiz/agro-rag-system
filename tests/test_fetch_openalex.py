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
