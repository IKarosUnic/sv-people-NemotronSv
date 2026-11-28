"""Deterministic Offline-First ETL Sync & Missing-Data Enrichment Tests (Phase 1.20)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from saltbor.census_intelligence.pipeline import TerritorialPreparationPipeline
from saltbor.census_intelligence.schemas import TerritorialSelectionInput
from saltbor.census_intelligence.territorial_discovery import LocalTerritorialCache
from saltbor.data_sync.enrichment import MissingDataEnrichmentTool
from saltbor.data_sync.etl_sync import NationalDataSyncManager
from saltbor.data_sync.security import DomainNotAllowedError, SafeHTTPFetcher


class _MockOSMEndpointHandler(BaseHTTPRequestHandler):
    """Local HTTP stub simulating Nominatim & Overpass APIs without touching external internet."""

    call_count = 0

    def do_GET(self) -> None:  # noqa: N802
        type(self).call_count += 1
        body = json.dumps([
            {
                "lat": "13.6769",
                "lon": "-89.2797",
                "display_name": "Urbanización Jardines del Volcán XYZ, Santa Tecla, La Libertad, El Salvador",
            }
        ]).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        type(self).call_count += 1
        length = int(self.headers.get("Content-Length", "0"))
        _ = self.rfile.read(length)
        body = json.dumps({
            "elements": [
                {
                    "type": "node",
                    "id": 990001,
                    "lat": 13.6775,
                    "lon": -89.2801,
                    "tags": {"amenity": "school", "name": "Centro Escolar Mock Overpass"},
                },
                {
                    "type": "node",
                    "id": 990002,
                    "lat": 13.6761,
                    "lon": -89.2785,
                    "tags": {"highway": "bus_stop", "name": "Parada Jardines Mock"},
                },
            ]
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return None


def _start_mock_server() -> tuple[HTTPServer, threading.Thread, int]:
    _MockOSMEndpointHandler.call_count = 0
    server = HTTPServer(("127.0.0.1", 0), _MockOSMEndpointHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def test_security_allowlist_blocks_untrusted_urls_and_plain_http() -> None:
    fetcher = SafeHTTPFetcher()
    with pytest.raises(DomainNotAllowedError):
        fetcher.validate_url("http://nominatim.openstreetmap.org/search?q=test")
    with pytest.raises(DomainNotAllowedError):
        fetcher.validate_url("https://untrusted-host.example.com/data.csv")
    with pytest.raises(DomainNotAllowedError):
        fetcher.validate_url("http://127.0.0.1:8080/test")
    assert fetcher.validate_url("https://overpass-api.de/api/interpreter")


def test_enrichment_tool_caches_nominatim_and_overpass_for_offline_reuse(tmp_path: Path) -> None:
    cache_db = str(tmp_path / "enrichment_cache.sqlite")
    server, thread, port = _start_mock_server()
    try:
        cache = LocalTerritorialCache(cache_db)
        tool = MissingDataEnrichmentTool(
            cache=cache,
            fetcher=SafeHTTPFetcher(allow_localhost_for_tests=True),
        )
        nom_url = f"http://127.0.0.1:{port}/nominatim"
        ovp_url = f"http://127.0.0.1:{port}/overpass"

        # 1. Offline by default -> UNAVAILABLE, zero HTTP calls
        res_off = tool.geocode_if_missing("Colonia Mock Inexistente 99", allow_online=False, nominatim_url=nom_url)
        assert res_off["origin"] == "UNAVAILABLE"
        assert res_off["found"] is False
        assert _MockOSMEndpointHandler.call_count == 0

        # 2. Explicit opt-in online -> fetches once & caches
        res_on = tool.geocode_if_missing("Colonia Mock Inexistente 99", allow_online=True, nominatim_url=nom_url)
        assert res_on["found"] is True
        assert res_on["origin"] == "RETRIEVED_ONLINE_CACHED"
        assert "ODbL" in res_on["attribution"]
        assert _MockOSMEndpointHandler.call_count == 1

        # 3. Sufficient local features skips Overpass even when online
        ovp_suf = tool.fetch_overpass_bbox_if_sparse(
            bbox=(-89.29, 13.67, -89.27, 13.69),
            sector="school",
            local_feature_count=5,
            min_threshold=2,
            allow_online=True,
            overpass_url=ovp_url,
        )
        assert ovp_suf["origin"] == "LOCAL_SUFFICIENT"
        assert _MockOSMEndpointHandler.call_count == 1

        # 4. Sparse local features + opt-in fetches Overpass & caches
        ovp_on = tool.fetch_overpass_bbox_if_sparse(
            bbox=(-89.29, 13.67, -89.27, 13.69),
            sector="school",
            local_feature_count=0,
            min_threshold=2,
            allow_online=True,
            overpass_url=ovp_url,
        )
        assert ovp_on["origin"] == "RETRIEVED_ONLINE_CACHED"
        assert ovp_on["features_count"] == 2
        assert _MockOSMEndpointHandler.call_count == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        cache.close()

    # 5. Reopen SQLite cache completely OFFLINE (server stopped!) -> 100% cache hit
    cache2 = LocalTerritorialCache(cache_db)
    try:
        tool2 = MissingDataEnrichmentTool(cache=cache2)
        nom_cached = tool2.geocode_if_missing("Colonia Mock Inexistente 99", allow_online=False)
        assert nom_cached["found"] is True
        assert nom_cached["cache_hit"] is True
        assert nom_cached["origin"] == "LOCAL_ENRICHMENT_CACHE"

        ovp_cached = tool2.fetch_overpass_bbox_if_sparse(
            bbox=(-89.29, 13.67, -89.27, 13.69),
            sector="school",
            local_feature_count=0,
            min_threshold=2,
            allow_online=False,
        )
        assert ovp_cached["cache_hit"] is True
        assert ovp_cached["origin"] == "LOCAL_ENRICHMENT_CACHE"
        assert len(ovp_cached["features"]) == 2
    finally:
        cache2.close()


def test_pipeline_offline_fail_then_opt_in_enrichment_then_offline_cache(tmp_path: Path) -> None:
    cache_db = str(tmp_path / "pipe_enr.sqlite")
    server, thread, port = _start_mock_server()
    try:
        pipe = TerritorialPreparationPipeline(cache_db_path=cache_db)
        pipe.enrichment_tool.NOMINATIM_URL = f"http://127.0.0.1:{port}/nominatim"
        pipe.enrichment_tool.OVERPASS_URL = f"http://127.0.0.1:{port}/overpass"
        pipe.enrichment_tool.fetcher = SafeHTTPFetcher(allow_localhost_for_tests=True)

        unknown_place = "Residencial Fantasma Que No Existe En DB 777"
        with pytest.raises(ValueError):
            pipe.prepare(TerritorialSelectionInput(query=unknown_place, allow_online_fallback=False))

        res_online = pipe.prepare(
            TerritorialSelectionInput(query=unknown_place, sector="school", allow_online_fallback=True),
            max_sample_households=80,
        )
        assert res_online.discovery.offline_mode is False
        assert res_online.discovery.primary_district_name
        assert res_online.enrichment_summary["nominatim"]["origin"] == "RETRIEVED_ONLINE_CACHED"
        assert res_online.enrichment_summary["allow_online_fallback"] is True
        pipe.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    # Re-open pipeline offline with same SQLite cache -> still resolves via cached Nominatim!
    pipe2 = TerritorialPreparationPipeline(cache_db_path=cache_db)
    try:
        res_off_cached = pipe2.prepare(
            TerritorialSelectionInput(query="Residencial Fantasma Que No Existe En DB 777", allow_online_fallback=False),
            max_sample_households=80,
        )
        assert res_off_cached.discovery.offline_mode is True
        assert res_off_cached.enrichment_summary["nominatim"]["origin"] == "LOCAL_ENRICHMENT_CACHE"
    finally:
        pipe2.close()


def test_national_data_sync_manager_local_csv_etl_and_pii_guard(tmp_path: Path) -> None:
    mgr = NationalDataSyncManager()
    try:
        status_before = mgr.get_sync_status()
        assert status_before["censo_2024_districts_total"] == 262
        before_verified = status_before["censo_2024_districts_verified"]
        assert isinstance(status_before["pending_data_gaps"], list)

        # Geofabrik without online permission degrades cleanly
        geo_off = mgr.sync_source("osm_geofabrik", allow_online=False)
        assert geo_off["success"] is False

        # Sync district census update CSV for Chalchuapa (not in default 18 sample if district-level)
        censo_csv = tmp_path / "censo_distritos.csv"
        censo_csv.write_text(
            "distrito,total_population,households,mean_household_size\n"
            "Chalchuapa,85200,24340,3.5\n"
            "Juayúa,27800,7940,3.5\n",
            encoding="utf-8",
        )
        sync_censo = mgr.sync_source("censo_2024_districts", local_file=censo_csv)
        assert sync_censo["success"] is True
        assert sync_censo["origin"] == "LOCAL_FILE_IMPORT"
        assert sync_censo["status_after"]["censo_2024_districts_verified"] >= before_verified

        # Sync MINED schools CSV
        mined_csv = tmp_path / "mined_centros.csv"
        mined_csv.write_text(
            "codigo_ce,nombre_centro,distrito,lat,lon,niveles,matricula,capacidad\n"
            "10999,Complejo Educativo Sincronizado,Santa Tecla,13.678,-89.281,parvularia;basica;media,420,500\n",
            encoding="utf-8",
        )
        sync_mined = mgr.sync_source("mined_schools", local_file=mined_csv)
        assert sync_mined["success"] is True
        assert sync_mined["status_after"]["mined_schools_imported"] >= 1

        # Reject PII dataset
        pii_csv = tmp_path / "pii_bad.csv"
        pii_csv.write_text("distrito,dui,total_population\nSanta Tecla,01234567-8,1000\n", encoding="utf-8")
        with pytest.raises(ValueError):
            mgr.sync_source("censo_2024_districts", local_file=pii_csv)
    finally:
        mgr.close()


def test_api_sync_endpoints_cli_and_studio_ui_toggle(tmp_path: Path) -> None:
    from saltbor.visualization.server import create_app

    app = create_app()
    client = TestClient(app)

    r_status = client.get("/api/territorial/sync/status")
    assert r_status.status_code == 200
    assert r_status.json()["censo_2024_districts_total"] == 262

    # Untrusted URL must return HTTP 400
    r_bad = client.post(
        "/api/territorial/sync/run",
        json={"source_kind": "censo_2024_districts", "source_url": "https://evil.example.org/x.csv", "allow_online": True},
    )
    assert r_bad.status_code == 400

    # Local file import succeeds via REST
    c_csv = tmp_path / "rest_minsal.csv"
    c_csv.write_text(
        "codigo,establecimiento,distrito,tipo,lat,lon,capacidad_diaria\n"
        "MINSAL-77,UCSF Sincronizada Test,Santa Tecla,ucsf,13.674,-89.279,180\n",
        encoding="utf-8",
    )
    r_ok = client.post(
        "/api/territorial/sync/run",
        json={"source_kind": "minsal_health", "local_file": str(c_csv)},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["success"] is True

    # /api/territorial/discover returns enrichment_summary
    r_disc = client.post(
        "/api/territorial/discover",
        json={"location_query": "Santa Tecla", "allow_online_fallback": False},
    )
    assert r_disc.status_code == 200
    assert "enrichment_summary" in r_disc.json()

    # CLI sync status works cleanly
    cli_proc = subprocess.run(
        [sys.executable, "-m", "saltbor.main", "sync", "status"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert cli_proc.returncode == 0
    assert '"censo_2024_districts_total": 262' in cli_proc.stdout

    # Studio HTML + JS include Phase 1.20 opt-in toggle
    repo_root = Path(__file__).resolve().parents[2]
    html = (repo_root / "saltbor" / "visualization" / "web" / "index.html").read_text(encoding="utf-8")
    js = (repo_root / "saltbor" / "visualization" / "web" / "modules" / "territorial_studio.js").read_text(encoding="utf-8")
    assert "studio-chk-online-fallback" in html
    assert "allow_online_fallback" in js
    assert "enrichment_summary" in js
