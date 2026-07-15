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
