"""Territorial Context Discovery & Dynamic 3-Scale Expansion Engines (Phase 1.18 Sections 4 & 5).

Reuses NationalTerritorialContextEngine, IngestedGeography (SQLite R-Tree), and
OSMRoadNetwork while providing:
- Point, GeoJSON Polygon/MultiPolygon, and administrative query ingestion
- Local SQLite territorial cache with incremental sync metadata & offline-first fallback
- Optional rate-limited Overpass & Nominatim adapters (allow_online_osm=False default, ODbL compliant)
- Dynamic 3-scale expansion: Primary Area, Influence Area (5/10/15/20/custom min), and
  sector-driven Contextual Area crossing administrative boundaries with configurable limits
- Barrier & crossing awareness (rivers/quebradas, water bodies, Tobler slopes, bridges)
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import MultiPoint, Point, Polygon, MultiPolygon, mapping, shape
from shapely.ops import unary_union

from saltbor.conversational.territorial_context import NationalTerritorialContextEngine
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.datasets.salvadoran.territory_data import SALVADORAN_DISTRICTS_P8, SalvadoranDistrictData
from saltbor.world.geographic.osm_router import OSMRoadNetwork, haversine_m
from saltbor.world.geographic.spatial_index import wgs84_to_local_metric_xy

from saltbor.census_intelligence.schemas import (
    DiscoveredTerritorialContext,
    TerritorialExpansionResult,
    TerritorialScaleArea,
    TerritorialSelectionInput,
    ZoneTier,
)

OSM_ODBL_ATTRIBUTION = "© OpenStreetMap contributors, available under ODbL 1.0 (https://www.openstreetmap.org/copyright)"


def _bbox_for_radius(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float, float]:
    d_lat = radius_km / 111.0
    d_lon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)


def _planar_area_km2(geom: Any) -> float:
    """Compute planar polygon area in km2 using local SIRGAS-centered metric XY projection."""
    if geom is None or geom.is_empty:
        return 0.0

    def _ring_area_m2(coords: Any) -> float:
        pts = [wgs84_to_local_metric_xy(float(c[1]), float(c[0])) for c in coords]
        if len(pts) < 3:
            return 0.0
        acc = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            acc += x0 * y1 - x1 * y0
        return abs(acc) * 0.5

    total_m2 = 0.0
    if isinstance(geom, Polygon):
        outer = _ring_area_m2(list(geom.exterior.coords))
        holes = sum(_ring_area_m2(list(r.coords)) for r in geom.interiors)
        total_m2 = max(0.0, outer - holes)
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            outer = _ring_area_m2(list(poly.exterior.coords))
            holes = sum(_ring_area_m2(list(r.coords)) for r in poly.interiors)
            total_m2 += max(0.0, outer - holes)
    return round(total_m2 / 1_000_000.0, 4)


def _circle_polygon_wgs84(lat: float, lon: float, radius_km: float, steps: int = 24) -> Polygon:
    cos_lat = max(0.2, math.cos(math.radians(lat)))
    coords: List[Tuple[float, float]] = []
    for idx in range(steps):
        ang = (2.0 * math.pi * idx) / steps
        d_lat = (radius_km / 111.0) * math.sin(ang)
        d_lon = (radius_km / (111.0 * cos_lat)) * math.cos(ang)
        coords.append((round(lon + d_lon, 6), round(lat + d_lat, 6)))
    coords.append(coords[0])
    return Polygon(coords)


def _expand_polygon_buffer_km(poly: Any, extra_km: float) -> Any:
    if extra_km <= 0:
        return poly
    center = poly.centroid
    cos_lat = max(0.2, math.cos(math.radians(center.y)))
    deg_approx = extra_km / (111.0 * math.sqrt(cos_lat))
    return poly.buffer(deg_approx, resolution=12)


# ---------------------------------------------------------------------------
# Offline-First Cached Overpass / Nominatim Adapters (Opt-in Online Only)
# ---------------------------------------------------------------------------

class LocalTerritorialCache:
    """SQLite local cache storing Overpass/Nominatim/discovery snapshots for offline resilience."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS territorial_discovery_cache (
                cache_key   TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at  REAL NOT NULL,
                ttl_sec     REAL NOT NULL DEFAULT 86400.0
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json, updated_at, ttl_sec FROM territorial_discovery_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if not row:
                return None
            if (time.time() - float(row["updated_at"])) > float(row["ttl_sec"]):
                return None
            try:
                return json.loads(row["payload_json"])
            except Exception:
                return None

    def put(self, key: str, source_name: str, payload: Dict[str, Any], ttl_sec: float = 86400.0) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO territorial_discovery_cache (cache_key, source_name, payload_json, updated_at, ttl_sec)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    source_name=excluded.source_name,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at,
                    ttl_sec=excluded.ttl_sec
                """,
                (key, source_name, json.dumps(payload, default=str), time.time(), float(ttl_sec)),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class RateLimitedOSMAdapter:
    """Opt-in Overpass & Nominatim adapter respecting OSM usage policy and offline fallback."""

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "SALTBOR-TerritorialIntelligence/1.18 (Apache-2.0; local research)"

    def __init__(self, cache: LocalTerritorialCache, allow_online: bool = False) -> None:
        self.cache = cache
        self.allow_online = allow_online
        self._last_request_ts = 0.0
        self._lock = threading.Lock()

    def geocode_nominatim(self, query: str) -> Optional[Dict[str, Any]]:
        key = f"nominatim:{hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        if not self.allow_online:
            return None
        with self._lock:
            wait = 1.15 - (time.time() - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            try:
                params = urllib.parse.urlencode({"q": f"{query}, El Salvador", "format": "json", "limit": 3})
                req = urllib.request.Request(
                    f"{self.NOMINATIM_URL}?{params}",
                    headers={"User-Agent": self.USER_AGENT},
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    self._last_request_ts = time.time()
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and data:
                        out = {
                            "lat": float(data[0]["lat"]),
                            "lon": float(data[0]["lon"]),
                            "display_name": data[0].get("display_name", query),
                            "attribution": OSM_ODBL_ATTRIBUTION,
                        }
                        self.cache.put(key, "nominatim", out)
                        return out
            except Exception:
                return None
        return None


# ---------------------------------------------------------------------------
# Dynamic Territorial Expansion Engine (Section 5)
# ---------------------------------------------------------------------------

class DynamicTerritorialExpansionEngine:
    """Computes Primary, Network Influence, and Dynamic Sector Contextual Areas."""

    _SECTOR_FACILITY_CLASSES: Dict[str, Tuple[str, ...]] = {
        "school": ("education",),
        "education": ("education",),
        "health": ("health",),
        "clinic": ("health",),
        "hospital": ("health",),
        "market": ("market", "retail_commercial", "food_service", "finance"),
        "commerce": ("market", "retail_commercial", "food_service", "finance"),
        "road": ("bus_stop", "bus_station", "market", "education", "health"),
        "transport": ("bus_stop", "bus_station"),
        "general": ("education", "health", "market", "retail_commercial"),
    }

    def __init__(self, geography: Optional[IngestedGeography] = None) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self._net_cache: Dict[Tuple[float, float, float], OSMRoadNetwork] = {}
        self._districts: Dict[str, SalvadoranDistrictData] = (
            SALVADORAN_DISTRICTS_P8
            if isinstance(SALVADORAN_DISTRICTS_P8, dict)
            else {d.district_id: d for d in SALVADORAN_DISTRICTS_P8}
        )

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def _get_network(self, lat: float, lon: float, radius_km: float) -> OSMRoadNetwork:
        capped_r = min(max(1.2, radius_km), 6.0)
        key = (round(lat, 3), round(lon, 3), round(capped_r, 1))
        if key in self._net_cache:
            return self._net_cache[key]
        bbox = _bbox_for_radius(lat, lon, capped_r)
        net = OSMRoadNetwork.from_geography(self.geography, bbox=bbox, max_features=2600)
        if len(self._net_cache) > 24:
            self._net_cache.clear()
        self._net_cache[key] = net
        return net

    def _detect_barriers_and_crossings(
        self,
        bbox: Tuple[float, float, float, float],
        slope_pct: float,
    ) -> Tuple[List[str], int, int]:
        barriers: List[str] = []
        bridges_crossings = 0
        restrictions = 0

        if self.geography.available:
            waterways = self.geography.features_in_bbox(bbox, layer="waterways", limit=250, include_geometry=False)
            water_polys = self.geography.count_in_bbox(bbox, layer="water")
            roads = self.geography.features_in_bbox(bbox, layer="roads", limit=400, include_geometry=False)

            rivers = sum(1 for w in waterways if w.get("feature_class") in ("river", "stream"))
            if rivers > 0:
                barriers.append(f"Barreras hidrológicas: {rivers} tramos de ríos/quebradas en la zona")
            if sum(water_polys.values()) > 0:
                barriers.append(f"Cuerpos de agua superficial ({sum(water_polys.values())} polígonos)")

            # Estimate crossings by proximity between roads and waterway centroids
            ww_pts = [(float(w["centroid"]["lat"]), float(w["centroid"]["lon"])) for w in waterways[:60]]
            for rd in roads:
                rc = rd["centroid"]
                rlat, rlon = float(rc["lat"]), float(rc["lon"])
                if any(abs(rlat - wlat) <= 0.0008 and abs(rlon - wlon) <= 0.0008 for wlat, wlon in ww_pts):
                    bridges_crossings += 1
                sc = (rd.get("source_class") or "").lower()
                if sc in ("motorway", "trunk", "steps", "private"):
                    restrictions += 1
                    if sc == "steps":
                        barriers.append("Accesos con gradas o pasos peatonales restringidos")

        if slope_pct >= 12.0:
            barriers.append(f"Pendiente topográfica pronunciada ({slope_pct:.1f}%)")
        if restrictions > 0:
            barriers.append(f"Restricciones viales/acceso detectadas ({restrictions} segmentos especiales)")

        return list(dict.fromkeys(barriers)), bridges_crossings, restrictions

    def _network_isochrone(
        self,
        net: OSMRoadNetwork,
        origin_lat: float,
        origin_lon: float,
        time_budgets_min: List[float],
        mode: str,
        tobler_factor: float,
        base_poly: Any,
    ) -> Tuple[Dict[float, Any], float, int, int, float]:
        """Compute multi-threshold Dijkstra travel-time hulls (5, 10, 15, 20, custom min)."""
        max_min = max(time_budgets_min)
        max_sec = max_min * 60.0
        eff_mode = "drive" if mode == "drive" else "walk"
        speed_fallback_ms = (28_000.0 / 3600.0) if eff_mode == "drive" else (1.25 * max(0.45, tobler_factor))

        if len(net) == 0:
            polys = {}
            for m in time_budgets_min:
                r_km = max(0.25, (m * 60.0 * speed_fallback_ms) / 1000.0)
                polys[m] = unary_union([base_poly, _expand_polygon_buffer_km(base_poly, r_km * 0.65)])
            return polys, 1.28, 0, 0, (max_min * 60.0 * speed_fallback_ms) / 1000.0

        start_id, _ = net.nearest_node(origin_lat, origin_lon)
        if start_id is None:
            polys = {m: _expand_polygon_buffer_km(base_poly, (m * 60.0 * speed_fallback_ms) / 1000.0) for m in time_budgets_min}
            return polys, 1.28, len(net), net.edge_count, (max_min * 60.0 * speed_fallback_ms) / 1000.0

        best_sec: Dict[int, float] = {start_id: 0.0}
        best_dist: Dict[int, float] = {start_id: 0.0}
        pq: List[Tuple[float, int]] = [(0.0, start_id)]

        while pq:
            t_cur, u = heapq.heappop(pq)
            if t_cur > best_sec.get(u, math.inf) or t_cur > max_sec:
                continue
            for edge in net.adjacency.get(u, []):
                spd = net._speed_ms(edge, eff_mode)
                if spd <= 0.0:
                    continue
                cost = edge.length_m / spd
                if eff_mode == "walk":
                    cost = cost / max(0.45, tobler_factor)
                t_nxt = t_cur + cost
                if t_nxt <= max_sec and t_nxt < best_sec.get(edge.target, math.inf):
                    best_sec[edge.target] = t_nxt
                    best_dist[edge.target] = best_dist[u] + edge.length_m
                    heapq.heappush(pq, (t_nxt, edge.target))

        circuity_samples: List[float] = []
        polys_out: Dict[float, Any] = {}
        max_reach_km = 0.25

        for m in sorted(set(time_budgets_min)):
            cutoff_sec = m * 60.0
            pts: List[Tuple[float, float]] = []
            local_max_km = max(0.25, (cutoff_sec * speed_fallback_ms) / 1000.0 * 0.55)
            for nid, t_val in best_sec.items():
                if t_val <= cutoff_sec:
                    plat, plon = net._node_coords[nid]
                    pts.append((plat, plon))
                    straight_m = haversine_m(origin_lat, origin_lon, plat, plon)
                    local_max_km = max(local_max_km, straight_m / 1000.0)
                    if m == max_min and straight_m > 50.0 and best_dist.get(nid, straight_m) >= straight_m:
                        circuity_samples.append(min(2.2, best_dist[nid] / straight_m))

            if m == max_min:
                max_reach_km = local_max_km

            # Radial 16-sector hull around reachable network nodes merged with primary polygon
            sectors = 16
            fallback_r = (cutoff_sec * speed_fallback_ms) / 1000.0 * 0.72
            sector_r = [fallback_r * 0.5] * sectors
            for plat, plon in pts:
                d_km = haversine_m(origin_lat, origin_lon, plat, plon) / 1000.0
                if d_km <= 0.01:
                    continue
                ang = math.atan2(plat - origin_lat, plon - origin_lon)
                idx = int(((ang + math.pi) / (2.0 * math.pi)) * sectors) % sectors
                if d_km > sector_r[idx]:
                    sector_r[idx] = min(fallback_r * 1.45, d_km)

            cos_lat = max(0.2, math.cos(math.radians(origin_lat)))
            ring: List[Tuple[float, float]] = []
            for idx in range(sectors):
                ang = -math.pi + (idx + 0.5) * (2.0 * math.pi / sectors)
                r_km = max(0.15, sector_r[idx])
                d_lat = (r_km / 111.0) * math.sin(ang)
                d_lon = (r_km / (111.0 * cos_lat)) * math.cos(ang)
                ring.append((round(origin_lon + d_lon, 6), round(origin_lat + d_lat, 6)))
            ring.append(ring[0])
            net_hull = Polygon(ring)
            polys_out[m] = unary_union([base_poly, net_hull]).convex_hull if len(pts) < 12 else unary_union([base_poly, net_hull])

        avg_circ = sum(circuity_samples) / len(circuity_samples) if circuity_samples else 1.26
        return polys_out, round(avg_circ, 3), len(net), net.edge_count, round(max_reach_km, 3)

    def _intersecting_districts(self, geom: Any) -> List[str]:
        b = geom.bounds  # minx, miny, maxx, maxy
        center_lat = 0.5 * (b[1] + b[3])
        center_lon = 0.5 * (b[0] + b[2])
        hits: List[Tuple[float, str]] = []
        for did, dist in self._districts.items():
            d_km = haversine_m(center_lat, center_lon, dist.latitude, dist.longitude) / 1000.0
            # District covers ~5km urban / ~8km rural around cabecera
            thresh = 6.0 if dist.is_urban_core else 9.0
            if geom.contains(Point(dist.longitude, dist.latitude)) or d_km <= thresh:
                hits.append((d_km, f"{dist.name} ({did})"))
        hits.sort(key=lambda x: x[0])
        if not hits:
            nearest = min(
                self._districts.values(),
                key=lambda d: haversine_m(center_lat, center_lon, d.latitude, d.longitude),
            )
            return [f"{nearest.name} ({nearest.district_id})"]
        return [lbl for _, lbl in hits[:5]]

    def _count_sector_facilities_in_geom(self, geom: Any, sector: str) -> int:
        if not self.geography.available:
            return 0
        target_classes = set(self._SECTOR_FACILITY_CLASSES.get(sector.lower(), self._SECTOR_FACILITY_CLASSES["general"]))
        b = geom.bounds
        pois = self.geography.features_in_bbox(b, layer="pois", limit=400) + self.geography.features_in_bbox(b, layer="pois_a", limit=300)
        cnt = 0
        for f in pois:
            fc = (f.get("feature_class") or "").lower()
            sc = (f.get("source_class") or "").lower()
            if fc in target_classes or sc in target_classes:
                pt = Point(float(f["centroid"]["lon"]), float(f["centroid"]["lat"]))
                if geom.contains(pt):
                    cnt += 1
        return cnt

    def expand_territory(
        self,
        primary_geom: Any,
        center_lat: float,
        center_lon: float,
        primary_district_id: str,
        travel_time_minutes: float = 15.0,
        custom_times: Optional[List[float]] = None,
        transport_mode: str = "walk",
        sector: str = "general",
        tobler_factor: float = 0.85,
        slope_pct: float = 5.0,
        max_expansion_minutes: float = 30.0,
        max_expansion_km: float = 8.0,
    ) -> TerritorialExpansionResult:
        """Build Primary, Influence (5/10/15/20/custom), and dynamic Contextual areas."""
        primary_area_km2 = _planar_area_km2(primary_geom)
        primary_bbox = list(primary_geom.bounds)
        primary_r_eq = round(math.sqrt(max(0.01, primary_area_km2) / math.pi), 3)
        primary_barriers, primary_bridges, primary_restr = self._detect_barriers_and_crossings(
            tuple(primary_bbox), slope_pct
        )
        primary_dists = self._intersecting_districts(primary_geom)

        primary_scale = TerritorialScaleArea(
            zone_tier=ZoneTier.PRIMARY_AREA,
            label="Área Principal Seleccionada",
            area_km2=primary_area_km2,
            radius_equiv_km=primary_r_eq,
            travel_time_minutes=0.0,
            transport_mode=transport_mode,
            geometry_geojson=mapping(primary_geom),
            bbox=[round(v, 6) for v in primary_bbox],
            intersecting_districts=primary_dists,
            barriers_detected=primary_barriers,
            bridges_crossings_detected=primary_bridges,
            access_restrictions_detected=primary_restr,
        )

        # B. Influence area via OSMRoadNetwork Dijkstra across 5, 10, 15, 20 & requested minutes
        req_times = sorted({5.0, 10.0, 15.0, 20.0, float(travel_time_minutes)})
        est_max_r_km = min(max_expansion_km, max(1.8, (max(req_times) * (0.45 if transport_mode == "drive" else 0.085))))
        net = self._get_network(center_lat, center_lon, est_max_r_km)

        iso_polys, avg_circ, net_nodes, net_edges, reach_km = self._network_isochrone(
            net=net,
            origin_lat=center_lat,
            origin_lon=center_lon,
            time_budgets_min=req_times,
            mode=transport_mode,
            tobler_factor=tobler_factor,
            base_poly=primary_geom,
        )
        inf_geom = iso_polys[float(travel_time_minutes)]
        inf_bbox = list(inf_geom.bounds)
        inf_barriers, inf_bridges, inf_restr = self._detect_barriers_and_crossings(tuple(inf_bbox), slope_pct)
        inf_area_km2 = _planar_area_km2(inf_geom)
        inf_dists = self._intersecting_districts(inf_geom)

        influence_scale = TerritorialScaleArea(
            zone_tier=ZoneTier.INFLUENCE_AREA,
            label=f"Área de Influencia ({travel_time_minutes:.0f} min · {transport_mode})",
            area_km2=inf_area_km2,
            radius_equiv_km=round(math.sqrt(max(0.01, inf_area_km2) / math.pi), 3),
            travel_time_minutes=float(travel_time_minutes),
            transport_mode=transport_mode,
            geometry_geojson=mapping(inf_geom),
            bbox=[round(v, 6) for v in inf_bbox],
            intersecting_districts=inf_dists,
            network_nodes_count=net_nodes,
            network_edges_count=net_edges,
            circuity_factor=avg_circ,
            barriers_detected=inf_barriers,
            bridges_crossings_detected=inf_bridges,
            access_restrictions_detected=inf_restr,
        )

        # C. Dynamic Contextual Area: ring expansion beyond administrative boundaries
        ctx_minutes = float(travel_time_minutes)
        ctx_geom = inf_geom
        rings = 1
        facs_in_primary = self._count_sector_facilities_in_geom(primary_geom, sector)
        facs_in_ctx = self._count_sector_facilities_in_geom(ctx_geom, sector)

        # Target minimum relevant alternatives outside primary polygon (e.g. schools within 15..25+ min)
        target_min_facs = 6 if sector.lower() in ("school", "education", "market", "commerce", "general") else 3
        limit_reached = False
        limit_reason: Optional[str] = None

        ctx_net = self._get_network(center_lat, center_lon, min(max_expansion_km, 4.8))
        while (facs_in_ctx - facs_in_primary) < target_min_facs or ctx_minutes < max(25.0, travel_time_minutes + 10.0):
            nxt_min = ctx_minutes + 5.0
            nxt_r_km = (nxt_min * 60.0 * ((28_000.0 / 3600.0) if transport_mode == "drive" else (1.25 * max(0.45, tobler_factor)))) / 1000.0
            if nxt_min > max_expansion_minutes or nxt_r_km > max_expansion_km:
                limit_reached = True
                limit_reason = (
                    f"Límite máximo de expansión alcanzado ({ctx_minutes:.0f} min / {max_expansion_km:.1f} km) "
                    f"con {facs_in_ctx} establecimientos relevantes capturados."
                )
                break
            ctx_minutes = nxt_min
            rings += 1
            step_polys, _, _, _, _ = self._network_isochrone(
                net=ctx_net,
                origin_lat=center_lat,
                origin_lon=center_lon,
                time_budgets_min=[ctx_minutes],
                mode=transport_mode,
                tobler_factor=tobler_factor,
                base_poly=primary_geom,
            )
            ctx_geom = step_polys[ctx_minutes]
            facs_in_ctx = self._count_sector_facilities_in_geom(ctx_geom, sector)
            if (facs_in_ctx - facs_in_primary) >= target_min_facs and ctx_minutes >= max(25.0, travel_time_minutes + 10.0):
                break

        ctx_bbox = list(ctx_geom.bounds)
        ctx_barriers, ctx_bridges, ctx_restr = self._detect_barriers_and_crossings(tuple(ctx_bbox), slope_pct)
        ctx_area_km2 = _planar_area_km2(ctx_geom)
        ctx_dists = self._intersecting_districts(ctx_geom)

        contextual_scale = TerritorialScaleArea(
            zone_tier=ZoneTier.CONTEXTUAL_AREA,
            label=f"Área Contextual Dinámica ({ctx_minutes:.0f} min · sector {sector})",
            area_km2=ctx_area_km2,
            radius_equiv_km=round(math.sqrt(max(0.01, ctx_area_km2) / math.pi), 3),
            travel_time_minutes=ctx_minutes,
            transport_mode=transport_mode,
            geometry_geojson=mapping(ctx_geom),
            bbox=[round(v, 6) for v in ctx_bbox],
            intersecting_districts=ctx_dists,
            network_nodes_count=len(ctx_net),
            network_edges_count=ctx_net.edge_count,
            circuity_factor=avg_circ,
            barriers_detected=ctx_barriers,
            bridges_crossings_detected=ctx_bridges,
            access_restrictions_detected=ctx_restr,
        )

        return TerritorialExpansionResult(
            primary_area=primary_scale,
            influence_area=influence_scale,
            contextual_area=contextual_scale,
            isochrones_by_minutes={
                f"{int(m)}min": mapping(poly) for m, poly in iso_polys.items()
            },
            crossed_administrative_boundaries=len(ctx_dists) > 1 or any(primary_district_id not in d for d in ctx_dists),
            expansion_limit_reached=limit_reached,
            expansion_limit_reason=limit_reason,
            rings_explored=rings,
            external_facilities_captured=max(0, facs_in_ctx - facs_in_primary),
            methodology=(
                f"Expansión dinámica en 3 escalas sobre OSMRoadNetwork (Dijkstra peatonal/vehicular + Tobler={tobler_factor:.2f} + "
                f"barreras hidrológicas/pendiente) sin corte administrativo artificial."
            ),
        )


# ---------------------------------------------------------------------------
# Territorial Context Discovery Engine (Section 4)
# ---------------------------------------------------------------------------

class TerritorialContextDiscoveryEngine:
    """Central territorial discovery engine orchestrating OSM, administrative lookup & expansion."""

    def __init__(
        self,
        territorial_engine: Optional[NationalTerritorialContextEngine] = None,
        geography: Optional[IngestedGeography] = None,
        cache_db_path: str = ":memory:",
    ) -> None:
        self._owns_territorial = territorial_engine is None
        self.territorial_engine = territorial_engine or NationalTerritorialContextEngine()
        self._owns_geo = geography is None
        self.geography = geography or self.territorial_engine.geography
        self.cache = LocalTerritorialCache(db_path=cache_db_path)
        self.expansion_engine = DynamicTerritorialExpansionEngine(geography=self.geography)

    def close(self) -> None:
        self.cache.close()
        if self._owns_territorial:
            self.territorial_engine.close()

    def discover(self, selection: TerritorialSelectionInput) -> DiscoveredTerritorialContext:
        """Discover territorial context from point, GeoJSON polygon, or place query."""
        # Check cache for deterministic offline repeatability
        sel_hash = hashlib.sha256(selection.model_dump_json().encode("utf-8")).hexdigest()[:20]
        cached = self.cache.get(f"disc:{sel_hash}")
        if cached is not None:
            model = DiscoveredTerritorialContext(**cached)
            model.cache_hit = True
            return model

        osm_adapter = RateLimitedOSMAdapter(cache=self.cache, allow_online=selection.allow_online_osm)
        allow_online = bool(selection.allow_online_osm or selection.allow_online_fallback)
        enrichment_summary: Dict[str, Any] = {}
        primary_geom: Any = None
        mode: str = "administrative_query"
        center_lat = selection.lat
        center_lon = selection.lon

        if selection.polygon_geojson is not None:
            raw_poly = selection.polygon_geojson
            if raw_poly.get("type") == "Feature":
                raw_poly = raw_poly.get("geometry", raw_poly)
            primary_geom = shape(raw_poly)
            if not primary_geom.is_valid:
                primary_geom = primary_geom.buffer(0)
            c = primary_geom.centroid
            center_lat, center_lon = float(c.y), float(c.x)
            mode = "polygon"
        elif selection.sites:
            pts = [Point(s.lon, s.lat) for s in selection.sites]
            if len(pts) == 1:
                center_lat, center_lon = selection.sites[0].lat, selection.sites[0].lon
                primary_geom = _circle_polygon_wgs84(center_lat, center_lon, radius_km=0.35)
                mode = "point"
            else:
                hull = MultiPoint(pts).convex_hull
                primary_geom = _expand_polygon_buffer_km(hull, 0.28)
                c = primary_geom.centroid
                center_lat, center_lon = float(c.y), float(c.x)
                mode = "polygon"
        elif center_lat is not None and center_lon is not None:
            mode = "point"
            primary_geom = _circle_polygon_wgs84(center_lat, center_lon, radius_km=0.25)
        elif selection.query:
            # Resolve locally first, fallback to cached/optional Nominatim enrichment if unresolved
            ctx_try = self.territorial_engine.resolve_location(query=selection.query)
            if not ctx_try.resolved:
                from saltbor.data_sync.enrichment import MissingDataEnrichmentTool

                enr_tool = getattr(self, "_enrichment_tool", None) or MissingDataEnrichmentTool(cache=self.cache)
                nom_res = enr_tool.geocode_if_missing(selection.query, allow_online=allow_online)
                enrichment_summary["nominatim"] = nom_res
                if nom_res.get("found"):
                    center_lat, center_lon = float(nom_res["lat"]), float(nom_res["lon"])
                    mode = "point"
                    primary_geom = _circle_polygon_wgs84(center_lat, center_lon, radius_km=0.35)

        geo_ctx = self.territorial_engine.resolve_location(
            query=selection.query if center_lat is None else None,
            lat=center_lat,
            lon=center_lon,
        )
        if not geo_ctx.resolved:
            raise ValueError(
                geo_ctx.ambiguity_reason
                or "; ".join(geo_ctx.missing_data)
                or "No se pudo resolver la ubicación en El Salvador."
            )

        center_lat = float(geo_ctx.lat)
        center_lon = float(geo_ctx.lon)
        if primary_geom is None:
            primary_geom = _circle_polygon_wgs84(center_lat, center_lon, radius_km=0.45)

        expansion = self.expansion_engine.expand_territory(
            primary_geom=primary_geom,
            center_lat=center_lat,
            center_lon=center_lon,
            primary_district_id=geo_ctx.district_id,
            travel_time_minutes=selection.travel_time_minutes,
            custom_times=selection.custom_travel_times_minutes,
            transport_mode=selection.transport_mode,
            sector=selection.sector,
            tobler_factor=float(geo_ctx.tobler_walking_speed_factor or 0.85),
            slope_pct=float(geo_ctx.slope_pct or 5.0),
            max_expansion_minutes=selection.max_expansion_minutes,
            max_expansion_km=selection.max_expansion_km,
        )

        # Intersecting administrative units (primary + influence + contextual)
        all_dists = (
            SALVADORAN_DISTRICTS_P8.values()
            if isinstance(SALVADORAN_DISTRICTS_P8, dict)
            else SALVADORAN_DISTRICTS_P8
        )
        dist_by_label = {f"{d.name} ({d.district_id})": d for d in all_dists}
        intersecting_units: List[Dict[str, Any]] = []
        seen_ids = set()
        for lbl in (
            expansion.primary_area.intersecting_districts
            + expansion.influence_area.intersecting_districts
            + expansion.contextual_area.intersecting_districts
        ):
            d = dist_by_label.get(lbl)
            if d and d.district_id not in seen_ids:
                seen_ids.add(d.district_id)
                intersecting_units.append({
                    "district_id": d.district_id,
                    "district_name": d.name,
                    "municipality_id": d.municipality_id,
                    "department_code": d.department_code,
                    "in_primary": lbl in expansion.primary_area.intersecting_districts,
                    "in_influence": lbl in expansion.influence_area.intersecting_districts,
                    "in_contextual": lbl in expansion.contextual_area.intersecting_districts,
                })

        result = DiscoveredTerritorialContext(
            selection_mode=mode,  # type: ignore[arg-type]
            center_lat=round(center_lat, 6),
            center_lon=round(center_lon, 6),
            primary_district_id=geo_ctx.district_id,
            primary_district_name=geo_ctx.district_name,
            municipality_id=geo_ctx.municipality_id,
            municipality_name=geo_ctx.municipality_name,
            department_code=geo_ctx.department_code,
            department_name=geo_ctx.department_name,
            is_urban=bool(geo_ctx.is_urban),
            elevation_m=float(geo_ctx.elevation_m or 0.0),
            slope_pct=float(geo_ctx.slope_pct or 5.0),
            tobler_walking_speed_factor=float(geo_ctx.tobler_walking_speed_factor or 0.85),
            intersecting_units=intersecting_units,
            expansion=expansion,
            osm_attribution=OSM_ODBL_ATTRIBUTION,
            cache_hit=False,
            offline_mode=not allow_online,
            missing_geographic_info=list(geo_ctx.missing_data),
            enrichment_summary=enrichment_summary,
        )
        self.cache.put(f"disc:{sel_hash}", "local_discovery", result.model_dump(mode="json"))
        return result
