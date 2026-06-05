"""
agrilab_parser.py
-----------------
Parser for AGRILAB Laboratorios S.A.S. soil analysis PDFs.
Single sample per report. Uses pdfplumber table extraction.
"""

import re
import sys
import json
import pdfplumber
from typing import Optional


PARAMS = [
    (r"^pH$",                                    "pH",       "pH_unit",   "fertilidad",      False),
    (r"Conductividad El[eé]ctrica",               "CE",       "dS/m",      "fertilidad",      False),
    (r"Capacidad de Intercambio|^CICE",           "CICE",     "meq/100g",  "fertilidad",      False),
    (r"Saturaci[oó]n de Humedad",                 "SHM",      "%",         "fertilidad",      False),
    (r"Carbono Org[aá]nico",                      "COOx",     "%",         "fertilidad",      False),
    (r"Materia Org[aá]nica",                      "MO",       "%",         "fertilidad",      False),
    (r"Nitr[oó]geno Total",                       "N_Total",  "%",         "fertilidad",      False),
    (r"Densidad Aparente",                        "Da",       "g/cm3",     "fertilidad",      False),
    (r"^Arcilla$",                                "Arcilla",  "%",         "textura",         False),
    (r"^Arena$",                                  "Arena",    "%",         "textura",         False),
    (r"^Limo$",                                   "Limo",     "%",         "textura",         False),
    (r"^Textura$",                                "Textura",  None,        "textura",         False),
    (r"Potasio Intercambiable",                   "K_inter",  "mg/kg",     "cationes",        True),
    (r"Calcio Intercambiable",                    "Ca_inter", "mg/kg",     "cationes",        True),
    (r"Magnesio Intercambiable",                  "Mg_inter", "mg/kg",     "cationes",        True),
    (r"Sodio Intercambiable",                     "Na_inter", "mg/kg",     "cationes",        True),
    (r"Acidez Intercambiable",                    "Ac_Inter", "meq/100g",  "cationes",        True),
    (r"^Hierro$",                                 "Fe",       "mg/kg",     "microelementos",  True),
    (r"^Manganeso$",                              "Mn",       "mg/kg",     "microelementos",  True),
    (r"^Cobre$",                                  "Cu",       "mg/kg",     "microelementos",  True),
    (r"^Zinc$",                                   "Zn",       "mg/kg",     "microelementos",  True),
    (r"^Boro$",                                   "B",        "mg/kg",     "microelementos",  True),
    (r"^F[oó]sforo$",                             "P",        "mg/kg",     "microelementos",  True),
    (r"^Azufre$",                                 "S",        "mg/kg",     "microelementos",  True),
    (r"Saturaci[oó]n de Magnesio",                "Sat_Mg",   "%",         "relaciones",      False),
    (r"Saturaci[oó]n de Sodio",                   "Sat_Na",   "%",         "relaciones",      False),
    (r"Saturaci[oó]n de Aluminio",                "Sat_Al",   "%",         "relaciones",      False),
    (r"Saturaci[oó]n de Potasio",                 "Sat_K",    "%",         "relaciones",      False),
    (r"Saturaci[oó]n de Calcio",                  "Sat_Ca",   "%",         "relaciones",      False),
    (r"Calcio/Magnesio",                          "Ca_Mg",    None,        "relaciones",      False),
    (r"Calcio/Potasio",                           "Ca_K",     None,        "relaciones",      False),
    (r"Magnesio/Potasio",                         "Mg_K",     None,        "relaciones",      False),
    (r"\(Ca\+Mg\)/K",                             "CaMg_K",   None,        "relaciones",      False),
]

NA_VALUES = {"n.r.", "n.a.", "no aplica.", "no aplica", "nan", "none", ""}

SKIP_LABELS = {
    "VARIABLE", "EXPRESIÓN", "EXPRESION", "ANÁLISIS", "ANALISIS",
    "DETERMINACIÓN", "DETERMINACION", "RELACIONES MATEMÁTICAS",
    "RELACIONES MATEMATICAS", "CONVENCIONES", "OBSERVACIONES",
    "INFORMACIÓN", "INFORMACION", "INFORME", "REMITENTE", "PROPIETARIO",
    "FECHA INGRESO", "CULTIVO", "MUNICIPIO", "INFORMACIÓN ADICIONAL",
    "DESCRIPCIÓN FÍSICA", "DESCRIPCION FISICA",
}


def get_col_map(ncols: int) -> dict:
    if ncols >= 13:
        return {"result": 4, "unit": 6, "rmin": 8, "rmax": 9}
    else:
        return {"result": 2, "unit": 3, "rmin": 4, "rmax": 5}


def cell(row: list, i: int) -> str:
    if i >= len(row) or row[i] is None:
        return ""
    return str(row[i]).strip()


