"""Pydantic v2 Schemas & Universal Provenance Contracts for SALTBOR Phase 1.18."""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field


class EvidenceClassification(str, enum.Enum):
    """Mandatory 8-class universal provenance taxonomy (Phase 1.18 Section 14)."""

    PUBLIC_OFFICIAL = "PUBLIC_OFFICIAL"
    DIRECT_OBSERVATION = "DIRECT_OBSERVATION"
    ESTIMATED_FROM_OFFICIAL = "ESTIMATED_FROM_OFFICIAL"
    SYNTHETIC_CALIBRATED = "SYNTHETIC_CALIBRATED"
    SYNTHETIC_UNCALIBRATED = "SYNTHETIC_UNCALIBRATED"
    DETERMINISTIC_MULTIPLIER = "DETERMINISTIC_MULTIPLIER"
    HYPOTHESIS = "HYPOTHESIS"
    UNAVAILABLE = "UNAVAILABLE"


class GeographicGranularity(str, enum.Enum):
    """Statistical reporting granularity levels."""

    NATIONAL = "NATIONAL"
    DEPARTMENT = "DEPARTMENT"
    MUNICIPALITY = "MUNICIPALITY"
    DISTRICT = "DISTRICT"
    CANTON = "CANTON"
    SECTOR_CENSAL = "SECTOR_CENSAL"
    MANZANA = "MANZANA"
    CUSTOM_POLYGON = "CUSTOM_POLYGON"
    URBAN_RURAL_STRATUM = "URBAN_RURAL_STRATUM"


class VerificationStatus(str, enum.Enum):
    """Verification state for territorial infrastructure & service entities (Section 9)."""

    OSM_IDENTIFIED = "OSM_IDENTIFIED"
    OFFICIAL_CONFIRMED = "OFFICIAL_CONFIRMED"
    FIELD_VERIFIED = "FIELD_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    POSSIBLY_INACTIVE = "POSSIBLY_INACTIVE"


class ZoneTier(str, enum.Enum):
    """Three dynamic territorial scales (Section 5)."""

    PRIMARY_AREA = "PRIMARY_AREA"
    INFLUENCE_AREA = "INFLUENCE_AREA"
    CONTEXTUAL_AREA = "CONTEXTUAL_AREA"


class MobilityEvidenceType(str, enum.Enum):
    """Strict separation between observed, estimated, and synthetic mobility (Section 11)."""

    OBSERVED_MOBILITY = "OBSERVED_MOBILITY"
    ESTIMATED_MOBILITY = "ESTIMATED_MOBILITY"
    SYNTHETIC_MOBILITY = "SYNTHETIC_MOBILITY"


class ProvenancedIndicator(BaseModel):
    """Universal evidence indicator carrying full Phase 1.18 Section 14 provenance."""

    indicator_id: str
    name: str
    value: Any = None
    unit: str = ""
    source: str
    evidence_type: EvidenceClassification
    reference_date: str
    territorial_coverage: str
    method: str
    confidence_level: float = Field(ge=0.0, le=1.0)
    uncertainty: str = ""
    validation_status: str = "VERIFIED"


