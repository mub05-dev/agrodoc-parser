"""
fertilab_parser.py
------------------
Parser for FERTILAB (Fertilidad de Suelos S. de RL) soil analysis PDFs.
Single sample per report. Uses pdfplumber.
"""

import re
import sys
import json
import pdfplumber
from typing import Optional


NA_VALUES = {"", "none", "n/a", "na", "nd", "pnd", "-", "n.a."}

# Cationes order in the % Sat / me/100g rows: Ca Mg K Na Al* H* CIC
_CAT_ORDER = ["Ca", "Mg", "K", "Na"]
_NOR = r"[\d.]+|NA|ND|PND|N\.A\."


def cv(v) -> str:
    return str(v).strip() if v is not None else ""


def parse_number(raw: str) -> Optional[float]:
    if not raw or raw.strip().lower() in NA_VALUES:
        return None
    cleaned = re.sub(r"(\d),(\d{3})\b", r"\1\2", raw.strip())
    cleaned = re.sub(r"[^\d.\-]", "", cleaned.replace(",", "."))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def parse_date(raw: str) -> Optional[str]:
    """YYYY/MM/DD → DD/MM/YYYY"""
    if not raw:
        return None
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})", raw.strip())
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return raw.strip() or None


def find(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() or None if m else None


def parse_profundidad(raw: str) -> Optional[int]:
    if not raw:
        return None
    m = re.search(r"(\d+)\s*-\s*(\d+)", raw)
    if m:
        return int(m.group(2))
    m = re.search(r"(\d+)", raw)
    return int(m.group(1)) if m else None


def build_med(nombre, simbolo, unidad, valor, seccion, valor_txt=None) -> dict:
    return {
        "nombre":    nombre,
        "simbolo":   simbolo,
        "unidad":    unidad,
        "valor":     valor,
        "valor_txt": valor_txt,
        "rango_min": None,
        "rango_max": None,
        "status":    None,
        "seccion":   seccion,
    }


def parse_header(text: str) -> dict:
    folio = find(r"FOLIO:\s*(\S+)", text)

    # Predio / ID: "LOTE 2 / Ms8"
    raw_predio = find(r"Predio\s*/\s*ID:\s*(.+?)(?:\s{2,}|Peso Muestra|\n)", text)
    predio, lab_id = None, None
    if raw_predio:
        parts = [p.strip() for p in raw_predio.split("/")]
        predio = parts[0] if parts else raw_predio
        lab_id = parts[1] if len(parts) > 1 else None

    return {
        "laboratorio":     "Fertilidad de Suelos S. de RL (FERTILAB)",
        "folio":           folio,
        "productor":       find(r"Productor:\s*(.+?)(?:\s{2,}|Tipo de agri)", text),
        "tipo_agricultura":find(r"Tipo de agricultura:\s*(.+?)(?:\n|Localiz)", text),
        "localizacion":    find(r"Localizaci[oó]n muestra:\s*(.+?)(?:\s{2,}|Cultivo)", text),
        "cultivo":         find(r"Cultivo a Establecer:\s*(.+?)(?:\n|Coordenadas)", text),
        "predio":          predio,
        "lab_id":          lab_id,
        "cliente":         find(r"Cliente:\s*(.+?)(?:\s{2,}|Fecha de recep)", text),
        "profundidad_raw": find(r"Prof\.\s*Muestra:\s*(.+?)(?:\s{2,}|\n|Predio)", text),
        "fecha_recepcion": parse_date(find(r"Fecha de recepci[oó]n:\s*(\d{4}/\d{2}/\d{2})", text)),
        "fecha_ejecucion": parse_date(find(r"Fecha de ejecuci[oó]n:\s*(\d{4}/\d{2}/\d{2})", text)),
        "fecha_emision":   parse_date(find(r"Fecha de emisi[oó]n:\s*(\d{4}/\d{2}/\d{2})", text)),
    }


def parse_propiedades_fisicas(text: str) -> list:
    meds = []

    m = re.search(r"Clase Textural\s+(\w+)", text, re.IGNORECASE)
    if m:
        meds.append(build_med("Clase Textural", "Textura", None, None, "fisico",
                              valor_txt=m.group(1)))

    patterns = [
        (r"Saturaci[oó]n\s+(\d+\.?\d*)\s*%",   "sat_pct", "Punto de Saturación",      "%",     "fisico"),
        (r"Capacidad de Campo\s+(\d+\.?\d*)\s*%","CC",     "Capacidad de Campo",        "%",     "fisico"),
        (r"March.*?Perm.*?\s+(\d+\.?\d*)\s*%",  "PMP",    "Punto March. Perm.",        "%",     "fisico"),
        (r"Hidr[aá]ulica\s+(\d+\.?\d*)\s*cm",   "CK",     "Cond. Hidráulica",          "cm/hr", "fisico"),
        (r"Aparente\s+(\d+\.?\d*)\s*g",          "Da",     "Dens. Aparente",            "g/cm3", "fisico"),
    ]
    for pat, simbolo, nombre, unidad, seccion in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            meds.append(build_med(nombre, simbolo, unidad,
                                  parse_number(m.group(1)), seccion))
    return meds


def parse_ph_salinidad(text: str) -> list:
    meds = []
    patterns = [
        (r"pH\s*\(1[.:,]2\s*agua\)\s+([\d.]+)",            "pH",  "pH (1:2 agua)",           "SU",   "fertilidad"),
        (r"Carbonatos Totales.*?\s+([\d.]+)\s*%",           "CO3", "Carbonatos Totales",       "%",    "fertilidad"),
        (r"Salinidad\s*\(CE Extracto\)\s+([\d.]+)\s*dS",   "CE",  "Salinidad (CE Extracto)",  "dS/m", "fertilidad"),
    ]
    for pat, simbolo, nombre, unidad, seccion in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            meds.append(build_med(nombre, simbolo, unidad,
                                  parse_number(m.group(1)), seccion))
    return meds


_PARAMS_FERT = [
    (r"^mo$",             "MO",  "%",   "fertilidad"),
    (r"^p-bray$|^p$",    "P",   "ppm", "fertilidad"),
    (r"^k$",             "K",   "ppm", "cationes"),
    (r"^ca$",            "Ca",  "ppm", "cationes"),
    (r"^mg$",            "Mg",  "ppm", "cationes"),
    (r"^na$",            "Na",  "ppm", "cationes"),
    (r"^fe$",            "Fe",  "ppm", "microelementos"),
    (r"^zn$",            "Zn",  "ppm", "microelementos"),
    (r"^mn$",            "Mn",  "ppm", "microelementos"),
    (r"^cu$",            "Cu",  "ppm", "microelementos"),
    (r"^b$",             "B",   "ppm", "microelementos"),
    (r"^s$",             "S",   "ppm", "fertilidad"),
    (r"^n-no3$",         "NO3", "ppm", "fertilidad"),
]


def _match_fert(label: str):
    lc = label.lower().strip()
    for pat, simbolo, unidad, seccion in _PARAMS_FERT:
        if re.search(pat, lc):
            return simbolo, unidad, seccion
    return None, None, None


def parse_fertilidad_table(tables: list) -> list:
    meds = []

    target, header_idx = None, None
    for t in tables:
        for j, row in enumerate(t):
            if row and any(cv(c).lower() in ("det.", "det") for c in row if c):
                target, header_idx = t, j
                break
        if target:
            break

    if not target:
        return meds

    # Data row: first row after header that has multi-line content in col 0
    data_row = None
    for row in target[header_idx + 1:]:
        if row and row[0] and "\n" in str(row[0]):
            data_row = row
            break

    if not data_row:
        return meds

    raw_labels = str(data_row[0]).split("\n") if data_row[0] else []
    raw_values = str(data_row[1]).split("\n") if len(data_row) > 1 and data_row[1] else []
    raw_units  = str(data_row[2]).split("\n") if len(data_row) > 2 and data_row[2] else []

    # Filter single-digit lines that are method-number prefixes split from labels by OCR
    clean_labels = [l for l in raw_labels
                    if l.strip() and not re.match(r"^\d+$", l.strip())]

    def _clean(l: str) -> str:
        l = re.sub(r"^\d+\s*", "", l).strip()   # "1MO" → "MO"
        l = re.sub(r"\s*\*\s*$", "", l).strip() # "Na *" → "Na"
        return l

    clean_labels = [_clean(l) for l in clean_labels]

    for i, lbl in enumerate(clean_labels):
        val_raw  = raw_values[i] if i < len(raw_values) else ""
        unit_raw = raw_units[i]  if i < len(raw_units)  else ""

        simbolo, unidad, seccion = _match_fert(lbl)
        if not simbolo:
            continue

        valor = parse_number(val_raw)
        unit_clean = unit_raw.strip()
        if unit_clean and unit_clean.lower() not in NA_VALUES:
            unidad = unit_clean

        meds.append(build_med(lbl, simbolo, unidad, valor, seccion))

    return meds


_REL_MAP = {
    "ca/k":    "Ca_K",
    "mg/k":    "Mg_K",
    "ca+mg/k": "CaMg_K",
    "ca/mg":   "Ca_Mg",
}


def parse_cationes(text: str) -> list:
    meds = []

    m = re.search(
        rf"% Sat\s+({_NOR})\s+({_NOR})\s+({_NOR})\s+({_NOR})",
        text, re.IGNORECASE,
    )
    if m:
        for val, ion in zip(m.groups(), _CAT_ORDER):
            v = parse_number(val)
            if v is not None:
                meds.append(build_med(f"% Sat. {ion}", f"Sat_{ion}", "%", v, "saturacion"))

    m = re.search(
        rf"me/100g\s+({_NOR})\s+({_NOR})\s+({_NOR})\s+({_NOR})"
        rf"\s+(?:{_NOR})\s+(?:{_NOR})\s+({_NOR})",
        text, re.IGNORECASE,
    )
    if m:
        *cat_vals, cic_val = m.groups()
        for val, ion in zip(cat_vals, _CAT_ORDER):
            v = parse_number(val)
            if v is not None:
                meds.append(build_med(f"{ion} me/100g", f"{ion}_meq", "me/100g", v, "cationes"))
        cic = parse_number(cic_val)
        if cic is not None:
            meds.append(build_med("CIC", "CIC", "me/100g", cic, "fertilidad"))

    return meds


def parse_relaciones(tables: list) -> list:
    meds = []

    target = None
    for t in tables:
        for row in t:
            if row and any(cv(c).lower() in ("ca/k", "resultados") for c in row if c):
                target = t
                break
        if target:
            break

    if not target:
        return meds

    headers, values = None, None
    for row in target:
        labels = [cv(c).lower() for c in row if c]
        if "ca/k" in labels:
            headers = [cv(c) for c in row]
        elif "resultados" in labels:
            values = [cv(c) for c in row]

    if not headers or not values:
        return meds

    for i, h in enumerate(headers):
        key = h.lower().strip()
        if key in _REL_MAP and i < len(values):
            v = parse_number(values[i])
            if v is not None:
                meds.append(build_med(h, _REL_MAP[key], None, v, "relaciones"))

    return meds


def parse_fertilab(pdf_path: str) -> dict:
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        tables_p1 = pdf.pages[0].extract_tables() if pdf.pages else []

    hdr = parse_header(full_text)

    mediciones = []
    mediciones += parse_propiedades_fisicas(full_text)
    mediciones += parse_ph_salinidad(full_text)
    mediciones += parse_fertilidad_table(tables_p1)
    mediciones += parse_cationes(full_text)
    mediciones += parse_relaciones(tables_p1)

    prof_raw = hdr.get("profundidad_raw")

    informe = {
        "laboratorio":     hdr.get("laboratorio"),
        "folio":           hdr.get("folio"),
        "productor":       hdr.get("productor"),
        "tipo_agricultura":hdr.get("tipo_agricultura"),
        "localizacion":    hdr.get("localizacion"),
        "cultivo":         hdr.get("cultivo"),
        "predio":          hdr.get("predio"),
        "cliente":         hdr.get("cliente"),
        "fecha_recepcion": hdr.get("fecha_recepcion"),
        "fecha_ejecucion": hdr.get("fecha_ejecucion"),
        "fecha_emision":   hdr.get("fecha_emision"),
        "tipo_analisis":   "suelo",
    }

    return {
        "informe": informe,
        "muestras": [
            {
                "geo_id":           "M1",
                "geo_id_confirmed": False,
                "lab_id":           hdr.get("lab_id"),
                "nombre":           hdr.get("predio") or hdr.get("folio"),
                "profundidad_raw":  prof_raw,
                "profundidad_cm":   parse_profundidad(prof_raw),
                "tipo_analisis":    "suelo",
                "mediciones":       mediciones,
            }
        ],
        "total_muestras": 1,
    }