def parse_number(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = raw.replace(",", ".").strip()
    if cleaned.lower() in NA_VALUES:
        return None
    try:
        return float(cleaned)
    except Exception:
        return None


def parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    return raw or None


def get_status(valor: Optional[float], rmin: Optional[float], rmax: Optional[float]) -> Optional[str]:
    if valor is None or (rmin is None and rmax is None):
        return None
    if rmin is not None and valor < rmin:
        return "bajo"
    if rmax is not None and valor > rmax:
        return "alto"
    return "ok"


def match_param(label: str):
    for pattern, simbolo, unidad, seccion, dual in PARAMS:
        if re.search(pattern, label.strip(), re.IGNORECASE):
            return simbolo, unidad, seccion, dual
    return None, None, None, False


def is_skip_row(row: list) -> bool:
    label = cell(row, 0).upper()
    if not label:
        return True
    return any(label.startswith(s) for s in SKIP_LABELS)


def detect_type(text: str) -> str:
    t = text.upper()
    if "FOLIAR" in t or "TEJIDO" in t or "PLANTA" in t:
        return "foliar"
    if "AGUA" in t and "AN" in t:
        return "agua"
    return "suelo"



def extract_header_from_table(table: list) -> dict:
    data: dict = {}
    for row in table:
        label = cell(row, 0).lower()
        if not label:
            continue
        if "informe" in label and "n" in label:
            data["numero_lab"] = cell(row, 10) or None
        elif "remitente" in label:
            data["remitente"]  = cell(row, 1) or None
            data["responsable"] = cell(row, 10) or None
        elif "propietario" in label:
            data["propietario"] = cell(row, 1) or None
            data["email"]       = cell(row, 10) or None
        elif "fecha ingreso" in label:
            data["fecha_ingreso"] = parse_date(cell(row, 1))
            data["fecha_emision"] = parse_date(cell(row, 10))
        elif "cultivo" in label:
            data["cultivo"] = cell(row, 2) or None
            data["lote"]    = cell(row, 12) or None
        elif "municipio" in label:
            parts = [cell(row, 2), cell(row, 5)]
            data["municipio"] = " - ".join(p for p in parts if p)
        elif "descripci" in label and "f" in label:
            for i in range(1, len(row)):
                v = cell(row, i)
                if v:
                    data["descripcion_fisica"] = v
                    break
        elif "análisis" in label or "analisis" in label:
            data["tipo_analisis_raw"] = cell(row, 0)
    return data


def extract_numero_informe(text: str) -> Optional[str]:
    m = re.search(r"(\d{4,6}-V\d+-\d{4})", text)
    return m.group(1) if m else None


def parse_medicion_row(row: list, ncols: int, dual_unit: bool,
                       label: str, simbolo: str, unidad_default: Optional[str],
                       seccion: str) -> Optional[dict]:

    cm = get_col_map(ncols)
    result_raw = cell(row, cm["result"])
    unit_raw   = cell(row, cm["unit"])
    rmin_raw   = cell(row, cm["rmin"])
    rmax_raw   = cell(row, cm["rmax"])

    rmin = parse_number(rmin_raw)
    rmax = parse_number(rmax_raw)

    if dual_unit:
        valor_mgkg = parse_number(result_raw)
        valor_meq  = parse_number(unit_raw)
        valor  = valor_mgkg if valor_mgkg is not None else valor_meq
        unidad = "mg/kg" if valor_mgkg is not None else ("meq/100g" if valor_meq is not None else unidad_default)
        status = get_status(valor_meq if valor_meq is not None else valor, rmin, rmax)

        med: dict = {
            "nombre":    label,
            "simbolo":   simbolo,
            "unidad":    unidad,
            "valor":     valor,
            "valor_txt": None,
            "rango_min": rmin,
            "rango_max": rmax,
            "status":    status,
            "seccion":   seccion,
        }
        if valor_mgkg is not None:
            med["valor_mgkg"] = valor_mgkg
        if valor_meq is not None:
            med["valor_meq"] = valor_meq
        return med

    else:
        valor = parse_number(result_raw)
        valor_txt = result_raw if valor is None and result_raw.lower() not in NA_VALUES else None
        unidad = unit_raw if unit_raw and unit_raw.lower() not in NA_VALUES else unidad_default
        
        status = get_status(valor, rmin, rmax)

        return {
            "nombre":    label,
            "simbolo":   simbolo,
            "unidad":    unidad,
            "valor":     valor,
            "valor_txt": valor_txt,
            "rango_min": rmin,
            "rango_max": rmax,
            "status":    status,
            "seccion":   seccion,
        }


def parse_agrilab(pdf_path: str) -> dict:
    mediciones: list = []
    header_raw: dict = {}
    full_text = ""
    seen: set = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text += (page.extract_text() or "") + "\n"

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue

                ncols = len(table[0])

                if ncols >= 13 and not header_raw:
                    header_raw = extract_header_from_table(table)

                for row in table:
                    if not row or is_skip_row(row):
                        continue

                    label = cell(row, 0)
                    simbolo, unidad_default, seccion, dual = match_param(label)
                    if not simbolo or simbolo in seen:
                        continue

                    med = parse_medicion_row(row, ncols, dual, label, simbolo, unidad_default, seccion)
                    if med:
                        mediciones.append(med)
                        seen.add(simbolo)

    tipo_analisis = detect_type(header_raw.get("tipo_analisis_raw", "") or full_text)

    header = {
        "laboratorio":       "AGRILAB Laboratorios S.A.S.",
        "numero_informe":    extract_numero_informe(full_text),
        "numero_lab":        header_raw.get("numero_lab"),
        "remitente":         header_raw.get("remitente"),
        "propietario":       header_raw.get("propietario"),
        "responsable":       header_raw.get("responsable"),
        "email":             header_raw.get("email"),
        "cultivo":           header_raw.get("cultivo"),
        "lote":              header_raw.get("lote"),
        "municipio":         header_raw.get("municipio"),
        "fecha_ingreso":     header_raw.get("fecha_ingreso"),
        "fecha_emision":     header_raw.get("fecha_emision"),
        "descripcion_fisica": header_raw.get("descripcion_fisica"),
        "tipo_analisis":     tipo_analisis,
    }

    return {
        "informe": header,
        "muestras": [
            {
                "geo_id":           "M1",
                "geo_id_confirmed": False,
                "lab_id":           header.get("numero_lab"),
                "nombre":           header.get("lote") or header.get("cultivo"),
                "profundidad_raw":  None,
                "profundidad_cm":   None,
                "mediciones":       mediciones,
            }
        ],
        "total_muestras": 1,
    }

