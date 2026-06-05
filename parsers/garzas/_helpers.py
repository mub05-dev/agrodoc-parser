"""
las_garzas_parser.py
--------------------
Parser for Laboratorio Agropecuario Las Garzas soil analysis PDFs.
One sample per page, two-column text layout. Uses pdfplumber.
"""

import re
import sys
import json
import pdfplumber
from datetime import datetime
from typing import Optional


def parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def parse_number(raw: str) -> Optional[float]:
    """Strips detection-limit prefix: '<0,03' → 0.03"""
    if not raw:
        return None
    cleaned = str(raw).strip()
    cleaned = re.sub(r"^<\s*", "", cleaned)
    try:
        return float(cleaned.replace(",", "."))
    except Exception:
        return None


QUALITATIVE_STATUS_MAP = {
    "mb": "bajo",
    "b":  "bajo",
    "m":  "ok",
    "a":  "alto",
    "ma": "alto",
}


def qualitative_to_status(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    return QUALITATIVE_STATUS_MAP.get(code.strip().lower())


PARAMS_LAS_GARZAS = [
    # pattern                                   simbolo         nombre                      unidad        seccion
    (r"pH en agua\s*\(1:2,5\)",               "pH",           "pH en agua (1:2,5)",       "SU",         "fertilidad"),
    (r"Cond\.\s*El[eé]ctrica.*?mmhos",        "CE",           "Cond. Eléctrica",          "mmhos/cm",   "fertilidad"),
    (r"Materia\s+Org[aá]nica",                "MO",           "Materia Orgánica",         "%",          "fertilidad"),
    (r"N\*?\s*Disponible",                    "N_disp",       "N Disponible",             "mg/kg",      "fertilidad"),
    (r"P\s+Disponible",                       "P_disp",       "P Disponible",             "mg/kg",      "fertilidad"),
    (r"K\s+Disponible",                       "K_disp",       "K Disponible",             "mg/kg",      "fertilidad"),
    (r"S\s+disponible",                       "S_disp",       "S Disponible",             "mg/kg",      "fertilidad"),
    (r"Ca\s+intercambiable",                  "Ca_inter",     "Ca Intercambiable",        "cmol+/kg",   "cationes"),
    (r"Mg\s+intercambiable",                  "Mg_inter",     "Mg Intercambiable",        "cmol+/kg",   "cationes"),
    (r"Na\s+intercambiable",                  "Na_inter",     "Na Intercambiable",        "cmol+/kg",   "cationes"),
    (r"K\s+intercambiable",                   "K_inter",      "K Intercambiable",         "cmol+/kg",   "cationes"),
    (r"Suma\s+de\s+bases",                    "suma_bases",   "Suma de Bases",            "cmol+/kg",   "cationes"),
    (r"Al\s+intercambiable",                  "Al_inter",     "Al Intercambiable",        "cmol+/kg",   "cationes"),
    (r"\bCICE\b",                             "CICE",         "CICE",                     "cmol+/kg",   "cationes"),
    (r"Saturaci[oó]n\s+de\s+Al",              "sat_Al",       "Saturación de Al",         "%",          "cationes"),
    (r"\bCIC\b(?!E)",                         "CIC",          "CIC",                      "meq/100g",   "cationes"),
    (r"%\s*Sat\.\s*Bases",                    "sat_bases",    "% Sat. Bases",             "%",          "cationes"),
    (r"Al\s+Extractable",                     "Al_ext",       "Al Extractable",           "mg/kg",      "cationes"),
    (r"\bCobre\b",                            "Cu",           "Cobre",                    "mg/kg",      "microelementos"),
    (r"\bZinc\b",                             "Zn",           "Zinc",                     "mg/kg",      "microelementos"),
    (r"\bManganeso\b",                        "Mn",           "Manganeso",                "mg/kg",      "microelementos"),
    (r"\bHierro\b",                           "Fe",           "Hierro",                   "mg/kg",      "microelementos"),
    (r"\bBoro\b",                             "B",            "Boro",                     "mg/kg",      "microelementos"),
]


def extract_param_value(text: str, name_pattern: str) -> tuple:
    """
    Finds name_pattern in text, then extracts the first standalone numeric value
    (preceded by whitespace) on the same line. Returns (value, qualitative_code).

    Handles detection limits ('<0,03' → 0.03) and qualitative codes ('37 A').
    Standalone match prevents capturing digits embedded in units like 'meq/100g'.
    """
    m = re.search(name_pattern, text, re.IGNORECASE)
    if not m:
        return None, None

    pos = m.end()
    line_end = text.find('\n', pos)
    rest = text[pos:line_end] if line_end >= 0 else text[pos:]

    val_m = re.search(r"\s(<\s*[\d,\.]+|[\d,\.]+)", rest)
    if not val_m:
        return None, None

    raw_val = val_m.group(1)
    valor = parse_number(raw_val)
    if valor is None:
        return None, None

    after = rest[val_m.end():]
    qual_m = re.match(r"\s+(MB|MA|B|M|A)\b", after)
    qual = qual_m.group(1) if qual_m else None

    return valor, qual


def extract_texture(text: str) -> tuple:
    """Returns (clase_textural, arena, limo, arcilla, densidad_aparente)."""
    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    clase_raw = find(r"Clase\s+Textural[:\s]+(.+?)(?:\s{2,}|Densidad|\n)")
    clase = clase_raw.strip() if clase_raw else None

    arena   = parse_number(find(r"Arena\s+\(%\)\s+(\d+)"))
    limo    = parse_number(find(r"Limo\s+\(%\)\s+(\d+)"))
    arcilla = parse_number(find(r"Arcilla\s+\(%\)\s+(\d+)"))

    # Densidad appears immediately after 'Arcilla (%) NN' on the same line
    dens_raw = find(r"Arcilla\s+\(%\)\s+\d+\s+(-|[\d,\.]+)")
    densidad = parse_number(dens_raw) if dens_raw and dens_raw != "-" else None

    return clase, arena, limo, arcilla, densidad


def parse_page(text: str, geo_id: int) -> Optional[dict]:
    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    lab_id         = find(r"N[ºo°]\s*Laboratorio[:\s]+(\d+)")
    numero_informe = find(r"N[ºo°]\s*INFORME[:\s]+([\w\s\-]+?)(?=\n|CLIENTE)")
    cliente        = find(r"CLIENTE[:\s]+(.+?)(?=N[ºo°]\s*Laboratorio|\n)")
    predio         = find(r"PREDIO[:\s]+(.+?)(?=COMUNA|\n)")
    comuna         = find(r"COMUNA[:\s]+(.+?)(?=FECHA|\n)")
    fecha_rec_raw  = find(r"FECHA\s+RECEPCION[:\s]+([\d/]+)")
    fecha_ent_raw  = find(r"FECHA\s+ENTREGA[:\s]+([\d/]+)")
    potrero        = find(r"Potrero[:\s]+(.+?)(?=\n|Muestra)")
    prof_raw       = find(r"Profundidad\s+(\d+)\s*cm")

    if not lab_id:
        return None

    mediciones = []
    for name_pattern, simbolo, nombre, unidad, seccion in PARAMS_LAS_GARZAS:
        valor, qual = extract_param_value(text, name_pattern)
        if valor is None:
            continue
        mediciones.append({
            "nombre":      nombre,
            "simbolo":     simbolo,
            "unidad":      unidad,
            "valor":       valor,
            "rango_min":   None,
            "rango_max":   None,
            "status":      qualitative_to_status(qual),
            "qualitative": qual,
            "seccion":     seccion,
        })

    clase, arena, limo, arcilla, densidad = extract_texture(text)
    for simbolo, val in [("arena", arena), ("limo", limo), ("arcilla", arcilla)]:
        if val is not None:
            mediciones.append({
                "nombre":      simbolo,
                "simbolo":     simbolo,
                "unidad":      "%",
                "valor":       val,
                "rango_min":   None,
                "rango_max":   None,
                "status":      None,
                "qualitative": None,
                "seccion":     "textura",
            })
    if densidad is not None:
        mediciones.append({
            "nombre":      "dens_aparente",
            "simbolo":     "dens_aparente",
            "unidad":      "g/cc",
            "valor":       densidad,
            "rango_min":   None,
            "rango_max":   None,
            "status":      None,
            "qualitative": None,
            "seccion":     "textura",
        })

    return {
        "geo_id":           f"M{geo_id}",
        "geo_id_confirmed": False,
        "lab_id":           lab_id,
        "numero_informe":   numero_informe,
        "nombre":           potrero,
        "predio":           predio,
        "comuna":           comuna,
        "clase_textural":   clase,
        "profundidad_cm":   int(prof_raw) if prof_raw else None,
        "fecha_recepcion":  parse_date(fecha_rec_raw),
        "fecha_entrega":    parse_date(fecha_ent_raw),
        "mediciones":       mediciones,
    }


def parse_las_garzas(pdf_path: str) -> dict:
    all_samples = []
    cliente_global = None
    fecha_rec_global = None
    fecha_ent_global = None

    with pdfplumber.open(pdf_path) as pdf:
        for geo_id, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            muestra = parse_page(text, geo_id)
            if not muestra:
                continue

            if geo_id == 1:
                cliente_global    = re.search(r"CLIENTE[:\s]+(.+?)(?=N[ºo°]\s*Laboratorio|\n)",
                                              text, re.IGNORECASE)
                cliente_global    = cliente_global.group(1).strip() if cliente_global else None
                fecha_rec_global  = muestra.get("fecha_recepcion")
                fecha_ent_global  = muestra.get("fecha_entrega")

            all_samples.append(muestra)

    return {
        "informe": {
            "laboratorio":    "Las Garzas",
            "cliente":        cliente_global,
            "fecha_recepcion": fecha_rec_global,
            "fecha_entrega":  fecha_ent_global,
            "tipo_analisis":  "suelo",
        },
        "muestras":       all_samples,
        "total_muestras": len(all_samples),
    }

