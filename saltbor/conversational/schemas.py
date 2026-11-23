"""Pydantic v2 Schemas and Enums for SALTBOR Phase 1.16A Conversational Territorial Studio."""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


class ConversationIntent(str, enum.Enum):
    """Supported conversational intent categories."""

    BUSINESS_PLACEMENT = "BUSINESS_PLACEMENT"
    EDUCATIONAL_INFRASTRUCTURE = "EDUCATIONAL_INFRASTRUCTURE"
    HEALTH_INFRASTRUCTURE = "HEALTH_INFRASTRUCTURE"
    TRANSPORT_INFRASTRUCTURE = "TRANSPORT_INFRASTRUCTURE"
    PUBLIC_SERVICES = "PUBLIC_SERVICES"
    AGRICULTURAL_INTERVENTION = "AGRICULTURAL_INTERVENTION"
    ENVIRONMENTAL_SCENARIO = "ENVIRONMENTAL_SCENARIO"
    DEMOGRAPHIC_ANALYSIS = "DEMOGRAPHIC_ANALYSIS"
    ECONOMIC_ANALYSIS = "ECONOMIC_ANALYSIS"
    SOCIAL_ANALYSIS = "SOCIAL_ANALYSIS"
    TERRITORIAL_COMPARISON = "TERRITORIAL_COMPARISON"
    GENERAL_SCENARIO = "GENERAL_SCENARIO"
    FOLLOW_UP = "FOLLOW_UP"
    INFORMATION_REQUEST = "INFORMATION_REQUEST"


class InterventionCategory(str, enum.Enum):
    """Supported territorial intervention categories."""

    SCHOOL = "SCHOOL"
    CLINIC = "CLINIC"
    HOSPITAL = "HOSPITAL"
    PHARMACY = "PHARMACY"
    RESTAURANT = "RESTAURANT"
    PUPUSERIA = "PUPUSERIA"
    SHOP = "SHOP"
    MARKET = "MARKET"
    COMMERCIAL_ESTABLISHMENT = "COMMERCIAL_ESTABLISHMENT"
    AGRICULTURAL_BUSINESS = "AGRICULTURAL_BUSINESS"
    ROAD = "ROAD"
    PUBLIC_TRANSPORT = "PUBLIC_TRANSPORT"
    WATER_INFRASTRUCTURE = "WATER_INFRASTRUCTURE"
    ELECTRICITY_INFRASTRUCTURE = "ELECTRICITY_INFRASTRUCTURE"
    TRAINING_CENTER = "TRAINING_CENTER"
    RECREATIONAL_FACILITY = "RECREATIONAL_FACILITY"
    HOUSING = "HOUSING"
    ENVIRONMENTAL_PROJECT = "ENVIRONMENTAL_PROJECT"


class PopulationCategory(str, enum.Enum):
    """Non-overlapping or explicitly reconciled population flow categories."""

    PERMANENT_RESIDENT = "PERMANENT_RESIDENT"
    TEMPORARY_POPULATION = "TEMPORARY_POPULATION"
    DAILY_COMMUTER = "DAILY_COMMUTER"
    STUDENT = "STUDENT"
    WORKER = "WORKER"
    VISITOR = "VISITOR"
    COMMERCIAL_FLOW = "COMMERCIAL_FLOW"
    TRANSIT_POPULATION = "TRANSIT_POPULATION"


class ActivationLOD(int, enum.Enum):
    """Phase 1.16A population activation resolution levels (0 coarsest -> 3 finest)."""

    LOD_0_TERRITORIAL_AGGREGATE = 0
    LOD_1_HOUSEHOLD_GROUP = 1
    LOD_2_INDIVIDUAL_SUMMARY = 2
    LOD_3_INDIVIDUAL_FULL = 3


class AnalyticalVerdict(str, enum.Enum):
    """Evidence-based recommendation classifications (never simplistic YES/NO)."""

    PROMISING = "PROMISING"
    CONDITIONALLY_PROMISING = "CONDITIONALLY_PROMISING"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    HIGH_RISK = "HIGH_RISK"
    NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS = "NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS"


