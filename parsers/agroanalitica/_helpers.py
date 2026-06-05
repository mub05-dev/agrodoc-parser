"""
agroanalitica_parser.py
-----------------------
Parser for AGROANALÍTICA Consultoría Agrícola soil analysis PDFs.
Image-based PDF — renders pages with pypdfium2, extracts text via pytesseract OCR.
Supports: Análisis de Fertilidad (4 samples/page) and Extracto Saturado (2 samples/page).
"""

import os
import re
import sys
import json
import platform
from typing import Optional

import pypdfium2 as pdfium
import pytesseract
from PIL import Image

_tess_env = os.getenv("TESSERACT_CMD")
if _tess_env:
    pytesseract.pytesseract.tesseract_cmd = _tess_env
elif platform.system() == "Windows":
    _win_default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(_win_default):
        pytesseract.pytesseract.tesseract_cmd = _win_default

OCR_CONFIG   = "--psm 11"
OCR_LANG     = "eng"
RENDER_SCALE = 4.0

# Column boundaries as fraction of image width
# Fertilidad page 1: param | M-1 | M-2 | M-3 | M-4 | reference
COLS_FERT = [0.0, 0.25, 0.37, 0.51, 0.66, 0.82, 1.0]

# Extracto saturado pages 2-3: param | Mx_ppm | Mx_meq | M(x+1)_ppm | M(x+1)_meq | reference
COLS_EXTR = [0.0, 0.22, 0.38, 0.54, 0.68, 0.82, 1.0]


PARAMS_FERT = [
    (r"%\s*mo\b|materia.org",          "MO",      "%",        "fertilidad"),
    (r"ph\s*(1:2|cac)",                "pH",      "SU",       "fertilidad"),
    (r"c\.e\.\(|c\.e\.\s",            "CE",      "dS/m",     "fertilidad"),
    (r"%\s*sat\.?",                    "SAT",     "%",        "fertilidad"),
    (r"nitratos|n-no3",                "NO3",     "ppm",      "fertilidad"),
    (r"fosforo|p-po4",                 "P",       "ppm",      "fertilidad"),
    (r"azufre|s-so[04]",               "S",       "ppm",      "fertilidad"),
    (r"amonio|n-nh4",                  "NH4",     "ppm",      "fertilidad"),
    (r"potasio\s*\(k",                  "K",       "ppm",      "cationes"),
    (r"calcio\s*\(ca",                  "Ca",      "ppm",      "cationes"),
    (r"magnesio\s*\(mg",                "Mg",      "ppm",      "cationes"),
    (r"sodio\s*\(na",                   "Na",      "ppm",      "cationes"),
    (r"fierro|hierro|\(fe\)",          "Fe",      "ppm",      "microelementos"),
    (r"cobre|\(cu\)",                  "Cu",      "ppm",      "microelementos"),
    (r"zinc|\(zn\)",                   "Zn",      "ppm",      "microelementos"),
    (r"manganeso|\(mn\)",              "Mn",      "ppm",      "microelementos"),
    (r"boro\s*\(b\)",                  "B",       "ppm",      "microelementos"),
    (r"%\s*arena",                     "Arena",   "%",        "textura"),
    (r"(?:%\s*)?limo\b",               "Limo",    "%",        "textura"),
    (r"(?:%\s*)?arcilla\b",            "Arcilla", "%",        "textura"),
    (r"clasif|textural",               "Textura", None,       "textura"),
    (r"c\.[il]\.?c|cic\s*\(",          "CIC",     "meq/100g", "fertilidad"),
]

# % Saturación de Bases sub-rows
SAT_BASES = {
    "na": ("Sat_Na", "%", "saturacion"),
    "k":  ("Sat_K",  "%", "saturacion"),
    "ca": ("Sat_Ca", "%", "saturacion"),
    "mg": ("Sat_Mg", "%", "saturacion"),
}


