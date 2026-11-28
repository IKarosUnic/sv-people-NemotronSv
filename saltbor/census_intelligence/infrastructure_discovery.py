"""Infrastructure & Service Discovery Engine (Phase 1.18 Section 9).

Discovers and deduplicates territorial entities across Education, Health,
Economy, Infrastructure, and Environment from OSM (`geography.sqlite`),
curated P8 records, and imported official registries (MINEDUCYT / MINSAL).
Maintains strict verification status (`OSM_IDENTIFIED`, `OFFICIAL_CONFIRMED`,
`FIELD_VERIFIED`, `UNVERIFIED`, `POSSIBLY_INACTIVE`), never invents school
levels or capacity, and tags every entity with its ZoneTier (Primary, Influence,
Contextual).
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import Point, shape

from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.datasets.salvadoran.establishments_data import SALVADORAN_ESTABLISHMENTS_P8
from saltbor.world.geographic.osm_router import haversine_m

from saltbor.census_intelligence.census_engine import NationalCensusDataIntegrationEngine
from saltbor.census_intelligence.schemas import (
    DiscoveredTerritorialContext,
    EvidenceClassification,
    InfrastructureEntity,
    InfrastructureInventory,
    VerificationStatus,
    ZoneTier,
)


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").lower().strip())
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9\s]", " ", cleaned).strip()


def _infer_school_levels_from_tokens(name: str, source_class: str) -> Tuple[List[str], str]:
    """Infer school levels ONLY from explicit unambiguous tokens; never guess all levels."""
    txt = _norm(f"{name} {source_class}")
    levels: List[str] = []
    if any(k in txt for k in ("kinder", "parvularia", "preschool", "preescolar", "kindergarten", "maternal")):
        levels.append("parvularia")
    if any(k in txt for k in ("primaria", "escuela basica", "centro escolar", "basica")):
        levels.extend(["basica_ciclo_1", "basica_ciclo_2"])
    if any(k in txt for k in ("tercer ciclo", "complejo educativo")):
        levels.extend(["basica_ciclo_1", "basica_ciclo_2", "basica_ciclo_3"])
    if any(k in txt for k in ("bachillerato", "instituto nacional", "complejo educativo", "college")):
        levels.append("bachillerato")
    if any(k in txt for k in ("universidad", "university", "esen", "superior")):
        levels.append("superior")

    deduped = list(dict.fromkeys(levels))
    if deduped:
        return deduped, "TOKEN_INFERRED"
    return [], "UNVERIFIED"


class InfrastructureServiceDiscoveryEngine:
    """Builds a deduplicated, zone-tiered infrastructure & service inventory."""

    def __init__(
        self,
        geography: Optional[IngestedGeography] = None,
        census_engine: Optional[NationalCensusDataIntegrationEngine] = None,
    ) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self.census_engine = census_engine

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def discover_inventory(
        self,
        discovery: DiscoveredTerritorialContext,
        extra_osm_features: Optional[List[Dict[str, Any]]] = None,
    ) -> InfrastructureInventory:
        """Discover infrastructure & services across Primary, Influence & Contextual scales."""
        exp = discovery.expansion
        primary_geom = shape(exp.primary_area.geometry_geojson)
        influence_geom = shape(exp.influence_area.geometry_geojson)
        contextual_geom = shape(exp.contextual_area.geometry_geojson)
        ctx_bbox = tuple(exp.contextual_area.bbox) if len(exp.contextual_area.bbox) == 4 else contextual_geom.bounds

        tobler = max(0.45, float(discovery.tobler_walking_speed_factor or 0.85))
        circuity = max(1.0, float(exp.influence_area.circuity_factor or 1.25))
        walk_m_per_min = 1.25 * tobler * 60.0
        drive_m_per_min = 28_000.0 / 60.0

        def _zone_tier(lon: float, lat: float) -> Optional[ZoneTier]:
            pt = Point(lon, lat)
            if primary_geom.contains(pt):
                return ZoneTier.PRIMARY_AREA
            if influence_geom.contains(pt):
                return ZoneTier.INFLUENCE_AREA
            if contextual_geom.contains(pt):
                return ZoneTier.CONTEXTUAL_AREA
            return None

        raw_candidates: List[InfrastructureEntity] = []

        if self.geography.available:
            # 1. POIs & Polygon POIs (Education, Health, Economy, Recreation)
            poi_rows = (
                self.geography.features_in_bbox(ctx_bbox, layer="pois", limit=1200, include_geometry=False)
                + self.geography.features_in_bbox(ctx_bbox, layer="pois_a", limit=1200, include_geometry=False)
            )
            for f in poi_rows:
                fc = (f.get("feature_class") or "other").lower()
                sc = (f.get("source_class") or "").lower()
                plat, plon = float(f["centroid"]["lat"]), float(f["centroid"]["lon"])
                zt = _zone_tier(plon, plat)
                if zt is None:
                    continue

                if fc == "education":
                    domain = "EDUCATION"
                    subtype = sc or "school"
                elif fc == "health":
                    domain = "HEALTH"
                    subtype = sc or "clinic"
                elif sc == "pharmacy":
                    domain = "HEALTH"
                    subtype = "pharmacy"
                elif fc in ("market", "retail_commercial", "food_service", "finance", "service_business", "hospitality"):
                    domain = "ECONOMY"
                    subtype = sc or fc
                elif fc == "recreation":
                    domain = "INFRASTRUCTURE"
                    subtype = sc or "public_space"
                else:
                    continue

                dist_m = round(haversine_m(discovery.center_lat, discovery.center_lon, plat, plon), 1)
                walk_min = round((dist_m * circuity) / max(1.0, walk_m_per_min), 1)
                drive_min = round((dist_m * circuity) / max(1.0, drive_m_per_min), 1)

                name = (f.get("name") or "").strip() or f"{subtype} ({f['feature_id']})"
                levels: List[str] = []
                lv_status = "NOT_APPLICABLE"
                if domain == "EDUCATION":
                    levels, lv_status = _infer_school_levels_from_tokens(name, sc)

                ver_status = (
                    VerificationStatus.OSM_IDENTIFIED
                    if (f.get("name") or "").strip()
                    else VerificationStatus.UNVERIFIED
                )

                raw_candidates.append(
                    InfrastructureEntity(
                        entity_id=f["feature_id"],
                        name=name,
                        domain=domain,  # type: ignore[arg-type]
                        subtype=subtype,
                        lat=round(plat, 6),
                        lon=round(plon, 6),
                        zone_tier=zt,
                        distance_m=dist_m,
                        estimated_walk_min=walk_min,
                        estimated_drive_min=drive_min,
                        source="OpenStreetMap (Geofabrik ODbL-1.0)",
                        updated_at=f.get("acquired_at", "2026-11-23"),
                        verification_status=ver_status,
                        confidence_level=0.78 if ver_status == VerificationStatus.OSM_IDENTIFIED else 0.45,
                        confirmed_levels=levels,
                        levels_evidence_status=lv_status,  # type: ignore[arg-type]
                        enrollment=None,
                        installed_capacity=None,
                        available_vacancies=None,
                        capacity_evidence_type=EvidenceClassification.UNAVAILABLE,
                        raw_tags={"layer": f.get("layer"), "source_class": sc, "feature_class": fc},
                    )
                )

            # 2. Educational & Health Buildings (that may lack a POI)
            for b_cls, domain, subtype in (
                ("educational", "EDUCATION", "educational_building"),
                ("health", "HEALTH", "health_building"),
                ("commercial", "ECONOMY", "commercial_building"),
            ):
                b_rows = self.geography.features_in_bbox(
                    ctx_bbox, layer="buildings", feature_class=b_cls, limit=250, include_geometry=False
                )
                for b in b_rows:
                    blat, blon = float(b["centroid"]["lat"]), float(b["centroid"]["lon"])
                    zt = _zone_tier(blon, blat)
                    if zt is None:
                        continue
                    dist_m = round(haversine_m(discovery.center_lat, discovery.center_lon, blat, blon), 1)
                    name = (b.get("name") or "").strip() or f"{subtype} ({b['feature_id']})"
                    levels, lv_status = _infer_school_levels_from_tokens(name, b_cls) if domain == "EDUCATION" else ([], "NOT_APPLICABLE")
                    raw_candidates.append(
                        InfrastructureEntity(
                            entity_id=b["feature_id"],
                            name=name,
                            domain=domain,  # type: ignore[arg-type]
                            subtype=subtype,
                            lat=round(blat, 6),
                            lon=round(blon, 6),
                            zone_tier=zt,
                            distance_m=dist_m,
                            estimated_walk_min=round((dist_m * circuity) / max(1.0, walk_m_per_min), 1),
                            estimated_drive_min=round((dist_m * circuity) / max(1.0, drive_m_per_min), 1),
                            source="OpenStreetMap Buildings (Geofabrik ODbL-1.0)",
                            updated_at=b.get("acquired_at", "2026-11-23"),
                            verification_status=VerificationStatus.UNVERIFIED if not (b.get("name") or "").strip() else VerificationStatus.OSM_IDENTIFIED,
                            confidence_level=0.40 if not (b.get("name") or "").strip() else 0.70,
                            confirmed_levels=levels,
                            levels_evidence_status=lv_status,  # type: ignore[arg-type]
                            capacity_evidence_type=EvidenceClassification.UNAVAILABLE,
                            raw_tags={"layer": "buildings", "feature_class": b_cls},
                        )
                    )

            # 3. Transport & Public Spaces
            tr_rows = (
                self.geography.features_in_bbox(ctx_bbox, layer="transport", limit=300, include_geometry=False)
                + self.geography.features_in_bbox(ctx_bbox, layer="transport_a", limit=100, include_geometry=False)
            )
            for t in tr_rows:
                tlat, tlon = float(t["centroid"]["lat"]), float(t["centroid"]["lon"])
                zt = _zone_tier(tlon, tlat)
                if zt is None:
                    continue
                dist_m = round(haversine_m(discovery.center_lat, discovery.center_lon, tlat, tlon), 1)
                sc = (t.get("source_class") or t.get("feature_class") or "bus_stop").lower()
                raw_candidates.append(
                    InfrastructureEntity(
                        entity_id=t["feature_id"],
                        name=(t.get("name") or "").strip() or f"Parada/Transporte ({sc})",
                        domain="INFRASTRUCTURE",
                        subtype=sc,
                        lat=round(tlat, 6),
                        lon=round(tlon, 6),
                        zone_tier=zt,
                        distance_m=dist_m,
                        estimated_walk_min=round((dist_m * circuity) / max(1.0, walk_m_per_min), 1),
                        source="OpenStreetMap Transport (ODbL-1.0)",
                        updated_at=t.get("acquired_at", "2026-11-23"),
                        verification_status=VerificationStatus.OSM_IDENTIFIED,
                        confidence_level=0.75,
                    )
                )

            # 4. Environment (waterways, water, protected areas)
            env_rows = (
                self.geography.features_in_bbox(ctx_bbox, layer="waterways", limit=120, include_geometry=False)
                + self.geography.features_in_bbox(ctx_bbox, layer="water", limit=80, include_geometry=False)
                + self.geography.features_in_bbox(ctx_bbox, layer="protected_areas", limit=50, include_geometry=False)
            )
            for e in env_rows:
                elat, elon = float(e["centroid"]["lat"]), float(e["centroid"]["lon"])
                zt = _zone_tier(elon, elat)
                if zt is None:
                    continue
                dist_m = round(haversine_m(discovery.center_lat, discovery.center_lon, elat, elon), 1)
                raw_candidates.append(
                    InfrastructureEntity(
                        entity_id=e["feature_id"],
                        name=(e.get("name") or "").strip() or f"{e.get('layer')}:{e.get('feature_class')}",
                        domain="ENVIRONMENT",
                        subtype=(e.get("feature_class") or e.get("layer") or "natural_feature"),
                        lat=round(elat, 6),
                        lon=round(elon, 6),
                        zone_tier=zt,
                        distance_m=dist_m,
                        source="OpenStreetMap Environment (ODbL-1.0)",
                        updated_at=e.get("acquired_at", "2026-11-23"),
                        verification_status=VerificationStatus.OSM_IDENTIFIED,
                        confidence_level=0.80,
                    )
                )

        # 5. Merge Official MINED / MINSAL records if imported via Census Engine
        if self.census_engine is not None:
            for ms in self.census_engine.get_imported_mined_schools():
                slat = ms.get("lat")
                slon = ms.get("lon")
                if slat is None or slon is None:
                    continue
                zt = _zone_tier(float(slon), float(slat)) or ZoneTier.CONTEXTUAL_AREA
                dist_m = round(haversine_m(discovery.center_lat, discovery.center_lon, float(slat), float(slon)), 1)
                if dist_m > 12_000:
                    continue
                cap = ms.get("installed_capacity")
                enr = ms.get("enrollment")
                raw_candidates.append(
                    InfrastructureEntity(
                        entity_id=f"MINED:{ms['school_code']}",
                        name=ms["name"],
                        domain="EDUCATION",
                        subtype=f"mined_{ms.get('sector', 'publico')}",
                        lat=round(float(slat), 6),
                        lon=round(float(slon), 6),
                        zone_tier=zt,
                        distance_m=dist_m,
                        estimated_walk_min=round((dist_m * circuity) / max(1.0, walk_m_per_min), 1),
                        estimated_drive_min=round((dist_m * circuity) / max(1.0, drive_m_per_min), 1),
                        source=ms.get("source_institution", "MINEDUCYT El Salvador"),
                        updated_at=ms.get("published_at", "2024"),
                        verification_status=VerificationStatus.OFFICIAL_CONFIRMED,
                        confidence_level=0.95,
                        confirmed_levels=ms.get("levels", []),
                        levels_evidence_status="OFFICIAL_CONFIRMED" if ms.get("levels") else "UNVERIFIED",
                        enrollment=enr,
                        installed_capacity=cap,
                        available_vacancies=ms.get("available_vacancies"),
                        capacity_evidence_type=(
                            EvidenceClassification.PUBLIC_OFFICIAL
                            if cap is not None or enr is not None
                            else EvidenceClassification.UNAVAILABLE
                        ),
                    )
                )

        # 5b. Merge optional cached Overpass enrichment POIs (ODbL-1.0)
        for ex_feat in extra_osm_features or []:
            elat = ex_feat.get("lat")
            elon = ex_feat.get("lon")
            if elat is None or elon is None:
                continue
            zt = _zone_tier(float(elon), float(elat)) or ZoneTier.CONTEXTUAL_AREA
            dist_m = round(haversine_m(discovery.center_lat, discovery.center_lon, float(elat), float(elon)), 1)
            if dist_m > 12_000:
                continue
            dom = str(ex_feat.get("domain") or "INFRASTRUCTURE")
            sub = str(ex_feat.get("subtype") or "poi")
            tags = ex_feat.get("tags") or {}
            levels, levels_status = _extract_levels(tags) if dom == "EDUCATION" else ([], "UNVERIFIED")
            raw_candidates.append(
                InfrastructureEntity(
                    entity_id=str(ex_feat.get("entity_id") or f"overpass:{sub}:{elat}:{elon}"),
                    name=str(ex_feat.get("name") or sub),
                    domain=dom,
                    subtype=sub,
                    lat=round(float(elat), 6),
                    lon=round(float(elon), 6),
                    zone_tier=zt,
                    distance_m=dist_m,
                    estimated_walk_min=round((dist_m * circuity) / max(1.0, walk_m_per_min), 1),
                    estimated_drive_min=round((dist_m * circuity) / max(1.0, drive_m_per_min), 1),
                    source=str(ex_feat.get("source") or "OpenStreetMap Overpass (Cached ODbL-1.0)"),
                    updated_at=str(ex_feat.get("updated_at") or "2026"),
                    verification_status=VerificationStatus.OSM_IDENTIFIED,
                    confidence_level=0.72,
                    confirmed_levels=levels,
                    levels_evidence_status=levels_status,
                    capacity_evidence_type=EvidenceClassification.UNAVAILABLE,
                )
            )

        # 6. Deduplicate spatial + name matches within 60m per domain
        # Prioritize OFFICIAL_CONFIRMED > OSM_IDENTIFIED > UNVERIFIED
        prio = {
            VerificationStatus.FIELD_VERIFIED: 0,
            VerificationStatus.OFFICIAL_CONFIRMED: 1,
            VerificationStatus.OSM_IDENTIFIED: 2,
            VerificationStatus.UNVERIFIED: 3,
            VerificationStatus.POSSIBLY_INACTIVE: 4,
        }
        raw_candidates.sort(key=lambda e: (prio[e.verification_status], e.distance_m))

        deduped: List[InfrastructureEntity] = []
        dups_merged = 0
        for cand in raw_candidates:
            cand_norm = _norm(cand.name)
            matched_idx: Optional[int] = None
            for idx, ex in enumerate(deduped):
                if ex.domain != cand.domain:
                    continue
                if abs(ex.lat - cand.lat) <= 0.00055 and abs(ex.lon - cand.lon) <= 0.00055:
                    ex_norm = _norm(ex.name)
                    dist_between = haversine_m(ex.lat, ex.lon, cand.lat, cand.lon)
                    if dist_between <= 65.0 and (
                        cand.verification_status == VerificationStatus.UNVERIFIED
                        or ex.verification_status == VerificationStatus.UNVERIFIED
                        or cand_norm == ex_norm
                        or cand_norm in ex_norm
                        or ex_norm in cand_norm
                        or dist_between <= 28.0
                    ):
                        matched_idx = idx
                        break
            if matched_idx is not None:
                dups_merged += 1
                ex = deduped[matched_idx]
                if cand.confirmed_levels and not ex.confirmed_levels:
                    ex.confirmed_levels = cand.confirmed_levels
                    ex.levels_evidence_status = cand.levels_evidence_status
                if cand.enrollment is not None and ex.enrollment is None:
                    ex.enrollment = cand.enrollment
                    ex.installed_capacity = cand.installed_capacity
                    ex.available_vacancies = cand.available_vacancies
                    ex.capacity_evidence_type = cand.capacity_evidence_type
            else:
                deduped.append(cand)

        deduped.sort(key=lambda e: e.distance_m)
        by_domain: Dict[str, int] = {}
        by_zone: Dict[str, int] = {}
        by_ver: Dict[str, int] = {}
        for e in deduped:
            by_domain[e.domain] = by_domain.get(e.domain, 0) + 1
            by_zone[e.zone_tier.value] = by_zone.get(e.zone_tier.value, 0) + 1
            by_ver[e.verification_status.value] = by_ver.get(e.verification_status.value, 0) + 1

        return InfrastructureInventory(
            entities=deduped,
            counts_by_domain=by_domain,
            counts_by_zone_tier=by_zone,
            counts_by_verification_status=by_ver,
            duplicates_merged=dups_merged,
        )
