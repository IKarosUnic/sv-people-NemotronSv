"""Modular FastAPI Router for SALTBOR Phase 1.16A/1.16B Conversational Territorial Studio."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from saltbor.ai import AIModelRouter, AIProviderType
from saltbor.conversational import (
    ProgressiveReportBuilder,
    ReportDepthLevel,
    SALTBORConversationalOrchestrator,
)

router = APIRouter(prefix="/studio", tags=["Conversational Territorial Studio"])

_studio_orchestrator: Optional[SALTBORConversationalOrchestrator] = None


def get_studio_orchestrator() -> SALTBORConversationalOrchestrator:
    global _studio_orchestrator
    if _studio_orchestrator is None:
        _studio_orchestrator = SALTBORConversationalOrchestrator(persistence_path="saltbor_studio.db")
    return _studio_orchestrator


def set_studio_orchestrator(orchestrator: Optional[SALTBORConversationalOrchestrator]) -> None:
    global _studio_orchestrator
    _studio_orchestrator = orchestrator


class StudioChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    map_visible: bool = False
    auto_execute: bool = False
    seed: Optional[int] = None
    temporal_days_override: Optional[int] = None


class StudioExecuteRequest(BaseModel):
    conversation_id: str
    scenario_id: Optional[str] = None
    seed: int = 42
    compare_alternatives: bool = False
    max_active_agents: int = Field(default=40, ge=8, le=250)
    map_visible: bool = False
    run_in_background: bool = False


class StudioCompareRequest(BaseModel):
    conversation_id: str
    seeds: list[int] = Field(default_factory=lambda: [42, 101, 202])
    max_active_agents: int = Field(default=32, ge=8, le=120)


class StudioProviderConfigRequest(BaseModel):
    gemini_api_key: Optional[str] = None
    allow_remote: Optional[bool] = None
    provider_mode: Optional[str] = None  # "gemini" | "ollama" | "offline"
    flash_lite_model: Optional[str] = None
    flash_model: Optional[str] = None
    ollama_model: Optional[str] = None
    strict_redaction: Optional[bool] = None


@router.post("/chat")
def studio_chat_endpoint(req: StudioChatRequest) -> Dict[str, Any]:
    """Primary natural-language Spanish entry point (Stage A preliminary or optional Stage B)."""
    orch = get_studio_orchestrator()
    result = orch.handle_message(
        message=req.message,
        conversation_id=req.conversation_id,
        lat=req.lat,
        lon=req.lon,
        map_visible=req.map_visible,
        auto_execute=req.auto_execute,
        seed=req.seed,
        temporal_days_override=req.temporal_days_override,
    )
    return result.model_dump(mode="json")


@router.post("/execute")
def studio_execute_endpoint(req: StudioExecuteRequest) -> Dict[str, Any]:
    """Execute Stage B simulation through real SALTBOR engines (sync or background)."""
    orch = get_studio_orchestrator()
    if req.run_in_background:
        job_id = orch.start_background_stage_b(
            conversation_id=req.conversation_id,
            scenario_id=req.scenario_id,
            seed=req.seed,
            compare_alternatives=req.compare_alternatives,
            max_active_agents=req.max_active_agents,
            map_visible=req.map_visible,
        )
        return {"status": "started", "job_id": job_id, "conversation_id": req.conversation_id}

    res = orch.execute_stage_b(
        conversation_id=req.conversation_id,
        scenario_id=req.scenario_id,
        seed=req.seed,
        compare_alternatives=req.compare_alternatives,
        max_active_agents=req.max_active_agents,
        map_visible=req.map_visible,
    )
    return res.model_dump(mode="json")


@router.get("/jobs/{job_id}")
def studio_job_status_endpoint(job_id: str) -> Dict[str, Any]:
    """Poll status and authentic stage progression of a background Stage B simulation job."""
    orch = get_studio_orchestrator()
    status = orch.get_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return status


@router.post("/jobs/{job_id}/cancel")
def studio_job_cancel_endpoint(job_id: str) -> Dict[str, Any]:
    """Cancel a running background Stage B simulation job."""
    orch = get_studio_orchestrator()
    if not orch.cancel_job(job_id):
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"status": "cancelling", "job_id": job_id}


@router.post("/compare")
def studio_compare_endpoint(req: StudioCompareRequest) -> Dict[str, Any]:
    """Run multi-seed paired scenario comparison for the active conversation scenario."""
    orch = get_studio_orchestrator()
    session = orch.persistence.load_session(req.conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Conversation '{req.conversation_id}' not found.")

    geo_ctx = orch.territorial_engine.resolve_location(
        query=session.active_location_query,
        lat=session.active_coordinates[0] if session.active_coordinates else None,
        lon=session.active_coordinates[1] if session.active_coordinates else None,
    )
    if not geo_ctx.resolved or session.active_intervention is None:
        raise HTTPException(status_code=400, detail="Conversation lacks a resolved territory or active intervention.")

    temporal = session.active_temporal_horizon or orch.temporal_controller.parse_temporal_horizon(None)
    report = orch.comparison_engine.compare_scenarios(
        context=geo_ctx,
        base_intervention=session.active_intervention,
        temporal=temporal,
        seeds=req.seeds,
        max_active_agents=req.max_active_agents,
    )
    return report.model_dump(mode="json")


@router.get("/conversations")
def studio_list_conversations_endpoint(limit: int = 30) -> Dict[str, Any]:
    """List persisted conversations and scenario references."""
    orch = get_studio_orchestrator()
    return {"conversations": orch.persistence.list_sessions(limit=limit)}


@router.get("/conversations/{conversation_id}")
def studio_get_conversation_endpoint(conversation_id: str) -> Dict[str, Any]:
    """Retrieve and resume persisted conversation state and experiment references."""
    orch = get_studio_orchestrator()
    session = orch.persistence.load_session(conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found.")
    executions = orch.persistence.list_executions_for_conversation(conversation_id)
    for ex in executions:
        try:
            scen = orch.persistence.get_scenario_by_id(ex["scenario_id"])
            bundle = ProgressiveReportBuilder.build_from_persisted_execution(ex, scen)
            ex["progressive_report"] = bundle.model_dump(mode="json")
        except Exception:
            ex["progressive_report"] = None
    return {
        "session": session.model_dump(mode="json"),
        "executions": executions,
    }


@router.get("/executions/{execution_id}/report")
def studio_execution_progressive_report_endpoint(
    execution_id: str,
    level: str = "BASIC",
) -> Dict[str, Any]:
    """Return a single persisted simulation report at BASIC, INTERMEDIATE, or EXPERT depth."""
    norm_level = (level or "BASIC").strip().upper()
    if norm_level not in {lvl.value for lvl in ReportDepthLevel}:
        raise HTTPException(
            status_code=400,
            detail=f"Nivel de reporte inválido '{level}'. Valores válidos: BASIC, INTERMEDIATE, EXPERT.",
        )

    orch = get_studio_orchestrator()
    ex = orch.persistence.get_execution_by_id(execution_id)
    if ex is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found.")

    scen = orch.persistence.get_scenario_by_id(ex["scenario_id"])
    bundle = ProgressiveReportBuilder.build_from_persisted_execution(ex, scen)
    bundle_json = bundle.model_dump(mode="json")
    return {
        "execution_id": execution_id,
        "selected_level": norm_level,
        "view": bundle_json[norm_level.lower()],
        "progressive_report": bundle_json,
    }


@router.get("/territory/search")
def studio_search_territory_endpoint(q: str = "", limit: int = 10) -> Dict[str, Any]:
    """Autocomplete Salvadoran departments, municipalities, districts, cantones, and OSM places."""
    orch = get_studio_orchestrator()
    matches: List[Dict[str, Any]] = orch.territorial_engine.search_locations(query=q, limit=max(1, min(25, limit)))
    return {"query": q, "results": matches}


@router.get("/territory/resolve")
def studio_resolve_territory_endpoint(
    query: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: float = 1.5,
) -> Dict[str, Any]:
    """Resolve any Salvadoran place name or coordinate with OSM provenance."""
    orch = get_studio_orchestrator()
    ctx = orch.territorial_engine.resolve_location(query=query, lat=lat, lon=lon, radius_km=radius_km)
    return ctx.model_dump(mode="json")


def _compute_provider_status_payload(orch: SALTBORConversationalOrchestrator) -> Dict[str, Any]:
    router_obj: AIModelRouter = orch.router
    gemini = router_obj.gemini_provider
    ollama = router_obj.ollama_provider
    has_key = bool(gemini._api_key)

    if router_obj.preferred_provider == AIProviderType.OFFLINE_DETERMINISTIC and not router_obj.allow_remote:
        provider_mode = "offline"
    elif router_obj.preferred_provider == AIProviderType.LOCAL_OLLAMA and not router_obj.allow_remote:
        provider_mode = "ollama"
    elif router_obj.allow_remote:
        provider_mode = "gemini"
    else:
        provider_mode = "offline"

    ollama_ok = ollama.is_available()
    last_err = (gemini.last_error_message or "").lower()
    if gemini.quota_exhausted:
        status_code = "QUOTA_EXCEEDED"
    elif "rate limit" in last_err:
        status_code = "RATE_LIMITED"
    elif provider_mode == "offline":
        status_code = "OFFLINE_MODE"
    elif provider_mode == "ollama":
        status_code = "LOCAL_PROVIDER_ACTIVE" if ollama_ok else "UNAVAILABLE"
    elif router_obj.allow_remote and has_key:
        status_code = "CONNECTED"
    elif not has_key:
        status_code = "NOT_CONFIGURED"
    else:
        status_code = "UNAVAILABLE"

    return {
        "allow_remote": router_obj.allow_remote,
        "provider_mode": provider_mode,
        "status_code": status_code,
        "providers": router_obj.get_provider_status(),
        "gemini_byok_configured": has_key,
        "gemini_key_masked": orch.privacy_guard.mask_api_key(gemini._api_key),
        "gemini_quota_exhausted": gemini.quota_exhausted,
        "ollama_model": ollama.model,
        "ollama_available": ollama_ok,
        "strict_redaction": orch.privacy_guard.enable_strict_redaction,
        "rate_limit": gemini.get_rate_limit_status(),
        "budget": orch.budget_manager.get_summary_report(),
    }


@router.get("/providers/status")
def studio_providers_status_endpoint() -> Dict[str, Any]:
    """Return masked BYOK status, configurable Gemini model IDs, Ollama, offline mode, and privacy flags."""
    orch = get_studio_orchestrator()
    return _compute_provider_status_payload(orch)


@router.post("/providers/config")
def studio_providers_config_endpoint(req: StudioProviderConfigRequest) -> Dict[str, Any]:
    """Configure ephemeral in-memory BYOK key, provider mode, model IDs, and privacy preferences."""
    orch = get_studio_orchestrator()
    router_obj = orch.router
    gemini = router_obj.gemini_provider
    ollama = router_obj.ollama_provider

    if req.gemini_api_key is not None:
        if req.gemini_api_key.strip().lower() in ("", "clear", "none"):
            gemini.clear_byok_key()
            router_obj.allow_remote = False
        else:
            gemini.set_byok_key(req.gemini_api_key)
            router_obj.allow_remote = True if req.allow_remote is None else req.allow_remote

    if req.provider_mode is not None:
        mode = req.provider_mode.strip().lower()
        if mode == "gemini":
            router_obj.allow_remote = True
            router_obj.preferred_provider = AIProviderType.REMOTE_GEMINI
        elif mode == "ollama":
            router_obj.allow_remote = False
            router_obj.preferred_provider = AIProviderType.LOCAL_OLLAMA
        elif mode == "offline":
            router_obj.allow_remote = False
            router_obj.preferred_provider = AIProviderType.OFFLINE_DETERMINISTIC

    if req.allow_remote is not None:
        router_obj.allow_remote = req.allow_remote

    gemini.configure_models(
        flash_lite_model=req.flash_lite_model,
        flash_model=req.flash_model,
    )

    if req.ollama_model and req.ollama_model.strip():
        ollama.model = req.ollama_model.strip()

    if req.strict_redaction is not None:
        orch.privacy_guard.enable_strict_redaction = bool(req.strict_redaction)

    payload = _compute_provider_status_payload(orch)
    payload["status"] = "updated"
    return payload
