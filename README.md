# agrodoc-parser
Modular PDF and Excel parser for agricultural laboratory analysis documents. Auto-detects laboratory and returns structured JSON.
# agrodoc-parser

Modular PDF and Excel parser for agricultural laboratory analysis documents. Automatically detects the laboratory from the document and returns structured JSON — no configuration required.

Built as a FastAPI microservice, designed to be integrated into any agricultural management system.

---

## Quick start

```bash
git clone https://github.com/mub05-dev/agrodoc-parser.git
cd agrodoc-parser
pip install -r requirements.txt
uvicorn main:app --reload
```

The service will be available at `http://localhost:8000`.  
Interactive API docs at `http://localhost:8000/docs`.

---

## API

### `POST /parse`

Receives a PDF and returns normalized JSON.

```bash
curl -X POST http://localhost:8000/parse \
  -F "file=@your_analysis.pdf"
```

### `POST /parse-excel`

Receives an Excel `.xlsx` file and returns normalized JSON.

```bash
curl -X POST http://localhost:8000/parse-excel \
  -F "file=@your_analysis.xlsx"
```

### `POST /parse-batch`

Receives multiple PDFs from the **same laboratory** and returns a single merged response with all samples sorted and indexed.

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

## Output format

All endpoints return the same structure:

```json
{
  "report": {
    "laboratory": "Agrolab",
    "analysis_type": "suelo",
    "numero_orden": "211.117",
    "productor": "Bloom Group",
    "predio": "Huiño Huiño",
    "provincia": "Osorno",
    "comuna": "San Pablo",
    "fecha_muestreo": "2026-04-13",
    "fecha_analisis": "2026-04-16",
    "fecha_informe": "2026-05-04"
  },
  "samples": [
    {
      "geo_id": "M1",
      "geo_id_confirmed": false,
      "lab_id": "308677",
      "name": "308677",
      "measurements": [
        {
          "symbol": "Arena",
          "name": "Arena (2,00 - 0,05 mm)",
          "unit": "%",
          "value": 48.0,
          "value_text": null,
          "range_min": null,
          "range_max": null,
          "status": null,
          "qualitative": null,
          "section": "textura"
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

### Key fields

| Field | Description |
|---|---|
| `report` | Document-level metadata: laboratory, dates, producer, location |
| `samples` | List of samples, each with a `geo_id` and its `measurements` |
| `geo_id` | Internal sample identifier (`M1`, `M2`, ...) |
| `measurements` | Parsed parameters with value, unit, ranges, and status |
| `status` | Nutritional status: `"bajo"`, `"ok"`, `"alto"`, or `null` |
| `meta.laboratory_key` | Detected laboratory identifier |
| `meta.parser` | Detection method: `"deterministic"` or `"ocr"` |

---

## Project structure

```
agrodoc-parser/
  main.py          — FastAPI app and endpoints
  router.py        — Detection and routing logic
  schema.py        — Pydantic models (ParseResult, Sample, Measurement, etc.)
  requirements.txt
  Dockerfile
  parsers/
    base.py        — BaseLabParser abstract class
    registry.py    — Ordered list of all active parsers
    utils.py       — Shared PDF utilities (text extraction, page count)
    agrolab/
      parser.py    — AgrolabParser(BaseLabParser)
      _helpers.py  — Parsing logic
    motzz/
    ceres/
    ...            — One folder per laboratory
```

---

## Adding a new laboratory

Each laboratory lives in its own folder under `parsers/`. Adding support for a new lab takes three steps:

**1. Create the parser folder**

```
parsers/
  my_lab/
    __init__.py
    parser.py
    _helpers.py
```

**2. Implement `BaseLabParser`**

```python
# parsers/my_lab/parser.py
from parsers.base import BaseLabParser
from parsers.my_lab._helpers import parse_my_lab
from schema import ParseResult

class MyLabParser(BaseLabParser):

    @property
    def laboratory_key(self) -> str:
        return "my_lab"

    @property
    def file_type(self) -> str:
        return "pdf"  # or "excel"

    @property
    def priority(self) -> int:
        # Use higher values (10+) for specific detection strings
        # Use lower values (0-5) for generic strings with collision risk
        return 10

    def detect(self, text: str) -> bool:
        # text is already uppercased by the router
        return "MY LABORATORY NAME" in text

    def parse(self, file_path: str) -> ParseResult:
        raw = parse_my_lab(file_path)
        return ParseResult.model_validate(raw)
```

**3. Register it**

Add one import and one instance to `parsers/registry.py`:

```python
from parsers.my_lab.parser import MyLabParser

REGISTRY: list[BaseLabParser] = sorted([
    ...
    MyLabParser(),  # add here
], key=lambda p: p.priority, reverse=True)
```

That's it. The router picks it up automatically.

> **Note on `priority`:** parsers are evaluated in descending priority order. If your detection string is short or could appear in other labs' documents, assign a lower priority so more specific parsers are checked first.

---

## Docker

```bash
docker build -t agrodoc-parser .
docker run -p 8000:8000 agrodoc-parser
```

---

## Requirements

- Python 3.10+
- [camelot-py](https://camelot-py.readthedocs.io/) — table extraction from PDFs
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — required for image-based PDFs (optional)

Install Tesseract on Ubuntu:
```bash
sudo apt install tesseract-ocr
```

On Windows, download the installer from the [official repository](https://github.com/UB-Mannheim/tesseract/wiki) and set the `TESSERACT_CMD` environment variable to the executable path.

---

## License

MIT