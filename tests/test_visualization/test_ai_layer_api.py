"""Test suite for Phase 1.15 AI Intelligence Layer REST endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from saltbor.visualization.api import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_ai_providers_status_endpoint():
    resp = client.get("/api/ai/providers/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert "OFFLINE_DETERMINISTIC" in data["providers"]
    assert data["providers"]["OFFLINE_DETERMINISTIC"]["available"] is True
    assert "gemini_key_masked" in data
    assert "gemini_quota_exhausted" in data
    assert "budget" in data
    assert data["budget"]["total_spend_usd"] >= 0.0


def test_ai_byok_configuration_and_purge():
    # Configure BYOK in memory
    cfg_resp = client.post("/api/ai/providers/byok", json={"gemini_api_key": "AIzaSyFakeTestKey1234567890", "enable_remote": True})
    assert cfg_resp.status_code == 200
    cfg_data = cfg_resp.json()
    assert cfg_data["byok_active"] is True
    assert "AIzaSy" in cfg_data["masked_key"]
    assert cfg_data["masked_key"] != "AIzaSyFakeTestKey1234567890"

    # Status reflects configuration
    st_resp = client.get("/api/ai/providers/status")
    assert st_resp.status_code == 200
    assert st_resp.json()["gemini_byok_configured"] is True

    # Purge key from memory
    del_resp = client.post("/api/ai/providers/byok", json={"gemini_api_key": "clear", "enable_remote": False})
    assert del_resp.status_code == 200
    assert del_resp.json()["byok_active"] is False

    # Status reflects purged state
    st_after = client.get("/api/ai/providers/status")
    assert st_after.json()["gemini_byok_configured"] is False


def test_ai_territories_and_coverage_endpoint():
    resp = client.get("/api/ai/territories/districts")
    assert resp.status_code == 200
    districts = resp.json()
    assert len(districts) >= 10

    cov_resp = client.get("/api/ai/territories/coverage?territory=El%20Rosario")
    assert cov_resp.status_code == 200
    cov = cov_resp.json()
    assert "El Rosario" in cov["name"] or cov["territory_id"] is not None
    assert cov["data_quality_score"] > 0.0
    assert "missing_variables" in cov
    assert "uncertainties" in cov


def test_ai_build_natural_language_scenario():
    payload = {
        "prompt": "Simula qué sucedería si un deslave bloquea durante 15 días el camino en El Rosario",
        "territory_override": "El Rosario",
    }
    resp = client.post("/api/ai/scenarios/build_natural_language", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert "scenario_id" in data
    assert len(data["shocks"]) >= 1
    assert data["state"] in ["READY", "VALIDATING", "DRAFT"]
    assert data["coverage"]["data_quality_score"] > 0.0


def test_ai_causal_validation_endpoint():
    payload = {
        "cause": "road_interruption",
        "effect": "freight_cost_surge",
    }
    resp = client.post("/api/ai/causal/validate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["status"] == "VALIDATED_MECHANISM"
    assert "CrossDomainInteractionEngine" in data["engine"]

    # Unsupported mechanism
    bad_payload = {
        "cause": "magic_spell",
        "effect": "instant_wealth",
    }
    bad_resp = client.post("/api/ai/causal/validate", json=bad_payload)
    assert bad_resp.status_code == 200
    bad_data = bad_resp.json()
    assert bad_data["valid"] is False
    assert bad_data["status"] == "HYPOTHESIS_PENDING_VALIDATION"


def test_ai_planning_recommendations_endpoint():
    payload = {
        "research_objective": "Mitigar el impacto del encarecimiento de alimentos en familias agrícolas",
        "territory_name": "Cantón El Rosario",
    }
    resp = client.post("/api/ai/planning/recommendations", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["alternatives"]) >= 3
    assert len(data["key_indicators_to_monitor"]) >= 3
    assert "disclaimer" in data


def test_ai_execution_and_results_analysis():
    # Build scenario
    build_payload = {
        "prompt": "Simular corte vial de 10 días en San José Las Flores",
        "territory_override": "San José Las Flores",
    }
    b_resp = client.post("/api/ai/scenarios/build_natural_language", json=build_payload)
    assert b_resp.status_code == 200
    b_data = b_resp.json()
    scen_id = b_data["scenario_id"]

    # Run execution
    run_payload = {
        "scenario_id": scen_id,
        "seed": 42,
    }
    run_resp = client.post("/api/ai/execution/run", json=run_payload)
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["status"] == "completed"
    assert run_data["consistency_passed"] is True
    assert run_data["duration_ticks"] > 0

    # Analyze results
    analyze_payload = {
        "scenario_id": scen_id,
        "seed": 42,
    }
    a_resp = client.post("/api/ai/results/analyze", json=analyze_payload)
    assert a_resp.status_code == 200
    a_data = a_resp.json()
    assert "executive_summary" in a_data
    assert "double_entry_ledger_audit" in a_data
    assert "scientific_disclaimer" in a_data


def test_ai_counterfactual_comparison_and_context():
    resp = client.get("/api/ai/scenarios/compare_counterfactual")
    assert resp.status_code == 200
    data = resp.json()
    assert data["double_entry_ledger_verified"] is True
    assert "synthesis_narrative" in data
    assert "causality_caveat" in data

    # Partition access
    ctx_resp = client.get("/api/ai/context/partition?partition=SIMULATION_ONTOLOGY")
    assert ctx_resp.status_code == 200
    assert ctx_resp.json()["accessible"] is True

    priv_resp = client.get("/api/ai/context/partition?partition=INDIVIDUAL_SYNTHETIC_MEMORY")
    assert priv_resp.status_code == 200
    assert priv_resp.json()["accessible"] is False
