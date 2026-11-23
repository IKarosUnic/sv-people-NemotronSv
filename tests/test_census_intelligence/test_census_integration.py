"""Tests A: National Census Data Integration Engine (CSV, JSON, GeoJSON, XLSX, Versioning, PII Guard, SAE)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from saltbor.census_intelligence import (
    EvidenceClassification,
    GeographicGranularity,
    NationalCensusDataIntegrationEngine,
    PIIViolationError,
)


def _create_minimal_xlsx(path: Path, headers: list[str], rows: list[list[str | int | float]]) -> None:
    """Create a valid minimal OOXML .xlsx file using pure Python stdlib zipfile."""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.worksheet+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    wb = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Datos" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )

    def _row_xml(r_idx: int, vals: list) -> str:
        cells = []
        for c_idx, v in enumerate(vals):
            col = chr(ord("A") + c_idx)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append(f'<c r="{col}{r_idx}"><v>{v}</v></c>')
            else:
                esc = str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                cells.append(f'<c r="{col}{r_idx}" t="inlineStr"><is><t>{esc}</t></is></c>')
        return f'<row r="{r_idx}">{"".join(cells)}</row>'

    all_rows = [_row_xml(1, headers)] + [_row_xml(i + 2, r) for i, r in enumerate(rows)]
    sheet1 = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(all_rows)}</sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", wb)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet1)


def test_shipped_official_datasets_loaded_with_honest_granularity():
    eng = NationalCensusDataIntegrationEngine()
    datasets = {d.dataset_id: d for d in eng.list_datasets()}
    assert "censo_2024_onec_bcr" in datasets
    assert "ehpm_2024_onec_bcr" in datasets
    assert "mined_2024_macro" in datasets

    censo_meta = datasets["censo_2024_onec_bcr"]
    assert GeographicGranularity.DEPARTMENT in censo_meta.available_granularities
    assert GeographicGranularity.MANZANA in censo_meta.unavailable_granularities

    # Santa Tecla has verified 2024 district figure (125,532)
    q_st = eng.query_area_statistics("dist_santa_tecla", GeographicGranularity.DISTRICT)
    assert q_st.official_population == 125532
    assert q_st.population_evidence_type == EvidenceClassification.PUBLIC_OFFICIAL
    assert q_st.exact_granularity_available is True

    # Requesting CANTON / MANZANA must NOT fabricate official counts — must trigger SAE with explicit uncertainty
    q_manz = eng.query_area_statistics("dist_santa_tecla", GeographicGranularity.MANZANA)
    assert q_manz.exact_granularity_available is False
    assert q_manz.population_evidence_type == EvidenceClassification.ESTIMATED_FROM_OFFICIAL
    assert q_manz.sae_estimate is not None
    assert q_manz.sae_estimate.uncertainty_pct > 0
    assert "mined_per_school_enrollment_and_installed_capacity" in q_manz.unavailable_variables


def test_csv_xlsx_json_import_versioning_duplicates_and_validation(tmp_path: Path):
    eng = NationalCensusDataIntegrationEngine()

    # 1. CSV import with duplicate row + invalid negative row
    csv_path = tmp_path / "mined_sample.csv"
    csv_path.write_text(
        "codigo_ce,nombre_centro,distrito,lat,lon,niveles,matricula,capacidad\n"
        "CE001,Centro Escolar Prueba Norte,Santa Tecla,13.671,-89.285,parvularia;basica_ciclo_1,240,300\n"
        "CE001,Centro Escolar Prueba Norte,Santa Tecla,13.671,-89.285,parvularia;basica_ciclo_1,240,300\n"
        "CE002,,Santa Tecla,13.672,-89.284,bachillerato,100,150\n",
        encoding="utf-8",
    )
    res_csv = eng.import_csv(csv_path, adapter_name="mined_schools", dataset_id="mined_st_test", version="2026.1")
    assert res_csv.records_imported >= 1
    assert res_csv.duplicates_skipped >= 1
    assert len(res_csv.validation_errors) >= 1
    assert len(eng.get_imported_mined_schools()) == 1

    # 2. XLSX pure-stdlib import
    xlsx_path = tmp_path / "censo_extra.xlsx"
    _create_minimal_xlsx(
        xlsx_path,
        headers=["geographic_unit", "granularity", "total_population", "mean_household_size"],
        rows=[["Soyapango", "DISTRICT", 241403, 3.2]],
    )
    res_xlsx = eng.import_xlsx(xlsx_path, adapter_name="censo_2024_onec", dataset_id="censo_soya_v1", version="1.0")
    assert res_xlsx.file_format == "xlsx"
    assert res_xlsx.records_imported == 2

    # Versioning bump on same dataset_id preserves history
    res_xlsx_v2 = eng.import_xlsx(xlsx_path, adapter_name="censo_2024_onec", dataset_id="censo_soya_v1", version="2.0")
    assert res_xlsx_v2.version == "2.0"
    assert len(eng.get_dataset_history("censo_soya_v1")) == 2

    # 3. GeoJSON FeatureCollection import
    geojson_path = tmp_path / "salud.geojson"
    geojson_path.write_text(
        json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-89.283, 13.671]},
                "properties": {"codigo": "MS01", "nombre": "Unidad de Salud Test", "distrito": "Santa Tecla", "capacidad_diaria": 85},
            }],
        }),
        encoding="utf-8",
    )
    res_geo = eng.import_json(geojson_path, adapter_name="minsal_health", dataset_id="minsal_test")
    assert res_geo.file_format == "geojson"
    assert res_geo.records_imported == 1


def test_pii_guard_rejects_personal_identifiable_columns(tmp_path: Path):
    eng = NationalCensusDataIntegrationEngine()
    pii_csv = tmp_path / "pii_bad.csv"
    pii_csv.write_text("dui,nombre_completo,distrito,total_population\n01234567-8,Juan Perez,Santa Tecla,1\n", encoding="utf-8")
    with pytest.raises(PIIViolationError):
        eng.import_csv(pii_csv, adapter_name="censo_2024_onec", dataset_id="pii_bad")
