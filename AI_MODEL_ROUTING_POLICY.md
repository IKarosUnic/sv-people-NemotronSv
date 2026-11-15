# POLÍTICA DE ENRUTAMIENTO DE MODELOS DE INTELIGENCIA ARTIFICIAL (AI MODEL ROUTING POLICY)
## SALTBOR PHASE 1.15 — SELECCIÓN DINÁMICA, PRIORIDADES Y FALLBACK

### 1. Matriz de Enrutamiento por Complejidad y Categoría de Tarea

| Categoría de Tarea | Prioridad 1 | Prioridad 2 | Fallback Incondicional | Racionalidad Científica |
| :--- | :--- | :--- | :--- | :--- |
| **`SCENARIO_EXTRACTION`** | Proveedor Local Ollama | Remoto (si autorizado) | `OfflineDeterministicProvider` | Extracción de variables declarativas estructuradas sin riesgo de alucinación. |
| **`GEOGRAPHIC_VALIDATION`** | `TerritoryCatalogService` (Nativo) | N/A | N/A | Exclusivamente validado contra el registro oficial salvadoreño D.L. 762. |
| **`CAUSAL_PROPOSAL`** | Catálogo Científico SALTBOR | Ollama / Remoto | `AICausalOrchestrationAssistant` | Prohibido inventar relaciones físicas o deltas numéricos sin respaldo. |
| **`POLICY_PLANNING`** | Remoto (si autorizado) | Ollama Local | `OfflineDeterministicProvider` | Generación de hipótesis alternativas comparables. |
| **`RESULTS_ANALYSIS`** | Híbrido: Métricas Reales + LLM | Ollama Local | `OfflineDeterministicProvider` | Toda cifra numérica debe provenir del log de simulación o del ledger contable. |
| **`COUNTERFACTUAL_COMPARISON`** | `GeneralizedTerritorialScenarioEngine` | N/A | N/A | Comparación analítica de indicadores entre ramas base, choque y recuperación. |

---

### 2. Algoritmo de Conmutación por Error (Failover)

1. Si el usuario fijó un proveedor específico (`preferred_provider`) y este se encuentra disponible y dentro del presupuesto, se envía la solicitud.
2. Si falla la ejecución o se agota el timeout, se reintenta automáticamente con el siguiente proveedor disponible en la cadena de prioridad.
3. Si los servicios remotos o locales están apagados o desconectados, la solicitud es resuelta por el `OfflineDeterministicProvider` en $< 1\text{ ms}$.
4. La simulación jamás se detiene por falta de disponibilidad de un modelo de lenguaje.
