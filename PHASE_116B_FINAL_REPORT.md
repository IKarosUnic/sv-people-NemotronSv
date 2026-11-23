# SALTBOR Phase 1.16B — Final Report: Conversational Territorial Intelligence Studio, Chat-First UX & Optional National Map

**Status**: IMPLEMENTED & VERIFIED  
**Environment**: Python 3.14.5 · Windows 11 · Vanilla HTML5 / CSS3 / ES6 · FastAPI · MapLibre GL JS (100% local static assets)

---

## 1. Executive Summary

Phase 1.16B delivers SALTBOR's **Chat-First Conversational Territorial Simulation Studio** (`TerritorialSimulationStudio`) without rebuilding or fragmenting the existing observatory application. Any user can now land directly on an approachable Spanish conversational workspace, ask territorial or business questions anywhere in El Salvador without understanding GIS or demographic parameters, run authentic Stage B multi-engine simulations over the synthetic population, inspect evidence strictly separated from LLM interpretation, and open an optional contextual national map on demand.

All legacy views (`Territorio & SIG Cartográfico`, `Explorador Individual`, `Arquitectura Cognitiva`, `Grafo de Conocimiento`, `Red Social & ADESCO`, `Tablero de Civilización`, `Economía & Recursos`, `Línea de Tiempo`, `Laboratorio Científico`, `Informes de Validación`, etc.) and API contracts remain fully intact.

---

## 2. Mandatory Architecture & Audit Documentation