class AnalysisStage(str, enum.Enum):
    """Two-stage conversational simulation workflow stage."""

    STAGE_A_PRELIMINARY = "STAGE_A_PRELIMINARY"
    STAGE_B_SIMULATED = "STAGE_B_SIMULATED"


class ReportDepthLevel(str, enum.Enum):
    """Progressive presentation depth levels (never alter underlying outputs)."""

    BASIC = "BASIC"
    INTERMEDIATE = "INTERMEDIATE"
    EXPERT = "EXPERT"


class UniversalEvidenceOrigin(str, enum.Enum):
    """Mandatory FASE 5 provenance taxonomy strictly separating real, estimated & simulated data."""

    OBSERVED = "OBSERVED"
    PUBLIC_OFFICIAL = "PUBLIC_OFFICIAL"
    ESTIMATED = "ESTIMATED"
    EXTRAPOLATED = "EXTRAPOLATED"
    SYNTHETIC_SIMULATED = "SYNTHETIC_SIMULATED"
    DIRECT_SIMULATION_EVENT = "DIRECT_SIMULATION_EVENT"
    DETERMINISTIC_MULTIPLIER = "DETERMINISTIC_MULTIPLIER"
    UNAVAILABLE = "UNAVAILABLE"


class DataProvenance(BaseModel):
    """Mandatory provenance record attached to every territorial data element."""

    source: str
    license: str = "ODbL-1.0 / Public Official D.L. 762"
    retrieval_date: str = "2026-11-13"
    geographic_resolution: str = "district"
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    validation_status: str = "VERIFIED_REAL"
    limitations: str = ""


