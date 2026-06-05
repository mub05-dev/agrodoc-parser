"""
ceres_parser.py
---------------
Parser for Agrolaboratorio Ceres (Guatemala) soil analysis PDFs.
Multiple samples per page. Status codes: D=Deficiente→bajo, A=Adecuado→ok, E=Exceso→alto.

PDF structure: the main table uses a "blob row" where col0 contains ALL parameter
names newline-separated, col_muestra has ALL values newline-separated, and
col_status has the first D/A/E letter. Subsequent rows each hold one more D/A/E.
"""

import re
import sys
import json
import pdfplumber
from datetime import datetime
from typing import Optional


STATUS_LETTER_MAP = {
    "D": "bajo",
    "A": "ok",
    "E": "alto",
}

PARAMS_CERES = [
    (r"N-total",             "N_total",   "nutrientes"),
    (r"Nitrato",             "N_NO3",     "nutrientes"),
    (r"P\s+Mehlich",         "P_mehlich", "nutrientes"),
    (r"^K\s*\(%\)",          "K_pct",     "complejo adsorbente"),
    (r"^K\s*\(",             "K_inter",   "nutrientes"),
    (r"^Ca\s*\(%\)",         "Ca_pct",    "complejo adsorbente"),
    (r"^Ca\s*\(mg",          "Ca_inter",  "nutrientes"),
    (r"^Mg\s*\(%\)",         "Mg_pct",    "complejo adsorbente"),
    (r"^Mg\s*\(mg",          "Mg_inter",  "nutrientes"),
    (r"^Na\s*\(mg",          "Na_inter",  "nutrientes"),
    (r"^S\s*\(",             "S",         "nutrientes"),
    (r"^B\s*\(",             "B",         "nutrientes"),
    (r"^Fe\s*\(",            "Fe",        "nutrientes"),
    (r"^Cu\s*\(",            "Cu",        "nutrientes"),
    (r"^Mn\s*\(",            "Mn",        "nutrientes"),
    (r"^Zn\s*\(",            "Zn",        "nutrientes"),
    (r"^pH",                 "pH",        "otras caracteristicas"),
    (r"C\.e\.",              "CE",        "otras caracteristicas"),
    (r"M\.O\.",              "MO",        "otras caracteristicas"),
    (r"C\.I\.C",             "CIC",       "otras caracteristicas"),
    (r"^Acidez",             "Ac_inter",  "otras caracteristicas"),
    (r"^Al\s*\(mmol",        "Al",        "otras caracteristicas"),
    (r"^Ca/Mg",              "Ca_Mg",     "relaciones cationicas"),
    (r"^Ca/K",               "Ca_K",      "relaciones cationicas"),
    (r"^Mg/K",               "Mg_K",      "relaciones cationicas"),
    (r"^Ca\+Mg/K",           "CaMg_K",    "relaciones cationicas"),
    (r"^Al\s*\(%\)",         "Al_pct",    "complejo adsorbente"),
    (r"^H\s*\(%\)",          "H_pct",     "complejo adsorbente"),
]


