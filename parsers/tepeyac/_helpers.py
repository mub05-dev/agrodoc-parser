"""
tepeyac_parser.py
-----------------
Parser for Fertilizantes Tepeyac soil analysis PDFs.
Multiple samples per page, multi-column table, camelot stream.
"""

import re
import sys
import json
import camelot
import pdfplumber
from datetime import datetime
from typing import Optional, List, Tuple


def parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return None


def parse_number(raw: str) -> Optional[float]:
    if not raw:
        return None
    cleaned = str(raw).strip()
    if cleaned in ("", "-", "NA", "N/A", "na"):
        return None
    try:
        return float(cleaned.replace(",", "."))
    except Exception:
        return None


def parse_ref_cols(col_min: str, col_sep: str, col_max: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract (rango_min, rango_max) from last 3 camelot columns.
    Handles 'X a Y', '< X' (with or without the '<' in col_sep), and '-'.
    """
    max_val = parse_number(col_max)
    if max_val is None:
        return None, None
    min_val = parse_number(col_min)
    return min_val, max_val


def compute_status(valor: Optional[float], rango_min: Optional[float], rango_max: Optional[float]) -> Optional[str]:
    if valor is None or (rango_min is None and rango_max is None):
        return None
    if rango_min is not None and valor < rango_min:
        return "bajo"
    if rango_max is not None and valor > rango_max:
        return "alto"
    return "ok"


SECTION_HEADERS = {
    "PARÁMETROS": "parametros",
    "PARAMETROS": "parametros",
    "ELEMENTOS MAYORES": "mayores",
    "ELEMENTOS MENORES": "micronutrientes",
    "MICRONUTRIENTES": "micronutrientes",
    "% SATURACIÓN DE BASES": "saturacion_bases",
    "% SATURACION DE BASES": "saturacion_bases",
    "RELACIÓN ENTRE CATIONES": "relaciones",
    "RELACION ENTRE CATIONES": "relaciones",
}


def _get_section(col0: str) -> Optional[str]:
    return SECTION_HEADERS.get(col0.strip().upper())


def get_simbolo(name: str, unit: str, section: str) -> Optional[Tuple[str, str]]:
    """Returns (simbolo, seccion_output) or None to skip."""
    n = name.lower().strip()
    if not n:
        return None

    if "textura" in n:
        return None 

    if "punto de saturaci" in n:
        return "sat_pct", "parametros"
    if n == "arena":
        return "Arena", "parametros"
    if n == "limo":
        return "Limo", "parametros"
    if n == "arcilla":
        return "Arcilla", "parametros"
    if "conductividad el" in n:
        return "CE", "parametros"
    if n.startswith("ph"):
        return "pH", "parametros"
    if "materia org" in n:
        return "MO", "parametros"
    if "carbonatos" in n:
        return "CaCO3", "parametros"
    if "conductividad hidr" in n:
        return "CK", "parametros"

    if "nitr" in n and "total" in n:
        return "N_total", "mayores"
    if "nitr" in n:
        return "N_NO3", "mayores"
    if "fosforo" in n or "fósforo" in n:
        if "bray" in n:
            return "P_bray", "mayores"
        if "olsen" in n:
            return "P_olsen", "mayores"
        return "P", "mayores"
    if "aluminio" in n:
        return "Al", "mayores"
    if "acidez" in n:
        return "Ac_inter", "mayores"
    if "capacidad de intercambio" in n:
        return "CIC", "mayores"

    if "hierro" in n:
        return "Fe", "micronutrientes"
    if "manganeso" in n:
        return "Mn", "micronutrientes"
    if "zinc" in n:
        return "Zn", "micronutrientes"
    if "cobre" in n:
        return "Cu", "micronutrientes"
    if "boro" in n:
        return "B", "micronutrientes"

    if "porcentaje de sodio" in n or ("sodio" in n and "intercambiable" in n):
        return "PSI", "saturacion_bases"
    if "calcio" in n and "(ca)" in n:
        return ("Ca_inter", "mayores") if section == "mayores" else ("Ca_sat", "saturacion_bases")
    if "magnesio" in n and "(mg)" in n:
        return ("Mg_inter", "mayores") if section == "mayores" else ("Mg_sat", "saturacion_bases")
    if "potasio" in n and "(k)" in n:
        return ("K_inter", "mayores") if section == "mayores" else ("K_sat", "saturacion_bases")
    if "sodio" in n and "(na)" in n:
        return ("Na_inter", "mayores") if section == "mayores" else ("Na_sat", "saturacion_bases")

    if n == "ca / mg":
        return "Ca_Mg", "relaciones"
    if n == "mg / k":
        return "Mg_K", "relaciones"
    if n == "ca / k":
        return "Ca_K", "relaciones"
    if "(ca + mg) / k" in n:
        return "CaMg_K", "relaciones"

    return None


def parse_header_from_text(text: str) -> dict:
    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    # Terminates a field value: 2+ spaces, or a known field keyword followed by colon, or newline
    # Terminates at: 2+ spaces, a known field keyword, or newline.
    T = r"(?:\s{2,}|\s+(?=(?:Cliente|Predio|Empresa|Ubicaci[oó]n|Cultivo|Riego|Recepci[oó]n|Etapa|No\.)[:\s])|\n)"

    
    titulo = find(r"INFORME DE RESULTADOS DE AN[AÁ]LISIS\s+(?:DE\s+)?(.+)")
    tipo = "foliar" if titulo and "PLANTA" in titulo.upper() else "suelo"

    return {
        "solicitud":        find(r"Solicitud[:\s]+([\w\-]+)"),
        "reporte_no":       find(r"Reporte No[:\s]+([\w\-]+)"),
        "fecha_informe":    parse_date(find(r"Fecha[:\s]+([\d/]+)") or ""),
        "tipo_analisis":    tipo,
        "cliente":          find(r"Cliente[:\s]+(.+?)" + T),
        "predio":           find(r"Predio[:\s]+(.+?)" + T),
        "empresa":          find(r"Empresa[:\s]+(.+?)" + T),
        "ubicacion":        find(r"Ubicaci[oó]n[:\s]+(.+?)" + T),
        "cultivo_anterior": find(r"Cultivo anterior[:\s]+(.+?)" + T),
        "cultivo_actual":   find(r"Cultivo actual[:\s]+(.+?)" + T),
        "riego":            find(r"Riego[:\s]+(.+?)" + T),
        "fecha_recepcion":  parse_date(find(r"Recepci[oó]n[:\s]+([\d/]+)") or ""),
    }



_NOMBRE_COMPLETO: dict = {
    "CIC": "Capacidad de Intercambio Catiónico (CIC)",
    "PSI": "Porcentaje de Sodio Intercambiable (PSI)",
}


def _normalize_unit(raw: str) -> str:
    """Collapse repeated tokens like '% % % %' → '%'."""
    tokens = raw.split()
    if not tokens:
        return raw
    unique = list(dict.fromkeys(tokens))
    return unique[0] if len(unique) == 1 else raw


def _parse_data_table(df, geo_id_start: int) -> List[dict]:
    """Parse one camelot data table → list of sample dicts."""
    n_cols = len(df.columns)
    rows = list(df.iterrows())

    
    lab_id_cols: List[int] = []
    lab_ids: List[str] = []

    for _, row in rows:
        if "No. Laboratorio" in str(row.iloc[1]):
            for j in range(2, n_cols):
                val = str(row.iloc[j]).strip()
                if not val:
                    continue 
                if re.match(r"\d{4}-\d+-\d+", val):
                    lab_ids.append(val)
                    lab_id_cols.append(j)
                else:
                    break
            break

    n_samples = len(lab_ids)
    if n_samples == 0:
        n_samples = max(1, n_cols - 5)
        lab_id_cols = list(range(2, 2 + n_samples))

    
    sample_names: List[str] = []
    for _, row in rows:
        col0 = str(row.iloc[0]).strip()
        col1 = str(row.iloc[1]).strip()
        id_col = col1 if col1 else col0
        if "ID muestra" in id_col and "No. Laboratorio" not in id_col:
            names = [str(row.iloc[j]).strip() if j < n_cols else "" for j in lab_id_cols]
            # Validate: sample names should look like S1, S2… not lab IDs
            if names and not re.match(r"\d{4}-\d+", names[0]):
                sample_names = names
                break

    
    samples: List[dict] = [
        {
            "geo_id":           f"M{geo_id_start + i}",
            "geo_id_confirmed": False,
            "lab_id":           lab_ids[i] if i < len(lab_ids) else None,
            "nombre":           sample_names[i] if i < len(sample_names) else None,
            "clase_textural":   None,
            "mediciones":       [],
        }
        for i in range(n_samples)
    ]

   
    current_section = "parametros"
    pending_name: Optional[str] = None
    skip_next = False
    names_assigned = bool(sample_names)
    last_unit = ""

    for _, row in rows:
        col0 = str(row.iloc[0]).strip()
        col1 = str(row.iloc[1]).strip() if n_cols > 1 else ""

        if skip_next:
            skip_next = False
            continue

        
        sec = _get_section(col0)
        if sec:
            current_section = sec
            if not names_assigned:
                
                for i, j in enumerate(lab_id_cols):
                    if i < len(samples) and j < n_cols:
                        v = str(row.iloc[j]).strip()
                        if v and v not in ("RESULTADOS", "REFERENCIAS", "UNIDADES"):
                            samples[i]["nombre"] = v
                names_assigned = True
            continue

        
        val_cols = [str(row.iloc[j]).strip() if j < n_cols else "" for j in lab_id_cols]
        if col0 and not col1 and all(v == "" for v in val_cols):
            pending_name = col0
            continue

        
        if not col0 and col1 and pending_name:
            param_name = pending_name
            pending_name = None
            skip_next = True
        else:
            param_name = col0
            pending_name = None

        if not param_name:
            continue

        
        raw_unit = col1
        unit = _normalize_unit(raw_unit) if raw_unit else last_unit
        if unit and unit.upper() not in ("UNIDADES", "RESULTADOS", "ID MUESTRA"):
            last_unit = unit

        if not unit or unit.upper() in ("UNIDADES", "RESULTADOS"):
            continue

       
        if "textura" in param_name.lower():
            for i, j in enumerate(lab_id_cols):
                if j < n_cols and i < len(samples):
                    val_str = str(row.iloc[j]).strip()
                    if val_str:
                        samples[i]["clase_textural"] = val_str
            continue

        
        rango_min, rango_max = parse_ref_cols(
            str(row.iloc[n_cols - 3]).strip(),
            str(row.iloc[n_cols - 2]).strip(),
            str(row.iloc[n_cols - 1]).strip(),
        )

        result = get_simbolo(param_name, unit, current_section)
        if result is None:
            continue
        simbolo, seccion_out = result

        for i, j in enumerate(lab_id_cols):
            if j >= n_cols or i >= len(samples):
                continue
            raw_val = str(row.iloc[j]).strip()
            if not raw_val:  
                continue
            valor = parse_number(raw_val)  
            samples[i]["mediciones"].append({
                "nombre":      _NOMBRE_COMPLETO.get(simbolo, param_name),
                "simbolo":     simbolo,
                "unidad":      unit,
                "valor":       valor,
                "rango_min":   rango_min,
                "rango_max":   rango_max,
                "status":      compute_status(valor, rango_min, rango_max),
                "qualitative": None,
                "seccion":     seccion_out,
            })

    return samples


def parse_tepeyac(pdf_path: str) -> dict:
    """Main entry point. Returns normalized JSON for a Tepeyac soil report."""
    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""

    header = parse_header_from_text(first_page_text)

    tables = camelot.read_pdf(pdf_path, flavor="stream", pages="all")

    all_samples: List[dict] = []
    geo_id = 1

    
    for t in tables:
        df = t.df
        if len(df.columns) < 6:
            continue
        
        has_lab_row = any("No. Laboratorio" in str(row.iloc[1]) for _, row in df.iterrows())
        if not has_lab_row:
            continue

        page_samples = _parse_data_table(df, geo_id)
        all_samples.extend(page_samples)
        geo_id += len(page_samples)

    return {
        "informe": {
            "laboratorio": "Fertilizantes Tepeyac",
            **header,
        },
        "muestras":       all_samples,
        "total_muestras": len(all_samples),
    }

