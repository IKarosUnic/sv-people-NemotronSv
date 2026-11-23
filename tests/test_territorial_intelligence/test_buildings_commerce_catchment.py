"""Tests for NationalBuildingIntelligenceEngine, TerritorialLandUseIntelligenceEngine,
CommercialActivityIntelligenceEngine, BusinessDistributionEngine & TerritorialCatchmentAnalysisEngine.
"""

from __future__ import annotations

from saltbor.conversational.territorial_context import NationalTerritorialContextEngine
from saltbor.territorial_intelligence import (
    CatchmentMethod,
    CatchmentScale,
    CommercialActivityIntelligenceEngine,
    CommercialCategory,
    NationalBuildingIntelligenceEngine,
    TerritorialCatchmentAnalysisEngine,
    TerritorialEconomicContextEngine,
    TerritorialLandUseIntelligenceEngine,
)


def test_building_intelligence_and_classification_origins():
    geo = NationalTerritorialContextEngine()
    b_eng = NationalBuildingIntelligenceEngine()
    lu_eng = TerritorialLandUseIntelligenceEngine()
    try:
        ctx = geo.resolve_location("Soyapango")
        assert ctx.resolved
        b_rep = b_eng.analyze_buildings(ctx.lat, ctx.lon, radius_km=1.2)
        assert b_rep.total_buildings_observed > 400
        assert b_rep.total_surface_area_m2 > 0
        assert len(b_rep.counts_by_origin) >= 2
        # Never invent occupancy, height, or levels when absent from OSM shapefile
        assert all(b.occupancy_known is False for b in b_rep.sample_buildings)
        assert all(b.height_m is None and b.levels is None for b in b_rep.sample_buildings)

        lu_rep = lu_eng.analyze_land_use(ctx, radius_km=1.2)
        assert lu_rep.total_road_segments > 50
        assert lu_rep.accessibility_index > 0.2
        assert "flood_exposure" in lu_rep.natural_hazards
    finally:
        b_eng.close()
        lu_eng.close()
        geo.close()


def test_commercial_intelligence_separates_unverified_buildings():
    geo = NationalTerritorialContextEngine()
    b_eng = NationalBuildingIntelligenceEngine()
    econ_eng = TerritorialEconomicContextEngine()
    try:
        ctx = geo.resolve_location("Santa Tecla")
        b_rep = b_eng.analyze_buildings(ctx.lat, ctx.lon, radius_km=1.5)
        comm = econ_eng.build_economic_context(ctx, radius_km=1.5, building_report=b_rep)
        assert comm.concentration_metrics.confirmed_establishments_count > 30
        assert all(e.is_synthetic is False for e in comm.establishments)
        assert all(e.known_employment is None or e.is_formal_status_known for e in comm.establishments)
        assert all(u.status == "unverified_commercial_building" for u in comm.unverified_commercial_buildings)
        assert 0.0 <= comm.concentration_metrics.commercial_diversity_shannon_norm <= 1.0
        assert "no implica automáticamente" in comm.concentration_metrics.profitability_caveat.lower()
    finally:
        econ_eng.close()
        b_eng.close()
        geo.close()


def test_adaptive_catchment_scales_and_methods():
    geo = NationalTerritorialContextEngine()
    cat_eng = TerritorialCatchmentAnalysisEngine()
    try:
        ctx = geo.resolve_location("San Miguel")
        c_pupu = cat_eng.analyze_catchment(ctx, service_type="pupuseria")
        c_hosp = cat_eng.analyze_catchment(ctx, service_type="hospital")
        c_straight = cat_eng.analyze_catchment(
            ctx,
            service_type="pharmacy",
            method=CatchmentMethod.STRAIGHT_LINE_RADIUS,
            scale=CatchmentScale.COMMUNITY,
        )
        assert c_pupu.scale == CatchmentScale.NEIGHBORHOOD
        assert c_hosp.scale == CatchmentScale.REGIONAL
        assert c_hosp.effective_area_km2 > c_pupu.effective_area_km2 * 3.0
        assert c_pupu.network_nodes_analyzed > 20
        assert c_pupu.circuity_factor >= 1.0
        assert c_pupu.isochrone_polygon_geojson is not None
        assert c_straight.primary_method == CatchmentMethod.STRAIGHT_LINE_RADIUS
    finally:
        cat_eng.close()
        geo.close()
