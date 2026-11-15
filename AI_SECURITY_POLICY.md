# POLÍTICA DE SEGURIDAD Y PRIVACIDAD DE IA (AI SECURITY POLICY)
## SALTBOR PHASE 1.15 — BARRERAS DE AISLAMIENTO, CERO INYECCIÓN Y MINIMIZACIÓN DE DATOS

### 1. Barreras de Seguridad No Negociables

1. **Cero Ejecución de Código Arbitrario**:
   - Las respuestas de los modelos de IA son tratadas como texto no confiable (*untrusted input*).
   - Ninguna cadena retornada por un LLM se evalúa con `eval()`, `exec()`, ni se pasa directamente al intérprete de la shell.
2. **Cero Escritura Directa en Base de Datos**:
   - Los modelos de IA no tienen acceso a conexiones SQLite ni al bus de persistencia.
   - Toda modificación de estado ocurre a través de los métodos transaccionales y auditados de los motores de SALTBOR.
3. **Validación Estricta de Esquemas**:
   - Las configuraciones de escenarios extraídas se validan rigurosamente mediante esquemas Pydantic / dataclasses antes de ser aceptadas por el `AISimulationExecutionController`.

### 2. Protocolo de Minimización de Datos y Privacidad Individual

1. **Encapsulamiento de la Memoria Sintética**:
   - Las memorias episódicas y estados emocionales de los humanos sintéticos (`SyntheticHuman`) se encuentran encapsulados en la partición `INDIVIDUAL_SYNTHETIC_MEMORY`.
   - El subsistema `AIMemoryAndContext` bloquea el acceso de la capa de IA a las memorias privadas individuales (verificado en `EXP_115_X`).
2. **Anonimización en Tránsito**:
   - Si se autoriza el uso de APIs remotas (Gemini u OpenAI), la función `_anonymize_text` filtra y redacta patrones de nombres propios salvadoreños, documentos únicos de identidad (DUI) y direcciones exactas antes de enviar cualquier prompt fuera del host.
3. **Operación Local-First**:
   - Por defecto, todos los datos territoriales y demográficos se procesan localmente sin telemetría ni comunicación saliente.
