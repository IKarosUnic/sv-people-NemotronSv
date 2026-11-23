# SALTBOR — Implementación de Inteligencia Progresiva y Reportes Multinivel

**Estado**: COMPLETADO Y VERIFICADO (Fases 1–7)  
**Entorno**: Python 3.14.5 (Windows 11) · Ejecución 100% local y offline · Sin alteración de motores ni contabilidad de doble entrada (`$0.00 diff`)

---

## 1. Arquitectura de Presentación Progresiva (Fase 1)

La selección de profundidad opera exclusivamente como **capa de presentación posprocesamiento**, manteniendo intactos los cálculos, semillas, libros contables y motores de SALTBOR:

- **Niveles disponibles** (`ReportDepthLevel` en [schemas.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/schemas.py#L91)):
  - `BASIC` (predeterminado — **"Resumen sencillo"**)
  - `INTERMEDIATE` (**"Análisis de decisiones"**)
  - `EXPERT` (**"Análisis exhaustivo"**)
- **Invarianza matemática garantizada**:
  - `ProgressiveReportBuilder.build_from_studio_result()` y `ProgressiveReportBuilder.build_from_persisted_execution()` en [progressive_reports.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/progressive_reports.py#L456) producen un `ProgressiveReportBundle` con `canonical_numeric_fingerprint` compartido e inmutable entre los tres niveles, tanto en resultados en vivo como al reconstruir ejecuciones persistidas en SQLite WAL (incluidos registros previos).

---

## 2. Profundidad por Nivel (Fases 2, 3 y 4)

### 2.1 Nivel `BASIC` (`BasicReportView`)
- **Contenido obligatorio**: qué se evaluó (`what_was_evaluated`), ubicación (`where_was_evaluated`), horizonte temporal (`temporal_horizon_summary`), veredicto comprensible (`overall_verdict_plain`), titular (`overall_result_headline`), tarjetas explicadas de ingresos (`estimated_revenue`), gastos totales derivados sin inventar (`estimated_expenses` = `ingresos - resultado operativo neto`), saldo operativo (`operating_result`), demanda potencial (`potential_demand`), clientes potenciales (`potential_customers`), destacados contextuales (`contextual_highlights`), oportunidades (`main_opportunities`), riesgos (`main_risks`), recomendación clara (`understandable_recommendation`) y aviso explícito de no garantía (`non_guarantee_notice`).

### 2.2 Nivel `INTERMEDIATE` (`IntermediateReportView`)
- **Análisis de 11 ejes de decisión**: demanda y mercado, competencia, comportamiento de consumidores, capacidad económica, movilidad territorial, accesibilidad, empleo, costos y rentabilidad, riesgos comerciales, recomendaciones accionables y comparación de escenarios (`alternative_scenarios` con `ScenarioEnvelopeEntry`: envolvente transparente **Conservador / Base / Optimista** más comparaciones multi-semilla cuando están disponibles, documentando explícitamente cada parámetro en `parameters_used` y `derivation_note`).

### 2.3 Nivel `EXPERT` (`ExpertReportView`)
- **Auditoría técnica completa**: `execution_metadata` (`execution_id`, `scenario_id`, `seed`, `engine_version`, `active_engines`, `reproducible_parameters`), catálogo completo de indicadores (`all_indicators`), resumen de agentes y reacciones agrupadas (`synthetic_agents_summary`), series y segmentos (`simulation_events_and_segments`), auditoría contable (`transactions_and_accounting`), extrapolaciones de cohorte (`extrapolations`), calidad territorial específica por pregunta (`territorial_sources_and_quality`), metodología y supuestos (`methodology_and_assumptions`), incertidumbre (`uncertainty`), datos faltantes (`missing_data`), limitaciones (`limitations`) y conteo por origen universal (`evidence_origin_counts`).

---

## 3. Sistema Universal de Evidencia y Explicabilidad Contextual (Fases 5 y 6)

### 3.1 Clasificación Universal de Evidencia (`UniversalEvidenceOrigin`)
Implementado en `normalize_evidence_origin()` y `classify_empirical_calibration()` en [progressive_reports.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/progressive_reports.py):

1. `OBSERVED` → `CARTOGRAPHIC_OBSERVED` (cartografía/objetos observados en OSM)
2. `PUBLIC_OFFICIAL` → `PUBLIC_OFFICIAL_APPROX` (catálogo territorial D.L. 762)
3. `ESTIMATED` → `HEURISTIC_UNVERIFIED`
4. `EXTRAPOLATED` → `UNCALIBRATED_SYNTHETIC`
5. `SYNTHETIC_SIMULATED` → `UNCALIBRATED_SYNTHETIC`
6. `DIRECT_SIMULATION_EVENT` → `UNCALIBRATED_SYNTHETIC`
7. `DETERMINISTIC_MULTIPLIER` → `HEURISTIC_UNVERIFIED`
8. `UNAVAILABLE` → `UNAVAILABLE`

Ningún resultado sintético recibe confianza estadística empírica ni se mezcla sin etiqueta explícita entre datos reales, estimaciones y simulaciones.

### 3.2 Explicabilidad Dinámica (`generate_contextual_explanations`)
Ejemplo validado sobre `low_liquidity_agent_share = 0.25` (n = 40 agentes):
- **BASIC**: `"En el grupo de personas simulado, aproximadamente una de cada cuatro tenía menos de $15 disponibles."`
- **EXPERT**: `"El 25% (0.250 ratio) corresponde a la proporción de agentes sintéticos hidratados (n=40) cuya liquidez disponible fue inferior a USD 15 (...). No representa una estimación censal de la población territorial."`

---

## 4. Integración Backend, API REST y Frontend Studio (Fase 7)

- **Esquemas y constructores**:
  - [schemas.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/schemas.py)
  - [progressive_reports.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/progressive_reports.py)
  - [evidence_engine.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/evidence_engine.py) (enriquecimiento universal del 100% de indicadores)
  - [orchestrator.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/orchestrator.py) (adjunta `progressive_report` en `execute_stage_b`)
  - [persistence.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/persistence.py) (`get_execution_by_id`, `get_scenario_by_id`)
  - [__init__.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/__init__.py)
- **API REST en** [conversational_studio_router.py](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/routers/conversational_studio_router.py#L188-L214):
  - `GET /api/studio/executions/{execution_id}/report?level=BASIC|INTERMEDIATE|EXPERT` (HTTP `400` si el nivel es inválido, `404` si el ID no existe).
  - `GET /api/studio/conversations/{conversation_id}` adjunta `progressive_report` en cada ejecución persistida.
- **UI Studio en** [territorial_studio.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/modules/territorial_studio.js) y [studio.css](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/studio.css):
  - Selector de 3 pestañas (`Resumen sencillo` activo por defecto, `Análisis de decisiones`, `Análisis exhaustivo`) tanto para resultados en vivo (`renderStageBResult`) como para historial cargado (`loadConversation` vía `_renderPersistedProgressiveCard`), badges universales `.studio-origin-badge` y exportación Markdown multinivel (`exportMarkdownReport`).

---

## 5. Verificación Automatizada Post-Edición y Grafo de Conocimiento

1. **Sintaxis Frontend**:
   - `node --check "saltbor/visualization/web/modules/territorial_studio.js"` → código de salida `0`.
2. **Suite Conversacional, Inteligencia Territorial y Reportes Progresivos** ([test_progressive_reports.py](file:///c:/GIT%20HUB/sv%20people/tests/test_conversational/test_progressive_reports.py)):
   - `python -m pytest tests/test_conversational/ tests/test_territorial_intelligence/ tests/test_experiments/test_phase117_territorial_experiments.py -v`
   - Resultado observado: **`41 passed in 33.55s`** (`0 failed`, `0 skipped`).
3. **Suite de Regresión Multifase y Rendimiento (Fases 1.14, 1.15, 1.16A, GIS, Territorio, E2E y API)**:
   - `python -m pytest tests/test_gis/ tests/test_visualization/test_studio_frontend_e2e.py tests/test_visualization/test_api_endpoints.py tests/test_territory/ tests/test_experiments/test_phase114_territorial_experiments.py tests/test_experiments/test_phase115_ai_experiments.py tests/test_experiments/test_phase116a_conversational_experiments.py -q`
   - Resultado observado: **`144 passed in 19.59s`** (`0 failed`, `0 skipped`).
4. **Graphify**:
   - `python -m graphify update .` → reconstruido: **`16212` nodos, `44275` aristas, `477` comunidades**.
   - `python -m graphify query "ProgressiveReportBuilder"` → verificados `112` nodos conectados en BFS (`depth=2`) sin advertencias de esquema ni desconexión.
