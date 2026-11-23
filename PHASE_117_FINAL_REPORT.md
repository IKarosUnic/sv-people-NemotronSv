# SALTBOR Phase 1.17 — National Territorial Intelligence, Built-Environment Understanding & On-Demand Spatial Simulation Final Report

**Date**: 2026-11-23  
**Phase**: 1.17 (Nationwide Location-Independent Territorial Intelligence & On-Demand Spatial Simulation)  
**Hardware Target**: AMD Ryzen 7 8700G / 32 GB RAM / Radeon 780M (Python 3.14.5, Windows 11)  

---

## 1. Executive Summary

SALTBOR has completed its architectural transition from a testing platform centered by default on the San Salvador Historic Center into a nationwide, location-independent territorial intelligence and on-demand simulation platform spanning all **14 departments**, **44 municipalities**, and **262 districts** of El Salvador.

- **Historic Center Decoupled as Default, Preserved as Benchmark**: FastAPI server startup via [`create_app()`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/server.py) now boots cleanly into `IDLE_ON_DEMAND` (`active_population = 0`, `historic_center_active = False`). Historic Center remains explicitly invocable via [`SimulationRunner.create_historic_center_benchmark()`](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/runner.py), [`SimulationController.activate_historic_center_benchmark()`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/controller.py), and `POST /api/territorial/benchmark/historic-center`.
- **Full National GIS Rebuild & SQLite R-Tree Index**: [`pipeline.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/datasets/gis/pipeline.py) now ingests **795,877** verified OSM features across **15 layers** (including **632,482** building polygons, **121,344** road segments, **8,011** point POIs, **11,400** polygon POIs in `pois_a`, **10,887** landuse polygons, places of worship, transport polygons, and protected areas) with SQLite R-Tree (`geographic_features_rtree`), returning 500-building spatial queries in **7.22–12.71 ms**.
- **Phase 1.17 Intelligence Package (`saltbor/territorial_intelligence/`)**: Implemented and verified building/land-use intelligence, commercial vs. unverified-building differentiation, adaptive 8-method/5-scale catchments wired to `OSMRoadNetwork`, 10-role heterogeneous human mobility flows, 5-tier employment analysis & shocks (`$0.00` ledger conservation), persistent spatial population distribution (`SpatialGridIndex` + LOD 0–3), A–G epistemic evidence partitioning, and 262-district coverage registry.
- **Zero Regression Across 173 Automated Checks**: **11/11** Phase 1.17 pytest suites (including **20/20** validation experiments `EXP_117_A..EXP_117_T` and the 3-department Decisive E2E Test) plus **162/162** cross-phase regression tests across Phases 1.14, 1.15, 1.16A/B, GIS, territory, and Studio API/UI passed with **0 failures**.

---

## 2. Implemented Engines & Verification Status Matrix

Following the mandatory separation rule, every component reports its exact status without conflating `IMPLEMENTED`, `INTEGRATED`, `EXECUTABLE`, `VERIFIED`, and `EMPIRICALLY_CALIBRATED`:

| Subsystem / Class | Module | IMPLEMENTED | INTEGRATED | EXECUTABLE | VERIFIED | EMPIRICALLY_CALIBRATED |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `OnDemandTerritorialSimulationEngine` | [`on_demand_engine.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/on_demand_engine.py) | YES | YES | YES | YES | PARTIAL (synthesizes synthetic behavior on real GIS/census priors) |
| `NationalBuildingIntelligenceEngine` | [`building_and_landuse.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/building_and_landuse.py) | YES | YES | YES | YES | YES (real OSM footprints + conservative `unknown`/`INFERRED` separation) |
| `TerritorialLandUseIntelligenceEngine` | [`building_and_landuse.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/building_and_landuse.py) | YES | YES | YES | YES | PARTIAL (real OSM landuse/roads/hydrology + district relief heuristic) |
| `CommercialActivityIntelligenceEngine`, `BusinessDistributionEngine`, `TerritorialEconomicContextEngine` | [`commercial_intelligence.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/commercial_intelligence.py) | YES | YES | YES | YES | YES (OSM POIs + P8 records separated from unverified commercial buildings) |
| `TerritorialCatchmentAnalysisEngine` | [`catchment.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/catchment.py) | YES | YES | YES | YES | PARTIAL (real `OSMRoadNetwork` Dijkstra circuity + rule-calibrated radii) |
| `HumanMobilityFlowEngine`, `TerritorialPopulationDistributionEngine`, `PopulationFlowEvidenceEngine` | [`mobility_flow.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/mobility_flow.py) | YES | YES | YES | YES | PARTIAL (agent/role/schedule model grounded in real corridors; measured sensor counts `False`) |
| `EmploymentOpportunityAnalysisEngine`, `TerritorialLaborMarketEngine` | [`employment.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/employment.py) | YES | YES | YES | YES | PARTIAL (5-tier provenance; EHPM informal priors; verified live vacancies `0`) |
| `DynamicPopulationDistributionEngine` | [`population_distribution.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/population_distribution.py) | YES | YES | YES | YES | PARTIAL (synthetic households spatially grounded onto OSM residential buildings/landuse) |
| `TerritorialEvidenceEngine` (A–G + Grounding Audit) | [`evidence.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/evidence.py) | YES | YES | YES | YES | N/A (epistemic partitioning & narrative anti-fabrication auditor) |
| `NationalTerritorialCoverageRegistry` | [`coverage.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/territorial_intelligence/coverage.py) | YES | YES | YES | YES | YES (computed dynamically from `geography.sqlite` across 262 districts) |

---

## 3. National GIS Database Rebuild (`geography.sqlite`)

[`saltbor/datasets/gis/pipeline.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/datasets/gis/pipeline.py) was upgraded and re-ingested (`ingest_manifest.json` duration: `151.64s`) with SQLite R-Tree spatial indexing (`has_rtree: True`) and **795,877** real OSM features across **15 layers**:

