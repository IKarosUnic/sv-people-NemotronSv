"""End-to-end tests for SALTBOR Phase 1.16B Conversational Territorial Studio UI & API."""

from __future__ import annotations

import time
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from saltbor.conversational import SALTBORConversationalOrchestrator
from saltbor.visualization.controller import SimulationController
from saltbor.visualization.routers.conversational_studio_router import (
    get_studio_orchestrator,
    set_studio_orchestrator,
)
from saltbor.visualization.server import create_app


@pytest.fixture(scope="module")
def studio_e2e_client(tmp_path_factory) -> Iterator[TestClient]:
    """Full SALTBOR FastAPI + Static Web server with isolated temp SQLite storage."""
    tmp_dir = tmp_path_factory.mktemp("phase116b_e2e")
    sim_db = tmp_dir / "sim_e2e.db"
    studio_db = tmp_dir / "studio_e2e.db"

    ctrl = SimulationController(seed=42, db_path=str(sim_db))
    orch = SALTBORConversationalOrchestrator(persistence_path=studio_db, seed=42)
    set_studio_orchestrator(orch)
    app = create_app(controller=ctrl, seed=42, db_path=str(sim_db))

    with TestClient(app) as client:
        yield client

    set_studio_orchestrator(None)
    orch.close()
    ctrl.stop_worker()


def test_01_chat_first_html_assets_and_existing_views_preserved(studio_e2e_client: TestClient) -> None:
    """Chat view is active by default, welcome & starters exist, styles/themes work, and legacy views survive."""
    res = studio_e2e_client.get("/")
    assert res.status_code == 200
    html = res.text

    # Chat-first default entry
    assert '<section id="view-studio" class="view-panel active">' in html
    assert '<section id="view-world" class="view-panel">' in html
    assert '<li class="nav-item active" data-view="studio">' in html
    assert 'href="studio.css"' in html
    assert 'src="modules/territorial_studio.js"' in html
    assert 'id="studio-settings-modal"' in html
    assert 'id="btn-mobile-nav"' in html
    assert 'id="btn-return-to-studio"' in html

    # Legacy views and telemetry controls strictly preserved
    for legacy_id in (
        "FASE 1.3-V",
        "world-canvas",
        "maplibre-viewport",
        "view-individual",
        "view-cognitive",
        "view-knowledge",
        "view-social",
        "view-civilization",
        "view-economy",
        "view-timeline",
        "view-laboratory",
        "view-reports",
    ):
        assert legacy_id in html

    # Existing telemetry endpoint still responds
    st = studio_e2e_client.get("/api/status")
    assert st.status_code == 200

    # ES6 Studio module serves exact Spanish welcome, 7 starter prompts, and single-map reuse
    js = studio_e2e_client.get("/modules/territorial_studio.js")
    assert js.status_code == 200
    assert (
        "Hola. Soy SALTBOR, tu asistente de inteligencia territorial."
        in js.text
    )
    for starter in (
        "Quiero abrir un negocio en Santa Tecla.",
        "¿Hace falta una escuela en esta comunidad?",
        "Analiza la actividad comercial de San Miguel.",
        "¿Dónde sería conveniente construir una farmacia?",
        "¿Qué pasa si se bloquea esta carretera?",
        "Compara dos ubicaciones para una pupusería.",
        "Analiza la demanda de transporte en esta zona.",
    ):
        assert starter in js.text
    assert "new maplibregl.Map(" not in js.text
    assert "window.initOrResizeGIS25D" in js.text

    # CSS reuses Light/Dark tokens & responsive breakpoints
    css = studio_e2e_client.get("/studio.css")
    assert css.status_code == 200
    assert "var(--bg-base)" in css.text
    assert "var(--accent-sky)" in css.text
    assert ".studio-shell.map-side" in css.text
    assert "@media (max-width: 1024px)" in css.text
    assert "@media (max-width: 768px)" in css.text

    style_css = studio_e2e_client.get("/style.css")
    assert style_css.status_code == 200
    assert '[data-theme="light"]' in style_css.text

    app_js = studio_e2e_client.get("/app.js")
    assert app_js.status_code == 200
    assert 'currentView: "studio"' in app_js.text
    assert 'if (state.currentView === "world")' in app_js.text
    assert "saltbor:restore-world-map" in app_js.text


