"""Geospatial Population Allocation Engine (Phase 1.18 Section 6).

Allocates synthetic residential population strictly onto valid residential
buildings and residential landuse polygons inside the selected area, respecting
statistical unit totals and explicitly enforcing:
  Building != Dwelling != Household != Person.
Excludes commercial, industrial, educational, health, religious, institutional,
and agricultural buildings as well as water/protected overlays, and tags
untyped OSM `building=yes` footprints with probabilistic occupancy uncertainty.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import Point, shape

from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography

from saltbor.census_intelligence.census_engine import NationalCensusDataIntegrationEngine
from saltbor.census_intelligence.territorial_discovery import _planar_area_km2


def _polygon_area_m2(geometry: Optional[Dict[str, Any]]) -> Optional[float]:
    if not isinstance(geometry, dict):
        return None
    try:
        return round(_planar_area_km2(shape(geometry)) * 1_000_000.0, 1)
    except Exception:
        return None
from saltbor.census_intelligence.schemas import (
    BuildingAllocationRecord,
    DiscoveredTerritorialContext,
    EvidenceClassification,
    GeographicGranularity,
    PopulationAllocationResult,
)

_EXCLUDED_BUILDING_CLASSES = {
    "commercial",
    "industrial",
    "educational",
    "health",
    "religious",
    "recreational",
    "institutional",
    "agricultural",
}


class GeospatialPopulationAllocationEngine:
    """Dasymetric & probabilistic geospatial allocator for synthetic households."""

    def __init__(
        self,
        geography: Optional[IngestedGeography] = None,
        census_engine: Optional[NationalCensusDataIntegrationEngine] = None,
    ) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self.census_engine = census_engine or NationalCensusDataIntegrationEngine()
        self._district_res_area_cache: Dict[str, float] = {}

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def _estimate_district_residential_area_m2(
        self,
        district_id: str,
        center_lat: float,
        center_lon: float,
        is_urban: bool,
    ) -> float:
        """Estimate parent district residential building footprint area (m2) via cached R-Tree sample."""
        if district_id in self._district_res_area_cache:
            return self._district_res_area_cache[district_id]

        if not self.geography.available:
            self._district_res_area_cache[district_id] = 1_500_000.0 if is_urban else 450_000.0
            return self._district_res_area_cache[district_id]

        r_km = 3.2 if is_urban else 5.0
        d_lat = r_km / 111.0
        d_lon = r_km / (111.0 * max(0.2, math.cos(math.radians(center_lat))))
        bbox = (center_lon - d_lon, center_lat - d_lat, center_lon + d_lon, center_lat + d_lat)
        counts = self.geography.count_in_bbox(bbox, layer="buildings")
        res_cnt = counts.get("residential", 0)
        unk_cnt = counts.get("unknown", 0)
        # Approximate total residential-equivalent building footprint area in district core
        # (avg residential footprint ~115 m2; ~62% of unknown footprints in urban cores are residential)
        est_area = max(50_000.0, res_cnt * 115.0 + unk_cnt * 0.62 * 105.0)
        self._district_res_area_cache[district_id] = round(est_area, 1)
        return self._district_res_area_cache[district_id]

    def allocate_population(
        self,
        discovery: DiscoveredTerritorialContext,
        is_full_district_query: Optional[bool] = None,
    ) -> PopulationAllocationResult:
        """Allocate population & households onto residential anchors inside primary_area."""
        primary = discovery.expansion.primary_area
        primary_geom = shape(primary.geometry_geojson)
        if not primary_geom.is_valid:
            primary_geom = primary_geom.buffer(0)
        bbox = tuple(primary.bbox) if len(primary.bbox) == 4 else primary_geom.bounds

        full_district_mode = (
            is_full_district_query
            if is_full_district_query is not None
            else (discovery.selection_mode == "administrative_query" and primary.area_km2 >= 0.5)
        )

        # Retrieve district statistical baseline first to inspect Censo 2024 parameters
        base_census = self.census_engine.query_area_statistics(
            district_id=discovery.primary_district_id,
            requested_granularity=GeographicGranularity.DISTRICT,
        )
        occ_rate = 1.0 - float(base_census.unoccupied_dwellings_share or 0.189)
        mean_hh_size = float(base_census.mean_household_size or 3.1)
        hh_per_occ_dwelling = 1.03

        buildings_analyzed = 0
        res_confirmed = 0
        unk_probabilistic = 0
        excluded_count = 0
        excluded_by_class: Dict[str, int] = {}
        anchors: List[BuildingAllocationRecord] = []
        poly_res_area_m2 = 0.0
        total_capacity_people = 0.0
        limitations: List[str] = []

        if self.geography.available:
            raw_bldgs = self.geography.features_in_bbox(bbox, layer="buildings", limit=1800, include_geometry=True)
            lu_feats = self.geography.features_in_bbox(bbox, layer="landuse", limit=300, include_geometry=True)
            water_feats = self.geography.features_in_bbox(bbox, layer="water", limit=100, include_geometry=True)
            prot_feats = self.geography.features_in_bbox(bbox, layer="protected_areas", limit=50, include_geometry=True)

            def _to_geoms(feats: List[Dict[str, Any]], classes: Optional[set[str]] = None) -> List[Any]:
                geoms: List[Any] = []
                for ft in feats:
                    if classes is not None and ft.get("feature_class") not in classes:
                        continue
                    g = ft.get("geometry")
                    if g:
                        try:
                            sg = shape(g)
                            if not sg.is_valid:
                                sg = sg.buffer(0)
                            geoms.append(sg)
                            continue
                        except Exception:
                            pass
                    bb = ft.get("bbox")
                    if bb and len(bb) == 4:
                        geoms.append(shape({
                            "type": "Polygon",
                            "coordinates": [[[bb[0], bb[1]], [bb[2], bb[1]], [bb[2], bb[3]], [bb[0], bb[3]], [bb[0], bb[1]]]],
                        }))
                return geoms

            res_lu_geoms = _to_geoms(lu_feats, {"residential_area"})
            non_res_lu_geoms = _to_geoms(lu_feats, {"commercial_area", "industrial_area", "waste_area"})
            heavy_excl_geoms = _to_geoms(lu_feats, {"industrial_area", "waste_area"})
            hazard_geoms = _to_geoms(water_feats + prot_feats)

            def _in_geoms(lon: float, lat: float, geoms: List[Any]) -> bool:
                if not geoms:
                    return False
                pt = Point(lon, lat)
                return any(g.contains(pt) for g in geoms)

            for b in raw_bldgs:
                b_lat = float(b["centroid"]["lat"])
                b_lon = float(b["centroid"]["lon"])
                if not primary_geom.contains(Point(b_lon, b_lat)):
                    continue

                buildings_analyzed += 1
                fc = (b.get("feature_class") or "unknown").lower()
                area_m2 = float(_polygon_area_m2(b.get("geometry")) or 105.0)

                if fc in _EXCLUDED_BUILDING_CLASSES:
                    excluded_count += 1
                    excluded_by_class[fc] = excluded_by_class.get(fc, 0) + 1
                    anchors.append(
                        BuildingAllocationRecord(
                            feature_id=b["feature_id"],
                            lat=round(b_lat, 6),
                            lon=round(b_lon, 6),
                            source_building_class=fc,
                            allocated_residential=False,
                            exclusion_reason=f"Edificio no residencial ({fc})",
                            surface_area_m2=area_m2,
                        )
                    )
                    continue

                if _in_geoms(b_lon, b_lat, hazard_geoms):
                    excluded_count += 1
                    excluded_by_class["water_or_protected"] = excluded_by_class.get("water_or_protected", 0) + 1
                    anchors.append(
                        BuildingAllocationRecord(
                            feature_id=b["feature_id"],
                            lat=round(b_lat, 6),
                            lon=round(b_lon, 6),
                            source_building_class=fc,
                            allocated_residential=False,
                            exclusion_reason="Ubicado dentro de cuerpo de agua o área protegida",
                            surface_area_m2=area_m2,
                        )
                    )
                    continue

                if fc == "residential":
                    in_heavy_non_res = _in_geoms(b_lon, b_lat, heavy_excl_geoms) and not _in_geoms(b_lon, b_lat, res_lu_geoms)
                    if in_heavy_non_res:
                        excluded_count += 1
                        excluded_by_class["non_residential_landuse"] = excluded_by_class.get("non_residential_landuse", 0) + 1
                        continue
                    occ_prob = 0.88
                    uncertain = False
                    res_confirmed += 1
                    est_dwellings = max(1.0, min(6.0, area_m2 / 95.0))
                else:
                    # fc == "unknown" (building=yes): probabilistic allocation ONLY with residential evidence
                    in_res_lu = _in_geoms(b_lon, b_lat, res_lu_geoms)
                    in_non_res = _in_geoms(b_lon, b_lat, non_res_lu_geoms)
                    if in_non_res and not in_res_lu:
                        excluded_count += 1
                        excluded_by_class["unknown_in_non_res_zone"] = excluded_by_class.get("unknown_in_non_res_zone", 0) + 1
                        anchors.append(
                            BuildingAllocationRecord(
                                feature_id=b["feature_id"],
                                lat=round(b_lat, 6),
                                lon=round(b_lon, 6),
                                source_building_class=fc,
                                allocated_residential=False,
                                exclusion_reason="Edificio sin etiqueta en zona comercial/industrial",
                                surface_area_m2=area_m2,
                            )
                        )
                        continue
                    if area_m2 > 600.0 or area_m2 < 20.0:
                        excluded_count += 1
                        excluded_by_class["unknown_non_dwelling_footprint"] = excluded_by_class.get("unknown_non_dwelling_footprint", 0) + 1
                        continue

                    occ_prob = 0.65 if in_res_lu else 0.42
                    uncertain = True
                    unk_probabilistic += 1
                    est_dwellings = max(1.0, min(3.0, area_m2 / 100.0))

                exp_occ_hh = max(1, int(round(est_dwellings * occ_rate * occ_prob * hh_per_occ_dwelling)))
                effective_area = area_m2 * occ_prob
                poly_res_area_m2 += effective_area
                total_capacity_people += est_dwellings * occ_rate * occ_prob * hh_per_occ_dwelling * mean_hh_size

                anchors.append(
                    BuildingAllocationRecord(
                        feature_id=b["feature_id"],
                        lat=round(b_lat, 6),
                        lon=round(b_lon, 6),
                        source_building_class=fc,
                        allocated_residential=True,
                        surface_area_m2=area_m2,
                        estimated_dwellings=round(est_dwellings, 2),
                        estimated_occupied_households=exp_occ_hh,
                        occupancy_probability=round(occ_prob, 2),
                        occupancy_uncertain=uncertain,
                    )
                )

            # If zero residential building footprints exist inside primary_geom, fall back to residential_area landuse centroids
            if (res_confirmed + unk_probabilistic) == 0:
                for lu in lu_feats:
                    if lu.get("feature_class") == "residential_area":
                        lu_lat, lu_lon = float(lu["centroid"]["lat"]), float(lu["centroid"]["lon"])
                        if primary_geom.contains(Point(lu_lon, lu_lat)):
                            lu_area = float(_polygon_area_m2(lu.get("geometry")) or 15000.0)
                            poly_res_area_m2 += lu_area * 0.25
                            total_capacity_people += max(30.0, (lu_area / 220.0) * mean_hh_size * occ_rate)
                            anchors.append(
                                BuildingAllocationRecord(
                                    feature_id=lu["feature_id"],
                                    lat=round(lu_lat, 6),
                                    lon=round(lu_lon, 6),
                                    source_building_class="residential_landuse_centroid",
                                    allocated_residential=True,
                                    surface_area_m2=round(lu_area, 1),
                                    estimated_dwellings=max(10.0, round(lu_area / 220.0, 1)),
                                    estimated_occupied_households=max(8, int(round((lu_area / 220.0) * occ_rate))),
                                    occupancy_probability=0.55,
                                    occupancy_uncertain=True,
                                )
                            )
                if not any(a.allocated_residential for a in anchors):
                    limitations.append(
                        "Cero huellas edificatorias residenciales en OSM dentro del polígono; se utiliza área residencial agregada del polígono."
                    )

        dist_res_area_m2 = self._estimate_district_residential_area_m2(
            discovery.primary_district_id,
            discovery.center_lat,
            discovery.center_lon,
            discovery.is_urban,
        )
        dist_pop = base_census.official_population or (
            base_census.sae_estimate.estimated_population if base_census.sae_estimate else 25000
        )

        if full_district_mode:
            poly_share = 1.0
            alloc_pop = int(dist_pop)
            alloc_hh = max(1, int(round(alloc_pop / mean_hh_size)))
            method = "District-scale statistical allocation grounded onto residential OSM footprints"
            ev_type = base_census.population_evidence_type
            unc_pct = 0.0 if ev_type == EvidenceClassification.PUBLIC_OFFICIAL else 18.0
        else:
            poly_share = min(1.0, max(0.0005, poly_res_area_m2 / max(1.0, dist_res_area_m2)))
            cap_est = int(round(total_capacity_people)) if total_capacity_people >= 12.0 else None
            sub_census = self.census_engine.query_area_statistics(
                district_id=discovery.primary_district_id,
                requested_granularity=GeographicGranularity.CUSTOM_POLYGON,
                custom_area_label=primary.label,
                local_residential_share=poly_share,
                local_building_capacity_estimate=cap_est,
            )
            alloc_pop = sub_census.sae_estimate.estimated_population if sub_census.sae_estimate else max(15, int(round(dist_pop * poly_share)))
            alloc_hh = sub_census.sae_estimate.estimated_households if sub_census.sae_estimate else max(5, int(round(alloc_pop / mean_hh_size)))
            method = (
                "Dasymetric residential footprint allocation (excluding commercial/industrial/educational/health/water) "
                "+ Empirical-Bayes SAE constrained to Censo 2024"
            )
            ev_type = EvidenceClassification.ESTIMATED_FROM_OFFICIAL
            unc_pct = sub_census.sae_estimate.uncertainty_pct if sub_census.sae_estimate else 28.0

        if unk_probabilistic > 0:
            limitations.append(
                f"{unk_probabilistic} edificaciones OSM sin etiqueta específica (building=yes) asignadas probabilísticamente con incertidumbre explícita."
            )
        if excluded_count > 0:
            limitations.append(
                f"{excluded_count} edificaciones no residenciales o incompatibles excluidas de asignación habitacional."
            )

        return PopulationAllocationResult(
            district_id=discovery.primary_district_id,
            district_official_population=int(dist_pop),
            target_area_km2=primary.area_km2,
            district_reference_residential_area_m2=dist_res_area_m2,
            polygon_residential_area_m2=round(poly_res_area_m2, 1),
            polygon_share_of_district=round(poly_share, 5),
            allocated_population_target=alloc_pop,
            allocated_households_target=alloc_hh,
            buildings_analyzed=buildings_analyzed,
            buildings_residential_confirmed=res_confirmed,
            buildings_unknown_probabilistic=unk_probabilistic,
            buildings_excluded_non_residential=excluded_count,
            excluded_counts_by_class=excluded_by_class,
            building_anchors=anchors[:250],
            allocation_method=method,
            evidence_type=ev_type,
            uncertainty_pct=round(unc_pct, 1),
            limitations=limitations,
        )