PARAMS_EXTR = [
    (r"^ph$",                           "pH",      "SU",    "general",       False),
    (r"c\.e\.\(|c\.e\.\s",             "CE",      "dS/m",  "general",       False),
    (r"\bras\b",                        "RAS",     None,    "general",       False),
    (r"\bpsi\b",                        "PSI",     None,    "general",       False),
    (r"%\s*sat\.?",                     "SAT",     "%",     "general",       False),
    (r"potasio|\(k\+\)",               "K",       "ppm",   "cationes",      True),
    (r"calcio|\(ca\+\+\)",             "Ca",      "ppm",   "cationes",      True),
    (r"magnesio|\(mg\+\+\)",           "Mg",      "ppm",   "cationes",      True),
    (r"sodio|\(na\+\)",                "Na",      "ppm",   "cationes",      True),
    (r"amonio|\(n-nh4",                "NH4",     "ppm",   "cationes",      True),
    (r"suma de cationes",              "SumaCat", "meq/l", "cationes",      False),
    (r"nitratos|\(no3",                "NO3",     "ppm",   "aniones",       True),
    (r"fosfatos|\(po4",                "PO4",     "ppm",   "aniones",       True),
    (r"sulfatos|\(so4",                "SO4",     "ppm",   "aniones",       True),
    (r"cloruros|\(cl[^o]",             "Cl",      "ppm",   "aniones",       True),
    (r"carbonatos|\(co3",              "CO3",     "ppm",   "aniones",       True),
    (r"bicarbonatos|\(hco3",           "HCO3",    "ppm",   "aniones",       True),
    (r"suma de aniones",               "SumaAni", "meq/l", "aniones",       False),
    (r"no3.{0,3}/\s*k\+",             "NO3_K",   None,    "relaciones",    False),
    (r"k\+\s*/\s*ca",                  "K_Ca",    None,    "relaciones",    False),
    (r"ca\+\+\s*/\s*mg",               "Ca_Mg",   None,    "relaciones",    False),
    (r"k\+\s*/\s*mg",                  "K_Mg",    None,    "relaciones",    False),
    (r"fierro|hierro|\(fe\)",          "Fe",      "ppm",   "micronutrientes", False),
    (r"cobre|\(cu\)",                  "Cu",      "ppm",   "micronutrientes", False),
    (r"zinc|\(zn\)",                   "Zn",      "ppm",   "micronutrientes", False),
    (r"manganeso|\(mn\)",              "Mn",      "ppm",   "micronutrientes", False),
    (r"boro\s*\(b\)|\bbor[oa]\b",     "B",       "ppm",   "micronutrientes", False),
]

NA_VALUES = {"", "none", "n/a", "|", "-", "ff", "=", "ee", "f"}


def render_page(pdf_path: str, page_num: int) -> Image.Image:
    from PIL import ImageEnhance
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        bitmap = pdf[page_num].render(scale=RENDER_SCALE)
        img = bitmap.to_pil()
    finally:
        pdf.close()
    return ImageEnhance.Contrast(img).enhance(1.5)


def ocr_words(image: Image.Image) -> list:
    data = pytesseract.image_to_data(
        image, lang=OCR_LANG, config=OCR_CONFIG,
        output_type=pytesseract.Output.DICT,
    )
    words = []
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        conf = int(data["conf"][i])
        if txt and conf > 20:
            words.append({
                "text": txt,
                "cx": data["left"][i] + data["width"][i] // 2,
                "cy": data["top"][i] + data["height"][i] // 2,
            })
    return words


def ocr_header_zone(pdf_path: str) -> str:
    """
    Three independent crops with different OCR configs:
    - Zone A (14%-30%): AGRICOLA, LOTE — psm 11, contrast 2.5x
    - Zone B (12%-42%): CULTIVO — psm 11, contrast 2.5x
    - Zone C (16%-26%): folio+date band at 5x with digit whitelist
    """
    from PIL import ImageEnhance
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        img4 = pdf[0].render(scale=4).to_pil()
        img5 = pdf[0].render(scale=5).to_pil()
    finally:
        pdf.close()

    def _ocr_contrast(img, y0_pct, y1_pct, contrast=2.5, config="--psm 11"):
        crop = img.crop((0, int(img.size[1] * y0_pct), img.size[0], int(img.size[1] * y1_pct)))
        enhanced = ImageEnhance.Contrast(crop.convert("L")).enhance(contrast)
        return pytesseract.image_to_string(enhanced, lang=OCR_LANG, config=config)

    zone_a = _ocr_contrast(img4, 0.14, 0.30)
    zone_b = _ocr_contrast(img4, 0.12, 0.42)
    zone_c = _ocr_contrast(
        img5, 0.16, 0.26, contrast=3.0,
        config='--psm 6 -c tessedit_char_whitelist=0123456789/,. ',
    )
    return zone_c + "\n" + zone_a + "\n" + zone_b


