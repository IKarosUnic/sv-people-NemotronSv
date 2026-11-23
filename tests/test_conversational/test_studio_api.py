"""End-to-end FastAPI tests for SALTBOR Conversational Studio endpoints (/api/studio/*)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saltbor.conversational import SALTBORConversationalOrchestrator
from saltbor.visualization.api import router
from saltbor.visualization.routers.conversational_studio_router import set_studio_orchestrator


@pytest.fixture()
def studio_client(tmp_path):
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "api_studio.db", seed=42)
    set_studio_orchestrator(orch)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    try:
        yield client
    finally:
        set_studio_orchestrator(None)
        orch.close()


def test_studio_chat_execute_compare_and_resume_api(studio_client):
    # 1. Stage A chat (map hidden)
    r_chat = studio_client.post(
        "/api/studio/chat",
        json={"message": "Quiero abrir una pupusería en Santa Tecla.", "map_visible": False},
    )
    assert r_chat.status_code == 200
    d_chat = r_chat.json()
    cid = d_chat["conversation_id"]
    sid = d_chat["scenario_id"]
    assert d_chat["stage"] == "STAGE_A_PRELIMINARY"
    assert d_chat["ready_to_execute"] is True

    # 2. Follow-up modification preserving continuity
    r_fu = studio_client.post(
        "/api/studio/chat",
        json={"message": "¿Y si contrato dos empleados más?", "conversation_id": cid},
    )
    assert r_fu.status_code == 200
    d_fu = r_fu.json()
    assert d_fu["parsed_request"]["is_follow_up"] is True
    assert d_fu["proposed_intervention"]["workforce_count"] == 4

    # 3. Stage B execution
    r_exec = studio_client.post(
        "/api/studio/execute",
        json={"conversation_id": cid, "scenario_id": d_fu["scenario_id"], "seed": 42, "map_visible": False},
    )
    assert r_exec.status_code == 200
    d_exec = r_exec.json()
    assert d_exec["stage"] == "STAGE_B_SIMULATED"
    assert d_exec["evidence"]["ledger_audit"]["conservation_passed"] is True
    assert d_exec["recommendation"]["verdict"] in (
        "PROMISING",
        "CONDITIONALLY_PROMISING",
        "INSUFFICIENT_EVIDENCE",
        "HIGH_RISK",
        "NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS",
    )

    # 4. Multi-seed comparison endpoint
    r_cmp = studio_client.post("/api/studio/compare", json={"conversation_id": cid, "seeds": [42, 101]})
    assert r_cmp.status_code == 200
    assert len(r_cmp.json()["alternatives"]) >= 1

    # 5. Resume persisted conversation
    r_res = studio_client.get(f"/api/studio/conversations/{cid}")
    assert r_res.status_code == 200
    assert len(r_res.json()["executions"]) == 1


def test_studio_territory_resolve_and_provider_config_security(studio_client):
    r_geo = studio_client.get("/api/studio/territory/resolve?query=San%20Miguel")
    assert r_geo.status_code == 200
    assert r_geo.json()["resolved"] is True
    assert r_geo.json()["department_name"] == "San Miguel"

    # Configure BYOK key & verify it is masked everywhere
    r_cfg = studio_client.post(
        "/api/studio/providers/config",
        json={
            "gemini_api_key": "AIzaSyTopSecretKey99999999",
            "allow_remote": True,
            "flash_lite_model": "gemini-2.5-flash-lite",
            "flash_model": "gemini-2.5-flash",
        },
    )
    assert r_cfg.status_code == 200
    assert "AIzaSyTopSecretKey99999999" not in r_cfg.text
    assert r_cfg.json()["gemini_byok_configured"] is True

    r_st = studio_client.get("/api/studio/providers/status")
    assert r_st.status_code == 200
    assert "AIzaSyTopSecretKey99999999" not in r_st.text
    assert r_st.json()["rate_limit"]["flash_model"] == "gemini-2.5-flash"

    # Clear key cleanly
    r_clr = studio_client.post("/api/studio/providers/config", json={"gemini_api_key": "clear"})
    assert r_clr.status_code == 200
    assert r_clr.json()["gemini_byok_configured"] is False
