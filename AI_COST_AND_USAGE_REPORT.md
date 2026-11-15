# INFORME DE COSTOS, CONSUMO Y RECURSOS DE IA (AI COST AND USAGE REPORT)
## SALTBOR PHASE 1.15 — EFICIENCIA, PRESUPUESTOS Y CONTABILIDAD DE TOKENS

### 1. Resumen de Consumo Computacional

| Métrica | Modo Determinista Nativo (Default) | Inferencia Ollama Local | Inferencia Remota (Gemini/OpenAI) |
| :--- | :--- | :--- | :--- |
| **Gasto Financiero Directo** | $\$0.00$ USD | $\$0.00$ USD | Sujeto a cuotas autorizadas |
| **Consumo de Tokens** | 0 tokens externos (tokens teóricos estimados) | $200 - 600$ tokens/petición | $250 - 800$ tokens/petición |
| **Latencia Media por Consulta** | $< 0.8\text{ ms}$ | $\approx 420\text{ ms}$ | $\approx 850\text{ ms}$ |
| **Tasa de Aciertos de Caché** | Alta (hash determinista SHA-256) | Alta | Alta |
| **Impacto en Memoria RAM** | $< 2\text{ MB}$ | $2.5 - 5.0\text{ GB}$ (proceso Ollama) | Negligible en host |

---

### 2. Gestión de Presupuestos y Protección

- Implementado en `AIComputeBudgetManager` (`saltbor/ai/budget.py`).
- Parámetros configurables:
  - `max_monthly_budget_usd`: Límite superior de gasto (por defecto $\$10.00$ USD).
  - `max_requests_per_session`: Máximo de llamadas por sesión interactiva (por defecto 500).
  - `enforce_offline_at_budget_exhaustion`: Conmutación obligatoria e instantánea al `OfflineDeterministicProvider` al agotar el presupuesto.
- Caché in-memory con llave criptográfica `SHA-256(task_category + prompt + temp)` que evita llamadas duplicadas para consultas idénticas.
