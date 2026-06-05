import pytest
from pydantic import ValidationError

from schema import (
    AnalysisGroup,
    BatchResponse,
    BatchSample,
    Measurement,
    ParseMeta,
    ParseResponse,
    ParseResult,
    Report,
    Sample,
)


# --- Measurement ---

def test_measurement_spanish_aliases():
    m = Measurement(simbolo="N", nombre="Nitrógeno", unidad="mg/kg", valor=12.5)
    assert m.symbol == "N"
    assert m.name == "Nitrógeno"
    assert m.unit == "mg/kg"
    assert m.value == 12.5


def test_measurement_english_field_names():
    m = Measurement(symbol="P", name="Fósforo", unit="%", value=3.2)
    assert m.symbol == "P"
    assert m.value == 3.2


def test_measurement_optional_fields_default_none():
    m = Measurement(symbol="K", name="Potasio")
    assert m.unit is None
    assert m.value is None
    assert m.value_text is None
    assert m.range_min is None
    assert m.range_max is None
    assert m.status is None
    assert m.section is None


def test_measurement_value_text_alias():
    m = Measurement(symbol="Ca", name="Calcio", valor_txt="<0.1")
    assert m.value_text == "<0.1"


def test_measurement_section_alias():
    m = Measurement(symbol="pH", name="pH", seccion="general")
    assert m.section == "general"


def test_measurement_requires_symbol_and_name():
    with pytest.raises(ValidationError):
        Measurement(symbol="N")  # missing name


# --- Sample ---

def test_sample_basic():
    s = Sample(geo_id="M1")
    assert s.geo_id == "M1"
    assert s.geo_id_confirmed is False
    assert s.measurements == []


def test_sample_nombre_alias():
    s = Sample(geo_id="M1", nombre="Muestra Norte")
    assert s.name == "Muestra Norte"


def test_sample_mediciones_alias():
    m = Measurement(symbol="N", name="Nitrógeno")
    s = Sample(geo_id="M1", mediciones=[m.model_dump()])
    assert len(s.measurements) == 1


def test_sample_extra_fields_allowed():
    s = Sample(geo_id="M1", campo_extra="valor")
    assert s.geo_id == "M1"


def test_sample_requires_geo_id():
    with pytest.raises(ValidationError):
        Sample()


# --- Report ---

def test_report_spanish_alias():
    r = Report(laboratorio="Agrolab", tipo_analisis="suelo")
    assert r.laboratory == "Agrolab"
    assert r.analysis_type == "suelo"


def test_report_english_field_names():
    r = Report(laboratory="Ceres", analysis_type="foliar")
    assert r.laboratory == "Ceres"


def test_report_analysis_type_optional():
    r = Report(laboratory="Lab X")
    assert r.analysis_type is None


# --- ParseResult ---

def test_parse_result_spanish_aliases():
    result = ParseResult(
        informe={"laboratorio": "agrolab", "tipo_analisis": "suelo"},
        muestras=[{"geo_id": "M1"}],
        total_muestras=1,
    )
    assert result.report.laboratory == "agrolab"
    assert result.total_samples == 1
    assert len(result.samples) == 1


# --- ParseMeta ---

def test_parse_meta_fields():
    meta = ParseMeta(
        laboratory_key="agrolab",
        parser="deterministic",
        detected_as="agrolab",
    )
    assert meta.laboratory_key == "agrolab"
    assert meta.parser == "deterministic"


# --- ParseResponse ---

def test_parse_response_structure():
    response = ParseResponse(
        report=Report(laboratory="agrolab"),
        samples=[Sample(geo_id="M1")],
        total_samples=1,
        meta=ParseMeta(laboratory_key="agrolab", parser="deterministic", detected_as="agrolab"),
    )
    assert response.total_samples == 1
    assert response.meta.parser == "deterministic"


# --- BatchSample ---

def test_batch_sample_requires_source_document():
    with pytest.raises(ValidationError):
        BatchSample(geo_id="M1")


def test_batch_sample_valid():
    bs = BatchSample(geo_id="M1", source_document=0)
    assert bs.source_document == 0


# --- BatchResponse ---

def test_batch_response_structure():
    meta = ParseMeta(laboratory_key="agrolab", parser="deterministic", detected_as="agrolab")
    group = AnalysisGroup(
        analysis_type="suelo",
        documents=[{"laboratory": "agrolab"}],
        samples=[BatchSample(geo_id="M1", source_document=0)],
        total_samples=1,
    )
    batch = BatchResponse(
        laboratory="agrolab",
        analyses=[group],
        total_samples=1,
        meta=meta,
    )
    assert batch.laboratory == "agrolab"
    assert len(batch.analyses) == 1
    assert batch.analyses[0].analysis_type == "suelo"