- [PHASE_116B_FRONTEND_AUDIT.md](file:///c:/GIT%20HUB/sv%20people/PHASE_116B_FRONTEND_AUDIT.md) — Frontend architecture audit, existing view preservation, single-map & asset audit.
- [PHASE_116B_UI_ARCHITECTURE.md](file:///c:/GIT%20HUB/sv%20people/PHASE_116B_UI_ARCHITECTURE.md) — `TerritorialSimulationStudio` layout hierarchy, drawer states, and lazy map docking design.
- [PHASE_116B_API_INTEGRATION.md](file:///c:/GIT%20HUB/sv%20people/PHASE_116B_API_INTEGRATION.md) — Complete `/api/studio/*` REST contracts, Stage A/B separation, stage polling, cancellation, and BYOK security rules.
- [PHASE_116B_DESIGN_SYSTEM.md](file:///c:/GIT%20HUB/sv%20people/PHASE_116B_DESIGN_SYSTEM.md) — Dark/Light CSS token reuse, epistemic provenance color semantics, accessibility, and responsive breakpoints (`1024px`, `768px`, `1200px`).

---

## 3. Implemented Deliverables

### 3.1 Frontend (`saltbor/visualization/web/`)

- **[index.html](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/index.html)**:
  - Set `<section id="view-studio" class="view-panel active">` (`<li class="nav-item active" data-view="studio">`) as the default entry workspace (`Estudio Territorial IA`), while preserving all existing views (`#view-world`, `#view-individual`, etc.).
  - Added `#studio-shell` (collapsible `#studio-history-drawer`, `.studio-chat-pane`, `#studio-progress-banner` with live stage label and `#studio-btn-cancel-job`, composer with `#studio-location-search` autocomplete, `#studio-btn-pick-point`, `#studio-advanced-row` temporal override, and `.studio-map-drawer` supporting `hidden` | `side` | `expanded` | `full`).
  - Added `#studio-settings-modal` (Gemini BYOK password input, configurable Flash-Lite & Flash model IDs, Ollama local model, Offline deterministic mode, and strict identifier/redaction toggle), `#btn-mobile-nav`, `#btn-open-studio-settings`, and `#btn-return-to-studio`.
- **[studio.css](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/studio.css)**:
  - Reuses all Dark (`:root`) and Light (`:root[data-theme="light"]`) CSS custom properties from [style.css](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/style.css).
  - Enforces epistemic distinction via `.studio-badge.real`, `.studio-badge.synthetic`, `.studio-badge.warn`, `.studio-badge.risk`, and `.studio-badge.info`.
  - Adds `body.view-mode-studio` topbar compaction so settings (`⚙️`), theme (`🌓`), UI toggle, and `EN VIVO` status remain cleanly visible within `1280px`–`1440px` desktop widths, plus overlay `#inspector-panel` containment (`<= 1200px`) and mobile stacking (`<= 768px`, `40px` touch buttons, zero horizontal clipping).
- **[style.css](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/style.css)**:
  - Strengthened `[data-theme="light"]` selector specificity (`:root[data-theme="light"], html[data-theme="light"], [data-theme="light"]`) to prevent cascade ambiguity.
- **[territorial_studio.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/modules/territorial_studio.js)**:
  - Implements exact Spanish welcome text and 7 interactive starter prompt chips.
  - Supports Stage A preliminary triage, conversational follow-up continuity, Stage B background execution with authentic `350 ms` job stage polling + live cancellation, separated Synthetic Evidence & Analyst Verdict cards, multi-seed scenario comparison, Markdown report download, conversation list & reload persistence, location autocomplete + optional single-map reuse (`#maplibre-viewport` docked lazily via `window.initOrResizeGIS25D()`, never creating a duplicate MapLibre instance), and BYOK/Ollama/Offline configuration.
- **[app.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/app.js)**:
  - Defaults `state.currentView` to `"studio"`, lazily defers `initOrResizeGIS25D()` unless `currentView === "world"`, dispatches `saltbor:restore-world-map` before restoring World Explorer view, guards `#inspector-panel` auto-expansion when `state.currentView === "studio"`, syncs MapLibre canvas background tint on Dark/Light theme toggle, and keeps `gis-layer-national-highways` visible at urban zooms (`maxzoom: 19.0`).

### 3.2 Additive Backend Extensions

- **[conversational_studio_router.py](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/routers/conversational_studio_router.py)**: Added `GET /api/studio/conversations`, `GET /api/studio/territory/search`, `temporal_days_override` on `StudioChatRequest`, and explicit `provider_mode`, `status_code` (`CONNECTED`, `NOT_CONFIGURED`, `QUOTA_EXCEEDED`, `RATE_LIMITED`, `UNAVAILABLE`, `LOCAL_PROVIDER_ACTIVE`, `OFFLINE_MODE`), `ollama_model`, and `strict_redaction` state in `/api/studio/providers/*`.
- **[orchestrator.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/orchestrator.py)**: Added real progress stage emissions (`VALIDATING_SCENARIO`, `RESOLVING_LOCATION`, `PREPARING_POPULATION`, `RUNNING_SIMULATION`, `COLLECTING_EVIDENCE`, `COMPARING_SCENARIOS`, `ANALYZING_RESULTS`) stored as `stage_code`, `stage_label`, and `stage_history` inside `start_background_stage_b()`.
- **[persistence.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/persistence.py)**, **[territorial_context.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/territorial_context.py)**, and **[intervention_designer.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py)**: Added `list_sessions()`, `search_locations()`, and closing-hour follow-up extraction (e.g., `"hasta las diez de la noche"` $\rightarrow$ `closing_hour = 22`).

---

## 4. Verification Results

### 4.1 Automated Test Suite

Executed after all final edits on `2026-11-23`:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_visualization/test_studio_frontend_e2e.py tests/test_visualization/test_web_assets.py tests/test_conversational/ tests/test_experiments/test_phase116a_conversational_experiments.py tests/test_phase116_118_improvements.py tests/test_visualization/test_ai_layer_api.py -q
```

**Observed result**: `56 passed, 1 warning in 51.20s` (single benign Starlette `httpx2` deprecation warning in `fastapi/testclient.py`).

Covered test modules:
- [test_studio_frontend_e2e.py](file:///c:/GIT%20HUB/sv%20people/tests/test_visualization/test_studio_frontend_e2e.py) (`8 passed`): chat-first DOM & legacy asset preservation, natural Spanish prompts with map hidden, follow-up worker & closing-hour continuity, natural/explicit temporal overrides, national territory search & coordinate resolution, Stage B background job polling & accounting conservation (`$0.00 diff`), cancellation & `404` handling, and Gemini BYOK masking / Quota Exceeded / Rate Limited / Ollama / Offline provider state checks.
- [test_web_assets.py](file:///c:/GIT%20HUB/sv%20people/tests/test_visualization/test_web_assets.py) (`3 passed`): legacy HTML/CSS/JS smoke invariants preserved.
- `tests/test_conversational/*` (`18 passed`), [test_phase116a_conversational_experiments.py](file:///c:/GIT%20HUB/sv%20people/tests/test_experiments/test_phase116a_conversational_experiments.py) (`12 passed`), [test_phase116_118_improvements.py](file:///c:/GIT%20HUB/sv%20people/tests/test_phase116_118_improvements.py) (`7 passed`), and [test_ai_layer_api.py](file:///c:/GIT%20HUB/sv%20people/tests/test_visualization/test_ai_layer_api.py) (`8 passed`).

### 4.2 Live Chromium Verification & Screenshots

Verified live against `http://127.0.0.1:8765/` (`create_app` + isolated temporary SQLite databases) across desktop (`1440x900`), optional side map (`map-side`), settings modal, Light Theme toggle, and mobile viewport (`390x844`):
- **0 console / page / WebGL errors**.
- First verification pass exposed header overflow at `1440px`/`390px` and `#inspector-panel` auto-expansion squeezing the side map & mobile view; after fixing `style.css`, `studio.css`, `app.js`, and `territorial_studio.js`, the full second verification pass passed across all 5 visual & interactive scenarios.
- Saved screenshots:
  - [studio_01_welcome.png](file:///c:/GIT%20HUB/sv%20people/docs/screenshots/phase116b/studio_01_welcome.png) — Desktop chat-first entry with Spanish welcome, 7 starter prompts, hidden map, and clean unobstructed topbar.
  - [studio_02_stage_b_evidence.png](file:///c:/GIT%20HUB/sv%20people/docs/screenshots/phase116b/studio_02_stage_b_evidence.png) — Follow-up continuity & Stage B execution (`Contabilidad: $0.00 diff`, `SYNTHETIC_SIMULATED` evidence, saved history entry).
  - [studio_03_side_map.png](file:///c:/GIT%20HUB/sv%20people/docs/screenshots/phase116b/studio_03_side_map.png) — Single MapLibre GL JS viewport docked side-by-side (`map-side`) centered on Santa Tecla with target & facility overlays.
  - [studio_04_settings_modal.png](file:///c:/GIT%20HUB/sv%20people/docs/screenshots/phase116b/studio_04_settings_modal.png) — BYOK Gemini / Ollama / Offline provider & privacy modal.
  - [studio_05_light_theme.png](file:///c:/GIT%20HUB/sv%20people/docs/screenshots/phase116b/studio_05_light_theme.png) — Active `[data-theme="light"]` Light Theme across Studio and side map.
  - [studio_06_mobile.png](file:///c:/GIT%20HUB/sv%20people/docs/screenshots/phase116b/studio_06_mobile.png) — Mobile `390x844` responsive layout with visible menu trigger, fit topbar, and full-width conversation stream.

---

## 5. Known Limitations & Notes

- During live panning/zooming of the optional side map over remote Esri raster tiles, 5 background tile fetches logged standard in-flight cancellation (`net::ERR_ABORTED`) without affecting rendered tiles or WebGL overlays; full offline vector fallback remains selectable in the base-map selector (`Vector Local Puro`).
- Switching directly to legacy non-Studio views (`Territorio & SIG Cartográfico`, etc.) intentionally unhides the full simulation telemetry/population toolbar in `#control-center` (`body:not(.view-mode-studio)`).

---

## 6. How to Run Locally

```powershell
# 1. Start SALTBOR server (opens Chat-First Territorial Studio by default)
.venv\Scripts\python.exe -m saltbor.visualization.server
# or:
.venv\Scripts\python.exe -c "import uvicorn; from saltbor.visualization.server import create_app; uvicorn.run(create_app(), host='127.0.0.1', port=8000)"
```

Then open `http://127.0.0.1:8000/` in any local browser.