| Layer | Feature Count | Role in Phase 1.17 |
| :--- | ---: | :--- |
| `buildings` | 632,482 | Nationwide building footprints (`building=yes` mapped conservatively to `unknown`) |
| `roads` | 121,344 | `OSMRoadNetwork` routing, circuity, mobility corridors, and accessibility |
| `pois_a` | 11,400 | Newly ingested polygon POIs (shops, schools, clinics, hospitals, malls, markets) |
| `landuse` | 10,887 | Residential, commercial, industrial, agricultural & conservation overlays |
| `pois` | 8,011 | Point POIs with expanded commercial/service/workshop classes |
| `waterways` | 4,433 | Natural river/quebrada barrier detection for adaptive catchments |
| `places` | 2,657 | Settlement/cantón/neighborhood geocoding nationwide |
| `water` | 1,437 | Water bodies & flood-exposure context |
| `pofw_a` & `pofw` | 947 + 448 | Religious community landmarks (newly ingested) |
| `transport` & `transport_a` | 897 + 118 | Bus stops, terminals, and transit hubs (polygon layer newly ingested) |
| `adminareas` | 474 | Administrative reference geometries |
| `protected_areas` | 220 | Environmental & land-use constraint overlays (newly ingested) |
| `natural` | 122 | Parks, peaks, and physical landscape features |

---

## 4. Historic Center Decoupling & Backward Compatibility

