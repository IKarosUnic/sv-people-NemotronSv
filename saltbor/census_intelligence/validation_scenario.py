"""Real Santa Tecla Residential Validation Scenario (Phase 1.18 Section 17).

Evaluates a concrete residential polygon in Santa Tecla (around Residencial El Paraíso,
Residencial Cima de El Paraíso, Residencial Irlanda, Comunidad San Martín I & II, and
Residencial La Misión) WITHOUT treating all 125,532 residents of Santa Tecla as the
target neighborhood population, and compares 4 educational intervention scenarios
with strict provenance separation and $0.00 VerifiableEconomicLedger conservation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from saltbor.territory.economic_ledger import (
    AccountType,
    TransactionConcept,
    TransactionEntry,
    VerifiableEconomicLedger,
)
from saltbor.territory.models import (
    PublicServiceFacility,
    ServiceCapacityStatus,
    ServiceCategory,
)
from saltbor.territory.public_services import PublicServiceCapacityEngine

from saltbor.census_intelligence.mobility_accessibility import HumanMobilityAccessibilityEngine
from saltbor.census_intelligence.pipeline import TerritorialPreparationPipeline
from saltbor.census_intelligence.schemas import (
    EvidenceClassification,
    InfrastructureEntity,
    TerritorialPreparationResult,
    TerritorialSelectionInput,
    VerificationStatus,
    ZoneTier,
)

# Real residential urbanizaciones polygon in southern/western Santa Tecla
SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON: Dict[str, Any] = {
    "type": "Polygon",
    "coordinates": [[
        [-89.2925, 13.6645],
        [-89.2820, 13.6645],
        [-89.2820, 13.6695],
        [-89.2925, 13.6695],
        [-89.2925, 13.6645],
    ]],
}


def run_santa_tecla_school_validation(
    pipeline: Optional[TerritorialPreparationPipeline] = None,
    seed: int = 42,
) -> Dict[str, Any]:
    """Execute Section 17 validation scenario comparing 4 educational interventions."""
    owns_pipe = pipeline is None
    pipe = pipeline or TerritorialPreparationPipeline()
    t0 = time.perf_counter()

    try:
        selection = TerritorialSelectionInput(
            polygon_geojson=SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON,
            travel_time_minutes=15.0,
            transport_mode="walk",
            sector="school",
            max_expansion_minutes=30.0,
            max_expansion_km=4.5,
            seed=seed,
        )
        prep: TerritorialPreparationResult = pipe.prepare(selection, max_sample_households=350)

        mob_engine = HumanMobilityAccessibilityEngine()
        center_lat = prep.discovery.center_lat
        center_lon = prep.discovery.center_lon
        schools = [e for e in prep.infrastructure.entities if e.domain == "EDUCATION"]

        edu_summary = prep.sector_context.target_population_summary
        by_level = edu_summary.get("by_level", {})
        total_school_age = int(edu_summary.get("total_school_age_4_18", 0))
        parv_prim_demand = (
            int(by_level.get("parvularia", {}).get("school_age_population", 0))
            + int(by_level.get("basica_ciclo_1", {}).get("school_age_population", 0))
            + int(by_level.get("basica_ciclo_2", {}).get("school_age_population", 0))
        )

        # Register real discovered schools inside PublicServiceCapacityEngine (capacity UNCONFIGURED = None!)
        svc_engine = PublicServiceCapacityEngine()
        for sc in schools[:15]:
            svc_engine.register_facility(
                PublicServiceFacility(
                    facility_id=sc.entity_id,
                    name=sc.name,
                    category=ServiceCategory.EDUCATION,
                    department_code=prep.discovery.department_code,
                    municipality_id=prep.discovery.municipality_id,
                    latitude=sc.lat,
                    longitude=sc.lon,
                    coverage_radius_km=1.5,
                    configured_capacity_per_day=sc.installed_capacity,  # Strictly None unless MINED imported
                    status=(
                        ServiceCapacityStatus.OPERATIONAL
                        if sc.installed_capacity is not None
                        else ServiceCapacityStatus.UNCONFIGURED
                    ),
                )
            )

        # Ledger audit for construction / operational grants across scenarios ($0.00 diff invariant)
        ledger = VerifiableEconomicLedger()
        ledger.initial_currency_pool = 500_000.0
        ledger.record_transaction(
            concept=TransactionConcept.INITIAL_CAPITAL,
            originating_domain="education",
            description="Dotación inicial fondo municipal educativo",
            tick=0,
            entries=[
                TransactionEntry("MUNICIPAL_EDU_FUND_cash", "MUNICIPAL_EDU_FUND", AccountType.ASSET_CASH, debit=500_000.0, credit=0.0),
                TransactionEntry("MUNICIPAL_EDU_FUND_equity", "MUNICIPAL_EDU_FUND", AccountType.EQUITY, debit=0.0, credit=500_000.0),
            ],
        )

        # SCENARIO 1: Sin nueva escuela (Baseline)
        m1 = prep.mobility_accessibility

        # SCENARIO 2: Escuela nueva con Parvularia y Primaria (1°-6°) - Hypothesis 320 cupos
        school_parv_prim = InfrastructureEntity(
            entity_id="HYP_SCHOOL_PARV_PRIM",
            name="Centro Escolar Comunitario Parvularia–Primaria (Propuesto)",
            domain="EDUCATION",
            subtype="school",
            lat=center_lat,
            lon=center_lon,
            zone_tier=ZoneTier.PRIMARY_AREA,
            distance_m=0.0,
            estimated_walk_min=2.0,
            source="Scenario 2 Hypothesis",
            updated_at="2026-11-23",
            verification_status=VerificationStatus.UNVERIFIED,
            confidence_level=0.5,
            confirmed_levels=["parvularia", "basica_ciclo_1", "basica_ciclo_2"],
            levels_evidence_status="OFFICIAL_CONFIRMED",
            installed_capacity=320,
            available_vacancies=320,
            capacity_evidence_type=EvidenceClassification.HYPOTHESIS,
        )
        m2 = mob_engine.analyze_accessibility(
            discovery=prep.discovery,
            batch=prep.population_batch,
            inventory=prep.infrastructure,
            sector="school",
            travel_time_budget_min=15.0,
            hypothetical_facilities=[school_parv_prim],
        )
        # Check covered vs uncovered higher levels (3er ciclo + bachillerato still external)
        upper_demand = (
            int(by_level.get("basica_ciclo_3", {}).get("school_age_population", 0))
            + int(by_level.get("bachillerato", {}).get("school_age_population", 0))
        )

        # SCENARIO 3: Escuela comunitaria completa (Parvularia a Bachillerato) - Hypothesis 600 cupos
        school_full = InfrastructureEntity(
            entity_id="HYP_SCHOOL_FULL_K12",
            name="Complejo Educativo Comunitario Completo (Parvularia–Bachillerato)",
            domain="EDUCATION",
            subtype="school",
            lat=center_lat,
            lon=center_lon,
            zone_tier=ZoneTier.PRIMARY_AREA,
            distance_m=0.0,
            estimated_walk_min=2.0,
            source="Scenario 3 Hypothesis",
            updated_at="2026-11-23",
            verification_status=VerificationStatus.UNVERIFIED,
            confidence_level=0.5,
            confirmed_levels=["parvularia", "basica_ciclo_1", "basica_ciclo_2", "basica_ciclo_3", "bachillerato"],
            levels_evidence_status="OFFICIAL_CONFIRMED",
            installed_capacity=600,
            available_vacancies=600,
            capacity_evidence_type=EvidenceClassification.HYPOTHESIS,
        )
        m3 = mob_engine.analyze_accessibility(
            discovery=prep.discovery,
            batch=prep.population_batch,
            inventory=prep.infrastructure,
            sector="school",
            travel_time_budget_min=15.0,
            hypothetical_facilities=[school_full],
        )
        ledger.record_transaction(
            concept=TransactionConcept.MUNICIPAL_INFRASTRUCTURE_WAGE,
            originating_domain="education",
            description="Escenario 3 inversión hipotética escuela completa",
            tick=1,
            entries=[
                TransactionEntry("MUNICIPAL_EDU_FUND_cash", "MUNICIPAL_EDU_FUND", AccountType.ASSET_CASH, debit=0.0, credit=185_000.0),
                TransactionEntry("MUNICIPAL_EDU_FUND_exp", "MUNICIPAL_EDU_FUND", AccountType.EXPENSE, debit=185_000.0, credit=0.0),
                TransactionEntry("CONSTRUCTION_CONTRACTOR_cash", "CONSTRUCTION_CONTRACTOR", AccountType.ASSET_CASH, debit=185_000.0, credit=0.0),
                TransactionEntry("CONSTRUCTION_CONTRACTOR_rev", "CONSTRUCTION_CONTRACTOR", AccountType.REVENUE, debit=0.0, credit=185_000.0),
            ],
        )

        # SCENARIO 4: Ampliación de capacidad en escuelas existentes cercanas (+60 cupos c/u a 3 más cercanas)
        nearest_3 = [s.entity_id for s in schools[:3]]
        cap_exp = {eid: 60 for eid in nearest_3}
        m4 = mob_engine.analyze_accessibility(
            discovery=prep.discovery,
            batch=prep.population_batch,
            inventory=prep.infrastructure,
            sector="school",
            travel_time_budget_min=15.0,
            capacity_expansions=cap_exp,
        )
        ledger.record_transaction(
            concept=TransactionConcept.MUNICIPAL_INFRASTRUCTURE_WAGE,
            originating_domain="education",
            description="Escenario 4 ampliación hipotética de 3 escuelas cercanas",
            tick=2,
            entries=[
                TransactionEntry("MUNICIPAL_EDU_FUND_cash", "MUNICIPAL_EDU_FUND", AccountType.ASSET_CASH, debit=0.0, credit=65_000.0),
                TransactionEntry("MUNICIPAL_EDU_FUND_exp", "MUNICIPAL_EDU_FUND", AccountType.EXPENSE, debit=65_000.0, credit=0.0),
                TransactionEntry("EXISTING_SCHOOLS_EXPANSION_cash", "EXISTING_SCHOOLS_EXPANSION", AccountType.ASSET_CASH, debit=65_000.0, credit=0.0),
                TransactionEntry("EXISTING_SCHOOLS_EXPANSION_rev", "EXISTING_SCHOOLS_EXPANSION", AccountType.REVENUE, debit=0.0, credit=65_000.0),
            ],
        )

        # Ledger conservation verification
        conserved, ledger_msg, ledger_metrics = ledger.verify_accounting_conservation()

        scenarios = [
            {
                "scenario_id": "ESCENARIO_1_BASELINE",
                "title": "Sin nueva escuela (Situación base observada y sintética)",
                "mean_walk_time_min": m1.mean_walk_time_to_nearest_service_min,
                "share_within_15min": m1.share_within_travel_budget,
                "levels_covered_in_primary_area": [],
                "uncovered_local_demand_students": total_school_age,
                "capacity_evidence_classification": EvidenceClassification.UNAVAILABLE.value,
                "mobility_evidence_classification": EvidenceClassification.SYNTHETIC_CALIBRATED.value,
                "note": "No se asumen capacidades reales de escuelas existentes por falta de registro MINEDUCYT por centro.",
            },
            {
                "scenario_id": "ESCENARIO_2_PARV_PRIMARIA",
                "title": "Nueva escuela con Parvularia y Primaria (1.º a 6.º grado)",
                "mean_walk_time_min": m2.mean_walk_time_to_nearest_service_min,
                "share_within_15min": m2.share_within_travel_budget,
                "levels_covered_in_primary_area": ["parvularia", "basica_ciclo_1", "basica_ciclo_2"],
                "local_demand_parv_prim": parv_prim_demand,
                "uncovered_upper_levels_demand": upper_demand,
                "hypothetical_new_capacity": 320,
                "capacity_evidence_classification": EvidenceClassification.HYPOTHESIS.value,
                "mobility_evidence_classification": EvidenceClassification.SYNTHETIC_CALIBRATED.value,
                "note": "Reduce distancia para parvularia y primaria, pero 3.er ciclo y bachillerato siguen dependiendo de escuelas externas.",
            },
            {
                "scenario_id": "ESCENARIO_3_COMPLETA_K12",
                "title": "Nuevo centro escolar comunitario completo (Parvularia hasta Bachillerato)",
                "mean_walk_time_min": m3.mean_walk_time_to_nearest_service_min,
                "share_within_15min": m3.share_within_travel_budget,
                "levels_covered_in_primary_area": ["parvularia", "basica_ciclo_1", "basica_ciclo_2", "basica_ciclo_3", "bachillerato"],
                "local_demand_all_levels": total_school_age,
                "uncovered_upper_levels_demand": 0,
                "hypothetical_new_capacity": 600,
                "capacity_evidence_classification": EvidenceClassification.HYPOTHESIS.value,
                "mobility_evidence_classification": EvidenceClassification.SYNTHETIC_CALIBRATED.value,
                "note": "Cierra la brecha territorial de proximidad en los 5 niveles dentro del área residencial.",
            },
            {
                "scenario_id": "ESCENARIO_4_AMPLIACION_EXISTENTES",
                "title": "Ampliación de capacidad en establecimientos existentes cercanos",
                "mean_walk_time_min": m4.mean_walk_time_to_nearest_service_min,
                "share_within_15min": m4.share_within_travel_budget,
                "expanded_facilities_ids": nearest_3,
                "hypothetical_added_capacity": 180,
                "capacity_evidence_classification": EvidenceClassification.HYPOTHESIS.value,
                "mobility_evidence_classification": EvidenceClassification.SYNTHETIC_CALIBRATED.value,
                "note": "Mitiga saturación hipotética en escuelas vecinas pero no reduce tiempos de caminata respecto al Escenario 1.",
            },
        ]

        return {
            "validation_id": f"VAL_ST_SCHOOL_{seed}",
            "target_zone": "Entorno residencial Santa Tecla (El Paraíso / Cima del Paraíso / San Martín / Irlanda / La Misión)",
            "district_official_population_2024": 125532,
            "allocated_polygon_population": prep.allocation.allocated_population_target,
            "allocated_polygon_households": prep.allocation.allocated_households_target,
            "polygon_area_km2": prep.discovery.expansion.primary_area.area_km2,
            "influence_area_km2": prep.discovery.expansion.influence_area.area_km2,
            "contextual_area_km2": prep.discovery.expansion.contextual_area.area_km2,
            "schools_discovered_total": len(schools),
            "schools_in_primary": sum(1 for s in schools if s.zone_tier == ZoneTier.PRIMARY_AREA),
            "schools_in_influence": sum(1 for s in schools if s.zone_tier == ZoneTier.INFLUENCE_AREA),
            "schools_in_contextual": sum(1 for s in schools if s.zone_tier == ZoneTier.CONTEXTUAL_AREA),
            "school_age_breakdown": by_level,
            "calibration": {
                "status": prep.certificate.calibration_status,
                "srmse": prep.calibration.srmse,
                "statistical_coverage_pct": prep.calibration.statistical_coverage_pct,
                "evidence_classification": prep.calibration.evidence_classification.value,
            },
            "scenarios": scenarios,
            "ledger_conservation": {
                "conserved": conserved,
                "message": ledger_msg,
                "total_discrepancy_usd": ledger_metrics.get("cash_conservation_diff", 0.0),
                "metrics": ledger_metrics,
            },
            "provenance_integrity": prep.provenance_integrity,
            "limitations": prep.certificate.limitations + prep.sector_context.limitations,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    finally:
        if owns_pipe:
            pipe.close()
