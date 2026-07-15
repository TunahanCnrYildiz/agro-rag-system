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
