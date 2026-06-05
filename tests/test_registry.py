from parsers.registry import EXCEL_REGISTRY, PDF_REGISTRY, REGISTRY


def test_registry_not_empty():
    assert len(REGISTRY) > 0


def test_registry_has_all_labs():
    keys = {p.laboratory_key for p in REGISTRY}
    expected = {
        "agrolab", "ceres", "las_garzas", "fertilab",
        "phytomonitor", "agrilab", "agroanalitica",
        "tepeyac", "motzz", "tepeyac_plant",
    }
    assert expected == keys


def test_registry_sorted_by_priority_descending():
    priorities = [p.priority for p in REGISTRY]
    assert priorities == sorted(priorities, reverse=True)


def test_pdf_registry_only_pdf_parsers():
    assert all(p.file_type == "pdf" for p in PDF_REGISTRY)


def test_excel_registry_only_excel_parsers():
    assert all(p.file_type == "excel" for p in EXCEL_REGISTRY)


def test_pdf_and_excel_registries_cover_all():
    assert len(PDF_REGISTRY) + len(EXCEL_REGISTRY) == len(REGISTRY)


def test_no_duplicate_laboratory_keys():
    keys = [p.laboratory_key for p in REGISTRY]
    assert len(keys) == len(set(keys))


def test_all_parsers_have_required_attributes():
    for parser in REGISTRY:
        assert isinstance(parser.laboratory_key, str)
        assert parser.laboratory_key != ""
        assert parser.file_type in ("pdf", "excel")
        assert isinstance(parser.priority, int)
