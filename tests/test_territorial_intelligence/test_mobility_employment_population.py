"""Tests for HumanMobilityFlowEngine, DynamicPopulationDistributionEngine,
TerritorialLaborMarketEngine, EmploymentOpportunityAnalysisEngine & TerritorialCoverage.
"""

from __future__ import annotations

from saltbor.conversational.territorial_context import NationalTerritorialContextEngine
from saltbor.territorial_intelligence import (
    DayType,
    DynamicPopulationDistributionEngine,
    EmploymentOpportunityAnalysisEngine,
    FlowEvidenceTier,
    HumanMobilityFlowEngine,
    NationalTerritorialCoverageRegistry,
    TerritorialLaborMarketEngine,
    TimePeriod,
)


def test_mobility_roles_heterogeneous_schedules_and_flow_evidence():
    geo = NationalTerritorialContextEngine()
    pop_dist = DynamicPopulationDistributionEngine(seed=42)
    mob = HumanMobilityFlowEngine(population_manager=pop_dist.population_manager)
    try:
        ctx = geo.resolve_location("Santa Ana")
        act = pop_dist.activate_for_territory(ctx, max_active_agents=36, seed=42)
        assert act["hydrated_active_agents"] == 36
        assert act["population_reset_occurred"] is False

        humans = pop_dist.population_manager.get_active_humans_for_district(ctx.district_id)
        morn = mob.analyze_mobility(ctx, humans=humans, time_period=TimePeriod.MORNING, day_type=DayType.WEEKDAY)
        night = mob.analyze_mobility(ctx, humans=humans, time_period=TimePeriod.NIGHT, day_type=DayType.WEEKEND)

        assert morn.double_counting_prevented is True
        assert sum(morn.role_breakdown.values()) == len(humans)
        assert morn.schedule_heterogeneity_entropy > 0.25
        assert morn.estimated_pedestrian_activity_index > night.estimated_pedestrian_activity_index
        assert morn.measured_flows_available is False
        assert morn.evidence_tiers["street_sensor_pedestrian_counts"] == FlowEvidenceTier.MEASURED_FLOW
        assert len(morn.mobility_corridors) >= 1
    finally:
        mob.close()
        pop_dist.close()
        geo.close()


def test_employment_analysis_and_all_6_interventions_conserved():
    geo = NationalTerritorialContextEngine()
    pop_dist = DynamicPopulationDistributionEngine(seed=77)
    labor = TerritorialLaborMarketEngine()
    emp_opp = EmploymentOpportunityAnalysisEngine(labor)
    try:
        ctx = geo.resolve_location("Soyapango")
        pop_dist.activate_for_territory(ctx, max_active_agents=30, seed=77)
        humans = pop_dist.population_manager.get_active_humans_for_district(ctx.district_id)

        rep = labor.analyze_labor_market(ctx, humans=humans)
        assert rep.verified_vacancies_available is False
        assert rep.verified_job_vacancies == []
        assert rep.potential_labor_supply_approx > 10000

        for kind in (
            "COMMERCIAL_CENTER",
            "NEW_BUSINESSES",
            "FACTORY_HIRING",
            "ROAD_ACCESSIBILITY",
            "TRAINING_CENTER",
            "EMPLOYER_CLOSURE",
        ):
            res = emp_opp.simulate_employment_intervention(kind, ctx, humans, horizon_days=15)
            assert res.conservation_passed is True
            assert res.ledger_conservation_diff_usd == 0.0
            if kind != "EMPLOYER_CLOSURE":
                assert res.local_resident_hire_share < 1.0  # Never assumes 100% automatic local hiring
                assert res.inbound_commuters_hired > 0
            else:
                assert res.direct_jobs_created_or_lost < 0
    finally:
        pop_dist.close()
        geo.close()


def test_national_coverage_registry_all_14_departments_and_262_districts():
    reg = NationalTerritorialCoverageRegistry()
    try:
        summary = reg.get_national_summary()
        assert summary.total_departments == 14
        assert summary.total_districts == 262
        assert sum(summary.tier_counts.values()) == 262
        geojson = reg.export_coverage_geojson()
        assert len(geojson["features"]) == 262
    finally:
        reg.close()