1. [`SimulationConfig`](file:///c:/GIT%20HUB/sv%20people/saltbor/core/config.py) gained `territory_mode`, `territory_scope`, `territory_district_id`, `center_lat`, and `center_lon`.
2. [`create_app()`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/server.py) passes `auto_initialize_benchmark=False` to [`SimulationController`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/controller.py), booting into `IDLE_ON_DEMAND` with `active_population = 0` and `historic_center_active = False`.
3. [`SimulationRunner`](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/runner.py) and [`IntegratedWorldSimulationEngine`](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/integrated_world.py) scope communities, stores, CPRs, institutions, storm coordinates, and travel anchors strictly to the active territory while preserving Historic Center under `territory_mode == "historic_center_benchmark"` (`create_historic_center_benchmark()`), verified by both `EXP_117_A`, `EXP_117_P` (`8.108 ms/tick` over 96 ticks), and all legacy pilot GIS tests (`tests/test_gis/`).

---

## 5. Conversational Studio, API & Optional Map Integration

- **Persistence**: [`ConversationalPersistenceStore`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/persistence.py) applies idempotent schema v2 SQLite WAL migrations (`studio_schema_meta`, `territorial_scenarios`, `territorial_evidence_packages`, `territorial_coverage_cache`, `persistent_population_assignments`).
- **Chat Orchestration**: [`SALTBORConversationalOrchestrator`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/orchestrator.py) integrates `OnDemandTerritorialSimulationEngine` into Stage A (fast observed snapshot, no fabricated outcomes) and Stage B (full A–G evidence package + scenario persistence), with a bounded `_ti_static_cache` reusing Stage A computations seamlessly into Stage B, plus multi-turn follow-up cues (`"ahora analiza"`, `"flujo de personas"`, `"oportunidades de empleo"`).
- **Decision Analyst & Ollama Latency Guard**: [`GeminiDecisionAnalyst`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/decision_analyst.py) exposes `analyze_evidence_package()` supporting Gemini BYOK, local Ollama (probing `127.0.0.1` cleanly with 200ms timeout to avoid IPv6 loopback stalls in [`ollama.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/ai/providers/ollama.py)), and deterministic offline mode.
- **REST & Studio Map**: [`territorial_intelligence_router.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/routers/territorial_intelligence_router.py) serves `/api/territorial/*`. [`territorial_studio.js`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/modules/territorial_studio.js) keeps the chat-first layout with the map hidden by default (`map_required: false`) and overlays catchment polygons + commercial establishment markers whenever the optional map drawer is opened.

---

## 6. Scientific Validation & Experiment Results (`EXP_117_A..EXP_117_T`)

Recorded in [`experiments/phase117/phase117_experiments_record.json`](file:///c:/GIT%20HUB/sv%20people/experiments/phase117/phase117_experiments_record.json) (`passed_count: 20 / 20`, `all_passed: true`):

| ID | Title | Scope / Context | Passed |
| :--- | :--- | :--- | :---: |
| `EXP_117_A` | Historic Center is no longer the default simulation location | National / Location-Independent | True |
| `EXP_117_B` | Location resolution across distinct Salvadoran departments | 4 Departments (`SA, SS, SV, SM`) | True |
| `EXP_117_C` | Building and land-use context retrieval outside Historic Center | Soyapango, San Salvador Este | True |
| `EXP_117_D` | Commercial establishment identification and provenance | Soyapango, San Salvador | True |
| `EXP_117_E` | Adaptive catchment areas by service type | Soyapango road network | True |
| `EXP_117_F` | Resident versus temporary population differentiation without double counting | Soyapango + San Salvador commuters | True |
| `EXP_117_G` | Commuting and diurnal mobility flow analysis | Soyapango | True |
| `EXP_117_H` | Employment opportunity analysis with explicit 5-tier provenance | Soyapango | True |
| `EXP_117_I` | Residential population distribution outside Historic Center | San Miguel | True |
| `EXP_117_J` | Scenario activation without population reset | Cross-city persistence (`SS -> SA`) | True |
| `EXP_117_K` | Honest missing geographic data handling | San Vicente Sur / Morazán | True |
| `EXP_117_L` | Real versus synthetic data differentiation (A–G) | Soyapango | True |
| `EXP_117_M` | Evidence-grounded AI interpretation | Soyapango | True |
| `EXP_117_N` | Alternative commercial location comparison | La Libertad Sur vs San Salvador Este | True |
| `EXP_117_O` | Employment intervention & conserved spillover effects | Soyapango & Santa Ana | True |
| `EXP_117_P` | Historic Center preserved regression benchmark | San Salvador Centro Histórico | True |
| `EXP_117_Q` | Cross-department territorial scenario execution | `SS, SM, SA, CH` | True |
| `EXP_117_R` | Sustained performance under 4 concurrent scenarios | Multi-department concurrent | True |
| `EXP_117_S` | SQLite R-Tree spatial index and 262-district coverage performance | All 262 districts | True |
| `EXP_117_T` | End-to-end multi-turn conversational territorial simulation | Santa Tecla, La Libertad Sur | True |

---

## 7. Decisive End-to-End Test Verification (Soyapango + San Miguel + Santa Ana)

Executed both via [`test_phase117_territorial_experiments.py`](file:///c:/GIT%20HUB/sv%20people/tests/test_experiments/test_phase117_territorial_experiments.py) and live engine verification across **3 distinct departments** (San Salvador, San Miguel, Santa Ana) without touching Historic Center (`district_id != "0614"`):

| Location & Prompt Scope | Department | Lifecycle State | Observed Buildings | Sampled Footprint Area (m²) | Confirmed Establishments | Unverified Comm. Bldgs | Catchment Area (km²) | Coverage Tier | Known Employers (Verified Vacancies) | Spatial Mismatch Index | Cumulative Persistent Population |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: |
| **Soyapango** (`dist_soyapango`) | San Salvador | `COMPLETED` | 2,802 | 498,938.6 | 522 | 1 | 28.897 | `GOOD` | 60 (0) | 0.341 | 40 |
| **San Miguel** (`dist_san_miguel`) | San Miguel | `COMPLETED` | 1,653 | 534,086.4 | 362 | 3 | 28.897 | `GOOD` | 60 (0) | 0.399 | 80 (no reset) |
| **Santa Ana** (`dist_santa_ana`) | Santa Ana | `COMPLETED` | 1,568 | 366,181.4 | 465 | 0 | 28.897 | `GOOD` | 60 (0) | 0.357 | 120 (no reset) |

Each scenario produced **5** partitioned indicators in Tier A (`A_real_observed_data`) and **16** simulated indicators in Tier E (`E_simulated_outcomes`), `measured_flows_available: False`, zero ungrounded narrative claims, and strict `$0.00` accounting conservation.

---

## 8. Performance Benchmarks & Automated Test Verification

Measured via [`scripts/benchmark_phase117.py`](file:///c:/GIT%20HUB/sv%20people/scripts/benchmark_phase117.py) and recorded in [`PHASE_117_BENCHMARKS.json`](file:///c:/GIT%20HUB/sv%20people/PHASE_117_BENCHMARKS.json):

- **Memory RSS**: `98.78 MB` startup → `207.76 MB` after national scenario, concurrent, and 96-tick runs (well within 32 GB envelope).
- **SQLite R-Tree 500-Building Queries**: Soyapango `12.71 ms`, Santa Tecla `10.55 ms`, San Miguel `9.98 ms`, Santa Ana `7.22 ms`.
- **Full National Coverage Evaluation (262 Districts)**: `957.99 ms` → `GOOD`: **199**, `PARTIAL`: **61**, `POOR`: **2**, `INSUFFICIENT`: **0**.
- **Single-District Scenario Latency**: Soyapango `812.45 ms` (2,195 bldgs, cold init), San Miguel `411.47 ms` (939 bldgs), Santa Ana `437.96 ms` (1,264 bldgs), Chalatenango `192.82 ms` (1,248 bldgs).
- **4-Scenario Concurrent Execution**: `1,660.5 ms` total wall time (workers: `1584.54`, `1644.01`, `1452.75`, `1496.19 ms`).
- **Historic Center Preserved Benchmark (96 ticks)**: `8.108 ms/tick`.
- **Pytest Suites After Final Edits**:
  - Phase 1.17 Unit, API, On-Demand Lifecycle & 20-Experiment Suite (`tests/test_territorial_intelligence/` + `tests/test_experiments/test_phase117_territorial_experiments.py`): **11 passed in 20.49s** (`0` failed, `0` skipped).
  - Cross-Phase Regression Suite (`tests/test_conversational/`, `tests/test_gis/`, `tests/test_visualization/test_studio_frontend_e2e.py`, `tests/test_visualization/test_api_endpoints.py`, `tests/test_territory/`, `tests/test_experiments/test_phase114_territorial_experiments.py`, `test_phase115_ai_experiments.py`, `test_phase116a_conversational_experiments.py`): **162 passed in 31.38s** (`0` failed, `0` skipped; `EXP_116A_12` also verified standalone in `6.45s` pytest runtime).

---

## 9. Graphify Knowledge Graph Verification

Rebuilt via `python -m graphify update .`:
- **Updated Graph**: `16,097` nodes, `43,901` edges, `479` communities in `graphify-out/` ([`GRAPH_REPORT.md`](file:///c:/GIT%20HUB/sv%20people/graphify-out/GRAPH_REPORT.md)).
- **Traversal Verification**: `python -m graphify query "OnDemandTerritorialSimulationEngine"` returned `366` connected nodes, linking `OnDemandTerritorialSimulationEngine` cleanly with `SALTBORConversationalOrchestrator`, `IngestedGeography`, `NationalPopulationActivationManager`, `NationalTerritorialContextEngine`, `TerritorialEvidenceEngine`, `HumanMobilityFlowEngine`, `DynamicPopulationDistributionEngine`, `NationalTerritorialCoverageRegistry`, `TerritorialCatchmentAnalysisEngine`, and `phase117_territorial_experiments.py`.

---

## 10. Known Limitations

1. **OSM Footprint Metadata**: Standard Geofabrik El Salvador shapefiles do not include building heights, floor counts (`height_m=None`, `levels=None`), or verified interior commercial occupancy (`occupancy_known=False`).
2. **Empirical Sensor & Live Vacancy Absence**: Neither live traffic/pedestrian sensor counts (`measured_flows_available=False`) nor live national job vacancy feeds (`verified_job_vacancies=[]`) exist offline; mobility flows and sector/employment projections remain transparently labeled under Tiers **C–E**.
3. **Informal Commerce Uncertainty**: Informal markets and street vending in El Salvador are underrepresented in OSM points/polygons; SALTBOR models informal density ranges explicitly with uncertainty bounds and labels synthetic informal agents distinctly from observed POIs.
4. **Terrain & DEM Resolution**: Slope and elevation hazards rely on district-level relief and waterway proximity heuristics rather than sub-meter LiDAR DEM rasters.
5. **Direct Controller Unit-Test Constructors**: `SimulationController(...)` keeps `auto_initialize_benchmark=True` by default when called directly without arguments for legacy unit-test backward compatibility, while FastAPI `create_app()` strictly defaults to `IDLE_ON_DEMAND` (`auto_initialize_benchmark=False`).

---

## 11. Related Phase 1.17 Deliverables

- [`PHASE_117_ARCHITECTURE_AUDIT.md`](file:///c:/GIT%20HUB/sv%20people/PHASE_117_ARCHITECTURE_AUDIT.md) — Mandatory 14-area pre-implementation audit, 5-status matrix, and compatibility plan.
- [`PHASE_117_ARCHITECTURE_AND_API.md`](file:///c:/GIT%20HUB/sv%20people/PHASE_117_ARCHITECTURE_AND_API.md) — Mermaid architecture diagram, spatial/WAL DB migrations, `/api/territorial/*` contracts, and A–G schema.
- [`PHASE_117_BENCHMARKS.json`](file:///c:/GIT%20HUB/sv%20people/PHASE_117_BENCHMARKS.json) — Machine-readable hardware & latency benchmarks.
- [`experiments/phase117/phase117_experiments_record.json`](file:///c:/GIT%20HUB/sv%20people/experiments/phase117/phase117_experiments_record.json) — Full JSON record of all 20 reproducible experiments (`EXP_117_A..EXP_117_T`).
