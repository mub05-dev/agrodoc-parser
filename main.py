"""
main.py
-----------------
Agricultural lab analysis parser microservice.
Endpoints:
-POST /parse         → receives a PDF, returns normalized JSON
-POST /parse-excel   → receives an Excel (.xlsx), returns normalized JSON
-GET  /health        → healthcheck for docker-compose and CI/CD
"""

import os
import tempfile
import logging

from typing             import List
from fastapi            import FastAPI, File, UploadFile, HTTPException
from fastapi.responses  import JSONResponse
from router             import route_parser, route_excel_parser, merge_batch_results
from schema             import ParseResponse, BatchResponse


logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title       = "Lab Analysis — Parser Service",
    description = "Microservice for parsing agricultural lab PDF reports.",
    version     = "1.0.0",
)


MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE    = MAX_FILE_SIZE_MB * 1024 * 1024

XLSX_MIME_TYPES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
)


@app.get("/health", tags=["System"])
def health():
    """Healthcheck. Returns 200 if the service is running."""
    return {"status": "ok", "service": "parser-service"}


@app.post("/parse", response_model=ParseResponse, tags=["Parser"])
async def parse_pdf(file: UploadFile = File(...)):
    """
    Receives a lab analysis PDF and returns normalized JSON
    with report, samples, and measurements.

    - Automatically detects the laboratory (Agrolab, Motzz, etc.)
    - Uses deterministic parser for known labs
    """

    if not file or not file.filename:
        raise HTTPException(
            status_code = 400,
            detail      = "No file provided. Upload a PDF using the 'file' field."
        )

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code = 400,
            detail      = f"File type not allowed: {file.content_type}. Only PDFs are accepted."
        )

    content = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code = 400,
            detail      = "File is empty."
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code = 413,
            detail      = f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB."
        )

    if not content.startswith(b"%PDF"):
        raise HTTPException(
            status_code = 400,
            detail      = "File is not a valid PDF."
        )

    safe_filename = os.path.basename(file.filename or "unknown")
    logger.info(f"PDF received: {safe_filename} ({len(content) / 1024:.1f} KB)")


    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = route_parser(tmp_path)

        logger.info(
            f"Parse complete: lab={result.meta.laboratory_key} "
            f"samples={result.total_samples}"
        )

        return result

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error parsing {safe_filename}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code = 422,
            detail      = {
                "error":    "Failed to process PDF.",
                "message":  str(e),
                "file":     safe_filename,
            }
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


MAX_BATCH_FILES = 20


@app.post("/parse-batch", response_model=BatchResponse, tags=["Parser"])
async def parse_batch(files: List[UploadFile] = File(...)):
    """
    Receives multiple PDFs from the same laboratory and returns a single normalized JSON
    with all samples merged and sorted by sample number.

    - All files must belong to the same laboratory
    - Samples are ordered numerically by lab_id or sample name across documents
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum allowed: {MAX_BATCH_FILES}."
        )

    tmp_paths: List[str] = []
    contents:  List[bytes] = []

    for file in files:
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="One or more files are missing a filename.")

        if file.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(
                status_code=400,
                detail=f"'{file.filename}': only PDFs are accepted (got {file.content_type})."
            )

        content = await file.read()

        if len(content) == 0:
            raise HTTPException(status_code=400, detail=f"'{file.filename}' is empty.")

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"'{file.filename}' exceeds maximum size of {MAX_FILE_SIZE_MB} MB."
            )

        if not content.startswith(b"%PDF"):
            raise HTTPException(
                status_code=400,
                detail=f"'{file.filename}' is not a valid PDF."
            )

        contents.append(content)

    try:
        for i, (file, content) in enumerate(zip(files, contents)):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_paths.append(tmp.name)

        results = []
        lab_keys: List[str] = []

        for file, tmp_path in zip(files, tmp_paths):
            safe_name = os.path.basename(file.filename or "unknown")
            logger.info(f"Batch — parsing: {safe_name}")
            result = route_parser(tmp_path)
            results.append(result)
            lab_keys.append(result.meta.laboratory_key)

        unique_labs = set(lab_keys)
        if len(unique_labs) > 1:
            detail = {lab: [os.path.basename(f.filename or "") for f, k in zip(files, lab_keys) if k == lab]
                      for lab in unique_labs}
            raise HTTPException(
                status_code=422,
                detail={
                    "error":       "Mixed laboratories detected. All files must be from the same lab.",
                    "labs_found":  detail,
                }
            )

        merged = merge_batch_results(results)
        logger.info(
            f"Batch complete: lab={merged.meta.laboratory_key} "
            f"files={len(files)} samples={merged.total_samples}"
        )
        return merged

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error in parse-batch: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=422,
            detail={"error": "Failed to process batch.", "message": str(e)}
        )

    finally:
        for p in tmp_paths:
            if os.path.exists(p):
                os.unlink(p)


@app.post("/parse-excel", response_model=ParseResponse, tags=["Parser"])
async def parse_excel(file: UploadFile = File(...)):
    """
    Receives a lab analysis Excel (.xlsx) and returns normalized JSON
    with report, samples, and measurements.

    - Automatically detects the laboratory from sheet structure
    - Currently supported: Fertilizantes Tepeyac (plant analysis)
    """

    if not file or not file.filename:
        raise HTTPException(
            status_code = 400,
            detail      = "No file provided. Upload an Excel file using the 'file' field."
        )

    if file.content_type not in XLSX_MIME_TYPES:
        raise HTTPException(
            status_code = 400,
            detail      = f"File type not allowed: {file.content_type}. Only .xlsx files are accepted."
        )

    content = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code = 400,
            detail      = "File is empty."
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code = 413,
            detail      = f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB."
        )

    if not content.startswith(b"PK\x03\x04"):
        raise HTTPException(
            status_code = 400,
            detail      = "File is not a valid .xlsx file."
        )

    safe_filename = os.path.basename(file.filename or "unknown")
    logger.info(f"Excel received: {safe_filename} ({len(content) / 1024:.1f} KB)")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = route_excel_parser(tmp_path)

        logger.info(
            f"Parse complete: lab={result.meta.laboratory_key} "
            f"samples={result.total_samples}"
        )

        return result

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error parsing {safe_filename}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code = 422,
            detail      = {
                "error":   "Failed to process Excel file.",
                "message": str(e),
                "file":    safe_filename,
            }
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)