def validate_provenance_integrity(indicators: List[ProvenancedIndicator]) -> Dict[str, Any]:
    """Audit indicators to guarantee synthetic/estimated/unavailable items never impersonate PUBLIC_OFFICIAL."""
    violations: List[Dict[str, str]] = []
    counts_by_type: Dict[str, int] = {t.value: 0 for t in EvidenceClassification}

    for ind in indicators:
        counts_by_type[ind.evidence_type.value] = counts_by_type.get(ind.evidence_type.value, 0) + 1
        src_l = (ind.source or "").lower()
        meth_l = (ind.method or "").lower()

        if ind.evidence_type == EvidenceClassification.UNAVAILABLE:
            if ind.value is not None:
                violations.append({
                    "indicator_id": ind.indicator_id,
                    "reason": "UNAVAILABLE indicator must carry value=None.",
                })
            if ind.confidence_level > 0.0:
                violations.append({
                    "indicator_id": ind.indicator_id,
                    "reason": "UNAVAILABLE indicator must have confidence_level=0.0.",
                })

        if ind.evidence_type == EvidenceClassification.PUBLIC_OFFICIAL:
            if any(tok in src_l or tok in meth_l for tok in ("synthetic", "sintet", "sae", "small area", "hypothesis", "hipotes", "raking", "ipf")):
                violations.append({
                    "indicator_id": ind.indicator_id,
                    "reason": "Synthetic, SAE, or hypothetical indicator cannot be labeled PUBLIC_OFFICIAL.",
                })

    return {
        "valid": len(violations) == 0,
        "total_indicators": len(indicators),
        "counts_by_type": counts_by_type,
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Census Integration Models (Section 3)
# ---------------------------------------------------------------------------

class CensusDatasetMetadata(BaseModel):
    """Versioned metadata and granularity audit for an integrated statistical dataset."""

    dataset_id: str
    adapter_name: str
    title: str
    source_institution: str
    source_url: str = ""
    license: str = "Public Sector Information (LAIP El Salvador)"
    version: str
    published_at: str
    updated_at: str
    reference_year: int
    available_granularities: List[GeographicGranularity] = Field(default_factory=list)
    unavailable_granularities: List[GeographicGranularity] = Field(default_factory=list)
    record_count: int = 0
    duplicates_detected: int = 0
    content_sha256: str = ""
    limitations: List[str] = Field(default_factory=list)


class CensusVariableRecord(BaseModel):
    """Normalized official or derived statistical record linked to a geographic unit."""

    dataset_id: str
    dataset_version: str
    source_institution: str
    geographic_unit_id: str
    geographic_unit_name: str
    granularity: GeographicGranularity
    variable_name: str
    value: float | int | str | Dict[str, Any]
    unit: str = ""
    reference_year: int
    published_at: str
    evidence_type: EvidenceClassification = EvidenceClassification.PUBLIC_OFFICIAL
    confidence_level: float = Field(default=0.92, ge=0.0, le=1.0)
    notes: str = ""


class CensusImportResult(BaseModel):
    """Outcome of importing a CSV, XLSX, JSON, or GeoJSON census/official dataset."""

    dataset_id: str
    version: str
    file_format: str
    records_imported: int
    duplicates_skipped: int
    validation_errors: List[str] = Field(default_factory=list)
    pii_columns_blocked: List[str] = Field(default_factory=list)
    detected_granularity: GeographicGranularity
    content_sha256: str
    success: bool = True


class SmallAreaEstimate(BaseModel):
    """Explicit Small Area Estimation output when sub-district official counts do not exist."""

    target_area_label: str
    requested_granularity: GeographicGranularity
    parent_official_unit_id: str
    parent_official_unit_name: str
    parent_official_granularity: GeographicGranularity
    parent_official_population: int
    estimated_population: int
    estimated_households: int
    sae_method: str
    uncertainty_pct: float
    confidence_interval_95: Tuple[int, int]
    evidence_type: EvidenceClassification = EvidenceClassification.ESTIMATED_FROM_OFFICIAL
    confidence_level: float = Field(ge=0.0, le=1.0)
    limitations: List[str] = Field(default_factory=list)


class CensusQueryResult(BaseModel):
    """Structured statistical query outcome preserving granularity & missing-variable honesty."""

    query_unit_id: str
    query_unit_name: str
    requested_granularity: GeographicGranularity
    matched_granularity: GeographicGranularity
    exact_granularity_available: bool
    official_population: Optional[int] = None
    population_evidence_type: EvidenceClassification
    sae_estimate: Optional[SmallAreaEstimate] = None
    sex_distribution: Dict[str, float] = Field(default_factory=dict)
    age_groups_distribution: Dict[str, float] = Field(default_factory=dict)
    household_size_distribution: Dict[str, float] = Field(default_factory=dict)
    mean_household_size: float = 3.1
    female_headed_household_share: float = 0.45
    unoccupied_dwellings_share: float = 0.189
    ehpm_priors: Dict[str, Any] = Field(default_factory=dict)
    mined_macro: Dict[str, Any] = Field(default_factory=dict)
    available_variables: List[str] = Field(default_factory=list)
    unavailable_variables: List[str] = Field(default_factory=list)
    source_datasets: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Territorial Discovery & Dynamic 3-Scale Expansion Models (Sections 4 & 5)
# ---------------------------------------------------------------------------

class TerritorialSelectionInput(BaseModel):
    """User selection: point, polygon GeoJSON, administrative query, travel time & sector."""

    query: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    polygon_geojson: Optional[Dict[str, Any]] = None
    travel_time_minutes: float = Field(default=15.0, ge=1.0, le=120.0)
    custom_travel_times_minutes: List[float] = Field(default_factory=lambda: [5.0, 10.0, 15.0, 20.0])
    transport_mode: Literal["walk", "drive", "mixed"] = "walk"
    sector: str = "general"
    max_expansion_minutes: float = Field(default=30.0, ge=5.0, le=180.0)
    max_expansion_km: float = Field(default=8.0, ge=0.5, le=50.0)
    allow_online_osm: bool = False
    seed: int = 42


class TerritorialScaleArea(BaseModel):
    """Geometry and metrics for one of the 3 scales (Primary, Influence, Contextual)."""

    zone_tier: ZoneTier
    label: str
    area_km2: float
    radius_equiv_km: float
    travel_time_minutes: float
    transport_mode: str
    geometry_geojson: Dict[str, Any]
    bbox: List[float] = Field(default_factory=list)
    intersecting_districts: List[str] = Field(default_factory=list)
    network_nodes_count: int = 0
    network_edges_count: int = 0
    circuity_factor: float = 1.0
    barriers_detected: List[str] = Field(default_factory=list)
    bridges_crossings_detected: int = 0
    access_restrictions_detected: int = 0


class TerritorialExpansionResult(BaseModel):
    """Dynamic multi-scale expansion output including limit warnings."""

    primary_area: TerritorialScaleArea
    influence_area: TerritorialScaleArea
    contextual_area: TerritorialScaleArea
    isochrones_by_minutes: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    crossed_administrative_boundaries: bool = False
    expansion_limit_reached: bool = False
    expansion_limit_reason: Optional[str] = None
    rings_explored: int = 1
    external_facilities_captured: int = 0
    methodology: str


class DiscoveredTerritorialContext(BaseModel):
    """Complete geographic + administrative + expansion discovery payload."""

    selection_mode: Literal["point", "polygon", "administrative_query"]
    center_lat: float
    center_lon: float
    primary_district_id: str
    primary_district_name: str
    municipality_id: str
    municipality_name: str
    department_code: str
    department_name: str
    is_urban: bool
    elevation_m: float
    slope_pct: float
    tobler_walking_speed_factor: float
    intersecting_units: List[Dict[str, Any]] = Field(default_factory=list)
    expansion: TerritorialExpansionResult
    osm_attribution: str = "© OpenStreetMap contributors, ODbL 1.0"
    cache_hit: bool = False
    offline_mode: bool = True
    missing_geographic_info: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Geospatial Population Allocation & Synthetic Households (Sections 6, 7 & 8)
# ---------------------------------------------------------------------------

class BuildingAllocationRecord(BaseModel):
    """Spatial allocation weight of a single building footprint (never Building == Household)."""

    feature_id: str
    lat: float
    lon: float
    source_building_class: str
    allocated_residential: bool
    exclusion_reason: Optional[str] = None
    surface_area_m2: float = 0.0
    estimated_dwellings: float = 0.0
    estimated_occupied_households: int = 0
    occupancy_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    occupancy_uncertain: bool = False


class PopulationAllocationResult(BaseModel):
    """Dasymetric & probabilistic residential allocation constrained to statistical totals."""

    district_id: str
    district_official_population: int
    target_area_km2: float
    district_reference_residential_area_m2: float
    polygon_residential_area_m2: float
    polygon_share_of_district: float
    allocated_population_target: int
    allocated_households_target: int
    buildings_analyzed: int
    buildings_residential_confirmed: int
    buildings_unknown_probabilistic: int
    buildings_excluded_non_residential: int
    excluded_counts_by_class: Dict[str, int] = Field(default_factory=dict)
    building_anchors: List[BuildingAllocationRecord] = Field(default_factory=list)
    allocation_method: str
    evidence_type: EvidenceClassification
    uncertainty_pct: float
    limitations: List[str] = Field(default_factory=list)


class SyntheticPerson(BaseModel):
    """Statistically grounded synthetic person generated inside a household (zero PII)."""

    person_id: str
    household_id: str
    age: int = Field(ge=0, le=110)
    age_group: str
    sex: Literal["M", "F"]
    relationship_to_head: Literal["head", "spouse", "child", "elder_relative", "other_relative"]
    # Education
    education_level: str
    schooling_years: int = Field(ge=0, le=25)
    enrolled_level: Optional[str] = None
    attending_school: Optional[bool] = None
    educational_lag_years: int = 0
    # Economy
    activity_condition: Literal["employed", "unemployed", "student", "inactive_home", "retired", "child_under_5"]
    occupation: str
    employment_formality: Literal["formal", "informal", "not_applicable", "unknown"] = "not_applicable"
    monthly_income_interval_usd: Optional[str] = None
    estimated_monthly_income_usd: Optional[float] = None
    socioeconomic_stratum: str = "medium_low"
    # Mobility & Behavior
    home_lat: float
    home_lon: float
    habitual_destination_type: str
    mobility_need_category: str
    cost_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    expansion_weight: float = Field(default=1.0, ge=0.0)
    unavailable_attributes: List[str] = Field(default_factory=list)


class SyntheticHousehold(BaseModel):
    """Synthetic household created BEFORE generating individual members (Section 7)."""

    household_id: str
    building_feature_id: Optional[str] = None
    home_lat: float
    home_lon: float
    district_id: str
    household_size: int = Field(ge=1)
    family_composition: Literal["nuclear", "extended", "single_parent", "unipersonal"]
    head_sex: Literal["M", "F"]
    dependents_count: int = 0
    children_adolescents_count: int = 0
    adults_count: int = 0
    elderly_count: int = 0
    monthly_income_bracket_usd: str
    estimated_monthly_income_usd: float
    socioeconomic_stratum: Literal["low", "medium_low", "medium", "medium_high"]
    housing_tenure: Literal["owned", "rented_or_other", "unknown"] = "unknown"
    expansion_weight: float = Field(default=1.0, ge=0.0)
    member_ids: List[str] = Field(default_factory=list)


class SyntheticPopulationBatch(BaseModel):
    """Batch of calibrated synthetic households and persons with hybrid scale metadata."""

    batch_id: str
    seed: int
    district_id: str
    area_label: str
    generation_scale: Literal["COMMUNITY", "ZONE", "DISTRICT", "MUNICIPALITY", "DEPARTMENT", "NATIONAL"]
    represented_population_total: int
    represented_households_total: int
    simulated_sample_persons: int
    simulated_sample_households: int
    is_weighted_cohort: bool = False
    households: List[SyntheticHousehold] = Field(default_factory=list)
    persons: List[SyntheticPerson] = Field(default_factory=list)


class VariableCalibrationMetric(BaseModel):
    """Per-variable goodness-of-fit comparing generated synthetic distribution vs official data."""

    variable_name: str
    calibrated: bool
    target_distribution: Dict[str, float] = Field(default_factory=dict)
    generated_distribution: Dict[str, float] = Field(default_factory=dict)
    max_absolute_diff: float
    mean_absolute_error: float
    relative_error_pct: float


class CalibrationReport(BaseModel):
    """Mandatory validation output from PopulationCalibrationEngine (Section 8)."""

    methods_applied: List[str] = Field(default_factory=list)
    ipf_converged: bool = True
    ipf_iterations: int = 0
    raking_converged: bool = True
    combinatorial_optimization_steps: int = 0
    tae_before: float = 0.0
    tae_after: float = 0.0
    srmse: float = 0.0
    max_relative_error_pct: float = 0.0
    statistical_coverage_pct: float = 0.0
    variable_metrics: List[VariableCalibrationMetric] = Field(default_factory=list)
    uncalibrated_variables: List[str] = Field(default_factory=list)
    calibration_passed: bool = True
    evidence_classification: EvidenceClassification = EvidenceClassification.SYNTHETIC_CALIBRATED
    confidence_level: float = Field(default=0.82, ge=0.0, le=1.0)
    uncertainty_score: float = Field(default=0.18, ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)


class PopulationPreparationCertificate(BaseModel):
    """Mandatory certificate attached before ANY simulation runs (Section 2)."""

    certificate_id: str
    prepared_at: str
    seed: int
    territorial_scope: str
    census_sources_used: List[str] = Field(default_factory=list)
    census_granularity_used: GeographicGranularity
    statistical_coverage_pct: float
    calibration_status: Literal["CALIBRATED_ACCEPTABLE", "CALIBRATED_WITH_WARNINGS", "UNCALIBRATED_LOW_CONFIDENCE"]
    srmse: float
    confidence_level: float = Field(ge=0.0, le=1.0)
    uncertainty_score: float = Field(ge=0.0, le=1.0)
    evidence_classification: EvidenceClassification
    limitations: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Infrastructure, Sector Context, Mobility & Pipeline Models (Sections 9, 10, 11)
# ---------------------------------------------------------------------------

class InfrastructureEntity(BaseModel):
    """Discovered service or physical infrastructure entity with provenance & verification."""

    entity_id: str
    name: str
    domain: Literal["EDUCATION", "HEALTH", "ECONOMY", "INFRASTRUCTURE", "ENVIRONMENT"]
    subtype: str
    lat: float
    lon: float
    zone_tier: ZoneTier
    distance_m: float
    estimated_walk_min: Optional[float] = None
    estimated_drive_min: Optional[float] = None
    source: str
    updated_at: str
    verification_status: VerificationStatus
    confidence_level: float = Field(ge=0.0, le=1.0)
    # Education / service specific attributes (never fabricated)
    confirmed_levels: List[str] = Field(default_factory=list)
    levels_evidence_status: Literal["OFFICIAL_CONFIRMED", "TOKEN_INFERRED", "UNVERIFIED", "NOT_APPLICABLE"] = "NOT_APPLICABLE"
    enrollment: Optional[int] = None
    installed_capacity: Optional[int] = None
    available_vacancies: Optional[int] = None
    capacity_evidence_type: EvidenceClassification = EvidenceClassification.UNAVAILABLE
    raw_tags: Dict[str, Any] = Field(default_factory=dict)


class InfrastructureInventory(BaseModel):
    """Deduplicated inventory across Primary, Influence, and Contextual areas."""

    entities: List[InfrastructureEntity] = Field(default_factory=list)
    counts_by_domain: Dict[str, int] = Field(default_factory=dict)
    counts_by_zone_tier: Dict[str, int] = Field(default_factory=dict)
    counts_by_verification_status: Dict[str, int] = Field(default_factory=dict)
    duplicates_merged: int = 0
    non_omission_notice: str = (
        "La ausencia de un establecimiento en OpenStreetMap no garantiza su inexistencia en terreno."
    )


class SectorContextReport(BaseModel):
    """Adaptive sector analysis (education, health, market, road, or plugin)."""

    sector_name: str
    target_population_summary: Dict[str, Any] = Field(default_factory=dict)
    existing_facilities_summary: Dict[str, Any] = Field(default_factory=dict)
    accessibility_summary: Dict[str, Any] = Field(default_factory=dict)
    coverage_gaps: List[Dict[str, Any]] = Field(default_factory=list)
    domain_details: Dict[str, Any] = Field(default_factory=dict)
    provenanced_indicators: List[ProvenancedIndicator] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class MobilityAccessibilityReport(BaseModel):
    """Connects synthetic households/persons to discovered services with strict evidence typing."""

    observed_mobility_available: bool = False
    observed_mobility_note: str = (
        "Sin mediciones observadas de conteo o matrices OD reales en el área; toda asignación es estimada o sintética."
    )
    households_connected: int = 0
    persons_evaluated: int = 0
    mean_walk_time_to_nearest_service_min: Optional[float] = None
    share_within_travel_budget: float = 0.0
    barrier_impacted_households: int = 0
    facility_demand_assignments: Dict[str, int] = Field(default_factory=dict)
    unserved_demand_count: int = 0
    declared_hypotheses: List[str] = Field(default_factory=list)
    provenanced_indicators: List[ProvenancedIndicator] = Field(default_factory=list)


class TerritorialPreparationResult(BaseModel):
    """Full Phase 1.18 output emitted by TerritorialPreparationPipeline prior to simulation."""

    preparation_id: str
    discovery: DiscoveredTerritorialContext
    census_query: CensusQueryResult
    allocation: PopulationAllocationResult
    population_batch: SyntheticPopulationBatch
    calibration: CalibrationReport
    certificate: PopulationPreparationCertificate
    infrastructure: InfrastructureInventory
    sector_context: SectorContextReport
    mobility_accessibility: MobilityAccessibilityReport
    provenanced_indicators: List[ProvenancedIndicator] = Field(default_factory=list)
    provenance_integrity: Dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: float = 0.0
