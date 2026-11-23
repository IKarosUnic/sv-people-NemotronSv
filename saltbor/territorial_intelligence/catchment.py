"""Territorial Catchment & Adaptive Area-of-Influence Analysis Engine (Phase 1.17 Section 5).

Supports all 8 spatial catchment methodologies (straight-line, walking network,
road network, travel-time accessibility, natural geographic barriers,
administrative boundaries, service-specific catchment, and demand-based influence)
and 5 configurable scales, leveraging real OSM road geometry via OSMRoadNetwork.
"""

from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Optional, Tuple

from saltbor.conversational.schemas import TerritorialContext
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.world.geographic.osm_router import OSMRoadNetwork, haversine_m

from saltbor.territorial_intelligence.schemas import (
    CatchmentAreaResult,
    CatchmentMethod,
    CatchmentScale,
)

_SCALE_RADII_KM: Dict[CatchmentScale, float] = {
    CatchmentScale.IMMEDIATE: 0.45,
    CatchmentScale.NEIGHBORHOOD: 0.90,
    CatchmentScale.COMMUNITY: 1.50,
    CatchmentScale.MUNICIPAL_DISTRICT: 3.50,
    CatchmentScale.REGIONAL: 10.00,
}

_SERVICE_PROFILE: Dict[str, Tuple[CatchmentScale, CatchmentMethod, float]] = {
    "pupuseria": (CatchmentScale.NEIGHBORHOOD, CatchmentMethod.WALKING_NETWORK_DISTANCE, 12.0),
    "restaurant": (CatchmentScale.NEIGHBORHOOD, CatchmentMethod.WALKING_NETWORK_DISTANCE, 15.0),
    "shop": (CatchmentScale.IMMEDIATE, CatchmentMethod.WALKING_NETWORK_DISTANCE, 10.0),
    "pharmacy": (CatchmentScale.COMMUNITY, CatchmentMethod.TRAVEL_TIME_ACCESSIBILITY, 15.0),
    "school": (CatchmentScale.COMMUNITY, CatchmentMethod.WALKING_NETWORK_DISTANCE, 20.0),
    "clinic": (CatchmentScale.MUNICIPAL_DISTRICT, CatchmentMethod.ROAD_NETWORK_DISTANCE, 20.0),
    "hospital": (CatchmentScale.REGIONAL, CatchmentMethod.TRAVEL_TIME_ACCESSIBILITY, 35.0),
    "employment_center": (CatchmentScale.MUNICIPAL_DISTRICT, CatchmentMethod.TRAVEL_TIME_ACCESSIBILITY, 30.0),
    "commercial_center": (CatchmentScale.MUNICIPAL_DISTRICT, CatchmentMethod.DEMAND_BASED_INFLUENCE, 25.0),
    "market": (CatchmentScale.COMMUNITY, CatchmentMethod.ROAD_NETWORK_DISTANCE, 20.0),
    "general": (CatchmentScale.COMMUNITY, CatchmentMethod.SERVICE_SPECIFIC_CATCHMENT, 18.0),
}


def _bbox_for_radius(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float, float]:
    d_lat = radius_km / 111.0
    d_lon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)


