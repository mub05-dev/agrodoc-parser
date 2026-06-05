from pathlib import Path

import pytest
from fastapi.testclient import TestClient


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def pdf_agrolab():
    return FIXTURES_DIR / "agrolab" / "sample.pdf"


@pytest.fixture(scope="session")
def pdf_ceres():
    return FIXTURES_DIR / "ceres" / "sample.pdf"


@pytest.fixture(scope="session")
def pdf_las_garzas():
    return FIXTURES_DIR / "las_garzas" / "sample.pdf"


@pytest.fixture(scope="session")
def pdf_fertilab():
    return FIXTURES_DIR / "fertilab" / "sample.pdf"


@pytest.fixture(scope="session")
def pdf_phytomonitor():
    return FIXTURES_DIR / "phytomonitor" / "sample.pdf"


@pytest.fixture(scope="session")
def pdf_agrilab():
    return FIXTURES_DIR / "agrilab" / "sample.pdf"


@pytest.fixture(scope="session")
def pdf_agroanalitica():
    return FIXTURES_DIR / "agroanalitica" / "sample.pdf"


@pytest.fixture(scope="session")
def pdf_tepeyac():
    return FIXTURES_DIR / "tepeyac" / "sample.pdf"


@pytest.fixture(scope="session")
def pdf_motzz():
    return FIXTURES_DIR / "motzz" / "sample.pdf"


@pytest.fixture(scope="session")
def xlsx_tepeyac_plant():
    return FIXTURES_DIR / "tepeyac_plant" / "sample.xlsx"


@pytest.fixture(scope="session")
def client():
    from main import app
    with TestClient(app) as c:
        yield c
