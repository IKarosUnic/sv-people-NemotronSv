"""Pluggable Sector-Specific Context Engine (Phase 1.18 Section 10).

Adapts territorial & population discovery to the intervention sector:
- Education (school): levels parvularia..bachillerato, lag, enrollment vs capacity gaps
- Health (clinic/hospital): vulnerable cohorts, facility network, capacity availability
- Market (commerce): households, purchasing power brackets, competition
- Road / Transport: connected districts, corridors, bridges, barriers
Supports registering custom SectorAnalyzers without rewriting the core engine.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List

from saltbor.census_intelligence.schemas import (
    CensusQueryResult,
    DiscoveredTerritorialContext,
    EvidenceClassification,
    InfrastructureInventory,
    MobilityAccessibilityReport,
    ProvenancedIndicator,
    SectorContextReport,
    SyntheticPopulationBatch,
)


class SectorAnalyzer(abc.ABC):
    """Plugin interface for sector-specific contextual intelligence."""

    sector_name: str = "general"

    @abc.abstractmethod
    def analyze(
        self,
        discovery: DiscoveredTerritorialContext,
        census: CensusQueryResult,
        batch: SyntheticPopulationBatch,
        inventory: InfrastructureInventory,
        mobility: MobilityAccessibilityReport,
    ) -> SectorContextReport:
        """Compute sector-specific demand, supply, accessibility & gap report."""


class EducationSectorAnalyzer(SectorAnalyzer):
    """Evaluates educational demand from parvularia through bachillerato & facility gaps."""

    sector_name = "school"

    _LEVEL_AGE_BANDS = [
        ("parvularia", "Parvularia (4–6 años)", 4, 6),
        ("basica_ciclo_1", "Básica 1.er Ciclo (7–9 años)", 7, 9),
        ("basica_ciclo_2", "Básica 2.º Ciclo (10–12 años)", 10, 12),
        ("basica_ciclo_3", "Básica 3.er Ciclo (13–15 años)", 13, 15),
        ("bachillerato", "Bachillerato (16–18 años)", 16, 18),
    ]

    def analyze(
        self,
        discovery: DiscoveredTerritorialContext,
        census: CensusQueryResult,
        batch: SyntheticPopulationBatch,
        inventory: InfrastructureInventory,
        mobility: MobilityAccessibilityReport,
    ) -> SectorContextReport:
        scope = f"{discovery.primary_district_name} ({discovery.primary_district_id})"
        by_level: Dict[str, Dict[str, Any]] = {}
        total_school_age = 0
        total_attending = 0
        total_lag = 0

        for lvl_id, label, lo, hi in self._LEVEL_AGE_BANDS:
            cohort = [p for p in batch.persons if lo <= p.age <= hi]
            w_pop = int(round(sum(p.expansion_weight for p in cohort)))
            w_att = int(round(sum(p.expansion_weight for p in cohort if p.attending_school)))
            w_non = max(0, w_pop - w_att)
            w_lag = int(round(sum(p.expansion_weight for p in cohort if p.educational_lag_years > 0)))
            total_school_age += w_pop
            total_attending += w_att
            total_lag += w_lag
            by_level[lvl_id] = {
                "label": label,
                "school_age_population": w_pop,
                "estimated_attending": w_att,
                "not_attending_or_dropout_risk": w_non,
                "educational_lag_count": w_lag,
            }

        schools = [e for e in inventory.entities if e.domain == "EDUCATION"]
        primary_schools = [s for s in schools if s.zone_tier.value == "PRIMARY_AREA"]
        influence_schools = [s for s in schools if s.zone_tier.value == "INFLUENCE_AREA"]
        contextual_schools = [s for s in schools if s.zone_tier.value == "CONTEXTUAL_AREA"]

        confirmed_capacity_schools = [s for s in schools if s.installed_capacity is not None]
        known_enrollment_schools = [s for s in schools if s.enrollment is not None]

        # Check coverage per educational level (never assume a school offers all levels)
        gaps: List[Dict[str, Any]] = []
        for lvl_id, label, _, _ in self._LEVEL_AGE_BANDS:
            demand = by_level[lvl_id]["school_age_population"]
            matching_in_primary = [s for s in primary_schools if lvl_id in s.confirmed_levels]
            matching_in_ctx = [s for s in schools if lvl_id in s.confirmed_levels]
            if len(matching_in_primary) == 0 and demand > 0:
                gaps.append({
                    "level": lvl_id,
                    "label": label,
                    "demand_students": demand,
                    "schools_in_primary_area_confirmed": 0,
                    "schools_in_context_confirmed": len(matching_in_ctx),
                    "gap_type": "NO_PRIMARY_ZONE_FACILITY" if len(primary_schools) == 0 else "UNVERIFIED_LEVEL_COVERAGE",
                    "evidence_note": (
                        "Cero escuelas dentro del polígono principal; escuelas cercanas ubicadas en área de influencia/contextual."
                        if len(primary_schools) == 0
                        else "Existen centros educativos cercanos pero sus niveles ofrecidos no están confirmados vía MINEDUCYT."
                    ),
                })

        limitations = [
            "No se asume que cada establecimiento OSM ofrezca todos los niveles educativos desde parvularia hasta bachillerato.",
            "La matrícula escolar no se confunde con la capacidad instalada ni con vacantes disponibles.",
        ]
        if not confirmed_capacity_schools:
            limitations.append(
                "Capacidad instalada y vacantes reales por centro escolar son UNAVAILABLE (no se ha importado nómina nominal MINEDUCYT)."
            )

        inds = [
            ProvenancedIndicator(
                indicator_id="edu_school_age_population_est",
                name="Población sintética calibrada en edad escolar (4–18 años)",
                value=total_school_age,
                unit="personas",
                source="SyntheticHouseholdGenerationEngine + Calibration",
                evidence_type=EvidenceClassification.SYNTHETIC_CALIBRATED,
                reference_date="2026-11-23",
                territorial_coverage=scope,
                method="Calibrated synthetic household cohort age 4..18",
                confidence_level=0.78,
                uncertainty="Basado en estructura demográfica Censo 2024 y SAE del área.",
            ),
            ProvenancedIndicator(
                indicator_id="edu_schools_in_primary_area",
                name="Establecimientos educativos observados en Área Principal",
                value=len(primary_schools),
                unit="centros",
                source="OpenStreetMap (ODbL-1.0)",
                evidence_type=EvidenceClassification.DIRECT_OBSERVATION,
                reference_date="2026-11-23",
                territorial_coverage=scope,
                method="Spatial containment in primary polygon",
                confidence_level=0.85,
                uncertainty="Ausencia en OSM no garantiza inexistencia física.",
            ),
            ProvenancedIndicator(
                indicator_id="edu_schools_in_expanded_context",
                name="Establecimientos educativos en Área de Influencia y Contextual",
                value=len(influence_schools) + len(contextual_schools),
                unit="centros",
                source="OpenStreetMap (ODbL-1.0)",
                evidence_type=EvidenceClassification.DIRECT_OBSERVATION,
                reference_date="2026-11-23",
                territorial_coverage=scope,
                method="Dynamic network expansion outside primary polygon",
                confidence_level=0.85,
            ),
            ProvenancedIndicator(
                indicator_id="edu_existing_installed_capacity",
                name="Capacidad instalada confirmada en centros escolares existentes",
                value=sum(s.installed_capacity for s in confirmed_capacity_schools) if confirmed_capacity_schools else None,
                unit="cupos",
                source="MINEDUCYT (registro por centro)",
                evidence_type=(
                    EvidenceClassification.PUBLIC_OFFICIAL
                    if confirmed_capacity_schools
                    else EvidenceClassification.UNAVAILABLE
                ),
                reference_date="2024",
                territorial_coverage=scope,
                method="Direct MINED registry lookup" if confirmed_capacity_schools else "Not imported",
                confidence_level=0.95 if confirmed_capacity_schools else 0.0,
                uncertainty="Dato no disponible sin padrón nominal MINEDUCYT." if not confirmed_capacity_schools else "",
            ),
        ]

        return SectorContextReport(
            sector_name="school",
            target_population_summary={
                "total_school_age_4_18": total_school_age,
                "estimated_attending": total_attending,
                "estimated_not_attending": max(0, total_school_age - total_attending),
                "educational_lag_count": total_lag,
                "by_level": by_level,
            },
            existing_facilities_summary={
                "total_schools_discovered": len(schools),
                "in_primary_area": len(primary_schools),
                "in_influence_area": len(influence_schools),
                "in_contextual_area": len(contextual_schools),
                "with_confirmed_capacity": len(confirmed_capacity_schools),
                "with_known_enrollment": len(known_enrollment_schools),
                "nearest_schools": [
                    {
                        "entity_id": s.entity_id,
                        "name": s.name,
                        "zone_tier": s.zone_tier.value,
                        "distance_m": s.distance_m,
                        "estimated_walk_min": s.estimated_walk_min,
                        "confirmed_levels": s.confirmed_levels,
                        "levels_evidence_status": s.levels_evidence_status,
                        "verification_status": s.verification_status.value,
                        "capacity_evidence_type": s.capacity_evidence_type.value,
                    }
                    for s in schools[:15]
                ],
            },
            accessibility_summary={
                "mean_walk_time_min": mobility.mean_walk_time_to_nearest_service_min,
                "share_within_budget": mobility.share_within_travel_budget,
                "barrier_impacted_students": mobility.barrier_impacted_households,
                "observed_mobility_available": mobility.observed_mobility_available,
            },
            coverage_gaps=gaps,
            domain_details={"levels_evaluated": [lv[0] for lv in self._LEVEL_AGE_BANDS]},
            provenanced_indicators=inds,
            limitations=limitations,
        )


class HealthSectorAnalyzer(SectorAnalyzer):
    """Evaluates health service demand, vulnerable age groups & clinic/hospital access."""

    sector_name = "health"

    def analyze(
        self,
        discovery: DiscoveredTerritorialContext,
        census: CensusQueryResult,
        batch: SyntheticPopulationBatch,
        inventory: InfrastructureInventory,
        mobility: MobilityAccessibilityReport,
    ) -> SectorContextReport:
        health_facs = [e for e in inventory.entities if e.domain == "HEALTH"]
        under_5 = int(round(sum(p.expansion_weight for p in batch.persons if p.age < 5)))
        elders = int(round(sum(p.expansion_weight for p in batch.persons if p.age >= 65)))
        women_repro = int(round(sum(p.expansion_weight for p in batch.persons if p.sex == "F" and 15 <= p.age <= 49)))
        confirmed = [h for h in health_facs if h.installed_capacity is not None]

        gaps: List[Dict[str, Any]] = []
        if not any(h.zone_tier.value == "PRIMARY_AREA" for h in health_facs):
            gaps.append({
                "gap_type": "NO_PRIMARY_HEALTH_FACILITY",
                "vulnerable_residents": under_5 + elders,
                "note": "Sin unidad de salud o clínica registrada dentro del área principal.",
            })

        return SectorContextReport(
            sector_name="health",
            target_population_summary={
                "represented_population": batch.represented_population_total,
                "children_under_5": under_5,
                "elderly_65_plus": elders,
                "women_reproductive_age_15_49": women_repro,
            },
            existing_facilities_summary={
                "total_health_facilities": len(health_facs),
                "hospitals_or_clinics": sum(1 for h in health_facs if h.subtype != "pharmacy"),
                "pharmacies": sum(1 for h in health_facs if h.subtype == "pharmacy"),
                "with_confirmed_capacity": len(confirmed),
                "nearest_facilities": [
                    {"name": h.name, "subtype": h.subtype, "zone_tier": h.zone_tier.value, "distance_m": h.distance_m}
                    for h in health_facs[:10]
                ],
            },
            accessibility_summary={
                "mean_walk_time_min": mobility.mean_walk_time_to_nearest_service_min,
                "share_within_budget": mobility.share_within_travel_budget,
            },
            coverage_gaps=gaps,
            limitations=["Capacidad instalada y personal médico MINSAL son UNAVAILABLE sin importación nominal."],
        )


class MarketSectorAnalyzer(SectorAnalyzer):
    """Evaluates household purchasing power, residential density & commercial competition."""

    sector_name = "market"

    def analyze(
        self,
        discovery: DiscoveredTerritorialContext,
        census: CensusQueryResult,
        batch: SyntheticPopulationBatch,
        inventory: InfrastructureInventory,
        mobility: MobilityAccessibilityReport,
    ) -> SectorContextReport:
        econ_facs = [e for e in inventory.entities if e.domain == "ECONOMY"]
        area_km2 = max(0.01, discovery.expansion.primary_area.area_km2)
        hh_density = round(batch.represented_households_total / area_km2, 1)
        tot_income_usd = round(sum(h.estimated_monthly_income_usd * h.expansion_weight for h in batch.households), 2)
        stratum_counts: Dict[str, int] = {}
        for h in batch.households:
            stratum_counts[h.socioeconomic_stratum] = stratum_counts.get(h.socioeconomic_stratum, 0) + int(round(h.expansion_weight))

        return SectorContextReport(
            sector_name="market",
            target_population_summary={
                "represented_households": batch.represented_households_total,
                "household_density_per_km2": hh_density,
                "estimated_aggregate_monthly_income_usd": tot_income_usd,
                "socioeconomic_strata": stratum_counts,
            },
            existing_facilities_summary={
                "total_commercial_entities": len(econ_facs),
                "in_primary_area": sum(1 for e in econ_facs if e.zone_tier.value == "PRIMARY_AREA"),
                "in_influence_area": sum(1 for e in econ_facs if e.zone_tier.value == "INFLUENCE_AREA"),
                "markets_and_supermarkets": sum(1 for e in econ_facs if "market" in e.subtype or "super" in e.subtype),
            },
            accessibility_summary={
                "mean_walk_time_min": mobility.mean_walk_time_to_nearest_service_min,
                "share_within_budget": mobility.share_within_travel_budget,
            },
            coverage_gaps=[],
            limitations=["Comercio informal callejero subrepresentado en OpenStreetMap."],
        )


class RoadSectorAnalyzer(SectorAnalyzer):
    """Evaluates road connectivity, connected districts, transit stops & geographic barriers."""

    sector_name = "road"

    def analyze(
        self,
        discovery: DiscoveredTerritorialContext,
        census: CensusQueryResult,
        batch: SyntheticPopulationBatch,
        inventory: InfrastructureInventory,
        mobility: MobilityAccessibilityReport,
    ) -> SectorContextReport:
        infra_facs = [e for e in inventory.entities if e.domain == "INFRASTRUCTURE"]
        env_facs = [e for e in inventory.entities if e.domain == "ENVIRONMENT"]
        exp = discovery.expansion
        return SectorContextReport(
            sector_name="road",
            target_population_summary={
                "represented_population": batch.represented_population_total,
                "connected_districts": [u["district_name"] for u in discovery.intersecting_units],
            },
            existing_facilities_summary={
                "transit_nodes_discovered": len(infra_facs),
                "environmental_barriers_entities": len(env_facs),
                "bridges_crossings_detected": exp.contextual_area.bridges_crossings_detected,
                "road_circuity_factor": exp.influence_area.circuity_factor,
            },
            accessibility_summary={
                "barriers_detected": exp.contextual_area.barriers_detected,
                "mean_walk_time_min": mobility.mean_walk_time_to_nearest_service_min,
            },
            coverage_gaps=[
                {"gap_type": "ROAD_BARRIER_OR_RESTRICTIONS", "detail": b}
                for b in exp.contextual_area.barriers_detected
            ],
            limitations=["Frecuencias y rutas exactas de transporte público no disponibles en OSM."],
        )


class SectorSpecificContextEngine:
    """Extensible registry dispatching adaptive contextual analysis by sector."""

    def __init__(self) -> None:
        self._analyzers: Dict[str, SectorAnalyzer] = {}
        self.register_sector("school", EducationSectorAnalyzer())
        self.register_sector("education", EducationSectorAnalyzer())
        self.register_sector("health", HealthSectorAnalyzer())
        self.register_sector("clinic", HealthSectorAnalyzer())
        self.register_sector("hospital", HealthSectorAnalyzer())
        self.register_sector("market", MarketSectorAnalyzer())
        self.register_sector("commerce", MarketSectorAnalyzer())
        self.register_sector("road", RoadSectorAnalyzer())
        self.register_sector("transport", RoadSectorAnalyzer())

    def register_sector(self, name: str, analyzer: SectorAnalyzer) -> None:
        """Register a new sector analyzer plugin without modifying the core engine."""
        self._analyzers[name.strip().lower()] = analyzer

    def list_sectors(self) -> List[str]:
        return sorted(self._analyzers.keys())

    def analyze(
        self,
        sector: str,
        discovery: DiscoveredTerritorialContext,
        census: CensusQueryResult,
        batch: SyntheticPopulationBatch,
        inventory: InfrastructureInventory,
        mobility: MobilityAccessibilityReport,
    ) -> SectorContextReport:
        key = (sector or "general").strip().lower()
        analyzer = self._analyzers.get(key)
        if analyzer is None:
            # Default composite summary reusing market + road context
            return MarketSectorAnalyzer().analyze(discovery, census, batch, inventory, mobility)
        return analyzer.analyze(discovery, census, batch, inventory, mobility)