def parse_number(raw: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(str(raw).strip().replace(",", "."))
    except Exception:
        return None


def parse_date_ceres(raw: str) -> Optional[str]:
    """'7/04/2026' → '2026-04-07'"""
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def parse_range(raw: str) -> tuple:
    """
    '3.0-6.0'     → (3.0, 6.0)
    '40 A 100'    → (40.0, 100.0)
    'MENOR DE 2'  → (None, 2.0)
    '4.00-5.00/1' → (4.0, 5.0)  ratio — /1 ignored
    """
    if not raw:
        return None, None
    raw = raw.strip()
    m = re.match(r"MENOR\s+DE\s+([\d,\.]+)", raw, re.IGNORECASE)
    if m:
        return None, parse_number(m.group(1))
    m = re.match(r"([\d,\.]+)\s+A\s+([\d,\.]+)", raw, re.IGNORECASE)
    if m:
        return parse_number(m.group(1)), parse_number(m.group(2))
    m = re.match(r"([\d,\.]+)-([\d,\.]+)", raw)
    if m:
        return parse_number(m.group(1)), parse_number(m.group(2))
    return None, None


def extract_unit_from_label(label: str) -> Optional[str]:
    m = re.search(r"\(([^)]+)\)", label)
    return m.group(1).strip() if m else None


def detect_section(label: str) -> Optional[str]:
    l = label.strip()
    if re.search(r"OTRAS\s+CARACTER", l, re.IGNORECASE):
        return "otras caracteristicas"
    if re.search(r"RELACIONES\s+CATI", l, re.IGNORECASE):
        return "relaciones cationicas"
    if re.search(r"COMPLEJO\s+ADSOR", l, re.IGNORECASE):
        return "complejo adsorbente"
    if re.match(r"^NUTRIENTES$", l, re.IGNORECASE):
        return "nutrientes"
    return None


def match_param(label: str) -> tuple:
    for pattern, simbolo, seccion in PARAMS_CERES:
        if re.search(pattern, label, re.IGNORECASE):
            return simbolo, seccion
    return None, None


def extract_page_header(text: str) -> dict:
    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else None

    return {
        "laboratorio":     "Agrolaboratorio Ceres",
        "numero_orden":    find(r"DOC[:\s]+([^\n]+)"),
        "interesado":      find(r"Interesado[:\s]+([\w\s]+?)(?=Tel:|DOC:|$)"),
        "cultivo":         find(r"Cultivo[:\s\n]+([A-Za-zÀ-ž]+)"),
        "municipio":       find(r"Municipio y depto[:\s]*(.+?)(?=Condici|$|\n)"),
        "fecha_recepcion": parse_date_ceres(find(r"Fecha de recepci[oó]n[:\s]+([\d/]+)")),
        "fecha_emision":   parse_date_ceres(find(r"Fecha de emisi[oó]n[:\s]+([\d/]+)")),
        "_referencia":     find(r"Ref\.\s+([\d\-\s]+(?:a\s+[\d\-]+)?)"),
    }


def derive_lab_ids(ref_text: str, n_muestras: int) -> list:
    """'26-0376 a 26-0378' with n=3 → ['26-0376', '26-0377', '26-0378']"""
    if not ref_text:
        return [None] * n_muestras
    m = re.search(r"(\d+)-(\d+)\s+a\s+\d+-(\d+)", ref_text)
    if not m:
        return [ref_text.strip()] * n_muestras
    prefix = m.group(1)
    start  = int(m.group(2))
    width  = len(m.group(2))
    return [f"{prefix}-{(start + i):0{width}d}" for i in range(n_muestras)]


def select_data_table(tables: list):
    if not tables:
        return None
    return max(tables, key=lambda t: sum(len(r) for r in t))


def find_status_col(header_row: list, val_col: int, data_rows: list) -> Optional[int]:
    """
    Finds the D/A/E status column closest to val_col.
    Searches between val_col+1 and the next sample col or range col.
    """
    n_cols = len(header_row)
    next_boundary = n_cols
    for j in range(val_col + 1, n_cols):
        v = str(header_row[j] or "").strip()
        if re.match(r"Muestra\s+\d+", v, re.IGNORECASE) or re.search(r"RANGO", v, re.IGNORECASE):
            next_boundary = j
            break

    for j in range(val_col + 1, next_boundary):
        non_empty = [
            str(row[j] or "").strip()
            for row in data_rows
            if j < len(row) and str(row[j] or "").strip()
        ]
        if non_empty and all(v in STATUS_LETTER_MAP for v in non_empty):
            return j
    return None


def parse_ceres_table(table: list, geo_id_start: int, page_text: str) -> list:
    if not table or len(table) < 2:
        return []

    header_row_idx = next(
        (i for i, row in enumerate(table)
         if any(v and re.match(r"Muestra\s+\d+", str(v), re.IGNORECASE) for v in row)),
        None
    )
    if header_row_idx is None:
        return []

    header_row = table[header_row_idx]
    data_rows  = table[header_row_idx + 1:]
    n_cols     = len(header_row)

    muestra_val_cols = [
        (j, str(v).strip())
        for j, v in enumerate(header_row)
        if v and re.match(r"Muestra\s+\d+", str(v), re.IGNORECASE)
    ]
    rango_col = next(
        (j for j in range(n_cols - 1, -1, -1)
         if header_row[j] and re.search(r"RANGO", str(header_row[j]), re.IGNORECASE)),
        None
    )

    if not muestra_val_cols:
        return []

    # Blob row: col0 has all param names newline-separated
    blob_row = next(
        (row for row in data_rows if row[0] and '\n' in str(row[0])),
        None
    )
    if blob_row is None:
        return []

    param_lines = [p.strip() for p in str(blob_row[0]).split('\n') if p.strip()]
    rangos_raw  = (
        [r.strip() for r in str(blob_row[rango_col] or "").split('\n') if r.strip()]
        if rango_col is not None else []
    )

    page_header = extract_page_header(page_text)
    lab_ids     = derive_lab_ids(page_header.get("_referencia", ""), len(muestra_val_cols))

    muestras = []
    for i, (val_col, muestra_nombre) in enumerate(muestra_val_cols):
        status_col = find_status_col(header_row, val_col, data_rows)

        values_raw = [
            v.strip()
            for v in str(blob_row[val_col] or "").split('\n')
            if v.strip()
        ]

        status_letters = []
        if status_col is not None:
            for row in data_rows:
                if status_col < len(row):
                    v = str(row[status_col] or "").strip()
                    if v in STATUS_LETTER_MAP:
                        status_letters.append(v)

        muestras.append({
            "geo_id":           f"M{geo_id_start + i}",
            "geo_id_confirmed": False,
            "lab_id":           lab_ids[i],
            "nombre":           muestra_nombre,
            "_values":          values_raw,
            "_statuses":        status_letters,
            "mediciones":       [],
        })

    # Align param_lines with values/statuses/rangos.
    # param_lines include section headers (no value); values/statuses/rangos do not.
    val_idx         = 0
    current_section = "nutrientes"

    for param_line in param_lines:
        sec = detect_section(param_line)
        if sec:
            current_section = sec
            continue

        simbolo, seccion = match_param(param_line)
        seccion  = seccion or current_section
        unidad   = extract_unit_from_label(param_line)
        rango_raw_str = rangos_raw[val_idx] if val_idx < len(rangos_raw) else ""
        rango_min, rango_max = parse_range(rango_raw_str)

        for muestra in muestras:
            valor         = parse_number(muestra["_values"][val_idx]) if val_idx < len(muestra["_values"]) else None
            status_letter = muestra["_statuses"][val_idx] if val_idx < len(muestra["_statuses"]) else None

            if valor is None:
                continue

            muestra["mediciones"].append({
                "nombre":      param_line,
                "simbolo":     simbolo,
                "unidad":      unidad,
                "valor":       valor,
                "rango_min":   rango_min,
                "rango_max":   rango_max,
                "status":      STATUS_LETTER_MAP.get(status_letter),
                "qualitative": status_letter,
                "seccion":     seccion,
            })

        val_idx += 1

    for m in muestras:
        m.pop("_values",    None)
        m.pop("_statuses",  None)

    return muestras


def get_full_text(pdf_path: str) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def get_page_count(pdf_path: str) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def is_methodology_page(text: str) -> bool:
    return bool(re.search(r"METODOLOG[IÍ]A.*ANALISIS|METODOLOG[IÍ]A.*SUELO", text, re.IGNORECASE))


def detect_type(text: str) -> str:
    t = text.upper()
    if "ANALISIS QUIMICO" in t or "ANÁLISIS QUIMICO" in t:
        return "suelo"
    if "TEJIDOS" in t or "FOLIAR" in t:
        return "foliar"
    if "AGUA" in t and "ANALISIS" in t:
        return "agua"
    return "suelo"


def parse_ceres(pdf_path: str) -> dict:
    all_samples = []
    geo_counter = 1
    doc_numbers = []

    with pdfplumber.open(pdf_path) as pdf:
        full_text  = "\n".join(p.extract_text() or "" for p in pdf.pages)
        tipo       = detect_type(full_text)
        page1_text = pdf.pages[0].extract_text() or ""
        header     = extract_page_header(page1_text)
        header.pop("_referencia", None)
        header["tipo_analisis"] = tipo

        for page in pdf.pages:
            page_text = page.extract_text() or ""

            if is_methodology_page(page_text):
                continue

            m_doc = re.search(r"DOC[:\s]+([^\n]+)", page_text, re.IGNORECASE)
            if m_doc:
                doc_numbers.append(m_doc.group(1).strip())

            tables = page.extract_tables()
            if not tables:
                continue

            data_table = select_data_table(tables)
            muestras   = parse_ceres_table(data_table, geo_counter, page_text)

            if muestras:
                all_samples.extend(muestras)
                geo_counter += len(muestras)

    if doc_numbers:
        header["numeros_orden"] = doc_numbers

    return {
        "informe":        header,
        "muestras":       all_samples,
        "total_muestras": len(all_samples),
    }
