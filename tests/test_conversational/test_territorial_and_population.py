"""Tests for national geographic resolution, ambiguity handling, population activation, and LOD."""

from __future__ import annotations

from saltbor.conversational import (
    ActivationLOD,
    NationalPopulationActivationManager,
    NationalTerritorialContextEngine,
    PopulationCategory,
    TerritorialPopulationContextEngine,
)
from saltbor.datasets.salvadoran.territory_data import SALVADORAN_DEPARTMENTS_P8


def test_national_resolution_all_14_departments_and_canton():
    geo = NationalTerritorialContextEngine()
    try:
        depts = (
            list(SALVADORAN_DEPARTMENTS_P8.values())
            if isinstance(SALVADORAN_DEPARTMENTS_P8, dict)
            else list(SALVADORAN_DEPARTMENTS_P8)
        )
        assert len(depts) == 14
        for d in depts:
            ctx = geo.resolve_location(d.name)
            assert ctx.resolved is True, f"Failed to resolve department {d.name}"
            assert ctx.department_code == d.code
            assert "administrative_hierarchy" in ctx.provenance_by_domain
            assert "osm_geospatial" in ctx.provenance_by_domain
            assert ctx.provenance_by_domain["osm_geospatial"].license == "ODbL-1.0"

        # Specific canton resolution
        canton_ctx = geo.resolve_location("Cantón San José Las Flores")
        assert canton_ctx.resolved is True
        assert canton_ctx.canton_name is not None
        assert "flores" in canton_ctx.canton_name.lower()
        assert canton_ctx.buildings_is_partial is True  # Honest partial OSM disclosure outside SS Centro
    finally:
        geo.close()


def test_ambiguous_geographic_references_and_map_coordinates():
    geo = NationalTerritorialContextEngine()
    try:
        # "El Rosario" exists in Cuscatlán, La Paz, and Morazán
        ambig = geo.resolve_location("El Rosario")
        assert ambig.resolved is False
        assert ambig.is_ambiguous is True
        assert len(ambig.candidates) >= 2

        # Clarified with department
        clarified = geo.resolve_location("El Rosario, La Paz")
        assert clarified.resolved is True
        assert clarified.is_ambiguous is False
        assert clarified.department_name == "La Paz"

        # Optional map coordinate (San Salvador Centro)
        coord_ctx = geo.resolve_location(lat=13.6978, lon=-89.1915)
        assert coord_ctx.resolved is True
        assert coord_ctx.coordinate_source == "user_map_coordinate"
        assert coord_ctx.road_network_summary["total_segments_in_radius"] > 0
        assert coord_ctx.buildings_count > 0  # SS Centro has OSM buildings
        assert coord_ctx.buildings_is_partial is False

        # Out of country coordinates rejected honestly
        outside = geo.resolve_location(lat=40.7128, lon=-74.0060)
        assert outside.resolved is False
    finally:
        geo.close()


def test_population_activation_deactivation_and_identity_persistence():
    geo = NationalTerritorialContextEngine()
    mgr = NationalPopulationActivationManager(seed=42)
    pop_ctx_eng = TerritorialPopulationContextEngine()
    try:
        ctx_st = geo.resolve_location("Santa Tecla")
        act = mgr.activate_region(ctx_st, target_lod=ActivationLOD.LOD_3_INDIVIDUAL_FULL, max_active_agents=30)
        assert act["hydrated_active_agents"] == 30
        assert mgr.active_registry.count == 30

        pop_ctx = pop_ctx_eng.build_population_context(ctx_st, act)
        assert pop_ctx["permanent_residents_approx"] == ctx_st.approx_population
        assert len(pop_ctx["uncertainties"]) >= 1

        humans = mgr.get_active_humans_for_district(ctx_st.district_id)
        target_uid = humans[0].uid
        humans[0].physical_state.money = 123.45

        # Deactivate to LOD 0 -> RAM freed, persistent identity & money preserved
        deact = mgr.deactivate_region(ctx_st.district_id, target_lod=ActivationLOD.LOD_0_TERRITORIAL_AGGREGATE)
        assert deact["dehydrated_agents"] == 30
        assert mgr.active_registry.count == 0
        assert mgr.total_unique_persistent_individuals() == 30

        # Re-activate to LOD 2 -> same UID & modified wealth preserved
        mgr.activate_region(ctx_st, target_lod=ActivationLOD.LOD_2_INDIVIDUAL_SUMMARY, max_active_agents=30)
        restored = mgr.active_registry.get(target_uid)
        assert abs(restored.physical_state.money - 123.45) < 1e-6
    finally:
        geo.close()


def test_commuter_flows_without_double_counting():
    geo = NationalTerritorialContextEngine()
    mgr = NationalPopulationActivationManager(seed=77)
    try:
        st = geo.resolve_location("Santa Tecla")
        ss = geo.resolve_location("San Salvador")
        mgr.ensure_district_cohort(st, cohort_size=25)
        mgr.ensure_district_cohort(ss, cohort_size=25)
        total_before = mgr.total_unique_persistent_individuals()
        assert total_before == 50

        flow = mgr.register_inter_district_flow(st, ss, PopulationCategory.DAILY_COMMUTER, count=8)
        assert flow["moved_unique_uids"] == 8
        assert mgr.total_unique_persistent_individuals() == total_before

        acc_st = mgr.get_district_population_accounting(st.district_id)
        acc_ss = mgr.get_district_population_accounting(ss.district_id)
        assert acc_st["outbound_commuters"] == 8
        assert acc_ss["inbound_commuters"] == 8
        assert acc_st["unique_individuals_present"] == 17
        assert acc_ss["unique_individuals_present"] == 33
        assert acc_st["double_counting_detected"] is False
        assert acc_ss["double_counting_detected"] is False
    finally:
        geo.close()
