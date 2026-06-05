"""
motzz_parser.py
---------------
Parser for Motzz Laboratory, Inc. soil analysis PDFs.
One sample per page. Uses camelot stream for table extraction.
"""

import re
import sys
import json
import camelot
from datetime import datetime
from typing import Optional
from parsers.utils import get_full_text, get_page_count


PARAMS_MOTZZ = [
    (r"^pH",                      "pH",        "SU",        "fertilidad"),
    (r"Electrical Conductivity",  "CE",        "dS/m",      "fertilidad"),
    (r"Calcium",                  "Ca",        "ppm",       "cationes"),
    (r"Magnesium",                "Mg",        "ppm",       "cationes"),
    (r"Sodium",                   "Na",        "ppm",       "cationes"),
    (r"Potassium",                "K",         "ppm",       "cationes"),
    (r"Zinc",                     "Zn",        "ppm",       "microelementos"),
    (r"Iron",                     "Fe",        "ppm",       "microelementos"),
    (r"Manganese",                "Mn",        "ppm",       "microelementos"),
    (r"Copper",                   "Cu",        "ppm",       "microelementos"),
    (r"Nickel",                   "Ni",        "ppm",       "microelementos"),
    (r"Nitrate-N",                "NO3N",      "ppm",       "fertilidad"),
    (r"Phosphate-P",              "PO4P",      "ppm",       "fertilidad"),
    (r"Sulfate-S",                "SO4S",      "ppm",       "fertilidad"),
    (r"Boron",                    "B",         "ppm",       "microelementos"),
    (r"Free Lime",                "FL",        None,        "fertilidad"),
    (r"^ESP",                     "ESP",       "%",         "fertilidad"),
    (r"^CEC",                     "CEC",       "meq/100g",  "cationes"),
    (r"Organic Matter",           "MO",        "%",         "fertilidad"),
]

QUALITATIVE_STATUS_MAP = {
    "very low":  "bajo",
    "low":       "bajo",
    "medium":    "ok",
    "high":      "alto",
    "very high": "alto",
}


def parse_date_us(raw: str) -> Optional[str]:
    """'1/5/2021' → '2021-01-05'"""
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None


def parse_number(raw: str) -> Optional[float]:
    """Handles thousands comma ('3,500' → 3500) and trailing percent ('93.6%' → 93.6)."""
    if not raw:
        return None
    cleaned = str(raw).strip().replace("%", "")
    if re.match(r"^\d{1,3},\d{3}$", cleaned):
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except Exception:
        return None


def qualitative_to_status(text: str) -> Optional[str]:
    if not text:
        return None
    return QUALITATIVE_STATUS_MAP.get(text.strip().lower())


def extract_header(text: str) -> dict:
    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    return {
        "laboratorio":    "Motzz Laboratory",
        "numero_orden":   find(r"PO Number[:\s]+([\w\-]+)"),
        "productor":      find(r"Project[:\s]+(.+?)(?=\n|Date)"),
        "predio":         None,
        "provincia":      None,
        "comuna":         None,
        "remite":         None,
        "fecha_recepcion": parse_date_us(find(r"Date Received[:\s]+([\d/]+)")),
        "fecha_informe":   parse_date_us(find(r"Date Reported[:\s]+([\d/]+)")),
        "fecha_muestreo":  None,
        "fecha_analisis":  None,
    }


def detect_type(text: str) -> str:
    t = text.upper()
    if "SOIL ANALYSIS" in t:
        return "suelo"
    if "FOLIAR" in t or "TISSUE" in t or "PLANT" in t:
        return "foliar"
    if "WATER" in t and "ANALYSIS" in t:
        return "agua"
    return "suelo"


def parse_lab_header(df) -> dict:
    """
    Extracts lab_id, field and depth from the sample header row.
    Format: 'Lab Number: 935016-1 | Field 2.1   30cm | No Crop'
    """
    for _, row in df.iterrows():
        cell = str(row.iloc[0]).strip()
        if "Lab Number:" in cell:
            m_lab = re.search(r"Lab Number[:\s]+([\w\-]+)", cell)
            lab_id = m_lab.group(1).strip() if m_lab else None

            field_raw = str(row.iloc[1]).strip()
            m_field = re.match(r"(Field\s+[\d\.]+)\s+([\w\.]+)", field_raw)
            field       = m_field.group(1).strip() if m_field else field_raw
            profundidad = m_field.group(2).strip() if m_field else None

            prof_num = None
            if profundidad:
                m_num = re.match(r"(\d+)\s*(cm|m)", profundidad.lower())
                if m_num:
                    val  = int(m_num.group(1))
                    unit = m_num.group(2)
                    prof_num = val if unit == "cm" else val * 100

            return {
                "lab_id":         lab_id,
                "nombre":         field,
                "profundidad_raw": profundidad,
                "profundidad_cm": prof_num,
            }
    return {"lab_id": None, "nombre": None, "profundidad_raw": None, "profundidad_cm": None}


