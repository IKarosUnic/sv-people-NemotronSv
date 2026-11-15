# INFORME DE GENERALIZACIÓN TERRITORIAL (SCENARIO GENERALIZATION REPORT)
## SALTBOR PHASE 1.15 — INDEPENDENCIA DE CANTÓN Y COBERTURA NACIONAL

### 1. Superación del Sesgo de San José Las Flores

El demostrador de la Fase 1.14 operaba restringido a una única cohorte en Cantón San José Las Flores. En la Fase 1.15:
- Se implementó `TerritoryCatalogService` con cobertura para los **262 distritos oficiales** de El Salvador según el D.L. 762 (Mayo 2024).
- Se habilitó la selección dinámica de cualquier cantón o caserío con resolución automática de jerarquías: Departamento IGN $\rightarrow$ Municipio D.L. 762 $\rightarrow$ Distrito $\rightarrow$ Cantón.
- La prueba de aceptación decisiva se ejecutó de forma autónoma en **Cantón El Rosario / El Refugio**, validando la creación y ejecución de un escenario completo sin código Python dedicado.

---

### 2. Detección de Cobertura y Safeguards

Para evitar extrapolar suposiciones no verificadas a territorios con menor densidad de datos:
1. Cada territorio evaluado recibe un puntaje de calidad de datos (`data_quality_score` de 0.0 a 1.0).
2. Se verifican de forma individual las variables críticas:
   - Censo poblacional georreferenciado.
   - Puestos de salud o UCSF locales (o distancia a cabecera).
   - Centros escolares de educación básica y media.
   - Red de abarroterías y nodos comerciales.
3. El sistema enumera explícitamente `missing_variables` e `uncertainties` en la respuesta de la API y en la interfaz web, asegurando honestidad epistémica ante el investigador.
