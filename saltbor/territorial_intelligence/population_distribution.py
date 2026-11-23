"""Dynamic Territorial Population Distribution Engine (Phase 1.17 Section 8).

Geographically distributes persistent synthetic households across real OSM
residential buildings and residential landuse polygons for any selected
location across El Salvador using SpatialGridIndex and selective LOD 0–3
activation. Never resets existing humans when changing locations or scenarios.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from saltbor.conversational.population_activation import (
    NationalPopulationActivationManager,
    TerritorialPopulationContextEngine,
)
from saltbor.conversational.schemas import ActivationLOD, TerritorialContext
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.population.human import SyntheticHuman
from saltbor.world.geographic.spatial_index import SpatialGridIndex

from saltbor.territorial_intelligence.schemas import (
    BuildingIntelligenceReport,
    BuildingUseCategory,
)


class DynamicPopulationDistributionEngine:
    """Distributes & activates persistent synthetic humans spatially without reset."""

    def __init__(
        self,
        population_manager: Optional[NationalPopulationActivationManager] = None,
        geography: Optional[IngestedGeography] = None,
        seed: int = 42,
    ) -> None:
        self.population_manager = population_manager or NationalPopulationActivationManager(seed=seed)
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self.context_engine = TerritorialPopulationContextEngine()

        # Spatial index of persistent synthetic human coordinates across the country
        self.spatial_index: SpatialGridIndex[str] = SpatialGridIndex(cell_size_degrees=0.01)
        # uid -> {home_district_id, current_district_id, household_id, lat, lon, residential_building_id, is_synthetic_assignment}
        self._spatial_assignments: Dict[str, Dict[str, Any]] = {}

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def activate_for_territory(
        self,
        context: TerritorialContext,
        building_report: Optional[BuildingIntelligenceReport] = None,
        target_lod: ActivationLOD = ActivationLOD.LOD_3_INDIVIDUAL_FULL,
        max_active_agents: int = 40,
        seed: int = 42,
    ) -> Dict[str, Any]:
        """Hydrate persistent humans for a territory and bind synthetic residential footprints."""
        before_total = self.population_manager.total_unique_persistent_individuals()
        before_uids = set(self.population_manager._human_meta.keys())

        activation_info = self.population_manager.activate_region(
            context=context,
            target_lod=target_lod,
            max_active_agents=max_active_agents,
            seed=seed,
        )
        humans = self.population_manager.get_active_humans_for_district(context.district_id)

        # Gather real residential / mixed buildings or residential landuse centroids for spatial grounding
        residential_anchors = self._collect_residential_anchors(context, building_report)
        rng = np.random.default_rng(seed + sum(ord(c) for c in context.district_id))

        assigned_count = 0
        reused_existing_count = 0
        hh_coords: Dict[str, Tuple[float, float, Optional[str]]] = {}

        for idx, h in enumerate(humans):
            uid = str(h.uid)
            if uid in before_uids and uid in self._spatial_assignments:
                reused_existing_count += 1
                continue

            meta = self.population_manager._human_meta.get(uid)
            hh_id = meta.household_id if meta else f"hh_{context.district_id}_{idx // 3:03d}"

            if hh_id not in hh_coords:
                if residential_anchors:
                    anchor = residential_anchors[len(hh_coords) % len(residential_anchors)]
                    a_lat, a_lon, b_id = anchor
                    # Slight deterministic jitter (~10m) within parcel so multiple households never stack identically
                    j_lat = float(rng.normal(0.0, 0.00012))
                    j_lon = float(rng.normal(0.0, 0.00012))
                    hh_coords[hh_id] = (round(a_lat + j_lat, 6), round(a_lon + j_lon, 6), b_id)
                else:
                    # Spread within district core radius when building footprints are absent
                    r_deg = min(0.012, (context.radius_km * 0.65) / 111.0)
                    angle = float(rng.uniform(0.0, 2.0 * math.pi))
                    rad = float(rng.uniform(0.05, 1.0)) * r_deg
                    hh_coords[hh_id] = (
                        round(context.lat + rad * math.sin(angle), 6),
                        round(context.lon + rad * math.cos(angle), 6),
                        None,
                    )

            h_lat, h_lon, b_id = hh_coords[hh_id]
            self._spatial_assignments[uid] = {
                "uid": uid,
                "home_district_id": meta.home_district_id if meta else context.district_id,
                "current_district_id": meta.current_district_id if meta else context.district_id,
                "household_id": hh_id,
                "lat": h_lat,
                "lon": h_lon,
                "residential_building_id": b_id,
                "assignment_type": "SYNTHETIC_RESIDENTIAL_ASSIGNMENT",
                "grounded_on_osm_building": b_id is not None,
            }
            self.spatial_index.insert(uid, h_lat, h_lon, uid)
            assigned_count += 1

        after_total = self.population_manager.total_unique_persistent_individuals()
        pop_ctx = self.context_engine.build_population_context(context, activation_info)

        return {
            "district_id": context.district_id,
            "district_name": context.district_name,
            "target_lod": target_lod.name,
            "hydrated_active_agents": len(humans),
            "newly_spatially_assigned": assigned_count,
            "existing_identities_preserved": reused_existing_count,
            "persistent_total_before": before_total,
            "persistent_total_after": after_total,
            "population_reset_occurred": False,
            "osm_residential_anchors_used": len(residential_anchors),
            "population_context": pop_ctx,
            "sample_spatial_assignments": [
                self._spatial_assignments[str(h.uid)]
                for h in humans[:8]
                if str(h.uid) in self._spatial_assignments
            ],
        }

    def query_synthetic_humans_in_radius(
        self, lat: float, lon: float, radius_km: float = 1.5
    ) -> List[Dict[str, Any]]:
        """Query spatially indexed synthetic residents within radius_km."""
        hits = self.spatial_index.find_within_radius(lat, lon, radius_km)
        return [
            {**self._spatial_assignments[uid], "distance_km": round(dist_km, 3)}
            for uid, dist_km in hits
            if uid in self._spatial_assignments
        ]

    def get_all_spatial_assignments(self) -> List[Dict[str, Any]]:
        return list(self._spatial_assignments.values())

    def _collect_residential_anchors(
        self,
        context: TerritorialContext,
        building_report: Optional[BuildingIntelligenceReport],
    ) -> List[Tuple[float, float, Optional[str]]]:
        anchors: List[Tuple[float, float, Optional[str]]] = []
        if building_report is not None:
            for b in building_report.sample_buildings:
                if b.building_use in (BuildingUseCategory.RESIDENTIAL, BuildingUseCategory.MIXED_USE):
                    anchors.append((b.lat, b.lon, b.feature_id))
            if not anchors:
                # Use untyped building centroids cautiously if residential tags absent
                for b in building_report.sample_buildings[:60]:
                    if b.building_use == BuildingUseCategory.UNKNOWN:
                        anchors.append((b.lat, b.lon, b.feature_id))

        if not anchors and self.geography.available:
            d_lat = context.radius_km / 111.0
            d_lon = context.radius_km / (111.0 * max(0.2, math.cos(math.radians(context.lat))))
            bbox = (context.lon - d_lon, context.lat - d_lat, context.lon + d_lon, context.lat + d_lat)
            for b in self.geography.features_in_bbox(bbox, layer="buildings", feature_class="residential", limit=80):
                anchors.append((float(b["centroid"]["lat"]), float(b["centroid"]["lon"]), b["feature_id"]))
            if not anchors:
                for lu in self.geography.features_in_bbox(bbox, layer="landuse", feature_class="residential_area", limit=40):
                    anchors.append((float(lu["centroid"]["lat"]), float(lu["centroid"]["lon"]), None))
        return anchors
