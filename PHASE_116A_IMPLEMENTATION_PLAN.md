# SALTBOR PHASE 1.16A — IMPLEMENTATION PLAN

**Objective**: Deliver the Conversational Territorial Simulation Studio backend intelligence layer for El Salvador while maintaining 100% offline fallback, strict double-entry accounting conservation, and zero regression on Phases 1.15–1.18.

---

## 1. Execution Phases

### Phase A — Audit & Specifications (Completed in Step 1)
- Create `PHASE_116A_AUDIT.md`, `PHASE_116A_ARCHITECTURE.md`, `NATIONAL_POPULATION_COVERAGE.md`, `SIMULATION_ENGINE_INTEGRATION_MATRIX.md`, `EVIDENCE_MODEL_SPECIFICATION.md`, and `PHASE_116A_IMPLEMENTATION_PLAN.md`.

### Phase B — Upgrade AI Providers, Privacy Guard & Bridge (Step 2)
- Update `saltbor/ai/providers/remote.py`: configurable non-obsolete Gemini model IDs (`gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-2.5-pro`), `x-goog-api-key` header transmission, sliding-window rate limiting + daily quota, Pydantic output validation, and anti-code-execution safety check.
- Update `saltbor/ai/privacy.py`: protect Salvadoran toponyms (`San José Las Flores`, `Santa Tecla`, etc.) from redaction false positives; add NIT, email, and API key pattern redaction + payload minimization & synthetic/real tagging.
- Fix `unit_price_usd` attribute handling in `saltbor/simulation/scenario_bridge.py`.

### Phase C — Implement `saltbor/conversational/` Package (Step 3)
1. `schemas.py`: Pydantic v2 models for 14 intents, 18 intervention types, 8 population categories, LOD 0–3, provenance, synthetic opinions, verdicts, Stage A/B payloads, and session persistence.
2. `territorial_context.py`: `NationalTerritorialContextEngine` resolving all 14 departments, 44 municipalities, 262 districts, 474 cantones, OSM places/roads/facilities, and optional `(lat, lon)` coordinates with ambiguity candidate detection and strict provenance.
3. `population_activation.py`: `NationalPopulationActivationManager` & `TerritorialPopulationContextEngine` bridging `MultilevelPopulationManager` & `CognitiveLODManager`, preserving persistent human identities, preventing commuter double-counting, and supporting selective regional activation/deactivation.
4. `temporal_controller.py`: `ConversationalTemporalController` parsing natural Spanish horizons (`esta semana`, `30 días`, `tres meses`, `época lluviosa`, `un año`, `5 años`), proposing defaults, confirming costly runs, and executing multi-resolution (fine tick, hybrid seasonal, longitudinal) simulations with checkpoints and cancellation.
5. `intervention_designer.py`: `TerritorialInterventionDesigner` creating and modifying real entities across `CommercialEngine`, `BusinessRegistry`, `LaborMarketEngine`, `PublicServiceCapacityEngine`, `LiveScenarioBridge`, and `VerifiableEconomicLedger`.
6. `evidence_engine.py`: `SyntheticPopulationEvidenceEngine` extracting grounded indicators with provenance, group breakdowns, missing indicators, and non-independent synthetic human opinions.
7. `decision_analyst.py`: `GeminiDecisionAnalyst` producing calibrated verdicts (`PROMISING`, `CONDITIONALLY_PROMISING`, `INSUFFICIENT_EVIDENCE`, `HIGH_RISK`, `NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS`) via Gemini -> Ollama -> OfflineDeterministic without hallucinating simulation outputs.
8. `scenario_comparison.py`: `TerritorialScenarioComparisonEngine` performing multi-seed paired counterfactual comparisons across Baseline vs Proposed vs Alternative interventions.
9. `persistence.py`: `ConversationalPersistenceStore` storing chat turns, scenario configs, executions, evidence references, analyses, and checkpoints in SQLite WAL.
10. `orchestrator.py`: `SALTBORConversationalOrchestrator` providing Spanish NLU + continuity, Two-Stage workflow (Stage A preliminary assessment vs Stage B real simulation), and background job control.

### Phase D — Persistence Migration & Studio FastAPI Router (Step 4)
- Extend `saltbor/persistence/schema.py` with `conv_*` WAL tables (`_SCHEMA_VERSION = 5`).
- Create `saltbor/visualization/routers/conversational_studio_router.py` exposing `/api/studio/*` endpoints and wire into `saltbor/visualization/api.py`.

### Phase E — Comprehensive Testing, 12 Experiments & Benchmarking (Steps 5–6)
- Build 5 test modules in `tests/test_conversational/` covering every requirement in Section 14.
- Implement and run all 12 experiments (`EXP_116A_01`–`EXP_116A_12`) in `saltbor/simulation/experiments/phase116a_conversational_experiments.py` and `tests/test_experiments/test_phase116a_conversational_experiments.py`.
- Generate `PHASE_116A_BENCHMARKS.json` and `PHASE_116A_FINAL_REPORT.md` and run full regression suite.
