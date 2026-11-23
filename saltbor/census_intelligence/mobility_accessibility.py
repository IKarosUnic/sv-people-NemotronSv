"""Human Mobility & Territorial Accessibility Engine (Phase 1.18 Section 11).

Connects calibrated synthetic households and individuals to discovered
infrastructure and services across Primary, Influence, and Contextual zones.
Strictly differentiates:
- OBSERVED_MOBILITY (street counts / OD telemetry -> UNAVAILABLE offline)
- ESTIMATED_MOBILITY (GIS network reachability, travel time, barriers)
- SYNTHETIC_MOBILITY (household/agent destination choices & scenario responses)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from saltbor.world.geographic.osm_router import haversine_m

from saltbor.census_intelligence.schemas import (
    DiscoveredTerritorialContext,
    EvidenceClassification,
    InfrastructureEntity,
    InfrastructureInventory,
    MobilityAccessibilityReport,
    ProvenancedIndicator,
    SyntheticPopulationBatch,
)


class HumanMobilityAccessibilityEngine:
    """Connects synthetic households to territorial services and reacts to interventions."""

    _SECTOR_DOMAIN_MAP = {
        "school": "EDUCATION",
        "education": "EDUCATION",
        "health": "HEALTH",
        "clinic": "HEALTH",
        "hospital": "HEALTH",
        "market": "ECONOMY",
        "commerce": "ECONOMY",
        "road": "INFRASTRUCTURE",
        "transport": "INFRASTRUCTURE",
    }

    def analyze_accessibility(
        self,
        discovery: DiscoveredTerritorialContext,
        batch: SyntheticPopulationBatch,
        inventory: InfrastructureInventory,
        sector: str = "general",
        travel_time_budget_min: float = 15.0,
        hypothetical_facilities: Optional[List[InfrastructureEntity]] = None,
        capacity_expansions: Optional[Dict[str, int]] = None,
    ) -> MobilityAccessibilityReport:
        """Assign synthetic households/agents to accessible services with transparent hypotheses."""
        target_domain = self._SECTOR_DOMAIN_MAP.get(sector.lower())
        all_entities = list(inventory.entities) + list(hypothetical_facilities or [])

        if target_domain:
            candidates = [e for e in all_entities if e.domain == target_domain]
        else:
            candidates = [e for e in all_entities if e.domain in ("EDUCATION", "HEALTH", "ECONOMY")]

        tobler = max(0.45, float(discovery.tobler_walking_speed_factor or 0.85))
        circuity = max(1.0, float(discovery.expansion.influence_area.circuity_factor or 1.25))
        walk_m_per_min = 1.25 * tobler * 60.0
        has_barrier = len(discovery.expansion.influence_area.barriers_detected) > 0
        barrier_penalty_min = 2.0 if has_barrier else 0.0

        # Effective capacities if configured or hypothesized
        remaining_cap: Dict[str, Optional[int]] = {}
        for e in candidates:
            cap = e.available_vacancies if e.available_vacancies is not None else e.installed_capacity
            if capacity_expansions and e.entity_id in capacity_expansions:
                cap = (cap or 0) + int(capacity_expansions[e.entity_id])
            remaining_cap[e.entity_id] = cap

        hh_walk_times: List[float] = []
        within_budget = 0
        barrier_impacted = 0
        facility_demand: Dict[str, int] = {}
        unserved = 0

        # If sector is school/education, route school-age individuals weighted; else route households
        if target_domain == "EDUCATION":
            demand_units = [p for p in batch.persons if 4 <= p.age <= 18]
        else:
            demand_units = batch.households  # type: ignore[assignment]

        for unit in demand_units:
            ulat = unit.home_lat
            ulon = unit.home_lon
            weight = int(max(1, round(unit.expansion_weight)))

            # Filter compatible education levels when confirmed/inferred
            best_entity: Optional[InfrastructureEntity] = None
            best_score = math.inf
            best_walk = math.inf

            for fac in candidates:
                if target_domain == "EDUCATION" and hasattr(unit, "enrolled_level"):
                    req_lvl = getattr(unit, "enrolled_level", None)
                    if req_lvl and fac.confirmed_levels:
                        # If facility only confirms e.g. university or preschool, skip mismatch
                        if "superior" in fac.confirmed_levels and len(fac.confirmed_levels) == 1:
                            continue
                        if fac.confirmed_levels == ["parvularia"] and req_lvl != "parvularia":
                            continue
                d_m = haversine_m(ulat, ulon, fac.lat, fac.lon)
                walk_t = (d_m * circuity) / max(1.0, walk_m_per_min)
                if d_m > 350.0 and has_barrier:
                    walk_t += barrier_penalty_min
                cap = remaining_cap.get(fac.entity_id)
                if cap is not None and cap <= 0:
                    continue
                # Utility penalty for cost sensitivity on private/distant options
                score = walk_t
                if score < best_score:
                    best_score = score
                    best_entity = fac
                    best_walk = walk_t

            if best_entity is None:
                unserved += weight
            else:
                hh_walk_times.append(best_walk)
                if best_walk <= travel_time_budget_min:
                    within_budget += weight
                if best_walk > travel_time_budget_min and has_barrier:
                    barrier_impacted += weight
                facility_demand[best_entity.entity_id] = facility_demand.get(best_entity.entity_id, 0) + weight
                if remaining_cap.get(best_entity.entity_id) is not None:
                    remaining_cap[best_entity.entity_id] = max(0, int(remaining_cap[best_entity.entity_id]) - weight)

        total_units = max(1, sum(int(max(1, round(u.expansion_weight))) for u in demand_units))
        mean_walk = round(sum(hh_walk_times) / len(hh_walk_times), 2) if hh_walk_times else None
        share_within = round(within_budget / total_units, 3)

        hypotheses = [
            f"Velocidad peatonal Tobler estimada: {1.25 * tobler:.2f} m/s con factor de rodeo vial {circuity:.2f}x.",
            "En ausencia de conteos origen-destino reales, la elección de establecimientos representa comportamiento sintético de mínima fricción temporal.",
        ]
        if hypothetical_facilities:
            hypotheses.append(f"Se incorporaron {len(hypothetical_facilities)} establecimiento(s) hipotético(s) de escenario para evaluar reasignación de demanda.")

        scope = f"{discovery.primary_district_name} ({discovery.primary_district_id})"
        inds = [
            ProvenancedIndicator(
                indicator_id="mobility_observed_od_counts",
                name="Conteos observados de movilidad / matrices OD reales",
                value=None,
                unit="viajes/día",
                source="Telemetría / Encuesta OD",
                evidence_type=EvidenceClassification.UNAVAILABLE,
                reference_date="2026-11-23",
                territorial_coverage=scope,
                method="Direct sensor/survey check (unavailable)",
                confidence_level=0.0,
                uncertainty="Sin mediciones reales conectadas.",
            ),
            ProvenancedIndicator(
                indicator_id="mobility_estimated_walk_time_mean",
                name="Tiempo peatonal estimado al servicio más cercano",
                value=mean_walk,
                unit="minutos",
                source="OSMRoadNetwork + Tobler Slope",
                evidence_type=EvidenceClassification.ESTIMATED_FROM_OFFICIAL,
                reference_date="2026-11-23",
                territorial_coverage=scope,
                method="Haversine × circuity_factor / Tobler walking speed",
                confidence_level=0.72,
                uncertainty="Depende de geometría OSM y ausencia de horarios de buses.",
            ),
            ProvenancedIndicator(
                indicator_id="mobility_synthetic_share_within_budget",
                name=f"Cobertura sintética dentro de {travel_time_budget_min:.0f} min",
                value=share_within,
                unit="ratio",
                source="HumanMobilityAccessibilityEngine",
                evidence_type=EvidenceClassification.SYNTHETIC_CALIBRATED,
                reference_date="2026-11-23",
                territorial_coverage=scope,
                method="Synthetic household/student bounded-rationality service assignment",
                confidence_level=0.70,
                uncertainty="Modelo de comportamiento sintético bajo hipótesis declaradas.",
            ),
        ]

        return MobilityAccessibilityReport(
            observed_mobility_available=False,
            households_connected=len(batch.households),
            persons_evaluated=len(batch.persons),
            mean_walk_time_to_nearest_service_min=mean_walk,
            share_within_travel_budget=share_within,
            barrier_impacted_households=barrier_impacted,
            facility_demand_assignments=facility_demand,
            unserved_demand_count=unserved,
            declared_hypotheses=hypotheses,
            provenanced_indicators=inds,
        )