class GeographicCandidate(BaseModel):
    """Candidate location returned when a place reference is ambiguous."""

    district_id: str
    name: str
    municipality_id: str
    municipality_name: str
    department_code: str
    department_name: str
    match_level: str
    matched_label: str
    lat: float
    lon: float
    approx_population: int = 0
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class QuestionDataQualityAssessment(BaseModel):
    """Question-specific data quality, dataset coverage, and provenance assessment."""

    question_type: str
    required_datasets: List[str] = Field(default_factory=list)
    available_datasets: List[str] = Field(default_factory=list)
    coverage_by_dataset: Dict[str, str] = Field(default_factory=dict)
    freshness: Dict[str, str] = Field(default_factory=dict)
    provenance: Dict[str, str] = Field(default_factory=dict)
    missing_fields: List[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    summary: str = ""


class TerritorialContext(BaseModel):
    """Resolved Salvadoran territorial context with strict provenance and gaps."""

    query: str
    resolved: bool = True
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None
    candidates: List[GeographicCandidate] = Field(default_factory=list)

    # Administrative hierarchy (D.L. 762)
    department_code: str = ""
    department_name: str = ""
    municipality_id: str = ""
    municipality_name: str = ""
    district_id: str = ""
    district_name: str = ""
    canton_name: Optional[str] = None
    is_urban: bool = False
    approx_population: int = 0

    # Coordinates & topography
    lat: float = 0.0
    lon: float = 0.0
    coordinate_source: str = "district_centroid"
    elevation_m: Optional[float] = None
    slope_pct: Optional[float] = None
    tobler_walking_speed_factor: Optional[float] = None
    terrain_class: str = "UNKNOWN"

    # Geospatial layers (real OSM where available)
    radius_km: float = 1.5
    landuse_summary: Dict[str, int] = Field(default_factory=dict)
    buildings_count: int = 0
    buildings_is_partial: bool = True
    road_network_summary: Dict[str, Any] = Field(default_factory=dict)
    nearest_road: Optional[Dict[str, Any]] = None
    accessibility_index: float = 0.0
    hydrology_summary: Dict[str, int] = Field(default_factory=dict)
    nearby_facilities: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    nearby_facilities_counts: Dict[str, int] = Field(default_factory=dict)
    transport_stops_count: int = 0
    environmental_risks: Dict[str, float] = Field(default_factory=dict)
    commercial_activity_summary: Dict[str, Any] = Field(default_factory=dict)

    # Provenance & uncertainty
    data_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    question_data_quality: Optional[QuestionDataQualityAssessment] = None
    provenance_by_domain: Dict[str, DataProvenance] = Field(default_factory=dict)
    missing_data: List[str] = Field(default_factory=list)
    uncertainties: List[str] = Field(default_factory=list)


class TemporalHorizonSpec(BaseModel):
    """Temporal horizon configuration and multi-resolution schedule metadata."""

    raw_expression: Optional[str] = None
    horizon_days: int = Field(default=30, ge=1, le=3650)
    resolution_mode: Literal["FINE_TICK", "HYBRID_REPRESENTATIVE", "LONG_TERM_AGGREGATED"] = "HYBRID_REPRESENTATIVE"
    ticks_per_day: int = 96
    total_simulated_ticks: int = 2880
    effective_engine_ticks: int = 96
    representative_days: int = 1
    seasonal_profile: Literal["ANNUAL_CYCLE", "RAINY_SEASON", "DRY_SEASON", "SCHOOL_CALENDAR", "STANDARD"] = "STANDARD"
    calendar_alignment: str = "standard_calendar"
    inferred_default: bool = True
    requires_confirmation: bool = False
    confirmation_reason: Optional[str] = None
    estimated_runtime_seconds: float = 0.2
    seed: int = 42


class InterventionSpec(BaseModel):
    """Structured definition of a proposed territorial intervention or scenario shock."""

    intervention_id: str
    category: InterventionCategory
    name: str
    location_query: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    district_id: Optional[str] = None
    capacity: int = Field(default=24, ge=0)
    opening_hour: int = Field(default=6, ge=0, le=23)
    closing_hour: int = Field(default=20, ge=1, le=24)
    resources: Dict[str, Any] = Field(default_factory=dict)
    workforce_count: int = Field(default=2, ge=0)
    daily_wage_usd: float = Field(default=12.0, ge=0.0)
    products_or_services: List[str] = Field(default_factory=list)
    unit_price_usd: float = Field(default=1.0, ge=0.0)
    unit_cost_ratio: float = Field(default=0.55, ge=0.0, le=1.0)
    daily_fixed_cost_usd: float = Field(default=6.0, ge=0.0)
    initial_capital_usd: float = Field(default=200.0, ge=0.0)
    conditions: List[str] = Field(default_factory=list)
    opening_day: int = Field(default=1, ge=0)
    duration_days: int = Field(default=30, ge=1)
    is_shock_scenario: bool = False
    shock_type: Optional[str] = None
    shock_severity: float = Field(default=0.5, ge=0.0, le=1.0)
    compare_alternatives: List[str] = Field(default_factory=list)
    custom_modifications: Dict[str, Any] = Field(default_factory=dict)


class ParsedUserRequest(BaseModel):
    """Structured extraction from a natural-language user message."""

    raw_message: str
    intent: ConversationIntent
    intervention_type: Optional[InterventionCategory] = None
    geographic_reference: Optional[str] = None
    map_coordinates: Optional[Tuple[float, float]] = None
    target_entities: List[str] = Field(default_factory=list)
    temporal_expression: Optional[str] = None
    requested_days: Optional[int] = None
    required_domains: List[str] = Field(default_factory=list)
    expected_outcomes: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    analysis_depth: Literal["quick", "standard", "deep", "comparative"] = "standard"
    is_follow_up: bool = False
    follow_up_modifications: Dict[str, Any] = Field(default_factory=dict)
    referenced_scenario_id: Optional[str] = None
    extraction_provider: str = "OFFLINE_DETERMINISTIC"
    extraction_model: str = "deterministic-spanish-nlu"


class EvidenceProvenance(BaseModel):
    """Strict provenance record for each simulation indicator."""

    source_engine: str
    source_entity: str
    calculation_method: str
    time_interval: str
    population_scope: str
    geographic_scope: str
    seed: int
    data_quality: float = Field(default=0.7, ge=0.0, le=1.0)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    limitations: str = ""


class EvidenceIndicator(BaseModel):
    """Single quantitative or qualitative indicator produced by real simulation."""

    indicator_id: str
    domain: str
    name: str
    definition: str = ""
    value: Optional[Any] = None
    unit: str = ""
    data_origin: str = "AGGREGATED_SYNTHETIC_AGENTS"
    evidence_origin: str = "SYNTHETIC_SIMULATED"
    empirical_calibration_status: str = "UNCALIBRATED_SYNTHETIC"
    uncertainty: str = ""
    is_synthetic: bool = True
    available: bool = True
    basic_explanation: str = ""
    expert_explanation: str = ""
    provenance: EvidenceProvenance


class SyntheticOpinionRecord(BaseModel):
    """Grounded synthetic agent reaction (explicitly non-independent model output)."""

    opinion_id: str
    agent_uids: List[str]
    group_label: str
    query_method: str
    context_summary: str
    response_text: str
    stance: str
    simulated_tick: int
    seed: int
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    is_independent_sample: Literal[False] = False
    correlation_warning: str = (
        "Correlated synthetic model outputs sharing simulation state; NOT independent real-world survey observations."
    )
    limitations: str = (
        "Generated from simulated synthetic human state, memory, budget, and personality; not empirical human polling."
    )


class EvidenceBundle(BaseModel):
    """Complete structured evidence collected from Stage B simulation execution."""

    scenario_id: str
    seed: int
    horizon_days: int
    simulated_ticks: int
    wall_clock_seconds: float = 0.0
    geographic_scope: str
    district_id: str
    data_classification: Literal["SYNTHETIC_SIMULATED"] = "SYNTHETIC_SIMULATED"
    active_engines: List[str] = Field(default_factory=list)
    population_summary: Dict[str, Any] = Field(default_factory=dict)
    indicators: List[EvidenceIndicator] = Field(default_factory=list)
    group_breakdowns: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    temporal_series: List[Dict[str, Any]] = Field(default_factory=list)
    synthetic_opinions: List[SyntheticOpinionRecord] = Field(default_factory=list)
    ledger_audit: Dict[str, Any] = Field(default_factory=dict)
    missing_indicators: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class DecisionRecommendation(BaseModel):
    """Structured analytical report produced by GeminiDecisionAnalyst."""

    verdict: AnalyticalVerdict
    executive_summary: str
    observed_patterns: List[str] = Field(default_factory=list)
    population_needs: List[str] = Field(default_factory=list)
    unmet_demand: List[str] = Field(default_factory=list)
    affected_groups: List[str] = Field(default_factory=list)
    alternatives_comparison: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)
    relevant_indicators: Dict[str, Any] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    uncertainty: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    alternative_interpretations: List[str] = Field(default_factory=list)
    model_vs_external_distinction: str = (
        "Los valores cuantitativos provienen de la simulación de SALTBOR (SYNTHETIC_SIMULATED); "
        "la cartografía y jerarquía D.L. 762 provienen de fuentes oficiales y OSM (PUBLIC_OFFICIAL)."
    )
    provider_used: str = "OFFLINE_DETERMINISTIC"
    model_used: str = "deterministic-evidence-analyst"
    disclaimer: str = (
        "Clasificación analítica basada en evidencia simulada bajo supuestos explícitos; "
        "no constituye garantía de resultados reales."
    )


