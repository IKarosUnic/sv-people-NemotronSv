# SALTBOR Phase 1.16B — Studio API Integration Specification

## 1. Architectural Integration Overview

The `TerritorialSimulationStudio` frontend module ([territorial_studio.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/modules/territorial_studio.js)) acts strictly as a natural-language conversational client, provenance presenter, and optional map coordinator. It NEVER fabricates simulation metrics, bypasses the accounting ledger, or performs client-side demographic projections.

All territorial resolution, synthetic population activation, multi-engine simulation execution, and evidence synthesis occur through the Phase 1.16A/1.16B FastAPI backend router mounted under `/api/studio/*` in [conversational_studio_router.py](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/routers/conversational_studio_router.py), orchestrated by `SALTBORConversationalOrchestrator` ([orchestrator.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/orchestrator.py)).

---

## 2. Two-Stage Execution & Job Lifecycle

| Stage | Endpoint | Purpose | Network Requirement |
| :--- | :--- | :--- | :--- |
| **Stage A (Preliminary)** | `POST /api/studio/chat` | Interprets natural Spanish prompt, resolves territory (query or coordinates), parses intervention + temporal horizon, estimates population coverage, and proposes a simulation configuration without running heavy ticks yet. | Works 100% offline; uses Gemini/Ollama only if configured for enrichment. |
| **Stage B (Simulated Execution)** | `POST /api/studio/execute` | Executes `SimulationRunner` via real SALTBOR engines with paired baseline vs. intervention comparison, synthetic agent opinions, accounting conservation audit (`ledger_audit`), and Gemini/Offline synthesis. | Works 100% offline; supports synchronous (`run_in_background=false`) or polled background worker (`run_in_background=true`). |
| **Live Stage Polling** | `GET /api/studio/jobs/{job_id}` | Streams real backend phase transitions without fake progress bars (`VALIDATING_SCENARIO` $\rightarrow$ `RESOLVING_LOCATION` $\rightarrow$ `PREPARING_POPULATION` $\rightarrow$ `RUNNING_SIMULATION` $\rightarrow$ `COLLECTING_EVIDENCE` $\rightarrow$ `COMPARING_SCENARIOS` $\rightarrow$ `ANALYZING_RESULTS` $\rightarrow$ `COMPLETED` / `INSUFFICIENT_DATA` / `CANCELLED` / `FAILED`). | Local in-memory job table (`350 ms` UI poll interval). |
| **Job Cancellation** | `POST /api/studio/jobs/{job_id}/cancel` | Signals the `threading.Event` cancel flag inside `SALTBORConversationalOrchestrator.cancel_job()`. | Immediate cancellation signal. |

---

## 3. Complete Endpoint Contract Matrix

### 3.1 Conversational Flow & Execution

- **`POST /api/studio/chat`**
  - Request (`StudioChatRequest`):
    - `message: str` (natural Spanish input, including follow-ups like `"¿Y si contrato dos empleados más?"` or `"¿Qué pasa si abro hasta las diez de la noche?"`)
    - `conversation_id: Optional[str]` (maintains continuity across follow-ups)
    - `lat: Optional[float]`, `lon: Optional[float]` (optional map-selected or search-selected coordinates)
    - `map_visible: bool = False` (proves headless chat-first independence)
    - `auto_execute: bool = False`
    - `seed: Optional[int]`
    - `temporal_days_override: Optional[int]` (optional explicit duration override from advanced UI control)
  - Response (`ConversationStageResult` JSON):
    - Includes `conversation_id`, `scenario_id`, `stage` (`STAGE_A_PRELIMINARY`), `ready_to_execute`, `parsed_request`, `territorial_context`, `proposed_intervention`, `temporal_horizon`, `population_context`, `computational_estimate`, and `assistant_reply`.

