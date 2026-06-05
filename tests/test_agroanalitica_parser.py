import pytest

from parsers.agroanalitica.parser import AgroanaliticaParser
from schema import ParseResult


@pytest.fixture(scope="module")
def parser():
    return AgroanaliticaParser()


@pytest.fixture(scope="module")
def result(parser, pdf_agroanalitica):
    return parser.parse(str(pdf_agroanalitica))


# --- detect ---

def test_detect_true_sin_tilde(parser):
    assert parser.detect("AGROANALITICA LABORATORIO") is True


def test_detect_true_con_tilde(parser):
    assert parser.detect("AGROANALÍTICA RESULTADOS") is True


def test_detect_true_concatenado(parser):
    assert parser.detect("AGROANALITICALABORATORIO INFORME") is True


def test_detect_case_insensitive(parser):
    assert parser.detect("agroanalitica laboratorio") is True


def test_detect_false(parser):
    assert parser.detect("OTRO LABORATORIO SIN RELACION") is False


# --- properties ---

def test_laboratory_key(parser):
    assert parser.laboratory_key == "agroanalitica"


def test_file_type(parser):
    assert parser.file_type == "pdf"


def test_priority(parser):
    assert isinstance(parser.priority, int)


# --- parse ---

def test_parse_returns_parse_result(result):
    assert isinstance(result, ParseResult)


def test_parse_report_laboratory(result):
    assert "agroanal" in result.report.laboratory.lower()


def test_parse_has_samples(result):
    assert len(result.samples) > 0


def test_parse_total_samples_matches(result):
    assert result.total_samples == len(result.samples)


def test_parse_samples_have_geo_id(result):
    for sample in result.samples:
        assert sample.geo_id is not None and sample.geo_id != ""


def test_parse_samples_have_measurements(result):
    for sample in result.samples:
        assert len(sample.measurements) > 0


def test_parse_measurements_have_symbol_and_name(result):
    for sample in result.samples:
        for m in sample.measurements:
            assert m.symbol is not None and m.symbol != ""
            assert m.name is not None and m.name != ""
