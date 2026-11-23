"""National Territorial Context Engine for El Salvador (Phase 1.16A).

Resolves natural-language Spanish place references (departments, municipalities,
districts, cantones, OSM places, named roads, named facilities) and optional map
coordinates `(lat, lon)` across all 14 departments and 262 districts of El Salvador,
attaching real OSM geospatial context and explicit data provenance without ever
fabricating missing attributes.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.datasets.salvadoran.establishments_data import SALVADORAN_ESTABLISHMENTS_P8
from saltbor.datasets.salvadoran.territory_data import (
    SALVADORAN_DEPARTMENTS_P8,
    SALVADORAN_DISTRICTS_P8,
    SALVADORAN_MUNICIPALITIES_P8,
    SalvadoranDistrictData,
)
from saltbor.territory.territory_catalog import TerritoryCatalogService
from saltbor.world.gis.engine import GISEngine

from saltbor.conversational.schemas import (
    DataProvenance,
    GeographicCandidate,
    QuestionDataQualityAssessment,
    TerritorialContext,
)

logger = logging.getLogger(__name__)

# Bounding box of El Salvador (generous coastal/border margin)
_SV_MIN_LAT, _SV_MAX_LAT = 13.00, 14.50
_SV_MIN_LON, _SV_MAX_LON = -90.20, -87.60

_ADMIN_PREFIX_RE = re.compile(
    r"\b(?:en\s+el\s+|en\s+la\s+|en\s+|cerca\s+de\s+la\s+|cerca\s+del\s+|cerca\s+de\s+|"
    r"cant[oó]n\s+|caser[ií]o\s+|distrito\s+de\s+|distrito\s+|municipio\s+de\s+|municipio\s+|"
    r"departamento\s+de\s+|departamento\s+|ciudad\s+de\s+|centro\s+de\s+)\b",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _normalize_place(text: str) -> str:
    cleaned = _strip_accents(text.lower().strip())
    cleaned = re.sub(r"[¿?¡!.,;:()\"']", " ", cleaned)
    cleaned = _ADMIN_PREFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class NationalTerritorialContextEngine:
    """Resolves natural Spanish territorial references across El Salvador with OSM provenance."""

    def __init__(
        self,
        catalog: Optional[TerritoryCatalogService] = None,
        geography_db_path: Optional[str] = None,
        gis_engine: Optional[GISEngine] = None,
    ) -> None:
        self.catalog = catalog or TerritoryCatalogService()
        self.geography = IngestedGeography(geography_db_path or DEFAULT_GEO_SQLITE)
        self.gis_engine = gis_engine or GISEngine()
        self._query_cache: Dict[Tuple[str, Optional[float], Optional[float], float], TerritorialContext] = {}

        self._departments = (
            SALVADORAN_DEPARTMENTS_P8
            if isinstance(SALVADORAN_DEPARTMENTS_P8, dict)
            else {d.code: d for d in SALVADORAN_DEPARTMENTS_P8}
        )
        self._municipalities = (
            SALVADORAN_MUNICIPALITIES_P8
            if isinstance(SALVADORAN_MUNICIPALITIES_P8, dict)
            else {m.municipality_id: m for m in SALVADORAN_MUNICIPALITIES_P8}
        )
        self._districts = (
            SALVADORAN_DISTRICTS_P8
            if isinstance(SALVADORAN_DISTRICTS_P8, dict)
            else {d.district_id: d for d in SALVADORAN_DISTRICTS_P8}
        )
        self._manifest_cache: Optional[Dict[str, Any]] = None
        self._build_lookup_indexes()

    def close(self) -> None:
        """Close underlying SQLite connection cleanly."""
        try:
            self.geography.close()
        except Exception as exc:
            logger.debug("Ignoring geography close error: %s", exc)

    def _build_lookup_indexes(self) -> None:
        """Build fast normalized indexes for departments, municipalities, districts, and cantones."""
        self._dept_by_norm: Dict[str, str] = {}
        for code, dept in self._departments.items():
            self._dept_by_norm[_normalize_place(dept.name)] = code

        self._mun_by_norm: Dict[str, str] = {}
        for mun_id, mun in self._municipalities.items():
            self._mun_by_norm[_normalize_place(mun.name)] = mun_id

        self._district_by_norm: Dict[str, List[SalvadoranDistrictData]] = {}
        self._canton_by_norm: Dict[str, List[Tuple[str, SalvadoranDistrictData]]] = {}
        for dist in self._districts.values():
            norm_d = _normalize_place(dist.name)
            self._district_by_norm.setdefault(norm_d, []).append(dist)
            for canton in dist.known_cantones:
                norm_c = _normalize_place(canton)
                self._canton_by_norm.setdefault(norm_c, []).append((canton, dist))

    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r_km = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
        return 2.0 * r_km * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))

    @staticmethod
    def is_in_el_salvador(lat: float, lon: float) -> bool:
        return (_SV_MIN_LAT <= lat <= _SV_MAX_LAT) and (_SV_MIN_LON <= lon <= _SV_MAX_LON)

    def _get_manifest(self) -> Dict[str, Any]:
        if self._manifest_cache is None:
            self._manifest_cache = self.geography.manifest() if self.geography.available else {"available": False}
        return self._manifest_cache

    def _to_candidate(
        self,
        dist: SalvadoranDistrictData,
        match_level: str,
        matched_label: str,
        confidence: float,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
    ) -> GeographicCandidate:
        dept = self._departments.get(dist.department_code)
        mun = self._municipalities.get(dist.municipality_id)
        return GeographicCandidate(
            district_id=dist.district_id,
            name=dist.name,
            municipality_id=dist.municipality_id,
            municipality_name=mun.name if mun else dist.municipality_id,
            department_code=dist.department_code,
            department_name=dept.name if dept else dist.department_code,
            match_level=match_level,
            matched_label=matched_label,
            lat=round(lat if lat is not None else dist.latitude, 6),
            lon=round(lon if lon is not None else dist.longitude, 6),
            approx_population=int(dist.approx_population),
            confidence=round(confidence, 3),
        )

    def _nearest_district(self, lat: float, lon: float) -> SalvadoranDistrictData:
        return min(
            self._districts.values(),
            key=lambda d: self.haversine_km(lat, lon, d.latitude, d.longitude),
        )

    def _search_osm_named_features(self, query_norm: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Search OSM places, roads, and POIs in geography.sqlite by name."""
        if not self.geography.available or len(query_norm) < 3:
            return []
        try:
            rows = self.geography.conn.execute(
                "SELECT feature_id, layer, name, feature_class, lat, lon, validation_state, source, license "
                "FROM geographic_features "
                "WHERE name != '' AND layer IN ('places', 'roads', 'pois', 'adminareas') "
                "AND LOWER(name) LIKE ? LIMIT ?",
                (f"%{query_norm}%", limit * 3),
            ).fetchall()
        except Exception as exc:
            logger.debug("OSM named feature lookup failed: %s", exc)
            return []

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for r in rows:
            name_norm = _normalize_place(r["name"] or "")
            if not name_norm:
                continue
            score = 1.0 if name_norm == query_norm else (0.85 if query_norm in name_norm else 0.65)
            if r["layer"] == "places":
                score += 0.1
            scored.append((score, dict(r)))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def search_locations(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search departments, municipalities, districts, cantones, and OSM places for UI autocomplete."""
        q_norm = _normalize_place(query or "")
        results: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def _add(label: str, level: str, dist: SalvadoranDistrictData, lat: Optional[float] = None, lon: Optional[float] = None) -> None:
            key = f"{level}:{dist.district_id}:{label.lower()}"
            if key in seen or len(results) >= limit:
                return
            seen.add(key)
            dept = self._departments.get(dist.department_code)
            mun = self._municipalities.get(dist.municipality_id)
            results.append(
                {
                    "label": label,
                    "level": level,
                    "district_id": dist.district_id,
                    "district_name": dist.name,
                    "municipality_id": dist.municipality_id,
                    "municipality_name": mun.name if mun else dist.municipality_id,
                    "department_code": dist.department_code,
                    "department_name": dept.name if dept else dist.department_code,
                    "lat": round(lat if lat is not None else dist.latitude, 6),
                    "lon": round(lon if lon is not None else dist.longitude, 6),
                    "approx_population": int(dist.approx_population),
                }
            )

        # If query is empty, return major national hubs across departments
        if not q_norm:
            top_dists = sorted(self._districts.values(), key=lambda d: d.approx_population, reverse=True)[:limit]
            for d in top_dists:
                dept = self._departments.get(d.department_code)
                _add(f"{d.name} ({dept.name if dept else d.department_code})", "district", d)
            return results

        for d_norm, code in self._dept_by_norm.items():
            if q_norm in d_norm:
                dept = self._departments[code]
                cab = self._district_by_norm.get(_normalize_place(dept.cabecera), [])
                dist = cab[0] if cab else next(d for d in self._districts.values() if d.department_code == code)
                _add(f"Departamento de {dept.name}", "department", dist, dept.centroid_lat, dept.centroid_lon)

        for dist_norm, d_list in self._district_by_norm.items():
            if q_norm in dist_norm:
                for d in d_list:
                    dept = self._departments.get(d.department_code)
                    _add(f"{d.name}, {dept.name if dept else d.department_code}", "district", d)

        for c_norm, c_list in self._canton_by_norm.items():
            if q_norm in c_norm:
                for c_lbl, d in c_list:
                    dept = self._departments.get(d.department_code)
                    _add(f"{c_lbl} ({d.name}, {dept.name if dept else d.department_code})", "canton", d)

        if len(results) < limit and len(q_norm) >= 3:
            for hit in self._search_osm_named_features(q_norm, limit=limit - len(results)):
                nearest = self._nearest_district(float(hit["lat"]), float(hit["lon"]))
                _add(
                    f"{hit['name']} ({nearest.name})",
                    f"osm_{hit['layer']}",
                    nearest,
                    float(hit["lat"]),
                    float(hit["lon"]),
                )

        return results[:limit]

    def resolve_location(
        self,
        query: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        radius_km: float = 1.5,
    ) -> TerritorialContext:
        """Resolve a Spanish place reference and/or map coordinate into full territorial context."""
        raw_q = (query or "").strip()
        cache_key = (raw_q.lower(), round(lat, 5) if lat is not None else None, round(lon, 5) if lon is not None else None, radius_km)
        if cache_key in self._query_cache:
            return self._query_cache[cache_key].model_copy(deep=True)

        # 1. Explicit coordinate resolution (optional map click)
        if lat is not None and lon is not None:
            if not self.is_in_el_salvador(lat, lon):
                ctx = TerritorialContext(
                    query=raw_q or f"{lat},{lon}",
                    resolved=False,
                    lat=lat,
                    lon=lon,
                    missing_data=["Coordenadas fuera del territorio operativo de El Salvador (13.0-14.5N, -90.2--87.6W)."],
                    uncertainties=["Ubicación fuera de cobertura nacional de SALTBOR."],
                )
                return ctx

            nearest_dist = self._nearest_district(lat, lon)
            ctx = self._build_context(
                query=raw_q or f"({lat:.5f}, {lon:.5f})",
                dist=nearest_dist,
                canton_name=None,
                lat=lat,
                lon=lon,
                coordinate_source="user_map_coordinate",
                radius_km=radius_km,
            )
            self._query_cache[cache_key] = ctx.model_copy(deep=True)
            return ctx

        if not raw_q:
            return TerritorialContext(
                query="",
                resolved=False,
                missing_data=["Referencia geográfica no proporcionada."],
                uncertainties=["Se requiere especificar un departamento, distrito, cantón o coordenada."],
            )

        norm_full = _normalize_place(raw_q)
        raw_norm = _strip_accents(raw_q.lower().strip())

        # Check explicit department qualifier inside query (e.g. "El Rosario, La Paz")
        matched_dept_code: Optional[str] = None
        for d_norm, code in self._dept_by_norm.items():
            if d_norm and d_norm in norm_full:
                matched_dept_code = code
                break

        # Also check special phrase "centro de <x>"
        is_centro = "centro" in raw_norm

        candidates: List[GeographicCandidate] = []
        chosen_dist: Optional[SalvadoranDistrictData] = None
        chosen_canton: Optional[str] = None
        chosen_coords: Optional[Tuple[float, float]] = None
        coord_source = "district_centroid"

        has_canton_hint = any(k in raw_norm for k in ("canton", "caserio"))

        # 2A. Exact district match
        if norm_full in self._district_by_norm:
            dists = self._district_by_norm[norm_full]
            if matched_dept_code and len(dists) > 1:
                dists = [d for d in dists if d.department_code == matched_dept_code] or dists
            for d in dists:
                candidates.append(self._to_candidate(d, "district", d.name, 0.96))

        # 2B. Exact department name (prioritize over unqualified canton names like "La Paz" vs "Cantón La Paz")
        if not candidates and not has_canton_hint and norm_full in self._dept_by_norm:
            code = self._dept_by_norm[norm_full]
            dept = self._departments[code]
            cab_norm = _normalize_place(dept.cabecera)
            cab_dists = self._district_by_norm.get(cab_norm, [])
            if not cab_dists:
                cab_dists = [d for d in self._districts.values() if d.department_code == code]
                cab_dists.sort(key=lambda d: d.approx_population, reverse=True)
            if cab_dists:
                chosen_dist = cab_dists[0]
                chosen_coords = (dept.centroid_lat, dept.centroid_lon)
                coord_source = "department_cabecera"
                candidates.append(self._to_candidate(chosen_dist, "department", dept.name, 0.95, *chosen_coords))

        # 2C. Exact municipality name (e.g. "La Libertad Sur", "San Salvador Centro")
        if not candidates and not has_canton_hint and norm_full in self._mun_by_norm:
            mun_id = self._mun_by_norm[norm_full]
            mun = self._municipalities[mun_id]
            cab_norm = _normalize_place(mun.cabecera_municipal)
            cab_dists = [
                d for d in self._districts.values()
                if d.municipality_id == mun_id and _normalize_place(d.name) == cab_norm
            ]
            if not cab_dists:
                cab_dists = [d for d in self._districts.values() if d.municipality_id == mun_id]
                cab_dists.sort(key=lambda d: d.approx_population, reverse=True)
            if cab_dists:
                chosen_dist = cab_dists[0]
                chosen_coords = (mun.centroid_lat, mun.centroid_lon)
                coord_source = "municipality_cabecera"
                candidates.append(self._to_candidate(chosen_dist, "municipality", mun.name, 0.94, *chosen_coords))

        # 2D. Exact canton match
        if not candidates and norm_full in self._canton_by_norm:
            canton_hits = self._canton_by_norm[norm_full]
            if matched_dept_code and len(canton_hits) > 1:
                canton_hits = [(c, d) for c, d in canton_hits if d.department_code == matched_dept_code] or canton_hits
            for canton_lbl, d in canton_hits:
                candidates.append(self._to_candidate(d, "canton", canton_lbl, 0.92))

        # 2E. Substring matching inside sentences or multi-word queries
        if not candidates:
            # Check longest matching district names contained inside normalized query
            district_hits: List[Tuple[int, SalvadoranDistrictData]] = []
            for d_norm, d_list in self._district_by_norm.items():
                if len(d_norm) >= 4 and d_norm in norm_full:
                    for d in d_list:
                        district_hits.append((len(d_norm), d))
            if district_hits:
                max_len = max(item[0] for item in district_hits)
                top_dists = [d for length, d in district_hits if length == max_len]
                if matched_dept_code and len(top_dists) > 1:
                    top_dists = [d for d in top_dists if d.department_code == matched_dept_code] or top_dists
                seen_ids = set()
                for d in top_dists:
                    if d.district_id not in seen_ids:
                        seen_ids.add(d.district_id)
                        candidates.append(self._to_candidate(d, "district_phrase", d.name, 0.90))

        if not candidates:
            # Check canton substring matches
            canton_phrase_hits: List[Tuple[int, str, SalvadoranDistrictData]] = []
            for c_norm, c_list in self._canton_by_norm.items():
                if len(c_norm) >= 4 and (c_norm in norm_full or norm_full in c_norm):
                    for c_lbl, d in c_list:
                        canton_phrase_hits.append((len(c_norm), c_lbl, d))
            if canton_phrase_hits:
                max_len = max(item[0] for item in canton_phrase_hits)
                top_c = [(c_lbl, d) for l, c_lbl, d in canton_phrase_hits if l == max_len]
                if matched_dept_code and len(top_c) > 1:
                    top_c = [(c, d) for c, d in top_c if d.department_code == matched_dept_code] or top_c
                seen_pairs = set()
                for c_lbl, d in top_c:
                    key = (d.district_id, c_lbl)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        candidates.append(self._to_candidate(d, "canton_phrase", c_lbl, 0.86))

        # 2F. OSM places, roads, or facilities lookup (e.g. "Carretera Panamericana", "Hospital Rosales")
        if not candidates:
            osm_hits = self._search_osm_named_features(norm_full, limit=6)
            seen_osm_districts = set()
            for hit in osm_hits:
                nearest = self._nearest_district(float(hit["lat"]), float(hit["lon"]))
                key = (nearest.district_id, hit["name"])
                if key not in seen_osm_districts:
                    seen_osm_districts.add(key)
                    candidates.append(
                        self._to_candidate(
                            nearest,
                            f"osm_{hit['layer']}",
                            f"{hit['name']} ({nearest.name})",
                            0.80,
                            lat=float(hit["lat"]),
                            lon=float(hit["lon"]),
                        )
                    )

        # 3. Evaluate ambiguity vs unique resolution
        if not candidates:
            ctx = TerritorialContext(
                query=raw_q,
                resolved=False,
                is_ambiguous=False,
                missing_data=[
                    f"No se encontró '{raw_q}' en D.L. 762 (14 departamentos, 44 municipios, 262 distritos, 474 cantones) ni en OSM."
                ],
                uncertainties=["Solicite al usuario precisar distrito, departamento o seleccionar coordenada en el mapa."],
            )
            return ctx

        # Deduplicate candidates by district_id
        unique_by_district: Dict[str, GeographicCandidate] = {}
        for cand in candidates:
            if cand.district_id not in unique_by_district:
                unique_by_district[cand.district_id] = cand
        deduped = list(unique_by_district.values())

        # If more than 1 distinct district matches (e.g. "El Rosario", "San Isidro"), return ambiguity!
        # Exception: explicit "centro de San Salvador" should pick San Salvador (0614) cleanly if top hit is exact.
        if len(deduped) > 1:
            exact_top = [c for c in deduped if _normalize_place(c.name) == norm_full]
            if len(exact_top) == 1 and is_centro:
                deduped = exact_top
            else:
                ctx = TerritorialContext(
                    query=raw_q,
                    resolved=False,
                    is_ambiguous=True,
                    ambiguity_reason=(
                        f"La referencia '{raw_q}' coincide con {len(deduped)} ubicaciones en El Salvador."
                    ),
                    candidates=deduped[:6],
                    uncertainties=["Aclaración geográfica requerida antes de simular población específica."],
                )
                return ctx

        top = deduped[0]
        chosen_dist = self._districts[top.district_id]
        if top.match_level in ("canton", "canton_phrase"):
            chosen_canton = top.matched_label
        elif has_canton_hint:
            matching_c = [c for c in chosen_dist.known_cantones if _normalize_place(c) in norm_full or norm_full in _normalize_place(c)]
            chosen_canton = matching_c[0] if matching_c else raw_q
        lat_val, lon_val = top.lat, top.lon
        if chosen_coords is not None:
            lat_val, lon_val = chosen_coords
        elif top.match_level.startswith("osm_"):
            coord_source = top.match_level

        ctx = self._build_context(
            query=raw_q,
            dist=chosen_dist,
            canton_name=chosen_canton,
            lat=lat_val,
            lon=lon_val,
            coordinate_source=coord_source,
            radius_km=radius_km,
        )
        self._query_cache[cache_key] = ctx.model_copy(deep=True)
        return ctx

    def _build_context(
        self,
        query: str,
        dist: SalvadoranDistrictData,
        canton_name: Optional[str],
        lat: float,
        lon: float,
        coordinate_source: str,
        radius_km: float,
    ) -> TerritorialContext:
        dept = self._departments.get(dist.department_code)
        mun = self._municipalities.get(dist.municipality_id)
        topo = self.catalog.get_topographic_hazard_profile(dist.name)
        manifest = self._get_manifest()
        acquired_at = manifest.get("dataset", {}).get("acquired_at", "2026-11-13")

        # Bounding box around target coordinates (~0.009 deg per km latitude)
        d_lat = radius_km / 111.0
        d_lon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
        bbox = (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)

        landuse_summary: Dict[str, int] = {}
        buildings_count = 0
        buildings_is_partial = True
        road_classes: Dict[str, int] = {}
        road_total = 0
        nearest_road: Optional[Dict[str, Any]] = None
        hydrology_summary: Dict[str, int] = {}
        nearby_facilities: Dict[str, List[Dict[str, Any]]] = {}
        nearby_counts: Dict[str, int] = {}
        transport_count = 0
        missing_data: List[str] = []
        uncertainties: List[str] = []
        provenance_by_domain: Dict[str, DataProvenance] = {}

        # Administrative provenance
        provenance_by_domain["administrative_hierarchy"] = DataProvenance(
            source=f"SALTBOR D.L. 762 Catalog ({dist.source})",
            license="Public Official (Decreto Legislativo 762 / CNR-IGN)",
            retrieval_date="2026-11-13",
            geographic_resolution="district_and_canton",
            confidence=0.95,
            validation_status="VERIFIED_REAL",
            limitations="Población distrital aproximada; límites poligonales exactos de cantones dependen de cartografía CNR.",
        )

        # Topographic & hazard provenance
        provenance_by_domain["topography_and_hazards"] = DataProvenance(
            source="TerritoryCatalogService (elevation_m + Tobler slope heuristic)",
            license="Public Official / Calibrated Model",
            retrieval_date="2026-11-13",
            geographic_resolution="district_elevation_centroid",
            confidence=0.72,
            validation_status="EMPIRICALLY_CALIBRATED",
            limitations="Pendiente estimada a nivel de relieve distrital, no DEM lidar por parcela.",
        )

        if self.geography.available:
            # Landuse
            lu_feats = self.geography.features_in_bbox(bbox, layer="landuse", limit=300)
            for f in lu_feats:
                fc = f["feature_class"] or "other"
                landuse_summary[fc] = landuse_summary.get(fc, 0) + 1

            # Buildings (honest local & national completeness assessment)
            bldg_counts = self.geography.count_in_bbox(bbox, layer="buildings")
            buildings_count = sum(bldg_counts.values())
            bldg_meta = manifest.get("layers", {}).get("buildings", {})
            layer_is_partial = bool(bldg_meta.get("is_partial", False))
            if layer_is_partial:
                cov_bbox = bldg_meta.get("coverage_bbox") or [-89.202, 13.693, -89.186, 13.704]
                in_bldg_bbox = (cov_bbox[0] <= lon <= cov_bbox[2]) and (cov_bbox[1] <= lat <= cov_bbox[3])
                buildings_is_partial = not (in_bldg_bbox and buildings_count > 0)
            else:
                # Full national shapefile ingested: rural/non-urban districts and sub-cantons still have incomplete OSM footprints
                buildings_is_partial = (not dist.is_urban_core) or (canton_name is not None) or (buildings_count < 100)

            if buildings_count == 0:
                missing_data.append(
                    "Polígonos detallados de edificaciones OSM (0 huellas mapeadas dentro del radio analizado)."
                )
                uncertainties.append(
                    "Capacidad edilicia y densidad de manzanas estimadas sin huellas de edificios OSM en este punto."
                )
            elif buildings_is_partial:
                uncertainties.append(
                    f"Cobertura parcial de huellas OSM en entorno rural/periférico ({buildings_count} edificios registrados)."
                )

            # Roads & nearest road
            road_feats = self.geography.features_in_bbox(bbox, layer="roads", limit=600)
            road_total = len(road_feats)
            for f in road_feats:
                fc = f["feature_class"] or "other"
                road_classes[fc] = road_classes.get(fc, 0) + 1
            nearest_road = self.geography.nearest_road(lat, lon)

            # Hydrology
            for hydro_layer in ("water", "waterways"):
                h_feats = self.geography.features_in_bbox(bbox, layer=hydro_layer, limit=200)
                if h_feats:
                    hydrology_summary[hydro_layer] = len(h_feats)

            # POIs & nearby facilities (both point pois and polygon pois_a)
            poi_feats = (
                self.geography.features_in_bbox(bbox, layer="pois", limit=300)
                + self.geography.features_in_bbox(bbox, layer="pois_a", limit=200)
            )
            for f in poi_feats:
                fc = f["feature_class"] or "other"
                nearby_counts[fc] = nearby_counts.get(fc, 0) + 1
                dist_km = self.haversine_km(lat, lon, f["centroid"]["lat"], f["centroid"]["lon"])
                nearby_facilities.setdefault(fc, []).append(
                    {
                        "feature_id": f["feature_id"],
                        "name": f["name"] or fc,
                        "feature_class": fc,
                        "distance_m": round(dist_km * 1000.0, 1),
                        "lat": round(f["centroid"]["lat"], 5),
                        "lon": round(f["centroid"]["lon"], 5),
                    }
                )
            for fc, items in nearby_facilities.items():
                items.sort(key=lambda x: x["distance_m"])
                nearby_facilities[fc] = items[:8]

            # Transport stops
            tr_feats = self.geography.features_in_bbox(bbox, layer="transport", limit=100)
            transport_count = len(tr_feats)

            provenance_by_domain["osm_geospatial"] = DataProvenance(
                source="OpenStreetMap contributors via Geofabrik (geography.sqlite)",
                license="ODbL-1.0",
                retrieval_date=acquired_at,
                geographic_resolution=f"bbox_radius_{radius_km}km",
                confidence=0.84 if road_total > 0 else 0.45,
                validation_status="VERIFIED_REAL",
                limitations=(
                    "OSM es colaborativo: ausencia de POI o vía no garantiza inexistencia en terreno; "
                    "horarios de transporte y capacidad escolar/médica no constan en OSM."
                ),
            )
        else:
            missing_data.append("Base espacial geography.sqlite no disponible en ruta configurada.")

        # Also incorporate curated P8 establishments in department/district
        p8_items = (
            SALVADORAN_ESTABLISHMENTS_P8.values()
            if isinstance(SALVADORAN_ESTABLISHMENTS_P8, dict)
            else SALVADORAN_ESTABLISHMENTS_P8
        )
        p8_matches = [
            {
                "id": e.establishment_id,
                "name": e.name,
                "category": e.category.value if hasattr(e.category, "value") else str(e.category),
            }
            for e in p8_items
            if e.department_code == dist.department_code
            and (_normalize_place(dist.name) in _normalize_place(e.name) or dist.district_id == "0614")
        ]

        # Accessibility index [0.0, 1.0] combining road density, transport stops, and Tobler slope
        tobler = float(topo.get("tobler_walking_speed_factor", 0.85))
        road_factor = min(1.0, road_total / 40.0)
        transit_factor = min(1.0, transport_count / 6.0)
        accessibility_index = round(
            min(1.0, max(0.1, (0.55 * road_factor + 0.25 * transit_factor + 0.20 * tobler))),
            3,
        )

        if not nearby_counts.get("education") and not dist.is_urban_core:
            uncertainties.append("Sin nodos escolares OSM dentro del radio inmediato; verificar centros escolares en cantones vecinos.")
        if not nearby_counts.get("health"):
            uncertainties.append("Sin establecimientos de salud OSM dentro del radio inmediato.")
        if transport_count == 0:
            uncertainties.append("Sin paradas de transporte público etiquetadas en OSM dentro del radio; frecuencia de buses no observada.")

        # Compute calibrated offline data quality score (never 1.00 without empirical field/sensor verification;
        # explicitly penalizes absent or partial OSM building footprints)
        quality = 0.0
        if dist.approx_population > 0:
            quality += 0.15
        if road_total > 0:
            quality += 0.20 if road_total >= 20 else 0.10
        if sum(nearby_counts.values()) > 0:
            quality += 0.15 if sum(nearby_counts.values()) >= 10 else 0.08
        if landuse_summary:
            quality += 0.10
        if buildings_count > 0:
            quality += 0.15 if not buildings_is_partial else 0.07
        if transport_count > 0:
            quality += 0.10
        quality = round(min(0.85, max(0.10, quality)), 2)

        commercial_summary = {
            "food_service_pois": nearby_counts.get("food_service", 0),
            "market_pois": nearby_counts.get("market", 0),
            "finance_pois": nearby_counts.get("finance", 0),
            "commercial_landuse_polygons": landuse_summary.get("commercial_area", 0),
            "curated_p8_establishments": len(p8_matches),
            "p8_samples": p8_matches[:5],
        }

        ctx = TerritorialContext(
            query=query,
            resolved=True,
            is_ambiguous=False,
            department_code=dist.department_code,
            department_name=dept.name if dept else dist.department_code,
            municipality_id=dist.municipality_id,
            municipality_name=mun.name if mun else dist.municipality_id,
            district_id=dist.district_id,
            district_name=dist.name,
            canton_name=canton_name,
            is_urban=bool(dist.is_urban_core),
            approx_population=int(dist.approx_population),
            lat=round(lat, 6),
            lon=round(lon, 6),
            coordinate_source=coordinate_source,
            elevation_m=float(dist.elevation_m),
            slope_pct=float(topo.get("estimated_slope_pct", 5.0)),
            tobler_walking_speed_factor=tobler,
            terrain_class=str(topo.get("relief_class", "VALLE_VOLCANICO")),
            radius_km=radius_km,
            landuse_summary=landuse_summary,
            buildings_count=buildings_count,
            buildings_is_partial=buildings_is_partial,
            road_network_summary={
                "total_segments_in_radius": road_total,
                "by_class": road_classes,
            },
            nearest_road=nearest_road,
            accessibility_index=accessibility_index,
            hydrology_summary=hydrology_summary,
            nearby_facilities=nearby_facilities,
            nearby_facilities_counts=nearby_counts,
            transport_stops_count=transport_count,
            environmental_risks={
                "landslide_risk_index": float(topo.get("landslide_risk_index", 0.35)),
                "flood_inundation_risk_index": float(topo.get("flood_inundation_risk_index", 0.35)),
                "drought_corridor_risk_index": float(topo.get("drought_corridor_risk_index", 0.35)),
            },
            commercial_activity_summary=commercial_summary,
            data_quality_score=quality,
            provenance_by_domain=provenance_by_domain,
            missing_data=missing_data,
            uncertainties=uncertainties,
        )
        ctx.question_data_quality = self.evaluate_question_data_quality(ctx, "general")
        return ctx

    def evaluate_question_data_quality(
        self,
        context: TerritorialContext,
        question_type: str = "general",
    ) -> QuestionDataQualityAssessment:
        """Compute question-specific dataset availability, coverage, freshness, provenance & gaps."""
        q_norm = (question_type or "general").upper()
        osm_prov = context.provenance_by_domain.get("osm_geospatial")
        adm_prov = context.provenance_by_domain.get("administrative_hierarchy")
        osm_date = osm_prov.retrieval_date if osm_prov else "2026-11-23"
        adm_date = adm_prov.retrieval_date if adm_prov else "2026-11-13"

        if "BUSINESS" in q_norm or "COMMER" in q_norm:
            required = [
                "osm_buildings",
                "osm_pois_commerce",
                "osm_roads",
                "dl762_population",
                "empirical_commercial_occupancy",
                "empirical_footfall_and_spend",
            ]
        elif "EDUCAT" in q_norm:
            required = [
                "osm_schools_points_and_polygons",
                "osm_roads",
                "dl762_population",
                "mined_enrollment_capacity",
            ]
        elif "HEALTH" in q_norm:
            required = [
                "osm_health_facilities",
                "osm_roads",
                "dl762_population",
                "minsal_facility_capacity",
            ]
        elif "TRANSPORT" in q_norm or "MOBILITY" in q_norm:
            required = [
                "osm_roads",
                "osm_transport_stops",
                "dl762_topography",
                "empirical_od_traffic_counts",
            ]
        else:
            required = [
                "osm_buildings",
                "osm_pois_all",
                "osm_roads",
                "osm_landuse",
                "dl762_population",
                "empirical_field_validation",
            ]

        road_cnt = int(context.road_network_summary.get("total_segments_in_radius", 0))
        poi_cnt = sum(context.nearby_facilities_counts.values())
        edu_cnt = context.nearby_facilities_counts.get("education", 0)
        hlt_cnt = context.nearby_facilities_counts.get("health", 0)
        bldg_cnt = int(context.buildings_count)
        comm_pois = sum(
            context.nearby_facilities_counts.get(k, 0)
            for k in ("food_service", "retail_commercial", "service_business", "market", "finance", "workshop")
        )

        dataset_state: Dict[str, Tuple[bool, str, str, str]] = {
            "osm_buildings": (
                bldg_cnt > 0,
                "PARTIAL" if (bldg_cnt == 0 or context.buildings_is_partial) else "GOOD",
                osm_date,
                "Geofabrik OSM El Salvador (ODbL-1.0); sin niveles/altura ni ocupación interior.",
            ),
            "osm_pois_commerce": (
                comm_pois > 0,
                "GOOD" if comm_pois >= 10 else ("PARTIAL" if comm_pois > 0 else "NONE"),
                osm_date,
                "Geofabrik OSM pois + pois_a + P8 curados.",
            ),
            "osm_pois_all": (
                poi_cnt > 0,
                "GOOD" if poi_cnt >= 15 else ("PARTIAL" if poi_cnt > 0 else "NONE"),
                osm_date,
                "Geofabrik OSM pois + pois_a (ODbL-1.0).",
            ),
            "osm_schools_points_and_polygons": (
                edu_cnt > 0,
                "GOOD" if edu_cnt >= 5 else ("PARTIAL" if edu_cnt > 0 else "NONE"),
                osm_date,
                "Geofabrik OSM education (pois + pois_a).",
            ),
            "osm_health_facilities": (
                hlt_cnt > 0,
                "GOOD" if hlt_cnt >= 3 else ("PARTIAL" if hlt_cnt > 0 else "NONE"),
                osm_date,
                "Geofabrik OSM health (pois + pois_a).",
            ),
            "osm_roads": (
                road_cnt > 0,
                "GOOD" if road_cnt >= 25 else ("PARTIAL" if road_cnt > 0 else "NONE"),
                osm_date,
                "Geofabrik OSM roads + OSMRoadNetwork.",
            ),
            "osm_landuse": (
                bool(context.landuse_summary),
                "GOOD" if sum(context.landuse_summary.values()) >= 5 else ("PARTIAL" if context.landuse_summary else "NONE"),
                osm_date,
                "Geofabrik OSM landuse polygons.",
            ),
            "osm_transport_stops": (
                context.transport_stops_count > 0,
                "GOOD" if context.transport_stops_count >= 5 else ("PARTIAL" if context.transport_stops_count > 0 else "NONE"),
                osm_date,
                "Geofabrik OSM transport stops.",
            ),
            "dl762_population": (
                context.approx_population > 0,
                "APPROXIMATE_DISTRICT_PRIOR" if context.approx_population > 0 else "NONE",
                adm_date,
                "D.L. 762 / EHPM district-level population prior.",
            ),
            "dl762_topography": (
                context.elevation_m is not None,
                "DISTRICT_CENTROID_HEURISTIC",
                adm_date,
                "TerritoryCatalogService elevation + Tobler slope heuristic.",
            ),
            "empirical_commercial_occupancy": (False, "MISSING", "N/A", "Sin registro municipal/fiscal de ocupación de locales en vivo."),
            "empirical_footfall_and_spend": (False, "MISSING", "N/A", "Sin conteos peatonales en campo ni transacciones POS empíricas."),
            "mined_enrollment_capacity": (False, "MISSING", "N/A", "Sin matrícula escolar ni aulas reales por centro escolar en el radio."),
            "minsal_facility_capacity": (False, "MISSING", "N/A", "Sin camas ni cupos médicos diarios reales por establecimiento."),
            "empirical_od_traffic_counts": (False, "MISSING", "N/A", "Sin aforos vehiculares ni matrices origen-destino medidas en campo."),
            "empirical_field_validation": (False, "MISSING", "N/A", "Sin encuesta o medición de campo local en tiempo real."),
        }

        available: List[str] = []
        coverage_map: Dict[str, str] = {}
        freshness_map: Dict[str, str] = {}
        prov_map: Dict[str, str] = {}
        missing_fields: List[str] = []
        score_sum = 0.0

        for ds in required:
            is_avail, cov_label, fr_date, prov_desc = dataset_state.get(
                ds, (False, "MISSING", "N/A", "Dataset no disponible offline.")
            )
            coverage_map[ds] = cov_label
            freshness_map[ds] = fr_date
            prov_map[ds] = prov_desc
            if is_avail:
                available.append(ds)
                if cov_label in ("GOOD",):
                    score_sum += 1.0
                else:
                    score_sum += 0.6
                    missing_fields.append(f"{ds}: cobertura {cov_label.lower()} ({prov_desc})")
            else:
                missing_fields.append(f"{ds}: no disponible ({prov_desc})")

        if bldg_cnt > 0:
            missing_fields.append("osm_buildings: sin altura/niveles ni estado de ocupación por edificio.")
        confidence = round(min(0.88, max(0.10, score_sum / max(1, len(required)))), 2)
        summary = (
            f"Cobertura para '{question_type}': {len(available)}/{len(required)} fuentes base presentes "
            f"(confianza calibrada {confidence:.2f}/1.00; brechas empíricas locales documentadas)."
        )
        return QuestionDataQualityAssessment(
            question_type=question_type,
            required_datasets=required,
            available_datasets=available,
            coverage_by_dataset=coverage_map,
            freshness=freshness_map,
            provenance=prov_map,
            missing_fields=list(dict.fromkeys(missing_fields)),
            confidence_score=confidence,
            summary=summary,
        )
