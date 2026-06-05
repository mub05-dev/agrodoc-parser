import pytest


# ─── /health ─────────────────────────────────────────────────────────────────

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "parser-service"}


# ─── /parse — validaciones ────────────────────────────────────────────────────

def test_parse_no_file(client):
    r = client.post("/parse")
    assert r.status_code == 422  # FastAPI validation error (missing required field)


def test_parse_wrong_content_type(client):
    r = client.post("/parse", files={"file": ("doc.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_parse_empty_file(client):
    r = client.post("/parse", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert r.status_code == 400


def test_parse_invalid_pdf_magic(client):
    r = client.post("/parse", files={"file": ("bad.pdf", b"not a pdf content", "application/pdf")})
    assert r.status_code == 400


def test_parse_file_too_large(client):
    big = b"%PDF" + b"x" * (21 * 1024 * 1024)
    r = client.post("/parse", files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 413


# ─── /parse — PDF real ────────────────────────────────────────────────────────

def test_parse_valid_pdf_status(client, pdf_agrolab):
    with open(pdf_agrolab, "rb") as f:
        r = client.post("/parse", files={"file": ("sample.pdf", f, "application/pdf")})
    assert r.status_code == 200


def test_parse_valid_pdf_response_structure(client, pdf_agrolab):
    with open(pdf_agrolab, "rb") as f:
        data = client.post("/parse", files={"file": ("sample.pdf", f, "application/pdf")}).json()
    assert "report" in data
    assert "samples" in data
    assert "total_samples" in data
    assert "meta" in data


def test_parse_valid_pdf_meta_fields(client, pdf_agrolab):
    with open(pdf_agrolab, "rb") as f:
        data = client.post("/parse", files={"file": ("sample.pdf", f, "application/pdf")}).json()
    assert data["meta"]["laboratory_key"] == "agrolab"
    assert data["meta"]["parser"] in ("deterministic", "ocr")


def test_parse_valid_pdf_has_samples(client, pdf_agrolab):
    with open(pdf_agrolab, "rb") as f:
        data = client.post("/parse", files={"file": ("sample.pdf", f, "application/pdf")}).json()
    assert len(data["samples"]) > 0
    assert data["total_samples"] == len(data["samples"])


# ─── /parse-batch — validaciones ─────────────────────────────────────────────

def test_parse_batch_no_files(client):
    r = client.post("/parse-batch")
    assert r.status_code == 422


def test_parse_batch_empty_file(client):
    r = client.post("/parse-batch", files=[("files", ("empty.pdf", b"", "application/pdf"))])
    assert r.status_code == 400


def test_parse_batch_invalid_pdf_magic(client):
    r = client.post("/parse-batch", files=[("files", ("bad.pdf", b"not a pdf", "application/pdf"))])
    assert r.status_code == 400


def test_parse_batch_valid_two_files(client, pdf_agrolab):
    with open(pdf_agrolab, "rb") as f1, open(pdf_agrolab, "rb") as f2:
        r = client.post("/parse-batch", files=[
            ("files", ("a.pdf", f1, "application/pdf")),
            ("files", ("b.pdf", f2, "application/pdf")),
        ])
    assert r.status_code == 200


def test_parse_batch_response_structure(client, pdf_agrolab):
    with open(pdf_agrolab, "rb") as f:
        data = client.post("/parse-batch", files=[("files", ("a.pdf", f, "application/pdf"))]).json()
    assert "laboratory" in data
    assert "analyses" in data
    assert "total_samples" in data
    assert "meta" in data


def test_parse_batch_samples_reindexed(client, pdf_agrolab):
    with open(pdf_agrolab, "rb") as f1, open(pdf_agrolab, "rb") as f2:
        data = client.post("/parse-batch", files=[
            ("files", ("a.pdf", f1, "application/pdf")),
            ("files", ("b.pdf", f2, "application/pdf")),
        ]).json()
    samples = data["analyses"][0]["samples"]
    geo_ids = [s["geo_id"] for s in samples]
    assert all(g.startswith("M") for g in geo_ids)
    assert geo_ids == sorted(geo_ids, key=lambda x: int(x[1:]))


# ─── /parse-excel — validaciones ─────────────────────────────────────────────

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_parse_excel_no_file(client):
    r = client.post("/parse-excel")
    assert r.status_code == 422


def test_parse_excel_wrong_content_type(client):
    r = client.post("/parse-excel", files={"file": ("doc.pdf", b"content", "application/pdf")})
    assert r.status_code == 400


def test_parse_excel_empty_file(client):
    r = client.post("/parse-excel", files={"file": ("empty.xlsx", b"", XLSX_MIME)})
    assert r.status_code == 400


def test_parse_excel_invalid_magic(client):
    r = client.post("/parse-excel", files={"file": ("bad.xlsx", b"not a zip", XLSX_MIME)})
    assert r.status_code == 400


# ─── /parse-excel — Excel real ───────────────────────────────────────────────

def test_parse_excel_valid_status(client, xlsx_tepeyac_plant):
    with open(xlsx_tepeyac_plant, "rb") as f:
        r = client.post("/parse-excel", files={"file": ("sample.xlsx", f, XLSX_MIME)})
    assert r.status_code == 200


def test_parse_excel_valid_response_structure(client, xlsx_tepeyac_plant):
    with open(xlsx_tepeyac_plant, "rb") as f:
        data = client.post("/parse-excel", files={"file": ("sample.xlsx", f, XLSX_MIME)}).json()
    assert "report" in data
    assert "samples" in data
    assert "total_samples" in data
    assert "meta" in data


def test_parse_excel_meta_lab_key(client, xlsx_tepeyac_plant):
    with open(xlsx_tepeyac_plant, "rb") as f:
        data = client.post("/parse-excel", files={"file": ("sample.xlsx", f, XLSX_MIME)}).json()
    assert data["meta"]["laboratory_key"] == "tepeyac_plant"