def _col_means(band_gray) -> list:
    bW, bH = band_gray.size
    pixels = list(band_gray.getdata())
    means = []
    for x in range(bW):
        col = [pixels[y * bW + x] for y in range(bH)]
        means.append(sum(col) / bH)
    return means


def _find_cell_xranges(means: list, min_cell_width_pct=0.04, win=2) -> list:
    """
    Detects gray cell segments by luminosity.
    win=2 preserves thin border lines between adjacent cells;
    win=7 eliminates noise for cells separated by white background.
    """
    bW = len(means)

    smoothed = []
    for i in range(bW):
        lo, hi = max(0, i - win), min(bW, i + win + 1)
        smoothed.append(sum(means[lo:hi]) / (hi - lo))

    DARK_THRESH  = 150
    GRAY_THRESH  = 238
    min_cell_px  = int(bW * min_cell_width_pct)

    def _is_cell(m):
        return DARK_THRESH < m < GRAY_THRESH

    cells   = []
    in_cell = _is_cell(smoothed[0])
    start   = 0

    for x in range(1, bW):
        now_cell = _is_cell(smoothed[x])
        if now_cell != in_cell:
            if in_cell and (x - start) >= min_cell_px:
                cells.append((start, x))
            start    = x
            in_cell  = now_cell

    if in_cell and (bW - start) >= min_cell_px:
        cells.append((start, bW))

    return cells


def _ocr_cell(cell_img) -> str:
    """
    OCRs a single cell. Tries multiple binarization thresholds and two PSM modes;
    returns the result with the most digit characters.
    """
    from PIL import ImageEnhance
    w, h = cell_img.size
    cell_img = cell_img.resize((w * 2, h * 2), resample=Image.LANCZOS)
    gray = ImageEnhance.Contrast(cell_img.convert("L")).enhance(3.0)

    best_txt, best_n = "", 0
    for thresh in (120, 140, 160, 180):
        binary = gray.point(lambda p, t=thresh: 255 if p > t else 0)
        for psm in ("--psm 7", "--psm 8"):
            cfg = f"{psm} -c tessedit_char_whitelist=0123456789/,"
            txt = pytesseract.image_to_string(binary, lang=OCR_LANG, config=cfg).strip()
            n   = len(re.sub(r"\D", "", txt))
            if n > best_n:
                best_n, best_txt = n, txt
    return best_txt


def ocr_folio_dates(pdf_path: str) -> dict:
    """
    Extracts folio and date fields by detecting cell boundaries via vertical
    contrast rather than fixed pixel offsets. Each cell is OCR'd individually
    with a digit whitelist for maximum accuracy.
    """
    SCALE = 6
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        img = pdf[0].render(scale=SCALE).to_pil()
    finally:
        pdf.close()

    W, H = img.size
    gray = img.convert("L")

    y_folio0 = int(H * 0.172)
    y_folio1 = int(H * 0.192)
    y_date0  = int(H * 0.193)
    y_date1  = int(H * 0.216)

    folio_band = gray.crop((0, y_folio0, W, y_folio1))
    date_band  = gray.crop((0, y_date0,  W, y_date1))

    
    folio_cells = _find_cell_xranges(_col_means(folio_band), win=2)
    date_cells  = _find_cell_xranges(_col_means(date_band),  win=7)

    PAD = 6

    def _ocr_row_cells(cells, band_gray, orig_img, y0, y1):
        results = []
        for x0, x1 in cells:
            cell = orig_img.crop((max(0, x0 - PAD), max(0, y0 - PAD),
                                  min(W, x1 + PAD), min(H, y1 + PAD)))
            txt  = _ocr_cell(cell)
            cx_pct = (x0 + x1) / 2 / W
            results.append((cx_pct, txt))
        return results

    folio_results = _ocr_row_cells(folio_cells, folio_band, img, y_folio0, y_folio1)
    date_results  = _ocr_row_cells(date_cells,  date_band,  img, y_date0,  y_date1)

    _DATE_PAT = re.compile(r"\d{2}/\d{2}/\d{2,4}")

    def _is_folio(txt):
        return len(re.sub(r"\D", "", txt)) >= 4 and not _DATE_PAT.search(txt)

    def _is_date(txt):
        return bool(_DATE_PAT.search(txt))

    folio_nums = sorted((x, t) for x, t in folio_results if _is_folio(t))
    folio_rec_raw = folio_nums[0][1] if folio_nums else None

    
    fecha_nums = sorted((x, t) for x, t in date_results if _is_folio(t))
    folio_ent_raw = fecha_nums[0][1] if fecha_nums else None

    fecha_dates = sorted((x, t) for x, t in date_results if _is_date(t))
    fecha_rec_raw = fecha_dates[0][1] if len(fecha_dates) >= 1 else None
    fecha_ent_raw = fecha_dates[1][1] if len(fecha_dates) >= 2 else fecha_rec_raw

    def _clean_folio(raw):
        if not raw:
            return None
        return re.sub(r"[^\d]", "", raw) or None

    def _fmt_fecha(raw):
        if not raw:
            return None
        m = re.search(r"(\d{2})[/](\d{2})[/](\d{2,4})", raw)
        if m:
            mo, d, y = m.group(1), m.group(2), m.group(3)
            return f"{d}/{mo}/{'20'+y if len(y)==2 else y}"
        return raw

    return {
        "folio_recepcion": _clean_folio(folio_rec_raw),
        "folio_entrega":   _clean_folio(folio_ent_raw),
        "fecha_recepcion": _fmt_fecha(fecha_rec_raw),
        "fecha_entrega":   _fmt_fecha(fecha_ent_raw),
    }


