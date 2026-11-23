# SALTBOR PHASE 1.16A — MANDATORY INITIAL AUDIT

**Audit Date**: 2026-11-23  
**Scope**: Complete backend architecture, Graphify dependency topology, `SimulationRunner` execution paths, OSM/GIS national datasets, multi-level population/LOD, scenario bridges, Phase 1.15 AI layer, persistence, and API contracts.  
**Target Environment**: Python 3.14.5, Windows 11, SQLite WAL, Local-First / Offline-Capable.

---

## 1. Graphify Structural Dependency Audit

Inspected `graphify-out/GRAPH_REPORT.md` (15,002 nodes, 42,756 edges, 438 communities) and `graphify-out/graph.json`.

Key central hub degrees observed in `graph.json`:

| Hub Node | Source File | Graphify Degree | Role |
| :--- | :--- | :---: | :--- |
| `SimulationRunner` | [runner.py](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/runner.py) | 1,020 | Master tick runtime orchestrator |
| `GeneralizedTerritorialScenarioEngine` | [generalized_scenarios.py](file:///c:/GIT%20HUB/sv%20people/saltbor/territory/generalized_scenarios.py) | 72 | Declarative multi-domain scenario simulator |
| `MultilevelPopulationManager` | [population_manager.py](file:///c:/GIT%20HUB/sv%20people/saltbor/population/multilevel/population_manager.py) | 49 | Persistent/active/aggregated hydration manager |
| `AIModelRouter` | [router.py](file:///c:/GIT%20HUB/sv%20people/saltbor/ai/router.py) | 34 | Provider failover router (Gemini -> Ollama -> Deterministic) |
| `CommercialEngine` | [commercial_engine.py](file:///c:/GIT%20HUB/sv%20people/saltbor/economy/commerce/commercial_engine.py) | 29 | Bounded-rationality retail/dining visits |
| `RemoteGeminiProvider` | [remote.py](file:///c:/GIT%20HUB/sv%20people/saltbor/ai/providers/remote.py) | 28 | Remote Gemini HTTP adapter |
| `IngestedGeography` | [pipeline.py](file:///c:/GIT%20HUB/sv%20people/saltbor/datasets/gis/pipeline.py) | 28 | Read-only SQLite OSM national feature query engine |
| `TerritoryCatalogService` | [territory_catalog.py](file:///c:/GIT%20HUB/sv%20people/saltbor/territory/territory_catalog.py) | 21 | D.L. 762 262-district catalog & topographic hazard profiler |
| `NaturalLanguageScenarioBuilder` | [scenario_builder.py](file:///c:/GIT%20HUB/sv%20people/saltbor/ai/scenario_builder.py) | 19 | Phase 1.15 NL-to-scenario compiler |
| `GISEngine` | [engine.py](file:///c:/GIT%20HUB/sv%20people/saltbor/world/gis/engine.py) | 15 | Shapely STRtree zonal GeoJSON spatial index |

> Note: `graphify-out` was built at commit `d666b0c9`, prior to commit `bd89009` (Phase 1.16–1.18: `TickStagePipeline`, `AdaptiveLODBudgetController`, `LiveScenarioBridge`, `QuickSimulator`, `PinpointPlacementSimulator`, `ExternalHistoricalValidator`). All Phase 1.16–1.18 modules were inspected directly in source.

---

## 2. Actual Execution Path of `SimulationRunner`

Inspected [runner.py](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/runner.py) (`SimulationRunner.__init__`, `initialize`, `step`, `run`, `run_longitudinal`, `checkpoint`).

In each discrete tick (15 simulated minutes, `96 ticks/day`):
1. `self.clock.tick()` advances discrete time.
2. `self.environment.step()` and `self.regional_trade.step()` execute (`environment_ms`).
3. `self.orchestrator.step()` dispatches periodic (`WeeklyCuchubales` every 672 ticks, `MonthlyRemittanceSchedule` every 2,880 ticks) and `EVENT_TRIGGERED` handlers (`ADESCOEngine`, `JudicialTribunal`, `InformalCommerceEngine`, `RemittanceEngine`, `DistributedEducationEngine`, `ScientificThinkingEngine`, `AdvancedOfflineDialogueEngine`, `Phase15EverydayLifeEngine`), followed by `self.domain_engine.step()` (`orchestrator_ms`).
4. `self.live_scenario_bridge.step()` injects scenario shocks and interventions (`live_scenario_ms`).
5. At `tick_of_day == 0` (`daily_rollover_ms`), daily cycles execute:
   - `HouseholdLedger.execute_daily_living_expenses()`
   - `HousingEngine.collect_daily_rent()`
   - `LaborMarketEngine.execute_daily_payroll()`
   - `CommercialEngine.execute_daily_accounting()`
   - `WorldHumanInteractionEngine.record_human_environmental_impact()`
   - Cultural decay, social network decay, `CommunityFormationEngine`, `SocialNormEvolutionEngine`, `CollectiveResourceManager`, `InstitutionalEvolutionEngine`, `SocialStratificationEngine`, `EmergentOrganizationEngine`, and `CivilizationEvolutionEngine.step_daily()`.
6. `PopulationRegistry.build_location_index()`, `SimulationScheduler.get_execution_order()`, and `AdaptiveLODBudgetController.select_humans_for_tick()` select active humans (`population_update_ms`), running `human.update(...)` and `self.extension.step_individual(...)`, followed by `self.extension.step(...)`.
7. `self.integrated_world.step()` advances street kinematics and transport (`world_transit_ms`).
8. `self.psychology.process_events()` and `self.psychology.step_population()` use `event_bus.events_since()` (`psychology_ms`).
9. Periodic SQLite WAL checkpointing runs every `checkpoint_interval_ticks`.

**Critical observation**: `SimulationRunner` runs in a single-site local world (`LocationRegistry.create_saltbor_map()` + ~20 default synthetic humans unless scaled). Meanwhile, `GeneralizedTerritorialScenarioEngine` runs a separate cohort (`assemble_cohort_and_territory()`), and `MultilevelPopulationManager` exists as a separate multi-tier manager not wired into `SimulationRunner.step()` by default.

---

## 3. Epistemic Rigor Classification (Implemented vs Integrated vs Executed vs Tested vs Calibrated vs Validated)

| Subsystem | Implemented | Integrated in Runtime | Executed in Live Simulation | Tested | Empirically Calibrated | Validated |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `SimulationRunner` & `TickStagePipeline` | Yes | Yes | Yes | Yes | Partial (hourly cycles) | Yes (Phase 1.16) |
| `CommercialEngine` (`execute_visit`, bounded rationality) | Yes | Yes (`SimulationRunner.commerce_engine`) | Yes (daily accounting & events) | Yes | Partial (El Salvador staples) | Yes |
| `LaborMarketEngine`, `HousingEngine`, `HouseholdLedger` | Yes | Yes (`SimulationRunner` daily cycle) | Yes | Yes | Partial (USD wages/rent) | Yes |
| `VerifiableEconomicLedger` (double-entry `$0.00` diff) | Yes | Yes (`LiveScenarioBridge`, `GeneralizedTerritorialScenarioEngine`) | Yes | Yes | N/A (mathematical invariant) | Yes |
| `PublicServiceCapacityEngine` | Yes | Partial (`GeneralizedTerritorialScenarioEngine`, NOT `SimulationRunner` daily loop) | Only in scenario engine | Yes | No (defaults/unconfigured) | Partial |
| `DistributedEducationEngine` | Yes | Yes (apprenticeship event hook) | Event-triggered | Yes | No | Partial |
| `HealthEngine`, `ExtensionRuntime`, `PsychologicalEngine` | Yes | Yes (`SimulationRunner.extension`, `psychology`) | Yes | Yes | Partial | Yes |
| `IntegratedWorldSimulationEngine` & `TransportationEngine` | Yes | Yes (`SimulationRunner.integrated_world`) | Yes | Yes | Partial | Yes |
| `IngestedGeography` (`geography.sqlite`, 151,227 OSM rows) | Yes | Yes (`PinpointPlacementSimulator`, GIS API) | On demand | Yes | Real OSM ODbL-1.0 | Verified Real (with partial `buildings`) |
| `TerritoryCatalogService` (14 depts, 44 muns, 262 dists, 474 cantones) | Yes | Yes (AI builder, validation router) | On demand | Yes | D.L. 762 + ~6.58M pop + Tobler hazards | Yes (Level 5 historical backtest in `ExternalHistoricalValidator`) |
| `MultilevelPopulationManager` (persistent + active + aggregated) | Yes | Standalone (not wired into `SimulationRunner`) | Unit/benchmarks only | Yes | Synthetic demographic priors | Partial |
| `CognitiveLODManager` + `AdaptiveLODBudgetController` | Yes | Yes (`SimulationRunner.step`) | Yes | Yes | Heuristic thresholds | Yes |
| `AIModelRouter`, `RemoteGeminiProvider`, `OllamaProvider`, `OfflineDeterministicProvider` | Yes | Yes (FastAPI `/api/ai/*`, `QuickSimulator`) | On demand | Yes (mostly offline/mock) | N/A | Partial |
| `Conversational Orchestrator / Evidence / Studio` | **No** | **No** | **No** | **No** | **No** | **No** |

---

## 4. Concrete Gaps Identified Prior to Phase 1.16A

1. **Obsolete Gemini Model IDs & Key Hygiene (`saltbor/ai/providers/remote.py`)**:
   - Hardcoded `gemini-1.5-flash` and `gemini-1.5-pro` instead of configurable non-obsolete model IDs (e.g., `gemini-2.5-flash-lite`, `gemini-2.5-flash`).
   - Passed the API key in the query string (`?key={self._api_key}`) rather than the `x-goog-api-key` header.
   - Missing per-minute / daily rate-limiting guard, Pydantic schema validation on structured JSON outputs, and prompt-code-execution guard.
2. **Template-Bound Phase 1.15 AI Builders (`scenario_builder.py`, `results_analyst.py`)**:
   - `NaturalLanguageScenarioBuilder` fell back unknown places silently to `"San José Las Flores"` and injected road-landslide hypotheses regardless of prompt intent.
   - `SimulationResultsAnalyst` invoked `self.router.route_request(req)` and then ignored `resp`, returning hardcoded road-shock/tiendita prose.
3. **Privacy Guard False Positives & Gaps (`saltbor/ai/privacy.py`)**:
   - `_name_pattern` matched `"José Las"` inside `"Cantón San José Las Flores"`, corrupting valid Salvadoran place names.
   - Did not redact email addresses, Salvadoran NIT numbers (`\d{4}-\d{6}-\d{3}-\d`), or leaked API key tokens (`AIza...`, `sk-...`).
4. **LiveScenarioBridge Price Field Bug (`saltbor/simulation/scenario_bridge.py`)**:
   - Lines 192–193 and 217 referenced `prod.unit_price`, whereas `CommercialProduct` in [commercial_engine.py](file:///c:/GIT%20HUB/sv%20people/saltbor/economy/commerce/commercial_engine.py) defines `unit_price_usd`.
5. **Partial OSM Coverage Disclosure**:
   - `geography.sqlite` contains 151,227 features across 10 layers (`roads`: 121,344; `landuse`: 10,887; `pois`: 8,011; `waterways`: 4,433; `places`: 2,657; `water`: 1,437; `transport`: 897; `adminareas`: 474; `natural`: 122), **but `buildings` (989 rows) has `is_partial=1` restricted to `[-89.202, 13.693, -89.186, 13.704]` (San Salvador Centro)**. Any national engine must expose this explicitly and never hallucinate missing buildings.
6. **LOD Numbering Inversion**:
   - Existing `MultilevelPopulationManager` uses `LOD_0_INDIVIDUAL` (finest) to `LOD_4_REGIONAL` (coarsest), whereas Phase 1.16A defines `LOD 0` (territorial aggregates) to `LOD 3` (detailed individual cognition). An explicit adapter/mapping layer is required.
7. **Missing Conversational Studio Capabilities**:
   - No `SALTBORConversationalOrchestrator` with Spanish multi-turn context, no Two-Stage (preliminary vs simulation) workflow, no `NationalPopulationActivationManager` with anti-double-counting commuter tracking, no `ConversationalTemporalController` supporting 1-year/5-year seasonal horizons, no `SyntheticPopulationEvidenceEngine` with grounded non-independent synthetic opinions, and no conversation/scenario SQLite WAL persistence.
