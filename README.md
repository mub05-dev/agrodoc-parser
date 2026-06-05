# agrodoc-parser

![CI](https://github.com/mub05-dev/agrodoc-parser/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Modular microservice for parsing agricultural laboratory analysis documents (PDF and Excel). Automatically detects the issuing laboratory and returns structured, normalized JSON — no configuration required.

Built with FastAPI. Designed to be integrated into any agricultural management system and extended to support new laboratories.

---

## Supported laboratories

| Laboratory | Country | Format | Analysis types |
|---|---|---|---|
| [Agrolab](https://www.agrolab.cl) | Chile | PDF | Soil, foliar |
| [Ceres](https://www.labceres.com) | Guatemala | PDF | Soil, foliar |
| [Las Garzas](https://lasgarzas.com.mx) | Mexico | PDF | Soil |
| [Fertilab](https://fertilab.net) | Mexico | PDF | Soil |
| [Phytomonitor](https://phytomonitor.com.mx) | Mexico | PDF | Soil, foliar |
| [Agrilab](https://agrilab.com.co) | Colombia | PDF | Soil |
| [Agroanalitica](https://agroanalitica.com) | Venezuela | PDF | Soil |
| [Fertilizantes Tepeyac](https://ftepeyac.com) | Mexico | PDF | Soil |
| [Motzz / Arizona Agricultural Solutions](https://motzz.com) | USA | PDF | Soil |
| [Fertilizantes Tepeyac (plant)](https://ftepeyac.com) | Mexico | Excel | Plant |

> Missing your laboratory? [Add it in minutes](#adding-a-new-laboratory) and open a PR.

---

## Quick start

### Local

```bash
git clone https://github.com/mub05-dev/agrodoc-parser.git
cd agrodoc-parser
pip install -r requirements.txt
uvicorn main:app --reload
```

The service runs at `http://localhost:8000`.
Interactive API docs at `http://localhost:8000/docs`.

### Docker

```bash
docker build -t agrodoc-parser .
docker run -p 8000:8000 agrodoc-parser
```

With a custom Tesseract path (Windows host):

```bash
docker run -p 8000:8000 -e TESSERACT_CMD=/usr/bin/tesseract agrodoc-parser
```

---

## API

### `POST /parse` — single PDF

```bash
curl -X POST http://localhost:8000/parse \
  -F "file=@your_analysis.pdf"
```

### `POST /parse-excel` — single Excel

```bash
curl -X POST http://localhost:8000/parse-excel \
  -F "file=@your_analysis.xlsx"
```

### `POST /parse-batch` — multiple PDFs (same laboratory)

All files must belong to the same laboratory. Samples are merged, sorted, and re-indexed across documents.

```bash
curl -X POST http://localhost:8000/parse-batch \
  -F "files=@report_1.pdf" \
  -F "files=@report_2.pdf" \
  -F "files=@report_3.pdf"
```

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status": "ok", "service": "parser-service"}
```

---

## Response format

All endpoints return the same structure:

```json
{
  "report": {
    "laboratory": "Agrolab",
    "analysis_type": "suelo",
    "numero_orden": "211.117",
    "productor": "Bloom Group",
    "predio": "Huiño Huiño",
    "fecha_muestreo": "2026-04-13",
    "fecha_informe": "2026-05-04"
  },
  "samples": [
    {
      "geo_id": "M1",
      "lab_id": "308677",
      "measurements": [
        {
          "symbol": "N",
          "name": "Nitrógeno",
          "unit": "mg/kg",
          "value": 48.0,
          "status": "ok",
          "section": "macronutrientes"
        }
      ]
    }
  ],
  "total_samples": 10,
  "meta": {
    "laboratory_key": "agrolab",
    "parser": "deterministic",
    "detected_as": "agrolab"
  }
}
```

| Field | Description |
|---|---|
| `report` | Document-level metadata: laboratory, dates, producer, location |
| `samples` | List of samples, each with a `geo_id` and its `measurements` |
| `geo_id` | Normalized sample identifier (`M1`, `M2`, ...) |
| `measurements` | Parsed parameters with value, unit, ranges, and status |
| `status` | Nutritional status: `"bajo"`, `"ok"`, `"alto"`, or `null` |
| `meta.laboratory_key` | Detected laboratory slug |
| `meta.parser` | Detection method: `"deterministic"` or `"ocr"` |

---

## Adding a new laboratory

Each laboratory lives in its own folder under `parsers/`. The project includes a [cookiecutter](https://cookiecutter.readthedocs.io) template that scaffolds everything automatically.

### Using the template (recommended)

```bash
pip install cookiecutter
cookiecutter cookiecutter-lab-parser/
```

Cookiecutter will prompt for:

| Variable | Example |
|---|---|
| `lab_slug` | `nuevo_lab` |
| `lab_class_name` | `NuevoLabParser` |
| `lab_display_name` | `Nuevo Lab` |
| `detect_string` | `NUEVO LAB` |
| `file_type` | `pdf` or `excel` |
| `priority` | `5` |

It then creates:
- `parsers/nuevo_lab/__init__.py`
- `parsers/nuevo_lab/parser.py`
- `parsers/nuevo_lab/_helpers.py` — implement your parse logic here
- `tests/test_nuevo_lab_parser.py`
- `tests/fixtures/nuevo_lab/` — drop a sample PDF here

### Remaining steps after scaffold

**1. Implement parse logic** in `parsers/nuevo_lab/_helpers.py`

The function must return a dict matching the schema:

```python
def parse_nuevo_lab(file_path: str) -> dict:
    return {
        "informe": {
            "laboratorio": "Nuevo Lab",
            "tipo_analisis": "suelo",
        },
        "muestras": [
            {
                "geo_id": "M1",
                "lab_id": "001",
                "mediciones": [
                    {"simbolo": "N", "nombre": "Nitrógeno", "unidad": "mg/kg", "valor": 12.5}
                ]
            }
        ],
        "total_muestras": 1,
    }
```

**2. Register the parser** in `parsers/registry.py`:

```python
from parsers.nuevo_lab.parser import NuevoLabParser

REGISTRY: list[BaseLabParser] = sorted([
    ...
    NuevoLabParser(),
], key=lambda p: p.priority, reverse=True)
```

**3. Add a sample file** to `tests/fixtures/nuevo_lab/sample.pdf`

**4. Run the tests:**

```bash
pytest tests/test_nuevo_lab_parser.py -v
```

> **Note on `priority`:** parsers are evaluated in descending order. Use higher values (10+) for specific detection strings and lower values (1–5) for generic strings that could appear in other labs' documents.

---

## Project structure

```
agrodoc-parser/
├── main.py                        — FastAPI app and endpoints
├── router.py                      — Detection and routing logic
├── schema.py                      — Pydantic models
├── requirements.txt
├── Dockerfile
├── parsers/
│   ├── base.py                    — BaseLabParser abstract class
│   ├── registry.py                — All active parsers, sorted by priority
│   ├── utils.py                   — Shared PDF utilities
│   └── {lab}/
│       ├── parser.py              — Parser class
│       └── _helpers.py            — Parsing logic
├── tests/
│   ├── conftest.py                — Shared fixtures
│   ├── fixtures/{lab}/sample.pdf  — Real lab documents
│   └── test_*.py
└── cookiecutter-lab-parser/       — Template for new parsers
```

---

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run with coverage
pytest --cov=. --cov-report=term-missing
```

---

## Requirements

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — required for image-based PDFs

**Ubuntu / Debian:**
```bash
sudo apt install tesseract-ocr ghostscript
```

**Windows:** download the installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) and set the environment variable:
```
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

**macOS:**
```bash
brew install tesseract ghostscript
```

---

## Contributing

Contributions are welcome — especially new laboratory parsers.

1. Fork the repository
2. Create a branch: `git checkout -b feature/new-lab-name`
3. Scaffold the parser: `cookiecutter cookiecutter-lab-parser/`
4. Implement and test
5. Open a pull request

Please ensure `pytest` passes before submitting.

---

## License

MIT
