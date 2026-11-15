# AUDITORÍA TÉCNICA Y ESTRUCTURAL — FASE 1.15
## CAPA DE INTELIGENCIA ARTIFICIAL, GENERACIÓN UNIVERSAL DE ESCENARIOS Y ORQUESTACIÓN AUTÓNOMA

**Fecha de Ejecución**: Noviembre 2026  
**Sistema**: SALTBOR Multi-Scale Territorial Simulation Platform  
**Entorno de Ejecución**: Python 3.14.5 (Windows 11 host), SQLite WAL Mode, 100% Offline / Local-First  
**Referencia Cartográfica y Administrativa**: República de El Salvador, D.L. 762 (14 Departamentos, 44 Municipios, CNR / IGN 2024)  
**Herramienta de Análisis Estructural**: Graphify (14,542 nodos, 41,543 aristas, 427 comunidades)  

---

### 1. Resumen Ejecutivo de la Auditoría

En cumplimiento estricto del mandato de la Sección 2 ("Non-Negotiable Initial Audit"), se realizó una inspección forense integral del repositorio antes de iniciar cualquier desarrollo de código nuevo.

El sistema SALTBOR completó en la Fase 1.14 y en los primeros componentes de la Fase 1.15 la integración de motores territoriales desacoplados:
- `CrossDomainInteractionEngine`
- `MultiScaleTerritorialSimulationEngine`
- `RegionalEconomicNetworkEngine`
- `PublicServiceCapacityEngine`
- `CollaborativeGovernanceEngine`
- `GeneralizedTerritorialScenarioEngine`
- `VerifiableEconomicLedger`
- `CausalTraceEngine`
- `SharedEntityConsistencyValidator`
- `HumanBehaviorHeterogeneityEngine`

Sin embargo, existía una brecha decisiva entre la definición programática de escenarios y la interacción en lenguaje natural asistida por IA:
1. **Ausencia de una Capa de Inteligencia Artificial Unificada**: Solo existían interfaces abstractas y desactivadas en `saltbor/llm/` (`LLMAdapter`, `OllamaAdapter`, `LocalModelAdapter`, `ExternalAPIAdapter`).
2. **Definición de Escenarios Aún Declarativa/Estructural**: Para ejecutar un nuevo escenario en un cantón diferente de San José Las Flores sin programar una clase Python, el usuario debía ingresar manualmente JSONs de `shocks` e `interventions` o usar código Python interactivo.
3. **Falta de Traductor de Lenguaje Natural a Escenario Estructurado**: No existía un `NaturalLanguageScenarioBuilder` capaz de parsear descripciones en lenguaje natural, extraer variables territoriales, consultar cobertura de datos y formular especificaciones reproducibles.
4. **Falta de Enrutamiento Inteligente y Fallback Offline Total**: La plataforma requiere operar de manera determinista aún cuando ningún LLM esté disponible o cuando Ollama/OpenAI/Gemini no estén accesibles.

---

### 2. Inspección Detallada por Subsistema

#### 2.1 Integraciones de IA y Clientes de Modelos Existentes
- **`saltbor/llm/adapter.py`**:
  - `LLMAdapter` (clase abstracta con `is_available()` y `generate()`).
  - `NullAdapter` (retorna cadenas vacías, seguro para ejecución offline).
  - `OllamaAdapter` (cliente HTTP nativo vía `urllib.request` apuntando por defecto a `http://localhost:11434/api/generate`, sin dependencias externas).
- **`saltbor/llm/interfaces/ai_layer.py`**:
  - `PromptContext`, `ModelResponse`, `ModelProviderInterface`.
  - Adaptadores deshabilitados (`LocalModelAdapter`, `ExternalAPIAdapter`).
  - `ContextBuilder` incompleto.
- **Auditoría de Entorno**: En el host actual, `Ollama` no se encuentra en ejecución y no hay claves de entorno fijadas (`GEMINI_API_KEY` o `OPENAI_API_KEY`). El subsistema debe garantizar el 100% de funcionalidad con un motor heurístico/semántico determinista local (`OfflineDeterministicProvider`) que cumpla las especificaciones sin degradar la simulación.

#### 2.2 Arquitectura de API Existente (`saltbor/visualization/api.py`)
- Cuenta con 164 endpoints REST basados en FastAPI y Pydantic.
- Dispone de endpoints de alto nivel para escenarios:
  - `GET /territory/scenarios/list`
  - `POST /territory/scenarios/create`
  - `POST /territory/scenarios/run`
  - `GET /territory/scenarios/compare`
  - `GET /territory/scenarios/ledger`
  - `GET /territory/scenarios/trace`
  - `GET /territory/scenarios/entities`
  - `GET /territory/scenarios/population_analysis`
  - `GET /territory/scenarios/provenance`
