"""Modular FastAPI Router for SALTBOR Phase 1.17 On-Demand National Territorial Intelligence."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from saltbor.territorial_intelligence.schemas import (
    CatchmentMethod,
    CatchmentScale,
    CommercialCategory,
    DayType,
    TimePeriod,
)
from saltbor.visualization.routers.conversational_studio_router import get_studio_orchestrator

router = APIRouter(prefix="/territorial", tags=["National Territorial Intelligence (Phase 1.17)"])


class OnDemandScenarioRequest(BaseModel):
    location_query: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    polygon_geojson: Optional[Dict[str, Any]] = None
    travel_time_minutes: float = Field(default=15.0, ge=1.0, le=120.0)
    max_expansion_minutes: float = Field(default=30.0, ge=5.0, le=180.0)
    objective: str = "Análisis territorial integral"
    service_type: str = "general"
    catchment_method: Optional[CatchmentMethod] = None
    catchment_scale: Optional[CatchmentScale] = None
    horizon_days: int = Field(default=30, ge=1, le=3650)
    seed: int = 42
    max_active_agents: int = Field(default=40, ge=8, le=250)
    employment_intervention_kind: Optional[str] = None
    compare_with_baseline: bool = False
    allow_partial_data: bool = True


class TerritorialDiscoverRequest(BaseModel):
    location_query: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    polygon_geojson: Optional[Dict[str, Any]] = None
    travel_time_minutes: float = Field(default=15.0, ge=1.0, le=120.0)
    transport_mode: str = "walk"
    sector: str = "general"
    max_expansion_minutes: float = Field(default=30.0, ge=5.0, le=180.0)
    max_expansion_km: float = Field(default=8.0, ge=0.5, le=50.0)
    seed: int = 42


class CensusImportRequest(BaseModel):
    adapter_name: str = "institutional_custom"
    dataset_id: str
    title: str = ""
    source_institution: str = ""
    version: str = "1.0.0"
    published_at: str = "2026-11-23"
    reference_year: int = 2024
    rows: List[Dict[str, Any]] = Field(..., min_length=1)


class CompareLocationsRequest(BaseModel):
    location_queries: List[str] = Field(..., min_length=2, max_length=6)
    objective: str = "Comparación de ubicaciones comerciales"
    service_type: str = "pupuseria"
    horizon_days: int = Field(default=30, ge=1, le=365)
    seed: int = 42


class EmploymentInterventionRequest(BaseModel):
    location_query: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    intervention_kind: str = "NEW_BUSINESSES"
    horizon_days: int = Field(default=30, ge=1, le=365)
    custom_jobs_delta: Optional[int] = None
    seed: int = 42


def _engine():
    return get_studio_orchestrator().on_demand_engine


@router.get("/status")
def get_territorial_engine_status() -> Dict[str, Any]:
    """Return genuine IDLE / active state of OnDemandTerritorialSimulationEngine."""
    return _engine().get_status()


@router.post("/scenarios")
def create_on_demand_scenario(req: OnDemandScenarioRequest) -> Dict[str, Any]:
    """Resolve location, assess coverage, activate population, and run an on-demand territorial scenario."""
    orch = get_studio_orchestrator()
    rec = orch.on_demand_engine.create_and_run_scenario(
        location_query=req.location_query,
        lat=req.lat,
        lon=req.lon,
        polygon_geojson=req.polygon_geojson,
        travel_time_minutes=req.travel_time_minutes,
        max_expansion_minutes=req.max_expansion_minutes,
        objective=req.objective,
        service_type=req.service_type,
        catchment_method=req.catchment_method,
        catchment_scale=req.catchment_scale,
        horizon_days=req.horizon_days,
        seed=req.seed,
        max_active_agents=req.max_active_agents,
        employment_intervention_kind=req.employment_intervention_kind,
        compare_with_baseline=req.compare_with_baseline,
        allow_partial_data=req.allow_partial_data,
    )
    orch.persistence.save_territorial_scenario(rec)
    orch.persistence.save_population_assignments(
        orch.on_demand_engine.population_dist_engine.get_all_spatial_assignments()
    )
    return rec.model_dump(mode="json")


@router.get("/scenarios")
def list_on_demand_scenarios() -> Dict[str, Any]:
    """List scenarios created during the active session."""
    scenarios = _engine().list_scenarios()
    return {
        "count": len(scenarios),
        "scenarios": [
            {
                "scenario_id": s.scenario_id,
                "state": s.state.value,
                "query": s.query,
                "objective": s.objective,
                "is_historic_center_benchmark": s.is_historic_center_benchmark,
                "resolved_location": s.resolved_location,
                "seed": s.seed,
                "created_at": s.created_at,
            }
            for s in scenarios
        ],
    }


@router.get("/scenarios/{scenario_id}")
def get_on_demand_scenario(scenario_id: str) -> Dict[str, Any]:
    """Retrieve complete scenario record, lifecycle history, and A–G evidence package."""
    eng = _engine()
    rec = eng.get_scenario(scenario_id)
    if rec is not None:
        return rec.model_dump(mode="json")
    persisted = get_studio_orchestrator().persistence.load_territorial_scenario(scenario_id)
    if persisted is not None:
        return persisted
    raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")


@router.post("/scenarios/{scenario_id}/pause")
def pause_on_demand_scenario(scenario_id: str) -> Dict[str, Any]:
    if not _engine().pause_scenario(scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
    return {"scenario_id": scenario_id, "state": "PAUSED"}


@router.post("/scenarios/{scenario_id}/resume")
def resume_on_demand_scenario(scenario_id: str) -> Dict[str, Any]:
    if not _engine().resume_scenario(scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
    return {"scenario_id": scenario_id, "state": "READY"}


@router.post("/scenarios/{scenario_id}/cancel")
def cancel_on_demand_scenario(scenario_id: str) -> Dict[str, Any]:
    if not _engine().cancel_scenario(scenario_id):
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
    return {"scenario_id": scenario_id, "state": "CANCELLED"}


@router.post("/scenarios/{scenario_id}/rerun")
def rerun_on_demand_scenario(scenario_id: str, seed: Optional[int] = None) -> Dict[str, Any]:
    try:
        rec = _engine().rerun_scenario(scenario_id, seed=seed)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")
    get_studio_orchestrator().persistence.save_territorial_scenario(rec)
    return rec.model_dump(mode="json")


@router.post("/scenarios/compare")
def compare_territorial_locations(req: CompareLocationsRequest) -> Dict[str, Any]:
    """Run independent scenarios across multiple Salvadoran locations and compare indicators."""
    return _engine().compare_locations(
        location_queries=req.location_queries,
        objective=req.objective,
        service_type=req.service_type,
        horizon_days=req.horizon_days,
        seed=req.seed,
    )


@router.post("/benchmark/historic-center")
def run_historic_center_benchmark(seed: int = 42) -> Dict[str, Any]:
    """Explicitly run the preserved Historic Center benchmark scenario (never default)."""
    rec = _engine().create_historic_center_benchmark_scenario(seed=seed)
    get_studio_orchestrator().persistence.save_territorial_scenario(rec)
    return rec.model_dump(mode="json")


@router.get("/buildings")
def get_building_intelligence(
    query: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: float = Query(default=1.0, ge=0.1, le=5.0),
) -> Dict[str, Any]:
    """Inspect real OSM built environment classification, provenance & area around a location."""
    eng = _engine()
    ctx = eng.territorial_engine.resolve_location(query=query, lat=lat, lon=lon, radius_km=radius_km)
    if not ctx.resolved:
        raise HTTPException(status_code=400, detail=ctx.ambiguity_reason or "Ubicación no resuelta.")
    report = eng.building_engine.analyze_buildings(ctx.lat, ctx.lon, radius_km=radius_km)
    return report.model_dump(mode="json")


@router.get("/commerce")
def get_commercial_intelligence(
    query: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: float = Query(default=1.5, ge=0.2, le=6.0),
    category: Optional[CommercialCategory] = None,
) -> Dict[str, Any]:
    """Inspect confirmed real establishments, unverified commercial buildings, and concentration metrics."""
    eng = _engine()
    ctx = eng.territorial_engine.resolve_location(query=query, lat=lat, lon=lon, radius_km=radius_km)
    if not ctx.resolved:
        raise HTTPException(status_code=400, detail=ctx.ambiguity_reason or "Ubicación no resuelta.")
    bldg = eng.building_engine.analyze_buildings(ctx.lat, ctx.lon, radius_km=min(1.5, radius_km))
    report = eng.economic_context_engine.build_economic_context(
        context=ctx,
        radius_km=radius_km,
        building_report=bldg,
        category_filter=category,
    )
    return report.model_dump(mode="json")


@router.get("/catchment")
def get_catchment_analysis(
    query: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    service_type: str = "general",
    method: Optional[CatchmentMethod] = None,
    scale: Optional[CatchmentScale] = None,
) -> Dict[str, Any]:
    """Compute adaptive area of influence with network circuity & natural barrier detection."""
    eng = _engine()
    ctx = eng.territorial_engine.resolve_location(query=query, lat=lat, lon=lon)
    if not ctx.resolved:
        raise HTTPException(status_code=400, detail=ctx.ambiguity_reason or "Ubicación no resuelta.")
    res = eng.catchment_engine.analyze_catchment(
        context=ctx,
        service_type=service_type,
        method=method,
        scale=scale,
    )
    return res.model_dump(mode="json")


@router.get("/mobility")
def get_mobility_flow_analysis(
    query: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    time_period: TimePeriod = TimePeriod.MORNING,
    day_type: DayType = DayType.WEEKDAY,
) -> Dict[str, Any]:
    """Analyze 10-role non-double-counted human mobility flows with explicit evidence tiers."""
    eng = _engine()
    ctx = eng.territorial_engine.resolve_location(query=query, lat=lat, lon=lon)
    if not ctx.resolved:
        raise HTTPException(status_code=400, detail=ctx.ambiguity_reason or "Ubicación no resuelta.")
    eng.population_dist_engine.activate_for_territory(ctx, max_active_agents=30, seed=42)
    humans = eng.population_manager.get_active_humans_for_district(ctx.district_id)
    catchment = eng.catchment_engine.analyze_catchment(ctx, service_type="general")
    comm = eng.economic_context_engine.build_economic_context(ctx, radius_km=catchment.effective_radius_km)
    flow = eng.mobility_engine.analyze_mobility(
        context=ctx,
        humans=humans,
        catchment=catchment,
        commercial_report=comm,
        time_period=time_period,
        day_type=day_type,
    )
    return flow.model_dump(mode="json")


@router.get("/employment")
def get_employment_analysis(
    query: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, Any]:
    """Analyze 5-tier territorial employment opportunities without fabricating vacancies."""
    eng = _engine()
    ctx = eng.territorial_engine.resolve_location(query=query, lat=lat, lon=lon)
    if not ctx.resolved:
        raise HTTPException(status_code=400, detail=ctx.ambiguity_reason or "Ubicación no resuelta.")
    comm = eng.economic_context_engine.build_economic_context(ctx)
    report = eng.labor_engine.analyze_labor_market(context=ctx, commercial_report=comm)
    return report.model_dump(mode="json")


@router.post("/employment/intervention")
def simulate_employment_intervention_endpoint(req: EmploymentInterventionRequest) -> Dict[str, Any]:
    """Simulate employment shock/intervention with commuter competition & ledger conservation."""
    eng = _engine()
    ctx = eng.territorial_engine.resolve_location(query=req.location_query, lat=req.lat, lon=req.lon)
    if not ctx.resolved:
        raise HTTPException(status_code=400, detail=ctx.ambiguity_reason or "Ubicación no resuelta.")
    eng.population_dist_engine.activate_for_territory(ctx, max_active_agents=32, seed=req.seed)
    humans = eng.population_manager.get_active_humans_for_district(ctx.district_id)
    res = eng.employment_opportunity_engine.simulate_employment_intervention(
        intervention_kind=req.intervention_kind,
        context=ctx,
        humans=humans,
        horizon_days=req.horizon_days,
        custom_jobs_delta=req.custom_jobs_delta,
    )
    return res.model_dump(mode="json")


@router.get("/coverage")
def get_national_coverage_registry(department_code: Optional[str] = None) -> Dict[str, Any]:
    """Return national territorial coverage assessment across all 14 departments & 262 districts."""
    summary = _engine().coverage_registry.get_national_summary()
    if department_code:
        code = department_code.upper()
        depts = [d for d in summary.department_summaries if d.department_code == code]
        dists = [d for d in summary.district_records if d.department_code == code]
        return {
            "department_code": code,
            "departments": [d.model_dump(mode="json") for d in depts],
            "districts": [d.model_dump(mode="json") for d in dists],
        }
    return {
        "total_departments": summary.total_departments,
        "total_districts": summary.total_districts,
        "tier_counts": summary.tier_counts,
        "department_summaries": [d.model_dump(mode="json") for d in summary.department_summaries],
        "generated_at": summary.generated_at,
    }


@router.get("/coverage/geojson")
def get_national_coverage_geojson() -> Dict[str, Any]:
    """Return GeoJSON FeatureCollection for national coverage tier visualization."""
    return _engine().coverage_registry.export_coverage_geojson()


@router.get("/census/datasets")
def list_integrated_census_datasets() -> Dict[str, Any]:
    """List integrated official census, EHPM, MINED, MINSAL, and institutional datasets."""
    pipe = _engine().preparation_pipeline
    datasets = pipe.census_engine.list_datasets()
    return {
        "count": len(datasets),
        "datasets": [d.model_dump(mode="json") for d in datasets],
    }


@router.post("/census/import")
def import_census_records_endpoint(req: CensusImportRequest) -> Dict[str, Any]:
    """Import normalized statistical or institutional rows via adapter with PII guard."""
    orch = get_studio_orchestrator()
    pipe = orch.on_demand_engine.preparation_pipeline
    try:
        res = pipe.census_engine.import_records(
            rows=req.rows,
            adapter_name=req.adapter_name,
            dataset_id=req.dataset_id,
            title=req.title,
            source_institution=req.source_institution,
            version=req.version,
            published_at=req.published_at,
            reference_year=req.reference_year,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    meta = next((d for d in pipe.census_engine.list_datasets() if d.dataset_id == res.dataset_id), None)
    if meta is not None:
        orch.persistence.save_census_dataset_meta(meta)
    return res.model_dump(mode="json")


@router.post("/discover")
def discover_territory_and_prepare_population(req: TerritorialDiscoverRequest) -> Dict[str, Any]:
    """Run full Phase 1.18 discovery, 3-scale expansion, census/SAE, allocation & calibration."""
    from saltbor.census_intelligence.schemas import TerritorialSelectionInput

    orch = get_studio_orchestrator()
    pipe = orch.on_demand_engine.preparation_pipeline
    sel = TerritorialSelectionInput(
        query=req.location_query,
        lat=req.lat,
        lon=req.lon,
        polygon_geojson=req.polygon_geojson,
        travel_time_minutes=req.travel_time_minutes,
        transport_mode=req.transport_mode if req.transport_mode in ("walk", "drive", "mixed") else "walk",
        sector=req.sector,
        max_expansion_minutes=req.max_expansion_minutes,
        max_expansion_km=req.max_expansion_km,
        seed=req.seed,
    )
    try:
        prep = pipe.prepare(sel, max_sample_households=280)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    orch.persistence.save_synthetic_population_batch(prep)

    # Spatial aggregation (grid clusters ~100m) so map is never saturated with thousands of markers
    grid_clusters: Dict[tuple[int, int], Dict[str, Any]] = {}
    for hh in prep.population_batch.households:
        gx = int(round(hh.home_lat / 0.0009))
        gy = int(round(hh.home_lon / 0.0009))
        cell = grid_clusters.setdefault(
            (gx, gy),
            {"lat_sum": 0.0, "lon_sum": 0.0, "count": 0, "households": 0.0, "persons": 0.0, "income_sum": 0.0},
        )
        w = float(hh.expansion_weight)
        cell["lat_sum"] += hh.home_lat
        cell["lon_sum"] += hh.home_lon
        cell["count"] += 1
        cell["households"] += w
        cell["persons"] += len(hh.member_ids) * w
        cell["income_sum"] += hh.estimated_monthly_income_usd * w

    pop_cluster_features = []
    for cell in grid_clusters.values():
        n = max(1, cell["count"])
        pop_cluster_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(cell["lon_sum"] / n, 6), round(cell["lat_sum"] / n, 6)]},
            "properties": {
                "kind": "population_cluster",
                "households": int(round(cell["households"])),
                "persons": int(round(cell["persons"])),
                "avg_income_usd": round(cell["income_sum"] / max(1.0, cell["households"]), 2),
                "evidence_classification": prep.calibration.evidence_classification.value,
            },
        })

    exp = prep.discovery.expansion
    areas_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": exp.contextual_area.geometry_geojson,
                "properties": {
                    "zone_tier": "CONTEXTUAL_AREA",
                    "label": exp.contextual_area.label,
                    "area_km2": exp.contextual_area.area_km2,
                    "travel_time_minutes": exp.contextual_area.travel_time_minutes,
                    "barriers": exp.contextual_area.barriers_detected,
                },
            },
            {
                "type": "Feature",
                "geometry": exp.influence_area.geometry_geojson,
                "properties": {
                    "zone_tier": "INFLUENCE_AREA",
                    "label": exp.influence_area.label,
                    "area_km2": exp.influence_area.area_km2,
                    "travel_time_minutes": exp.influence_area.travel_time_minutes,
                    "circuity_factor": exp.influence_area.circuity_factor,
                },
            },
            {
                "type": "Feature",
                "geometry": exp.primary_area.geometry_geojson,
                "properties": {
                    "zone_tier": "PRIMARY_AREA",
                    "label": exp.primary_area.label,
                    "area_km2": exp.primary_area.area_km2,
                    "allocated_population": prep.allocation.allocated_population_target,
                    "allocated_households": prep.allocation.allocated_households_target,
                },
            },
        ],
    }

    infra_features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [e.lon, e.lat]},
            "properties": {
                "entity_id": e.entity_id,
                "name": e.name,
                "domain": e.domain,
                "subtype": e.subtype,
                "zone_tier": e.zone_tier.value,
                "distance_m": e.distance_m,
                "estimated_walk_min": e.estimated_walk_min,
                "verification_status": e.verification_status.value,
                "confirmed_levels": e.confirmed_levels,
                "levels_evidence_status": e.levels_evidence_status,
                "capacity_evidence_type": e.capacity_evidence_type.value,
                "source": e.source,
            },
        }
        for e in prep.infrastructure.entities[:220]
    ]

    return {
        "preparation_id": prep.preparation_id,
        "elapsed_ms": prep.elapsed_ms,
        "discovery": prep.discovery.model_dump(mode="json"),
        "census_query": prep.census_query.model_dump(mode="json"),
        "allocation": prep.allocation.model_dump(mode="json", exclude={"building_anchors"}),
        "calibration": prep.calibration.model_dump(mode="json"),
        "certificate": prep.certificate.model_dump(mode="json"),
        "sector_context": prep.sector_context.model_dump(mode="json"),
        "mobility_accessibility": prep.mobility_accessibility.model_dump(mode="json"),
        "infrastructure_summary": {
            "counts_by_domain": prep.infrastructure.counts_by_domain,
            "counts_by_zone_tier": prep.infrastructure.counts_by_zone_tier,
            "counts_by_verification_status": prep.infrastructure.counts_by_verification_status,
            "duplicates_merged": prep.infrastructure.duplicates_merged,
            "non_omission_notice": prep.infrastructure.non_omission_notice,
        },
        "provenanced_indicators": [i.model_dump(mode="json") for i in prep.provenanced_indicators],
        "provenance_integrity": prep.provenance_integrity,
        "areas_geojson": areas_geojson,
        "population_clusters_geojson": {"type": "FeatureCollection", "features": pop_cluster_features},
        "infrastructure_geojson": {"type": "FeatureCollection", "features": infra_features},
    }


@router.post("/validation/santa-tecla-school")
def run_santa_tecla_validation_endpoint(seed: int = 42) -> Dict[str, Any]:
    """Execute Section 17 Santa Tecla residential 4-scenario school evaluation."""
    from saltbor.census_intelligence.validation_scenario import run_santa_tecla_school_validation

    pipe = _engine().preparation_pipeline
    return run_santa_tecla_school_validation(pipeline=pipe, seed=seed)
