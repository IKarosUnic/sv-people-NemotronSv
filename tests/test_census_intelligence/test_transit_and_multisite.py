"""Tests for Phase 1.19 Multi-Site Selection, Road Congestion & Transit Stop Optimization."""

from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from saltbor.census_intelligence import (
    EvidenceClassification,
    SiteMarker,
    SiteRole,
    TerritorialPreparationPipeline,
    TerritorialSelectionInput,
    TransitOptimizationEngine,
)
from saltbor.conversational import SALTBORConversationalOrchestrator
from saltbor.visualization.routers.conversational_studio_router import set_studio_orchestrator
from saltbor.visualization.server import create_app
from saltbor.world.geographic.osm_router import haversine_m


def test_multisite_corridor_and_manual_plus_auto_stop_optimization():
    pipe = TerritorialPreparationPipeline()
    try:
        # 4 user-marked sites across Santa Tecla (origin, destination, 1 proposed stop, 1 congestion hotspot)
        sites = [
            SiteMarker(site_id="S1", lat=13.6662, lon=-89.2905, role=SiteRole.ORIGIN, label="El Paraíso"),
            SiteMarker(site_id="S2", lat=13.6732, lon=-89.2815, role=SiteRole.DESTINATION, label="Centro Santa Tecla"),
            SiteMarker(site_id="S3", lat=13.6695, lon=-89.2860, role=SiteRole.PROPOSED_STOP, label="Parada Usuario"),
            SiteMarker(site_id="S4", lat=13.6718, lon=-89.2840, role=SiteRole.CONGESTION_HOTSPOT, label="Cruce Saturado"),
        ]
        sel = TerritorialSelectionInput(sites=sites, travel_time_minutes=15.0, sector="road", seed=42)
        prep = pipe.prepare(sel, max_sample_households=160)
        assert prep.discovery.selection_mode == "polygon"
        assert prep.discovery.expansion.primary_area.area_km2 >= 0.4

        net = pipe.discovery_engine.expansion_engine._get_network(
            prep.discovery.center_lat, prep.discovery.center_lon, 2.5
        )
        opt = TransitOptimizationEngine(min_stop_spacing_m=250.0)
        res = opt.simulate_and_optimize(
            prep=prep,
            net=net,
            sites=sites,
            mode="hybrid",
            k_auto_stops=3,
        )

        assert res.user_sites_count == 4
        assert len(res.proposed_stops) >= 3
        assert res.baseline_congestion.observed_traffic_counts_available is False
        assert res.baseline_congestion.edges_analyzed > 20
        assert res.ledger_conservation["conserved"] is True
        assert res.ledger_conservation["total_discrepancy_usd"] == 0.0
        assert res.provenance_integrity["valid"] is True

        # Every proposed stop must sit on a valid transit road class (never motorway/steps/footway)
        for st in res.proposed_stops:
            assert st.road_class in ("primary", "secondary", "tertiary", "residential")

        # Verify system-proposed stops respect >= 250m spacing among themselves
        sys_stops = [s for s in res.proposed_stops if s.origin_kind == "SYSTEM_PROPOSED"]
        for i in range(len(sys_stops)):
            for j in range(i + 1, len(sys_stops)):
                assert haversine_m(sys_stops[i].lat, sys_stops[i].lon, sys_stops[j].lat, sys_stops[j].lon) >= 249.0

        # Post-intervention walk time should not worsen vs baseline
        if res.baseline_mean_walk_to_stop_min and res.post_mean_walk_to_stop_min:
            assert res.post_mean_walk_to_stop_min <= res.baseline_mean_walk_to_stop_min

        # Observed traffic counts must remain UNAVAILABLE
        obs_ind = next(i for i in res.provenanced_indicators if i.indicator_id == "transit_observed_traffic_counts")
        assert obs_ind.evidence_type == EvidenceClassification.UNAVAILABLE
        assert obs_ind.value is None

        # Route between origin & destination should produce GeoJSON LineString
        assert len(res.corridor_routes_geojson["features"]) >= 1
    finally:
        pipe.close()


@pytest.fixture(scope="module")
def phase119_client(tmp_path_factory) -> Iterator[TestClient]:
    tmp_dir = tmp_path_factory.mktemp("phase119_api")
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_dir / "studio_119.db", seed=42)
    set_studio_orchestrator(orch)
    app = create_app(controller=None, seed=42, db_path=str(tmp_dir / "sim_119.db"))
    with TestClient(app) as client:
        yield client
    set_studio_orchestrator(None)
    orch.close()
    app.state.controller.stop_worker()


def test_transit_api_endpoints_and_multisite_frontend_assets(phase119_client: TestClient):
    r_sim = phase119_client.post(
        "/api/territorial/transit/simulate",
        json={
            "sites": [
                {"lat": 13.6662, "lon": -89.2905, "role": "origin", "label": "Origen A"},
                {"lat": 13.6732, "lon": -89.2815, "role": "destination", "label": "Destino B"},
                {"lat": 13.6695, "lon": -89.2860, "role": "proposed_stop", "label": "Parada C"},
            ],
            "mode": "hybrid",
            "k_auto_stops": 2,
            "seed": 42,
        },
    )
    assert r_sim.status_code == 200
    d_sim = r_sim.json()
    assert d_sim["ledger_conservation"]["total_discrepancy_usd"] == 0.0
    assert len(d_sim["congestion_geojson"]["features"]) >= 10
    assert len(d_sim["stops_geojson"]["features"]) >= 2

    r_opt = phase119_client.post(
        "/api/territorial/transit/optimize-stops",
        json={"location_query": "Soyapango", "k_auto_stops": 3, "seed": 42},
    )
    assert r_opt.status_code == 200
    assert len(r_opt.json()["proposed_stops"]) == 3

    html = phase119_client.get("/").text
    assert 'id="studio-btn-add-site"' in html
    assert 'id="studio-btn-sim-transit"' in html

    js = phase119_client.get("/modules/territorial_studio.js").text
    assert "new maplibregl.Map(" not in js
    assert "/api/territorial/transit/simulate" in js
