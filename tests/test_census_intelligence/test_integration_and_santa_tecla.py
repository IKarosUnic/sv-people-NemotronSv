"""Tests F: Integration with SALTBOR Engines, Santa Tecla 4-Scenario Validation, API & Frontend."""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from saltbor.census_intelligence.schemas import EvidenceClassification
from saltbor.census_intelligence.validation_scenario import (
    SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON,
    run_santa_tecla_school_validation,
)
from saltbor.conversational import SALTBORConversationalOrchestrator
from saltbor.visualization.routers.conversational_studio_router import set_studio_orchestrator
from saltbor.visualization.server import create_app


@pytest.fixture(scope="module")
def phase118_client(tmp_path_factory) -> Iterator[TestClient]:
    tmp_dir = tmp_path_factory.mktemp("phase118_api")
    sim_db = tmp_dir / "sim_118.db"
    studio_db = tmp_dir / "studio_118.db"
    orch = SALTBORConversationalOrchestrator(persistence_path=studio_db, seed=42)
    set_studio_orchestrator(orch)
    app = create_app(controller=None, seed=42, db_path=str(sim_db))
    with TestClient(app) as client:
        yield client
    set_studio_orchestrator(None)
    orch.close()
    app.state.controller.stop_worker()


def test_santa_tecla_real_4_scenario_validation_and_conservation():
    res = run_santa_tecla_school_validation(seed=42)
    assert res["district_official_population_2024"] == 125532
    assert 50 <= res["allocated_polygon_population"] <= 15000
    assert res["schools_discovered_total"] >= 15
    assert res["schools_in_influence"] + res["schools_in_contextual"] >= 10
    assert res["calibration"]["evidence_classification"] == EvidenceClassification.SYNTHETIC_CALIBRATED.value
    assert res["ledger_conservation"]["conserved"] is True
    assert res["ledger_conservation"]["total_discrepancy_usd"] == 0.0
    assert res["provenance_integrity"]["valid"] is True

    scens = {s["scenario_id"]: s for s in res["scenarios"]}
    assert len(scens) == 4
    s1 = scens["ESCENARIO_1_BASELINE"]
    s2 = scens["ESCENARIO_2_PARV_PRIMARIA"]
    s3 = scens["ESCENARIO_3_COMPLETA_K12"]
    s4 = scens["ESCENARIO_4_AMPLIACION_EXISTENTES"]

    # Scenario 1 must keep existing capacity strictly UNAVAILABLE (never fabricated)
    assert s1["capacity_evidence_classification"] == EvidenceClassification.UNAVAILABLE.value
    # Scenarios 2 & 3 reduce walking time below Scenario 1 & 4; Scenario 3 covers all 5 levels
    assert s3["mean_walk_time_min"] <= s1["mean_walk_time_min"]
    assert s3["uncovered_upper_levels_demand"] == 0
    assert len(s3["levels_covered_in_primary_area"]) == 5
    assert len(s2["levels_covered_in_primary_area"]) == 3
    assert s4["capacity_evidence_classification"] == EvidenceClassification.HYPOTHESIS.value


def test_phase118_api_endpoints_and_on_demand_integration(phase118_client: TestClient):
    # 1. Integrated official datasets endpoint
    ds = phase118_client.get("/api/territorial/census/datasets")
    assert ds.status_code == 200
    assert ds.json()["count"] >= 4

    # 2. Discover endpoint with Santa Tecla polygon
    disc = phase118_client.post(
        "/api/territorial/discover",
        json={
            "polygon_geojson": SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON,
            "travel_time_minutes": 15.0,
            "sector": "school",
            "max_expansion_minutes": 30.0,
            "seed": 42,
        },
    )
    assert disc.status_code == 200
    d_json = disc.json()
    assert len(d_json["areas_geojson"]["features"]) == 3
    assert len(d_json["population_clusters_geojson"]["features"]) >= 1
    assert len(d_json["infrastructure_geojson"]["features"]) >= 10
    assert d_json["provenance_integrity"]["valid"] is True
    assert d_json["certificate"]["calibration_status"] in ("CALIBRATED_ACCEPTABLE", "CALIBRATED_WITH_WARNINGS")

    # 3. Full OnDemand scenario includes preparation_certificate & calibration_summary
    scen = phase118_client.post(
        "/api/territorial/scenarios",
        json={
            "location_query": "Santa Tecla",
            "objective": "Evaluar centro escolar comunitario",
            "service_type": "school",
            "seed": 42,
        },
    )
    assert scen.status_code == 200
    s_json = scen.json()
    assert s_json["state"] == "COMPLETED"
    assert s_json["preparation_certificate"] is not None
    assert s_json["calibration_summary"]["calibration_passed"] is True
    assert "NationalCensusDataIntegrationEngine" in s_json["activated_engines"]

    # 4. Santa Tecla school validation endpoint
    val = phase118_client.post("/api/territorial/validation/santa-tecla-school?seed=42")
    assert val.status_code == 200
    assert len(val.json()["scenarios"]) == 4

    # 5. Frontend HTML/JS/CSS carry Phase 1.18 explorer controls while respecting MapLibre reuse rule
    html = phase118_client.get("/").text
    assert 'id="studio-btn-draw-polygon"' in html
    assert 'id="studio-travel-time-select"' in html
    assert 'id="studio-btn-discover-territory"' in html

    js = phase118_client.get("/modules/territorial_studio.js").text
    assert "new maplibregl.Map(" not in js
    assert "/api/territorial/discover" in js
