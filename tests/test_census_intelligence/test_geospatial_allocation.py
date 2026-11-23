"""Tests C: Geospatial Allocation (Polygons, Points, Census Intersection & Building Exclusions)."""

from __future__ import annotations

from shapely.geometry import Point, shape

from saltbor.census_intelligence import (
    GeospatialPopulationAllocationEngine,
    TerritorialContextDiscoveryEngine,
    TerritorialSelectionInput,
)
from saltbor.census_intelligence.validation_scenario import SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON


def test_polygon_allocation_excludes_non_residential_and_avoids_whole_city_population():
    disc_eng = TerritorialContextDiscoveryEngine()
    alloc_eng = GeospatialPopulationAllocationEngine(geography=disc_eng.geography)
    try:
        disc = disc_eng.discover(
            TerritorialSelectionInput(
                polygon_geojson=SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON,
                travel_time_minutes=15.0,
                sector="school",
            )
        )
        assert disc.selection_mode == "polygon"
        assert disc.primary_district_id == "dist_santa_tecla"

        alloc = alloc_eng.allocate_population(disc)
        # Crucial Phase 1.18 rule: Santa Tecla residential polygon MUST NOT receive all 125,532 residents!
        assert alloc.district_official_population == 125532
        assert 50 <= alloc.allocated_population_target <= 15000
        assert alloc.buildings_residential_confirmed > 100
        assert alloc.buildings_unknown_probabilistic > 0
        assert alloc.buildings_excluded_non_residential >= 2  # educational buildings excluded!
        assert "educational" in alloc.excluded_counts_by_class

        # Verify every allocated residential anchor is strictly inside the user polygon
        poly = shape(SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON)
        for anchor in alloc.building_anchors:
            assert poly.contains(Point(anchor.lon, anchor.lat))
            if anchor.source_building_class in ("commercial", "industrial", "educational", "health", "religious"):
                assert anchor.allocated_residential is False
                assert anchor.estimated_occupied_households == 0
    finally:
        disc_eng.close()


def test_point_selection_allocates_bounded_neighborhood():
    disc_eng = TerritorialContextDiscoveryEngine()
    alloc_eng = GeospatialPopulationAllocationEngine(geography=disc_eng.geography)
    try:
        disc = disc_eng.discover(TerritorialSelectionInput(lat=13.6989, lon=-89.1914, travel_time_minutes=10.0))
        alloc = alloc_eng.allocate_population(disc)
        assert alloc.allocated_households_target >= 1
        assert alloc.allocated_population_target < alloc.district_official_population
    finally:
        disc_eng.close()
