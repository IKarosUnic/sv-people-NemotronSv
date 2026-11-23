# SALTBOR Phase 1.17 — Mandatory Initial Architecture Audit & Migration Plan

**Date**: 2026-11-23  
**Scope**: Repository & runtime audit prior to Phase 1.17 implementation  
**Graphify Baseline**: `graphify-out/graph.json` (15,002 nodes, 42,756 edges, 438 communities; built at commit `d666b0c9`; current HEAD `bd89009`)  
**Rule**: `IMPLEMENTED`, `INTEGRATED`, `EXECUTABLE`, `VERIFIED`, and `EMPIRICALLY_CALIBRATED` are strictly separated and never conflated.

---

## 1. Audit Across All 14 Required Subsystems

### 1.1 Current `SimulationRunner` and Simulation Lifecycle
- **Files**: [`saltbor/simulation/runner.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/runner.py), [`saltbor/core/config.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/core/config.py), [`saltbor/visualization/controller.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/controller.py), [`saltbor/visualization/server.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/server.py).
- **Findings**:
  - `SimulationRunner.__init__` initializes a 500m × 500m synthetic town (`LocationRegistry.create_saltbor_map()`, `NavigationGraph.build_saltbor_graph()`) and registers over 35 engines (`tick_pipeline`, `orchestrator`, `extension`, `integrated_world`, `commerce_engine`, `labor_market`, `housing_engine`, `domain_engine`).
  - `SimulationConfig` lacks `territory_mode`, `territory_scope`, `territory_district_id`, `center_lat`, and `center_lon` fields.
  - `create_app()` in [`server.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/server.py#L62-L63) unconditionally creates `SimulationController(seed=seed, db_path=db_path)`, which eagerly calls `self._initialize_runner()` ([`controller.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/controller.py#L106)) and boots a 20-agent Historic Center simulation on server startup.
  - Meanwhile, Phase 1.16A [`SALTBORConversationalOrchestrator`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/orchestrator.py#L59) uses an independent two-stage lifecycle (`STAGE_A_PRELIMINARY` → `STAGE_B_SIMULATED`) with background jobs (`VALIDATING_SCENARIO` → `RESOLVING_LOCATION` → `PREPARING_POPULATION` → `RUNNING_SIMULATION` → `COLLECTING_EVIDENCE` → `ANALYZING_RESULTS` → `COMPLETED`), bypassing `SimulationRunner` entirely in favor of `TerritorialInterventionDesigner.execute_intervention_simulation()`.

### 1.2 Current Default Population and Population Distribution
- **Files**: [`saltbor/population/factory.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/population/factory.py), [`saltbor/datasets/mock_data.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/datasets/mock_data.py), [`saltbor/conversational/population_activation.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/population_activation.py).
- **Findings**:
  - Default `SimulationRunner` generates 20 agents via `PopulationFactory.create_population(try_nemotron=False)` ([`runner.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/runner.py#L1578-L1583)) with homes/workplaces anchored to Historic Center nodes (`casa_norte_1`, `plaza_central`, `mercado_central`).
  - `SimulationController.scale_active_population()` ([`controller.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/controller.py#L489-L493)) assigns all scaled agents to the 12 Historic Center anchor IDs.
  - `NationalPopulationActivationManager` (Phase 1.16A) generates district-level synthetic cohorts keyed by `uuid5("saltbor:{seed}:{district_id}:{idx}")`, preserving UIDs across activation/deactivation, **but** lacks:
    - Geographic placement of households onto real residential building footprints or residential land-use polygons;
    - A national `SpatialGridIndex` for fast coordinate-based household queries;
    - SQLite persistence of national residential/household assignments across process restarts (`population_manager` keeps `_human_meta` only in RAM).

### 1.3 Historic Center Initialization and Hardcoded Geographic Dependencies
- **Hardcoded References Identified**:
  1. [`saltbor/simulation/runner.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/runner.py#L525): `community_id="comunidad_centro_historico"`, lines `1178` (`San Salvador Centro`), `1197`/`1393`/`1407`/`1421` (`comunidad_centro_historico`), `1473` (`ADESCO y Administración Comunal Centro Histórico`), `1242-1260` (`mercado_central`, `comedor_dona_maria`).
  2. [`saltbor/simulation/integrated_world.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/integrated_world.py#L102-L103): `"Quebrada El Zapote / Calle Rubén Darío"` at `(13.6980, -89.1950)`; lines `188`/`193` fallback `(13.6978, -89.1915)` and `(13.6980, -89.1925)`.
  3. [`saltbor/world/gis/simulation_adapter.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/world/gis/simulation_adapter.py#L20-L48): `LOCATION_WGS84_ANCHORS` maps all 17 simulation anchor IDs exclusively to San Salvador Centro coordinates (`13.6935–13.7020`, `-89.2010–-89.1870`), and `get_anchor_point()` defaults unknown locations to `(13.6978, -89.1915, "Plaza Barrios")`.
  4. [`saltbor/datasets/gis/pipeline.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/datasets/gis/pipeline.py) & [`ingest_manifest.json`](file:///c:/GIT%20HUB/sv%20people/saltbor/datasets/gis/ingested/ingest_manifest.json#L35-L58): `buildings` layer in `geography.sqlite` has ONLY **989** features, clipped strictly to Historic Center bbox `[-89.202, 13.693, -89.186, 13.704]` (`is_partial: true`).
  5. [`saltbor/visualization/api.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/api.py#L1704): `zone_id: str = Query(default="san_salvador_centro")`, line `1905` (`community_id = "comunidad_centro_historico"`), line `5517` (`lat = 13.6989, lon = -89.1914`).
  6. [`saltbor/world/geographic/engine.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/world/geographic/engine.py#L135): `find_nearest_district()` falls back to `dist_san_salvador` if spatial index lookup returns empty.
  7. [`saltbor/conversational/territorial_context.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/territorial_context.py#L574-L583): Explicitly assumes building footprints outside `[-89.202, 13.693, -89.186, 13.704]` are absent/partial; line `652` grants `dist.district_id == "0614"` preferential P8 establishment matching.

### 1.4 Existing OSM Integration and Geographic Datasets
- **CRITICAL AUDIT FINDING**: On disk under `saltbor/datasets/gis/downloads/el_salvador_shp/`, the **complete nationwide Geofabrik El Salvador shapefile bundle** is already vendored, but `geography.sqlite` left the vast majority of built-environment and commercial features uningested:
  - `gis_osm_buildings_a_free_1`: **632,483** building polygons on disk vs **989** ingested (`0.16%` ingested, Historic Center only!).
  - `gis_osm_pois_a_free_1`: **11,400** polygon POIs on disk (848 schools, 715 restaurants, 401 convenience, 383 pharmacies, 345 doityourself, 312 fast_food, 275 clinics, 270 banks, 208 cafes, 177 supermarkets, 159 malls, 149 hotels, 116 marketplaces, 115 hospitals) vs **0** ingested!
  - `gis_osm_pois_free_1`: **8,011** point POIs on disk / **7,995** ingested, **but** `_AMENITY_CLASSES` in [`pipeline.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/datasets/gis/pipeline.py#L257-L283) only maps 25 classes, collapsing **4,363** commercial POIs (`convenience`, `supermarket`, `clothes`, `bakery`, `hairdresser`, `doityourself`, `shoe_shop`, `beauty_shop`, `hotel`) into `"other"`.
  - `gis_osm_pofw_a_free_1` (947), `gis_osm_pofw_free_1` (448), `gis_osm_transport_a_free_1` (119), `gis_osm_protected_areas_a_free_1` (220): on disk, **0** ingested.
  - `gis_osm_roads_free_1` (121,344), `gis_osm_landuse_a_free_1` (10,887), `gis_osm_places_free_1` (2,657), `gis_osm_water_a_free_1` (1,437), `gis_osm_waterways_free_1` (4,433), `gis_osm_adminareas_a_free_1` (474): ingested nationally.
- **Misclassification Bug Found**: In `pipeline.py` line `173`, `_BUILDING_CLASSES` maps `"yes": "residential"`, which could misclassify untyped OSM building footprints (`building=yes`) as residential instead of `"unknown"`.

### 1.5 Existing Building, Road, Land-Use and Facility Records
- `saltbor/datasets/salvadoran/territory_data.py`: 14 departments, 44 D.L. 762 municipalities, 262 districts with centroids, elevations, approx populations, urban core flags, and 474+ known cantones.
- `saltbor/datasets/salvadoran/establishments_data.py`: Curated P8 real establishments (`SALVADORAN_ESTABLISHMENTS_P8`) weighted heavily toward San Salvador and departmental capitals; insufficient standalone coverage for municipalities like Soyapango without OSM POI + POI-polygon ingestion.
- `saltbor/world/gis/engine.py` (`GISEngine`): Loads GeoJSON files ONLY for `san_salvador_centro/` (`buildings.geojson`, `streets.geojson`, `parks.geojson`, `poi.geojson`, etc.).

### 1.6 Existing Geographic Database and Spatial Indexes
- `geography.sqlite` (`180 MB` currently) has B-tree indexes (`idx_features_layer`, `idx_features_layer_lat_lon`, `idx_features_class`, `idx_features_bbox`, `idx_features_name`), **NO SQLite R-Tree virtual table** (`geographic_features_rtree` missing), even though SQLite `3.50.4` in Python 3.14.5 natively supports `USING rtree(...)`.
- `SpatialGridIndex` (`saltbor/world/geographic/spatial_index.py`) works in RAM for 262 districts and curated P8 points, and `Shapely STRtree` is used only for the Historic Center GeoJSONs in `GISEngine`.

### 1.7 Existing Map Implementation and Location Selection
- `saltbor/visualization/web/index.html`, `app.js`, and `modules/territorial_studio.js`:
  - MapLibre GL JS (offline vendored) renders a single reusable map instance (`window.initOrResizeGIS25D`).
  - Phase 1.16B already made Studio (`view-studio`) the default active view with `mapMode = "hidden"` and optional drawer (`hidden` / `side` / `expanded` / `full`), plus location search autocomplete (`/api/studio/territory/search`) and optional point click.
  - However, when `view-world` or the optional map opens, `/api/gis/viewport` works nationally for roads/landuse, while buildings outside `san_salvador_centro` return 0 polygons because `geography.sqlite` only ingested 989 Historic Center buildings. Moreover, `territorial_studio.js` lacks overlays for catchment hulls, commercial establishments by category, employment concentrations, and national coverage status.

### 1.8 Existing Synthetic Human Identities, Households and Persistence
- `saltbor/persistence/schema.py` (`_SCHEMA_VERSION = 5`): stores `humans`, `memories_*`, `relationships`, `credit_loans`, `businesses`, `institutions`, `communities`, `simulation_state` for `SimulationRunner`.
- `saltbor/conversational/persistence.py`: stores `conv_sessions`, `conv_turns`, `conv_scenarios`, `conv_executions`, `conv_checkpoints` in `saltbor_studio.db` (SQLite WAL).
- **Gap**: No persistent tables exist for Phase 1.17 `territorial_scenarios` lifecycle states, partitioned A–G `territorial_evidence_packages`, `territorial_coverage_cache`, or `persistent_population_assignments` across national districts.

### 1.9 Existing LOD and Population Activation Mechanisms
- `CognitiveLODManager` (`saltbor/population/lod.py`) and `MultilevelPopulationManager` (`saltbor/population/multilevel/population_manager.py`) are implemented and integrated in `NationalPopulationActivationManager` (`saltbor/conversational/population_activation.py`), supporting hydration/dehydration between LOD 0–3 without losing UIDs or wealth.
- `AdaptiveLODBudgetController` (`saltbor/simulation/tick_pipeline.py`) operates inside `SimulationRunner.step()`.

### 1.10 Existing Mobility, Employment, Commerce and Economic Engines
- `CommercialEngine` (`saltbor/economy/commerce/commercial_engine.py`) & `BusinessRegistry` (`saltbor/economy/business/enterprise.py`): implement bounded-rationality visits, conversions, inventory, and operating P&L.
- `LaborMarketEngine` (`saltbor/economy/labor/market.py`): implements contracts, wages, and vacancies.
- `VerifiableEconomicLedger` (`saltbor/territory/economic_ledger.py`): enforces double-entry accounting (`$0.00` discrepancy).
- `OSMRoadNetwork` (`saltbor/world/geographic/osm_router.py`): implements Dijkstra travel-time routing on OSM line geometry, **but** is NOT yet wired into `NationalTerritorialContextEngine` or adaptive catchment / mobility flow engines (currently `NationalTerritorialContextEngine` uses straight-line `radius_km` bbox + simple segment counts!).
- **Disconnected / Display-Only**: `RealGeographicEngine` + `GISEngine` (`san_salvador_centro` GeoJSONs) serve `/api/world` and `/api/gis/*` endpoints mostly for visual display rather than driving on-demand national simulation scenarios. No engine yet models 10-role human mobility flows, time-of-day diurnal heterogeneity across districts, adaptive 8-method catchments, building-level classification origins, unverified commercial buildings vs confirmed businesses, or 5-tier employment opportunity analysis.

### 1.11 Phase 1.14 Connected Territorial Scenarios
- `saltbor/territory/connected_scenarios.py` and `cross_domain.py`: implemented, executable, and verified on a fixed 2-household Cantón San José Las Flores cohort. Must remain preserved for backward compatibility.

### 1.12 Phase 1.15 Gemini/Ollama Provider Architecture
- `saltbor/ai/` (`AIModelRouter`, `RemoteGeminiProvider`, `OllamaProvider`, `OfflineDeterministicProvider`, `AIComputeBudgetManager`, `AIPrivacyGuard`): implemented and executable with graceful fallback to local Ollama and Offline Deterministic mode.

### 1.13 Phase 1.16 Conversational Backend and Frontend
- `saltbor/conversational/` and `saltbor/visualization/routers/conversational_studio_router.py` + `saltbor/visualization/web/modules/territorial_studio.js`: functional Stage A / Stage B conversational studio (`48/48` baseline tests passing in `tests/test_conversational/` + `tests/test_gis/`), **but** Stage A only checks `territorial_context` + coarse population counts, lacks national building/commercial/catchment/mobility/employment engines, misses follow-up cues (`"ahora analiza"`, `"flujo de personas"`, `"oportunidades de empleo"`), and cannot construct full `OnDemandTerritorialSimulationEngine` lifecycles or A–G evidence packages.

### 1.14 Existing Experiment, Evidence and Provenance Systems
- `SyntheticPopulationEvidenceEngine` (`saltbor/conversational/evidence_engine.py`): collects flat `EvidenceIndicator` lists from `TerritorialInterventionDesigner`, but does NOT explicitly partition evidence into the 7 Phase 1.17 epistemic tiers **A–G** (`Real observed`, `Official statistical`, `Geographic derivations`, `Synthetic population`, `Simulated outcomes`, `AI interpretations`, `Recommendations`).
- `ExternalHistoricalValidator` (`saltbor/scientific/external_validation.py`): validates national series backtesting (BCR, ONEC/EHPM, MINED).

---

## 2. Engine Status Matrix (Strictly Non-Conflated)

| Subsystem / Engine | IMPLEMENTED | INTEGRATED | EXECUTABLE | VERIFIED | EMPIRICALLY_CALIBRATED | Audit Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `SimulationRunner` (Core Loop) | YES | YES | YES | YES | PARTIAL | Defaults to Historic Center when `SimulationConfig()` has no territorial scope; must remain preserved as benchmark. |
| `IngestedGeography` (`geography.sqlite`) | YES | YES | YES | YES | YES (OSM) | Currently missing R-Tree index, missing `pois_a`/`pofw`/`protected_areas`, and `buildings` clipped to 989 Historic Center footprints. |
| `GISEngine` (`san_salvador_centro` GeoJSON) | YES | PARTIAL | YES | YES | YES (Pilot) | Pilot-only; display-centric for `/api/gis/layer/*`; does not cover all 14 departments. |
| `OSMRoadNetwork` (`osm_router.py`) | YES | NO | YES | YES | PARTIAL | Implemented Dijkstra over OSM roads, **disconnected** from `NationalTerritorialContextEngine` and catchment/mobility analysis. |
| `NationalTerritorialContextEngine` | YES | YES | YES | YES | PARTIAL | Resolves 14 depts / 44 munis / 262 districts / 474+ cantones, but constrained by fixed `radius_km` bbox and partial `buildings` DB. |
| `NationalPopulationActivationManager` | YES | YES | YES | YES | PARTIAL | Selective LOD 0–3 hydration works in RAM; lacks building-level spatial assignment and SQLite persistence. |
| `CommercialEngine` + `BusinessRegistry` | YES | YES | YES | YES | PARTIAL | Bounded-rationality commerce + double-entry ledger works, **but** lacks national OSM POI commercial intelligence & unverified building separation. |
| `LaborMarketEngine` | YES | YES | YES | YES | NO | Wage/contract mechanics work; lacks territorial job-vacancy vs known-employer vs sectoral estimate separation. |
| `TerritoryCatalogService` (`territory_catalog.py`) | YES | YES | YES | YES | YES (D.L. 762) | Authoritative 262-district registry + Tobler hazard heuristics; lacks per-district OSM building/commercial/road/mobility coverage matrix. |
| `ConnectedTerritorialScenarios` (P1.14) | YES | YES | YES | YES | PARTIAL | Validated on San José Las Flores 2-family scenario; backward-compatible. |
| `AIModelRouter` (Gemini/Ollama/Offline, P1.15) | YES | YES | YES | YES | N/A | Functional BYOK Gemini + Ollama + Offline deterministic failover with `AIPrivacyGuard`. |
| `SALTBORConversationalOrchestrator` (P1.16) | YES | YES | YES | YES | PARTIAL | Functional chat-first workflow; needs `OnDemandTerritorialSimulationEngine`, richer follow-ups, and A–G evidence partitioning. |
| `Phase 1.17 Territorial Intelligence Engines` | NO (Target) | NO | NO | NO | NO | To be implemented under `saltbor/territorial_intelligence/` in Step 3. |

---

## 3. Specific Gaps & Anomalies Detected

1. **Disconnection**: `OSMRoadNetwork` is unused by conversational/territorial catchment calculations.
2. **Display-Only Geography**: `RealGeographicEngine.get_volcanoes()/get_lakes()` and `GISEngine` (`san_salvador_centro`) primarily render UI overlays rather than feeding dynamic nationwide simulations.
3. **Population Without Real Built-Environment Assignment**: `PopulationFactory` assigns agents to `"casa_norte_1"` / `"plaza_central"` strings; `NationalPopulationActivationManager` registers `district_id` without spatial coordinates or residential footprint links.
4. **Partial Buildings DB Masquerading as Missing National Coverage**: 632,483 OSM buildings sit unused in `el_salvador_shp/gis_osm_buildings_a_free_1.shp` while `geography.sqlite` only ingested 989 Historic Center polygons.
5. **Missing R-Tree Spatial Index**: All bbox queries scan B-tree indexes instead of an SQLite R-Tree (`geographic_features_rtree`).
6. **Hardcoded Historic Center Default Server Startup**: `create_app()` in `server.py` creates an active 20-agent Historic Center `SimulationRunner` at boot instead of `IDLE` location-independent readiness.
7. **Mock vs Real Clarity**: `PopulationFactory` falls back to `MockDataGenerator` (`sal_names`), and `TerritorialContext` lacks explicit A–G epistemic tiering.

---

## 4. Migration & Backward-Compatibility Plan

1. **Preserve Historic Center as Explicit Benchmark**:
   - Add `territory_mode: Literal["on_demand", "historic_center_benchmark"]` and explicit location fields to `SimulationConfig`.
   - Keep `SimulationRunner(SimulationConfig())` and `SimulationController(...)` direct constructors backward-compatible for all existing Phase 0.1–1.16 unit/integration/regression tests.
   - Change `create_app()` (`server.py`) so default server startup uses `auto_initialize_benchmark=False`, booting into `IDLE` on-demand mode (`active_territory = None`, Historic Center NOT active by default), while adding `SimulationRunner.create_historic_center_benchmark()` and `POST /api/territorial/benchmark/historic-center` to run the Historic Center explicitly.
2. **Additive SQLite Schema Upgrades**:
   - Rebuild derived `geography.sqlite` from the vendored Geofabrik extract with all 15 layers, corrected non-fabricating building/POI classes, and `geographic_features_rtree` R-Tree virtual table.
   - Add Phase 1.17 tables (`territorial_scenarios`, `territorial_evidence_packages`, `territorial_coverage_cache`, `persistent_population_assignments`) idempotently via `CREATE TABLE IF NOT EXISTS` in `ConversationalPersistenceStore`.
3. **Reuse Existing APIs & Studio Frontend**:
   - Keep `/api/status`, `/api/world`, `/api/gis/*`, `/api/studio/*`, `/api/territory/*`, and `/api/ai/*` intact.
   - Add modular `/api/territorial/*` router and enrich `/api/studio/chat` + `/api/studio/execute` + `territorial_studio.js` without breaking existing DOM IDs, starter prompts, or single-MapLibre reuse.
