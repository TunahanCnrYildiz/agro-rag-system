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


def test_fao_id_lowercased():
    # FAO exposes case-variant handles (I4774E / i4774e) for the same doc;
    # the id must be lowercased so they collapse to one file / one dedup key.
    cand = _record_to_candidate(
        _rec(identifier="oai:openknowledge.fao.org:20.500.14283/I4774E")
    )
    assert cand[0] == "i4774e"


def test_none_for_animal_market_machinery_even_with_plant_term():
    # each has a plant term (crop/bananas/harvesting) but an off-scope term too
    assert _record_to_candidate(
        _rec(title="Global Animal Disease report on crop regions",
             description="Intelligence report.")
    ) is None
    assert _record_to_candidate(
        _rec(title="Market and value chain analysis of crop sectors",
             description="Economic study of prices.")
    ) is None
    assert _record_to_candidate(
        _rec(title="Roots, tubers and bananas in animal feeding",
             description="Feeding trial with crop residues.")
    ) is None
    assert _record_to_candidate(
        _rec(title="Agricultural robotics for crop harvesting",
             description="Automated machinery.")
    ) is None


def test_none_for_zoonotic_disease_and_humanitarian():
    # bare "nutrition"/"disease" are include terms, but these human/animal-crisis
    # contexts must still be excluded
    assert _record_to_candidate(
        _rec(title="Technical meeting on MERS-CoV at the animal interface",
             description="Understanding crop-region disease spread.")
    ) is None
    assert _record_to_candidate(
        _rec(title="Avian influenza (HPAI) outbreaks in poultry",
             description="Surveillance near crop areas.")
    ) is None
    assert _record_to_candidate(
        _rec(title="Somalia famine prevention scale-up plan",
             description="Emergency crop and seed distribution.")
    ) is None
    assert _record_to_candidate(
        _rec(title="Quarterly food and nutrition security report",
             description="Household diet and crop access.")
    ) is None


def test_keeps_plant_disease_and_pest_records():
    # in-scope plant pest/disease management must NOT be caught by the animal
    # disease excludes
    assert _record_to_candidate(
        _rec(title="Integrated management of crop pests and diseases",
             description="Organic control of a plant disease outbreak.")
    ) is not None


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


def test_is_pruned_detects_offtopic(tmp_path, monkeypatch):
    books = tmp_path / "books"
    (books / "_offtopic").mkdir(parents=True)
    (books / "_offtopic" / "fao_z9.pdf").write_bytes(b"x")
    monkeypatch.setattr(ff, "BOOKS_DIR", books)
    assert ff._is_pruned("z9") is True
    assert ff._is_pruned("z8") is False


def test_list_sets_parses_specs_and_names(monkeypatch):
    root = ET.fromstring(
        f'<OAI-PMH {_NS_DECL}><ListSets>'
        f'<set><setSpec>col_2</setSpec><setName>Publications</setName></set>'
        f'<set><setSpec>col_3</setSpec><setName>Technical documents</setName></set>'
        f'</ListSets></OAI-PMH>'
    )
    monkeypatch.setattr(ff, "_oai", lambda s, params: root)
    out = ff.list_sets(object())
    assert out == [("col_2", "Publications"), ("col_3", "Technical documents")]


def test_run_dry_run_downloads_nothing(tmp_path, monkeypatch):
    books = tmp_path / "books"
    monkeypatch.setattr(ff, "BOOKS_DIR", books)
    monkeypatch.setattr(ff, "pdf_session", lambda *a, **k: object())
    monkeypatch.setattr(
        ff, "_collect_candidates",
        lambda s, spec, mb, ms: [("x1", "u1.pdf", "crop production guide")],
    )
    monkeypatch.setattr(
        ff, "download",
        lambda *a: (_ for _ in ()).throw(AssertionError("no download in dry-run")),
    )
    n = ff.run(set_spec="set", max_books=100, max_scan=8000, dry_run=True)
    assert n == 0


def test_run_skips_existing_and_counts_saved(tmp_path, monkeypatch):
    books = tmp_path / "books"
    books.mkdir()
    (books / "fao_have.pdf").write_bytes(b"%PDF-old")  # already present -> skip
    monkeypatch.setattr(ff, "BOOKS_DIR", books)
    monkeypatch.setattr(ff, "pdf_session", lambda *a, **k: object())
    monkeypatch.setattr(ff.time, "sleep", lambda *a: None)
    monkeypatch.setattr(
        ff, "_collect_candidates",
        lambda s, spec, mb, ms: [
            ("have", "u_have.pdf", "already here"),
            ("new1", "u_new1.pdf", "new crop guide"),
        ],
    )
    saved_urls = []

    def fake_download(session, url, dest):
        saved_urls.append(url)
        dest.write_bytes(b"%PDF-new")
        return True

    monkeypatch.setattr(ff, "download", fake_download)
    n = ff.run(set_spec="set", max_books=100, max_scan=8000, dry_run=False)
    assert n == 1                       # only "new1" downloaded
    assert saved_urls == ["u_new1.pdf"]  # existing "have" skipped


def test_main_list_sets_prints(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["fetch_fao", "--list-sets"])
    monkeypatch.setattr(ff, "pdf_session", lambda *a, **k: object())
    monkeypatch.setattr(ff, "list_sets", lambda s: [("col_2", "Publications")])
    ff.main()
    printed = capsys.readouterr().out
    assert "col_2" in printed and "Publications" in printed
