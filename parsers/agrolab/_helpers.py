"""
agrolab_parser.py
-----------------
Parser for Agrolab soil and foliar analysis PDFs.
Supports foliar, soil physical, and soil chemical+physical reports.
Uses camelot stream for table extraction.
"""

import re
import sys
import json
import camelot
from datetime import datetime
from typing import Optional
from parsers.utils import get_full_text, get_page_count


def parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def parse_number(raw: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(str(raw).strip().replace(",", "."))
    except Exception:
        return None


def compute_status(value, rmin, rmax) -> Optional[str]:
    if any(x is None for x in [value, rmin, rmax]):
        return None
    if value < rmin:
        return "bajo"
    if value > rmax:
        return "alto"
    return "ok"


QUALITATIVE_STATUS_MAP = {
    "muy bajo":     "bajo",
    "bajo":         "bajo",
    "lig.acido":    "ok",
    "neutro":       "ok",
    "medio":        "ok",
    "adecuado":     "ok",
    "sin problema": "ok",
    "alto":         "alto",
    "muy alto":     "alto",
    "lev.salino":   "alto",
}


def qualitative_to_status(text: str) -> Optional[str]:
    if not text:
        return None
    return QUALITATIVE_STATUS_MAP.get(text.strip().lower())


def split_value_qualitative(cell: str) -> tuple:
    """'6,6 Neutro' → (6.6, 'Neutro') | '49,9' → (49.9, None)"""
    cell = str(cell).strip()
    m = re.match(r"^([\d,\.]+)\s*(.*)$", cell)
    if not m:
        return None, None
    valor = parse_number(m.group(1))
    qual  = m.group(2).strip() or None
    return valor, qual


def extract_header(text: str) -> dict:
    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    return {
        "laboratorio":    "Agrolab",
        "numero_orden":   find(r"N[º°]\s*Orden[:\s]+([\d\.]+)"),
        "productor":      find(r"Productor\s*[:\n]+\s*(.+?)(?=Especie|Empresa|\n)"),
        "predio":         find(r"Predio\s*[:\n]+\s*(.+?)(?=Tejido|Remite|\n)"),
        "provincia":      find(r"Provincia\s*[:\n]+\s*(.+?)(?=Fecha|\n)"),
        "comuna":         find(r"Comuna\s*[:\n]+\s*(.+?)(?=Fecha|\n)"),
        "remite":         find(r"Remite\s*[:\n]+\s*(.+?)(?=\n)"),
        "fecha_muestreo": parse_date(find(r"Fecha muestreo\s*[:\n]+\s*([\d\-]+)")),
        "fecha_analisis": parse_date(find(r"Fecha an[aá]lisis\s*[:\n]+\s*([\d\-]+)")),
        "fecha_informe":  parse_date(find(r"F\.informe\s*[:\n]+\s*([\d\-]+)")),
    }


def detect_type(text: str) -> str:
    t = text.upper()
    if "TEJIDOS VEGETALES" in t:
        return "foliar"
    if "ANALISIS SUELO" in t or "ANÁLISIS SUELO" in t:
        return "suelo"
    if "ANALISIS AGUA" in t or "ANÁLISIS AGUA" in t:
        return "agua"
    return "desconocido"


def find_lab_cols(df) -> list:
    """Columns whose cells match 6-digit lab IDs."""
    for _, row in df.iterrows():
        vals = [str(v).strip() for v in row]
        matches = [j for j, v in enumerate(vals) if re.match(r'^\d{6}$', v)]
        if len(matches) >= 1:
            return matches
    return []


def find_rango_cols(df, lab_cols: list) -> tuple:
    """
    Locates rango_min / rango_max columns.
    Searches a row that contains a known nutrient and two numeric columns
    beyond the lab_cols block.
    """
    for _, row in df.iterrows():
        vals = [str(v).strip() for v in row]
        row_text = ' '.join(vals)
        if not re.search(r'nitrógeno|nitrogeno|fosforo|fósforo|potasio', row_text.lower()):
            continue
        num_cols = [j for j, v in enumerate(vals) if re.match(r'^[\d,\.]+$', v)]
        rango_cols = [c for c in num_cols if c not in lab_cols]
        if len(rango_cols) >= 2:
            return rango_cols[0], rango_cols[-1]
    return None, None


def extract_row_by_keyword(df, keyword: str, data_cols: list, exact: bool = False) -> list:
    """
    Finds a row by keyword and returns values at data_cols.
    exact=True uses word boundaries — prevents 'edad' matching inside 'variedad'.
    Strips embedded newlines that appear in some Agrolab PDFs.
    """
    for _, row in df.iterrows():
        label = str(row.iloc[0]).replace('\n', ' ').strip().lower()
        if exact:
            if not re.search(rf'\b{re.escape(keyword.lower())}\b', label):
                continue
        else:
            if keyword.lower() not in label:
                continue
        return [str(row.iloc[c]).strip() for c in data_cols]
    return [''] * len(data_cols)


NUTRIENTES_FOLIAR = [
    ("Nitrógeno total", "N",  "%"),
    ("Fósforo",         "P",  "%"),
    ("Potasio",         "K",  "%"),
    ("Calcio",          "Ca", "%"),
    ("Magnesio",        "Mg", "%"),
    ("Azufre",          "S",  "%"),
    ("Hierro",          "Fe", "ppm"),
    ("Manganeso",       "Mn", "ppm"),
    ("Zinc",            "Zn", "ppm"),
    ("Cobre",           "Cu", "ppm"),
    ("Boro",            "B",  "ppm"),
]


def extract_nombres_cuartel(df, lab_cols: list) -> list:
    """
    Extracts cuartel names, concatenating the Identificación row with the
    following row when it contains a name continuation (e.g. 'Espino Surcos\\nLargos').
    """
    nombres = [''] * len(lab_cols)
    for i, row in df.iterrows():
        if 'identificaci' in str(row.iloc[0]).lower():
            nombres = [str(row.iloc[c]).strip() for c in lab_cols]
            if i + 1 < len(df):
                nxt = df.iloc[i + 1]
                nxt_text = ' '.join(str(v) for v in nxt)
                is_continuation = not re.search(
                    r'variedad|edad|laboratorio|rango|adecuado|\d{6}',
                    nxt_text.lower()
                )
                if is_continuation:
                    for k, c in enumerate(lab_cols):
                        extra = str(nxt.iloc[c]).strip()
                        if extra:
                            nombres[k] = (nombres[k] + ' ' + extra).strip()
            break
    return nombres


def parse_foliar_table(df) -> list:
    lab_cols = find_lab_cols(df)
    if not lab_cols:
        return []

    n = len(lab_cols)
    rango_col_min, rango_col_max = find_rango_cols(df, lab_cols)

    especie = None
    m = re.search(r"Especie\s*[:\n]\s*(\w+)", df.to_string(), re.IGNORECASE)
    if m:
        especie = m.group(1).strip().lower()

    nombres    = extract_nombres_cuartel(df, lab_cols)
    variedades = extract_row_by_keyword(df, "variedad",    lab_cols)
    edades     = extract_row_by_keyword(df, "edad",        lab_cols, exact=True)
    lab_ids    = extract_row_by_keyword(df, "laboratorio", lab_cols)

    muestras = []
    for i in range(n):
        try:
            edad = int(edades[i]) if edades[i] else None
        except Exception:
            edad = None
        muestras.append({
            "geo_id":           f"M{i + 1}",
            "geo_id_confirmed": False,
            "lab_id":           lab_ids[i]    if i < len(lab_ids)    else None,
            "nombre":           nombres[i]    if i < len(nombres)    else None,
            "especie":          especie,
            "variedad":         variedades[i] if i < len(variedades) else None,
            "edad_anios":       edad,
            "seccion":          "foliar",
            "mediciones":       [],
        })

    for nombre_param, simbolo, unidad in NUTRIENTES_FOLIAR:
        for _, row in df.iterrows():
            row_text = ' '.join(str(v) for v in row)
            if nombre_param.lower() not in row_text.lower():
                continue

            rango_min, rango_max = None, None
            if rango_col_min is not None:
                rango_min = parse_number(str(row.iloc[rango_col_min]))
            if rango_col_max is not None:
                rango_max = parse_number(str(row.iloc[rango_col_max]))

            for idx, col in enumerate(lab_cols):
                val = parse_number(str(row.iloc[col]))
                if val is None:
                    continue
                muestras[idx]["mediciones"].append({
                    "nombre":      nombre_param,
                    "simbolo":     simbolo,
                    "unidad":      unidad,
                    "valor":       val,
                    "rango_min":   rango_min,
                    "rango_max":   rango_max,
                    "status":      compute_status(val, rango_min, rango_max),
                    "qualitative": None,
                    "seccion":     "foliar",
                })
            break

    return muestras


PARAMS_SUELO = [
    (r"^pH",                             "pH",           "1:2,5",    "fertilidad"),
    (r"C\.Eléctrica|C\.Electrica",       "CE",           "dS/m",     "fertilidad"),
    (r"Materia\s+org",                   "MO",           "%",        "fertilidad"),
    (r"Nitrógeno\s+disp|Nitrogeno\s+d",  "N_disp",       "mg/kg",    "fertilidad"),
    (r"Fósforo\s+disp|Fosforo\s+d",      "P_disp",       "mg/kg",    "fertilidad"),
    (r"Potasio\s+disp",                  "K_disp",       "mg/kg",    "fertilidad"),
    (r"\(Ca\)|Calcio.*Ca\b",             "Ca_inter",     "meq/100g", "cationes"),
    (r"\(Mg\)|Magnesio",                 "Mg_inter",     "meq/100g", "cationes"),
    (r"\(K\).*Potasio|Potasio.*\(K",     "K_inter",      "meq/100g", "cationes"),
    (r"\(Na\)|Sodio",                    "Na_inter",     "meq/100g", "cationes"),
    (r"CIC\s*\(",                        "CIC",          "meq/100g", "cationes"),
    (r"\(Fe\)|Hierro",                   "Fe",           "mg/kg",    "microelementos"),
    (r"\(Mn\)|Manganeso",                "Mn",           "mg/kg",    "microelementos"),
    (r"\(Zn\)|Zinc",                     "Zn",           "mg/kg",    "microelementos"),
    (r"\(Cu\)|Cobre",                    "Cu",           "mg/kg",    "microelementos"),
    (r"\(B\)|Boro",                      "B",            "mg/kg",    "microelementos"),
    (r"Arena\s*\(2,00",                  "Arena",        "%",        "textura"),
    (r"Limo\s*\(0,05",                   "Limo",         "%",        "textura"),
    (r"Arcilla\s*\(<",                   "Arcilla",      "%",        "textura"),
    (r"Arena\s+gruesa",                  "arena_gruesa", "%",        "textura"),
    (r"Arena\s+fina",                    "arena_fina",   "%",        "textura"),
    (r"Densidad\s+aparente",             "dens_aparente","g/cc",     "textura"),
    (r"Densidad\s+real",                 "dens_real",    "g/cc",     "textura"),
    (r"0,3\s+bar",                       "cap_campo",    "%",        "textura"),
    (r"15,0\s+bar",                      "pto_marchitez","%",        "textura"),
    (r"Humedad\s+aprovechable",          "hum_aprovech", "%",        "textura"),
    (r"Porosidad\s+total",               "por_total",    "%",        "textura"),
    (r"Microporosidad",                  "micropor",     "%",        "textura"),
    (r"Macroporosidad",                  "macropor",     "%",        "textura"),
]

SKIP_ROWS_SUELO = {
    "fertilidad", "cationes intercambiables", "microelementos disponibles",
    "textura", "retención de humedad", "retencion de humedad",
    "espacio poroso", "granulometría arena gruesa y fina",
    "granulometria arena gruesa y fina",
}


def parse_suelo_table(df) -> list:
    lab_cols = find_lab_cols(df)
    if not lab_cols:
        return []

    n = len(lab_cols)

    nombres       = extract_row_by_keyword(df, "identificaci", lab_cols)
    profundidades = extract_row_by_keyword(df, "profundidad",  lab_cols)
    lab_ids       = extract_row_by_keyword(df, "laboratorio",  lab_cols)

    muestras = []
    for i in range(n):
        prof_raw = profundidades[i] if i < len(profundidades) else None
        prof_num = None
        if prof_raw:
            pm = re.findall(r"(\d+)", prof_raw)
            if pm:
                prof_num = int(pm[-1])
        lab_id = lab_ids[i] if i < len(lab_ids) else None
        nombre = nombres[i] if i < len(nombres) else None

        # Bloom Group PDFs have no Identificación Cuartel row — fall back to lab_id
        if not nombre and lab_id:
            nombre = lab_id

        muestras.append({
            "geo_id":           f"M{i + 1}",
            "geo_id_confirmed": False,
            "lab_id":           lab_id,
            "nombre":           nombre,
            "profundidad_cm":   prof_num,
            "mediciones":       [],
        })

    for _, row in df.iterrows():
        label = str(row.iloc[0]).strip()
        if label.lower() in SKIP_ROWS_SUELO:
            continue
        if "% CIC" in label or "suma de bases" in label.lower():
            continue
        if not label:
            continue

        for pattern, simbolo, unidad, seccion in PARAMS_SUELO:
            if not re.search(pattern, label, re.IGNORECASE):
                continue
            for idx, col in enumerate(lab_cols):
                cell = str(row.iloc[col]).strip()
                if not cell:
                    continue
                valor, qualitative = split_value_qualitative(cell)
                if valor is None:
                    continue
                muestras[idx]["mediciones"].append({
                    "nombre":      re.sub(r"\s+", " ", label).strip(),
                    "simbolo":     simbolo,
                    "unidad":      unidad,
                    "valor":       valor,
                    "rango_min":   None,
                    "rango_max":   None,
                    "status":      qualitative_to_status(qualitative),
                    "qualitative": qualitative,
                    "seccion":     seccion,
                })
            break

    return muestras


def parse_agrolab(pdf_path: str) -> dict:
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

    # Keep only the largest table per page (most complete)
    tables_by_page = {}
    for t in tables:
        p = t.page
        if p not in tables_by_page or (t.df.shape[0] * t.df.shape[1]) > (tables_by_page[p].df.shape[0] * tables_by_page[p].df.shape[1]):
            tables_by_page[p] = t

    all_samples = []
    for page_num in sorted(tables_by_page.keys()):
        df     = tables_by_page[page_num].df
        # Try to detect type from the table; fall back to global type when the
        # header isn't inside the table (e.g. Bloom Group PDFs)
        t_tipo = detect_type(df.to_string())
        if t_tipo == "desconocido":
            t_tipo = tipo

        if t_tipo == "foliar":
            muestras = parse_foliar_table(df)
        elif t_tipo == "suelo":
            muestras = parse_suelo_table(df)
        else:
            continue

        all_samples.extend(muestras)

    # Reassign geo_ids sequentially across pages
    for i, s in enumerate(all_samples):
        s["geo_id"] = f"M{i + 1}"

    return {
        "informe":        {**header, "tipo_analisis": tipo},
        "muestras":       all_samples,
        "total_muestras": len(all_samples),
    }