class ScenarioComparisonEntry(BaseModel):
    """Summary metrics for one scenario across multiple seeds."""

    label: str
    scenario_id: str
    seeds: List[int]
    metrics_mean: Dict[str, float] = Field(default_factory=dict)
    metrics_ci95: Dict[str, Tuple[float, float]] = Field(default_factory=dict)
    multi_scale_views: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ScenarioComparisonReport(BaseModel):
    """Multi-seed paired counterfactual comparison report."""

    comparison_id: str
    baseline: ScenarioComparisonEntry
    alternatives: List[ScenarioComparisonEntry] = Field(default_factory=list)
    paired_deltas: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    recommended_alternative: str = ""
    methodology_note: str = (
        "Comparación pareada bajo condiciones iniciales comparables y múltiples semillas; "
        "las diferencias observadas dependen de los supuestos del modelo y no prueban causalidad empírica."
    )


class PreliminaryAssessment(BaseModel):
    """Stage A response returned before running an expensive simulation."""

    conversation_id: str
    scenario_id: str
    stage: AnalysisStage = AnalysisStage.STAGE_A_PRELIMINARY
    parsed_request: ParsedUserRequest
    territorial_context: TerritorialContext
    population_context: Dict[str, Any] = Field(default_factory=dict)
    proposed_intervention: Optional[InterventionSpec] = None
    temporal_horizon: TemporalHorizonSpec
    required_engines: List[str] = Field(default_factory=list)
    missing_data: List[str] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_questions: List[str] = Field(default_factory=list)
    computational_estimate: Dict[str, Any] = Field(default_factory=dict)
    capabilities_summary: List[str] = Field(default_factory=list)
    limitations_summary: List[str] = Field(default_factory=list)
    territorial_intelligence: Dict[str, Any] = Field(default_factory=dict)
    ready_to_execute: bool = True
    assistant_reply: str = ""


