"""National Building & Land-Use Intelligence Engines (Phase 1.17 Section 3).

Provides physical built-environment, terrain, hydrology, road hierarchy, and
environmental-hazard understanding around any Salvadoran location using real
R-Tree-indexed OSM features and authoritative D.L. 762 / CNR topography.
Never fabricates building occupancy, floor counts, or business activity from
footprint geometry alone.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from saltbor.conversational.schemas import TerritorialContext
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.territory.territory_catalog import TerritoryCatalogService
from saltbor.world.geographic.spatial_index import wgs84_to_local_metric_xy

from saltbor.territorial_intelligence.schemas import (
    BuildingIntelligenceReport,
    BuildingRecord,
    BuildingUseCategory,
    ClassificationOrigin,
    LandUseIntelligenceReport,
)


def _polygon_area_m2(geometry: Optional[Dict[str, Any]]) -> Optional[float]:
    """Compute planar polygon footprint area in square meters using SIRGAS-centered metric XY."""
    if not isinstance(geometry, dict):
        return None
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return None

    def _ring_area(ring: List[List[float]]) -> float:
        if len(ring) < 3:
            return 0.0
        pts = [wgs84_to_local_metric_xy(float(p[1]), float(p[0])) for p in ring]
        area2 = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            area2 += x0 * y1 - x1 * y0
        return abs(area2) * 0.5

    if gtype == "Polygon":
        outer = _ring_area(coords[0]) if coords else 0.0
        holes = sum(_ring_area(h) for h in coords[1:]) if len(coords) > 1 else 0.0
        return round(max(0.0, outer - holes), 1)
    if gtype == "MultiPolygon":
        total = 0.0
        for poly in coords:
            if poly:
                outer = _ring_area(poly[0])
                holes = sum(_ring_area(h) for h in poly[1:]) if len(poly) > 1 else 0.0
                total += max(0.0, outer - holes)
        return round(total, 1)
    return None


def _bbox_for_radius(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float, float]:
    d_lat = radius_km / 111.0
    d_lon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)


def _map_building_use(feature_class: str) -> BuildingUseCategory:
    mapping = {
        "residential": BuildingUseCategory.RESIDENTIAL,
        "commercial": BuildingUseCategory.COMMERCIAL,
        "industrial": BuildingUseCategory.INDUSTRIAL,
        "institutional": BuildingUseCategory.INSTITUTIONAL,
        "educational": BuildingUseCategory.EDUCATIONAL,
        "health": BuildingUseCategory.HEALTH,
        "agricultural": BuildingUseCategory.AGRICULTURAL,
        "religious": BuildingUseCategory.RELIGIOUS,
        "recreational": BuildingUseCategory.RECREATIONAL,
        "mixed_use": BuildingUseCategory.MIXED_USE,
    }
    return mapping.get((feature_class or "").lower(), BuildingUseCategory.UNKNOWN)


class NationalBuildingIntelligenceEngine:
    """Queries and classifies OSM building footprints nationwide with strict provenance."""

    def __init__(self, geography: Optional[IngestedGeography] = None) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def analyze_buildings(
        self,
        lat: float,
        lon: float,
        radius_km: float = 1.0,
        limit: int = 800,
        include_sample_limit: int = 120,
    ) -> BuildingIntelligenceReport:
        """Analyze building footprints around (lat, lon) without fabricating occupancy or floors."""
        if not self.geography.available:
            return BuildingIntelligenceReport(
                lat=lat,
                lon=lon,
                radius_km=radius_km,
                is_partial_coverage=True,
                limitations=["Base espacial geography.sqlite no disponible."],
            )

        bbox = _bbox_for_radius(lat, lon, radius_km)
        exact_counts = self.geography.count_in_bbox(bbox, layer="buildings")
        total_observed = sum(exact_counts.values())

        # Pull building polygons (with geometry for surface area calculation) up to limit
        raw_bldgs = self.geography.features_in_bbox(
            bbox, layer="buildings", limit=limit, include_geometry=True
        )
        # Also pull landuse & POIs in bbox ONLY to tag explicit INFERRED hints for untyped buildings
        landuse_feats = self.geography.features_in_bbox(bbox, layer="landuse", limit=250)
        poi_feats = self.geography.features_in_bbox(bbox, layer="pois", limit=300) + \
            self.geography.features_in_bbox(bbox, layer="pois_a", limit=200)

        # Pre-flatten POI & landuse overlays once before looping over buildings
        poi_lookup: List[Tuple[float, float, BuildingUseCategory]] = []
        _poi_use_map = {
            "retail_commercial": BuildingUseCategory.COMMERCIAL,
            "food_service": BuildingUseCategory.COMMERCIAL,
            "market": BuildingUseCategory.COMMERCIAL,
            "finance": BuildingUseCategory.COMMERCIAL,
            "service_business": BuildingUseCategory.COMMERCIAL,
            "workshop": BuildingUseCategory.COMMERCIAL,
            "hospitality": BuildingUseCategory.COMMERCIAL,
            "education": BuildingUseCategory.EDUCATIONAL,
            "health": BuildingUseCategory.HEALTH,
            "government": BuildingUseCategory.INSTITUTIONAL,
            "public_safety": BuildingUseCategory.INSTITUTIONAL,
            "public_service": BuildingUseCategory.INSTITUTIONAL,
            "religious": BuildingUseCategory.RELIGIOUS,
        }
        for p in poi_feats:
            u = _poi_use_map.get(p.get("feature_class", ""))
            if u is not None:
                c = p["centroid"]
                poi_lookup.append((float(c["lat"]), float(c["lon"]), u))

        lu_lookup: List[Tuple[float, float, float, float, BuildingUseCategory]] = []
        _lu_use_map = {
            "residential_area": BuildingUseCategory.RESIDENTIAL,
            "commercial_area": BuildingUseCategory.COMMERCIAL,
            "industrial_area": BuildingUseCategory.INDUSTRIAL,
            "agricultural_area": BuildingUseCategory.AGRICULTURAL,
            "institutional_area": BuildingUseCategory.INSTITUTIONAL,
            "recreation_area": BuildingUseCategory.RECREATIONAL,
        }
        for lu in landuse_feats:
            u = _lu_use_map.get(lu.get("feature_class", ""))
            bb = lu.get("bbox")
            if u is not None and bb:
                lu_lookup.append((float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]), u))

        counts_by_use: Dict[str, int] = {}
        counts_by_origin: Dict[str, int] = {}
        total_area_m2 = 0.0
        records: List[BuildingRecord] = []

        for b in raw_bldgs:
            b_lat = float(b["centroid"]["lat"])
            b_lon = float(b["centroid"]["lon"])
            name = (b.get("name") or "").strip()
            src_cls = (b.get("source_class") or "").strip().lower()
            use_cat = _map_building_use(b.get("feature_class", "unknown"))

            # Determine classification origin cleanly without fabricating business identity
            if use_cat != BuildingUseCategory.UNKNOWN:
                if name:
                    origin = ClassificationOrigin.OBSERVED
                    conf = 0.88
                    dq = 0.85
                    note = "Nombre y tipo explícito en fuente OSM."
                else:
                    origin = ClassificationOrigin.SOURCE_PROVIDED
                    conf = 0.72
                    dq = 0.75
                    note = f"Tipo '{src_cls or use_cat.value}' provisto por OSM; ocupación no verificada."
            else:
                inferred_use: Optional[BuildingUseCategory] = None
                for plat, plon, p_u in poi_lookup:
                    if abs(plat - b_lat) <= 0.00018 and abs(plon - b_lon) <= 0.00018:
                        inferred_use = p_u
                        break
                if inferred_use is None:
                    for b0, b1, b2, b3, lu_u in lu_lookup:
                        if b0 <= b_lon <= b2 and b1 <= b_lat <= b3:
                            inferred_use = lu_u
                            break
                if inferred_use is not None:
                    use_cat = inferred_use
                    origin = ClassificationOrigin.INFERRED
                    conf = 0.45
                    dq = 0.50
                    note = "Uso inferido por superposición con polígono de uso de suelo o POI cercano; sin verificación directa."
                else:
                    origin = ClassificationOrigin.UNKNOWN
                    conf = 0.25
                    dq = 0.40
                    note = "Edificación sin etiqueta de uso en OSM (building=yes o sin tipo)."

            area_m2 = _polygon_area_m2(b.get("geometry"))
            if area_m2 is not None:
                total_area_m2 += area_m2

            counts_by_use[use_cat.value] = counts_by_use.get(use_cat.value, 0) + 1
            counts_by_origin[origin.value] = counts_by_origin.get(origin.value, 0) + 1

            if len(records) < include_sample_limit:
                records.append(
                    BuildingRecord(
                        feature_id=b["feature_id"],
                        osm_id=b.get("osm_id", ""),
                        name=name,
                        source_dataset=b.get("source", "Geofabrik_OSM_El_Salvador"),
                        source_url=b.get("source_url", "https://download.geofabrik.de/central-america/el-salvador.html"),
                        license=b.get("license", "ODbL-1.0"),
                        last_update=b.get("acquired_at", "2026-11-23"),
                        lat=round(b_lat, 6),
                        lon=round(b_lon, 6),
                        bbox=b.get("bbox", []),
                        geometry_type=b.get("geometry_type", "Polygon"),
                        source_classification=src_cls,
                        building_use=use_cat,
                        classification_origin=origin,
                        height_m=None,  # Geofabrik shapefile omits building:levels/height; never fabricated
                        levels=None,
                        surface_area_m2=area_m2,
                        occupancy_known=False,
                        data_quality=dq,
                        confidence=conf,
                        notes=note,
                    )
                )

        # If total_observed exceeded sample limit, fold remaining exact counts into counts_by_use
        if total_observed > len(raw_bldgs):
            counts_by_use_full: Dict[str, int] = dict(counts_by_use)
            sampled_ratio = len(raw_bldgs) / max(1, total_observed)
            for fc, n in exact_counts.items():
                u = _map_building_use(fc).value
                if u not in counts_by_use_full:
                    counts_by_use_full[u] = n
            counts_by_use = counts_by_use_full
            _ = sampled_ratio

        manifest = self.geography.manifest()
        bldg_layer_meta = manifest.get("layers", {}).get("buildings", {})
        is_partial = total_observed == 0 or bool(bldg_layer_meta.get("is_partial", False))

        limitations = [
            "Las alturas y número de niveles no están incluidos en el shapefile Geofabrik estándar (height_m=None, levels=None).",
            "La ocupación real de viviendas o locales comerciales no se infiere de la huella poligonal.",
        ]
        if total_observed > limit:
            limitations.append(
                f"Se observaron {total_observed} edificaciones en el área; el detalle geométrico se procesó sobre una muestra de {limit}."
            )
        if total_observed == 0:
            limitations.append("Cero huellas de edificios mapeadas en OSM dentro del radio analizado; cobertura edilicia incompleta.")

        return BuildingIntelligenceReport(
            lat=round(lat, 6),
            lon=round(lon, 6),
            radius_km=radius_km,
            total_buildings_observed=total_observed,
            total_surface_area_m2=round(total_area_m2, 1),
            counts_by_use=counts_by_use,
            counts_by_origin=counts_by_origin,
            sample_buildings=records,
            is_partial_coverage=is_partial,
            provenance={
                "source": "OpenStreetMap contributors via Geofabrik (geography.sqlite + R-Tree)",
                "license": "ODbL-1.0",
                "rtree_indexed": self.geography.has_rtree,
                "exact_osm_class_counts": exact_counts,
            },
            limitations=limitations,
        )

    @staticmethod
    def _infer_from_overlay(
        b_lat: float,
        b_lon: float,
        landuse_feats: List[Dict[str, Any]],
        poi_feats: List[Dict[str, Any]],
    ) -> Optional[BuildingUseCategory]:
        # 1. Very close POI (< ~0.00018 deg ~ 20m) gives cautious inferred hint
        for p in poi_feats:
            plat = float(p["centroid"]["lat"])
            plon = float(p["centroid"]["lon"])
            if abs(plat - b_lat) <= 0.00018 and abs(plon - b_lon) <= 0.00018:
                fc = p.get("feature_class", "")
                if fc in ("retail_commercial", "food_service", "market", "finance", "service_business", "workshop", "hospitality"):
                    return BuildingUseCategory.COMMERCIAL
                if fc == "education":
                    return BuildingUseCategory.EDUCATIONAL
                if fc == "health":
                    return BuildingUseCategory.HEALTH
                if fc in ("government", "public_safety", "public_service"):
                    return BuildingUseCategory.INSTITUTIONAL
                if fc == "religious":
                    return BuildingUseCategory.RELIGIOUS

        # 2. Landuse polygon bbox containment
        for lu in landuse_feats:
            bb = lu.get("bbox")
            if bb and bb[0] <= b_lon <= bb[2] and bb[1] <= b_lat <= bb[3]:
                fc = lu.get("feature_class", "")
                if fc == "residential_area":
                    return BuildingUseCategory.RESIDENTIAL
                if fc == "commercial_area":
                    return BuildingUseCategory.COMMERCIAL
                if fc == "industrial_area":
                    return BuildingUseCategory.INDUSTRIAL
                if fc == "agricultural_area":
                    return BuildingUseCategory.AGRICULTURAL
                if fc == "institutional_area":
                    return BuildingUseCategory.INSTITUTIONAL
                if fc == "recreation_area":
                    return BuildingUseCategory.RECREATIONAL
        return None


class TerritorialLandUseIntelligenceEngine:
    """Combines OSM landuse, hydrology, roads, protected areas & CNR relief profiles."""

    def __init__(
        self,
        geography: Optional[IngestedGeography] = None,
        catalog: Optional[TerritoryCatalogService] = None,
    ) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self.catalog = catalog or TerritoryCatalogService()

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def analyze_land_use(
        self,
        context: TerritorialContext,
        radius_km: Optional[float] = None,
    ) -> LandUseIntelligenceReport:
        r_km = radius_km or context.radius_km or 1.5
        bbox = _bbox_for_radius(context.lat, context.lon, r_km)
        topo = self.catalog.get_topographic_hazard_profile(context.district_name or context.district_id)

        lu_counts: Dict[str, int] = {}
        lu_area_m2: Dict[str, float] = {}
        road_counts: Dict[str, int] = {}
        hydro_counts: Dict[str, int] = {}
        protected_count = 0
        transport_count = 0
        missing_layers: List[str] = []

        if self.geography.available:
            lu_counts = self.geography.count_in_bbox(bbox, layer="landuse")
            lu_feats = self.geography.features_in_bbox(bbox, layer="landuse", limit=300, include_geometry=True)
            for f in lu_feats:
                fc = f.get("feature_class") or "other"
                area = _polygon_area_m2(f.get("geometry")) or 0.0
                lu_area_m2[fc] = round(lu_area_m2.get(fc, 0.0) + area, 1)

            road_counts = self.geography.count_in_bbox(bbox, layer="roads")
            for h_layer in ("water", "waterways"):
                hc = self.geography.count_in_bbox(bbox, layer=h_layer)
                for k, v in hc.items():
                    hydro_counts[f"{h_layer}:{k}"] = v
            protected_count = sum(self.geography.count_in_bbox(bbox, layer="protected_areas").values())
            transport_count = (
                sum(self.geography.count_in_bbox(bbox, layer="transport").values())
                + sum(self.geography.count_in_bbox(bbox, layer="transport_a").values())
            )
            if not lu_counts:
                missing_layers.append("Polígonos OSM de uso de suelo (landuse) vacíos en este radio.")
            if not road_counts:
                missing_layers.append("Sin segmentos viales OSM en este radio.")
        else:
            missing_layers.append("Base espacial geography.sqlite no disponible.")

        total_lu = max(1, sum(lu_counts.values()))
        agri_share = round(lu_counts.get("agricultural_area", 0) / total_lu, 3) if lu_counts else (0.65 if not context.is_urban else 0.05)
        urban_signal = round(
            (lu_counts.get("residential_area", 0) + lu_counts.get("commercial_area", 0) + lu_counts.get("industrial_area", 0))
            / total_lu,
            3,
        ) if lu_counts else (0.70 if context.is_urban else 0.15)

        hazards = {
            "flood_exposure": float(topo.get("flood_inundation_risk_index", 0.35)),
            "landslide_exposure": float(topo.get("landslide_risk_index", 0.35)),
            "drought_exposure": float(topo.get("drought_corridor_risk_index", 0.35)),
        }
        constraints: List[str] = []
        if protected_count > 0:
            constraints.append(f"{protected_count} área(s) natural(es) protegida(s) registrada(s) en OSM dentro del radio.")
        if hazards["flood_exposure"] >= 0.65 or hydro_counts.get("waterways:river", 0) > 0:
            constraints.append("Proximidad hidrológica / exposición moderada-alta a inundación en época lluviosa.")
        if hazards["landslide_exposure"] >= 0.65 or float(topo.get("estimated_slope_pct", 5.0)) >= 12.0:
            constraints.append("Pendiente pronunciada / exposición a deslizamientos en laderas.")

        return LandUseIntelligenceReport(
            district_id=context.district_id,
            district_name=context.district_name,
            department_name=context.department_name,
            elevation_m=float(context.elevation_m or 0.0),
            slope_pct=float(topo.get("estimated_slope_pct", context.slope_pct or 5.0)),
            tobler_walking_speed_factor=float(topo.get("tobler_walking_speed_factor", context.tobler_walking_speed_factor or 0.85)),
            terrain_class=str(topo.get("relief_class", context.terrain_class or "UNKNOWN")),
            land_use_counts=lu_counts,
            land_use_area_m2=lu_area_m2,
            road_hierarchy_counts=road_counts,
            total_road_segments=sum(road_counts.values()),
            hydrology_counts=hydro_counts,
            protected_areas_count=protected_count,
            transport_nodes_count=transport_count,
            accessibility_index=float(context.accessibility_index),
            natural_hazards=hazards,
            agricultural_land_share=agri_share,
            urban_expansion_signal=urban_signal,
            environmental_constraints=constraints,
            missing_layers=missing_layers,
            provenance={
                "osm_layers": "OpenStreetMap contributors (ODbL-1.0)",
                "topography": "TerritoryCatalogService / CNR relief heuristics",
            },
        )
