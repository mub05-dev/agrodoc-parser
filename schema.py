from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class Measurement(BaseModel):
    symbol:     str                  = Field(validation_alias="simbolo")
    name:       str                  = Field(validation_alias="nombre")
    unit:       Optional[str]        = Field(None, validation_alias="unidad")
    value:      Optional[float]      = Field(None, validation_alias="valor")
    value_text: Optional[str]        = Field(None, validation_alias="valor_txt")
    range_min:  Optional[float]      = Field(None, validation_alias="rango_min")
    range_max:  Optional[float]      = Field(None, validation_alias="rango_max")
    status:     Optional[str]        = None   # "low" | "ok" | "high"
    qualitative: Optional[str]       = None
    section:    Optional[str]        = Field(None, validation_alias="seccion")

    model_config = ConfigDict(populate_by_name=True)


class Sample(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    geo_id:           str
    geo_id_confirmed: bool                  = False
    lab_id:           Optional[str]         = None
    name:             Optional[str]         = Field(None, validation_alias="nombre")
    measurements:     list[Measurement]     = Field(default_factory=list, validation_alias="mediciones")


class Report(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    laboratory:     str                  = Field(validation_alias="laboratorio")
    analysis_type:  Optional[str]        = Field(None, validation_alias="tipo_analisis")


class ParseMeta(BaseModel):
    laboratory_key: str
    parser:         str
    detected_as:    str


class ParseResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    report:        Report          = Field(validation_alias="informe")
    samples:       list[Sample]    = Field(validation_alias="muestras")
    total_samples: int             = Field(validation_alias="total_muestras")


class ParseResponse(BaseModel):
    report:        Report
    samples:       list[Sample]
    total_samples: int
    meta:          ParseMeta


class BatchSample(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    geo_id:           str
    geo_id_confirmed: bool              = False
    lab_id:           Optional[str]     = None
    name:             Optional[str]     = Field(None, validation_alias="nombre")
    source_document:  int
    measurements:     list[Measurement] = Field(default_factory=list, validation_alias="mediciones")


class AnalysisGroup(BaseModel):
    analysis_type: str
    documents:     list[dict[str, Any]]
    samples:       list[BatchSample]
    total_samples: int


class BatchResponse(BaseModel):
    laboratory:    str
    analyses:      list[AnalysisGroup]
    total_samples: int
    meta:          ParseMeta