def group_into_rows(words: list, tolerance: int = 14) -> list:
    if not words:
        return []
    by_y = sorted(words, key=lambda w: w["cy"])
    rows, cur = [], [by_y[0]]
    for w in by_y[1:]:
        avg_y = sum(x["cy"] for x in cur) / len(cur)
        if abs(w["cy"] - avg_y) <= tolerance:
            cur.append(w)
        else:
            rows.append(sorted(cur, key=lambda x: x["cx"]))
            cur = [w]
    rows.append(sorted(cur, key=lambda x: x["cx"]))
    return rows


def row_to_cells(row_words: list, col_bounds: list, page_width: int) -> list:
    cells = [""] * (len(col_bounds) - 1)
    for w in row_words:
        pct = w["cx"] / page_width
        col = len(col_bounds) - 2
        for i in range(len(col_bounds) - 1):
            if col_bounds[i] <= pct < col_bounds[i + 1]:
                col = i
                break
        sep = " " if cells[col] else ""
        cells[col] = cells[col] + sep + w["text"]
    return cells


def page_full_text(rows: list) -> str:
    return " ".join(w["text"] for row in rows for w in row).lower()


def detect_page_type(rows: list) -> str:
    t = page_full_text(rows)
    if "extracto" in t and "saturado" in t:
        return "extracto_saturado"
    if "fertilidad" in t:
        return "fertilidad"
    return "unknown"


def parse_number(raw: str) -> Optional[float]:
    if not raw or raw.strip().lower() in NA_VALUES:
        return None
    
    cleaned = re.sub(r"(\d),(\d{3})\b", r"\1\2", raw)
    cleaned = re.sub(r"[^\d.\-]", "", cleaned.replace(",", "."))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


_NUM = r"\d+(?:\.\d+)?"