def parse_base_saturation(df) -> list:
    """
    Parses the % Base Saturation special row pair.
    Row N: ['% Base Saturation', 'Calculated', 'Ca', 'Mg', 'K', 'Na']
    Row N+1: ['', '', '93.6%', '4.4%', '1.3%', '0.7%']
    """
    header_row = None
    values_row = None

    for i, row in df.iterrows():
        if "Base Saturation" in str(row.iloc[0]):
            header_row = row
            if i + 1 < len(df):
                values_row = df.iloc[i + 1]
            break

    if header_row is None or values_row is None:
        return []

    elementos = [str(header_row.iloc[c]).strip() for c in range(2, 6)]
    valores   = [str(values_row.iloc[c]).strip() for c in range(2, 6)]

    mediciones = []
    for elem, val_raw in zip(elementos, valores):
        if not elem or not val_raw:
            continue
        valor = parse_number(val_raw)
        if valor is None:
            continue
        mediciones.append({
            "nombre":      f"Base Saturation {elem}",
            "simbolo":     f"BS_{elem}",
            "unidad":      "%",
            "valor":       valor,
            "rango_min":   None,
            "rango_max":   None,
            "status":      None,
            "qualitative": None,
            "seccion":     "cationes",
        })
    return mediciones


def parse_motzz_table(df, geo_id: int) -> Optional[dict]:
    meta = parse_lab_header(df)
    if not meta["lab_id"]:
        return None

    mediciones = []

    for _, row in df.iterrows():
        label   = str(row.iloc[0]).strip()
        result  = str(row.iloc[2]).strip()
        unit    = str(row.iloc[3]).strip()
        level   = str(row.iloc[5]).strip()

        if not label or label in ("Soil Complete Test", "Soil:  Organic Matter",
                                   "% Base Saturation", ""):
            continue
        if "Lab Number" in label or "Field" in label:
            continue

        matched = False
        for pattern, simbolo, unidad_default, seccion in PARAMS_MOTZZ:
            if not re.search(pattern, label, re.IGNORECASE):
                continue

            if simbolo == "FL":
                qual   = result if result else (level if level else None)
                status = qualitative_to_status(qual)
                mediciones.append({
                    "nombre":      label,
                    "simbolo":     simbolo,
                    "unidad":      None,
                    "valor":       None,
                    "rango_min":   None,
                    "rango_max":   None,
                    "status":      status,
                    "qualitative": qual,
                    "seccion":     seccion,
                })
                matched = True
                break

            valor = parse_number(result)
            if valor is None:
                matched = True
                break

            qual   = level if level else None
            status = qualitative_to_status(qual)
            unidad_final = unit if unit else unidad_default

            mediciones.append({
                "nombre":      label,
                "simbolo":     simbolo,
                "unidad":      unidad_final,
                "valor":       valor,
                "rango_min":   None,
                "rango_max":   None,
                "status":      status,
                "qualitative": qual,
                "seccion":     seccion,
            })
            matched = True
            break

    mediciones += parse_base_saturation(df)

    return {
        "geo_id":           f"M{geo_id}",
        "geo_id_confirmed": False,
        "lab_id":           meta["lab_id"],
        "nombre":           meta["nombre"],
        "profundidad_raw":  meta["profundidad_raw"],
        "profundidad_cm":   meta["profundidad_cm"],
        "mediciones":       mediciones,
    }


def parse_motzz(pdf_path: str) -> dict:
    full_text = get_full_text(pdf_path)
    tipo      = detect_type(full_text)
    header    = extract_header(full_text)
    n_pages   = get_page_count(pdf_path)

    pages_str = f"1-{n_pages}" if n_pages > 1 else "1"
    tables = camelot.read_pdf(
        pdf_path,
        pages=pages_str,
        flavor="stream",
        edge_tol=50,
    )

    all_samples = []
    geo_counter = 1

    for table in tables:
        df      = table.df
        muestra = parse_motzz_table(df, geo_counter)
        if muestra:
            all_samples.append(muestra)
            geo_counter += 1

    return {
        "informe": {
            **header,
            "tipo_analisis": tipo,
        },
        "muestras":       all_samples,
        "total_muestras": len(all_samples),
    }
