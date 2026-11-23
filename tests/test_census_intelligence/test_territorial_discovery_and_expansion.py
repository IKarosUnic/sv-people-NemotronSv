"""Tests D: Territorial Discovery, 3-Scale Expansion, School Discovery Beyond Primary & Deduplication."""

from __future__ import annotations

from pathlib import Path

from saltbor.census_intelligence import (
    InfrastructureServiceDiscoveryEngine,
    NationalCensusDataIntegrationEngine,
    TerritorialContextDiscoveryEngine,
    TerritorialSelectionInput,
    VerificationStatus,
    ZoneTier,
)
from saltbor.census_intelligence.validation_scenario import SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON


def test_discovery_expands_beyond_primary_polygon_and_deduplicates_schools(tmp_path: Path):
    census_eng = NationalCensusDataIntegrationEngine()
    # Import 1 official MINED school overlapping an OSM school near Santa Tecla to test OFFICIAL_CONFIRMED merge
    mined_csv = tmp_path / "mined_st.csv"
    mined_csv.write_text(
        "codigo_ce,nombre_centro,distrito,lat,lon,niveles,matricula,capacidad\n"
        "MINED100,Colegio Salesiano Santa Inés,Santa Tecla,13.67148,-89.28640,parvularia;basica_ciclo_1;basica_ciclo_2;basica_ciclo_3;bachillerato,1100,1250\n",
        encoding="utf-8",
    )
    census_eng.import_csv(mined_csv, adapter_name="mined_schools", dataset_id="mined_st_official")

    disc_eng = TerritorialContextDiscoveryEngine()
    infra_eng = InfrastructureServiceDiscoveryEngine(geography=disc_eng.geography, census_engine=census_eng)
    try:
        sel = TerritorialSelectionInput(
            polygon_geojson=SANTA_TECLA_RESIDENTIAL_POLYGON_GEOJSON,
            travel_time_minutes=15.0,
            sector="school",
            max_expansion_minutes=30.0,
            max_expansion_km=4.5,
        )
        disc = disc_eng.discover(sel)
        exp = disc.expansion

        assert exp.primary_area.area_km2 < exp.influence_area.area_km2 < exp.contextual_area.area_km2
        assert "5min" in exp.isochrones_by_minutes and "15min" in exp.isochrones_by_minutes and "20min" in exp.isochrones_by_minutes
        assert exp.crossed_administrative_boundaries is True or len(disc.intersecting_units) >= 1

        # Second call hits local SQLite discovery cache deterministically offline
        disc_cached = disc_eng.discover(sel)
        assert disc_cached.cache_hit is True
        assert disc_cached.offline_mode is True

        inv = infra_eng.discover_inventory(disc)
        schools = [e for e in inv.entities if e.domain == "EDUCATION"]
        outside_primary = [s for s in schools if s.zone_tier in (ZoneTier.INFLUENCE_AREA, ZoneTier.CONTEXTUAL_AREA)]
        assert len(outside_primary) >= 10
        assert inv.duplicates_merged >= 1

        # Verify differentiation between OFFICIAL_CONFIRMED, OSM_IDENTIFIED, and UNVERIFIED
        statuses = {s.verification_status for s in schools}
        assert VerificationStatus.OFFICIAL_CONFIRMED in statuses
        assert VerificationStatus.OSM_IDENTIFIED in statuses
    finally:
        disc_eng.close()


def test_expansion_limit_flag_triggers_when_cap_reached():
    disc_eng = TerritorialContextDiscoveryEngine()
    try:
        # Ultra-tight cap (10 min max expansion) should explicitly report limit reached
        disc = disc_eng.discover(
            TerritorialSelectionInput(
                lat=13.667,
                lon=-89.287,
                travel_time_minutes=5.0,
                sector="school",
                max_expansion_minutes=10.0,
                max_expansion_km=1.2,
            )
        )
        assert disc.expansion.expansion_limit_reached is True
        assert disc.expansion.expansion_limit_reason is not None
    finally:
        disc_eng.close()
