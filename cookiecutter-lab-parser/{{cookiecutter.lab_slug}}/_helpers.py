from typing import Optional
from parsers.utils import get_full_text


def parse_number(raw: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(str(raw).strip().replace(",", "."))
    except Exception:
        return None


def parse_{{cookiecutter.lab_slug}}(file_path: str) -> dict:
    text = get_full_text(file_path)

    # TODO: extract report metadata (date, order number, producer, etc.)
    report = {
        "laboratorio": "{{cookiecutter.lab_display_name}}",
        "tipo_analisis": None,  # e.g. "suelo", "foliar", "planta"
    }

    # TODO: extract samples and measurements
    # Each sample: {"geo_id": "M1", "lab_id": "...", "mediciones": [...]}
    # Each measurement: {"simbolo": "N", "nombre": "Nitrógeno", "unidad": "mg/kg", "valor": 12.5}
    samples = []

    return {
        "informe": report,
        "muestras": samples,
        "total_muestras": len(samples),
    }
