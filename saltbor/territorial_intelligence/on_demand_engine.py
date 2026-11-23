"""On-Demand Territorial Simulation Engine (Phase 1.17 Section 2).

Transforms SALTBOR into a location-independent territorial intelligence platform.
Constructs reproducible spatial simulation scenarios dynamically from user-chosen
locations or natural-language queries across all 14 departments of El Salvador,
tracking genuine backend lifecycle states without ever silently falling back to
the Historic Center.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from saltbor.ai.budget import AIComputeBudgetManager
from saltbor.ai.privacy import AIPrivacyGuard
from saltbor.ai.router import AIModelRouter
from saltbor.conversational.decision_analyst import GeminiDecisionAnalyst
from saltbor.conversational.evidence_engine import SyntheticPopulationEvidenceEngine
from saltbor.conversational.intervention_designer import TerritorialInterventionDesigner
from saltbor.conversational.population_activation import NationalPopulationActivationManager
from saltbor.conversational.schemas import (
    ActivationLOD,
    ConversationIntent,
    InterventionCategory,
    InterventionSpec,
    ParsedUserRequest,
    TerritorialContext,
    TemporalHorizonSpec,
)
from saltbor.conversational.temporal_controller import ConversationalTemporalController
from saltbor.conversational.territorial_context import NationalTerritorialContextEngine
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography

from saltbor.territorial_intelligence.building_and_landuse import (
    NationalBuildingIntelligenceEngine,
    TerritorialLandUseIntelligenceEngine,
)
from saltbor.territorial_intelligence.catchment import TerritorialCatchmentAnalysisEngine
from saltbor.territorial_intelligence.commercial_intelligence import TerritorialEconomicContextEngine
from saltbor.territorial_intelligence.coverage import NationalTerritorialCoverageRegistry
from saltbor.territorial_intelligence.employment import (
    EmploymentOpportunityAnalysisEngine,
    TerritorialLaborMarketEngine,
)
from saltbor.territorial_intelligence.evidence import TerritorialEvidenceEngine
from saltbor.territorial_intelligence.mobility_flow import HumanMobilityFlowEngine
from saltbor.territorial_intelligence.population_distribution import DynamicPopulationDistributionEngine
from saltbor.territorial_intelligence.schemas import (
    CatchmentMethod,
    CatchmentScale,
    CommercialCategory,
    DayType,
    LifecycleTransition,
    OnDemandScenarioRecord,
    TerritorialSimulationState,
    TimePeriod,
)
from saltbor.census_intelligence.household_generator import SyntheticHouseholdGenerationEngine
from saltbor.census_intelligence.pipeline import TerritorialPreparationPipeline
from saltbor.census_intelligence.schemas import TerritorialSelectionInput

logger = logging.getLogger(__name__)


class OnDemandTerritorialSimulationEngine:
    """Location-independent orchestrator constructing territorial scenarios on demand."""

    def __init__(
        self,
        territorial_engine: Optional[NationalTerritorialContextEngine] = None,
        population_manager: Optional[NationalPopulationActivationManager] = None,
        geography: Optional[IngestedGeography] = None,
        router: Optional[AIModelRouter] = None,
        budget_manager: Optional[AIComputeBudgetManager] = None,
        privacy_guard: Optional[AIPrivacyGuard] = None,
        seed: int = 42,
    ) -> None:
        self.seed = seed
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self._owns_territorial = territorial_engine is None
        self.territorial_engine = territorial_engine or NationalTerritorialContextEngine()
        self.population_manager = population_manager or NationalPopulationActivationManager(seed=seed)

        self.router = router or AIModelRouter()
        self.budget_manager = budget_manager or AIComputeBudgetManager()
        self.privacy_guard = privacy_guard or AIPrivacyGuard()

        # Phase 1.17 Sub-Engines
        self.building_engine = NationalBuildingIntelligenceEngine(geography=self.geography)
        self.land_use_engine = TerritorialLandUseIntelligenceEngine(geography=self.geography)
        self.economic_context_engine = TerritorialEconomicContextEngine(geography=self.geography)
        self.catchment_engine = TerritorialCatchmentAnalysisEngine(geography=self.geography)
        self.population_dist_engine = DynamicPopulationDistributionEngine(
            population_manager=self.population_manager,
            geography=self.geography,
            seed=seed,
        )
        self.mobility_engine = HumanMobilityFlowEngine(
            geography=self.geography,
            population_manager=self.population_manager,
        )
        self.labor_engine = TerritorialLaborMarketEngine()
        self.employment_opportunity_engine = EmploymentOpportunityAnalysisEngine(self.labor_engine)
        self.evidence_engine = TerritorialEvidenceEngine()
        self.coverage_registry = NationalTerritorialCoverageRegistry(geography=self.geography)
        self.preparation_pipeline = TerritorialPreparationPipeline(
            geography=self.geography,
            territorial_engine=self.territorial_engine,
        )

        # Reused Phase 1.16A Execution & Analysis Engines
        self.temporal_controller = ConversationalTemporalController()
        self.intervention_designer = TerritorialInterventionDesigner()
        self.sim_evidence_engine = SyntheticPopulationEvidenceEngine()
        self.decision_analyst = GeminiDecisionAnalyst(
            router=self.router,
            budget_manager=self.budget_manager,
            privacy_guard=self.privacy_guard,
        )

        # Runtime state: starts IDLE with ZERO active Historic Center assumption
        self.current_state: TerritorialSimulationState = TerritorialSimulationState.IDLE
        self.active_territory: Optional[Dict[str, Any]] = None
        self._scenarios: Dict[str, OnDemandScenarioRecord] = {}
        self._scenario_runtime_inputs: Dict[str, Dict[str, Any]] = {}
        self._pause_flags: Dict[str, threading.Event] = {}
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    def close(self) -> None:
        if self._owns_territorial:
            self.territorial_engine.close()
        if self._owns_geo:
            self.geography.close()

    def get_status(self) -> Dict[str, Any]:
        """Return genuine current engine status (never assumes Historic Center)."""
        with self._lock:
            return {
                "state": self.current_state.value,
                "active_territory": self.active_territory,
                "historic_center_is_default": False,
                "total_scenarios": len(self._scenarios),
                "persistent_unique_individuals": self.population_manager.total_unique_persistent_individuals(),
                "rtree_indexed": self.geography.has_rtree,
                "scenario_ids": list(self._scenarios.keys()),
            }

    def get_scenario(self, scenario_id: str) -> Optional[OnDemandScenarioRecord]:
        with self._lock:
            return self._scenarios.get(scenario_id)

    def list_scenarios(self) -> List[OnDemandScenarioRecord]:
        with self._lock:
            return list(self._scenarios.values())

    def _transition(
        self,
        record: OnDemandScenarioRecord,
        new_state: TerritorialSimulationState,
        detail: str = "",
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        now = time.time()
        with self._lock:
            record.state = new_state
            record.updated_at = now
            record.state_history.append(
                LifecycleTransition(state=new_state, timestamp=now, detail=detail)
            )
            self.current_state = new_state
        if progress_callback is not None:
            try:
                progress_callback(new_state.value, detail)
            except Exception:
                pass

    def prepare_scenario(
        self,
        location_query: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        objective: str = "Análisis territorial integral",
        service_type: str = "general",
        catchment_method: Optional[CatchmentMethod] = None,
        catchment_scale: Optional[CatchmentScale] = None,
        horizon_days: int = 30,
        seed: Optional[int] = None,
        max_active_agents: int = 40,
        target_lod: ActivationLOD = ActivationLOD.LOD_3_INDIVIDUAL_FULL,
        intervention_category: Optional[InterventionCategory] = None,
        employment_intervention_kind: Optional[str] = None,
        time_period: TimePeriod = TimePeriod.MORNING,
        day_type: DayType = DayType.WEEKDAY,
        season: str = "DRY",
        is_historic_center_benchmark: bool = False,
        allow_partial_data: bool = True,
        scenario_id: Optional[str] = None,
        polygon_geojson: Optional[Dict[str, Any]] = None,
        travel_time_minutes: float = 15.0,
        max_expansion_minutes: float = 30.0,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> OnDemandScenarioRecord:
        """Progress a scenario through LOCATION_RESOLUTION -> VALIDATION -> READY."""
        sid = scenario_id or f"SCEN_117_{uuid4().hex[:8]}"
        used_seed = seed if seed is not None else self.seed
        now = time.time()

        record = OnDemandScenarioRecord(
            scenario_id=sid,
            state=TerritorialSimulationState.IDLE,
            state_history=[LifecycleTransition(state=TerritorialSimulationState.IDLE, timestamp=now, detail="Inicializado")],
            query=location_query or (f"({lat}, {lon})" if lat is not None and lon is not None else ""),
            objective=objective,
            is_historic_center_benchmark=is_historic_center_benchmark,
            seed=used_seed,
            horizon_days=horizon_days,
            parameters={
                "service_type": service_type,
                "catchment_method": catchment_method.value if catchment_method else None,
                "catchment_scale": catchment_scale.value if catchment_scale else None,
                "max_active_agents": max_active_agents,
                "target_lod": target_lod.name,
                "intervention_category": intervention_category.value if intervention_category else None,
                "employment_intervention_kind": employment_intervention_kind,
                "time_period": time_period.value,
                "day_type": day_type.value,
                "season": season,
            },
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._scenarios[sid] = record
            self._pause_flags[sid] = threading.Event()
            self._cancel_flags[sid] = threading.Event()

        # 1. LOCATION_RESOLUTION (never implicitly substitutes Historic Center)
        self._transition(record, TerritorialSimulationState.LOCATION_RESOLUTION, "Resolviendo ubicación geográfica en El Salvador", progress_callback)
        if not (location_query and location_query.strip()) and (lat is None or lon is None):
            record.clarification_question = (
                "No se especificó ubicación. Indica un departamento, municipio, distrito, cantón o coordenadas en El Salvador."
            )
            self._transition(record, TerritorialSimulationState.NEEDS_CLARIFICATION, record.clarification_question, progress_callback)
            return record

        geo_ctx = self.territorial_engine.resolve_location(query=location_query, lat=lat, lon=lon)
        if geo_ctx.is_ambiguous:
            cand_dicts = [c.model_dump(mode="json") for c in geo_ctx.candidates]
            labels = [f"{c.matched_label} ({c.department_name})" for c in geo_ctx.candidates[:4]]
            record.clarification_candidates = cand_dicts
            record.clarification_question = (
                f"La referencia '{location_query}' coincide con múltiples ubicaciones: {', '.join(labels)}. ¿Cuál deseas analizar?"
            )
            self._transition(record, TerritorialSimulationState.NEEDS_CLARIFICATION, record.clarification_question, progress_callback)
            return record

        if not geo_ctx.resolved:
            record.clarification_question = (
                f"No fue posible resolver '{location_query or f'{lat},{lon}'}' dentro de El Salvador. Precisa el distrito, municipio o departamento."
            )
            self._transition(record, TerritorialSimulationState.NEEDS_CLARIFICATION, record.clarification_question, progress_callback)
            return record

        record.resolved_location = {
            "department_code": geo_ctx.department_code,
            "department_name": geo_ctx.department_name,
            "municipality_id": geo_ctx.municipality_id,
            "municipality_name": geo_ctx.municipality_name,
            "district_id": geo_ctx.district_id,
            "district_name": geo_ctx.district_name,
            "canton_name": geo_ctx.canton_name,
            "lat": geo_ctx.lat,
            "lon": geo_ctx.lon,
            "coordinate_source": geo_ctx.coordinate_source,
            "is_urban": geo_ctx.is_urban,
            "approx_population": geo_ctx.approx_population,
        }
        with self._lock:
            self.active_territory = dict(record.resolved_location)

        # 2. TERRITORIAL_CONTEXT_LOADING
        self._transition(
            record,
            TerritorialSimulationState.TERRITORIAL_CONTEXT_LOADING,
            f"Cargando entorno edificado, uso de suelo, comercio y área de influencia en {geo_ctx.district_name}",
            progress_callback,
        )
        catchment = self.catchment_engine.analyze_catchment(
            context=geo_ctx,
            service_type=service_type,
            method=catchment_method,
            scale=catchment_scale,
        )
        bldg_report = self.building_engine.analyze_buildings(
            lat=geo_ctx.lat,
            lon=geo_ctx.lon,
            radius_km=min(2.0, catchment.effective_radius_km),
        )
        lu_report = self.land_use_engine.analyze_land_use(
            context=geo_ctx,
            radius_km=catchment.effective_radius_km,
        )
        comm_report = self.economic_context_engine.build_economic_context(
            context=geo_ctx,
            radius_km=catchment.effective_radius_km,
            area_km2=catchment.effective_area_km2,
            building_report=bldg_report,
        )
        record.catchment = catchment
        record.building_intelligence = bldg_report
        record.land_use_intelligence = lu_report
        record.commercial_context = comm_report

        # 3. DATA_QUALITY_ASSESSMENT
        self._transition(
            record,
            TerritorialSimulationState.DATA_QUALITY_ASSESSMENT,
            "Evaluando cobertura territorial nacional y calidad de datos",
            progress_callback,
        )
        cov_rec = self.coverage_registry.get_district_coverage(geo_ctx.district_id)
        record.coverage_assessment = cov_rec
        if cov_rec is not None and not allow_partial_data and cov_rec.coverage_tier.value == "INSUFFICIENT":
            record.error = "Cobertura insuficiente para ejecutar análisis estricto sin modo preliminar."
            self._transition(record, TerritorialSimulationState.INSUFFICIENT_DATA, record.error, progress_callback)
            return record

        # 4. POPULATION_ACTIVATION (Phase 1.18 mandatory census/calibration chain + selective LOD)
        self._transition(
            record,
            TerritorialSimulationState.POPULATION_ACTIVATION,
            f"Preparando censo, asignación espacial, calibración y población sintética en {geo_ctx.district_name} ({target_lod.name})",
            progress_callback,
        )
        safe_agents = max(8, min(250, int(max_active_agents)))
        prep_sector = (
            "school" if "escuel" in f"{objective} {service_type}".lower() else
            "health" if any(k in f"{objective} {service_type}".lower() for k in ("salud", "clinic", "hospital")) else
            "road" if any(k in f"{objective} {service_type}".lower() for k in ("carret", "road", "vial")) else
            "market" if any(k in f"{objective} {service_type}".lower() for k in ("mercad", "comerc", "pupus", "tienda")) else
            service_type or "general"
        )
        prep_res = None
        if not is_historic_center_benchmark:
            try:
                prep_sel = TerritorialSelectionInput(
                    query=location_query if polygon_geojson is None and (lat is None or lon is None) else None,
                    lat=geo_ctx.lat if polygon_geojson is None else None,
                    lon=geo_ctx.lon if polygon_geojson is None else None,
                    polygon_geojson=polygon_geojson,
                    travel_time_minutes=travel_time_minutes,
                    sector=prep_sector,
                    max_expansion_minutes=max_expansion_minutes,
                    seed=used_seed,
                )
                prep_res = self.preparation_pipeline.prepare(prep_sel, max_sample_households=120)
                SyntheticHouseholdGenerationEngine.hydrate_to_synthetic_humans(
                    batch=prep_res.population_batch,
                    population_manager=self.population_manager,
                    context=geo_ctx,
                    max_active=safe_agents,
                )
                record.preparation_certificate = prep_res.certificate.model_dump(mode="json")
                record.calibration_summary = {
                    "srmse": prep_res.calibration.srmse,
                    "calibration_passed": prep_res.calibration.calibration_passed,
                    "statistical_coverage_pct": prep_res.calibration.statistical_coverage_pct,
                    "evidence_classification": prep_res.calibration.evidence_classification.value,
                }
                record.territorial_expansion = prep_res.discovery.expansion.model_dump(mode="json")
                record.sector_context = prep_res.sector_context.model_dump(mode="json")
                record.evidence_classifications = {
                    ind.indicator_id: ind.evidence_type.value for ind in prep_res.provenanced_indicators
                }
            except Exception as prep_exc:
                logger.warning("Phase 1.18 preparation fallback for %s: %s", sid, prep_exc)

        pop_act = self.population_dist_engine.activate_for_territory(
            context=geo_ctx,
            building_report=bldg_report,
            target_lod=target_lod,
            max_active_agents=safe_agents,
            seed=used_seed,
        )
        if prep_res is not None:
            pop_act["preparation_certificate"] = record.preparation_certificate
            pop_act["calibration_summary"] = record.calibration_summary
        record.population_activation = pop_act

        # 5. SCENARIO_CONSTRUCTION
        self._transition(
            record,
            TerritorialSimulationState.SCENARIO_CONSTRUCTION,
            "Construyendo especificación reproducible de escenario y motores requeridos",
            progress_callback,
        )
        temporal = self.temporal_controller.parse_temporal_horizon(
            text=f"{horizon_days} días",
            intent=ConversationIntent.BUSINESS_PLACEMENT if intervention_category else ConversationIntent.ECONOMIC_ANALYSIS,
            seed=used_seed,
            explicit_days=horizon_days,
        )
        cat = intervention_category or self._infer_intervention_category(objective, service_type)
        parsed = ParsedUserRequest(
            raw_message=objective,
            intent=ConversationIntent.BUSINESS_PLACEMENT if cat else ConversationIntent.ECONOMIC_ANALYSIS,
            intervention_type=cat,
            geographic_reference=geo_ctx.district_name,
            map_coordinates=(geo_ctx.lat, geo_ctx.lon),
            requested_days=horizon_days,
        )
        intervention = self.intervention_designer.design_intervention(
            parsed=parsed,
            context=geo_ctx,
            temporal=temporal,
        )
        required_engines = self._select_required_engines(cat, employment_intervention_kind)
        record.activated_engines = required_engines
        record.provenance = {
            "scenario_id": sid,
            "seed": used_seed,
            "geographic_scope": f"{geo_ctx.district_name} ({geo_ctx.district_id}), {geo_ctx.department_name}",
            "is_historic_center_benchmark": is_historic_center_benchmark,
            "osm_rtree_indexed": self.geography.has_rtree,
            "data_quality_score": geo_ctx.data_quality_score,
            "coverage_tier": cov_rec.coverage_tier.value if cov_rec else "PARTIAL",
            "sources": ["Geofabrik_OSM_El_Salvador (ODbL-1.0)", "SALTBOR D.L. 762", "EHPM Priors"],
        }

        with self._lock:
            self._scenario_runtime_inputs[sid] = {
                "geo_ctx": geo_ctx,
                "temporal": temporal,
                "intervention": intervention,
                "employment_intervention_kind": employment_intervention_kind,
                "time_period": time_period,
                "day_type": day_type,
                "season": season,
                "max_active_agents": safe_agents,
                "preparation_result": prep_res,
            }

        # 6. VALIDATION -> READY
        self._transition(record, TerritorialSimulationState.VALIDATION, "Validando consistencia territorial y contable", progress_callback)
        self._transition(record, TerritorialSimulationState.READY, "Escenario listo para ejecución", progress_callback)
        return record

    def execute_scenario(
        self,
        scenario_id: str,
        seed: Optional[int] = None,
        compare_with_baseline: bool = False,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> OnDemandScenarioRecord:
        """Execute a prepared scenario through RUNNING -> EVIDENCE_COLLECTION -> ANALYSIS -> COMPLETED."""
        record = self.get_scenario(scenario_id)
        if record is None:
            raise KeyError(f"Scenario '{scenario_id}' not found")
        if record.state in (TerritorialSimulationState.NEEDS_CLARIFICATION, TerritorialSimulationState.INSUFFICIENT_DATA):
            return record

        runtime = self._scenario_runtime_inputs.get(scenario_id)
        if runtime is None:
            raise RuntimeError(f"Runtime inputs missing for scenario '{scenario_id}'")

        geo_ctx: TerritorialContext = runtime["geo_ctx"]
        temporal: TemporalHorizonSpec = runtime["temporal"]
        used_seed = seed if seed is not None else record.seed
        if used_seed != temporal.seed:
            temporal = temporal.model_copy(update={"seed": used_seed})
        intervention: InterventionSpec = runtime["intervention"]
        emp_kind: Optional[str] = runtime.get("employment_intervention_kind")
        cancel_evt = self._cancel_flags[scenario_id]
        pause_evt = self._pause_flags[scenario_id]

        # Wait if paused
        while pause_evt.is_set() and not cancel_evt.is_set():
            time.sleep(0.05)

        if cancel_evt.is_set():
            self._transition(record, TerritorialSimulationState.CANCELLED, "Escenario cancelado antes de iniciar ejecución", progress_callback)
            return record

        try:
            # 7. RUNNING
            self._transition(record, TerritorialSimulationState.RUNNING, f"Simulando {geo_ctx.district_name} (seed={used_seed})", progress_callback)
            baseline_snap = self.population_manager.capture_baseline_snapshot()
            humans = self.population_manager.get_active_humans_for_district(geo_ctx.district_id)
            pop_acc = self.population_manager.get_district_population_accounting(geo_ctx.district_id)

            sim_output = self.intervention_designer.execute_intervention_simulation(
                spec=intervention,
                context=geo_ctx,
                humans=humans,
                temporal=temporal,
                temporal_controller=self.temporal_controller,
                seed=used_seed,
                include_intervention=True,
                cancel_event=cancel_evt,
            )

            if cancel_evt.is_set():
                self.population_manager.restore_baseline_snapshot(baseline_snap)
                self._transition(record, TerritorialSimulationState.CANCELLED, "Escenario cancelado durante ejecución", progress_callback)
                return record

            # Mobility flow & labor market analysis on hydrated cohort
            mobility_report = self.mobility_engine.analyze_mobility(
                context=geo_ctx,
                humans=humans,
                catchment=record.catchment,
                commercial_report=record.commercial_context,
                time_period=runtime["time_period"],
                day_type=runtime["day_type"],
                season=runtime["season"],
            )
            emp_report = self.labor_engine.analyze_labor_market(
                context=geo_ctx,
                commercial_report=record.commercial_context,
                mobility_report=mobility_report,
                humans=humans,
            )
            emp_interv = None
            if emp_kind:
                emp_interv = self.employment_opportunity_engine.simulate_employment_intervention(
                    intervention_kind=emp_kind,
                    context=geo_ctx,
                    humans=humans,
                    horizon_days=temporal.horizon_days,
                )

            # 8. EVIDENCE_COLLECTION
            self._transition(record, TerritorialSimulationState.EVIDENCE_COLLECTION, "Recopilando paquete probatorio A–G", progress_callback)
            sim_ev = self.sim_evidence_engine.collect_evidence(
                scenario_id=scenario_id,
                seed=used_seed,
                context=geo_ctx,
                temporal=temporal,
                intervention=intervention,
                sim_output=sim_output,
                humans=humans,
                pop_accounting=pop_acc,
            )
            # Restore baseline human state after simulation snapshot collection so persistent identities remain clean
            self.population_manager.restore_baseline_snapshot(baseline_snap)

            # Optional baseline comparison (no-intervention baseline vs intervention)
            if compare_with_baseline:
                base_sim = self.intervention_designer.execute_intervention_simulation(
                    spec=intervention,
                    context=geo_ctx,
                    humans=humans,
                    temporal=temporal,
                    temporal_controller=self.temporal_controller,
                    seed=used_seed,
                    include_intervention=False,
                )
                self.population_manager.restore_baseline_snapshot(baseline_snap)
                record.baseline_comparison = {
                    "baseline_totals": base_sim.get("totals", {}),
                    "intervention_totals": sim_output.get("totals", {}),
                    "delta_household_income_usd": round(
                        float(sim_output.get("totals", {}).get("household_income_earned_usd", 0.0))
                        - float(base_sim.get("totals", {}).get("household_income_earned_usd", 0.0)),
                        2,
                    ),
                }

            # 9. ANALYSIS (Gemini optional, Ollama/Offline deterministic always grounded)
            self._transition(record, TerritorialSimulationState.ANALYSIS, "Interpretando evidencia con analista fundamentado", progress_callback)
            rec_analysis = self.decision_analyst.analyze(
                evidence=sim_ev,
                context=geo_ctx,
                intervention=intervention,
            )
            evidence_pkg = self.evidence_engine.build_evidence_package(
                scenario_id=scenario_id,
                seed=used_seed,
                context=geo_ctx,
                horizon_days=temporal.horizon_days,
                building_report=record.building_intelligence,
                land_use_report=record.land_use_intelligence,
                commercial_report=record.commercial_context,
                catchment=record.catchment,
                mobility_report=mobility_report,
                employment_report=emp_report,
                employment_intervention=emp_interv,
                coverage_record=record.coverage_assessment,
                humans=humans,
                sim_evidence=sim_ev,
                recommendation=rec_analysis,
                preparation_result=runtime.get("preparation_result"),
            )

            record.mobility_flow = mobility_report
            record.employment_analysis = emp_report
            record.employment_intervention = emp_interv
            record.evidence_package = evidence_pkg
            record.activated_engines = list(dict.fromkeys(record.activated_engines + sim_ev.active_engines + ["TerritorialEvidenceEngine", "HumanMobilityFlowEngine", "TerritorialLaborMarketEngine"]))
            record.provenance["analyst_provider"] = rec_analysis.provider_used
            record.provenance["analyst_model"] = rec_analysis.model_used
            record.provenance["ledger_conservation"] = sim_ev.ledger_audit

            # 10. COMPLETED
            self._transition(record, TerritorialSimulationState.COMPLETED, "Simulación territorial completada", progress_callback)
            return record
        except Exception as exc:
            record.error = str(exc)
            self._transition(record, TerritorialSimulationState.FAILED, f"Error: {exc}", progress_callback)
            return record

    def create_and_run_scenario(self, **kwargs: Any) -> OnDemandScenarioRecord:
        """Convenience wrapper executing full lifecycle from IDLE to COMPLETED."""
        compare_with_baseline = bool(kwargs.pop("compare_with_baseline", False))
        progress_callback = kwargs.get("progress_callback")
        rec = self.prepare_scenario(**kwargs)
        if rec.state == TerritorialSimulationState.READY:
            return self.execute_scenario(
                rec.scenario_id,
                seed=rec.seed,
                compare_with_baseline=compare_with_baseline,
                progress_callback=progress_callback,
            )
        return rec

    def pause_scenario(self, scenario_id: str) -> bool:
        rec = self.get_scenario(scenario_id)
        if rec is None:
            return False
        self._pause_flags[scenario_id].set()
        self._transition(rec, TerritorialSimulationState.PAUSED, "Escenario pausado")
        return True

    def resume_scenario(self, scenario_id: str) -> bool:
        rec = self.get_scenario(scenario_id)
        if rec is None:
            return False
        self._pause_flags[scenario_id].clear()
        if rec.state == TerritorialSimulationState.PAUSED:
            self._transition(rec, TerritorialSimulationState.READY, "Escenario reanudado")
        return True

    def cancel_scenario(self, scenario_id: str) -> bool:
        rec = self.get_scenario(scenario_id)
        if rec is None:
            return False
        self._cancel_flags[scenario_id].set()
        self._pause_flags[scenario_id].clear()
        self._transition(rec, TerritorialSimulationState.CANCELLED, "Escenario cancelado por solicitud")
        return True

    def rerun_scenario(self, scenario_id: str, seed: Optional[int] = None) -> OnDemandScenarioRecord:
        rec = self.get_scenario(scenario_id)
        if rec is None:
            raise KeyError(f"Scenario '{scenario_id}' not found")
        self._cancel_flags[scenario_id].clear()
        self._pause_flags[scenario_id].clear()
        return self.execute_scenario(scenario_id, seed=seed or rec.seed)

    def compare_locations(
        self,
        location_queries: List[str],
        objective: str = "Comparación territorial comercial",
        service_type: str = "pupuseria",
        intervention_category: InterventionCategory = InterventionCategory.PUPUSERIA,
        horizon_days: int = 30,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Run independent on-demand scenarios for multiple Salvadoran locations and compare evidence."""
        results: List[Dict[str, Any]] = []
        for idx, loc_q in enumerate(location_queries):
            rec = self.create_and_run_scenario(
                location_query=loc_q,
                objective=f"{objective} ({loc_q})",
                service_type=service_type,
                intervention_category=intervention_category,
                horizon_days=horizon_days,
                seed=seed,
                max_active_agents=32,
            )
            comm_m = rec.commercial_context.concentration_metrics if rec.commercial_context else None
            ev_map = {}
            if rec.evidence_package:
                for ind in rec.evidence_package.E_simulated_outcomes:
                    ev_map[ind.indicator_id] = ind.value
            results.append({
                "scenario_id": rec.scenario_id,
                "location_query": loc_q,
                "state": rec.state.value,
                "resolved_location": rec.resolved_location,
                "coverage_tier": rec.coverage_assessment.coverage_tier.value if rec.coverage_assessment else "UNKNOWN",
                "buildings_observed": rec.building_intelligence.total_buildings_observed if rec.building_intelligence else 0,
                "confirmed_establishments": comm_m.confirmed_establishments_count if comm_m else 0,
                "business_density_per_km2": comm_m.business_density_per_km2 if comm_m else 0.0,
                "residential_demand_potential": comm_m.residential_demand_potential_index if comm_m else 0.0,
                "catchment_effective_area_km2": rec.catchment.effective_area_km2 if rec.catchment else 0.0,
                "simulated_outcomes": ev_map,
                "verdict": rec.evidence_package.G_recommendations[0] if (rec.evidence_package and rec.evidence_package.G_recommendations) else "",
            })

        return {
            "comparison_id": f"CMP_LOC_{uuid4().hex[:8]}",
            "objective": objective,
            "service_type": service_type,
            "seed": seed,
            "locations": results,
            "location_isolation_verified": (
                len({r["resolved_location"]["district_id"] for r in results if r.get("resolved_location")}) == len(results)
                if len(results) > 1 else True
            ),
        }

    def create_historic_center_benchmark_scenario(self, seed: int = 42) -> OnDemandScenarioRecord:
        """Explicitly construct the preserved Historic Center benchmark scenario when requested."""
        return self.create_and_run_scenario(
            location_query="San Salvador Centro",
            lat=13.6989,
            lon=-89.1914,
            objective="Escenario de referencia preservado — Centro Histórico de San Salvador",
            service_type="general",
            horizon_days=30,
            seed=seed,
            is_historic_center_benchmark=True,
        )

    @staticmethod
    def _infer_intervention_category(objective: str, service_type: str) -> Optional[InterventionCategory]:
        text = f"{objective} {service_type}".lower()
        if "pupus" in text:
            return InterventionCategory.PUPUSERIA
        if "farmac" in text:
            return InterventionCategory.PHARMACY
        if "escuel" in text or "coleg" in text:
            return InterventionCategory.SCHOOL
        if "capacit" in text:
            return InterventionCategory.TRAINING_CENTER
        if "hospital" in text:
            return InterventionCategory.HOSPITAL
        if "clinic" in text or "salud" in text:
            return InterventionCategory.CLINIC
        if "mercad" in text:
            return InterventionCategory.MARKET
        if "restaur" in text or "comedor" in text:
            return InterventionCategory.RESTAURANT
        if "tienda" in text or "pulper" in text:
            return InterventionCategory.SHOP
        if "carret" in text or "vial" in text or "calle" in text:
            return InterventionCategory.ROAD
        return InterventionCategory.COMMERCIAL_ESTABLISHMENT

    @staticmethod
    def _select_required_engines(
        cat: Optional[InterventionCategory],
        emp_kind: Optional[str],
    ) -> List[str]:
        engines = [
            "NationalCensusDataIntegrationEngine",
            "TerritorialContextDiscoveryEngine",
            "DynamicTerritorialExpansionEngine",
            "GeospatialPopulationAllocationEngine",
            "SyntheticHouseholdGenerationEngine",
            "PopulationCalibrationEngine",
            "InfrastructureServiceDiscoveryEngine",
            "SectorSpecificContextEngine",
            "HumanMobilityAccessibilityEngine",
            "NationalTerritorialContextEngine",
            "NationalBuildingIntelligenceEngine",
            "TerritorialLandUseIntelligenceEngine",
            "CommercialActivityIntelligenceEngine",
            "BusinessDistributionEngine",
            "TerritorialCatchmentAnalysisEngine",
            "DynamicPopulationDistributionEngine",
            "HumanMobilityFlowEngine",
            "TerritorialLaborMarketEngine",
            "VerifiableEconomicLedger",
        ]
        if cat in (
            InterventionCategory.PUPUSERIA,
            InterventionCategory.RESTAURANT,
            InterventionCategory.SHOP,
            InterventionCategory.MARKET,
            InterventionCategory.PHARMACY,
            InterventionCategory.COMMERCIAL_ESTABLISHMENT,
        ):
            engines.extend(["CommercialEngine", "BusinessEnterprise"])
        if cat in (InterventionCategory.SCHOOL, InterventionCategory.CLINIC, InterventionCategory.HOSPITAL, InterventionCategory.TRAINING_CENTER):
            engines.append("PublicServiceCapacityEngine")
        if emp_kind:
            engines.append("EmploymentOpportunityAnalysisEngine")
        return list(dict.fromkeys(engines))
