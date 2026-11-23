"""Pydantic v2 Schemas & Epistemic Enums for SALTBOR Phase 1.17 Territorial Intelligence.

Enforces strict separation across epistemic tiers (A–G), explicit provenance,
zero data fabrication, non-double-counted mobility flows, and full lifecycle
state tracking for location-independent on-demand territorial simulations.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


class TerritorialSimulationState(str, enum.Enum):
    """Explicit backend lifecycle states for OnDemandTerritorialSimulationEngine."""

    IDLE = "IDLE"
    LOCATION_RESOLUTION = "LOCATION_RESOLUTION"
    TERRITORIAL_CONTEXT_LOADING = "TERRITORIAL_CONTEXT_LOADING"
    DATA_QUALITY_ASSESSMENT = "DATA_QUALITY_ASSESSMENT"
    POPULATION_ACTIVATION = "POPULATION_ACTIVATION"
    SCENARIO_CONSTRUCTION = "SCENARIO_CONSTRUCTION"
    VALIDATION = "VALIDATION"
    READY = "READY"
    RUNNING = "RUNNING"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    ANALYSIS = "ANALYSIS"
    COMPLETED = "COMPLETED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class EpistemicTier(str, enum.Enum):
    """Mandatory 7-tier epistemic separation (Section 9)."""

    A_REAL_OBSERVED = "A_REAL_OBSERVED"
    B_OFFICIAL_STATISTICAL = "B_OFFICIAL_STATISTICAL"
    C_GEOGRAPHIC_DERIVATION = "C_GEOGRAPHIC_DERIVATION"
    D_SYNTHETIC_POPULATION = "D_SYNTHETIC_POPULATION"
    E_SIMULATED_OUTCOME = "E_SIMULATED_OUTCOME"
    F_AI_INTERPRETATION = "F_AI_INTERPRETATION"
    G_RECOMMENDATION = "G_RECOMMENDATION"


class ClassificationOrigin(str, enum.Enum):
    """Origin of a building or entity classification (Section 3.2)."""

    OBSERVED = "OBSERVED"
    SOURCE_PROVIDED = "SOURCE_PROVIDED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class BuildingUseCategory(str, enum.Enum):
    """Supported built-environment use categories (Section 3.2)."""

    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    INSTITUTIONAL = "institutional"
    EDUCATIONAL = "educational"
    HEALTH = "health"
    AGRICULTURAL = "agricultural"
    RELIGIOUS = "religious"
    RECREATIONAL = "recreational"
    MIXED_USE = "mixed_use"
    UNKNOWN = "unknown"


class CommercialCategory(str, enum.Enum):
    """Supported commercial & economic establishment categories (Section 4)."""

    SHOP = "shop"
    RESTAURANT = "restaurant"
    PUPUSERIA = "pupuseria"
    MARKET = "market"
    SUPERMARKET = "supermarket"
    PHARMACY = "pharmacy"
    WORKSHOP = "workshop"
    OFFICE = "office"
    FACTORY = "factory"
    WAREHOUSE = "warehouse"
    SERVICE_BUSINESS = "service_business"
    INFORMAL_COMMERCIAL = "informal_commercial"
    COMMERCIAL_CENTER = "commercial_center"
    STREET_MARKET = "street_market"
    TRANSPORT_COMMERCE = "transport_commerce"
    AGRICULTURAL_BUSINESS = "agricultural_business"


class CatchmentMethod(str, enum.Enum):
    """All 8 catchment / area-of-influence methodologies (Section 5)."""

    STRAIGHT_LINE_RADIUS = "STRAIGHT_LINE_RADIUS"
    WALKING_NETWORK_DISTANCE = "WALKING_NETWORK_DISTANCE"
    ROAD_NETWORK_DISTANCE = "ROAD_NETWORK_DISTANCE"
    TRAVEL_TIME_ACCESSIBILITY = "TRAVEL_TIME_ACCESSIBILITY"
    NATURAL_GEOGRAPHIC_BARRIERS = "NATURAL_GEOGRAPHIC_BARRIERS"
    ADMINISTRATIVE_BOUNDARIES = "ADMINISTRATIVE_BOUNDARIES"
    SERVICE_SPECIFIC_CATCHMENT = "SERVICE_SPECIFIC_CATCHMENT"
    DEMAND_BASED_INFLUENCE = "DEMAND_BASED_INFLUENCE"


class CatchmentScale(str, enum.Enum):
    """Configurable spatial analysis scales (Section 5)."""

    IMMEDIATE = "IMMEDIATE"
    NEIGHBORHOOD = "NEIGHBORHOOD"
    COMMUNITY = "COMMUNITY"
    MUNICIPAL_DISTRICT = "MUNICIPAL_DISTRICT"
    REGIONAL = "REGIONAL"


class MobilityRole(str, enum.Enum):
    """10 non-overlapping human mobility & population roles (Section 6)."""

    PERMANENT_RESIDENT = "PERMANENT_RESIDENT"
    TEMPORARY_RESIDENT = "TEMPORARY_RESIDENT"
    WORKER = "WORKER"
    STUDENT = "STUDENT"
    COMMUTER = "COMMUTER"
    VISITOR = "VISITOR"
    CUSTOMER = "CUSTOMER"
    TRANSIT = "TRANSIT"
    SERVICE_SEEKER = "SERVICE_SEEKER"
    SEASONAL_AGRICULTURAL_WORKER = "SEASONAL_AGRICULTURAL_WORKER"


class TimePeriod(str, enum.Enum):
    """Diurnal temporal slots (Section 6.1)."""

    MORNING = "MORNING"
    MIDDAY = "MIDDAY"
    AFTERNOON = "AFTERNOON"
    EVENING = "EVENING"
    NIGHT = "NIGHT"


class DayType(str, enum.Enum):
    """Calendar day categories (Section 6.1)."""

    WEEKDAY = "WEEKDAY"
    WEEKEND = "WEEKEND"
    HOLIDAY = "HOLIDAY"


class FlowEvidenceTier(str, enum.Enum):
    """Explicit evidence boundary for human mobility counts (Section 6.2)."""

    MEASURED_FLOW = "MEASURED_FLOW"
    OFFICIAL_STATISTICAL_ESTIMATE = "OFFICIAL_STATISTICAL_ESTIMATE"
    GIS_DERIVED_ACCESSIBILITY = "GIS_DERIVED_ACCESSIBILITY"
    MODEL_GENERATED_MOBILITY = "MODEL_GENERATED_MOBILITY"
    SYNTHETIC_AGENT_SIMULATION = "SYNTHETIC_AGENT_SIMULATION"


class EmploymentEvidenceTier(str, enum.Enum):
    """5-tier employment opportunity evidence separation (Section 7)."""

    VERIFIED_JOB_VACANCY = "VERIFIED_JOB_VACANCY"
    KNOWN_EMPLOYER = "KNOWN_EMPLOYER"
    SECTORAL_EMPLOYMENT_ESTIMATE = "SECTORAL_EMPLOYMENT_ESTIMATE"
    SYNTHETIC_LABOR_SCENARIO = "SYNTHETIC_LABOR_SCENARIO"
    OPPORTUNITY_HYPOTHESIS = "OPPORTUNITY_HYPOTHESIS"


class CoverageTier(str, enum.Enum):
    """Territorial coverage quality tier (Section 11)."""

    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    POOR = "POOR"
    INSUFFICIENT = "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Building & Land-Use Intelligence Models (Section 3)
# ---------------------------------------------------------------------------

class BuildingRecord(BaseModel):
    """Normalized built-environment footprint retaining strict provenance & non-fabrication."""

    feature_id: str
    osm_id: str = ""
    name: str = ""
    source_dataset: str = "Geofabrik_OSM_El_Salvador"
    source_url: str = "https://download.geofabrik.de/central-america/el-salvador.html"
    license: str = "ODbL-1.0"
    last_update: str = "2026-11-23"
    lat: float
    lon: float
    bbox: List[float] = Field(default_factory=list)
    geometry_type: str = "Polygon"
    geometry: Optional[Dict[str, Any]] = None
    source_classification: str = ""
    building_use: BuildingUseCategory = BuildingUseCategory.UNKNOWN
    classification_origin: ClassificationOrigin = ClassificationOrigin.UNKNOWN
    height_m: Optional[float] = None
    levels: Optional[int] = None
    surface_area_m2: Optional[float] = None
    construction_or_modified_date: Optional[str] = None
    occupancy_known: bool = False
    data_quality: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    notes: str = ""


class BuildingIntelligenceReport(BaseModel):
    """Built-environment summary around a target location."""

    lat: float
    lon: float
    radius_km: float
    total_buildings_observed: int = 0
    total_surface_area_m2: float = 0.0
    counts_by_use: Dict[str, int] = Field(default_factory=dict)
    counts_by_origin: Dict[str, int] = Field(default_factory=dict)
    occupancy_assumption_warning: str = (
        "La presencia de una huella edificatoria no implica ocupación confirmada ni actividad económica activa."
    )
    sample_buildings: List[BuildingRecord] = Field(default_factory=list)
    is_partial_coverage: bool = False
    provenance: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class LandUseIntelligenceReport(BaseModel):
    """Physical geography, land cover, hydrology, hazards & accessibility."""

    district_id: str
    district_name: str
    department_name: str
    elevation_m: float
    slope_pct: float
    tobler_walking_speed_factor: float
    terrain_class: str
    land_use_counts: Dict[str, int] = Field(default_factory=dict)
    land_use_area_m2: Dict[str, float] = Field(default_factory=dict)
    road_hierarchy_counts: Dict[str, int] = Field(default_factory=dict)
    total_road_segments: int = 0
    hydrology_counts: Dict[str, int] = Field(default_factory=dict)
    protected_areas_count: int = 0
    transport_nodes_count: int = 0
    accessibility_index: float = 0.0
    natural_hazards: Dict[str, float] = Field(default_factory=dict)
    agricultural_land_share: float = 0.0
    urban_expansion_signal: float = 0.0
    environmental_constraints: List[str] = Field(default_factory=list)
    missing_layers: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Commercial Activity & Economic Context Models (Section 4)
# ---------------------------------------------------------------------------

class CommercialEstablishmentRecord(BaseModel):
    """Verified or source-recorded establishment (never fabricated from geometry alone)."""

    establishment_id: str
    name: str
    category: CommercialCategory
    raw_source_class: str = ""
    lat: float
    lon: float
    distance_m: float = 0.0
    geographic_coverage_note: str = "point_or_building_centroid"
    source: str
    verification_status: str = "VERIFIED_REAL"
    is_formal_status_known: bool = False
    formal_status: Literal["formal", "informal", "unknown"] = "unknown"
    is_synthetic: bool = False
    opening_hours: Optional[str] = None
    known_activity: str = ""
    available_products_or_services: List[str] = Field(default_factory=list)
    known_employment: Optional[int] = None
    last_verified_date: str = "2026-11-23"


class UnverifiedCommercialBuilding(BaseModel):
    """Building tagged commercial/retail in OSM without a confirmed operating business POI."""

    building_feature_id: str
    lat: float
    lon: float
    surface_area_m2: Optional[float] = None
    source_classification: str = ""
    status: Literal["unverified_commercial_building"] = "unverified_commercial_building"
    note: str = "Edificio con uso comercial registrado sin establecimiento comercial confirmado."


class CommercialConcentrationMetrics(BaseModel):
    """Derived commercial density, diversity & accessibility metrics (Section 4.1)."""

    analysis_area_km2: float
    confirmed_establishments_count: int
    unverified_commercial_buildings_count: int
    business_density_per_km2: float
    commercial_diversity_shannon_norm: float = Field(default=0.0, ge=0.0, le=1.0)
    competitor_concentration_by_category: Dict[str, int] = Field(default_factory=dict)
    commercial_accessibility_score: float = Field(default=0.0, ge=0.0, le=1.0)
    residential_demand_potential_index: float = Field(default=0.0, ge=0.0, le=1.0)
    proximity_to_nearest_transport_m: Optional[float] = None
    proximity_to_nearest_education_m: Optional[float] = None
    proximity_to_nearest_health_m: Optional[float] = None
    employment_center_proximity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    profitability_caveat: str = (
        "Una alta densidad comercial no implica automáticamente alta demanda insatisfecha ni rentabilidad garantizada."
    )


class CommercialContextReport(BaseModel):
    """Complete commercial & economic intelligence surrounding a location."""

    district_id: str
    district_name: str
    establishments: List[CommercialEstablishmentRecord] = Field(default_factory=list)
    unverified_commercial_buildings: List[UnverifiedCommercialBuilding] = Field(default_factory=list)
    simulated_informal_entities: List[CommercialEstablishmentRecord] = Field(default_factory=list)
    category_counts: Dict[str, int] = Field(default_factory=dict)
    concentration_metrics: CommercialConcentrationMetrics
    informal_economy_prior_share: float = 0.62
    informal_economy_uncertainty_note: str = (
        "El comercio informal salvadoreño representa una fracción sustancial no cubierta íntegramente en OSM; "
        "toda entidad informal simulada se etiqueta explícitamente como sintética."
    )
    economic_context_summary: Dict[str, Any] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Adaptive Territorial Catchment Models (Section 5)
# ---------------------------------------------------------------------------

class CatchmentAreaResult(BaseModel):
    """Adaptive area-of-influence calculation with explicit methodology."""

    target_lat: float
    target_lon: float
    service_type: str
    scale: CatchmentScale
    primary_method: CatchmentMethod
    applied_methods: List[CatchmentMethod] = Field(default_factory=list)
    nominal_radius_km: float
    effective_radius_km: float
    effective_area_km2: float
    network_nodes_analyzed: int = 0
    network_edges_analyzed: int = 0
    circuity_factor: float = 1.0
    estimated_walk_reach_15min_m: float = 0.0
    estimated_drive_reach_15min_m: float = 0.0
    barriers_detected: List[str] = Field(default_factory=list)
    barrier_discount_factor: float = 1.0
    administrative_units_touched: List[str] = Field(default_factory=list)
    isochrone_polygon_geojson: Optional[Dict[str, Any]] = None
    methodology_explanation: str
    limitations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Human Mobility & Population Flow Models (Section 6)
# ---------------------------------------------------------------------------

class MobilityCorridor(BaseModel):
    """Identified transport / pedestrian corridor grounded in OSM roads & stops."""

    corridor_name: str
    road_class: str
    segment_count: int
    transport_stops_along_corridor: int
    estimated_relative_intensity: float = Field(default=0.0, ge=0.0, le=1.0)


class PopulationFlowReport(BaseModel):
    """Role-differentiated, time-dependent population & mobility flow analysis."""

    district_id: str
    district_name: str
    time_period: TimePeriod
    day_type: DayType
    season: Literal["DRY", "RAINY", "HARVEST_TRANSITION"] = "DRY"
    unique_resident_population_approx: int
    unique_active_synthetic_individuals: int
    double_counting_prevented: bool = True
    role_breakdown: Dict[str, int] = Field(default_factory=dict)
    temporal_profile_by_period: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    estimated_pedestrian_activity_index: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_daily_arrivals: int = 0
    estimated_daily_departures: int = 0
    origin_destination_patterns: List[Dict[str, Any]] = Field(default_factory=list)
    mobility_corridors: List[MobilityCorridor] = Field(default_factory=list)
    schedule_heterogeneity_entropy: float = 0.0
    measured_flows_available: bool = False
    measured_flows_note: str = (
        "No existen conteos peatonales censados en tiempo real; las cifras son estimaciones estadísticas/GIS "
        "y resultados de agentes sintéticos, nunca mediciones observadas en calle."
    )
    evidence_tiers: Dict[str, FlowEvidenceTier] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Employment & Labor-Market Models (Section 7)
# ---------------------------------------------------------------------------

class EmploymentAnalysisReport(BaseModel):
    """5-tier employment opportunity analysis grounded in real employers & priors."""

    district_id: str
    district_name: str
    verified_job_vacancies: List[Dict[str, Any]] = Field(default_factory=list)
    verified_vacancies_available: bool = False
    known_employers: List[CommercialEstablishmentRecord] = Field(default_factory=list)
    sectoral_employment_estimates: Dict[str, float] = Field(default_factory=dict)
    potential_labor_supply_approx: int = 0
    formal_employment_share_est: float = 0.38
    informal_employment_share_est: float = 0.62
    labor_accessibility_score: float = Field(default=0.0, ge=0.0, le=1.0)
    jobs_workers_spatial_mismatch_index: float = Field(default=0.0, ge=0.0, le=1.0)
    estimated_unmet_labor_demand_note: str = ""
    employment_barriers: List[str] = Field(default_factory=list)
    synthetic_labor_scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    opportunity_hypotheses: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class EmploymentInterventionResult(BaseModel):
    """Simulated labor-market & economic impact with strict ledger conservation."""

    intervention_type: str
    location_name: str
    direct_jobs_created_or_lost: int
    local_resident_hire_share: float
    inbound_commuter_hire_share: float
    local_residents_hired: int
    inbound_commuters_hired: int
    total_wages_disbursed_usd: float
    consumption_spillover_usd: float
    mobility_delta_pct: float
    commercial_attraction_delta_pct: float
    ledger_conservation_diff_usd: float = 0.0
    conservation_passed: bool = True
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# National Coverage Registry (Section 11)
# ---------------------------------------------------------------------------

class TerritorialCoverageRecord(BaseModel):
    """Data completeness & confidence record per Salvadoran district/department."""

    territory_id: str
    territory_name: str
    level: Literal["department", "district"]
    department_code: str
    department_name: str
    municipality_id: str = ""
    municipality_name: str = ""
    lat: float
    lon: float
    geographic_coverage_score: float = Field(ge=0.0, le=1.0)
    building_data_coverage_score: float = Field(ge=0.0, le=1.0)
    road_data_coverage_score: float = Field(ge=0.0, le=1.0)
    land_use_coverage_score: float = Field(ge=0.0, le=1.0)
    commercial_data_coverage_score: float = Field(ge=0.0, le=1.0)
    population_data_coverage_score: float = Field(ge=0.0, le=1.0)
    mobility_data_coverage_score: float = Field(ge=0.0, le=1.0)
    employment_data_coverage_score: float = Field(ge=0.0, le=1.0)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    coverage_tier: CoverageTier
    feature_counts: Dict[str, int] = Field(default_factory=dict)
    data_sources: List[str] = Field(default_factory=list)
    last_update: str = "2026-11-23"
    missing_information: List[str] = Field(default_factory=list)


class NationalCoverageSummary(BaseModel):
    """Aggregate coverage matrix across all 14 departments and 262 districts."""

    total_departments: int = 14
    total_districts: int = 262
    tier_counts: Dict[str, int] = Field(default_factory=dict)
    department_summaries: List[TerritorialCoverageRecord] = Field(default_factory=list)
    district_records: List[TerritorialCoverageRecord] = Field(default_factory=list)
    generated_at: str = "2026-11-23"


# ---------------------------------------------------------------------------
# Evidence-Driven A–G Package & On-Demand Scenario Record (Sections 2 & 9)
# ---------------------------------------------------------------------------

class TerritorialEvidenceIndicator(BaseModel):
    """Single indicator with mandatory provenance & epistemic tier."""

    indicator_id: str
    name: str
    value: Any
    unit: str = ""
    epistemic_tier: EpistemicTier
    geographic_scope: str
    population_scope: str
    time_interval: str
    source_engine: str
    calculation_method: str
    data_provenance: str
    data_quality: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_interval_95: Optional[Tuple[float, float]] = None
    simulation_seed: Optional[int] = None
    scenario_id: str
    limitations: str = ""
    evidence_classification: Optional[str] = None


class TerritorialEvidencePackage(BaseModel):
    """Explicitly partitioned 7-bucket evidence bundle (Section 9 A–G)."""

    package_id: str
    scenario_id: str
    seed: int
    geographic_scope: str
    population_scope: str
    time_interval: str
    A_real_observed_data: List[TerritorialEvidenceIndicator] = Field(default_factory=list)
    B_official_statistical_estimates: List[TerritorialEvidenceIndicator] = Field(default_factory=list)
    C_geographic_derivations: List[TerritorialEvidenceIndicator] = Field(default_factory=list)
    D_synthetic_population_characteristics: List[TerritorialEvidenceIndicator] = Field(default_factory=list)
    E_simulated_outcomes: List[TerritorialEvidenceIndicator] = Field(default_factory=list)
    F_ai_interpretations_and_hypotheses: List[str] = Field(default_factory=list)
    G_recommendations: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    ai_provider_used: str = "OFFLINE_DETERMINISTIC"
    ai_model_used: str = "deterministic-grounded"


class LifecycleTransition(BaseModel):
    """Authentic recorded backend state transition."""

    state: TerritorialSimulationState
    timestamp: float
    detail: str = ""


class OnDemandScenarioRecord(BaseModel):
    """Full reproducible record for an on-demand territorial scenario."""

    scenario_id: str
    state: TerritorialSimulationState
    state_history: List[LifecycleTransition] = Field(default_factory=list)
    query: str
    objective: str = ""
    is_historic_center_benchmark: bool = False
    resolved_location: Optional[Dict[str, Any]] = None
    clarification_question: Optional[str] = None
    clarification_candidates: List[Dict[str, Any]] = Field(default_factory=list)
    coverage_assessment: Optional[TerritorialCoverageRecord] = None
    building_intelligence: Optional[BuildingIntelligenceReport] = None
    land_use_intelligence: Optional[LandUseIntelligenceReport] = None
    commercial_context: Optional[CommercialContextReport] = None
    catchment: Optional[CatchmentAreaResult] = None
    mobility_flow: Optional[PopulationFlowReport] = None
    employment_analysis: Optional[EmploymentAnalysisReport] = None
    employment_intervention: Optional[EmploymentInterventionResult] = None
    population_activation: Dict[str, Any] = Field(default_factory=dict)
    activated_engines: List[str] = Field(default_factory=list)
    evidence_package: Optional[TerritorialEvidencePackage] = None
    preparation_certificate: Optional[Dict[str, Any]] = None
    calibration_summary: Optional[Dict[str, Any]] = None
    territorial_expansion: Optional[Dict[str, Any]] = None
    sector_context: Optional[Dict[str, Any]] = None
    evidence_classifications: Dict[str, str] = Field(default_factory=dict)
    seed: int = 42
    horizon_days: int = 30
    parameters: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    baseline_comparison: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0
