"""
phytomonitor_parser.py
----------------------
Parser for PHYTOMONITOR SA DE CV soil analysis PDFs.
Multiple samples per report (one per page block). Uses pdfplumber.
Some samples span two pages (Boro on overflow page).
"""

import re
import sys
import json
import pdfplumber
from typing import Optional


NA_VALUES = {"", "none", "n/a", "na", "nd", "-"}
_NUM = r"\d+(?:\.\d+)?"


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


def parse_range(raw: str) -> tuple:
    raw = re.sub(
        r"\s*(ppm|ms/cm|g/cm\d?|gr/ml|%)\s*$", "", raw.strip(), flags=re.IGNORECASE
    ).strip()
    if not raw:
        return None, None
    raw = re.sub(r"(\d),(\d{3})\b", r"\1\2", raw)
    m = re.match(rf"[<＜]\s*({_NUM})", raw)
    if m:
        return None, float(m.group(1))
    m = re.search(rf"({_NUM})\s*[-–]\s*({_NUM})", raw)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def get_status(v, rmin, rmax) -> Optional[str]:
    if v is None:
        return None
    if rmin is not None and v < rmin:
        return "bajo"
    if rmax is not None and v > rmax:
        return "alto"
    if rmin is not None or rmax is not None:
        return "ok"
    return None


def build_med(nombre, simbolo, unidad, valor, seccion,
              rmin=None, rmax=None, valor_txt=None, **extra) -> dict:
    med = {
        "nombre":    nombre,
        "simbolo":   simbolo,
        "unidad":    unidad,
        "valor":     valor,
        "valor_txt": valor_txt,
        "rango_min": rmin,
        "rango_max": rmax,
        "status":    get_status(valor, rmin, rmax),
        "seccion":   seccion,
    }
    med.update(extra)
    return med


def parse_profundidad(raw: str) -> Optional[int]:
    if not raw:
        return None
    m = re.search(r"(\d+)\s*-\s*(\d+)", raw)
    if m:
        return int(m.group(2))
    m = re.search(r"(\d+)", raw)
    return int(m.group(1)) if m else None


_PARAMS = [
    (r"ph\s*1:1",                              "pH",      "SU",      "fertilidad"),
    (r"conductividad|ms/cm",                   "CE",      "mS/cm",   "fertilidad"),
    (r"materia.*org",                          "MO",      "%",       "fertilidad"),
    (r"textura.*triangulo|triangulo.*tex",     "Textura", None,      "fisico"),
    (r"^arcilla",                              "Arcilla", "%",       "fisico"),
    (r"^arena",                                "Arena",   "%",       "fisico"),
    (r"^limo",                                 "Limo",    "%",       "fisico"),
    (r"porcentaje.*sat|saturaci[oó]n.*%",      "sat_pct", "%",       "fisico"),
    (r"capacidad de campo",                    "CC",      "%",       "fisico"),
    (r"marchitez",                             "PMP",     "%",       "fisico"),
    (r"densidad.*aparente",                    "Da",      "g/cm3",   "fisico"),
    (r"intercambio cati[oó]nico|\bcic\b",      "CIC",     "meq/100g","fertilidad"),
    (r"nitrogeno.*nitri|n-no\s*3",             "NO3",     "ppm",     "fertilidad"),
    (r"fosforo.*fosfato|p-po\s*4",             "P",       "ppm",     "fertilidad"),
    (r"azufre.*sulfato|s-so\s*4",              "S",       "ppm",     "fertilidad"),
    (r"sodio|na\+",                            "Na",      "ppm",     "cationes"),
    (r"potasio|k\+",                           "K",       "ppm",     "cationes"),
    (r"calcio|ca\+",                           "Ca",      "ppm",     "cationes"),
    (r"magnesio|mg\+",                         "Mg",      "ppm",     "cationes"),
    (r"fierro|hierro|\bfe[-\d]",               "Fe",      "ppm",     "microelementos"),
    (r"\bzinc|\bzn\+",                         "Zn",      "ppm",     "microelementos"),
    (r"\bcobre|\bcu\s*\+",                     "Cu",      "ppm",     "microelementos"),
    (r"manganeso|\bmn\+",                      "Mn",      "ppm",     "microelementos"),
    (r"\bboro|\bb\+3",                         "B",       "ppm",     "microelementos"),
]

