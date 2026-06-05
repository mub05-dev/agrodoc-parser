import pytest

from parsers.registry import EXCEL_REGISTRY, PDF_REGISTRY
from router import _detect_from_text, merge_batch_results, route_excel_parser, route_parser
from schema import BatchResponse, ParseMeta, ParseResponse, Report, Sample


# ─── _detect_from_text ───────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_key", [
    ("AGROLAB INFORME DE SUELOS", "agrolab"),
    ("LABCERESGUATE RESULTADOS", "ceres"),
    ("LABORATORIO AGROPECUARIO LAS GARZAS", "las_garzas"),
    ("FERTILAB ANALISIS DE SUELO", "fertilab"),
    ("PHYTOMONITOR INFORME", "phytomonitor"),
    ("AGRILAB LABORATORIOS REPORTE", "agrilab"),
    ("AGROANALITICA LABORATORIO", "agroanalitica"),
    ("FERTILIZANTES TEPEYAC RESULTADOS", "tepeyac"),
    ("ARIZONA AGRICULTURAL SOLUTIONS LAB NUMBER 001", "motzz"),
])
def test_detect_from_text_each_lab(text, expected_key):
    key = _detect_from_text(text, PDF_REGISTRY)
    assert key == expected_key


def test_detect_from_text_unknown_returns_none():
    key = _detect_from_text("TEXTO SIN LABORATORIO RECONOCIDO", PDF_REGISTRY)
    assert key is None


def test_detect_from_text_empty_returns_none():
    key = _detect_from_text("", PDF_REGISTRY)
    assert key is None


def test_detect_from_text_excel_tepeyac_plant():
    key = _detect_from_text("RESULTADOS DATOS_CLIENTE", EXCEL_REGISTRY)
    assert key == "tepeyac_plant"


# ─── route_parser (PDF) ───────────────────────────────────────────────────────

def test_route_parser_returns_parse_response(pdf_agrolab):
    response = route_parser(str(pdf_agrolab))
    assert isinstance(response, ParseResponse)


def test_route_parser_correct_lab_key(pdf_agrolab):
    response = route_parser(str(pdf_agrolab))
    assert response.meta.laboratory_key == "agrolab"


def test_route_parser_deterministic_parser(pdf_agrolab):
    response = route_parser(str(pdf_agrolab))
    assert response.meta.parser == "deterministic"


def test_route_parser_has_samples(pdf_agrolab):
    response = route_parser(str(pdf_agrolab))
    assert len(response.samples) > 0


def test_route_parser_invalid_file_raises(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"%PDF fake content without lab")
    with pytest.raises(Exception):
        route_parser(str(fake))


# ─── route_excel_parser ───────────────────────────────────────────────────────

def test_route_excel_parser_returns_parse_response(xlsx_tepeyac_plant):
    response = route_excel_parser(str(xlsx_tepeyac_plant))
    assert isinstance(response, ParseResponse)


def test_route_excel_parser_correct_lab_key(xlsx_tepeyac_plant):
    response = route_excel_parser(str(xlsx_tepeyac_plant))
    assert response.meta.laboratory_key == "tepeyac_plant"


def test_route_excel_parser_has_samples(xlsx_tepeyac_plant):
    response = route_excel_parser(str(xlsx_tepeyac_plant))
    assert len(response.samples) > 0


# ─── merge_batch_results ─────────────────────────────────────────────────────

def _make_response(lab: str, analysis_type: str, lab_ids: list[str]) -> ParseResponse:
    samples = [Sample(geo_id=f"X{i}", lab_id=lid) for i, lid in enumerate(lab_ids, 1)]
    return ParseResponse(
        report=Report(laboratory=lab, analysis_type=analysis_type),
        samples=samples,
        total_samples=len(samples),
        meta=ParseMeta(laboratory_key=lab.lower(), parser="deterministic", detected_as=lab.lower()),
    )


def test_merge_geo_ids_reindexed():
    r1 = _make_response("agrolab", "suelo", ["3", "1"])
    r2 = _make_response("agrolab", "suelo", ["2"])
    batch = merge_batch_results([r1, r2])
    geo_ids = [s.geo_id for s in batch.analyses[0].samples]
    assert geo_ids == ["M1", "M2", "M3"]


def test_merge_samples_sorted_by_lab_id():
    r1 = _make_response("agrolab", "suelo", ["3", "1"])
    r2 = _make_response("agrolab", "suelo", ["2"])
    batch = merge_batch_results([r1, r2])
    lab_ids = [s.lab_id for s in batch.analyses[0].samples]
    assert lab_ids == ["1", "2", "3"]


def test_merge_total_samples_correct():
    r1 = _make_response("agrolab", "suelo", ["1", "2"])
    r2 = _make_response("agrolab", "suelo", ["3"])
    batch = merge_batch_results([r1, r2])
    assert batch.total_samples == 3


def test_merge_groups_by_analysis_type():
    r1 = _make_response("agrolab", "suelo", ["1"])
    r2 = _make_response("agrolab", "foliar", ["1"])
    batch = merge_batch_results([r1, r2])
    types = {a.analysis_type for a in batch.analyses}
    assert types == {"suelo", "foliar"}


def test_merge_returns_batch_response():
    r1 = _make_response("agrolab", "suelo", ["1"])
    batch = merge_batch_results([r1])
    assert isinstance(batch, BatchResponse)


def test_merge_source_document_index():
    r1 = _make_response("agrolab", "suelo", ["1"])
    r2 = _make_response("agrolab", "suelo", ["2"])
    batch = merge_batch_results([r1, r2])
    source_docs = {s.source_document for s in batch.analyses[0].samples}
    assert source_docs == {0, 1}
