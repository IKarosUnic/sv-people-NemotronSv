"""Explicit Offline-First National Data Sync & ETL Manager (Phase 1.20).

Provides user-invoked synchronization of official Salvadoran datasets and
Geofabrik OSM geography without ever coupling the simulation runtime to live
network availability.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from saltbor.census_intelligence.census_engine import (
    DEFAULT_OFFICIAL_CENSUS_DIR,
    NationalCensusDataIntegrationEngine,
)
from saltbor.census_intelligence.territorial_discovery import LocalTerritorialCache
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.datasets.salvadoran.territory_data import SALVADORAN_DISTRICTS_P8

from saltbor.data_sync.security import SafeHTTPFetcher


class NationalDataSyncManager:
    """Explicit ETL manager checking coverage gaps & synchronizing official files."""

    def __init__(
        self,
        census_engine: Optional[NationalCensusDataIntegrationEngine] = None,
        geography_path: Optional[Path] = None,
        cache: Optional[LocalTerritorialCache] = None,
        fetcher: Optional[SafeHTTPFetcher] = None,
    ) -> None:
        self.census_engine = census_engine or NationalCensusDataIntegrationEngine()
        self.geography_path = Path(geography_path) if geography_path else DEFAULT_GEO_SQLITE
        self._owns_cache = cache is None
        self.cache = cache or LocalTerritorialCache(":memory:")
        self.fetcher = fetcher or SafeHTTPFetcher()

    def close(self) -> None:
        if self._owns_cache:
            self.cache.close()

    def get_sync_status(self) -> Dict[str, Any]:
        """Inspect current freshness, verified district coverage, and missing registries."""
        datasets = self.census_engine.list_datasets()
        censo_bundle = self.census_engine._raw_bundles.get("censo_2024_onec_bcr", {})
        verified_districts = {
            d["district_id"] for d in censo_bundle.get("districts_verified", [])
        }
        # Also include any district-level Censo 2024 records imported dynamically
        for rec in self.census_engine._records.values():
            if rec.variable_name == "total_population" and rec.granularity.value == "DISTRICT":
                verified_districts.add(rec.geographic_unit_id)

        total_districts = len(SALVADORAN_DISTRICTS_P8)
        mined_count = len(self.census_engine.get_imported_mined_schools())
        minsal_count = len(self.census_engine.get_imported_minsal_facilities())

        geo_info: Dict[str, Any] = {"available": False, "path": str(self.geography_path)}
        if self.geography_path.exists():
            geo = IngestedGeography(self.geography_path)
            try:
                manifest = geo.manifest()
                geo_info = {
                    "available": geo.available,
                    "path": str(self.geography_path),
                    "has_rtree": geo.has_rtree,
                    "acquired_at": manifest.get("dataset", {}).get("acquired_at"),
                    "total_features": sum(
                        int(layer_meta.get("feature_count", 0))
                        for layer_meta in manifest.get("layers", {}).values()
                    ),
                    "layers_count": len(manifest.get("layers", {})),
                }
            finally:
                geo.close()

        cache_rows = self.cache._conn.execute("SELECT COUNT(*) FROM territorial_discovery_cache").fetchone()
        cache_count = int(cache_rows[0]) if cache_rows else 0

        gaps = []
        if len(verified_districts) < total_districts:
            gaps.append(
                f"Censo 2024 distrital oficial cargado para {len(verified_districts)}/{total_districts} distritos "
                f"({total_districts - len(verified_districts)} distritos usan SAE departamental)."
            )
        if mined_count == 0:
            gaps.append("Padrón nominal por centro escolar MINEDUCYT no cargado (matrícula y cupos locales UNAVAILABLE).")
        if minsal_count == 0:
            gaps.append("Padrón nominal de establecimientos MINSAL no cargado (capacidad médica local UNAVAILABLE).")

        return {
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "offline_ready": geo_info.get("available", False) and len(datasets) >= 3,
            "geography_sqlite": geo_info,
            "censo_2024_districts_verified": len(verified_districts),
            "censo_2024_districts_total": total_districts,
            "mined_schools_imported": mined_count,
            "minsal_facilities_imported": minsal_count,
            "enrichment_cache_entries": cache_count,
            "datasets": [d.model_dump(mode="json") for d in datasets],
            "pending_data_gaps": gaps,
        }

    def sync_source(
        self,
        source_kind: str,
        local_file: Optional[str | Path] = None,
        source_url: Optional[str] = None,
        allow_online: bool = False,
        force: bool = False,
        version: Optional[str] = None,
        persistence: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run explicit ETL sync from local file or allowlisted official URL."""
        kind = source_kind.strip().lower()
        ver = version or datetime.now(timezone.utc).strftime("%Y.%m.%d")
        pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if kind == "osm_geofabrik":
            if not allow_online and not local_file:
                return {
                    "success": False,
                    "source_kind": kind,
                    "reason": "Modo offline: indique allow_online=True para descargar Geofabrik o ejecute pipeline local.",
                }
            from saltbor.datasets.gis import pipeline as gis_pipeline

            dl_dir = gis_pipeline.DEFAULT_DOWNLOADS.parent
            if force and allow_online:
                for shp in gis_pipeline.DEFAULT_DOWNLOADS.glob("*.shp"):
                    shp.unlink(missing_ok=True)
            extracted = gis_pipeline.download_source(
                downloads_dir=dl_dir,
                url=source_url or gis_pipeline.GEOFABRIK_SHAPEFILE_ZIP,
            )
            manifest = gis_pipeline.ingest(downloads_dir=extracted, output_path=self.geography_path)
            return {
                "success": True,
                "source_kind": kind,
                "geography_path": str(self.geography_path),
                "total_features": sum(
                    int(m.get("feature_count", 0)) for m in manifest.get("layers", {}).values()
                ),
            }

        adapter_map = {
            "censo_2024_districts": ("censo_2024_onec", "censo_2024_districts_sync"),
            "ehpm": ("ehpm_onec", "ehpm_sync"),
            "mined_schools": ("mined_schools", "mined_schools_sync"),
            "minsal_health": ("minsal_health", "minsal_health_sync"),
            "institutional_custom": ("institutional_custom", "institutional_custom_sync"),
        }
        if kind not in adapter_map:
            raise ValueError(f"Tipo de fuente desconocido '{source_kind}'. Opciones: {sorted(list(adapter_map.keys()) + ['osm_geofabrik'])}")

        adapter_name, ds_id = adapter_map[kind]
        target_path: Optional[Path] = Path(local_file) if local_file else None
        temp_cleanup: Optional[Path] = None
        origin = "LOCAL_FILE_IMPORT"

        if target_path is None:
            if not source_url or not allow_online:
                return {
                    "success": False,
                    "source_kind": kind,
                    "reason": "Se requiere 'local_file' o ('source_url' con allow_online=True).",
                }
            raw, sha = self.fetcher.fetch_bytes(source_url, timeout_sec=20.0, max_bytes=20 * 1024 * 1024)
            ext = ".xlsx" if source_url.lower().endswith(".xlsx") else (".json" if source_url.lower().endswith((".json", ".geojson")) else ".csv")
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            tmp.write(raw)
            tmp.close()
            target_path = Path(tmp.name)
            temp_cleanup = target_path
            origin = "ONLINE_OFFICIAL_ALLOWLIST"

        try:
            suf = target_path.suffix.lower()
            if suf == ".csv":
                res = self.census_engine.import_csv(
                    target_path, adapter_name=adapter_name, dataset_id=ds_id, version=ver, published_at=pub_date
                )
            elif suf == ".xlsx":
                res = self.census_engine.import_xlsx(
                    target_path, adapter_name=adapter_name, dataset_id=ds_id, version=ver, published_at=pub_date
                )
            elif suf in (".json", ".geojson"):
                res = self.census_engine.import_json(
                    target_path, adapter_name=adapter_name, dataset_id=ds_id, version=ver, published_at=pub_date
                )
            else:
                raise ValueError(f"Formato no soportado '{suf}'. Use .csv, .xlsx, .json o .geojson.")

            if persistence is not None:
                meta = next((d for d in self.census_engine.list_datasets() if d.dataset_id == res.dataset_id), None)
                if meta is not None:
                    persistence.save_census_dataset_meta(meta)

            return {
                "success": res.success,
                "source_kind": kind,
                "origin": origin,
                "import_result": res.model_dump(mode="json"),
                "status_after": self.get_sync_status(),
            }
        finally:
            if temp_cleanup is not None:
                temp_cleanup.unlink(missing_ok=True)
