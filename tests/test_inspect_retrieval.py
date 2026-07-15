from evals import inspect_retrieval as ir


class _Doc:
    def __init__(self, content, source, page):
        self.page_content = content
        self.metadata = {"source": source, "page": page}


def test_build_report_marks_floor_and_lists_sources():
    rows = [
        ("q1", "domates gübre", [
            (_Doc("Azotlu gübreler domateste verimi artırır.", "dp_1.pdf", 3), 0.52),
            (_Doc("Tamamen ilgisiz bir metin parçası.", "ia_x.pdf", 1), 0.20),
        ], None),
    ]
    md = ir.build_report(rows, k=2, which="eval", floor=0.36, prod_k=4)
    assert "dp_1.pdf" in md and "ia_x.pdf" in md   # both sources listed
    assert "✓" in md and "✗" in md                  # above/below floor marked
    assert "0.520" in md                            # score formatting


def test_build_report_handles_error_row():
    rows = [("q2", "bir sorgu", None, "boom")]
    md = ir.build_report(rows, k=2, which="hard", floor=0.36, prod_k=4)
    assert "retrieval failed: boom" in md


def test_snippet_collapses_whitespace_and_escapes_pipe():
    assert ir._snippet("a\n\n  b   c") == "a b c"
    assert "\\|" in ir._snippet("col1 | col2")


def test_probe_queries_sets():
    assert ir.probe_queries("hard") == ir.HARD_PROBES
    assert len(ir.probe_queries("all")) == len(ir.probe_queries("eval")) + len(ir.HARD_PROBES)