_SKIP_LABELS = {
    "resultados", "parametros fisicos", "resultado", "niveles", "nivel",
    "aniones (-)", "cationes (+)", "microelementos", "ppm",
    "meq/100 gr.", "% base saturada",
}


def match_param(label: str):
    lc = label.lower().strip()
    if lc in _SKIP_LABELS:
        return None, None, None
    for pat, simbolo, unidad, seccion in _PARAMS:
        if re.search(pat, lc):
            return simbolo, unidad, seccion
    return None, None, None


def parse_report_header(tables: list) -> dict:
    """Extracts client data from the 9-column header table (Table 1)."""
    for t in tables:
        if not (t and len(t[0]) == 9):
            continue
        hdr: dict = {}
        for row in t:
            if not row:
                continue
            lbl0 = cv(row[0]).lower()
            lbl4 = cv(row[4]).lower() if len(row) > 4 else ""
            lbl7 = cv(row[7]).lower() if len(row) > 7 else ""
            if "folio informe" in lbl7:
                hdr["folio_informe"] = cv(row[8]) if len(row) > 8 else None
            if "fecha" in lbl4 and "emis" in lbl4 and len(row) > 6 and row[6]:
                hdr["fecha_emision"] = cv(row[6])
            if "cliente" in lbl0:
                hdr["cliente"]       = cv(row[1]) if len(row) > 1 else None
                hdr["zona_muestreo"] = cv(row[5]) if len(row) > 5 else None
            if "solicitado" in lbl0:
                hdr["solicitado_por"] = cv(row[1]) if len(row) > 1 else None
                hdr["ubicacion"]      = cv(row[5]) if len(row) > 5 else None
            if "folio servicio" in lbl0:
                hdr["folio_servicio"]  = cv(row[1]) if len(row) > 1 else None
                hdr["fecha_recepcion"] = cv(row[5]) if len(row) > 5 else None
        if hdr:
            return hdr
    return {}


def parse_muestra_id(tables: list) -> dict:
    """Extracts sample identification from the 4-column sample table (Table 2)."""
    for t in tables:
        if not (t and len(t[0]) == 4):
            continue
        data: dict = {}
        for row in t:
            if not row:
                continue
            lbl = cv(row[0]).lower()
            if "folio de muestra" in lbl:
                data["folio_muestra"] = cv(row[1])
                data["fecha_toma"]    = cv(row[3])
            elif "tipo de muestra" in lbl:
                data["tipo"] = cv(row[1])
                data["lote"] = cv(row[3])
            elif lbl.startswith("sector"):
                data["sector"]  = cv(row[1])
                data["cultivo"] = cv(row[3])
            elif "profundidad" in lbl:
                data["profundidad_raw"] = cv(row[1])
        if "folio_muestra" in data:
            return data
    return {}


def parse_results_table(table: list) -> list:
    """
    Parses a 3- or 5-column results table.
    Col 0: label  Col 1: ppm/value  Col 2: meq (5-col only)
    Col 3: %sat (5-col only)  Col[-1]: range/level
    """
    meds = []
    for row in table:
        if not row:
            continue
        label = cv(row[0])
        if not label:
            continue

        simbolo, unidad, seccion = match_param(label)
        if not simbolo:
            continue

        val_raw   = cv(row[1]) if len(row) > 1 else ""
        range_raw = cv(row[-1]) if len(row) > 1 else ""

        rmin, rmax = parse_range(range_raw)
        valor     = parse_number(val_raw)
        valor_txt = (val_raw if valor is None
                     and val_raw and val_raw.lower() not in NA_VALUES
                     else None)

        med = build_med(label, simbolo, unidad, valor, seccion,
                        rmin=rmin, rmax=rmax, valor_txt=valor_txt)

        if len(row) >= 5 and row[2] is not None:
            meq = parse_number(cv(row[2]))
            sat = parse_number(cv(row[3])) if row[3] is not None else None
            if meq is not None:
                med["valor_meq"]  = meq
                med["unidad_meq"] = "meq/100g"
            if sat is not None:
                med["sat_pct"] = sat

        meds.append(med)
    return meds