class ExplainedMetricCard(BaseModel):
    """Self-describing metric with universal provenance, dual-depth explanation & limitations."""

    indicator_id: str
    label: str
    raw_value: Optional[Any] = None
    formatted_value: str
    unit: str = ""
    evidence_origin: UniversalEvidenceOrigin = UniversalEvidenceOrigin.SYNTHETIC_SIMULATED
    is_synthetic: bool = True
    empirical_calibration_status: str = "UNCALIBRATED_SYNTHETIC"
    what_it_represents: str
    where_it_comes_from: str
    how_it_was_obtained: str
    uncertainty: str
    limitations: str
    basic_explanation: str
    expert_explanation: str
    not_guaranteed_note: Optional[str] = None


class BasicReportView(BaseModel):
    """FASE 2 — Accessible plain-language summary (default view)."""

    depth_level: ReportDepthLevel = ReportDepthLevel.BASIC
    what_was_evaluated: str
    where_was_evaluated: str
    temporal_horizon_summary: str
    overall_verdict_code: str
    overall_verdict_plain: str
    overall_result_headline: str
    estimated_revenue: Optional[ExplainedMetricCard] = None
    estimated_expenses: Optional[ExplainedMetricCard] = None
    operating_result: Optional[ExplainedMetricCard] = None
    potential_demand: Optional[ExplainedMetricCard] = None
    potential_customers: Optional[ExplainedMetricCard] = None
    contextual_highlights: List[ExplainedMetricCard] = Field(default_factory=list)
    main_opportunities: List[str] = Field(default_factory=list)
    main_risks: List[str] = Field(default_factory=list)
    understandable_recommendation: str
    non_guarantee_notice: str = (
        "Las cifras financieras y de demanda provienen de una simulación bajo supuestos explícitos; "
        "no representan ingresos ni ganancias garantizadas."
    )


class ScenarioEnvelopeEntry(BaseModel):
    """Documented alternative/sensitivity scenario envelope for decision comparison."""

    scenario_label: str
    available: bool = True
    parameters_used: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Optional[float]] = Field(default_factory=dict)
    derivation_note: str = ""