class TerritorialCatchmentAnalysisEngine:
    """Calculates adaptive, barrier-aware, network-grounded areas of influence."""

    def __init__(self, geography: Optional[IngestedGeography] = None) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        # Cache local OSMRoadNetwork graphs by rounded center + radius to avoid rebuilding per call
        self._network_cache: Dict[Tuple[float, float, float], OSMRoadNetwork] = {}

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def _get_local_network(self, lat: float, lon: float, radius_km: float) -> OSMRoadNetwork:
        key = (round(lat, 3), round(lon, 3), round(min(radius_km, 4.5), 1))
        if key in self._network_cache:
            return self._network_cache[key]

        bbox = _bbox_for_radius(lat, lon, min(radius_km * 1.15, 5.0))
        net = OSMRoadNetwork.from_geography(self.geography, bbox=bbox, max_features=1800)

        if len(self._network_cache) > 32:
            self._network_cache.clear()
        self._network_cache[key] = net
        return net

    def analyze_catchment(
        self,
        context: TerritorialContext,
        service_type: str = "general",
        method: Optional[CatchmentMethod] = None,
        scale: Optional[CatchmentScale] = None,
        travel_time_budget_min: Optional[float] = None,
        neighboring_districts: Optional[List[str]] = None,
    ) -> CatchmentAreaResult:
        """Compute adaptive territorial area of influence with explicit methodology."""
        st_key = (service_type or "general").lower()
        default_scale, default_method, default_minutes = _SERVICE_PROFILE.get(
            st_key, _SERVICE_PROFILE["general"]
        )
        chosen_scale = scale or default_scale
        chosen_method = method or default_method
        budget_min = float(travel_time_budget_min or default_minutes)
        nominal_radius_km = _SCALE_RADII_KM[chosen_scale]

        applied_methods = [chosen_method]
        if chosen_method != CatchmentMethod.NATURAL_GEOGRAPHIC_BARRIERS:
            applied_methods.append(CatchmentMethod.NATURAL_GEOGRAPHIC_BARRIERS)
        if chosen_method != CatchmentMethod.ADMINISTRATIVE_BOUNDARIES:
            applied_methods.append(CatchmentMethod.ADMINISTRATIVE_BOUNDARIES)

        # 1. Inspect real OSM road network & run bounded Dijkstra reachability
        net = self._get_local_network(context.lat, context.lon, nominal_radius_km)
        node_count = len(net)
        edge_count = net.edge_count

        mode = "drive" if chosen_scale in (CatchmentScale.MUNICIPAL_DISTRICT, CatchmentScale.REGIONAL) or chosen_method == CatchmentMethod.ROAD_NETWORK_DISTANCE else "walk"
        tobler = max(0.45, float(context.tobler_walking_speed_factor or 0.85))
        reachable_pts, avg_circuity, walk_15_m, drive_15_m = self._compute_network_reach(
            net=net,
            origin_lat=context.lat,
            origin_lon=context.lon,
            budget_min=budget_min,
            mode=mode,
            tobler_factor=tobler,
            nominal_radius_km=nominal_radius_km,
        )

        # 2. Detect natural geographic barriers (rivers, water bodies, steep terrain)
        barriers: List[str] = []
        barrier_discount = 1.0
        if self.geography.available:
            bbox = _bbox_for_radius(context.lat, context.lon, nominal_radius_km)
            rivers = self.geography.count_in_bbox(bbox, layer="waterways")
            water_bodies = self.geography.count_in_bbox(bbox, layer="water")
            river_total = rivers.get("river", 0) + rivers.get("stream", 0)
            if river_total >= 4:
                barriers.append(f"Cauces hidrológicos en radio ({river_total} tramos río/quebrada)")
                barrier_discount *= 0.90
            if sum(water_bodies.values()) > 0:
                barriers.append(f"Cuerpos de agua superficial ({sum(water_bodies.values())} polígonos)")
                barrier_discount *= 0.92
        if float(context.slope_pct or 0.0) >= 12.0:
            barriers.append(f"Pendiente topográfica pronunciada ({context.slope_pct:.1f}%)")
            barrier_discount *= max(0.75, tobler)

        # 3. Derive effective radius & area from chosen method + network circuity + barriers
        if chosen_method == CatchmentMethod.STRAIGHT_LINE_RADIUS:
            eff_radius_km = nominal_radius_km * barrier_discount
        elif chosen_method == CatchmentMethod.ADMINISTRATIVE_BOUNDARIES:
            eff_radius_km = max(1.0, nominal_radius_km * (1.15 if not context.is_urban else 0.95)) * barrier_discount
        elif chosen_method == CatchmentMethod.DEMAND_BASED_INFLUENCE:
            demand_boost = 1.15 if context.approx_population >= 80000 else 0.95
            eff_radius_km = nominal_radius_km * demand_boost * barrier_discount
        else:
            # Network-adjusted effective reach (real circuity compresses radial coverage)
            circuity_compression = 1.0 / max(1.0, min(1.85, avg_circuity))
            eff_radius_km = nominal_radius_km * max(0.65, circuity_compression * 1.15) * barrier_discount

        eff_radius_km = round(max(0.25, eff_radius_km), 3)
        eff_area_km2 = round(math.pi * (eff_radius_km ** 2) * barrier_discount, 3)

        # Build reachable GeoJSON polygon (convex/radial hull around reachable nodes or honest circle)
        hull_geojson = self._build_catchment_polygon(
            center_lat=context.lat,
            center_lon=context.lon,
            reachable_pts=reachable_pts,
            fallback_radius_km=eff_radius_km,
        )

        admin_units = [f"{context.district_name} ({context.district_id})"]
        if neighboring_districts:
            admin_units.extend(neighboring_districts[:4])

        method_desc = (
            f"Área de influencia ({chosen_scale.value}) para '{st_key}' calculada mediante "
            f"{chosen_method.value} (presupuesto {budget_min:.0f} min en modo {mode}), "
            f"ajustada por factor de rodeo vial ({avg_circuity:.2f}x), pendiente Tobler ({tobler:.2f}x) "
            f"y barreras naturales ({len(barriers)} detectadas)."
        )
        limitations = [
            "Las redes viales OSM no incluyen frecuencias ni rutas de buses en tiempo real.",
        ]
        if node_count == 0:
            limitations.append(
                "Sin grafo vial conectado suficiente en la ventana inmediata; alcance estimado geométricamente con penalización topográfica."
            )

        return CatchmentAreaResult(
            target_lat=context.lat,
            target_lon=context.lon,
            service_type=st_key,
            scale=chosen_scale,
            primary_method=chosen_method,
            applied_methods=applied_methods,
            nominal_radius_km=round(nominal_radius_km, 3),
            effective_radius_km=eff_radius_km,
            effective_area_km2=eff_area_km2,
            network_nodes_analyzed=node_count,
            network_edges_analyzed=edge_count,
            circuity_factor=round(avg_circuity, 3),
            estimated_walk_reach_15min_m=round(walk_15_m, 1),
            estimated_drive_reach_15min_m=round(drive_15_m, 1),
            barriers_detected=barriers,
            barrier_discount_factor=round(barrier_discount, 3),
            administrative_units_touched=admin_units,
            isochrone_polygon_geojson=hull_geojson,
            methodology_explanation=method_desc,
            limitations=limitations,
        )

    @staticmethod
    def _compute_network_reach(
        net: OSMRoadNetwork,
        origin_lat: float,
        origin_lon: float,
        budget_min: float,
        mode: str,
        tobler_factor: float,
        nominal_radius_km: float,
    ) -> Tuple[List[Tuple[float, float]], float, float, float]:
        # Default fallback reaches using Tobler walking speed (~1.25 m/s * tobler) & urban driving (~28 km/h)
        walk_15_fallback = 15.0 * 60.0 * 1.25 * tobler_factor
        drive_15_fallback = 15.0 * (28_000.0 / 60.0)

        if len(net) == 0:
            return [], 1.28, walk_15_fallback, drive_15_fallback

        start_id, _ = net.nearest_node(origin_lat, origin_lon)
        if start_id is None:
            return [], 1.28, walk_15_fallback, drive_15_fallback

        budget_sec = budget_min * 60.0
        best_sec: Dict[int, float] = {start_id: 0.0}
        best_dist: Dict[int, float] = {start_id: 0.0}
        pq: List[Tuple[float, int]] = [(0.0, start_id)]

        while pq:
            t_cur, u = heapq.heappop(pq)
            if t_cur > best_sec.get(u, math.inf) or t_cur > budget_sec:
                continue
            for edge in net.adjacency.get(u, []):
                spd = net._speed_ms(edge, mode)
                if spd <= 0.0:
                    continue
                cost = edge.length_m / spd
                if mode == "walk":
                    cost = cost / max(0.4, tobler_factor)
                t_nxt = t_cur + cost
                if t_nxt <= budget_sec and t_nxt < best_sec.get(edge.target, math.inf):
                    best_sec[edge.target] = t_nxt
                    best_dist[edge.target] = best_dist[u] + edge.length_m
                    heapq.heappush(pq, (t_nxt, edge.target))

        reachable_pts: List[Tuple[float, float]] = []
        circuity_ratios: List[float] = []
        max_walk_15 = 0.0
        for nid, t_val in best_sec.items():
            if nid == start_id:
                continue
            nlat, nlon = net._node_coords[nid]
            reachable_pts.append((nlat, nlon))
            straight = haversine_m(origin_lat, origin_lon, nlat, nlon)
            net_d = best_dist.get(nid, straight)
            if straight > 40.0 and net_d >= straight:
                circuity_ratios.append(min(2.2, net_d / straight))
            if t_val <= 900.0:
                max_walk_15 = max(max_walk_15, straight)

        avg_circuity = sum(circuity_ratios) / len(circuity_ratios) if circuity_ratios else 1.26
        walk_15_m = max(max_walk_15, walk_15_fallback * 0.65) if mode == "walk" else walk_15_fallback
        drive_15_m = min(nominal_radius_km * 1000.0 * 1.4, drive_15_fallback)
        return reachable_pts, avg_circuity, walk_15_m, drive_15_m

    @staticmethod
    def _build_catchment_polygon(
        center_lat: float,
        center_lon: float,
        reachable_pts: List[Tuple[float, float]],
        fallback_radius_km: float,
    ) -> Dict[str, Any]:
        # Build 16-sector radial hull around reachable network nodes, falling back to radius
        sectors = 16
        sector_r_km = [fallback_radius_km * 0.45] * sectors
        if len(reachable_pts) >= 8:
            for plat, plon in reachable_pts:
                d_km = haversine_m(center_lat, center_lon, plat, plon) / 1000.0
                if d_km <= 0.01:
                    continue
                ang = math.atan2(plat - center_lat, plon - center_lon)
                idx = int(((ang + math.pi) / (2.0 * math.pi)) * sectors) % sectors
                if d_km > sector_r_km[idx]:
                    sector_r_km[idx] = min(fallback_radius_km * 1.35, d_km)
        else:
            sector_r_km = [fallback_radius_km] * sectors

        ring: List[List[float]] = []
        cos_lat = max(0.2, math.cos(math.radians(center_lat)))
        for idx in range(sectors):
            ang = -math.pi + (idx + 0.5) * (2.0 * math.pi / sectors)
            r_km = sector_r_km[idx]
            d_lat = (r_km / 111.0) * math.sin(ang)
            d_lon = (r_km / (111.0 * cos_lat)) * math.cos(ang)
            ring.append([round(center_lon + d_lon, 6), round(center_lat + d_lat, 6)])
        ring.append(ring[0])
        return {"type": "Polygon", "coordinates": [ring]}
