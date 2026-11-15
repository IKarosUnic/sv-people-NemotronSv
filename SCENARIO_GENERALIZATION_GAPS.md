# BRECHAS DE GENERALIZACIÓN TERRITORIAL (SCENARIO GENERALIZATION GAPS)
## SALTBOR PHASE 1.15 — AUDITORÍA DE EXTENSIBILIDAD GEOGRÁFICA

### 1. Resumen de Brechas Detectadas

| Componente | Estado Pre-Fase 1.15 | Brecha Identificada | Solución Fase 1.15 |
| :--- | :--- | :--- | :--- |
| **Selección de Territorio** | Sesgo hacia Cantón San José Las Flores (Chalatenango). | Faltaba selector dinámico universal con carga automática de infraestructura y perfil demográfico para los 262 distritos y cantones de El Salvador. | `TerritoryCatalogService` y selector dinámico en UI que valida cobertura de datos por cantón/distrito. |
| **Perfil Demográfico y Hogares** | Dos familias fijas (Henríquez y Vásquez) en la demostración de 1.14. | Falta de generación/muestreo de cohortes sintéticas representativas en cualquier cantón sin duplicar identidades persistentes. | Muestreo dinámico de hogares a partir de la distribución demográfica local registrada en `territory_data.py` y `PopulationRegistry`. |
| **Infraestructura de Servicios Públicos** | Puesto de salud y centro escolar cableados en San José Las Flores. | Si un cantón carece de centro de salud registrado, el sistema no reportaba la brecha de accesibilidad ni la distancia a la cabecera distrital. | Reporte explícito de cobertura (`DataCoverageReport`): si no hay clínica local, se computa la fricción hacia la clínica distrital más cercana. |
| **Red de Abastecimiento Comercial** | Una tiendita local ("La Bendición") abastecida desde Chalatenango cabecera. | Falta de resolución automática de la cadena de suministro hacia el mercado mayorista del municipio o cabecera departamental correspondiente. | Resolución jerárquica de la cadena de suministro según la distancia geográfica al mercado central más cercano. |
| **Topografía y Vulnerabilidad a Shocks** | Parámetros de deslizamiento fijos calibrados para la topografía montañosa de Chalatenango Norte. | Cantones costeros o de planicie volcánica tienen riesgos hidrológicos diferentes (inundaciones vs derrumbes). | Tipología de shocks basada en la elevación ($m.s.n.m.$) y relieve extraídos de `physical_geography.py`. |
| **Creación de Escenarios sin Código** | Requería invocar métodos Python específicos o construir JSON crudos. | Los analistas no deben programar una clase Python por cada contingencia territorial. | `NaturalLanguageScenarioBuilder` y `UniversalScenarioEngine` declarativo que compila lenguaje natural a especificación ejecutable. |