class IntermediateReportView(BaseModel):
    """FASE 3 — Decision-oriented structured territorial & commercial analysis."""

    depth_level: ReportDepthLevel = ReportDepthLevel.INTERMEDIATE
    demand_and_market: str
    competition: str
    consumer_behavior: str
    economic_capacity: str
    territorial_mobility: str
    accessibility: str
    employment: str
    costs_and_profitability: str
    commercial_risks: List[str] = Field(default_factory=list)
    alternative_scenarios: List[ScenarioEnvelopeEntry] = Field(default_factory=list)
    actionable_recommendations: List[str] = Field(default_factory=list)
    key_metrics: List[ExplainedMetricCard] = Field(default_factory=list)


class ExpertReportView(BaseModel):
    """FASE 4 — Full technical, methodological, ledger & reproducible evidence audit."""

    depth_level: ReportDepthLevel = ReportDepthLevel.EXPERT
    execution_metadata: Dict[str, Any] = Field(default_factory=dict)
    all_indicators: List[ExplainedMetricCard] = Field(default_factory=list)
    synthetic_agents_summary: Dict[str, Any] = Field(default_factory=dict)
    simulation_events_and_segments: List[Dict[str, Any]] = Field(default_factory=list)
    transactions_and_accounting: Dict[str, Any] = Field(default_factory=dict)
    extrapolations: Dict[str, Any] = Field(default_factory=dict)
    territorial_sources_and_quality: Dict[str, Any] = Field(default_factory=dict)
    methodology_and_assumptions: List[str] = Field(default_factory=list)
    uncertainty: List[str] = Field(default_factory=list)
    missing_data: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    evidence_origin_counts: Dict[str, int] = Field(default_factory=dict)


class ProgressiveReportBundle(BaseModel):
    """Unified 3-level presentation payload backed by a single immutable evidence source."""

    default_level: ReportDepthLevel = ReportDepthLevel.BASIC
    available_levels: List[ReportDepthLevel] = Field(
        default_factory=lambda: [
            ReportDepthLevel.BASIC,
            ReportDepthLevel.INTERMEDIATE,
            ReportDepthLevel.EXPERT,
        ]
    )
    source_execution_id: str = ""
    source_scenario_id: str = ""
    source_seed: int = 42
    canonical_numeric_fingerprint: Dict[str, Any] = Field(default_factory=dict)
    basic: BasicReportView
    intermediate: IntermediateReportView
    expert: ExpertReportView


class SimulationStudioResult(BaseModel):
    """Stage B response containing full simulation evidence and analyst recommendation."""

    conversation_id: str
    scenario_id: str
    execution_id: str
    stage: AnalysisStage = AnalysisStage.STAGE_B_SIMULATED
    map_visible: bool = False
    territorial_context: TerritorialContext
    temporal_horizon: TemporalHorizonSpec
    intervention: Optional[InterventionSpec] = None
    evidence: EvidenceBundle
    recommendation: DecisionRecommendation
    comparison: Optional[ScenarioComparisonReport] = None
    checkpoint_id: Optional[str] = None
    provenance_record: Dict[str, Any] = Field(default_factory=dict)
    territorial_intelligence: Dict[str, Any] = Field(default_factory=dict)
    progressive_report: Optional[ProgressiveReportBundle] = None
    assistant_reply: str = ""


class ConversationTurn(BaseModel):
    """Single conversational turn stored independently of raw simulation dumps."""

    turn_index: int
    role: Literal["user", "assistant"]
    message: str
    timestamp: float
    stage: AnalysisStage
    scenario_id: Optional[str] = None
    intent: Optional[str] = None


class ConversationSessionState(BaseModel):
    """Persistent conversational session state enabling multi-turn continuity."""

    conversation_id: str
    active_scenario_id: Optional[str] = None
    active_district_id: Optional[str] = None
    active_location_query: Optional[str] = None
    active_coordinates: Optional[Tuple[float, float]] = None
    active_intervention: Optional[InterventionSpec] = None
    active_temporal_horizon: Optional[TemporalHorizonSpec] = None
    scenario_ids: List[str] = Field(default_factory=list)
    turns: List[ConversationTurn] = Field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