def extract_cic_from_text(text: str) -> Optional[dict]:
    m = re.search(r"Capacidad de Intercambio Cationico\s+([\d.]+)", text, re.IGNORECASE)
    if not m:
        return None
    v = parse_number(m.group(1))
    return build_med("Capacidad de Intercambio Catiónico", "CIC", "meq/100g", v, "fertilidad")


def extract_boro_from_text(text: str) -> Optional[dict]:
    """Extracts Boro from overflow pages where Table 5 is absent."""
    m = re.search(
        r"Boro\s+B\+3[^\n]*?\s+([\d.]+)\s+([\d.]+-[\d.]+)",
        text, re.IGNORECASE,
    )
    if m:
        v = parse_number(m.group(1))
        rmin, rmax = parse_range(m.group(2))
        return build_med("Boro B+3 (Azometina-H)", "B", "ppm", v, "microelementos",
                         rmin=rmin, rmax=rmax)
    m = re.search(r"Boro\s+B\+3[^\n]*?\s+([\d.]+)", text, re.IGNORECASE)
    if m:
        return build_med("Boro B+3 (Azometina-H)", "B", "ppm",
                         parse_number(m.group(1)), "microelementos")
    return None


def parse_phytomonitor(pdf_path: str) -> dict:
    muestras: list = []
    report_hdr: dict = {}
    current_meds: Optional[list] = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text   = page.extract_text() or ""
            tables = page.extract_tables()

            if not report_hdr:
                report_hdr = parse_report_header(tables)

            m_id = parse_muestra_id(tables)

            if m_id:
                meds: list = []
                current_meds = meds

                for t in tables:
                    if not t:
                        continue
                    ncols = len(t[0]) if t[0] else 0
                    if ncols not in (3, 5):
                        continue
                    first_lbl = cv(t[0][0]).lower()
                    if any(k in first_lbl for k in
                           ("fecha", "datos del", "identificaci", "observ")):
                        continue
                    meds.extend(parse_results_table(t))

                if not any(m["simbolo"] == "CIC" for m in meds):
                    cic = extract_cic_from_text(text)
                    if cic:
                        meds.append(cic)

                prof_raw = m_id.get("profundidad_raw")
                muestras.append({
                    "geo_id":           f"M{len(muestras) + 1}",
                    "geo_id_confirmed": False,
                    "lab_id":           m_id.get("folio_muestra"),
                    "nombre":           m_id.get("sector") or m_id.get("lote"),
                    "lote":             m_id.get("lote"),
                    "sector":           m_id.get("sector"),
                    "cultivo":          m_id.get("cultivo"),
                    "profundidad_raw":  prof_raw,
                    "profundidad_cm":   parse_profundidad(prof_raw),
                    "fecha_toma":       m_id.get("fecha_toma"),
                    "tipo_analisis":    "suelo",
                    "mediciones":       meds,
                })

            elif current_meds is not None:
                
                if not any(m["simbolo"] == "B" for m in current_meds):
                    boro = extract_boro_from_text(text)
                    if boro:
                        current_meds.append(boro)

    informe = {
        "laboratorio":    "PHYTOMONITOR SA DE CV",
        "folio_informe":  report_hdr.get("folio_informe"),
        "folio_servicio": report_hdr.get("folio_servicio"),
        "cliente":        report_hdr.get("cliente"),
        "zona_muestreo":  report_hdr.get("zona_muestreo"),
        "ubicacion":      report_hdr.get("ubicacion"),
        "solicitado_por": report_hdr.get("solicitado_por"),
        "fecha_emision":  report_hdr.get("fecha_emision"),
        "fecha_recepcion":report_hdr.get("fecha_recepcion"),
        "tipo_analisis":  "suelo",
    }

    return {
        "informe":        informe,
        "muestras":       muestras,
        "total_muestras": len(muestras),
    }