- **`POST /api/studio/execute`**
  - Request (`StudioExecuteRequest`):
    - `conversation_id: str`, `scenario_id: Optional[str]`, `seed: int = 42`, `compare_alternatives: bool = False`, `max_active_agents: int = Field(default=40, ge=8, le=250)`, `map_visible: bool = False`, `run_in_background: bool = False`.
  - Background Response: `{"status": "started", "job_id": "<JOB_...>", "conversation_id": "..."}`
  - Sync / Final Job Result (`SimulationStudioResult` JSON):
    - Separated top-level blocks: `territorial_context`, `temporal_horizon`, `intervention`, `evidence` (simulated indicators with `provenance`, `ledger_audit`, `synthetic_opinions`, `missing_indicators`), `recommendation` (LLM/analyst synthesis with `verdict`, `executive_summary`, `model_vs_external_distinction`, `assumptions`, `uncertainty`, `limitations`, `alternative_interpretations`, `disclaimer`), `comparison` (baseline vs. intervention metrics), and `provenance_record`.

- **`GET /api/studio/jobs/{job_id}`** and **`POST /api/studio/jobs/{job_id}/cancel`**
  - `GET /api/studio/jobs/{job_id}` returns `job_id`, `status` (`RUNNING` | `CANCELLING` | `CANCELLED` | `COMPLETED` | `FAILED`), `stage_code`, `stage_label`, `stage_history`, `result`, and `error`. Returns HTTP `404` if unknown.
  - `POST /api/studio/jobs/{job_id}/cancel` returns `{"status": "cancelling", "job_id": job_id}` or `404`.

- **`POST /api/studio/compare`**
  - Request (`StudioCompareRequest`): `conversation_id: str`, `seeds: list[int] = [42, 101, 202]`, `max_active_agents: int = 32`.
  - Returns multi-seed scenario comparison (`alternatives`) executed through `scenario_comparison.py`.

---

### 3.2 Conversation Persistence & Reopening

- **`GET /api/studio/conversations?limit=30`**
  - Calls `orch.persistence.list_sessions(limit=limit)` from [persistence.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/persistence.py).
  - Returns `{"conversations": [...]}` with `conversation_id`, `title`, `active_location_query`, and `execution_count`.
- **`GET /api/studio/conversations/{conversation_id}`**
  - Returns `{"session": ..., "executions": [...]}` so closing/refreshing the UI and clicking a saved history entry restores full Stage A context, follow-ups, Stage B evidence, and verdict cards. Returns `404` if missing.

---

### 3.3 National Territory Resolution & Search

- **`GET /api/studio/territory/search?q=&limit=10`**
  - Searches across El Salvador's 14 departments, municipalities/districts (D.L. 762), cantones, and local OSM datasets without loading MapLibre.
  - Returns `{"query": q, "results": [...]}` (`district_name`, `department_name`, `level`, `label`, `lat`, `lon`).
- **`GET /api/studio/territory/resolve?query=&lat=&lon=&radius_km=1.5`**
  - Returns a structured `TerritorialContextResult` with `resolved`, `department_name`, `district_name`, `lat`, `lon`, `elevation_m`, `slope_deg`, `nearby_facilities`, `data_availability` (explicitly distinguishing verified national/OSM data from unavailable fields).

---

### 3.4 AI Providers, BYOK Security & Privacy Configuration

- **`GET /api/studio/providers/status`**
  - Returns:
    - `provider_mode`: `"offline"` | `"ollama"` | `"gemini"`
    - `status_code`: `"CONNECTED"` | `"NOT_CONFIGURED"` | `"QUOTA_EXCEEDED"` | `"RATE_LIMITED"` | `"UNAVAILABLE"` | `"LOCAL_PROVIDER_ACTIVE"` | `"OFFLINE_MODE"`
    - `gemini_byok_configured`: `bool`
    - `gemini_key_masked`: redacted mask from `PrivacyGuard.mask_api_key()` (raw key NEVER serialized back)
    - `ollama_model`, `ollama_available`, `strict_redaction`, `rate_limit` (`flash_model`, `flash_lite_model`), `budget`.
- **`POST /api/studio/providers/config`**
  - Request (`StudioProviderConfigRequest`): `gemini_api_key` (`"clear"` wipes ephemeral memory key and forces `allow_remote = False`), `provider_mode`, `allow_remote`, `flash_lite_model`, `flash_model`, `ollama_model`, `strict_redaction`.
  - Updates backend state in memory only and returns masked status (`status: "updated"`). Keys are never written to `localStorage`, HTML attributes, SQLite, or frontend bundles.
