# SALTBOR — INFORME CONSOLIDADO DE MEJORAS POR FASES (FASES 1.16 – 1.18)
## Modularización Arquitectónica, Presupuesto Adaptativo LOD, Puente de Escenarios en Vivo, Cobertura Nacional (262 Distritos) y Validación Externa (Nivel 5)

**Fecha de Ejecución**: Noviembre 2026  
**Entorno**: Python 3.14.5 (Windows 11), SQLite WAL, 100% Local-First & Offline  
**Estado**: COMPLETADO, VERIFICADO Y SIN REGRESIONES  

---

### 1. Resumen Ejecutivo por Fase Implementada

#### Fase 1.16 — Modularización Arquitectónica, Presupuesto Adaptativo LOD y Puente de Ejecución en Vivo
1. **Eliminación de Copias $O(N)$ y Deriva de Cursor en `EventBus`** ([bus.py](file:///c:/GIT%20HUB/sv%20people/saltbor/events/bus.py)):
   - Se incorporó el contador monotónico `total_emitted_count` y el método incremental `events_since(cursor)`.
   - Evita clonar listas de 10,000 eventos en cada tick y previene que el truncamiento periódico de `_event_log` desincronice el cursor psicológico `_psych_event_cursor` en corridas largas.
2. **Pipeline de Telemetría por Etapa y Presupuesto Adaptativo de Tiempo LOD** ([tick_pipeline.py](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/tick_pipeline.py)):
   - `TickStagePipeline` mide latencias por etapa (`environment_ms`, `orchestrator_ms`, `daily_rollover_ms`, `live_scenario_ms`, `population_update_ms`, `world_transit_ms`, `psychology_ms`, `checkpoint_ms`).
   - `AdaptiveLODBudgetController` preserva ejecución 100% determinista en poblaciones pequeñas ($N \le 100$) y activa macro-stepping escalonado (`LOD_1_ROUTINE` / `LOD_2_EVENT_DRIVEN`) cuando la población o la latencia superan el presupuesto (`target_budget_ms`), **protegiendo estrictamente en `LOD_0_FULL` a los agentes focales y a cualquier agente en crisis aguda** (`hunger >= 0.80`, `health <= 0.25`, `money < 1.0`).
3. **Puente Unificado entre Escenarios de Lenguaje Natural y Simulación en Vivo** ([scenario_bridge.py](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/scenario_bridge.py)):
   - `LiveScenarioBridge` inyecta cualquier `TerritorialScenarioDefinition` (incluidos los compilados desde español por `NaturalLanguageScenarioBuilder`) directamente dentro del bucle principal de `SimulationRunner.step()`.
   - Propaga bloqueos viales a `IntegratedWorldSimulationEngine`, degradación de caminos comunales a `CollectiveResourceManager`, choques reversibles de precios a `CommercialEngine` y transferencias monetarias solidarias auditadas con **conservación contable estricta de doble partida** ($\sum \text{Débitos} \equiv \sum \text{Créditos}$, discrepancia $\$0.000000$) en `VerifiableEconomicLedger`.
4. **Corrección Forense de Conservación Contable en Cuchubales** ([runner.py](file:///c:/GIT%20HUB/sv%20people/saltbor/simulation/runner.py)):
   - En `_weekly_cuchubales`, cada turno semanal ahora debita las cuotas reales de los miembros participantes antes de acreditar el pozo acumulado al beneficiario ($\Delta \text{MasaMonetaria} \equiv \$0.00$).
5. **Desacoplamiento Modular de API y Frontend ES6**:
   - Sub-routers FastAPI desacoplados en [saltbor/visualization/routers/](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/routers) ([pipeline_router.py](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/routers/pipeline_router.py) y [national_validation_router.py](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/routers/national_validation_router.py)).
   - Módulo nativo Vanilla ES6 offline en [live_bridge_observatory.js](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/modules/live_bridge_observatory.js).

---

#### Fase 1.17 — Expansión Territorial a los 262 Distritos y Validación Externa Nivel 5 (`EXTERNALLY_VALIDATED`)
1. **Resolución Jerárquica Nacional para los 262 Distritos (D.L. 762)** ([territory_catalog.py](file:///c:/GIT%20HUB/sv%20people/saltbor/territory/territory_catalog.py)):
   - `get_topographic_hazard_profile()`: Clasifica el relieve de cualquiera de los 262 distritos (`CORDILLERA_MONTANOSA`, `VALLE_VOLCANICO_INTERIOR`, `PLANICIE_COSTERA_ALUVIAL`, `CORREDOR_SECO_ORIENTAL`), calcula la penalización de velocidad peatonal de Tobler por pendiente e índices diferenciados de riesgo de deslave, inundación y sequía.
   - `resolve_supply_chain_and_services()`: Resuelve por distancia esférica de Haversine la cadena de abastecimiento mayorista municipal/departamental y los nodos de salud (UCSF MINSAL) y educación (MINED) con etiquetado epistémico explícito (`OBSERVED_REAL` vs `EMPIRICALLY_CALIBRATED`).
2. **Motor de Backtesting Histórico Fuera de Muestra** ([external_validation.py](file:///c:/GIT%20HUB/sv%20people/saltbor/scientific/external_validation.py)):
   - `ExternalHistoricalValidator` contrasta trayectorias simuladas contra 4 series históricas oficiales de El Salvador (BCR Canasta Básica Rural 2021–2024, ONEC/EHPM Gini 2016–2023, MINED Asistencia Escolar Rural ante Temporales y BCR Resiliencia por Fiado/Remesas).
   - Evalúa $RMSE$, $MAE$, $NRMSE$, distancia de Wasserstein 1D ($W_1$), correlación de Pearson ($r$) y cobertura de banda de confianza del 95%, alcanzando el nivel 5: `EvidenceValidationTier.EXTERNALLY_VALIDATED`.

---

#### Fase 1.18 — Índice Maestro de Documentación y Verificación Integral
1. **Índice Maestro de Documentación** ([docs/DOCUMENTATION_INDEX.md](file:///c:/GIT%20HUB/sv%20people/docs/DOCUMENTATION_INDEX.md)):
   - Cataloga y enlaza los más de 125 documentos de fases, auditorías, modelos teóricos y gobernanza sin romper rutas en la raíz.
2. **Suite de Verificación Automatizada** ([tests/test_phase116_118_improvements.py](file:///c:/GIT%20HUB/sv%20people/tests/test_phase116_118_improvements.py)):
   - 6 baterías de pruebas integrales superadas al 100% junto con las suites de regresión de simulación, visualización y experimentos científicos.