def parse_range(raw: str) -> tuple:
    raw = raw.strip()
    if not raw:
        return None, None
    raw = re.sub(r"(\d),(\d{3})\b", r"\1\2", raw)
    m = re.match(rf"[<＜]\s*({_NUM})", raw)
    if m:
        return None, float(m.group(1))
    m = re.search(rf"({_NUM})\s*[-–]\s*({_NUM})", raw)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.match(rf"({_NUM})\s+({_NUM})\s*$", raw)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def get_status(v: Optional[float], rmin: Optional[float], rmax: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    if rmin is not None and v < rmin:
        return "bajo"
    if rmax is not None and v > rmax:
        return "alto"
    if rmin is not None or rmax is not None:
        return "ok"
    return None


def match_fert(label: str):
    lc = label.lower()
    for pattern, simbolo, unidad, seccion in PARAMS_FERT:
        if re.search(pattern, lc):
            return simbolo, unidad, seccion
    return None, None, None


def match_extr(label: str):
    lc = label.lower()
    for pattern, simbolo, unidad, seccion, dual in PARAMS_EXTR:
        if re.search(pattern, lc):
            return simbolo, unidad, seccion, dual
    return None, None, None, False


def build_medicion(nombre, simbolo, unidad, valor, rmin, rmax, seccion,
                   valor_txt=None, **extra) -> dict:
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


def extract_header_text(rows: list) -> str:
    return " ".join(w["text"] for row in rows for w in row)


def parse_folio_info(text: str) -> dict:
    """
    Parses OCR output from the header zone (psm 11 produces irregular lines).
    Handles OCR variants like '(_acrico.a]4570 AGRICOLA LA CORONILA [LoTE [CAMPO NUEVO'.
    """
    def find(pat):
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else None

    agricola = find(r"AGRICOLA[\s|]+(\d+\s+.+?)(?:\s*[|\[\]]+\s*(?:LOTE|$)|\s*$)")
    lote = find(r"LOTE\s*[|\[\]]*\s*([A-Z][A-Z0-9 ]+?)(?:\s*[|\[\]]|\s*$)")
    cultivo = find(r"(?:C?ULTIVO|ULTI[A-Z]{1,3})\s*[|\[\]]+\s*([A-Z][\w. ]+?)(?:\s*[|\[\]]|\s*TIPO|\s*$)")

    def _fmt_fecha(raw: str) -> Optional[str]:
        """MM/DD/YY or MM/DD/YYYY → DD/MM/YYYY"""
        parts = raw.split("/")
        if len(parts) != 3:
            return raw
        m, d, y = parts
        if len(y) == 2:
            y = "20" + y
        return f"{d}/{m}/{y}"

    fechas_raw = re.findall(r"\b(\d{2}/\d{2}/\d{2,4})\b", text)
    fecha_rec = _fmt_fecha(fechas_raw[0]) if len(fechas_raw) > 0 else None
    fecha_ent = _fmt_fecha(fechas_raw[1]) if len(fechas_raw) > 1 else None

    
    folios_raw = re.findall(r"\b(\d{1,3}[,.]?\d{3}|\d{4,6})\b", text)
    folios = [re.sub(r"[,.]", "", f) for f in folios_raw
              if "667" not in f and "761" not in f]
    folio_rec = folios[0] if len(folios) > 0 else None
    folio_ent = folios[1] if len(folios) > 1 else None

    return {
        "laboratorio":     "AGROANALÍTICA Consultoría Agrícola",
        "agricola":        agricola,
        "lote":            lote,
        "cultivo":         cultivo,
        "folio_recepcion": folio_rec,
        "folio_entrega":   folio_ent,
        "fecha_recepcion": fecha_rec,
        "fecha_entrega":   fecha_ent,
    }


_SAT_BASES_ORDER = ["na", "k", "ca", "mg"]


def _apply_ref(meds_list: list, ref_str: str) -> None:
    """Backfills rmin/rmax/status on measurements that have no range yet."""
    rmin, rmax = parse_range(ref_str)
    if rmin is None and rmax is None:
        return
    for med in meds_list:
        if med.get("rango_min") is None and med.get("rango_max") is None:
            med["rango_min"] = rmin
            med["rango_max"] = rmax
            med["status"]    = get_status(med["valor"], rmin, rmax)


def parse_fertilidad_page(rows: list, page_width: int) -> tuple:
    """Returns (lab_ids[4], muestra_names[4], mediciones_per_muestra[4])"""
    lab_ids  = [None, None, None, None]
    m_names  = ["M-1", "M-2", "M-3", "M-4"]
    meds     = [[] for _ in range(4)]
    in_sat_bases  = False
    sat_bases_idx = 0
    seen_per_m    = [{} for _ in range(4)]
    last_param    = None
    last_added_meds: list = []

    for row_words in rows:
        cells = row_to_cells(row_words, COLS_FERT, page_width)
        label = cells[0].strip()
        vals  = cells[1:5]
        ref   = cells[5] if len(cells) > 5 else ""

        label_lc = label.lower()

        if re.search(r"reg.*lab|de lab", label_lc):
            for i, v in enumerate(vals):
                v_clean = re.sub(r"[^\d]", "", v)
                if v_clean:
                    lab_ids[i] = v_clean
            continue

        if re.search(r"^muestra", label_lc):
            for i, v in enumerate(vals):
                vt = v.strip()
                if vt:
                    m_names[i] = vt
            continue

        if re.search(r"saturacion.*bases|sat.*bases", label_lc):
            in_sat_bases  = True
            sat_bases_idx = 0
            continue

        if re.search(r"determinac|datos\s+expresados|nivel\s+de|niveles\s+de|"
                     r"folio|fecha|recepcion|entrega|solicitante|lote|cultivo|"
                     r"tipo\s+de|agricola|analisis\s+de|muestra$|ppm|meq",
                     label_lc):
            continue

        if not label:
            has_vals = any(v.strip() for v in vals)
            has_ref  = bool(ref.strip())
            if not has_vals and not has_ref:
                continue

            if has_vals:
                if in_sat_bases and sat_bases_idx < len(_SAT_BASES_ORDER):
                    key = _SAT_BASES_ORDER[sat_bases_idx]
                    simbolo, unidad, seccion = SAT_BASES[key]
                    newly: list = []
                    for i, v in enumerate(vals):
                        valor = parse_number(v)
                        if valor is not None and simbolo not in seen_per_m[i]:
                            med = build_medicion(key, simbolo, unidad, valor, None, None, seccion)
                            meds[i].append(med)
                            seen_per_m[i][simbolo] = True
                            newly.append(med)
                    last_added_meds = newly
                    sat_bases_idx += 1
                elif last_param is not None:
                    simbolo, lbl, unidad, seccion, p_rmin, p_rmax = last_param
                    for i, v in enumerate(vals):
                        v = v.strip()
                        valor = parse_number(v)
                        valor_txt = v if valor is None and v and v.lower() not in NA_VALUES else None
                        if (valor is not None or valor_txt) and simbolo not in seen_per_m[i]:
                            med = build_medicion(lbl, simbolo, unidad, valor,
                                                 p_rmin, p_rmax, seccion, valor_txt=valor_txt)
                            meds[i].append(med)
                            seen_per_m[i][simbolo] = True
                            last_added_meds.append(med)

            if has_ref:
                _apply_ref(last_added_meds, ref)
            continue

        rmin_row, rmax_row = parse_range(ref)

        if in_sat_bases:
            key = label_lc.strip()
            if key in SAT_BASES:
                simbolo, unidad, seccion = SAT_BASES[key]
                newly = []
                for i, v in enumerate(vals):
                    valor = parse_number(v)
                    if valor is not None and simbolo not in seen_per_m[i]:
                        med = build_medicion(label, simbolo, unidad, valor,
                                             rmin_row, rmax_row, seccion)
                        meds[i].append(med)
                        seen_per_m[i][simbolo] = True
                        newly.append(med)
                last_added_meds = newly
                if ref.strip():
                    _apply_ref(last_added_meds, ref)
                try:
                    sat_bases_idx = _SAT_BASES_ORDER.index(key) + 1
                except ValueError:
                    sat_bases_idx += 1
            continue

        simbolo, unidad, seccion = match_fert(label)
        if not simbolo:
            last_param = None
            continue

        last_param = (simbolo, label, unidad, seccion, rmin_row, rmax_row)
        newly = []
        for i, v in enumerate(vals):
            v = v.strip()
            valor = parse_number(v)
            valor_txt = v if valor is None and v and v.lower() not in NA_VALUES else None
            if (valor is not None or valor_txt) and simbolo not in seen_per_m[i]:
                med = build_medicion(label, simbolo, unidad, valor, rmin_row, rmax_row, seccion,
                                     valor_txt=valor_txt)
                meds[i].append(med)
                seen_per_m[i][simbolo] = True
                newly.append(med)
        last_added_meds = newly
        if ref.strip():
            _apply_ref(last_added_meds, ref)

    return lab_ids, m_names, meds


def parse_extracto_page(rows: list, page_width: int, muestra_offset: int) -> tuple:
    """Returns (lab_ids[2], muestra_names[2], mediciones_per_muestra[2])"""
    lab_ids = [None, None]
    m_names = [f"M-{muestra_offset+1}", f"M-{muestra_offset+2}"]
    meds    = [[], []]
    seen    = [{}, {}]

    for row_words in rows:
        cells  = row_to_cells(row_words, COLS_EXTR, page_width)
        label  = cells[0].strip()
        label_lc = label.lower()

        if re.search(r"reg.*lab|de lab", label_lc):
            for i, ci in enumerate([1, 3]):
                v_clean = re.sub(r"[^\d]", "", cells[ci] if ci < len(cells) else "")
                if v_clean:
                    lab_ids[i] = v_clean
            continue

        if re.search(r"^muestra", label_lc):
            for i, ci in enumerate([1, 3]):
                vt = (cells[ci] if ci < len(cells) else "").strip()
                if vt:
                    m_names[i] = vt
            continue

        if re.search(r"determinac|datos\s+expresados|nivel|folio|fecha|"
                     r"recepcion|entrega|solicitante|lote|cultivo|tipo\s+de|"
                     r"agricola|analisis\s+de|^ppm$|^meq",
                     label_lc):
            continue

        ref  = cells[5] if len(cells) > 5 else ""
        rmin, rmax = parse_range(ref)

        simbolo, unidad, seccion, dual = match_extr(label)
        if not simbolo:
            continue

       
        for mi, (ci_ppm, ci_meq) in enumerate([(1, 2), (3, 4)]):
            ppm_raw = cells[ci_ppm].strip() if ci_ppm < len(cells) else ""
            meq_raw = cells[ci_meq].strip() if ci_meq < len(cells) else ""

            if simbolo in seen[mi]:
                continue

            if dual:
                v_ppm = parse_number(ppm_raw)
                v_meq = parse_number(meq_raw)
                if v_ppm is None and v_meq is None:
                    continue
                med = build_medicion(label, simbolo, unidad, v_ppm, rmin, rmax, seccion)
                if v_ppm is not None:
                    med["valor_ppm"] = v_ppm
                if v_meq is not None:
                    med["valor_meq"] = v_meq
                    med["unidad_meq"] = "meq/l"
                meds[mi].append(med)
                seen[mi][simbolo] = True

            else:
                raw = ppm_raw if ppm_raw and ppm_raw.lower() not in NA_VALUES else meq_raw
                valor = parse_number(raw)
                if valor is None:
                    continue
                meds[mi].append(build_medicion(label, simbolo, unidad, valor, rmin, rmax, seccion))
                seen[mi][simbolo] = True

    return lab_ids, m_names, meds


def parse_agroanalitica(pdf_path: str) -> dict:
    pdf     = pdfium.PdfDocument(pdf_path)
    n_pages = len(pdf)
    pdf.close()

    all_muestras: list = []
    geo_counter = 1

    hdr_ocr = ocr_header_zone(pdf_path)
    header  = parse_folio_info(hdr_ocr)
    folio_data = ocr_folio_dates(pdf_path)
    header.update({k: v for k, v in folio_data.items() if v is not None})
    header["tipo_analisis"] = "suelo"

    for pi in range(n_pages):
        image   = render_page(pdf_path, pi)
        W       = image.size[0]
        words   = ocr_words(image)
        rows    = group_into_rows(words)
        ptype   = detect_page_type(rows)

        if ptype == "fertilidad":
            lab_ids, m_names, meds_list = parse_fertilidad_page(rows, W)
            for i in range(4):
                all_muestras.append({
                    "geo_id":           f"M{geo_counter}",
                    "geo_id_confirmed": False,
                    "lab_id":           lab_ids[i],
                    "nombre":           m_names[i],
                    "tipo_analisis":    "suelo",
                    "seccion_analisis": "fertilidad",
                    "profundidad_raw":  None,
                    "profundidad_cm":   None,
                    "mediciones":       meds_list[i],
                })
                geo_counter += 1

        elif ptype == "extracto_saturado":
           
            offset = 0 if pi == 1 else 2
            lab_ids, m_names, meds_list = parse_extracto_page(rows, W, offset)
            for i in range(2):
                all_muestras.append({
                    "geo_id":           f"M{geo_counter}",
                    "geo_id_confirmed": False,
                    "lab_id":           lab_ids[i],
                    "nombre":           m_names[i],
                    "tipo_analisis":    "suelo",
                    "seccion_analisis": "extracto_saturado",
                    "profundidad_raw":  None,
                    "profundidad_cm":   None,
                    "mediciones":       meds_list[i],
                })
                geo_counter += 1

    return {
        "informe":       header,
        "muestras":      all_muestras,
        "total_muestras": len(all_muestras),
    }