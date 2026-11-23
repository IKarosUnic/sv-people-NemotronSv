# SALTBOR PHASE 1.16B — MANDATORY FRONTEND AUDIT

**Audit Date**: 2026-11-23  
**Scope**: Complete SALTBOR Web Application (`saltbor/visualization/web/`), MapLibre GIS digital twin, API integrations, Phase 1.15/1.18 frontend modules, Graphify dependency topology, design system tokens, responsiveness, accessibility, and test contracts.

---

## 1. Framework, Architecture & File Inventory

SALTBOR strictly enforces a **100% Vanilla HTML5 + CSS3 + ES6 Modules** web architecture (`agent_skills/frontend/SKILL.md`), with zero Node.js, npm, React, Vue, Tailwind, or external CDN dependencies:

| Asset | Size | Role |
| :--- | :---: | :--- |
| [index.html](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/index.html) | 192,313 bytes (2,331 lines) | Single-page shell: `#control-center` topbar, `#sidebar` nav (13 existing views), `#viewport` view panels, quick/pinpoint modals |
| [style.css](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/style.css) | 51,022 bytes (2,401 lines) | Design tokens (`:root` dark default, `[data-theme="light"]`), topbar/sidebar/inspector/GIS styles |
| [app.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/app.js) | 335,720 bytes (6,446 lines) | Core IIFE managing `state`, `switchView`, SSE stream, Canvas fallback, MapLibre GL JS 2.5D GIS, and all 13 observability tabs |
| [live_bridge_observatory.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/modules/live_bridge_observatory.js) | 12,604 bytes (274 lines) | ES6 module for Phase 1.16–1.18 telemetry, Quick Simulator, and Pinpoint placement |
| [assets/maplibre/maplibre-gl.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/assets/maplibre/maplibre-gl.js) & `.css` | 803,086 + 65,534 bytes | Local offline-bundled MapLibre GL JS v4+ WebGL engine |

---

## 2. Routing, State Management & Existing Map Audit

1. **Routing**: Client-side view switching via `switchView(viewName)` in [app.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/app.js) toggling `.active` on `.nav-item[data-view]` and `#view-<name>.view-panel`.
2. **State Management**: Single central `state` object inside `app.js` (exposed via `window.saltborState = state`), tracking `currentView`, `theme`, `gisMap`, `selectedAgentUid`, and fetched domain datasets.
3. **Map Implementation (`setupGIS25D` & `initOrResizeGIS25D`)**:
   - Currently `#view-world` is marked `.active` on load, and `DOMContentLoaded` calls `initOrResizeGIS25D()` immediately — forcing the MapLibre WebGL viewport to occupy the primary screen at launch.
   - `state.gisMap` is a single `maplibregl.Map` attached to `#maplibre-viewport`, featuring national/AMSS/Centro camera presets (`btn-cam-national`, `btn-cam-city`, `btn-cam-recenter`), 2D/2.5D/Street perspectives, basemap switcher (including `vector` local offline mode), and GeoJSON layers backed by `/api/geography/geojson`, `/api/world`, `/api/individuals`, and `/api/quick/pinpoint`.
   - A hidden `#world-canvas` exists strictly for backward compatibility with [test_web_assets.py](file:///c:/GIT%20HUB/sv%20people/tests/test_visualization/test_web_assets.py).
4. **Graphify Dependencies**: Inspected `graphify-out/graph.json`: `2,932` visualization nodes (dominated by `test_api_endpoints.py`, `api.py`, and frontend controller hooks). Note `app.js` uses plain IIFE scoping plus `window.saltborState`, `window.showGISFeatureInspector`, and ES6 modules under `modules/`.

---

## 3. Existing API Contracts & AI Integration Audit

- **Phase 1.15 AI Lab** (in `app.js` lines 6338+ & `index.html`): Calls `/api/ai/territories/coverage`, `/api/ai/scenarios/build_natural_language`, `/api/ai/execution/run`, `/api/ai/results/analyze` inside a secondary tab form rather than a primary chat workspace.
- **Phase 1.16A Studio Backend** (implemented in [conversational_studio_router.py](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/routers/conversational_studio_router.py)):
  - Already exposes `POST /api/studio/chat`, `POST /api/studio/execute` (with `run_in_background`), `GET /api/studio/jobs/{job_id}`, `POST /api/studio/jobs/{job_id}/cancel`, `POST /api/studio/compare`, `GET /api/studio/conversations/{conversation_id}`, `GET /api/studio/territory/resolve`, `GET /api/studio/providers/status`, `POST /api/studio/providers/config`.
  - **Missing backend endpoints identified for full Phase 1.16B UX**:
    1. `GET /api/studio/conversations` — list persisted conversations so the History sidebar can populate on load.
    2. `GET /api/studio/territory/search?q=...` — fast location autocomplete across 14 departments, 44 municipalities, 262 districts, 474 cantones, and OSM places.
    3. Authentic backend stage progress fields (`stage_code`, `stage_label`, `stage_history`) inside `GET /api/studio/jobs/{job_id}` so the frontend displays real execution phases without fabricating progress.
    4. Explicit `provider_mode` (`gemini` | `ollama` | `offline`), `ollama_model`, and `strict_redaction` controls on `/api/studio/providers/status` & `/api/studio/providers/config`.

---

## 4. Accessibility, Responsiveness & Design Gaps Identified

1. **`user-select: none` on `html, body`** ([style.css](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/style.css) line 83): Prevents users from selecting/copying chat text or evidence values unless overridden inside `.studio-shell`.
2. **Fixed Desktop Overflow (`overflow: hidden`)**: Desktop topbar + 230px left sidebar + fixed viewport breaks cleanly below `1024px` unless responsive breakpoints collapse the sidebar/history drawer and allow fluid scrolling inside the chat stream.
3. **Eager Map Initialization**: Launching directly into `#view-world` conflicts with Phase 1.16B's chat-first requirement (`#view-studio` default, map hidden & lazy-loaded).
4. **Test Compatibility Contract ([test_web_assets.py](file:///c:/GIT%20HUB/sv%20people/tests/test_visualization/test_web_assets.py))**:
   - `index.html` MUST preserve `"SALTBOR"`, `"FASE 1.3-V"`, `"world-canvas"`, `"view-individual"`, `"view-cognitive"`, `"view-knowledge"`, `"view-social"`, `"view-civilization"`, `"view-economy"`, `"view-timeline"`, `"view-laboratory"`, `"view-reports"`.
   - `style.css` MUST preserve `--accent-sky` and `control-center`.
   - `app.js` MUST preserve `renderWorldLoop`, `fetchIndividualsRoster`, and `projectGeo`.