- **Gaps en API**:
  - No existen endpoints para `/ai/scenarios/build_natural_language`, `/ai/providers/status`, `/ai/causal/suggest`, `/ai/results/analyze` ni `/ai/scenarios/plan`.

#### 2.3 Motores de Simulación Territorial Conectados
- `GeneralizedTerritorialScenarioEngine` (`saltbor/territory/generalized_scenarios.py`):
  - 1,310 líneas de lógica declarativa basada en ticks.
  - Orquesta shocks viales, inundaciones, sequías, inflación de alimentos, despidos laborales, sobrecargas de clínicas.
  - Conecta el balance contable de doble partida (`VerifiableEconomicLedger`).
  - Conservación absoluta: $\sum \text{Debits} \equiv \sum \text{Credits}$.
- `CrossDomainInteractionEngine` (`saltbor/territory/cross_domain.py`):
  - Fórmulas analíticas de transporte $\rightarrow$ comercio $\rightarrow$ educación $\rightarrow$ salud.
- `MultiScaleTerritorialSimulationEngine` (`saltbor/territory/multi_scale.py`):
  - Jerarquía espacial (Individuo, Hogar, Empresa/Institución, Comunidad, Municipio D.L. 762, Departamento IGN).

#### 2.4 Sistemas Causales y de Eventos
- `CausalTraceEngine` (`saltbor/territory/causal_trace.py`):
  - Grafo DAG con 4 niveles epistémicos: `EXPLICIT_MECHANISM`, `OBSERVED_ASSOCIATION`, `CAUSAL_HYPOTHESIS`, `EMPIRICAL_EVIDENCE`.
  - Detección de ciclos y orden topológico garantizado.
- `saltbor/events/bus.py` y `causal_graph.py`: Bus desacoplado de eventos pub/sub.

#### 2.5 Datos Geográficos e Integración Poblacional
- `saltbor/datasets/salvadoran/territory_data.py`:
  - 14 departamentos, 44 municipios oficiales (D.L. 762), 262 distritos, cantones y caseríos reales.
  - Coordenadas geográficas, altitudes, población aproximada.
- `saltbor/datasets/salvadoran/establishments_data.py` y `departments.py`:
  - Directorio comercial, de salud y educación.
- **Cobertura Territorial**: San José Las Flores cuenta con datos detallados; otros cantones (como El Rosario, San Gerardo, Arcatao, Dulce Nombre de María, etc.) cuentan con perfiles a nivel de distrito y coordenadas, pero requieren detección explícita de cobertura de datos para evitar suposiciones no verificadas.

#### 2.6 Cobertura y Frescura de Graphify
- Estado inicial: 14,515 nodos (commit `81317d74`).
- Estado actualizado mediante `graphify update .`: 14,542 nodos, 41,543 aristas, 427 comunidades.
- Herramienta totalmente operativa para el mapeo de dependencias e impacto estructural.

---

### 3. Identificación de Brechas (Gaps) y Suposiciones

1. **Suposición de Cantón Específico**: Aunque el motor `GeneralizedTerritorialScenarioEngine` soporta parámetros para cualquier cantón, la UI frontend preseleccionaba `Cantón San José Las Flores`.
2. **Brecha de Inferencia Semántica**: La traducción de lenguaje natural no debe requerir APIs de pago externas para pruebas de regresión automáticas y entornos sin conexión a Internet.
3. **Validación de Causalidad**: Es imperativo rechazar mecanismos causales no fundamentados como `HYPOTHESIS_PENDING_VALIDATION` y evitar la creación de efectos numéricos arbitrarios.
4. **Contabilidad Rigurosa**: La integración de la IA debe mantenerse como una capa de consulta y orquestación asistida; **jamás** debe tener permisos de escritura directa en la base de datos o en los saldos del `VerifiableEconomicLedger`.

---

### 4. Veredicto y Siguientes Pasos

La arquitectura de SALTBOR se encuentra sólida y lista para incorporar la capa `SALTBOR_AI_INTELLIGENCE_LAYER`. Se procede con la elaboración de los 4 documentos complementarios exigidos por la Sección 2.3 antes del diseño e implementación del código.
