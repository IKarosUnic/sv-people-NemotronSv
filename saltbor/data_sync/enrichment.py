"""On-Demand Missing-Data Enrichment Tool with Mandatory SQLite Cache (Phase 1.20).

Executes ONLY when local data has verified gaps AND the user explicitly opts in
(`allow_online=True`). Every retrieved item is cached locally in SQLite so all
subsequent queries remain 100% offline, deterministic, and ODbL/provenance-tagged.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from saltbor.census_intelligence.territorial_discovery import LocalTerritorialCache, OSM_ODBL_ATTRIBUTION
from saltbor.data_sync.security import SafeHTTPFetcher

_SECTOR_OVERPASS_FILTERS: Dict[str, List[str]] = {
    "school": ['["amenity"~"school|kindergarten|college|university"]'],
    "education": ['["amenity"~"school|kindergarten|college|university"]'],
    "health": ['["amenity"~"hospital|clinic|doctors|pharmacy"]'],
    "clinic": ['["amenity"~"hospital|clinic|doctors|pharmacy"]'],
    "market": ['["shop"~"."]', '["amenity"~"marketplace|restaurant|fast_food|bank"]'],
    "road": ['["highway"~"bus_stop|primary|secondary|tertiary"]', '["public_transport"~"platform|station"]'],
    "general": ['["amenity"~"school|hospital|clinic|pharmacy|marketplace"]', '["building"~"residential|house|apartments"]'],
}


class MissingDataEnrichmentTool:
    """Targeted online fallback tool with mandatory local SQLite caching."""

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    def __init__(
        self,
        cache: Optional[LocalTerritorialCache] = None,
        fetcher: Optional[SafeHTTPFetcher] = None,
    ) -> None:
        self._owns_cache = cache is None
        self.cache = cache or LocalTerritorialCache(":memory:")
        self.fetcher = fetcher or SafeHTTPFetcher()
        self._rate_lock = threading.Lock()
        self._last_request_ts = 0.0

    def close(self) -> None:
        if self._owns_cache:
            self.cache.close()

    def _respect_rate_limit(self, min_interval_sec: float = 1.05) -> None:
        with self._rate_lock:
            wait = min_interval_sec - (time.time() - self._last_request_ts)
            if wait > 0:
                time.sleep(wait)
            self._last_request_ts = time.time()

    def geocode_if_missing(
        self,
        query: str,
        allow_online: bool = False,
        nominatim_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check local cache first; only query Nominatim if allow_online=True."""
        norm_q = (query or "").strip().lower()
        key = f"enr_nom:{hashlib.sha256(norm_q.encode('utf-8')).hexdigest()[:20]}"
        cached = self.cache.get(key)
        if cached is not None:
            return {**cached, "cache_hit": True, "origin": "LOCAL_ENRICHMENT_CACHE"}

        if not allow_online or not norm_q:
            return {"found": False, "cache_hit": False, "origin": "UNAVAILABLE", "reason": "Offline o consulta no habilitada."}

        base_url = nominatim_url or self.NOMINATIM_URL
        try:
            self._respect_rate_limit(1.05)
            params = urllib.parse.urlencode({"q": f"{query}, El Salvador", "format": "json", "limit": 3})
            raw, sha = self.fetcher.fetch_bytes(f"{base_url}?{params}", timeout_sec=8.0, max_bytes=512_000)
            data = json.loads(raw.decode("utf-8"))
            if isinstance(data, list) and data:
                result = {
                    "found": True,
                    "lat": float(data[0]["lat"]),
                    "lon": float(data[0]["lon"]),
                    "display_name": data[0].get("display_name", query),
                    "attribution": OSM_ODBL_ATTRIBUTION,
                    "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "sha256": sha,
                    "cache_hit": False,
                    "origin": "RETRIEVED_ONLINE_CACHED",
                }
                self.cache.put(key, "nominatim_enrichment", result, ttl_sec=30 * 86400.0)
                return result
        except Exception as exc:
            return {"found": False, "cache_hit": False, "origin": "UNAVAILABLE", "reason": str(exc)}
        return {"found": False, "cache_hit": False, "origin": "UNAVAILABLE", "reason": "Sin coincidencias en Nominatim."}

    def fetch_overpass_bbox_if_sparse(
        self,
        bbox: Tuple[float, float, float, float],
        sector: str = "general",
        local_feature_count: int = 0,
        min_threshold: int = 2,
        allow_online: bool = False,
        overpass_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch missing OSM features via Overpass ONLY when local_feature_count < min_threshold."""
        min_lon, min_lat, max_lon, max_lat = [round(float(v), 4) for v in bbox]
        sec_key = (sector or "general").lower()
        key = f"enr_ovp:{sec_key}:{min_lon}:{min_lat}:{max_lon}:{max_lat}"

        # Always check cache first (even if offline, cached past enrichment works offline!)
        cached = self.cache.get(key)
        if cached is not None:
            return {**cached, "cache_hit": True, "origin": "LOCAL_ENRICHMENT_CACHE"}

        if local_feature_count >= min_threshold:
            return {
                "triggered": False,
                "cache_hit": False,
                "origin": "LOCAL_SUFFICIENT",
                "features": [],
            }

        if not allow_online:
            return {
                "triggered": False,
                "cache_hit": False,
                "origin": "UNAVAILABLE",
                "reason": "Datos locales escasos y respaldo online deshabilitado (allow_online=False).",
                "features": [],
            }

        filters = _SECTOR_OVERPASS_FILTERS.get(sec_key, _SECTOR_OVERPASS_FILTERS["general"])
        bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"
        clauses = "\n".join(
            f"  node{flt}({bbox_str});\n  way{flt}({bbox_str});"
            for flt in filters
        )
        ql = f"[out:json][timeout:15];\n(\n{clauses}\n);\nout center 200;"

        target_url = overpass_url or self.OVERPASS_URL
        try:
            self._respect_rate_limit(1.0)
            body = urllib.parse.urlencode({"data": ql}).encode("utf-8")
            raw, sha = self.fetcher.fetch_bytes(target_url, data=body, timeout_sec=15.0, max_bytes=2 * 1024 * 1024)
            payload = json.loads(raw.decode("utf-8"))
            elements = payload.get("elements", [])
            normalized: List[Dict[str, Any]] = []
            captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

            for el in elements:
                tags = el.get("tags") or {}
                lat = el.get("lat") or (el.get("center") or {}).get("lat")
                lon = el.get("lon") or (el.get("center") or {}).get("lon")
                if lat is None or lon is None:
                    continue
                amenity = (tags.get("amenity") or "").lower()
                shop = (tags.get("shop") or "").lower()
                pt_tag = (tags.get("public_transport") or "").lower()
                hw = (tags.get("highway") or "").lower()

                if amenity in ("school", "kindergarten", "college", "university"):
                    domain, subtype = "EDUCATION", amenity
                elif amenity in ("hospital", "clinic", "doctors", "pharmacy"):
                    domain, subtype = "HEALTH", amenity
                elif shop or amenity in ("marketplace", "restaurant", "fast_food", "bank"):
                    domain, subtype = "ECONOMY", shop or amenity
                elif hw == "bus_stop" or pt_tag in ("platform", "station"):
                    domain, subtype = "INFRASTRUCTURE", "bus_stop"
                else:
                    continue

                normalized.append({
                    "entity_id": f"overpass:{el.get('type', 'node')}:{el.get('id')}",
                    "name": (tags.get("name") or "").strip() or f"{subtype} (Overpass)",
                    "domain": domain,
                    "subtype": subtype,
                    "lat": round(float(lat), 6),
                    "lon": round(float(lon), 6),
                    "source": "OpenStreetMap Overpass (Cached ODbL-1.0)",
                    "updated_at": captured_at,
                    "tags": tags,
                })

            result = {
                "triggered": True,
                "cache_hit": False,
                "origin": "RETRIEVED_ONLINE_CACHED",
                "attribution": OSM_ODBL_ATTRIBUTION,
                "captured_at": captured_at,
                "sha256": sha,
                "features_count": len(normalized),
                "features": normalized,
            }
            self.cache.put(key, "overpass_enrichment", result, ttl_sec=14 * 86400.0)
            return result
        except Exception as exc:
            return {
                "triggered": True,
                "cache_hit": False,
                "origin": "UNAVAILABLE",
                "reason": f"Fallo al consultar Overpass (degradado seguro a offline): {exc}",
                "features": [],
            }
