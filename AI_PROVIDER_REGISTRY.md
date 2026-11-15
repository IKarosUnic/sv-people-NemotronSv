# REGISTRO DE PROVEEDORES DE INTELIGENCIA ARTIFICIAL (AI PROVIDER REGISTRY)
## SALTBOR PHASE 1.15 — CATÁLOGO OPERATIVO Y DISPONIBILIDAD

| Identificador | Clase Implementadora | Tipo de Ejecución | Modelos Soportados | Chequeo de Salud | Latencia Típica | Costo por Token |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `OFFLINE_DETERMINISTIC` | `OfflineDeterministicProvider` | Local / Nativo (Python Standard Library) | Reglas semánticas + D.L. 762 | Inmediato (`True`) | $< 1\text{ ms}$ | $\$0.00$ |
| `LOCAL_OLLAMA` | `OllamaProvider` | Local HTTP Daemon (`localhost:11434`) | Llama 3.2, Mistral 7B, Qwen 2.5 | `GET /api/tags` (timeout 1.0s) | $200 - 800\text{ ms}$ | $\$0.00$ |
| `REMOTE_GEMINI` | `RemoteGeminiProvider` | Cloud HTTPS REST | Gemini 1.5 Flash, Gemini 1.5 Pro | Presencia de `GEMINI_API_KEY` | $400 - 1,200\text{ ms}$ | Según cuota Google Cloud |
| `REMOTE_OPENAI` | `RemoteOpenAIProvider` | Cloud HTTPS REST | GPT-4o-mini, GPT-4o | Presencia de `OPENAI_API_KEY` | $500 - 1,500\text{ ms}$ | Según cuota OpenAI |

---

### Verificación de Configuración
- Los proveedores se inicializan mediante `AIModelRouter` en `saltbor/ai/router.py`.
- El endpoint `GET /api/ai/providers/status` expone el estado en tiempo real para la interfaz del observatorio.
