"""Tests for OnDemandTerritorialSimulationEngine, Historic Center decoupling,
SQLite WAL migrations, multi-turn chat, and /api/territorial/* REST endpoints.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from saltbor.conversational import SALTBORConversationalOrchestrator
from saltbor.simulation.runner import SimulationRunner
from saltbor.territorial_intelligence import TerritorialSimulationState
from saltbor.visualization.routers.conversational_studio_router import set_studio_orchestrator
from saltbor.visualization.server import create_app


@pytest.fixture(scope="module")
def territorial_client(tmp_path_factory) -> Iterator[TestClient]:
    tmp_dir = tmp_path_factory.mktemp("phase117_api")
    sim_db = tmp_dir / "sim_117.db"
    studio_db = tmp_dir / "studio_117.db"

    orch = SALTBORConversationalOrchestrator(persistence_path=studio_db, seed=42)
    set_studio_orchestrator(orch)
    # Default create_app() with controller=None MUST boot into IDLE location-independent mode!
    app = create_app(controller=None, seed=42, db_path=str(sim_db))

    with TestClient(app) as client:
        yield client

    set_studio_orchestrator(None)
    orch.close()
    app.state.controller.stop_worker()


def test_default_server_starts_idle_without_historic_center(territorial_client: TestClient):
    st = territorial_client.get("/api/status").json()
    assert st["status"] == "IDLE_ON_DEMAND"
    assert st["historic_center_active"] is False
    assert st["historic_center_is_default"] is False
    assert st["active_population"] == 0
    assert st["active_territory"] is None

    tst = territorial_client.get("/api/territorial/status").json()
    assert tst["state"] == "IDLE"
    assert tst["historic_center_is_default"] is False
    assert tst["rtree_indexed"] is True


def test_on_demand_scenario_lifecycle_and_clarification(territorial_client: TestClient):
    # 1. Ambiguous location asks clarification instead of defaulting to Historic Center
    r_ambig = territorial_client.post(
        "/api/territorial/scenarios",
        json={"location_query": "El Rosario", "objective": "Evaluar comercio"},
    )
    assert r_ambig.status_code == 200
    d_ambig = r_ambig.json()
    assert d_ambig["state"] == TerritorialSimulationState.NEEDS_CLARIFICATION.value
    assert d_ambig["clarification_question"]

    # 2. Real Soyapango scenario completes with A–G evidence & R-Tree built environment
    r_soya = territorial_client.post(
        "/api/territorial/scenarios",
        json={
            "location_query": "Soyapango",
            "objective": "Analizar centro comercial y empleo",
            "service_type": "commercial_center",
            "employment_intervention_kind": "COMMERCIAL_CENTER",
            "compare_with_baseline": True,
            "horizon_days": 30,
        },
    )
    assert r_soya.status_code == 200
    d_soya = r_soya.json()
    assert d_soya["state"] == "COMPLETED"
    assert d_soya["resolved_location"]["district_name"] == "Soyapango"
    assert d_soya["resolved_location"]["district_id"] != "0614"
    assert d_soya["building_intelligence"]["total_buildings_observed"] > 500
    assert d_soya["commercial_context"]["concentration_metrics"]["confirmed_establishments_count"] > 50
    assert d_soya["evidence_package"]["A_real_observed_data"]
    assert d_soya["evidence_package"]["E_simulated_outcomes"]
    assert d_soya["baseline_comparison"] is not None

    # 3. Scenario retrieval, pause, resume, rerun
    sid = d_soya["scenario_id"]
    assert territorial_client.get(f"/api/territorial/scenarios/{sid}").status_code == 200
    assert territorial_client.post(f"/api/territorial/scenarios/{sid}/pause").json()["state"] == "PAUSED"
    assert territorial_client.post(f"/api/territorial/scenarios/{sid}/resume").json()["state"] == "READY"
    assert territorial_client.post(f"/api/territorial/scenarios/{sid}/rerun?seed=101").json()["state"] == "COMPLETED"


def test_territorial_intelligence_endpoints_and_explicit_benchmark(territorial_client: TestClient):
    assert territorial_client.get("/api/territorial/buildings?query=Santa+Tecla").json()["total_buildings_observed"] > 200
    assert territorial_client.get("/api/territorial/commerce?query=San+Miguel").json()["concentration_metrics"]["confirmed_establishments_count"] > 20
    assert territorial_client.get("/api/territorial/catchment?query=Santa+Ana&service_type=hospital").json()["scale"] == "REGIONAL"
    assert territorial_client.get("/api/territorial/mobility?query=Soyapango").json()["measured_flows_available"] is False
    assert territorial_client.get("/api/territorial/employment?query=Soyapango").json()["verified_vacancies_available"] is False

    cov = territorial_client.get("/api/territorial/coverage").json()
    assert cov["total_departments"] == 14
    assert cov["total_districts"] == 262

    # Historic Center remains explicitly invocable as preserved benchmark
    hc = territorial_client.post("/api/territorial/benchmark/historic-center?seed=42").json()
    assert hc["is_historic_center_benchmark"] is True
    assert hc["state"] == "COMPLETED"

    runner = SimulationRunner.create_historic_center_benchmark(seed=42, db_path=":memory:")
    runner.initialize(load_existing=False)
    runner.step()
    assert runner.clock.current_tick == 1
    assert runner.is_historic_center_benchmark is True
    runner.close()
