"""National Territorial Data Coverage Registry across all 14 Departments & 262 Districts (Phase 1.17 Section 11).

Computes authentic geographic, building, road, land-use, commercial, population,
mobility, and employment data coverage directly from geography.sqlite (R-Tree)
and authoritative D.L. 762 / P8 datasets, classifying every territory honestly as
GOOD, PARTIAL, POOR, or INSUFFICIENT.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Any, Dict, List, Optional

from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.datasets.salvadoran.establishments_data import SALVADORAN_ESTABLISHMENTS_P8
from saltbor.datasets.salvadoran.territory_data import (
    SALVADORAN_DEPARTMENTS_P8,
    SALVADORAN_DISTRICTS_P8,
    SALVADORAN_MUNICIPALITIES_P8,
    SalvadoranDepartmentProfile,
    SalvadoranDistrictData,
    SalvadoranMunicipalityData,
)

from saltbor.territorial_intelligence.schemas import (
    CoverageTier,
    NationalCoverageSummary,
    TerritorialCoverageRecord,
)


class NationalTerritorialCoverageRegistry:
    """Computes and caches national data coverage quality across El Salvador."""

    def __init__(self, geography: Optional[IngestedGeography] = None) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)

        self._departments: Dict[str, SalvadoranDepartmentProfile] = (
            SALVADORAN_DEPARTMENTS_P8
            if isinstance(SALVADORAN_DEPARTMENTS_P8, dict)
            else {d.code: d for d in SALVADORAN_DEPARTMENTS_P8}
        )
        self._municipalities: Dict[str, SalvadoranMunicipalityData] = (
            SALVADORAN_MUNICIPALITIES_P8
            if isinstance(SALVADORAN_MUNICIPALITIES_P8, dict)
            else {m.municipality_id: m for m in SALVADORAN_MUNICIPALITIES_P8}
        )
        self._districts: Dict[str, SalvadoranDistrictData] = (
            SALVADORAN_DISTRICTS_P8
            if isinstance(SALVADORAN_DISTRICTS_P8, dict)
            else {d.district_id: d for d in SALVADORAN_DISTRICTS_P8}
        )
        self._p8_by_dept: Dict[str, int] = {}
        p8_items = (
            SALVADORAN_ESTABLISHMENTS_P8.values()
            if isinstance(SALVADORAN_ESTABLISHMENTS_P8, dict)
            else SALVADORAN_ESTABLISHMENTS_P8
        )
        for rec in p8_items:
            self._p8_by_dept[rec.department_code] = self._p8_by_dept.get(rec.department_code, 0) + 1

        self._summary_cache: Optional[NationalCoverageSummary] = None
        self._district_cache: Dict[str, TerritorialCoverageRecord] = {}

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def _compute_district_record(self, dist: SalvadoranDistrictData) -> TerritorialCoverageRecord:
        if dist.district_id in self._district_cache:
            return self._district_cache[dist.district_id]

        dept = self._departments.get(dist.department_code)
        mun = self._municipalities.get(dist.municipality_id)
        r_km = 2.0 if dist.is_urban_core else 3.0
        d_lat = r_km / 111.0
        d_lon = r_km / (111.0 * max(0.2, math.cos(math.radians(dist.latitude))))
        bbox = (dist.longitude - d_lon, dist.latitude - d_lat, dist.longitude + d_lon, dist.latitude + d_lat)

        counts: Dict[str, int] = {}
        if self.geography.available:
            if self.geography.has_rtree:
                rows = self.geography.conn.execute(
                    "SELECT gf.layer, COUNT(*) AS n "
                    "FROM geographic_features gf "
                    "JOIN geographic_features_rtree r ON gf.rowid = r.id "
                    "WHERE r.max_lon >= ? AND r.min_lon <= ? AND r.max_lat >= ? AND r.min_lat <= ? "
                    "GROUP BY gf.layer",
                    (bbox[0], bbox[2], bbox[1], bbox[3]),
                ).fetchall()
            else:
                rows = self.geography.conn.execute(
                    "SELECT layer, COUNT(*) AS n FROM geographic_features "
                    "WHERE NOT (max_lon < ? OR min_lon > ? OR max_lat < ? OR min_lat > ?) GROUP BY layer",
                    (bbox[0], bbox[2], bbox[1], bbox[3]),
                ).fetchall()
            counts = {r["layer"]: int(r["n"]) for r in rows}

        bldgs = counts.get("buildings", 0)
        roads = counts.get("roads", 0)
        landuse = counts.get("landuse", 0)
        pois = counts.get("pois", 0) + counts.get("pois_a", 0)
        transport = counts.get("transport", 0) + counts.get("transport_a", 0)
        places = counts.get("places", 0)

        geo_score = round(min(1.0, 0.35 + (0.25 if roads > 0 else 0.0) + (0.20 if places > 0 else 0.0) + (0.20 if bldgs > 0 else 0.0)), 3)
        bldg_score = round(min(1.0, bldgs / 400.0), 3) if bldgs > 0 else 0.0
        road_score = round(min(1.0, roads / 120.0), 3) if roads > 0 else 0.0
        lu_score = round(min(1.0, landuse / 15.0), 3) if landuse > 0 else 0.0
        comm_score = round(min(1.0, (pois + self._p8_by_dept.get(dist.department_code, 0) * 0.25) / 35.0), 3)
        pop_score = 0.85 if dist.approx_population > 0 else 0.20
        mob_score = round(min(1.0, 0.55 * road_score + 0.45 * min(1.0, transport / 5.0)), 3)
        emp_score = round(min(1.0, 0.45 * comm_score + 0.35 * pop_score + 0.20 * mob_score), 3)

        overall = round(
            0.20 * bldg_score
            + 0.20 * road_score
            + 0.12 * lu_score
            + 0.18 * comm_score
            + 0.15 * pop_score
            + 0.10 * mob_score
            + 0.05 * emp_score,
            3,
        )

        if overall >= 0.65:
            tier = CoverageTier.GOOD
        elif overall >= 0.40:
            tier = CoverageTier.PARTIAL
        elif overall >= 0.20:
            tier = CoverageTier.POOR
        else:
            tier = CoverageTier.INSUFFICIENT

        missing: List[str] = []
        if bldgs < 20:
            missing.append("Cobertura limitada o nula de huellas de edificios en OSM.")
        if roads < 15:
            missing.append("Red vial secundaria/local escasa en OSM.")
        if landuse == 0:
            missing.append("Sin polígonos de uso de suelo OSM.")
        if pois == 0:
            missing.append("Sin establecimientos comerciales/servicios mapeados en OSM.")
        if transport == 0:
            missing.append("Sin paradas o terminales de transporte público etiquetadas en OSM.")
        missing.append("Sin conteo censal origen-destino ni bolsas de empleo en vivo.")

        rec = TerritorialCoverageRecord(
            territory_id=dist.district_id,
            territory_name=dist.name,
            level="district",
            department_code=dist.department_code,
            department_name=dept.name if dept else dist.department_code,
            municipality_id=dist.municipality_id,
            municipality_name=mun.name if mun else dist.municipality_id,
            lat=dist.latitude,
            lon=dist.longitude,
            geographic_coverage_score=geo_score,
            building_data_coverage_score=bldg_score,
            road_data_coverage_score=road_score,
            land_use_coverage_score=lu_score,
            commercial_data_coverage_score=comm_score,
            population_data_coverage_score=pop_score,
            mobility_data_coverage_score=mob_score,
            employment_data_coverage_score=emp_score,
            overall_confidence=overall,
            coverage_tier=tier,
            feature_counts=counts,
            data_sources=["Geofabrik_OSM_El_Salvador (ODbL-1.0)", "D.L. 762 / CNR", "EHPM Priors"],
            last_update=_dt.date.today().isoformat(),
            missing_information=missing,
        )
        self._district_cache[dist.district_id] = rec
        return rec

    def get_district_coverage(self, district_id: str) -> Optional[TerritorialCoverageRecord]:
        dist = self._districts.get(district_id)
        if dist is None:
            return None
        return self._compute_district_record(dist)

    def get_national_summary(self, force_refresh: bool = False) -> NationalCoverageSummary:
        if self._summary_cache is not None and not force_refresh:
            return self._summary_cache

        district_records = [self._compute_district_record(d) for d in self._districts.values()]
        tier_counts = {t.value: 0 for t in CoverageTier}
        by_dept: Dict[str, List[TerritorialCoverageRecord]] = {}
        for rec in district_records:
            tier_counts[rec.coverage_tier.value] += 1
            by_dept.setdefault(rec.department_code, []).append(rec)

        dept_summaries: List[TerritorialCoverageRecord] = []
        for code, dept in self._departments.items():
            items = by_dept.get(code, [])
            if not items:
                continue
            n = len(items)
            avg_overall = round(sum(r.overall_confidence for r in items) / n, 3)
            if avg_overall >= 0.65:
                d_tier = CoverageTier.GOOD
            elif avg_overall >= 0.40:
                d_tier = CoverageTier.PARTIAL
            elif avg_overall >= 0.20:
                d_tier = CoverageTier.POOR
            else:
                d_tier = CoverageTier.INSUFFICIENT

            agg_counts: Dict[str, int] = {}
            for r in items:
                for k, v in r.feature_counts.items():
                    agg_counts[k] = agg_counts.get(k, 0) + v

            dept_summaries.append(
                TerritorialCoverageRecord(
                    territory_id=code,
                    territory_name=dept.name,
                    level="department",
                    department_code=code,
                    department_name=dept.name,
                    lat=dept.centroid_lat,
                    lon=dept.centroid_lon,
                    geographic_coverage_score=round(sum(r.geographic_coverage_score for r in items) / n, 3),
                    building_data_coverage_score=round(sum(r.building_data_coverage_score for r in items) / n, 3),
                    road_data_coverage_score=round(sum(r.road_data_coverage_score for r in items) / n, 3),
                    land_use_coverage_score=round(sum(r.land_use_coverage_score for r in items) / n, 3),
                    commercial_data_coverage_score=round(sum(r.commercial_data_coverage_score for r in items) / n, 3),
                    population_data_coverage_score=round(sum(r.population_data_coverage_score for r in items) / n, 3),
                    mobility_data_coverage_score=round(sum(r.mobility_data_coverage_score for r in items) / n, 3),
                    employment_data_coverage_score=round(sum(r.employment_data_coverage_score for r in items) / n, 3),
                    overall_confidence=avg_overall,
                    coverage_tier=d_tier,
                    feature_counts=agg_counts,
                    data_sources=["Geofabrik_OSM_El_Salvador (ODbL-1.0)", "D.L. 762 / CNR"],
                    last_update=_dt.date.today().isoformat(),
                    missing_information=[
                        f"{sum(1 for r in items if r.coverage_tier in (CoverageTier.POOR, CoverageTier.INSUFFICIENT))} de {n} distritos con cobertura baja o insuficiente."
                    ],
                )
            )

        summary = NationalCoverageSummary(
            total_departments=len(dept_summaries),
            total_districts=len(district_records),
            tier_counts=tier_counts,
            department_summaries=dept_summaries,
            district_records=district_records,
            generated_at=_dt.date.today().isoformat(),
        )
        self._summary_cache = summary
        return summary

    def export_coverage_geojson(self) -> Dict[str, Any]:
        """Return GeoJSON FeatureCollection for national coverage visualization."""
        summary = self.get_national_summary()
        features = []
        for rec in summary.district_records:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [rec.lon, rec.lat]},
                    "properties": {
                        "territory_id": rec.territory_id,
                        "name": rec.territory_name,
                        "department_code": rec.department_code,
                        "department_name": rec.department_name,
                        "coverage_tier": rec.coverage_tier.value,
                        "overall_confidence": rec.overall_confidence,
                        "buildings_count": rec.feature_counts.get("buildings", 0),
                        "roads_count": rec.feature_counts.get("roads", 0),
                        "pois_count": rec.feature_counts.get("pois", 0) + rec.feature_counts.get("pois_a", 0),
                    },
                }
            )
        return {
            "type": "FeatureCollection",
            "properties": {
                "total_departments": summary.total_departments,
                "total_districts": summary.total_districts,
                "tier_counts": summary.tier_counts,
            },
            "features": features,
        }
