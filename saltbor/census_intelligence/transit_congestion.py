"""Multi-Site Congestion Estimation & Transit Stop Optimization Engine (Phase 1.19).

Models synthetic road-segment congestion (V/C ratio + BPR delay) on real
OSMRoadNetwork geometry and evaluates user-placed or system-optimized transit
stops & multi-site corridors. Strictly separates UNAVAILABLE observed traffic
counts from HYPOTHESIS theoretical capacities and SYNTHETIC_CALIBRATED demand.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Literal, Optional, Tuple
from uuid import uuid4

from saltbor.territory.economic_ledger import (
    AccountType,
    TransactionConcept,
    TransactionEntry,
    VerifiableEconomicLedger,
)
from saltbor.world.geographic.osm_router import OSMRoadNetwork, haversine_m

from saltbor.census_intelligence.schemas import (
    CongestionAnalysisResult,
    CorridorLineInput,
    EvidenceClassification,
    ProvenancedIndicator,
    RoadSegmentLoad,
    SiteMarker,
    SiteRole,
    TerritorialPreparationResult,
    TransitSimulationResult,
    TransitStopCandidate,
    validate_provenance_integrity,
)

# Theoretical hourly directional capacities (veh/hr) — explicitly HYPOTHESIS
_THEORETICAL_CAPACITY_VEH_HR: Dict[str, int] = {
    "motorway": 3200,
    "trunk": 2200,
    "primary": 1400,
    "secondary": 950,
    "tertiary": 650,
    "residential": 350,
    "unclassified": 300,
    "service": 200,
}

_FREE_FLOW_KMH: Dict[str, float] = {
    "motorway": 85.0,
    "trunk": 70.0,
    "primary": 50.0,
    "secondary": 42.0,
    "tertiary": 35.0,
    "residential": 25.0,
    "unclassified": 25.0,
    "service": 15.0,
}

_VALID_TRANSIT_ROAD_CLASSES = {"primary", "secondary", "tertiary", "residential"}


class RoadCongestionEstimator:
    """Computes synthetic V/C load and BPR travel-time delay on OSMRoadNetwork edges."""

    @staticmethod
    def estimate_congestion(
        net: OSMRoadNetwork,
        prep: TerritorialPreparationResult,
        sites: Optional[List[SiteMarker]] = None,
        modal_shift_relief: float = 0.0,
        relieved_stop_coords: Optional[List[Tuple[float, float]]] = None,
        max_segments_out: int = 350,
    ) -> CongestionAnalysisResult:
        scope = f"{prep.discovery.primary_district_name} ({prep.discovery.primary_district_id})"
        if len(net) == 0 or net.edge_count == 0:
            return CongestionAnalysisResult(
                observed_traffic_counts_available=False,
                edges_analyzed=0,
                provenanced_indicators=[
                    ProvenancedIndicator(
                        indicator_id="transit_observed_traffic_counts",
                        name="Aforos vehiculares observados en vía",
                        value=None,
                        unit="veh/hora",
                        source="Sensores Viales / VMT",
                        evidence_type=EvidenceClassification.UNAVAILABLE,
                        reference_date="2026-11-24",
                        territorial_coverage=scope,
                        method="Direct sensor lookup (unavailable offline)",
                        confidence_level=0.0,
                        uncertainty="Sin telemetría de tráfico real conectada.",
                    )
                ],
            )

        # Deduplicate undirected edge pairs for clean segment reporting
        seen_pairs: set[Tuple[int, int]] = set()
        unique_edges: List[Tuple[int, Any]] = []
        for u, edges in net.adjacency.items():
            for e in edges:
                rc = (e.road_class or "residential").lower()
                if rc in ("footway", "steps", "path", "cycleway", "pedestrian"):
                    continue
                pair = (min(u, e.target), max(u, e.target))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    unique_edges.append((u, e))

        # Anchor demand hubs: commercial/economy & destination sites + households
        econ_hubs = [
            (e.lat, e.lon)
            for e in prep.infrastructure.entities
            if e.domain in ("ECONOMY", "EDUCATION", "HEALTH")
        ][:35]
        for s in (sites or []):
            if s.role in (SiteRole.DESTINATION, SiteRole.PROPOSED_SERVICE, SiteRole.CONGESTION_HOTSPOT):
                econ_hubs.append((s.lat, s.lon))

        hotspot_coords = [(s.lat, s.lon) for s in (sites or []) if s.role == SiteRole.CONGESTION_HOTSPOT]
        hh_pts = [(hh.home_lat, hh.home_lon, float(hh.expansion_weight)) for hh in prep.population_batch.households[:180]]

        # District-level background corridor pressure calibrated to population & urban status
        pop_factor = min(1.8, max(0.45, prep.allocation.district_official_population / 95_000.0))
        urban_mult = 1.25 if prep.discovery.is_urban else 0.70

        segments: List[RoadSegmentLoad] = []
        bottleneck_count = 0
        vc_sum = 0.0
        max_vc = 0.0
        delay_sum = 0.0
        hotspots_out: List[Dict[str, Any]] = []

        for idx, (u, e) in enumerate(unique_edges):
            rc = (e.road_class or "residential").lower()
            cap = _THEORETICAL_CAPACITY_VEH_HR.get(rc, 300)
            ff_speed = float(e.maxspeed_kmh or _FREE_FLOW_KMH.get(rc, 25.0))
            lat1, lon1 = net._node_coords[u]
            lat2, lon2 = net._node_coords[e.target]
            mid_lat, mid_lon = 0.5 * (lat1 + lat2), 0.5 * (lon1 + lon2)

            # Base arterial through-traffic by road hierarchy
            hierarchy_load = {
                "motorway": 0.62,
                "trunk": 0.72,
                "primary": 0.68,
                "secondary": 0.55,
                "tertiary": 0.42,
                "residential": 0.22,
                "unclassified": 0.20,
                "service": 0.15,
            }.get(rc, 0.22)
            base_vol = cap * hierarchy_load * pop_factor * urban_mult

            # Add local synthetic household + hub attraction pressure within 450m
            local_hh_load = 0.0
            for hlat, hlon, hw in hh_pts:
                if abs(hlat - mid_lat) <= 0.0042 and abs(hlon - mid_lon) <= 0.0042:
                    local_hh_load += hw * 1.4

            hub_pull = 0.0
            for elat, elon in econ_hubs:
                if abs(elat - mid_lat) <= 0.0035 and abs(elon - mid_lon) <= 0.0035:
                    hub_pull += 42.0

            hotspot_boost = 1.0
            for hlat, hlon in hotspot_coords:
                if abs(hlat - mid_lat) <= 0.0030 and abs(hlon - mid_lon) <= 0.0030:
                    hotspot_boost = 1.38
                    break

            vol = (base_vol + local_hh_load + hub_pull) * hotspot_boost

            # Apply transit modal-shift relief near proposed/active stops
            if modal_shift_relief > 0.0 and relieved_stop_coords:
                near_stop = any(
                    abs(slat - mid_lat) <= 0.0055 and abs(slon - mid_lon) <= 0.0055
                    for slat, slon in relieved_stop_coords
                )
                if near_stop and rc in _VALID_TRANSIT_ROAD_CLASSES | {"trunk"}:
                    vol *= max(0.55, 1.0 - modal_shift_relief)

            vc = round(vol / max(1.0, float(cap)), 3)
            # BPR delay: t = t0 * (1 + 0.15 * (V/C)^4)
            delay_f = round(min(4.5, 1.0 + 0.15 * (vc ** 4)), 3)
            cong_speed = round(max(4.0, ff_speed / delay_f), 1)
            is_bn = vc >= 0.85

            if is_bn:
                bottleneck_count += 1
                if len(hotspots_out) < 12:
                    hotspots_out.append({
                        "edge_id": f"E_{u}_{e.target}",
                        "road_name": e.name or f"Vía {rc}",
                        "road_class": rc,
                        "lat": round(mid_lat, 6),
                        "lon": round(mid_lon, 6),
                        "vc_ratio": vc,
                        "congested_speed_kmh": cong_speed,
                    })

            vc_sum += vc
            max_vc = max(max_vc, vc)
            delay_sum += delay_f

            if idx < max_segments_out or is_bn:
                segments.append(
                    RoadSegmentLoad(
                        edge_id=f"E_{u}_{e.target}",
                        road_name=e.name or f"Vía {rc}",
                        road_class=rc,
                        coordinates=[[round(lon1, 6), round(lat1, 6)], [round(lon2, 6), round(lat2, 6)]],
                        length_m=round(e.length_m, 1),
                        theoretical_capacity_veh_hr=cap,
                        estimated_volume_veh_hr=round(vol, 1),
                        vc_ratio=vc,
                        free_flow_speed_kmh=ff_speed,
                        congested_speed_kmh=cong_speed,
                        delay_factor=delay_f,
                        is_bottleneck=is_bn,
                    )
                )

        n_edges = max(1, len(unique_edges))
        mean_vc = round(vc_sum / n_edges, 3)
        mean_delay = round(delay_sum / n_edges, 3)

        inds = [
            ProvenancedIndicator(
                indicator_id="transit_observed_traffic_counts",
                name="Aforos vehiculares observados en vía",
                value=None,
                unit="veh/hora",
                source="Sensores Viales / VMT",
                evidence_type=EvidenceClassification.UNAVAILABLE,
                reference_date="2026-11-24",
                territorial_coverage=scope,
                method="Direct sensor lookup (unavailable offline)",
                confidence_level=0.0,
                uncertainty="Sin telemetría de tráfico real conectada.",
            ),
            ProvenancedIndicator(
                indicator_id="transit_synthetic_mean_vc_ratio",
                name="Razón volumen/capacidad vial modelada (V/C promedio)",
                value=mean_vc,
                unit="ratio",
                source="RoadCongestionEstimator (BPR + OSMRoadNetwork)",
                evidence_type=EvidenceClassification.SYNTHETIC_CALIBRATED,
                reference_date="2026-11-24",
                territorial_coverage=scope,
                method="BPR curve over theoretical OSM road capacities & synthetic OD flows",
                confidence_level=0.62,
                uncertainty="Capacidades teóricas por clase vial (HYPOTHESIS); sin semáforos reales.",
            ),
            ProvenancedIndicator(
                indicator_id="transit_bottleneck_segments_count",
                name="Tramos críticos con saturación modelada (V/C >= 0.85)",
                value=bottleneck_count,
                unit="tramos",
                source="RoadCongestionEstimator",
                evidence_type=EvidenceClassification.HYPOTHESIS,
                reference_date="2026-11-24",
                territorial_coverage=scope,
                method="Threshold V/C >= 0.85 under theoretical capacity table",
                confidence_level=0.58,
                uncertainty="Identificación sujeta a validación con conteos de campo.",
            ),
        ]

        return CongestionAnalysisResult(
            observed_traffic_counts_available=False,
            edges_analyzed=len(unique_edges),
            bottleneck_edges_count=bottleneck_count,
            mean_vc_ratio=mean_vc,
            max_vc_ratio=round(max_vc, 3),
            mean_delay_factor=mean_delay,
            segments=segments[:max_segments_out],
            hotspots=sorted(hotspots_out, key=lambda h: h["vc_ratio"], reverse=True),
            provenanced_indicators=inds,
        )


class TransitOptimizationEngine:
    """Evaluates multi-site corridors, manual stops & automated decongestion stop placement."""

    def __init__(self, min_stop_spacing_m: float = 250.0) -> None:
        self.min_stop_spacing_m = min_stop_spacing_m

    def simulate_and_optimize(
        self,
        prep: TerritorialPreparationResult,
        net: OSMRoadNetwork,
        sites: Optional[List[SiteMarker]] = None,
        corridors: Optional[List[CorridorLineInput]] = None,
        mode: Literal["manual_sites", "auto_optimize_stops", "hybrid"] = "hybrid",
        k_auto_stops: int = 3,
    ) -> TransitSimulationResult:
        t0 = time.perf_counter()
        user_sites = list(sites or [])
        scope = f"{prep.discovery.primary_district_name} ({prep.discovery.primary_district_id})"

        # 1. Existing OSM transit stops
        existing_stops: List[TransitStopCandidate] = []
        for e in prep.infrastructure.entities:
            if e.domain == "INFRASTRUCTURE" and e.subtype in ("bus_stop", "bus_station", "taxi_rank"):
                existing_stops.append(
                    TransitStopCandidate(
                        stop_id=e.entity_id,
                        name=e.name,
                        lat=e.lat,
                        lon=e.lon,
                        origin_kind="EXISTING_OSM",
                        road_class="primary",
                        evidence_type=EvidenceClassification.DIRECT_OBSERVATION,
                    )
                )

        # 2. Baseline congestion (before new stops / corridors)
        baseline_cong = RoadCongestionEstimator.estimate_congestion(
            net=net, prep=prep, sites=user_sites, modal_shift_relief=0.0
        )

        # 3. Collect user-placed stops
        proposed_stops: List[TransitStopCandidate] = []
        all_stop_coords: List[Tuple[float, float]] = [(s.lat, s.lon) for s in existing_stops]

        def _snap_to_valid_transit_node(lat: float, lon: float) -> Tuple[float, float, str]:
            best_nid = None
            best_d = math.inf
            best_rc = "secondary"
            for nid, edges in net.adjacency.items():
                valid_edges = [ed for ed in edges if (ed.road_class or "").lower() in _VALID_TRANSIT_ROAD_CLASSES]
                if not valid_edges:
                    continue
                nlat, nlon = net._node_coords[nid]
                d = haversine_m(lat, lon, nlat, nlon)
                if d < best_d:
                    best_d = d
                    best_nid = nid
                    best_rc = (valid_edges[0].road_class or "secondary").lower()
            if best_nid is not None:
                nlat, nlon = net._node_coords[best_nid]
                return round(nlat, 6), round(nlon, 6), best_rc
            return round(lat, 6), round(lon, 6), "secondary"

        def _spacing_ok(lat: float, lon: float) -> bool:
            return all(haversine_m(lat, lon, sx, sy) >= self.min_stop_spacing_m for sx, sy in all_stop_coords)

        if mode in ("manual_sites", "hybrid"):
            for idx, st in enumerate(user_sites):
                if st.role == SiteRole.PROPOSED_STOP:
                    slat, slon, rc = _snap_to_valid_transit_node(st.lat, st.lon)
                    sp_ok = _spacing_ok(slat, slon)
                    hh_cov, pop_cov = self._count_coverage(slat, slon, prep, radius_m=450.0)
                    cand = TransitStopCandidate(
                        stop_id=st.site_id or f"USER_STOP_{idx + 1}",
                        name=st.label or f"Parada Usuario #{idx + 1}",
                        lat=slat,
                        lon=slon,
                        origin_kind="USER_PLACED",
                        road_class=rc,
                        covered_households=hh_cov,
                        covered_population=pop_cov,
                        spacing_verified=sp_ok,
                        evidence_type=EvidenceClassification.HYPOTHESIS,
                    )
                    proposed_stops.append(cand)
                    all_stop_coords.append((slat, slon))

        # 4. Assisted / automatic k-stop placement on valid road nodes near bottlenecks & households
        if mode in ("auto_optimize_stops", "hybrid") and k_auto_stops > 0 and len(net) > 0:
            candidate_nodes: List[Tuple[float, float, str]] = []
            for nid, edges in net.adjacency.items():
                valid_edges = [ed for ed in edges if (ed.road_class or "").lower() in _VALID_TRANSIT_ROAD_CLASSES]
                if valid_edges:
                    nlat, nlon = net._node_coords[nid]
                    candidate_nodes.append((nlat, nlon, (valid_edges[0].road_class or "secondary").lower()))

            # Sample uniformly up to 160 candidate nodes for fast deterministic evaluation
            step = max(1, len(candidate_nodes) // 160)
            sampled_cands = candidate_nodes[::step]
            bn_pts = [(h["lat"], h["lon"]) for h in baseline_cong.hotspots]

            for k_idx in range(k_auto_stops):
                best_score = -1.0
                best_cand: Optional[Tuple[float, float, str, int, int, int]] = None
                for clat, clon, crc in sampled_cands:
                    if not _spacing_ok(clat, clon):
                        continue
                    hh_cov, pop_cov = self._count_coverage(clat, clon, prep, radius_m=450.0)
                    bn_relief = sum(1 for bx, by in bn_pts if haversine_m(clat, clon, bx, by) <= 550.0)
                    road_bonus = 25 if crc in ("primary", "secondary") else 10
                    score = hh_cov * 3.0 + bn_relief * 35.0 + road_bonus
                    if score > best_score:
                        best_score = score
                        best_cand = (clat, clon, crc, hh_cov, pop_cov, bn_relief)
                if best_cand is None:
                    break
                clat, clon, crc, hh_cov, pop_cov, bn_relief = best_cand
                proposed_stops.append(
                    TransitStopCandidate(
                        stop_id=f"AUTO_STOP_{k_idx + 1}",
                        name=f"Parada Propuesta #{k_idx + 1} ({crc})",
                        lat=round(clat, 6),
                        lon=round(clon, 6),
                        origin_kind="SYSTEM_PROPOSED",
                        road_class=crc,
                        covered_households=hh_cov,
                        covered_population=pop_cov,
                        relieved_bottlenecks_count=bn_relief,
                        spacing_verified=True,
                        evidence_type=EvidenceClassification.HYPOTHESIS,
                    )
                )
                all_stop_coords.append((clat, clon))

        # 5. Before vs After walking accessibility to nearest stop
        tobler = max(0.45, float(prep.discovery.tobler_walking_speed_factor or 0.85))
        walk_m_per_min = 1.25 * tobler * 60.0
        circuity = max(1.0, float(prep.discovery.expansion.influence_area.circuity_factor or 1.25))

        base_stop_pts = [(s.lat, s.lon) for s in existing_stops]
        post_stop_pts = base_stop_pts + [(s.lat, s.lon) for s in proposed_stops]

        base_walk = self._mean_walk_to_pts(prep, base_stop_pts, circuity, walk_m_per_min)
        post_walk = self._mean_walk_to_pts(prep, post_stop_pts, circuity, walk_m_per_min)
        walk_red_pct = (
            round(max(0.0, (base_walk - post_walk) / base_walk * 100.0), 2)
            if base_walk and post_walk and base_walk > 0
            else 0.0
        )

        # Estimate modal shift (households within <= 8 min walk of new stops shifting 18%..32% of trips)
        newly_well_served = 0
        total_hh_w = 0
        for hh in prep.population_batch.households:
            w = int(max(1, round(hh.expansion_weight)))
            total_hh_w += w
            if post_stop_pts:
                min_d = min(haversine_m(hh.home_lat, hh.home_lon, sx, sy) for sx, sy in post_stop_pts)
                if (min_d * circuity) / max(1.0, walk_m_per_min) <= 8.0:
                    newly_well_served += w
        well_served_share = newly_well_served / max(1, total_hh_w)
        modal_shift = round(min(0.32, well_served_share * (0.28 if proposed_stops else 0.12)), 3)

        # 6. Post-intervention road congestion
        post_cong = RoadCongestionEstimator.estimate_congestion(
            net=net,
            prep=prep,
            sites=user_sites,
            modal_shift_relief=modal_shift,
            relieved_stop_coords=[(s.lat, s.lon) for s in proposed_stops] or base_stop_pts,
        )
        bn_red_pct = (
            round(
                max(0.0, (baseline_cong.bottleneck_edges_count - post_cong.bottleneck_edges_count) / baseline_cong.bottleneck_edges_count * 100.0),
                2,
            )
            if baseline_cong.bottleneck_edges_count > 0
            else 0.0
        )
        vc_red_pct = (
            round(max(0.0, (baseline_cong.mean_vc_ratio - post_cong.mean_vc_ratio) / baseline_cong.mean_vc_ratio * 100.0), 2)
            if baseline_cong.mean_vc_ratio > 0
            else 0.0
        )

        # 7. Multi-site corridor routing over OSMRoadNetwork
        route_features: List[Dict[str, Any]] = []
        origins = [s for s in user_sites if s.role == SiteRole.ORIGIN]
        dests = [s for s in user_sites if s.role in (SiteRole.DESTINATION, SiteRole.PROPOSED_SERVICE)]
        if origins and dests and len(net) > 0:
            for o_idx, orig in enumerate(origins[:4]):
                for d_idx, dst in enumerate(dests[:4]):
                    rt = net.route((orig.lat, orig.lon), (dst.lat, dst.lon), mode="drive")
                    if rt.found and len(rt.path) >= 2:
                        route_features.append({
                            "type": "Feature",
                            "geometry": {"type": "LineString", "coordinates": [[round(lon, 6), round(lat, 6)] for lat, lon in rt.path]},
                            "properties": {
                                "route_id": f"RT_{o_idx}_{d_idx}",
                                "distance_m": round(rt.distance_m, 1),
                                "duration_min": round(rt.duration_minutes, 1),
                                "mode": "drive",
                            },
                        })
        for c_idx, cor in enumerate(corridors or []):
            if len(cor.coordinates) >= 2:
                route_features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": cor.coordinates},
                    "properties": {"route_id": cor.corridor_id or f"USER_COR_{c_idx + 1}", "label": cor.label},
                })

        # 8. Accounting Conservation ($0.00 diff) for transit stop investment & fare simulation
        ledger = VerifiableEconomicLedger()
        ledger.initial_currency_pool = 120_000.0
        ledger.record_transaction(
            concept=TransactionConcept.INITIAL_CAPITAL,
            originating_domain="transportation",
            description="Fondo municipal para infraestructura de paradas y movilidad",
            tick=0,
            entries=[
                TransactionEntry("TRANSIT_FUND_cash", "TRANSIT_FUND", AccountType.ASSET_CASH, debit=120_000.0, credit=0.0),
                TransactionEntry("TRANSIT_FUND_eq", "TRANSIT_FUND", AccountType.EQUITY, debit=0.0, credit=120_000.0),
            ],
        )
        if proposed_stops:
            install_cost = len(proposed_stops) * 4_500.0
            ledger.record_transaction(
                concept=TransactionConcept.MUNICIPAL_INFRASTRUCTURE_WAGE,
                originating_domain="transportation",
                description=f"Instalación hipotética de {len(proposed_stops)} parada(s) de transporte",
                tick=1,
                entries=[
                    TransactionEntry("TRANSIT_FUND_cash", "TRANSIT_FUND", AccountType.ASSET_CASH, debit=0.0, credit=install_cost),
                    TransactionEntry("TRANSIT_FUND_exp", "TRANSIT_FUND", AccountType.EXPENSE, debit=install_cost, credit=0.0),
                    TransactionEntry("INFRA_CONTRACTOR_cash", "INFRA_CONTRACTOR", AccountType.ASSET_CASH, debit=install_cost, credit=0.0),
                    TransactionEntry("INFRA_CONTRACTOR_rev", "INFRA_CONTRACTOR", AccountType.REVENUE, debit=0.0, credit=install_cost),
                ],
            )
        conserved, ledger_msg, ledger_metrics = ledger.verify_accounting_conservation()

        # 9. GeoJSON outputs
        cong_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": seg.coordinates},
                    "properties": {
                        "edge_id": seg.edge_id,
                        "road_name": seg.road_name,
                        "road_class": seg.road_class,
                        "vc_ratio": seg.vc_ratio,
                        "congested_speed_kmh": seg.congested_speed_kmh,
                        "is_bottleneck": seg.is_bottleneck,
                    },
                }
                for seg in post_cong.segments
            ],
        }
        stops_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [st.lon, st.lat]},
                    "properties": {
                        "stop_id": st.stop_id,
                        "name": st.name,
                        "origin_kind": st.origin_kind,
                        "road_class": st.road_class,
                        "covered_households": st.covered_households,
                        "covered_population": st.covered_population,
                        "spacing_verified": st.spacing_verified,
                        "evidence_type": st.evidence_type.value,
                    },
                }
                for st in (existing_stops + proposed_stops)
            ],
        }

        indicators = list(post_cong.provenanced_indicators) + [
            ProvenancedIndicator(
                indicator_id="transit_post_walk_to_stop_min",
                name="Tiempo peatonal estimado a parada más cercana (post-intervención)",
                value=post_walk,
                unit="minutos",
                source="TransitOptimizationEngine",
                evidence_type=EvidenceClassification.SYNTHETIC_CALIBRATED if post_walk is not None else EvidenceClassification.UNAVAILABLE,
                reference_date="2026-11-24",
                territorial_coverage=scope,
                method="Nearest valid stop distance × circuity / Tobler speed",
                confidence_level=0.72 if post_walk is not None else 0.0,
                uncertainty="Sujeto a frecuencias reales de rutas de buses no observadas.",
            ),
            ProvenancedIndicator(
                indicator_id="transit_modal_shift_hypothesis",
                name="Cambio modal potencial hacia transporte público",
                value=modal_shift,
                unit="ratio",
                source="TransitOptimizationEngine",
                evidence_type=EvidenceClassification.HYPOTHESIS,
                reference_date="2026-11-24",
                territorial_coverage=scope,
                method="8-min stop catchment share × calibrated modal shift elasticity",
                confidence_level=0.55,
                uncertainty="Hipótesis de comportamiento ante oferta de paradas sin encuesta de preferencia declarada.",
            ),
        ]
        integrity = validate_provenance_integrity(indicators)

        return TransitSimulationResult(
            simulation_id=f"TRANSIT_119_{uuid4().hex[:8]}",
            district_id=prep.discovery.primary_district_id,
            district_name=prep.discovery.primary_district_name,
            mode=mode,
            user_sites_count=len(user_sites),
            existing_osm_stops_count=len(existing_stops),
            proposed_stops=proposed_stops,
            baseline_congestion=baseline_cong,
            post_intervention_congestion=post_cong,
            baseline_mean_walk_to_stop_min=base_walk,
            post_mean_walk_to_stop_min=post_walk,
            walk_time_reduction_pct=walk_red_pct,
            estimated_modal_shift_to_transit_share=modal_shift,
            bottleneck_reduction_pct=bn_red_pct,
            mean_vc_reduction_pct=vc_red_pct,
            corridor_routes_geojson={"type": "FeatureCollection", "features": route_features},
            congestion_geojson=cong_geojson,
            stops_geojson=stops_geojson,
            ledger_conservation={
                "conserved": conserved,
                "message": ledger_msg,
                "total_discrepancy_usd": ledger_metrics.get("cash_conservation_diff", 0.0),
            },
            provenanced_indicators=indicators,
            provenance_integrity=integrity,
            limitations=[
                "Sin aforos vehiculares reales ni frecuencias/horarios de buses en OSM; los niveles V/C y el alivio de congestión son estimaciones sintéticas bajo capacidades teóricas (HYPOTHESIS).",
                f"Las paradas propuestas cumplen espaciamiento mínimo >= {self.min_stop_spacing_m:.0f}m sobre vías aptas (primary/secondary/tertiary/residential).",
            ],
            elapsed_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )

    @staticmethod
    def _count_coverage(lat: float, lon: float, prep: TerritorialPreparationResult, radius_m: float) -> Tuple[int, int]:
        hh_cnt = 0
        pop_cnt = 0
        for hh in prep.population_batch.households:
            if haversine_m(lat, lon, hh.home_lat, hh.home_lon) <= radius_m:
                w = int(max(1, round(hh.expansion_weight)))
                hh_cnt += w
                pop_cnt += len(hh.member_ids) * w
        return hh_cnt, pop_cnt

    @staticmethod
    def _mean_walk_to_pts(
        prep: TerritorialPreparationResult,
        pts: List[Tuple[float, float]],
        circuity: float,
        walk_m_per_min: float,
    ) -> Optional[float]:
        if not pts or not prep.population_batch.households:
            return None
        times: List[float] = []
        for hh in prep.population_batch.households:
            d_m = min(haversine_m(hh.home_lat, hh.home_lon, sx, sy) for sx, sy in pts)
            times.append((d_m * circuity) / max(1.0, walk_m_per_min))
        return round(sum(times) / len(times), 2)