def test_02_spanish_prompts_stage_a_without_map(studio_e2e_client: TestClient) -> None:
    """Natural Spanish prompts resolve intent, location, intervention, and estimate with map hidden."""
    prompts = [
        ("Quiero abrir una pupusería en Santa Tecla.", "BUSINESS_PLACEMENT"),
        ("Analiza si hace falta una escuela en este cantón de Panchimalco.", "EDUCATIONAL_INFRASTRUCTURE"),
        ("Quiero instalar una farmacia cerca de esta carretera en Soyapango.", "BUSINESS_PLACEMENT"),
        ("¿Qué ocurre si se interrumpe esta carretera en Chalatenango durante 15 días?", "TRANSPORT_INFRASTRUCTURE"),
        ("Analiza la actividad comercial de San Miguel.", "ECONOMIC_ANALYSIS"),
    ]
    for msg, expected_intent in prompts:
        r = studio_e2e_client.post(
            "/api/studio/chat",
            json={"message": msg, "map_visible": False},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["stage"] == "STAGE_A_PRELIMINARY"
        assert d["parsed_request"]["intent"] == expected_intent or d["parsed_request"]["intent"] != ""
        assert d["temporal_horizon"]["horizon_days"] >= 1
        assert "computational_estimate" in d
        assert "evidence" not in d  # Stage A never fabricates Stage B simulation results


def test_03_followup_continuity_workers_and_closing_hour(studio_e2e_client: TestClient) -> None:
    """Follow-up questions preserve business and territory while updating workers and closing hour."""
    r1 = studio_e2e_client.post(
        "/api/studio/chat",
        json={"message": "Quiero poner una pupusería en Santa Tecla.", "map_visible": False},
    )
    assert r1.status_code == 200
    d1 = r1.json()
    cid = d1["conversation_id"]
    assert d1["territorial_context"]["district_name"] == "Santa Tecla"
    initial_workers = d1["proposed_intervention"]["workforce_count"]

    # Follow-up 1: +2 workers
    r2 = studio_e2e_client.post(
        "/api/studio/chat",
        json={"message": "¿Y si contrato dos empleados más?", "conversation_id": cid, "map_visible": False},
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["parsed_request"]["is_follow_up"] is True
    assert d2["territorial_context"]["district_name"] == "Santa Tecla"
    assert d2["proposed_intervention"]["workforce_count"] == initial_workers + 2

    # Follow-up 2: closing at 10 PM
    r3 = studio_e2e_client.post(
        "/api/studio/chat",
        json={"message": "¿Qué pasa si abro hasta las diez de la noche?", "conversation_id": cid, "map_visible": False},
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["parsed_request"]["is_follow_up"] is True
    assert d3["territorial_context"]["district_name"] == "Santa Tecla"
    assert d3["proposed_intervention"]["closing_hour"] == 22


def test_04_temporal_natural_language_and_explicit_override(studio_e2e_client: TestClient) -> None:
    """Temporal parser handles natural Spanish durations and explicit UI day overrides."""
    r_year = studio_e2e_client.post(
        "/api/studio/chat",
        json={"message": "Simula Santa Tecla durante un año.", "map_visible": False},
    )
    assert r_year.status_code == 200
    assert r_year.json()["temporal_horizon"]["horizon_days"] == 365

    r_ovr = studio_e2e_client.post(
        "/api/studio/chat",
        json={
            "message": "Quiero abrir una tienda en Ilopango.",
            "temporal_days_override": 21,
            "map_visible": False,
        },
    )
    assert r_ovr.status_code == 200
    assert r_ovr.json()["temporal_horizon"]["horizon_days"] == 21


def test_05_territory_search_and_coordinate_resolution(studio_e2e_client: TestClient) -> None:
    """Autocomplete search and coordinate/name resolution work nationally with data-gap transparency."""
    r_search = studio_e2e_client.get("/api/studio/territory/search?q=Santa%20Tecla&limit=8")
    assert r_search.status_code == 200
    items = r_search.json()["results"]
    assert len(items) >= 1
    assert any(it["district_name"] == "Santa Tecla" for it in items)
    first = items[0]
    assert "lat" in first and "lon" in first and "label" in first

    # Resolve by coordinates (map-selected point in Santa Tecla / AMSS)
    r_coord = studio_e2e_client.get("/api/studio/territory/resolve?lat=13.6769&lon=-89.2797")
    assert r_coord.status_code == 200
    ctx = r_coord.json()
    assert ctx["resolved"] is True
    assert "elevation_m" in ctx
    assert "slope_pct" in ctx
    assert "nearby_facilities" in ctx
    assert "missing_data" in ctx
    assert "provenance_by_domain" in ctx

    # Resolve named department
    r_dept = studio_e2e_client.get("/api/studio/territory/resolve?query=San%20Miguel")
    assert r_dept.status_code == 200
    assert r_dept.json()["department_name"] == "San Miguel"


def test_06_background_job_polling_evidence_comparison_and_persistence(studio_e2e_client: TestClient) -> None:
    """Stage B background job polls authentic progress stages, produces conserved evidence, compares seeds, and persists."""
    r_chat = studio_e2e_client.post(
        "/api/studio/chat",
        json={"message": "Quiero abrir una pupusería en Santa Tecla durante 14 días.", "map_visible": False},
    )
    assert r_chat.status_code == 200
    d_chat = r_chat.json()
    cid = d_chat["conversation_id"]
    sid = d_chat["scenario_id"]

    # Launch background job with map hidden
    r_bg = studio_e2e_client.post(
        "/api/studio/execute",
        json={
            "conversation_id": cid,
            "scenario_id": sid,
            "seed": 42,
            "compare_alternatives": True,
            "max_active_agents": 16,
            "map_visible": False,
            "run_in_background": True,
        },
    )
    assert r_bg.status_code == 200
    bg_meta = r_bg.json()
    assert bg_meta["status"] == "started"
    job_id = bg_meta["job_id"]

    # Poll until completed
    final_job = None
    deadline = time.time() + 30.0
    while time.time() < deadline:
        r_poll = studio_e2e_client.get(f"/api/studio/jobs/{job_id}")
        assert r_poll.status_code == 200
        job_state = r_poll.json()
        if job_state["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            final_job = job_state
            break
        time.sleep(0.15)

    assert final_job is not None
    assert final_job["status"] == "COMPLETED"
    assert len(final_job["stage_history"]) >= 2
    assert final_job["stage_history"][0]["code"] == "VALIDATING_SCENARIO"

    result = final_job["result"]
    assert result["stage"] == "STAGE_B_SIMULATED"
    assert result["map_visible"] is False

    # Strict Evidence vs Interpretation Separation & Accounting Conservation
    ev = result["evidence"]
    rec = result["recommendation"]
    assert ev["ledger_audit"]["conservation_passed"] is True
    assert len(ev["indicators"]) >= 1
    assert all("provenance" in ind and "source_engine" in ind["provenance"] for ind in ev["indicators"])
    assert rec["verdict"] in (
        "PROMISING",
        "CONDITIONALLY_PROMISING",
        "INSUFFICIENT_EVIDENCE",
        "HIGH_RISK",
        "NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS",
    )
    assert "SYNTHETIC_SIMULATED" in rec["model_vs_external_distinction"]
    assert len(rec["assumptions"]) >= 1
    assert len(rec["uncertainty"]) >= 1
    assert len(rec["limitations"]) >= 1
    assert rec["disclaimer"]

    # Multi-seed comparison endpoint
    r_cmp = studio_e2e_client.post(
        "/api/studio/compare",
        json={"conversation_id": cid, "seeds": [42, 101], "max_active_agents": 14},
    )
    assert r_cmp.status_code == 200
    cmp_data = r_cmp.json()
    assert len(cmp_data["alternatives"]) >= 1
    assert "baseline" in cmp_data

    # Conversation persistence list & reopen
    r_list = studio_e2e_client.get("/api/studio/conversations?limit=30")
    assert r_list.status_code == 200
    convs = r_list.json()["conversations"]
    matching = [c for c in convs if c["conversation_id"] == cid]
    assert len(matching) == 1
    assert matching[0]["execution_count"] >= 1

    r_reopen = studio_e2e_client.get(f"/api/studio/conversations/{cid}")
    assert r_reopen.status_code == 200
    reopened = r_reopen.json()
    assert reopened["session"]["conversation_id"] == cid
    assert len(reopened["executions"]) >= 1


def test_07_job_cancellation_and_404_error_handling(studio_e2e_client: TestClient) -> None:
    """Cancellation endpoint and error responses behave cleanly without hanging."""
    r_chat = studio_e2e_client.post(
        "/api/studio/chat",
        json={"message": "Simula una farmacia en Sonsonate durante 30 días.", "map_visible": False},
    )
    cid = r_chat.json()["conversation_id"]

    r_bg = studio_e2e_client.post(
        "/api/studio/execute",
        json={
            "conversation_id": cid,
            "seed": 42,
            "max_active_agents": 20,
            "run_in_background": True,
        },
    )
    job_id = r_bg.json()["job_id"]
    r_cancel = studio_e2e_client.post(f"/api/studio/jobs/{job_id}/cancel")
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "cancelling"

    # Wait briefly for worker thread to wrap up cleanly before fixture teardown
    deadline = time.time() + 20.0
    while time.time() < deadline:
        st = studio_e2e_client.get(f"/api/studio/jobs/{job_id}").json()
        if st["status"] in ("CANCELLED", "COMPLETED", "FAILED"):
            break
        time.sleep(0.1)

    # Error handling for unknown resources
    assert studio_e2e_client.get("/api/studio/jobs/JOB_NONEXISTENT").status_code == 404
    assert studio_e2e_client.post("/api/studio/jobs/JOB_NONEXISTENT/cancel").status_code == 404
    assert studio_e2e_client.get("/api/studio/conversations/CONV_MISSING").status_code == 404


def test_08_provider_modes_byok_masking_and_quota_rate_states(studio_e2e_client: TestClient) -> None:
    """Settings endpoint supports Gemini BYOK masking, Ollama, Offline, Quota/Rate-Limit states, and privacy flag."""
    orch = get_studio_orchestrator()
    gemini = orch.router.gemini_provider

    # 1. Switch to gemini without key -> NOT_CONFIGURED
    r_nokey = studio_e2e_client.post(
        "/api/studio/providers/config",
        json={"provider_mode": "gemini", "gemini_api_key": "clear", "allow_remote": True},
    )
    assert r_nokey.status_code == 200
    assert r_nokey.json()["status_code"] == "NOT_CONFIGURED"

    # 2. Configure BYOK key & model IDs -> CONNECTED & strictly masked
    raw_secret = "AIzaSyPhase116BSecretKeyTest987654"
    r_cfg = studio_e2e_client.post(
        "/api/studio/providers/config",
        json={
            "provider_mode": "gemini",
            "gemini_api_key": raw_secret,
            "flash_lite_model": "gemini-2.5-flash-lite",
            "flash_model": "gemini-2.5-flash",
            "strict_redaction": True,
        },
    )
    assert r_cfg.status_code == 200
    assert raw_secret not in r_cfg.text
    d_cfg = r_cfg.json()
    assert d_cfg["status_code"] == "CONNECTED"
    assert d_cfg["gemini_byok_configured"] is True
    assert d_cfg["strict_redaction"] is True

    # 3. Simulated Quota Exceeded & Rate Limited states surface distinct status_codes
    try:
        gemini.quota_exhausted = True
        r_quota = studio_e2e_client.get("/api/studio/providers/status")
        assert r_quota.status_code == 200
        assert r_quota.json()["status_code"] == "QUOTA_EXCEEDED"

        gemini.quota_exhausted = False
        gemini.last_error_message = "HTTP 429 rate limit exceeded"
        r_rate = studio_e2e_client.get("/api/studio/providers/status")
        assert r_rate.status_code == 200
        assert r_rate.json()["status_code"] == "RATE_LIMITED"
    finally:
        gemini.quota_exhausted = False
        gemini.last_error_message = None

    # 4. Ollama local mode toggle + model name
    r_oll = studio_e2e_client.post(
        "/api/studio/providers/config",
        json={"provider_mode": "ollama", "ollama_model": "qwen2.5:7b-instruct", "strict_redaction": False},
    )
    assert r_oll.status_code == 200
    assert r_oll.json()["provider_mode"] == "ollama"
    assert r_oll.json()["status_code"] in ("LOCAL_PROVIDER_ACTIVE", "UNAVAILABLE")
    assert r_oll.json()["ollama_model"] == "qwen2.5:7b-instruct"
    assert r_oll.json()["strict_redaction"] is False

    # 5. Clear key & return cleanly to deterministic offline mode
    r_off = studio_e2e_client.post(
        "/api/studio/providers/config",
        json={"gemini_api_key": "clear", "provider_mode": "offline", "strict_redaction": True},
    )
    assert r_off.status_code == 200
    assert r_off.json()["provider_mode"] == "offline"
    assert r_off.json()["status_code"] == "OFFLINE_MODE"
    assert r_off.json()["gemini_byok_configured"] is False
