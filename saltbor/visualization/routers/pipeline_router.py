"""Modular FastAPI Router for Tick Stage Telemetry, Adaptive LOD Budget & Live Scenario Bridge (Phase 1.16)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from saltbor.ai import (
    AIComputeBudgetManager,
    AIModelRouter,
    NaturalLanguageScenarioBuilder,
)
from saltbor.territory.territory_catalog import TerritoryCatalogService

router = APIRouter()

_nl_router = AIModelRouter()
_nl_budget = AIComputeBudgetManager()
_nl_catalog = TerritoryCatalogService()
_nl_builder = NaturalLanguageScenarioBuilder(
    router=_nl_router,
    budget_manager=_nl_budget,
    catalog=_nl_catalog,
)


class LODBudgetConfigRequest(BaseModel):
    target_budget_ms: float = 50.0
    auto_activate_population_threshold: int = 100
    force_adaptive: bool = False


class LiveScenarioInjectRequest(BaseModel):
    prompt: Optional[str] = None
    scenario_id: Optional[str] = None
    territory_override: Optional[str] = None
    step_ticks_immediately: int = 0


def _get_runner() -> Any:
    from saltbor.visualization.api import get_controller

    ctrl = get_controller()
    if not hasattr(ctrl, "runner") or ctrl.runner is None:
        raise HTTPException(status_code=500, detail="SimulationRunner not initialized.")
    return ctrl.runner


@router.get("/pipeline/telemetry")
def get_tick_pipeline_telemetry() -> Dict[str, Any]:
    """Return per-stage millisecond latency breakdown and p95 metrics for SimulationRunner.step()."""
    runner = _get_runner()
    return {
        "pipeline": runner.tick_pipeline.get_telemetry_summary(),
        "lod_budget": runner.lod_budget_controller.get_status(),
        "event_bus_total_emitted": getattr(runner.event_bus, "total_emitted_count", 0),
        "event_bus_buffered_count": len(runner.event_bus.event_log),
    }


@router.post("/pipeline/lod_budget")
def configure_lod_budget(req: LODBudgetConfigRequest) -> Dict[str, Any]:
    """Update the AdaptiveLODBudgetController target ms/tick budget and activation threshold."""
    runner = _get_runner()
    ctrl = runner.lod_budget_controller
    ctrl.target_budget_ms = max(1.0, req.target_budget_ms)
    ctrl.auto_activate_population_threshold = max(10, req.auto_activate_population_threshold)
    ctrl.force_adaptive = req.force_adaptive
    return {
        "status": "updated",
        "lod_budget": ctrl.get_status(),
    }


@router.post("/ai/execution/inject_live")
def inject_natural_language_scenario_into_live_runner(req: LiveScenarioInjectRequest) -> Dict[str, Any]:
    """Compile a natural-language scenario (or lookup by scenario_id) and inject it into the live SimulationRunner."""
    runner = _get_runner()

    if req.prompt:
        built = _nl_builder.build_scenario_from_text(
            prompt=req.prompt,
            preferred_canton_override=req.territory_override,
        )
        scen_def = built.scenario_definition
    elif req.scenario_id:
        from saltbor.visualization.api import _ai_controller

        scen_def = _ai_controller.engine.scenarios.get(req.scenario_id)
        if scen_def is None:
            raise HTTPException(status_code=404, detail=f"Scenario '{req.scenario_id}' not found.")
    else:
        raise HTTPException(status_code=400, detail="Must provide either 'prompt' or 'scenario_id'.")

    session = runner.live_scenario_bridge.inject_scenario(scen_def)

    ticks_advanced = 0
    if req.step_ticks_immediately > 0:
        steps = min(96, req.step_ticks_immediately)
        for _ in range(steps):
            runner.step()
        ticks_advanced = steps

    return {
        "status": "injected_into_live_runner",
        "scenario_id": scen_def.scenario_id,
        "name": scen_def.name,
        "community_id": scen_def.community_id,
        "start_tick": session.start_tick,
        "end_tick": session.end_tick,
        "ticks_advanced_immediately": ticks_advanced,
        "current_runner_tick": int(runner.clock.current_tick),
        "live_bridge_status": runner.live_scenario_bridge.get_status_summary(),
    }


@router.get("/ai/execution/live_status")
def get_live_scenario_bridge_status() -> Dict[str, Any]:
    """Return status and double-entry accounting verification of all live injected scenarios."""
    runner = _get_runner()
    return runner.live_scenario_bridge.get_status_summary()


# ============================================================================
# ULTRA-SIMPLE 1-CLICK & NATURAL LANGUAGE CITIZEN SIMULATOR ENDPOINTS
# ============================================================================
from saltbor.simulation.quick_simulator import QuickSimulator

_quick_sim = QuickSimulator()


class QuickSimulationRequest(BaseModel):
    evento: str = "temporal_deslave"
    territorio: Optional[str] = None
    dias: Optional[int] = None
    con_ayuda: Optional[bool] = None
    sincronizar_mapa_en_vivo: bool = True
    seed: int = 42


@router.get("/quick/presets")
def list_quick_simulation_presets() -> list[Dict[str, Any]]:
    """Return 1-click user-friendly simulation presets with icons, titles, and default days."""
    return _quick_sim.list_presets()


@router.post("/quick/run")
def run_quick_simulation_endpoint(req: QuickSimulationRequest) -> Dict[str, Any]:
    """Run an event or simulation from either a 1-click preset ID or plain Spanish text."""
    runner = None
    if req.sincronizar_mapa_en_vivo:
        try:
            runner = _get_runner()
        except Exception:
            runner = None

    return _quick_sim.run(
        prompt_or_preset=req.evento,
        territory=req.territorio,
        days=req.dias,
        include_relief=req.con_ayuda,
        seed=req.seed,
        live_runner=runner,
        live_ticks_to_advance=2,
    )


# ============================================================================
# ULTRA-PRECISE PINPOINT MAP PLACEMENT & MICRO-CATCHMENT ENDPOINTS
# ============================================================================
from saltbor.simulation.pinpoint_simulator import PinpointPlacementSimulator

_pinpoint_sim = PinpointPlacementSimulator()


class PinpointPlaceRequest(BaseModel):
    lat: float = 13.69785
    lon: float = -89.19142
    descripcion: str = "Abrir una pupusería llamada 'El Comal de Oro' con pupusas a $0.85"
    categoria: Optional[str] = None
    nombre: Optional[str] = None
    precio_usd: Optional[float] = None
    capital_inicial_usd: Optional[float] = None
    capacidad: Optional[int] = None
    hora_apertura: Optional[int] = None
    hora_cierre: Optional[int] = None
    radio_m: float = 400.0
    dias: int = 7


@router.get("/quick/inspect_point")
def inspect_exact_map_point(
    lat: float = 13.69785,
    lon: float = -89.19142,
    radius_m: float = 400.0,
) -> Dict[str, Any]:
    """Inspect real OSM streets, POIs, district/municipality, and competing places at exact `(lat, lon)`."""
    try:
        runner = _get_runner()
    except Exception:
        runner = None
    return _pinpoint_sim.inspect_point(lat=lat, lon=lon, radius_m=radius_m, live_runner=runner)


@router.post("/quick/pinpoint")
def place_and_simulate_pinpoint_endpoint(req: PinpointPlaceRequest) -> Dict[str, Any]:
    """Place a highly specific entity at an exact `(lat, lon)` point on the map and simulate micro-outcomes."""
    try:
        runner = _get_runner()
    except Exception:
        runner = None

    return _pinpoint_sim.place_and_simulate(
        lat=req.lat,
        lon=req.lon,
        description=req.descripcion,
        category=req.categoria,
        custom_name=req.nombre,
        unit_price_usd=req.precio_usd,
        initial_capital_usd=req.capital_inicial_usd,
        capacity=req.capacidad,
        opening_hour=req.hora_apertura,
        closing_hour=req.hora_cierre,
        catchment_radius_m=req.radio_m,
        days=req.dias,
        live_runner=runner,
    )


